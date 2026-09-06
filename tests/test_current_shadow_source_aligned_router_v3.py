from __future__ import annotations

from datetime import datetime, timezone

import pytest

from domain import current_shadow_all_market_router as router
from domain._current_shadow_price_core import (
    AH_PREDICTION_CONFIDENCE_METHOD,
    AUTHORITY_FLAGS,
    MINIMUM_SELECTABLE_OVER_TOTAL_GOALS_LINE,
    ROUTER_POLICY_ID,
    ShadowDevigStatus,
    ShadowOpportunityEligibility,
    ShadowPriceDisposition,
    ShadowRouterDecisionStatus,
    settlement_unit_return,
)
from domain._current_shadow_price_records import (
    _issue_shadow_price_all_bundle,
    _issue_shadow_price_result,
)
from domain.markets import MarketId, OutcomeId


NOW = datetime(2026, 9, 6, 14, 0, tzinfo=timezone.utc)
FIXTURE = "FOTMOB:SOURCE-ALIGNED-V3"
EVENT = "sr:match:900001"
A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
E = "e" * 64
F = "f" * 64


def _result(
    market: MarketId,
    outcome: OutcomeId,
    *,
    token: str,
    probability: float | None,
    odds: float,
    ev: float,
    line: float | None = None,
    fair: float | None = 0.50,
    devig: ShadowDevigStatus | None = ShadowDevigStatus.PROPORTIONAL_COMPLETE_PARTITION,
    states: tuple[tuple[str, float], ...] | None = None,
):
    if states is None and probability is not None:
        states = (("WIN", probability), ("LOSS", 1.0 - probability))
    returns = () if states is None else tuple(
        (state, settlement_unit_return(state, odds)) for state, _ in states
    )
    return _issue_shadow_price_result(
        fixture_identity=FIXTURE,
        market_id=market,
        outcome_id=outcome,
        line=line,
        disposition=ShadowPriceDisposition.PRICED,
        model_probability=probability,
        decimal_odds=odds,
        implied_probability=1.0 / odds,
        fair_probability=fair,
        overround=None if fair is None else 1.05,
        devig_status=devig,
        net_expected_value=ev,
        expected_return_multiplier=1.0 + ev,
        settlement_state_probabilities=() if states is None else states,
        settlement_unit_returns=returns,
        quote_identity_sha256=(token * 64)[:64],
        provider_event_id=EVENT,
        provider_semantic_status="SUPPORTED",
        rejection_reason=None,
        probability_method="reviewed_test_probability",
        probability_input_namespace="reviewed.test",
        prc_scan_sha256=C,
        prc_assessment_sha256=A,
        sealed_prediction_sha256=A,
        history_prefix_identity=B,
        source_fixture_identity=FIXTURE,
        provider_registry_sha256=D,
        source_raw_sha256=A,
        source_manifest_sha256=B,
        source_inventory_sha256=C,
        provider_observation_sha256=E,
        fixture_reconciliation_sha256=D,
        current_mapping_rebind_sha256=E,
        bridge_bundle_sha256=F,
        score_matrix_audit=None,
        specialist_evidence=None,
    )


def _route(monkeypatch: pytest.MonkeyPatch, *results):
    bundle = _issue_shadow_price_all_bundle(
        fixture_identity=FIXTURE,
        evaluation_time=NOW,
        prc_scan_sha256=C,
        provider_registry_sha256=D,
        fixture_reconciliation_sha256=D,
        current_mapping_rebind_sha256=E,
        bridge_bundle_sha256=F,
        quote_count=len(results),
        results=tuple(results),
        authority=AUTHORITY_FLAGS,
        _context=object(),
    )
    monkeypatch.setattr(router, "verify_shadow_price_all_bundle", lambda value: value)
    return router.route_shadow_price_results(bundle)


