from __future__ import annotations

import pytest

from domain._market_router_context import REVIEWED_ROUTER_CONTEXT_FIELD_IDS
from domain._market_router_contracts import (
    EXPECTED_MARKET_ROUTER_CONTRACT_SHA256_BY_VERSION,
    MINIMUM_EVENT_PROBABILITY,
    ModelAgreementStatus,
    OpportunityEligibility,
    RouterDecisionStatus,
    calculate_market_router_contract_sha256,
    validate_market_router_contract,
)
from domain.markets import MarketId, OutcomeId
from domain.market_router import route_market_candidates
from tests._market_router_helpers import (
    NOW,
    complete_fixture_state,
    phase6_variant,
    quote_bundle,
)


def test_frozen_router_contract_validates_exact_upstream_dependencies():
    identities = validate_market_router_contract()
    assert identities["market_router_contract_sha256"] == EXPECTED_MARKET_ROUTER_CONTRACT_SHA256_BY_VERSION[1]
    assert identities["price_all_contract_sha256"] == "1fb0a6c891adccd76b4864a6197e55d22154176a4191f57ce92cde13501535aa"
    assert identities["fixture_state_field_registry_sha256"] == "330e81a3fd8dc88c8fee98544d7f63e9d429c43c5d32ca761da5227e34de588a"
    assert calculate_market_router_contract_sha256(
        price_all_contract_sha256="0" * 64,
        canonical_market_semantics_sha256="1" * 64,
    ) != EXPECTED_MARKET_ROUTER_CONTRACT_SHA256_BY_VERSION[1]


def test_router_prices_every_candidate_before_selection_and_preserves_audit(tmp_path):
    state = complete_fixture_state()
    home = phase6_variant(probabilities=(0.62, 0.20, 0.18))
    btts = phase6_variant(MarketId.BTTS, OutcomeId.YES, probabilities=(0.61, 0.39))
    quotes = quote_bundle(tmp_path, MarketId.MATCH_RESULT, (
        (OutcomeId.HOME, 2.0), (OutcomeId.DRAW, 4.0), (OutcomeId.AWAY, 4.0)))
    decision = route_market_candidates(
        [btts, home], quotes.values(), fixture_state=state, evaluation_time=NOW)
    assert len(decision.price_all_results) == 2
    assert {item.candidate.candidate_id for item in decision.price_all_results} == {
        home.candidate_id, btts.candidate_id}
    assert any(item.disposition.value == "UNPRICED_NO_EXACT_QUOTE" for item in decision.price_all_results)
    assert decision.decision_status is RouterDecisionStatus.SELECTED
    assert decision.selected_opportunity.market_id is MarketId.MATCH_RESULT


def test_lower_probability_with_stronger_real_value_beats_higher_probability(tmp_path):
    state = complete_fixture_state()
    high_probability = phase6_variant(probabilities=(0.75, 0.15, 0.10))
    lower_probability = phase6_variant(
        MarketId.BTTS, OutcomeId.YES, probabilities=(0.60, 0.40), model_id="DIXON_COLES_SCORE_V1")
    match_quotes = quote_bundle(tmp_path, MarketId.MATCH_RESULT, (
        (OutcomeId.HOME, 1.40), (OutcomeId.DRAW, 6.0), (OutcomeId.AWAY, 8.0)))
    btts_quotes = quote_bundle(tmp_path, MarketId.BTTS, (
        (OutcomeId.YES, 2.10), (OutcomeId.NO, 1.80)))
    decision = route_market_candidates(
        [high_probability, lower_probability],
        [*match_quotes.values(), *btts_quotes.values()],
        fixture_state=state,
        evaluation_time=NOW,
    )
    assert decision.decision_status is RouterDecisionStatus.SELECTED
    assert decision.selected_opportunity.market_id is MarketId.BTTS
    assert decision.selected_opportunity.calibrated_event_probability_floor == pytest.approx(0.60)
    assert decision.runner_up.market_id is MarketId.MATCH_RESULT


