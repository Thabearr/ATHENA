from __future__ import annotations

import ast
import dataclasses
from datetime import timedelta
from pathlib import Path

import pytest

from domain import market_router_canonical_adapter as canonical
from domain import market_router_v3_current_provider as v3
from domain import price_all as canonical_price
from domain._market_router_contracts import (
    ModelAgreementStatus,
    OpportunityEligibility,
    RouterDecisionStatus,
)
from domain.markets import MarketId, OutcomeId
from tests._price_all_helpers import phase6_candidate
from tests.test_current_direct_provider_live_quote_mapping_consumption import EVALUATION
from tests.test_market_router_v3_current_provider import _fixture_state, _priced_match_result

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_PATH = ROOT / "domain/market_router_canonical_adapter.py"


def _wrap(evaluation):
    return canonical_price.PriceAllEvaluation._from_v3(evaluation)


def _opportunity(
    *,
    token: str,
    market: MarketId,
    outcome: OutcomeId,
    line: float | None = None,
    ev: float = 0.10,
    confidence: float = 0.70,
    odds: float = 1.50,
    quote_age: float = 30.0,
    eligibility: OpportunityEligibility = OpportunityEligibility.ELIGIBLE,
) -> canonical.RouterOpportunity:
    return canonical.RouterOpportunity(
        opportunity_id=(token * 64)[:64],
        prediction_identity_sha256=canonical._prediction_identity_sha256(
            "fixture", market, outcome, line
        ),
        fixture_id="fixture",
        event_id="sr:match:1",
        market_id=market,
        outcome_id=outcome,
        line=line,
        provider_market_id=f"provider-market-{token}",
        provider_outcome_id=f"provider-outcome-{token}",
        provider_specifier=None,
        provider_market_name="provider market",
        provider_outcome_name="provider outcome",
        decimal_odds=odds,
        quote_sha256=(token[::-1] * 64)[:64],
        quote_observed_at=EVALUATION - timedelta(seconds=quote_age),
        router_quote_age_seconds=quote_age,
        current_inventory_sha256="1" * 64,
        source_manifest_sha256="2" * 64,
        source_raw_sha256="3" * 64,
        current_mapping_rebind_sha256="4" * 64,
        current_mapping_contract_sha256="5" * 64,
        source_current_reconciliation_sha256="6" * 64,
        source_legacy_mapping_sha256="7" * 64,
        fair_probability=0.50,
        variants=(),
        robust_net_expected_value=ev,
        best_net_expected_value=ev,
        ev_spread=0.0,
        event_probability_floor=confidence,
        robust_edge=max(0.0, confidence - 0.50),
        prediction_confidence=confidence,
        prediction_confidence_method=canonical.SCALAR_PREDICTION_CONFIDENCE_METHOD,
        model_agreement_status=ModelAgreementStatus.SINGLE_MODEL_NO_DISAGREEMENT_EVIDENCE,
        context_gate_passed=True,
        route_source_freshness_passed=True,
        source_v3_eligibility=eligibility,
        eligibility=eligibility,
        rejection_reasons=() if eligibility is OpportunityEligibility.ELIGIBLE else ("test rejection",),
    )


def test_contract_pins_canonical_price_all_and_exact_router_v3() -> None:
    contract = canonical.validate_canonical_market_router_contract()
    assert contract["canonical_market_router_contract_sha256"] == canonical.EXPECTED_CONTRACT_SHA256
    assert contract["source_router_v3_contract_sha256"] == v3.EXPECTED_CONTRACT_SHA256
    assert contract["canonical_price_all_policy_id"] == canonical_price.POLICY_ID
    assert canonical.CANONICAL_TARGET_MODULE == "domain.market_router"
    assert canonical.MAX_SELECTED_PER_FIXTURE == 1
    assert canonical.SAME_GAME_COMBINATION_AUTHORIZED is False
    assert canonical.AUTHORITY["market_routing"] is True
    assert canonical.AUTHORITY["coherence_grouping"] is True
    assert canonical.AUTHORITY["portfolio_optimization"] is False
    assert canonical.AUTHORITY["sportybet_execution"] is False
    assert canonical.AUTHORITY["bet"] is False


