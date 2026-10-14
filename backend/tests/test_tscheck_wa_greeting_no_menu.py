"""Criterion: 'Greeting does not send the menu' — a plain greeting ('oi') must NOT trigger
send_menu / a product list; only an explicit menu request ('manda o cardápio') does."""
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


def test_greeting_does_not_list_products_but_explicit_request_does(client):
    store_id, cookies = _register_store(client, "wagreet")
    _upgrade_to_pro(client, store_id)
    client.post("/day/open", json={"initial_cash": 0}, cookies=cookies)
    product = client.post("/products", json={"name": "tscheck Marmita Especial", "category": "Marmita", "price": 22.0}, cookies=cookies)
    assert product.status_code == 200, product.text
    phone = f"55119{random.randint(10000000, 99999999)}"

    r1 = client.post("/whatsapp/simulate-message", json={"phone": phone, "name": "tscheck Cliente", "text": "oi"}, cookies=cookies)
    assert r1.status_code == 200, r1.text
    chat1 = r1.json()
    bot_msgs = [m["text"] for m in chat1["messages"] if m["sender"] == "bot"]
    assert bot_msgs, chat1
    # No menu-photo batch message and no product name/price dump should appear on a bare greeting.
    assert not any("foto(s) do cardápio" in m for m in bot_msgs), bot_msgs
    assert not any("tscheck Marmita Especial" in m and "22" in m for m in bot_msgs), bot_msgs

    r2 = client.post("/whatsapp/simulate-message", json={"phone": phone, "name": "tscheck Cliente", "text": "manda o cardápio"}, cookies=cookies)
    assert r2.status_code == 200, r2.text
    chat2 = r2.json()
    assert chat2.get("latest_order") is None, "asking for the menu must not create an order"
    bot_msgs2 = [m["text"] for m in chat2["messages"] if m["sender"] == "bot"]
    joined = "\n".join(bot_msgs2)
    assert "tscheck marmita especial" in joined.lower(), f"explicit menu request should list the product: {bot_msgs2}"
