import asyncio
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
from lib.receipt import check_receipt, read_receipt
from lib.mercadopago import confirm_if_paid, create_pix, store_token
from lib.tastes import taste_profile
from models.domain import (
    PaymentPart, pix_amount,
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
    doc = await db.chats.find_one_and_update({"chat_id": chat_id}, {"$set": {"is_human_controlled": input.enable_human, "status": "human" if input.enable_human else "bot_active"}}, return_document=ReturnDocument.AFTER)
    if not doc:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    text = HANDOFF_TEXT if input.enable_human else BACK_TO_AI_TEXT
    doc = await push_message(chat_id, "bot", text)
    await wa_send(doc.get("jid") or doc["phone"], text)
    return await chat_with_order(doc)


HANDOFF_TEXT = "👋 Um atendente da nossa equipe vai assumir o seu atendimento agora. Só um instante!"
BACK_TO_AI_TEXT = "🤖 Seu atendimento voltou para a nossa assistente virtual. Pode me dizer o que precisa 😊"
_chat_locks: dict[str, asyncio.Lock] = {}


def build_system(settings: dict, products: list[dict], zones: list[dict], customer: dict | None, fee_note: str, tastes: dict | None = None) -> str:
    def fmt(options: list[dict]) -> str:
        return ", ".join(f"{o['name']} R$ {o['price']:.2f}" + (f" (apelidos: {'/'.join(o['aliases'])})" if o.get("aliases") else "") for o in options)

    menu = "\n".join(
        f"- id={p['product_id']} | {p['name']} ({p['category']}) R$ {p['price']:.2f}"
        + (" | o cliente pode chamar de: " + ", ".join(p["aliases"]) if p.get("aliases") else "")
        + (" | tamanhos: " + fmt(p["sizes"]) if p.get("sizes") else "")
        + (" | adicionais: " + fmt(p["additionals"]) if p.get("additionals") else "")
        + (f" | estoque: {p['stock']}" if p.get("stock") is not None else "")
        for p in products if p.get("active")
    )
    zone_txt = "\n".join(f"- {z['name']}: R$ {z['fee']:.2f}" for z in zones) or "- taxa padrão"
    prefs = ", ".join((customer or {}).get("preferences", [])) or "nenhuma registrada"
    t = tastes or {}
    tastes_txt = "\n".join(line for line in [
        f"- Pratos favoritos: {', '.join(t['favorites'])}" if t.get("favorites") else "",
        f"- Adicionais que costuma pedir: {', '.join(t['usual_additionals'])}" if t.get("usual_additionals") else "",
        f"- Costuma pedir para: {t['usual_delivery']}" if t.get("usual_delivery") else "",
        f"- Costuma pagar com: {t['usual_payment']}" if t.get("usual_payment") else "",
        f"- Último pedido: {t['last_order']}" if t.get("last_order") else "",
    ] if line) or "- cliente novo, sem histórico"
    return f"""Você é o atendente virtual do restaurante "{settings['store_name']}" no WhatsApp. Responda em português do Brasil, de forma natural, curta, simpática e direta.
Endereço da loja: {(settings['store_address'] + ' ' + settings['store_maps_url']).strip() or 'não cadastrado (NÃO invente; diga que a equipe confirma)'}
Pix da loja: {'configurado (o sistema envia QR/chave quando send_pix=true)' if settings.get('pix_key') else 'NÃO configurado: não prometa enviar Pix; diga que um atendente envia os dados do Pix'}
Horários: {settings['business_hours'] or 'não cadastrado (NÃO invente)'}
Pix: {settings['pix_key_type']} {settings['pix_key']} ({settings['pix_beneficiary']})
CARDÁPIO DISPONÍVEL:
{menu}
ZONAS DE ENTREGA:
{zone_txt}
{fee_note}
Cliente: {(customer or {}).get('name', 'novo cliente')} — {'cliente recorrente com ' + str(customer.get('orders_count', 0)) + ' pedido(s)' if customer and customer.get('orders_count') else 'primeiro contato'}. Preferências e restrições conhecidas: {prefs}. Último endereço: {(customer or {}).get('address', '') or 'não informado'}.
GOSTOS DO CLIENTE (aprendidos do histórico de pedidos):
{tastes_txt}
- Use os gostos para personalizar: a um cliente recorrente, ofereça de forma natural "o de sempre" (o último pedido ou o favorito, com os adicionais de costume). Se ele disser "o de sempre"/"o mesmo", feche esse pedido na hora.
- Respeite SEMPRE as restrições (ex.: vegetariano, sem cebola): não ofereça itens que as contrariem e coloque a restrição nas observações do pedido.
- Se o cliente revelar um gosto ou restrição nova (ex.: "não como carne", "amo farofa"), registre em "preferences".
REGRAS:
- Mensagens CURTAS no estilo WhatsApp: no máximo 2 a 3 linhas. Nada de blocos longos.
- Na primeira mensagem, cumprimente pelo nome (se recorrente, mostre que reconhece) e pergunte o que deseja. NÃO mande o cardápio sem o cliente pedir.
- Só quando o cliente pedir o cardápio ("cardápio", "o que tem hoje", "menu"): liste os pratos ativos com preço, tamanhos e adicionais de forma enxuta e use "send_menu": true (o sistema envia as fotos dos pratos).
- SEJA RÁPIDO: assim que o cliente disser o que quer, FECHE O PEDIDO NA HORA com intent "order_confirmed" e responda com um RESUMO curto do pedido (itens, tamanhos, adicionais, observações, retirada/entrega). NÃO peça confirmação ("posso confirmar?") e não repita perguntas.
- RETIRADA é o padrão: se o cliente não falar em entrega, use delivery_type "Retirada". NUNCA pergunte se é entrega ou retirada. Ao fechar retirada, informe o endereço da loja com o link do Maps.
- PAGAMENTO só depois do pedido fechado. RETIRADA: NÃO pergunte a forma de pagamento; só trate de pagamento se o próprio cliente falar nisso. ENTREGA: junto com o resumo, pergunte uma vez como vai pagar (Pix, dinheiro ou cartão; se dinheiro, o troco) e, quando ele responder, use "order_confirmed" de novo com payment_intent (o sistema atualiza o mesmo pedido). Dizer a forma de pagamento NÃO é pagar: NUNCA diga que o pagamento foi feito/confirmado.
- PAGAMENTO EM 2 FORMAS: se o cliente quiser dividir (ex.: "20 no pix e o resto em dinheiro"), preencha order.payments com as 2 partes [{{"method": "Pix", "amount": 20}}, {{"method": "Dinheiro", "amount": RESTO}}] somando o total do pedido, e payment_intent "Pix + Dinheiro". O Pix enviado será só da parte Pix.
- Se o produto tem tamanhos e o cliente não disse qual, use o tamanho M (ou o primeiro disponível) sem perguntar.
- ENTREGA (só quando o cliente pedir entrega): se não houver endereço nem localização, peça apenas o endereço ou a localização. Com endereço ou localização, feche o pedido informando a taxa. Se veio só a localização, feche e peça o complemento (número, apto, referência) na mesma mensagem.
- ALTERAÇÕES: se o cliente mudar, adicionar ou tirar itens, trocar endereço ou complemento depois de fechar, use "order_confirmed" de novo com o pedido COMPLETO e atualizado. O sistema EDITA o mesmo pedido desta conversa (nunca cria outro); diga "pedido atualizado".
- OBSERVAÇÕES: se o cliente pedir algo especial (ex.: "sem cebola", "molho à parte", "tocar o interfone"), coloque em order.notes.
- PIX: se o cliente quiser pagar com Pix ou pedir a chave/código, use "send_pix": true (o sistema envia o código Pix Copia e Cola; o QR Code só se o cliente pedir QR). Não escreva a chave. Peça o COMPROVANTE depois de pagar, a menos que o Pix seja automático (Mercado Pago), aí a confirmação chega sozinha. Se o cliente mandar um comprovante sem ter pedido o Pix, tudo bem: o sistema confere.
- COMPROVANTES: o sistema confere o comprovante sozinho. Nunca afirme que um pagamento foi recebido.
- O telefone do cliente já é conhecido pelo WhatsApp: NUNCA pergunte o telefone. Números de casa/rua não são telefone.
- Só ofereça itens do cardápio acima.
- Ao fechar o pedido, NÃO escreva preços nem totais: o sistema envia logo abaixo o resumo oficial com o valor correto. Só fale preço quando o cliente perguntar quanto custa um item.
- Se pedir para cancelar ("cancelar pedido", "não quero mais", "desisto"), confirme com educação e use intent "cancel". Se pedir atendente/gerente/humano, use intent "human".
- NUNCA use ferramentas, tags XML, markdown, blocos de código ou termos técnicos. O campo "reply" é exatamente o que o cliente vai ler.
{settings['ai_custom_instructions']}
Responda SOMENTE com JSON válido:
{{"reply": "texto para o cliente", "send_pix": false, "send_menu": false, "intent": "chat|order_confirmed|cancel|human", "preferences": ["preferências alimentares detectadas"],
 "order": {{"items": [{{"product_id": "...", "size": "", "quantity": 1, "additionals": ["nome"]}}], "delivery_type": "Retirada|Entrega", "address": "", "payment_intent": "|Pix|Dinheiro|Cartão Crédito|Cartão Débito|Pix + Dinheiro...", "payments": [], "notes": ""}}}}"""


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
        wanted = [str(x).lower().strip() for x in it.get("additionals", [])]
        adds = [a for a in p.get("additionals", []) if any(w in [a["name"].lower(), *[al.lower() for al in a.get("aliases", [])]] for w in wanted)]
        unit = (size["price"] if size else p["price"]) + sum(a["price"] for a in adds)
        items.append(OrderItem(product_id=p["product_id"], name=p["name"], price=unit, quantity=max(1, int(it.get("quantity", 1))), size=size["name"] if size else "", additionals=adds))
    return items


OPEN_STATUSES = {"$nin": ["Concluído", "Cancelado"]}  # archived (closed-day) orders are never edited


async def linked_order(doc: dict, phone: str) -> dict | None:
    """The order this conversation is working on: the chat's linked order if still open, else the latest open one."""
    if doc.get("order_id"):
        o = await db.orders.find_one({"order_id": doc["order_id"], "status": OPEN_STATUSES, "archived": {"$ne": True}})
        if o:
            return o
    return await db.orders.find_one({"customer_phone": phone, "source": "whatsapp", "status": OPEN_STATUSES, "archived": {"$ne": True}}, sort=[("created_at", -1)])


async def handle_receipt(input: IncomingMessage, doc: dict, phone: str, to: str, settings: dict) -> Chat | None:
    """Photo/PDF from the customer: validates it as a Pix receipt for the open order (strict), else describes it."""
    try:
        data = await read_receipt(input.media_base64, input.media_mime)
    except Exception as exc:
        logger.error("leitura de arquivo falhou: %s", exc)
        data = {}
    order = await linked_order(doc, phone)
    if not data.get("is_receipt") or not order or order.get("payment_status") == "pago":
        input.text = f"{input.text} [o cliente enviou {'um PDF' if 'pdf' in input.media_mime else 'uma imagem'}: {data.get('description') or 'não foi possível ler'}]".strip()
        return None
    if order.get("mp_order_id"):  # automatic Pix: only Mercado Pago can confirm
        if await confirm_if_paid(order):
            return await chat_with_order(await db.chats.find_one({"chat_id": doc["chat_id"]}))
    paid, note = check_receipt(data, pix_amount(order), settings)
    upd = {"payment_status": "pago", "payment_method": "Pix", "receipt_note": note} if paid else {"payment_status": "em_verificacao", "receipt_note": note}
    await db.orders.update_one({"order_id": order["order_id"]}, {"$set": upd})
    text = ("Comprovante conferido ✅ Pagamento do pedido #{id} confirmado. Obrigado!" if paid
            else "Recebi seu comprovante 📎 mas não consegui confirmar automaticamente (valor ou recebedor diferentes). Nossa equipe vai conferir e te avisa já já 🙏").format(id=order["order_id"][-6:].upper())
    doc = await push_message(doc["chat_id"], "bot", text, {} if paid else {"status": "needs_human", "is_human_controlled": True})
    await wa_send(to, text)
    return await chat_with_order(doc)


async def process_message(input: IncomingMessage, simulated: bool = False) -> Chat:
    lock = _chat_locks.setdefault(f"{input.phone}", asyncio.Lock())
    async with lock:
        return await _process_message(input, simulated)


async def _process_message(input: IncomingMessage, simulated: bool = False) -> Chat:
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
    if loc_extra:  # keep the GPS point for the courier: CRM + any open delivery order of this customer
        await db.customers.update_one({"phone": phone}, {"$set": loc_extra})
        await db.orders.update_many({"customer_phone": phone, "status": {"$nin": ["Concluído", "Cancelado"]}}, {"$set": {"latitude": input.latitude, "longitude": input.longitude}})
    doc = await push_message(chat_id, "customer", input.text or ("📎 Arquivo enviado" if input.media_base64 else ""), loc_extra)
    if doc.get("is_human_controlled"):
        return await chat_with_order(doc)
    pending = await linked_order(doc, phone)
    if pending and pending.get("mp_order_id") and pending.get("payment_status") != "pago" and await confirm_if_paid(pending):
        return await chat_with_order(await db.chats.find_one({"chat_id": chat_id}))

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

    if input.media_base64:
        done = await handle_receipt(input, doc, phone, to, settings)
        if done:
            return done
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
        raw = await ask_llm(f"wa-{chat_id}", build_system(settings, products, zones, customer, fee_note, await taste_profile(phone)), f"Conversa até agora:\n{history}\n\nResponda à última mensagem do cliente.")
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
        last = await linked_order(doc, phone)
        if last:  # stays in the history as Cancelado
            await update_order_status(last["order_id"], StatusUpdate(status="Cancelado"))
        extra = {"status": "completed"}
    elif intent == "order_confirmed":
        o = data.get("order") or {}
        items = price_items(o.get("items", []), {p["product_id"]: p for p in products})
        if items:
            dtype = o.get("delivery_type") or "Retirada"
            intent_pay = (o.get("payment_intent") or "").strip()
            split = [PaymentPart(method=str(p.get("method", "")), amount=float(p.get("amount") or 0)) for p in (o.get("payments") or [])[:2] if p.get("method")]
            open_order = await linked_order(doc, phone)
            updated = bool(open_order)
            if open_order:  # changes EDIT this conversation's order (never a duplicate); payment stays as it is
                fee, zone = 0.0, ""
                addr = o.get("address") or open_order.get("address", "")
                if dtype == "Entrega":  # e.g. pickup → delivery: charge the zone fee for the address/location
                    q = await quote_fee_full(zones, settings, open_order.get("latitude") if lat is None else lat, open_order.get("longitude") if lng is None else lng, addr)
                    fee, zone = q["fee"], q["zone_name"]
                order = await update_order(open_order["order_id"], OrderUpdate(delivery_type=dtype, address=addr, payment_intent=intent_pay or open_order.get("payment_intent", ""), payments=split or None, notes=o.get("notes") or open_order.get("notes", ""), items=items, delivery_fee=fee, zone_name=zone))
            else:  # saying how you'll pay is NOT paying: payment_method stays Pendente until a receipt is verified
                order = await create_order_record(OrderCreate(customer_name=doc["customer_name"], customer_phone=phone, delivery_type=dtype, address=o.get("address", ""), payment_method="Pendente", payment_intent=intent_pay, payments=split, notes=o.get("notes", ""), items=items, latitude=lat, longitude=lng, status="Em Análise", source="whatsapp"))
            if lat is not None:  # remember the customer's GPS point in the CRM for the next deliveries
                await db.customers.update_one({"phone": phone}, {"$set": {"last_lat": lat, "last_lng": lng}})
            brl = lambda v: f"{v:.2f}".replace(".", ",")
            head = "Pedido atualizado" if updated else "Pedido"
            reply = f"{reply}\n\n🧾 {head} #{order.order_id[-6:].upper()} • Total R$ {brl(order.total)} (taxa R$ {brl(order.delivery_fee)}). Está em análise e logo confirmamos!".strip()
            extra = {"status": "in_review", "order_id": order.order_id}
            if order.payment_intent == "Pix" and order.payment_status != "pago":
                data["send_pix"] = True
    pix_key, pix_code, pix_qr = "", "", ""
    open_now = await linked_order({**doc, **extra}, phone)
    said = (input.text or "").lower()
    asked_pix = bool(re.search(r"\bpix\b|chave|copia e cola|qr ?code", said)) and not re.search(r"paguei|pago|comprovante|transferi", said)
    wants_pix = bool(data.get("send_pix")) or (asked_pix and intent != "cancel")
    data["send_pix"] = False
    if wants_pix and open_now and open_now.get("payment_status") != "pago":
        if settings["pix_key"] or settings.get("pix_provider") == "mercadopago":
            data["send_pix"] = True
        else:  # never silent: the customer asked and there is no key to send
            logger.warning("Pix pedido mas loja sem chave Pix configurada")
            reply = f"{reply}\n\nUm atendente já te envia os dados do Pix 🙏"
            extra = {**extra, "status": "needs_human", "is_human_controlled": True}
    elif wants_pix and not open_now and intent != "order_confirmed":
        reply = f"{reply}\n\nAssim que você confirmar o pedido, eu te mando o Pix 😊"
    want_qr = bool(re.search(r"\bqr\b|qr ?code|qrcode", said))
    mp_token = await store_token() if settings.get("pix_provider") == "mercadopago" else ""
    if data.get("send_pix") and mp_token:
        data["send_pix"] = False
        mp = await create_pix(open_now, mp_token, pix_amount(open_now))
        if mp and mp["qr_code"]:
            await db.orders.update_one({"order_id": open_now["order_id"]}, {"$set": {"mp_order_id": mp["mp_order_id"], "pix_copia_e_cola": mp["qr_code"]}})
            pix_code, pix_qr = mp["qr_code"], (f"data:image/png;base64,{mp['qr_code_base64']}" if want_qr and mp["qr_code_base64"] else "")
            reply = f"{reply}\n\nAssim que o Pix cair, eu confirmo aqui automaticamente ✅"
        elif not settings["pix_key"]:
            reply = f"{reply}\n\nUm atendente já te envia os dados do Pix 🙏"
            extra = {**extra, "status": "needs_human", "is_human_controlled": True}
        else:
            data["send_pix"] = True  # Mercado Pago failed: falls back to the static Pix
    if data.get("send_pix") and settings["pix_key"]:
        if settings["pix_mode"] == "brcode" and has_feature("pix_qr"):
            pix = await gerar_pix(pix_amount(open_now), open_now["order_id"], settings)
            if pix:
                pix_code, pix_qr = pix["copiaECola"], (pix["qrCodeBase64"] if want_qr else "")
        if not pix_code:
            pix_key = settings["pix_key"]
    if (pix_code or pix_key) and not mp_token and "comprovante" not in reply.lower():
        reply = f"{reply}\n\nDepois de pagar, me manda o comprovante aqui (foto ou PDF) 📎"
    menu_images = [{"image": p["image_url"], "caption": f"{p['name']} · R$ {p['price']:.2f}".replace(".", ",")} for p in products if data.get("send_menu") and p.get("active") and p.get("image_url")][:10]
    doc = await push_message(chat_id, "bot", reply, extra)
    if menu_images:
        await push_message(chat_id, "bot", f"📸 {len(menu_images)} foto(s) do cardápio enviadas")
    if pix_code:
        await push_message(chat_id, "bot", f"{'QR Code + ' if pix_qr else ''}Pix Copia e Cola: {pix_code}")
    elif pix_key:
        await push_message(chat_id, "bot", f"Chave Pix ({settings['pix_key_type']}): {pix_key}")
    await wa_send(to, reply, pix_key, pix_code, pix_qr, menu_images)
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
