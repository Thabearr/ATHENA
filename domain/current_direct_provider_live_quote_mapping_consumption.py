"""Consume PR252 current canonical mappings with exact PR246 current quote evidence.

This boundary is additive. It verifies the exact PR252 current-event canonical mapping
rebind, replays the retained PR246 direct event-detail evidence, and emits bookmaker
quotes only for exact mapped rows that are currently bookable and have reviewed
settlement equivalence.

It never copies legacy mapping odds, computes value, routes, optimizes, constructs a
slip, executes SportyBet actions, stakes, or places a wager.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
import enum
import hashlib
import json
import math
import types
from collections.abc import Mapping, Sequence
from typing import Any

from domain import current_direct_provider_canonical_market_mapping_rebind as mapping
from domain import sportybet_live_event_quote_evidence as live
from domain.markets import MarketId, OutcomeId, validate_selection
from domain.sportybet_reviewed_canonical_market_mapping import (
    SettlementEquivalenceAuthority,
)

SCHEMA_VERSION = 1
CONTRACT_VERSION = 1
DATASET_NAME = "athena-current-direct-provider-live-quote-mapping-consumption-v1"
STATUS_AS_OF = "CURRENT_DIRECT_PROVIDER_MAPPED_QUOTES_AS_OF_REPLAY_VERIFIED"
STATUS_LIVE = "CURRENT_DIRECT_PROVIDER_LIVE_MAPPED_QUOTES_VERIFIED"
PROVIDER = "SportyBet"
AS_OF_REPLAY = "AS_OF_REPLAY"
LIVE_CURRENT = "LIVE_CURRENT"
MAX_SOURCE_AGE_SECONDS = 900
MINIMUM_LEAD_SECONDS = 120
IDENTITY_POLICY = (
    "EXACT_PR252_MAPPED_NATIVE_AND_CANONICAL_IDENTITY_REBOUND_TO_EXACT_"
    "PR246_CURRENT_INVENTORY_V1"
)
AVAILABILITY_POLICY = (
    "ONLY_CURRENTLY_BOOKABLE_EXACT_ROWS_ISSUE_QUOTES_UNAVAILABLE_ROWS_AUDITED_V1"
)
SETTLEMENT_POLICY = (
    "ONLY_REVIEWED_BOOKMAKER_EQUIVALENT_ROWS_ISSUE_QUOTES_"
    "UNPROVEN_PROMOTIONS_AUDITED_V1"
)
PRICE_POLICY = "CURRENT_PR246_ODDS_ONLY_NEVER_LEGACY_MAPPING_ODDS_V1"
PR252_CONTRACT_SHA256 = (
    "de022fd931313fa8d3c2c093ff0cb9b12f2c0f1ba0d9adc4b646c94dfd306e96"
)
DIRECT_EVENT_CONTRACT_SHA256 = (
    "b888cebab6447cd4072d823dab67b56f1f75f72eb72d67b692d47a4378b27555"
)
NEXT_BOUNDARY = "PRICE_ALL_V3_CURRENT_DIRECT_PROVIDER_QUOTE_CONSUMPTION_REQUIRED"
EXPECTED_CONTRACT_SHA256 = (
    "671e6016093bc3f30141ddd13ab259bebb70086945fb30a588a185703fd128d4"
)

_CONTRACT_AUTHORITY = types.MappingProxyType(
    {
        "current_mapping_source_replay": True,
        "direct_event_source_replay": True,
        "current_provider_mapped_quote_evidence": True,
        "price_all": False,
        "market_router": False,
        "portfolio_optimization": False,
        "final_selection": False,
        "accumulator_slip_construction": False,
        "sportybet_execution": False,
        "staking": False,
        "bet": False,
    }
)


class CurrentDirectProviderLiveQuoteMappingConsumptionError(ValueError):
    """Raised when current mapped-quote consumption fails closed."""


class QuoteAuditDisposition(str, enum.Enum):
    QUOTED = "QUOTED"
    CURRENTLY_UNAVAILABLE = "CURRENTLY_UNAVAILABLE"
    SETTLEMENT_EQUIVALENCE_UNPROVEN = "SETTLEMENT_EQUIVALENCE_UNPROVEN"


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
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            "canonical JSON serialization failed"
        ) from exc


def _utc(value: Any, label: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            f"{label} must be timezone-aware"
        )
    try:
        return value.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            f"{label} is invalid"
        ) from exc


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _contract_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "dataset_name": DATASET_NAME,
        "provider": PROVIDER,
        "source_mapping_dataset_name": mapping.DATASET_NAME,
        "source_mapping_contract_sha256": PR252_CONTRACT_SHA256,
        "direct_event_contract_sha256": DIRECT_EVENT_CONTRACT_SHA256,
        "source_observation_authority": live.OBSERVATION_AUTHORITY,
        "proof_modes": [AS_OF_REPLAY, LIVE_CURRENT],
        "status_as_of": STATUS_AS_OF,
        "status_live": STATUS_LIVE,
        "max_source_age_seconds": MAX_SOURCE_AGE_SECONDS,
        "minimum_lead_seconds": MINIMUM_LEAD_SECONDS,
        "identity_policy": IDENTITY_POLICY,
        "availability_policy": AVAILABILITY_POLICY,
        "settlement_policy": SETTLEMENT_POLICY,
        "price_policy": PRICE_POLICY,
        "provider_quote_timestamp": None,
        "provider_snapshot_id": None,
        "authority": dict(_CONTRACT_AUTHORITY),
        "next_boundary": NEXT_BOUNDARY,
    }


def calculate_current_live_quote_mapping_contract_sha256() -> str:
    return hashlib.sha256(_canonical_bytes(_contract_payload())).hexdigest()


def validate_current_live_quote_mapping_contract() -> Mapping[str, str]:
    try:
        current_contract = mapping.validate_current_mapping_rebind_contract()
        direct_contract = live.validate_direct_event_source_contract()
    except (
        mapping.CurrentDirectProviderCanonicalMappingRebindError,
        live.SportyBetLiveEventQuoteEvidenceError,
    ) as exc:
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            "mapped-quote dependency validation failed"
        ) from exc
    if current_contract != PR252_CONTRACT_SHA256:
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            "PR252 current mapping contract identity drifted"
        )
    if direct_contract["contract_sha256"] != DIRECT_EVENT_CONTRACT_SHA256:
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            "PR246 direct event contract identity drifted"
        )
    if (
        mapping.MAX_SOURCE_AGE_SECONDS != MAX_SOURCE_AGE_SECONDS
        or mapping.MINIMUM_LEAD_SECONDS != MINIMUM_LEAD_SECONDS
        or live.MAX_OBSERVATION_AGE_SECONDS != MAX_SOURCE_AGE_SECONDS
        or live.MINIMUM_LEAD_SECONDS != MINIMUM_LEAD_SECONDS
    ):
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            "current quote freshness policy drifted"
        )
    actual = calculate_current_live_quote_mapping_contract_sha256()
    if actual != EXPECTED_CONTRACT_SHA256:
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            "current live quote mapping contract SHA-256 mismatch"
        )
    return types.MappingProxyType(
        {
            "current_live_quote_mapping_contract_sha256": actual,
            "pr252_contract_sha256": current_contract,
            "direct_event_contract_sha256": direct_contract["contract_sha256"],
        }
    )


@dataclasses.dataclass(frozen=True)
class CurrentMappedQuoteAudit:
    provider_market_id: str
    provider_specifier: str | None
    provider_outcome_id: str
    canonical_market_id: MarketId
    canonical_outcome_id: OutcomeId
    canonical_line: float | None
    source_mapping_row_sha256: str
    disposition: QuoteAuditDisposition

    def __post_init__(self) -> None:
        if type(self.canonical_market_id) is not MarketId:
            raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
                "audit canonical_market_id must be exact MarketId"
            )
        if type(self.canonical_outcome_id) is not OutcomeId:
            raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
                "audit canonical_outcome_id must be exact OutcomeId"
            )
        if type(self.disposition) is not QuoteAuditDisposition:
            raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
                "quote audit disposition is invalid"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_market_id": self.provider_market_id,
            "provider_specifier": self.provider_specifier,
            "provider_outcome_id": self.provider_outcome_id,
            "canonical_market_id": self.canonical_market_id.value,
            "canonical_outcome_id": self.canonical_outcome_id.value,
            "canonical_line": self.canonical_line,
            "source_mapping_row_sha256": self.source_mapping_row_sha256,
            "disposition": self.disposition.value,
        }


@dataclasses.dataclass(frozen=True, init=False)
class CurrentDirectProviderMappedQuote:
    fixture_id: str
    event_id: str
    provider_market_id: str
    provider_market_name: str
    provider_specifier: str | None
    provider_outcome_id: str
    provider_outcome_name: str
    canonical_market_id: MarketId
    canonical_outcome_id: OutcomeId
    canonical_line: float | None
    odds_raw: str
    decimal_odds: float
    observed_at: datetime
    observation_authority: str
    provider_quote_at: None
    provider_snapshot_id: None
    current_inventory_sha256: str
    source_manifest_sha256: str
    source_raw_sha256: str
    current_mapping_rebind_sha256: str
    current_mapping_contract_sha256: str
    source_current_reconciliation_sha256: str
    source_legacy_mapping_sha256: str
    source_mapping_row_sha256: str
    settlement_equivalence_authority: SettlementEquivalenceAuthority

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            "current direct-provider mapped quotes are builder-only"
        )

    @property
    def quote_identity(self) -> tuple[Any, ...]:
        return (
            self.fixture_id,
            self.event_id,
            self.provider_market_id,
            self.provider_specifier,
            self.provider_outcome_id,
            self.canonical_market_id,
            self.canonical_outcome_id,
            self.canonical_line,
            self.current_inventory_sha256,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "event_id": self.event_id,
            "provider_market_id": self.provider_market_id,
            "provider_market_name": self.provider_market_name,
            "provider_specifier": self.provider_specifier,
            "provider_outcome_id": self.provider_outcome_id,
            "provider_outcome_name": self.provider_outcome_name,
            "canonical_market_id": self.canonical_market_id.value,
            "canonical_outcome_id": self.canonical_outcome_id.value,
            "canonical_line": self.canonical_line,
            "odds_raw": self.odds_raw,
            "decimal_odds": self.decimal_odds,
            "observed_at": self.observed_at.isoformat(timespec="microseconds").replace(
                "+00:00", "Z"
            ),
            "observation_authority": self.observation_authority,
            "provider_quote_at": None,
            "provider_snapshot_id": None,
            "current_inventory_sha256": self.current_inventory_sha256,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "current_mapping_rebind_sha256": self.current_mapping_rebind_sha256,
            "current_mapping_contract_sha256": self.current_mapping_contract_sha256,
            "source_current_reconciliation_sha256": (
                self.source_current_reconciliation_sha256
            ),
            "source_legacy_mapping_sha256": self.source_legacy_mapping_sha256,
            "source_mapping_row_sha256": self.source_mapping_row_sha256,
            "settlement_equivalence_authority": (
                self.settlement_equivalence_authority.value
            ),
        }


@dataclasses.dataclass(frozen=True, init=False)
class CurrentDirectProviderMappedQuoteBundle:
    schema_version: int
    dataset_name: str
    status: str
    proof_mode: str
    evaluation_time: datetime
    event_id: str
    fixture_id: str
    home_team_name: str
    away_team_name: str
    kickoff_utc: datetime
    discovery_observed_at: datetime
    direct_event_observed_at: datetime
    discovery_age_seconds: float
    direct_event_age_seconds: float
    kickoff_lead_seconds: float
    max_source_age_seconds: int
    minimum_lead_seconds: int
    current_mapping_rebind_sha256: str
    current_mapping_contract_sha256: str
    source_current_reconciliation_sha256: str
    source_legacy_mapping_sha256: str
    current_inventory_sha256: str
    current_manifest_sha256: str
    current_raw_sha256: str
    quotes: tuple[CurrentDirectProviderMappedQuote, ...]
    quote_audits: tuple[CurrentMappedQuoteAudit, ...]
    source_mapping_audits: tuple[mapping.CurrentCanonicalMappingAudit, ...]
    authority: Mapping[str, bool]
    next_boundary: str
    contract_sha256: str
    _source_mapping: mapping.CurrentDirectProviderCanonicalMarketMappingRebind

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            "current direct-provider mapped quote bundles are builder-only"
        )

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(_canonical_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "status": self.status,
            "proof_mode": self.proof_mode,
            "evaluation_time": self.evaluation_time.isoformat(
                timespec="microseconds"
            ).replace("+00:00", "Z"),
            "event_id": self.event_id,
            "fixture_id": self.fixture_id,
            "home_team_name": self.home_team_name,
            "away_team_name": self.away_team_name,
            "kickoff_utc": self.kickoff_utc.isoformat(timespec="microseconds").replace(
                "+00:00", "Z"
            ),
            "discovery_observed_at": self.discovery_observed_at.isoformat(
                timespec="microseconds"
            ).replace("+00:00", "Z"),
            "direct_event_observed_at": self.direct_event_observed_at.isoformat(
                timespec="microseconds"
            ).replace("+00:00", "Z"),
            "discovery_age_seconds": self.discovery_age_seconds,
            "direct_event_age_seconds": self.direct_event_age_seconds,
            "kickoff_lead_seconds": self.kickoff_lead_seconds,
            "max_source_age_seconds": self.max_source_age_seconds,
            "minimum_lead_seconds": self.minimum_lead_seconds,
            "current_mapping_rebind_sha256": self.current_mapping_rebind_sha256,
            "current_mapping_contract_sha256": self.current_mapping_contract_sha256,
            "source_current_reconciliation_sha256": (
                self.source_current_reconciliation_sha256
            ),
            "source_legacy_mapping_sha256": self.source_legacy_mapping_sha256,
            "current_inventory_sha256": self.current_inventory_sha256,
            "current_manifest_sha256": self.current_manifest_sha256,
            "current_raw_sha256": self.current_raw_sha256,
            "quote_count": len(self.quotes),
            "quotes": [item.to_dict() for item in self.quotes],
            "quote_audits": [item.to_dict() for item in self.quote_audits],
            "source_mapping_audits": [
                item.to_dict() for item in self.source_mapping_audits
            ],
            "authority": dict(self.authority),
            "next_boundary": self.next_boundary,
            "contract_sha256": self.contract_sha256,
            "provider_quote_at": None,
            "provider_snapshot_id": None,
            "wager_placed": False,
        }


def _set_frozen(obj: Any, values: Mapping[str, Any]) -> Any:
    for name, value in values.items():
        object.__setattr__(obj, name, value)
    return obj


def _detail_directory(
    value: mapping.CurrentDirectProviderCanonicalMarketMappingRebind,
):
    details = dict(value._current_bundle._detail_directories)
    if value.event_id not in details:
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            "PR252 retained current bundle lacks direct event evidence"
        )
    return details[value.event_id]


def _replay_inventory(
    value: mapping.CurrentDirectProviderCanonicalMarketMappingRebind,
) -> live.SportyBetLiveEventQuoteInventory:
    try:
        inventory = live.build_live_event_quote_inventory(
            _detail_directory(value),
            repository_root=value._current_bundle._repository_root,
        )
    except live.SportyBetLiveEventQuoteEvidenceError as exc:
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            "current direct event-detail source replay failed closed"
        ) from exc
    if (
        inventory.event_id != value.event_id
        or inventory.home_team_name != value.home_team_name
        or inventory.away_team_name != value.away_team_name
        or inventory.kickoff_utc != value.kickoff_utc
        or inventory.observed_at != value.direct_event_observed_at
        or inventory.canonical_sha256 != value.current_inventory_sha256
        or inventory.source_manifest_sha256 != value.current_manifest_sha256
        or inventory.source_raw_sha256 != value.current_raw_sha256
    ):
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            "replayed current inventory differs from exact PR252 ancestry"
        )
    if not inventory.prematch_bookable_observed:
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            "current event is not proven prematch/bookable"
        )
    return inventory


def _adapt_quote(
    *,
    source_mapping: mapping.CurrentDirectProviderCanonicalMarketMappingRebind,
    mapped: mapping.CurrentDirectProviderCanonicalMappedSelection,
    selected: live.SportyBetLiveEventSelection,
    mapping_sha256: str,
    inventory: live.SportyBetLiveEventQuoteInventory,
) -> CurrentDirectProviderMappedQuote:
    market, outcome, line = validate_selection(
        mapped.canonical_market_id,
        mapped.canonical_outcome_id,
        mapped.canonical_line,
    )
    if (
        type(selected.odds_raw) is not str
        or not selected.odds_raw
        or not math.isfinite(selected.odds_decimal)
        or selected.odds_decimal <= 1.0
    ):
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            "current direct-provider odds are invalid"
        )
    try:
        raw_float = float(selected.odds_raw)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            "current direct-provider odds_raw is invalid"
        ) from exc
    if not math.isfinite(raw_float) or raw_float != selected.odds_decimal:
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            "current direct-provider odds identity mismatch"
        )
    value = object.__new__(CurrentDirectProviderMappedQuote)
    return _set_frozen(
        value,
        {
            "fixture_id": source_mapping.fixture_id,
            "event_id": source_mapping.event_id,
            "provider_market_id": selected.market_id,
            "provider_market_name": selected.market_name,
            "provider_specifier": selected.specifier,
            "provider_outcome_id": selected.outcome_id,
            "provider_outcome_name": selected.outcome_name,
            "canonical_market_id": market,
            "canonical_outcome_id": outcome,
            "canonical_line": line,
            "odds_raw": selected.odds_raw,
            "decimal_odds": selected.odds_decimal,
            "observed_at": inventory.observed_at,
            "observation_authority": live.OBSERVATION_AUTHORITY,
            "provider_quote_at": None,
            "provider_snapshot_id": None,
            "current_inventory_sha256": inventory.canonical_sha256,
            "source_manifest_sha256": inventory.source_manifest_sha256,
            "source_raw_sha256": inventory.source_raw_sha256,
            "current_mapping_rebind_sha256": mapping_sha256,
            "current_mapping_contract_sha256": PR252_CONTRACT_SHA256,
            "source_current_reconciliation_sha256": (
                source_mapping.source_current_reconciliation_sha256
            ),
            "source_legacy_mapping_sha256": source_mapping.source_legacy_mapping_sha256,
            "source_mapping_row_sha256": mapped.source_mapping_row_sha256,
            "settlement_equivalence_authority": (
                mapped.settlement_equivalence_authority
            ),
        },
    )


def _derive_quotes(
    *,
    source_mapping: mapping.CurrentDirectProviderCanonicalMarketMappingRebind,
    inventory: live.SportyBetLiveEventQuoteInventory,
    mapping_sha256: str,
) -> tuple[
    tuple[CurrentDirectProviderMappedQuote, ...],
    tuple[CurrentMappedQuoteAudit, ...],
]:
    by_native = {
        (item.market_id, item.specifier, item.outcome_id): item
        for item in inventory.selections
    }
    if len(by_native) != len(inventory.selections):
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            "current inventory native identities are not unique"
        )
    quotes: list[CurrentDirectProviderMappedQuote] = []
    audits: list[CurrentMappedQuoteAudit] = []
    for mapped in source_mapping.mapped_selections:
        if type(mapped) is not mapping.CurrentDirectProviderCanonicalMappedSelection:
            raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
                "PR252 mapped selection type mismatch"
            )
        key = (
            mapped.provider_market_id,
            mapped.provider_specifier,
            mapped.provider_outcome_id,
        )
        selected = by_native.get(key)
        if selected is None:
            raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
                "PR252 mapped row is absent from exact retained current inventory"
            )
        if (
            selected.market_name != mapped.provider_market_name
            or selected.outcome_name != mapped.provider_outcome_name
            or selected.bookable != mapped.current_bookable_observed
            or selected.bookability_basis != mapped.current_bookability_basis
            or mapped.current_inventory_sha256 != inventory.canonical_sha256
            or mapped.canonical_market_mapping_authorized is not True
        ):
            raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
                "PR252 mapped row differs from exact current provider identity"
            )
        settlement = mapped.settlement_equivalence_authority
        if type(settlement) is not SettlementEquivalenceAuthority:
            raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
                "settlement equivalence authority type mismatch"
            )
        if (
            mapped.bookmaker_equivalence_authorized is not True
            or settlement
            is SettlementEquivalenceAuthority.PROVIDER_PROMOTION_RULES_UNPROVEN
        ):
            disposition = QuoteAuditDisposition.SETTLEMENT_EQUIVALENCE_UNPROVEN
        elif not selected.bookable:
            disposition = QuoteAuditDisposition.CURRENTLY_UNAVAILABLE
        else:
            disposition = QuoteAuditDisposition.QUOTED
            quotes.append(
                _adapt_quote(
                    source_mapping=source_mapping,
                    mapped=mapped,
                    selected=selected,
                    mapping_sha256=mapping_sha256,
                    inventory=inventory,
                )
            )
        audits.append(
            CurrentMappedQuoteAudit(
                provider_market_id=mapped.provider_market_id,
                provider_specifier=mapped.provider_specifier,
                provider_outcome_id=mapped.provider_outcome_id,
                canonical_market_id=mapped.canonical_market_id,
                canonical_outcome_id=mapped.canonical_outcome_id,
                canonical_line=mapped.canonical_line,
                source_mapping_row_sha256=mapped.source_mapping_row_sha256,
                disposition=disposition,
            )
        )
    quotes_sorted = tuple(
        sorted(
            quotes,
            key=lambda item: (
                item.canonical_market_id.value,
                "" if item.canonical_line is None else str(item.canonical_line),
                item.canonical_outcome_id.value,
                item.provider_market_id,
                item.provider_outcome_id,
            ),
        )
    )
    audits_sorted = tuple(
        sorted(
            audits,
            key=lambda item: (
                item.canonical_market_id.value,
                "" if item.canonical_line is None else str(item.canonical_line),
                item.canonical_outcome_id.value,
                item.provider_market_id,
                item.provider_outcome_id,
            ),
        )
    )
    if len({item.quote_identity for item in quotes_sorted}) != len(quotes_sorted):
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            "current mapped quote identities are not unique"
        )
    return quotes_sorted, audits_sorted


def _authority(*, proof_mode: str, quotes: Sequence[CurrentDirectProviderMappedQuote]):
    return types.MappingProxyType(
        {
            "current_mapping_source_replay": True,
            "direct_event_source_replay": True,
            "current_provider_mapped_quote_evidence": bool(quotes),
            "as_of_source_freshness": True,
            "wall_clock_currentness_at_issuance": proof_mode == LIVE_CURRENT,
            "price_all": False,
            "market_router": False,
            "portfolio_optimization": False,
            "final_selection": False,
            "accumulator_slip_construction": False,
            "sportybet_execution": False,
            "staking": False,
            "bet": False,
        }
    )


def _build(
    *,
    source_mapping: mapping.CurrentDirectProviderCanonicalMarketMappingRebind,
    evaluation_time: datetime,
    proof_mode: str,
) -> CurrentDirectProviderMappedQuoteBundle:
    validate_current_live_quote_mapping_contract()
    if type(source_mapping) is not mapping.CurrentDirectProviderCanonicalMarketMappingRebind:
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            "source_mapping must be exact PR252 mapping rebind"
        )
    try:
        verified = mapping.verify_current_direct_provider_canonical_mapping_rebind(
            source_mapping
        )
    except mapping.CurrentDirectProviderCanonicalMappingRebindError as exc:
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            "PR252 mapping source replay failed closed"
        ) from exc
    if type(verified) is not mapping.CurrentDirectProviderCanonicalMarketMappingRebind:
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            "PR252 verifier returned invalid mapping type"
        )
    if proof_mode not in {AS_OF_REPLAY, LIVE_CURRENT}:
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            "proof_mode is invalid"
        )
    if proof_mode == LIVE_CURRENT and verified.proof_mode != mapping.LIVE_CURRENT:
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            "live quote issuance requires a PR252 LIVE_CURRENT mapping rebind"
        )
    if (
        verified.dataset_name != mapping.DATASET_NAME
        or verified.status != mapping.STATUS
        or verified.contract_sha256 != PR252_CONTRACT_SHA256
        or verified.next_boundary != mapping.NEXT_BOUNDARY
        or verified.max_source_age_seconds != MAX_SOURCE_AGE_SECONDS
        or verified.minimum_lead_seconds != MINIMUM_LEAD_SECONDS
    ):
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            "PR252 mapping contract/policy state mismatch"
        )
    if (
        verified.authority.get("fresh_price") is not False
        or verified.authority.get("price_all") is not False
        or verified.authority.get("bet") is not False
    ):
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            "PR252 authority boundary drifted"
        )
    evaluation = _utc(evaluation_time, "evaluation_time")
    mapping_evaluation = _utc(verified.evaluation_time, "mapping evaluation_time")
    if evaluation < mapping_evaluation:
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            "quote evaluation_time cannot predate PR252 mapping issuance"
        )
    inventory = _replay_inventory(verified)
    discovery_age = (evaluation - verified.discovery_observed_at).total_seconds()
    direct_age = (evaluation - inventory.observed_at).total_seconds()
    kickoff_lead = (verified.kickoff_utc - evaluation).total_seconds()
    for value, label in (
        (discovery_age, "discovery age"),
        (direct_age, "direct event age"),
        (kickoff_lead, "kickoff lead"),
    ):
        if not math.isfinite(value):
            raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
                f"{label} is non-finite"
            )
    if discovery_age < 0 or direct_age < 0:
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            "quote evaluation predates retained provider evidence"
        )
    if discovery_age > MAX_SOURCE_AGE_SECONDS or direct_age > MAX_SOURCE_AGE_SECONDS:
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            "current direct-provider evidence is stale at quote issuance"
        )
    if kickoff_lead <= MINIMUM_LEAD_SECONDS:
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            "current event is too close to kickoff for mapped quote issuance"
        )

    mapping_sha256 = verified.canonical_sha256
    quotes, quote_audits = _derive_quotes(
        source_mapping=verified,
        inventory=inventory,
        mapping_sha256=mapping_sha256,
    )
    value = object.__new__(CurrentDirectProviderMappedQuoteBundle)
    return _set_frozen(
        value,
        {
            "schema_version": SCHEMA_VERSION,
            "dataset_name": DATASET_NAME,
            "status": STATUS_LIVE if proof_mode == LIVE_CURRENT else STATUS_AS_OF,
            "proof_mode": proof_mode,
            "evaluation_time": evaluation,
            "event_id": verified.event_id,
            "fixture_id": verified.fixture_id,
            "home_team_name": verified.home_team_name,
            "away_team_name": verified.away_team_name,
            "kickoff_utc": verified.kickoff_utc,
            "discovery_observed_at": verified.discovery_observed_at,
            "direct_event_observed_at": inventory.observed_at,
            "discovery_age_seconds": discovery_age,
            "direct_event_age_seconds": direct_age,
            "kickoff_lead_seconds": kickoff_lead,
            "max_source_age_seconds": MAX_SOURCE_AGE_SECONDS,
            "minimum_lead_seconds": MINIMUM_LEAD_SECONDS,
            "current_mapping_rebind_sha256": mapping_sha256,
            "current_mapping_contract_sha256": PR252_CONTRACT_SHA256,
            "source_current_reconciliation_sha256": (
                verified.source_current_reconciliation_sha256
            ),
            "source_legacy_mapping_sha256": verified.source_legacy_mapping_sha256,
            "current_inventory_sha256": inventory.canonical_sha256,
            "current_manifest_sha256": inventory.source_manifest_sha256,
            "current_raw_sha256": inventory.source_raw_sha256,
            "quotes": quotes,
            "quote_audits": quote_audits,
            "source_mapping_audits": tuple(verified.mapping_audits),
            "authority": _authority(proof_mode=proof_mode, quotes=quotes),
            "next_boundary": NEXT_BOUNDARY,
            "contract_sha256": EXPECTED_CONTRACT_SHA256,
            "_source_mapping": source_mapping,
        },
    )


def issue_current_direct_provider_mapped_quotes_as_of(
    *,
    source_mapping: mapping.CurrentDirectProviderCanonicalMarketMappingRebind,
    evaluation_time: datetime,
) -> CurrentDirectProviderMappedQuoteBundle:
    """Deterministic replay; never claims wall-clock currentness."""
    return _build(
        source_mapping=source_mapping,
        evaluation_time=evaluation_time,
        proof_mode=AS_OF_REPLAY,
    )


def issue_current_direct_provider_mapped_quotes(
    *,
    source_mapping: mapping.CurrentDirectProviderCanonicalMarketMappingRebind,
) -> CurrentDirectProviderMappedQuoteBundle:
    """Issue mapped current quotes from a verified PR252 LIVE_CURRENT source."""
    return _build(
        source_mapping=source_mapping,
        evaluation_time=_now_utc(),
        proof_mode=LIVE_CURRENT,
    )


def verify_current_direct_provider_mapped_quote_bundle(
    value: Any,
) -> CurrentDirectProviderMappedQuoteBundle:
    """Rebuild from the retained exact PR252 source and require exact equality."""
    if type(value) is not CurrentDirectProviderMappedQuoteBundle:
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            "value must be exact CurrentDirectProviderMappedQuoteBundle"
        )
    rebuilt = _build(
        source_mapping=value._source_mapping,
        evaluation_time=value.evaluation_time,
        proof_mode=value.proof_mode,
    )
    if _canonical_bytes(value.to_dict()) != _canonical_bytes(rebuilt.to_dict()):
        raise CurrentDirectProviderLiveQuoteMappingConsumptionError(
            "mapped quote bundle differs from exact retained-source reconstruction"
        )
    return rebuilt


__all__ = [
    "AS_OF_REPLAY",
    "AVAILABILITY_POLICY",
    "CONTRACT_VERSION",
    "CurrentDirectProviderLiveQuoteMappingConsumptionError",
    "CurrentDirectProviderMappedQuote",
    "CurrentDirectProviderMappedQuoteBundle",
    "CurrentMappedQuoteAudit",
    "DATASET_NAME",
    "DIRECT_EVENT_CONTRACT_SHA256",
    "EXPECTED_CONTRACT_SHA256",
    "IDENTITY_POLICY",
    "LIVE_CURRENT",
    "MAX_SOURCE_AGE_SECONDS",
    "MINIMUM_LEAD_SECONDS",
    "NEXT_BOUNDARY",
    "PRICE_POLICY",
    "PR252_CONTRACT_SHA256",
    "QuoteAuditDisposition",
    "SCHEMA_VERSION",
    "SETTLEMENT_POLICY",
    "STATUS_AS_OF",
    "STATUS_LIVE",
    "calculate_current_live_quote_mapping_contract_sha256",
    "issue_current_direct_provider_mapped_quotes",
    "issue_current_direct_provider_mapped_quotes_as_of",
    "validate_current_live_quote_mapping_contract",
    "verify_current_direct_provider_mapped_quote_bundle",
]
