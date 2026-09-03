from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from domain import current_shadow_all_market_portfolio as portfolio
from domain import current_sportybet_accumulator_request as production_request
from domain._accumulator_optimizer_contracts import FragilityStatus
from domain._current_shadow_price_core import (
    ShadowOpportunityEligibility, ShadowPriceDisposition, ShadowRouterDecisionStatus,
)
from domain.markets import MARKET_REGISTRY, MarketFamily, MarketId, OutcomeId

UTC = timezone.utc
NOW = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


def _leg(
    token: str,
    *,
    home: str | None = None,
    away: str | None = None,
    competition: str = "League A",
    market_id: MarketId = MarketId.BTTS,
    survival: float = 0.70,
    ev: float = 0.03,
    confidence: float = 0.70,
    odds: float = 2.0,
    fragile: FragilityStatus | None = None,
) -> portfolio.ShadowPortfolioLeg:
    home = home or f"Home {token}"
    away = away or f"Away {token}"
    family = MARKET_REGISTRY[market_id].family
    status = fragile or portfolio._fragility(ev, survival)
    return portfolio.ShadowPortfolioLeg(
        leg_id=(token * 64)[:64],
        price_all_bundle_sha256="a" * 64,
        router_decision_sha256="b" * 64,
        selected_opportunity_id="c" * 64,
        fixture_identity=f"FOTMOB:{1000 + len(token)}{ord(token[0])}",
        provider_event_id=f"sr:match:{900000 + ord(token[0])}",
        home_team=home,
        away_team=away,
        competition=competition,
        kickoff_utc=NOW + timedelta(hours=4),
        market_id=market_id,
        outcome_id=MARKET_REGISTRY[market_id].supported_outcomes[0],
        line=None,
        market_family=family,
        quote_identity_sha256="d" * 64,
        provider_market_id="29",
        provider_market_name="GG/NG",
        provider_specifier=None,
        provider_outcome_id="74",
        provider_outcome_name="Yes",
        decimal_odds=odds,
        source_raw_sha256="e" * 64,
        source_manifest_sha256="f" * 64,
        source_inventory_sha256="1" * 64,
        provider_registry_sha256="2" * 64,
        provider_observation_sha256="3" * 64,
        fixture_reconciliation_sha256="4" * 64,
        prediction_confidence=confidence,
        prediction_confidence_method="SCALAR_MODEL_PROBABILITY_V1",
        prediction_first_rank=1,
        canonical_prediction_identity=f"{market_id.value}|{MARKET_REGISTRY[market_id].supported_outcomes[0].value}|NONE",
        router_policy_id="SHADOW_PREDICTION_FIRST_ROUTER_V2",
        portfolio_policy_id=portfolio.PORTFOLIO_POLICY_ID,
        selection_reason="PREDICTION_FIRST_AUTHORITY",
        robust_net_expected_value=ev,
        robust_edge=0.02,
        event_probability_floor=survival,
        survival_probability_floor=survival,
        router_quote_age_seconds=10.0,
        portfolio_quote_age_seconds=20.0,
        portfolio_kickoff_lead_seconds=4 * 3600.0,
        fragility_status=status,
    )


def _source(token: str):
    value = object.__new__(portfolio.ShadowPortfolioRouterInput)
    object.__setattr__(value, "fixture_identity", f"FOTMOB:{100 + ord(token)}")
    object.__setattr__(value, "provider_event_id", f"sr:match:{500 + ord(token)}")
    object.__setattr__(value, "source_observed_at", NOW - timedelta(seconds=20))
    object.__setattr__(value, "kickoff_utc", NOW + timedelta(hours=3))
    object.__setattr__(value, "price_all_bundle", SimpleNamespace(evaluation_time=NOW - timedelta(seconds=10)))
    object.__setattr__(
        value,
        "router_decision",
        SimpleNamespace(
            status=ShadowRouterDecisionStatus.SELECTED,
            selected_opportunity_id="c" * 64,
        ),
    )
    object.__setattr__(value, "router_decision_sha256", "b" * 64)
    return value


def test_router_input_and_optimization_are_builder_only():
    with pytest.raises(portfolio.CurrentShadowPortfolioError, match="builder-only"):
        portfolio.ShadowPortfolioRouterInput()
    with pytest.raises(portfolio.CurrentShadowPortfolioError, match="builder-only"):
        portfolio.ShadowPortfolioOptimization()


