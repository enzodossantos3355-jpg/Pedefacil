"""Runs the WhatsApp bridge (Baileys) inside the backend's lifecycle.

Production runs only uvicorn (no supervisor program for the bridge, no Node in the image), so the backend:
  1. restores every store's Baileys session files from Mongo (`wa_auth`): no QR re-scan after redeploys,
  2. starts the bundled bridge (backend/whatsapp_bridge/bridge.mjs) with the Node runtime shipped via pip
     (nodejs-wheel-binaries) and restarts it if it dies,
  3. backs the session files up to Mongo every few seconds.
Production runs several replicas, but WhatsApp allows one live socket per session: two bridges with the same
credentials keep replacing each other (constant disconnects). So replicas elect one leader through a lease in
Mongo (`wa_leader`); only the leader runs the bridge and the backup, and the others forward their bridge calls
to the leader's /api/wa-bridge proxy.
In the preview, supervisor already runs the bridge (program "whatsapp"), so only the backup loop runs.
"""

import asyncio
import glob
import logging
import os
import shutil
import socket
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from pymongo.errors import DuplicateKeyError

from lib.db import raw_db

logger = logging.getLogger(__name__)
# The bundled bridge lives INSIDE backend/ because the published image only ships backend/ and frontend/
# (whatsapp-service/ is not deployed). Rebuild it with `cd whatsapp-service && yarn bundle`.
BACKEND_DIR = Path(__file__).resolve().parents[1]
BRIDGE = BACKEND_DIR / "whatsapp_bridge" / "bridge.mjs"
_DEV_AUTH = BACKEND_DIR.parent / "whatsapp-service" / "auth"  # preview: supervisor's bridge uses this folder
AUTH_DIR = Path(os.environ.get("WHATSAPP_AUTH_DIR") or (_DEV_AUTH if _DEV_AUTH.parent.exists() else BACKEND_DIR / "whatsapp_bridge" / "auth"))
BACKUP_EVERY = 15
LOCAL_URL = os.environ.get("WHATSAPP_SERVICE_URL", "http://localhost:8002")
LEASE = 20  # seconds a leader keeps the bridge without renewing
TICK = 5  # lease renewal / leader lookup interval
PROXY_PORT = os.environ.get("WHATSAPP_PROXY_PORT", "8080")  # pod's nginx, which serves /api
ME = socket.gethostname()
_state: dict = {"embedded": False, "holder": None, "addr": None}


def embedded() -> bool:
    """True when nothing else manages the bridge (production)."""
    flag = os.environ.get("WHATSAPP_EMBEDDED", "").lower()
    if flag in ("1", "true", "0", "false"):
        return flag in ("1", "true")
    return not glob.glob("/etc/supervisor/conf.d/*whatsapp*")


def node_binary() -> str:
    import nodejs_wheel

    return str(Path(nodejs_wheel.__file__).parent / "bin" / "node")


def my_addr() -> str:
    try:
        return socket.gethostbyname(ME)
    except OSError:
        return ""


def bridge_url() -> str:
    """Base URL for bridge calls: the local bridge, or the leader replica's proxy when another pod leads."""
    holder, addr = _state["holder"], _state["addr"]
    if not _state["embedded"] or not holder or holder == ME or not addr:
        return LOCAL_URL
    return f"http://{addr}:{PROXY_PORT}/api/wa-bridge"


def auth_root() -> Path:
    try:
        AUTH_DIR.mkdir(parents=True, exist_ok=True)
        return AUTH_DIR
    except OSError:  # read-only image filesystem → temp dir (Mongo backup keeps the session anyway)
        fallback = Path(tempfile.gettempdir()) / "pedefacil-wa-auth"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


async def restore_sessions(root: Path) -> int:
    count = 0
    async for doc in raw_db.wa_auth.find({}):
        folder = root / doc["store_id"]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / doc["file"]).write_text(doc["content"], encoding="utf-8")
        count += 1
    return count


async def backup_loop(root: Path) -> None:
    seen: dict[str, float] = {}
    while True:
        try:
            present: set[tuple[str, str]] = set()
            for path in root.glob("*/*.json"):
                store_id, name = path.parent.name, path.name
                present.add((store_id, name))
                mtime = path.stat().st_mtime
                key = f"{store_id}/{name}"
                if seen.get(key) != mtime:
                    await raw_db.wa_auth.update_one({"store_id": store_id, "file": name}, {"$set": {"content": path.read_text(encoding="utf-8")}}, upsert=True)
                    seen[key] = mtime
            # a store that logged out (folder removed by the bridge) loses its saved session too
            stores_on_disk = {s for s, _ in present}
            async for doc in raw_db.wa_auth.find({}, {"store_id": 1, "file": 1}):
                if doc["store_id"] not in stores_on_disk or (doc["store_id"], doc["file"]) not in present:
                    await raw_db.wa_auth.delete_one({"_id": doc["_id"]})
                    seen.pop(f"{doc['store_id']}/{doc['file']}", None)
        except Exception as exc:
            logger.warning("whatsapp session backup: %s", exc)
        await asyncio.sleep(BACKUP_EVERY)


