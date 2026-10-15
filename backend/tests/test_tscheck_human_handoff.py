"""Criterion: 'Human handoff messages and AI pause' — POST /api/whatsapp/chats/{id}/toggle-human
{enable_human:true} appends the "Um atendente ... vai assumir" bot message and sets
is_human_controlled true; {enable_human:false} appends "voltou para a nossa assistente virtual"
and clears it.

Creating the chat row requires one LLM round-trip through POST /whatsapp/simulate-message
(there is no non-LLM way to seed a chat without the WhatsApp bridge connected, per
spec_deviations); this file uses exactly ONE such call, well within the 2-call budget, and the
handoff assertions themselves are pure API/DB checks with zero extra LLM calls."""
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


def _upgrade_to_padrao(client, store_id):
    master_login = client.post("/auth/login", json={"email": MASTER_EMAIL, "password": MASTER_PASSWORD})
    assert master_login.status_code == 200, master_login.text
    upd = client.put(f"/master/stores/{store_id}", json={"plan": "padrao", "status": "active"}, cookies=master_login.cookies)
    assert upd.status_code == 200, upd.text


def test_toggle_human_appends_handoff_and_back_messages(client):
    store_id, cookies = _register_store(client, "handoff")
    _upgrade_to_padrao(client, store_id)
    client.post("/day/open", json={"initial_cash": 0}, cookies=cookies)

    phone = f"5577{random.randint(900000000, 999999999)}"
    sim = client.post("/whatsapp/simulate-message", json={"phone": phone, "name": "tscheck Handoff", "text": "oi"}, cookies=cookies)
    assert sim.status_code == 200, sim.text
    chat_id = sim.json()["chat_id"]

    on = client.post(f"/whatsapp/chats/{chat_id}/toggle-human", json={"enable_human": True}, cookies=cookies)
    assert on.status_code == 200, on.text
    body = on.json()
    assert body["is_human_controlled"] is True
    assert any("vai assumir" in m["text"] for m in body["messages"] if m["sender"] == "bot"), body["messages"]

    off = client.post(f"/whatsapp/chats/{chat_id}/toggle-human", json={"enable_human": False}, cookies=cookies)
    assert off.status_code == 200, off.text
    body2 = off.json()
    assert body2["is_human_controlled"] is False
    assert any("voltou para a nossa assistente virtual" in m["text"] for m in body2["messages"] if m["sender"] == "bot"), body2["messages"]
