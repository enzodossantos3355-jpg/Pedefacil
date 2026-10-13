import io
import json
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pymongo import ReturnDocument

from lib.ai import wa_send
from lib.dates import today_iso
from lib.db import db
from lib.geo import quote_fee
from models.domain import (
    STATUS_FLOW, Courier, CourierCreate, Customer, CustomerCreate, DashboardSummary, DayOpenRequest, DayStatus,
    DeliveryZone, DeliveryZoneCreate, FeeQuote, FeeQuoteResult, Order, OrderCreate, OrderUpdate, Product,
    ProductCreate, ReportSummary, StatusUpdate, StoreSettings, new_id,
)
import os

router = APIRouter(tags=["operations"])
IMG = [
    "https://images.pexels.com/photos/30635705/pexels-photo-30635705.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
    "https://images.pexels.com/photos/30635717/pexels-photo-30635717.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
]
STATUS_MESSAGES = {
    "Novo": "✅ Seu pedido #{id} foi confirmado e já está na fila da cozinha!",
    "Em Preparo": "👩‍🍳 Seu pedido #{id} está sendo preparado.",
    "Pronto": "🍱 Seu pedido #{id} está pronto!",
    "Saiu para Entrega": "🛵 Seu pedido #{id} saiu para entrega e logo chega até você!",
    "Entregue": "🙏 Pedido #{id} entregue. Obrigado pela preferência, bom apetite!",
    "Cancelado": "Seu pedido #{id} foi cancelado. Se precisar, estamos à disposição.",
}
BACKUP_COLLECTIONS = ["products", "orders", "customers", "delivery_zones", "store_settings", "couriers", "chats", "day_closes"]


async def seed_demo_data() -> None:
    if await db.products.count_documents({}) == 0:
        await db.products.insert_many([
            Product(product_id="prod-tradicional", name="Marmita Tradicional", category="Marmita", price=22.9, description="Arroz soltinho, feijão cremoso, proteína do dia, farofa e salada.", image_url=IMG[0], sizes=[{"name": "P", "price": 18.9}, {"name": "M", "price": 22.9}, {"name": "G", "price": 27.9}], additionals=[{"name": "Ovo frito", "price": 3}, {"name": "Bacon", "price": 4}], stock=40).model_dump(),
            Product(product_id="prod-executiva", name="Marmita Executiva", category="Marmita", price=31.9, description="Bife acebolado com guarnições frescas.", image_url=IMG[1], stock=25).model_dump(),
            Product(product_id="prod-suco", name="Suco Natural 500ml", category="Bebida", price=8.5, description="Suco natural preparado na hora.", image_url="https://images.unsplash.com/photo-1626379907504-327b925f4b79?auto=format&fit=crop&w=600&q=80").model_dump(),
        ])
    if await db.orders.count_documents({}) == 0:
        await db.orders.insert_many([
            Order(order_id="ord-demo01", customer_name="Mariana Costa", customer_phone="5511988887777", delivery_type="Entrega", address="Rua das Palmeiras, 45", payment_method="Pix", items=[{"product_id": "prod-tradicional", "name": "Marmita Tradicional", "size": "M", "price": 22.9, "quantity": 2}], subtotal=45.8, delivery_fee=5, total=50.8, status="Em Preparo").model_dump(),
            Order(order_id="ord-demo02", customer_name="Rafael Lima", customer_phone="5511977776666", delivery_type="Retirada", payment_method="Cartão Crédito", items=[{"product_id": "prod-executiva", "name": "Marmita Executiva", "price": 31.9, "quantity": 1}], subtotal=31.9, total=31.9, status="Novo").model_dump(),
            Order(order_id="ord-demo03", customer_name="Bianca Souza", customer_phone="5511966665555", delivery_type="Entrega", address="Av. Brasil, 120", payment_method="Pix", items=[{"product_id": "prod-tradicional", "name": "Marmita Tradicional", "size": "G", "price": 27.9, "quantity": 1}], subtotal=27.9, delivery_fee=6, total=33.9, status="Em Análise", source="whatsapp").model_dump(),
        ])
    if await db.customers.count_documents({}) == 0:
        await db.customers.insert_many([
            Customer(customer_id="cust-demo01", name="Mariana Costa", phone="5511988887777", address="Rua das Palmeiras, 45", orders_count=4, total_spent=168.6, preferences=["Sem cebola"]).model_dump(),
            Customer(customer_id="cust-demo02", name="Rafael Lima", phone="5511977776666", address="Retirada no balcão", orders_count=2, total_spent=64.8).model_dump(),
        ])
    if await db.delivery_zones.count_documents({}) == 0:
        await db.delivery_zones.insert_many([
            DeliveryZone(zone_id="zone-centro", name="Centro", fee=5, kind="keyword", keywords=["centro", "sé", "república"]).model_dump(),
            DeliveryZone(zone_id="zone-raio3", name="Até 3 km", fee=6, kind="radius", radius_km=3).model_dump(),
        ])
    if await db.couriers.count_documents({}) == 0:
        await db.couriers.insert_one(Courier(courier_id="moto-demo01", name="Carlos Entregas", phone="5511955554444").model_dump())
    if await db.store_settings.count_documents({}) == 0:
        await db.store_settings.insert_one(StoreSettings(pix_key="11999998888", pix_beneficiary="Marmita Hub Ltda").model_dump())
    if await db.day_status.count_documents({}) == 0:
        await db.day_status.insert_one(DayStatus(opened_at=datetime.now(timezone.utc)).model_dump())


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
    active = [o for o in orders if o.status in STATUS_FLOW[:5]]
    settings = await get_settings()
    return DashboardSummary(today=m["today"], revenue=m["revenue"], month_revenue=m["month_revenue"], total_orders=len(orders), active_orders=len(active), average_ticket=m["avg_ticket"], average_fee=m["avg_fee"], open_orders=len(active), accepting_orders=settings["accepting_orders"], recent_orders=orders[:6])


