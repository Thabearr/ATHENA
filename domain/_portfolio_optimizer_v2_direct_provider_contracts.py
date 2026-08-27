"""Frozen contract for ATHENA Portfolio Optimizer v2 direct-provider Router consumption."""
from __future__ import annotations

import hashlib
import json
import math
import types
from typing import Any, Mapping

from domain import sportybet_fotmob_full_utc_reconciliation as reconciliation
from domain import sportybet_fotmob_full_utc_reconciliation_receipt as reconciliation_receipt
from domain import _accumulator_optimizer_contracts as legacy
from domain import _market_router_v2_contracts as router_v2_contracts

SCHEMA_VERSION = 1
CONTRACT_VERSION = 1
DATASET_NAME = "athena-portfolio-optimizer-v2-direct-provider-router-consumption-v1"
STATUS = "PORTFOLIO_OPTIMIZER_V2_DIRECT_PROVIDER_ROUTER_CONSUMPTION_VERIFIED"

MARKET_ROUTER_V2_CONTRACT_SHA256 = router_v2_contracts.EXPECTED_CONTRACT_SHA256
LEGACY_ACCUMULATOR_OPTIMIZER_V2_CONTRACT_SHA256 = (
    "de6578c1a21370a1859901a73e4d3993d1544a66cb0f09384a45a8233a5ce253"
)

MAXIMUM_TARGET_SIZE = legacy.MAXIMUM_TARGET_SIZE
MAXIMUM_TEAM_APPEARANCES = legacy.MAXIMUM_TEAM_APPEARANCES
MAXIMUM_COMPETITION_SHARE = legacy.MAXIMUM_COMPETITION_SHARE
MINIMUM_COMPETITION_CAP_WHEN_TARGET_GE_2 = (
    legacy.MINIMUM_COMPETITION_CAP_WHEN_TARGET_GE_2
)
MAXIMUM_MARKET_FAMILY_SHARE = legacy.MAXIMUM_MARKET_FAMILY_SHARE
MINIMUM_MARKET_FAMILY_CAP_WHEN_TARGET_GE_2 = (
    legacy.MINIMUM_MARKET_FAMILY_CAP_WHEN_TARGET_GE_2
)
MAXIMUM_FRAGILE_SHARE = legacy.MAXIMUM_FRAGILE_SHARE
MINIMUM_FRAGILE_CAP = legacy.MINIMUM_FRAGILE_CAP
MINIMUM_ROBUST_NET_EXPECTED_VALUE_FOR_NON_FRAGILE = (
    legacy.MINIMUM_ROBUST_NET_EXPECTED_VALUE_FOR_NON_FRAGILE
)
MINIMUM_SURVIVAL_FLOOR_FOR_NON_FRAGILE = (
    legacy.MINIMUM_SURVIVAL_FLOOR_FOR_NON_FRAGILE
)

ROUTER_DECISION_RECONSTRUCTION_POLICY_ID = (
    "VERIFY_EXACT_MARKET_ROUTER_V2_DECISION_BEFORE_PORTFOLIO_ADMISSION_V1"
)
FIXTURE_EXPOSURE_IDENTITY_POLICY_ID = (
    "DIRECT_PROVIDER_ROUTER_RECONCILIATION_SHA_MATCH_"
    "SOURCE_REPLAYED_FULL_UTC_RECEIPT_V1"
)
PORTFOLIO_TIME_FRESHNESS_POLICY_ID = (
    "RECHECK_DIRECT_PROVIDER_SOURCE_AGE_AND_KICKOFF_LEAD_AT_PORTFOLIO_TIME_V1"
)
JOINT_SELECTION_POLICY_ID = legacy.JOINT_SELECTION_POLICY_ID
CORRELATION_POLICY_ID = legacy.CORRELATION_POLICY_ID
SURVIVAL_POLICY_ID = legacy.SURVIVAL_POLICY_ID
RESERVE_POLICY_ID = legacy.RESERVE_POLICY_ID
SHORTFALL_POLICY_ID = legacy.SHORTFALL_POLICY_ID
FRAGILITY_POLICY_ID = legacy.FRAGILITY_POLICY_ID
FRAGILITY_THRESHOLD_STATUS = legacy.FRAGILITY_THRESHOLD_STATUS
JOINT_DEPENDENCE_STATUS = legacy.JOINT_DEPENDENCE_STATUS

