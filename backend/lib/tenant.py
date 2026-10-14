"""Multi-tenant scoping: every restaurant (store) only ever sees its own documents.

`current_store` is set per request (session → user → store) or by the WhatsApp bridge (store_id in the payload).
ScopedCollection injects {"store_id": current} into every filter and inserted document, so routers keep using
`db.orders.find(...)` unchanged and can never leak another store's data.
"""

from contextvars import ContextVar
from typing import Any

current_store: ContextVar[str] = ContextVar("current_store", default="")
current_plan: ContextVar[dict] = ContextVar("current_plan", default={})

TENANT_COLLECTIONS = {
    "orders", "products", "customers", "delivery_zones", "store_settings", "couriers", "chats",
    "day_status", "day_closes", "tables",
}


def store_id() -> str:
    sid = current_store.get()
    if not sid:
        raise RuntimeError("tenant context missing: no store selected for this operation")
    return sid


class ScopedCollection:
    def __init__(self, raw):
        self.raw = raw

    @staticmethod
    def _f(flt: dict | None) -> dict:
        return {**(flt or {}), "store_id": store_id()}

    @staticmethod
    def _d(doc: dict) -> dict:
        doc["store_id"] = store_id()
        return doc

    def find(self, flt: dict | None = None, *args: Any, **kw: Any):
        return self.raw.find(self._f(flt), *args, **kw)

    async def find_one(self, flt: dict | None = None, *args: Any, **kw: Any):
        return await self.raw.find_one(self._f(flt), *args, **kw)

    async def find_one_and_update(self, flt: dict, update: dict, *args: Any, **kw: Any):
        return await self.raw.find_one_and_update(self._f(flt), update, *args, **kw)

    async def update_one(self, flt: dict, update: dict, *args: Any, **kw: Any):
        return await self.raw.update_one(self._f(flt), update, *args, **kw)

    async def update_many(self, flt: dict, update: dict, *args: Any, **kw: Any):
        return await self.raw.update_many(self._f(flt), update, *args, **kw)

    async def delete_one(self, flt: dict, *args: Any, **kw: Any):
        return await self.raw.delete_one(self._f(flt), *args, **kw)

    async def delete_many(self, flt: dict | None = None, *args: Any, **kw: Any):
        return await self.raw.delete_many(self._f(flt), *args, **kw)

    async def count_documents(self, flt: dict | None = None, *args: Any, **kw: Any):
        return await self.raw.count_documents(self._f(flt), *args, **kw)

    async def insert_one(self, doc: dict, *args: Any, **kw: Any):
        return await self.raw.insert_one(self._d(doc), *args, **kw)

    async def insert_many(self, docs: list[dict], *args: Any, **kw: Any):
        return await self.raw.insert_many([self._d(d) for d in docs], *args, **kw)


class ScopedDB:
    """Drop-in for the motor database: tenant collections are scoped, global ones (users, stores...) are raw."""

    def __init__(self, raw):
        self._raw = raw

    def __getattr__(self, name: str):
        col = self._raw[name]
        return ScopedCollection(col) if name in TENANT_COLLECTIONS else col

    def __getitem__(self, name: str):
        return self.__getattr__(name)
