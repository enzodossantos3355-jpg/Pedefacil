"""Criterion: 'Send delivery sheet to courier via WhatsApp' (send-courier) validates
the order and the assigned courier before touching WhatsApp, and fails cleanly when
the store's WhatsApp is not connected (the real state of a fresh test store)."""
import random

MASTER_EMAIL = "enzodossantos3355@gmail.com"
MASTER_PASSWORD = "enzo123cg"


def _register_store(client, slug):
    email = f"tscheck-{slug}-{random.randint(100000, 999999)}@teste.com"
    resp = client.post(
        "/auth/register",
        json={
            "store_name": f"tscheck-{slug}-store-{random.randint(1000, 9999)}",
            "email": email,
            "password": "Teste12345",
            "name": "Tester",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["store_id"], resp.cookies


def _upgrade_to_padrao(client, store_id):
    master_login = client.post("/auth/login", json={"email": MASTER_EMAIL, "password": MASTER_PASSWORD})
    assert master_login.status_code == 200, master_login.text
    upd = client.put(f"/master/stores/{store_id}", json={"plan": "padrao", "status": "active"}, cookies=master_login.cookies)
    assert upd.status_code == 200, upd.text


def test_send_courier_unknown_order_404(client):
    store_id, cookies = _register_store(client, "couriersend404")
    _upgrade_to_padrao(client, store_id)
    resp = client.post("/orders/tscheck-nonexistent-order-id/send-courier", cookies=cookies)
    assert resp.status_code == 404, resp.text


def test_send_courier_without_assigned_courier_422(client):
    store_id, cookies = _register_store(client, "couriersend422")
    _upgrade_to_padrao(client, store_id)
    order = client.post(
        "/orders",
        json={
            "customer_name": "tscheck Cliente",
            "customer_phone": "5511999990000",
            "delivery_type": "Entrega",
            "address": "Rua Teste, 123",
            "payment_method": "Pix",
            "items": [{"product_id": "x", "name": "Item", "price": 10, "quantity": 1, "size": "", "additionals": []}],
        },
        cookies=cookies,
    )
    assert order.status_code == 200, order.text
    order_id = order.json()["order_id"]
    resp = client.post(f"/orders/{order_id}/send-courier", cookies=cookies)
    assert resp.status_code == 422, resp.text


def test_send_courier_with_phone_fails_when_whatsapp_disconnected(client):
    store_id, cookies = _register_store(client, "couriersendwa")
    _upgrade_to_padrao(client, store_id)
    courier = client.post("/couriers", json={"name": "tscheck Entregador", "phone": "5511988880000", "active": True}, cookies=cookies)
    assert courier.status_code == 200, courier.text
    courier_id = courier.json()["courier_id"]
    order = client.post(
        "/orders",
        json={
            "customer_name": "tscheck Cliente 2",
            "customer_phone": "5511999990001",
            "delivery_type": "Entrega",
            "address": "Rua Teste, 456",
            "payment_method": "Pix",
            "items": [{"product_id": "x", "name": "Item", "price": 10, "quantity": 1, "size": "", "additionals": []}],
        },
        cookies=cookies,
    )
    assert order.status_code == 200, order.text
    order_id = order.json()["order_id"]
    upd = client.put(
        f"/orders/{order_id}",
        json={"courier_id": courier_id},
        cookies=cookies,
    )
    assert upd.status_code == 200, upd.text
    resp = client.post(f"/orders/{order_id}/send-courier", cookies=cookies)
    # a fresh test store has no WhatsApp session connected: the endpoint must fail
    # cleanly (409) instead of crashing or silently succeeding.
    assert resp.status_code == 409, resp.text