def test_replay_selected_case_matches_router_v3_source_decision(monkeypatch) -> None:
    evaluation = _priced_match_result(monkeypatch, probability=0.60)
    fixture_state = _fixture_state()
    expected = v3.route_price_all_v3_current_provider_as_of(
        evaluation,
        fixture_state=fixture_state,
        evaluation_time=EVALUATION + timedelta(seconds=10),
    )
    actual = canonical.route(
        _wrap(evaluation),
        fixture_state=fixture_state,
        evaluation_time=EVALUATION + timedelta(seconds=10),
    )
    assert expected.decision_status is RouterDecisionStatus.SELECTED
    assert actual.decision_status is expected.decision_status
    assert actual.selected_opportunity_id == expected.selected_opportunity_id
    assert actual.source_router_v3_selected_opportunity_id == expected.selected_opportunity_id
    assert actual.source_router_v3_decision_sha256 == expected.canonical_sha256
    selected = actual.selected_opportunity
    assert selected is not None
    assert selected.market_id is expected.selected_opportunity.market_id
    assert selected.outcome_id is expected.selected_opportunity.outcome_id
    assert selected.line == expected.selected_opportunity.line
    assert selected.robust_net_expected_value == expected.selected_opportunity.robust_net_expected_value
    assert selected.prediction_confidence == pytest.approx(0.60)
    assert selected.prediction_confidence_method == canonical.SCALAR_PREDICTION_CONFIDENCE_METHOD
    assert actual.to_dict()["wager_placed"] is False


def test_replay_no_bet_case_matches_and_source_rejection_cannot_be_upgraded(monkeypatch) -> None:
    evaluation = _priced_match_result(monkeypatch, probability=0.45)
    fixture_state = _fixture_state()
    expected = v3.route_price_all_v3_current_provider_as_of(
        evaluation,
        fixture_state=fixture_state,
        evaluation_time=EVALUATION + timedelta(seconds=10),
    )
    actual = canonical.route(
        _wrap(evaluation),
        fixture_state=fixture_state,
        evaluation_time=EVALUATION + timedelta(seconds=10),
    )
    assert expected.decision_status is RouterDecisionStatus.NO_BET
    assert actual.decision_status is RouterDecisionStatus.NO_BET
    assert actual.selected_opportunity_id is None
    assert all(
        row.source_v3_eligibility is OpportunityEligibility.REJECTED
        and row.eligibility is OpportunityEligibility.REJECTED
        for row in actual.opportunities
    )
    assert actual.strongest_counterfactual_opportunity_id is not None


def test_replay_stale_source_and_fixture_identity_mismatch_remain_no_bet(monkeypatch) -> None:
    evaluation = _priced_match_result(monkeypatch, probability=0.60)
    stale = canonical.route(
        _wrap(evaluation),
        fixture_state=_fixture_state(),
        evaluation_time=EVALUATION + timedelta(seconds=841),
    )
    assert stale.decision_status is RouterDecisionStatus.NO_BET
    assert stale.selected_opportunity_id is None
    assert all(row.route_source_freshness_passed is False for row in stale.opportunities)

    mismatch = canonical.route(
        _wrap(evaluation),
        fixture_state=_fixture_state(fixture_id="foreign"),
        evaluation_time=EVALUATION + timedelta(seconds=10),
    )
    assert mismatch.decision_status is RouterDecisionStatus.NO_BET
    assert mismatch.selected_opportunity_id is None
    assert any("identity differs" in reason for reason in mismatch.decision_reasons)


def test_decision_reconstructs_exactly_and_authority_is_immutable(monkeypatch) -> None:
    evaluation = _priced_match_result(monkeypatch, probability=0.60)
    decision = canonical.route(
        _wrap(evaluation),
        fixture_state=_fixture_state(),
        evaluation_time=EVALUATION + timedelta(seconds=10),
    )
    rebuilt = canonical.verify_router_decision(decision)
    assert rebuilt.to_dict() == decision.to_dict()
    assert rebuilt.canonical_sha256 == decision.canonical_sha256
    with pytest.raises(TypeError):
        decision.authority["bet"] = True  # type: ignore[index]
    with pytest.raises(canonical.CanonicalMarketRouterError, match="builder-only"):
        canonical.RouterDecision()


