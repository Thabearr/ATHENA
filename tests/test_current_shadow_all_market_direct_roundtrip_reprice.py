from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from domain import current_shadow_all_market_share_code as share


NOW = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)


def _fresh_leg(*, odds: str = "1.13") -> dict[str, object]:
    return {
        "fixture_identity": "FOTMOB:1",
        "provider_event_id": "sr:match:1",
        "home_team": "Home",
        "away_team": "Away",
        "provider_market_id": "1",
        "provider_market_name": "1X2",
        "provider_specifier": None,
        "provider_outcome_id": "1",
        "provider_outcome_name": "Home",
        "selected_opportunity_id": "opportunity-1",
        "decimal_odds": odds,
        "fresh_net_expected_value_diagnostic": 999.0,
    }


def _accepted(*, odds: str, market_name: str = "1X2") -> dict[str, object]:
    return {
        "eventId": "sr:match:1",
        "homeTeamName": "Home",
        "awayTeamName": "Away",
        "markets": [
            {
                "id": "1",
                "desc": market_name,
                "specifier": None,
                "outcomes": [{"id": "1", "desc": "Home", "odds": odds}],
            }
        ],
    }


def _transport_receipt(
    *,
    create_odds: str,
    load_odds: str | None = None,
    market_name: str = "1X2",
) -> dict[str, object]:
    load_value = create_odds if load_odds is None else load_odds
    return {
        "selection_count": 1,
        "create_accepted_selection_count": 1,
        "load_accepted_selection_count": 1,
        "create_accepted_outcomes": [
            _accepted(odds=create_odds, market_name=market_name)
        ],
        "load_accepted_outcomes": [
            _accepted(odds=load_value, market_name=market_name)
        ],
        "create_unavailable_outcomes": 0,
        "load_unavailable_outcomes": 0,
        "exact_roundtrip_selection_identity_verified": True,
        "shareCode": "TEST123",
        "shareURL": "https://example.test/?shareCode=TEST123",
        "combined_odds": load_value,
        "sportybet_login_used": False,
        "sportybet_cookie_used": False,
        "sportybet_wallet_used": False,
        "stake_submitted": False,
        "wager_placed": False,
    }


def _portfolio():
    opportunity = SimpleNamespace(
        opportunity_id="opportunity-1",
        price_result=SimpleNamespace(
            settlement_state_probabilities=(),
            model_probability=0.90,
        ),
    )
    source = SimpleNamespace(
        fixture_identity="FOTMOB:1",
        router_decision=SimpleNamespace(opportunities=(opportunity,)),
    )
    return SimpleNamespace(
        _router_inputs=(source,),
        selected_legs=(SimpleNamespace(),),
        requested_target_size=1,
        evaluation_time=NOW,
        canonical_sha256="a" * 64,
    )


def test_stable_direct_odds_move_above_floor_rebinds_final_price():
    leg = _fresh_leg(odds="1.13")
    receipt = _transport_receipt(create_odds="1.12")

    assert share._verify_roundtrip((leg,), receipt) == ()

    rebound = share._bind_roundtrip_fresh_legs(_portfolio(), (leg,), receipt)
    assert rebound[0]["semantic_resolved_decimal_odds"] == "1.13"
    assert rebound[0]["direct_roundtrip_decimal_odds"] == "1.12"
    assert rebound[0]["decimal_odds"] == "1.12"
    assert rebound[0]["direct_roundtrip_odds_refreshed"] is True
    assert rebound[0]["fresh_net_expected_value_diagnostic"] == pytest.approx(0.008)


def test_stable_direct_odds_below_floor_remain_reprice_required():
    reasons = share._verify_roundtrip(
        (_fresh_leg(odds="1.13"),),
        _transport_receipt(create_odds="1.08"),
    )
    assert reasons == ("FOTMOB:1:DIRECT_PROVIDER_ODDS_BELOW_1_09",)


def test_create_reload_odds_drift_still_fails_closed():
    reasons = share._verify_roundtrip(
        (_fresh_leg(odds="1.13"),),
        _transport_receipt(create_odds="1.12", load_odds="1.11"),
    )
    assert reasons == ("DIRECT_TRANSPORT_CREATE_RELOAD_CHANGED",)


def test_direct_semantics_drift_still_fails_closed():
    reasons = share._verify_roundtrip(
        (_fresh_leg(odds="1.13"),),
        _transport_receipt(create_odds="1.12", market_name="Changed 1X2"),
    )
    assert reasons == ("FOTMOB:1:DIRECT_PROVIDER_SEMANTICS_CHANGED",)


def test_verified_share_code_survives_stable_above_floor_direct_reprice(
    tmp_path, monkeypatch,
):
    portfolio = _portfolio()
    leg = _fresh_leg(odds="1.13")
    receipt = _transport_receipt(create_odds="1.12")
    semantic_receipt = {
        "schema": "test-semantic",
        "caller_supplied_market_outcome_ids_accepted": False,
        "wager_placed": False,
    }
    selections = ({"eventId": "sr:match:1", "marketId": "1", "outcomeId": "1"},)

    monkeypatch.setattr(
        share.portfolio_module,
        "verify_shadow_portfolio_optimization",
        lambda value: value,
    )
    monkeypatch.setattr(share, "_transport_lead_reasons", lambda *_args: ())
    monkeypatch.setattr(
        share,
        "_fresh_resolve_portfolio",
        lambda *_args, **_kwargs: (selections, semantic_receipt, (leg,), ()),
    )
    monkeypatch.setattr(
        share.direct_bridge,
        "create_and_roundtrip",
        lambda **_kwargs: receipt,
    )
    monkeypatch.setattr(share, "_now", lambda: NOW)

    result = share.create_verified_shadow_all_market_share_code(
        portfolio=portfolio,
        output_dir=tmp_path,
        delay_seconds=0,
    )

    assert result.status == share.STATUS_CODE_VERIFIED
    assert result.code_verified is True
    assert result.share_code == "TEST123"
    assert result.exact_create_reload_equality is True
    assert result.fresh_selected_legs[0]["semantic_resolved_decimal_odds"] == "1.13"
    assert result.fresh_selected_legs[0]["decimal_odds"] == "1.12"
    assert result.fresh_selected_legs[0]["direct_roundtrip_odds_refreshed"] is True
    assert result.to_dict()["wager_placed"] is False
