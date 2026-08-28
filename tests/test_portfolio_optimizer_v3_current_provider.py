from __future__ import annotations

from datetime import timedelta

import pytest

from domain import portfolio_optimizer_v3_current_provider as portfolio
from domain import sportybet_current_event_discovery_reconciliation as current_recon
from domain._portfolio_optimizer_v2_direct_provider_contracts import PortfolioOptimizationStatus
from tests.test_current_direct_provider_live_quote_mapping_consumption import EVALUATION
from tests.test_market_router_v3_current_provider import (
    EVENT,
    FIXTURE,
    KICKOFF,
    _fixture_state,
    _priced_match_result,
)
from domain import market_router_v3_current_provider as router


def _input(monkeypatch, probability: float = 0.60):
    evaluation = _priced_match_result(monkeypatch, probability=probability)
    decision = router.route_price_all_v3_current_provider_as_of(
        evaluation,
        fixture_state=_fixture_state(),
        evaluation_time=EVALUATION + timedelta(seconds=10),
    )
    retained = evaluation._source_bundle._source_mapping._current_bundle
    retained.rows = (
        current_recon.CurrentEventReconciliationRow(
            event_id=EVENT,
            home_team_name=evaluation.home_team_name,
            away_team_name=evaluation.away_team_name,
            competition_name="Reviewed League",
            kickoff_utc=KICKOFF,
            discovery_observed_at=evaluation.discovery_observed_at,
            discovery_age_seconds=evaluation.discovery_age_seconds,
            kickoff_lead_seconds=evaluation.kickoff_lead_seconds,
            disposition=current_recon.CurrentEventReconciliationDisposition.UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED,
            exact_fotmob_match_count=1,
            matched_fotmob_fixture_id=FIXTURE,
            direct_event_observed_at=evaluation.direct_event_observed_at,
            direct_event_age_seconds=evaluation.direct_event_age_seconds,
            direct_event_manifest_sha256=evaluation.current_manifest_sha256,
            direct_event_inventory_sha256=evaluation.current_inventory_sha256,
            direct_event_raw_sha256=evaluation.current_raw_sha256,
            fixture_reconciliation_authorized=True,
        ),
    )
    retained.canonical_sha256 = evaluation.source_current_reconciliation_sha256
    monkeypatch.setattr(
        portfolio.current_recon,
        "verify_current_event_discovery_reconciliation_bundle",
        lambda value: retained if value is retained else (_ for _ in ()).throw(AssertionError()),
    )
    return portfolio.CurrentProviderPortfolioRouterInput.from_router_decision(decision)


def test_portfolio_v3_contract_pins_router_v3_pr251_and_frozen_policy():
    identities = portfolio.validate_portfolio_optimizer_v3_contract()
    assert identities["market_router_v3_contract_sha256"] == router.EXPECTED_CONTRACT_SHA256
    assert identities["current_reconciliation_contract_sha256"] == current_recon.EXPECTED_CONTRACT_SHA256
    assert identities["portfolio_optimizer_v3_contract_sha256"] == portfolio.calculate_portfolio_optimizer_v3_contract_sha256()


def test_router_input_is_issued_from_retained_current_reconciliation(monkeypatch):
    value = _input(monkeypatch)
    assert value.fixture_id == FIXTURE
    assert value.event_id == EVENT
    assert value.competition == "Reviewed League"
    assert value.current_reconciliation_sha256 == value.router_decision.price_all_evaluation.source_current_reconciliation_sha256
    assert portfolio.verify_current_provider_portfolio_router_input(value).to_dict() == value.to_dict()


def test_target_twenty_preserves_explicit_nineteen_leg_shortfall(monkeypatch):
    source = _input(monkeypatch)
    result = portfolio.optimize_current_provider_portfolio_as_of(
        (source,),
        target_size=20,
        evaluation_time=EVALUATION + timedelta(seconds=20),
    )
    assert result.requested_target_size == 20
    assert len(result.selected_legs) == 1
    assert result.shortfall == 19
    assert result.fulfilled is False
    assert result.optimization_status is PortfolioOptimizationStatus.QUALIFIED_SET
    assert len(result.route_audits) == 1
    assert result.route_audits[0].admitted is True
    assert result.authority["sportybet_execution"] is False
    assert result.to_dict()["wager_placed"] is False


def test_no_bet_router_is_never_promoted_or_replaced(monkeypatch):
    source = _input(monkeypatch, probability=0.45)
    result = portfolio.optimize_current_provider_portfolio_as_of(
        (source,),
        target_size=1,
        evaluation_time=EVALUATION + timedelta(seconds=20),
    )
    assert result.selected_legs == ()
    assert result.reserve_legs == ()
    assert result.shortfall == 1
    assert result.optimization_status is PortfolioOptimizationStatus.NO_QUALIFIED_LEGS
    assert result.route_audits[0].admitted is False


def test_duplicate_provider_event_input_fails_closed(monkeypatch):
    source = _input(monkeypatch)
    with pytest.raises(portfolio.PortfolioOptimizerV3CurrentProviderError, match="duplicate fixture"):
        portfolio.optimize_current_provider_portfolio_as_of(
            (source, source),
            target_size=2,
            evaluation_time=EVALUATION + timedelta(seconds=20),
        )


def test_portfolio_time_stale_leg_is_audited_not_silently_selected(monkeypatch):
    source = _input(monkeypatch)
    result = portfolio.optimize_current_provider_portfolio_as_of(
        (source,),
        target_size=1,
        evaluation_time=EVALUATION + timedelta(seconds=841),
    )
    assert result.selected_legs == ()
    assert result.shortfall == 1
    assert result.route_audits[0].admitted is False
    assert "stale" in " ".join(result.route_audits[0].admission_reasons)


def test_portfolio_reconstructs_exactly(monkeypatch):
    source = _input(monkeypatch)
    result = portfolio.optimize_current_provider_portfolio_as_of(
        (source,), target_size=1, evaluation_time=EVALUATION + timedelta(seconds=20)
    )
    rebuilt = portfolio.verify_current_provider_portfolio_optimization(result)
    assert rebuilt.canonical_sha256 == result.canonical_sha256
