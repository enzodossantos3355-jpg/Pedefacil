from urllib.parse import quote_plus
import io
import json
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pymongo import ReturnDocument

from lib.ai import wa_send, wa_send_later
from lib.dates import today_iso
from lib.access import check_limit, has_feature, need
from lib.db import db, raw_db

from lib.geo import coords_from_text, geocode_address, quote_fee_full
from lib.pix import gerar_pix
from lib.tastes import all_profiles
from models.domain import (
    LEGACY_STATUS, STATUS_FLOW, Courier, CourierCreate, Customer, CustomerCreate, DashboardSummary, DayOpenRequest, DayStatus,
    DeliveryZone, DeliveryZoneCreate, FeeQuote, FeeQuoteResult, Order, OrderCreate, OrderUpdate, Product,
    AppNotification, CourierEarning, DayClose, DayCloseDetail, ReportLine, PixCharge, ProductCreate, ReportSummary, StatusUpdate, StoreSettings, new_id,
)
import os

router = APIRouter(tags=["operations"])
IMG = [
    "https://images.pexels.com/photos/30635705/pexels-photo-30635705.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
    "https://images.pexels.com/photos/30635717/pexels-photo-30635717.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
]
STATUS_MESSAGES = {
    "Em Preparo": "👩‍🍳 Seu pedido #{id} está sendo preparado.",
    "Pronto": "🍱 Seu pedido #{id} está pronto!",
    "Em Entrega": "🛵 Seu pedido #{id} saiu para entrega e logo chega até você!",
    "Concluído": "🙏 Pedido #{id} concluído. Obrigado pela preferência, bom apetite!",
    "Cancelado": "Seu pedido #{id} foi cancelado. Se precisar, estamos à disposição.",
}
BACKUP_COLLECTIONS = ["products", "orders", "customers", "delivery_zones", "store_settings", "couriers", "chats", "day_closes"]


async def require_open_day() -> None:
    """Orders, PDV, AI and attendance only work while the cash register (caixa) is open."""
    day = await db.day_status.find_one({}) or {}
    if day.get("is_open") is False:
        raise HTTPException(status_code=409, detail="Dia fechado. Comece um novo dia para operar.")


OPEN_DAY = [Depends(require_open_day)]


async def get_settings() -> dict:
    return StoreSettings(**(await db.store_settings.find_one({}) or {})).model_dump()


def is_today(dt: datetime, ref: str) -> bool:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d") >= ref  # pod clock is UTC; good enough for "today"


async def all_orders() -> list[Order]:
    return [Order(**d) for d in await db.orders.find().sort("created_at", -1).to_list(2000)]


def metrics(orders: list[Order]) -> dict:
    today = today_iso()
    month = today[:7]
    valid = [o for o in orders if o.status != "Cancelado"]
    today_valid = [o for o in valid if o.created_at.strftime("%Y-%m-%d") == today] or valid
    revenue = sum(o.total for o in today_valid)
    fees = [o.delivery_fee for o in valid if o.delivery_type == "Entrega"]
    return {
        "today": today,
        "revenue": revenue,
        "month_revenue": sum(o.total for o in valid if o.created_at.strftime("%Y-%m") == month) or sum(o.total for o in valid),
        "avg_ticket": revenue / len(today_valid) if today_valid else 0,
        "avg_fee": sum(fees) / len(fees) if fees else 0,
        "valid": valid,
    }


@router.get("/dashboard", response_model=DashboardSummary)
async def dashboard():
    orders = await all_orders()
    m = metrics(orders)
    active = [o for o in orders if o.status in STATUS_FLOW[:5]]  # Em Análise → Em Entrega
    settings = await get_settings()
    return DashboardSummary(today=m["today"], revenue=m["revenue"], month_revenue=m["month_revenue"], total_orders=len(orders), active_orders=len(active), average_ticket=m["avg_ticket"], average_fee=m["avg_fee"], open_orders=len(active), accepting_orders=settings["accepting_orders"], recent_orders=orders[:6])


