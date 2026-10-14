"""Criterion: 'Couriers page /entregadores' — add courier (name+WhatsApp), pause/reactivate,
delete; the courier becomes selectable (assignable) on delivery orders."""
import random

MASTER_EMAIL = "enzodossantos3355@gmail.com"
MASTER_PASSWORD = "enzo123cg"


def _register_store(client, slug):
    email = f"tscheck-{slug}-{random.randint(100000, 999999)}@teste.com"
    resp = client.post(
        "/auth/register",
        json={"store_name": f"tscheck-{slug}-store-{random.randint(1000, 9999)}", "email": email, "password": "Teste12345", "name": "Tester"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["store_id"], resp.cookies


def _upgrade_to_pro(client, store_id):
    master_login = client.post("/auth/login", json={"email": MASTER_EMAIL, "password": MASTER_PASSWORD})
    assert master_login.status_code == 200, master_login.text
    upd = client.put(f"/master/stores/{store_id}", json={"plan": "pro", "status": "active"}, cookies=master_login.cookies)
    assert upd.status_code == 200, upd.text


def test_courier_lifecycle_and_assignment_to_order(client):
    store_id, cookies = _register_store(client, "courierlife")
    _upgrade_to_pro(client, store_id)
    client.post("/day/open", json={"initial_cash": 0}, cookies=cookies)

    created = client.post("/couriers", json={"name": "tscheck Entregador Vida", "phone": "5511966660000", "active": True}, cookies=cookies)
    assert created.status_code == 200, created.text
    courier = created.json()
    courier_id = courier["courier_id"]
    assert courier["active"] is True

    listed = client.get("/couriers", cookies=cookies)
    assert any(c["courier_id"] == courier_id for c in listed.json()), listed.text

    order = client.post(
        "/orders",
        json={
            "customer_name": "tscheck Courier Order",
            "customer_phone": "5511955550000",
            "delivery_type": "Entrega",
            "address": "Rua Courier, 1",
            "payment_method": "Pix",
            "items": [{"product_id": "x", "name": "Item", "price": 12, "quantity": 1, "size": "", "additionals": []}],
        },
        cookies=cookies,
    )
    assert order.status_code == 200, order.text
    order_id = order.json()["order_id"]
    # delivery orders assign the courier via PUT /orders/{id} (what the order form's "Entregador" select does)
    assigned = client.put(f"/orders/{order_id}", json={"courier_id": courier_id}, cookies=cookies)
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["courier_id"] == courier_id

    paused = client.put(f"/couriers/{courier_id}", json={"name": courier["name"], "phone": courier["phone"], "active": False}, cookies=cookies)
    assert paused.status_code == 200, paused.text
    assert paused.json()["active"] is False

    reactivated = client.put(f"/couriers/{courier_id}", json={"name": courier["name"], "phone": courier["phone"], "active": True}, cookies=cookies)
    assert reactivated.status_code == 200, reactivated.text
    assert reactivated.json()["active"] is True

    deleted = client.delete(f"/couriers/{courier_id}", cookies=cookies)
    assert deleted.status_code == 200, deleted.text
    after = client.get("/couriers", cookies=cookies)
    assert not any(c["courier_id"] == courier_id for c in after.json()), after.text


def test_courier_creation_requires_motoboys_feature(client):
    store_id, cookies = _register_store(client, "courierlocked")
    # fresh trial store: motoboys feature not unlocked
    resp = client.post("/couriers", json={"name": "tscheck Locked", "phone": "5511944440000", "active": True}, cookies=cookies)
    assert resp.status_code == 403, resp.text
