"""Criterion: 'Customer notes' — a special request like 'sem farofa' said while ordering
must end up recorded in order.notes."""
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


def test_special_request_goes_into_order_notes(client):
    store_id, cookies = _register_store(client, "wanotes")
    _upgrade_to_pro(client, store_id)
    client.post("/day/open", json={"initial_cash": 0}, cookies=cookies)
    product = client.post("/products", json={"name": "tscheck Marmita Farofa", "category": "Marmita", "price": 20.0}, cookies=cookies)
    assert product.status_code == 200, product.text
    phone = f"55119{random.randint(10000000, 99999999)}"

    r1 = client.post("/whatsapp/simulate-message", json={"phone": phone, "name": "tscheck Cliente", "text": "quero 1 marmita farofa, sem farofa, pra retirar"}, cookies=cookies)
    assert r1.status_code == 200, r1.text
    order1 = r1.json().get("latest_order")
    assert order1, r1.text
    assert "farofa" in order1["notes"].lower(), f"expected 'sem farofa' note on the order, got notes={order1['notes']!r}"

    orders = client.get("/orders", cookies=cookies)
    db_order = next(o for o in orders.json() if o["order_id"] == order1["order_id"])
    assert "farofa" in db_order["notes"].lower(), db_order