@router.get("/orders", response_model=list[Order])
async def list_orders():
    """Only the current (not yet archived) day; archived days live in Armazenamento."""
    return [Order(**d) for d in await db.orders.find({"archived": {"$ne": True}}).sort("created_at", -1).to_list(2000)]


async def pix_code_for(total: float, order_id: str) -> str:
    """Pix BR Code mode: every order total gets its own static Pix Copia e Cola (txid = order id)."""
    settings = await get_settings()
    if settings["pix_mode"] != "brcode" or not has_feature("pix_qr"):
        return ""
    pix = await gerar_pix(total, order_id, settings)
    return pix["copiaECola"] if pix else ""


async def create_order_record(input: OrderCreate) -> Order:
    subtotal = sum(i.price * i.quantity for i in input.items)
    fee, zone_name = 0.0, ""
    if input.delivery_type == "Entrega":  # Retirada and Mesa never pay delivery
        if input.delivery_fee is not None:
            fee = input.delivery_fee
        else:
            q = await quote_fee_full(await db.delivery_zones.find().to_list(500), await get_settings(), input.latitude, input.longitude, input.address)
            fee, zone_name = q["fee"], q["zone_name"]
    zone_name = zone_name or (input.zone_name if input.delivery_type == "Entrega" else "")
    order = Order(**input.model_dump(exclude={"delivery_fee", "zone_name"}), subtotal=subtotal, delivery_fee=fee, zone_name=zone_name, total=round(max(0.0, subtotal + fee + input.surcharge - input.discount), 2))
    if len(order.payments) == 2:  # second part is always the remainder of the final total (fee included)
        order.payments[1].amount = round(max(0.0, order.total - order.payments[0].amount), 2)
    if order.payments and order.source != "whatsapp":
        order.payment_method = " + ".join(p.method for p in order.payments)
    if order.source != "whatsapp" and order.payment_method != "Pendente":
        order.payment_status = "pago"  # staff chose the method at the counter
    order.pix_copia_e_cola = await pix_code_for(order.total, order.order_id)
    await db.orders.insert_one(order.model_dump())
    for item in input.items:  # automatic stock decrement
        await db.products.update_one({"product_id": item.product_id, "stock": {"$ne": None}}, {"$inc": {"stock": -item.quantity}})
        await db.products.update_one({"product_id": item.product_id, "stock": {"$lte": 0}}, {"$set": {"stock": 0, "active": False}})
    if input.customer_phone:
        update = {"$set": {"name": input.customer_name, "phone": input.customer_phone, "address": input.address or ""}, "$inc": {"orders_count": 1, "total_spent": order.total}, "$setOnInsert": {"customer_id": new_id("cust"), "notes": "", "preferences": []}}
        if input.address:
            update["$addToSet"] = {"addresses": input.address}
        await db.customers.update_one({"phone": input.customer_phone}, update, upsert=True)
    return order


@router.post("/orders", response_model=Order, dependencies=OPEN_DAY)
async def create_order(input: OrderCreate):
    await check_limit("orders", await db.orders.count_documents({}))
    return await create_order_record(input)


@router.put("/orders/{order_id}", response_model=Order, dependencies=OPEN_DAY)
async def update_order(order_id: str, input: OrderUpdate):
    current = await db.orders.find_one({"order_id": order_id})
    if not current:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    data = input.model_dump(exclude_none=True)
    if data.get("payments") and current.get("source") != "whatsapp":  # staff split: shown as "Pix + Dinheiro" (paid)
        data["payment_method"] = " + ".join(p["method"] for p in data["payments"])
    if data.get("payment_method", "Pendente") != "Pendente" and "payment_status" not in data:
        data["payment_status"] = "pago"  # staff set the method in the panel
    items = data.get("items", current["items"])
    fee = data.get("delivery_fee", current.get("delivery_fee", 0))
    data["subtotal"] = sum(i["price"] * i["quantity"] for i in items)
    data["total"] = round(max(0.0, data["subtotal"] + fee + data.get("surcharge", current.get("surcharge", 0)) - data.get("discount", current.get("discount", 0))), 2)
    pays = data.get("payments") or current.get("payments") or []
    if len(pays) == 2:
        pays[1]["amount"] = round(max(0.0, data["total"] - pays[0]["amount"]), 2)
        data["payments"] = pays
    if data["total"] != current.get("total"):
        data["pix_copia_e_cola"] = await pix_code_for(data["total"], order_id)
    updated = await db.orders.find_one_and_update({"order_id": order_id}, {"$set": data}, return_document=ReturnDocument.AFTER)
    if "status" in data and data["status"] != current["status"]:
        await notify_status(Order(**updated), current["status"])
    return Order(**updated)


