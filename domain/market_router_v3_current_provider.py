"""Market Router v3 for exact Price-all v3 current-provider evaluations."""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
import hashlib
import json
import math
import types
from collections.abc import Mapping, Sequence
from typing import Any

from domain import market_router_v2_direct_provider as frozen_v2
from domain import price_all_v3_current_provider as price_v3
from domain._market_router_context import RouterContextQualification, qualify_router_context
from domain._market_router_contracts import (
    MarketRouterError,
    ModelAgreementStatus,
    OpportunityEligibility,
    RouterDecisionStatus,
)
from domain._market_router_v2_contracts import (
    EXPECTED_CONTRACT_SHA256 as ROUTER_V2_CONTRACT_SHA256,
    MINIMUM_EVENT_PROBABILITY,
    MINIMUM_NET_EXPECTED_VALUE,
    MINIMUM_ROBUST_EDGE,
    MINIMUM_ROBUST_NET_EXPECTED_VALUE,
    validate_market_router_v2_contract,
)
from domain._price_all_contracts import CalibratedValueCandidate, DevigStatus
from domain.fixture_state_v2 import (
    FIXTURE_STATE_FIELD_REGISTRY_SHA256,
    FixtureStateV2Snapshot,
)
from domain.markets import MarketId, OutcomeId

SCHEMA_VERSION = 1
CONTRACT_VERSION = 1
DATASET_NAME = "athena-market-router-v3-current-provider-value-consumption-v1"
STATUS_AS_OF = "MARKET_ROUTER_V3_CURRENT_PROVIDER_AS_OF_VERIFIED"
STATUS_LIVE = "MARKET_ROUTER_V3_CURRENT_PROVIDER_LIVE_VERIFIED"
PRICE_ALL_V3_CONTRACT_SHA256 = price_v3.EXPECTED_CONTRACT_SHA256
SOURCE_REPLAY_POLICY_ID = "VERIFY_EXACT_PRICE_ALL_V3_CURRENT_PROVIDER_EVALUATION_V1"
ROUTE_TIME_POLICY_ID = "RECHECK_PR253_EVIDENCE_AGES_AND_KICKOFF_AT_ROUTER_TIME_V1"
ROBUST_POLICY_ID = "PRESERVE_FROZEN_ROUTER_V2_LOWER_ENVELOPE_THRESHOLDS_AND_TIES_V1"
NO_BET_POLICY_ID = "NO_ELIGIBLE_CURRENT_PROVIDER_VALUE_IS_SUCCESSFUL_NO_BET_V1"
NEXT_BOUNDARY = "PORTFOLIO_OPTIMIZER_V3_CURRENT_PROVIDER_ROUTER_CONSUMPTION_REQUIRED"
EXPECTED_CONTRACT_SHA256 = "61a90a29495399668e19ae4a149527abea98c172d7bdacf1a1b521776b4d771a"

AUTHORITY = types.MappingProxyType(
    {
        "current_provider_value_consumption": True,
        "source_freshness_recheck": True,
        "market_routing": True,
        "fixture_market_selection": True,
        "counterfactual_recording": True,
        "football_probability_generation": False,
        "calibration": False,
        "value_record_computation": False,
        "model_promotion": False,
        "portfolio_optimization": False,
        "accumulator": False,
        "sportybet_execution": False,
        "staking": False,
        "bet": False,
    }
)

_FULL_SETTLEMENT = frozenset({MarketId.DRAW_NO_BET, MarketId.ASIAN_HANDICAP})
_REQUIRES_FAIR = frozen_v2._REQUIRES_ORDINARY_FAIR
_BLOCKED_SPECIALISTS = frozen_v2._BLOCKED_SPECIALISTS


