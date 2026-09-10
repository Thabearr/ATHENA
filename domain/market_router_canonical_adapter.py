"""Canonical ATHENA Router / coherence migration interface (P1.4).

The permanent canonical module name is ``domain.market_router``. That name is
still occupied by the supported Phase-8/v1 implementation, so P1.4 uses this
explicit adapter until those callers migrate. The adapter consumes the P1.3
canonical PriceAllEvaluation, delegates exact source reconstruction and the
frozen value/context gates to reviewed Router v3, and promotes one routing
contract with comparable prediction confidence, quote-independent tie-breaking,
logical coherence diagnostics, and counterfactual recording.

This module does not fetch providers, generate football probabilities, reprice
markets, optimize a portfolio, construct a share code, calculate a stake, or
place a wager. Coherence is policy inside this router boundary, not a second
selector.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import enum
import hashlib
import json
import math
import types
from typing import Any

from domain import market_router_v3_current_provider as _v3
from domain import price_all as _price_all
from domain._market_router_contracts import (
    ModelAgreementStatus,
    OpportunityEligibility,
    RouterDecisionStatus,
)
from domain._price_all_contracts import CalibratedValueCandidate
from domain.fixture_state_v2 import FixtureStateV2Snapshot
from domain.markets import MarketId, OutcomeId

SCHEMA_VERSION = 1
POLICY_ID = "ATHENA_CANONICAL_ROUTER_COHERENCE_V1"
IMPLEMENTATION_ID = "domain.market_router_canonical_adapter"
CANONICAL_TARGET_MODULE = "domain.market_router"
SOURCE_ROUTER_IMPLEMENTATION_ID = "domain.market_router_v3_current_provider"
SOURCE_ROUTER_V3_CONTRACT_SHA256 = _v3.EXPECTED_CONTRACT_SHA256
CANONICAL_PRICE_ALL_POLICY_ID = _price_all.POLICY_ID
SOURCE_ALIGNED_REFERENCE_POLICY_ID = "SHADOW_SOURCE_ALIGNED_SETTLEMENT_AWARE_ROUTER_V3"
SELECTION_POLICY_ID = (
    "SETTLEMENT_AWARE_EV_THEN_COMPARABLE_CONFIDENCE_THEN_"
    "QUOTE_INDEPENDENT_PREDICTION_IDENTITY_V1"
)
COUNTERFACTUAL_POLICY_ID = (
    "MEASURED_VALUE_THEN_COMPARABLE_CONFIDENCE_THEN_"
    "QUOTE_INDEPENDENT_PREDICTION_IDENTITY_V1"
)
COHERENCE_POLICY_ID = (
    "LOGICAL_EVENT_ATOMS_AND_NESTED_TOTALS_DIAGNOSTIC_"
    "DEFAULT_SINGLE_SELECTION_V1"
)
MAX_SELECTED_PER_FIXTURE = 1
SAME_GAME_COMBINATION_AUTHORIZED = False
MINIMUM_PREDICTION_CONFIDENCE = 0.55
MINIMUM_DECIMAL_ODDS = 1.09
SCALAR_PREDICTION_CONFIDENCE_METHOD = "MODEL_EVENT_PROBABILITY"
DNB_PREDICTION_CONFIDENCE_METHOD = "SETTLEMENT_SURVIVAL_WIN_PLUS_PUSH"
AH_PREDICTION_CONFIDENCE_METHOD = "SETTLEMENT_SURVIVAL_WIN_PLUS_HALF_WIN_PLUS_PUSH"
DNB_SETTLEMENT_STATES = ("WIN", "PUSH", "LOSS")
AH_SETTLEMENT_STATES = ("WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS")
_RELATIONSHIPS = (
    "SHARED_REGULATION_RESULT_ATOM",
    "SHARED_TOTALS_OVER_2_5_ATOM",
    "SHARED_BTTS_NO_ATOM",
    "NESTED_TOTAL_GOALS_OVER",
    "NESTED_TOTAL_GOALS_UNDER",
)

AUTHORITY = types.MappingProxyType(
    {
        "canonical_price_all_consumption": True,
        "source_router_v3_reconstruction": True,
        "source_freshness_recheck": True,
        "market_routing": True,
        "fixture_market_selection": True,
        "coherence_grouping": True,
        "counterfactual_recording": True,
        "football_probability_generation": False,
        "calibration": False,
        "price_all_value_computation": False,
        "model_promotion": False,
        "portfolio_optimization": False,
        "accumulator": False,
        "share_code_generation": False,
        "sportybet_execution": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "bet": False,
        "wager_placed": False,
    }
)


class CanonicalMarketRouterError(ValueError):
    """Canonical Router rejected an input or exact source reconstruction."""


class CoherenceMemberStatus(str, enum.Enum):
    WINNER = "WINNER"
    RUNNER_UP = "RUNNER_UP"
    ELIGIBLE_LOWER_RANK = "ELIGIBLE_LOWER_RANK"
    REJECTED = "REJECTED"


def _canonical_bytes(value: Any) -> bytes:
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise CanonicalMarketRouterError("canonical serialization failed") from exc


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _utc(value: Any, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise CanonicalMarketRouterError(f"{label} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _line_identity(line: float | None) -> str:
    if line is None:
        return "NONE"
    if isinstance(line, bool) or not isinstance(line, (int, float)):
        raise CanonicalMarketRouterError("prediction line identity must be finite numeric or None")
    value = float(line)
    if not math.isfinite(value):
        raise CanonicalMarketRouterError("prediction line identity must be finite numeric or None")
    return (0.0 if value == 0.0 else value).hex()


def _prediction_key(
    market_id: MarketId, outcome_id: OutcomeId, line: float | None
) -> tuple[str, str, str]:
    if type(market_id) is not MarketId or type(outcome_id) is not OutcomeId:
        raise CanonicalMarketRouterError("prediction identity must use canonical market/outcome enums")
    return market_id.value, outcome_id.value, _line_identity(line)


def _prediction_identity_sha256(
    fixture_id: str,
    market_id: MarketId,
    outcome_id: OutcomeId,
    line: float | None,
) -> str:
    if type(fixture_id) is not str or not fixture_id.strip():
        raise CanonicalMarketRouterError("fixture_id is required for prediction identity")
    return _sha(
        {
            "fixture_id": fixture_id,
            "market_id": market_id.value,
            "outcome_id": outcome_id.value,
            "line_identity": _line_identity(line),
        }
    )


def _contract_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "implementation_id": IMPLEMENTATION_ID,
        "canonical_target_module": CANONICAL_TARGET_MODULE,
        "source_router_implementation_id": SOURCE_ROUTER_IMPLEMENTATION_ID,
        "source_router_v3_contract_sha256": SOURCE_ROUTER_V3_CONTRACT_SHA256,
        "canonical_price_all_policy_id": CANONICAL_PRICE_ALL_POLICY_ID,
        "source_aligned_reference_policy_id": SOURCE_ALIGNED_REFERENCE_POLICY_ID,
        "selection_policy_id": SELECTION_POLICY_ID,
        "counterfactual_policy_id": COUNTERFACTUAL_POLICY_ID,
        "coherence_policy_id": COHERENCE_POLICY_ID,
        "max_selected_per_fixture": MAX_SELECTED_PER_FIXTURE,
        "same_game_combination_authorized": SAME_GAME_COMBINATION_AUTHORIZED,
        "thresholds": {
            "minimum_prediction_confidence": MINIMUM_PREDICTION_CONFIDENCE,
            "minimum_decimal_odds": MINIMUM_DECIMAL_ODDS,
        },
        "confidence_methods": {
            "scalar": SCALAR_PREDICTION_CONFIDENCE_METHOD,
            "draw_no_bet": DNB_PREDICTION_CONFIDENCE_METHOD,
            "asian_handicap": AH_PREDICTION_CONFIDENCE_METHOD,
        },
        "coherence_relationships": list(_RELATIONSHIPS),
        "authority": dict(AUTHORITY),
    }


def calculate_canonical_market_router_contract_sha256() -> str:
    return _sha(_contract_payload())


EXPECTED_CONTRACT_SHA256 = "85b4b5c712154f7d4708eb53e9cadfcb7c65dc21bdb12cd94cf1b8cd48795e32"


def validate_canonical_market_router_contract() -> Mapping[str, Any]:
    try:
        v3 = _v3.validate_market_router_v3_contract()
        price = _price_all.validate_price_all_contract()
    except Exception as exc:
        raise CanonicalMarketRouterError("canonical Router dependency validation failed") from exc
    if v3["market_router_v3_contract_sha256"] != SOURCE_ROUTER_V3_CONTRACT_SHA256:
        raise CanonicalMarketRouterError("source Router v3 contract identity drifted")
    if price["policy_id"] != CANONICAL_PRICE_ALL_POLICY_ID:
        raise CanonicalMarketRouterError("canonical Price-all policy identity drifted")
    if price["implementation_contract_sha256"] != _v3.PRICE_ALL_V3_CONTRACT_SHA256:
        raise CanonicalMarketRouterError("canonical Price-all does not bind Router v3 pricing ancestry")
    actual = calculate_canonical_market_router_contract_sha256()
    if actual != EXPECTED_CONTRACT_SHA256:
        raise CanonicalMarketRouterError("canonical Router contract drifted")
    return types.MappingProxyType(
        {
            "canonical_market_router_contract_sha256": actual,
            "source_router_v3_contract_sha256": SOURCE_ROUTER_V3_CONTRACT_SHA256,
            "canonical_price_all_policy_id": CANONICAL_PRICE_ALL_POLICY_ID,
        }
    )


def _probability(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CanonicalMarketRouterError(f"{label} must be finite probability")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise CanonicalMarketRouterError(f"{label} must be in [0, 1]")
    return result


def _candidate_confidence(candidate: CalibratedValueCandidate) -> tuple[float, str]:
    if type(candidate) is not CalibratedValueCandidate:
        raise CanonicalMarketRouterError("exact calibrated value candidate is required")
    probabilities = dict(candidate.settlement_probabilities)
    names = tuple(name for name, _ in candidate.settlement_probabilities)
    if candidate.market_id is MarketId.DRAW_NO_BET:
        if names != DNB_SETTLEMENT_STATES:
            raise CanonicalMarketRouterError("DNB settlement confidence semantics drifted")
        values = {key: _probability(value, f"DNB {key}") for key, value in probabilities.items()}
        return values["WIN"] + values["PUSH"], DNB_PREDICTION_CONFIDENCE_METHOD
    if candidate.market_id is MarketId.ASIAN_HANDICAP:
        if names != AH_SETTLEMENT_STATES:
            raise CanonicalMarketRouterError("Asian Handicap settlement confidence semantics drifted")
        values = {key: _probability(value, f"AH {key}") for key, value in probabilities.items()}
        return (
            values["WIN"] + values["HALF_WIN"] + values["PUSH"],
            AH_PREDICTION_CONFIDENCE_METHOD,
        )
    unit = dict(candidate.calibration_unit)
    if unit.get("selection_outcome") is not None:
        if set(probabilities) != {"YES", "NO"}:
            raise CanonicalMarketRouterError("selection-specific scalar confidence semantics drifted")
        return (
            _probability(probabilities["YES"], "selection-specific model probability"),
            SCALAR_PREDICTION_CONFIDENCE_METHOD,
        )
    label = candidate.outcome_id.value
    if label not in probabilities:
        raise CanonicalMarketRouterError("candidate outcome is absent from scalar probability semantics")
    return _probability(probabilities[label], "model event probability"), SCALAR_PREDICTION_CONFIDENCE_METHOD


@dataclasses.dataclass(frozen=True)
class RouterVariant:
    candidate_id: str
    model_id: str
    calibration_artifact_sha256: str
    raw_probability_identity: str
    price_all_result_sha256: str
    disposition: str
    net_expected_value: float | None
    prediction_confidence: float
    prediction_confidence_method: str
    raw_model_edge: float | None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class RouterOpportunity:
    opportunity_id: str
    prediction_identity_sha256: str
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
    variants: tuple[RouterVariant, ...]
    robust_net_expected_value: float | None
    best_net_expected_value: float | None
    ev_spread: float | None
    event_probability_floor: float | None
    robust_edge: float | None
    prediction_confidence: float | None
    prediction_confidence_method: str | None
    model_agreement_status: ModelAgreementStatus
    context_gate_passed: bool
    route_source_freshness_passed: bool
    source_v3_eligibility: OpportunityEligibility
    eligibility: OpportunityEligibility
    rejection_reasons: tuple[str, ...]
    canonical_rank: int | None = None
    coherence_group_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "prediction_identity_sha256": self.prediction_identity_sha256,
            "fixture_id": self.fixture_id,
            "event_id": self.event_id,
            "market_id": self.market_id.value,
            "outcome_id": self.outcome_id.value,
            "line": self.line,
            "provider_market_id": self.provider_market_id,
            "provider_outcome_id": self.provider_outcome_id,
            "provider_specifier": self.provider_specifier,
            "provider_market_name": self.provider_market_name,
            "provider_outcome_name": self.provider_outcome_name,
            "decimal_odds": self.decimal_odds,
            "quote_sha256": self.quote_sha256,
            "quote_observed_at": None if self.quote_observed_at is None else self.quote_observed_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "router_quote_age_seconds": self.router_quote_age_seconds,
            "current_inventory_sha256": self.current_inventory_sha256,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "current_mapping_rebind_sha256": self.current_mapping_rebind_sha256,
            "current_mapping_contract_sha256": self.current_mapping_contract_sha256,
            "source_current_reconciliation_sha256": self.source_current_reconciliation_sha256,
            "source_legacy_mapping_sha256": self.source_legacy_mapping_sha256,
            "fair_probability": self.fair_probability,
            "variants": [item.to_dict() for item in self.variants],
            "robust_net_expected_value": self.robust_net_expected_value,
            "best_net_expected_value": self.best_net_expected_value,
            "ev_spread": self.ev_spread,
            "event_probability_floor": self.event_probability_floor,
            "robust_edge": self.robust_edge,
            "prediction_confidence": self.prediction_confidence,
            "prediction_confidence_method": self.prediction_confidence_method,
            "model_agreement_status": self.model_agreement_status.value,
            "context_gate_passed": self.context_gate_passed,
            "route_source_freshness_passed": self.route_source_freshness_passed,
            "source_v3_eligibility": self.source_v3_eligibility.value,
            "eligibility": self.eligibility.value,
            "rejection_reasons": list(self.rejection_reasons),
            "canonical_rank": self.canonical_rank,
            "coherence_group_ids": list(self.coherence_group_ids),
        }


@dataclasses.dataclass(frozen=True)
class CoherenceMemberDiagnostic:
    opportunity_id: str
    prediction_identity_sha256: str
    status: CoherenceMemberStatus
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "prediction_identity_sha256": self.prediction_identity_sha256,
            "status": self.status.value,
            "reason": self.reason,
        }


@dataclasses.dataclass(frozen=True)
class CoherenceGroup:
    coherence_group_id: str
    fixture_id: str
    relationship_id: str
    relationship_key: str
    opportunity_ids: tuple[str, ...]
    winner_opportunity_id: str | None
    runner_up_opportunity_id: str | None
    selected_opportunity_id: str | None
    joint_probability_supported: bool
    selection_limit: int
    members: tuple[CoherenceMemberDiagnostic, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "coherence_group_id": self.coherence_group_id,
            "fixture_id": self.fixture_id,
            "relationship_id": self.relationship_id,
            "relationship_key": self.relationship_key,
            "opportunity_ids": list(self.opportunity_ids),
            "winner_opportunity_id": self.winner_opportunity_id,
            "runner_up_opportunity_id": self.runner_up_opportunity_id,
            "selected_opportunity_id": self.selected_opportunity_id,
            "joint_probability_supported": self.joint_probability_supported,
            "selection_limit": self.selection_limit,
            "members": [item.to_dict() for item in self.members],
        }


@dataclasses.dataclass(frozen=True, init=False)
class RouterDecision:
    schema_version: int
    policy_id: str
    status: str
    proof_mode: str
    fixture_id: str
    event_id: str
    evaluation_time: datetime
    decision_status: RouterDecisionStatus
    decision_reasons: tuple[str, ...]
    selected_opportunity_id: str | None
    runner_up_opportunity_id: str | None
    strongest_counterfactual_opportunity_id: str | None
    opportunities: tuple[RouterOpportunity, ...]
    coherence_groups: tuple[CoherenceGroup, ...]
    price_all_evaluation_sha256: str
    source_router_v3_decision_sha256: str
    source_router_v3_contract_sha256: str
    source_router_v3_selected_opportunity_id: str | None
    source_router_v3_runner_up_opportunity_id: str | None
    source_router_v3_counterfactual_opportunity_id: str | None
    canonical_market_router_contract_sha256: str
    authority: Mapping[str, bool]
    _price_all_evaluation: _price_all.PriceAllEvaluation
    _fixture_state: FixtureStateV2Snapshot
    _source_decision: _v3.MarketRouterV3CurrentProviderDecision
    _require_live_current: bool

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise CanonicalMarketRouterError("canonical RouterDecision is builder-only")

    @property
    def selected_opportunity(self) -> RouterOpportunity | None:
        return next((item for item in self.opportunities if item.opportunity_id == self.selected_opportunity_id), None)

    @property
    def canonical_sha256(self) -> str:
        return _sha(self._identity_dict())

    @property
    def router_decision_id(self) -> str:
        return self.canonical_sha256

    def _identity_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "status": self.status,
            "proof_mode": self.proof_mode,
            "fixture_id": self.fixture_id,
            "event_id": self.event_id,
            "evaluation_time": self.evaluation_time.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "decision_status": self.decision_status.value,
            "decision_reasons": list(self.decision_reasons),
            "selected_opportunity_id": self.selected_opportunity_id,
            "runner_up_opportunity_id": self.runner_up_opportunity_id,
            "strongest_counterfactual_opportunity_id": self.strongest_counterfactual_opportunity_id,
            "opportunities": [item.to_dict() for item in self.opportunities],
            "coherence_groups": [item.to_dict() for item in self.coherence_groups],
            "price_all_evaluation_sha256": self.price_all_evaluation_sha256,
            "source_router_v3_decision_sha256": self.source_router_v3_decision_sha256,
            "source_router_v3_contract_sha256": self.source_router_v3_contract_sha256,
            "source_router_v3_selected_opportunity_id": self.source_router_v3_selected_opportunity_id,
            "source_router_v3_runner_up_opportunity_id": self.source_router_v3_runner_up_opportunity_id,
            "source_router_v3_counterfactual_opportunity_id": self.source_router_v3_counterfactual_opportunity_id,
            "canonical_market_router_contract_sha256": self.canonical_market_router_contract_sha256,
            "authority": dict(self.authority),
            "max_selected_per_fixture": MAX_SELECTED_PER_FIXTURE,
            "same_game_combination_authorized": SAME_GAME_COMBINATION_AUTHORIZED,
            "wager_placed": False,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._identity_dict()
        payload["router_decision_id"] = self.router_decision_id
        payload["canonical_sha256"] = self.canonical_sha256
        return payload


def _candidate_map(evaluation: Any) -> dict[str, CalibratedValueCandidate]:
    result: dict[str, CalibratedValueCandidate] = {}
    for row in evaluation.results:
        candidate = row.candidate
        if candidate.candidate_id in result:
            raise CanonicalMarketRouterError("duplicate candidate identity in verified Price-all evaluation")
        result[candidate.candidate_id] = candidate
    return result


def _project_opportunity(
    source: _v3.CurrentProviderRoutedOpportunity,
    candidates: Mapping[str, CalibratedValueCandidate],
) -> RouterOpportunity:
    confidence_values: list[float] = []
    confidence_methods: set[str] = set()
    variants: list[RouterVariant] = []
    confidence_error: str | None = None
    for variant in source.variants:
        candidate = candidates.get(variant.candidate_id)
        if candidate is None:
            confidence_error = "source Router variant candidate is absent from canonical Price-all evaluation"
            break
        try:
            confidence, method = _candidate_confidence(candidate)
        except CanonicalMarketRouterError as exc:
            confidence_error = str(exc)
            break
        confidence_values.append(confidence)
        confidence_methods.add(method)
        variants.append(
            RouterVariant(
                candidate_id=variant.candidate_id,
                model_id=variant.model_id,
                calibration_artifact_sha256=variant.calibration_artifact_sha256,
                raw_probability_identity=variant.raw_probability_identity,
                price_all_result_sha256=variant.price_all_result_sha256,
                disposition=variant.disposition,
                net_expected_value=variant.net_expected_value,
                prediction_confidence=confidence,
                prediction_confidence_method=method,
                raw_model_edge=variant.raw_model_edge,
            )
        )
    if confidence_error is None and len(variants) != len(source.variants):
        confidence_error = "canonical confidence projection did not cover every source Router variant"
    if confidence_error is None and len(confidence_methods) != 1:
        confidence_error = "source Router variants do not share one comparable confidence method"

    prediction_confidence = min(confidence_values) if confidence_error is None and confidence_values else None
    prediction_confidence_method = next(iter(confidence_methods)) if confidence_error is None and confidence_methods else None
    reasons = list(source.rejection_reasons)
    if source.eligibility is not OpportunityEligibility.ELIGIBLE:
        reasons.append("source Router v3 value/context eligibility did not pass")
    if confidence_error is not None:
        reasons.append(f"comparable prediction confidence unavailable: {confidence_error}")
    elif prediction_confidence is None:
        reasons.append("comparable prediction confidence unavailable")
    elif prediction_confidence < MINIMUM_PREDICTION_CONFIDENCE:
        reasons.append(f"prediction confidence {prediction_confidence} < {MINIMUM_PREDICTION_CONFIDENCE}")
    if source.decimal_odds is None:
        reasons.append("exact current decimal odds are unavailable")
    elif not math.isfinite(source.decimal_odds) or source.decimal_odds < MINIMUM_DECIMAL_ODDS:
        reasons.append(f"decimal odds {source.decimal_odds} < {MINIMUM_DECIMAL_ODDS}")
    reasons = list(dict.fromkeys(reasons))
    eligibility = OpportunityEligibility.ELIGIBLE if not reasons else OpportunityEligibility.REJECTED

    return RouterOpportunity(
        opportunity_id=source.opportunity_id,
        prediction_identity_sha256=_prediction_identity_sha256(source.fixture_id, source.market_id, source.outcome_id, source.line),
        fixture_id=source.fixture_id,
        event_id=source.event_id,
        market_id=source.market_id,
        outcome_id=source.outcome_id,
        line=source.line,
        provider_market_id=source.provider_market_id,
        provider_outcome_id=source.provider_outcome_id,
        provider_specifier=source.provider_specifier,
        provider_market_name=source.provider_market_name,
        provider_outcome_name=source.provider_outcome_name,
        decimal_odds=source.decimal_odds,
        quote_sha256=source.quote_sha256,
        quote_observed_at=source.quote_observed_at,
        router_quote_age_seconds=source.router_quote_age_seconds,
        current_inventory_sha256=source.current_inventory_sha256,
        source_manifest_sha256=source.source_manifest_sha256,
        source_raw_sha256=source.source_raw_sha256,
        current_mapping_rebind_sha256=source.current_mapping_rebind_sha256,
        current_mapping_contract_sha256=source.current_mapping_contract_sha256,
        source_current_reconciliation_sha256=source.source_current_reconciliation_sha256,
        source_legacy_mapping_sha256=source.source_legacy_mapping_sha256,
        fair_probability=source.fair_probability,
        variants=tuple(variants),
        robust_net_expected_value=source.robust_net_expected_value,
        best_net_expected_value=source.best_net_expected_value,
        ev_spread=source.ev_spread,
        event_probability_floor=source.event_probability_floor,
        robust_edge=source.robust_edge,
        prediction_confidence=prediction_confidence,
        prediction_confidence_method=prediction_confidence_method,
        model_agreement_status=source.model_agreement_status,
        context_gate_passed=source.context_gate_passed,
        route_source_freshness_passed=source.route_source_freshness_passed,
        source_v3_eligibility=source.eligibility,
        eligibility=eligibility,
        rejection_reasons=tuple(reasons),
    )


def _selection_rank_key(item: RouterOpportunity) -> tuple[Any, ...]:
    if item.eligibility is not OpportunityEligibility.ELIGIBLE:
        raise CanonicalMarketRouterError("selection rank key used for rejected opportunity")
    if item.robust_net_expected_value is None or not math.isfinite(item.robust_net_expected_value):
        raise CanonicalMarketRouterError("eligible opportunity lacks finite robust net expected value")
    if item.prediction_confidence is None or not math.isfinite(item.prediction_confidence):
        raise CanonicalMarketRouterError("eligible opportunity lacks comparable prediction confidence")
    return (
        -item.robust_net_expected_value,
        -item.prediction_confidence,
        _prediction_key(item.market_id, item.outcome_id, item.line),
    )


def _counterfactual_rank_key(item: RouterOpportunity) -> tuple[Any, ...]:
    robust = item.robust_net_expected_value
    confidence = item.prediction_confidence
    edge = item.robust_edge
    return (
        0 if robust is not None and math.isfinite(robust) else 1,
        -(robust if robust is not None and math.isfinite(robust) else 0.0),
        0 if confidence is not None and math.isfinite(confidence) else 1,
        -(confidence if confidence is not None and math.isfinite(confidence) else 0.0),
        0 if edge is not None and math.isfinite(edge) else 1,
        -(edge if edge is not None and math.isfinite(edge) else 0.0),
        _prediction_key(item.market_id, item.outcome_id, item.line),
    )


def _rank_opportunities(
    opportunities: Sequence[RouterOpportunity],
) -> tuple[tuple[RouterOpportunity, ...], list[RouterOpportunity], list[RouterOpportunity]]:
    eligible = [item for item in opportunities if item.eligibility is OpportunityEligibility.ELIGIBLE]
    identities: dict[str, str] = {}
    for item in eligible:
        if item.prediction_identity_sha256 in identities:
            raise CanonicalMarketRouterError("ambiguous canonical prediction identity across eligible priced opportunities")
        identities[item.prediction_identity_sha256] = item.opportunity_id
    eligible.sort(key=_selection_rank_key)
    ranks = {item.opportunity_id: rank for rank, item in enumerate(eligible, start=1)}
    ranked = tuple(dataclasses.replace(item, canonical_rank=ranks.get(item.opportunity_id)) for item in opportunities)
    eligible_ranked = sorted((item for item in ranked if item.eligibility is OpportunityEligibility.ELIGIBLE), key=_selection_rank_key)
    rejected_ranked = sorted((item for item in ranked if item.eligibility is OpportunityEligibility.REJECTED), key=_counterfactual_rank_key)
    return ranked, eligible_ranked, rejected_ranked


def _logical_event_atoms(item: RouterOpportunity) -> tuple[str, ...]:
    atoms: set[str] = set()
    if item.market_id is MarketId.MATCH_RESULT and item.outcome_id in {OutcomeId.HOME, OutcomeId.DRAW, OutcomeId.AWAY}:
        atoms.add(f"RESULT:{item.outcome_id.value}")
    elif item.market_id is MarketId.DOUBLE_CHANCE:
        atoms.update(
            {
                OutcomeId.HOME_OR_DRAW: ("RESULT:HOME", "RESULT:DRAW"),
                OutcomeId.DRAW_OR_AWAY: ("RESULT:DRAW", "RESULT:AWAY"),
                OutcomeId.HOME_OR_AWAY: ("RESULT:HOME", "RESULT:AWAY"),
            }.get(item.outcome_id, ())
        )
    elif item.outcome_id is OutcomeId.YES and item.market_id in {
        MarketId.DRAW_OR_OVER_2_5,
        MarketId.HOME_OR_OVER_2_5,
        MarketId.AWAY_OR_OVER_2_5,
    }:
        atoms.update(
            (
                {
                    MarketId.DRAW_OR_OVER_2_5: "RESULT:DRAW",
                    MarketId.HOME_OR_OVER_2_5: "RESULT:HOME",
                    MarketId.AWAY_OR_OVER_2_5: "RESULT:AWAY",
                }[item.market_id],
                "TOTALS:OVER:2.5",
            )
        )
    elif item.market_id is MarketId.TOTAL_GOALS and item.line == 2.5 and item.outcome_id is OutcomeId.OVER:
        atoms.add("TOTALS:OVER:2.5")
    elif item.outcome_id is OutcomeId.YES and item.market_id in {MarketId.HOME_WIN_TO_NIL, MarketId.AWAY_WIN_TO_NIL}:
        atoms.add("RESULT:HOME" if item.market_id is MarketId.HOME_WIN_TO_NIL else "RESULT:AWAY")
        atoms.add("BTTS:NO")
    elif item.market_id is MarketId.BTTS and item.outcome_id is OutcomeId.NO:
        atoms.add("BTTS:NO")
    return tuple(sorted(atoms))


def _relationship_for_atom(atom: str) -> str:
    if atom.startswith("RESULT:"):
        return "SHARED_REGULATION_RESULT_ATOM"
    if atom == "TOTALS:OVER:2.5":
        return "SHARED_TOTALS_OVER_2_5_ATOM"
    if atom == "BTTS:NO":
        return "SHARED_BTTS_NO_ATOM"
    raise CanonicalMarketRouterError("unknown logical coherence atom")


def _coherence_specs(
    opportunities: Sequence[RouterOpportunity],
) -> list[tuple[str, str, tuple[RouterOpportunity, ...]]]:
    by_atom: dict[str, list[RouterOpportunity]] = {}
    for item in opportunities:
        for atom in _logical_event_atoms(item):
            by_atom.setdefault(atom, []).append(item)
    specs: list[tuple[str, str, tuple[RouterOpportunity, ...]]] = []
    for atom, members in sorted(by_atom.items()):
        unique = {item.prediction_identity_sha256: item for item in members}
        if len(unique) >= 2:
            specs.append((_relationship_for_atom(atom), atom, tuple(unique.values())))
    for outcome, relation in (
        (OutcomeId.OVER, "NESTED_TOTAL_GOALS_OVER"),
        (OutcomeId.UNDER, "NESTED_TOTAL_GOALS_UNDER"),
    ):
        members = tuple(
            item for item in opportunities
            if item.market_id is MarketId.TOTAL_GOALS and item.outcome_id is outcome and item.line is not None
        )
        if len(members) >= 2 and len({_line_identity(item.line) for item in members}) >= 2:
            specs.append((relation, outcome.value, members))
    return specs


def _build_coherence_groups(
    opportunities: Sequence[RouterOpportunity], *, selected_opportunity_id: str | None
) -> tuple[CoherenceGroup, ...]:
    groups: list[CoherenceGroup] = []
    for relationship_id, relationship_key, raw_members in _coherence_specs(opportunities):
        members = tuple(sorted(raw_members, key=lambda item: item.prediction_identity_sha256))
        eligible = sorted((item for item in members if item.eligibility is OpportunityEligibility.ELIGIBLE), key=_selection_rank_key)
        winner = eligible[0].opportunity_id if eligible else None
        runner = eligible[1].opportunity_id if len(eligible) > 1 else None
        diagnostics: list[CoherenceMemberDiagnostic] = []
        for item in members:
            if item.eligibility is OpportunityEligibility.REJECTED:
                status = CoherenceMemberStatus.REJECTED
                reason = "; ".join(item.rejection_reasons) or "canonical Router eligibility rejected"
            elif item.opportunity_id == winner:
                status = CoherenceMemberStatus.WINNER
                reason = "highest canonical Router rank within this logical coherence group"
            elif item.opportunity_id == runner:
                status = CoherenceMemberStatus.RUNNER_UP
                reason = "second canonical Router rank within this logical coherence group"
            else:
                status = CoherenceMemberStatus.ELIGIBLE_LOWER_RANK
                reason = "eligible but lower canonical Router rank within this logical coherence group"
            diagnostics.append(CoherenceMemberDiagnostic(item.opportunity_id, item.prediction_identity_sha256, status, reason))
        group_id = _sha(
            {
                "fixture_id": members[0].fixture_id,
                "relationship_id": relationship_id,
                "relationship_key": relationship_key,
                "prediction_identity_sha256": sorted(item.prediction_identity_sha256 for item in members),
            }
        )
        groups.append(
            CoherenceGroup(
                coherence_group_id=group_id,
                fixture_id=members[0].fixture_id,
                relationship_id=relationship_id,
                relationship_key=relationship_key,
                opportunity_ids=tuple(item.opportunity_id for item in members),
                winner_opportunity_id=winner,
                runner_up_opportunity_id=runner,
                selected_opportunity_id=(
                    selected_opportunity_id
                    if selected_opportunity_id is not None and any(item.opportunity_id == selected_opportunity_id for item in members)
                    else None
                ),
                joint_probability_supported=False,
                selection_limit=MAX_SELECTED_PER_FIXTURE,
                members=tuple(diagnostics),
            )
        )
    return tuple(sorted(groups, key=lambda item: item.coherence_group_id))


def _bind_coherence_group_ids(
    opportunities: Sequence[RouterOpportunity], groups: Sequence[CoherenceGroup]
) -> tuple[RouterOpportunity, ...]:
    memberships: dict[str, list[str]] = {item.opportunity_id: [] for item in opportunities}
    for group in groups:
        for opportunity_id in group.opportunity_ids:
            memberships[opportunity_id].append(group.coherence_group_id)
    return tuple(
        dataclasses.replace(item, coherence_group_ids=tuple(sorted(memberships[item.opportunity_id])))
        for item in opportunities
    )


def _set_frozen(value: Any, fields: Mapping[str, Any]) -> Any:
    for name, field in fields.items():
        object.__setattr__(value, name, field)
    return value


def _project_decision(
    source: _v3.MarketRouterV3CurrentProviderDecision,
    *,
    canonical_price: _price_all.PriceAllEvaluation,
    fixture_state: FixtureStateV2Snapshot,
    require_live_current: bool,
) -> RouterDecision:
    if type(source) is not _v3.MarketRouterV3CurrentProviderDecision:
        raise CanonicalMarketRouterError("exact Router v3 decision is required")
    candidates = _candidate_map(_price_all.unwrap_v3_evaluation(canonical_price))
    projected = tuple(_project_opportunity(item, candidates) for item in source.opportunities)
    ranked, eligible, rejected = _rank_opportunities(projected)
    if eligible:
        decision_status = RouterDecisionStatus.SELECTED
        selected = eligible[0].opportunity_id
        runner = eligible[1].opportunity_id if len(eligible) > 1 else None
        counterfactual = rejected[0].opportunity_id if rejected else runner
        decision_reasons = ("highest settlement-aware value then comparable-confidence opportunity selected",)
    else:
        decision_status = RouterDecisionStatus.NO_BET
        selected = None
        runner = None
        counterfactual = min(ranked, key=_counterfactual_rank_key).opportunity_id if ranked else None
        decision_reasons = (
            tuple(source.decision_reasons)
            if source.decision_status is RouterDecisionStatus.NO_BET and source.decision_reasons
            else ("no opportunity cleared canonical Router eligibility",)
        )
    groups = _build_coherence_groups(ranked, selected_opportunity_id=selected)
    ranked = _bind_coherence_group_ids(ranked, groups)
    contracts = validate_canonical_market_router_contract()
    value = object.__new__(RouterDecision)
    return _set_frozen(
        value,
        {
            "schema_version": SCHEMA_VERSION,
            "policy_id": POLICY_ID,
            "status": "CANONICAL_ROUTER_LIVE_VERIFIED" if require_live_current else "CANONICAL_ROUTER_AS_OF_VERIFIED",
            "proof_mode": source.proof_mode,
            "fixture_id": source.fixture_id,
            "event_id": source.event_id,
            "evaluation_time": source.evaluation_time,
            "decision_status": decision_status,
            "decision_reasons": decision_reasons,
            "selected_opportunity_id": selected,
            "runner_up_opportunity_id": runner,
            "strongest_counterfactual_opportunity_id": counterfactual,
            "opportunities": ranked,
            "coherence_groups": groups,
            "price_all_evaluation_sha256": canonical_price.canonical_sha256,
            "source_router_v3_decision_sha256": source.canonical_sha256,
            "source_router_v3_contract_sha256": SOURCE_ROUTER_V3_CONTRACT_SHA256,
            "source_router_v3_selected_opportunity_id": source.selected_opportunity_id,
            "source_router_v3_runner_up_opportunity_id": source.runner_up_opportunity_id,
            "source_router_v3_counterfactual_opportunity_id": source.strongest_counterfactual_opportunity_id,
            "canonical_market_router_contract_sha256": contracts["canonical_market_router_contract_sha256"],
            "authority": types.MappingProxyType(dict(AUTHORITY)),
            "_price_all_evaluation": canonical_price,
            "_fixture_state": fixture_state,
            "_source_decision": source,
            "_require_live_current": require_live_current,
        },
    )


def route(
    price_all_evaluation: _price_all.PriceAllEvaluation,
    *,
    fixture_state: FixtureStateV2Snapshot,
    evaluation_time: datetime,
) -> RouterDecision:
    """Route a verified canonical PriceAllEvaluation at an explicit replay time."""
    validate_canonical_market_router_contract()
    if type(price_all_evaluation) is not _price_all.PriceAllEvaluation:
        raise CanonicalMarketRouterError("exact canonical PriceAllEvaluation is required")
    if type(fixture_state) is not FixtureStateV2Snapshot:
        raise CanonicalMarketRouterError("exact Fixture State v2 snapshot is required")
    now = _utc(evaluation_time, "evaluation_time")
    try:
        canonical_price = _price_all.verify_price_all_evaluation(price_all_evaluation)
        source = _v3.route_price_all_v3_current_provider_as_of(
            _price_all.unwrap_v3_evaluation(canonical_price),
            fixture_state=fixture_state,
            evaluation_time=now,
        )
    except Exception as exc:
        if isinstance(exc, CanonicalMarketRouterError):
            raise
        raise CanonicalMarketRouterError("canonical Router source reconstruction failed") from exc
    return _project_decision(source, canonical_price=canonical_price, fixture_state=fixture_state, require_live_current=False)


def route_current(
    price_all_evaluation: _price_all.PriceAllEvaluation,
    *,
    fixture_state: FixtureStateV2Snapshot,
) -> RouterDecision:
    """Route exact LIVE_CURRENT canonical Price-all ancestry using Router-v3 clock ownership."""
    validate_canonical_market_router_contract()
    if type(price_all_evaluation) is not _price_all.PriceAllEvaluation:
        raise CanonicalMarketRouterError("exact canonical PriceAllEvaluation is required")
    if type(fixture_state) is not FixtureStateV2Snapshot:
        raise CanonicalMarketRouterError("exact Fixture State v2 snapshot is required")
    try:
        canonical_price = _price_all.verify_price_all_evaluation(price_all_evaluation)
        source = _v3.route_price_all_v3_current_provider(
            _price_all.unwrap_v3_evaluation(canonical_price), fixture_state=fixture_state
        )
    except Exception as exc:
        if isinstance(exc, CanonicalMarketRouterError):
            raise
        raise CanonicalMarketRouterError("canonical live Router source reconstruction failed") from exc
    return _project_decision(source, canonical_price=canonical_price, fixture_state=fixture_state, require_live_current=True)


def verify_router_decision(value: Any) -> RouterDecision:
    """Rebuild from exact canonical Price-all / source Router evidence and reject drift."""
    if type(value) is not RouterDecision:
        raise CanonicalMarketRouterError("exact canonical RouterDecision is required")
    try:
        canonical_price = _price_all.verify_price_all_evaluation(value._price_all_evaluation)
        source = _v3.verify_market_router_v3_current_provider_decision(value._source_decision)
    except Exception as exc:
        raise CanonicalMarketRouterError("canonical Router source verification failed") from exc
    if source.price_all_evaluation.canonical_sha256 != _price_all.unwrap_v3_evaluation(canonical_price).canonical_sha256:
        raise CanonicalMarketRouterError("source Router decision is not bound to the canonical Price-all evaluation")
    if value._require_live_current and source.proof_mode != _price_all.LIVE_CURRENT:
        raise CanonicalMarketRouterError("recorded live Router decision lacks LIVE_CURRENT ancestry")
    rebuilt = _project_decision(
        source,
        canonical_price=canonical_price,
        fixture_state=value._fixture_state,
        require_live_current=value._require_live_current,
    )
    if rebuilt.to_dict() != value.to_dict():
        raise CanonicalMarketRouterError("canonical Router decision differs from exact source reconstruction")
    return rebuilt


__all__ = [
    "AH_PREDICTION_CONFIDENCE_METHOD",
    "AUTHORITY",
    "CANONICAL_TARGET_MODULE",
    "CanonicalMarketRouterError",
    "CoherenceGroup",
    "CoherenceMemberDiagnostic",
    "CoherenceMemberStatus",
    "DNB_PREDICTION_CONFIDENCE_METHOD",
    "EXPECTED_CONTRACT_SHA256",
    "IMPLEMENTATION_ID",
    "MAX_SELECTED_PER_FIXTURE",
    "MINIMUM_DECIMAL_ODDS",
    "MINIMUM_PREDICTION_CONFIDENCE",
    "POLICY_ID",
    "RouterDecision",
    "RouterOpportunity",
    "RouterVariant",
    "SAME_GAME_COMBINATION_AUTHORIZED",
    "SCALAR_PREDICTION_CONFIDENCE_METHOD",
    "SCHEMA_VERSION",
    "SOURCE_ROUTER_V3_CONTRACT_SHA256",
    "calculate_canonical_market_router_contract_sha256",
    "route",
    "route_current",
    "validate_canonical_market_router_contract",
    "verify_router_decision",
]
