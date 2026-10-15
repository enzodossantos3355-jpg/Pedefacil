"""Mercado Pago "Pix Automático" (Orders API), per restaurant.

Each store pastes its own Access Token (kept in `mp_credentials`, never returned to the browser).
A Pix order is created on Mercado Pago with the order total; payment is confirmed ONLY by re-reading the
order from Mercado Pago with that store's token (status processed/accredited) — never from a picture or the webhook body.
"""

import logging
import re

import httpx

from lib.ai import wa_send
from lib.db import db

logger = logging.getLogger(__name__)
MP = "https://api.mercadopago.com"


async def store_token() -> str:
    doc = await db.mp_credentials.find_one({})
    return (doc or {}).get("access_token", "")


async def check_token(token: str) -> dict | None:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{MP}/users/me", headers={"Authorization": f"Bearer {token}"})
    return r.json() if r.status_code == 200 else None


async def create_pix(order: dict, token: str, amount_value: float | None = None) -> dict | None:
    """Creates (idempotently per order+total) the Mercado Pago Pix order → {mp_order_id, qr_code, qr_code_base64, ticket_url}."""
    amount = f"{(amount_value if amount_value is not None else order['total']):.2f}"
    digits = re.sub(r"\D", "", order.get("customer_phone", "")) or "cliente"
    payload = {
        "type": "online", "total_amount": amount, "external_reference": order["order_id"], "processing_mode": "automatic",
        "transactions": {"payments": [{"amount": amount, "payment_method": {"id": "pix", "type": "bank_transfer"}}]},
        "payer": {"email": f"cliente{digits}@pedefacil.com.br"},
    }
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{MP}/v1/orders", json=payload, headers={"Authorization": f"Bearer {token}", "X-Idempotency-Key": f"{order['order_id']}-{amount}"})
    if r.status_code >= 400:
        logger.error("Mercado Pago create order %s: %s", r.status_code, r.text[:300])
        return None
    data = r.json()
    pm = ((data.get("transactions") or {}).get("payments") or [{}])[0].get("payment_method", {})
    return {"mp_order_id": data.get("id", ""), "qr_code": pm.get("qr_code", ""), "qr_code_base64": pm.get("qr_code_base64", ""), "ticket_url": pm.get("ticket_url", "")}


async def is_paid(mp_order_id: str, token: str) -> bool:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{MP}/v1/orders/{mp_order_id}", headers={"Authorization": f"Bearer {token}"})
    if r.status_code != 200:
        return False
    o = r.json()
    pay = ((o.get("transactions") or {}).get("payments") or [{}])[0]
    return o.get("status") == "processed" and o.get("status_detail") == "accredited" and pay.get("status", "processed") == "processed"


async def confirm_if_paid(order: dict, token: str | None = None) -> bool:
    """Checks Mercado Pago for this order; when approved marks it paid and tells the customer on WhatsApp."""
    if not order.get("mp_order_id") or order.get("payment_status") == "pago":
        return order.get("payment_status") == "pago"
    token = token or await store_token()
    if not token or not await is_paid(order["mp_order_id"], token):
        return False
    res = await db.orders.update_one({"order_id": order["order_id"], "payment_status": {"$ne": "pago"}},
                                     {"$set": {"payment_status": "pago", "payment_method": "Pix", "receipt_note": "Pago via Mercado Pago (confirmado automaticamente)"}})
    if res.modified_count:
        chat = await db.chats.find_one({"phone": order.get("customer_phone", "")}) or {}
        await wa_send(chat.get("jid") or order.get("customer_phone", ""), f"✅ Pagamento do pedido #{order['order_id'][-6:].upper()} confirmado! Obrigado 😊")
    return True
