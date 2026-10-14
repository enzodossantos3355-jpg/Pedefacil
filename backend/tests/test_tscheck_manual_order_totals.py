"""Criterion: 'Manual order form' — total = subtotal + surcharge - discount, computed and
persisted server-side (POST /api/orders) regardless of what the client sends as 'total'."""
import random


def _register_store(client, slug):
    email = f"tscheck-{slug}-{random.randint(100000, 999999)}@teste.com"
    resp = client.post(
        "/auth/register",
        json={"store_name": f"tscheck-{slug}-store-{random.randint(1000, 9999)}", "email": email, "password": "Teste12345", "name": "Tester"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["store_id"], resp.cookies


def test_order_total_computed_server_side_from_surcharge_and_discount(client):
    store_id, cookies = _register_store(client, "ordertotal")
    client.post("/day/open", json={"initial_cash": 0}, cookies=cookies)

    resp = client.post(
        "/orders",
        json={
            "customer_name": "tscheck Totals Cliente",
            "customer_phone": "5511933330000",
            "delivery_type": "Retirada",
            "payment_method": "Pendente",
            "surcharge": 5.0,
            "discount": 2.5,
            "notes": "tscheck observação",
            "items": [
                {"product_id": "x", "name": "Item A", "price": 10.0, "quantity": 2, "size": "", "additionals": []},
                {"product_id": "y", "name": "Item B", "price": 3.0, "quantity": 1, "size": "", "additionals": []},
            ],
        },
        cookies=cookies,
    )
    assert resp.status_code == 200, resp.text
    order = resp.json()
    # subtotal = 10*2 + 3*1 = 23 ; total = 23 + 5 - 2.5 = 25.5
    assert order["subtotal"] == 23.0, order
    assert order["surcharge"] == 5.0, order
    assert order["discount"] == 2.5, order
    assert order["total"] == 25.5, order
    assert order["payment_method"] == "Pendente", order

    fetched = client.get("/orders", cookies=cookies)
    db_order = next(o for o in fetched.json() if o["order_id"] == order["order_id"])
    assert db_order["total"] == 25.5, db_order
