"""Frozen contracts for ATHENA Phase 8 Market Router v1."""
from __future__ import annotations

from enum import Enum
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Mapping

from domain._price_all_contracts import validate_price_all_contract
from domain.fixture_state_v2 import (
    FIXTURE_STATE_FIELD_REGISTRY_SHA256,
    FIXTURE_STATE_FIELD_REGISTRY_VERSION,
)

MARKET_ROUTER_DATASET = "athena_market_router_v1"
MARKET_ROUTER_SCHEMA_VERSION = 1
MARKET_ROUTER_CONTRACT_VERSION = 1

MINIMUM_EVENT_PROBABILITY = 0.55
MINIMUM_NET_EXPECTED_VALUE = 0.0
MINIMUM_ROBUST_NET_EXPECTED_VALUE = 0.0
MINIMUM_ROBUST_EDGE = 0.0
MINIMUM_REVIEWED_CONTEXT_COMPLETENESS = 1.0

PRICE_BEFORE_ROUTE_POLICY_ID = "ALL_EXACT_PHASE7_CANDIDATES_PRICE_BEFORE_ROUTE_V1"
ROBUST_VALUE_POLICY_ID = "CANONICAL_OPPORTUNITY_WORST_MODEL_NET_EV_V1"
ROBUST_EDGE_POLICY_ID = "MIN_EVENT_PROBABILITY_MINUS_PHASE7_FAIR_PROBABILITY_V1"
MODEL_AGREEMENT_POLICY_ID = "EXACT_OPPORTUNITY_MULTI_MODEL_LOWER_ENVELOPE_V1"
CONTEXT_QUALIFICATION_POLICY_ID = "STRICT_CURRENTLY_MAPPABLE_FIXTURE_STATE_COMPLETE_V1"
CONTEXT_RISK_METHOD = "STRICT_EVIDENCE_GATE_NO_LEARNED_NUMERIC_BUFFER_V1"
UNCERTAINTY_STATUS = "DETERMINISTIC_ROUTER_V1_NO_LEARNED_UNCERTAINTY_META_MODEL"
NO_BET_POLICY_ID = "NO_ELIGIBLE_ROBUST_POSITIVE_VALUE_IS_SUCCESSFUL_NO_BET_V1"
COUNTERFACTUAL_POLICY_ID = "PRESERVE_RUNNER_UP_AND_STRONGEST_REJECTED_V1"
TIE_BREAK_POLICY_ID = (
    "ROBUST_EV_DESC_EDGE_DESC_WHERE_AVAILABLE_EVENT_FLOOR_DESC_QUOTE_AGE_ASC_ID_ASC_V1"
)
REAL_CURRENT_MARKET_ROUTER_STATUS = "NOT_RUN_VERIFIED_CURRENT_ROUTING_CORPUS_UNAVAILABLE"

AUTHORITY_FLAGS = MappingProxyType({
    "market_routing": True,
    "fixture_market_selection": True,
    "counterfactual_recording": True,
    "football_probability_generation": False,
    "calibration": False,
    "bookmaker_pricing": False,
    "accumulator": False,
    "slip_construction": False,
    "booking_code_generation": False,
    "bookmaker_execution": False,
    "production_approval": False,
    "bet": False,
})


class MarketRouterError(ValueError):
    """Raised when the Market Router input or frozen contract fails closed."""


class RouterDecisionStatus(str, Enum):
    SELECTED = "SELECTED"
    NO_BET = "NO_BET"