def test_naked_router_or_price_all_objects_cannot_enter_trust_builder():
    with pytest.raises(portfolio.CurrentShadowPortfolioError):
        portfolio.build_shadow_portfolio_router_input(
            price_all_bundle=object(),
            router_decision=object(),
        )


def test_prediction_first_caps_exclude_legacy_fragility_authority():
    assert portfolio._caps(1) == {"team": 1, "competition": 1, "market_family": 1}
    assert portfolio._caps(20) == {"team": 1, "competition": 8, "market_family": 10}
    assert portfolio._caps(50) == {"team": 1, "competition": 20, "market_family": 25}


def test_fragility_thresholds_are_frozen_and_exact():
    assert portfolio._fragility(0.02, 0.60) is FragilityStatus.NON_FRAGILE
    assert portfolio._fragility(0.019, 0.60) is FragilityStatus.FRAGILE_THIN_VALUE
    assert portfolio._fragility(0.02, 0.59) is FragilityStatus.FRAGILE_THIN_SURVIVAL
    assert portfolio._fragility(0.019, 0.59) is FragilityStatus.FRAGILE_THIN_VALUE_AND_SURVIVAL


def test_dnb_and_asian_handicap_survival_semantics_are_not_scalarized():
    dnb = SimpleNamespace(
        market_id=MarketId.DRAW_NO_BET,
        settlement_state_probabilities=(("WIN", 0.5), ("PUSH", 0.2), ("LOSS", 0.3)),
    )
    ah = SimpleNamespace(
        market_id=MarketId.ASIAN_HANDICAP,
        settlement_state_probabilities=(
            ("WIN", 0.30), ("HALF_WIN", 0.15), ("PUSH", 0.10),
            ("HALF_LOSS", 0.15), ("LOSS", 0.30),
        ),
    )
    opportunity = SimpleNamespace(event_probability_floor=None)
    assert portfolio._survival(opportunity, dnb) == pytest.approx(0.7)
    assert portfolio._survival(opportunity, ah) == pytest.approx(0.55)


def test_malformed_full_settlement_state_sets_fail_closed():
    bad_dnb = SimpleNamespace(
        market_id=MarketId.DRAW_NO_BET,
        settlement_state_probabilities=(("WIN", 0.6), ("LOSS", 0.4)),
    )
    with pytest.raises(portfolio.CurrentShadowPortfolioError, match="DNB settlement"):
        portfolio._survival(SimpleNamespace(event_probability_floor=None), bad_dnb)


def test_team_competition_and_family_caps_are_explicit_but_fragility_is_diagnostic():
    caps = {"team": 1, "competition": 1, "market_family": 1}
    selected = [
        _leg(
            "a",
            home="Shared",
            competition="League A",
            survival=0.55,
            ev=0.01,
        )
    ]
    candidate = _leg(
        "b",
        home="Shared",
        competition="League A",
        market_id=MarketId.BTTS,
        survival=0.55,
        ev=0.01,
    )
    reasons = portfolio._constraint_reasons(candidate, selected, caps)
    assert any(item.startswith("TEAM_CAP:") for item in reasons)
    assert any(item.startswith("COMPETITION_CAP:") for item in reasons)
    assert any(item.startswith("MARKET_FAMILY_CAP:") for item in reasons)
    assert "FRAGILITY_CAP" not in reasons


def test_prediction_confidence_outranks_ev_survival_and_odds():
    high = _leg("a", confidence=0.80, ev=-0.20, survival=0.55, odds=1.09)
    low = _leg("b", confidence=0.70, ev=0.50, survival=0.95, odds=8.0)
    assert portfolio._prediction_selection_key(high) < portfolio._prediction_selection_key(low)


def test_ev_and_eligible_odds_changes_cannot_change_prediction_order():
    first = _leg("a", confidence=0.75, ev=-0.50, odds=1.09)
    changed = _leg("a", confidence=0.75, ev=9.0, odds=20.0)
    other = _leg("b", confidence=0.70, ev=100.0, odds=50.0)
    assert portfolio._prediction_selection_key(first) == portfolio._prediction_selection_key(changed)
    assert portfolio._prediction_selection_key(first) < portfolio._prediction_selection_key(other)


def test_hard_cap_exclusion_reason_names_exact_cap():
    selected = [_leg("a", competition="League A", confidence=0.90)]
    candidate = _leg("b", competition="League A", confidence=0.95)
    reasons = portfolio._constraint_reasons(
        candidate, selected, {"team": 1, "competition": 1, "market_family": 2}
    )
    assert reasons == ("COMPETITION_CAP:League A",)


