"""Criterion: 'Receipt check without Pix key' — lib/receipt.check_receipt must still mark the
receipt as matched (True) when the recipient name matches and the amount is exact and the
transfer is not scheduled, even when the store has no registered pix_key (empty string).
A scheduled transfer, or a receipt for a different favorecido, must fail."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.receipt import check_receipt  # noqa: E402

SETTINGS_NO_KEY = {"pix_key": "", "pix_beneficiary": "Feijoada Da Ana"}


def test_receipt_matches_by_name_alone_when_store_has_no_pix_key():
    data = {
        "amount": 20.0,
        "recipient_key": "",
        "recipient_name": "Feijoada Da Ana",
        "status_ok": True,
        "scheduled": False,
    }
    ok, note = check_receipt(data, 20.0, SETTINGS_NO_KEY)
    assert ok is True, note


def test_receipt_scheduled_transfer_fails_even_with_right_name_and_amount():
    data = {
        "amount": 20.0,
        "recipient_key": "",
        "recipient_name": "Feijoada Da Ana",
        "status_ok": True,
        "scheduled": True,
    }
    ok, note = check_receipt(data, 20.0, SETTINGS_NO_KEY)
    assert ok is False, note


def test_receipt_other_favorecido_fails_with_no_pix_key_configured():
    data = {
        "amount": 20.0,
        "recipient_key": "",
        "recipient_name": "Outra Pessoa Qualquer",
        "status_ok": True,
        "scheduled": False,
    }
    ok, note = check_receipt(data, 20.0, SETTINGS_NO_KEY)
    assert ok is False, note
