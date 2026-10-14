"""Criterion: Master panel lists restaurants, can change plan; non-master gets 403."""
import random

from .conftest import api_url


def _register_store(client, slug):
    email = f"tscheck-{slug}-{random.randint(100000, 999999)}@teste.com"
    resp = client.post(
        "/auth/register",
        json={
            "store_name": f"tscheck-{slug}-store-{random.randint(1000,9999)}",
            "email": email,
            "password": "Teste12345",
            "name": "Tester",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["store_id"], resp.cookies


def _master_login(client):
    resp = client.post(
        "/auth/login",
        json={"email": "master@pedefacil.com", "password": "master123"},
    )
    assert resp.status_code == 200, resp.text
    return resp.cookies


def test_master_lists_stores_and_changes_plan(client):
    store_id, store_cookies = _register_store(client, "masterplan")
    master_cookies = _master_login(client)

    listing = client.get("/master/stores", cookies=master_cookies)
    assert listing.status_code == 200, listing.text
    stores = listing.json()
    assert any(s["store_id"] == store_id for s in stores)

    update = client.put(
        f"/master/stores/{store_id}",
        json={"plan": "pro", "status": "active"},
        cookies=master_cookies,
    )
    assert update.status_code == 200, update.text

    billing = client.get("/billing/me", cookies=store_cookies)
    assert billing.status_code == 200, billing.text
    assert billing.json()["plan"] == "pro"


def test_non_master_forbidden_on_master_stores(client):
    _, store_cookies = _register_store(client, "notmaster")
    resp = client.get("/master/stores", cookies=store_cookies)
    assert resp.status_code == 403, resp.text
