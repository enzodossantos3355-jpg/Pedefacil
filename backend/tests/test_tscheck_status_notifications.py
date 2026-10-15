"""Criterion: 'Status notifications' — STATUS_MESSAGES has no entry for 'Novo' (only progress
states get a WhatsApp message), notify_status is wired on order status updates, and wa_send
normalizes a typed 10/11-digit Brazilian number by prefixing country code 55."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routers.operations import STATUS_MESSAGES  # noqa: E402


def test_status_messages_excludes_novo():
    assert "Novo" not in STATUS_MESSAGES
    # but the real transition states all have a template
    for s in ("Em Preparo", "Pronto", "Em Entrega", "Concluído", "Cancelado"):
        assert s in STATUS_MESSAGES and "{id}" in STATUS_MESSAGES[s]


def test_wa_send_prefixes_55_for_local_numbers(monkeypatch):
    import asyncio

    import lib.ai as ai

    captured = {}

    async def fake_wa_call(method, path, body):
        captured["to"] = body["to"]
        return {"ok": True}

    monkeypatch.setattr(ai, "wa_call", fake_wa_call)

    asyncio.run(ai.wa_send("(77) 98888-7777", "oi"))
    assert captured["to"] == "5577988887777"

    asyncio.run(ai.wa_send("77988887777", "oi"))
    assert captured["to"] == "5577988887777"

    # an already-international/jid-style address is left untouched
    asyncio.run(ai.wa_send("5577988887777@s.whatsapp.net", "oi"))
    assert captured["to"] == "5577988887777@s.whatsapp.net"