def test_comparable_confidence_semantics_are_model_derived() -> None:
    scalar, *_ = phase6_candidate(
        MarketId.MATCH_RESULT,
        OutcomeId.HOME,
        None,
        (0.61, 0.21, 0.18),
    )
    dnb, *_ = phase6_candidate(
        MarketId.DRAW_NO_BET,
        OutcomeId.HOME,
        None,
        (0.50, 0.12, 0.38),
    )
    ah, *_ = phase6_candidate(
        MarketId.ASIAN_HANDICAP,
        OutcomeId.HOME,
        -0.25,
        (0.42, 0.12, 0.08, 0.10, 0.28),
    )
    scalar_confidence, scalar_method = canonical._candidate_confidence(scalar)
    assert scalar_confidence == pytest.approx(0.61)
    assert scalar_method == canonical.SCALAR_PREDICTION_CONFIDENCE_METHOD
    dnb_confidence, dnb_method = canonical._candidate_confidence(dnb)
    assert dnb_confidence == pytest.approx(0.62)
    assert dnb_method == canonical.DNB_PREDICTION_CONFIDENCE_METHOD
    confidence, method = canonical._candidate_confidence(ah)
    assert confidence == pytest.approx(0.62)
    assert method == canonical.AH_PREDICTION_CONFIDENCE_METHOD


def test_quote_independent_tie_break_ignores_odds_age_and_quote_identity() -> None:
    match = _opportunity(
        token="a",
        market=MarketId.MATCH_RESULT,
        outcome=OutcomeId.HOME,
        ev=0.10,
        confidence=0.70,
        odds=1.20,
        quote_age=800.0,
    )
    total = _opportunity(
        token="b",
        market=MarketId.TOTAL_GOALS,
        outcome=OutcomeId.OVER,
        line=2.5,
        ev=0.10,
        confidence=0.70,
        odds=9.00,
        quote_age=1.0,
    )
    first = sorted((total, match), key=canonical._selection_rank_key)
    assert first[0].market_id is MarketId.MATCH_RESULT

    changed_match = dataclasses.replace(
        match,
        decimal_odds=8.50,
        quote_sha256="8" * 64,
        router_quote_age_seconds=2.0,
    )
    changed_total = dataclasses.replace(
        total,
        decimal_odds=1.10,
        quote_sha256="9" * 64,
        router_quote_age_seconds=899.0,
    )
    second = sorted((changed_total, changed_match), key=canonical._selection_rank_key)
    assert [row.prediction_identity_sha256 for row in second] == [
        row.prediction_identity_sha256 for row in first
    ]
    assert second[0].market_id is MarketId.MATCH_RESULT


def test_odds_floor_is_eligibility_only_not_rank_authority() -> None:
    low = _opportunity(
        token="c",
        market=MarketId.MATCH_RESULT,
        outcome=OutcomeId.HOME,
        odds=1.08,
    )
    good = dataclasses.replace(low, decimal_odds=1.09)
    assert canonical.MINIMUM_DECIMAL_ODDS == pytest.approx(1.09)
    assert canonical._selection_rank_key(good) == canonical._selection_rank_key(
        dataclasses.replace(good, decimal_odds=10.0, quote_sha256="f" * 64)
    )
    assert low.decimal_odds < canonical.MINIMUM_DECIMAL_ODDS


def test_duplicate_eligible_prediction_identity_fails_closed() -> None:
    first = _opportunity(
        token="d",
        market=MarketId.MATCH_RESULT,
        outcome=OutcomeId.HOME,
    )
    alternate_quote = dataclasses.replace(
        first,
        opportunity_id="e" * 64,
        quote_sha256="0" * 64,
        decimal_odds=2.5,
        router_quote_age_seconds=1.0,
    )
    with pytest.raises(canonical.CanonicalMarketRouterError, match="ambiguous canonical prediction identity"):
        canonical._rank_opportunities((first, alternate_quote))


