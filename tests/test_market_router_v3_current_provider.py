from __future__ import annotations

from datetime import timedelta

import pytest

from domain import market_router_v3_current_provider as router
from domain import price_all_v3_current_provider as price
from domain._market_router_contracts import (
    ModelAgreementStatus,
    OpportunityEligibility,
    RouterDecisionStatus,
)
from domain.fixture_intelligence import build_snapshot
from domain.fixture_state_v2 import build_fixture_state_v2_snapshot
from domain.markets import MarketId, OutcomeId
from tests._market_router_helpers import _CONTEXT_BINDINGS, _fact
from tests._price_all_helpers import phase6_candidate
from tests.test_current_direct_provider_live_quote_mapping_consumption import (
    EVALUATION,
    EVENT,
    FIXTURE,
    KICKOFF,
    _build,
    _inventory,
    _mapped_row,
    _selection,
    _source_mapping,
)


def _fixture_state(*, fixture_id: str = FIXTURE):
    facts = tuple(
        _fact(category, field, value, marker=str(index))
        for index, (category, field, value) in enumerate(_CONTEXT_BINDINGS)
    )
    return build_fixture_state_v2_snapshot(
        build_snapshot(fixture_id, KICKOFF, EVALUATION - timedelta(minutes=1), facts)
    )


def _priced_match_result(monkeypatch, probability: float = 0.60):
    selections = (
        _selection(market_id="1", market_name="Match Result", specifier=None, outcome_id="1", outcome_name="Home", odds_raw="2.00", decimal_odds=2.0),
        _selection(market_id="1", market_name="Match Result", specifier=None, outcome_id="X", outcome_name="Draw", odds_raw="4.00", decimal_odds=4.0),
        _selection(market_id="1", market_name="Match Result", specifier=None, outcome_id="2", outcome_name="Away", odds_raw="4.00", decimal_odds=4.0),
    )
    inventory = _inventory(*selections)
    mapped = tuple(
        _mapped_row(
            inventory,
            market_id="1",
            market_name="Match Result",
            specifier=None,
            outcome_id=provider_outcome,
            outcome_name=name,
            canonical_market=MarketId.MATCH_RESULT,
            canonical_outcome=outcome,
            line=None,
        )
        for provider_outcome, name, outcome in (
            ("1", "Home", OutcomeId.HOME),
            ("X", "Draw", OutcomeId.DRAW),
            ("2", "Away", OutcomeId.AWAY),
        )
    )
    source, _ = _build(
        monkeypatch,
        inventory=inventory,
        source_mapping=_source_mapping(inventory, *mapped),
    )
    candidate = phase6_candidate(
        MarketId.MATCH_RESULT,
        OutcomeId.HOME,
        None,
        (probability, (1.0 - probability) * 0.55, (1.0 - probability) * 0.45),
        fixture_id=FIXTURE,
        event_id=EVENT,
    )[0]
    evaluation = price.price_all_current_provider_candidates_as_of(
        (candidate,), source, evaluation_time=EVALUATION
    )
    return evaluation


def _rejected_opportunity(
    opportunity_id: str,
    *,
    robust_ev: float | None,
    robust_edge: float | None = None,
    event_probability: float | None = None,
) -> router.CurrentProviderRoutedOpportunity:
    return router.CurrentProviderRoutedOpportunity(
        opportunity_id=opportunity_id,
        fixture_id=FIXTURE,
        event_id=EVENT,
        market_id=MarketId.MATCH_RESULT,
        outcome_id=OutcomeId.HOME,
        line=None,
        provider_market_id=None,
        provider_outcome_id=None,
        provider_specifier=None,
        provider_market_name=None,
        provider_outcome_name=None,
        decimal_odds=None,
        quote_sha256=None,
        quote_observed_at=None,
        router_quote_age_seconds=None,
        current_inventory_sha256="a" * 64,
        source_manifest_sha256="b" * 64,
        source_raw_sha256="c" * 64,
        current_mapping_rebind_sha256="d" * 64,
        current_mapping_contract_sha256="e" * 64,
        source_current_reconciliation_sha256="f" * 64,
        source_legacy_mapping_sha256="0" * 64,
        fair_probability=None,
        variants=(),
        robust_net_expected_value=robust_ev,
        best_net_expected_value=robust_ev,
        ev_spread=0.0 if robust_ev is not None else None,
        event_probability_floor=event_probability,
        robust_edge=robust_edge,
        model_agreement_status=ModelAgreementStatus.SINGLE_MODEL_NO_DISAGREEMENT_EVIDENCE,
        context_gate_passed=False,
        route_source_freshness_passed=False,
        eligibility=OpportunityEligibility.REJECTED,
        rejection_reasons=("test rejection",),
    )


def test_router_v3_contract_pins_price_v3_and_frozen_router_v2():
    identities = router.validate_market_router_v3_contract()
    assert identities["price_all_v3_contract_sha256"] == price.EXPECTED_CONTRACT_SHA256
    assert identities["router_v2_policy_contract_sha256"] == router.ROUTER_V2_CONTRACT_SHA256
    assert identities["market_router_v3_contract_sha256"] == router.calculate_market_router_v3_contract_sha256()