def test_multi_model_variants_group_one_opportunity_and_use_lower_envelope(tmp_path):
    state = complete_fixture_state()
    first = phase6_variant(probabilities=(0.64, 0.20, 0.16), model_id="POISSON_GLM_SCORE_V1")
    second = phase6_variant(probabilities=(0.58, 0.24, 0.18), model_id="DIXON_COLES_SCORE_V1")
    quotes = quote_bundle(tmp_path, MarketId.MATCH_RESULT, (
        (OutcomeId.HOME, 2.0), (OutcomeId.DRAW, 4.0), (OutcomeId.AWAY, 4.0)))
    decision = route_market_candidates(
        [first, second], quotes.values(), fixture_state=state, evaluation_time=NOW)
    assert len(decision.opportunities) == 1
    opportunity = decision.opportunities[0]
    assert opportunity.model_agreement_status is ModelAgreementStatus.MULTI_MODEL_COMPATIBLE_LOWER_ENVELOPE
    assert len(opportunity.variants) == 2
    assert opportunity.robust_net_expected_value == pytest.approx(0.16)
    assert opportunity.best_net_expected_value == pytest.approx(0.28)
    assert opportunity.ev_spread == pytest.approx(0.12)
    assert opportunity.calibrated_event_probability_floor == pytest.approx(0.58)
    assert opportunity.fair_probability == pytest.approx(0.5)
    assert opportunity.robust_edge == pytest.approx(0.08)


def test_single_model_never_claims_perfect_agreement(tmp_path):
    state = complete_fixture_state()
    candidate = phase6_variant()
    quotes = quote_bundle(tmp_path, MarketId.MATCH_RESULT, (
        (OutcomeId.HOME, 2.0), (OutcomeId.DRAW, 4.0), (OutcomeId.AWAY, 4.0)))
    opportunity = route_market_candidates(
        [candidate], quotes.values(), fixture_state=state, evaluation_time=NOW).opportunities[0]
    assert opportunity.model_agreement_status is ModelAgreementStatus.SINGLE_MODEL_NO_DISAGREEMENT_EVIDENCE
    assert "PERFECT" not in opportunity.model_agreement_status.value


def test_dnb_routes_on_full_settlement_ev_without_fake_edge(tmp_path):
    state = complete_fixture_state()
    candidate = phase6_variant(
        MarketId.DRAW_NO_BET, OutcomeId.HOME, probabilities=(0.55, 0.20, 0.25))
    quotes = quote_bundle(tmp_path, MarketId.DRAW_NO_BET, ((OutcomeId.HOME, 2.0),))
    decision = route_market_candidates(
        [candidate], quotes.values(), fixture_state=state, evaluation_time=NOW)
    opportunity = decision.opportunities[0]
    assert opportunity.robust_net_expected_value == pytest.approx(0.30)
    assert opportunity.calibrated_event_probability_floor is None
    assert opportunity.robust_edge is None
    assert opportunity.eligibility is OpportunityEligibility.ELIGIBLE
    assert decision.decision_status is RouterDecisionStatus.SELECTED


def test_asian_handicap_routes_on_full_split_settlement_ev_without_fake_edge(tmp_path):
    state = complete_fixture_state()
    candidate = phase6_variant(
        MarketId.ASIAN_HANDICAP, OutcomeId.HOME, -0.25,
        probabilities=(0.35, 0.15, 0.10, 0.15, 0.25))
    quotes = quote_bundle(tmp_path, MarketId.ASIAN_HANDICAP, ((OutcomeId.HOME, 2.0),), -0.25)
    decision = route_market_candidates(
        [candidate], quotes.values(), fixture_state=state, evaluation_time=NOW)
    opportunity = decision.opportunities[0]
    assert opportunity.robust_net_expected_value == pytest.approx(0.10)
    assert opportunity.robust_edge is None
    assert decision.decision_status is RouterDecisionStatus.SELECTED


