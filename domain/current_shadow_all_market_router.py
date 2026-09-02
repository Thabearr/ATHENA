"""Research-only all-market Shadow Router with Prediction-first V2 semantics.

The Router consumes only an exact source-replayable ``ShadowPriceAllBundle``.
Price-all therefore completes before either the Prediction-first authority or
the retained value-first counterfactual is calculated.
"""
from __future__ import annotations

import dataclasses
import math
from typing import Optional

from domain._current_shadow_price_core import (
    AH_PREDICTION_CONFIDENCE_METHOD,
    AH_SETTLEMENT_STATES,
    AUTHORITY_FLAGS,
    DNB_PREDICTION_CONFIDENCE_METHOD,
    DNB_SETTLEMENT_STATES,
    MINIMUM_DECIMAL_ODDS,
    MINIMUM_EVENT_PROBABILITY,
    MINIMUM_NET_EXPECTED_VALUE,
    MINIMUM_PREDICTION_CONFIDENCE,
    MINIMUM_ROBUST_EDGE,
    MINIMUM_ROBUST_NET_EXPECTED_VALUE,
    ORDINARY_PARTITIONS,
    OVERLAPPING_MARKETS,
    PUSH_SPLIT_MARKETS,
    ROUTER_POLICY_ID,
    SCALAR_PREDICTION_CONFIDENCE_METHOD,
    ShadowDevigStatus,
    ShadowModelAgreementStatus,
    ShadowOpportunityEligibility,
    ShadowPriceDisposition,
    ShadowPriceError,
    ShadowRouterDecisionStatus,
    VALUE_FIRST_ROUTER_POLICY_ID,
    _finite,
    _odds,
    _probability,
    settlement_unit_return,
)
from domain._current_shadow_price_records import (
    ShadowMarketRouterDecision,
    ShadowPriceAllBundle,
    ShadowPriceResult,
    ShadowRoutedOpportunity,
    _issue_shadow_router_decision,
)
from domain.current_shadow_all_market_price_all import verify_shadow_price_all_bundle
from domain.markets import MarketId, OutcomeId


_SCALAR_MARKETS = frozenset(ORDINARY_PARTITIONS) | OVERLAPPING_MARKETS


def _event_floor(result: ShadowPriceResult) -> Optional[float]:
    return result.model_probability


def _prediction_canonical_key(result: ShadowPriceResult) -> tuple[str, str, str]:
    """Return the quote-independent identity of one football prediction."""

    if type(result.market_id) is not MarketId or type(result.outcome_id) is not OutcomeId:
        raise ShadowPriceError("prediction canonical identity is malformed")
    if result.line is None:
        line_identity = "NONE"
    elif type(result.line) is float and math.isfinite(result.line):
        line = 0.0 if result.line == 0.0 else result.line
        line_identity = line.hex()
    else:
        raise ShadowPriceError("prediction canonical line identity is malformed")
    return (result.market_id.value, result.outcome_id.value, line_identity)


def _robust_edge(result: ShadowPriceResult, event_floor: Optional[float]) -> Optional[float]:
    if event_floor is None or result.fair_probability is None:
        return None
    return event_floor - result.fair_probability


def _value_first_eligibility(
    result: ShadowPriceResult,
) -> tuple[ShadowOpportunityEligibility, tuple[str, ...]]:
    """Reproduce the former value-first Router decision for diagnostics only."""

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


# Kept as a private compatibility alias for existing PR-D test helpers.
_eligibility = _value_first_eligibility