def test_routes_exact_current_price_ancestry_and_preserves_native_semantics(monkeypatch):
    evaluation = _priced_match_result(monkeypatch)
    decision = router.route_price_all_v3_current_provider_as_of(
        evaluation,
        fixture_state=_fixture_state(),
        evaluation_time=EVALUATION + timedelta(seconds=10),
    )
    selected = decision.selected_opportunity
    assert decision.decision_status is RouterDecisionStatus.SELECTED
    assert selected.provider_market_id == "1"
    assert selected.provider_outcome_id == "1"
    assert selected.current_inventory_sha256 == evaluation.current_inventory_sha256
    assert selected.source_raw_sha256 == evaluation.current_raw_sha256
    assert selected.robust_net_expected_value == pytest.approx(0.20)
    assert selected.robust_edge == pytest.approx(0.10)
    assert decision.authority["portfolio_optimization"] is False
    assert decision.to_dict()["wager_placed"] is False


def test_no_bet_is_first_class_for_nonpositive_robust_value(monkeypatch):
    evaluation = _priced_match_result(monkeypatch, probability=0.45)
    decision = router.route_price_all_v3_current_provider_as_of(
        evaluation,
        fixture_state=_fixture_state(),
        evaluation_time=EVALUATION + timedelta(seconds=10),
    )
    assert decision.decision_status is RouterDecisionStatus.NO_BET
    assert decision.selected_opportunity is None
    assert decision.opportunities[0].eligibility is OpportunityEligibility.REJECTED
    assert decision.strongest_counterfactual_opportunity_id == decision.opportunities[0].opportunity_id


def test_counterfactual_rank_preserves_frozen_v2_presence_semantics():
    negative_but_measured = _rejected_opportunity(
        "measured",
        robust_ev=-0.10,
        robust_edge=-0.05,
        event_probability=0.40,
    )
    missing_value = _rejected_opportunity(
        "missing",
        robust_ev=None,
        robust_edge=None,
        event_probability=None,
    )
    ordered = sorted(
        (missing_value, negative_but_measured),
        key=router._counterfactual_rank_key,
    )
    assert ordered[0] is negative_but_measured
    assert router._strongest_counterfactual((missing_value, negative_but_measured)) == (
        negative_but_measured.opportunity_id
    )


def test_router_rechecks_current_source_freshness(monkeypatch):
    evaluation = _priced_match_result(monkeypatch)
    decision = router.route_price_all_v3_current_provider_as_of(
        evaluation,
        fixture_state=_fixture_state(),
        evaluation_time=EVALUATION + timedelta(seconds=841),
    )
    assert decision.decision_status is RouterDecisionStatus.NO_BET
    assert decision.route_source_freshness_passed is False
    assert decision.selected_opportunity is None
    assert decision.strongest_counterfactual_opportunity_id == decision.opportunities[0].opportunity_id


def test_fixture_state_identity_mismatch_fails_closed_as_no_bet(monkeypatch):
    evaluation = _priced_match_result(monkeypatch)
    decision = router.route_price_all_v3_current_provider_as_of(
        evaluation,
        fixture_state=_fixture_state(fixture_id="foreign"),
        evaluation_time=EVALUATION + timedelta(seconds=10),
    )
    assert decision.decision_status is RouterDecisionStatus.NO_BET
    assert "identity differs" in " ".join(decision.decision_reasons)
    assert decision.strongest_counterfactual_opportunity_id == decision.opportunities[0].opportunity_id


def test_live_lane_owns_clock_and_rejects_as_of_price_source(monkeypatch):
    evaluation = _priced_match_result(monkeypatch)
    monkeypatch.setattr(router, "_now_utc", lambda: EVALUATION + timedelta(seconds=10))
    with pytest.raises(router.MarketRouterV3CurrentProviderError, match="live Price-all"):
        router.route_price_all_v3_current_provider(evaluation, fixture_state=_fixture_state())


def test_live_lane_rejects_as_of_price_status_even_if_proof_label_is_live(monkeypatch):
    evaluation = _priced_match_result(monkeypatch)
    object.__setattr__(evaluation, "proof_mode", price.LIVE_CURRENT)
    monkeypatch.setattr(
        router.price_v3,
        "verify_price_all_v3_current_provider_evaluation",
        lambda value: value,
    )
    monkeypatch.setattr(router, "_now_utc", lambda: EVALUATION + timedelta(seconds=10))
    with pytest.raises(router.MarketRouterV3CurrentProviderError, match="live Price-all"):
        router.route_price_all_v3_current_provider(evaluation, fixture_state=_fixture_state())


def test_decision_reconstructs_exactly(monkeypatch):
    evaluation = _priced_match_result(monkeypatch)
    decision = router.route_price_all_v3_current_provider_as_of(
        evaluation,
        fixture_state=_fixture_state(),
        evaluation_time=EVALUATION + timedelta(seconds=10),
    )
    assert router.verify_market_router_v3_current_provider_decision(decision).canonical_sha256 == decision.canonical_sha256
