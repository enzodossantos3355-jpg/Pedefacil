"""Criterion: 'Notification bell in header' — GET /api/notifications lists orders in
Em Análise/Novo, chats needing a human, and receipts em_verificacao."""
import random


def _register_store(client, slug):
    email = f"tscheck-{slug}-{random.randint(100000, 999999)}@teste.com"
    resp = client.post(
        "/auth/register",
        json={"store_name": f"tscheck-{slug}-store-{random.randint(1000, 9999)}", "email": email, "password": "Teste12345", "name": "Tester"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["store_id"], resp.cookies


def test_notifications_include_pending_order(client):
    store_id, cookies = _register_store(client, "notiforder")
    client.post("/day/open", json={"initial_cash": 0}, cookies=cookies)
    order = client.post(
        "/orders",
        json={
            "customer_name": "tscheck Notif Cliente",
            "customer_phone": "5511977770000",
            "delivery_type": "Retirada",
            "payment_method": "Pendente",
            "status": "Em Análise",
            "items": [{"product_id": "x", "name": "Item", "price": 10, "quantity": 1, "size": "", "additionals": []}],
        },
        cookies=cookies,
    )
    assert order.status_code == 200, order.text
    order_id = order.json()["order_id"]

    resp = client.get("/notifications", cookies=cookies)
    assert resp.status_code == 200, resp.text
    items = resp.json()
    matching = [n for n in items if order_id[-6:].upper() in n["title"]]
    assert matching, f"expected a notification for order {order_id}, got {items}"
    assert matching[0]["kind"] == "new_order"
    assert matching[0]["link"] == "/pedidos"


def test_notifications_unauthenticated_rejected(client):
    resp = client.get("/notifications")
    assert resp.status_code in (401, 403), resp.text