def test_optimizer_shortfall_never_pads_router_rejected_or_counterfactual(monkeypatch):
    sources = (_source("a"), _source("b"))
    legs = {
        sources[0].fixture_identity: _leg("a", competition="League A"),
        sources[1].fixture_identity: _leg("b", home= "Home b", away="Away b", competition="League A"),
    }
    monkeypatch.setattr(portfolio, "verify_shadow_portfolio_router_input", lambda item: item)
    monkeypatch.setattr(portfolio, "_build_leg", lambda item, now: legs[item.fixture_identity])
    monkeypatch.setattr(
        portfolio, "_diagnostics",
        lambda *_args: ((), (), {}, {}),
    )
    result = portfolio.optimize_shadow_portfolio(sources, target_size=20, evaluation_time=NOW)
    assert len(result.selected_legs) <= 2
    assert result.shortfall == 20 - len(result.selected_legs)
    assert result.shortfall > 0
    assert result.to_dict()["statistical_correlation_coefficients"] is None


def test_all_markets_families_and_monotone_funnels_are_always_present():
    leg = _leg("a", confidence=0.80, odds=1.20)
    price_result = SimpleNamespace(
        market_id=leg.market_id,
        outcome_id=leg.outcome_id,
        line=leg.line,
        quote_identity_sha256="d" * 64,
        disposition=ShadowPriceDisposition.PRICED,
        decimal_odds=1.20,
    )
    opportunity = SimpleNamespace(
        opportunity_id=leg.selected_opportunity_id,
        price_result=price_result,
        prediction_confidence=0.80,
        prediction_confidence_method="SCALAR_MODEL_PROBABILITY_V1",
        prediction_first_rank=1,
        robust_net_expected_value=-0.10,
        robust_edge=-0.05,
        eligibility=ShadowOpportunityEligibility.ELIGIBLE,
        rejection_reasons=(),
    )
    source = SimpleNamespace(
        fixture_identity=leg.fixture_identity,
        provider_event_id=leg.provider_event_id,
        router_decision=SimpleNamespace(opportunities=(opportunity,)),
    )
    markets, families, fixture_funnel, opportunity_funnel = portfolio._diagnostics(
        (source,), (leg,), ()
    )
    assert [row["market_id"] for row in markets] == [item.value for item in MarketId]
    assert [row["market_family"] for row in families] == [item.value for item in MarketFamily]
    assert next(row for row in families if row["market_family"] == "ASIAN_HANDICAP")["candidate_count"] == 0
    for funnel in (fixture_funnel, opportunity_funnel):
        assert funnel["unit"] in {"fixture", "opportunity"}
        values = [funnel[key] for key in (
            "policy_approved", "provider_present", "identity_reconciled", "model_ready",
            "priced", "prediction_qualified", "odds_qualified", "portfolio_selected",
        )]
        assert values == sorted(values, reverse=True)


def test_duplicate_fixture_and_provider_event_inputs_fail_closed(monkeypatch):
    one = _source("a")
    two = _source("b")
    monkeypatch.setattr(portfolio, "verify_shadow_portfolio_router_input", lambda item: item)
    object.__setattr__(two, "fixture_identity", one.fixture_identity)
    with pytest.raises(portfolio.CurrentShadowPortfolioError, match="duplicate fixture"):
        portfolio.optimize_shadow_portfolio((one, two), target_size=2, evaluation_time=NOW)
    two = _source("b")
    object.__setattr__(two, "provider_event_id", one.provider_event_id)
    with pytest.raises(portfolio.CurrentShadowPortfolioError, match="duplicate provider event"):
        portfolio.optimize_shadow_portfolio((one, two), target_size=2, evaluation_time=NOW)


def test_target_bounds_and_production_accumulator_phase6_block_remain_unchanged(tmp_path):
    with pytest.raises(ValueError):
        portfolio.optimize_shadow_portfolio((), target_size=0, evaluation_time=NOW)
    with pytest.raises(ValueError):
        portfolio.optimize_shadow_portfolio((), target_size=51, evaluation_time=NOW)
    result = production_request.execute_current_accumulator_request(
        target_size=1,
        output_dir=tmp_path / "production-request",
    )
    assert result.status == production_request.STATUS_PHASE6_AUTHORITY_REQUIRED
    assert result.real_current_provider_execution_attempted is False
    assert result.wager_placed is False