class MarketRouterV3CurrentProviderError(ValueError):
    pass


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise MarketRouterV3CurrentProviderError("canonical serialization failed") from exc


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _utc(value: Any, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise MarketRouterV3CurrentProviderError(f"{label} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _contract_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "dataset_name": DATASET_NAME,
        "price_all_v3_contract_sha256": PRICE_ALL_V3_CONTRACT_SHA256,
        "router_v2_policy_contract_sha256": ROUTER_V2_CONTRACT_SHA256,
        "fixture_state_field_registry_sha256": FIXTURE_STATE_FIELD_REGISTRY_SHA256,
        "source_replay_policy_id": SOURCE_REPLAY_POLICY_ID,
        "route_time_policy_id": ROUTE_TIME_POLICY_ID,
        "robust_policy_id": ROBUST_POLICY_ID,
        "no_bet_policy_id": NO_BET_POLICY_ID,
        "thresholds": {
            "minimum_event_probability": MINIMUM_EVENT_PROBABILITY,
            "minimum_net_expected_value": MINIMUM_NET_EXPECTED_VALUE,
            "minimum_robust_net_expected_value": MINIMUM_ROBUST_NET_EXPECTED_VALUE,
            "minimum_robust_edge": MINIMUM_ROBUST_EDGE,
        },
        "authority": dict(AUTHORITY),
        "next_boundary": NEXT_BOUNDARY,
    }


def calculate_market_router_v3_contract_sha256() -> str:
    return _sha(_contract_payload())


def validate_market_router_v3_contract() -> Mapping[str, str]:
    try:
        price_contract = price_v3.validate_price_all_v3_contract()
        router_contract = validate_market_router_v2_contract()
    except Exception as exc:
        raise MarketRouterV3CurrentProviderError("Router v3 dependency validation failed") from exc
    if price_contract["price_all_v3_contract_sha256"] != PRICE_ALL_V3_CONTRACT_SHA256:
        raise MarketRouterV3CurrentProviderError("Price-all v3 identity drifted")
    if router_contract["market_router_v2_contract_sha256"] != ROUTER_V2_CONTRACT_SHA256:
        raise MarketRouterV3CurrentProviderError("Router v2 policy identity drifted")
    actual = calculate_market_router_v3_contract_sha256()
    if actual != EXPECTED_CONTRACT_SHA256:
        raise MarketRouterV3CurrentProviderError("Router v3 contract drifted")
    return types.MappingProxyType(
        {
            "market_router_v3_contract_sha256": actual,
            "price_all_v3_contract_sha256": PRICE_ALL_V3_CONTRACT_SHA256,
            "router_v2_policy_contract_sha256": ROUTER_V2_CONTRACT_SHA256,
        }
    )


def _event_probability(candidate: CalibratedValueCandidate) -> float | None:
    if candidate.market_id in _FULL_SETTLEMENT:
        return None
    probabilities = candidate.probability_map
    selection_outcome = dict(candidate.calibration_unit).get("selection_outcome")
    if selection_outcome is not None:
        if set(probabilities) != {"YES", "NO"}:
            raise MarketRouterV3CurrentProviderError("selection probability semantics differ")
        return probabilities["YES"]
    try:
        return probabilities[candidate.outcome_id.value]
    except KeyError as exc:
        raise MarketRouterV3CurrentProviderError("candidate outcome probability is absent") from exc


@dataclasses.dataclass(frozen=True)
class RouterV3Variant:
    candidate_id: str
    model_id: str
    calibration_artifact_sha256: str
    raw_probability_identity: str
    price_all_result_sha256: str
    disposition: str
    net_expected_value: float | None
    event_probability: float | None
    raw_model_edge: float | None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class CurrentProviderRoutedOpportunity:
    opportunity_id: str
    fixture_id: str
    event_id: str
    market_id: MarketId
    outcome_id: OutcomeId
    line: float | None
    provider_market_id: str | None
    provider_outcome_id: str | None
    provider_specifier: str | None
    provider_market_name: str | None
    provider_outcome_name: str | None
    decimal_odds: float | None
    quote_sha256: str | None
    quote_observed_at: datetime | None
    router_quote_age_seconds: float | None
    current_inventory_sha256: str
    source_manifest_sha256: str
    source_raw_sha256: str
    current_mapping_rebind_sha256: str
    current_mapping_contract_sha256: str
    source_current_reconciliation_sha256: str
    source_legacy_mapping_sha256: str
    fair_probability: float | None
    variants: tuple[RouterV3Variant, ...]
    robust_net_expected_value: float | None
    best_net_expected_value: float | None
    ev_spread: float | None
    event_probability_floor: float | None
    robust_edge: float | None
    model_agreement_status: ModelAgreementStatus
    context_gate_passed: bool
    route_source_freshness_passed: bool
    eligibility: OpportunityEligibility
    rejection_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            **{key: value for key, value in dataclasses.asdict(self).items() if key not in {
                "market_id", "outcome_id", "quote_observed_at", "variants",
                "model_agreement_status", "eligibility",
            }},
            "market_id": self.market_id.value,
            "outcome_id": self.outcome_id.value,
            "quote_observed_at": None if self.quote_observed_at is None else self.quote_observed_at.isoformat().replace("+00:00", "Z"),
            "variants": [item.to_dict() for item in self.variants],
            "model_agreement_status": self.model_agreement_status.value,
            "eligibility": self.eligibility.value,
            "rejection_reasons": list(self.rejection_reasons),
        }


