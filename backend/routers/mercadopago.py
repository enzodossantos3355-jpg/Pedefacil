"""Mercado Pago settings (per store), payment polling and the public webhook."""

from fastapi import APIRouter, HTTPException, Request

from lib.db import db, raw_db
from lib.mercadopago import check_token, confirm_if_paid, store_token
from lib.tenant import current_store
from models.domain import MercadoPagoStatus, MercadoPagoToken

router = APIRouter(tags=["mercadopago"])
public_router = APIRouter(tags=["mercadopago"])


@router.get("/payments/mercadopago", response_model=MercadoPagoStatus)
async def mp_status():
    doc = await db.mp_credentials.find_one({}) or {}
    return MercadoPagoStatus(configured=bool(doc.get("access_token")), account=doc.get("account", ""), store_id=current_store.get())


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


@public_router.post("/webhooks/mercadopago")
async def mp_webhook(request: Request, store: str = ""):
    """Configured in the Mercado Pago panel per store (…/api/webhooks/mercadopago?store=ID). The body only says
    'something changed': we re-read the order from Mercado Pago with that store's token before marking it paid."""
    if not store or not await raw_db.stores.find_one({"store_id": store}):
        return {"received": True}
    try:
        body = await request.json()
    except Exception:
        body = {}
    mp_id = (body.get("data") or {}).get("id") or request.query_params.get("data.id", "")
    current_store.set(store)
    flt = {"mp_order_id": mp_id} if mp_id else {"mp_order_id": {"$nin": ["", None]}, "payment_status": {"$ne": "pago"}, "archived": {"$ne": True}}
    for o in await db.orders.find(flt).to_list(20):
        await confirm_if_paid(o)
    return {"received": True}
