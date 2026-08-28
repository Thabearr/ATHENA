"""Frozen contract for ATHENA current SportyBet event discovery and FotMob reconciliation."""
from __future__ import annotations

import hashlib
import json
import math
import types
from typing import Any, Mapping

from domain import fotmob_fixture_catalog_handoff as fotmob_handoff
from domain import sportybet_live_event_quote_evidence as live_event

SCHEMA_VERSION = 1
CONTRACT_VERSION = 1
DATASET_NAME = "athena-sportybet-current-event-fixture-reconciliation-v1"
CAPTURE_DATASET_NAME = "athena-sportybet-current-upcoming-event-capture-v1"
INVENTORY_DATASET_NAME = "athena-sportybet-current-upcoming-event-inventory-v1"
REPLAY_STATUS = "SPORTYBET_EVENT_FIXTURE_RECONCILIATION_AS_OF_REPLAY_VERIFIED"
LIVE_STATUS = "CURRENT_SPORTYBET_EVENT_FIXTURE_RECONCILIATION_VERIFIED"
FOOTBALL_SPORT_ID = "sr:sport:1"
UPCOMING_PATH = "/api/ng/factsCenter/wapConfigurableUpcomingEvents"
SOURCE_METHOD = "PUBLIC_ANONYMOUS_FACTS_CENTER_CONFIGURABLE_UPCOMING_GET"
OBSERVATION_AUTHORITY = (
    "ATHENA_DIRECT_PROVIDER_RESPONSE_COMPLETION_NOT_PROVIDER_EVENT_TIMESTAMP"
)
MAX_OBSERVATION_AGE_SECONDS = live_event.MAX_OBSERVATION_AGE_SECONDS
MINIMUM_LEAD_SECONDS = live_event.MINIMUM_LEAD_SECONDS
MATCHING_BASIS = (
    "EXACT_HOME_AWAY_COMPETITION_FULL_UTC_NO_FUZZY_NO_ALIAS_"
    "NO_REVERSAL_NO_ROUNDING_NO_TOLERANCE"
)
DIRECT_EVENT_CONTRACT_SHA256 = live_event.EXPECTED_CONTRACT_SHA256
FOTMOB_HANDOFF_DATASET_NAME = fotmob_handoff.DATASET_NAME
FOTMOB_HANDOFF_SCHEMA_VERSION = fotmob_handoff.SCHEMA_VERSION
NEXT_BOUNDARY = "SPORTYBET_CURRENT_EVENT_CANONICAL_MARKET_MAPPING_REBIND_REQUIRED"
EXPECTED_CONTRACT_SHA256 = "9f65195b3fad2398dae7c8f4a78f426c519bb11156e1217793ac25c57f47dc7f"

AUTHORITY = types.MappingProxyType(
    {
        "direct_provider_network_acquisition": True,
        "current_event_discovery": True,
        "fixture_reconciliation": True,
        "exact_source_provenance": True,
        "provider_event_timestamp": False,
        "provider_snapshot_identity": False,
        "canonical_market_mapping": False,
        "price_all": False,
        "market_router": False,
        "portfolio_optimization": False,
        "accumulator_slip_construction": False,
        "sportybet_execution": False,
        "staking": False,
        "bet": False,
    }
)


class SportyBetCurrentEventDiscoveryContractError(ValueError):
    """Raised when the current-event discovery contract drifts."""


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
        raise SportyBetCurrentEventDiscoveryContractError(
            "canonical JSON serialization failed"
        ) from exc


