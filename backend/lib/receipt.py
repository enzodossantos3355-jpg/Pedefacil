"""Reads Pix receipts (photo or PDF) sent on WhatsApp and checks them against the order.

The AI only EXTRACTS data; the decision is made here with strict rules: an order is marked paid only when the
amount matches the order total AND the recipient matches the store's Pix (key or beneficiary name). Anything
else stays "em_verificacao" for the team to check, so nothing is confirmed as paid without evidence.
"""

import base64
import json
import os
import re
import tempfile
import unicodedata

from emergentintegrations.llm.chat import FileContentWithMimeType, LlmChat, UserMessage

PROMPT = """Você analisa comprovantes de pagamento Pix brasileiros. Leia o arquivo e responda SOMENTE JSON:
{"is_receipt": true|false, "status_ok": true|false, "amount": 0.00, "recipient_name": "", "recipient_key": "", "date": "", "description": ""}
- is_receipt: é um comprovante de transferência/Pix?
- status_ok: o comprovante indica pagamento concluído/efetivado (não agendado, não pendente)?
- amount: valor pago em reais (número). recipient_*: dados de QUEM RECEBEU.
- description: o que é a imagem, em 1 frase (se não for comprovante)."""


def _norm(v: str) -> str:
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFD", (v or "").lower()).encode("ascii", "ignore").decode())


async def read_receipt(media_b64: str, mime: str) -> dict:
    ext = ".pdf" if "pdf" in mime else ".jpg"
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
        f.write(base64.b64decode(media_b64))
        path = f.name
    try:
        chat = LlmChat(api_key=os.environ.get("EMERGENT_LLM_KEY", ""), session_id="receipt", system_message=PROMPT).with_model("gemini", "gemini-2.5-flash")
        raw = await chat.send_message(UserMessage(text="Analise este arquivo.", file_contents=[FileContentWithMimeType(mime_type="application/pdf" if ext == ".pdf" else (mime or "image/jpeg"), file_path=path)]))
    finally:
        os.unlink(path)
    m = re.search(r"\{.*\}", raw or "", re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return {}


def check_receipt(data: dict, order_total: float, settings: dict) -> tuple[bool, str]:
    """Strict validation → (paid?, note for the team)."""
    amount = float(data.get("amount") or 0)
    key, name = _norm(settings.get("pix_key", "")), _norm(settings.get("pix_beneficiary", "") or settings.get("store_name", ""))
    r_key, r_name = _norm(data.get("recipient_key", "")), _norm(data.get("recipient_name", ""))
    key_ok = bool(key and r_key and (key[-8:] in r_key or r_key[-8:] in key))
    first = name[:6]
    name_ok = bool(first and r_name and (first in r_name or r_name[:6] in name))
    amount_ok = abs(amount - order_total) <= 0.01
    note = f"Comprovante: R$ {amount:.2f} para {data.get('recipient_name') or '?'} ({data.get('recipient_key') or 'sem chave'}) em {data.get('date') or '?'}"
    problems = [p for p, ok in (("valor diferente do pedido", amount_ok), ("recebedor não confere", key_ok or name_ok), ("pagamento não concluído", bool(data.get("status_ok")))) if not ok]
    return (not problems), note + (f" — {', '.join(problems)}" if problems else " — conferido")
