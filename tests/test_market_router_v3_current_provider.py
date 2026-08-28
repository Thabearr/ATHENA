from __future__ import annotations

from datetime import timedelta

import pytest

from domain import market_router_v3_current_provider as router
from domain import price_all_v3_current_provider as price
from domain._market_router_contracts import OpportunityEligibility, RouterDecisionStatus
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


def test_fixture_state_identity_mismatch_fails_closed_as_no_bet(monkeypatch):
    evaluation = _priced_match_result(monkeypatch)
    decision = router.route_price_all_v3_current_provider_as_of(
        evaluation,
        fixture_state=_fixture_state(fixture_id="foreign"),
        evaluation_time=EVALUATION + timedelta(seconds=10),
    )
    assert decision.decision_status is RouterDecisionStatus.NO_BET
    assert "identity differs" in " ".join(decision.decision_reasons)


def test_live_lane_owns_clock_and_rejects_as_of_price_source(monkeypatch):
    evaluation = _priced_match_result(monkeypatch)
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
