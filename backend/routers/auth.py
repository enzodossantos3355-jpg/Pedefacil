import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Response

from lib.db import db
from models.domain import LoginRequest, User, UserCreate, new_id

router = APIRouter(prefix="/auth", tags=["auth"])
SESSION_COOKIE = "marmita_session"


def password_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def public_user(doc: dict) -> User:
    return User(id=doc["id"], name=doc["name"], email=doc["email"], role=doc.get("role", "admin"))


async def ensure_demo_user(email: str, password: str) -> dict | None:
    if email.lower() not in {"admin@marmitahub.com", "atendente@marmitahub.com"} or password != "marmita123":
        return None
    role = "atendente" if email.lower().startswith("atendente") else "admin"
    doc = {
        "id": f"demo-{role}",
        "name": "Atendente da Loja" if role == "atendente" else "Administrador da Loja",
        "email": email.lower(),
        "role": role,
        "password_hash": password_hash(password),
        "created_at": datetime.now(timezone.utc),
    }
    await db.users.update_one({"email": doc["email"]}, {"$setOnInsert": doc}, upsert=True)
    return await db.users.find_one({"email": doc["email"]})


async def start_session(response: Response, user: dict) -> None:
    token = secrets.token_urlsafe(32)
    await db.sessions.insert_one({"token": token, "user_id": user["id"], "created_at": datetime.now(timezone.utc)})
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 14)


@router.post("/register", response_model=User)
async def register(input: UserCreate, response: Response):
    email = input.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="Este e-mail já está cadastrado.")
    doc = input.model_dump()
    doc.update({"id": new_id("user"), "email": email, "password_hash": password_hash(input.password)})
    doc.pop("password")
    await db.users.insert_one(doc)
    await start_session(response, doc)
    return public_user(doc)


@router.post("/login", response_model=User)
async def login(input: LoginRequest, response: Response):
    email = input.email.lower().strip()
    user = await db.users.find_one({"email": email}) or await ensure_demo_user(email, input.password)
    if not user or user.get("password_hash") != password_hash(input.password):
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos.")
    await start_session(response, user)
    return public_user(user)


@router.get("/me", response_model=User)
async def me(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Sessão não encontrada.")
    session = await db.sessions.find_one({"token": token})
    if not session:
        raise HTTPException(status_code=401, detail="Sessão expirada.")
    user = await db.users.find_one({"id": session["user_id"]})
    if not user:
        raise HTTPException(status_code=401, detail="Usuário não encontrado.")
    return public_user(user)


@router.post("/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await db.sessions.delete_one({"token": token})
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}