"""Criterion: Locked features show lock + upgrade (API side: plan_required gating)."""
import random

from .conftest import api_url


def _register_trial_store(client):
    email = f"tscheck-locked-{random.randint(100000, 999999)}@teste.com"
    resp = client.post(
        "/auth/register",
        json={
            "store_name": f"tscheck-locked-store-{random.randint(1000,9999)}",
            "email": email,
            "password": "Teste12345",
            "name": "Tester",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.cookies


def test_trial_store_whatsapp_locked(client):
    cookies = _register_trial_store(client)
    resp = client.get("/whatsapp/chats", cookies=cookies)
    assert resp.status_code == 403, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "plan_required"
    assert detail["required_plan"] == "padrao"


def test_unauthenticated_whatsapp_rejected(client):
    resp = client.get("/whatsapp/chats")
    assert resp.status_code in (401, 403), resp.text