APPROVED_MESSAGE = "✅ Seu pedido #{id} foi confirmado pela loja e já está na fila da cozinha!"


async def notify_status(order: Order, previous: str = "") -> None:
    settings = await get_settings()
    # "Novo" is only announced when the store approves an AI order that was "Em Análise"
    template = APPROVED_MESSAGE if order.status == "Novo" and previous == "Em Análise" else STATUS_MESSAGES.get(order.status)
    if settings["notify_status_changes"] and template and order.customer_phone and has_feature("whatsapp_ia"):
        text = template.format(id=order.order_id[-6:].upper())
        if order.status == "Concluído":
            platform = await raw_db.platform_settings.find_one({}) or {}
            footer = platform.get("footer_text") or "Atendimento feito com PedeFácil"
            text += f"\n\n✨ {footer}" + (f"\n{platform['site_url']}" if platform.get("site_url") else "")
        chat = await db.chats.find_one({"phone": order.customer_phone}) or {}
        wa_send_later(chat.get("jid") or order.customer_phone, text)


@router.get("/notifications", response_model=list[AppNotification])
async def notifications():
    """Panel bell: new orders waiting, conversations asking for a human, Pix receipts to check."""
    out: list[AppNotification] = []
    for o in await db.orders.find({"status": {"$in": ["Em Análise", "Novo"]}, "archived": {"$ne": True}}).sort("created_at", -1).to_list(30):
        out.append(AppNotification(id=f"o-{o['order_id']}-{o['status']}", kind="new_order", title=f"Pedido #{o['order_id'][-6:].upper()} · {o['status']}", detail=f"{o['customer_name']} · R$ {o['total']:.2f}", link="/pedidos", created_at=o["created_at"]))
    for o in await db.orders.find({"payment_status": "em_verificacao", "archived": {"$ne": True}}).to_list(30):
        out.append(AppNotification(id=f"r-{o['order_id']}", kind="receipt", title=f"Comprovante para conferir · #{o['order_id'][-6:].upper()}", detail=o.get("receipt_note", "")[:120], link="/pedidos", created_at=o["created_at"]))
    for c in await db.chats.find({"status": "needs_human"}).to_list(30):
        out.append(AppNotification(id=f"h-{c['chat_id']}-{len(c.get('messages', []))}", kind="needs_human", title=f"{c['customer_name']} pediu um atendente", detail=c.get("last_message", "")[:120], link="/atendimento", created_at=c.get("last_timestamp") or c.get("created_at")))
    return sorted(out, key=lambda n: n.created_at, reverse=True)


