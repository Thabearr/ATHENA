"""ATHENA Market Router v2 for verified direct-provider Price-all value records.

This boundary consumes one exact verified ``PriceAllV2DirectProviderEvaluation``
from PR248, rechecks direct-provider freshness at Router evaluation time, applies
the reviewed deterministic robust-value Router policy, and selects at most one
canonical opportunity for a fixture or returns first-class ``NO_BET``.

It does not create football probabilities, recompute Price-all value, optimize a
portfolio, construct an accumulator, execute SportyBet actions, stake, or bet.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import types
from typing import Any, Mapping, Sequence

from domain import price_all_v2_direct_provider as price_v2
from domain._market_router_context import RouterContextQualification, qualify_router_context
from domain._market_router_contracts import MarketRouterError
from domain._market_router_v2_contracts import (
    AUTHORITY,
    DATASET_NAME,
    LEGACY_MARKET_ROUTER_V1_CONTRACT_SHA256,
    MINIMUM_EVENT_PROBABILITY,
    MINIMUM_NET_EXPECTED_VALUE,
    MINIMUM_ROBUST_EDGE,
    MINIMUM_ROBUST_NET_EXPECTED_VALUE,
    ModelAgreementStatus,
    NEXT_BOUNDARY,
    OpportunityEligibility,
    PRICE_ALL_V2_CONTRACT_SHA256,
    RouterDecisionStatus,
    STATUS,
    UNCERTAINTY_STATUS,
    MarketRouterV2DirectProviderError,
    validate_market_router_v2_contract,
)
from domain._price_all_contracts import CalibratedValueCandidate, DevigStatus
from domain.fixture_state_v2 import FixtureStateV2Snapshot
from domain.markets import MarketId, OutcomeId

_FULL_SETTLEMENT_MARKETS = frozenset({MarketId.DRAW_NO_BET, MarketId.ASIAN_HANDICAP})
_REQUIRES_ORDINARY_FAIR = frozenset(
    {
        MarketId.MATCH_RESULT,
        MarketId.BTTS,
        MarketId.TOTAL_GOALS,
        MarketId.DRAW_OR_OVER_2_5,
        MarketId.HOME_OR_OVER_2_5,
        MarketId.AWAY_OR_OVER_2_5,
        MarketId.HOME_WIN_TO_NIL,
        MarketId.AWAY_WIN_TO_NIL,
    }
)
_BLOCKED_SPECIALISTS = frozenset(
    {
        MarketId.HOME_WIN_EITHER_HALF,
        MarketId.AWAY_WIN_EITHER_HALF,
        MarketId.MATCH_RESULT_1UP,
        MarketId.MATCH_RESULT_2UP,
    }
)


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise MarketRouterV2DirectProviderError(
            "canonical JSON serialization failed"
        ) from exc


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _utc(value: Any, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise MarketRouterV2DirectProviderError(f"{label} must be timezone-aware")
    try:
        return value.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise MarketRouterV2DirectProviderError(f"{label} is invalid") from exc


def _quote_sha(result: price_v2.PriceAllV2DirectProviderResult) -> str | None:
    return None if result.quote is None else _sha(result.quote.to_dict())


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
            raise MarketRouterV2DirectProviderError(
                "selection-specific event probability semantics are incompatible"
            )
        return probabilities["YES"]
    label = candidate.outcome_id.value
    if label not in probabilities:
        raise MarketRouterV2DirectProviderError(
            "candidate outcome is absent from calibrated component semantics"
        )
    return probabilities[label]


@dataclass(frozen=True)
class RouterV2ModelVariant:
    candidate_id: str
    model_id: str
    calibration_artifact_sha256: str
    calibration_strategy: str
    raw_probability_identity: str
    price_all_v2_result_sha256: str
    price_all_v2_disposition: str
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
            "price_all_v2_result_sha256": self.price_all_v2_result_sha256,
            "price_all_v2_disposition": self.price_all_v2_disposition,
            "net_expected_value": self.net_expected_value,
            "calibrated_event_probability": self.calibrated_event_probability,
            "raw_model_edge": self.raw_model_edge,
        }


@dataclass(frozen=True)
class DirectProviderRoutedOpportunity:
    opportunity_id: str
    fixture_id: str
    sportybet_event_id: str
    market_id: MarketId
    outcome_id: OutcomeId
    line: float | None
    quote_identity_sha256: str | None
    decimal_odds: float | None
    provider_market_id: str | None
    provider_outcome_id: str | None
    provider_specifier: str | None
    quote_source: str | None
    quote_observed_at: datetime | None
    price_all_quote_age_seconds: float | None
    router_quote_age_seconds: float | None
    source_quote_source_sha256: str
    source_bundle_sha256: str
    source_raw_sha256: str | None
    reviewed_mapping_sha256: str | None
    fixture_reconciliation_sha256: str | None
    fair_probability: float | None
    variants: tuple[RouterV2ModelVariant, ...]
    robust_net_expected_value: float | None
    best_net_expected_value: float | None
    ev_spread: float | None
    calibrated_event_probability_floor: float | None
    robust_edge: float | None
    model_agreement_status: ModelAgreementStatus
    context_gate_passed: bool
    route_source_freshness_passed: bool
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
            "provider_market_id": self.provider_market_id,
            "provider_outcome_id": self.provider_outcome_id,
            "provider_specifier": self.provider_specifier,
            "quote_source": self.quote_source,
            "quote_observed_at": (
                None
                if self.quote_observed_at is None
                else self.quote_observed_at.astimezone(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            ),
            "price_all_quote_age_seconds": self.price_all_quote_age_seconds,
            "router_quote_age_seconds": self.router_quote_age_seconds,
            "source_quote_source_sha256": self.source_quote_source_sha256,
            "source_bundle_sha256": self.source_bundle_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "reviewed_mapping_sha256": self.reviewed_mapping_sha256,
            "fixture_reconciliation_sha256": self.fixture_reconciliation_sha256,
            "fair_probability": self.fair_probability,
            "variants": [item.to_dict() for item in self.variants],
            "robust_net_expected_value": self.robust_net_expected_value,
            "best_net_expected_value": self.best_net_expected_value,
            "ev_spread": self.ev_spread,
            "calibrated_event_probability_floor": self.calibrated_event_probability_floor,
            "robust_edge": self.robust_edge,
            "model_agreement_status": self.model_agreement_status.value,
            "context_gate_passed": self.context_gate_passed,
            "route_source_freshness_passed": self.route_source_freshness_passed,
            "eligibility": self.eligibility.value,
            "rejection_reasons": list(self.rejection_reasons),
        }


@dataclass(frozen=True, init=False)
class MarketRouterV2DirectProviderDecision:
    dataset_name: str
    status: str
    fixture_id: str
    sportybet_event_id: str
    evaluation_time: datetime
    price_all_evaluation_time: datetime
    source_observed_at: datetime
    kickoff_utc: datetime
    router_quote_age_seconds: float
    router_kickoff_lead_seconds: float
    max_quote_age_seconds: int
    minimum_lead_seconds: int
    fixture_state_sha256: str
    source_quote_source_sha256: str
    source_bundle_sha256: str
    price_all_v2_evaluation_sha256: str
    price_all_v2_contract_sha256: str
    legacy_market_router_v1_contract_sha256: str
    market_router_v2_contract_sha256: str
    context: RouterContextQualification
    route_source_freshness_passed: bool
    route_source_freshness_reasons: tuple[str, ...]
    decision_status: RouterDecisionStatus
    decision_reasons: tuple[str, ...]
    selected_opportunity_id: str | None
    runner_up_opportunity_id: str | None
    strongest_counterfactual_opportunity_id: str | None
    opportunities: tuple[DirectProviderRoutedOpportunity, ...]
    price_all_evaluation: price_v2.PriceAllV2DirectProviderEvaluation
    authority: Mapping[str, bool]
    next_boundary: str
    _fixture_state: FixtureStateV2Snapshot
    _price_all_evaluation: price_v2.PriceAllV2DirectProviderEvaluation

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise MarketRouterV2DirectProviderError(
            "Router v2 decisions are issued only by verified direct-provider routing"
        )

    @property
    def selected_opportunity(self) -> DirectProviderRoutedOpportunity | None:
        if self.selected_opportunity_id is None:
            return None
        return next(
            item
            for item in self.opportunities
            if item.opportunity_id == self.selected_opportunity_id
        )

    @property
    def runner_up(self) -> DirectProviderRoutedOpportunity | None:
        if self.runner_up_opportunity_id is None:
            return None
        return next(
            item
            for item in self.opportunities
            if item.opportunity_id == self.runner_up_opportunity_id
        )

    @property
    def strongest_counterfactual(self) -> DirectProviderRoutedOpportunity | None:
        if self.strongest_counterfactual_opportunity_id is None:
            return None
        return next(
            item
            for item in self.opportunities
            if item.opportunity_id == self.strongest_counterfactual_opportunity_id
        )

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(_canonical_bytes(self.to_dict())).hexdigest()

    @property
    def router_decision_id(self) -> str:
        return self.canonical_sha256

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "status": self.status,
            "fixture_id": self.fixture_id,
            "sportybet_event_id": self.sportybet_event_id,
            "evaluation_time": self.evaluation_time.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "price_all_evaluation_time": self.price_all_evaluation_time.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "source_observed_at": self.source_observed_at.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "kickoff_utc": self.kickoff_utc.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "router_quote_age_seconds": self.router_quote_age_seconds,
            "router_kickoff_lead_seconds": self.router_kickoff_lead_seconds,
            "max_quote_age_seconds": self.max_quote_age_seconds,
            "minimum_lead_seconds": self.minimum_lead_seconds,
            "fixture_state_sha256": self.fixture_state_sha256,
            "source_quote_source_sha256": self.source_quote_source_sha256,
            "source_bundle_sha256": self.source_bundle_sha256,
            "price_all_v2_evaluation_sha256": self.price_all_v2_evaluation_sha256,
            "price_all_v2_contract_sha256": self.price_all_v2_contract_sha256,
            "legacy_market_router_v1_contract_sha256": (
                self.legacy_market_router_v1_contract_sha256
            ),
            "market_router_v2_contract_sha256": self.market_router_v2_contract_sha256,
            "context": self.context.to_dict(),
            "route_source_freshness_passed": self.route_source_freshness_passed,
            "route_source_freshness_reasons": list(self.route_source_freshness_reasons),
            "decision_status": self.decision_status.value,
            "decision_reasons": list(self.decision_reasons),
            "selected_opportunity_id": self.selected_opportunity_id,
            "runner_up_opportunity_id": self.runner_up_opportunity_id,
            "strongest_counterfactual_opportunity_id": (
                self.strongest_counterfactual_opportunity_id
            ),
            "opportunities": [item.to_dict() for item in self.opportunities],
            "price_all_evaluation": self.price_all_evaluation.to_dict(),
            "uncertainty_status": UNCERTAINTY_STATUS,
            "authority": dict(self.authority),
            "next_boundary": self.next_boundary,
            "wager_placed": False,
        }


def _set_frozen(obj: Any, values: Mapping[str, Any]) -> Any:
    for name, value in values.items():
        object.__setattr__(obj, name, value)
    return obj


def _opportunity_group_key(
    result: price_v2.PriceAllV2DirectProviderResult,
) -> tuple[Any, ...]:
    candidate = result.candidate
    return (
        candidate.fixture_id,
        candidate.sportybet_event_id,
        candidate.market_id.value,
        candidate.outcome_id.value,
        candidate.line,
        _quote_sha(result),
    )


def _group_compatibility(
    results: Sequence[price_v2.PriceAllV2DirectProviderResult],
) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    unit_semantics = {
        _canonical_bytes(dict(item.candidate.calibration_unit)) for item in results
    }
    component_semantics = {
        tuple(name for name, _probability in item.candidate.settlement_probabilities)
        for item in results
    }
    if len(unit_semantics) != 1 or len(component_semantics) != 1:
        reasons.append(
            "contributing model variants have incompatible calibration component semantics"
        )
    quote_shas = {_quote_sha(item) for item in results}
    if len(quote_shas) != 1:
        reasons.append(
            "contributing model variants do not share one exact direct-provider quote identity"
        )
    fair_values = {item.fair_probability for item in results}
    if len(fair_values) != 1:
        reasons.append(
            "Price-all v2 fair-probability identity differs across model variants"
        )
    source_identities = {
        (
            item.source_quote_source_sha256,
            item.source_bundle_sha256,
            item.price_all_v2_contract_sha256,
        )
        for item in results
    }
    if len(source_identities) != 1:
        reasons.append(
            "contributing model variants do not share one Price-all v2 source ancestry"
        )
    return not reasons, tuple(reasons)


def _build_opportunity(
    results: Sequence[price_v2.PriceAllV2DirectProviderResult],
    *,
    context_passed: bool,
    route_source_freshness_passed: bool,
    router_quote_age_seconds: float,
    global_reasons: tuple[str, ...],
) -> DirectProviderRoutedOpportunity:
    if not results:
        raise MarketRouterV2DirectProviderError(
            "cannot build empty direct-provider routing opportunity"
        )
    first = results[0]
    candidate = first.candidate
    compatible, compatibility_reasons = _group_compatibility(results)
    rejection = list(compatibility_reasons)
    all_priced = all(
        item.disposition is price_v2.DirectProviderPriceDisposition.PRICED
        for item in results
    )
    if not all_priced:
        states = ",".join(sorted({item.disposition.value for item in results}))
        rejection.append(
            f"Price-all v2 did not price every model variant: {states}"
        )
    if candidate.market_id in _BLOCKED_SPECIALISTS:
        rejection.append(
            "specialist market lacks reviewed Phase 6 routing authority"
        )
    if not context_passed:
        rejection.append("strict reviewed Fixture State context gate did not pass")
    if not route_source_freshness_passed:
        rejection.append("direct-provider source failed Router-time freshness gate")
    rejection.extend(f"routing identity gate failed: {reason}" for reason in global_reasons)

    fair_probability = first.fair_probability if all_priced else None
    variants: list[RouterV2ModelVariant] = []
    ev_values: list[float] = []
    event_probabilities: list[float] = []
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
            variants.append(
                RouterV2ModelVariant(
                    candidate_id=item.candidate.candidate_id,
                    model_id=item.candidate.model_id,
                    calibration_artifact_sha256=(
                        item.candidate.calibration_artifact_sha256
                    ),
                    calibration_strategy=item.candidate.calibration_strategy,
                    raw_probability_identity=item.candidate.raw_probability_identity,
                    price_all_v2_result_sha256=item.canonical_sha256,
                    price_all_v2_disposition=item.disposition.value,
                    net_expected_value=item.net_expected_value,
                    calibrated_event_probability=probability,
                    raw_model_edge=edge,
                )
            )
    else:
        for item in sorted(results, key=lambda value: value.candidate.candidate_id):
            variants.append(
                RouterV2ModelVariant(
                    candidate_id=item.candidate.candidate_id,
                    model_id=item.candidate.model_id,
                    calibration_artifact_sha256=(
                        item.candidate.calibration_artifact_sha256
                    ),
                    calibration_strategy=item.candidate.calibration_strategy,
                    raw_probability_identity=item.candidate.raw_probability_identity,
                    price_all_v2_result_sha256=item.canonical_sha256,
                    price_all_v2_disposition=item.disposition.value,
                    net_expected_value=item.net_expected_value,
                    calibrated_event_probability=None,
                    raw_model_edge=None,
                )
            )

    robust_ev = min(ev_values) if len(ev_values) == len(results) and ev_values else None
    best_ev = max(ev_values) if len(ev_values) == len(results) and ev_values else None
    ev_spread = (
        best_ev - robust_ev
        if robust_ev is not None and best_ev is not None
        else None
    )
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
            rejection.append(
                "ordinary partition lacks a complete current direct-provider fair-probability quote set"
            )
        if any(
            item.net_expected_value is None
            or item.net_expected_value <= MINIMUM_NET_EXPECTED_VALUE
            for item in results
        ):
            rejection.append(
                "every contributing model variant must have strictly positive Price-all v2 net EV"
            )
        if robust_ev is None or robust_ev <= MINIMUM_ROBUST_NET_EXPECTED_VALUE:
            rejection.append("robust net expected value must be strictly positive")
        if event_floor is not None and event_floor < MINIMUM_EVENT_PROBABILITY:
            rejection.append(
                f"calibrated event-probability floor is below {MINIMUM_EVENT_PROBABILITY:.2f}"
            )
        if fair_probability is not None:
            if robust_edge is None:
                rejection.append(
                    "ordinary fair-probability opportunity lacks event-probability semantics"
                )
            elif robust_edge <= MINIMUM_ROBUST_EDGE:
                rejection.append(
                    "robust edge versus direct-provider fair probability must be strictly positive"
                )

    quote = first.quote if all_priced else None
    quote_sha = None if quote is None else _sha(quote.to_dict())
    opportunity_id = _sha(
        {
            "fixture_id": candidate.fixture_id,
            "sportybet_event_id": candidate.sportybet_event_id,
            "market_id": candidate.market_id.value,
            "outcome_id": candidate.outcome_id.value,
            "line": candidate.line,
            "quote_identity_sha256": quote_sha,
            "source_quote_source_sha256": first.source_quote_source_sha256,
        }
    )
    rejection_reasons = tuple(sorted(set(rejection)))
    eligibility = (
        OpportunityEligibility.ELIGIBLE
        if not rejection_reasons
        else OpportunityEligibility.REJECTED
    )
    return DirectProviderRoutedOpportunity(
        opportunity_id=opportunity_id,
        fixture_id=candidate.fixture_id,
        sportybet_event_id=candidate.sportybet_event_id,
        market_id=candidate.market_id,
        outcome_id=candidate.outcome_id,
        line=candidate.line,
        quote_identity_sha256=quote_sha,
        decimal_odds=None if quote is None else quote.decimal_odds,
        provider_market_id=None if quote is None else quote.provider_market_id,
        provider_outcome_id=None if quote is None else quote.provider_outcome_id,
        provider_specifier=None if quote is None else quote.provider_specifier,
        quote_source=None if quote is None else quote.source,
        quote_observed_at=None if quote is None else quote.observed_at,
        price_all_quote_age_seconds=(
            first.quote_age_seconds if quote is not None else None
        ),
        router_quote_age_seconds=(
            router_quote_age_seconds if quote is not None else None
        ),
        source_quote_source_sha256=first.source_quote_source_sha256,
        source_bundle_sha256=first.source_bundle_sha256,
        source_raw_sha256=None if quote is None else quote.source_raw_sha256,
        reviewed_mapping_sha256=(
            None if quote is None else quote.reviewed_mapping_sha256
        ),
        fixture_reconciliation_sha256=(
            None if quote is None else quote.fixture_reconciliation_sha256
        ),
        fair_probability=fair_probability,
        variants=tuple(variants),
        robust_net_expected_value=robust_ev,
        best_net_expected_value=best_ev,
        ev_spread=ev_spread,
        calibrated_event_probability_floor=event_floor,
        robust_edge=robust_edge,
        model_agreement_status=agreement,
        context_gate_passed=context_passed,
        route_source_freshness_passed=route_source_freshness_passed,
        eligibility=eligibility,
        rejection_reasons=rejection_reasons,
    )


def _eligible_rank_key(item: DirectProviderRoutedOpportunity) -> tuple[Any, ...]:
    if item.robust_net_expected_value is None:
        raise MarketRouterV2DirectProviderError(
            "eligible opportunity lacks robust EV"
        )
    edge_present = item.robust_edge is not None
    event_present = item.calibrated_event_probability_floor is not None
    quote_age = (
        item.router_quote_age_seconds
        if item.router_quote_age_seconds is not None
        else math.inf
    )
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


def _counterfactual_rank_key(
    item: DirectProviderRoutedOpportunity,
) -> tuple[Any, ...]:
    robust = item.robust_net_expected_value
    edge = item.robust_edge
    event = item.calibrated_event_probability_floor
    age = item.router_quote_age_seconds
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


def _issue_decision(
    *,
    fixture_state: FixtureStateV2Snapshot,
    price_evaluation: price_v2.PriceAllV2DirectProviderEvaluation,
    evaluation_time: datetime,
    context: RouterContextQualification,
    router_quote_age_seconds: float,
    router_kickoff_lead_seconds: float,
    route_source_freshness_passed: bool,
    route_source_freshness_reasons: tuple[str, ...],
    global_reasons: tuple[str, ...],
    contracts: Mapping[str, str],
) -> MarketRouterV2DirectProviderDecision:
    grouped: dict[
        tuple[Any, ...], list[price_v2.PriceAllV2DirectProviderResult]
    ] = {}
    for item in price_evaluation.results:
        grouped.setdefault(_opportunity_group_key(item), []).append(item)

    opportunities = tuple(
        sorted(
            (
                _build_opportunity(
                    values,
                    context_passed=context.passed,
                    route_source_freshness_passed=route_source_freshness_passed,
                    router_quote_age_seconds=router_quote_age_seconds,
                    global_reasons=global_reasons,
                )
                for values in grouped.values()
            ),
            key=lambda item: item.opportunity_id,
        )
    )
    eligible = sorted(
        (
            item
            for item in opportunities
            if item.eligibility is OpportunityEligibility.ELIGIBLE
        ),
        key=_eligible_rank_key,
    )
    rejected = sorted(
        (
            item
            for item in opportunities
            if item.eligibility is OpportunityEligibility.REJECTED
        ),
        key=_counterfactual_rank_key,
    )

    if global_reasons:
        decision_status = RouterDecisionStatus.NO_BET
        decision_reasons = global_reasons
        selected = None
        runner = None
        counterfactual = (
            sorted(opportunities, key=_counterfactual_rank_key)[0].opportunity_id
            if opportunities
            else None
        )
    elif not route_source_freshness_passed:
        decision_status = RouterDecisionStatus.NO_BET
        decision_reasons = route_source_freshness_reasons
        selected = None
        runner = None
        counterfactual = (
            sorted(opportunities, key=_counterfactual_rank_key)[0].opportunity_id
            if opportunities
            else None
        )
    elif not context.passed:
        pieces = ["strict reviewed Fixture State context gate did not pass"]
        if context.missing_field_ids:
            pieces.append(
                "missing=" + ",".join(item.value for item in context.missing_field_ids)
            )
        if context.blocked_field_ids:
            pieces.append(
                "blocked=" + ",".join(item.value for item in context.blocked_field_ids)
            )
        decision_status = RouterDecisionStatus.NO_BET
        decision_reasons = tuple(pieces)
        selected = None
        runner = None
        counterfactual = (
            sorted(opportunities, key=_counterfactual_rank_key)[0].opportunity_id
            if opportunities
            else None
        )
    elif eligible:
        decision_status = RouterDecisionStatus.SELECTED
        decision_reasons = (
            "highest reviewed robust positive-value opportunity selected from verified Price-all v2 direct-provider values",
        )
        selected = eligible[0].opportunity_id
        runner = eligible[1].opportunity_id if len(eligible) > 1 else None
        counterfactual = rejected[0].opportunity_id if rejected else runner
    else:
        decision_status = RouterDecisionStatus.NO_BET
        decision_reasons = (
            "no canonical opportunity cleared the frozen direct-provider robust-value Router v2 policy",
        )
        selected = None
        runner = None
        counterfactual = (
            sorted(opportunities, key=_counterfactual_rank_key)[0].opportunity_id
            if opportunities
            else None
        )

    value = object.__new__(MarketRouterV2DirectProviderDecision)
    return _set_frozen(
        value,
        {
            "dataset_name": DATASET_NAME,
            "status": STATUS,
            "fixture_id": price_evaluation.fixture_id,
            "sportybet_event_id": price_evaluation.event_id,
            "evaluation_time": evaluation_time,
            "price_all_evaluation_time": price_evaluation.evaluation_time,
            "source_observed_at": price_evaluation.source_observed_at,
            "kickoff_utc": price_evaluation.kickoff_utc,
            "router_quote_age_seconds": router_quote_age_seconds,
            "router_kickoff_lead_seconds": router_kickoff_lead_seconds,
            "max_quote_age_seconds": price_evaluation.max_quote_age_seconds,
            "minimum_lead_seconds": price_evaluation.minimum_lead_seconds,
            "fixture_state_sha256": fixture_state.canonical_sha256,
            "source_quote_source_sha256": (
                price_evaluation.source_quote_source_sha256
            ),
            "source_bundle_sha256": price_evaluation.source_bundle_sha256,
            "price_all_v2_evaluation_sha256": price_evaluation.canonical_sha256,
            "price_all_v2_contract_sha256": contracts[
                "price_all_v2_contract_sha256"
            ],
            "legacy_market_router_v1_contract_sha256": contracts[
                "legacy_market_router_v1_contract_sha256"
            ],
            "market_router_v2_contract_sha256": contracts[
                "market_router_v2_contract_sha256"
            ],
            "context": context,
            "route_source_freshness_passed": route_source_freshness_passed,
            "route_source_freshness_reasons": route_source_freshness_reasons,
            "decision_status": decision_status,
            "decision_reasons": decision_reasons,
            "selected_opportunity_id": selected,
            "runner_up_opportunity_id": runner,
            "strongest_counterfactual_opportunity_id": counterfactual,
            "opportunities": opportunities,
            "price_all_evaluation": price_evaluation,
            "authority": types.MappingProxyType(dict(AUTHORITY)),
            "next_boundary": NEXT_BOUNDARY,
            "_fixture_state": fixture_state,
            "_price_all_evaluation": price_evaluation,
        },
    )


def route_price_all_v2_direct_provider_evaluation(
    price_evaluation: price_v2.PriceAllV2DirectProviderEvaluation,
    *,
    fixture_state: FixtureStateV2Snapshot,
    evaluation_time: datetime,
) -> MarketRouterV2DirectProviderDecision:
    """Route one verified Price-all v2 evaluation to one opportunity or NO_BET."""
    contracts = validate_market_router_v2_contract()
    now = _utc(evaluation_time, "evaluation_time")
    if type(price_evaluation) is not price_v2.PriceAllV2DirectProviderEvaluation:
        raise MarketRouterV2DirectProviderError(
            "price_evaluation must be exact PriceAllV2DirectProviderEvaluation"
        )
    if type(fixture_state) is not FixtureStateV2Snapshot:
        raise MarketRouterV2DirectProviderError(
            "fixture_state must be exact FixtureStateV2Snapshot"
        )
    try:
        verified = price_v2.verify_price_all_v2_direct_provider_evaluation(
            price_evaluation
        )
    except price_v2.PriceAllV2DirectProviderError as exc:
        raise MarketRouterV2DirectProviderError(
            "Price-all v2 evaluation reconstruction failed"
        ) from exc
    if (
        verified.dataset_name != price_v2.DATASET_NAME
        or verified.status != price_v2.STATUS
        or verified.next_boundary != price_v2.NEXT_BOUNDARY
        or verified.price_all_v2_contract_sha256 != PRICE_ALL_V2_CONTRACT_SHA256
    ):
        raise MarketRouterV2DirectProviderError(
            "Price-all v2 evaluation state is not approved for Router v2"
        )
    if (
        verified.authority.get("verified_direct_provider_price_consumption") is not True
        or verified.authority.get("value_record_computation") is not True
        or verified.authority.get("market_router") is not False
        or verified.authority.get("bet") is not False
    ):
        raise MarketRouterV2DirectProviderError(
            "Price-all v2 evaluation authority flags mismatch"
        )
    if verified.evaluation_time > now:
        raise MarketRouterV2DirectProviderError(
            "Router evaluation_time predates Price-all v2 evaluation"
        )

    source_observed = _utc(verified.source_observed_at, "source_observed_at")
    kickoff = _utc(verified.kickoff_utc, "kickoff_utc")
    router_quote_age = (now - source_observed).total_seconds()
    router_kickoff_lead = (kickoff - now).total_seconds()
    if not math.isfinite(router_quote_age) or router_quote_age < 0:
        raise MarketRouterV2DirectProviderError(
            "direct-provider source observation is future-dated at Router time"
        )
    if not math.isfinite(router_kickoff_lead):
        raise MarketRouterV2DirectProviderError(
            "Router kickoff lead is invalid"
        )

    freshness_reasons: list[str] = []
    if router_quote_age > verified.max_quote_age_seconds:
        freshness_reasons.append(
            "direct-provider source exceeds the effective Price-all v2 maximum quote age at Router time"
        )
    if router_kickoff_lead <= verified.minimum_lead_seconds:
        freshness_reasons.append(
            "direct-provider source is too close to kickoff at Router time"
        )
    route_source_freshness_passed = not freshness_reasons

    try:
        context = qualify_router_context(fixture_state)
    except MarketRouterError as exc:
        raise MarketRouterV2DirectProviderError(
            "Fixture State Router context qualification failed"
        ) from exc

    global_reasons: list[str] = []
    if fixture_state.fixture_identifier != verified.fixture_id:
        global_reasons.append(
            "Fixture State identity does not match Price-all v2 fixture"
        )
    fixture_as_of = _utc(fixture_state.as_of, "fixture_state.as_of")
    fixture_kickoff = _utc(fixture_state.kickoff, "fixture_state.kickoff")
    if fixture_as_of > now:
        global_reasons.append(
            "Fixture State as_of is later than Router evaluation time"
        )
    if fixture_kickoff != kickoff:
        global_reasons.append(
            "Fixture State kickoff does not match reconciled direct-provider kickoff"
        )
    if now >= fixture_kickoff:
        global_reasons.append(
            "Router evaluation must occur strictly before Fixture State kickoff"
        )
    candidate_fixture_ids = {item.candidate.fixture_id for item in verified.results}
    candidate_event_ids = {
        item.candidate.sportybet_event_id for item in verified.results
    }
    if candidate_fixture_ids and candidate_fixture_ids != {verified.fixture_id}:
        global_reasons.append(
            "Price-all v2 results contain a candidate fixture outside evaluation identity"
        )
    if candidate_event_ids and candidate_event_ids != {verified.event_id}:
        global_reasons.append(
            "Price-all v2 results contain a SportyBet event outside evaluation identity"
        )

    return _issue_decision(
        fixture_state=fixture_state,
        price_evaluation=verified,
        evaluation_time=now,
        context=context,
        router_quote_age_seconds=router_quote_age,
        router_kickoff_lead_seconds=router_kickoff_lead,
        route_source_freshness_passed=route_source_freshness_passed,
        route_source_freshness_reasons=tuple(sorted(set(freshness_reasons))),
        global_reasons=tuple(sorted(set(global_reasons))),
        contracts=contracts,
    )


def verify_market_router_v2_direct_provider_decision(
    value: MarketRouterV2DirectProviderDecision,
) -> MarketRouterV2DirectProviderDecision:
    """Rebuild one Router v2 decision from its retained exact upstream inputs."""
    if type(value) is not MarketRouterV2DirectProviderDecision:
        raise MarketRouterV2DirectProviderError(
            "value must be exact MarketRouterV2DirectProviderDecision"
        )
    rebuilt = route_price_all_v2_direct_provider_evaluation(
        value._price_all_evaluation,
        fixture_state=value._fixture_state,
        evaluation_time=value.evaluation_time,
    )
    if rebuilt.to_dict() != value.to_dict():
        raise MarketRouterV2DirectProviderError(
            "Router v2 decision differs from exact source reconstruction"
        )
    return rebuilt


__all__ = [name for name in globals() if not name.startswith("_")]
