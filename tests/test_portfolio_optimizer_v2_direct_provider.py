from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from domain import market_router_v2_direct_provider as router_v2
from domain import portfolio_optimizer_v2_direct_provider as portfolio
from domain import sportybet_fotmob_full_utc_reconciliation as reconciliation
from domain import sportybet_fotmob_full_utc_reconciliation_receipt as receipt
from domain._portfolio_optimizer_v2_direct_provider_contracts import (
    EXPECTED_CONTRACT_SHA256,
    LEGACY_ACCUMULATOR_OPTIMIZER_V2_CONTRACT_SHA256,
    MARKET_ROUTER_V2_CONTRACT_SHA256,
    NEXT_BOUNDARY,
    PortfolioOptimizationStatus,
    calculate_portfolio_optimizer_v2_contract_sha256,
    validate_portfolio_optimizer_v2_contract,
)
from domain.markets import MarketId, OutcomeId
from tests import test_market_router_v2_direct_provider as router_helpers
from tests import test_price_all_v2_direct_provider as price_helpers
from tests._accumulator_optimizer_helpers import source_bundle
from tests._market_router_helpers import phase6_variant

OBSERVED = price_helpers.OBSERVED


def _rows_for(
    market: MarketId,
    outcome: OutcomeId,
) -> tuple[tuple[OutcomeId, float], ...]:
    if market is MarketId.MATCH_RESULT:
        return (
            (OutcomeId.HOME, 2.0),
            (OutcomeId.DRAW, 4.0),
            (OutcomeId.AWAY, 4.0),
        )
    if market is MarketId.BTTS:
        return ((OutcomeId.YES, 2.0), (OutcomeId.NO, 2.0))
    if market is MarketId.DRAW_NO_BET:
        return ((outcome, 2.0),)
    raise AssertionError(f"unsupported portfolio test market: {market}")


def _probabilities_for(market: MarketId) -> tuple[float, ...]:
    if market is MarketId.MATCH_RESULT:
        return (0.60, 0.22, 0.18)
    if market is MarketId.BTTS:
        return (0.60, 0.40)
    if market is MarketId.DRAW_NO_BET:
        return (0.55, 0.20, 0.25)
    raise AssertionError(f"unsupported portfolio test market: {market}")


def _fake_reconciliation(
    *,
    fixture_id: str,
    event_id: str,
    home: str,
    away: str,
    competition: str,
    kickoff,
):
    return SimpleNamespace(
        disposition=(
            reconciliation.FullUtcReconciliationDisposition.UNIQUE_EXACT_FULL_UTC_MATCH_RECONCILED
        ),
        fixture_reconciliation_authorized=True,
        matched_fixture=SimpleNamespace(
            source_fixture_identifier=fixture_id,
            home_team=home,
            away_team=away,
            competition=competition,
        ),
        sportybet_event_id=event_id,
        sportybet_kickoff_utc=kickoff,
    )


def _install_receipt_verifier(monkeypatch, registry):
    def _verify(directory, *, source_bundle, repository_root):
        return registry[str(Path(directory))]

    monkeypatch.setattr(
        receipt,
        "verify_reconciliation_receipt_directory",
        _verify,
    )


def _router_input(
    monkeypatch,
    tmp_path,
    registry,
    index: int,
    *,
    home: str | None = None,
    away: str | None = None,
    competition: str | None = None,
    market: MarketId = MarketId.MATCH_RESULT,
    outcome: OutcomeId | None = None,
    probabilities: tuple[float, ...] | None = None,
    kickoff=None,
    max_quote_age_seconds: int = 900,
    router_evaluation_offset_seconds: int = 20,
):
    fixture_id = str(8000 + index)
    event_id = f"sr:match:{9000 + index}"
    home = home or f"Home {index}"
    away = away or f"Away {index}"
    competition = competition or f"Competition {index}"
    outcome = outcome or (
        OutcomeId.YES if market is MarketId.BTTS else OutcomeId.HOME
    )
    probabilities = probabilities or _probabilities_for(market)
    kickoff = kickoff or (OBSERVED + timedelta(hours=2))

    monkeypatch.setattr(price_helpers, "EVENT", event_id)
    monkeypatch.setattr(price_helpers, "FIXTURE", fixture_id)

    candidate = phase6_variant(
        market,
        outcome,
        probabilities=probabilities,
        fixture_id=fixture_id,
        event_id=event_id,
    )
    evaluation, actual_kickoff = router_helpers._evaluation(
        monkeypatch,
        tmp_path / f"direct-source-{index}",
        candidates=[candidate],
        market=market,
        rows=_rows_for(market, outcome),
        kickoff=kickoff,
        max_quote_age_seconds=max_quote_age_seconds,
    )
    decision = router_v2.route_price_all_v2_direct_provider_evaluation(
        evaluation,
        fixture_state=router_helpers._fixture_state(
            actual_kickoff,
            fixture_id=fixture_id,
        ),
        evaluation_time=(
            OBSERVED + timedelta(seconds=router_evaluation_offset_seconds)
        ),
    )
    receipt_directory = tmp_path / f"receipt-{fixture_id}"
    registry[str(receipt_directory)] = _fake_reconciliation(
        fixture_id=fixture_id,
        event_id=event_id,
        home=home,
        away=away,
        competition=competition,
        kickoff=actual_kickoff,
    )
    value = portfolio.DirectProviderPortfolioRouterInput.from_source_replayed_receipt(
        router_decision=decision,
        receipt_directory=receipt_directory,
        source_bundle=source_bundle(),
        repository_root=tmp_path,
    )
    return value, decision


