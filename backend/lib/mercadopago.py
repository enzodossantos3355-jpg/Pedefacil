"""Mercado Pago "Pix Automático" (Orders API), per restaurant.

Each store pastes its own Access Token (kept in `mp_credentials`, never returned to the browser).
A Pix order is created on Mercado Pago with the order total; payment is confirmed ONLY by re-reading the
order from Mercado Pago with that store's token (status processed/accredited) — never from a picture or the webhook body.
"""

import json
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


# ---------- Point Smart 2 (Point Integration API, Payment Intents) ----------
import os  # noqa: E402

POINT = f"{MP}/point/integration-api"
POINT_ACTIVE = {"OPEN", "ON_TERMINAL", "PROCESSING", "CONFIRMATION_REQUIRED"}


async def point_token() -> str:
    """Store's own Mercado Pago token (same account as Pix Automático); env MP_ACCESS_TOKEN as fallback."""
    return await store_token() or os.environ.get("MP_ACCESS_TOKEN", "")


async def point_call(method: str, path: str, token: str, body: dict | None = None) -> tuple[int, dict]:
    """Calls the Point API with Bearer token + JSON; logs URL, body and the full response (never the token)."""
    url = f"{POINT}{path}"
    logger.info("Point → %s %s body=%s", method, url, json.dumps(body, ensure_ascii=False) if body is not None else "-")
    try:
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.request(method, url, json=body, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    except httpx.HTTPError as exc:
        logger.error("Point ✗ %s %s → sem resposta: %s", method, url, exc)
        return 504, {"message": f"Mercado Pago não respondeu ({type(exc).__name__})."}
    try:
        data = r.json() if r.content else {}
    except ValueError:
        data = {"raw": r.text[:500]}
    (logger.error if r.status_code >= 400 else logger.info)("Point ← %s %s → %s %s", method, url, r.status_code, r.text[:1500])
    return r.status_code, data


def mp_error_detail(code: int, data: dict, fallback: str) -> dict:
    """Exact Mercado Pago error for the panel: {message, mp_error}."""
    msg = data.get("message") or data.get("error") or fallback
    causes = data.get("cause") or data.get("errors") or []
    if isinstance(causes, list) and causes:
        msg += " — " + "; ".join(str(c.get("description") or c.get("message") or c) if isinstance(c, dict) else str(c) for c in causes)
    return {"message": f"Mercado Pago ({code}): {msg}", "mp_error": data}


async def payment_approved(payment_id: str, token: str) -> bool:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{MP}/v1/payments/{payment_id}", headers={"Authorization": f"Bearer {token}"})
    return r.status_code == 200 and r.json().get("status") == "approved"


async def sync_point(order: dict, token: str | None = None, raise_errors: bool = False):
    """Reads the intent state on Mercado Pago; PROCESSED (or FINISHED with an approved payment) marks the order paid."""
    token = token or await point_token()
    if not order.get("point_intent_id") or not token:
        return order
    code, intent = await point_call("GET", f"/payment-intents/{order['point_intent_id']}", token)
    if code != 200:
        return (code, intent) if raise_errors else order
    state = intent.get("state", "")
    pay_id = str((intent.get("payment") or {}).get("id") or "")
    paid = state == "PROCESSED" or (state in ("FINISHED", "CONFIRMATION_REQUIRED") and pay_id and await payment_approved(pay_id, token))
    upd: dict = {"point_state": state}
    if paid and order.get("payment_status") != "pago":
        upd.update(payment_status="pago", payment_method="Cartão (Point)", receipt_note=f"Pago na maquininha Point (pagamento {pay_id or '?'})")
    await db.orders.update_one({"order_id": order["order_id"]}, {"$set": upd})
    return None if raise_errors else {**order, **upd}
