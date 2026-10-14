"""PedeFácil plans: features unlocked per plan + limits. Mirrored by frontend/src/lib/plans.ts."""

from datetime import datetime, timezone

BASE_FEATURES = ["pedidos", "pdv", "cardapio", "clientes", "caixa"]
PADRAO_FEATURES = BASE_FEATURES + ["whatsapp_ia", "pix_qr", "zonas", "motoboys", "mesas"]
PRO_FEATURES = PADRAO_FEATURES + ["relatorios_ia", "voz", "audio_whatsapp", "backup", "multi_atendentes"]

PLANS: dict[str, dict] = {
    "trial": {"name": "Teste grátis", "price": 0.0, "features": BASE_FEATURES,
              "limits": {"orders": 20, "products": 8, "customers": 20, "users": 1}},
    "basico": {"name": "Básico", "price": 49.0, "lookup_key": "pedefacil_basico_mensal", "features": BASE_FEATURES,
               "limits": {"users": 2}},
    "padrao": {"name": "Padrão", "price": 99.0, "lookup_key": "pedefacil_padrao_mensal", "features": PADRAO_FEATURES,
               "limits": {"users": 3}},
    "pro": {"name": "Pro", "price": 199.0, "lookup_key": "pedefacil_pro_mensal", "features": PRO_FEATURES,
            "limits": {"users": 20}},
}
PAID_ORDER = ["basico", "padrao", "pro"]
TRIAL_DAYS = 7
GRACE_DAYS = 3


def required_plan(feature: str) -> str:
    return next((p for p in PAID_ORDER if feature in PLANS[p]["features"]), "pro")


def aware(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


def effective(store: dict) -> dict:
    """Plan actually in force right now: paid plan, trial, or expired (no access)."""
    now = datetime.now(timezone.utc)
    status = store.get("status", "trialing")
    trial_end = aware(store.get("trial_ends_at"))
    period_end = aware(store.get("current_period_end"))
    key, expired = None, False
    if status == "active" and (period_end is None or (period_end - now).days > -GRACE_DAYS):
        key = store.get("plan", "basico")
    elif status == "trialing" and trial_end and trial_end > now:
        key = "trial"
    else:
        expired = True
    plan = PLANS.get(key or "trial")
    days_left = max(0, (trial_end - now).days + 1) if key == "trial" and trial_end else None
    return {
        "plan": key or "expired", "plan_name": plan["name"] if key else "Expirado", "status": status,
        "features": plan["features"] if key else [], "limits": plan["limits"] if key else {},
        "expired": expired, "trial_days_left": days_left,
        "trial_ends_at": trial_end, "current_period_end": period_end,
    }