@dataclasses.dataclass(frozen=True, init=False)
class MarketRouterV3CurrentProviderDecision:
    dataset_name: str
    status: str
    proof_mode: str
    fixture_id: str
    event_id: str
    evaluation_time: datetime
    source_observed_at: datetime
    kickoff_utc: datetime
    router_quote_age_seconds: float
    router_kickoff_lead_seconds: float
    fixture_state_sha256: str
    price_all_evaluation_sha256: str
    price_all_v3_contract_sha256: str
    router_v2_policy_contract_sha256: str
    market_router_v3_contract_sha256: str
    context: RouterContextQualification
    route_source_freshness_passed: bool
    route_source_freshness_reasons: tuple[str, ...]
    decision_status: RouterDecisionStatus
    decision_reasons: tuple[str, ...]
    selected_opportunity_id: str | None
    runner_up_opportunity_id: str | None
    strongest_counterfactual_opportunity_id: str | None
    opportunities: tuple[CurrentProviderRoutedOpportunity, ...]
    price_all_evaluation: price_v3.PriceAllV3CurrentProviderEvaluation
    authority: Mapping[str, bool]
    next_boundary: str
    _fixture_state: FixtureStateV2Snapshot
    _price_all_evaluation: price_v3.PriceAllV3CurrentProviderEvaluation
    _require_live_current: bool

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise MarketRouterV3CurrentProviderError("Router v3 decisions are builder-only")

    @property
    def selected_opportunity(self) -> CurrentProviderRoutedOpportunity | None:
        return next((x for x in self.opportunities if x.opportunity_id == self.selected_opportunity_id), None)

    @property
    def canonical_sha256(self) -> str:
        return _sha(self.to_dict())

    @property
    def router_decision_id(self) -> str:
        return self.canonical_sha256

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "status": self.status,
            "proof_mode": self.proof_mode,
            "fixture_id": self.fixture_id,
            "event_id": self.event_id,
            "evaluation_time": self.evaluation_time.isoformat().replace("+00:00", "Z"),
            "source_observed_at": self.source_observed_at.isoformat().replace("+00:00", "Z"),
            "kickoff_utc": self.kickoff_utc.isoformat().replace("+00:00", "Z"),
            "router_quote_age_seconds": self.router_quote_age_seconds,
            "router_kickoff_lead_seconds": self.router_kickoff_lead_seconds,
            "fixture_state_sha256": self.fixture_state_sha256,
            "price_all_evaluation_sha256": self.price_all_evaluation_sha256,
            "price_all_v3_contract_sha256": self.price_all_v3_contract_sha256,
            "router_v2_policy_contract_sha256": self.router_v2_policy_contract_sha256,
            "market_router_v3_contract_sha256": self.market_router_v3_contract_sha256,
            "context": self.context.to_dict(),
            "route_source_freshness_passed": self.route_source_freshness_passed,
            "route_source_freshness_reasons": list(self.route_source_freshness_reasons),
            "decision_status": self.decision_status.value,
            "decision_reasons": list(self.decision_reasons),
            "selected_opportunity_id": self.selected_opportunity_id,
            "runner_up_opportunity_id": self.runner_up_opportunity_id,
            "strongest_counterfactual_opportunity_id": self.strongest_counterfactual_opportunity_id,
            "opportunities": [item.to_dict() for item in self.opportunities],
            "price_all_evaluation": self.price_all_evaluation.to_dict(),
            "authority": dict(self.authority),
            "next_boundary": self.next_boundary,
            "wager_placed": False,
        }


