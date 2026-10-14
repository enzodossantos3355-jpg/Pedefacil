import hashlib
import httpx
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from lib.access import SESSION_COOKIE, check_limit, enter_store, session_user, store_user
from lib.db import db, raw_db
from lib.plans import TRIAL_DAYS
from models.domain import GoogleSession, DayStatus, LoginRequest, StoreSettings, TeamMember, TeamMemberCreate, User, UserCreate, new_id

router = APIRouter(prefix="/auth", tags=["auth"])
EMERGENT_SESSION_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"

def password_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def public_user(doc: dict) -> User:
    store = await raw_db.stores.find_one({"store_id": doc.get("store_id", "")}) if doc.get("store_id") else None
    return User(id=doc["id"], name=doc["name"], email=doc["email"], role=doc.get("role", "admin"), store_id=doc.get("store_id", ""), store_name=(store or {}).get("name", ""))


async def ensure_master() -> None:
    """The PedeFácil owner account comes from backend/.env (MASTER_EMAIL / MASTER_PASSWORD)."""
    email = os.environ.get("MASTER_EMAIL", "").lower().strip()
    password = os.environ.get("MASTER_PASSWORD", "")
    if not email or not password:
        return
    await raw_db.users.update_one(
        {"email": email},
        {"$set": {"role": "master", "store_id": "", "password_hash": password_hash(password)},
         "$setOnInsert": {"id": new_id("user"), "name": "Dono do PedeFácil", "email": email, "created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )


async def start_session(response: Response, user: dict) -> None:
    token = secrets.token_urlsafe(32)
    await raw_db.sessions.insert_one({"token": token, "user_id": user["id"], "created_at": datetime.now(timezone.utc)})
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 14)


async def create_store_account(name: str, email: str, store_name: str, pwd_hash: str | None, picture: str = "") -> dict:
    """Each new account gets its own restaurant with a 7-day restricted free trial."""
    now = datetime.now(timezone.utc)
    store_id = new_id("store")
    store_name = store_name.strip() or f"Restaurante de {name.split()[0] if name.strip() else 'Novo'}"
    await raw_db.stores.insert_one({"store_id": store_id, "name": store_name, "owner_email": email, "plan": "basico", "status": "trialing",
                                    "trial_ends_at": now + timedelta(days=TRIAL_DAYS), "current_period_end": None, "created_at": now})
    doc = {"id": new_id("user"), "name": name or email.split("@")[0], "email": email, "role": "admin", "store_id": store_id,
           "password_hash": pwd_hash, "picture": picture, "created_at": now}
    await raw_db.users.insert_one(doc)
    await enter_store(store_id)
    await db.store_settings.insert_one(StoreSettings(store_name=store_name, pix_beneficiary=store_name).model_dump())
    await db.day_status.insert_one(DayStatus(opened_at=now).model_dump())
    return doc


@router.post("/register", response_model=User)
async def register(input: UserCreate, response: Response):
    email = input.email.lower().strip()
    if await raw_db.users.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="Este e-mail já está cadastrado.")
    doc = await create_store_account(input.name, email, input.store_name, password_hash(input.password))
    await start_session(response, doc)
    return await public_user(doc)


@router.post("/google", response_model=User)
async def google_login(input: GoogleSession, response: Response):
    """Emergent-managed Google OAuth: session_id → verified Google profile (server-side) → our own session cookie.
    Existing email logs into its account (any role); a new email signs up with its own store on the trial."""
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.get(EMERGENT_SESSION_URL, headers={"X-Session-ID": input.session_id})
    if res.status_code != 200:
        raise HTTPException(status_code=401, detail="Não foi possível confirmar o login com o Google. Tente novamente.")
    profile = res.json()
    email = (profile.get("email") or "").lower().strip()
    if not email:
        raise HTTPException(status_code=401, detail="Conta Google sem e-mail.")
    user = await raw_db.users.find_one({"email": email})
    if user:
        if profile.get("picture"):
            await raw_db.users.update_one({"id": user["id"]}, {"$set": {"picture": profile["picture"]}})
    else:
        user = await create_store_account(profile.get("name") or "", email, "", None, profile.get("picture") or "")
    await start_session(response, user)
    return await public_user(user)


@router.post("/login", response_model=User)
async def login(input: LoginRequest, response: Response):
    email = input.email.lower().strip()
    user = await raw_db.users.find_one({"email": email})
    if not user or not user.get("password_hash") or user["password_hash"] != password_hash(input.password):
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
