"""Optional dine-in tables (mesas): open a table, launch orders to the kitchen, close the bill."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from lib.db import db
from models.domain import DiningTable, Order, OrderCreate, StatusUpdate, TableClose, TableCreate, TableOrderCreate, TableView
from routers.operations import OPEN_DAY, create_order_record, update_order_status

router = APIRouter(tags=["tables"])
OPEN = {"$nin": ["Concluído", "Cancelado"]}


async def view(doc: dict) -> TableView:
    orders = [Order(**o) for o in await db.orders.find({"table_number": doc["number"], "status": OPEN}).sort("created_at", 1).to_list(200)] if doc["status"] == "ocupada" else []
    return TableView(**doc, orders=orders, total=round(sum(o.total for o in orders), 2))


async def get_table(table_id: str) -> dict:
    doc = await db.tables.find_one({"table_id": table_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Mesa não encontrada.")
    return doc


@router.get("/tables", response_model=list[TableView])
async def list_tables():
    return [await view(d) for d in await db.tables.find({}, {"_id": 0}).sort("number", 1).to_list(500)]


@router.post("/tables", response_model=TableView)
async def create_table(input: TableCreate):
    if await db.tables.find_one({"number": input.number}):
        raise HTTPException(status_code=409, detail=f"A mesa {input.number} já existe.")
    table = DiningTable(**input.model_dump())
    await db.tables.insert_one(table.model_dump())
    return TableView(**table.model_dump())


@router.delete("/tables/{table_id}")
async def delete_table(table_id: str):
    if (await get_table(table_id))["status"] == "ocupada":
        raise HTTPException(status_code=409, detail="Feche a conta da mesa antes de removê-la.")
    await db.tables.delete_one({"table_id": table_id})
    return {"ok": True}


@router.post("/tables/{table_id}/orders", response_model=TableView, dependencies=OPEN_DAY)
async def add_table_order(table_id: str, input: TableOrderCreate):
    table = await get_table(table_id)
    if not input.items:
        raise HTTPException(status_code=422, detail="Adicione pelo menos um item.")
    await create_order_record(OrderCreate(customer_name=input.customer_name or f"Mesa {table['number']}", delivery_type="Mesa", payment_method="Pendente",
                                          notes=input.notes, items=input.items, status="Novo", table_number=table["number"]))
    if table["status"] == "livre":
        await db.tables.update_one({"table_id": table_id}, {"$set": {"status": "ocupada", "opened_at": datetime.now(timezone.utc)}})
    return await view(await get_table(table_id))


@router.post("/tables/{table_id}/close", response_model=TableView, dependencies=OPEN_DAY)
async def close_table(table_id: str, input: TableClose):
    table = await get_table(table_id)
    for o in await db.orders.find({"table_number": table["number"], "status": OPEN}).to_list(200):
        await db.orders.update_one({"order_id": o["order_id"]}, {"$set": {"payment_method": input.payment_method}})
        await update_order_status(o["order_id"], StatusUpdate(status="Concluído"))
    await db.tables.update_one({"table_id": table_id}, {"$set": {"status": "livre", "opened_at": None}})
    return await view(await get_table(table_id))
