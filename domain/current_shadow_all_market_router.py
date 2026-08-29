"""Research-only all-market Shadow Router (PR D).

Consumes only an exact source-replayable ``ShadowPriceAllBundle``. The Router
cannot accept caller-authored/subset price rows, so all eligible current quotes
are priced before any value selection occurs.
"""
from __future__ import annotations

from typing import Optional

from domain._current_shadow_price_core import (
    AUTHORITY_FLAGS,
    MINIMUM_EVENT_PROBABILITY,
    MINIMUM_NET_EXPECTED_VALUE,
    MINIMUM_ROBUST_EDGE,
    MINIMUM_ROBUST_NET_EXPECTED_VALUE,
    ORDINARY_PARTITIONS,
    PUSH_SPLIT_MARKETS,
    ROUTER_POLICY_ID,
    ShadowDevigStatus,
    ShadowModelAgreementStatus,
    ShadowOpportunityEligibility,
    ShadowPriceDisposition,
    ShadowPriceError,
    ShadowRouterDecisionStatus,
)
from domain._current_shadow_price_records import (
    ShadowMarketRouterDecision,
    ShadowPriceAllBundle,
    ShadowPriceResult,
    ShadowRoutedOpportunity,
    _issue_shadow_router_decision,
)
from domain.current_shadow_all_market_price_all import verify_shadow_price_all_bundle


def _event_floor(result: ShadowPriceResult) -> Optional[float]:
    return result.model_probability


def _robust_edge(result: ShadowPriceResult, event_floor: Optional[float]) -> Optional[float]:
    if event_floor is None or result.fair_probability is None:
        return None
    return event_floor - result.fair_probability


def _eligibility(result: ShadowPriceResult) -> tuple[ShadowOpportunityEligibility, tuple[str, ...]]:
    reasons: list[str] = []
    if result.disposition is not ShadowPriceDisposition.PRICED:
        return ShadowOpportunityEligibility.REJECTED, (
            result.rejection_reason or f"disposition={result.disposition.value}",
        )
    if result.net_expected_value is None:
        return ShadowOpportunityEligibility.REJECTED, ("missing net_expected_value",)

    robust_ev = result.net_expected_value
    if result.net_expected_value <= MINIMUM_NET_EXPECTED_VALUE:
        reasons.append(
            f"net_expected_value {result.net_expected_value} <= {MINIMUM_NET_EXPECTED_VALUE}"
        )
    if robust_ev <= MINIMUM_ROBUST_NET_EXPECTED_VALUE:
        reasons.append(
            f"robust_net_expected_value {robust_ev} <= {MINIMUM_ROBUST_NET_EXPECTED_VALUE}"
        )

    event_floor = _event_floor(result)
    if result.market_id not in PUSH_SPLIT_MARKETS:
        if event_floor is None:
            reasons.append("scalar-event market lacks model probability")
        elif event_floor < MINIMUM_EVENT_PROBABILITY:
            reasons.append(
                f"event probability floor {event_floor} < {MINIMUM_EVENT_PROBABILITY}"
            )

    if result.market_id in ORDINARY_PARTITIONS:
        if result.devig_status is not ShadowDevigStatus.PROPORTIONAL_COMPLETE_PARTITION:
            reasons.append("ordinary partition lacks complete same-snapshot proportional de-vig")
        if result.fair_probability is None:
            reasons.append("ordinary partition missing fair_probability")
        else:
            edge = _robust_edge(result, event_floor)
            if edge is None or edge <= MINIMUM_ROBUST_EDGE:
                reasons.append(f"robust edge {edge} <= {MINIMUM_ROBUST_EDGE}")
    elif result.fair_probability is not None:
        edge = _robust_edge(result, event_floor)
        if edge is None or edge <= MINIMUM_ROBUST_EDGE:
            reasons.append(f"robust edge {edge} <= {MINIMUM_ROBUST_EDGE}")

    if reasons:
        return ShadowOpportunityEligibility.REJECTED, tuple(reasons)
    return ShadowOpportunityEligibility.ELIGIBLE, ()


def _rank_key(item: ShadowRoutedOpportunity) -> tuple[float, float, float, str]:
    if item.eligibility is not ShadowOpportunityEligibility.ELIGIBLE:
        raise ShadowPriceError("eligible rank key used for rejected opportunity")
    if item.robust_net_expected_value is None:
        raise ShadowPriceError("eligible opportunity lacks robust EV")
    edge = item.robust_edge if item.robust_edge is not None else float("-inf")
    floor = item.event_probability_floor if item.event_probability_floor is not None else float("-inf")
    return (-item.robust_net_expected_value, -edge, -floor, item.opportunity_id)


def _rejected_rank_key(item: ShadowRoutedOpportunity) -> tuple[float, str]:
    robust = item.robust_net_expected_value if item.robust_net_expected_value is not None else float("-inf")
    return (-robust, item.opportunity_id)


def route_shadow_price_results(price_all: ShadowPriceAllBundle) -> ShadowMarketRouterDecision:
    """Select strongest robust current value or return truthful ``NO_BET``."""
    verified = verify_shadow_price_all_bundle(price_all)
    opportunities: list[ShadowRoutedOpportunity] = []
    for result in verified.results:
        eligibility, reasons = _eligibility(result)
        event_floor = _event_floor(result)
        opportunities.append(
            ShadowRoutedOpportunity(
                opportunity_id=result.opportunity_id,
                price_result=result,
                eligibility=eligibility,
                robust_net_expected_value=result.net_expected_value,
                robust_edge=_robust_edge(result, event_floor),
                event_probability_floor=event_floor,
                model_agreement=ShadowModelAgreementStatus.SINGLE_MODEL_NO_DISAGREEMENT_EVIDENCE,
                rejection_reasons=reasons,
            )
        )

    eligible = sorted(
        (item for item in opportunities if item.eligibility is ShadowOpportunityEligibility.ELIGIBLE),
        key=_rank_key,
    )
    rejected = sorted(
        (item for item in opportunities if item.eligibility is ShadowOpportunityEligibility.REJECTED),
        key=_rejected_rank_key,
    )

    if eligible:
        status = ShadowRouterDecisionStatus.SELECTED
        selected = eligible[0].opportunity_id
        runner_up = eligible[1].opportunity_id if len(eligible) > 1 else None
    else:
        status = ShadowRouterDecisionStatus.NO_BET
        selected = None
        runner_up = None

    strongest_rejected = rejected[0].opportunity_id if rejected else None
    return _issue_shadow_router_decision(
        fixture_identity=verified.fixture_identity,
        status=status,
        selected_opportunity_id=selected,
        runner_up_opportunity_id=runner_up,
        strongest_rejected_opportunity_id=strongest_rejected,
        opportunities=tuple(opportunities),
        price_all_bundle_sha256=verified.canonical_sha256,
        router_policy_id=ROUTER_POLICY_ID,
        authority=AUTHORITY_FLAGS,
    )


__all__ = ["route_shadow_price_results"]