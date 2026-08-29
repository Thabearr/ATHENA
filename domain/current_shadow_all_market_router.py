"""Research-only Shadow all-market Router (PR D).

Consumes complete Price-all output. Selects strongest robust opportunity or NO_BET.
Does not implement Portfolio, share-code, stake, or production selection.
"""
from __future__ import annotations

from typing import Optional, Sequence

from domain._current_shadow_price_types import (
    AUTHORITY_FLAGS,
    MINIMUM_EVENT_PROBABILITY,
    MINIMUM_NET_EXPECTED_VALUE,
    MINIMUM_ROBUST_EDGE,
    MINIMUM_ROBUST_NET_EXPECTED_VALUE,
    ORDINARY_PARTITIONS,
    PUSH_SPLIT_MARKETS,
    ROUTER_POLICY_ID,
    ShadowDevigStatus,
    ShadowMarketRouterDecision,
    ShadowModelAgreementStatus,
    ShadowOpportunityEligibility,
    ShadowPriceDisposition,
    ShadowPriceError,
    ShadowPriceResult,
    ShadowRoutedOpportunity,
    ShadowRouterDecisionStatus,
)


def _event_floor(result: ShadowPriceResult) -> Optional[float]:
    if result.model_probability is None:
        return None
    return result.model_probability


def _robust_edge(result: ShadowPriceResult, event_floor: Optional[float]) -> Optional[float]:
    if event_floor is None or result.fair_probability is None:
        return None
    return event_floor - result.fair_probability


def _eligibility(result: ShadowPriceResult) -> tuple[ShadowOpportunityEligibility, tuple[str, ...]]:
    reasons: list[str] = []
    if result.disposition is not ShadowPriceDisposition.PRICED:
        reasons.append(f"disposition={result.disposition.value}")
        return ShadowOpportunityEligibility.REJECTED, tuple(reasons)

    if result.net_expected_value is None:
        reasons.append("missing net_expected_value")
        return ShadowOpportunityEligibility.REJECTED, tuple(reasons)

    if result.net_expected_value <= MINIMUM_NET_EXPECTED_VALUE:
        reasons.append(
            f"net_expected_value {result.net_expected_value} <= {MINIMUM_NET_EXPECTED_VALUE}"
        )

    robust_ev = result.net_expected_value  # single-model lower envelope
    if robust_ev <= MINIMUM_ROBUST_NET_EXPECTED_VALUE:
        reasons.append(
            f"robust_net_expected_value {robust_ev} <= {MINIMUM_ROBUST_NET_EXPECTED_VALUE}"
        )

    event_floor = _event_floor(result)
    if result.market_id in ORDINARY_PARTITIONS and event_floor is not None:
        if event_floor < MINIMUM_EVENT_PROBABILITY:
            reasons.append(
                f"event probability floor {event_floor} < {MINIMUM_EVENT_PROBABILITY}"
            )

    edge = _robust_edge(result, event_floor)
    if result.fair_probability is not None:
        if edge is None or edge <= MINIMUM_ROBUST_EDGE:
            reasons.append(
                f"robust edge {edge} <= {MINIMUM_ROBUST_EDGE}"
            )

    if reasons:
        return ShadowOpportunityEligibility.REJECTED, tuple(reasons)
    return ShadowOpportunityEligibility.ELIGIBLE, ()


def _rank_key(item: ShadowRoutedOpportunity) -> tuple:
    if item.eligibility is not ShadowOpportunityEligibility.ELIGIBLE:
        raise ShadowPriceError("rank key only for eligible opportunities")
    robust = item.robust_net_expected_value
    if robust is None:
        raise ShadowPriceError("eligible opportunity lacks robust EV")
    edge = item.robust_edge
    edge_key = edge if edge is not None else float("-inf")
    floor = item.event_probability_floor
    floor_key = floor if floor is not None else float("-inf")
    return (-robust, -edge_key, -floor_key, item.opportunity_id)


def _rejected_rank_key(item: ShadowRoutedOpportunity) -> tuple:
    robust = item.robust_net_expected_value
    robust_key = robust if robust is not None else float("-inf")
    return (-robust_key, item.opportunity_id)


def route_shadow_price_results(
    *,
    fixture_identity: str,
    price_results: Sequence[ShadowPriceResult],
) -> ShadowMarketRouterDecision:
    """Route complete Price-all output: select strongest robust value or NO_BET."""

    if type(fixture_identity) is not str or not fixture_identity.strip():
        raise ShadowPriceError("fixture_identity must be non-empty")
    if not isinstance(price_results, Sequence) or isinstance(price_results, (str, bytes)):
        raise ShadowPriceError("price_results must be a sequence")
    for item in price_results:
        if type(item) is not ShadowPriceResult:
            raise ShadowPriceError("price_results must contain ShadowPriceResult")
        if item.fixture_identity != fixture_identity:
            raise ShadowPriceError("price result fixture_identity mismatch")

    opportunities: list[ShadowRoutedOpportunity] = []
    for result in price_results:
        if result.disposition is ShadowPriceDisposition.AUDIT_ONLY_UPSTREAM_BLOCKED:
            eligibility = ShadowOpportunityEligibility.REJECTED
            reasons = (result.rejection_reason or result.disposition.value,)
            opp = ShadowRoutedOpportunity(
                opportunity_id=result.opportunity_id(),
                price_result=result,
                eligibility=eligibility,
                robust_net_expected_value=result.net_expected_value,
                robust_edge=None,
                event_probability_floor=result.model_probability,
                model_agreement=ShadowModelAgreementStatus.SINGLE_MODEL_NO_DISAGREEMENT_EVIDENCE,
                rejection_reasons=reasons,
            )
            opportunities.append(opp)
            continue

        eligibility, reasons = _eligibility(result)
        event_floor = _event_floor(result)
        edge = _robust_edge(result, event_floor)
        opportunities.append(
            ShadowRoutedOpportunity(
                opportunity_id=result.opportunity_id(),
                price_result=result,
                eligibility=eligibility,
                robust_net_expected_value=result.net_expected_value,
                robust_edge=edge,
                event_probability_floor=event_floor,
                model_agreement=ShadowModelAgreementStatus.SINGLE_MODEL_NO_DISAGREEMENT_EVIDENCE,
                rejection_reasons=reasons,
            )
        )

    ids = [item.opportunity_id for item in opportunities]
    if len(ids) != len(set(ids)):
        raise ShadowPriceError("duplicate opportunity IDs")

    eligible = sorted(
        [item for item in opportunities if item.eligibility is ShadowOpportunityEligibility.ELIGIBLE],
        key=_rank_key,
    )
    rejected = sorted(
        [item for item in opportunities if item.eligibility is ShadowOpportunityEligibility.REJECTED],
        key=_rejected_rank_key,
    )

    if eligible:
        selected = eligible[0].opportunity_id
        runner = eligible[1].opportunity_id if len(eligible) > 1 else None
        status = ShadowRouterDecisionStatus.SELECTED
    else:
        selected = None
        runner = None
        status = ShadowRouterDecisionStatus.NO_BET

    strongest_rejected = rejected[0].opportunity_id if rejected else None

    return ShadowMarketRouterDecision(
        fixture_identity=fixture_identity,
        status=status,
        selected_opportunity_id=selected,
        runner_up_opportunity_id=runner,
        strongest_rejected_opportunity_id=strongest_rejected,
        opportunities=tuple(opportunities),
        price_results=tuple(price_results),
        router_policy_id=ROUTER_POLICY_ID,
        authority=dict(AUTHORITY_FLAGS),
    )


__all__ = ["route_shadow_price_results"]
