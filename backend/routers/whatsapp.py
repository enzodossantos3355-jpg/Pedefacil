import json
import logging
import os
import re

import httpx

from fastapi import APIRouter, Header, HTTPException
from pymongo import ReturnDocument

from lib.ai import ask_llm, parse_json, sanitize_phone, wa_call, wa_send
from lib.db import db
from lib.geo import quote_fee
from models.domain import (
    Chat, ChatMessage, DescriptionRequest, HumanToggle, IncomingMessage, MessageCreate, Order, OrderCreate,
    OrderItem, SimulateMessage, TextRequest, WhatsAppStart, now_utc,
)
from routers.operations import create_order_record, get_settings, report_summary, update_order_status
from models.domain import StatusUpdate

router = APIRouter(tags=["whatsapp"])
logger = logging.getLogger(__name__)
HUMAN_WORDS = ("atendente", "humano", "gerente", "suporte", "pessoa de verdade", "falar com alguém", "falar com o dono", "falar com dono", "reclamação", "reclamacao")
MAPS_RE = re.compile(r"(-?\d{1,2}\.\d{3,})\s*,\s*(-?\d{1,3}\.\d{3,})")
LINK_RE = re.compile(r"https?://\S*(?:maps\.app\.goo\.gl|goo\.gl/maps|google\.[^/\s]+/maps|maps\.google)\S*", re.I)


async def coords_from_text(text: str) -> tuple[float, float] | None:
    """Reads a Google Maps link (resolving short links) or raw "lat,lng" from the message."""
    link = LINK_RE.search(text or "")
    target = text or ""
    if link:
        target = link.group(0)
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=8) as client:
                target = str((await client.get(target)).url) + " " + target
        except Exception:
            pass
    m = MAPS_RE.search(target)
    if m:
        lat, lng = float(m.group(1)), float(m.group(2))
        if -90 <= lat <= 90 and -180 <= lng <= 180:
            return lat, lng
    return None


@router.get("/whatsapp/status")
async def whatsapp_status():
    return await wa_call("GET", "/status")


@router.post("/whatsapp/start")
async def whatsapp_start(input: WhatsAppStart):
    return await wa_call("POST", "/start", {"pairing_phone": input.pairing_phone or None})


@router.post("/whatsapp/disconnect")
async def whatsapp_disconnect():
    return await wa_call("POST", "/disconnect")


@router.post("/whatsapp/force-reconnect")
async def whatsapp_reconnect():
    return await wa_call("POST", "/reconnect")


async def chat_with_order(doc: dict) -> Chat:
    chat = Chat(**doc)
    last = await db.orders.find_one({"customer_phone": chat.phone}, sort=[("created_at", -1)])
    chat.latest_order = Order(**last) if last else None
    return chat


@router.get("/whatsapp/chats", response_model=list[Chat])
async def list_chats():
    return [await chat_with_order(d) for d in await db.chats.find().sort("last_timestamp", -1).to_list(500)]


