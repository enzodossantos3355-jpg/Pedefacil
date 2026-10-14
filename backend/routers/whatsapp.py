import json
import logging
import os
import re

import httpx

from fastapi import APIRouter, Header, HTTPException
from pymongo import ReturnDocument

from lib.access import enter_store, has_feature, need
from lib.ai import ask_llm, parse_json, sanitize_phone, wa_call, wa_send
from lib.db import db
from lib.geo import coords_from_text, find_cep, quote_fee_full
from lib.pix import gerar_pix
from lib.stt import transcribe_audio
from models.domain import (
    Chat, ChatMessage, DescriptionRequest, HumanToggle, IncomingMessage, MessageCreate, Order, OrderCreate,
    OrderItem, SimulateMessage, TextRequest, WhatsAppStart, now_utc,
)
from routers.operations import OPEN_DAY, create_order_record, get_settings, report_summary, update_order, update_order_status
from models.domain import OrderUpdate, StatusUpdate

router = APIRouter(tags=["whatsapp"])  # WhatsApp panel: needs the whatsapp_ia plan feature (see server.py)
open_router = APIRouter(tags=["whatsapp"])  # every active store
internal_router = APIRouter(tags=["whatsapp"])  # called by the Baileys bridge (internal token, no session)
logger = logging.getLogger(__name__)
HUMAN_WORDS = ("atendente", "humano", "gerente", "suporte", "pessoa de verdade", "falar com alguém", "falar com o dono", "falar com dono", "reclamação", "reclamacao")


@open_router.get("/whatsapp/status")
async def whatsapp_status():
    if not has_feature("whatsapp_ia"):
        return {"status": "locked", "is_connected": False, "qr_code": None, "pairing_code": None, "phone": None}
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


@router.post("/whatsapp/chats/{chat_id}/message", response_model=Chat, dependencies=OPEN_DAY)
async def send_message(chat_id: str, input: MessageCreate):
    doc = await push_message(chat_id, "attendant", input.text, {"is_human_controlled": True, "status": "needs_human"})
    if not doc:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    await wa_send(doc.get("jid") or doc["phone"], input.text)
    return await chat_with_order(doc)


@router.delete("/whatsapp/chats/{chat_id}")
async def delete_chat(chat_id: str):
    if not (await db.chats.delete_one({"chat_id": chat_id})).deleted_count:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    return {"ok": True}


