"""Criterion: 'Payment never marked paid by the AI' — saying how you'll pay ('vou pagar no pix')
must NOT set payment_status to pago; it stays pendente with payment_intent recorded. Also,
pickup (Retirada) orders must not have the bot ask for a payment method."""
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


def test_payment_intent_never_auto_marks_paid(client):
    store_id, cookies = _register_store(client, "wapay")
    _upgrade_to_pro(client, store_id)
    client.post("/day/open", json={"initial_cash": 0}, cookies=cookies)
    product = client.post("/products", json={"name": "tscheck Marmita Pay", "category": "Marmita", "price": 18.0}, cookies=cookies)
    assert product.status_code == 200, product.text
    phone = f"55119{random.randint(10000000, 99999999)}"

    r1 = client.post("/whatsapp/simulate-message", json={"phone": phone, "name": "tscheck Cliente", "text": "quero 1 marmita pay, entrega na Rua Teste 100"}, cookies=cookies)
    assert r1.status_code == 200, r1.text
    order1 = r1.json().get("latest_order")
    assert order1, r1.text

    r2 = client.post("/whatsapp/simulate-message", json={"phone": phone, "name": "tscheck Cliente", "text": "vou pagar no pix"}, cookies=cookies)
    assert r2.status_code == 200, r2.text
    order2 = r2.json().get("latest_order")
    assert order2, r2.text
    assert order2["order_id"] == order1["order_id"]
    assert order2["payment_method"] == "Pendente", f"payment_method must stay Pendente, got {order2['payment_method']}"
    assert order2["payment_intent"] == "Pix", order2
    assert order2["payment_status"] == "pendente", f"payment_status must stay pendente, got {order2['payment_status']}"

    orders = client.get("/orders", cookies=cookies)
    db_order = next(o for o in orders.json() if o["order_id"] == order1["order_id"])
    assert db_order["payment_method"] == "Pendente"
    assert db_order["payment_status"] == "pendente"


def test_pickup_order_bot_does_not_ask_for_payment_method(client):
    store_id, cookies = _register_store(client, "wapickup")
    _upgrade_to_pro(client, store_id)
    client.post("/day/open", json={"initial_cash": 0}, cookies=cookies)
    product = client.post("/products", json={"name": "tscheck Marmita Pickup", "category": "Marmita", "price": 15.0}, cookies=cookies)
    assert product.status_code == 200, product.text
    phone = f"55119{random.randint(10000000, 99999999)}"

    r1 = client.post("/whatsapp/simulate-message", json={"phone": phone, "name": "tscheck Cliente", "text": "quero 1 marmita pickup para retirar"}, cookies=cookies)
    assert r1.status_code == 200, r1.text
    chat1 = r1.json()
    order1 = chat1.get("latest_order")
    assert order1, chat1
    assert order1["delivery_type"] == "Retirada", order1
    bot_msgs = [m["text"].lower() for m in chat1["messages"] if m["sender"] == "bot"]
    joined = "\n".join(bot_msgs)
    assert "pix, dinheiro" not in joined and "como vai pagar" not in joined and "forma de pagamento" not in joined, bot_msgs