def test_portfolio_v2_contract_pins_router_v2_and_legacy_optimizer_policy():
    identities = validate_portfolio_optimizer_v2_contract()
    assert identities["market_router_v2_contract_sha256"] == (
        "071d1246ee285634af5598b66872fb27c683f2d13ab14dc25b31de90b72195de"
    )
    assert identities["legacy_accumulator_optimizer_v2_contract_sha256"] == (
        "de6578c1a21370a1859901a73e4d3993d1544a66cb0f09384a45a8233a5ce253"
    )
    assert MARKET_ROUTER_V2_CONTRACT_SHA256 == (
        identities["market_router_v2_contract_sha256"]
    )
    assert LEGACY_ACCUMULATOR_OPTIMIZER_V2_CONTRACT_SHA256 == (
        identities["legacy_accumulator_optimizer_v2_contract_sha256"]
    )
    assert calculate_portfolio_optimizer_v2_contract_sha256() == (
        EXPECTED_CONTRACT_SHA256
    )


def test_selected_router_v2_decision_becomes_source_bound_portfolio_leg(
    monkeypatch, tmp_path
):
    registry = {}
    _install_receipt_verifier(monkeypatch, registry)
    router_input, decision = _router_input(
        monkeypatch,
        tmp_path,
        registry,
        1,
    )
    assert decision.decision_status.value == "SELECTED"

    result = portfolio.optimize_direct_provider_portfolio(
        [router_input],
        target_size=1,
        evaluation_time=OBSERVED + timedelta(seconds=30),
    )

    assert result.optimization_status is PortfolioOptimizationStatus.QUALIFIED_SET
    assert result.shortfall == 0
    assert len(result.selected_legs) == 1
    leg = result.selected_legs[0]
    selected = decision.selected_opportunity
    assert selected is not None
    assert leg.router_decision_sha256 == decision.canonical_sha256
    assert leg.quote_identity_sha256 == selected.quote_identity_sha256
    assert leg.provider_market_id == selected.provider_market_id
    assert leg.provider_outcome_id == selected.provider_outcome_id
    assert leg.provider_specifier == selected.provider_specifier
    assert leg.source_quote_source_sha256 == decision.source_quote_source_sha256
    assert leg.source_bundle_sha256 == decision.source_bundle_sha256
    assert leg.source_raw_sha256 == selected.source_raw_sha256
    assert leg.reviewed_mapping_sha256 == selected.reviewed_mapping_sha256
    assert leg.fixture_reconciliation_sha256 == (
        selected.fixture_reconciliation_sha256
    )
    assert leg.portfolio_quote_age_seconds == pytest.approx(30.0)
    assert leg.router_quote_age_seconds == pytest.approx(20.0)
    assert leg.robust_net_expected_value == pytest.approx(0.20)
    assert leg.survival_probability_floor == pytest.approx(0.60)
    assert result.authority["portfolio_optimization"] is True
    assert result.authority["final_cross_fixture_selection"] is True
    assert result.authority["market_routing"] is False
    assert result.authority["accumulator_slip_construction"] is False
    assert result.authority["sportybet_execution"] is False
    assert result.authority["bet"] is False
    assert result.next_boundary == NEXT_BOUNDARY
    assert result.to_dict()["wager_placed"] is False


def test_portfolio_rechecks_staleness_after_router_selected(monkeypatch, tmp_path):
    registry = {}
    _install_receipt_verifier(monkeypatch, registry)
    router_input, decision = _router_input(
        monkeypatch,
        tmp_path,
        registry,
        2,
    )
    assert decision.decision_status.value == "SELECTED"

    result = portfolio.optimize_direct_provider_portfolio(
        [router_input],
        target_size=1,
        evaluation_time=OBSERVED + timedelta(seconds=901),
    )
    assert result.optimization_status is (
        PortfolioOptimizationStatus.NO_QUALIFIED_LEGS
    )
    assert result.selected_legs == ()
    assert result.shortfall == 1
    audit = result.route_audits[0]
    assert audit.portfolio_admitted is False
    assert "maximum quote age" in " ".join(audit.portfolio_admission_reasons)


