"""Focused tests for PR D Shadow Price-all + all-market Router (source-bound)."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from domain.markets import MarketId, OutcomeId
from domain import current_all_market_shadow_probability_settlement as prc
from domain.current_shadow_all_market_price_all import (
    build_shadow_exact_quote,
    price_all_shadow_fixture,
)
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
from domain.sportybet_live_event_quote_evidence import (
    INVENTORY_DATASET_NAME,
    OBSERVATION_AUTHORITY,
    SportyBetLiveEventQuoteInventory,
    SportyBetLiveEventSelection,
)

NOW = datetime(2026, 8, 29, 17, 0, 0, tzinfo=timezone.utc)
SHA_RAW = "b" * 64
SHA_MAN = "c" * 64


def _xg(home: float = 1.8, away: float = 0.9) -> prc.ResearchXGRates:
    return prc.ResearchXGRates(
        calibrated_home=home,
        calibrated_away=away,
        sealed_prediction_sha256="a" * 64,
        history_prefix_identity="d" * 64,
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


def _sel(market_id, outcome_id, odds, *, market_name, outcome_name, specifier=None):
    raw = f"{odds:.2f}"
    return SportyBetLiveEventSelection(
        event_id="sr:match:1001",
        market_id=market_id,
        market_name=market_name,
        specifier=specifier,
        outcome_id=outcome_id,
        outcome_name=outcome_name,
        bookable=True,
        bookability_basis="EXPLICIT_ACTIVE_FLAG",
        odds_raw=raw,
        odds_decimal=float(raw),
    )


def _inventory(selections, *, observed_at=NOW):
    return SportyBetLiveEventQuoteInventory(
        dataset_name=INVENTORY_DATASET_NAME,
        event_id="sr:match:1001",
        home_team_name="Home",
        away_team_name="Away",
        kickoff_utc=observed_at + timedelta(hours=2),
        booking_status=None,
        event_status="not_started",
        match_status=None,
        prematch_bookable_observed=True,
        observed_at=observed_at,
        observation_authority=OBSERVATION_AUTHORITY,
        provider_quote_at=None,
        provider_snapshot_id=None,
        source_manifest_sha256=SHA_MAN,
        source_raw_sha256=SHA_RAW,
        selections=selections,
    )


def _issue(inv, sel, market, outcome, *, line=None, status="SUPPORTED"):
    return build_shadow_exact_quote(
        inventory=inv,
        selection=sel,
        fixture_identity="FOTMOB:PRD1",
        market_id=market,
        outcome_id=outcome,
        line=line,
        provider_semantic_status=status,
    )


def _mr_quotes(odds=(1.40, 4.50, 7.00)):
    sels = (
        _sel("1", "1", odds[0], market_name="1X2", outcome_name="Home"),
        _sel("1", "2", odds[1], market_name="1X2", outcome_name="Draw"),
        _sel("1", "3", odds[2], market_name="1X2", outcome_name="Away"),
    )
    inv = _inventory(sels)
    return (
        _issue(inv, sels[0], MarketId.MATCH_RESULT, OutcomeId.HOME),
        _issue(inv, sels[1], MarketId.MATCH_RESULT, OutcomeId.DRAW),
        _issue(inv, sels[2], MarketId.MATCH_RESULT, OutcomeId.AWAY),
    ), inv


def test_caller_cannot_mint_shadow_exact_quote_directly():
    with pytest.raises(ShadowPriceError, match="source-bound builder"):
        ShadowExactQuote(
            fixture_identity="FOTMOB:PRD1",
            provider_event_id="sr:match:1001",
            market_id=MarketId.MATCH_RESULT,
            outcome_id=OutcomeId.HOME,
            line=None,
            provider_market_id="1",
            provider_market_name="1X2",
            provider_specifier=None,
            provider_outcome_id="1",
            provider_outcome_name="Home",
            decimal_odds=1.5,
            observed_at=NOW,
            source_raw_sha256=SHA_RAW,
            source_manifest_sha256=SHA_MAN,
            source_inventory_sha256="e" * 64,
            provider_semantic_status="SUPPORTED",
            source_bound_issuance="FORGED",
        )


def test_price_all_retains_15_market_audit_surface():
    scan = _scan()
    quotes, _ = _mr_quotes()
    results = price_all_shadow_fixture(scan, quotes, evaluation_time=NOW)
    assert {r.market_id for r in results} == set(MarketId)
    for r in results:
        assert r.prc_scan_sha256 is not None
        assert r.fixture_identity == "FOTMOB:PRD1"


def test_empty_quotes_produces_no_bet_not_fixture_mismatch():
    scan = _scan()
    results = price_all_shadow_fixture(scan, (), evaluation_time=NOW)
    assert all(r.fixture_identity == "FOTMOB:PRD1" for r in results)
    decision = route_shadow_price_results(fixture_identity="FOTMOB:PRD1", price_results=results)
    assert decision.status is ShadowRouterDecisionStatus.NO_BET
    assert "UNKNOWN" not in decision.fixture_identity


def test_provider_unproven_blocks_pricing():
    scan = _scan(provider="CURRENT_PROVIDER_UNAVAILABLE/UNPROVEN")
    quotes, _ = _mr_quotes()
    results = price_all_shadow_fixture(scan, quotes, evaluation_time=NOW)
    mr = [r for r in results if r.market_id is MarketId.MATCH_RESULT]
    assert all(r.disposition is ShadowPriceDisposition.UNPRICED_PROVIDER_BLOCKED for r in mr)


def test_match_result_proportional_devig_and_ancestry():
    scan = _scan(2.2, 0.7)
    quotes, _ = _mr_quotes((1.50, 4.20, 6.50))
    results = price_all_shadow_fixture(scan, quotes, evaluation_time=NOW)
    home = next(r for r in results if r.market_id is MarketId.MATCH_RESULT and r.outcome_id is OutcomeId.HOME)
    assert home.disposition is ShadowPriceDisposition.PRICED
    assert home.devig_status is ShadowDevigStatus.PROPORTIONAL_COMPLETE_PARTITION
    assert home.fair_probability is not None
    assert home.source_raw_sha256 == SHA_RAW
    assert home.source_manifest_sha256 == SHA_MAN
    assert home.score_matrix_audit is not None
    assert home.sealed_prediction_sha256 == "a" * 64
    d = home.to_dict()
    assert d["prc_scan_sha256"] is not None
    assert d["score_matrix_audit"] is not None
    assert d["source_raw_sha256"] == SHA_RAW


def test_incomplete_ordinary_partition_not_router_eligible():
    scan = _scan(2.2, 0.7)
    sel = _sel("1", "1", 1.50, market_name="1X2", outcome_name="Home")
    inv = _inventory((sel,))
    quotes = (_issue(inv, sel, MarketId.MATCH_RESULT, OutcomeId.HOME),)
    results = price_all_shadow_fixture(scan, quotes, evaluation_time=NOW)
    home = next(r for r in results if r.market_id is MarketId.MATCH_RESULT and r.outcome_id is OutcomeId.HOME)
    assert home.disposition is ShadowPriceDisposition.PRICED
    assert home.devig_status is ShadowDevigStatus.INCOMPLETE_PARTITION
    assert home.fair_probability is None
    decision = route_shadow_price_results(fixture_identity="FOTMOB:PRD1", price_results=results)
    opp = next(
        o for o in decision.opportunities
        if o.price_result.market_id is MarketId.MATCH_RESULT
        and o.price_result.outcome_id is OutcomeId.HOME
    )
    assert opp.eligibility is ShadowOpportunityEligibility.REJECTED
    assert any("PROPORTIONAL_COMPLETE_PARTITION" in r or "fair_probability" in r for r in opp.rejection_reasons)


def test_cross_snapshot_ordinary_not_router_eligible():
    scan = _scan(2.2, 0.7)
    sels_a = (
        _sel("1", "1", 1.50, market_name="1X2", outcome_name="Home"),
        _sel("1", "2", 4.20, market_name="1X2", outcome_name="Draw"),
        _sel("1", "3", 6.50, market_name="1X2", outcome_name="Away"),
    )
    inv_a = _inventory(sels_a)
    sels_b = (_sel("1", "3", 6.50, market_name="1X2", outcome_name="Away"),)
    inv_b = SportyBetLiveEventQuoteInventory(
        dataset_name=INVENTORY_DATASET_NAME,
        event_id="sr:match:1001",
        home_team_name="Home",
        away_team_name="Away",
        kickoff_utc=NOW + timedelta(hours=2),
        booking_status=None,
        event_status="not_started",
        match_status=None,
        prematch_bookable_observed=True,
        observed_at=NOW,
        observation_authority=OBSERVATION_AUTHORITY,
        provider_quote_at=None,
        provider_snapshot_id=None,
        source_manifest_sha256=SHA_MAN,
        source_raw_sha256="f" * 64,
        selections=sels_b,
    )
    quotes = (
        _issue(inv_a, sels_a[0], MarketId.MATCH_RESULT, OutcomeId.HOME),
        _issue(inv_a, sels_a[1], MarketId.MATCH_RESULT, OutcomeId.DRAW),
        _issue(inv_b, sels_b[0], MarketId.MATCH_RESULT, OutcomeId.AWAY),
    )
    results = price_all_shadow_fixture(scan, quotes, evaluation_time=NOW)
    home = next(r for r in results if r.market_id is MarketId.MATCH_RESULT and r.outcome_id is OutcomeId.HOME)
    assert home.devig_status is ShadowDevigStatus.CROSS_SNAPSHOT
    decision = route_shadow_price_results(fixture_identity="FOTMOB:PRD1", price_results=results)
    for opp in decision.opportunities:
        if opp.price_result.market_id is MarketId.MATCH_RESULT and opp.price_result.disposition is ShadowPriceDisposition.PRICED:
            assert opp.eligibility is ShadowOpportunityEligibility.REJECTED


def test_double_chance_respects_probability_floor():
    scan = _scan(1.1, 1.1)
    sels = (
        _sel("10", "9", 1.30, market_name="Double Chance", outcome_name="Home or Draw"),
        _sel("10", "10", 1.40, market_name="Double Chance", outcome_name="Home or Away"),
        _sel("10", "11", 1.50, market_name="Double Chance", outcome_name="Draw or Away"),
    )
    inv = _inventory(sels)
    quotes = (
        _issue(inv, sels[0], MarketId.DOUBLE_CHANCE, OutcomeId.HOME_OR_DRAW),
        _issue(inv, sels[1], MarketId.DOUBLE_CHANCE, OutcomeId.HOME_OR_AWAY),
        _issue(inv, sels[2], MarketId.DOUBLE_CHANCE, OutcomeId.DRAW_OR_AWAY),
    )
    results = price_all_shadow_fixture(scan, quotes, evaluation_time=NOW)
    decision = route_shadow_price_results(fixture_identity="FOTMOB:PRD1", price_results=results)
    for opp in decision.opportunities:
        if (
            opp.price_result.market_id is MarketId.DOUBLE_CHANCE
            and opp.price_result.disposition is ShadowPriceDisposition.PRICED
            and opp.event_probability_floor is not None
            and opp.event_probability_floor < MINIMUM_EVENT_PROBABILITY
        ):
            assert opp.eligibility is ShadowOpportunityEligibility.REJECTED
            assert any("event probability" in r for r in opp.rejection_reasons)


def test_dnb_settlement_aware_ev():
    scan = _scan(2.0, 0.8)
    sels = (
        _sel("11", "4", 1.45, market_name="Draw No Bet", outcome_name="Home"),
        _sel("11", "5", 2.60, market_name="Draw No Bet", outcome_name="Away"),
    )
    inv = _inventory(sels)
    quotes = (
        _issue(inv, sels[0], MarketId.DRAW_NO_BET, OutcomeId.HOME),
        _issue(inv, sels[1], MarketId.DRAW_NO_BET, OutcomeId.AWAY),
    )
    results = price_all_shadow_fixture(scan, quotes, evaluation_time=NOW)
    dnb = [r for r in results if r.market_id is MarketId.DRAW_NO_BET and r.disposition is ShadowPriceDisposition.PRICED]
    assert dnb
    for r in dnb:
        assert r.devig_status is ShadowDevigStatus.NOT_IDENTIFIABLE_PUSH_OR_SPLIT_SETTLEMENT
        states = dict(r.settlement_state_probabilities)
        assert math.isclose(sum(states.values()), 1.0, abs_tol=1e-9)


def test_stale_quote():
    scan = _scan()
    sel = _sel("1", "1", 1.5, market_name="1X2", outcome_name="Home")
    inv = _inventory((sel,), observed_at=NOW - timedelta(seconds=2000))
    quotes = (_issue(inv, sel, MarketId.MATCH_RESULT, OutcomeId.HOME),)
    results = price_all_shadow_fixture(scan, quotes, evaluation_time=NOW)
    home = next(r for r in results if r.market_id is MarketId.MATCH_RESULT and r.outcome_id is OutcomeId.HOME)
    assert home.disposition is ShadowPriceDisposition.UNPRICED_STALE_QUOTE


def test_selection_not_in_inventory_fails():
    sel = _sel("1", "1", 1.5, market_name="1X2", outcome_name="Home")
    other = _sel("1", "2", 4.0, market_name="1X2", outcome_name="Draw")
    inv = _inventory((other,))
    with pytest.raises(ShadowPriceError, match="not found in inventory|not present"):
        build_shadow_exact_quote(
            inventory=inv,
            selection=sel,
            fixture_identity="FOTMOB:PRD1",
            market_id=MarketId.MATCH_RESULT,
            outcome_id=OutcomeId.HOME,
            line=None,
            provider_semantic_status="SUPPORTED",
        )


def test_router_authority_false():
    scan = _scan(2.5, 0.6)
    quotes, _ = _mr_quotes((1.55, 4.0, 7.0))
    results = price_all_shadow_fixture(scan, quotes, evaluation_time=NOW)
    decision = route_shadow_price_results(fixture_identity="FOTMOB:PRD1", price_results=results)
    assert decision.authority["wager_placed"] is False
    assert decision.authority["production_market_router"] is False
    assert decision.authority["bet"] is False


def test_authority_all_production_false():
    for key in (
        "production_price_all", "production_market_router", "production_selection",
        "production_portfolio", "bet", "wager_placed", "staking", "sportybet_execution",
    ):
        assert AUTHORITY_FLAGS[key] is False


def test_no_legacy_shortcuts():
    for path in (
        Path("domain/current_shadow_all_market_price_all.py"),
        Path("domain/current_shadow_all_market_router.py"),
        Path("domain/_current_shadow_price_types.py"),
    ):
        text = path.read_text(encoding="utf-8")
        for forbidden in ("AccaBuilder", "MatchAnalyst", "MARKET_BASELINES", "place_bet"):
            assert forbidden not in text


def test_total_goals_multi_line():
    scan = _scan()
    sels = (
        _sel("18", "12", 1.90, market_name="Over/Under", outcome_name="Over", specifier="total=1.5"),
        _sel("18", "13", 1.90, market_name="Over/Under", outcome_name="Under", specifier="total=1.5"),
        _sel("18", "12", 2.10, market_name="Over/Under", outcome_name="Over", specifier="total=2.5"),
        _sel("18", "13", 1.75, market_name="Over/Under", outcome_name="Under", specifier="total=2.5"),
    )
    inv = _inventory(sels)
    quotes = (
        _issue(inv, sels[0], MarketId.TOTAL_GOALS, OutcomeId.OVER, line=1.5),
        _issue(inv, sels[1], MarketId.TOTAL_GOALS, OutcomeId.UNDER, line=1.5),
        _issue(inv, sels[2], MarketId.TOTAL_GOALS, OutcomeId.OVER, line=2.5),
        _issue(inv, sels[3], MarketId.TOTAL_GOALS, OutcomeId.UNDER, line=2.5),
    )
    results = price_all_shadow_fixture(scan, quotes, evaluation_time=NOW)
    tg = [r for r in results if r.market_id is MarketId.TOTAL_GOALS and r.disposition is ShadowPriceDisposition.PRICED]
    lines = sorted({r.line for r in tg})
    assert 1.5 in lines and 2.5 in lines
