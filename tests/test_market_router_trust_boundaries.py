from __future__ import annotations

from datetime import timedelta

import pytest

from domain._market_router_contracts import RouterDecisionStatus
from domain.fixture_state_v2 import FixtureStateFieldId, FixtureStateStatus
from domain.markets import MarketId, OutcomeId
from domain.market_router import route_market_candidates
from domain.model_status import MODEL_STATUS_REGISTRY
from tests._market_router_helpers import (
    EVENT,
    NOW,
    complete_fixture_state,
    phase6_variant,
    quote_bundle,
)


def _match_quotes(tmp_path):
    return quote_bundle(tmp_path, MarketId.MATCH_RESULT, (
        (OutcomeId.HOME, 2.0), (OutcomeId.DRAW, 4.0), (OutcomeId.AWAY, 4.0)))


def test_legacy_baseline_and_ranking_inputs_are_not_router_parameters(tmp_path):
    state = complete_fixture_state()
    candidate = phase6_variant()
    quotes = _match_quotes(tmp_path)
    with pytest.raises(TypeError):
        route_market_candidates(
            [candidate], quotes.values(), fixture_state=state, evaluation_time=NOW,
            global_baseline_delta=0.99,
        )
    with pytest.raises(TypeError):
        route_market_candidates(
            [candidate], quotes.values(), fixture_state=state, evaluation_time=NOW,
            ranking_score=999.0,
        )


def test_caller_cannot_supply_robust_edge_context_risk_or_completeness(tmp_path):
    state = complete_fixture_state()
    candidate = phase6_variant()
    quotes = _match_quotes(tmp_path)
    for name, value in (
        ("robust_edge", 1.0),
        ("context_risk", 0.0),
        ("evidence_completeness", 1.0),
        ("model_agreement", 1.0),
    ):
        with pytest.raises(TypeError):
            route_market_candidates(
                [candidate], quotes.values(), fixture_state=state, evaluation_time=NOW,
                **{name: value},
            )


def test_fixture_state_identity_mismatch_is_no_bet_after_phase7_pricing(tmp_path):
    state = complete_fixture_state(fixture_id="different-fixture")
    candidate = phase6_variant(fixture_id="fx")
    quotes = _match_quotes(tmp_path)
    decision = route_market_candidates(
        [candidate], quotes.values(), fixture_state=state, evaluation_time=NOW)
    assert len(decision.price_all_results) == 1
    assert decision.decision_status is RouterDecisionStatus.NO_BET
    assert any("does not match" in reason for reason in decision.decision_reasons)


def test_mixed_fixture_ids_fail_closed_without_dropping_price_results(tmp_path):
    state = complete_fixture_state(fixture_id="fx")
    first = phase6_variant(fixture_id="fx")
    second = phase6_variant(
        MarketId.BTTS, OutcomeId.YES, probabilities=(0.60, 0.40),
        fixture_id="fx-other", model_id="DIXON_COLES_SCORE_V1")
    match_quotes = _match_quotes(tmp_path)
    btts_quotes = quote_bundle(tmp_path, MarketId.BTTS, (
        (OutcomeId.YES, 2.0), (OutcomeId.NO, 2.0)))
    decision = route_market_candidates(
        [first, second], [*match_quotes.values(), *btts_quotes.values()],
        fixture_state=state, evaluation_time=NOW)
    assert len(decision.price_all_results) == 2
    assert decision.decision_status is RouterDecisionStatus.NO_BET
    assert decision.context.passed is True
    assert all(item.context_gate_passed is True for item in decision.opportunities)
    assert all(
        "strict reviewed Fixture State context gate did not pass" not in item.rejection_reasons
        for item in decision.opportunities
    )
    assert any("mixed ATHENA fixture IDs" in reason for reason in decision.decision_reasons)


def test_mixed_sportybet_event_ids_fail_closed(tmp_path):
    state = complete_fixture_state()
    first = phase6_variant(event_id=EVENT)
    second = phase6_variant(
        MarketId.BTTS, OutcomeId.YES, probabilities=(0.60, 0.40),
        event_id="sr:match:999", model_id="DIXON_COLES_SCORE_V1")
    match_quotes = _match_quotes(tmp_path)
    decision = route_market_candidates(
        [first, second], match_quotes.values(), fixture_state=state, evaluation_time=NOW)
    assert decision.decision_status is RouterDecisionStatus.NO_BET
    assert any("mixed SportyBet event IDs" in reason for reason in decision.decision_reasons)


def test_blocked_reviewed_context_forces_no_bet_and_is_audited(tmp_path):
    state = complete_fixture_state(blocked_field="home_form")
    candidate = phase6_variant()
    quotes = _match_quotes(tmp_path)
    decision = route_market_candidates(
        [candidate], quotes.values(), fixture_state=state, evaluation_time=NOW)
    assert decision.context.passed is False
    assert FixtureStateFieldId.HOME_FORM in decision.context.blocked_field_ids
    assert decision.decision_status is RouterDecisionStatus.NO_BET


