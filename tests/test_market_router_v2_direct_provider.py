from __future__ import annotations

import dataclasses
from datetime import timedelta

import pytest

from domain import market_router_v2_direct_provider as router_v2
from domain import price_all_v2_direct_provider as price_v2
from domain._market_router_contracts import (
    ModelAgreementStatus,
    OpportunityEligibility,
    RouterDecisionStatus,
)
from domain._market_router_v2_contracts import (
    EXPECTED_CONTRACT_SHA256,
    LEGACY_MARKET_ROUTER_V1_CONTRACT_SHA256,
    NEXT_BOUNDARY,
    PRICE_ALL_V2_CONTRACT_SHA256,
    calculate_market_router_v2_contract_sha256,
    validate_market_router_v2_contract,
)
from domain.fixture_intelligence import IntelligenceFactStatus, build_snapshot
from domain.fixture_state_v2 import build_fixture_state_v2_snapshot
from domain.markets import MarketId, OutcomeId
from tests._market_router_helpers import _CONTEXT_BINDINGS, _fact, phase6_variant
from tests.test_price_all_v2_direct_provider import (
    EVENT,
    FIXTURE,
    OBSERVED,
    _quote_source,
)


def _fixture_state(
    kickoff,
    *,
    fixture_id: str = FIXTURE,
    missing_field: str | None = None,
    blocked_field: str | None = None,
):
    facts = []
    for index, (category, field, value) in enumerate(_CONTEXT_BINDINGS):
        if field == missing_field:
            continue
        status = (
            IntelligenceFactStatus.STALE
            if field == blocked_field
            else IntelligenceFactStatus.SUPPORTED
        )
        facts.append(
            _fact(category, field, value, status=status, marker=str(index + 1))
        )
    intelligence = build_snapshot(
        fixture_id,
        kickoff,
        OBSERVED,
        facts,
    )
    return build_fixture_state_v2_snapshot(intelligence)


def _evaluation(
    monkeypatch,
    tmp_path,
    *,
    candidates,
    market: MarketId = MarketId.MATCH_RESULT,
    rows=((OutcomeId.HOME, 2.0), (OutcomeId.DRAW, 4.0), (OutcomeId.AWAY, 4.0)),
    line: float | None = None,
    kickoff=None,
    max_quote_age_seconds: int = 900,
    minimum_lead_seconds: int = 120,
):
    kickoff = kickoff or (OBSERVED + timedelta(hours=2))
    source, _bundle = _quote_source(
        monkeypatch,
        tmp_path,
        market=market,
        rows=tuple(rows),
        line=line,
        kickoff=kickoff,
    )
    evaluation = price_v2.price_all_direct_provider_candidates(
        candidates,
        source,
        evaluation_time=OBSERVED + timedelta(seconds=10),
        max_quote_age_seconds=max_quote_age_seconds,
        minimum_lead_seconds=minimum_lead_seconds,
    )
    return evaluation, kickoff


def test_router_v2_contract_pins_price_all_v2_and_legacy_router_v1():
    identities = validate_market_router_v2_contract()
    assert identities["price_all_v2_contract_sha256"] == (
        "b5e3c063ac8b4e9fc1521cabbfe1da873a67b70efc67bc08d8ada61f2024e599"
    )
    assert identities["legacy_market_router_v1_contract_sha256"] == (
        "0e4486527b060109852ab56dd76774b2d150cf8326875e44537a3bce2dc656bf"
    )
    assert PRICE_ALL_V2_CONTRACT_SHA256 == price_v2.EXPECTED_CONTRACT_SHA256
    assert LEGACY_MARKET_ROUTER_V1_CONTRACT_SHA256 == identities[
        "legacy_market_router_v1_contract_sha256"
    ]
    assert calculate_market_router_v2_contract_sha256() == EXPECTED_CONTRACT_SHA256


