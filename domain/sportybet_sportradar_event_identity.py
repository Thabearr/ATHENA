"""Documentation-backed SportyBet -> Sportradar event identifier bridge.

This boundary re-derives the exact machine event-header candidate from preserved
SportyBet evidence, then interprets only the provider event-ID namespace using a
frozen review of official Sportradar documentation.

Official Sportradar documentation reviewed on 2026-08-18 documents the legacy
``sr:match:<n>`` sport-event prefix, its migration to ``sr:sport_event:<n>``
with the numeric identifier preserved, and unique soccer sport-event IDs. That
lets ATHENA freeze a non-circular resolver key without borrowing a year from
FotMob or from the current calendar.

This module does not resolve Sportradar event metadata, infer kickoff year, make
a network request, prove SportyBet/FotMob fixture equivalence, or authorize any
pricing, selection, booking-code, execution, or BET path.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import types
from collections.abc import Mapping
from typing import Any

from domain import sportybet_machine_event_header_candidate as header
from domain import sportybet_user_controlled_evidence as manual
from domain import sportybet_user_controlled_native_inventory as native
from domain.sportybet_lite_source_capture import SportyBetLiteRequestKind

SCHEMA_VERSION = 1
DATASET_NAME = "athena-sportybet-sportradar-event-identity-v1"
PROVIDER = "SportyBet"
STATUS = "DOCUMENTED_SPORTRADAR_EVENT_ID_NAMESPACE_CANDIDATE"
IDENTIFIER_AUTHORITY = "REVIEWED_OFFICIAL_SPORTRADAR_DOCUMENTATION_ONLY"
LEGACY_SPORT_EVENT_PREFIX = "sr:match:"
CURRENT_SPORT_EVENT_PREFIX = "sr:sport_event:"
SOCCER_SPORT_ID = "sr:sport:1"
MIGRATION_GUIDE_URL = (
    "https://developer.sportradar.com/soccer/reference/"
    "soccer-v3-to-v4-migration-guide"
)
ID_HANDLING_URL = (
    "https://developer.sportradar.com/soccer/docs/soccer-ig-id-handling"
)
DOCUMENTATION_REVIEWED_AT = "2026-08-18"
DOCUMENTATION_CONTRACT_SHA256 = (
    "ea3417948148b5ae2aa7c1aac4f5795437bfe913b67c6212d31267d8cd36d902"
)
MAX_CANONICAL_BYTES = 256 * 1024

_LEGACY_EVENT_ID_RE = re.compile(r"^sr:match:(?P<n>[1-9][0-9]*)$", flags=re.ASCII)
_CURRENT_EVENT_ID_RE = re.compile(
    r"^sr:sport_event:(?P<n>[1-9][0-9]*)$",
    flags=re.ASCII,
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_EVIDENCE_ID_RE = re.compile(r"^[0-9a-f]{24}$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "bet_authorized",
        "bookmaker_equivalence_authorized",
        "booking_code_authorized",
        "canonical_market_mapping_authorized",
        "fixture_reconciliation_authorized",
        "fresh_price_authorized",
        "model_integration_authorized",
        "network_acquisition_authorized",
        "pricing_authorized",
        "selection_authorized",
        "slip_construction_authorized",
        "sportradar_metadata_resolution_authorized",
        "sportybet_execution_authorized",
    }
)


class SportyBetSportradarEventIdentityError(ValueError):
    """Raised when the documented event-ID bridge fails closed."""


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(_SAFETY_KEYS)}


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise SportyBetSportradarEventIdentityError("safety keys mismatch")
    detached: dict[str, bool] = {}
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise SportyBetSportradarEventIdentityError(
                f"safety[{key!r}] must be exact bool False"
            )
        detached[key] = False
    return types.MappingProxyType(detached)


def _hash(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise SportyBetSportradarEventIdentityError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _evidence_id(value: Any) -> str:
    if type(value) is not str or _EVIDENCE_ID_RE.fullmatch(value) is None:
        raise SportyBetSportradarEventIdentityError("source_evidence_id is invalid")
    return value


def _text(value: Any, label: str, *, maximum: int = 512) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise SportyBetSportradarEventIdentityError(
            f"{label} must be a non-empty exact trimmed string"
        )
    if len(value) > maximum:
        raise SportyBetSportradarEventIdentityError(
            f"{label} exceeds {maximum} characters"
        )
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise SportyBetSportradarEventIdentityError(
            f"{label} contains a control character"
        )
    return value


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise SportyBetSportradarEventIdentityError(
            "canonical serialization failed"
        ) from exc


def documentation_contract() -> dict[str, Any]:
    """Return the frozen reviewed documentation semantics, not live web data."""

    return {
        "authority": IDENTIFIER_AUTHORITY,
        "current_sport_event_prefix": CURRENT_SPORT_EVENT_PREFIX,
        "id_handling_url": ID_HANDLING_URL,
        "legacy_sport_event_prefix": LEGACY_SPORT_EVENT_PREFIX,
        "migration_guide_url": MIGRATION_GUIDE_URL,
        "numeric_identifier_preserved_across_prefix_migration": True,
        "reviewed_at": DOCUMENTATION_REVIEWED_AT,
        "soccer_match_sport_event_identifier_uniqueness_documented": True,
        "soccer_sport_id": SOCCER_SPORT_ID,
    }


def documentation_contract_bytes() -> bytes:
    return _canonical_bytes(documentation_contract())


def documentation_contract_sha256() -> str:
    value = hashlib.sha256(documentation_contract_bytes()).hexdigest()
    if value != DOCUMENTATION_CONTRACT_SHA256:  # pragma: no cover - frozen invariant
        raise SportyBetSportradarEventIdentityError(
            "frozen Sportradar documentation contract hash mismatch"
        )
    return value


def _legacy_numeric_payload(value: Any) -> str:
    text = _text(value, "sportybet_event_id", maximum=160)
    match = _LEGACY_EVENT_ID_RE.fullmatch(text)
    if match is None:
        raise SportyBetSportradarEventIdentityError(
            "SportyBet eventId is not a canonical documented legacy Sportradar sport-event ID"
        )
    return match.group("n")


def _validate_current_id(value: Any, numeric_payload: str) -> str:
    text = _text(value, "sportradar_current_sport_event_id", maximum=180)
    match = _CURRENT_EVENT_ID_RE.fullmatch(text)
    if match is None or match.group("n") != numeric_payload:
        raise SportyBetSportradarEventIdentityError(
            "current Sportradar sport-event ID must preserve the exact legacy numeric payload"
        )
    return text


@dataclasses.dataclass(frozen=True)
class SportyBetSportradarEventIdentityBridge:
    schema_version: int
    dataset_name: str
    provider: str
    status: str
    source_event_candidate_sha256: str
    source_evidence_id: str
    source_evidence_manifest_sha256: str
    source_native_inventory_sha256: str
    source_raw_sha256: str
    source_url: str
    sportybet_event_id: str
    sportybet_sport_id: str
    sportradar_numeric_event_id: int
    sportradar_legacy_sport_event_id: str
    sportradar_current_sport_event_id: str
    identifier_authority: str
    documentation_contract_sha256: str
    migration_guide_url: str
    id_handling_url: str
    numeric_identifier_preserved: bool
    soccer_match_identifier_uniqueness_documented: bool
    sportradar_namespace_qualified: bool
    event_metadata_resolved: bool
    fixture_identity_proven: bool
    sportybet_kickoff_year: None
    sportybet_kickoff_utc: None
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise SportyBetSportradarEventIdentityError("schema_version mismatch")
        if self.dataset_name != DATASET_NAME or self.provider != PROVIDER:
            raise SportyBetSportradarEventIdentityError("dataset/provider mismatch")
        if self.status != STATUS:
            raise SportyBetSportradarEventIdentityError("status mismatch")
        _hash(self.source_event_candidate_sha256, "source_event_candidate_sha256")
        _evidence_id(self.source_evidence_id)
        _hash(self.source_evidence_manifest_sha256, "source_evidence_manifest_sha256")
        _hash(self.source_native_inventory_sha256, "source_native_inventory_sha256")
        _hash(self.source_raw_sha256, "source_raw_sha256")

        try:
            kind, event_id, sport_id, _market_group, _target = manual.validate_source_url(
                self.source_url
            )
        except manual.SportyBetUserEvidenceError as exc:
            raise SportyBetSportradarEventIdentityError(str(exc)) from exc
        if kind is not SportyBetLiteRequestKind.EVENT_DETAIL:
            raise SportyBetSportradarEventIdentityError(
                "source URL must be reviewed SportyBet event-detail evidence"
            )
        if event_id != self.sportybet_event_id or sport_id != self.sportybet_sport_id:
            raise SportyBetSportradarEventIdentityError(
                "source URL does not bind the emitted SportyBet event/sport identity"
            )
        if self.sportybet_sport_id != SOCCER_SPORT_ID:
            raise SportyBetSportradarEventIdentityError(
                "documented bridge is frozen to soccer sportId sr:sport:1"
            )

        numeric_text = _legacy_numeric_payload(self.sportybet_event_id)
        if self.sportradar_legacy_sport_event_id != self.sportybet_event_id:
            raise SportyBetSportradarEventIdentityError(
                "legacy Sportradar sport-event ID must equal exact SportyBet eventId"
            )
        if (
            type(self.sportradar_numeric_event_id) is not int
            or isinstance(self.sportradar_numeric_event_id, bool)
            or self.sportradar_numeric_event_id <= 0
            or str(self.sportradar_numeric_event_id) != numeric_text
        ):
            raise SportyBetSportradarEventIdentityError(
                "numeric Sportradar event ID does not equal the canonical legacy payload"
            )
        _validate_current_id(self.sportradar_current_sport_event_id, numeric_text)

        if self.identifier_authority != IDENTIFIER_AUTHORITY:
            raise SportyBetSportradarEventIdentityError("identifier_authority mismatch")
        if self.documentation_contract_sha256 != documentation_contract_sha256():
            raise SportyBetSportradarEventIdentityError(
                "documentation_contract_sha256 mismatch"
            )
        if self.migration_guide_url != MIGRATION_GUIDE_URL:
            raise SportyBetSportradarEventIdentityError("migration_guide_url mismatch")
        if self.id_handling_url != ID_HANDLING_URL:
            raise SportyBetSportradarEventIdentityError("id_handling_url mismatch")
        for label in (
            "numeric_identifier_preserved",
            "soccer_match_identifier_uniqueness_documented",
            "sportradar_namespace_qualified",
        ):
            if getattr(self, label) is not True:
                raise SportyBetSportradarEventIdentityError(
                    f"{label} must be exact True"
                )
        for label in ("event_metadata_resolved", "fixture_identity_proven"):
            if getattr(self, label) is not False:
                raise SportyBetSportradarEventIdentityError(
                    f"{label} must be exact False"
                )
        if self.sportybet_kickoff_year is not None or self.sportybet_kickoff_utc is not None:
            raise SportyBetSportradarEventIdentityError(
                "kickoff year/UTC remain unresolved and must be null"
            )
        object.__setattr__(self, "safety", _validate_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "provider": self.provider,
            "status": self.status,
            "source_event_candidate_sha256": self.source_event_candidate_sha256,
            "source_evidence_id": self.source_evidence_id,
            "source_evidence_manifest_sha256": self.source_evidence_manifest_sha256,
            "source_native_inventory_sha256": self.source_native_inventory_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "source_url": self.source_url,
            "sportybet_event_id": self.sportybet_event_id,
            "sportybet_sport_id": self.sportybet_sport_id,
            "sportradar_numeric_event_id": self.sportradar_numeric_event_id,
            "sportradar_legacy_sport_event_id": self.sportradar_legacy_sport_event_id,
            "sportradar_current_sport_event_id": self.sportradar_current_sport_event_id,
            "identifier_authority": self.identifier_authority,
            "documentation_contract_sha256": self.documentation_contract_sha256,
            "migration_guide_url": self.migration_guide_url,
            "id_handling_url": self.id_handling_url,
            "numeric_identifier_preserved": True,
            "soccer_match_identifier_uniqueness_documented": True,
            "sportradar_namespace_qualified": True,
            "event_metadata_resolved": False,
            "fixture_identity_proven": False,
            "sportybet_kickoff_year": None,
            "sportybet_kickoff_utc": None,
            "safety": dict(self.safety),
        }


def build_sportradar_event_identity_bridge(
    *,
    manifest: manual.SportyBetUserControlledEvidenceManifest,
    inventory: native.SportyBetUserControlledNativeInventory,
    raw_html: bytes,
) -> SportyBetSportradarEventIdentityBridge:
    """Re-derive PR #156 evidence, then freeze only documented ID semantics."""

    try:
        candidate = header.build_machine_event_header_candidate(
            manifest=manifest,
            inventory=inventory,
            raw_html=raw_html,
        )
    except header.SportyBetMachineEventHeaderError as exc:
        raise SportyBetSportradarEventIdentityError(str(exc)) from exc

    if candidate.sport_id != SOCCER_SPORT_ID:
        raise SportyBetSportradarEventIdentityError(
            "documented Sportradar bridge currently supports soccer only"
        )
    numeric_text = _legacy_numeric_payload(candidate.event_id)
    numeric_id = int(numeric_text)
    return SportyBetSportradarEventIdentityBridge(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        provider=PROVIDER,
        status=STATUS,
        source_event_candidate_sha256=header.candidate_sha256(candidate),
        source_evidence_id=candidate.source_evidence_id,
        source_evidence_manifest_sha256=candidate.source_evidence_manifest_sha256,
        source_native_inventory_sha256=candidate.source_native_inventory_sha256,
        source_raw_sha256=candidate.source_raw_sha256,
        source_url=candidate.source_url,
        sportybet_event_id=candidate.event_id,
        sportybet_sport_id=candidate.sport_id,
        sportradar_numeric_event_id=numeric_id,
        sportradar_legacy_sport_event_id=candidate.event_id,
        sportradar_current_sport_event_id=f"{CURRENT_SPORT_EVENT_PREFIX}{numeric_text}",
        identifier_authority=IDENTIFIER_AUTHORITY,
        documentation_contract_sha256=documentation_contract_sha256(),
        migration_guide_url=MIGRATION_GUIDE_URL,
        id_handling_url=ID_HANDLING_URL,
        numeric_identifier_preserved=True,
        soccer_match_identifier_uniqueness_documented=True,
        sportradar_namespace_qualified=True,
        event_metadata_resolved=False,
        fixture_identity_proven=False,
        sportybet_kickoff_year=None,
        sportybet_kickoff_utc=None,
        safety=_default_safety(),
    )