def _validated_settlement_probabilities(
    result: ShadowPriceResult,
    expected_states: tuple[str, ...],
) -> tuple[Optional[dict[str, float]], tuple[str, ...]]:
    rows = result.settlement_state_probabilities
    if type(rows) is not tuple or any(type(row) is not tuple or len(row) != 2 for row in rows):
        return None, ("settlement distribution rows are malformed",)
    if tuple(row[0] for row in rows) != expected_states:
        return None, (f"settlement states must be exactly {expected_states}",)

    probabilities: dict[str, float] = {}
    try:
        for state, probability in rows:
            probabilities[state] = _probability(
                probability,
                f"{result.market_id.value} {state} settlement probability",
            )
    except (ShadowPriceError, AttributeError, TypeError) as exc:
        return None, (str(exc),)
    if not math.isclose(
        math.fsum(probabilities.values()),
        1.0,
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        return None, ("settlement distribution mass must sum to 1",)

    returns = result.settlement_unit_returns
    if type(returns) is not tuple or any(type(row) is not tuple or len(row) != 2 for row in returns):
        return None, ("settlement return rows are malformed",)
    if tuple(row[0] for row in returns) != expected_states:
        return None, ("settlement return states do not match settlement probabilities",)
    if result.decimal_odds is None:
        return None, ("settlement confidence requires exact decimal odds",)
    try:
        odds = _odds(result.decimal_odds)
        for (state, actual), expected in zip(
            returns,
            (settlement_unit_return(state, odds) for state in expected_states),
        ):
            if not math.isclose(
                _finite(actual, f"{state} settlement return"),
                expected,
                abs_tol=1e-12,
            ):
                return None, (f"{state} settlement return is inconsistent",)
    except (ShadowPriceError, AttributeError, TypeError) as exc:
        return None, (str(exc),)
    return probabilities, ()


def _prediction_confidence(
    result: ShadowPriceResult,
) -> tuple[Optional[float], Optional[str], tuple[str, ...]]:
    """Return model-derived comparable confidence, failing closed on ambiguity."""

    if type(result.market_id) is not MarketId or result.market_id not in (
        _SCALAR_MARKETS | PUSH_SPLIT_MARKETS
    ):
        return None, None, ("unknown market semantics have no comparable confidence",)
    if result.disposition is not ShadowPriceDisposition.PRICED:
        return None, None, (
            result.rejection_reason or f"disposition={result.disposition.value}",
        )

    if result.market_id is MarketId.DRAW_NO_BET:
        if result.model_probability is not None:
            return None, None, ("DNB must use settlement survival, not scalar probability",)
        probabilities, reasons = _validated_settlement_probabilities(
            result,
            DNB_SETTLEMENT_STATES,
        )
        if probabilities is None:
            return None, None, reasons
        return (
            math.fsum((probabilities["WIN"], probabilities["PUSH"])),
            DNB_PREDICTION_CONFIDENCE_METHOD,
            (),
        )

    if result.market_id is MarketId.ASIAN_HANDICAP:
        if result.model_probability is not None:
            return None, None, ("Asian Handicap must use settlement survival, not scalar probability",)
        probabilities, reasons = _validated_settlement_probabilities(
            result,
            AH_SETTLEMENT_STATES,
        )
        if probabilities is None:
            return None, None, reasons
        return (
            math.fsum((
                probabilities["WIN"],
                probabilities["HALF_WIN"],
                probabilities["PUSH"],
            )),
            AH_PREDICTION_CONFIDENCE_METHOD,
            (),
        )

    if result.model_probability is None:
        return None, None, ("scalar-event market lacks model probability",)
    try:
        confidence = _probability(result.model_probability, "model probability")
    except ShadowPriceError as exc:
        return None, None, (str(exc),)
    return confidence, SCALAR_PREDICTION_CONFIDENCE_METHOD, ()


def _prediction_first_eligibility(
    result: ShadowPriceResult,
    confidence: Optional[float],
    confidence_reasons: tuple[str, ...],
) -> tuple[ShadowOpportunityEligibility, tuple[str, ...]]:
    reasons = list(confidence_reasons)
    if result.disposition is not ShadowPriceDisposition.PRICED and not reasons:
        reasons.append("Price-all result is not exactly PRICED")
    if confidence is None and not reasons:
        reasons.append("prediction confidence is unavailable")
    elif confidence is not None and confidence < MINIMUM_PREDICTION_CONFIDENCE:
        reasons.append(
            f"prediction confidence {confidence} < {MINIMUM_PREDICTION_CONFIDENCE}"
        )

    if result.decimal_odds is None:
        reasons.append("exact current decimal odds are unavailable")
    else:
        try:
            odds = _odds(result.decimal_odds)
        except ShadowPriceError as exc:
            reasons.append(str(exc))
        else:
            if odds < MINIMUM_DECIMAL_ODDS:
                reasons.append(f"decimal odds {odds} < {MINIMUM_DECIMAL_ODDS}")

    if reasons:
        return ShadowOpportunityEligibility.REJECTED, tuple(reasons)
    return ShadowOpportunityEligibility.ELIGIBLE, ()


def _value_first_rank_key(item: ShadowRoutedOpportunity) -> tuple[float, float, float, str]:
    if item.value_first_eligibility is not ShadowOpportunityEligibility.ELIGIBLE:
        raise ShadowPriceError("value-first rank key used for rejected opportunity")
    if item.robust_net_expected_value is None:
        raise ShadowPriceError("value-first eligible opportunity lacks robust EV")
    edge = item.robust_edge if item.robust_edge is not None else float("-inf")
    floor = item.event_probability_floor if item.event_probability_floor is not None else float("-inf")
    return (-item.robust_net_expected_value, -edge, -floor, item.opportunity_id)


def _prediction_first_rank_key(
    item: ShadowRoutedOpportunity,
) -> tuple[float, tuple[str, str, str]]:
    if item.eligibility is not ShadowOpportunityEligibility.ELIGIBLE:
        raise ShadowPriceError("prediction-first rank key used for rejected opportunity")
    if item.prediction_confidence is None:
        raise ShadowPriceError("prediction-first eligible opportunity lacks confidence")
    return (-item.prediction_confidence, _prediction_canonical_key(item.price_result))


def _rejected_rank_key(item: ShadowRoutedOpportunity) -> tuple[float, str]:
    robust = item.robust_net_expected_value if item.robust_net_expected_value is not None else float("-inf")
    return (-robust, item.opportunity_id)


def _apply_ranks(
    opportunities: tuple[ShadowRoutedOpportunity, ...],
) -> tuple[
    tuple[ShadowRoutedOpportunity, ...],
    list[ShadowRoutedOpportunity],
    list[ShadowRoutedOpportunity],
    list[ShadowRoutedOpportunity],
]:
    prediction_eligible = [
        item for item in opportunities if item.eligibility is ShadowOpportunityEligibility.ELIGIBLE
    ]
    canonical_keys: dict[tuple[str, str, str], str] = {}
    for item in prediction_eligible:
        key = _prediction_canonical_key(item.price_result)
        if key in canonical_keys:
            raise ShadowPriceError(
                "ambiguous canonical prediction identity for Prediction-first ranking"
            )
        canonical_keys[key] = item.opportunity_id
    prediction_eligible.sort(key=_prediction_first_rank_key)
    value_eligible = sorted(
        (
            item
            for item in opportunities
            if item.value_first_eligibility is ShadowOpportunityEligibility.ELIGIBLE
        ),
        key=_value_first_rank_key,
    )
    prediction_ranks = {
        item.opportunity_id: rank
        for rank, item in enumerate(prediction_eligible, start=1)
    }
    value_ranks = {
        item.opportunity_id: rank
        for rank, item in enumerate(value_eligible, start=1)
    }
    ranked = tuple(
        dataclasses.replace(
            item,
            prediction_first_rank=prediction_ranks.get(item.opportunity_id),
            value_first_rank=value_ranks.get(item.opportunity_id),
        )
        for item in opportunities
    )
    value_rejected = sorted(
        (
            item
            for item in ranked
            if item.value_first_eligibility is ShadowOpportunityEligibility.REJECTED
        ),
        key=_rejected_rank_key,
    )
    return ranked, prediction_eligible, value_eligible, value_rejected


def route_shadow_price_results(price_all: ShadowPriceAllBundle) -> ShadowMarketRouterDecision:
    """Select the strongest comparable prediction after complete Price-all."""

    verified = verify_shadow_price_all_bundle(price_all)
    opportunities: list[ShadowRoutedOpportunity] = []
    for result in verified.results:
        confidence, confidence_method, confidence_reasons = _prediction_confidence(result)
        prediction_eligibility, prediction_reasons = _prediction_first_eligibility(
            result,
            confidence,
            confidence_reasons,
        )
        value_eligibility, value_reasons = _value_first_eligibility(result)
        event_floor = _event_floor(result)
        opportunities.append(
            ShadowRoutedOpportunity(
                opportunity_id=result.opportunity_id,
                price_result=result,
                eligibility=prediction_eligibility,
                robust_net_expected_value=result.net_expected_value,
                robust_edge=_robust_edge(result, event_floor),
                event_probability_floor=event_floor,
                model_agreement=ShadowModelAgreementStatus.SINGLE_MODEL_NO_DISAGREEMENT_EVIDENCE,
                rejection_reasons=prediction_reasons,
                prediction_confidence=confidence,
                prediction_confidence_method=confidence_method,
                value_first_eligibility=value_eligibility,
                value_first_rejection_reasons=value_reasons,
            )
        )

    ranked, prediction_eligible, value_eligible, value_rejected = _apply_ranks(
        tuple(opportunities)
    )
    prediction_rejected = sorted(
        (
            item
            for item in ranked
            if item.eligibility is ShadowOpportunityEligibility.REJECTED
        ),
        key=_rejected_rank_key,
    )

    value_first_selected = value_eligible[0].opportunity_id if value_eligible else None
    value_first_runner = (
        value_eligible[1].opportunity_id if len(value_eligible) > 1 else None
    )
    value_first_counterfactual = (
        value_first_selected
        if value_first_selected is not None
        else value_rejected[0].opportunity_id if value_rejected else None
    )

    if prediction_eligible:
        status = ShadowRouterDecisionStatus.SELECTED
        selected = prediction_eligible[0].opportunity_id
        runner_up = prediction_eligible[1].opportunity_id if len(prediction_eligible) > 1 else None
    else:
        status = ShadowRouterDecisionStatus.NO_BET
        selected = None
        runner_up = None

    strongest_rejected = prediction_rejected[0].opportunity_id if prediction_rejected else None
    return _issue_shadow_router_decision(
        fixture_identity=verified.fixture_identity,
        status=status,
        selected_opportunity_id=selected,
        runner_up_opportunity_id=runner_up,
        strongest_rejected_opportunity_id=strongest_rejected,
        opportunities=ranked,
        price_all_bundle_sha256=verified.canonical_sha256,
        router_policy_id=ROUTER_POLICY_ID,
        authority=AUTHORITY_FLAGS,
        value_first_selected_opportunity_id=value_first_selected,
        value_first_runner_up_opportunity_id=value_first_runner,
        value_first_counterfactual_opportunity_id=value_first_counterfactual,
        value_first_policy_id=VALUE_FIRST_ROUTER_POLICY_ID,
    )


def verify_shadow_router_decision(
    price_all: ShadowPriceAllBundle,
    decision: ShadowMarketRouterDecision,
) -> ShadowMarketRouterDecision:
    """Rebuild a Router decision and reject any serialized-field drift."""

    if type(decision) is not ShadowMarketRouterDecision:
        raise ShadowPriceError("decision must be an exact ShadowMarketRouterDecision")
    rebuilt = route_shadow_price_results(price_all)
    if rebuilt.to_dict() != decision.to_dict():
        raise ShadowPriceError("Router decision differs from exact source reconstruction")
    return rebuilt


__all__ = ["route_shadow_price_results", "verify_shadow_router_decision"]
