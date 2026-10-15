"""Criterion: 'Mercado Pago settings' — PUT /api/payments/mercadopago with an invalid token
returns 422; GET /api/payments/mercadopago never leaks a token field; POST
/api/webhooks/mercadopago?store=unknown returns 200 {received:true}; POST
/api/payments/mercadopago/check returns {confirmed:0} when no token is configured."""
import random


def _register_store(client, slug):
    email = f"tscheck-{slug}-{random.randint(100000, 999999)}@teste.com"
    resp = client.post(
        "/auth/register",
        json={"store_name": f"tscheck-{slug}-store-{random.randint(1000, 9999)}", "email": email, "password": "Teste12345", "name": "Tester"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["store_id"], resp.cookies


def test_invalid_token_rejected_and_status_never_leaks_token(client):
    _, cookies = _register_store(client, "mpinvalid")

    bad = client.put("/payments/mercadopago", json={"access_token": "definitely-not-a-real-mp-token"}, cookies=cookies)
    assert bad.status_code == 422, bad.text

    status = client.get("/payments/mercadopago", cookies=cookies)
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["configured"] is False
    assert "access_token" not in body and "token" not in body, body


def test_check_pending_returns_zero_without_token(client):
    _, cookies = _register_store(client, "mpcheck")
    res = client.post("/payments/mercadopago/check", cookies=cookies)
    assert res.status_code == 200, res.text
    assert res.json() == {"confirmed": 0}


def test_webhook_unknown_store_is_always_200_received():
    import httpx

    with httpx.Client(base_url="http://localhost:8001/api", timeout=30.0) as anon:
        res = anon.post("/webhooks/mercadopago", params={"store": "tscheck-unknown-store-id"}, json={"data": {"id": "123"}})
        assert res.status_code == 200, res.text
        assert res.json() == {"received": True}