@router.get("/whatsapp/chats/{chat_id}", response_model=Chat)
async def get_chat(chat_id: str):
    doc = await db.chats.find_one({"chat_id": chat_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    return await chat_with_order(doc)


async def push_message(chat_id: str, sender: str, text: str, extra: dict | None = None) -> dict:
    msg = ChatMessage(sender=sender, text=text)
    return await db.chats.find_one_and_update(
        {"chat_id": chat_id},
        {"$push": {"messages": msg.model_dump()}, "$set": {"last_message": text, "last_timestamp": msg.timestamp, **(extra or {})}},
        return_document=ReturnDocument.AFTER,
    )


@router.post("/whatsapp/chats/{chat_id}/message", response_model=Chat)
async def send_message(chat_id: str, input: MessageCreate):
    doc = await push_message(chat_id, "attendant", input.text, {"is_human_controlled": True, "status": "needs_human"})
    if not doc:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    await wa_send(doc.get("jid") or doc["phone"], input.text)
    return await chat_with_order(doc)


@router.post("/whatsapp/chats/{chat_id}/toggle-human", response_model=Chat)
async def toggle_human(chat_id: str, input: HumanToggle):
    doc = await db.chats.find_one_and_update({"chat_id": chat_id}, {"$set": {"is_human_controlled": input.enable_human, "status": "needs_human" if input.enable_human else "bot_active"}}, return_document=ReturnDocument.AFTER)
    if not doc:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    return await chat_with_order(doc)


def build_system(settings: dict, products: list[dict], zones: list[dict], customer: dict | None, fee_note: str) -> str:
    def fmt(options: list[dict]) -> str:
        return ", ".join("{} R$ {:.2f}".format(o["name"], o["price"]) for o in options)

    menu = "\n".join(
        f"- id={p['product_id']} | {p['name']} ({p['category']}) R$ {p['price']:.2f}"
        + (" | tamanhos: " + fmt(p["sizes"]) if p.get("sizes") else "")
        + (" | adicionais: " + fmt(p["additionals"]) if p.get("additionals") else "")
        + (f" | estoque: {p['stock']}" if p.get("stock") is not None else "")
        for p in products if p.get("active")
    )
    zone_txt = "\n".join(f"- {z['name']}: R$ {z['fee']:.2f}" for z in zones) or "- taxa padrão"
    prefs = ", ".join((customer or {}).get("preferences", [])) or "nenhuma registrada"
    return f"""Você é o atendente virtual do restaurante "{settings['store_name']}" no WhatsApp. Responda em português do Brasil, de forma natural, curta, simpática e direta.
Endereço da loja: {settings['store_address']} {settings['store_maps_url']}
Horários: {settings['business_hours']}
Pix: {settings['pix_key_type']} {settings['pix_key']} ({settings['pix_beneficiary']})
CARDÁPIO DISPONÍVEL:
{menu}
ZONAS DE ENTREGA:
{zone_txt}
{fee_note}
Cliente: {(customer or {}).get('name', 'novo cliente')} — {'cliente recorrente com ' + str(customer.get('orders_count', 0)) + ' pedido(s)' if customer and customer.get('orders_count') else 'primeiro contato'}. Preferências conhecidas: {prefs}. Último endereço: {(customer or {}).get('address', '') or 'não informado'}.
REGRAS:
- Mensagens CURTAS no estilo WhatsApp: no máximo 2 a 3 linhas. Nada de blocos longos.
- Na primeira mensagem, cumprimente pelo nome; se for recorrente, mostre que reconhece ("que bom te ver de novo").
- Ao apresentar o cardápio, liste os pratos ativos com preço, tamanhos (P, M, G) e adicionais de forma enxuta.
- RETIRADA é o padrão: se o cliente for retirar ou não mencionar entrega, NÃO pergunte forma de pagamento; finalize o pedido (payment_method "Pendente") e informe o endereço da loja com o link do Maps.
- ENTREGA: peça o endereço ou a localização, informe a taxa e só então pergunte a forma de pagamento.
- Se o cliente escolher Pix ou pedir a chave, informe a chave no texto e use "send_pix": true (o sistema envia o botão Copiar chave Pix).
- O telefone do cliente já é conhecido pelo WhatsApp: NUNCA pergunte o telefone. Números de casa/rua não são telefone.
- Se o cliente enviou localização, já calculamos a taxa: peça apenas o complemento (número, apto, ponto de referência).
- Só ofereça itens do cardápio acima. Confirme itens, tamanho, entrega/retirada, endereço e pagamento antes de fechar.
- Quando o cliente confirmar o pedido completo, use intent "order_confirmed".
- Se pedir para cancelar ("cancelar pedido", "não quero mais", "desisto"), confirme com educação e use intent "cancel". Se pedir atendente/gerente/humano, use intent "human".
{settings['ai_custom_instructions']}
Responda SOMENTE com JSON válido:
{{"reply": "texto para o cliente", "send_pix": false, "intent": "chat|order_confirmed|cancel|human", "preferences": ["preferências alimentares detectadas"],
 "order": {{"items": [{{"product_id": "...", "size": "", "quantity": 1, "additionals": ["nome"]}}], "delivery_type": "Retirada|Entrega", "address": "", "payment_method": "Pendente|Pix|Dinheiro|Cartão Crédito|Cartão Débito", "notes": ""}}}}"""


def price_items(raw_items: list[dict], products: dict[str, dict]) -> list[OrderItem]:
    """Prices always come from the catalog, never from the model output."""
    items = []
    for it in raw_items or []:
        p = products.get(it.get("product_id", ""))
        if not p:
            continue
        size = next((s for s in p.get("sizes", []) if s["name"].lower() == str(it.get("size", "")).lower()), None)
        adds = [a for a in p.get("additionals", []) if a["name"].lower() in [str(x).lower() for x in it.get("additionals", [])]]
        unit = (size["price"] if size else p["price"]) + sum(a["price"] for a in adds)
        items.append(OrderItem(product_id=p["product_id"], name=p["name"], price=unit, quantity=max(1, int(it.get("quantity", 1))), size=size["name"] if size else "", additionals=adds))
    return items


async def process_message(input: IncomingMessage, simulated: bool = False) -> Chat:
    phone = sanitize_phone(input.phone) or input.phone
    if input.latitude is None:
        found = await coords_from_text(input.text)
        if found:
            input.latitude, input.longitude = found
    chat_id = phone
    existing = await db.chats.find_one({"chat_id": chat_id})
    if not existing:
        await db.chats.insert_one(Chat(chat_id=chat_id, customer_name=input.name or "Cliente WhatsApp", phone=phone, jid="" if simulated else input.jid).model_dump())
    loc_extra = {"last_lat": input.latitude, "last_lng": input.longitude} if input.latitude is not None else {}
    doc = await push_message(chat_id, "customer", input.text, loc_extra)
    if doc.get("is_human_controlled"):
        return await chat_with_order(doc)

    settings = await get_settings()
    day = await db.day_status.find_one({}) or {}
    to = "" if simulated else (doc.get("jid") or phone)
    if not settings["accepting_orders"] or day.get("is_open") is False:
        text = settings["high_demand_message"] if not settings["accepting_orders"] else settings["closed_message"]
        doc = await push_message(chat_id, "bot", text)
        await wa_send(to, text)
        return await chat_with_order(doc)

    if any(w in input.text.lower() for w in HUMAN_WORDS):
        text = "Certo! Pausei o atendimento automático e já avisei nossa equipe. Uma pessoa vai continuar com você em instantes 🙏"
        doc = await push_message(chat_id, "bot", text, {"is_human_controlled": True, "status": "needs_human"})
        await wa_send(to, text)
        return await chat_with_order(doc)

    products = await db.products.find({}, {"_id": 0}).to_list(500)
    zones = await db.delivery_zones.find({}, {"_id": 0}).to_list(500)
    customer = await db.customers.find_one({"phone": phone}, {"_id": 0})
    fee_note = ""
    lat, lng = doc.get("last_lat"), doc.get("last_lng")
    if lat is not None:
        q = quote_fee(zones, settings, lat, lng, "")
        fee_note = f"LOCALIZAÇÃO RECEBIDA: confirme o recebimento com gentileza, informe a taxa e peça só o complemento. Taxa de entrega calculada R$ {q['fee']:.2f}" + (f" (zona {q['zone_name']})" if q["zone_name"] else " (fora das zonas: taxa padrão)")
    history = "\n".join(f"{m['sender']}: {m['text']}" for m in doc["messages"][-14:])
    try:
        raw = await ask_llm(f"wa-{chat_id}", build_system(settings, products, zones, customer, fee_note), f"Conversa até agora:\n{history}\n\nResponda à última mensagem do cliente.")
        data = parse_json(raw) or {"reply": raw, "intent": "chat"}
    except Exception as exc:
        logger.error("LLM falhou: %s", exc)
        data = {"reply": "Desculpe, tive um probleminha agora. Já vou chamar alguém da equipe para te ajudar!", "intent": "human"}

    intent, reply, extra, pix = data.get("intent", "chat"), data.get("reply") or "", {}, ""
    if data.get("preferences"):
        await db.customers.update_one({"phone": phone}, {"$addToSet": {"preferences": {"$each": data["preferences"]}}, "$setOnInsert": {"customer_id": f"cust_{phone}", "name": input.name or "Cliente WhatsApp", "orders_count": 0, "total_spent": 0}}, upsert=True)
    if intent == "human":
        extra = {"is_human_controlled": True, "status": "needs_human"}
    elif intent == "cancel":
        last = await db.orders.find_one({"customer_phone": phone, "status": {"$nin": ["Entregue", "Cancelado"]}}, sort=[("created_at", -1)])
        if last:
            await update_order_status(last["order_id"], StatusUpdate(status="Cancelado"))
        extra = {"status": "completed"}
    elif intent == "order_confirmed":
        o = data.get("order") or {}
        items = price_items(o.get("items", []), {p["product_id"]: p for p in products})
        if items:
            order = await create_order_record(OrderCreate(customer_name=doc["customer_name"], customer_phone=phone, delivery_type=o.get("delivery_type") or "Retirada", address=o.get("address", ""), payment_method=o.get("payment_method") or "Pendente", notes=o.get("notes", ""), items=items, latitude=lat, longitude=lng, status="Em Análise", source="whatsapp"))
            reply = f"{reply}\n\n🧾 Pedido #{order.order_id[-6:].upper()} • Total R$ {order.total:.2f} (taxa R$ {order.delivery_fee:.2f}). Está em análise e logo confirmamos!".strip()
            extra = {"status": "in_review"}
            if order.payment_method == "Pix" and settings["pix_key"]:
                pix = settings["pix_key"]
    if data.get("send_pix") and settings["pix_key"]:
        pix = settings["pix_key"]
    doc = await push_message(chat_id, "bot", reply, extra)
    if pix:
        await push_message(chat_id, "bot", f"Chave Pix ({settings['pix_key_type']}): {pix}")
    await wa_send(to, reply, pix)
    return await chat_with_order(await db.chats.find_one({"chat_id": chat_id}))


@router.post("/whatsapp/incoming")
async def incoming(input: IncomingMessage, x_internal_token: str = Header(default="")):
    if x_internal_token != os.environ.get("WHATSAPP_INTERNAL_TOKEN", ""):
        raise HTTPException(status_code=401, detail="unauthorized")
    await process_message(input)
    return {"ok": True}


@router.post("/whatsapp/simulate-message", response_model=Chat)
async def simulate(input: SimulateMessage):
    return await process_message(IncomingMessage(phone=input.phone, name=input.name, text=input.text, latitude=input.latitude, longitude=input.longitude), simulated=True)


@router.post("/ai/generate-description")
async def generate_description(input: DescriptionRequest):
    text = await ask_llm("menu-desc", "Você escreve descrições curtas (máx. 220 caracteres), apetitosas e acolhedoras para cardápios de restaurantes brasileiros. Responda só com a descrição.", f"Prato: {input.name}. Categoria: {input.category}.")
    return {"description": text.strip().strip('"')}


@router.post("/ai/parse-order")
async def parse_order(input: TextRequest):
    products = await db.products.find({"active": True}, {"_id": 0}).to_list(500)
    menu = "\n".join(f"- id={p['product_id']} | {p['name']} | tamanhos: {[s['name'] for s in p.get('sizes', [])]} | adicionais: {[a['name'] for a in p.get('additionals', [])]}" for p in products)
    raw = await ask_llm("parse-order", f"Converta mensagens de clientes em pedidos estruturados usando SOMENTE este cardápio:\n{menu}\nResponda só JSON: {{\"customer_name\": \"\", \"delivery_type\": \"Entrega|Retirada\", \"address\": \"\", \"payment_method\": \"Pix|Dinheiro|Cartão Crédito|Cartão Débito\", \"notes\": \"\", \"items\": [{{\"product_id\": \"\", \"size\": \"\", \"quantity\": 1, \"additionals\": []}}]}}. Nunca trate número de casa como telefone.", input.text)
    data = parse_json(raw)
    items = price_items(data.get("items", []), {p["product_id"]: p for p in products})
    return {**{k: data.get(k, "") for k in ("customer_name", "delivery_type", "address", "payment_method", "notes")}, "items": [i.model_dump() for i in items]}


@router.post("/ai/report-insights")
async def report_insights():
    report = await report_summary()
    text = await ask_llm("insights", "Você é consultor de restaurantes e marmitarias. Dê 4 recomendações práticas, curtas e numeradas em português, baseadas nos dados.", json.dumps(report.model_dump(), ensure_ascii=False))
    return {"insights": text.strip()}
