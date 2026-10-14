"""Idempotent Stripe catalog for the PedeFácil plans. Run: python setup_stripe.py"""

import os

import stripe
from dotenv import load_dotenv

load_dotenv()
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or "sk_test_emergent"

CATALOG = [
    {"emergent_product_id": "pedefacil_basico", "name": "PedeFácil Básico", "tax_code": "txcd_10103001",
     "prices": [{"lookup_key": "pedefacil_basico_mensal", "amount": 4900, "currency": "brl", "interval": "month"}]},
    {"emergent_product_id": "pedefacil_padrao", "name": "PedeFácil Padrão", "tax_code": "txcd_10103001",
     "prices": [{"lookup_key": "pedefacil_padrao_mensal", "amount": 9900, "currency": "brl", "interval": "month"}]},
    {"emergent_product_id": "pedefacil_pro", "name": "PedeFácil Pro", "tax_code": "txcd_10103001",
     "prices": [{"lookup_key": "pedefacil_pro_mensal", "amount": 19900, "currency": "brl", "interval": "month"}]},
]


def ensure_tax_settings(country, line1, city, state="", postal_code=""):
    s = stripe.tax.Settings.retrieve()
    if s.head_office and getattr(s.head_office, "address", None):
        return
    stripe.tax.Settings.modify(
        head_office={"address": {"country": country, "line1": line1, "city": city, "state": state, "postal_code": postal_code}},
        defaults={"tax_behavior": "exclusive"},
    )


def get_or_create_product(entry):
    for p in stripe.Product.list(active=True).auto_paging_iter():
        if p.to_dict().get("metadata", {}).get("emergent_product_id") == entry["emergent_product_id"]:
            return p
    return stripe.Product.create(name=entry["name"], tax_code=entry.get("tax_code"),
                                 metadata={"managed_by": "emergent", "emergent_product_id": entry["emergent_product_id"]})


def main():
    try:
        ensure_tax_settings("BR", "Av. Paulista, 1000", "São Paulo", "SP", "01310-100")
    except stripe.error.StripeError as exc:
        print("tax settings skipped:", exc.user_message)
    for entry in CATALOG:
        product = get_or_create_product(entry)
        for p in entry["prices"]:
            existing = stripe.Price.list(lookup_keys=[p["lookup_key"]], active=True, limit=1).data
            if existing and (existing[0].unit_amount != p["amount"] or existing[0].currency != p["currency"]):
                stripe.Price.modify(existing[0].id, active=False)
                existing = []
            if not existing:
                stripe.Price.create(product=product.id, unit_amount=p["amount"], currency=p["currency"], lookup_key=p["lookup_key"],
                                    transfer_lookup_key=True, recurring={"interval": p["interval"]})
            print("ok", p["lookup_key"])


if __name__ == "__main__":
    main()
