"""Frozen contract for ATHENA Phase 9 Accumulator Optimizer v2."""
from __future__ import annotations

from enum import Enum
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Mapping

from domain._market_router_contracts import validate_market_router_contract
from domain import sportybet_fotmob_full_utc_reconciliation as reconciliation
from domain import sportybet_fotmob_full_utc_reconciliation_receipt as reconciliation_receipt

ACCUMULATOR_OPTIMIZER_DATASET = "athena_accumulator_optimizer_v2"
ACCUMULATOR_OPTIMIZER_SCHEMA_VERSION = 2
ACCUMULATOR_OPTIMIZER_CONTRACT_VERSION = 1

MAXIMUM_TARGET_SIZE = 50
MAXIMUM_TEAM_APPEARANCES = 1
MAXIMUM_COMPETITION_SHARE = 0.40
MINIMUM_COMPETITION_CAP_WHEN_TARGET_GE_2 = 2
MAXIMUM_MARKET_FAMILY_SHARE = 0.50
MINIMUM_MARKET_FAMILY_CAP_WHEN_TARGET_GE_2 = 2
MAXIMUM_FRAGILE_SHARE = 0.30
MINIMUM_FRAGILE_CAP = 1

MINIMUM_ROBUST_NET_EXPECTED_VALUE_FOR_NON_FRAGILE = 0.02
MINIMUM_SURVIVAL_FLOOR_FOR_NON_FRAGILE = 0.60

ROUTER_REPLAY_POLICY_ID = "REPLAY_EXACT_PHASE8_ROUTE_BEFORE_PORTFOLIO_ADMISSION_V1"
FIXTURE_EXPOSURE_IDENTITY_POLICY_ID = (
    "QUOTE_BOUND_SOURCE_REPLAYED_FULL_UTC_RECONCILIATION_RECEIPT_V1"
)
JOINT_SELECTION_POLICY_ID = "DETERMINISTIC_MARGINAL_DIVERSIFICATION_WITH_HARD_CAPS_V1"
CORRELATION_POLICY_ID = "EXPOSURE_FLAGS_AND_CAPS_NO_FABRICATED_STATISTICAL_RHO_V1"
SURVIVAL_POLICY_ID = "WORST_MODEL_NON_NEGATIVE_SETTLEMENT_FLOOR_INDEPENDENCE_BASELINE_V1"
RESERVE_POLICY_ID = "PRESERVE_ALL_ROUTER_QUALIFIED_UNSELECTED_LEGS_WITH_REASONS_V1"
SHORTFALL_POLICY_ID = "REQUESTED_SIZE_IS_TARGET_NOT_REQUIREMENT_NEVER_PAD_V1"
FRAGILITY_POLICY_ID = "THIN_VALUE_OR_THIN_SURVIVAL_OPERATIONAL_FLAG_V1"
FRAGILITY_THRESHOLD_STATUS = "OPERATIONAL_V1_NOT_EMPIRICALLY_OPTIMIZED"
JOINT_DEPENDENCE_STATUS = "NO_VALIDATED_JOINT_CORRELATION_MODEL_V1"
REAL_CURRENT_ACCUMULATOR_OPTIMIZER_STATUS = (
    "NOT_RUN_VERIFIED_CURRENT_ROUTER_CORPUS_UNAVAILABLE"
)

AUTHORITY_FLAGS = MappingProxyType({
    "accumulator_optimization": True,
    "qualified_leg_set": True,
    "reserve_leg_recording": True,
    "market_routing": False,
    "bookmaker_pricing": False,
    "slip_construction": False,
    "booking_code_generation": False,
    "staking": False,
    "bookmaker_execution": False,
    "production_approval": False,
    "bet": False,
})


class AccumulatorOptimizerError(ValueError):
    """Raised when Phase 9 input or frozen semantics fail closed."""


class AccumulatorOptimizationStatus(str, Enum):
    QUALIFIED_SET = "QUALIFIED_SET"
    NO_QUALIFIED_LEGS = "NO_QUALIFIED_LEGS"