def test_missing_reviewed_context_forces_no_bet_at_frozen_full_completeness(tmp_path):
    state = complete_fixture_state(missing_field="away_elo")
    candidate = phase6_variant()
    quotes = _match_quotes(tmp_path)
    decision = route_market_candidates(
        [candidate], quotes.values(), fixture_state=state, evaluation_time=NOW)
    assert decision.context.completeness == pytest.approx(5 / 6)
    assert FixtureStateFieldId.AWAY_ELO in decision.context.missing_field_ids
    assert decision.decision_status is RouterDecisionStatus.NO_BET


def test_future_fixture_state_slots_are_reported_but_not_counted_as_available():
    state = complete_fixture_state()
    decision = route_market_candidates([], [], fixture_state=state, evaluation_time=NOW)
    assert FixtureStateFieldId.WEATHER in decision.context.excluded_future_field_ids
    assert state.field_index[FixtureStateFieldId.WEATHER].status is FixtureStateStatus.MISSING
    assert FixtureStateFieldId.WEATHER not in decision.context.available_field_ids
    assert decision.context.completeness == 1.0


def test_fixture_state_from_after_router_evaluation_time_fails_closed(tmp_path):
    state = complete_fixture_state()
    candidate = phase6_variant()
    quotes = _match_quotes(tmp_path)
    decision = route_market_candidates(
        [candidate], quotes.values(), fixture_state=state,
        evaluation_time=state.as_of - timedelta(seconds=1))
    assert decision.decision_status is RouterDecisionStatus.NO_BET
    assert any("as_of is later" in reason for reason in decision.decision_reasons)


def test_ordinary_partition_without_complete_devig_cannot_route(tmp_path):
    state = complete_fixture_state()
    candidate = phase6_variant(probabilities=(0.70, 0.20, 0.10))
    only_home = quote_bundle(tmp_path, MarketId.MATCH_RESULT, ((OutcomeId.HOME, 1.8),))
    decision = route_market_candidates(
        [candidate], only_home.values(), fixture_state=state, evaluation_time=NOW)
    assert decision.decision_status is RouterDecisionStatus.NO_BET
    assert any(
        "complete Phase 7 fair-probability" in reason
        for reason in decision.opportunities[0].rejection_reasons
    )


def test_negative_ev_cannot_win_even_with_high_probability(tmp_path):
    state = complete_fixture_state()
    candidate = phase6_variant(probabilities=(0.90, 0.05, 0.05))
    quotes = quote_bundle(tmp_path, MarketId.MATCH_RESULT, (
        (OutcomeId.HOME, 1.05), (OutcomeId.DRAW, 30.0), (OutcomeId.AWAY, 30.0)))
    decision = route_market_candidates(
        [candidate], quotes.values(), fixture_state=state, evaluation_time=NOW)
    assert decision.decision_status is RouterDecisionStatus.NO_BET
    assert decision.opportunities[0].robust_net_expected_value < 0


def test_no_global_selection_authority_mutation_occurs():
    assert all(not definition.selectable for definition in MODEL_STATUS_REGISTRY.values())
    assert all(
        definition.selection_authority.value == "NOT_AUTHORIZED"
        for definition in MODEL_STATUS_REGISTRY.values()
    )


def test_router_decision_does_not_claim_accumulator_or_bet_authority():
    state = complete_fixture_state()
    decision = route_market_candidates([], [], fixture_state=state, evaluation_time=NOW)
    payload = decision.to_dict()
    assert payload["authority_flags"]["market_routing"] is True
    assert payload["authority_flags"]["fixture_market_selection"] is True
    assert payload["authority_flags"]["accumulator"] is False
    assert payload["authority_flags"]["bet"] is False
    assert "selected" not in payload["authority_flags"]


def test_offline_runner_blocks_network_before_factory_import(monkeypatch):
    import scripts.evaluate_market_router as runner

    observed = {}

    def guarded_loader(_specification):
        import socket
        sock = socket.socket()
        try:
            with pytest.raises(runner.OfflineRouterRunnerError, match="network access is disabled"):
                sock.connect(("127.0.0.1", 9))
            observed["blocked_during_import"] = True
        finally:
            sock.close()

        def factory():
            return {
                "candidates": [],
                "quotes": [],
                "fixture_state": complete_fixture_state(),
                "evaluation_time": NOW,
            }
        return factory

    monkeypatch.setattr(runner, "_load_factory", guarded_loader)
    decision = runner.run_factory("fake.module:factory")
    assert observed == {"blocked_during_import": True}
    assert decision.decision_status is RouterDecisionStatus.NO_BET
