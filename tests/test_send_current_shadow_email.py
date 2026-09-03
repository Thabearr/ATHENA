from __future__ import annotations

import copy

import pytest

from scripts import send_current_shadow_email as mail


def _base_receipt():
    return {
        "dataset_name": mail.EXPECTED_DATASET,
        "status": "RESEARCH_SHADOW_CODE_VERIFIED_WITH_SHORTFALL",
        "observed_at": "2026-09-01T12:26:09.364844Z",
        "requested_target_size": 20,
        "selected_leg_count": 1,
        "shortfall": 19,
        "reasons": [],
        "shareCode": "Q5DHQ1",
        "shareURL": "http://www.sportybet.com/ng/?shareCode=Q5DHQ1",
        "sportybet_login_used": False,
        "sportybet_cookie_used": False,
        "sportybet_wallet_used": False,
        "stake_submitted": False,
        "wager_placed": False,
        "share_code_receipt": {
            "status": "RESEARCH_SHADOW_CODE_VERIFIED_WITH_SHORTFALL",
            "code_verified": True,
            "exact_create_reload_equality": True,
            "shareCode": "Q5DHQ1",
            "shareURL": "http://www.sportybet.com/ng/?shareCode=Q5DHQ1",
            "sportybet_login_used": False,
            "sportybet_cookie_used": False,
            "sportybet_wallet_used": False,
            "stake_submitted": False,
            "wager_placed": False,
        },
        "portfolio": {
            "selected_legs": [
                {
                    "home_team": "West Ham",
                    "away_team": "Wolves",
                    "market_id": "ASIAN_HANDICAP",
                    "provider_outcome_name": "Home (-1.0)",
                    "line": -1.0,
                    "decimal_odds": 2.95,
                    "prediction_confidence": 0.76,
                }
            ]
        },
    }


def test_verified_receipt_renders_exact_share_code_and_shortfall():
    text = mail.render_plain_text(_base_receipt())
    assert "Verified SportyBet share code: Q5DHQ1" in text
    assert "Requested target: 20" in text
    assert "Selected legs: 1" in text
    assert "Shortfall: 19" in text
    assert "West Ham vs Wolves" in text
    assert "prediction confidence 0.76" in text
    assert "fresh odds 2.95" in text
    assert "wager_placed=false" in text


def test_no_code_state_never_renders_share_code():
    receipt = _base_receipt()
    receipt.update(
        status="RESEARCH_NO_CODE_NO_BET",
        shareCode=None,
        shareURL=None,
        share_code_receipt=None,
        selected_leg_count=0,
        shortfall=20,
        reasons=["NO_BET"],
        portfolio=None,
    )
    text = mail.render_plain_text(receipt)
    assert "Verified SportyBet share code" not in text
    assert "No verified SportyBet share code was released" in text
    assert "Reasons: NO_BET" in text


def test_unverified_terminal_state_with_code_fails_closed():
    receipt = _base_receipt()
    receipt["status"] = "RESEARCH_NO_CODE_PROVIDER_CHANGED"
    with pytest.raises(mail.CurrentShadowEmailError, match="unverified terminal state"):
        mail.render_plain_text(receipt)


def test_nested_provider_code_mismatch_fails_closed():
    receipt = _base_receipt()
    receipt["share_code_receipt"] = copy.deepcopy(receipt["share_code_receipt"])
    receipt["share_code_receipt"]["shareCode"] = "WRONG"
    with pytest.raises(mail.CurrentShadowEmailError, match="share-code identities differ"):
        mail.render_plain_text(receipt)


def test_any_wager_or_stake_flag_blocks_delivery():
    for key in ("stake_submitted", "wager_placed"):
        receipt = _base_receipt()
        receipt[key] = True
        with pytest.raises(mail.CurrentShadowEmailError, match=key):
            mail.render_plain_text(receipt)


def test_subject_is_explicitly_shadow_and_includes_target():
    subject = mail._subject(_base_receipt())
    assert subject.startswith("ATHENA Shadow 2026-09-01")
    assert "target 20" in subject


def _write_receipt(tmp_path):
    path = tmp_path / "run.json"
    path.write_text(__import__("json").dumps(_base_receipt()), encoding="utf-8")
    return path


def test_missing_email_secrets_writes_explicit_skipped_receipt(tmp_path, monkeypatch):
    for key in ("GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "RECIPIENT_EMAIL"):
        monkeypatch.delenv(key, raising=False)
    delivery = tmp_path / "delivery.json"
    result = mail.send_receipt_email(
        receipt_path=_write_receipt(tmp_path), delivery_receipt_path=delivery
    )
    assert result["status"] == mail.EMAIL_SKIPPED_UNCONFIGURED
    assert result["smtp_successful_send"] is False
    assert delivery.is_file()


def test_email_delivered_only_after_successful_smtp_send(tmp_path, monkeypatch):
    monkeypatch.setenv("GMAIL_ADDRESS", "sender@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "super-private-value")
    monkeypatch.setenv("RECIPIENT_EMAIL", "recipient@example.com")
    calls = []

    class SMTP:
        def __init__(self, *_args, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def starttls(self): calls.append("starttls")
        def login(self, *_args): calls.append("login")
        def send_message(self, _message): calls.append("send")

    monkeypatch.setattr(mail.smtplib, "SMTP", SMTP)
    result = mail.send_receipt_email(receipt_path=_write_receipt(tmp_path))
    assert calls == ["starttls", "login", "send"]
    assert result["status"] == mail.EMAIL_DELIVERED
    assert result["smtp_successful_send"] is True


def test_smtp_failure_writes_failed_receipt_without_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("GMAIL_ADDRESS", "sender@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "super-private-value")
    monkeypatch.setenv("RECIPIENT_EMAIL", "recipient@example.com")

    class SMTP:
        def __init__(self, *_args, **_kwargs): raise OSError("network")

    monkeypatch.setattr(mail.smtplib, "SMTP", SMTP)
    delivery = tmp_path / "delivery.json"
    with pytest.raises(mail.CurrentShadowEmailError, match="EMAIL_FAILED"):
        mail.send_receipt_email(
            receipt_path=_write_receipt(tmp_path), delivery_receipt_path=delivery
        )
    value = __import__("json").loads(delivery.read_text(encoding="utf-8"))
    assert value["status"] == mail.EMAIL_FAILED
    raw = delivery.read_text(encoding="utf-8")
    assert "super-private-value" not in raw
    assert "sender@example.com" not in raw
    assert "recipient@example.com" not in raw