def test_portfolio_rechecks_kickoff_lead_after_router_selected(
    monkeypatch, tmp_path
):
    registry = {}
    _install_receipt_verifier(monkeypatch, registry)
    kickoff = OBSERVED + timedelta(seconds=200)
    router_input, decision = _router_input(
        monkeypatch,
        tmp_path,
        registry,
        3,
        kickoff=kickoff,
    )
    assert decision.route_source_freshness_passed is True

    result = portfolio.optimize_direct_provider_portfolio(
        [router_input],
        target_size=1,
        evaluation_time=OBSERVED + timedelta(seconds=80),
    )
    assert result.selected_legs == ()
    assert result.shortfall == 1
    audit = result.route_audits[0]
    assert audit.portfolio_kickoff_lead_seconds == pytest.approx(120.0)
    assert "too close to kickoff" in " ".join(
        audit.portfolio_admission_reasons
    )


def test_tighter_price_all_freshness_cannot_be_weakened_at_portfolio_time(
    monkeypatch, tmp_path
):
    registry = {}
    _install_receipt_verifier(monkeypatch, registry)
    router_input, decision = _router_input(
        monkeypatch,
        tmp_path,
        registry,
        4,
        max_quote_age_seconds=30,
    )
    assert decision.max_quote_age_seconds == 30
    assert decision.route_source_freshness_passed is True

    result = portfolio.optimize_direct_provider_portfolio(
        [router_input],
        target_size=1,
        evaluation_time=OBSERVED + timedelta(seconds=31),
    )
    assert result.selected_legs == ()
    assert "maximum quote age" in " ".join(
        result.route_audits[0].portfolio_admission_reasons
    )


def test_router_no_bet_is_never_overridden_by_portfolio(monkeypatch, tmp_path):
    registry = {}
    _install_receipt_verifier(monkeypatch, registry)
    router_input, decision = _router_input(
        monkeypatch,
        tmp_path,
        registry,
        5,
        probabilities=(0.50, 0.25, 0.25),
    )
    assert decision.decision_status.value == "NO_BET"

    result = portfolio.optimize_direct_provider_portfolio(
        [router_input],
        target_size=1,
        evaluation_time=OBSERVED + timedelta(seconds=30),
    )
    assert result.selected_legs == ()
    assert result.shortfall == 1
    audit = result.route_audits[0]
    assert audit.router_decision_status == "NO_BET"
    assert audit.portfolio_admitted is False
    assert audit.portfolio_admission_reasons == decision.decision_reasons


def test_team_exposure_cap_creates_valid_shortfall_without_padding(
    monkeypatch, tmp_path
):
    registry = {}
    _install_receipt_verifier(monkeypatch, registry)
    first, _ = _router_input(
        monkeypatch,
        tmp_path,
        registry,
        6,
        home="Shared FC",
        away="Away A",
        competition="Competition A",
        market=MarketId.MATCH_RESULT,
    )
    second, _ = _router_input(
        monkeypatch,
        tmp_path,
        registry,
        7,
        home="Shared FC",
        away="Away B",
        competition="Competition B",
        market=MarketId.BTTS,
    )
    third, _ = _router_input(
        monkeypatch,
        tmp_path,
        registry,
        8,
        home="Home C",
        away="Away C",
        competition="Competition C",
        market=MarketId.DRAW_NO_BET,
    )

    result = portfolio.optimize_direct_provider_portfolio(
        [first, second, third],
        target_size=3,
        evaluation_time=OBSERVED + timedelta(seconds=30),
    )
    assert len(result.selected_legs) == 2
    assert result.shortfall == 1
    selected_teams = [
        name
        for leg in result.selected_legs
        for name in (leg.home_team, leg.away_team)
    ]
    assert selected_teams.count("Shared FC") == 1
    assert len(result.reserve_legs) == 1
    assert any(
        reason == "TEAM_EXPOSURE_CAP:Shared FC"
        for reason in result.reserve_legs[0].reserve_reasons
    )