def test_double_chance_keeps_edge_none_but_can_route_positive_ev(tmp_path):
    state = complete_fixture_state()
    candidate = phase6_variant(
        MarketId.DOUBLE_CHANCE, OutcomeId.HOME_OR_DRAW, probabilities=(0.70, 0.30))
    quotes = quote_bundle(tmp_path, MarketId.DOUBLE_CHANCE, (
        (OutcomeId.HOME_OR_DRAW, 1.60),
        (OutcomeId.DRAW_OR_AWAY, 1.60),
        (OutcomeId.HOME_OR_AWAY, 1.60),
    ))
    decision = route_market_candidates(
        [candidate], quotes.values(), fixture_state=state, evaluation_time=NOW)
    opportunity = decision.opportunities[0]
    assert opportunity.fair_probability is None
    assert opportunity.robust_edge is None
    assert opportunity.robust_net_expected_value == pytest.approx(0.12)
    assert decision.decision_status is RouterDecisionStatus.SELECTED


def test_probability_and_positive_value_gates_are_conservative(tmp_path):
    state = complete_fixture_state()
    below_probability = phase6_variant(probabilities=(0.54, 0.26, 0.20))
    zero_ev = phase6_variant(
        MarketId.BTTS, OutcomeId.YES, probabilities=(0.50, 0.50), model_id="DIXON_COLES_SCORE_V1")
    match_quotes = quote_bundle(tmp_path, MarketId.MATCH_RESULT, (
        (OutcomeId.HOME, 2.0), (OutcomeId.DRAW, 4.0), (OutcomeId.AWAY, 4.0)))
    btts_quotes = quote_bundle(tmp_path, MarketId.BTTS, (
        (OutcomeId.YES, 2.0), (OutcomeId.NO, 2.0)))
    decision = route_market_candidates(
        [below_probability, zero_ev],
        [*match_quotes.values(), *btts_quotes.values()],
        fixture_state=state,
        evaluation_time=NOW,
    )
    assert MINIMUM_EVENT_PROBABILITY == 0.55
    assert decision.decision_status is RouterDecisionStatus.NO_BET
    reasons = " ".join(
        reason for opportunity in decision.opportunities for reason in opportunity.rejection_reasons)
    assert "below 0.55" in reasons
    assert "strictly positive" in reasons
    assert decision.strongest_counterfactual is not None


def test_no_candidates_is_deterministic_first_class_no_bet():
    state = complete_fixture_state()
    first = route_market_candidates([], [], fixture_state=state, evaluation_time=NOW)
    second = route_market_candidates([], [], fixture_state=state, evaluation_time=NOW)
    assert first.decision_status is RouterDecisionStatus.NO_BET
    assert first.selected_opportunity is None
    assert first.canonical_sha256 == second.canonical_sha256
    assert first.price_all_results == ()


def test_input_order_does_not_change_decision_or_audit_identity(tmp_path):
    state = complete_fixture_state()
    home = phase6_variant(probabilities=(0.62, 0.20, 0.18))
    btts = phase6_variant(
        MarketId.BTTS, OutcomeId.YES, probabilities=(0.63, 0.37), model_id="DIXON_COLES_SCORE_V1")
    match_quotes = quote_bundle(tmp_path, MarketId.MATCH_RESULT, (
        (OutcomeId.HOME, 2.0), (OutcomeId.DRAW, 4.0), (OutcomeId.AWAY, 4.0)))
    btts_quotes = quote_bundle(tmp_path, MarketId.BTTS, (
        (OutcomeId.YES, 1.90), (OutcomeId.NO, 2.10)))
    quotes = [*match_quotes.values(), *btts_quotes.values()]
    first = route_market_candidates([home, btts], quotes, fixture_state=state, evaluation_time=NOW)
    second = route_market_candidates([btts, home], reversed(quotes), fixture_state=state, evaluation_time=NOW)
    assert first.canonical_sha256 == second.canonical_sha256
    assert first.selected_opportunity_id == second.selected_opportunity_id


def test_context_contract_uses_only_currently_reviewed_fields():
    assert tuple(item.value for item in REVIEWED_ROUTER_CONTEXT_FIELD_IDS) == (
        "away_elo", "away_form", "fatigue", "home_elo", "home_form", "live_data_freshness")