def test_routes_verified_current_direct_provider_value_and_preserves_provenance(
    monkeypatch, tmp_path
):
    candidate = phase6_variant(
        probabilities=(0.60, 0.22, 0.18),
        fixture_id=FIXTURE,
        event_id=EVENT,
    )
    evaluation, kickoff = _evaluation(
        monkeypatch,
        tmp_path,
        candidates=[candidate],
    )
    decision = router_v2.route_price_all_v2_direct_provider_evaluation(
        evaluation,
        fixture_state=_fixture_state(kickoff),
        evaluation_time=OBSERVED + timedelta(seconds=20),
    )
    assert decision.decision_status is RouterDecisionStatus.SELECTED
    assert decision.selected_opportunity.market_id is MarketId.MATCH_RESULT
    assert decision.selected_opportunity.outcome_id is OutcomeId.HOME
    assert decision.selected_opportunity.decimal_odds == pytest.approx(2.0)
    assert decision.selected_opportunity.robust_net_expected_value == pytest.approx(0.20)
    assert decision.selected_opportunity.fair_probability == pytest.approx(0.5)
    assert decision.selected_opportunity.robust_edge == pytest.approx(0.10)
    assert decision.router_quote_age_seconds == pytest.approx(20.0)
    assert decision.route_source_freshness_passed is True
    assert decision.price_all_v2_evaluation_sha256 == evaluation.canonical_sha256
    assert decision.source_quote_source_sha256 == evaluation.source_quote_source_sha256
    assert decision.source_bundle_sha256 == evaluation.source_bundle_sha256
    assert decision.authority["market_routing"] is True
    assert decision.authority["verified_direct_provider_value_consumption"] is True
    assert decision.authority["portfolio_optimization"] is False
    assert decision.authority["sportybet_execution"] is False
    assert decision.authority["bet"] is False
    assert decision.next_boundary == NEXT_BOUNDARY
    assert decision.to_dict()["wager_placed"] is False


def test_router_rechecks_staleness_after_price_all_priced_the_quote(monkeypatch, tmp_path):
    candidate = phase6_variant(
        probabilities=(0.60, 0.22, 0.18), fixture_id=FIXTURE, event_id=EVENT
    )
    evaluation, kickoff = _evaluation(monkeypatch, tmp_path, candidates=[candidate])
    assert evaluation.results[0].disposition is price_v2.DirectProviderPriceDisposition.PRICED
    decision = router_v2.route_price_all_v2_direct_provider_evaluation(
        evaluation,
        fixture_state=_fixture_state(kickoff),
        evaluation_time=OBSERVED + timedelta(seconds=901),
    )
    assert decision.decision_status is RouterDecisionStatus.NO_BET
    assert decision.route_source_freshness_passed is False
    assert "maximum quote age" in " ".join(decision.route_source_freshness_reasons)
    assert decision.selected_opportunity is None
    assert decision.strongest_counterfactual is not None
    assert decision.strongest_counterfactual.eligibility is OpportunityEligibility.REJECTED


def test_router_rechecks_kickoff_lead_after_price_all_priced(monkeypatch, tmp_path):
    kickoff = OBSERVED + timedelta(seconds=200)
    candidate = phase6_variant(
        probabilities=(0.60, 0.22, 0.18), fixture_id=FIXTURE, event_id=EVENT
    )
    evaluation, _ = _evaluation(
        monkeypatch,
        tmp_path,
        candidates=[candidate],
        kickoff=kickoff,
    )
    assert evaluation.results[0].disposition is price_v2.DirectProviderPriceDisposition.PRICED
    decision = router_v2.route_price_all_v2_direct_provider_evaluation(
        evaluation,
        fixture_state=_fixture_state(kickoff),
        evaluation_time=OBSERVED + timedelta(seconds=80),
    )
    assert decision.router_kickoff_lead_seconds == pytest.approx(120.0)
    assert decision.route_source_freshness_passed is False
    assert decision.decision_status is RouterDecisionStatus.NO_BET
    assert "too close to kickoff" in " ".join(decision.route_source_freshness_reasons)


def test_tightened_price_all_freshness_policy_is_not_weakened_by_router(monkeypatch, tmp_path):
    candidate = phase6_variant(
        probabilities=(0.60, 0.22, 0.18), fixture_id=FIXTURE, event_id=EVENT
    )
    evaluation, kickoff = _evaluation(
        monkeypatch,
        tmp_path,
        candidates=[candidate],
        max_quote_age_seconds=30,
    )
    decision = router_v2.route_price_all_v2_direct_provider_evaluation(
        evaluation,
        fixture_state=_fixture_state(kickoff),
        evaluation_time=OBSERVED + timedelta(seconds=31),
    )
    assert decision.max_quote_age_seconds == 30
    assert decision.route_source_freshness_passed is False
    assert decision.decision_status is RouterDecisionStatus.NO_BET