NEXT_BOUNDARY = (
    "SPORTYBET_CURRENT_EVENT_DISCOVERY_AND_FIXTURE_RECONCILIATION_REQUIRED"
)
EXPECTED_CONTRACT_SHA256 = (
    "919149759ffc9aabef2fefe7c6e0db72d697ebd1ffe33205054fc3ffb4f785fd"
)

AUTHORITY = types.MappingProxyType(
    {
        "verified_direct_provider_router_consumption": True,
        "router_decision_reconstruction": True,
        "portfolio_time_freshness_recheck": True,
        "portfolio_optimization": True,
        "qualified_leg_set": True,
        "reserve_leg_recording": True,
        "final_cross_fixture_selection": True,
        "football_probability_generation": False,
        "calibration": False,
        "value_record_computation": False,
        "market_routing": False,
        "model_promotion": False,
        "statistical_joint_dependence_model": False,
        "accumulator_slip_construction": False,
        "sportybet_execution": False,
        "staking": False,
        "bet": False,
    }
)

PortfolioOptimizationStatus = legacy.AccumulatorOptimizationStatus
FragilityStatus = legacy.FragilityStatus


class PortfolioOptimizerV2DirectProviderError(ValueError):
    """Raised when the direct-provider Portfolio Optimizer v2 fails closed."""


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
        raise PortfolioOptimizerV2DirectProviderError(
            "canonical JSON serialization failed"
        ) from exc


def contract_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "status": STATUS,
        "market_router_v2_contract_sha256": MARKET_ROUTER_V2_CONTRACT_SHA256,
        "legacy_accumulator_optimizer_v2_contract_sha256": (
            LEGACY_ACCUMULATOR_OPTIMIZER_V2_CONTRACT_SHA256
        ),
        "sportybet_fotmob_reconciliation_dataset": reconciliation.DATASET_NAME,
        "sportybet_fotmob_reconciliation_schema_version": reconciliation.SCHEMA_VERSION,
        "sportybet_fotmob_reconciliation_receipt_dataset": (
            reconciliation_receipt.DATASET_NAME
        ),
        "sportybet_fotmob_reconciliation_receipt_schema_version": (
            reconciliation_receipt.SCHEMA_VERSION
        ),
        "router_decision_reconstruction_policy_id": (
            ROUTER_DECISION_RECONSTRUCTION_POLICY_ID
        ),
        "fixture_exposure_identity_policy_id": FIXTURE_EXPOSURE_IDENTITY_POLICY_ID,
        "portfolio_time_freshness_policy_id": PORTFOLIO_TIME_FRESHNESS_POLICY_ID,
        "joint_selection_policy_id": JOINT_SELECTION_POLICY_ID,
        "correlation_policy_id": CORRELATION_POLICY_ID,
        "survival_policy_id": SURVIVAL_POLICY_ID,
        "reserve_policy_id": RESERVE_POLICY_ID,
        "shortfall_policy_id": SHORTFALL_POLICY_ID,
        "fragility_policy_id": FRAGILITY_POLICY_ID,
        "joint_dependence_status": JOINT_DEPENDENCE_STATUS,
        "maximum_target_size": MAXIMUM_TARGET_SIZE,
        "caps": {
            "maximum_team_appearances": MAXIMUM_TEAM_APPEARANCES,
            "maximum_competition_share": MAXIMUM_COMPETITION_SHARE,
            "minimum_competition_cap_when_target_ge_2": (
                MINIMUM_COMPETITION_CAP_WHEN_TARGET_GE_2
            ),
            "maximum_market_family_share": MAXIMUM_MARKET_FAMILY_SHARE,
            "minimum_market_family_cap_when_target_ge_2": (
                MINIMUM_MARKET_FAMILY_CAP_WHEN_TARGET_GE_2
            ),
            "maximum_fragile_share": MAXIMUM_FRAGILE_SHARE,
            "minimum_fragile_cap": MINIMUM_FRAGILE_CAP,
        },
        "fragility_thresholds": {
            "minimum_robust_net_expected_value_for_non_fragile": (
                MINIMUM_ROBUST_NET_EXPECTED_VALUE_FOR_NON_FRAGILE
            ),
            "minimum_survival_floor_for_non_fragile": (
                MINIMUM_SURVIVAL_FLOOR_FOR_NON_FRAGILE
            ),
            "comparison": "FRAGILE_IF_EITHER_VALUE_IS_STRICTLY_BELOW_THRESHOLD",
            "status": FRAGILITY_THRESHOLD_STATUS,
        },
        "next_boundary": NEXT_BOUNDARY,
        "authority": dict(AUTHORITY),
    }