@router.get("/orders", response_model=list[Order])
async def list_orders():
    return await all_orders()


async def create_order_record(input: OrderCreate) -> Order:
    subtotal = sum(i.price * i.quantity for i in input.items)
    fee, zone_name = 0.0, ""
    if input.delivery_type != "Retirada":
        if input.delivery_fee is not None:
            fee = input.delivery_fee
        else:
            q = quote_fee(await db.delivery_zones.find().to_list(500), await get_settings(), input.latitude, input.longitude, input.address)
            fee, zone_name = q["fee"], q["zone_name"]
    order = Order(**input.model_dump(exclude={"delivery_fee"}), subtotal=subtotal, delivery_fee=fee, zone_name=zone_name, total=subtotal + fee)
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


@router.post("/orders", response_model=Order)
async def create_order(input: OrderCreate):
    return await create_order_record(input)


@router.put("/orders/{order_id}", response_model=Order)
async def update_order(order_id: str, input: OrderUpdate):
    current = await db.orders.find_one({"order_id": order_id})
    if not current:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    data = input.model_dump(exclude_none=True)
    items = data.get("items", current["items"])
    fee = data.get("delivery_fee", current.get("delivery_fee", 0))
    data["subtotal"] = sum(i["price"] * i["quantity"] for i in items)
    data["total"] = data["subtotal"] + fee
    updated = await db.orders.find_one_and_update({"order_id": order_id}, {"$set": data}, return_document=ReturnDocument.AFTER)
    if "status" in data and data["status"] != current["status"]:
        await notify_status(Order(**updated))
    return Order(**updated)


async def notify_status(order: Order) -> None:
    settings = await get_settings()
    template = STATUS_MESSAGES.get(order.status)
    if settings["notify_status_changes"] and template and order.customer_phone:
        await wa_send(order.customer_phone, template.format(id=order.order_id[-6:].upper()))


@router.patch("/orders/{order_id}/status", response_model=Order)
async def update_order_status(order_id: str, input: StatusUpdate):
    if input.status not in STATUS_FLOW:
        raise HTTPException(status_code=422, detail="Status inválido.")
    updated = await db.orders.find_one_and_update({"order_id": order_id}, {"$set": {"status": input.status}}, return_document=ReturnDocument.AFTER)
    if not updated:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    order = Order(**updated)
    await notify_status(order)
    return order


@router.post("/orders/{order_id}/approve", response_model=Order)
async def approve_order(order_id: str):
    return await update_order_status(order_id, StatusUpdate(status="Novo"))


@router.delete("/orders/{order_id}")
async def delete_order(order_id: str):
    if not (await db.orders.delete_one({"order_id": order_id})).deleted_count:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    return {"ok": True}


@router.get("/products", response_model=list[Product])
async def list_products():
    return [Product(**d) for d in await db.products.find().sort("name", 1).to_list(1000)]


@router.post("/products", response_model=Product)
async def create_product(input: ProductCreate):
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
    return [Customer(**d) for d in await db.customers.find().sort("name", 1).to_list(2000)]


@router.post("/customers", response_model=Customer)
async def create_customer(input: CustomerCreate):
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
    updated = await db.store_settings.find_one_and_update({}, {"$set": input.model_dump()}, upsert=True, return_document=ReturnDocument.AFTER)
    return StoreSettings(**updated)


@router.post("/store/toggle-accepting", response_model=StoreSettings)
async def toggle_store():
    current = await get_store()
    current.accepting_orders = not current.accepting_orders
    return await update_store(current)


@router.get("/maps/config")
async def maps_config():
    # Browser key for the Maps JavaScript API (restrict it by HTTP referrer in Google Cloud).
    return {"api_key": os.environ.get("GOOGLE_MAPS_API_KEY", "")}


