"""Focused trust-boundary tests for PR D Shadow Price-all + Router."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from domain.markets import MARKET_REGISTRY, MarketId, OutcomeId, MarketFamily
from domain import current_all_market_shadow_probability_settlement as prc
from domain._all_market_shadow_types import SOURCE_LANE_CURRENT_SOURCE_BOUND
from domain.current_shadow_all_market_price_all import price_all_shadow_fixture
from domain.current_shadow_all_market_router import route_shadow_price_results
from domain._current_shadow_quote_binding import build_shadow_exact_quote
from domain._current_shadow_price_types import (
    AUTHORITY_FLAGS,
    PRICE_ALL_ISSUANCE_TOKEN,
    ShadowDevigStatus,
    ShadowExactQuote,
    ShadowPriceDisposition,
    ShadowPriceError,
    ShadowPriceResult,
    ShadowRouterDecisionStatus,
    ShadowOpportunityEligibility,
)
from domain.current_sportybet_semantic_registry import (
    ProviderSemanticObservation,
    ProviderSemanticStatus,
    SettlementClass,
    EvidenceFreshnessState,
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
CONTRACT = "b888cebab6447cd4072d823dab67b56f1f75f72eb72d67b692d47a4378b27555"
MAP_POLICY = "PRB_EXACT_NATIVE_ID_NAME_SPECIFIER_OUTCOME_LABEL_V1"


def _xg(home: float = 1.8, away: float = 0.9) -> prc.ResearchXGRates:
    return prc.ResearchXGRates(
        calibrated_home=home,
        calibrated_away=away,
        sealed_prediction_sha256="a" * 64,
        history_prefix_identity="d" * 64,
        completeness_status="SEALED_RESEARCH_RATES",
    )


def _math_scan(home: float = 1.8, away: float = 0.9, provider: str | None = "SUPPORTED"):
    provider_map = None if provider is None else {m: provider for m in MarketId}
    return prc.scan_fixture_all_markets(
        fixture_identity="sr:match:1001",
        research_xg=_xg(home, away),
        total_goals_lines=(1.5, 2.5),
        asian_handicap_home_lines=(-0.5, 0.0),
        provider_semantic_by_market=provider_map,
    )


def _current_lane_scan(home: float = 1.8, away: float = 0.9, provider: str | None = "SUPPORTED"):
    return replace(_math_scan(home, away, provider), source_lane=SOURCE_LANE_CURRENT_SOURCE_BOUND)


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


def _obs(inv, sel, market, outcome, *, line=None):
    return ProviderSemanticObservation(
        canonical_market_id=market,
        canonical_outcome_id=outcome,
        canonical_family=MARKET_REGISTRY[market].family,
        provider_market_id=sel.market_id,
        provider_market_name=sel.market_name,
        provider_specifier=sel.specifier,
        line=line,
        provider_outcome_id=sel.outcome_id,
        provider_outcome_name=sel.outcome_name,
        bookable=True,
        bookability_basis="EXPLICIT_ACTIVE_FLAG",
        provider_event_id=inv.event_id,
        fixture_identity=inv.event_id,
        fixture_identity_basis="EXACT_PROVIDER_EVENT_ID",
        observed_at=inv.observed_at,
        source_event_detail_raw_sha256=inv.source_raw_sha256,
        source_manifest_sha256=inv.source_manifest_sha256,
        source_inventory_sha256=inv.canonical_sha256,
        source_contract_identity=CONTRACT,
        mapping_policy_identity=MAP_POLICY,
        settlement_class=SettlementClass.REGULATION_1X2_PARTITION,
        settlement_equivalence_reviewed=True,
        ordinary_devig_partition_valid=True,
        event_set_overlaps=False,
        push_or_split_settlement=False,
        line_analytically_eligible=True,
        evidence_freshness=EvidenceFreshnessState.CURRENT,
    )


def _issue_mr(odds=(1.40, 4.50, 7.00)):
    sels = (
        _sel("1", "1", odds[0], market_name="1X2", outcome_name="Home"),
        _sel("1", "2", odds[1], market_name="1X2", outcome_name="Draw"),
        _sel("1", "3", odds[2], market_name="1X2", outcome_name="Away"),
    )
    inv = _inventory(sels)
    quotes = tuple(
        build_shadow_exact_quote(
            inventory=inv,
            observation=_obs(inv, sels[i], MarketId.MATCH_RESULT, o),
            coverage_status=ProviderSemanticStatus.SUPPORTED,
        )
        for i, o in enumerate((OutcomeId.HOME, OutcomeId.DRAW, OutcomeId.AWAY))
    )
    return quotes, inv, sels


def test_cannot_relabel_1x2_as_btts():
    sel = _sel("1", "1", 1.50, market_name="1X2", outcome_name="Home")
    inv = _inventory((sel,))
    with pytest.raises(Exception):
        obs = _obs(inv, sel, MarketId.BTTS, OutcomeId.YES)
        build_shadow_exact_quote(
            inventory=inv,
            observation=obs,
            coverage_status=ProviderSemanticStatus.SUPPORTED,
        )


def test_mathematical_scan_rejected():
    scan = _math_scan()
    assert getattr(scan, "source_lane", None) != SOURCE_LANE_CURRENT_SOURCE_BOUND
    quotes, _, _ = _issue_mr()
    with pytest.raises(ShadowPriceError, match="CURRENT_SOURCE_BOUND"):
        price_all_shadow_fixture(scan, quotes, evaluation_time=NOW)


def test_cannot_mint_priced_without_issuance():
    with pytest.raises(ShadowPriceError, match="price_all|PRICED"):
        ShadowPriceResult(
            fixture_identity="sr:match:1001",
            market_id=MarketId.MATCH_RESULT,
            outcome_id=OutcomeId.HOME,
            line=None,
            disposition=ShadowPriceDisposition.PRICED,
            model_probability=0.7,
            decimal_odds=1.5,
            implied_probability=1 / 1.5,
            fair_probability=0.5,
            overround=1.1,
            devig_status=ShadowDevigStatus.PROPORTIONAL_COMPLETE_PARTITION,
            net_expected_value=0.2,
            expected_return_multiplier=1.2,
            settlement_state_probabilities=(("WIN", 0.7), ("LOSS", 0.3)),
            settlement_unit_returns=(("WIN", 0.5), ("LOSS", -1.0)),
            quote_identity_sha256="e" * 64,
            provider_event_id="sr:match:1001",
            provider_semantic_status="SUPPORTED",
            rejection_reason=None,
            probability_method="score_matrix",
            prc_scan_sha256="f" * 64,
            source_raw_sha256=SHA_RAW,
            source_manifest_sha256=SHA_MAN,
            source_inventory_sha256="e" * 64,
            price_all_issuance="FORGED",
        )


def test_price_all_current_lane_and_ancestry():
    scan = _current_lane_scan(2.2, 0.7)
    quotes, _, _ = _issue_mr((1.50, 4.20, 6.50))
    results = price_all_shadow_fixture(scan, quotes, evaluation_time=NOW)
    assert {r.market_id for r in results} == set(MarketId)
    home = next(
        r for r in results
        if r.market_id is MarketId.MATCH_RESULT and r.outcome_id is OutcomeId.HOME
    )
    assert home.disposition is ShadowPriceDisposition.PRICED
    assert home.price_all_issuance == PRICE_ALL_ISSUANCE_TOKEN
    assert home.prc_scan_sha256 is not None
    assert home.source_raw_sha256 == SHA_RAW
    assert home.to_dict()["price_all_issuance"] == PRICE_ALL_ISSUANCE_TOKEN


def test_empty_quotes_no_bet():
    scan = _current_lane_scan()
    results = price_all_shadow_fixture(scan, (), evaluation_time=NOW)
    decision = route_shadow_price_results(
        fixture_identity="sr:match:1001", price_results=results
    )
    assert decision.status is ShadowRouterDecisionStatus.NO_BET


def test_incomplete_partition_rejected():
    scan = _current_lane_scan(2.2, 0.7)
    sel = _sel("1", "1", 1.50, market_name="1X2", outcome_name="Home")
    inv = _inventory((sel,))
    quotes = (
        build_shadow_exact_quote(
            inventory=inv,
            observation=_obs(inv, sel, MarketId.MATCH_RESULT, OutcomeId.HOME),
            coverage_status=ProviderSemanticStatus.SUPPORTED,
        ),
    )
    results = price_all_shadow_fixture(scan, quotes, evaluation_time=NOW)
    home = next(
        r for r in results
        if r.market_id is MarketId.MATCH_RESULT and r.outcome_id is OutcomeId.HOME
    )
    assert home.devig_status is ShadowDevigStatus.INCOMPLETE_PARTITION
    decision = route_shadow_price_results(
        fixture_identity="sr:match:1001", price_results=results
    )
    opp = next(
        o for o in decision.opportunities
        if o.price_result.market_id is MarketId.MATCH_RESULT
        and o.price_result.outcome_id is OutcomeId.HOME
    )
    assert opp.eligibility is ShadowOpportunityEligibility.REJECTED


def test_observation_sha_mismatch_fails():
    sel = _sel("1", "1", 1.50, market_name="1X2", outcome_name="Home")
    inv = _inventory((sel,))
    obs = _obs(inv, sel, MarketId.MATCH_RESULT, OutcomeId.HOME)
    with pytest.raises(Exception):
        bad = replace(obs, source_inventory_sha256="0" * 64)
        build_shadow_exact_quote(
            inventory=inv,
            observation=bad,
            coverage_status=ProviderSemanticStatus.SUPPORTED,
        )


def test_authority_false():
    for key in (
        "production_price_all",
        "production_market_router",
        "production_selection",
        "bet",
        "wager_placed",
        "staking",
        "sportybet_execution",
    ):
        assert AUTHORITY_FLAGS[key] is False


def test_provider_unproven_blocks():
    scan = _current_lane_scan(provider="CURRENT_PROVIDER_UNAVAILABLE/UNPROVEN")
    quotes, _, _ = _issue_mr()
    results = price_all_shadow_fixture(scan, quotes, evaluation_time=NOW)
    mr = [r for r in results if r.market_id is MarketId.MATCH_RESULT]
    assert all(r.disposition is ShadowPriceDisposition.UNPRICED_PROVIDER_BLOCKED for r in mr)


def test_no_legacy():
    for path in (
        Path("domain/current_shadow_all_market_price_all.py"),
        Path("domain/current_shadow_all_market_router.py"),
    ):
        text = path.read_text()
        for forbidden in ("AccaBuilder", "MatchAnalyst", "place_bet"):
            assert forbidden not in text