@router.post("/orders/{order_id}/send-courier", dependencies=[need("motoboys")])
async def send_to_courier(order_id: str):
    """Sends the delivery sheet (with the customer's GPS route) to the assigned courier's WhatsApp."""
    order = await db.orders.find_one({"order_id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    courier = await db.couriers.find_one({"courier_id": order.get("courier_id", "")}) if order.get("courier_id") else None
    if not courier or not courier.get("phone"):
        raise HTTPException(status_code=422, detail="Atribua um entregador com telefone ao pedido.")
    route = (f"https://www.google.com/maps/dir/?api=1&destination={order['latitude']},{order['longitude']}" if order.get("latitude") is not None
             else f"https://www.google.com/maps/search/?api=1&query={quote_plus(order.get('address', ''))}")
    items = "\n".join(f"• {i['quantity']}x {i['name']}{' ' + i['size'] if i.get('size') else ''}" for i in order["items"])
    if order.get("payment_status") == "pago":
        pay = f"✅ JÁ PAGO ({order.get('payment_method') or 'Pix'}) — não cobrar"
    else:
        how = order.get("payment_intent") or (order.get("payment_method") if order.get("payment_method") != "Pendente" else "") or "a combinar"
        pay = f"💵 COBRAR NA ENTREGA R$ {order['total']:.2f} • {how}"
        if order.get("payments"):  # split: Pix part may already be paid, only the rest is collected
            pay = "💵 PAGAMENTO DIVIDIDO: " + " + ".join(f"{p['method']} R$ {p['amount']:.2f}" for p in order["payments"])
    notes = f"\n📝 Obs: {order['notes']}" if order.get("notes") else ""
    text = (f"🛵 ENTREGA #{order_id[-6:].upper()}\n👤 {order['customer_name']}\n📞 {order.get('customer_phone') or 'sem telefone'}\n"
            f"📍 {order.get('address') or 'ver localização'}\n🗺️ Localização: {route}\n\n🍱 Pedido:\n{items}{notes}\n\n{pay}\n🧾 Total R$ {order['total']:.2f} (taxa R$ {order.get('delivery_fee', 0):.2f})")
    if not await wa_send(courier["phone"], text):
        raise HTTPException(status_code=409, detail="WhatsApp da loja desconectado. Conecte em Configurações.")
    return {"ok": True}


@router.patch("/orders/{order_id}/status", response_model=Order, dependencies=OPEN_DAY)
async def update_order_status(order_id: str, input: StatusUpdate):
    if input.status not in STATUS_FLOW:
        raise HTTPException(status_code=422, detail="Status inválido.")
    previous = (await db.orders.find_one({"order_id": order_id}, {"status": 1}) or {}).get("status", "")
    updated = await db.orders.find_one_and_update({"order_id": order_id}, {"$set": {"status": input.status}}, return_document=ReturnDocument.AFTER)
    if not updated:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    order = Order(**updated)
    await notify_status(order, previous)
    if order.status == "Em Entrega" and order.courier_id:  # leaving for delivery: sheet goes to the courier automatically
        try:
            await send_to_courier(order_id)
        except HTTPException:
            pass
    return order


@router.post("/orders/{order_id}/approve", response_model=Order, dependencies=OPEN_DAY)
async def approve_order(order_id: str):
    return await update_order_status(order_id, StatusUpdate(status="Novo"))


@router.get("/orders/{order_id}/pix", response_model=PixCharge)
async def order_pix(order_id: str):
    order = await db.orders.find_one({"order_id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    pix = await gerar_pix(order["total"], order_id, await get_settings())
    if not pix:
        raise HTTPException(status_code=422, detail="Configure a chave Pix, o favorecido e a cidade em Configurações.")
    return PixCharge(copia_e_cola=pix["copiaECola"], qr_code_base64=pix["qrCodeBase64"], valor=pix["valor"], txid=pix["txid"])


@router.delete("/orders/{order_id}", dependencies=OPEN_DAY)
async def delete_order(order_id: str):
    if not (await db.orders.delete_one({"order_id": order_id})).deleted_count:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    return {"ok": True}


@router.get("/products", response_model=list[Product])
async def list_products():
    return [Product(**d) for d in await db.products.find().sort("name", 1).to_list(1000)]


@router.post("/products", response_model=Product)
async def create_product(input: ProductCreate):
    await check_limit("products", await db.products.count_documents({}))
    product = Product(**input.model_dump())
    await db.products.insert_one(product.model_dump())
    return product


@router.put("/products/{product_id}", response_model=Product)
async def update_product(product_id: str, input: ProductCreate):
    updated = await db.products.find_one_and_update({"product_id": product_id}, {"$set": input.model_dump()}, return_document=ReturnDocument.AFTER)
    if not updated:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    return Product(**updated)


@router.delete("/products/{product_id}")
async def delete_product(product_id: str):
    if not (await db.products.delete_one({"product_id": product_id})).deleted_count:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    return {"ok": True}


@router.get("/customers", response_model=list[Customer])
async def list_customers():
    profiles = await all_profiles()
    return [Customer(**{**d, **profiles.get(d.get("phone", ""), {})}) for d in await db.customers.find().sort("name", 1).to_list(2000)]


@router.post("/customers", response_model=Customer)
async def create_customer(input: CustomerCreate):
    await check_limit("customers", await db.customers.count_documents({}))
    customer = Customer(**input.model_dump(), addresses=[input.address] if input.address else [])
    await db.customers.insert_one(customer.model_dump())
    return customer


@router.put("/customers/{customer_id}", response_model=Customer)
async def update_customer(customer_id: str, input: CustomerCreate):
    updated = await db.customers.find_one_and_update({"customer_id": customer_id}, {"$set": input.model_dump()}, return_document=ReturnDocument.AFTER)
    if not updated:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    return Customer(**updated)


@router.delete("/customers/{customer_id}")
async def delete_customer(customer_id: str):
    if not (await db.customers.delete_one({"customer_id": customer_id})).deleted_count:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    return {"ok": True}


@router.get("/store/status", response_model=StoreSettings)
async def get_store():
    return StoreSettings(**await get_settings())


@router.put("/store/status", response_model=StoreSettings)
async def update_store(input: StoreSettings):
    current = await get_settings()
    if input.store_maps_url and input.store_maps_url != current["store_maps_url"]:
        coords = await coords_from_text(input.store_maps_url)
        if coords:
            input.store_lat, input.store_lng = coords
    elif input.store_address != current["store_address"] or input.store_lat is None:
        coords = await geocode_address(input.store_address)
        if coords:
            input.store_lat, input.store_lng = coords
    updated = await db.store_settings.find_one_and_update({}, {"$set": input.model_dump()}, upsert=True, return_document=ReturnDocument.AFTER)
    return StoreSettings(**updated)


@router.post("/store/toggle-accepting", response_model=StoreSettings)
async def toggle_store():
    current = await get_store()
    current.accepting_orders = not current.accepting_orders
    return await update_store(current)


@router.get("/delivery-zones", response_model=list[DeliveryZone])
async def list_zones():
    return [DeliveryZone(**d) for d in await db.delivery_zones.find().to_list(500)]


@router.post("/delivery-zones", response_model=DeliveryZone, dependencies=[need("zonas")])
async def create_zone(input: DeliveryZoneCreate):
    zone = DeliveryZone(**input.model_dump())
    await db.delivery_zones.insert_one(zone.model_dump())
    return zone


@router.put("/delivery-zones/{zone_id}", response_model=DeliveryZone, dependencies=[need("zonas")])
async def update_zone(zone_id: str, input: DeliveryZoneCreate):
    updated = await db.delivery_zones.find_one_and_update({"zone_id": zone_id}, {"$set": input.model_dump()}, return_document=ReturnDocument.AFTER)
    if not updated:
        raise HTTPException(status_code=404, detail="Região não encontrada.")
    return DeliveryZone(**updated)


@router.delete("/delivery-zones/{zone_id}", dependencies=[need("zonas")])
async def delete_zone(zone_id: str):
    await db.delivery_zones.delete_one({"zone_id": zone_id})
    return {"ok": True}


@router.post("/delivery-zones/quote", response_model=FeeQuoteResult)
async def quote_zone(input: FeeQuote):
    return FeeQuoteResult(**await quote_fee_full(await db.delivery_zones.find().to_list(500), await get_settings(), input.latitude, input.longitude, input.text))


@router.get("/couriers", response_model=list[Courier])
async def list_couriers():
    today = today_iso()
    couriers = [Courier(**d) for d in await db.couriers.find().sort("name", 1).to_list(500)]
    current = [Order(**o) for o in await db.orders.find({"archived": {"$ne": True}}).to_list(5000)]
    by_id = {e.courier_id: e for e in await courier_earnings(current)}
    for c in couriers:  # balance of the open day; resets when the day is closed (archived in the close)
        e = by_id.get(c.courier_id)
        c.deliveries_today, c.fees_today = (e.deliveries, e.fees) if e else (0, 0.0)
        c.working_today = c.working_date == today
    return couriers


async def courier_earnings(orders: list[Order]) -> list[CourierEarning]:
    """Each delivery that left/finished adds its zone fee to the courier's balance."""
    names = {c["courier_id"]: c["name"] for c in await db.couriers.find().to_list(500)}
    out: dict[str, CourierEarning] = {}
    for o in orders:
        if o.courier_id and o.delivery_type == "Entrega" and o.status in ("Em Entrega", "Concluído"):
            e = out.setdefault(o.courier_id, CourierEarning(courier_id=o.courier_id, name=names.get(o.courier_id, "Entregador removido"), deliveries=0, fees=0))
            e.deliveries += 1
            e.fees = round(e.fees + o.delivery_fee, 2)
    return list(out.values())


@router.post("/couriers/{courier_id}/working", response_model=Courier, dependencies=[need("motoboys")])
async def toggle_working(courier_id: str):
    """Owner picks who is working today; only these couriers can be assigned to deliveries."""
    c = await db.couriers.find_one({"courier_id": courier_id})
    if not c:
        raise HTTPException(status_code=404, detail="Entregador não encontrado.")
    today = today_iso()
    c["working_date"] = "" if c.get("working_date") == today else today
    await db.couriers.update_one({"courier_id": courier_id}, {"$set": {"working_date": c["working_date"]}})
    return Courier(**{**c, "working_today": c["working_date"] == today})


@router.post("/couriers", response_model=Courier, dependencies=[need("motoboys")])
async def create_courier(input: CourierCreate):
    courier = Courier(**input.model_dump())
    await db.couriers.insert_one(courier.model_dump())
    return courier


@router.put("/couriers/{courier_id}", response_model=Courier, dependencies=[need("motoboys")])
async def update_courier(courier_id: str, input: CourierCreate):
    updated = await db.couriers.find_one_and_update({"courier_id": courier_id}, {"$set": input.model_dump()}, return_document=ReturnDocument.AFTER)
    if not updated:
        raise HTTPException(status_code=404, detail="Entregador não encontrado.")
    return Courier(**updated)


@router.delete("/couriers/{courier_id}", dependencies=[need("motoboys")])
async def delete_courier(courier_id: str):
    await db.couriers.delete_one({"courier_id": courier_id})
    return {"ok": True}


@router.get("/day/status", response_model=DayStatus)
async def day_status():
    status = await db.day_status.find_one({}) or DayStatus().model_dump()
    orders = await all_orders()
    status["total_orders"] = len(orders)
    status["open_orders"] = len([o for o in orders if o.status not in {"Concluído", "Cancelado"}])
    status["revenue"] = metrics(orders)["revenue"]
    return DayStatus(**status)


@router.post("/day/open", response_model=DayStatus)
async def open_day(input: DayOpenRequest = DayOpenRequest()):
    updated = await db.day_status.find_one_and_update({}, {"$set": {"is_open": True, "day_state": "open", "initial_cash_balance": input.initial_cash, "opened_at": datetime.now(timezone.utc)}}, upsert=True, return_document=ReturnDocument.AFTER)
    return DayStatus(**updated)


@router.post("/day/close", response_model=DayStatus)
async def close_day():
    """Archives everything of the day: orders + courier earnings go to Armazenamento, WhatsApp conversations are deleted."""
    s = await day_status()
    close_id = new_id("close")
    current = await db.orders.find({"archived": {"$ne": True}}).to_list(5000)
    earnings = await courier_earnings([Order(**o) for o in current])
    chats_deleted = (await db.chats.delete_many({})).deleted_count
    opened = (await db.day_status.find_one({}) or {}).get("opened_at")
    await db.day_closes.insert_one({"close_id": close_id, "opened_at": opened, "created_at": datetime.now(timezone.utc), "revenue": s.revenue, "total_orders": s.total_orders, "avg_ticket": s.revenue / s.total_orders if s.total_orders else 0,
                                    "couriers": [e.model_dump() for e in earnings], "chats_deleted": chats_deleted})
    await db.orders.update_many({"archived": {"$ne": True}}, {"$set": {"archived": True, "close_id": close_id}})
    await db.couriers.update_many({}, {"$set": {"working_date": ""}})  # pick who works again on the next day
    updated = await db.day_status.find_one_and_update({}, {"$set": {"is_open": False, "day_state": "closed"}}, return_document=ReturnDocument.AFTER)
    return DayStatus(**updated)


@router.get("/day/closes", response_model=list[DayClose])
async def list_closes():
    return [DayClose(**d) for d in await db.day_closes.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)]


@router.get("/day/closes/{close_id}", response_model=DayCloseDetail)
async def close_detail(close_id: str):
    d = await db.day_closes.find_one({"close_id": close_id}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Fechamento não encontrado.")
    orders = [Order(**o) for o in await db.orders.find({"close_id": close_id}).sort("created_at", -1).to_list(5000)]
    valid = [o for o in orders if o.status != "Cancelado"]

    def group(pairs: list[tuple[str, int, float]]) -> list[ReportLine]:
        acc: dict[str, list[float]] = {}
        for label, n, total in pairs:
            a = acc.setdefault(label, [0, 0.0])
            a[0] += n
            a[1] += total
        return sorted((ReportLine(label=k, count=int(v[0]), total=round(v[1], 2)) for k, v in acc.items()), key=lambda r: r.total, reverse=True)

    pay: list[tuple[str, int, float]] = []
    for o in valid:  # split payments count each part in its own method
        pay += [(p.method, 1, p.amount) for p in o.payments] if o.payments else [(o.payment_method or "Pendente", 1, o.total)]
    if not d.get("opened_at") and orders:
        d["opened_at"] = min(o.created_at for o in orders)
    return DayCloseDetail(**d, orders=orders,
                          by_type=group([(o.delivery_type, 1, o.total) for o in valid]),
                          by_payment=group(pay),
                          top_products=group([(i.name, i.quantity, i.price * i.quantity) for o in valid for i in o.items])[:10])


@router.delete("/day/closes/{close_id}")
async def delete_close(close_id: str):
    """Deletes a closed day from Armazenamento with its archived orders (customers and reports of other days stay)."""
    if not (await db.day_closes.delete_one({"close_id": close_id})).deleted_count:
        raise HTTPException(status_code=404, detail="Fechamento não encontrado.")
    removed = (await db.orders.delete_many({"close_id": close_id, "archived": True})).deleted_count
    return {"ok": True, "orders_removed": removed}


@router.get("/reports/summary", response_model=ReportSummary)
async def report_summary():
    orders = await all_orders()
    m = metrics(orders)
    by_payment: dict[str, float] = {}
    products: dict[str, int] = {}
    for o in m["valid"]:
        by_payment[o.payment_method] = by_payment.get(o.payment_method, 0) + o.total
        for i in o.items:
            products[i.name] = products.get(i.name, 0) + i.quantity
    top = [{"name": n, "quantity": q} for n, q in sorted(products.items(), key=lambda p: p[1], reverse=True)]
    return ReportSummary(revenue=m["revenue"], month_revenue=m["month_revenue"], total_orders=len(orders), avg_ticket=m["avg_ticket"], avg_fee=m["avg_fee"], completed_orders=len([o for o in orders if o.status == "Concluído"]), by_payment=by_payment, top_products=top)


@router.get("/backup/export", dependencies=[need("backup")])
async def export_backup():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in BACKUP_COLLECTIONS:
            docs = await db[name].find({}, {"_id": 0}).to_list(100000)
            zf.writestr(f"{name}.json", json.dumps(docs, default=str, ensure_ascii=False, indent=2))
    buffer.seek(0)
    filename = f"marmita-hub-backup-{today_iso()}.zip"
    return StreamingResponse(buffer, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/backup/import", dependencies=[need("backup")])
async def import_backup(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            data = {n[:-5]: json.loads(zf.read(n)) for n in zf.namelist() if n.endswith(".json")}
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Arquivo inválido: envie um backup .zip gerado pelo sistema.")
    restored: dict[str, int] = {}
    for name, docs in data.items():
        if name not in BACKUP_COLLECTIONS or not isinstance(docs, list):
            continue
        for d in docs:
            if isinstance(d.get("created_at"), str):
                d["created_at"] = datetime.fromisoformat(d["created_at"])
        await db[name].delete_many({})
        if docs:
            await db[name].insert_many(docs)
        restored[name] = len(docs)
    return {"ok": True, "restored": restored}