def _set_frozen(value: Any, fields: Mapping[str, Any]) -> Any:
    for name, field in fields.items():
        object.__setattr__(value, name, field)
    return value


def _group_key(result: price_v3.PriceAllV3CurrentProviderResult) -> tuple[Any, ...]:
    candidate = result.candidate
    return (
        candidate.fixture_id, candidate.sportybet_event_id, candidate.market_id,
        candidate.outcome_id, candidate.line,
        None if result.quote is None else _sha(result.quote.to_dict()),
    )


def _build_opportunity(
    results: Sequence[price_v3.PriceAllV3CurrentProviderResult],
    *,
    context_passed: bool,
    freshness_passed: bool,
    router_age: float,
    global_reasons: tuple[str, ...],
) -> CurrentProviderRoutedOpportunity:
    first = results[0]
    candidate = first.candidate
    rejection = list(global_reasons)
    all_priced = all(x.disposition is price_v3.CurrentProviderPriceDisposition.PRICED for x in results)
    if not all_priced:
        rejection.append("Price-all v3 did not price every model variant")
    if candidate.market_id in _BLOCKED_SPECIALISTS:
        rejection.append("specialist market lacks reviewed Phase 6 routing authority")
    if not context_passed:
        rejection.append("strict reviewed Fixture State context gate did not pass")
    if not freshness_passed:
        rejection.append("current provider source failed Router-time freshness gate")
    semantic_units = {_canonical_bytes(dict(x.candidate.calibration_unit)) for x in results}
    component_vectors = {tuple(name for name, _ in x.candidate.settlement_probabilities) for x in results}
    quote_shas = {None if x.quote is None else _sha(x.quote.to_dict()) for x in results}
    ancestry = {(
        x.source_bundle_sha256, x.current_inventory_sha256, x.source_raw_sha256,
        x.current_mapping_rebind_sha256, x.source_current_reconciliation_sha256,
    ) for x in results}
    compatible = len(semantic_units) == len(component_vectors) == len(quote_shas) == len(ancestry) == 1
    if not compatible:
        rejection.append("model variants differ in semantics, quote identity, or current source ancestry")

    variants: list[RouterV3Variant] = []
    evs: list[float] = []
    probabilities: list[float] = []
    for item in sorted(results, key=lambda x: x.candidate.candidate_id):
        probability = _event_probability(item.candidate) if all_priced and compatible else None
        edge = probability - item.fair_probability if probability is not None and item.fair_probability is not None else None
        if item.net_expected_value is not None:
            evs.append(item.net_expected_value)
        if probability is not None:
            probabilities.append(probability)
        variants.append(RouterV3Variant(
            candidate_id=item.candidate.candidate_id,
            model_id=item.candidate.model_id,
            calibration_artifact_sha256=item.candidate.calibration_artifact_sha256,
            raw_probability_identity=item.candidate.raw_probability_identity,
            price_all_result_sha256=item.canonical_sha256,
            disposition=item.disposition.value,
            net_expected_value=item.net_expected_value,
            event_probability=probability,
            raw_model_edge=edge,
        ))
    robust_ev = min(evs) if len(evs) == len(results) and evs else None
    best_ev = max(evs) if len(evs) == len(results) and evs else None
    event_floor = min(probabilities) if len(probabilities) == len(results) and probabilities else None
    fair = first.fair_probability if all_priced and compatible else None
    robust_edge = event_floor - fair if event_floor is not None and fair is not None else None
    agreement = (
        ModelAgreementStatus.SINGLE_MODEL_NO_DISAGREEMENT_EVIDENCE if compatible and len(results) == 1
        else ModelAgreementStatus.MULTI_MODEL_COMPATIBLE_LOWER_ENVELOPE if compatible
        else ModelAgreementStatus.INCOMPATIBLE_MODEL_SEMANTICS
    )
    if all_priced:
        if candidate.market_id in _REQUIRES_FAIR and first.devig_status is not DevigStatus.AVAILABLE_COMPLETE_PARTITION:
            rejection.append("ordinary partition lacks exact complete current-provider fair probability")
        if any(x.net_expected_value is None or x.net_expected_value <= MINIMUM_NET_EXPECTED_VALUE for x in results):
            rejection.append("every model variant must have strictly positive net EV")
        if robust_ev is None or robust_ev <= MINIMUM_ROBUST_NET_EXPECTED_VALUE:
            rejection.append("robust net expected value must be strictly positive")
        if event_floor is not None and event_floor < MINIMUM_EVENT_PROBABILITY:
            rejection.append("event-probability floor is below reviewed minimum")
        if fair is not None and (robust_edge is None or robust_edge <= MINIMUM_ROBUST_EDGE):
            rejection.append("robust edge must be strictly positive")

    quote = first.quote if all_priced else None
    quote_sha = None if quote is None else _sha(quote.to_dict())
    opportunity_id = _sha({
        "fixture_id": candidate.fixture_id,
        "event_id": candidate.sportybet_event_id,
        "market_id": candidate.market_id.value,
        "outcome_id": candidate.outcome_id.value,
        "line": candidate.line,
        "quote_sha256": quote_sha,
        "source_bundle_sha256": first.source_bundle_sha256,
    })
    rejection_reasons = tuple(sorted(set(rejection)))
    return CurrentProviderRoutedOpportunity(
        opportunity_id=opportunity_id,
        fixture_id=candidate.fixture_id,
        event_id=candidate.sportybet_event_id,
        market_id=candidate.market_id,
        outcome_id=candidate.outcome_id,
        line=candidate.line,
        provider_market_id=None if quote is None else quote.provider_market_id,
        provider_outcome_id=None if quote is None else quote.provider_outcome_id,
        provider_specifier=None if quote is None else quote.provider_specifier,
        provider_market_name=None if quote is None else quote.provider_market_name,
        provider_outcome_name=None if quote is None else quote.provider_outcome_name,
        decimal_odds=None if quote is None else quote.decimal_odds,
        quote_sha256=quote_sha,
        quote_observed_at=None if quote is None else quote.observed_at,
        router_quote_age_seconds=router_age if quote is not None else None,
        current_inventory_sha256=first.current_inventory_sha256,
        source_manifest_sha256=first.source_manifest_sha256,
        source_raw_sha256=first.source_raw_sha256,
        current_mapping_rebind_sha256=first.current_mapping_rebind_sha256,
        current_mapping_contract_sha256=first.current_mapping_contract_sha256,
        source_current_reconciliation_sha256=first.source_current_reconciliation_sha256,
        source_legacy_mapping_sha256=first.source_legacy_mapping_sha256,
        fair_probability=fair,
        variants=tuple(variants),
        robust_net_expected_value=robust_ev,
        best_net_expected_value=best_ev,
        ev_spread=None if robust_ev is None or best_ev is None else best_ev - robust_ev,
        event_probability_floor=event_floor,
        robust_edge=robust_edge,
        model_agreement_status=agreement,
        context_gate_passed=context_passed,
        route_source_freshness_passed=freshness_passed,
        eligibility=OpportunityEligibility.ELIGIBLE if not rejection_reasons else OpportunityEligibility.REJECTED,
        rejection_reasons=rejection_reasons,
    )


