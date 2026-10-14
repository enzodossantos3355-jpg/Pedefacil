"""Criterion: 'WhatsApp changes edit the existing order' — POST /api/whatsapp/simulate-message
for the same phone must keep editing ONE order (never create a second one), including after
the order has moved out of 'Em Análise' into 'Novo'."""
import random
import time

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


def _make_product(client, cookies, name, price):
    resp = client.post("/products", json={"name": name, "category": "Marmita", "price": price}, cookies=cookies)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_whatsapp_edits_same_order_not_creating_duplicate(client):
    store_id, cookies = _register_store(client, "waedit")
    _upgrade_to_pro(client, store_id)
    client.post("/day/open", json={"initial_cash": 0}, cookies=cookies)
    product = _make_product(client, cookies, "tscheck Marmita Feijoada", 20.0)
    phone = f"55119{random.randint(10000000, 99999999)}"

    r1 = client.post("/whatsapp/simulate-message", json={"phone": phone, "name": "tscheck Cliente", "text": "quero 2 marmitas de feijoada"}, cookies=cookies)
    assert r1.status_code == 200, r1.text
    chat1 = r1.json()
    order1 = chat1.get("latest_order")
    assert order1, f"expected an order to be created from first message: {chat1}"
    assert order1["items"][0]["quantity"] == 2, order1

    r2 = client.post("/whatsapp/simulate-message", json={"phone": phone, "name": "tscheck Cliente", "text": "na verdade quero 3"}, cookies=cookies)
    assert r2.status_code == 200, r2.text
    chat2 = r2.json()
    order2 = chat2.get("latest_order")
    assert order2, f"expected an order after the change: {chat2}"
    assert order2["order_id"] == order1["order_id"], "the change must EDIT the same order, not create a new one"
    assert order2["items"][0]["quantity"] == 3, order2
    last_bot_msg = [m for m in chat2["messages"] if m["sender"] == "bot"][-1]["text"]
    assert "atualizado" in last_bot_msg.lower(), last_bot_msg

    orders = client.get("/orders", cookies=cookies)
    assert orders.status_code == 200
    same_phone_orders = [o for o in orders.json() if o["customer_phone"] == phone]
    assert len(same_phone_orders) == 1, f"expected exactly one order for this phone, got {len(same_phone_orders)}"

    # move the order to Novo (approved) and confirm further changes still edit it, not duplicate it
    approve = client.post(f"/orders/{order1['order_id']}/approve", cookies=cookies)
    assert approve.status_code == 200, approve.text
    assert approve.json()["status"] == "Novo"

    r3 = client.post("/whatsapp/simulate-message", json={"phone": phone, "name": "tscheck Cliente", "text": "quero mudar para 4 marmitas"}, cookies=cookies)
    assert r3.status_code == 200, r3.text
    order3 = r3.json().get("latest_order")
    assert order3 and order3["order_id"] == order1["order_id"], f"edit after status=Novo must still touch the same order: {order3}"
    assert order3["items"][0]["quantity"] == 4, order3

    orders_final = client.get("/orders", cookies=cookies)
    same_phone_final = [o for o in orders_final.json() if o["customer_phone"] == phone]
    assert len(same_phone_final) == 1, f"still expected exactly one order for this phone, got {len(same_phone_final)}"