@router.delete("/whatsapp/chats/{chat_id}/messages/{message_id}", response_model=Chat)
async def delete_message(chat_id: str, message_id: str):
    doc = await db.chats.find_one_and_update({"chat_id": chat_id}, {"$pull": {"messages": {"id": message_id}}}, return_document=ReturnDocument.AFTER)
    if not doc:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    last = doc["messages"][-1] if doc["messages"] else None
    doc = await db.chats.find_one_and_update({"chat_id": chat_id}, {"$set": {"last_message": last["text"] if last else "", **({"last_timestamp": last["timestamp"]} if last else {})}}, return_document=ReturnDocument.AFTER)
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
- SEJA RÁPIDO: assim que o cliente disser o que quer (ex: "quero 3 marmitas"), FECHE O PEDIDO NA HORA com intent "order_confirmed". NÃO peça confirmação e NÃO repita perguntas.
- RETIRADA é o padrão: se o cliente não falar em entrega, use delivery_type "Retirada". NUNCA pergunte se é entrega ou retirada. Ao fechar retirada, informe o endereço da loja com o link do Maps.
- NUNCA pergunte a forma de pagamento. Use payment_method "Pendente", a não ser que o próprio cliente diga como vai pagar (aí registre o que ele disse).
- Se o produto tem tamanhos e o cliente não disse qual, use o tamanho M (ou o primeiro disponível) sem perguntar.
- ENTREGA (só quando o cliente pedir entrega): se não houver endereço nem localização, peça apenas o endereço ou a localização. Com endereço ou localização, feche o pedido informando a taxa. Se veio só a localização, feche e peça o complemento (número, apto, referência) na mesma mensagem.
- Se o cliente mandar um complemento, alteração ou novo item depois de fechar, use "order_confirmed" de novo com o pedido COMPLETO atualizado (o sistema atualiza o mesmo pedido).
- Se o cliente escolher Pix ou pedir a chave, use "send_pix": true (o sistema envia a chave e o botão Copiar chave Pix; não escreva a chave no texto).
- O telefone do cliente já é conhecido pelo WhatsApp: NUNCA pergunte o telefone. Números de casa/rua não são telefone.
- Só ofereça itens do cardápio acima.
- Se pedir para cancelar ("cancelar pedido", "não quero mais", "desisto"), confirme com educação e use intent "cancel". Se pedir atendente/gerente/humano, use intent "human".
- NUNCA use ferramentas, tags XML, markdown, blocos de código ou termos técnicos. O campo "reply" é exatamente o que o cliente vai ler.
{settings['ai_custom_instructions']}
Responda SOMENTE com JSON válido:
{{"reply": "texto para o cliente", "send_pix": false, "intent": "chat|order_confirmed|cancel|human", "preferences": ["preferências alimentares detectadas"],
 "order": {{"items": [{{"product_id": "...", "size": "", "quantity": 1, "additionals": ["nome"]}}], "delivery_type": "Retirada|Entrega", "address": "", "payment_method": "Pendente|Pix|Dinheiro|Cartão Crédito|Cartão Débito", "notes": ""}}}}"""


REPLY_RE = re.compile(r'"reply"\s*:\s*"((?:[^"\\]|\\.)*)"', re.S)


def clean_text(text: str) -> str:
    """Strips anything technical (tool-call tags, code fences, JSON) so the customer only sees natural text."""
    text = re.sub(r"```.*?(```|$)", "", text or "", flags=re.S)
    text = re.sub(r"<[^>]{1,200}>", "", text)
    if "{" in text and '"' in text[text.index("{"):]:
        text = text[: text.index("{")]
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_reply(raw: str) -> dict:
    """Finds the model's JSON object even when wrapped in junk; never returns raw JSON as the reply."""
    raw = raw or ""
    decoder = json.JSONDecoder()
    for i, ch in enumerate(raw):
        if ch == "{":
            try:
                obj, _ = decoder.raw_decode(raw[i:])
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and "reply" in obj:
                return obj
    m = REPLY_RE.search(raw)
    if m:
        try:
            return {"reply": json.loads(f'"{m.group(1)}"'), "intent": "chat"}
        except json.JSONDecodeError:
            pass
    return {"reply": clean_text(raw), "intent": "chat"}


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
    if input.audio_base64 and not has_feature("audio_whatsapp"):
        input.audio_base64 = ""
        input.text = input.text or "[o cliente mandou um áudio, mas este plano não ouve áudios: peça com gentileza para escrever o pedido]"
    if input.audio_base64:
        try:
            heard = await transcribe_audio(input.audio_base64)
        except Exception as exc:
            logger.error("transcrição falhou: %s", exc)
            heard = ""
        input.text = f"{input.text} {heard}".strip() if heard else (input.text or "[áudio não compreendido]")
        input.text = f"🎤 {input.text}"
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
    if lat is not None or find_cep(input.text):
        q = await quote_fee_full(zones, settings, lat, lng, input.text)
        fee_note = f"LOCALIZAÇÃO/CEP RECEBIDO: confirme com gentileza, informe a taxa e, se faltar, peça só o complemento. Taxa de entrega calculada R$ {q['fee']:.2f}" + (f" (zona {q['zone_name']})" if q["zone_name"] else " (fora das zonas: taxa padrão)")
    history = "\n".join(f"{m['sender']}: {m['text']}" for m in doc["messages"][-14:])
    try:
        raw = await ask_llm(f"wa-{chat_id}", build_system(settings, products, zones, customer, fee_note), f"Conversa até agora:\n{history}\n\nResponda à última mensagem do cliente.")
        data = extract_reply(raw)
    except Exception as exc:
        logger.error("LLM falhou: %s", exc)
        data = {"reply": "Desculpe, tive um probleminha agora. Já vou chamar alguém da equipe para te ajudar!", "intent": "human"}

    intent, reply, extra, pix = data.get("intent", "chat"), clean_text(data.get("reply") or "") or "Desculpe, não entendi bem. Pode repetir o que deseja? 😊", {}, ""
    if data.get("preferences"):
        await db.customers.update_one({"phone": phone}, {"$addToSet": {"preferences": {"$each": data["preferences"]}}, "$setOnInsert": {"customer_id": f"cust_{phone}", "name": input.name or "Cliente WhatsApp", "orders_count": 0, "total_spent": 0}}, upsert=True)
    if intent == "human":
        extra = {"is_human_controlled": True, "status": "needs_human"}
    elif intent == "cancel":
        last = await db.orders.find_one({"customer_phone": phone, "status": {"$nin": ["Concluído", "Cancelado"]}}, sort=[("created_at", -1)])
        if last:
            await update_order_status(last["order_id"], StatusUpdate(status="Cancelado"))
        extra = {"status": "completed"}
    elif intent == "order_confirmed":
        o = data.get("order") or {}
        items = price_items(o.get("items", []), {p["product_id"]: p for p in products})
        if items:
            dtype = o.get("delivery_type") or "Retirada"
            open_order = await db.orders.find_one({"customer_phone": phone, "source": "whatsapp", "status": "Em Análise"}, sort=[("created_at", -1)])
            if open_order:  # re-confirmation updates the open order instead of duplicating it
                order = await update_order(open_order["order_id"], OrderUpdate(delivery_type=dtype, address=o.get("address") or open_order.get("address", ""), payment_method=o.get("payment_method") or open_order.get("payment_method"), notes=o.get("notes") or open_order.get("notes", ""), items=items, delivery_fee=0.0 if dtype == "Retirada" else None))
            else:
                order = await create_order_record(OrderCreate(customer_name=doc["customer_name"], customer_phone=phone, delivery_type=dtype, address=o.get("address", ""), payment_method=o.get("payment_method") or "Pendente", notes=o.get("notes", ""), items=items, latitude=lat, longitude=lng, status="Em Análise", source="whatsapp"))
            brl = lambda v: f"{v:.2f}".replace(".", ",")
            reply = f"{reply}\n\n🧾 Pedido #{order.order_id[-6:].upper()} • Total R$ {brl(order.total)} (taxa R$ {brl(order.delivery_fee)}). Está em análise e logo confirmamos!".strip()
            extra = {"status": "in_review"}
            if order.payment_method == "Pix":
                data["send_pix"] = True
    pix_key, pix_code, pix_qr = "", "", ""
    if data.get("send_pix") and settings["pix_key"]:
        if settings["pix_mode"] == "brcode" and has_feature("pix_qr"):
            last = await db.orders.find_one({"customer_phone": phone, "status": {"$nin": ["Concluído", "Cancelado"]}}, sort=[("created_at", -1)])
            pix = await gerar_pix(last["total"], last["order_id"], settings) if last else None
            if pix:
                pix_code, pix_qr = pix["copiaECola"], pix["qrCodeBase64"]
        if not pix_code:
            pix_key = settings["pix_key"]
    doc = await push_message(chat_id, "bot", reply, extra)
    if pix_code:
        await push_message(chat_id, "bot", f"QR Code Pix + Pix Copia e Cola: {pix_code}")
    elif pix_key:
        await push_message(chat_id, "bot", f"Chave Pix ({settings['pix_key_type']}): {pix_key}")
    await wa_send(to, reply, pix_key, pix_code, pix_qr)
    return await chat_with_order(await db.chats.find_one({"chat_id": chat_id}))


