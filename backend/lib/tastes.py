"""Customer taste profile learned automatically from order history (favorite dishes, sizes, add-ons, habits)."""

from collections import Counter

from lib.db import db

DONE = {"$ne": "Cancelado"}


def build_profile(orders: list[dict]) -> dict:
    items, adds, delivery, payment = Counter(), Counter(), Counter(), Counter()
    for o in orders:
        delivery[o.get("delivery_type", "")] += 1
        if o.get("payment_method") and o["payment_method"] != "Pendente":
            payment[o["payment_method"]] += 1
        for i in o.get("items", []):
            items[f"{i['name']}{' ' + i['size'] if i.get('size') else ''}"] += i.get("quantity", 1)
            for a in i.get("additionals", []):
                adds[a["name"]] += 1
    last = orders[0] if orders else None
    return {
        "favorites": [f"{name} ({n}x)" for name, n in items.most_common(3)],
        "usual_additionals": [name for name, _ in adds.most_common(3)],
        "usual_delivery": delivery.most_common(1)[0][0] if delivery else "",
        "usual_payment": payment.most_common(1)[0][0] if payment else "",
        "last_order": ", ".join(f"{i.get('quantity', 1)}x {i['name']}{' ' + i['size'] if i.get('size') else ''}" for i in last.get("items", [])) if last else "",
    }


async def taste_profile(phone: str) -> dict:
    orders = await db.orders.find({"customer_phone": phone, "status": DONE}, {"_id": 0, "items": 1, "delivery_type": 1, "payment_method": 1}).sort("created_at", -1).to_list(100)
    return build_profile(orders)


async def all_profiles() -> dict[str, dict]:
    """phone → profile for the CRM list, from a single orders query."""
    by_phone: dict[str, list[dict]] = {}
    for o in await db.orders.find({"status": DONE, "customer_phone": {"$ne": ""}}, {"_id": 0, "customer_phone": 1, "items": 1, "delivery_type": 1, "payment_method": 1}).sort("created_at", -1).to_list(20000):
        by_phone.setdefault(o["customer_phone"], []).append(o)
    return {phone: build_profile(orders) for phone, orders in by_phone.items()}
