"""Central de Suporte: restaurants open tickets with the PedeFácil owner, who replies from the master panel."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from lib.access import master_user, store_user
from lib.db import raw_db
from models.domain import SupportMessageCreate, SupportStatusUpdate, SupportTicket, SupportTicketCreate, new_id

router = APIRouter(tags=["support"])


def now() -> datetime:
    return datetime.now(timezone.utc)


async def add_message(ticket_id: str, flt: dict, sender: str, author: str, text: str, status: str) -> SupportTicket:
    msg = {"id": new_id("msg"), "sender": sender, "author": author, "text": text, "timestamp": now()}
    doc = await raw_db.support_tickets.find_one_and_update({"ticket_id": ticket_id, **flt}, {"$push": {"messages": msg}, "$set": {"status": status, "updated_at": now()}}, return_document=True)
    if not doc:
        raise HTTPException(status_code=404, detail="Chamado não encontrado.")
    return SupportTicket(**doc)


@router.get("/support/tickets", response_model=list[SupportTicket])
async def my_tickets(user: dict = Depends(store_user)):
    return [SupportTicket(**d) for d in await raw_db.support_tickets.find({"store_id": user["store_id"]}).sort("updated_at", -1).to_list(200)]


@router.post("/support/tickets", response_model=SupportTicket)
async def open_ticket(input: SupportTicketCreate, user: dict = Depends(store_user)):
    store = await raw_db.stores.find_one({"store_id": user["store_id"]}) or {}
    ticket = SupportTicket(ticket_id=new_id("tkt"), store_id=user["store_id"], store_name=store.get("name", ""), user_email=user["email"], subject=input.subject,
                           category=input.category, status="aberto", created_at=now(), updated_at=now(),
                           messages=[{"id": new_id("msg"), "sender": "loja", "author": user["name"], "text": input.message, "timestamp": now()}])
    await raw_db.support_tickets.insert_one(ticket.model_dump())
    return ticket


@router.post("/support/tickets/{ticket_id}/messages", response_model=SupportTicket)
async def reply_ticket(ticket_id: str, input: SupportMessageCreate, user: dict = Depends(store_user)):
    return await add_message(ticket_id, {"store_id": user["store_id"]}, "loja", user["name"], input.text, "aberto")


@router.get("/master/tickets", response_model=list[SupportTicket], dependencies=[Depends(master_user)])
async def all_tickets():
    return [SupportTicket(**d) for d in await raw_db.support_tickets.find().sort("updated_at", -1).to_list(500)]


@router.post("/master/tickets/{ticket_id}/messages", response_model=SupportTicket)
async def master_reply(ticket_id: str, input: SupportMessageCreate, user: dict = Depends(master_user)):
    return await add_message(ticket_id, {}, "suporte", "Suporte PedeFácil", input.text, "respondido")


@router.patch("/master/tickets/{ticket_id}", response_model=SupportTicket, dependencies=[Depends(master_user)])
async def master_status(ticket_id: str, input: SupportStatusUpdate):
    doc = await raw_db.support_tickets.find_one_and_update({"ticket_id": ticket_id}, {"$set": {"status": input.status, "updated_at": now()}}, return_document=True)
    if not doc:
        raise HTTPException(status_code=404, detail="Chamado não encontrado.")
    return SupportTicket(**doc)