class FragilityStatus(str, Enum):
    NON_FRAGILE = "NON_FRAGILE"
    FRAGILE_THIN_VALUE = "FRAGILE_THIN_VALUE"
    FRAGILE_THIN_SURVIVAL = "FRAGILE_THIN_SURVIVAL"
    FRAGILE_THIN_VALUE_AND_SURVIVAL = "FRAGILE_THIN_VALUE_AND_SURVIVAL"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def accumulator_optimizer_contract_payload(
    *,
    market_router_contract_sha256: str,
    canonical_market_semantics_sha256: str,
) -> dict[str, Any]:
    return {
        "dataset": ACCUMULATOR_OPTIMIZER_DATASET,
        "schema_version": ACCUMULATOR_OPTIMIZER_SCHEMA_VERSION,
        "market_router_contract_sha256": market_router_contract_sha256,
        "canonical_market_semantics_sha256": canonical_market_semantics_sha256,
        "sportybet_fotmob_reconciliation_dataset": reconciliation.DATASET_NAME,
        "sportybet_fotmob_reconciliation_schema_version": reconciliation.SCHEMA_VERSION,
        "sportybet_fotmob_reconciliation_receipt_dataset": (
            reconciliation_receipt.DATASET_NAME
        ),
        "sportybet_fotmob_reconciliation_receipt_schema_version": (
            reconciliation_receipt.SCHEMA_VERSION
        ),
        "maximum_target_size": MAXIMUM_TARGET_SIZE,
        "router_replay_policy_id": ROUTER_REPLAY_POLICY_ID,
        "fixture_exposure_identity_policy_id": FIXTURE_EXPOSURE_IDENTITY_POLICY_ID,
        "joint_selection_policy_id": JOINT_SELECTION_POLICY_ID,
        "correlation_policy_id": CORRELATION_POLICY_ID,
        "survival_policy_id": SURVIVAL_POLICY_ID,
        "reserve_policy_id": RESERVE_POLICY_ID,
        "shortfall_policy_id": SHORTFALL_POLICY_ID,
        "fragility_policy_id": FRAGILITY_POLICY_ID,
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
        "authority_flags": dict(AUTHORITY_FLAGS),
        "real_current_accumulator_optimizer_status": (
            REAL_CURRENT_ACCUMULATOR_OPTIMIZER_STATUS
        ),
    }


def calculate_accumulator_optimizer_contract_sha256(
    *,
    market_router_contract_sha256: str,
    canonical_market_semantics_sha256: str,
    version: int = ACCUMULATOR_OPTIMIZER_CONTRACT_VERSION,
) -> str:
    return hashlib.sha256(_canonical_bytes({
        "version": version,
        "semantics": accumulator_optimizer_contract_payload(
            market_router_contract_sha256=market_router_contract_sha256,
            canonical_market_semantics_sha256=canonical_market_semantics_sha256,
        ),
    })).hexdigest()


EXPECTED_ACCUMULATOR_OPTIMIZER_CONTRACT_SHA256_BY_VERSION: Mapping[int, str] = (
    MappingProxyType({
        1: "de6578c1a21370a1859901a73e4d3993d1544a66cb0f09384a45a8233a5ce253",
    })
)


def validate_accumulator_optimizer_contract() -> Mapping[str, str]:
    upstream = validate_market_router_contract()
    router_sha = upstream["market_router_contract_sha256"]
    market_sha = upstream["canonical_market_semantics_sha256"]
    if router_sha != "0e4486527b060109852ab56dd76774b2d150cf8326875e44537a3bce2dc656bf":
        raise AccumulatorOptimizerError("Market Router v1 identity drifted")
    if (reconciliation.DATASET_NAME, reconciliation.SCHEMA_VERSION) != (
        "athena-sportybet-fotmob-full-utc-reconciliation-v1",
        1,
    ):
        raise AccumulatorOptimizerError("SportyBet/FotMob reconciliation contract drifted")
    if (
        reconciliation_receipt.DATASET_NAME,
        reconciliation_receipt.SCHEMA_VERSION,
    ) != (
        "athena-sportybet-fotmob-full-utc-reconciliation-receipt-v1",
        1,
    ):
        raise AccumulatorOptimizerError(
            "SportyBet/FotMob reconciliation receipt contract drifted"
        )
    for value, label in (
        (MAXIMUM_COMPETITION_SHARE, "competition share"),
        (MAXIMUM_MARKET_FAMILY_SHARE, "market-family share"),
        (MAXIMUM_FRAGILE_SHARE, "fragile share"),
        (MINIMUM_ROBUST_NET_EXPECTED_VALUE_FOR_NON_FRAGILE, "robust EV threshold"),
        (MINIMUM_SURVIVAL_FLOOR_FOR_NON_FRAGILE, "survival threshold"),
    ):
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise AccumulatorOptimizerError(f"{label} drifted outside [0,1]")
    if MAXIMUM_TARGET_SIZE != 50 or MAXIMUM_TEAM_APPEARANCES != 1:
        raise AccumulatorOptimizerError("target/team exposure contract drifted")
    actual = calculate_accumulator_optimizer_contract_sha256(
        market_router_contract_sha256=router_sha,
        canonical_market_semantics_sha256=market_sha,
    )
    expected = EXPECTED_ACCUMULATOR_OPTIMIZER_CONTRACT_SHA256_BY_VERSION.get(
        ACCUMULATOR_OPTIMIZER_CONTRACT_VERSION
    )
    if expected is None or actual != expected:
        raise AccumulatorOptimizerError("Accumulator Optimizer v2 contract drift")
    return MappingProxyType({
        "market_router_contract_sha256": router_sha,
        "canonical_market_semantics_sha256": market_sha,
        "accumulator_optimizer_contract_sha256": actual,
    })


__all__ = [name for name in globals() if not name.startswith("_")]
