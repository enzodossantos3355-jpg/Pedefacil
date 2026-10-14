"""Criterion: 'Couriers page with daily working selection and balance' — toggling
POST /couriers/{id}/working marks the courier as working today; moving a delivery order
with a delivery_fee to 'Em Entrega' adds 1 delivery and that fee to the courier's fees_today."""
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


def test_working_toggle_and_fees_today_balance(client):
    store_id, cookies = _register_store(client, "courierbalance")
    _upgrade_to_pro(client, store_id)
    client.post("/day/open", json={"initial_cash": 0}, cookies=cookies)

    created = client.post("/couriers", json={"name": "tscheck Entregador Saldo", "phone": "5511933332222", "active": True}, cookies=cookies)
    assert created.status_code == 200, created.text
    courier_id = created.json()["courier_id"]
    assert created.json()["working_today"] is False
    assert created.json()["fees_today"] == 0

    # toggle on: now working today
    toggled = client.post(f"/couriers/{courier_id}/working", cookies=cookies)
    assert toggled.status_code == 200, toggled.text
    assert toggled.json()["working_today"] is True

    listed = client.get("/couriers", cookies=cookies)
    mine = next(c for c in listed.json() if c["courier_id"] == courier_id)
    assert mine["working_today"] is True

    # toggle off: no longer working today
    toggled_off = client.post(f"/couriers/{courier_id}/working", cookies=cookies)
    assert toggled_off.status_code == 200, toggled_off.text
    assert toggled_off.json()["working_today"] is False

    # toggle back on for the delivery flow
    client.post(f"/couriers/{courier_id}/working", cookies=cookies)

    order = client.post(
        "/orders",
        json={
            "customer_name": "tscheck Saldo Cliente",
            "customer_phone": "5511922223333",
            "delivery_type": "Entrega",
            "address": "Rua Saldo, 10",
            "payment_method": "Pix",
            "delivery_fee": 7.0,
            "items": [{"product_id": "x", "name": "Item", "price": 20, "quantity": 1, "size": "", "additionals": []}],
        },
        cookies=cookies,
    )
    assert order.status_code == 200, order.text
    order_id = order.json()["order_id"]
    assert order.json()["delivery_fee"] == 7.0, order.text

    assigned = client.put(f"/orders/{order_id}", json={"courier_id": courier_id}, cookies=cookies)
    assert assigned.status_code == 200, assigned.text

    # not yet counted while still Em Análise
    before = next(c for c in client.get("/couriers", cookies=cookies).json() if c["courier_id"] == courier_id)
    assert before["deliveries_today"] == 0, before
    assert before["fees_today"] == 0, before

    moved = client.patch(f"/orders/{order_id}/status", json={"status": "Em Entrega"}, cookies=cookies)
    assert moved.status_code == 200, moved.text

    after = next(c for c in client.get("/couriers", cookies=cookies).json() if c["courier_id"] == courier_id)
    assert after["deliveries_today"] == 1, after
    assert after["fees_today"] == 7.0, after