@internal_router.post("/whatsapp/incoming")
async def incoming(input: IncomingMessage, x_internal_token: str = Header(default="")):
    if x_internal_token != os.environ.get("WHATSAPP_INTERNAL_TOKEN", ""):
        raise HTTPException(status_code=401, detail="unauthorized")
    if input.jid and not (input.jid.endswith("@s.whatsapp.net") or input.jid.endswith("@lid")):
        return {"ok": True, "ignored": True}
    if not input.store_id:
        return {"ok": True, "ignored": True}
    plan = await enter_store(input.store_id)
    if plan["expired"] or not has_feature("whatsapp_ia"):
        return {"ok": True, "ignored": True}
    await process_message(input)
    return {"ok": True}


@router.post("/whatsapp/simulate-message", response_model=Chat)
async def simulate(input: SimulateMessage):
    return await process_message(IncomingMessage(phone=input.phone, name=input.name, text=input.text, latitude=input.latitude, longitude=input.longitude), simulated=True)


@open_router.post("/ai/generate-description")
async def generate_description(input: DescriptionRequest):
    text = await ask_llm("menu-desc", "Você escreve descrições curtas (máx. 220 caracteres), apetitosas e acolhedoras para cardápios de restaurantes brasileiros. Responda só com a descrição.", f"Prato: {input.name}. Categoria: {input.category}.")
    return {"description": text.strip().strip('"')}


@open_router.post("/ai/parse-order", dependencies=OPEN_DAY)
async def parse_order(input: TextRequest):
    products = await db.products.find({"active": True}, {"_id": 0}).to_list(500)
    menu = "\n".join(f"- id={p['product_id']} | {p['name']} | tamanhos: {[s['name'] for s in p.get('sizes', [])]} | adicionais: {[a['name'] for a in p.get('additionals', [])]}" for p in products)
    raw = await ask_llm("parse-order", f"Converta mensagens de clientes em pedidos estruturados usando SOMENTE este cardápio:\n{menu}\nResponda só JSON: {{\"customer_name\": \"\", \"delivery_type\": \"Entrega|Retirada\", \"address\": \"\", \"payment_method\": \"Pix|Dinheiro|Cartão Crédito|Cartão Débito\", \"notes\": \"\", \"items\": [{{\"product_id\": \"\", \"size\": \"\", \"quantity\": 1, \"additionals\": []}}]}}. Nunca trate número de casa como telefone.", input.text)
    data = parse_json(raw)
    items = price_items(data.get("items", []), {p["product_id"]: p for p in products})
    return {**{k: data.get(k, "") for k in ("customer_name", "delivery_type", "address", "payment_method", "notes")}, "items": [i.model_dump() for i in items]}


@open_router.post("/ai/report-insights", dependencies=[need("relatorios_ia")])
async def report_insights():
    report = await report_summary()
    text = await ask_llm("insights", "Você é consultor de restaurantes e marmitarias. Dê 4 recomendações práticas, curtas e numeradas em português, baseadas nos dados.", json.dumps(report.model_dump(), ensure_ascii=False))
    return {"insights": text.strip()}
