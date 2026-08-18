"""Qualify a SportyBet event display clock as GMT without inventing its year.

This boundary combines the exact PR #156 event-detail derivation with the exact
PR #157 official Terms qualification.  It performs no network I/O.  A specific
event display clock may inherit the provider's global GMT default only when the
Terms observation predates the event observation by no more than the frozen
window and the preserved event page contains no reviewed visible event-local
time-basis marker.  Any explicit marker fails closed for separate review.

The year remains unknown, so a UTC instant is never constructed here.  Fixture
reconciliation, pricing, selection, slip construction, booking-code generation,
execution and BET authority all remain false.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import re
import types
from collections.abc import Mapping
from typing import Any

from domain import sportybet_machine_event_header_candidate as header
from domain import sportybet_official_time_semantics as terms
from domain import sportybet_user_controlled_evidence as manual
from domain import sportybet_user_controlled_native_inventory as native
from domain.sportybet_lite_source_capture import serialize_utc, sha256_bytes

SCHEMA_VERSION = 1
DATASET_NAME = "athena-sportybet-event-local-time-basis-v1"
PROVIDER = "SportyBet"
STATUS = "QUALIFIED_EVENT_DISPLAY_TIME_BASIS_GMT_YEAR_UNKNOWN"
TEMPORAL_COMPATIBILITY_STATUS = "TERMS_PRECEDES_EVENT_WITHIN_FROZEN_WINDOW"
OVERRIDE_SCAN_STATUS = "NO_REVIEWED_VISIBLE_TIME_BASIS_MARKER_DETECTED"
TIME_ZONE_LABEL = "GMT"
UTC_OFFSET_SECONDS = 0
MAX_TERMS_AGE_MICROSECONDS = 3_600_000_000
MAX_CANONICAL_BYTES = 256 * 1024

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_EVIDENCE_ID_RE = re.compile(r"^[0-9a-f]{24}$", flags=re.ASCII)
_TIME_BASIS_MARKER_RE = re.compile(
    r"(?:"
    r"\b(?:GMT|UTC|WAT|CAT|SAST|BST|CET|CEST|EET|EEST|EST|EDT|CST|CDT|MST|MDT|PST|PDT|IST)\b"
    r"|\b(?:GMT|UTC)\s*[+-]\s*\d{1,2}(?::?\d{2})?\b"
    r"|(?<!\d)[+-]\d{2}:\d{2}(?!\d)"
    r"|\b[A-Z][A-Za-z]+/[A-Z][A-Za-z_]+\b"
    r"|\b(?:time\s*zone|timezone|local\s+time|times\s+(?:shown|stated|displayed)|kick-?off\s+times?)\b"
    r")",
    flags=re.ASCII | re.IGNORECASE,
)
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
        "sportybet_execution_authorized",
    }
)


class SportyBetEventLocalTimeBasisError(ValueError):
    """Raised when the event-local time-basis boundary fails closed."""


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(_SAFETY_KEYS)}


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise SportyBetEventLocalTimeBasisError("safety keys mismatch")
    detached: dict[str, bool] = {}
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise SportyBetEventLocalTimeBasisError(
                f"safety[{key!r}] must be exact bool False"
            )
        detached[key] = False
    return types.MappingProxyType(detached)


def _hash(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise SportyBetEventLocalTimeBasisError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _evidence_id(value: Any, label: str) -> str:
    if type(value) is not str or _EVIDENCE_ID_RE.fullmatch(value) is None:
        raise SportyBetEventLocalTimeBasisError(f"{label} is invalid")
    return value


def _utc(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, dt.datetime):
        raise SportyBetEventLocalTimeBasisError(f"{label} must be a datetime")
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            raise SportyBetEventLocalTimeBasisError(
                f"{label} must be timezone-aware"
            )
        return value.astimezone(dt.timezone.utc)
    except SportyBetEventLocalTimeBasisError:
        raise
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise SportyBetEventLocalTimeBasisError(f"{label} is invalid") from exc


def _delta_microseconds(later: dt.datetime, earlier: dt.datetime) -> int:
    delta = later - earlier
    if delta.days < 0:
        raise SportyBetEventLocalTimeBasisError(
            "Terms observation must not postdate event observation"
        )
    return (
        delta.days * 86_400_000_000
        + delta.seconds * 1_000_000
        + delta.microseconds
    )


def scan_visible_time_basis_markers(raw_html: Any) -> tuple[str, ...]:
    """Return exact visible tokens containing reviewed time-basis markers.

    Script/style/template content is excluded by the PR #156 visible-text parser.
    The successful default-application path requires this tuple to be empty.  An
    explicit GMT marker also fails closed here: explicit event-local declarations
    are intentionally routed to a separate review instead of being reinterpreted.
    """
    try:
        tokens = header.visible_text_tokens(raw_html)
    except header.SportyBetMachineEventHeaderError as exc:
        raise SportyBetEventLocalTimeBasisError(str(exc)) from exc
    found: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if _TIME_BASIS_MARKER_RE.search(token) is None:
            continue
        if token not in seen:
            seen.add(token)
            found.append(token)
    return tuple(found)


def _revalidate_terms(
    qualification: Any,
    raw_html: Any,
) -> tuple[terms.SportyBetOfficialTimeSemanticsQualification, str, str]:
    if not isinstance(
        qualification,
        terms.SportyBetOfficialTimeSemanticsQualification,
    ):
        raise SportyBetEventLocalTimeBasisError(
            "official Terms qualification type mismatch"
        )
    try:
        rebuilt = terms.build_qualification(
            raw_html,
            source_url=qualification.source_url,
            observed_at_user_attested=qualification.observed_at_user_attested,
            imported_at_utc=qualification.imported_at_utc,
            attestation=qualification.attestation,
        )
        supplied_bytes = terms.canonical_qualification_bytes(qualification)
        rebuilt_bytes = terms.canonical_qualification_bytes(rebuilt)
    except terms.SportyBetOfficialTimeSemanticsError as exc:
        raise SportyBetEventLocalTimeBasisError(str(exc)) from exc
    if supplied_bytes != rebuilt_bytes:
        raise SportyBetEventLocalTimeBasisError(
            "official Terms qualification is not the exact deterministic derivative of raw HTML"
        )
    if (
        rebuilt.time_zone_label != TIME_ZONE_LABEL
        or rebuilt.utc_offset_seconds != UTC_OFFSET_SECONDS
        or rebuilt.unless_stated_otherwise is not True
        or rebuilt.event_local_override_check_required is not True
    ):
        raise SportyBetEventLocalTimeBasisError(
            "official Terms qualification does not carry the reviewed GMT default rule"
        )
    return (
        rebuilt,
        terms.evidence_identifier(rebuilt),
        sha256_bytes(rebuilt_bytes),
    )


def _rederive_event_candidate(
    manifest: Any,
    inventory: Any,
    raw_html: Any,
) -> header.SportyBetMachineEventHeaderCandidate:
    if not isinstance(manifest, manual.SportyBetUserControlledEvidenceManifest):
        raise SportyBetEventLocalTimeBasisError("event manifest type mismatch")
    if not isinstance(inventory, native.SportyBetUserControlledNativeInventory):
        raise SportyBetEventLocalTimeBasisError("event inventory type mismatch")
    try:
        return header.build_machine_event_header_candidate(
            manifest=manifest,
            inventory=inventory,
            raw_html=raw_html,
        )
    except header.SportyBetMachineEventHeaderError as exc:
        raise SportyBetEventLocalTimeBasisError(str(exc)) from exc


@dataclasses.dataclass(frozen=True)
class SportyBetEventLocalTimeBasis:
    schema_version: int
    dataset_name: str
    provider: str
    status: str
    event_source_evidence_id: str
    event_source_manifest_sha256: str
    event_source_native_inventory_sha256: str
    event_source_raw_sha256: str
    event_candidate_sha256: str
    event_source_url: str
    event_id: str
    sport_id: str
    event_observed_at_user_attested: dt.datetime
    terms_evidence_id: str
    terms_qualification_sha256: str
    terms_raw_sha256: str
    terms_source_url: str
    terms_rule_sha256: str
    terms_observed_at_user_attested: dt.datetime
    terms_age_microseconds: int
    temporal_compatibility_status: str
    event_local_override_scan_status: str
    event_local_override_marker_count: int
    specific_event_time_basis_qualified: bool
    competition_display: str
    home_display: str
    away_display: str
    kickoff_display: str
    kickoff_day: int
    kickoff_month: int
    kickoff_weekday: str
    kickoff_hour: int
    kickoff_minute: int
    kickoff_year: None
    kickoff_timezone: str
    utc_offset_seconds: int
    kickoff_utc: None
    provider_quote_at: None
    provider_snapshot_id: None
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise SportyBetEventLocalTimeBasisError("schema_version mismatch")
        if self.dataset_name != DATASET_NAME or self.provider != PROVIDER:
            raise SportyBetEventLocalTimeBasisError("dataset/provider mismatch")
        if self.status != STATUS:
            raise SportyBetEventLocalTimeBasisError("status mismatch")
        _evidence_id(self.event_source_evidence_id, "event_source_evidence_id")
        _hash(self.event_source_manifest_sha256, "event_source_manifest_sha256")
        _hash(
            self.event_source_native_inventory_sha256,
            "event_source_native_inventory_sha256",
        )
        _hash(self.event_source_raw_sha256, "event_source_raw_sha256")
        _hash(self.event_candidate_sha256, "event_candidate_sha256")
        _evidence_id(self.terms_evidence_id, "terms_evidence_id")
        _hash(self.terms_qualification_sha256, "terms_qualification_sha256")
        _hash(self.terms_raw_sha256, "terms_raw_sha256")
        _hash(self.terms_rule_sha256, "terms_rule_sha256")
        event_observed = _utc(
            self.event_observed_at_user_attested,
            "event_observed_at_user_attested",
        )
        terms_observed = _utc(
            self.terms_observed_at_user_attested,
            "terms_observed_at_user_attested",
        )
        if (
            type(self.terms_age_microseconds) is not int
            or isinstance(self.terms_age_microseconds, bool)
            or not 0 <= self.terms_age_microseconds <= MAX_TERMS_AGE_MICROSECONDS
        ):
            raise SportyBetEventLocalTimeBasisError(
                "terms_age_microseconds is outside the frozen compatibility window"
            )
        if _delta_microseconds(event_observed, terms_observed) != self.terms_age_microseconds:
            raise SportyBetEventLocalTimeBasisError(
                "terms_age_microseconds does not match evidence observations"
            )
        if self.temporal_compatibility_status != TEMPORAL_COMPATIBILITY_STATUS:
            raise SportyBetEventLocalTimeBasisError(
                "temporal_compatibility_status mismatch"
            )
        if self.event_local_override_scan_status != OVERRIDE_SCAN_STATUS:
            raise SportyBetEventLocalTimeBasisError(
                "event_local_override_scan_status mismatch"
            )
        if (
            type(self.event_local_override_marker_count) is not int
            or isinstance(self.event_local_override_marker_count, bool)
            or self.event_local_override_marker_count != 0
        ):
            raise SportyBetEventLocalTimeBasisError(
                "event-local override marker count must be exact zero"
            )
        if self.specific_event_time_basis_qualified is not True:
            raise SportyBetEventLocalTimeBasisError(
                "specific_event_time_basis_qualified must be exact True"
            )
        if (
            type(self.kickoff_day) is not int
            or isinstance(self.kickoff_day, bool)
            or type(self.kickoff_month) is not int
            or isinstance(self.kickoff_month, bool)
            or type(self.kickoff_hour) is not int
            or isinstance(self.kickoff_hour, bool)
            or type(self.kickoff_minute) is not int
            or isinstance(self.kickoff_minute, bool)
        ):
            raise SportyBetEventLocalTimeBasisError(
                "kickoff components must be exact integers"
            )
        if self.kickoff_year is not None or self.kickoff_utc is not None:
            raise SportyBetEventLocalTimeBasisError(
                "event year and UTC instant remain unproven and must be null"
            )
        if self.kickoff_timezone != TIME_ZONE_LABEL:
            raise SportyBetEventLocalTimeBasisError("kickoff_timezone mismatch")
        if (
            type(self.utc_offset_seconds) is not int
            or isinstance(self.utc_offset_seconds, bool)
            or self.utc_offset_seconds != UTC_OFFSET_SECONDS
        ):
            raise SportyBetEventLocalTimeBasisError("utc_offset_seconds mismatch")
        if self.provider_quote_at is not None or self.provider_snapshot_id is not None:
            raise SportyBetEventLocalTimeBasisError(
                "provider quote/snapshot identity remains unproven"
            )
        if not all(
            type(value) is str and value and value == value.strip()
            for value in (
                self.event_source_url,
                self.event_id,
                self.sport_id,
                self.terms_source_url,
                self.competition_display,
                self.home_display,
                self.away_display,
                self.kickoff_display,
                self.kickoff_weekday,
            )
        ):
            raise SportyBetEventLocalTimeBasisError("required text field is invalid")
        object.__setattr__(self, "event_observed_at_user_attested", event_observed)
        object.__setattr__(self, "terms_observed_at_user_attested", terms_observed)
        object.__setattr__(self, "safety", _validate_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "provider": self.provider,
            "status": self.status,
            "event_source_evidence_id": self.event_source_evidence_id,
            "event_source_manifest_sha256": self.event_source_manifest_sha256,
            "event_source_native_inventory_sha256": self.event_source_native_inventory_sha256,
            "event_source_raw_sha256": self.event_source_raw_sha256,
            "event_candidate_sha256": self.event_candidate_sha256,
            "event_source_url": self.event_source_url,
            "event_id": self.event_id,
            "sport_id": self.sport_id,
            "event_observed_at_user_attested": serialize_utc(
                self.event_observed_at_user_attested
            ),
            "terms_evidence_id": self.terms_evidence_id,
            "terms_qualification_sha256": self.terms_qualification_sha256,
            "terms_raw_sha256": self.terms_raw_sha256,
            "terms_source_url": self.terms_source_url,
            "terms_rule_sha256": self.terms_rule_sha256,
            "terms_observed_at_user_attested": serialize_utc(
                self.terms_observed_at_user_attested
            ),
            "terms_age_microseconds": self.terms_age_microseconds,
            "temporal_compatibility_status": self.temporal_compatibility_status,
            "event_local_override_scan_status": self.event_local_override_scan_status,
            "event_local_override_marker_count": 0,
            "specific_event_time_basis_qualified": True,
            "competition_display": self.competition_display,
            "home_display": self.home_display,
            "away_display": self.away_display,
            "kickoff_display": self.kickoff_display,
            "kickoff_day": self.kickoff_day,
            "kickoff_month": self.kickoff_month,
            "kickoff_weekday": self.kickoff_weekday,
            "kickoff_hour": self.kickoff_hour,
            "kickoff_minute": self.kickoff_minute,
            "kickoff_year": None,
            "kickoff_timezone": TIME_ZONE_LABEL,
            "utc_offset_seconds": UTC_OFFSET_SECONDS,
            "kickoff_utc": None,
            "provider_quote_at": None,
            "provider_snapshot_id": None,
            "safety": dict(self.safety),
        }


def build_event_local_time_basis(
    *,
    event_manifest: manual.SportyBetUserControlledEvidenceManifest,
    event_inventory: native.SportyBetUserControlledNativeInventory,
    event_raw_html: bytes,
    terms_qualification: terms.SportyBetOfficialTimeSemanticsQualification,
    terms_raw_html: bytes,
) -> SportyBetEventLocalTimeBasis:
    candidate = _rederive_event_candidate(
        event_manifest,
        event_inventory,
        event_raw_html,
    )
    rebuilt_terms, terms_evidence_id, terms_qualification_sha = _revalidate_terms(
        terms_qualification,
        terms_raw_html,
    )
    event_observed = _utc(
        event_manifest.observed_at_user_attested,
        "event_manifest.observed_at_user_attested",
    )
    terms_observed = _utc(
        rebuilt_terms.observed_at_user_attested,
        "terms_qualification.observed_at_user_attested",
    )
    age_microseconds = _delta_microseconds(event_observed, terms_observed)
    if age_microseconds > MAX_TERMS_AGE_MICROSECONDS:
        raise SportyBetEventLocalTimeBasisError(
            "official Terms evidence is older than the frozen compatibility window"
        )
    markers = scan_visible_time_basis_markers(event_raw_html)
    if markers:
        raise SportyBetEventLocalTimeBasisError(
            "event page contains a reviewed visible time-basis marker; separate review required"
        )
    return SportyBetEventLocalTimeBasis(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        provider=PROVIDER,
        status=STATUS,
        event_source_evidence_id=candidate.source_evidence_id,
        event_source_manifest_sha256=candidate.source_evidence_manifest_sha256,
        event_source_native_inventory_sha256=candidate.source_native_inventory_sha256,
        event_source_raw_sha256=candidate.source_raw_sha256,
        event_candidate_sha256=header.candidate_sha256(candidate),
        event_source_url=candidate.source_url,
        event_id=candidate.event_id,
        sport_id=candidate.sport_id,
        event_observed_at_user_attested=event_observed,
        terms_evidence_id=terms_evidence_id,
        terms_qualification_sha256=terms_qualification_sha,
        terms_raw_sha256=rebuilt_terms.raw_sha256,
        terms_source_url=rebuilt_terms.source_url,
        terms_rule_sha256=rebuilt_terms.semantics_statement_sha256,
        terms_observed_at_user_attested=terms_observed,
        terms_age_microseconds=age_microseconds,
        temporal_compatibility_status=TEMPORAL_COMPATIBILITY_STATUS,
        event_local_override_scan_status=OVERRIDE_SCAN_STATUS,
        event_local_override_marker_count=0,
        specific_event_time_basis_qualified=True,
        competition_display=candidate.competition_display,
        home_display=candidate.home_display,
        away_display=candidate.away_display,
        kickoff_display=candidate.kickoff_display,
        kickoff_day=candidate.kickoff_day,
        kickoff_month=candidate.kickoff_month,
        kickoff_weekday=candidate.kickoff_weekday,
        kickoff_hour=candidate.kickoff_hour,
        kickoff_minute=candidate.kickoff_minute,
        kickoff_year=None,
        kickoff_timezone=TIME_ZONE_LABEL,
        utc_offset_seconds=UTC_OFFSET_SECONDS,
        kickoff_utc=None,
        provider_quote_at=None,
        provider_snapshot_id=None,
        safety=_default_safety(),
    )


def canonical_time_basis_bytes(value: Any) -> bytes:
    if not isinstance(value, SportyBetEventLocalTimeBasis):
        raise SportyBetEventLocalTimeBasisError("time-basis type mismatch")
    try:
        payload = (
            json.dumps(
                value.to_dict(),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise SportyBetEventLocalTimeBasisError(
            "time-basis serialization failed"
        ) from exc
    if len(payload) > MAX_CANONICAL_BYTES:
        raise SportyBetEventLocalTimeBasisError(
            "time-basis artifact exceeds reviewed size limit"
        )
    return payload


def time_basis_sha256(value: Any) -> str:
    return sha256_bytes(canonical_time_basis_bytes(value))
