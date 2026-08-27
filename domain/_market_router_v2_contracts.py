"""Frozen contract for ATHENA Market Router v2 direct-provider value consumption."""
from __future__ import annotations

import hashlib
import json
import math
import types
from typing import Any, Mapping

from domain import price_all_v2_direct_provider as price_v2
from domain._market_router_contracts import (
    CONTEXT_QUALIFICATION_POLICY_ID,
    CONTEXT_RISK_METHOD,
    MINIMUM_EVENT_PROBABILITY,
    MINIMUM_NET_EXPECTED_VALUE,
    MINIMUM_REVIEWED_CONTEXT_COMPLETENESS,
    MINIMUM_ROBUST_EDGE,
    MINIMUM_ROBUST_NET_EXPECTED_VALUE,
    MarketRouterError,
    ModelAgreementStatus,
    OpportunityEligibility,
    RouterDecisionStatus,
    validate_market_router_contract,
)
from domain.fixture_state_v2 import (
    FIXTURE_STATE_FIELD_REGISTRY_SHA256,
    FIXTURE_STATE_FIELD_REGISTRY_VERSION,
)

SCHEMA_VERSION = 1
CONTRACT_VERSION = 1
DATASET_NAME = "athena-market-router-v2-direct-provider-value-consumption-v1"
STATUS = "MARKET_ROUTER_V2_DIRECT_PROVIDER_VALUE_CONSUMPTION_VERIFIED"
PRICE_ALL_V2_CONTRACT_SHA256 = price_v2.EXPECTED_CONTRACT_SHA256
LEGACY_MARKET_ROUTER_V1_CONTRACT_SHA256 = (
    "0e4486527b060109852ab56dd76774b2d150cf8326875e44537a3bce2dc656bf"
)
SOURCE_RECONSTRUCTION_POLICY_ID = "VERIFY_EXACT_PRICE_ALL_V2_EVALUATION_BEFORE_ROUTING_V1"
ROUTE_TIME_FRESHNESS_POLICY_ID = (
    "RECHECK_DIRECT_PROVIDER_SOURCE_AGE_AND_KICKOFF_LEAD_AT_ROUTER_TIME_V1"
)
ROBUST_VALUE_POLICY_ID = "DIRECT_PROVIDER_CANONICAL_OPPORTUNITY_WORST_MODEL_NET_EV_V2"
ROBUST_EDGE_POLICY_ID = "MIN_EVENT_PROBABILITY_MINUS_DIRECT_PROVIDER_FAIR_PROBABILITY_V2"
MODEL_AGREEMENT_POLICY_ID = "EXACT_DIRECT_PROVIDER_OPPORTUNITY_MULTI_MODEL_LOWER_ENVELOPE_V2"
NO_BET_POLICY_ID = "NO_ELIGIBLE_DIRECT_PROVIDER_ROBUST_POSITIVE_VALUE_IS_SUCCESSFUL_NO_BET_V2"
COUNTERFACTUAL_POLICY_ID = "PRESERVE_RUNNER_UP_AND_STRONGEST_REJECTED_V2"
TIE_BREAK_POLICY_ID = (
    "ROBUST_EV_DESC_EDGE_DESC_WHERE_AVAILABLE_EVENT_FLOOR_DESC_ROUTE_QUOTE_AGE_ASC_ID_ASC_V2"
)
UNCERTAINTY_STATUS = "DETERMINISTIC_ROUTER_V2_NO_LEARNED_UNCERTAINTY_META_MODEL"
NEXT_BOUNDARY = "PORTFOLIO_OPTIMIZER_V2_DIRECT_PROVIDER_ROUTER_CONSUMPTION_REQUIRED"
EXPECTED_CONTRACT_SHA256 = "071d1246ee285634af5598b66872fb27c683f2d13ab14dc25b31de90b72195de"

AUTHORITY = types.MappingProxyType(
    {
        "verified_direct_provider_value_consumption": True,
        "source_freshness_recheck": True,
        "market_routing": True,
        "fixture_market_selection": True,
        "counterfactual_recording": True,
        "football_probability_generation": False,
        "calibration": False,
        "value_record_computation": False,
        "model_promotion": False,
        "final_selection": False,
        "portfolio_optimization": False,
        "accumulator": False,
        "sportybet_execution": False,
        "staking": False,
        "bet": False,
    }
)


