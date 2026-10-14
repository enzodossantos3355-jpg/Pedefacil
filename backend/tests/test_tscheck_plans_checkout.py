"""Criterion: Plans page + Stripe checkout (API side: checkout session creation)."""
import random

from .conftest import api_url


def test_checkout_creates_stripe_session(client):
    email = f"tscheck-checkout-{random.randint(100000, 999999)}@teste.com"
    reg = client.post(
        "/auth/register",
        json={
            "store_name": f"tscheck-checkout-store-{random.randint(1000,9999)}",
            "email": email,
            "password": "Teste12345",
            "name": "Tester",
        },
    )
    assert reg.status_code == 200, reg.text
    cookies = reg.cookies

    resp = client.post(
        "/billing/checkout",
        json={"plan": "padrao", "origin_url": "http://localhost:3000"},
        cookies=cookies,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "checkout_url" in data
    assert data["checkout_url"].startswith("https://checkout.stripe.com/")


def test_checkout_requires_auth(client):
    resp = client.post(
        "/billing/checkout",
        json={"plan": "padrao", "origin_url": "http://localhost:3000"},
    )
    assert resp.status_code in (401, 403), resp.text