def canonical_bridge_bytes(value: Any) -> bytes:
    if not isinstance(value, SportyBetSportradarEventIdentityBridge):
        raise SportyBetSportradarEventIdentityError("bridge type mismatch")
    payload = _canonical_bytes(value.to_dict())
    if len(payload) > MAX_CANONICAL_BYTES:
        raise SportyBetSportradarEventIdentityError(
            "bridge exceeds reviewed size limit"
        )
    return payload


def bridge_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bridge_bytes(value)).hexdigest()


__all__ = [
    "CURRENT_SPORT_EVENT_PREFIX",
    "DATASET_NAME",
    "DOCUMENTATION_CONTRACT_SHA256",
    "DOCUMENTATION_REVIEWED_AT",
    "ID_HANDLING_URL",
    "IDENTIFIER_AUTHORITY",
    "LEGACY_SPORT_EVENT_PREFIX",
    "MIGRATION_GUIDE_URL",
    "SOCCER_SPORT_ID",
    "STATUS",
    "SportyBetSportradarEventIdentityBridge",
    "SportyBetSportradarEventIdentityError",
    "bridge_sha256",
    "build_sportradar_event_identity_bridge",
    "canonical_bridge_bytes",
    "documentation_contract",
    "documentation_contract_bytes",
    "documentation_contract_sha256",
]
