import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from lib.access import SESSION_COOKIE, check_limit, enter_store, session_user, store_user
from lib.db import db, raw_db
from lib.plans import TRIAL_DAYS
from models.domain import DayStatus, LoginRequest, StoreSettings, TeamMember, TeamMemberCreate, User, UserCreate, new_id

router = APIRouter(prefix="/auth", tags=["auth"])
DEMO_STORE = "store-demo"
DEMO_USERS = {
    "admin@pedefacil.com": ("Administrador da Loja", "admin", "marmita123"),
    "atendente@pedefacil.com": ("Atendente da Loja", "atendente", "marmita123"),
    "master@pedefacil.com": ("Dono do PedeFácil", "master", "master123"),
}


def password_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def public_user(doc: dict) -> User:
    store = await raw_db.stores.find_one({"store_id": doc.get("store_id", "")}) if doc.get("store_id") else None
    return User(id=doc["id"], name=doc["name"], email=doc["email"], role=doc.get("role", "admin"), store_id=doc.get("store_id", ""), store_name=(store or {}).get("name", ""))


async def ensure_demo_users() -> None:
    for email, (name, role, pwd) in DEMO_USERS.items():
        doc = {"id": f"demo-{role}", "name": name, "email": email, "role": role, "password_hash": password_hash(pwd),
               "store_id": "" if role == "master" else DEMO_STORE, "created_at": datetime.now(timezone.utc)}
        await raw_db.users.update_one({"email": email}, {"$setOnInsert": doc}, upsert=True)


async def start_session(response: Response, user: dict) -> None:
    token = secrets.token_urlsafe(32)
    await raw_db.sessions.insert_one({"token": token, "user_id": user["id"], "created_at": datetime.now(timezone.utc)})
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 14)


@router.post("/register", response_model=User)
async def register(input: UserCreate, response: Response):
    """Each signup creates its own restaurant with a 7-day restricted free trial."""
    email = input.email.lower().strip()
    if await raw_db.users.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="Este e-mail já está cadastrado.")
    now = datetime.now(timezone.utc)
    store_id = new_id("store")
    store_name = input.store_name.strip() or f"Restaurante de {input.name.split()[0]}"
    await raw_db.stores.insert_one({"store_id": store_id, "name": store_name, "owner_email": email, "plan": "basico", "status": "trialing",
                                    "trial_ends_at": now + timedelta(days=TRIAL_DAYS), "current_period_end": None, "created_at": now})
    doc = {"id": new_id("user"), "name": input.name, "email": email, "role": "admin", "store_id": store_id,
           "password_hash": password_hash(input.password), "created_at": now}
    await raw_db.users.insert_one(doc)
    await enter_store(store_id)
    await db.store_settings.insert_one(StoreSettings(store_name=store_name, pix_beneficiary=store_name).model_dump())
    await db.day_status.insert_one(DayStatus(opened_at=now).model_dump())
    await start_session(response, doc)
    return await public_user(doc)


@router.post("/login", response_model=User)
async def login(input: LoginRequest, response: Response):
    email = input.email.lower().strip()
    if email in DEMO_USERS:
        await ensure_demo_users()
    user = await raw_db.users.find_one({"email": email})
    if not user or user.get("password_hash") != password_hash(input.password):
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos.")
    await start_session(response, user)
    return await public_user(user)


@router.get("/me", response_model=User)
async def me(request: Request):
    return await public_user(await session_user(request))


@router.post("/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await raw_db.sessions.delete_one({"token": token})
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


def require_admin(user: dict) -> None:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas o administrador da loja gerencia a equipe.")


@router.get("/team", response_model=list[TeamMember])
async def list_team(user: dict = Depends(store_user)):
    return [TeamMember(**u) for u in await raw_db.users.find({"store_id": user["store_id"]}, {"_id": 0}).to_list(100)]


@router.post("/team", response_model=TeamMember)
async def add_team_member(input: TeamMemberCreate, user: dict = Depends(store_user)):
    require_admin(user)
    await check_limit("users", await raw_db.users.count_documents({"store_id": user["store_id"]}))
    email = input.email.lower().strip()
    if await raw_db.users.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="Este e-mail já está cadastrado.")
    doc = {"id": new_id("user"), "name": input.name, "email": email, "role": "atendente", "store_id": user["store_id"],
           "password_hash": password_hash(input.password), "created_at": datetime.now(timezone.utc)}
    await raw_db.users.insert_one(doc)
    return TeamMember(**doc)


@router.delete("/team/{member_id}")
async def remove_team_member(member_id: str, user: dict = Depends(store_user)):
    require_admin(user)
    if member_id == user["id"]:
        raise HTTPException(status_code=400, detail="Você não pode remover a si mesmo.")
    if not (await raw_db.users.delete_one({"id": member_id, "store_id": user["store_id"]})).deleted_count:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    return {"ok": True}