@router.get("/delivery-zones", response_model=list[DeliveryZone])
async def list_zones():
    return [DeliveryZone(**d) for d in await db.delivery_zones.find().to_list(500)]


@router.post("/delivery-zones", response_model=DeliveryZone)
async def create_zone(input: DeliveryZoneCreate):
    zone = DeliveryZone(**input.model_dump())
    await db.delivery_zones.insert_one(zone.model_dump())
    return zone


@router.put("/delivery-zones/{zone_id}", response_model=DeliveryZone)
async def update_zone(zone_id: str, input: DeliveryZoneCreate):
    updated = await db.delivery_zones.find_one_and_update({"zone_id": zone_id}, {"$set": input.model_dump()}, return_document=ReturnDocument.AFTER)
    if not updated:
        raise HTTPException(status_code=404, detail="Região não encontrada.")
    return DeliveryZone(**updated)


@router.delete("/delivery-zones/{zone_id}")
async def delete_zone(zone_id: str):
    await db.delivery_zones.delete_one({"zone_id": zone_id})
    return {"ok": True}


@router.post("/delivery-zones/quote", response_model=FeeQuoteResult)
async def quote_zone(input: FeeQuote):
    return FeeQuoteResult(**quote_fee(await db.delivery_zones.find().to_list(500), await get_settings(), input.latitude, input.longitude, input.text))


@router.get("/couriers", response_model=list[Courier])
async def list_couriers():
    today = today_iso()
    couriers = [Courier(**d) for d in await db.couriers.find().sort("name", 1).to_list(500)]
    orders = await all_orders()
    for c in couriers:
        mine = [o for o in orders if o.courier_id == c.courier_id and o.created_at.strftime("%Y-%m-%d") == today and o.status != "Cancelado"]
        c.deliveries_today, c.fees_today = len(mine), sum(o.delivery_fee for o in mine)
    return couriers


@router.post("/couriers", response_model=Courier)
async def create_courier(input: CourierCreate):
    courier = Courier(**input.model_dump())
    await db.couriers.insert_one(courier.model_dump())
    return courier


@router.put("/couriers/{courier_id}", response_model=Courier)
async def update_courier(courier_id: str, input: CourierCreate):
    updated = await db.couriers.find_one_and_update({"courier_id": courier_id}, {"$set": input.model_dump()}, return_document=ReturnDocument.AFTER)
    if not updated:
        raise HTTPException(status_code=404, detail="Entregador não encontrado.")
    return Courier(**updated)


@router.delete("/couriers/{courier_id}")
async def delete_courier(courier_id: str):
    await db.couriers.delete_one({"courier_id": courier_id})
    return {"ok": True}


@router.get("/day/status", response_model=DayStatus)
async def day_status():
    status = await db.day_status.find_one({}) or DayStatus().model_dump()
    orders = await all_orders()
    status["total_orders"] = len(orders)
    status["open_orders"] = len([o for o in orders if o.status not in {"Entregue", "Cancelado"}])
    status["revenue"] = metrics(orders)["revenue"]
    return DayStatus(**status)


@router.post("/day/open", response_model=DayStatus)
async def open_day(input: DayOpenRequest = DayOpenRequest()):
    updated = await db.day_status.find_one_and_update({}, {"$set": {"is_open": True, "day_state": "open", "initial_cash_balance": input.initial_cash, "opened_at": datetime.now(timezone.utc)}}, upsert=True, return_document=ReturnDocument.AFTER)
    return DayStatus(**updated)


@router.post("/day/close", response_model=DayStatus)
async def close_day():
    s = await day_status()
    await db.day_closes.insert_one({"close_id": new_id("close"), "created_at": datetime.now(timezone.utc), "revenue": s.revenue, "total_orders": s.total_orders, "avg_ticket": s.revenue / s.total_orders if s.total_orders else 0})
    updated = await db.day_status.find_one_and_update({}, {"$set": {"is_open": False, "day_state": "closed"}}, return_document=ReturnDocument.AFTER)
    return DayStatus(**updated)


@router.get("/day/closes")
async def list_closes():
    return await db.day_closes.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)


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
    return ReportSummary(revenue=m["revenue"], month_revenue=m["month_revenue"], total_orders=len(orders), avg_ticket=m["avg_ticket"], avg_fee=m["avg_fee"], completed_orders=len([o for o in orders if o.status == "Entregue"]), by_payment=by_payment, top_products=top)


@router.get("/backup/export")
async def export_backup():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in BACKUP_COLLECTIONS:
            docs = await db[name].find({}, {"_id": 0}).to_list(100000)
            zf.writestr(f"{name}.json", json.dumps(docs, default=str, ensure_ascii=False, indent=2))
    buffer.seek(0)
    filename = f"marmita-hub-backup-{today_iso()}.zip"
    return StreamingResponse(buffer, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/backup/import")
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
