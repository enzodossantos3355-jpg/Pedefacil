"""Shared Mongo handle — import `client`/`db` from here (server.py, routers, seed.py)."""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING, IndexModel

from lib.tenant import ScopedDB

load_dotenv(Path(__file__).parent.parent / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
raw_db = client[os.environ["DB_NAME"]]
db = ScopedDB(raw_db)  # tenant collections are auto-scoped to the current store (lib/tenant.py)

logger = logging.getLogger(__name__)

# One entry per collection: every field a route filters, sorts, or dedupes on. Applied by ensure_indexes() at startup.
INDEXES: dict[str, list[IndexModel]] = {
    "status_checks": [IndexModel([("timestamp", DESCENDING)], name="timestamp_desc")],
    "users": [IndexModel([("email", ASCENDING)], name="email_unique", unique=True)],
    "sessions": [IndexModel([("token", ASCENDING)], name="token_unique", unique=True)],
    "orders": [IndexModel([("order_id", ASCENDING)], name="order_id_unique", unique=True), IndexModel([("created_at", DESCENDING)], name="created_desc")],
    "products": [IndexModel([("product_id", ASCENDING)], name="product_id_unique", unique=True)],
    "customers": [IndexModel([("customer_id", ASCENDING)], name="customer_id_unique", unique=True)],
    "chats": [IndexModel([("store_id", ASCENDING), ("chat_id", ASCENDING)], name="store_chat_unique", unique=True)],
    "stores": [IndexModel([("store_id", ASCENDING)], name="store_id_unique", unique=True)],
    "payment_transactions": [IndexModel([("session_id", ASCENDING)], name="session_unique", unique=True)],
}


async def ensure_indexes() -> None:
    for collection, models in INDEXES.items():
        for model in models:  # one at a time so a bad spec skips only itself
            try:
                await raw_db[collection].create_indexes([model])
            except Exception as exc:  # never block boot on an index; the log line names what to fix
                logger.error("ensure_indexes(%s.%s): %s", collection, model.document["name"], exc)