def calculate_portfolio_optimizer_v2_contract_sha256() -> str:
    return hashlib.sha256(
        _canonical_bytes(
            {"version": CONTRACT_VERSION, "semantics": contract_payload()}
        )
    ).hexdigest()


def validate_portfolio_optimizer_v2_contract() -> Mapping[str, str]:
    try:
        router = router_v2_contracts.validate_market_router_v2_contract()
        legacy_optimizer = legacy.validate_accumulator_optimizer_contract()
    except (
        router_v2_contracts.MarketRouterV2DirectProviderError,
        legacy.AccumulatorOptimizerError,
    ) as exc:
        raise PortfolioOptimizerV2DirectProviderError(
            "Portfolio Optimizer v2 dependency validation failed"
        ) from exc

    if (
        router["market_router_v2_contract_sha256"]
        != MARKET_ROUTER_V2_CONTRACT_SHA256
    ):
        raise PortfolioOptimizerV2DirectProviderError(
            "Market Router v2 direct-provider identity drifted"
        )
    if (
        legacy_optimizer["accumulator_optimizer_contract_sha256"]
        != LEGACY_ACCUMULATOR_OPTIMIZER_V2_CONTRACT_SHA256
    ):
        raise PortfolioOptimizerV2DirectProviderError(
            "legacy Accumulator Optimizer v2 policy identity drifted"
        )
    if (reconciliation.DATASET_NAME, reconciliation.SCHEMA_VERSION) != (
        "athena-sportybet-fotmob-full-utc-reconciliation-v1",
        1,
    ):
        raise PortfolioOptimizerV2DirectProviderError(
            "SportyBet/FotMob reconciliation contract drifted"
        )
    if (
        reconciliation_receipt.DATASET_NAME,
        reconciliation_receipt.SCHEMA_VERSION,
    ) != (
        "athena-sportybet-fotmob-full-utc-reconciliation-receipt-v1",
        1,
    ):
        raise PortfolioOptimizerV2DirectProviderError(
            "SportyBet/FotMob reconciliation receipt contract drifted"
        )
    for value, label in (
        (MAXIMUM_COMPETITION_SHARE, "competition share"),
        (MAXIMUM_MARKET_FAMILY_SHARE, "market-family share"),
        (MAXIMUM_FRAGILE_SHARE, "fragile share"),
        (
            MINIMUM_ROBUST_NET_EXPECTED_VALUE_FOR_NON_FRAGILE,
            "robust EV threshold",
        ),
        (
            MINIMUM_SURVIVAL_FLOOR_FOR_NON_FRAGILE,
            "survival threshold",
        ),
    ):
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise PortfolioOptimizerV2DirectProviderError(
                f"{label} drifted outside [0,1]"
            )
    if MAXIMUM_TARGET_SIZE != 50 or MAXIMUM_TEAM_APPEARANCES != 1:
        raise PortfolioOptimizerV2DirectProviderError(
            "target/team exposure contract drifted"
        )

    actual = calculate_portfolio_optimizer_v2_contract_sha256()
    if actual != EXPECTED_CONTRACT_SHA256:
        raise PortfolioOptimizerV2DirectProviderError(
            "Portfolio Optimizer v2 direct-provider contract drifted"
        )
    return types.MappingProxyType(
        {
            "market_router_v2_contract_sha256": (
                router["market_router_v2_contract_sha256"]
            ),
            "legacy_accumulator_optimizer_v2_contract_sha256": (
                legacy_optimizer["accumulator_optimizer_contract_sha256"]
            ),
            "canonical_market_semantics_sha256": (
                legacy_optimizer["canonical_market_semantics_sha256"]
            ),
            "portfolio_optimizer_v2_contract_sha256": actual,
        }
    )


__all__ = [name for name in globals() if not name.startswith("_")]
