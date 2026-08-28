"""Rebind reviewed SportyBet canonical market semantics to exact current events.

This boundary consumes:
1. a source-replayed PR #251 current-event/FotMob reconciliation bundle; and
2. an exact legacy reviewed canonical mapping rebuilt from its original reviewed
   reconciliation/native-inventory evidence and explicit review decisions.

It may rebind a legacy reviewed mapping row to a different current SportyBet
event only when provider market ID, specifier, outcome ID, market label and
outcome label are all exactly equal.  Event ID is deliberately the only native
identity component that may change.  Line markets are never generalized across
specifier values.  Bookmaker settlement authority is preserved exactly from
the reviewed source row.

This module does not copy odds, authorize a fresh price, compute value, route,
optimize, select, construct a slip, stake, execute, or place a bet.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
import enum
import hashlib
import json
import math
from pathlib import Path
import re
import types
from collections.abc import Mapping, Sequence
from typing import Any

from domain import sportybet_current_event_discovery_reconciliation as current
from domain import sportybet_live_event_quote_evidence as live
from domain import sportybet_reviewed_canonical_market_mapping as legacy
from domain.markets import MARKET_REGISTRY, MarketId, OutcomeId, make_selection
from domain.sportybet_early_payout_settlement import SportyBetEarlyPayoutSettlementReceipt

SCHEMA_VERSION = 1
CONTRACT_VERSION = 1
DATASET_NAME = "athena-current-direct-provider-canonical-market-mapping-rebind-v1"
STATUS = "CURRENT_DIRECT_PROVIDER_CANONICAL_MARKET_MAPPING_REBIND_VERIFIED"
PROVIDER = "SportyBet"
AS_OF_REPLAY = "AS_OF_REPLAY"
LIVE_CURRENT = "LIVE_CURRENT"
MAX_SOURCE_AGE_SECONDS = 900
MINIMUM_LEAD_SECONDS = 120
MATCHING_POLICY = (
    "EXACT_PROVIDER_MARKET_SPECIFIER_OUTCOME_AND_LABEL_EQUALITY_NO_ALIAS_NO_FUZZY"
)
LINE_REBIND_POLICY = "EXACT_REVIEWED_SPECIFIER_ONLY_NO_CROSS_LINE_GENERALIZATION"
PRICE_POLICY = "MAPPING_LAYER_DOES_NOT_COPY_OR_AUTHORIZE_ODDS"
SETTLEMENT_POLICY = "PRESERVE_EXACT_SOURCE_REVIEWED_SETTLEMENT_AUTHORITY_ONLY"
PR251_CONTRACT_SHA256 = (
    "64c7a2b71304f94a39de7e608be1f76a10e14a1a52a338f89d1c695ba0e5f1ee"
)
LEGACY_MAPPING_DATASET_NAME = "athena-sportybet-reviewed-canonical-market-mapping-v1"
LEGACY_MAPPING_STATUS = "REVIEWED_PROVIDER_NATIVE_CANONICAL_MARKET_MAPPING"
LEGACY_MAPPING_REVIEW_BASIS = (
    "EXPLICIT_REVIEW_OF_EXACT_PROVIDER_NATIVE_IDENTITY_AND_LABELS"
)
NEXT_BOUNDARY = "CURRENT_DIRECT_PROVIDER_LIVE_QUOTE_MAPPING_CONSUMPTION_REQUIRED"
EXPECTED_CONTRACT_SHA256 = "de022fd931313fa8d3c2c093ff0cb9b12f2c0f1ba0d9adc4b646c94dfd306e96"

_EVENT_RE = re.compile(r"^sr:match:[1-9][0-9]*$", re.ASCII)
_SHA_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)

CONTRACT_AUTHORITY = types.MappingProxyType(
    {
        "current_event_source_replay": True,
        "legacy_reviewed_mapping_source_replay": True,
        "exact_provider_semantic_rebind": True,
        "canonical_market_mapping": True,
        "fresh_price": False,
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


class CurrentDirectProviderCanonicalMappingRebindError(ValueError):
    """Raised when current canonical mapping rebind fails closed."""


class RebindAuditDisposition(str, enum.Enum):
    EXACT_REVIEWED_SEMANTIC_REBOUND = "EXACT_REVIEWED_SEMANTIC_REBOUND"
    SOURCE_TEMPLATE_ABSENT_FROM_CURRENT_EVENT = (
        "SOURCE_TEMPLATE_ABSENT_FROM_CURRENT_EVENT"
    )
    CURRENT_PROVIDER_LABEL_DRIFT_REJECTED = "CURRENT_PROVIDER_LABEL_DRIFT_REJECTED"


class RebindDisposition(str, enum.Enum):
    REBOUND_EXACT_REVIEWED_SEMANTICS = "REBOUND_EXACT_REVIEWED_SEMANTICS"
    NO_EXACT_REVIEWED_SEMANTICS = "NO_EXACT_REVIEWED_SEMANTICS"


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
        raise CurrentDirectProviderCanonicalMappingRebindError(
            "canonical JSON serialization failed"
        ) from exc


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        raise CurrentDirectProviderCanonicalMappingRebindError(
            f"{label} must be an exact SHA-256"
        )
    return value


def _event_id(value: Any) -> str:
    if type(value) is not str or _EVENT_RE.fullmatch(value) is None:
        raise CurrentDirectProviderCanonicalMappingRebindError(
            "event_id must use exact sr:match:<positive integer> form"
        )
    return value


def _utc(value: Any, label: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise CurrentDirectProviderCanonicalMappingRebindError(
            f"{label} must be timezone-aware"
        )
    try:
        return value.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CurrentDirectProviderCanonicalMappingRebindError(
            f"{label} is invalid"
        ) from exc


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _contract_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "dataset_name": DATASET_NAME,
        "status": STATUS,
        "provider": PROVIDER,
        "proof_modes": [AS_OF_REPLAY, LIVE_CURRENT],
        "max_source_age_seconds": MAX_SOURCE_AGE_SECONDS,
        "minimum_lead_seconds": MINIMUM_LEAD_SECONDS,
        "matching_policy": MATCHING_POLICY,
        "line_rebind_policy": LINE_REBIND_POLICY,
        "price_policy": PRICE_POLICY,
        "settlement_policy": SETTLEMENT_POLICY,
        "pr251_contract_sha256": PR251_CONTRACT_SHA256,
        "legacy_mapping_dataset_name": LEGACY_MAPPING_DATASET_NAME,
        "legacy_mapping_status": LEGACY_MAPPING_STATUS,
        "legacy_mapping_review_basis": LEGACY_MAPPING_REVIEW_BASIS,
        "target_market_ids": [item.value for item in legacy.TARGET_MARKET_IDS],
        "authority": dict(CONTRACT_AUTHORITY),
        "next_boundary": NEXT_BOUNDARY,
    }


def calculate_current_mapping_rebind_contract_sha256() -> str:
    return hashlib.sha256(_canonical_bytes(_contract_payload())).hexdigest()


def validate_current_mapping_rebind_contract() -> str:
    try:
        current.validate_current_event_discovery_contract()
        legacy._assert_target_registry()
    except (current.SportyBetCurrentEventDiscoveryError, legacy.SportyBetReviewedCanonicalMarketMappingError) as exc:
        raise CurrentDirectProviderCanonicalMappingRebindError(str(exc)) from exc
    if current.EXPECTED_CONTRACT_SHA256 != PR251_CONTRACT_SHA256:
        raise CurrentDirectProviderCanonicalMappingRebindError(
            "PR251 current-event contract identity drifted"
        )
    if (
        current.MAX_SOURCE_AGE_SECONDS != MAX_SOURCE_AGE_SECONDS
        or current.MINIMUM_LEAD_SECONDS != MINIMUM_LEAD_SECONDS
    ):
        raise CurrentDirectProviderCanonicalMappingRebindError(
            "PR251 currentness policy drifted"
        )
    if (
        legacy.DATASET_NAME != LEGACY_MAPPING_DATASET_NAME
        or legacy.STATUS != LEGACY_MAPPING_STATUS
        or legacy.REVIEW_BASIS != LEGACY_MAPPING_REVIEW_BASIS
    ):
        raise CurrentDirectProviderCanonicalMappingRebindError(
            "legacy reviewed canonical mapping metadata drifted"
        )
    if set(legacy.TARGET_MARKET_IDS) != set(MARKET_REGISTRY):
        raise CurrentDirectProviderCanonicalMappingRebindError(
            "legacy mapping target registry drifted"
        )
    calculated = calculate_current_mapping_rebind_contract_sha256()
    if calculated != EXPECTED_CONTRACT_SHA256:
        raise CurrentDirectProviderCanonicalMappingRebindError(
            "current canonical mapping rebind contract SHA-256 mismatch"
        )
    return calculated


@dataclasses.dataclass(frozen=True)
class CurrentCanonicalMappingAudit:
    source_event_id: str
    source_mapping_row_sha256: str
    provider_market_id: str
    provider_specifier: str | None
    provider_outcome_id: str
    reviewed_provider_market_name: str
    reviewed_provider_outcome_name: str
    current_provider_market_name: str | None
    current_provider_outcome_name: str | None
    canonical_market_id: MarketId
    canonical_outcome_id: OutcomeId
    canonical_line: float | None
    disposition: RebindAuditDisposition

    def __post_init__(self) -> None:
        _event_id(self.source_event_id)
        _sha(self.source_mapping_row_sha256, "source_mapping_row_sha256")
        if type(self.canonical_market_id) is not MarketId:
            raise CurrentDirectProviderCanonicalMappingRebindError(
                "audit canonical_market_id must be exact MarketId"
            )
        if type(self.canonical_outcome_id) is not OutcomeId:
            raise CurrentDirectProviderCanonicalMappingRebindError(
                "audit canonical_outcome_id must be exact OutcomeId"
            )
        if type(self.disposition) is not RebindAuditDisposition:
            raise CurrentDirectProviderCanonicalMappingRebindError(
                "audit disposition is invalid"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_event_id": self.source_event_id,
            "source_mapping_row_sha256": self.source_mapping_row_sha256,
            "provider_market_id": self.provider_market_id,
            "provider_specifier": self.provider_specifier,
            "provider_outcome_id": self.provider_outcome_id,
            "reviewed_provider_market_name": self.reviewed_provider_market_name,
            "reviewed_provider_outcome_name": self.reviewed_provider_outcome_name,
            "current_provider_market_name": self.current_provider_market_name,
            "current_provider_outcome_name": self.current_provider_outcome_name,
            "canonical_market_id": self.canonical_market_id.value,
            "canonical_outcome_id": self.canonical_outcome_id.value,
            "canonical_line": self.canonical_line,
            "disposition": self.disposition.value,
        }


@dataclasses.dataclass(frozen=True, init=False)
class CurrentDirectProviderCanonicalMappedSelection:
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
    canonical_display_label: str
    canonical_selection_display_name: str
    settlement_equivalence_authority: legacy.SettlementEquivalenceAuthority
    settlement_evidence_sha256: str | None
    bookmaker_equivalence_authorized: bool
    current_bookable_observed: bool
    current_bookability_basis: str
    source_mapping_row_sha256: str
    current_inventory_sha256: str
    canonical_market_mapping_authorized: bool

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise CurrentDirectProviderCanonicalMappingRebindError(
            "current canonical mapped selections are builder-only"
        )

    def to_dict(self) -> dict[str, Any]:
        result = {
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
            "canonical_display_label": self.canonical_display_label,
            "canonical_selection_display_name": self.canonical_selection_display_name,
            "settlement_equivalence_authority": self.settlement_equivalence_authority.value,
            "bookmaker_equivalence_authorized": self.bookmaker_equivalence_authorized,
            "current_bookable_observed": self.current_bookable_observed,
            "current_bookability_basis": self.current_bookability_basis,
            "source_mapping_row_sha256": self.source_mapping_row_sha256,
            "current_inventory_sha256": self.current_inventory_sha256,
            "canonical_market_mapping_authorized": True,
        }
        if self.settlement_evidence_sha256 is not None:
            result["settlement_evidence_sha256"] = self.settlement_evidence_sha256
        return result


def _set_frozen(obj: Any, values: Mapping[str, Any]) -> Any:
    for name, value in values.items():
        object.__setattr__(obj, name, value)
    return obj


def _source_row_sha256(row: legacy.MappedSportyBetCanonicalSelection) -> str:
    return hashlib.sha256(_canonical_bytes(row.to_dict())).hexdigest()


def _mapped_selection(
    *,
    fixture_id: str,
    event_id: str,
    source_row: legacy.MappedSportyBetCanonicalSelection,
    selected: live.SportyBetLiveEventSelection,
    current_inventory_sha256: str,
) -> CurrentDirectProviderCanonicalMappedSelection:
    canonical = make_selection(
        source_row.canonical_market_id,
        source_row.canonical_outcome_id,
        line=source_row.canonical_line,
    )
    value = object.__new__(CurrentDirectProviderCanonicalMappedSelection)
    return _set_frozen(
        value,
        {
            "fixture_id": fixture_id,
            "event_id": event_id,
            "provider_market_id": selected.market_id,
            "provider_market_name": selected.market_name,
            "provider_specifier": selected.specifier,
            "provider_outcome_id": selected.outcome_id,
            "provider_outcome_name": selected.outcome_name,
            "canonical_market_id": canonical.market_id,
            "canonical_outcome_id": canonical.outcome_id,
            "canonical_line": canonical.line,
            "canonical_display_label": canonical.display_label,
            "canonical_selection_display_name": canonical.selection_display_name,
            "settlement_equivalence_authority": (
                source_row.settlement_equivalence_authority
            ),
            "settlement_evidence_sha256": source_row.settlement_evidence_sha256,
            "bookmaker_equivalence_authorized": (
                source_row.bookmaker_equivalence_authorized
            ),
            "current_bookable_observed": selected.bookable,
            "current_bookability_basis": selected.bookability_basis,
            "source_mapping_row_sha256": _source_row_sha256(source_row),
            "current_inventory_sha256": current_inventory_sha256,
            "canonical_market_mapping_authorized": True,
        },
    )


def _derive_rows(
    *,
    fixture_id: str,
    event_id: str,
    source_mapping: legacy.SportyBetReviewedCanonicalMarketMapping,
    inventory: live.SportyBetLiveEventQuoteInventory,
) -> tuple[
    tuple[CurrentDirectProviderCanonicalMappedSelection, ...],
    tuple[CurrentCanonicalMappingAudit, ...],
    int,
]:
    if type(source_mapping) is not legacy.SportyBetReviewedCanonicalMarketMapping:
        raise CurrentDirectProviderCanonicalMappingRebindError(
            "source mapping must be exact reviewed canonical mapping"
        )
    if type(inventory) is not live.SportyBetLiveEventQuoteInventory:
        raise CurrentDirectProviderCanonicalMappingRebindError(
            "current inventory must be exact PR246 live event inventory"
        )
    if inventory.event_id != event_id:
        raise CurrentDirectProviderCanonicalMappingRebindError(
            "current inventory event identity mismatch"
        )
    safety = dict(source_mapping.safety)
    if (
        safety.get("canonical_market_mapping_authorized") is not True
        or safety.get("fresh_price_authorized") is not False
        or safety.get("pricing_authorized") is not False
        or safety.get("selection_authorized") is not False
        or safety.get("bet_authorized") is not False
    ):
        raise CurrentDirectProviderCanonicalMappingRebindError(
            "legacy reviewed mapping authority boundary drifted"
        )

    current_inventory_sha256 = inventory.canonical_sha256
    by_native = {
        (item.market_id, item.specifier, item.outcome_id): item
        for item in inventory.selections
    }
    if len(by_native) != len(inventory.selections):
        raise CurrentDirectProviderCanonicalMappingRebindError(
            "current inventory contains duplicate semantic native identity"
        )

    source_keys = set()
    mapped_rows: list[CurrentDirectProviderCanonicalMappedSelection] = []
    audits: list[CurrentCanonicalMappingAudit] = []
    for source_row in source_mapping.mapped_selections:
        if source_row.canonical_market_mapping_authorized is not True:
            raise CurrentDirectProviderCanonicalMappingRebindError(
                "source mapping row lacks canonical mapping authority"
            )
        key = (
            source_row.provider_market_id,
            source_row.provider_specifier,
            source_row.provider_outcome_id,
        )
        if key in source_keys:
            raise CurrentDirectProviderCanonicalMappingRebindError(
                "legacy mapping collapses to duplicate event-independent native identity"
            )
        source_keys.add(key)
        selected = by_native.get(key)
        if selected is None:
            disposition = RebindAuditDisposition.SOURCE_TEMPLATE_ABSENT_FROM_CURRENT_EVENT
            current_market_name = None
            current_outcome_name = None
        elif (
            selected.market_name != source_row.provider_market_name
            or selected.outcome_name != source_row.provider_selection_label
        ):
            disposition = RebindAuditDisposition.CURRENT_PROVIDER_LABEL_DRIFT_REJECTED
            current_market_name = selected.market_name
            current_outcome_name = selected.outcome_name
        else:
            disposition = RebindAuditDisposition.EXACT_REVIEWED_SEMANTIC_REBOUND
            current_market_name = selected.market_name
            current_outcome_name = selected.outcome_name
            mapped_rows.append(
                _mapped_selection(
                    fixture_id=fixture_id,
                    event_id=event_id,
                    source_row=source_row,
                    selected=selected,
                    current_inventory_sha256=current_inventory_sha256,
                )
            )
        audits.append(
            CurrentCanonicalMappingAudit(
                source_event_id=source_row.event_id,
                source_mapping_row_sha256=_source_row_sha256(source_row),
                provider_market_id=source_row.provider_market_id,
                provider_specifier=source_row.provider_specifier,
                provider_outcome_id=source_row.provider_outcome_id,
                reviewed_provider_market_name=source_row.provider_market_name,
                reviewed_provider_outcome_name=source_row.provider_selection_label,
                current_provider_market_name=current_market_name,
                current_provider_outcome_name=current_outcome_name,
                canonical_market_id=source_row.canonical_market_id,
                canonical_outcome_id=source_row.canonical_outcome_id,
                canonical_line=source_row.canonical_line,
                disposition=disposition,
            )
        )

    unreviewed_current = sum(
        1
        for item in inventory.selections
        if (item.market_id, item.specifier, item.outcome_id) not in source_keys
    )
    mapped_sorted = tuple(
        sorted(
            mapped_rows,
            key=lambda item: (
                legacy.TARGET_MARKET_IDS.index(item.canonical_market_id),
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
                legacy.TARGET_MARKET_IDS.index(item.canonical_market_id),
                "" if item.canonical_line is None else str(item.canonical_line),
                item.canonical_outcome_id.value,
                item.provider_market_id,
                item.provider_outcome_id,
            ),
        )
    )
    return mapped_sorted, audits_sorted, unreviewed_current


def _bundle_authority(
    *,
    proof_mode: str,
    mapped: Sequence[CurrentDirectProviderCanonicalMappedSelection],
) -> Mapping[str, bool]:
    has_mapping = bool(mapped)
    all_equivalent = has_mapping and all(
        item.bookmaker_equivalence_authorized for item in mapped
    )
    return types.MappingProxyType(
        {
            "current_event_source_replay": True,
            "legacy_reviewed_mapping_source_replay": True,
            "exact_provider_semantic_rebind": has_mapping,
            "canonical_market_mapping": has_mapping,
            "bookmaker_equivalence": all_equivalent,
            "as_of_source_freshness": True,
            "wall_clock_currentness_at_issuance": proof_mode == LIVE_CURRENT,
            "fresh_price": False,
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


@dataclasses.dataclass(frozen=True, init=False)
class CurrentDirectProviderCanonicalMarketMappingRebind:
    schema_version: int
    dataset_name: str
    status: str
    proof_mode: str
    disposition: RebindDisposition
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
    source_current_reconciliation_sha256: str
    source_current_reconciliation_contract_sha256: str
    source_legacy_mapping_sha256: str
    source_legacy_review_decisions_sha256: str
    source_legacy_event_id: str
    source_legacy_fixture_id: str
    current_inventory_sha256: str
    current_manifest_sha256: str
    current_raw_sha256: str
    mapped_selections: tuple[CurrentDirectProviderCanonicalMappedSelection, ...]
    mapping_audits: tuple[CurrentCanonicalMappingAudit, ...]
    source_template_count: int
    mapped_selection_count: int
    unreviewed_current_selection_count: int
    represented_target_market_ids: tuple[MarketId, ...]
    unrepresented_target_market_ids: tuple[MarketId, ...]
    all_source_templates_rebound: bool
    all_15_target_markets_represented: bool
    authority: Mapping[str, bool]
    next_boundary: str
    contract_sha256: str
    _current_bundle: current.SportyBetCurrentEventDiscoveryReconciliationBundle
    _target_event_id: str
    _legacy_reconciliation_receipt_directory: Any
    _legacy_reconciliation_source_bundle: Any
    _legacy_review_decisions: tuple[legacy.ReviewedCanonicalMappingDecision, ...]
    _legacy_repository_root: Path
    _early_payout_settlement_receipt: SportyBetEarlyPayoutSettlementReceipt | None
    _early_payout_settlement_receipt_bytes: bytes | None

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise CurrentDirectProviderCanonicalMappingRebindError(
            "current canonical mapping rebinds are builder-only"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "status": self.status,
            "proof_mode": self.proof_mode,
            "disposition": self.disposition.value,
            "evaluation_time": self.evaluation_time.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "event_id": self.event_id,
            "fixture_id": self.fixture_id,
            "home_team_name": self.home_team_name,
            "away_team_name": self.away_team_name,
            "kickoff_utc": self.kickoff_utc.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "discovery_observed_at": self.discovery_observed_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "direct_event_observed_at": self.direct_event_observed_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "discovery_age_seconds": self.discovery_age_seconds,
            "direct_event_age_seconds": self.direct_event_age_seconds,
            "kickoff_lead_seconds": self.kickoff_lead_seconds,
            "max_source_age_seconds": self.max_source_age_seconds,
            "minimum_lead_seconds": self.minimum_lead_seconds,
            "source_current_reconciliation_sha256": self.source_current_reconciliation_sha256,
            "source_current_reconciliation_contract_sha256": self.source_current_reconciliation_contract_sha256,
            "source_legacy_mapping_sha256": self.source_legacy_mapping_sha256,
            "source_legacy_review_decisions_sha256": self.source_legacy_review_decisions_sha256,
            "source_legacy_event_id": self.source_legacy_event_id,
            "source_legacy_fixture_id": self.source_legacy_fixture_id,
            "current_inventory_sha256": self.current_inventory_sha256,
            "current_manifest_sha256": self.current_manifest_sha256,
            "current_raw_sha256": self.current_raw_sha256,
            "mapped_selection_count": self.mapped_selection_count,
            "source_template_count": self.source_template_count,
            "unreviewed_current_selection_count": self.unreviewed_current_selection_count,
            "mapped_selections": [item.to_dict() for item in self.mapped_selections],
            "mapping_audits": [item.to_dict() for item in self.mapping_audits],
            "represented_target_market_ids": [item.value for item in self.represented_target_market_ids],
            "unrepresented_target_market_ids": [item.value for item in self.unrepresented_target_market_ids],
            "all_source_templates_rebound": self.all_source_templates_rebound,
            "all_15_target_markets_represented": self.all_15_target_markets_represented,
            "authority": dict(self.authority),
            "next_boundary": self.next_boundary,
            "contract_sha256": self.contract_sha256,
            "provider_quote_at": None,
            "provider_snapshot_id": None,
            "wager_placed": False,
        }

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(_canonical_bytes(self.to_dict())).hexdigest()


def _detail_directory(
    bundle: current.SportyBetCurrentEventDiscoveryReconciliationBundle,
    event_id: str,
) -> Path:
    rows = dict(bundle._detail_directories)
    if event_id not in rows:
        raise CurrentDirectProviderCanonicalMappingRebindError(
            "current reconciliation did not retain direct detail evidence for event"
        )
    return Path(rows[event_id])


def _target_row(
    bundle: current.SportyBetCurrentEventDiscoveryReconciliationBundle,
    event_id: str,
) -> current.CurrentEventReconciliationRow:
    rows = [item for item in bundle.rows if item.event_id == event_id]
    if len(rows) != 1:
        raise CurrentDirectProviderCanonicalMappingRebindError(
            "target event must occur exactly once in current reconciliation bundle"
        )
    row = rows[0]
    if (
        row.disposition
        is not current.CurrentEventReconciliationDisposition.UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED
        or row.fixture_reconciliation_authorized is not True
        or row.matched_fotmob_fixture_id is None
        or row.direct_event_observed_at is None
        or row.direct_event_manifest_sha256 is None
        or row.direct_event_inventory_sha256 is None
        or row.direct_event_raw_sha256 is None
    ):
        raise CurrentDirectProviderCanonicalMappingRebindError(
            "target event lacks exact current fixture-reconciliation authority"
        )
    return row


def _rebuild_legacy_mapping(
    *,
    reconciliation_receipt_directory: Any,
    reconciliation_source_bundle: Any,
    review_decisions: Sequence[legacy.ReviewedCanonicalMappingDecision],
    repository_root: Path,
    early_payout_settlement_receipt: SportyBetEarlyPayoutSettlementReceipt | None,
    early_payout_settlement_receipt_bytes: bytes | None,
) -> legacy.SportyBetReviewedCanonicalMarketMapping:
    try:
        return legacy.build_reviewed_canonical_market_mapping(
            reconciliation_receipt_directory=reconciliation_receipt_directory,
            reconciliation_source_bundle=reconciliation_source_bundle,
            review_decisions=review_decisions,
            repository_root=Path(repository_root),
            early_payout_settlement_receipt=early_payout_settlement_receipt,
            early_payout_settlement_receipt_bytes=early_payout_settlement_receipt_bytes,
        )
    except legacy.SportyBetReviewedCanonicalMarketMappingError as exc:
        raise CurrentDirectProviderCanonicalMappingRebindError(
            f"legacy reviewed mapping source replay failed closed: {exc}"
        ) from exc


def _build_from_verified_sources(
    *,
    verified_current: current.SportyBetCurrentEventDiscoveryReconciliationBundle,
    target_event_id: str,
    source_mapping: legacy.SportyBetReviewedCanonicalMarketMapping,
    evaluation_time: datetime,
    proof_mode: str,
    legacy_reconciliation_receipt_directory: Any,
    legacy_reconciliation_source_bundle: Any,
    legacy_review_decisions: Sequence[legacy.ReviewedCanonicalMappingDecision],
    legacy_repository_root: Path,
    early_payout_settlement_receipt: SportyBetEarlyPayoutSettlementReceipt | None,
    early_payout_settlement_receipt_bytes: bytes | None,
) -> CurrentDirectProviderCanonicalMarketMappingRebind:
    validate_current_mapping_rebind_contract()
    event_id = _event_id(target_event_id)
    if proof_mode not in {AS_OF_REPLAY, LIVE_CURRENT}:
        raise CurrentDirectProviderCanonicalMappingRebindError("proof_mode is invalid")
    evaluation = _utc(evaluation_time, "evaluation_time")
    current_evaluation = _utc(verified_current.evaluation_time, "current bundle evaluation_time")
    if evaluation < current_evaluation:
        raise CurrentDirectProviderCanonicalMappingRebindError(
            "mapping evaluation_time cannot predate current reconciliation issuance"
        )
    if (
        verified_current.max_source_age_seconds != MAX_SOURCE_AGE_SECONDS
        or verified_current.minimum_lead_seconds != MINIMUM_LEAD_SECONDS
        or verified_current.contract_sha256 != PR251_CONTRACT_SHA256
    ):
        raise CurrentDirectProviderCanonicalMappingRebindError(
            "current reconciliation policy/contract identity mismatch"
        )
    row = _target_row(verified_current, event_id)
    detail_directory = _detail_directory(verified_current, event_id)
    try:
        inventory = live.build_live_event_quote_inventory(
            detail_directory,
            repository_root=verified_current._repository_root,
        )
    except live.SportyBetLiveEventQuoteEvidenceError as exc:
        raise CurrentDirectProviderCanonicalMappingRebindError(
            f"current direct event-detail replay failed closed: {exc}"
        ) from exc
    if (
        inventory.event_id != row.event_id
        or inventory.home_team_name != row.home_team_name
        or inventory.away_team_name != row.away_team_name
        or inventory.kickoff_utc != row.kickoff_utc
    ):
        raise CurrentDirectProviderCanonicalMappingRebindError(
            "current direct event-detail identity differs from reconciled fixture"
        )
    if (
        inventory.canonical_sha256 != row.direct_event_inventory_sha256
        or inventory.source_manifest_sha256 != row.direct_event_manifest_sha256
        or inventory.source_raw_sha256 != row.direct_event_raw_sha256
        or inventory.observed_at != row.direct_event_observed_at
    ):
        raise CurrentDirectProviderCanonicalMappingRebindError(
            "current direct event-detail provenance differs from PR251 reconciliation"
        )
    if not inventory.prematch_bookable_observed:
        raise CurrentDirectProviderCanonicalMappingRebindError(
            "current event is no longer proven prematch/bookable by retained evidence"
        )

    discovery_age = (evaluation - row.discovery_observed_at).total_seconds()
    direct_age = (evaluation - inventory.observed_at).total_seconds()
    kickoff_lead = (row.kickoff_utc - evaluation).total_seconds()
    for value, label in (
        (discovery_age, "discovery age"),
        (direct_age, "direct event age"),
        (kickoff_lead, "kickoff lead"),
    ):
        if not math.isfinite(value):
            raise CurrentDirectProviderCanonicalMappingRebindError(
                f"{label} is non-finite"
            )
    if discovery_age < 0 or direct_age < 0:
        raise CurrentDirectProviderCanonicalMappingRebindError(
            "mapping evaluation predates retained provider evidence"
        )
    if discovery_age > MAX_SOURCE_AGE_SECONDS or direct_age > MAX_SOURCE_AGE_SECONDS:
        raise CurrentDirectProviderCanonicalMappingRebindError(
            "current provider evidence is stale at mapping rebind evaluation"
        )
    if kickoff_lead <= MINIMUM_LEAD_SECONDS:
        raise CurrentDirectProviderCanonicalMappingRebindError(
            "current event is too close to kickoff for mapping rebind"
        )

    mapped, audits, unreviewed_current = _derive_rows(
        fixture_id=row.matched_fotmob_fixture_id,
        event_id=event_id,
        source_mapping=source_mapping,
        inventory=inventory,
    )
    represented = tuple(
        market_id
        for market_id in legacy.TARGET_MARKET_IDS
        if any(item.canonical_market_id is market_id for item in mapped)
    )
    unrepresented = tuple(
        market_id for market_id in legacy.TARGET_MARKET_IDS if market_id not in represented
    )
    exact_audits = sum(
        item.disposition is RebindAuditDisposition.EXACT_REVIEWED_SEMANTIC_REBOUND
        for item in audits
    )
    disposition = (
        RebindDisposition.REBOUND_EXACT_REVIEWED_SEMANTICS
        if mapped
        else RebindDisposition.NO_EXACT_REVIEWED_SEMANTICS
    )
    source_current_sha = hashlib.sha256(
        _canonical_bytes(verified_current.to_dict())
    ).hexdigest()
    source_mapping_sha = legacy.canonical_mapping_sha256(source_mapping)
    value = object.__new__(CurrentDirectProviderCanonicalMarketMappingRebind)
    return _set_frozen(
        value,
        {
            "schema_version": SCHEMA_VERSION,
            "dataset_name": DATASET_NAME,
            "status": STATUS,
            "proof_mode": proof_mode,
            "disposition": disposition,
            "evaluation_time": evaluation,
            "event_id": event_id,
            "fixture_id": row.matched_fotmob_fixture_id,
            "home_team_name": row.home_team_name,
            "away_team_name": row.away_team_name,
            "kickoff_utc": row.kickoff_utc,
            "discovery_observed_at": row.discovery_observed_at,
            "direct_event_observed_at": inventory.observed_at,
            "discovery_age_seconds": discovery_age,
            "direct_event_age_seconds": direct_age,
            "kickoff_lead_seconds": kickoff_lead,
            "max_source_age_seconds": MAX_SOURCE_AGE_SECONDS,
            "minimum_lead_seconds": MINIMUM_LEAD_SECONDS,
            "source_current_reconciliation_sha256": source_current_sha,
            "source_current_reconciliation_contract_sha256": PR251_CONTRACT_SHA256,
            "source_legacy_mapping_sha256": source_mapping_sha,
            "source_legacy_review_decisions_sha256": source_mapping.review_decisions_sha256,
            "source_legacy_event_id": source_mapping.sportybet_event_id,
            "source_legacy_fixture_id": source_mapping.matched_fotmob_fixture_id,
            "current_inventory_sha256": inventory.canonical_sha256,
            "current_manifest_sha256": inventory.source_manifest_sha256,
            "current_raw_sha256": inventory.source_raw_sha256,
            "mapped_selections": mapped,
            "mapping_audits": audits,
            "source_template_count": len(source_mapping.mapped_selections),
            "mapped_selection_count": len(mapped),
            "unreviewed_current_selection_count": unreviewed_current,
            "represented_target_market_ids": represented,
            "unrepresented_target_market_ids": unrepresented,
            "all_source_templates_rebound": exact_audits == len(audits),
            "all_15_target_markets_represented": not unrepresented,
            "authority": _bundle_authority(proof_mode=proof_mode, mapped=mapped),
            "next_boundary": NEXT_BOUNDARY,
            "contract_sha256": EXPECTED_CONTRACT_SHA256,
            "_current_bundle": verified_current,
            "_target_event_id": event_id,
            "_legacy_reconciliation_receipt_directory": (
                legacy_reconciliation_receipt_directory
            ),
            "_legacy_reconciliation_source_bundle": legacy_reconciliation_source_bundle,
            "_legacy_review_decisions": tuple(legacy_review_decisions),
            "_legacy_repository_root": Path(legacy_repository_root),
            "_early_payout_settlement_receipt": early_payout_settlement_receipt,
            "_early_payout_settlement_receipt_bytes": early_payout_settlement_receipt_bytes,
        },
    )


def _build_from_sources(
    *,
    current_reconciliation_bundle: current.SportyBetCurrentEventDiscoveryReconciliationBundle,
    target_event_id: str,
    legacy_reconciliation_receipt_directory: Any,
    legacy_reconciliation_source_bundle: Any,
    legacy_review_decisions: Sequence[legacy.ReviewedCanonicalMappingDecision],
    legacy_repository_root: Path,
    evaluation_time: datetime,
    proof_mode: str,
    early_payout_settlement_receipt: SportyBetEarlyPayoutSettlementReceipt | None = None,
    early_payout_settlement_receipt_bytes: bytes | None = None,
) -> CurrentDirectProviderCanonicalMarketMappingRebind:
    validate_current_mapping_rebind_contract()
    try:
        verified_current = current.verify_current_event_discovery_reconciliation_bundle(
            current_reconciliation_bundle
        )
    except current.SportyBetCurrentEventDiscoveryError as exc:
        raise CurrentDirectProviderCanonicalMappingRebindError(
            f"PR251 current reconciliation source replay failed closed: {exc}"
        ) from exc
    source_mapping = _rebuild_legacy_mapping(
        reconciliation_receipt_directory=legacy_reconciliation_receipt_directory,
        reconciliation_source_bundle=legacy_reconciliation_source_bundle,
        review_decisions=legacy_review_decisions,
        repository_root=legacy_repository_root,
        early_payout_settlement_receipt=early_payout_settlement_receipt,
        early_payout_settlement_receipt_bytes=early_payout_settlement_receipt_bytes,
    )
    return _build_from_verified_sources(
        verified_current=verified_current,
        target_event_id=target_event_id,
        source_mapping=source_mapping,
        evaluation_time=evaluation_time,
        proof_mode=proof_mode,
        legacy_reconciliation_receipt_directory=legacy_reconciliation_receipt_directory,
        legacy_reconciliation_source_bundle=legacy_reconciliation_source_bundle,
        legacy_review_decisions=legacy_review_decisions,
        legacy_repository_root=legacy_repository_root,
        early_payout_settlement_receipt=early_payout_settlement_receipt,
        early_payout_settlement_receipt_bytes=early_payout_settlement_receipt_bytes,
    )


def rebind_current_direct_provider_canonical_mapping_as_of(
    *,
    current_reconciliation_bundle: current.SportyBetCurrentEventDiscoveryReconciliationBundle,
    target_event_id: str,
    legacy_reconciliation_receipt_directory: Any,
    legacy_reconciliation_source_bundle: Any,
    legacy_review_decisions: Sequence[legacy.ReviewedCanonicalMappingDecision],
    legacy_repository_root: Path,
    evaluation_time: datetime,
    early_payout_settlement_receipt: SportyBetEarlyPayoutSettlementReceipt | None = None,
    early_payout_settlement_receipt_bytes: bytes | None = None,
) -> CurrentDirectProviderCanonicalMarketMappingRebind:
    """Deterministic replay; does not claim wall-clock currentness."""
    return _build_from_sources(
        current_reconciliation_bundle=current_reconciliation_bundle,
        target_event_id=target_event_id,
        legacy_reconciliation_receipt_directory=legacy_reconciliation_receipt_directory,
        legacy_reconciliation_source_bundle=legacy_reconciliation_source_bundle,
        legacy_review_decisions=legacy_review_decisions,
        legacy_repository_root=legacy_repository_root,
        evaluation_time=evaluation_time,
        proof_mode=AS_OF_REPLAY,
        early_payout_settlement_receipt=early_payout_settlement_receipt,
        early_payout_settlement_receipt_bytes=early_payout_settlement_receipt_bytes,
    )


def rebind_current_direct_provider_canonical_mapping(
    *,
    current_reconciliation_bundle: current.SportyBetCurrentEventDiscoveryReconciliationBundle,
    target_event_id: str,
    legacy_reconciliation_receipt_directory: Any,
    legacy_reconciliation_source_bundle: Any,
    legacy_review_decisions: Sequence[legacy.ReviewedCanonicalMappingDecision],
    legacy_repository_root: Path,
    early_payout_settlement_receipt: SportyBetEarlyPayoutSettlementReceipt | None = None,
    early_payout_settlement_receipt_bytes: bytes | None = None,
) -> CurrentDirectProviderCanonicalMarketMappingRebind:
    """Issue a mapping rebind after rechecking retained current evidence now."""
    return _build_from_sources(
        current_reconciliation_bundle=current_reconciliation_bundle,
        target_event_id=target_event_id,
        legacy_reconciliation_receipt_directory=legacy_reconciliation_receipt_directory,
        legacy_reconciliation_source_bundle=legacy_reconciliation_source_bundle,
        legacy_review_decisions=legacy_review_decisions,
        legacy_repository_root=legacy_repository_root,
        evaluation_time=_now_utc(),
        proof_mode=LIVE_CURRENT,
        early_payout_settlement_receipt=early_payout_settlement_receipt,
        early_payout_settlement_receipt_bytes=early_payout_settlement_receipt_bytes,
    )


def verify_current_direct_provider_canonical_mapping_rebind(
    value: Any,
) -> CurrentDirectProviderCanonicalMarketMappingRebind:
    """Replay both current and legacy retained sources and require exact equality."""
    if type(value) is not CurrentDirectProviderCanonicalMarketMappingRebind:
        raise CurrentDirectProviderCanonicalMappingRebindError(
            "value must be exact CurrentDirectProviderCanonicalMarketMappingRebind"
        )
    rebuilt = _build_from_sources(
        current_reconciliation_bundle=value._current_bundle,
        target_event_id=value._target_event_id,
        legacy_reconciliation_receipt_directory=(
            value._legacy_reconciliation_receipt_directory
        ),
        legacy_reconciliation_source_bundle=value._legacy_reconciliation_source_bundle,
        legacy_review_decisions=value._legacy_review_decisions,
        legacy_repository_root=value._legacy_repository_root,
        evaluation_time=value.evaluation_time,
        proof_mode=value.proof_mode,
        early_payout_settlement_receipt=value._early_payout_settlement_receipt,
        early_payout_settlement_receipt_bytes=(
            value._early_payout_settlement_receipt_bytes
        ),
    )
    if _canonical_bytes(value.to_dict()) != _canonical_bytes(rebuilt.to_dict()):
        raise CurrentDirectProviderCanonicalMappingRebindError(
            "current canonical mapping rebind differs from exact retained-source reconstruction"
        )
    return rebuilt


__all__ = [
    "AS_OF_REPLAY",
    "CONTRACT_VERSION",
    "CurrentCanonicalMappingAudit",
    "CurrentDirectProviderCanonicalMappedSelection",
    "CurrentDirectProviderCanonicalMappingRebindError",
    "CurrentDirectProviderCanonicalMarketMappingRebind",
    "DATASET_NAME",
    "EXPECTED_CONTRACT_SHA256",
    "LINE_REBIND_POLICY",
    "LIVE_CURRENT",
    "MATCHING_POLICY",
    "MAX_SOURCE_AGE_SECONDS",
    "MINIMUM_LEAD_SECONDS",
    "NEXT_BOUNDARY",
    "PRICE_POLICY",
    "PR251_CONTRACT_SHA256",
    "RebindAuditDisposition",
    "RebindDisposition",
    "SCHEMA_VERSION",
    "SETTLEMENT_POLICY",
    "STATUS",
    "calculate_current_mapping_rebind_contract_sha256",
    "rebind_current_direct_provider_canonical_mapping",
    "rebind_current_direct_provider_canonical_mapping_as_of",
    "validate_current_mapping_rebind_contract",
    "verify_current_direct_provider_canonical_mapping_rebind",
]