def test_multi_model_variants_share_exact_direct_quote_and_use_lower_envelope(
    monkeypatch, tmp_path
):
    first = phase6_variant(
        probabilities=(0.64, 0.20, 0.16),
        fixture_id=FIXTURE,
        event_id=EVENT,
        model_id="POISSON_GLM_SCORE_V1",
    )
    second = phase6_variant(
        probabilities=(0.58, 0.24, 0.18),
        fixture_id=FIXTURE,
        event_id=EVENT,
        model_id="DIXON_COLES_SCORE_V1",
    )
    evaluation, kickoff = _evaluation(
        monkeypatch,
        tmp_path,
        candidates=[first, second],
    )
    decision = router_v2.route_price_all_v2_direct_provider_evaluation(
        evaluation,
        fixture_state=_fixture_state(kickoff),
        evaluation_time=OBSERVED + timedelta(seconds=20),
    )
    assert len(decision.opportunities) == 1
    opportunity = decision.opportunities[0]
    assert opportunity.model_agreement_status is (
        ModelAgreementStatus.MULTI_MODEL_COMPATIBLE_LOWER_ENVELOPE
    )
    assert len(opportunity.variants) == 2
    assert opportunity.robust_net_expected_value == pytest.approx(0.16)
    assert opportunity.best_net_expected_value == pytest.approx(0.28)
    assert opportunity.ev_spread == pytest.approx(0.12)
    assert opportunity.calibrated_event_probability_floor == pytest.approx(0.58)
    assert opportunity.fair_probability == pytest.approx(0.5)
    assert opportunity.robust_edge == pytest.approx(0.08)


def test_unpriced_direct_provider_candidate_remains_auditable_and_cannot_route(
    monkeypatch, tmp_path
):
    home = phase6_variant(
        probabilities=(0.60, 0.22, 0.18),
        fixture_id=FIXTURE,
        event_id=EVENT,
    )
    btts = phase6_variant(
        MarketId.BTTS,
        OutcomeId.YES,
        probabilities=(0.62, 0.38),
        fixture_id=FIXTURE,
        event_id=EVENT,
        model_id="DIXON_COLES_SCORE_V1",
    )
    evaluation, kickoff = _evaluation(
        monkeypatch,
        tmp_path,
        candidates=[btts, home],
    )
    assert {item.disposition for item in evaluation.results} == {
        price_v2.DirectProviderPriceDisposition.PRICED,
        price_v2.DirectProviderPriceDisposition.UNPRICED_NO_EXACT_QUOTE,
    }
    decision = router_v2.route_price_all_v2_direct_provider_evaluation(
        evaluation,
        fixture_state=_fixture_state(kickoff),
        evaluation_time=OBSERVED + timedelta(seconds=20),
    )
    assert len(decision.opportunities) == 2
    assert decision.decision_status is RouterDecisionStatus.SELECTED
    assert decision.selected_opportunity.market_id is MarketId.MATCH_RESULT
    rejected = next(item for item in decision.opportunities if item.market_id is MarketId.BTTS)
    assert rejected.eligibility is OpportunityEligibility.REJECTED
    assert "UNPRICED_NO_EXACT_QUOTE" in " ".join(rejected.rejection_reasons)


def test_dnb_routes_on_direct_provider_settlement_ev_without_fake_fair_edge(
    monkeypatch, tmp_path
):
    candidate = phase6_variant(
        MarketId.DRAW_NO_BET,
        OutcomeId.HOME,
        probabilities=(0.55, 0.20, 0.25),
        fixture_id=FIXTURE,
        event_id=EVENT,
    )
    evaluation, kickoff = _evaluation(
        monkeypatch,
        tmp_path,
        candidates=[candidate],
        market=MarketId.DRAW_NO_BET,
        rows=((OutcomeId.HOME, 2.0),),
    )
    decision = router_v2.route_price_all_v2_direct_provider_evaluation(
        evaluation,
        fixture_state=_fixture_state(kickoff),
        evaluation_time=OBSERVED + timedelta(seconds=20),
    )
    opportunity = decision.opportunities[0]
    assert opportunity.robust_net_expected_value == pytest.approx(0.30)
    assert opportunity.fair_probability is None
    assert opportunity.robust_edge is None
    assert opportunity.eligibility is OpportunityEligibility.ELIGIBLE
    assert decision.decision_status is RouterDecisionStatus.SELECTED


def test_context_failure_is_first_class_no_bet(monkeypatch, tmp_path):
    candidate = phase6_variant(
        probabilities=(0.60, 0.22, 0.18), fixture_id=FIXTURE, event_id=EVENT
    )
    evaluation, kickoff = _evaluation(monkeypatch, tmp_path, candidates=[candidate])
    decision = router_v2.route_price_all_v2_direct_provider_evaluation(
        evaluation,
        fixture_state=_fixture_state(kickoff, missing_field="home_form"),
        evaluation_time=OBSERVED + timedelta(seconds=20),
    )
    assert decision.decision_status is RouterDecisionStatus.NO_BET
    assert decision.context.passed is False
    assert decision.selected_opportunity is None
    assert "home_form" in " ".join(decision.decision_reasons)


