"""Runs the WhatsApp bridge (Baileys) inside the backend's lifecycle.

Production runs only uvicorn (no supervisor program for the bridge, no Node in the image), so the backend:
  1. restores every store's Baileys session files from Mongo (`wa_auth`): no QR re-scan after redeploys,
  2. starts the bundled bridge (backend/whatsapp_bridge/bridge.mjs) with the Node runtime shipped via pip
     (nodejs-wheel-binaries) and restarts it if it dies,
  3. backs the session files up to Mongo every few seconds.
Production runs several replicas, but WhatsApp allows one live socket per session: two bridges with the same
credentials keep replacing each other (constant disconnects). So replicas elect one leader through a lease in
Mongo (`wa_leader`); only the leader runs the bridge and the backup. The other replicas queue their bridge calls
in Mongo (`wa_rpc`) and the leader runs them on its local bridge and writes the reply back. (Direct pod-to-pod HTTP
to the leader's IP failed in production, so the panel flapped online/offline and some messages never went out.)
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
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pymongo.errors import DuplicateKeyError

from lib.db import raw_db

logger = logging.getLogger(__name__)
# The bundled bridge lives INSIDE backend/ because the published image only ships backend/ and frontend/
# (whatsapp-service/ is not deployed). Rebuild it with `cd whatsapp-service && yarn bundle`.
BACKEND_DIR = Path(__file__).resolve().parents[1]
BRIDGE = BACKEND_DIR / "whatsapp_bridge" / "bridge.mjs"
_DEV_AUTH = BACKEND_DIR.parent / "whatsapp-service" / "auth"  # preview: supervisor's bridge uses this folder
AUTH_DIR = Path(os.environ.get("WHATSAPP_AUTH_DIR") or (_DEV_AUTH if _DEV_AUTH.parent.exists() else BACKEND_DIR / "whatsapp_bridge" / "auth"))
BACKUP_EVERY = 5
LOCAL_URL = os.environ.get("WHATSAPP_SERVICE_URL", "http://localhost:8002")
LEASE = 20  # seconds a leader keeps the bridge without renewing
TICK = 5  # lease renewal / leader lookup interval
RPC_POLL = 0.25  # seconds between queue checks (leader) and reply checks (caller)
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


def forward_to_leader() -> bool:
    """True when another replica runs the bridge, so calls must go through the Mongo queue."""
    holder = _state["holder"]
    return _state["embedded"] and bool(holder) and holder != ME


async def rpc_call(method: str, path: str, body: dict | None, store_id: str, timeout: float) -> dict:
    """Queue one bridge call for the leader replica and wait for its reply."""
    rid = uuid.uuid4().hex
    await raw_db.wa_rpc.insert_one({"_id": rid, "state": "pending", "method": method, "path": path, "body": body, "store_id": store_id,
                                    "expires_at": time.time() + timeout, "created_at": datetime.now(timezone.utc)})
    deadline = time.monotonic() + timeout
    while True:
        await asyncio.sleep(RPC_POLL)
        doc = await raw_db.wa_rpc.find_one({"_id": rid}, {"state": 1, "result": 1})
        if doc and doc["state"] == "done":
            await raw_db.wa_rpc.delete_one({"_id": rid})
            return doc.get("result") or {}
        if time.monotonic() >= deadline:
            # still pending: withdraw it so a late leader cannot run it after the caller gave up (no duplicate sends on retry)
            if (await raw_db.wa_rpc.delete_one({"_id": rid, "state": "pending"})).deleted_count:
                raise TimeoutError(f"no WhatsApp leader answered {method} {path} (leader: {_state['holder']})")
            deadline = time.monotonic() + 20  # the leader already took it: wait for its answer instead of re-sending


async def _rpc_run(doc: dict) -> None:
    headers = {"x-internal-token": os.environ.get("WHATSAPP_INTERNAL_TOKEN", ""), "x-store-id": doc.get("store_id") or ""}
    try:
        async with httpx.AsyncClient(timeout=8 if doc["path"] == "/status" else 20) as client:
            res = await client.request(doc["method"], f"{LOCAL_URL}{doc['path']}", json=doc.get("body"), headers=headers)
            result = res.json() if res.content else {}
    except Exception as exc:
        logger.warning("whatsapp queued %s %s: %s: %s", doc["method"], doc["path"], type(exc).__name__, exc)
        result = {"status": "offline", "is_connected": False, "detail": "Serviço do WhatsApp indisponível"}
    await raw_db.wa_rpc.update_one({"_id": doc["_id"]}, {"$set": {"state": "done", "result": result}})


async def rpc_serve() -> None:
    """Leader only: run the bridge calls other replicas queued in `wa_rpc`."""
    try:
        await raw_db.wa_rpc.create_index("created_at", expireAfterSeconds=300, name="rpc_ttl")  # leftovers from crashed callers
        await raw_db.wa_rpc.create_index([("state", 1), ("created_at", 1)], name="rpc_queue")
    except Exception as exc:
        logger.warning("whatsapp rpc indexes: %s", exc)
    running: set[asyncio.Task] = set()
    while True:
        try:
            doc = await raw_db.wa_rpc.find_one_and_update({"state": "pending", "expires_at": {"$gt": time.time()}}, {"$set": {"state": "running"}},
                                                          sort=[("created_at", 1)])
        except Exception as exc:
            logger.warning("whatsapp rpc queue: %s", exc)
            await asyncio.sleep(1)
            continue
        if not doc:
            await asyncio.sleep(RPC_POLL)
            continue
        task = asyncio.create_task(_rpc_run(doc))  # calls run side by side; a slow send never blocks a status check
        running.add(task)
        task.add_done_callback(running.discard)


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


async def backup_once(root: Path, seen: dict[str, float]) -> None:
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


async def backup_loop(root: Path) -> None:
    seen: dict[str, float] = {}
    try:
        while True:
            try:
                await backup_once(root, seen)
            except Exception as exc:
                logger.warning("whatsapp session backup: %s", exc)
            await asyncio.sleep(BACKUP_EVERY)
    except asyncio.CancelledError:  # shutdown: save what the bridge wrote since the last pass, or a fresh pairing would need a new scan
        try:
            await asyncio.shield(backup_once(root, seen))
        except Exception as exc:
            logger.warning("whatsapp final session backup: %s", exc)
        raise


def _die_with_parent() -> None:
    try:
        import ctypes

        ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, 9)  # PR_SET_PDEATHSIG, SIGKILL (Linux only)
    except Exception:
        pass


async def run_bridge(root: Path) -> None:
    port = str(urlparse(LOCAL_URL).port or 8002)
    env = {**os.environ, "WHATSAPP_PORT": port, "WHATSAPP_AUTH_DIR": str(root), "BACKEND_URL": os.environ.get("BACKEND_INTERNAL_URL", "http://localhost:8001"),
           "WHATSAPP_INTERNAL_TOKEN": os.environ.get("WHATSAPP_INTERNAL_TOKEN", "")}
    proc = None
    while True:
        try:
            # preexec: if the backend is killed without cleanup (SIGKILL/OOM) the kernel kills the bridge too, so it can't linger
            # as a second live socket next to the next leader's bridge
            proc = await asyncio.create_subprocess_exec(node_binary(), str(BRIDGE), env=env, cwd=str(BRIDGE.parent), preexec_fn=_die_with_parent)
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
                    tasks = [asyncio.create_task(run_bridge(root)), asyncio.create_task(backup_loop(root)), asyncio.create_task(rpc_serve())]
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
    # Preview: NO session backup to Mongo. If the preview and the published app shared the same WhatsApp
    # credentials they would keep replacing each other ("conflict: replaced" → device_removed). Only production saves/restores.
    return []