def _rank(item: CurrentProviderRoutedOpportunity) -> tuple[Any, ...]:
    return (
        -(item.robust_net_expected_value or 0.0),
        0 if item.robust_edge is not None else 1,
        -(item.robust_edge or 0.0),
        0 if item.event_probability_floor is not None else 1,
        -(item.event_probability_floor or 0.0),
        item.router_quote_age_seconds if item.router_quote_age_seconds is not None else math.inf,
        item.opportunity_id,
    )


def _build(
    price_evaluation: price_v3.PriceAllV3CurrentProviderEvaluation,
    *, fixture_state: FixtureStateV2Snapshot, evaluation_time: datetime,
    require_live_current: bool,
) -> MarketRouterV3CurrentProviderDecision:
    contracts = validate_market_router_v3_contract()
    now = _utc(evaluation_time, "evaluation_time")
    if type(price_evaluation) is not price_v3.PriceAllV3CurrentProviderEvaluation:
        raise MarketRouterV3CurrentProviderError("exact Price-all v3 evaluation is required")
    if type(fixture_state) is not FixtureStateV2Snapshot:
        raise MarketRouterV3CurrentProviderError("exact Fixture State v2 snapshot is required")
    try:
        verified = price_v3.verify_price_all_v3_current_provider_evaluation(price_evaluation)
    except price_v3.PriceAllV3CurrentProviderError as exc:
        raise MarketRouterV3CurrentProviderError("Price-all v3 reconstruction failed") from exc
    if require_live_current and verified.proof_mode != price_v3.LIVE_CURRENT:
        raise MarketRouterV3CurrentProviderError("live Router v3 requires live Price-all v3 ancestry")
    if verified.evaluation_time > now:
        raise MarketRouterV3CurrentProviderError("Router time predates Price-all v3")
    source_observed = _utc(verified.direct_event_observed_at, "direct_event_observed_at")
    kickoff = _utc(verified.kickoff_utc, "kickoff_utc")
    age = (now - source_observed).total_seconds()
    lead = (kickoff - now).total_seconds()
    if not math.isfinite(age) or age < 0:
        raise MarketRouterV3CurrentProviderError("current source is future-dated")
    freshness_reasons = []
    if age > verified.max_quote_age_seconds:
        freshness_reasons.append("current source exceeds effective maximum quote age")
    if lead <= verified.minimum_lead_seconds:
        freshness_reasons.append("current source is too close to kickoff")
    freshness_passed = not freshness_reasons
    try:
        context = qualify_router_context(fixture_state)
    except MarketRouterError as exc:
        raise MarketRouterV3CurrentProviderError("Fixture State context qualification failed") from exc
    global_reasons = []
    if fixture_state.fixture_identifier != verified.fixture_id:
        global_reasons.append("Fixture State identity differs from Price-all fixture")
    if _utc(fixture_state.kickoff, "fixture_state.kickoff") != kickoff:
        global_reasons.append("Fixture State kickoff differs from current provider kickoff")
    if _utc(fixture_state.as_of, "fixture_state.as_of") > now:
        global_reasons.append("Fixture State is future-dated at Router time")
    if now >= kickoff:
        global_reasons.append("Router evaluation is not pre-match")

    grouped: dict[tuple[Any, ...], list[price_v3.PriceAllV3CurrentProviderResult]] = {}
    for result in verified.results:
        grouped.setdefault(_group_key(result), []).append(result)
    opportunities = tuple(sorted((
        _build_opportunity(
            group, context_passed=context.passed,
            freshness_passed=freshness_passed, router_age=age,
            global_reasons=tuple(global_reasons),
        ) for group in grouped.values()
    ), key=lambda x: x.opportunity_id))
    eligible = sorted((x for x in opportunities if x.eligibility is OpportunityEligibility.ELIGIBLE), key=_rank)
    rejected = sorted((x for x in opportunities if x.eligibility is OpportunityEligibility.REJECTED), key=_rank)
    if global_reasons:
        decision_status, reasons = RouterDecisionStatus.NO_BET, tuple(sorted(set(global_reasons)))
    elif freshness_reasons:
        decision_status, reasons = RouterDecisionStatus.NO_BET, tuple(freshness_reasons)
    elif not context.passed:
        decision_status, reasons = RouterDecisionStatus.NO_BET, ("strict reviewed Fixture State context gate did not pass",)
    elif eligible:
        decision_status, reasons = RouterDecisionStatus.SELECTED, ("highest frozen-policy robust current-provider opportunity selected",)
    else:
        decision_status, reasons = RouterDecisionStatus.NO_BET, ("no opportunity cleared frozen Router policy",)
    selected = eligible[0].opportunity_id if decision_status is RouterDecisionStatus.SELECTED else None
    runner = eligible[1].opportunity_id if len(eligible) > 1 and selected is not None else None
    counterfactual = rejected[0].opportunity_id if rejected else runner
    value = object.__new__(MarketRouterV3CurrentProviderDecision)
    return _set_frozen(value, {
        "dataset_name": DATASET_NAME,
        "status": STATUS_LIVE if require_live_current else STATUS_AS_OF,
        "proof_mode": verified.proof_mode,
        "fixture_id": verified.fixture_id,
        "event_id": verified.event_id,
        "evaluation_time": now,
        "source_observed_at": source_observed,
        "kickoff_utc": kickoff,
        "router_quote_age_seconds": age,
        "router_kickoff_lead_seconds": lead,
        "fixture_state_sha256": fixture_state.canonical_sha256,
        "price_all_evaluation_sha256": verified.canonical_sha256,
        "price_all_v3_contract_sha256": PRICE_ALL_V3_CONTRACT_SHA256,
        "router_v2_policy_contract_sha256": ROUTER_V2_CONTRACT_SHA256,
        "market_router_v3_contract_sha256": contracts["market_router_v3_contract_sha256"],
        "context": context,
        "route_source_freshness_passed": freshness_passed,
        "route_source_freshness_reasons": tuple(freshness_reasons),
        "decision_status": decision_status,
        "decision_reasons": reasons,
        "selected_opportunity_id": selected,
        "runner_up_opportunity_id": runner,
        "strongest_counterfactual_opportunity_id": counterfactual,
        "opportunities": opportunities,
        "price_all_evaluation": verified,
        "authority": types.MappingProxyType(dict(AUTHORITY)),
        "next_boundary": NEXT_BOUNDARY,
        "_fixture_state": fixture_state,
        "_price_all_evaluation": price_evaluation,
        "_require_live_current": require_live_current,
    })


