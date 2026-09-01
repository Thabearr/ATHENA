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