def contract_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "capture_dataset_name": CAPTURE_DATASET_NAME,
        "inventory_dataset_name": INVENTORY_DATASET_NAME,
        "replay_status": REPLAY_STATUS,
        "live_status": LIVE_STATUS,
        "provider_origin": live_event.ORIGIN,
        "provider_oper_id": live_event.OPER_ID,
        "football_sport_id": FOOTBALL_SPORT_ID,
        "upcoming_path": UPCOMING_PATH,
        "source_method": SOURCE_METHOD,
        "observation_authority": OBSERVATION_AUTHORITY,
        "max_observation_age_seconds": MAX_OBSERVATION_AGE_SECONDS,
        "minimum_lead_seconds": MINIMUM_LEAD_SECONDS,
        "matching_basis": MATCHING_BASIS,
        "direct_event_contract_sha256": DIRECT_EVENT_CONTRACT_SHA256,
        "fotmob_handoff_dataset_name": FOTMOB_HANDOFF_DATASET_NAME,
        "fotmob_handoff_schema_version": FOTMOB_HANDOFF_SCHEMA_VERSION,
        "request_scope": "FOOTBALL_SPORT_ID_ONLY_V1",
        "provider_event_identity": "sr:match:<positive integer>",
        "competition_identity": "EXACT_PROVIDER_TOURNAMENT_OR_COMPETITION_LABEL_REQUIRED",
        "duplicate_policy": "CONFLICTING_EVENT_DUPLICATES_FAIL_CLOSED_IDENTICAL_DUPLICATES_DEDUPED",
        "next_boundary": NEXT_BOUNDARY,
        "authority": dict(AUTHORITY),
    }


def calculate_current_event_discovery_contract_sha256() -> str:
    return hashlib.sha256(
        _canonical_bytes(
            {"version": CONTRACT_VERSION, "semantics": contract_payload()}
        )
    ).hexdigest()


def validate_current_event_discovery_contract() -> Mapping[str, str]:
    try:
        direct = live_event.validate_direct_event_source_contract()
    except live_event.SportyBetLiveEventQuoteEvidenceError as exc:
        raise SportyBetCurrentEventDiscoveryContractError(
            "direct-provider event dependency validation failed"
        ) from exc
    if direct["contract_sha256"] != DIRECT_EVENT_CONTRACT_SHA256:
        raise SportyBetCurrentEventDiscoveryContractError(
            "direct-provider event-read contract identity drifted"
        )
    if (
        FOTMOB_HANDOFF_DATASET_NAME != "athena-fotmob-fixture-catalog-handoff-v1"
        or FOTMOB_HANDOFF_SCHEMA_VERSION != 1
    ):
        raise SportyBetCurrentEventDiscoveryContractError(
            "FotMob reviewed catalog handoff contract drifted"
        )
    if live_event.ORIGIN != "https://www.sportybet.com" or live_event.OPER_ID != "2":
        raise SportyBetCurrentEventDiscoveryContractError(
            "SportyBet provider origin/oper identity drifted"
        )
    if (
        type(MAX_OBSERVATION_AGE_SECONDS) is not int
        or MAX_OBSERVATION_AGE_SECONDS <= 0
        or type(MINIMUM_LEAD_SECONDS) is not int
        or MINIMUM_LEAD_SECONDS <= 0
    ):
        raise SportyBetCurrentEventDiscoveryContractError(
            "freshness policy values are invalid"
        )
    for value, label in (
        (float(MAX_OBSERVATION_AGE_SECONDS), "maximum observation age"),
        (float(MINIMUM_LEAD_SECONDS), "minimum kickoff lead"),
    ):
        if not math.isfinite(value):
            raise SportyBetCurrentEventDiscoveryContractError(f"{label} is non-finite")
    actual = calculate_current_event_discovery_contract_sha256()
    if actual != EXPECTED_CONTRACT_SHA256:
        raise SportyBetCurrentEventDiscoveryContractError(
            "current SportyBet event discovery contract drifted"
        )
    return types.MappingProxyType(
        {
            "current_event_discovery_contract_sha256": actual,
            "direct_event_contract_sha256": direct["contract_sha256"],
            "fotmob_handoff_dataset_name": FOTMOB_HANDOFF_DATASET_NAME,
        }
    )


__all__ = [name for name in globals() if not name.startswith("_")]
