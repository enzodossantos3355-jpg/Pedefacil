"""Criterion: Signup creates an isolated restaurant on a 7-day restricted trial."""
import random

from .conftest import api_url


def _unique_email():
    return f"tscheck-signup-{random.randint(100000, 999999)}@teste.com"


def test_signup_creates_isolated_trial_store(client):
    email = _unique_email()
    resp = client.post(
        "/auth/register",
        json={
            "store_name": f"tscheck-signup-store-{random.randint(1000,9999)}",
            "email": email,
            "password": "Teste12345",
            "name": "Tester",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["role"] == "admin"
    store_id = body["store_id"]
    assert store_id and store_id != "store-demo"

    cookies = resp.cookies

    billing = client.get("/billing/me", cookies=cookies)
    assert billing.status_code == 200, billing.text
    bdata = billing.json()
    assert bdata["plan"] == "trial"
    assert bdata["trial_days_left"] == 7
    assert bdata["limits"]["orders"] == 20
    assert bdata["limits"]["products"] == 8

    orders = client.get("/orders", cookies=cookies)
    assert orders.status_code == 200
    assert orders.json() == [], "new store must not see demo store orders"

    products = client.get("/products", cookies=cookies)
    assert products.status_code == 200
    assert products.json() == [], "new store must not see demo store products"


def test_signup_duplicate_email_rejected(client):
    email = _unique_email()
    first = client.post(
        "/auth/register",
        json={
            "store_name": "tscheck-signup-dup",
            "email": email,
            "password": "Teste12345",
            "name": "Tester",
        },
    )
    assert first.status_code == 200, first.text

    second = client.post(
        "/auth/register",
        json={
            "store_name": "tscheck-signup-dup-2",
            "email": email,
            "password": "Teste12345",
            "name": "Tester2",
        },
    )
    assert second.status_code in (400, 409), second.text
