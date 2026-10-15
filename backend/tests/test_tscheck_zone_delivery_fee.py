"""Criterion: 'Manual order delivery fee selectable from created zones' — a delivery zone's fee
can be attached to a manual order via zone_name + delivery_fee, and the saved order persists
both exactly."""
import random


def _register_store(client, slug):
    email = f"tscheck-{slug}-{random.randint(100000, 999999)}@teste.com"
    resp = client.post(
        "/auth/register",
        json={"store_name": f"tscheck-{slug}-store-{random.randint(1000, 9999)}", "email": email, "password": "Teste12345", "name": "Tester"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["store_id"], resp.cookies


def _upgrade_to_padrao(client, store_id):
    master_login = client.post("/auth/login", json={"email": "enzodossantos3355@gmail.com", "password": "enzo123cg"})
    assert master_login.status_code == 200, master_login.text
    upd = client.put(f"/master/stores/{store_id}", json={"plan": "padrao", "status": "active"}, cookies=master_login.cookies)
    assert upd.status_code == 200, upd.text


def test_order_persists_zone_fee_and_name(client):
    store_id, cookies = _register_store(client, "zonefee")
    _upgrade_to_padrao(client, store_id)
    client.post("/day/open", json={"initial_cash": 0}, cookies=cookies)

    zone = client.post("/delivery-zones", json={"name": "tscheck Centro", "fee": 6.0, "kind": "keyword", "value": "centro"}, cookies=cookies)
    assert zone.status_code == 200, zone.text

    order = client.post(
        "/orders",
        json={
            "customer_name": "tscheck Zone Order",
            "customer_phone": "5511933330000",
            "delivery_type": "Entrega",
            "address": "Rua Zona, 10",
            "payment_method": "Pendente",
            "zone_name": "tscheck Centro",
            "delivery_fee": 6.0,
            "items": [{"product_id": "x", "name": "Marmita", "price": 20, "quantity": 1, "size": "", "additionals": []}],
        },
        cookies=cookies,
    )
    assert order.status_code == 200, order.text
    body = order.json()
    assert body["zone_name"] == "tscheck Centro", body
    assert body["delivery_fee"] == 6.0, body
    assert body["total"] == 26.0, body

    fetched = client.get("/orders", cookies=cookies)
    assert fetched.status_code == 200, fetched.text
    saved = next((o for o in fetched.json() if o["order_id"] == body["order_id"]), None)
    assert saved is not None, fetched.text
    assert saved["zone_name"] == "tscheck Centro"
    assert saved["delivery_fee"] == 6.0
