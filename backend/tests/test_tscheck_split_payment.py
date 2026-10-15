"""Criterion: 'Manual order with 2 payment methods' — an order created with
payments=[{method: Pix, amount: 10}, {method: Dinheiro, amount: 0}] has its second
amount recomputed server-side as the remainder of the total, and payment_method is
set to the joined string "Pix + Dinheiro"."""
import random


def _register_store(client, slug):
    email = f"tscheck-{slug}-{random.randint(100000, 999999)}@teste.com"
    resp = client.post(
        "/auth/register",
        json={"store_name": f"tscheck-{slug}-store-{random.randint(1000, 9999)}", "email": email, "password": "Teste12345", "name": "Tester"},
    )
    assert resp.status_code == 200, resp.text
    return resp.cookies


def test_order_split_payment_second_amount_is_remainder(client):
    cookies = _register_store(client, "splitpay")
    client.post("/day/open", json={"initial_cash": 0}, cookies=cookies)

    order = client.post(
        "/orders",
        json={
            "customer_name": "tscheck Split Customer",
            "customer_phone": "5511955554444",
            "delivery_type": "Retirada",
            "payment_method": "Pendente",
            "items": [{"product_id": "x", "name": "Marmita", "price": 20, "quantity": 1, "size": "", "additionals": []}],
            "payments": [{"method": "Pix", "amount": 10}, {"method": "Dinheiro", "amount": 0}],
        },
        cookies=cookies,
    )
    assert order.status_code == 200, order.text
    body = order.json()
    assert body["total"] == 20.0, body
    assert body["payment_method"] == "Pix + Dinheiro", body
    assert len(body["payments"]) == 2, body
    assert body["payments"][0] == {"method": "Pix", "amount": 10.0}, body
    assert body["payments"][1]["method"] == "Dinheiro", body
    assert body["payments"][1]["amount"] == 10.0, body  # remainder of 20 - 10

    fetched = client.get("/orders", cookies=cookies)
    saved = next((o for o in fetched.json() if o["order_id"] == body["order_id"]), None)
    assert saved is not None
    assert saved["payment_method"] == "Pix + Dinheiro"
    assert saved["payments"][1]["amount"] == 10.0
