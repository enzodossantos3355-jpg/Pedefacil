"""Criterion: Google OAuth wiring — backend verifies the Emergent session server-side
and rejects an invalid/unknown session_id (no account is created, no cookie is set)."""


def test_google_login_rejects_invalid_session(client):
    resp = client.post("/auth/google", json={"session_id": "tscheck-invalid-session-id-0000"})
    assert resp.status_code == 401, resp.text
    assert "marmita_session" not in resp.cookies


def test_google_login_requires_session_id(client):
    resp = client.post("/auth/google", json={})
    assert resp.status_code == 422, resp.text
