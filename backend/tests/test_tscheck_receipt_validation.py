"""Criterion: 'Receipt validation is strict' — lib/receipt.check_receipt(data, total, settings)
returns True only when amount == total AND recipient key/name matches AND status_ok; a wrong
amount must return False with a 'valor diferente' note. Pure function, no LLM call needed."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.receipt import check_receipt  # noqa: E402

SETTINGS = {"pix_key": "11999990000", "pix_beneficiary": "Feijoada Da Ana"}


def test_receipt_matches_amount_and_recipient_marks_paid():
    data = {
        "amount": 25.5,
        "recipient_key": "11999990000",
        "recipient_name": "Feijoada Da Ana Ltda",
        "status_ok": True,
    }
    ok, note = check_receipt(data, 25.5, SETTINGS)
    assert ok is True, note
    assert "conferido" in note


def test_receipt_wrong_amount_fails_with_note():
    data = {
        "amount": 10.0,
        "recipient_key": "11999990000",
        "recipient_name": "Feijoada Da Ana Ltda",
        "status_ok": True,
    }
    ok, note = check_receipt(data, 25.5, SETTINGS)
    assert ok is False
    assert "valor diferente" in note, note


def test_receipt_wrong_recipient_fails_even_with_right_amount():
    data = {
        "amount": 25.5,
        "recipient_key": "99888887777",
        "recipient_name": "Outra Pessoa",
        "status_ok": True,
    }
    ok, note = check_receipt(data, 25.5, SETTINGS)
    assert ok is False
    assert "favorecido" in note or "recebedor" in note, note


def test_receipt_not_completed_fails_even_with_right_amount_and_recipient():
    data = {
        "amount": 25.5,
        "recipient_key": "11999990000",
        "recipient_name": "Feijoada Da Ana Ltda",
        "status_ok": False,
    }
    ok, note = check_receipt(data, 25.5, SETTINGS)
    assert ok is False
    assert "não concluído" in note or "nao concluido" in note, note