def route_price_all_v3_current_provider_as_of(
    price_evaluation: price_v3.PriceAllV3CurrentProviderEvaluation,
    *, fixture_state: FixtureStateV2Snapshot, evaluation_time: datetime,
) -> MarketRouterV3CurrentProviderDecision:
    return _build(price_evaluation, fixture_state=fixture_state, evaluation_time=evaluation_time, require_live_current=False)


def route_price_all_v3_current_provider(
    price_evaluation: price_v3.PriceAllV3CurrentProviderEvaluation,
    *, fixture_state: FixtureStateV2Snapshot,
) -> MarketRouterV3CurrentProviderDecision:
    return _build(price_evaluation, fixture_state=fixture_state, evaluation_time=_now_utc(), require_live_current=True)


def verify_market_router_v3_current_provider_decision(value: Any) -> MarketRouterV3CurrentProviderDecision:
    if type(value) is not MarketRouterV3CurrentProviderDecision:
        raise MarketRouterV3CurrentProviderError("exact Router v3 decision is required")
    rebuilt = _build(
        value._price_all_evaluation, fixture_state=value._fixture_state,
        evaluation_time=value.evaluation_time,
        require_live_current=value._require_live_current,
    )
    if rebuilt.to_dict() != value.to_dict():
        raise MarketRouterV3CurrentProviderError("Router v3 differs from source reconstruction")
    return rebuilt


__all__ = [name for name in globals() if not name.startswith("_")]
