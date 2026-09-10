from __future__ import annotations

import ast
import inspect
from datetime import timedelta
from pathlib import Path

import pytest

from domain import market_router_canonical_adapter as router
from domain import portfolio_optimizer as canonical
from domain import portfolio_optimizer_v3_current_provider as v3
from domain import price_all as price_all
from domain._portfolio_optimizer_v2_direct_provider_contracts import (
    FragilityStatus,
    PortfolioOptimizationStatus,
)
from domain.markets import MARKET_REGISTRY, MarketId, OutcomeId
from tests.test_current_direct_provider_live_quote_mapping_consumption import EVALUATION
from tests.test_market_router_v3_current_provider import _fixture_state
from tests.test_portfolio_optimizer_v3_current_provider import _input as v3_input


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_PATH = ROOT / "domain/portfolio_optimizer.py"


def _canonical_input(monkeypatch, probability: float = 0.60):
    source = v3_input(monkeypatch, probability=probability)
    source_decision = source.router_decision
    wrapped = price_all.PriceAllEvaluation._from_v3(
        source_decision.price_all_evaluation
    )
    decision = router.route(
        wrapped,
        fixture_state=source_decision._fixture_state,
        evaluation_time=source_decision.evaluation_time,
    )
    return source, decision


def test_contract_pins_canonical_router_v3_policy_and_run_target_bounds() -> None:
    contract = canonical.validate_portfolio_contract()
    assert (
        contract["canonical_portfolio_contract_sha256"]
        == canonical.EXPECTED_CONTRACT_SHA256
    )
    assert (
        contract["canonical_router_contract_sha256"]
        == router.EXPECTED_CONTRACT_SHA256
    )
    assert (
        contract["source_portfolio_v3_contract_sha256"]
        == v3.EXPECTED_CONTRACT_SHA256
    )
    assert canonical.MIN_TARGET_LEGS == 1
    assert canonical.MAX_TARGET_LEGS == 50
    assert canonical.SOURCE_OPTIMIZATION_POLICY_ID == v3.OPTIMIZATION_POLICY_ID
    assert canonical.AUTHORITY["portfolio_optimization"] is True
    assert canonical.AUTHORITY["market_routing"] is False
    assert canonical.AUTHORITY["target_total_odds_optimization"] is False
    assert canonical.AUTHORITY["kelly_optimization"] is False
    assert canonical.AUTHORITY["sportybet_execution"] is False
    assert canonical.AUTHORITY["staking"] is False
    assert canonical.AUTHORITY["bet"] is False


def test_public_optimizer_uses_target_legs_not_target_size_or_odds_objective() -> None:
    signature = inspect.signature(canonical.optimize_portfolio_as_of)
    assert "target_legs" in signature.parameters
    assert "target_size" not in signature.parameters
    assert "target_total_odds" not in signature.parameters
    assert "kelly" not in signature.parameters
    assert signature.parameters["target_legs"].kind is inspect.Parameter.KEYWORD_ONLY


@pytest.mark.parametrize("bad", [True, 0, 51, 1.0, "25"])
def test_target_legs_bounds_fail_closed(monkeypatch, bad) -> None:
    _source, decision = _canonical_input(monkeypatch)
    with pytest.raises(canonical.CanonicalPortfolioError, match="target_legs"):
        canonical.optimize_portfolio_as_of(
            (decision,),
            target_legs=bad,
            evaluation_time=EVALUATION + timedelta(seconds=20),
        )


