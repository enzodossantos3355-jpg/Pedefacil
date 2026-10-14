"""Request access chain: session → user → store (tenant) → plan in force → feature/limit checks."""

from fastapi import Depends, HTTPException, Request

from lib.db import raw_db
from lib.plans import PLANS, effective, required_plan
from lib.tenant import current_plan, current_store

SESSION_COOKIE = "marmita_session"


async def session_user(request: Request) -> dict:
    token = request.cookies.get(SESSION_COOKIE)
    session = await raw_db.sessions.find_one({"token": token}) if token else None
    user = await raw_db.users.find_one({"id": session["user_id"]}) if session else None
    if not user:
        raise HTTPException(status_code=401, detail="Sessão expirada. Faça login novamente.")
    return user


async def enter_store(store_id: str) -> dict:
    """Sets the tenant + plan context for this request/task and returns the effective plan."""
    store = await raw_db.stores.find_one({"store_id": store_id}) or {}
    plan = effective(store) if store else effective({"status": "canceled"})
    current_store.set(store_id)
    current_plan.set(plan)
    return plan


async def store_user(request: Request) -> dict:
    """Any logged store user (even with an expired plan) — used by billing/plan screens."""
    user = await session_user(request)
    if user.get("role") == "master" or not user.get("store_id"):
        raise HTTPException(status_code=403, detail="Use o painel master.")
    await enter_store(user["store_id"])
    request.state.user = user
    return user


async def active_store(user: dict = Depends(store_user)) -> dict:
    """Store routes: the plan (trial or paid) must be in force."""
    if current_plan.get().get("expired"):
        raise HTTPException(status_code=402, detail={"code": "plan_expired", "message": "Seu teste grátis ou plano expirou. Escolha um plano para continuar."})
    return user


async def master_user(request: Request) -> dict:
    user = await session_user(request)
    if user.get("role") != "master":
        raise HTTPException(status_code=403, detail="Acesso restrito ao dono do sistema.")
    return user


def has_feature(feature: str) -> bool:
    return feature in current_plan.get().get("features", [])


def plan_error(feature: str) -> HTTPException:
    plan = required_plan(feature)
    return HTTPException(status_code=403, detail={"code": "plan_required", "feature": feature, "required_plan": plan, "message": f"Disponível no plano {PLANS[plan]['name']}. Faça upgrade para usar."})


def need(feature: str):
    async def check() -> None:
        if not has_feature(feature):
            raise plan_error(feature)
    return Depends(check)


async def check_limit(kind: str, current_count: int) -> None:
    limit = current_plan.get().get("limits", {}).get(kind)
    if limit is not None and current_count >= limit:
        names = {"orders": "pedidos", "products": "produtos", "customers": "clientes", "users": "usuários"}
        raise HTTPException(status_code=403, detail={"code": "plan_limit", "feature": kind, "required_plan": "basico" if current_plan.get().get("plan") == "trial" else "pro", "message": f"Limite de {limit} {names.get(kind, kind)} do seu plano atingido. Faça upgrade para continuar."})
