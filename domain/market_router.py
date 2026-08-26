"""ATHENA Phase 8 Market Router v1.

The authoritative entry point prices every exact Phase 7 candidate before it
performs any routing. It chooses at most one canonical market opportunity for
one fixture, or returns a first-class NO_BET decision. It never creates
football probabilities, bookmaker prices, accumulator legs, slips, or bets.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any, Iterable, Sequence

from domain._market_router_context import (
    RouterContextQualification,
    qualify_router_context,
)
from domain._market_router_contracts import (
    AUTHORITY_FLAGS,
    MINIMUM_EVENT_PROBABILITY,
    MINIMUM_NET_EXPECTED_VALUE,
    MINIMUM_ROBUST_EDGE,
    MINIMUM_ROBUST_NET_EXPECTED_VALUE,
    ModelAgreementStatus,
    OpportunityEligibility,
    RouterDecisionStatus,
    UNCERTAINTY_STATUS,
    MarketRouterError,
    validate_market_router_contract,
)
from domain._price_all_contracts import (
    CalibratedValueCandidate,
    DevigStatus,
    PriceDisposition,
    SportyBetExactQuote,
)
from domain.fixture_state_v2 import FixtureStateV2Snapshot
from domain.markets import MarketId, OutcomeId
from domain.price_all_value import PriceAllValueResult, price_all_candidates

_FULL_SETTLEMENT_MARKETS = frozenset({MarketId.DRAW_NO_BET, MarketId.ASIAN_HANDICAP})
_REQUIRES_ORDINARY_FAIR = frozenset({
    MarketId.MATCH_RESULT,
    MarketId.BTTS,
    MarketId.TOTAL_GOALS,
    MarketId.DRAW_OR_OVER_2_5,
    MarketId.HOME_OR_OVER_2_5,
    MarketId.AWAY_OR_OVER_2_5,
    MarketId.HOME_WIN_TO_NIL,
    MarketId.AWAY_WIN_TO_NIL,
})
_BLOCKED_SPECIALISTS = frozenset({
    MarketId.HOME_WIN_EITHER_HALF,
    MarketId.AWAY_WIN_EITHER_HALF,
    MarketId.MATCH_RESULT_1UP,
    MarketId.MATCH_RESULT_2UP,
})


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _quote_sha(quote: SportyBetExactQuote) -> str:
    return _sha(quote.to_dict())


def _utc(value: datetime) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise MarketRouterError("evaluation_time must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class RouterModelVariant:
    candidate_id: str
    model_id: str
    calibration_artifact_sha256: str
    calibration_strategy: str
    raw_probability_identity: str
    phase7_result_sha256: str
    phase7_disposition: str
    net_expected_value: float | None
    calibrated_event_probability: float | None
    raw_model_edge: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "model_id": self.model_id,
            "calibration_artifact_sha256": self.calibration_artifact_sha256,
            "calibration_strategy": self.calibration_strategy,
            "raw_probability_identity": self.raw_probability_identity,
            "phase7_result_sha256": self.phase7_result_sha256,
            "phase7_disposition": self.phase7_disposition,
            "net_expected_value": self.net_expected_value,
            "calibrated_event_probability": self.calibrated_event_probability,
            "raw_model_edge": self.raw_model_edge,
        }


@dataclass(frozen=True)
class RoutedOpportunity:
    opportunity_id: str
    fixture_id: str
    sportybet_event_id: str
    market_id: MarketId
    outcome_id: OutcomeId
    line: float | None
    quote_identity_sha256: str | None
    decimal_odds: float | None
    quote_source: str | None
    quote_observed_at: datetime | None
    quote_age_seconds: float | None
    evidence_snapshot_sha256: str | None
    fair_probability: float | None
    variants: tuple[RouterModelVariant, ...]
    robust_net_expected_value: float | None
    best_net_expected_value: float | None
    ev_spread: float | None
    calibrated_event_probability_floor: float | None
    robust_edge: float | None
    model_agreement_status: ModelAgreementStatus
    context_gate_passed: bool
    eligibility: OpportunityEligibility
    rejection_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "fixture_id": self.fixture_id,
            "sportybet_event_id": self.sportybet_event_id,
            "market_id": self.market_id.value,
            "outcome_id": self.outcome_id.value,
            "line": self.line,
            "quote_identity_sha256": self.quote_identity_sha256,
            "decimal_odds": self.decimal_odds,
            "quote_source": self.quote_source,
            "quote_observed_at": (
                None
                if self.quote_observed_at is None
                else self.quote_observed_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            ),
            "quote_age_seconds": self.quote_age_seconds,
            "evidence_snapshot_sha256": self.evidence_snapshot_sha256,
            "fair_probability": self.fair_probability,
            "variants": [item.to_dict() for item in self.variants],
            "robust_net_expected_value": self.robust_net_expected_value,
            "best_net_expected_value": self.best_net_expected_value,
            "ev_spread": self.ev_spread,
            "calibrated_event_probability_floor": self.calibrated_event_probability_floor,
            "robust_edge": self.robust_edge,
            "model_agreement_status": self.model_agreement_status.value,
            "context_gate_passed": self.context_gate_passed,
            "eligibility": self.eligibility.value,
            "rejection_reasons": list(self.rejection_reasons),
        }


@dataclass(frozen=True)
class MarketRouterDecision:
    fixture_id: str
    sportybet_event_id: str | None
    evaluation_time: datetime
    fixture_state_sha256: str
    price_all_contract_sha256: str
    router_contract_sha256: str
    context: RouterContextQualification
    decision_status: RouterDecisionStatus
    decision_reasons: tuple[str, ...]
    selected_opportunity_id: str | None
    runner_up_opportunity_id: str | None
    strongest_counterfactual_opportunity_id: str | None
    opportunities: tuple[RoutedOpportunity, ...]
    price_all_results: tuple[PriceAllValueResult, ...]

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(_canonical_bytes(self._identity_dict())).hexdigest()

    @property
    def router_decision_id(self) -> str:
        return self.canonical_sha256

    @property
    def selected_opportunity(self) -> RoutedOpportunity | None:
        if self.selected_opportunity_id is None:
            return None
        return next(
            item for item in self.opportunities if item.opportunity_id == self.selected_opportunity_id
        )

    @property
    def runner_up(self) -> RoutedOpportunity | None:
        if self.runner_up_opportunity_id is None:
            return None
        return next(
            item for item in self.opportunities if item.opportunity_id == self.runner_up_opportunity_id
        )

    @property
    def strongest_counterfactual(self) -> RoutedOpportunity | None:
        if self.strongest_counterfactual_opportunity_id is None:
            return None
        return next(
            item
            for item in self.opportunities
            if item.opportunity_id == self.strongest_counterfactual_opportunity_id
        )

    def _identity_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "sportybet_event_id": self.sportybet_event_id,
            "evaluation_time": self.evaluation_time.astimezone(timezone.utc).isoformat().replace(
                "+00:00", "Z"
            ),
            "fixture_state_sha256": self.fixture_state_sha256,
            "price_all_contract_sha256": self.price_all_contract_sha256,
            "router_contract_sha256": self.router_contract_sha256,
            "context": self.context.to_dict(),
            "decision_status": self.decision_status.value,
            "decision_reasons": list(self.decision_reasons),
            "selected_opportunity_id": self.selected_opportunity_id,
            "runner_up_opportunity_id": self.runner_up_opportunity_id,
            "strongest_counterfactual_opportunity_id": self.strongest_counterfactual_opportunity_id,
            "opportunities": [item.to_dict() for item in self.opportunities],
            "price_all_results": [item.to_dict() for item in self.price_all_results],
            "uncertainty_status": UNCERTAINTY_STATUS,
            "authority_flags": dict(AUTHORITY_FLAGS),
        }

    def to_dict(self) -> dict[str, Any]:
        result = self._identity_dict()
        result["router_decision_id"] = self.router_decision_id
        result["canonical_sha256"] = self.canonical_sha256
        return result


def _calibration_unit_dict(candidate: CalibratedValueCandidate) -> dict[str, Any]:
    return dict(candidate.calibration_unit)


def _event_probability(candidate: CalibratedValueCandidate) -> float | None:
    if candidate.market_id in _FULL_SETTLEMENT_MARKETS:
        return None
    probabilities = candidate.probability_map
    unit = _calibration_unit_dict(candidate)
    selection_outcome = unit.get("selection_outcome")
    if selection_outcome is not None:
        if set(probabilities) != {"YES", "NO"}:
            raise MarketRouterError("selection-specific event probability semantics are incompatible")
        return probabilities["YES"]
    label = candidate.outcome_id.value
    if label not in probabilities:
        raise MarketRouterError("candidate outcome is absent from calibrated component semantics")
    return probabilities[label]


def _opportunity_group_key(result: PriceAllValueResult) -> tuple[Any, ...]:
    candidate = result.candidate
    quote_sha = None if result.quote is None else _quote_sha(result.quote)
    return (
        candidate.fixture_id,
        candidate.sportybet_event_id,
        candidate.market_id.value,
        candidate.outcome_id.value,
        candidate.line,
        quote_sha,
    )


def _group_compatibility(results: Sequence[PriceAllValueResult]) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    unit_semantics = {
        _canonical_bytes(dict(item.candidate.calibration_unit)) for item in results
    }
    component_semantics = {
        tuple(name for name, _probability in item.candidate.settlement_probabilities)
        for item in results
    }
    if len(unit_semantics) != 1 or len(component_semantics) != 1:
        reasons.append("contributing model variants have incompatible calibration component semantics")
    quote_shas = {
        None if item.quote is None else _quote_sha(item.quote) for item in results
    }
    if len(quote_shas) != 1:
        reasons.append("contributing model variants do not share one exact quote identity")
    fair_values = {item.fair_probability for item in results}
    if len(fair_values) != 1:
        reasons.append("Phase 7 fair-probability identity differs across model variants")
    return not reasons, tuple(reasons)


def _build_opportunity(
    results: Sequence[PriceAllValueResult],
    *,
    context_passed: bool,
    identity_reasons: tuple[str, ...] = (),
) -> RoutedOpportunity:
    if not results:
        raise MarketRouterError("cannot build empty routing opportunity")
    first = results[0]
    candidate = first.candidate
    compatible, reasons = _group_compatibility(results)
    rejection = list(reasons)
    all_priced = all(item.disposition is PriceDisposition.PRICED for item in results)
    if not all_priced:
        states = ",".join(sorted({item.disposition.value for item in results}))
        rejection.append(f"Phase 7 did not price every model variant: {states}")
    if candidate.market_id in _BLOCKED_SPECIALISTS:
        rejection.append("specialist market lacks reviewed Phase 6 routing authority")
    if not context_passed:
        rejection.append("strict reviewed Fixture State context gate did not pass")
    rejection.extend(
        f"routing identity gate failed: {reason}" for reason in identity_reasons
    )

    fair_probability = first.fair_probability if all_priced else None
    event_probabilities: list[float] = []
    variants: list[RouterModelVariant] = []
    ev_values: list[float] = []
    if compatible:
        for item in sorted(results, key=lambda value: value.candidate.candidate_id):
            probability = _event_probability(item.candidate) if all_priced else None
            edge = (
                probability - item.fair_probability
                if probability is not None and item.fair_probability is not None
                else None
            )
            if probability is not None:
                event_probabilities.append(probability)
            if item.net_expected_value is not None:
                ev_values.append(item.net_expected_value)
            variants.append(RouterModelVariant(
                candidate_id=item.candidate.candidate_id,
                model_id=item.candidate.model_id,
                calibration_artifact_sha256=item.candidate.calibration_artifact_sha256,
                calibration_strategy=item.candidate.calibration_strategy,
                raw_probability_identity=item.candidate.raw_probability_identity,
                phase7_result_sha256=item.canonical_sha256,
                phase7_disposition=item.disposition.value,
                net_expected_value=item.net_expected_value,
                calibrated_event_probability=probability,
                raw_model_edge=edge,
            ))
    else:
        for item in sorted(results, key=lambda value: value.candidate.candidate_id):
            variants.append(RouterModelVariant(
                candidate_id=item.candidate.candidate_id,
                model_id=item.candidate.model_id,
                calibration_artifact_sha256=item.candidate.calibration_artifact_sha256,
                calibration_strategy=item.candidate.calibration_strategy,
                raw_probability_identity=item.candidate.raw_probability_identity,
                phase7_result_sha256=item.canonical_sha256,
                phase7_disposition=item.disposition.value,
                net_expected_value=item.net_expected_value,
                calibrated_event_probability=None,
                raw_model_edge=None,
            ))

    robust_ev = min(ev_values) if len(ev_values) == len(results) and ev_values else None
    best_ev = max(ev_values) if len(ev_values) == len(results) and ev_values else None
    ev_spread = (best_ev - robust_ev) if robust_ev is not None and best_ev is not None else None
    event_floor = (
        min(event_probabilities)
        if event_probabilities and len(event_probabilities) == len(results)
        else None
    )
    robust_edge = (
        event_floor - fair_probability
        if event_floor is not None and fair_probability is not None
        else None
    )

    if compatible and len(results) == 1:
        agreement = ModelAgreementStatus.SINGLE_MODEL_NO_DISAGREEMENT_EVIDENCE
    elif compatible:
        agreement = ModelAgreementStatus.MULTI_MODEL_COMPATIBLE_LOWER_ENVELOPE
    else:
        agreement = ModelAgreementStatus.INCOMPATIBLE_MODEL_SEMANTICS

    if all_priced:
        if (
            candidate.market_id in _REQUIRES_ORDINARY_FAIR
            and first.devig_status is not DevigStatus.AVAILABLE_COMPLETE_PARTITION
        ):
            rejection.append("ordinary partition lacks a complete Phase 7 fair-probability quote set")
        if any(
            item.net_expected_value is None
            or item.net_expected_value <= MINIMUM_NET_EXPECTED_VALUE
            for item in results
        ):
            rejection.append("every contributing model variant must have strictly positive Phase 7 net EV")
        if robust_ev is None or robust_ev <= MINIMUM_ROBUST_NET_EXPECTED_VALUE:
            rejection.append("robust net expected value must be strictly positive")
        if event_floor is not None and event_floor < MINIMUM_EVENT_PROBABILITY:
            rejection.append(
                f"calibrated event-probability floor is below {MINIMUM_EVENT_PROBABILITY:.2f}"
            )
        if fair_probability is not None:
            if robust_edge is None:
                rejection.append("ordinary fair-probability opportunity lacks event-probability semantics")
            elif robust_edge <= MINIMUM_ROBUST_EDGE:
                rejection.append("robust edge versus Phase 7 fair probability must be strictly positive")

    quote = first.quote if all_priced else None
    quote_sha = None if quote is None else _quote_sha(quote)
    opportunity_payload = {
        "fixture_id": candidate.fixture_id,
        "sportybet_event_id": candidate.sportybet_event_id,
        "market_id": candidate.market_id.value,
        "outcome_id": candidate.outcome_id.value,
        "line": candidate.line,
        "quote_identity_sha256": quote_sha,
    }
    opportunity_id = _sha(opportunity_payload)
    rejection_reasons = tuple(sorted(set(rejection)))
    eligibility = (
        OpportunityEligibility.ELIGIBLE
        if not rejection_reasons
        else OpportunityEligibility.REJECTED
    )
    return RoutedOpportunity(
        opportunity_id=opportunity_id,
        fixture_id=candidate.fixture_id,
        sportybet_event_id=candidate.sportybet_event_id,
        market_id=candidate.market_id,
        outcome_id=candidate.outcome_id,
        line=candidate.line,
        quote_identity_sha256=quote_sha,
        decimal_odds=None if quote is None else quote.decimal_odds,
        quote_source=None if quote is None else quote.source,
        quote_observed_at=None if quote is None else quote.observed_at,
        quote_age_seconds=first.quote_age_seconds if quote is not None else None,
        evidence_snapshot_sha256=(None if quote is None else quote.evidence_snapshot_sha256),
        fair_probability=fair_probability,
        variants=tuple(variants),
        robust_net_expected_value=robust_ev,
        best_net_expected_value=best_ev,
        ev_spread=ev_spread,
        calibrated_event_probability_floor=event_floor,
        robust_edge=robust_edge,
        model_agreement_status=agreement,
        context_gate_passed=context_passed,
        eligibility=eligibility,
        rejection_reasons=rejection_reasons,
    )


def _eligible_rank_key(item: RoutedOpportunity) -> tuple[Any, ...]:
    if item.robust_net_expected_value is None:
        raise MarketRouterError("eligible opportunity lacks robust EV")
    edge_present = item.robust_edge is not None
    event_present = item.calibrated_event_probability_floor is not None
    quote_age = item.quote_age_seconds if item.quote_age_seconds is not None else math.inf
    return (
        -item.robust_net_expected_value,
        0 if edge_present else 1,
        -(item.robust_edge if item.robust_edge is not None else 0.0),
        0 if event_present else 1,
        -(
            item.calibrated_event_probability_floor
            if item.calibrated_event_probability_floor is not None
            else 0.0
        ),
        quote_age,
        item.opportunity_id,
    )


def _counterfactual_rank_key(item: RoutedOpportunity) -> tuple[Any, ...]:
    robust = item.robust_net_expected_value
    edge = item.robust_edge
    event = item.calibrated_event_probability_floor
    age = item.quote_age_seconds
    return (
        0 if robust is not None else 1,
        -(robust if robust is not None else 0.0),
        0 if edge is not None else 1,
        -(edge if edge is not None else 0.0),
        0 if event is not None else 1,
        -(event if event is not None else 0.0),
        age if age is not None else math.inf,
        item.opportunity_id,
    )


def _decision(
    *,
    fixture_state: FixtureStateV2Snapshot,
    evaluation_time: datetime,
    price_results: tuple[PriceAllValueResult, ...],
    context: RouterContextQualification,
    router_contract_sha: str,
    price_all_contract_sha: str,
    identity_reasons: tuple[str, ...],
) -> MarketRouterDecision:
    grouped: dict[tuple[Any, ...], list[PriceAllValueResult]] = {}
    for item in price_results:
        grouped.setdefault(_opportunity_group_key(item), []).append(item)
    opportunities = tuple(sorted(
        (
            _build_opportunity(
                values,
                context_passed=context.passed,
                identity_reasons=identity_reasons,
            )
            for values in grouped.values()
        ),
        key=lambda item: item.opportunity_id,
    ))
    eligible = sorted(
        (item for item in opportunities if item.eligibility is OpportunityEligibility.ELIGIBLE),
        key=_eligible_rank_key,
    )
    rejected = sorted(
        (item for item in opportunities if item.eligibility is OpportunityEligibility.REJECTED),
        key=_counterfactual_rank_key,
    )
    candidate_events = sorted({item.candidate.sportybet_event_id for item in price_results})
    event_id = candidate_events[0] if len(candidate_events) == 1 else None

    if identity_reasons:
        status = RouterDecisionStatus.NO_BET
        reasons = identity_reasons
        selected = None
        runner = None
        counterfactual = (
            sorted(opportunities, key=_counterfactual_rank_key)[0].opportunity_id
            if opportunities else None
        )
    elif not context.passed:
        status = RouterDecisionStatus.NO_BET
        pieces = ["strict reviewed Fixture State context gate did not pass"]
        if context.missing_field_ids:
            pieces.append("missing=" + ",".join(item.value for item in context.missing_field_ids))
        if context.blocked_field_ids:
            pieces.append("blocked=" + ",".join(item.value for item in context.blocked_field_ids))
        reasons = tuple(pieces)
        selected = None
        runner = None
        counterfactual = (
            sorted(opportunities, key=_counterfactual_rank_key)[0].opportunity_id
            if opportunities else None
        )
    elif eligible:
        status = RouterDecisionStatus.SELECTED
        reasons = ("highest reviewed robust positive-value opportunity selected after full Phase 7 pricing",)
        selected = eligible[0].opportunity_id
        runner = eligible[1].opportunity_id if len(eligible) > 1 else None
        counterfactual = rejected[0].opportunity_id if rejected else runner
    else:
        status = RouterDecisionStatus.NO_BET
        reasons = ("no canonical opportunity cleared the frozen robust-value Router v1 policy",)
        selected = None
        runner = None
        counterfactual = (
            sorted(opportunities, key=_counterfactual_rank_key)[0].opportunity_id
            if opportunities else None
        )

    return MarketRouterDecision(
        fixture_id=fixture_state.fixture_identifier,
        sportybet_event_id=event_id,
        evaluation_time=evaluation_time,
        fixture_state_sha256=fixture_state.canonical_sha256,
        price_all_contract_sha256=price_all_contract_sha,
        router_contract_sha256=router_contract_sha,
        context=context,
        decision_status=status,
        decision_reasons=reasons,
        selected_opportunity_id=selected,
        runner_up_opportunity_id=runner,
        strongest_counterfactual_opportunity_id=counterfactual,
        opportunities=opportunities,
        price_all_results=price_results,
    )


def route_market_candidates(
    candidates: Iterable[CalibratedValueCandidate],
    quotes: Iterable[SportyBetExactQuote],
    *,
    fixture_state: FixtureStateV2Snapshot,
    evaluation_time: datetime,
) -> MarketRouterDecision:
    """Price every exact Phase 7 candidate, then route one opportunity or NO_BET."""
    identities = validate_market_router_contract()
    now = _utc(evaluation_time)
    if type(fixture_state) is not FixtureStateV2Snapshot:
        raise MarketRouterError("fixture_state must be exact FixtureStateV2Snapshot")
    candidate_values = tuple(candidates)
    quote_values = tuple(quotes)

    # Authoritative invariant: every candidate crosses Phase 7 before any
    # ranking, routing, context qualification, or winner choice occurs.
    price_results = price_all_candidates(
        candidate_values,
        quote_values,
        evaluation_time=now,
    )

    context = qualify_router_context(fixture_state)
    identity_reasons: list[str] = []
    fixture_ids = {item.candidate.fixture_id for item in price_results}
    event_ids = {item.candidate.sportybet_event_id for item in price_results}
    if len(fixture_ids) > 1:
        identity_reasons.append("mixed ATHENA fixture IDs are not routable together")
    if len(event_ids) > 1:
        identity_reasons.append("mixed SportyBet event IDs are not routable together")
    if fixture_ids and fixture_state.fixture_identifier not in fixture_ids:
        identity_reasons.append("Fixture State identity does not match candidate fixture")
    fixture_as_of = fixture_state.as_of.astimezone(timezone.utc)
    kickoff = fixture_state.kickoff.astimezone(timezone.utc)
    if fixture_as_of > now:
        identity_reasons.append("Fixture State as_of is later than Router evaluation time")
    if now >= kickoff:
        identity_reasons.append("Router evaluation must occur strictly before kickoff")

    return _decision(
        fixture_state=fixture_state,
        evaluation_time=now,
        price_results=price_results,
        context=context,
        router_contract_sha=identities["market_router_contract_sha256"],
        price_all_contract_sha=identities["price_all_contract_sha256"],
        identity_reasons=tuple(sorted(set(identity_reasons))),
    )


__all__ = [name for name in globals() if not name.startswith("_")]