def test_selected_replay_preserves_v3_selected_leg_shortfall_and_caps(monkeypatch) -> None:
    source, decision = _canonical_input(monkeypatch)
    now = EVALUATION + timedelta(seconds=20)
    expected = v3.optimize_current_provider_portfolio_as_of(
        (source,), target_size=20, evaluation_time=now
    )
    actual = canonical.optimize_portfolio_as_of(
        (decision,), target_legs=20, evaluation_time=now
    )

    assert actual.target_legs == expected.requested_target_size == 20
    assert actual.selected_count == len(expected.selected_legs) == 1
    assert actual.shortfall == expected.shortfall == 19
    assert actual.optimization_status is expected.optimization_status
    assert actual.selected_legs[0].leg_id == expected.selected_legs[0].leg_id
    assert actual.selected_legs[0].fixture_id == expected.selected_legs[0].fixture_id
    assert actual.selected_legs[0].market_id is expected.selected_legs[0].market_id
    assert actual.selected_legs[0].outcome_id is expected.selected_legs[0].outcome_id
    assert actual.selected_legs[0].line == expected.selected_legs[0].line
    assert actual.selected_legs[0].decimal_odds == expected.selected_legs[0].decimal_odds
    assert actual.selected_legs[0].robust_net_expected_value == expected.selected_legs[0].robust_net_expected_value
    assert dict(actual.exposure_summary)["caps"] == dict(expected.exposure_summary)["caps"]
    assert [item.leg.leg_id for item in actual.reserve_legs] == [
        item.leg.leg_id for item in expected.reserve_legs
    ]
    assert actual.target_total_odds_objective is False
    assert actual.kelly_objective is False
    assert actual.to_dict()["combined_decimal_odds_product_is_diagnostic_only"] is True
    assert actual.to_dict()["wager_placed"] is False


def test_no_bet_replay_preserves_zero_selection_and_full_shortfall(monkeypatch) -> None:
    source, decision = _canonical_input(monkeypatch, probability=0.45)
    now = EVALUATION + timedelta(seconds=20)
    expected = v3.optimize_current_provider_portfolio_as_of(
        (source,), target_size=4, evaluation_time=now
    )
    actual = canonical.optimize_portfolio_as_of(
        (decision,), target_legs=4, evaluation_time=now
    )
    assert decision.decision_status.value == "NO_BET"
    assert actual.selected_legs == ()
    assert actual.reserve_legs == ()
    assert actual.selected_count == 0
    assert actual.shortfall == expected.shortfall == 4
    assert actual.optimization_status is PortfolioOptimizationStatus.NO_QUALIFIED_LEGS
    assert actual.route_audits[0].admitted is False


def test_portfolio_time_stale_selected_leg_is_audited_not_promoted(monkeypatch) -> None:
    _source, decision = _canonical_input(monkeypatch)
    actual = canonical.optimize_portfolio_as_of(
        (decision,),
        target_legs=1,
        evaluation_time=EVALUATION + timedelta(seconds=841),
    )
    assert actual.selected_legs == ()
    assert actual.shortfall == 1
    assert actual.route_audits[0].admitted is False
    assert "stale" in " ".join(actual.route_audits[0].admission_reasons).lower()


def test_selected_portfolio_reconstructs_exactly_and_authority_is_immutable(monkeypatch) -> None:
    _source, decision = _canonical_input(monkeypatch)
    result = canonical.optimize_portfolio_as_of(
        (decision,),
        target_legs=1,
        evaluation_time=EVALUATION + timedelta(seconds=20),
    )
    rebuilt = canonical.verify_selected_portfolio(result)
    assert rebuilt.to_dict() == result.to_dict()
    assert rebuilt.canonical_sha256 == result.canonical_sha256
    with pytest.raises(TypeError):
        result.authority["bet"] = True  # type: ignore[index]
    with pytest.raises(canonical.CanonicalPortfolioError, match="builder-only"):
        canonical.SelectedPortfolio()


