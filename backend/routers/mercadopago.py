"""Mercado Pago settings (per store), payment polling and the public webhook."""

from fastapi import APIRouter, HTTPException, Request

from lib.db import db, raw_db
import asyncio
import os

from lib.mercadopago import POINT_ACTIVE, check_token, confirm_if_paid, mp_error_detail, point_call, point_token, store_token, sync_point
from lib.tenant import current_store
from models.domain import MercadoPagoStatus, MercadoPagoToken, Order, PointCharge, PointDevice, PointDeviceChoice

router = APIRouter(tags=["mercadopago"])
public_router = APIRouter(tags=["mercadopago"])


@router.get("/payments/mercadopago", response_model=MercadoPagoStatus)
async def mp_status():
    doc = await db.mp_credentials.find_one({}) or {}
    return MercadoPagoStatus(configured=bool(doc.get("access_token")), account=doc.get("account", ""), store_id=current_store.get(), point_device_id=doc.get("point_device_id", ""))


@router.put("/payments/mercadopago", response_model=MercadoPagoStatus)
async def mp_save(input: MercadoPagoToken):
    token = input.access_token.strip()
    me = await check_token(token)
    if not me:
        raise HTTPException(status_code=422, detail="Access Token inválido. Copie o Access Token de produção em Mercado Pago → Suas integrações → Credenciais.")
    account = me.get("nickname") or me.get("email") or str(me.get("id", ""))
    await db.mp_credentials.update_one({}, {"$set": {"access_token": token, "account": account}}, upsert=True)
    return MercadoPagoStatus(configured=True, account=account, store_id=current_store.get())


@router.delete("/payments/mercadopago", response_model=MercadoPagoStatus)
async def mp_remove():
    await db.mp_credentials.delete_many({})
    await db.store_settings.update_one({}, {"$set": {"pix_provider": "manual"}})
    return MercadoPagoStatus(configured=False, account="", store_id=current_store.get())


@router.post("/payments/mercadopago/check")
async def mp_check_pending():
    """Polling from the orders screen: confirms any open Mercado Pago Pix that was paid."""
    token = await store_token()
    confirmed = 0
    if token:
        for o in await db.orders.find({"mp_order_id": {"$nin": ["", None]}, "payment_status": {"$ne": "pago"}, "archived": {"$ne": True}, "status": {"$ne": "Cancelado"}}).to_list(50):
            confirmed += int(await confirm_if_paid(o, token))
    return {"confirmed": confirmed}


@router.get("/orders/{order_id}/payment-status")
async def order_payment_status(order_id: str):
    o = await db.orders.find_one({"order_id": order_id})
    if not o:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    paid = await confirm_if_paid(o)
    return {"order_id": order_id, "payment_status": "pago" if paid else o.get("payment_status", "pendente")}


@router.get("/payments/point/devices", response_model=list[PointDevice])
async def point_devices():
    token = await point_token()
    if not token:
        raise HTTPException(status_code=422, detail="Conecte sua conta Mercado Pago (Access Token) primeiro.")
    code, data = await point_call("GET", "/devices?offset=0&limit=50", token)
    if code != 200:
        raise HTTPException(status_code=502, detail="Não consegui listar as maquininhas no Mercado Pago.")
    return [PointDevice(id=d.get("id", ""), operating_mode=d.get("operating_mode", "")) for d in data.get("devices", [])]


@router.put("/payments/point/device", response_model=MercadoPagoStatus)
async def point_choose(input: PointDeviceChoice):
    token = await point_token()
    code, _ = await point_call("PATCH", f"/devices/{input.device_id}", token, {"operating_mode": "PDV"})  # integrated mode
    if code >= 400:
        raise HTTPException(status_code=422, detail="Não consegui colocar a maquininha no modo integrado (PDV). Confira se ela está ligada e logada na sua conta.")
    await db.mp_credentials.update_one({}, {"$set": {"point_device_id": input.device_id}}, upsert=True)
    return await mp_status()


async def _point_order(order_id: str) -> dict:
    o = await db.orders.find_one({"order_id": order_id})
    if not o:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    return o