def _relationships(*rows: canonical.RouterOpportunity) -> dict[str, canonical.CoherenceGroup]:
    groups = canonical._build_coherence_groups(rows, selected_opportunity_id=rows[0].opportunity_id)
    return {f"{group.relationship_id}:{group.relationship_key}": group for group in groups}


def test_explicit_overlap_coherence_groups_are_logical_and_diagnostic() -> None:
    home = _opportunity(token="1", market=MarketId.MATCH_RESULT, outcome=OutcomeId.HOME, ev=0.15)
    home_or_draw = _opportunity(token="2", market=MarketId.DOUBLE_CHANCE, outcome=OutcomeId.HOME_OR_DRAW, ev=0.12)
    home_or_over = _opportunity(token="3", market=MarketId.HOME_OR_OVER_2_5, outcome=OutcomeId.YES, ev=0.11)
    over_25 = _opportunity(token="4", market=MarketId.TOTAL_GOALS, outcome=OutcomeId.OVER, line=2.5, ev=0.10)
    win_nil = _opportunity(token="5", market=MarketId.HOME_WIN_TO_NIL, outcome=OutcomeId.YES, ev=0.09)
    btts_no = _opportunity(token="6", market=MarketId.BTTS, outcome=OutcomeId.NO, ev=0.08)
    over_15 = _opportunity(token="7", market=MarketId.TOTAL_GOALS, outcome=OutcomeId.OVER, line=1.5, ev=0.07)

    groups = _relationships(home, home_or_draw, home_or_over, over_25, win_nil, btts_no, over_15)
    assert "SHARED_REGULATION_RESULT_ATOM:RESULT:HOME" in groups
    assert "SHARED_TOTALS_OVER_2_5_ATOM:TOTALS:OVER:2.5" in groups
    assert "SHARED_BTTS_NO_ATOM:BTTS:NO" in groups
    assert "NESTED_TOTAL_GOALS_OVER:OVER" in groups

    result_group = groups["SHARED_REGULATION_RESULT_ATOM:RESULT:HOME"]
    assert result_group.winner_opportunity_id == home.opportunity_id
    assert result_group.runner_up_opportunity_id is not None
    assert result_group.selected_opportunity_id == home.opportunity_id
    assert result_group.joint_probability_supported is False
    assert result_group.selection_limit == 1
    assert {member.status for member in result_group.members} >= {
        canonical.CoherenceMemberStatus.WINNER,
        canonical.CoherenceMemberStatus.RUNNER_UP,
    }


def test_coherence_does_not_infer_unreviewed_dnb_ah_or_early_payout_relationships() -> None:
    dnb = _opportunity(token="8", market=MarketId.DRAW_NO_BET, outcome=OutcomeId.HOME)
    ah = _opportunity(token="9", market=MarketId.ASIAN_HANDICAP, outcome=OutcomeId.HOME, line=-0.25)
    either_half = _opportunity(token="a", market=MarketId.HOME_WIN_EITHER_HALF, outcome=OutcomeId.YES)
    early = _opportunity(token="b", market=MarketId.MATCH_RESULT_1UP, outcome=OutcomeId.HOME)
    assert canonical._build_coherence_groups(
        (dnb, ah, either_half, early), selected_opportunity_id=dnb.opportunity_id
    ) == ()


def test_canonical_adapter_is_one_router_boundary_not_a_fourth_formula_stack() -> None:
    text = CANONICAL_PATH.read_text(encoding="utf-8")
    tree = ast.parse(text)
    imports: set[str] = set()
    definitions: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
            imports.update(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            definitions.add(node.name)
    assert "domain.price_all" in imports
    assert "domain.market_router_v3_current_provider" in imports
    assert "domain.current_shadow_all_market_router" not in imports
    assert not any(
        token in module
        for module in imports
        for token in ("portfolio_optimizer", "share_code", "wallet", "staking", "wager")
    )
    assert "MarketCoherenceEngine" not in definitions
    assert "market_coherence_engine" not in text
    assert "route_price_all_v3_current_provider_as_of" in text
    assert "MAX_SELECTED_PER_FIXTURE = 1" in text
