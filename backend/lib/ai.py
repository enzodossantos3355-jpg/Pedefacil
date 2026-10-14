"""LLM helpers (Claude Sonnet 5.5 via the Emergent universal key) + WhatsApp bridge client."""

import json
import logging
import os
import re

import httpx
from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger(__name__)
MODEL = ("anthropic", "claude-sonnet-5-5")


async def ask_llm(session_id: str, system: str, text: str) -> str:
    chat = LlmChat(api_key=os.environ.get("EMERGENT_LLM_KEY", ""), session_id=session_id, system_message=system).with_model(*MODEL)
    # Server-side bot/back-office calls: there is no UI stream to feed, so a single response is used.
    return await chat.send_message(UserMessage(text=text))


def parse_json(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw or "", re.S)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


# Street/house numbers must never be mistaken for the customer's phone.
PHONE_RE = re.compile(r"(?:\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}")


def sanitize_phone(phone: str) -> str:
    """Keep only a plausible BR mobile/landline from the sender JID (10-13 digits)."""
    digits = re.sub(r"\D", "", phone or "")
    return digits if 10 <= len(digits) <= 13 else ""


def looks_like_phone(text: str) -> bool:
    return bool(PHONE_RE.search(text or "")) and not re.search(r"(rua|av|avenida|n[ºo°]|número|numero|apto|casa)\s*\d", (text or "").lower())


WA_URL = os.environ.get("WHATSAPP_SERVICE_URL", "http://localhost:8002")
WA_HEADERS = {"x-internal-token": os.environ.get("WHATSAPP_INTERNAL_TOKEN", "")}


async def wa_call(method: str, path: str, body: dict | None = None) -> dict:
    """Each store has its own WhatsApp session in the bridge, selected by the x-store-id header."""
    from lib.tenant import current_store
    from lib.wa_bridge import bridge_url  # another replica may be running the bridge
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            res = await client.request(method, f"{bridge_url()}{path}", json=body, headers={**WA_HEADERS, "x-store-id": current_store.get()})
            return res.json() if res.content else {}
    except Exception as exc:  # bridge offline must never break the panel
        logger.warning("whatsapp bridge %s %s: %s", method, path, exc)
        return {"status": "offline", "is_connected": False, "detail": "Serviço do WhatsApp indisponível"}


async def wa_send(to: str, text: str, pix_key: str = "", pix_code: str = "", pix_qr: str = "", images: list[dict] | None = None) -> bool:
    if not to:
        return False
    res = await wa_call("POST", "/send", {"to": to, "text": text, "pix_key": pix_key or None, "pix_code": pix_code or None, "pix_qr": pix_qr or None, "images": images or []})
    return bool(res.get("ok"))
