"""Narrow frozen Price-All v2 contract and settlement-policy evidence.

This module preserves the historical v2 identity and exact settlement policy
still consumed by v3. It does not issue evaluations or consume provider quotes.
"""
from __future__ import annotations

from decimal import Decimal
import hashlib
import json
import math
import types
from typing import Any, Mapping

from domain import sportybet_live_event_quote_evidence as _live
from domain import sportybet_price_all_direct_provider_quote_adapter as _adapter
from domain._price_all_contracts import (
    CalibratedValueCandidate,
    DEVIG_POLICY_ID,
    PriceAllError,
    SETTLEMENT_RETURN_POLICY_ID,
    SettlementState,
    validate_price_all_contract,
)
from domain.markets import MARKET_REGISTRY, MarketFamily, MarketId, OutcomeId

SCHEMA_VERSION = 1
CONTRACT_VERSION = 1
DATASET_NAME = "athena-price-all-v2-direct-provider-value-evaluation-v1"
QUOTE_POLICY_ID = "DIRECT_PROVIDER_RESPONSE_COMPLETION_FRESH_900S_AND_120S_KICKOFF_LEAD_V1"
NO_ROUTER_POLICY_ID = "PRICE_ALL_V2_NO_RANK_ROUTE_SELECT_OR_BET_V1"
DEFAULT_MAX_QUOTE_AGE_SECONDS = _live.MAX_OBSERVATION_AGE_SECONDS
DEFAULT_MINIMUM_LEAD_SECONDS = _live.MINIMUM_LEAD_SECONDS
LEGACY_PRICE_ALL_V1_CONTRACT_SHA256 = _adapter.LEGACY_PRICE_ALL_V1_CONTRACT_SHA256
SOURCE_ADAPTER_CONTRACT_SHA256 = _adapter.EXPECTED_CONTRACT_SHA256
NEXT_BOUNDARY = "MARKET_ROUTER_V2_DIRECT_PROVIDER_VALUE_CONSUMPTION_REQUIRED"
EXPECTED_CONTRACT_SHA256 = "b5e3c063ac8b4e9fc1521cabbfe1da873a67b70efc67bc08d8ada61f2024e599"

_AUTHORITY = types.MappingProxyType(
    {
        "verified_direct_provider_price_consumption": True,
        "value_record_computation": True,
        "football_probability_generation": False,
        "model_promotion": False,
        "market_router": False,
        "final_selection": False,
        "accumulator": False,
        "sportybet_execution": False,
        "staking": False,
        "bet": False,
    }
)
_PARTITION_ANCESTRY_FIELDS = (
    "fixture_id", "event_id", "source", "provider_market_id",
    "provider_specifier", "canonical_market_id", "canonical_line",
    "live_inventory_sha256", "source_bundle_sha256", "source_manifest_sha256",
    "source_raw_sha256", "reviewed_mapping_sha256",
    "fixture_reconciliation_sha256",
)

ORDINARY_PARTITIONS: Mapping[MarketId, tuple[OutcomeId, ...]] = types.MappingProxyType(
    {
        MarketId.MATCH_RESULT: (OutcomeId.HOME, OutcomeId.DRAW, OutcomeId.AWAY),
        MarketId.BTTS: (OutcomeId.YES, OutcomeId.NO),
        MarketId.TOTAL_GOALS: (OutcomeId.OVER, OutcomeId.UNDER),
        MarketId.DRAW_OR_OVER_2_5: (OutcomeId.YES, OutcomeId.NO),
        MarketId.HOME_OR_OVER_2_5: (OutcomeId.YES, OutcomeId.NO),
        MarketId.AWAY_OR_OVER_2_5: (OutcomeId.YES, OutcomeId.NO),
        MarketId.HOME_WIN_TO_NIL: (OutcomeId.YES, OutcomeId.NO),
        MarketId.AWAY_WIN_TO_NIL: (OutcomeId.YES, OutcomeId.NO),
    }
)


class PriceAllV2ContractError(ValueError):
    """Frozen Price-All v2 contract or settlement-policy validation failed."""


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=False, allow_nan=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise PriceAllV2ContractError("canonical JSON serialization failed") from exc


def contract_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "source_adapter_dataset_name": _adapter.DATASET_NAME,
        "source_adapter_status": _adapter.STATUS,
        "source_adapter_contract_sha256": SOURCE_ADAPTER_CONTRACT_SHA256,
        "legacy_price_all_v1_contract_sha256": LEGACY_PRICE_ALL_V1_CONTRACT_SHA256,
        "source_observation_authority": _live.OBSERVATION_AUTHORITY,
        "provider_quote_timestamp": None,
        "provider_snapshot_id": None,
        "quote_policy_id": QUOTE_POLICY_ID,
        "max_quote_age_seconds": DEFAULT_MAX_QUOTE_AGE_SECONDS,
        "minimum_kickoff_lead_seconds": DEFAULT_MINIMUM_LEAD_SECONDS,
        "devig_policy_id": DEVIG_POLICY_ID,
        "settlement_return_policy_id": SETTLEMENT_RETURN_POLICY_ID,
        "partition_ancestry_fields": list(_PARTITION_ANCESTRY_FIELDS),
        "no_router_policy_id": NO_ROUTER_POLICY_ID,
        "next_boundary": NEXT_BOUNDARY,
        "authority": dict(_AUTHORITY),
    }