def _synthetic_leg(
    index: int,
    *,
    home: str | None = None,
    away: str | None = None,
    competition: str | None = None,
    market: MarketId | None = None,
    fragile: bool = False,
) -> canonical.PortfolioLeg:
    market_id = market or (MarketId.MATCH_RESULT if index % 2 == 0 else MarketId.BTTS)
    outcome = OutcomeId.HOME if market_id is MarketId.MATCH_RESULT else OutcomeId.YES
    return canonical.PortfolioLeg(
        leg_id=f"{index:064x}",
        canonical_router_decision_sha256="1" * 64,
        source_router_v3_decision_sha256="2" * 64,
        selected_opportunity_id=f"{index + 1000:064x}",
        prediction_identity_sha256=f"{index + 2000:064x}",
        fixture_id=f"fixture-{index}",
        event_id=f"event-{index}",
        home_team=home or f"home-{index}",
        away_team=away or f"away-{index}",
        competition=competition or f"competition-{index % 2}",
        kickoff_utc=EVALUATION + timedelta(hours=4 + index),
        market_id=market_id,
        outcome_id=outcome,
        line=None,
        market_family=MARKET_REGISTRY[market_id].family,
        provider_market_id=f"pm-{index}",
        provider_outcome_id=f"po-{index}",
        provider_specifier=None,
        provider_market_name=f"market-{index}",
        provider_outcome_name=f"outcome-{index}",
        decimal_odds=1.50,
        quote_sha256=f"{index + 3000:064x}",
        current_inventory_sha256="3" * 64,
        source_manifest_sha256="4" * 64,
        source_raw_sha256="5" * 64,
        current_mapping_rebind_sha256="6" * 64,
        current_mapping_contract_sha256="7" * 64,
        current_reconciliation_sha256="8" * 64,
        source_legacy_mapping_sha256="9" * 64,
        router_quote_age_seconds=10.0,
        portfolio_quote_age_seconds=20.0,
        portfolio_kickoff_lead_seconds=3600.0,
        robust_net_expected_value=0.10,
        robust_edge=0.05,
        event_probability_floor=0.70,
        survival_probability_floor=0.70,
        prediction_confidence=0.70,
        prediction_confidence_method="MODEL_EVENT_PROBABILITY",
        model_count=1,
        fragility_status=(
            FragilityStatus.FRAGILE_THIN_SURVIVAL
            if fragile
            else FragilityStatus.NON_FRAGILE
        ),
    )


def test_target_25_with_14_eligible_returns_14_and_shortfall_11_without_padding() -> None:
    candidates = tuple(_synthetic_leg(index) for index in range(1, 15))
    selected, reserves, caps = canonical._select_candidates(
        candidates, target_legs=25
    )
    assert len(selected) == 14
    assert 25 - len(selected) == 11
    assert reserves == ()
    assert caps["team"] == v3.MAXIMUM_TEAM_APPEARANCES
    assert caps["competition"] == 10
    assert caps["market_family"] == 13
    assert caps["fragile"] == 8
    assert {item.leg_id for item in selected} == {item.leg_id for item in candidates}


def test_binding_team_cap_is_visible_in_reserve_receipt() -> None:
    first = _synthetic_leg(1, home="shared-team", away="away-a")
    second = _synthetic_leg(2, home="shared-team", away="away-b")
    selected, reserves, _caps = canonical._select_candidates(
        (first, second), target_legs=2
    )
    assert len(selected) == 1
    assert len(reserves) == 1
    assert "TEAM_EXPOSURE_CAP:shared-team" in reserves[0].reserve_reasons
    assert canonical._binding_caps(reserves) == (
        "TEAM_EXPOSURE_CAP:shared-team",
    )


def test_canonical_portfolio_import_boundary_has_no_shadow_delivery_or_wager_dependency() -> None:
    text = CANONICAL_PATH.read_text(encoding="utf-8")
    tree = ast.parse(text)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                imports.add(f"{node.module}.{alias.name}")
    assert "domain.market_router_canonical_adapter" in imports
    assert "domain.portfolio_optimizer_v3_current_provider" in imports
    assert "domain.run_contracts" in imports
    assert not any("current_shadow" in module for module in imports)
    assert not any(
        token in module
        for module in imports
        for token in (
            "share_code",
            "sportybet_accumulator_execution",
            "bookie_automator",
            "wallet",
            "staking",
            "wager",
        )
    )


def test_selected_portfolio_labels_dependence_and_no_future_objective(monkeypatch) -> None:
    _source, decision = _canonical_input(monkeypatch)
    result = canonical.optimize_portfolio_as_of(
        (decision,),
        target_legs=1,
        evaluation_time=EVALUATION + timedelta(seconds=20),
    )
    payload = result.to_dict()
    assert payload["joint_dependence_status"] == "NO_VALIDATED_JOINT_CORRELATION_MODEL_V1"
    assert payload["exposure_summary"]["statistical_correlation_coefficients"] is None
    assert payload["target_total_odds_objective"] is False
    assert payload["kelly_objective"] is False
    assert payload["selected_count"] + payload["shortfall"] == payload["target_legs"]