class OpportunityEligibility(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    REJECTED = "REJECTED"


class ModelAgreementStatus(str, Enum):
    SINGLE_MODEL_NO_DISAGREEMENT_EVIDENCE = "SINGLE_MODEL_NO_DISAGREEMENT_EVIDENCE"
    MULTI_MODEL_COMPATIBLE_LOWER_ENVELOPE = "MULTI_MODEL_COMPATIBLE_LOWER_ENVELOPE"
    INCOMPATIBLE_MODEL_SEMANTICS = "INCOMPATIBLE_MODEL_SEMANTICS"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def market_router_contract_payload(
    *,
    price_all_contract_sha256: str,
    canonical_market_semantics_sha256: str,
) -> dict[str, Any]:
    return {
        "dataset": MARKET_ROUTER_DATASET,
        "schema_version": MARKET_ROUTER_SCHEMA_VERSION,
        "price_all_contract_sha256": price_all_contract_sha256,
        "fixture_state_field_registry_version": FIXTURE_STATE_FIELD_REGISTRY_VERSION,
        "fixture_state_field_registry_sha256": FIXTURE_STATE_FIELD_REGISTRY_SHA256,
        "canonical_market_semantics_sha256": canonical_market_semantics_sha256,
        "price_before_route_policy_id": PRICE_BEFORE_ROUTE_POLICY_ID,
        "robust_value_policy_id": ROBUST_VALUE_POLICY_ID,
        "robust_edge_policy_id": ROBUST_EDGE_POLICY_ID,
        "model_agreement_policy_id": MODEL_AGREEMENT_POLICY_ID,
        "context_qualification_policy_id": CONTEXT_QUALIFICATION_POLICY_ID,
        "context_risk_method": CONTEXT_RISK_METHOD,
        "uncertainty_status": UNCERTAINTY_STATUS,
        "no_bet_policy_id": NO_BET_POLICY_ID,
        "counterfactual_policy_id": COUNTERFACTUAL_POLICY_ID,
        "tie_break_policy_id": TIE_BREAK_POLICY_ID,
        "thresholds": {
            "minimum_event_probability": MINIMUM_EVENT_PROBABILITY,
            "minimum_net_expected_value": MINIMUM_NET_EXPECTED_VALUE,
            "minimum_robust_net_expected_value": MINIMUM_ROBUST_NET_EXPECTED_VALUE,
            "minimum_robust_edge": MINIMUM_ROBUST_EDGE,
            "minimum_reviewed_context_completeness": MINIMUM_REVIEWED_CONTEXT_COMPLETENESS,
            "comparison": "STRICTLY_GREATER_FOR_EV_AND_EDGE;GREATER_OR_EQUAL_FOR_EVENT_PROBABILITY",
        },
        "authority_flags": dict(AUTHORITY_FLAGS),
        "real_current_market_router_status": REAL_CURRENT_MARKET_ROUTER_STATUS,
    }


def calculate_market_router_contract_sha256(
    *,
    price_all_contract_sha256: str,
    canonical_market_semantics_sha256: str,
    version: int = MARKET_ROUTER_CONTRACT_VERSION,
) -> str:
    payload = {
        "version": version,
        "semantics": market_router_contract_payload(
            price_all_contract_sha256=price_all_contract_sha256,
            canonical_market_semantics_sha256=canonical_market_semantics_sha256,
        ),
    }
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


EXPECTED_MARKET_ROUTER_CONTRACT_SHA256_BY_VERSION: Mapping[int, str] = MappingProxyType({
    1: "0e4486527b060109852ab56dd76774b2d150cf8326875e44537a3bce2dc656bf",
})


def validate_market_router_contract() -> Mapping[str, str]:
    upstream = validate_price_all_contract()
    price_sha = upstream["price_all_contract_sha256"]
    market_sha = upstream["canonical_market_semantics_sha256"]
    if FIXTURE_STATE_FIELD_REGISTRY_VERSION != 1:
        raise MarketRouterError("Fixture State v2 registry version drifted")
    if FIXTURE_STATE_FIELD_REGISTRY_SHA256 != (
        "330e81a3fd8dc88c8fee98544d7f63e9d429c43c5d32ca761da5227e34de588a"
    ):
        raise MarketRouterError("Fixture State v2 registry identity drifted")
    for value, label in (
        (MINIMUM_EVENT_PROBABILITY, "minimum event probability"),
        (MINIMUM_REVIEWED_CONTEXT_COMPLETENESS, "minimum context completeness"),
    ):
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise MarketRouterError(f"{label} drifted outside [0,1]")
    actual = calculate_market_router_contract_sha256(
        price_all_contract_sha256=price_sha,
        canonical_market_semantics_sha256=market_sha,
    )
    expected = EXPECTED_MARKET_ROUTER_CONTRACT_SHA256_BY_VERSION.get(
        MARKET_ROUTER_CONTRACT_VERSION
    )
    if expected is None or actual != expected:
        raise MarketRouterError("Market Router v1 contract drift")
    return MappingProxyType({
        "price_all_contract_sha256": price_sha,
        "fixture_state_field_registry_sha256": FIXTURE_STATE_FIELD_REGISTRY_SHA256,
        "canonical_market_semantics_sha256": market_sha,
        "market_router_contract_sha256": actual,
    })


__all__ = [name for name in globals() if not name.startswith("_")]