def calculate_price_all_v2_contract_sha256() -> str:
    return hashlib.sha256(
        _canonical_bytes({"version": CONTRACT_VERSION, "semantics": contract_payload()})
    ).hexdigest()


def validate_price_all_v2_contract() -> Mapping[str, str]:
    try:
        source_contracts = _adapter.validate_adapter_contract()
        legacy = validate_price_all_contract()
    except (_adapter.SportyBetPriceAllDirectProviderQuoteAdapterError, PriceAllError) as exc:
        raise PriceAllV2ContractError("Price-all v2 dependency validation failed") from exc
    if source_contracts["adapter_contract_sha256"] != SOURCE_ADAPTER_CONTRACT_SHA256:
        raise PriceAllV2ContractError("direct-provider adapter identity drifted")
    if (
        source_contracts["legacy_price_all_v1_contract_sha256"]
        != LEGACY_PRICE_ALL_V1_CONTRACT_SHA256
        or legacy["price_all_contract_sha256"] != LEGACY_PRICE_ALL_V1_CONTRACT_SHA256
    ):
        raise PriceAllV2ContractError("legacy Price-all v1 identity drifted")
    actual = calculate_price_all_v2_contract_sha256()
    if actual != EXPECTED_CONTRACT_SHA256:
        raise PriceAllV2ContractError("Price-all v2 contract drifted")
    return types.MappingProxyType(
        {
            "price_all_v2_contract_sha256": actual,
            "source_adapter_contract_sha256": source_contracts["adapter_contract_sha256"],
            "legacy_price_all_v1_contract_sha256": legacy["price_all_contract_sha256"],
        }
    )


def required_settlement_states(
    candidate: CalibratedValueCandidate,
) -> tuple[SettlementState, ...]:
    family = MARKET_REGISTRY[candidate.market_id].family
    if family is MarketFamily.DRAW_NO_BET:
        return (SettlementState.WIN, SettlementState.PUSH, SettlementState.LOSS)
    if family is MarketFamily.ASIAN_HANDICAP:
        return tuple(SettlementState)
    if family is MarketFamily.TOTAL_GOALS:
        quarter_units = Decimal(str(candidate.line)) * 4
        if quarter_units != quarter_units.to_integral_value():
            raise PriceAllV2ContractError(
                "total-goals line lacks reviewed quarter-goal settlement semantics"
            )
        modulo = int(quarter_units) % 4
        if modulo == 0:
            return (SettlementState.WIN, SettlementState.PUSH, SettlementState.LOSS)
        if modulo == 2:
            return (SettlementState.WIN, SettlementState.LOSS)
        return tuple(SettlementState)
    return (SettlementState.WIN, SettlementState.LOSS)


def settlement_ev(
    candidate: CalibratedValueCandidate,
    odds: float,
) -> tuple[tuple[tuple[str, float], ...], float]:
    required = required_settlement_states(candidate)
    supplied = candidate.probability_map
    required_names = {state.value for state in required}
    if set(supplied) == required_names:
        settlement_probabilities = supplied
    else:
        partition = ORDINARY_PARTITIONS.get(candidate.market_id)
        unit = dict(candidate.calibration_unit)
        if (
            required == (SettlementState.WIN, SettlementState.LOSS)
            and set(supplied) == {"YES", "NO"}
            and unit.get("selection_outcome") == candidate.outcome_id.value
        ):
            settlement_probabilities = types.MappingProxyType(
                {
                    SettlementState.WIN.value: supplied["YES"],
                    SettlementState.LOSS.value: supplied["NO"],
                }
            )
        elif (
            required == (SettlementState.WIN, SettlementState.LOSS)
            and partition is not None
            and set(supplied) == {outcome.value for outcome in partition}
        ):
            win = supplied[candidate.outcome_id.value]
            settlement_probabilities = types.MappingProxyType(
                {
                    SettlementState.WIN.value: win,
                    SettlementState.LOSS.value: math.fsum(
                        probability for name, probability in supplied.items()
                        if name != candidate.outcome_id.value
                    ),
                }
            )
        else:
            raise PriceAllV2ContractError(
                "calibrated settlement distribution is incomplete"
            )
    returns = {
        SettlementState.WIN: odds - 1.0,
        SettlementState.HALF_WIN: (odds - 1.0) / 2.0,
        SettlementState.PUSH: 0.0,
        SettlementState.HALF_LOSS: -0.5,
        SettlementState.LOSS: -1.0,
    }
    serialized = tuple((state.value, returns[state]) for state in required)
    ev = math.fsum(
        settlement_probabilities[state.value] * returns[state] for state in required
    )
    return serialized, ev


__all__ = [name for name in globals() if not name.startswith("_")]
