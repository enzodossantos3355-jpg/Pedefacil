"""Plans & billing (Stripe subscriptions, claimable sandbox) + master panel for the PedeFácil owner."""

import logging
import os
from datetime import datetime, timedelta, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request

from lib.access import master_user, store_user
from lib.db import raw_db
from lib.plans import PLANS, PAID_ORDER, effective
from lib.tenant import current_plan
from models.domain import CheckoutRequest, PlanInfo, PlanOption, PlatformSettings, StoreAdmin, StoreAdminUpdate

router = APIRouter(tags=["billing"])
logger = logging.getLogger(__name__)
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or "sk_test_emergent"
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
PERIOD_DAYS = 31


def now() -> datetime:
    return datetime.now(timezone.utc)


async def activate(store_id: str, plan: str, subscription_id: str | None) -> None:
    await raw_db.stores.update_one({"store_id": store_id}, {"$set": {"plan": plan, "status": "active", "current_period_end": now() + timedelta(days=PERIOD_DAYS), "stripe_subscription_id": subscription_id}})


@router.get("/billing/plans", response_model=list[PlanOption])
async def list_plans():
    return [PlanOption(key=k, name=PLANS[k]["name"], price=PLANS[k]["price"], features=PLANS[k]["features"], limits=PLANS[k]["limits"]) for k in PAID_ORDER]


@router.get("/billing/me", response_model=PlanInfo)
async def my_plan(user: dict = Depends(store_user)):
    settings = await raw_db.store_settings.find_one({"store_id": user["store_id"]}) or {}
    return PlanInfo(**current_plan.get(), tables_enabled=bool(settings.get("tables_enabled")))


@router.post("/billing/checkout")
async def create_checkout(input: CheckoutRequest, user: dict = Depends(store_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas o administrador pode assinar um plano.")
    prices = stripe.Price.list(lookup_keys=[PLANS[input.plan]["lookup_key"]], active=True, limit=1).data
    if not prices:
        raise HTTPException(status_code=500, detail="Plano não encontrado no Stripe.")
    price = prices[0]
    kwargs = dict(
        line_items=[{"price": price.id, "quantity": 1}],
        mode="subscription",
        success_url=f"{input.origin_url}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{input.origin_url}/payment/cancel",
        customer_email=user["email"],
        metadata={"store_id": user["store_id"], "plan": input.plan, "user_id": user["id"]},
        subscription_data={"metadata": {"store_id": user["store_id"], "plan": input.plan}},
    )
    session = stripe.checkout.Session.create(**kwargs)  # Stripe Tax is not available for BR accounts: card payment only
    await raw_db.payment_transactions.insert_one({
        "session_id": session.id, "user_id": user["id"], "store_id": user["store_id"], "plan": input.plan,
        "lookup_key": PLANS[input.plan]["lookup_key"], "amount": PLANS[input.plan]["price"], "currency": "brl",
        "status": "initiated", "payment_status": "pending", "created_at": now(), "updated_at": now(),
    })
    return {"checkout_url": session.url, "session_id": session.id}


async def mark_paid(session_id: str, subscription_id: str | None) -> None:
    record = await raw_db.payment_transactions.find_one_and_update(
        {"session_id": session_id, "payment_status": {"$ne": "paid"}},
        {"$set": {"status": "completed", "payment_status": "paid", "stripe_subscription_id": subscription_id, "updated_at": now()}},
    )
    if record:  # first path to confirm wins (poll or webhook) — DB first, then the plan is unlocked
        await activate(record["store_id"], record["plan"], subscription_id)


@router.get("/payments/status/{session_id}")
async def payment_status(session_id: str):
    record = await raw_db.payment_transactions.find_one({"session_id": session_id})
    if not record:
        raise HTTPException(status_code=404, detail="Transação não encontrada.")
    if record.get("payment_status") != "paid":
        try:
            s = stripe.checkout.Session.retrieve(session_id)
            if s.payment_status == "paid" or s.status == "complete":
                await mark_paid(session_id, s.subscription)
                record = await raw_db.payment_transactions.find_one({"session_id": session_id})
        except stripe.error.StripeError:
            pass
    return {"session_id": record["session_id"], "status": record["status"], "payment_status": record["payment_status"]}


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(payload, request.headers.get("stripe-signature", ""), STRIPE_WEBHOOK_SECRET)
    except (stripe.error.SignatureVerificationError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid signature")
    obj, t = event["data"]["object"], event["type"]
    if t == "checkout.session.completed":
        await mark_paid(obj["id"], obj.get("subscription"))
    elif t in ("checkout.session.expired", "checkout.session.async_payment_failed"):
        await raw_db.payment_transactions.update_one({"session_id": obj["id"], "payment_status": {"$ne": "paid"}}, {"$set": {"status": "failed" if "failed" in t else "expired", "payment_status": "failed" if "failed" in t else "expired", "updated_at": now()}})
    elif t == "invoice.paid" and obj.get("subscription"):  # monthly renewal
        await raw_db.stores.update_one({"stripe_subscription_id": obj["subscription"]}, {"$set": {"status": "active", "current_period_end": now() + timedelta(days=PERIOD_DAYS)}})
    elif t == "customer.subscription.deleted":
        await raw_db.stores.update_one({"stripe_subscription_id": obj["id"]}, {"$set": {"status": "canceled"}})
    return {"status": "ok"}


# ---------- Master panel (PedeFácil owner) ----------

async def store_admin(doc: dict) -> StoreAdmin:
    return StoreAdmin(**{k: doc.get(k) for k in ("store_id", "name", "owner_email", "plan", "status", "trial_ends_at", "current_period_end", "created_at")},
                      effective_plan=effective(doc)["plan"], orders_count=await raw_db.orders.count_documents({"store_id": doc["store_id"]}))


@router.get("/master/stores", response_model=list[StoreAdmin], dependencies=[Depends(master_user)])
async def master_stores():
    return [await store_admin(d) for d in await raw_db.stores.find().sort("created_at", -1).to_list(1000)]


@router.put("/master/stores/{store_id}", response_model=StoreAdmin, dependencies=[Depends(master_user)])
async def master_update_store(store_id: str, input: StoreAdminUpdate):
    doc = await raw_db.stores.find_one({"store_id": store_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Loja não encontrada.")
    patch: dict = {}
    if input.plan:
        patch["plan"] = input.plan
    if input.status:
        patch["status"] = input.status
        if input.status == "active" and not doc.get("current_period_end"):
            patch["current_period_end"] = now() + timedelta(days=PERIOD_DAYS)
    if input.extend_days:
        field = "trial_ends_at" if (input.status or doc.get("status")) == "trialing" else "current_period_end"
        base = max(filter(None, [doc.get(field) and doc[field].replace(tzinfo=timezone.utc), now()]))
        patch[field] = base + timedelta(days=input.extend_days)
    updated = await raw_db.stores.find_one_and_update({"store_id": store_id}, {"$set": patch}, return_document=True)
    return await store_admin(updated)


async def platform_settings() -> PlatformSettings:
    return PlatformSettings(**(await raw_db.platform_settings.find_one({}, {"_id": 0}) or {}))


@router.get("/master/settings", response_model=PlatformSettings, dependencies=[Depends(master_user)])
async def get_platform_settings():
    return await platform_settings()


@router.put("/master/settings", response_model=PlatformSettings, dependencies=[Depends(master_user)])
async def put_platform_settings(input: PlatformSettings):
    await raw_db.platform_settings.update_one({}, {"$set": input.model_dump()}, upsert=True)
    return input