@router.post("/pedidos/{order_id}/pagar-point", response_model=Order)
async def pagar_point(order_id: str, input: PointCharge):
    o = await _point_order(order_id)
    if o.get("payment_status") == "pago":
        raise HTTPException(status_code=409, detail="Este pedido já está pago.")
    device = (await db.mp_credentials.find_one({}) or {}).get("point_device_id") or os.environ.get("MP_DEVICE_ID", "")
    token = await point_token()
    if not device or not token:
        raise HTTPException(status_code=422, detail="Configure a Point Smart 2 em Configurações → Pix / Mercado Pago.")
    # The machine must exist on this account and be in integrated (PDV) mode, otherwise the intent never shows up
    code, devs = await point_call("GET", "/devices?offset=0&limit=50", token)
    if code >= 400:
        raise HTTPException(status_code=code, detail=mp_error_detail(code, devs, "não consegui consultar as maquininhas"))
    dev = next((d for d in devs.get("devices", []) if d.get("id") == device), None)
    if not dev:
        raise HTTPException(status_code=404, detail={"message": f"A maquininha {device} não foi encontrada nesta conta Mercado Pago. Em Configurações, clique em Buscar maquininhas e escolha de novo.", "mp_error": devs})
    if dev.get("operating_mode") != "PDV":
        await point_call("PATCH", f"/devices/{device}", token, {"operating_mode": "PDV"})
        raise HTTPException(status_code=409, detail={"message": "A maquininha não estava no modo integrado (PDV). Já pedi a troca: reinicie a Point Smart 2 e tente cobrar de novo.", "mp_error": dev})
    # amount: integer NUMBER in centavos (Point Payment Intent API: 1500 = R$ 15,00) — never a string, never with comma
    body = {"amount": int(round(float(o["total"]) * 100)), "description": f"Pedido #{order_id[-6:].upper()}",
            "additional_info": {"external_reference": order_id, "print_on_terminal": True}}
    if input.type:
        body["payment"] = {"type": input.type, **({"installments": 1} if input.type == "credit_card" else {})}
    code, data = await point_call("POST", f"/devices/{device}/payment-intents", token, body)
    if code >= 400 or not data.get("id"):  # pass Mercado Pago's own status + JSON error to the panel
        raise HTTPException(status_code=code if code >= 400 else 502, detail=mp_error_detail(code, data, "a cobrança não foi criada"))
    await db.orders.update_one({"order_id": order_id}, {"$set": {"point_intent_id": data["id"], "point_state": "OPEN", "point_device_id": device, "point_type": input.type},
                                                        "$addToSet": {"point_intents": data["id"]}})  # history: a released charge paid later is still recognized
    return Order(**await _point_order(order_id))


@router.post("/pedidos/{order_id}/cancelar-point", response_model=Order)
async def cancelar_point(order_id: str, force: bool = False):
    """Cancels on Mercado Pago (only possible while OPEN). `force=true` releases the order in the panel when the
    charge is already on the machine's screen (it must be cancelled on the Point itself)."""
    o = await _point_order(order_id)
    if o.get("point_intent_id") and not force:
        device = o.get("point_device_id") or (await db.mp_credentials.find_one({}) or {}).get("point_device_id", "")
        code, err = await point_call("DELETE", f"/devices/{device}/payment-intents/{o['point_intent_id']}", await point_token())
        if code >= 400 and code != 404:
            detail = mp_error_detail(code, err, "a cobrança já está na tela da maquininha")
            detail["message"] += " · Cancele na tela da Point Smart 2 e use “Liberar no painel”."
            detail["can_force"] = True
            raise HTTPException(status_code=code, detail=detail)
    await db.orders.update_one({"order_id": order_id}, {"$set": {"point_intent_id": "", "point_state": "CANCELED"}})
    return Order(**await _point_order(order_id))


@router.get("/pedidos/{order_id}/point-status", response_model=Order)
async def point_status(order_id: str):
    """Fallback polling (the webhook is the main path)."""
    o = await _point_order(order_id)
    if o.get("point_intent_id") and o.get("payment_status") != "pago" and (o.get("point_state") in POINT_ACTIVE or not o.get("point_state")):
        err = await sync_point(o, raise_errors=True)
        if err:
            raise HTTPException(status_code=err[0], detail=mp_error_detail(err[0], err[1], "não consegui consultar a cobrança"))
    return Order(**await _point_order(order_id))


async def _handle_point_event(intent_id: str, store: str) -> None:
    if not store:  # webhook without ?store=: find which restaurant owns this intent
        o = await raw_db.orders.find_one({"$or": [{"point_intent_id": intent_id}, {"point_intents": intent_id}]}, {"store_id": 1})
        store = (o or {}).get("store_id", "")
    if not store:
        return
    current_store.set(store)
    o = await db.orders.find_one({"$or": [{"point_intent_id": intent_id}, {"point_intents": intent_id}]})
    if o:
        await sync_point({**o, "point_intent_id": intent_id})


@public_router.post("/webhooks/mercadopago")
async def mp_webhook(request: Request, store: str = ""):
    """Configured in the Mercado Pago panel per store (…/api/webhooks/mercadopago?store=ID). The body only says
    'something changed': we re-read the order from Mercado Pago with that store's token before marking it paid."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    if body.get("topic") == "point_integration_wh" or body.get("type") == "point_integration_wh" or "state" in body:
        asyncio.create_task(_handle_point_event(str(body.get("id", "")), store))  # answer 200 now, reconcile after
        return {"received": True}
    if not store or not await raw_db.stores.find_one({"store_id": store}):
        return {"received": True}
    mp_id = (body.get("data") or {}).get("id") or request.query_params.get("data.id", "")
    current_store.set(store)
    flt = {"mp_order_id": mp_id} if mp_id else {"mp_order_id": {"$nin": ["", None]}, "payment_status": {"$ne": "pago"}, "archived": {"$ne": True}}
    for o in await db.orders.find(flt).to_list(20):
        await confirm_if_paid(o)
    return {"received": True}
