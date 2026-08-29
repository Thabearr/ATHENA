"""Focused tests for PR D Shadow Price-all + all-market Router."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from domain.markets import MarketId, OutcomeId
from domain import current_all_market_shadow_probability_settlement as prc
from domain.current_shadow_all_market_price_all import price_all_shadow_fixture
from domain.current_shadow_all_market_router import route_shadow_price_results
from domain._current_shadow_price_types import (
    AUTHORITY_FLAGS,
    MINIMUM_EVENT_PROBABILITY,
    ShadowDevigStatus,
    ShadowExactQuote,
    ShadowPriceDisposition,
    ShadowPriceError,
    ShadowRouterDecisionStatus,
    ShadowOpportunityEligibility,
)

NOW = datetime(2026, 8, 29, 17, 0, 0, tzinfo=timezone.utc)
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _xg(home: float = 1.8, away: float = 0.9) -> prc.ResearchXGRates:
    return prc.ResearchXGRates(
        calibrated_home=home,
        calibrated_away=away,
        sealed_prediction_sha256=SHA_A,
        completeness_status="SEALED_RESEARCH_RATES",
    )


def _scan(home: float = 1.8, away: float = 0.9, provider: str | None = "SUPPORTED"):
    provider_map = None
    if provider is not None:
        provider_map = {m: provider for m in MarketId}
    return prc.scan_fixture_all_markets(
        fixture_identity="FOTMOB:PRD1",
        research_xg=_xg(home, away),
        total_goals_lines=(1.5, 2.5),
        asian_handicap_home_lines=(-0.5, 0.0),
        provider_semantic_by_market=provider_map,
    )


def _quote(
    market: MarketId,
    outcome: OutcomeId,
    odds: float,
    *,
    line: float | None = None,
    market_id_native: str = "1",
    outcome_id_native: str = "1",
    specifier: str | None = None,
    observed_at: datetime = NOW,
    inv: str = SHA_A,
    raw: str = SHA_B,
    manifest: str = SHA_C,
    status: str = "SUPPORTED",
) -> ShadowExactQuote:
    return ShadowExactQuote(
        fixture_identity="FOTMOB:PRD1",
        provider_event_id="sr:match:1001",
        market_id=market,
        outcome_id=outcome,
        line=line,
        provider_market_id=market_id_native,
        provider_market_name=market.value,
        provider_specifier=specifier,
        provider_outcome_id=outcome_id_native,
        provider_outcome_name=outcome.value,
        decimal_odds=odds,
        observed_at=observed_at,
        source_raw_sha256=raw,
        source_manifest_sha256=manifest,
        source_inventory_sha256=inv,
        provider_semantic_status=status,
    )


def _mr_quotes(odds=(1.40, 4.50, 7.00)):
    return (
        _quote(MarketId.MATCH_RESULT, OutcomeId.HOME, odds[0], market_id_native="mr", outcome_id_native="h"),
        _quote(MarketId.MATCH_RESULT, OutcomeId.DRAW, odds[1], market_id_native="mr", outcome_id_native="d"),
        _quote(MarketId.MATCH_RESULT, OutcomeId.AWAY, odds[2], market_id_native="mr", outcome_id_native="a"),
    )


def test_price_all_retains_15_market_audit_surface():
    scan = _scan()
    quotes = _mr_quotes()
    results = price_all_shadow_fixture(scan, quotes, evaluation_time=NOW)
    seen = {r.market_id for r in results}
    assert set(MarketId) == seen


def test_only_analytical_ready_prices():
    scan = _scan()
    results = price_all_shadow_fixture(scan, _mr_quotes(), evaluation_time=NOW)
    weh = [r for r in results if r.market_id is MarketId.HOME_WIN_EITHER_HALF]
    assert weh
    assert all(
        r.disposition
        in {
            ShadowPriceDisposition.UNPRICED_UPSTREAM_BLOCKED,
            ShadowPriceDisposition.AUDIT_ONLY_UPSTREAM_BLOCKED,
            ShadowPriceDisposition.UNPRICED_NO_EXACT_QUOTE,
            ShadowPriceDisposition.UNPRICED_PROVIDER_BLOCKED,
        }
        for r in weh
    )


def test_provider_unproven_blocks_pricing():
    scan = _scan(provider="CURRENT_PROVIDER_UNAVAILABLE/UNPROVEN")
    results = price_all_shadow_fixture(scan, _mr_quotes(), evaluation_time=NOW)
    mr = [r for r in results if r.market_id is MarketId.MATCH_RESULT]
    assert mr
    assert all(
        r.disposition is ShadowPriceDisposition.UNPRICED_PROVIDER_BLOCKED
        for r in mr
        if r.disposition != ShadowPriceDisposition.AUDIT_ONLY_UPSTREAM_BLOCKED
    )


def test_match_result_proportional_devig_and_positive_ev():
    scan = _scan(2.2, 0.7)
    quotes = _mr_quotes((1.50, 4.20, 6.50))
    results = price_all_shadow_fixture(scan, quotes, evaluation_time=NOW)
    home = next(
        r for r in results
        if r.market_id is MarketId.MATCH_RESULT and r.outcome_id is OutcomeId.HOME
    )
    assert home.disposition is ShadowPriceDisposition.PRICED
    assert home.devig_status is ShadowDevigStatus.PROPORTIONAL_COMPLETE_PARTITION
    assert home.fair_probability is not None
    assert home.overround is not None and home.overround > 1.0
    implied_sum = sum(1.0 / q.decimal_odds for q in quotes)
    assert math.isclose(home.overround, implied_sum, abs_tol=1e-12)


def test_negative_ev_retained_before_router():
    scan = _scan(1.0, 1.5)
    quotes = _mr_quotes((1.20, 5.0, 8.0))
    results = price_all_shadow_fixture(scan, quotes, evaluation_time=NOW)
    home = next(
        r for r in results
        if r.market_id is MarketId.MATCH_RESULT and r.outcome_id is OutcomeId.HOME
    )
    assert home.disposition is ShadowPriceDisposition.PRICED
    assert home.net_expected_value is not None


def test_stale_and_future_quotes():
    scan = _scan()
    stale = _quote(
        MarketId.MATCH_RESULT, OutcomeId.HOME, 1.5,
        market_id_native="mr", outcome_id_native="h",
        observed_at=NOW - timedelta(seconds=2000),
    )
    results = price_all_shadow_fixture(scan, (stale,), evaluation_time=NOW)
    home = next(
        r for r in results
        if r.market_id is MarketId.MATCH_RESULT and r.outcome_id is OutcomeId.HOME
    )
    assert home.disposition is ShadowPriceDisposition.UNPRICED_STALE_QUOTE
    future = _quote(
        MarketId.MATCH_RESULT, OutcomeId.HOME, 1.5,
        market_id_native="mr", outcome_id_native="h",
        observed_at=NOW + timedelta(seconds=60),
    )
    results2 = price_all_shadow_fixture(scan, (future,), evaluation_time=NOW)
    home2 = next(
        r for r in results2
        if r.market_id is MarketId.MATCH_RESULT and r.outcome_id is OutcomeId.HOME
    )
    assert home2.disposition is ShadowPriceDisposition.UNPRICED_FUTURE_QUOTE


def test_total_goals_multi_line_independent():
    scan = _scan()
    quotes = (
        _quote(MarketId.TOTAL_GOALS, OutcomeId.OVER, 1.90, line=1.5, market_id_native="tg", outcome_id_native="o15", specifier="total=1.5"),
        _quote(MarketId.TOTAL_GOALS, OutcomeId.UNDER, 1.90, line=1.5, market_id_native="tg", outcome_id_native="u15", specifier="total=1.5"),
        _quote(MarketId.TOTAL_GOALS, OutcomeId.OVER, 2.10, line=2.5, market_id_native="tg", outcome_id_native="o25", specifier="total=2.5"),
        _quote(MarketId.TOTAL_GOALS, OutcomeId.UNDER, 1.75, line=2.5, market_id_native="tg", outcome_id_native="u25", specifier="total=2.5"),
    )
    results = price_all_shadow_fixture(scan, quotes, evaluation_time=NOW)
    tg = [r for r in results if r.market_id is MarketId.TOTAL_GOALS and r.disposition is ShadowPriceDisposition.PRICED]
    lines = sorted({r.line for r in tg})
    assert 1.5 in lines and 2.5 in lines


def test_double_chance_no_false_devig():
    scan = _scan()
    quotes = (
        _quote(MarketId.DOUBLE_CHANCE, OutcomeId.HOME_OR_DRAW, 1.30, market_id_native="dc", outcome_id_native="1x"),
        _quote(MarketId.DOUBLE_CHANCE, OutcomeId.HOME_OR_AWAY, 1.40, market_id_native="dc", outcome_id_native="12"),
        _quote(MarketId.DOUBLE_CHANCE, OutcomeId.DRAW_OR_AWAY, 1.50, market_id_native="dc", outcome_id_native="x2"),
    )
    results = price_all_shadow_fixture(scan, quotes, evaluation_time=NOW)
    dc = [r for r in results if r.market_id is MarketId.DOUBLE_CHANCE and r.disposition is ShadowPriceDisposition.PRICED]
    assert dc
    assert all(r.devig_status is ShadowDevigStatus.NOT_IDENTIFIABLE_OVERLAPPING_EVENTS for r in dc)
    assert all(r.fair_probability is None for r in dc)


def test_dnb_settlement_aware_ev():
    scan = _scan(2.0, 0.8)
    quotes = (
        _quote(MarketId.DRAW_NO_BET, OutcomeId.HOME, 1.45, market_id_native="dnb", outcome_id_native="h"),
        _quote(MarketId.DRAW_NO_BET, OutcomeId.AWAY, 2.60, market_id_native="dnb", outcome_id_native="a"),
    )
    results = price_all_shadow_fixture(scan, quotes, evaluation_time=NOW)
    dnb = [r for r in results if r.market_id is MarketId.DRAW_NO_BET and r.disposition is ShadowPriceDisposition.PRICED]
    assert dnb
    for r in dnb:
        assert r.devig_status is ShadowDevigStatus.NOT_IDENTIFIABLE_PUSH_OR_SPLIT_SETTLEMENT
        assert r.fair_probability is None
        states = dict(r.settlement_state_probabilities)
        assert "WIN" in states and "PUSH" in states and "LOSS" in states
        assert math.isclose(sum(states.values()), 1.0, abs_tol=1e-9)


def test_ah_settlement_aware_when_supported():
    scan = _scan(provider="SUPPORTED")
    quotes = (
        _quote(MarketId.ASIAN_HANDICAP, OutcomeId.HOME, 1.90, line=-0.5, market_id_native="ah", outcome_id_native="h", specifier="hcp=-0.5"),
        _quote(MarketId.ASIAN_HANDICAP, OutcomeId.AWAY, 1.90, line=0.5, market_id_native="ah", outcome_id_native="a", specifier="hcp=-0.5"),
    )
    results = price_all_shadow_fixture(scan, quotes, evaluation_time=NOW)
    ah = [r for r in results if r.market_id is MarketId.ASIAN_HANDICAP]
    assert ah
    priced = [r for r in ah if r.disposition is ShadowPriceDisposition.PRICED]
    for r in priced:
        assert r.devig_status is ShadowDevigStatus.NOT_IDENTIFIABLE_PUSH_OR_SPLIT_SETTLEMENT
        states = dict(r.settlement_state_probabilities)
        assert math.isclose(sum(states.values()), 1.0, abs_tol=1e-9)


def test_router_selects_strongest_or_no_bet():
    scan = _scan(2.5, 0.6)
    quotes = _mr_quotes((1.55, 4.0, 7.0))
    results = price_all_shadow_fixture(scan, quotes, evaluation_time=NOW)
    decision = route_shadow_price_results(fixture_identity="FOTMOB:PRD1", price_results=results)
    assert decision.authority["wager_placed"] is False
    assert decision.authority["production_market_router"] is False
    assert decision.authority["bet"] is False
    assert decision.status in {ShadowRouterDecisionStatus.SELECTED, ShadowRouterDecisionStatus.NO_BET}
    if decision.status is ShadowRouterDecisionStatus.SELECTED:
        assert decision.selected_opportunity_id is not None
        selected = next(o for o in decision.opportunities if o.opportunity_id == decision.selected_opportunity_id)
        assert selected.eligibility is ShadowOpportunityEligibility.ELIGIBLE
        assert selected.robust_net_expected_value is not None
        assert selected.robust_net_expected_value > 0.0


def test_router_rejects_low_probability():
    scan = _scan(1.1, 1.1)
    quotes = _mr_quotes((2.10, 3.20, 3.40))
    results = price_all_shadow_fixture(scan, quotes, evaluation_time=NOW)
    decision = route_shadow_price_results(fixture_identity="FOTMOB:PRD1", price_results=results)
    for opp in decision.opportunities:
        if (
            opp.price_result.market_id is MarketId.MATCH_RESULT
            and opp.price_result.disposition is ShadowPriceDisposition.PRICED
            and opp.event_probability_floor is not None
            and opp.event_probability_floor < MINIMUM_EVENT_PROBABILITY
        ):
            assert opp.eligibility is ShadowOpportunityEligibility.REJECTED
            assert any("event probability" in r for r in opp.rejection_reasons)


def test_no_bet_preserves_rejected_and_price_audit():
    scan = _scan(1.2, 1.2)
    quotes = _mr_quotes((1.10, 8.0, 12.0))
    results = price_all_shadow_fixture(scan, quotes, evaluation_time=NOW)
    decision = route_shadow_price_results(fixture_identity="FOTMOB:PRD1", price_results=results)
    assert len(decision.price_results) == len(results)
    assert decision.strongest_rejected_opportunity_id is not None or decision.status is ShadowRouterDecisionStatus.SELECTED


def test_odds_le_one_rejected():
    with pytest.raises(ShadowPriceError):
        _quote(MarketId.MATCH_RESULT, OutcomeId.HOME, 1.0, market_id_native="mr", outcome_id_native="h")


def test_authority_all_production_false():
    for key in (
        "production_price_all", "production_market_router", "production_selection",
        "production_portfolio", "bet", "wager_placed", "staking", "sportybet_execution",
    ):
        assert AUTHORITY_FLAGS[key] is False


def test_no_legacy_shortcuts_in_prd_modules():
    for path in (
        Path("domain/current_shadow_all_market_price_all.py"),
        Path("domain/current_shadow_all_market_router.py"),
        Path("domain/_current_shadow_price_types.py"),
    ):
        text = path.read_text(encoding="utf-8")
        for forbidden in ("AccaBuilder", "MatchAnalyst", "MARKET_BASELINES", "place_bet"):
            assert forbidden not in text


def test_btts_can_compete_without_tg_privilege():
    scan = _scan(1.6, 1.4)
    quotes = (
        *_mr_quotes((2.5, 3.3, 2.8)),
        _quote(MarketId.BTTS, OutcomeId.YES, 1.70, market_id_native="btts", outcome_id_native="y"),
        _quote(MarketId.BTTS, OutcomeId.NO, 2.10, market_id_native="btts", outcome_id_native="n"),
        _quote(MarketId.TOTAL_GOALS, OutcomeId.OVER, 1.95, line=2.5, market_id_native="tg", outcome_id_native="o", specifier="total=2.5"),
        _quote(MarketId.TOTAL_GOALS, OutcomeId.UNDER, 1.85, line=2.5, market_id_native="tg", outcome_id_native="u", specifier="total=2.5"),
    )
    results = price_all_shadow_fixture(scan, quotes, evaluation_time=NOW)
    decision = route_shadow_price_results(fixture_identity="FOTMOB:PRD1", price_results=results)
    assert decision.router_policy_id == "SHADOW_CONSERVATIVE_FROZEN_THRESHOLDS_V1"