def test_dnb_survival_floor_uses_non_negative_settlement_mass(
    monkeypatch, tmp_path
):
    registry = {}
    _install_receipt_verifier(monkeypatch, registry)
    router_input, decision = _router_input(
        monkeypatch,
        tmp_path,
        registry,
        9,
        market=MarketId.DRAW_NO_BET,
    )
    assert decision.decision_status.value == "SELECTED"
    assert decision.selected_opportunity.robust_edge is None

    result = portfolio.optimize_direct_provider_portfolio(
        [router_input],
        target_size=1,
        evaluation_time=OBSERVED + timedelta(seconds=30),
    )
    leg = result.selected_legs[0]
    assert leg.robust_net_expected_value == pytest.approx(0.30)
    assert leg.robust_edge is None
    assert leg.survival_probability_floor == pytest.approx(0.75)


def test_input_order_does_not_change_portfolio_identity(monkeypatch, tmp_path):
    registry = {}
    _install_receipt_verifier(monkeypatch, registry)
    first, _ = _router_input(
        monkeypatch,
        tmp_path,
        registry,
        10,
        competition="Competition X",
    )
    second, _ = _router_input(
        monkeypatch,
        tmp_path,
        registry,
        11,
        competition="Competition Y",
        market=MarketId.BTTS,
    )
    now = OBSERVED + timedelta(seconds=30)
    left = portfolio.optimize_direct_provider_portfolio(
        [first, second],
        target_size=2,
        evaluation_time=now,
    )
    right = portfolio.optimize_direct_provider_portfolio(
        [second, first],
        target_size=2,
        evaluation_time=now,
    )
    assert left.canonical_sha256 == right.canonical_sha256
    assert tuple(item.leg_id for item in left.selected_legs) == tuple(
        item.leg_id for item in right.selected_legs
    )


def test_builder_only_and_exact_reconstruction_reject_public_tamper(
    monkeypatch, tmp_path
):
    registry = {}
    _install_receipt_verifier(monkeypatch, registry)
    with pytest.raises(portfolio.PortfolioOptimizerV2DirectProviderError):
        portfolio.DirectProviderPortfolioRouterInput()
    with pytest.raises(portfolio.PortfolioOptimizerV2DirectProviderError):
        portfolio.DirectProviderPortfolioOptimization()

    router_input, _decision = _router_input(
        monkeypatch,
        tmp_path,
        registry,
        12,
    )
    result = portfolio.optimize_direct_provider_portfolio(
        [router_input],
        target_size=1,
        evaluation_time=OBSERVED + timedelta(seconds=30),
    )
    verified = portfolio.verify_direct_provider_portfolio_optimization(result)
    assert verified.canonical_sha256 == result.canonical_sha256

    object.__setattr__(result, "shortfall", 7)
    with pytest.raises(
        portfolio.PortfolioOptimizerV2DirectProviderError,
        match="differs from exact source reconstruction",
    ):
        portfolio.verify_direct_provider_portfolio_optimization(result)


def test_duplicate_fixture_input_fails_closed(monkeypatch, tmp_path):
    registry = {}
    _install_receipt_verifier(monkeypatch, registry)
    router_input, _ = _router_input(
        monkeypatch,
        tmp_path,
        registry,
        13,
    )
    with pytest.raises(
        portfolio.PortfolioOptimizerV2DirectProviderError,
        match="duplicate fixture inputs",
    ):
        portfolio.optimize_direct_provider_portfolio(
            [router_input, router_input],
            target_size=2,
            evaluation_time=OBSERVED + timedelta(seconds=30),
        )


def test_portfolio_evaluation_cannot_predate_router_decision(
    monkeypatch, tmp_path
):
    registry = {}
    _install_receipt_verifier(monkeypatch, registry)
    router_input, _ = _router_input(
        monkeypatch,
        tmp_path,
        registry,
        14,
        router_evaluation_offset_seconds=20,
    )
    with pytest.raises(
        portfolio.PortfolioOptimizerV2DirectProviderError,
        match="predates a Router v2 decision",
    ):
        portfolio.optimize_direct_provider_portfolio(
            [router_input],
            target_size=1,
            evaluation_time=OBSERVED + timedelta(seconds=19),
        )


def test_tampered_router_decision_is_rejected_before_portfolio_input_issuance(
    monkeypatch, tmp_path
):
    registry = {}
    _install_receipt_verifier(monkeypatch, registry)
    router_input, decision = _router_input(
        monkeypatch,
        tmp_path,
        registry,
        15,
    )
    object.__setattr__(decision, "source_bundle_sha256", "0" * 64)
    with pytest.raises(
        portfolio.PortfolioOptimizerV2DirectProviderError,
        match="Router v2 decision reconstruction failed",
    ):
        portfolio.DirectProviderPortfolioRouterInput.from_source_replayed_receipt(
            router_decision=decision,
            receipt_directory=router_input._receipt_directory,
            source_bundle=router_input._source_bundle,
            repository_root=router_input._repository_root,
        )