async def run_bridge(root: Path) -> None:
    port = str(urlparse(LOCAL_URL).port or 8002)
    env = {**os.environ, "WHATSAPP_PORT": port, "WHATSAPP_AUTH_DIR": str(root), "BACKEND_URL": os.environ.get("BACKEND_INTERNAL_URL", "http://localhost:8001"),
           "WHATSAPP_INTERNAL_TOKEN": os.environ.get("WHATSAPP_INTERNAL_TOKEN", "")}
    proc = None
    while True:
        try:
            proc = await asyncio.create_subprocess_exec(node_binary(), str(BRIDGE), env=env, cwd=str(BRIDGE.parent))
            logger.info("whatsapp bridge started (pid %s, port %s)", proc.pid, port)
            code = await proc.wait()
            logger.warning("whatsapp bridge exited with %s, restarting", code)
        except asyncio.CancelledError:
            if proc and proc.returncode is None:  # stop the socket before another replica opens one
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), 5)
                except asyncio.TimeoutError:
                    proc.kill()
            raise
        except Exception as exc:
            logger.error("whatsapp bridge failed to start: %s", exc)
        await asyncio.sleep(3)


async def claim_lease(addr: str) -> bool:
    """Take or renew the bridge lease; also records who leads so bridge_url() can route to it."""
    now = time.time()
    try:
        await raw_db.wa_leader.update_one(
            {"_id": "bridge", "$or": [{"holder": ME}, {"expires_at": {"$lt": now}}]},
            {"$set": {"holder": ME, "addr": addr, "expires_at": now + LEASE}},
            upsert=True,
        )
    except DuplicateKeyError:  # another replica holds a live lease
        pass
    doc = await raw_db.wa_leader.find_one({"_id": "bridge"}) or {}
    _state["holder"], _state["addr"] = doc.get("holder"), doc.get("addr")
    return doc.get("holder") == ME


async def stop_tasks(tasks: list[asyncio.Task]) -> None:
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def leader_loop(root: Path) -> None:
    addr = my_addr()
    tasks: list[asyncio.Task] = []
    renewed = 0.0
    try:
        while True:
            try:
                leading = await claim_lease(addr)
                renewed = time.time()
            except Exception as exc:
                logger.warning("whatsapp leader lease: %s", exc)
                leading = bool(tasks) and time.time() - renewed < LEASE - TICK  # step down before the lease can pass on
            if leading and not tasks:
                try:
                    for stale in root.iterdir():  # sessions from an earlier term may be outdated; Mongo has the current ones
                        if stale.is_dir():
                            shutil.rmtree(stale, ignore_errors=True)
                    restored = await restore_sessions(root)
                except Exception as exc:
                    logger.warning("whatsapp session restore: %s", exc)
                else:
                    logger.info("whatsapp: %s leads the bridge, restored %s session files", ME, restored)
                    tasks = [asyncio.create_task(run_bridge(root)), asyncio.create_task(backup_loop(root))]
            elif not leading and tasks:
                logger.warning("whatsapp: %s lost the bridge lease to %s, stopping local bridge", ME, _state["holder"])
                await stop_tasks(tasks)
                tasks = []
            await asyncio.sleep(TICK)
    except asyncio.CancelledError:
        await stop_tasks(tasks)
        try:  # hand over right away instead of making the next replica wait out the lease
            await raw_db.wa_leader.update_one({"_id": "bridge", "holder": ME}, {"$set": {"expires_at": 0}})
        except Exception:
            pass
        raise


async def start() -> list[asyncio.Task]:
    root = auth_root()
    _state["embedded"] = embedded()
    if _state["embedded"]:
        return [asyncio.create_task(leader_loop(root))]
    return [asyncio.create_task(backup_loop(root))]


proxy_router = APIRouter(tags=["whatsapp"])  # replica → leader replica, internal token


@proxy_router.api_route("/wa-bridge/{path:path}", methods=["GET", "POST"], include_in_schema=False)
async def proxy_to_bridge(path: str, request: Request) -> Response:
    token = os.environ.get("WHATSAPP_INTERNAL_TOKEN", "")
    if not token or request.headers.get("x-internal-token") != token:
        raise HTTPException(status_code=401, detail="unauthorized")
    headers = {k: v for k, v in request.headers.items() if k in ("x-internal-token", "x-store-id", "content-type")}
    async with httpx.AsyncClient(timeout=20) as client:
        res = await client.request(request.method, f"{LOCAL_URL}/{path}", content=await request.body(), headers=headers)
    return Response(res.content, status_code=res.status_code, media_type=res.headers.get("content-type"))
