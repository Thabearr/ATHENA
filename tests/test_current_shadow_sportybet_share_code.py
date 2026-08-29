from __future__ import annotations

import dataclasses
import datetime as dt

import pytest

from domain import current_shadow_sportybet_field_trial as field_trial
from domain import current_shadow_sportybet_share_code as share
from tests.test_current_shadow_sportybet_field_trial import _decision


def _portfolio(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    *_prefix, evaluation, decision = _decision(
        tmp_path,
        monkeypatch,
    )
    portfolio = field_trial.optimize_research_shadow_portfolio(
        (decision,),
        target_size=1,
        evaluation_time=evaluation,
    )
    assert len(portfolio.selected_legs) == 1
    return decision, portfolio, evaluation


def _semantic_success(leg, *, odds: str | None = None, market_id=None):
    selection = leg.expected_provider_native_identity()
    if market_id is not None:
        selection = {**selection, "marketId": market_id}
    audit = {
        "eventId": leg.fixture.event_id,
        "expected_home_team": leg.fixture.home_team,
        "expected_away_team": leg.fixture.away_team,
        "observed_home_team": leg.fixture.home_team,
        "observed_away_team": leg.fixture.away_team,
        "expected_market_name": leg.provider_market_name,
        "expected_outcome_name": leg.provider_outcome_name,
        "expected_specifier": leg.provider_specifier,
        "observed_market_name": leg.provider_market_name,
        "observed_outcome_name": leg.provider_outcome_name,
        "observed_specifier": leg.provider_specifier,
        "marketId": selection["marketId"],
        "outcomeId": selection["outcomeId"],
        "odds": odds or str(leg.decimal_odds),
        "fixture_semantics_verified": True,
        "selection_semantics_verified": True,
    }
    receipt = {
        "schema": "athena-sportybet-semantic-share-gate-v1",
        "intent_count": 1,
        "resolved_count": 1,
        "caller_supplied_market_outcome_ids_accepted": False,
        "resolved": [audit],
        "sportybet_login_used": False,
        "sportybet_cookie_used": False,
        "sportybet_wallet_used": False,
        "stake_submitted": False,
        "wager_placed": False,
    }
    return (selection,), receipt


def _accepted(leg, *, odds: str | None = None):
    return {
        "eventId": leg.fixture.event_id,
        "homeTeamName": leg.fixture.home_team,
        "awayTeamName": leg.fixture.away_team,
        "markets": [
            {
                "id": leg.provider_market_id,
                "desc": leg.provider_market_name,
                "specifier": leg.provider_specifier,
                "outcomes": [
                    {
                        "id": leg.provider_outcome_id,
                        "desc": leg.provider_outcome_name,
                        "odds": odds or str(leg.decimal_odds),
                    }
                ],
            }
        ],
    }


def _transport_success(leg, *, load_odds: str | None = None):
    create = _accepted(leg)
    load = _accepted(leg, odds=load_odds)
    return {
        "schema": "athena-sportybet-direct-share-proof-v2",
        "selection_count": 1,
        "create_accepted_selection_count": 1,
        "load_accepted_selection_count": 1,
        "create_accepted_outcomes": [create],
        "load_accepted_outcomes": [load],
        "create_unavailable_outcomes": 0,
        "load_unavailable_outcomes": 0,
        "exact_roundtrip_selection_identity_verified": True,
        "shareCode": "ABC123",
        "shareURL": "https://www.sportybet.com/share/ABC123",
        "combined_odds": str(leg.decimal_odds),
        "sportybet_login_used": False,
        "sportybet_cookie_used": False,
        "sportybet_wallet_used": False,
        "stake_submitted": False,
        "wager_placed": False,
    }


def _install_success(
    monkeypatch: pytest.MonkeyPatch,
    portfolio,
    evaluation,
):
    leg = portfolio.selected_legs[0]
    semantic = _semantic_success(leg)
    transport = _transport_success(leg)
    monkeypatch.setattr(
        share,
        "_now_utc",
        lambda: evaluation + dt.timedelta(seconds=30),
    )
    monkeypatch.setattr(
        share.semantic_bridge,
        "resolve_live_intents",
        lambda **_kwargs: semantic,
    )
    monkeypatch.setattr(
        share.direct_bridge,
        "create_and_roundtrip",
        lambda **_kwargs: transport,
    )
    return leg, semantic, transport


def test_verified_shadow_share_code_requires_semantic_native_odds_and_roundtrip_equality(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision, portfolio, evaluation = _portfolio(
        tmp_path,
        monkeypatch,
    )
    leg, _semantic, _transport = _install_success(
        monkeypatch,
        portfolio,
        evaluation,
    )
    result = share.create_current_shadow_sportybet_share_code(
        portfolio=portfolio,
        source_decisions=(decision,),
        output_dir=tmp_path / "share",
        delay_seconds=0,
    )

    assert result.status == share.STATUS_CODE_VERIFIED
    assert result.code_verified is True
    assert result.share_code == "ABC123"
    assert result.selected_leg_count == 1
    assert result.portfolio_shortfall == 0
    assert result.portfolio_sha256 == portfolio.canonical_sha256
    assert result.to_dict()["wager_placed"] is False
    assert result.to_dict()["sportybet_login_used"] is False
    assert share.AUTHORITY["anonymous_research_share_code_generation"] is True
    for key in (
        "production_model",
        "phase6",
        "production_selection",
        "production_sportybet_execution",
        "login",
        "cookies",
        "wallet",
        "staking",
        "bet",
        "wager_placed",
    ):
        assert share.AUTHORITY[key] is False
    assert leg.semantic_intent()["eventId"] == leg.fixture.event_id


def test_fresh_semantic_odds_change_requires_reprice_before_create(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision, portfolio, evaluation = _portfolio(
        tmp_path,
        monkeypatch,
    )
    leg = portfolio.selected_legs[0]
    changed_odds = str(leg.decimal_odds + 0.01)
    semantic = _semantic_success(leg, odds=changed_odds)
    calls = {"direct": 0}

    monkeypatch.setattr(
        share,
        "_now_utc",
        lambda: evaluation + dt.timedelta(seconds=30),
    )
    monkeypatch.setattr(
        share.semantic_bridge,
        "resolve_live_intents",
        lambda **_kwargs: semantic,
    )

    def direct_should_not_run(**_kwargs):
        calls["direct"] += 1
        raise AssertionError("direct create must not run after price drift")

    monkeypatch.setattr(
        share.direct_bridge,
        "create_and_roundtrip",
        direct_should_not_run,
    )

    result = share.create_current_shadow_sportybet_share_code(
        portfolio=portfolio,
        source_decisions=(decision,),
        output_dir=tmp_path / "share",
        delay_seconds=0,
    )
    assert result.status == share.STATUS_REPRICE_REQUIRED
    assert result.share_code is None
    assert calls["direct"] == 0
    assert any("PROVIDER_ODDS_CHANGED" in item for item in result.reasons)


def test_fresh_semantic_native_identity_change_requires_rebind_before_create(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision, portfolio, evaluation = _portfolio(
        tmp_path,
        monkeypatch,
    )
    leg = portfolio.selected_legs[0]
    semantic = _semantic_success(leg, market_id="999")
    calls = {"direct": 0}

    monkeypatch.setattr(
        share,
        "_now_utc",
        lambda: evaluation + dt.timedelta(seconds=30),
    )
    monkeypatch.setattr(
        share.semantic_bridge,
        "resolve_live_intents",
        lambda **_kwargs: semantic,
    )

    def direct_should_not_run(**_kwargs):
        calls["direct"] += 1
        raise AssertionError("direct create must not run after native drift")

    monkeypatch.setattr(
        share.direct_bridge,
        "create_and_roundtrip",
        direct_should_not_run,
    )

    result = share.create_current_shadow_sportybet_share_code(
        portfolio=portfolio,
        source_decisions=(decision,),
        output_dir=tmp_path / "share",
        delay_seconds=0,
    )
    assert result.status == share.STATUS_PROVIDER_CHANGED
    assert result.share_code is None
    assert calls["direct"] == 0
    assert any(
        "PROVIDER_NATIVE_IDENTITY_CHANGED" in item
        for item in result.reasons
    )


def test_create_reload_odds_change_never_exposes_unverified_code(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision, portfolio, evaluation = _portfolio(
        tmp_path,
        monkeypatch,
    )
    leg = portfolio.selected_legs[0]
    semantic = _semantic_success(leg)
    transport = _transport_success(
        leg,
        load_odds=str(leg.decimal_odds + 0.01),
    )

    monkeypatch.setattr(
        share,
        "_now_utc",
        lambda: evaluation + dt.timedelta(seconds=30),
    )
    monkeypatch.setattr(
        share.semantic_bridge,
        "resolve_live_intents",
        lambda **_kwargs: semantic,
    )
    monkeypatch.setattr(
        share.direct_bridge,
        "create_and_roundtrip",
        lambda **_kwargs: transport,
    )

    result = share.create_current_shadow_sportybet_share_code(
        portfolio=portfolio,
        source_decisions=(decision,),
        output_dir=tmp_path / "share",
        delay_seconds=0,
    )
    assert result.status == share.STATUS_ROUNDTRIP_CHANGED
    assert result.code_verified is False
    assert result.share_code is None


def test_stale_shadow_price_at_transport_requires_full_reprice_without_network(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision, portfolio, _evaluation = _portfolio(
        tmp_path,
        monkeypatch,
    )
    leg = portfolio.selected_legs[0]
    now = leg.quote_observed_at + dt.timedelta(
        seconds=field_trial.MAX_SOURCE_AGE_SECONDS + 1
    )
    calls = {"semantic": 0, "direct": 0}
    monkeypatch.setattr(share, "_now_utc", lambda: now)

    def semantic_should_not_run(**_kwargs):
        calls["semantic"] += 1
        raise AssertionError("semantic network must not run on stale price")

    def direct_should_not_run(**_kwargs):
        calls["direct"] += 1
        raise AssertionError("direct network must not run on stale price")

    monkeypatch.setattr(
        share.semantic_bridge,
        "resolve_live_intents",
        semantic_should_not_run,
    )
    monkeypatch.setattr(
        share.direct_bridge,
        "create_and_roundtrip",
        direct_should_not_run,
    )

    result = share.create_current_shadow_sportybet_share_code(
        portfolio=portfolio,
        source_decisions=(decision,),
        output_dir=tmp_path / "share",
        delay_seconds=0,
    )
    assert result.status == share.STATUS_REPRICE_REQUIRED
    assert result.share_code is None
    assert calls == {"semantic": 0, "direct": 0}


def test_no_qualified_research_legs_returns_no_code_without_network(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision, _portfolio_value, evaluation = _portfolio(
        tmp_path,
        monkeypatch,
    )
    no_bet = field_trial.ResearchFixtureDecision(
        fixture=decision.fixture,
        evaluation_time=decision.evaluation_time,
        latest_history_sha256=decision.latest_history_sha256,
        current_mapping_rebind_sha256=(
            decision.current_mapping_rebind_sha256
        ),
        status="NO_BET",
        selected_opportunity_id=None,
        opportunities=decision.opportunities,
        decision_reasons=("RESEARCH_TEST_NO_BET",),
    )
    portfolio = field_trial.optimize_research_shadow_portfolio(
        (no_bet,),
        target_size=1,
        evaluation_time=evaluation,
    )
    assert portfolio.selected_legs == ()

    monkeypatch.setattr(
        share,
        "_now_utc",
        lambda: evaluation + dt.timedelta(seconds=30),
    )
    monkeypatch.setattr(
        share.semantic_bridge,
        "resolve_live_intents",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("semantic network must not run")
        ),
    )
    monkeypatch.setattr(
        share.direct_bridge,
        "create_and_roundtrip",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("direct network must not run")
        ),
    )

    result = share.create_current_shadow_sportybet_share_code(
        portfolio=portfolio,
        source_decisions=(no_bet,),
        output_dir=tmp_path / "share",
        delay_seconds=0,
    )
    assert result.status == share.STATUS_NO_QUALIFIED_LEGS
    assert result.share_code is None
    assert result.selected_leg_count == 0
    assert result.to_dict()["wager_placed"] is False
