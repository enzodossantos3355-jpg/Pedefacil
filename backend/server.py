import asyncio
from contextlib import asynccontextmanager
from fastapi import HTTPException, FastAPI, APIRouter
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import logging
from pathlib import Path


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
from lib.db import client, db, ensure_indexes
from routers.auth import router as auth_router
from routers.operations import router as operations_router
from routers.auth import ensure_master
from routers.whatsapp import internal_router as whatsapp_internal_router, open_router as whatsapp_open_router, router as whatsapp_router
from routers.billing import router as billing_router
from routers.tables import router as tables_router
from routers.support import router as support_router
from fastapi import Depends
from lib.access import active_store, need
from lib import wa_bridge


# Startup runs before the yield, shutdown after it. Add your own setup/teardown here.
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.index_task = asyncio.create_task(ensure_indexes())  # background: a big index build must not block boot
    app.state.seed_task = asyncio.create_task(ensure_master())
    app.state.wa_tasks = await wa_bridge.start()  # production: runs the WhatsApp bridge; always: session backup
    yield
    for task in app.state.wa_tasks:
        task.cancel()
    await asyncio.gather(*app.state.wa_tasks, return_exceptions=True)  # lets the bridge leader stop and release its lease
    client.close()


# Create the main app without a prefix
app = FastAPI(lifespan=lifespan)

# Create a router with the /api prefix
from routers.mercadopago import public_router as mp_public_router, router as mp_router
api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(support_router)  # store user / master per route
api_router.include_router(billing_router)  # own per-route auth (store user / master / Stripe webhook)
api_router.include_router(whatsapp_internal_router)  # bridge → backend, internal token
async def tables_maintenance():
    raise HTTPException(status_code=503, detail="O sistema de mesas está em manutenção e volta em breve.")


STORE = [Depends(active_store)]  # session → store (tenant) → plan in force
api_router.include_router(operations_router, dependencies=STORE)
api_router.include_router(whatsapp_open_router, dependencies=STORE)
api_router.include_router(whatsapp_router, dependencies=[*STORE, need("whatsapp_ia")])
api_router.include_router(tables_router, dependencies=[*STORE, Depends(tables_maintenance)])
api_router.include_router(mp_public_router)  # Mercado Pago webhook (re-checks with the store's own token)
api_router.include_router(mp_router, dependencies=STORE)

# Add your routes to the router instead of directly to app
@api_router.get("/")
async def root():
    return {"message": "Hello World"}

@api_router.get("/status")
async def get_status():
    return {"ok": True, "service": "marmita-hub-api"}

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Include the router last so every route remains under /api.
app.include_router(api_router)