def test_fixture_and_reconciled_kickoff_identity_mismatch_fail_closed_to_no_bet(
    monkeypatch, tmp_path
):
    candidate = phase6_variant(
        probabilities=(0.60, 0.22, 0.18), fixture_id=FIXTURE, event_id=EVENT
    )
    evaluation, kickoff = _evaluation(monkeypatch, tmp_path, candidates=[candidate])
    wrong_state = _fixture_state(kickoff + timedelta(seconds=1), fixture_id="wrong-fixture")
    decision = router_v2.route_price_all_v2_direct_provider_evaluation(
        evaluation,
        fixture_state=wrong_state,
        evaluation_time=OBSERVED + timedelta(seconds=20),
    )
    assert decision.decision_status is RouterDecisionStatus.NO_BET
    reasons = " ".join(decision.decision_reasons)
    assert "Fixture State identity" in reasons
    assert "kickoff" in reasons
    assert decision.selected_opportunity is None


def test_no_candidates_is_deterministic_no_bet_with_verified_source(monkeypatch, tmp_path):
    evaluation, kickoff = _evaluation(monkeypatch, tmp_path, candidates=[])
    state = _fixture_state(kickoff)
    first = router_v2.route_price_all_v2_direct_provider_evaluation(
        evaluation,
        fixture_state=state,
        evaluation_time=OBSERVED + timedelta(seconds=20),
    )
    second = router_v2.route_price_all_v2_direct_provider_evaluation(
        evaluation,
        fixture_state=state,
        evaluation_time=OBSERVED + timedelta(seconds=20),
    )
    assert first.decision_status is RouterDecisionStatus.NO_BET
    assert first.selected_opportunity is None
    assert first.opportunities == ()
    assert first.canonical_sha256 == second.canonical_sha256


def test_input_result_order_is_canonicalized_upstream_and_router_identity_is_stable(
    monkeypatch, tmp_path
):
    first_candidate = phase6_variant(
        probabilities=(0.64, 0.20, 0.16),
        fixture_id=FIXTURE,
        event_id=EVENT,
        model_id="POISSON_GLM_SCORE_V1",
    )
    second_candidate = phase6_variant(
        probabilities=(0.58, 0.24, 0.18),
        fixture_id=FIXTURE,
        event_id=EVENT,
        model_id="DIXON_COLES_SCORE_V1",
    )
    first_eval, kickoff = _evaluation(
        monkeypatch,
        tmp_path / "first",
        candidates=[first_candidate, second_candidate],
    )
    second_eval, _ = _evaluation(
        monkeypatch,
        tmp_path / "second",
        candidates=[second_candidate, first_candidate],
    )
    state = _fixture_state(kickoff)
    first = router_v2.route_price_all_v2_direct_provider_evaluation(
        first_eval,
        fixture_state=state,
        evaluation_time=OBSERVED + timedelta(seconds=20),
    )
    second = router_v2.route_price_all_v2_direct_provider_evaluation(
        second_eval,
        fixture_state=state,
        evaluation_time=OBSERVED + timedelta(seconds=20),
    )
    assert first.canonical_sha256 == second.canonical_sha256
    assert first.selected_opportunity_id == second.selected_opportunity_id


def test_router_evaluation_cannot_predate_price_all_evaluation(monkeypatch, tmp_path):
    candidate = phase6_variant(
        probabilities=(0.60, 0.22, 0.18), fixture_id=FIXTURE, event_id=EVENT
    )
    evaluation, kickoff = _evaluation(monkeypatch, tmp_path, candidates=[candidate])
    with pytest.raises(
        router_v2.MarketRouterV2DirectProviderError,
        match="predates Price-all v2 evaluation",
    ):
        router_v2.route_price_all_v2_direct_provider_evaluation(
            evaluation,
            fixture_state=_fixture_state(kickoff),
            evaluation_time=OBSERVED + timedelta(seconds=9),
        )


def test_decision_is_builder_only_and_reconstruction_detects_public_tamper(
    monkeypatch, tmp_path
):
    candidate = phase6_variant(
        probabilities=(0.60, 0.22, 0.18), fixture_id=FIXTURE, event_id=EVENT
    )
    evaluation, kickoff = _evaluation(monkeypatch, tmp_path, candidates=[candidate])
    decision = router_v2.route_price_all_v2_direct_provider_evaluation(
        evaluation,
        fixture_state=_fixture_state(kickoff),
        evaluation_time=OBSERVED + timedelta(seconds=20),
    )
    with pytest.raises(router_v2.MarketRouterV2DirectProviderError):
        router_v2.MarketRouterV2DirectProviderDecision()
    with pytest.raises((TypeError, router_v2.MarketRouterV2DirectProviderError)):
        dataclasses.replace(decision, status="forged")
    object.__setattr__(decision, "decision_status", RouterDecisionStatus.NO_BET)
    with pytest.raises(
        router_v2.MarketRouterV2DirectProviderError,
        match="differs from exact source reconstruction",
    ):
        router_v2.verify_market_router_v2_direct_provider_decision(decision)