def test_over_0_5_is_audit_only_and_over_1_5_can_select(monkeypatch: pytest.MonkeyPatch) -> None:
    over_05 = _result(
        MarketId.TOTAL_GOALS,
        OutcomeId.OVER,
        token="1",
        probability=0.94,
        odds=1.10,
        ev=0.034,
        line=0.5,
        fair=0.86,
    )
    over_15 = _result(
        MarketId.TOTAL_GOALS,
        OutcomeId.OVER,
        token="2",
        probability=0.78,
        odds=1.35,
        ev=0.053,
        line=1.5,
        fair=0.70,
    )

    decision = _route(monkeypatch, over_05, over_15)
    by_id = {row.opportunity_id: row for row in decision.opportunities}
    low = by_id[over_05.opportunity_id]

    assert MINIMUM_SELECTABLE_OVER_TOTAL_GOALS_LINE == 1.5
    assert low.eligibility is ShadowOpportunityEligibility.REJECTED
    assert any("source contract" in reason for reason in low.rejection_reasons)
    assert decision.selected_opportunity_id == over_15.opportunity_id
    assert decision.router_policy_id == ROUTER_POLICY_ID


def test_raw_probability_cannot_outrank_better_settlement_aware_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    high_probability_thin_value = _result(
        MarketId.TOTAL_GOALS,
        OutcomeId.UNDER,
        token="3",
        probability=0.95,
        odds=1.10,
        ev=0.045,
        line=5.5,
        fair=0.87,
    )
    lower_probability_better_value = _result(
        MarketId.TOTAL_GOALS,
        OutcomeId.UNDER,
        token="4",
        probability=0.82,
        odds=1.35,
        ev=0.107,
        line=3.5,
        fair=0.70,
    )

    decision = _route(monkeypatch, high_probability_thin_value, lower_probability_better_value)

    assert decision.status is ShadowRouterDecisionStatus.SELECTED
    assert decision.selected_opportunity_id == lower_probability_better_value.opportunity_id
    chosen = next(
        row for row in decision.opportunities
        if row.opportunity_id == decision.selected_opportunity_id
    )
    assert chosen.prediction_confidence == pytest.approx(0.82)
    assert chosen.robust_net_expected_value == pytest.approx(0.107)
    assert chosen.prediction_first_rank == 1


def test_confidence_floor_still_prevents_high_ev_low_quality_ah_privilege(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ah = _result(
        MarketId.ASIAN_HANDICAP,
        OutcomeId.HOME,
        token="5",
        probability=None,
        odds=3.75,
        ev=0.90,
        line=0.25,
        fair=None,
        devig=ShadowDevigStatus.NOT_IDENTIFIABLE_PUSH_OR_SPLIT_SETTLEMENT,
        states=(
            ("WIN", 0.20),
            ("HALF_WIN", 0.10),
            ("PUSH", 0.027),
            ("HALF_LOSS", 0.10),
            ("LOSS", 0.573),
        ),
    )
    scalar = _result(
        MarketId.MATCH_RESULT,
        OutcomeId.HOME,
        token="6",
        probability=0.75,
        odds=1.20,
        ev=0.10,
        fair=0.50,
    )

    decision = _route(monkeypatch, ah, scalar)
    ah_row = next(row for row in decision.opportunities if row.opportunity_id == ah.opportunity_id)

    assert ah_row.prediction_confidence == pytest.approx(0.327)
    assert ah_row.prediction_confidence_method == AH_PREDICTION_CONFIDENCE_METHOD
    assert ah_row.eligibility is ShadowOpportunityEligibility.REJECTED
    assert decision.selected_opportunity_id == scalar.opportunity_id


def test_settlement_aware_ah_can_win_when_quality_and_value_both_lead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ah = _result(
        MarketId.ASIAN_HANDICAP,
        OutcomeId.HOME,
        token="7",
        probability=None,
        odds=1.80,
        ev=0.16,
        line=-0.25,
        fair=None,
        devig=ShadowDevigStatus.NOT_IDENTIFIABLE_PUSH_OR_SPLIT_SETTLEMENT,
        states=(
            ("WIN", 0.50),
            ("HALF_WIN", 0.12),
            ("PUSH", 0.08),
            ("HALF_LOSS", 0.08),
            ("LOSS", 0.22),
        ),
    )
    scalar = _result(
        MarketId.MATCH_RESULT,
        OutcomeId.HOME,
        token="8",
        probability=0.76,
        odds=1.25,
        ev=0.05,
        fair=0.67,
    )

    decision = _route(monkeypatch, ah, scalar)

    assert decision.selected_opportunity_id == ah.opportunity_id
    assert decision.authority["production_market_router"] is False
    assert decision.authority["production_selection"] is False
    assert decision.authority["bet"] is False
    assert decision.authority["wager_placed"] is False