class MarketRouterV2DirectProviderError(ValueError):
    """Raised when the Router v2 direct-provider boundary fails closed."""


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise MarketRouterV2DirectProviderError(
            "canonical JSON serialization failed"
        ) from exc


def contract_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "status": STATUS,
        "price_all_v2_contract_sha256": PRICE_ALL_V2_CONTRACT_SHA256,
        "legacy_market_router_v1_contract_sha256": LEGACY_MARKET_ROUTER_V1_CONTRACT_SHA256,
        "fixture_state_field_registry_version": FIXTURE_STATE_FIELD_REGISTRY_VERSION,
        "fixture_state_field_registry_sha256": FIXTURE_STATE_FIELD_REGISTRY_SHA256,
        "source_reconstruction_policy_id": SOURCE_RECONSTRUCTION_POLICY_ID,
        "route_time_freshness_policy_id": ROUTE_TIME_FRESHNESS_POLICY_ID,
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
            "comparison": (
                "STRICTLY_GREATER_FOR_EV_AND_EDGE;"
                "GREATER_OR_EQUAL_FOR_EVENT_PROBABILITY"
            ),
        },
        "upstream_effective_freshness_policy": (
            "PRESERVE_PRICE_ALL_V2_MAX_AGE_AND_MINIMUM_LEAD_WITHOUT_WEAKENING"
        ),
        "next_boundary": NEXT_BOUNDARY,
        "authority": dict(AUTHORITY),
    }


def calculate_market_router_v2_contract_sha256() -> str:
    return hashlib.sha256(
        _canonical_bytes(
            {"version": CONTRACT_VERSION, "semantics": contract_payload()}
        )
    ).hexdigest()


def validate_market_router_v2_contract() -> Mapping[str, str]:
    try:
        price_contracts = price_v2.validate_price_all_v2_contract()
        legacy_router = validate_market_router_contract()
    except (price_v2.PriceAllV2DirectProviderError, MarketRouterError) as exc:
        raise MarketRouterV2DirectProviderError(
            "Router v2 dependency validation failed"
        ) from exc
    if (
        price_contracts["price_all_v2_contract_sha256"]
        != PRICE_ALL_V2_CONTRACT_SHA256
    ):
        raise MarketRouterV2DirectProviderError(
            "Price-all v2 direct-provider contract identity drifted"
        )
    if (
        legacy_router["market_router_contract_sha256"]
        != LEGACY_MARKET_ROUTER_V1_CONTRACT_SHA256
    ):
        raise MarketRouterV2DirectProviderError(
            "legacy Market Router v1 policy identity drifted"
        )
    if FIXTURE_STATE_FIELD_REGISTRY_VERSION != 1:
        raise MarketRouterV2DirectProviderError(
            "Fixture State v2 registry version drifted"
        )
    if FIXTURE_STATE_FIELD_REGISTRY_SHA256 != (
        "330e81a3fd8dc88c8fee98544d7f63e9d429c43c5d32ca761da5227e34de588a"
    ):
        raise MarketRouterV2DirectProviderError(
            "Fixture State v2 registry identity drifted"
        )
    for value, label in (
        (MINIMUM_EVENT_PROBABILITY, "minimum event probability"),
        (MINIMUM_REVIEWED_CONTEXT_COMPLETENESS, "minimum context completeness"),
    ):
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise MarketRouterV2DirectProviderError(f"{label} drifted outside [0,1]")
    actual = calculate_market_router_v2_contract_sha256()
    if actual != EXPECTED_CONTRACT_SHA256:
        raise MarketRouterV2DirectProviderError(
            "Market Router v2 direct-provider contract drifted"
        )
    return types.MappingProxyType(
        {
            "price_all_v2_contract_sha256": price_contracts[
                "price_all_v2_contract_sha256"
            ],
            "legacy_market_router_v1_contract_sha256": legacy_router[
                "market_router_contract_sha256"
            ],
            "fixture_state_field_registry_sha256": FIXTURE_STATE_FIELD_REGISTRY_SHA256,
            "market_router_v2_contract_sha256": actual,
        }
    )


__all__ = [name for name in globals() if not name.startswith("_")]
