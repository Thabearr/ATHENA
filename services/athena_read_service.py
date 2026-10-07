"""Provider-free versioned read, cancel-intent, and export service contracts.

This module defines application ports for the later D4/D5 data owners. The
default desktop service uses unavailable ports until those owners exist; it
does not read legacy files or initialize storage.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import re
from types import MappingProxyType
from typing import Literal, Mapping, Protocol

from domain.run_contracts import RunReceipt


RunState = Literal[
    "QUEUED", "RUNNING", "CANCEL_REQUESTED", "TERMINAL", "CANCELLED", "INTERRUPTED"
]
ReceiptState = Literal["NOT_PRODUCED", "VERIFIED", "INTEGRITY_BLOCKED", "UNKNOWN"]
RunProfile = Literal["MAIN", "SHADOW"]
EventKind = Literal[
    "STATE_CHANGED", "STAGE_STARTED", "STAGE_COMPLETED", "BUSINESS_RESULT",
    "CANCEL_REQUESTED", "DIAGNOSTIC",
]
ExportKind = Literal["run_summary_json", "verified_receipt_json"]
RedactionMode = Literal["standard", "strict"]
CancelDisposition = Literal["requested", "already_requested", "already_terminal"]

_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$", re.ASCII)
_CURSOR = re.compile(r"^[A-Za-z0-9_-]{1,128}$", re.ASCII)
_EXPORT_ID = re.compile(r"^exp_[A-Za-z0-9_-]{32,64}$", re.ASCII)
_SHA256 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$", re.ASCII)
_IDENTITY_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$", re.ASCII)
_DIAGNOSTIC_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$", re.ASCII)
_COUNT_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$", re.ASCII)
_RUN_STATES = frozenset({"QUEUED", "RUNNING", "CANCEL_REQUESTED", "TERMINAL", "CANCELLED", "INTERRUPTED"})
_RECEIPT_TERMINAL_STATES = frozenset({"TERMINAL", "CANCELLED", "INTERRUPTED"})
_EVENT_KINDS = frozenset({
    "STATE_CHANGED", "STAGE_STARTED", "STAGE_COMPLETED", "BUSINESS_RESULT",
    "CANCEL_REQUESTED", "DIAGNOSTIC",
})
_EXPORT_KINDS = frozenset({"run_summary_json", "verified_receipt_json"})
_REDACTION_MODES = frozenset({"standard", "strict"})
_ERRORS = {
    "RUN_NOT_FOUND": (404, "The run was not found.", "never"),
    "EXPORT_NOT_FOUND": (404, "The export was not found.", "never"),
    "RUN_STORE_UNAVAILABLE": (503, "Run data is not available in this application.", "after_delay"),
    "RETAINED_FIXTURE_INDEX_UNAVAILABLE": (
        503, "Retained fixture browsing is not available in this application.", "after_delay"
    ),
    "CANCEL_STORE_UNAVAILABLE": (503, "Cancel intent is not available in this application.", "after_delay"),
    "EXPORT_STORE_UNAVAILABLE": (503, "Local export is not available in this application.", "after_delay"),
    "RECEIPT_NOT_PRODUCED": (409, "A verified terminal receipt has not been produced.", "never"),
    "RECEIPT_INTEGRITY_BLOCKED": (409, "Receipt integrity could not be verified.", "never"),
    "CANCEL_STATE_CONFLICT": (409, "Cancel intent could not be recorded for the current run state.", "never"),
    "INVALID_RUN_ID": (422, "The run identifier is invalid.", "never"),
    "INVALID_EXPORT_ID": (422, "The export identifier is invalid.", "never"),
    "INVALID_CURSOR": (422, "The cursor is invalid.", "never"),
    "INVALID_LIMIT": (422, "The page limit is invalid.", "never"),
    "INVALID_FILTER": (422, "The filter is invalid.", "never"),
    "INVALID_EXPORT_REQUEST": (422, "The export request is invalid.", "never"),
    "INVALID_EXPORT_KIND": (422, "The export kind is not supported.", "never"),
}


class ReadServiceError(Exception):
    """Finite, safe application error with no underlying exception text."""

    def __init__(self, code: str, *, diagnostic_id: str | None = None):
        if code not in _ERRORS:
            code = "RUN_STORE_UNAVAILABLE"
        status, message, retry = _ERRORS[code]
        self.code = code
        self.status_code = status
        self.safe_message = message
        self.retry_class = retry
        self.diagnostic_id = diagnostic_id if type(diagnostic_id) is str and _DIAGNOSTIC_ID.fullmatch(diagnostic_id) else None
        super().__init__(message)


class ReadBackendError(Exception):
    """Typed repository disposition; never serialize its text."""

    def __init__(self, code: str):
        if code not in _ERRORS:
            code = "RUN_STORE_UNAVAILABLE"
        self.code = code
        super().__init__(code)


def _require_run_id(value: str) -> None:
    if type(value) is not str or _RUN_ID.fullmatch(value) is None:
        raise ReadServiceError("INVALID_RUN_ID")


def _require_export_id(value: str) -> None:
    if type(value) is not str or _EXPORT_ID.fullmatch(value) is None:
        raise ReadServiceError("INVALID_EXPORT_ID")


def _require_cursor(value: str | None) -> None:
    if value is not None and (type(value) is not str or _CURSOR.fullmatch(value) is None):
        raise ReadServiceError("INVALID_CURSOR")


def _aware_utc(value: datetime | None, field: str, *, optional: bool = False) -> datetime | None:
    if value is None and optional:
        return None
    if (type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None):
        raise ValueError("invalid " + field)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _safe_code(value: str | None, field: str) -> None:
    if value is not None and (type(value) is not str or _CODE.fullmatch(value) is None):
        raise ValueError("invalid " + field)


def _safe_ref(value: str | None, field: str) -> None:
    if value is not None and (type(value) is not str or _IDENTITY_REF.fullmatch(value) is None):
        raise ValueError("invalid " + field)


def _safe_label(value: str, field: str, *, max_length: int = 100) -> None:
    if (type(value) is not str or not value or len(value) > max_length
            or value != value.strip()
            or any(ord(char) < 32 or ord(char) == 127 or char in "/\\" for char in value)):
        raise ValueError("invalid " + field)


def _count(value: int | None, field: str, *, optional: bool = True) -> None:
    if value is None and optional:
        return
    if type(value) is not int or value < 0:
        raise ValueError("invalid " + field)


@dataclass(frozen=True)
class RunSnapshotRecord:
    run_id: str
    state: RunState
    state_version: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_proven_stage: str | None = None
    counts: Mapping[str, int | None] | None = None
    target_legs: int | None = None
    selected_leg_count: int | None = None
    shortfall: int | None = None
    execution_state: str | None = None
    business_result: str | None = None
    delivery_state: str | None = None
    receipt_state: ReceiptState = "UNKNOWN"
    request_identity_ref: str | None = None
    release_identity_ref: str | None = None

    def __post_init__(self) -> None:
        if type(self.run_id) is not str or _RUN_ID.fullmatch(self.run_id) is None:
            raise ValueError("invalid run identity")
        if self.state not in _RUN_STATES:
            raise ValueError("invalid run state")
        _count(self.state_version, "state version")
        object.__setattr__(self, "created_at", _aware_utc(self.created_at, "created_at", optional=True))
        object.__setattr__(self, "updated_at", _aware_utc(self.updated_at, "updated_at", optional=True))
        if self.last_proven_stage is not None:
            _safe_code(self.last_proven_stage, "last proven stage")
        if self.counts is not None:
            if not isinstance(self.counts, Mapping):
                raise ValueError("invalid run counts")
            normalized: dict[str, int | None] = {}
            for key, value in self.counts.items():
                if type(key) is not str or _COUNT_NAME.fullmatch(key) is None:
                    raise ValueError("invalid run count name")
                _count(value, "run count")
                normalized[key] = value
            object.__setattr__(self, "counts", MappingProxyType(dict(sorted(normalized.items()))))
        if self.target_legs is not None and (type(self.target_legs) is not int or not 1 <= self.target_legs <= 50):
            raise ValueError("invalid target legs")
        _count(self.selected_leg_count, "selected leg count")
        _count(self.shortfall, "shortfall")
        _safe_code(self.execution_state, "execution state")
        _safe_code(self.business_result, "business result")
        _safe_code(self.delivery_state, "delivery state")
        if self.receipt_state not in {"NOT_PRODUCED", "VERIFIED", "INTEGRITY_BLOCKED", "UNKNOWN"}:
            raise ValueError("invalid receipt state")
        _safe_ref(self.request_identity_ref, "request identity reference")
        _safe_ref(self.release_identity_ref, "release identity reference")

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "state": self.state,
            "state_version": self.state_version,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
            "last_proven_stage": self.last_proven_stage,
            "counts": None if self.counts is None else dict(self.counts),
            "target_legs": self.target_legs,
            "selected_leg_count": self.selected_leg_count,
            "shortfall": self.shortfall,
            "execution_state": self.execution_state,
            "business_result": self.business_result,
            "delivery_state": self.delivery_state,
            "receipt_state": self.receipt_state,
            "request_identity_ref": self.request_identity_ref,
            "release_identity_ref": self.release_identity_ref,
        }


@dataclass(frozen=True)
class RunEventPayload:
    stage: str | None = None
    state: RunState | None = None
    business_result: str | None = None
    selected_leg_count: int | None = None
    shortfall: int | None = None
    diagnostic_id: str | None = None

    def __post_init__(self) -> None:
        _safe_code(self.stage, "event stage")
        if self.state is not None and self.state not in _RUN_STATES:
            raise ValueError("invalid event state")
        _safe_code(self.business_result, "event business result")
        _count(self.selected_leg_count, "event selected count")
        _count(self.shortfall, "event shortfall")
        if (self.diagnostic_id is not None
                and (type(self.diagnostic_id) is not str or _DIAGNOSTIC_ID.fullmatch(self.diagnostic_id) is None)):
            raise ValueError("invalid diagnostic identity")

    def to_dict(self) -> dict[str, object]:
        values = {
            "stage": self.stage,
            "state": self.state,
            "business_result": self.business_result,
            "selected_leg_count": self.selected_leg_count,
            "shortfall": self.shortfall,
            "diagnostic_id": self.diagnostic_id,
        }
        return {key: value for key, value in values.items() if value is not None}


@dataclass(frozen=True)
class RunEventRecord:
    sequence: int
    kind: EventKind
    observed_at: datetime
    state_version: int | None = None
    payload: RunEventPayload = RunEventPayload()

    def __post_init__(self) -> None:
        if type(self.sequence) is not int or self.sequence < 1:
            raise ValueError("invalid event sequence")
        if self.kind not in _EVENT_KINDS:
            raise ValueError("invalid event kind")
        object.__setattr__(self, "observed_at", _aware_utc(self.observed_at, "event observed_at"))
        _count(self.state_version, "event state version")
        if type(self.payload) is not RunEventPayload:
            raise ValueError("invalid event payload")

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "kind": self.kind,
            "state_version": self.state_version,
            "observed_at": _iso(self.observed_at),
            "payload": self.payload.to_dict(),
        }


@dataclass(frozen=True)
class RunEventPage:
    events: tuple[RunEventRecord, ...]

    def __post_init__(self) -> None:
        if type(self.events) is not tuple or any(type(item) is not RunEventRecord for item in self.events):
            raise ValueError("invalid run event page")


@dataclass(frozen=True)
class RunHistoryEntry:
    run_id: str
    state: RunState
    state_version: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    profile: RunProfile | None = None

    def __post_init__(self) -> None:
        if type(self.run_id) is not str or _RUN_ID.fullmatch(self.run_id) is None or self.state not in _RUN_STATES:
            raise ValueError("invalid run history row")
        _count(self.state_version, "history state version")
        object.__setattr__(self, "created_at", _aware_utc(self.created_at, "history created_at", optional=True))
        object.__setattr__(self, "updated_at", _aware_utc(self.updated_at, "history updated_at", optional=True))
        if self.profile is not None and self.profile not in {"MAIN", "SHADOW"}:
            raise ValueError("invalid run profile")

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "state": self.state,
            "state_version": self.state_version,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
            "profile": self.profile,
        }


@dataclass(frozen=True)
class RunHistoryPage:
    items: tuple[RunHistoryEntry, ...]
    next_cursor: str | None = None

    def __post_init__(self) -> None:
        if type(self.items) is not tuple or any(type(item) is not RunHistoryEntry for item in self.items):
            raise ValueError("invalid run history page")
        _require_cursor(self.next_cursor)


@dataclass(frozen=True)
class RetainedFixtureRecord:
    fixture_id: str
    kickoff_at: datetime
    competition_id: str
    competition_name: str
    home: str
    away: str
    scope: Literal["club", "international"]

    def __post_init__(self) -> None:
        if type(self.fixture_id) is not str or _RUN_ID.fullmatch(self.fixture_id) is None:
            raise ValueError("invalid fixture identity")
        object.__setattr__(self, "kickoff_at", _aware_utc(self.kickoff_at, "fixture kickoff"))
        _safe_ref(self.competition_id, "competition identity")
        _safe_label(self.competition_name, "competition name")
        _safe_label(self.home, "home team")
        _safe_label(self.away, "away team")
        if self.scope not in {"club", "international"}:
            raise ValueError("invalid fixture scope")

    def to_dict(self) -> dict[str, object]:
        return {
            "fixture_id": self.fixture_id,
            "kickoff_at": _iso(self.kickoff_at),
            "competition_id": self.competition_id,
            "competition_name": self.competition_name,
            "home": self.home,
            "away": self.away,
            "scope": self.scope,
        }


@dataclass(frozen=True)
class RetainedFixturePage:
    items: tuple[RetainedFixtureRecord, ...]
    next_cursor: str | None = None

    def __post_init__(self) -> None:
        if type(self.items) is not tuple or any(type(item) is not RetainedFixtureRecord for item in self.items):
            raise ValueError("invalid retained fixture page")
        _require_cursor(self.next_cursor)


@dataclass(frozen=True)
class ReceiptObservation:
    run_id: str
    run_state: RunState
    receipt_bytes: bytes | None
    diagnostic_id: str | None = None

    def __post_init__(self) -> None:
        if type(self.run_id) is not str or _RUN_ID.fullmatch(self.run_id) is None or self.run_state not in _RUN_STATES:
            raise ValueError("invalid receipt observation identity")
        if self.receipt_bytes is not None and type(self.receipt_bytes) is not bytes:
            raise ValueError("invalid canonical receipt bytes")
        if (self.diagnostic_id is not None
                and (type(self.diagnostic_id) is not str or _DIAGNOSTIC_ID.fullmatch(self.diagnostic_id) is None)):
            raise ValueError("invalid receipt diagnostic identity")


@dataclass(frozen=True)
class VerifiedReceiptView:
    receipt_sha256: str
    status: str
    observed_at: datetime
    exact_commit_sha: str
    request_identity_ref: str
    target_legs: int
    selected_leg_count: int
    shortfall: int
    delivery_state: Literal["NOT_REQUESTED", "NOT_PRODUCED", "RESULT_RECORDED"]
    wager_placed: Literal[False] = False

    def __post_init__(self) -> None:
        if _SHA256.fullmatch(self.receipt_sha256) is None:
            raise ValueError("invalid receipt digest")
        _safe_code(self.status, "receipt status")
        object.__setattr__(self, "observed_at", _aware_utc(self.observed_at, "receipt observed_at"))
        _safe_ref(self.exact_commit_sha, "receipt commit identity")
        _safe_ref(self.request_identity_ref, "receipt request identity")
        if type(self.target_legs) is not int or not 1 <= self.target_legs <= 50:
            raise ValueError("invalid receipt target legs")
        _count(self.selected_leg_count, "receipt selected count", optional=False)
        _count(self.shortfall, "receipt shortfall", optional=False)
        if self.delivery_state not in {"NOT_REQUESTED", "NOT_PRODUCED", "RESULT_RECORDED"}:
            raise ValueError("invalid receipt delivery state")
        if self.wager_placed is not False:
            raise ValueError("invalid receipt wager result")

    def to_dict(self) -> dict[str, object]:
        return {
            "receipt_sha256": self.receipt_sha256,
            "status": self.status,
            "observed_at": _iso(self.observed_at),
            "exact_commit_sha": self.exact_commit_sha,
            "request_identity_ref": self.request_identity_ref,
            "target_legs": self.target_legs,
            "selected_leg_count": self.selected_leg_count,
            "shortfall": self.shortfall,
            "delivery_state": self.delivery_state,
            "wager_placed": False,
        }


@dataclass(frozen=True)
class CancelIntentResult:
    run_id: str
    disposition: CancelDisposition
    state: RunState
    state_version: int | None

    def __post_init__(self) -> None:
        if type(self.run_id) is not str or _RUN_ID.fullmatch(self.run_id) is None:
            raise ValueError("invalid cancel run identity")
        if self.disposition not in {"requested", "already_requested", "already_terminal"}:
            raise ValueError("invalid cancel disposition")
        if self.state not in _RUN_STATES:
            raise ValueError("invalid cancel state")
        _count(self.state_version, "cancel state version")

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "disposition": self.disposition,
            "state": self.state,
            "state_version": self.state_version,
        }


@dataclass(frozen=True)
class ExportRequest:
    run_id: str | None
    receipt_sha256: str | None
    kind: ExportKind
    redaction_mode: RedactionMode = "standard"

    def __post_init__(self) -> None:
        if (self.run_id is None) == (self.receipt_sha256 is None):
            raise ValueError("export request must identify exactly one retained source")
        if self.run_id is not None and (type(self.run_id) is not str or _RUN_ID.fullmatch(self.run_id) is None):
            raise ValueError("invalid export run identity")
        if self.receipt_sha256 is not None and (type(self.receipt_sha256) is not str
                                                or _SHA256.fullmatch(self.receipt_sha256) is None):
            raise ValueError("invalid export receipt identity")
        if self.kind not in _EXPORT_KINDS or self.redaction_mode not in _REDACTION_MODES:
            raise ValueError("invalid export allowlist selection")


@dataclass(frozen=True)
class ExportRecord:
    export_id: str
    kind: ExportKind
    redaction_mode: RedactionMode
    run_id: str | None
    receipt_sha256: str | None
    logical_path: str
    created_at: datetime
    sha256: str
    byte_count: int

    def __post_init__(self) -> None:
        if type(self.export_id) is not str or _EXPORT_ID.fullmatch(self.export_id) is None:
            raise ValueError("invalid export identity")
        if self.kind not in _EXPORT_KINDS or self.redaction_mode not in _REDACTION_MODES:
            raise ValueError("invalid export metadata kind")
        if (self.run_id is None) == (self.receipt_sha256 is None):
            raise ValueError("invalid export source identity")
        if self.run_id is not None and (type(self.run_id) is not str or _RUN_ID.fullmatch(self.run_id) is None):
            raise ValueError("invalid export source run")
        if self.receipt_sha256 is not None and (type(self.receipt_sha256) is not str
                                                or _SHA256.fullmatch(self.receipt_sha256) is None):
            raise ValueError("invalid export source receipt")
        expected_name = "run-summary.json" if self.kind == "run_summary_json" else "verified-receipt.json"
        expected_path = f"exports/{self.export_id}/{expected_name}"
        parts = self.logical_path.split("/") if type(self.logical_path) is str else []
        if (self.logical_path != expected_path or len(parts) != 3 or any(part in {"", ".", ".."} for part in parts)
                or "\\" in self.logical_path or ":" in self.logical_path or "%" in self.logical_path
                or any(ord(char) < 32 or ord(char) == 127 for char in self.logical_path)):
            raise ValueError("invalid server-owned export locator")
        object.__setattr__(self, "created_at", _aware_utc(self.created_at, "export created_at"))
        if type(self.sha256) is not str or _SHA256.fullmatch(self.sha256) is None:
            raise ValueError("invalid export digest")
        if type(self.byte_count) is not int or self.byte_count < 0:
            raise ValueError("invalid export byte count")

    def to_dict(self) -> dict[str, object]:
        return {
            "export_id": self.export_id,
            "kind": self.kind,
            "redaction_mode": self.redaction_mode,
            "run_id": self.run_id,
            "receipt_sha256": self.receipt_sha256,
            "logical_path": self.logical_path,
            "created_at": _iso(self.created_at),
            "sha256": self.sha256,
            "byte_count": self.byte_count,
        }


class RunReadRepository(Protocol):
    """D4-owned read ports. Implementations return only proven app state."""

    def get_run_snapshot(self, run_id: str) -> RunSnapshotRecord | None: ...
    def list_run_events(self, run_id: str, *, after_sequence: int, limit: int) -> RunEventPage | None: ...
    def get_receipt_observation(self, run_id: str) -> ReceiptObservation | None: ...
    def list_runs(self, *, cursor: str | None, limit: int, state: RunState | None,
                  profile: RunProfile | None) -> RunHistoryPage: ...


class CancelIntentRepository(Protocol):
    """D4-owned cooperative cancel-intent port; it never controls a process."""

    def request_cancel(self, run_id: str) -> CancelIntentResult | None: ...


class RetainedFixtureIndex(Protocol):
    """D5-owned provider-free retained fixture index."""

    def list_retained_fixtures(self, *, cursor: str | None, limit: int, scope: str | None,
                               date_from: date | None, date_to: date | None) -> RetainedFixturePage: ...


class ExportRepository(Protocol):
    """D5-owned immutable export repository/service port."""

    def create_export(self, request: ExportRequest) -> ExportRecord: ...
    def get_export(self, export_id: str) -> ExportRecord | None: ...


class _UnavailableRunReadRepository:
    def get_run_snapshot(self, run_id: str):
        raise ReadBackendError("RUN_STORE_UNAVAILABLE")

    def list_run_events(self, run_id: str, *, after_sequence: int, limit: int):
        raise ReadBackendError("RUN_STORE_UNAVAILABLE")

    def get_receipt_observation(self, run_id: str):
        raise ReadBackendError("RUN_STORE_UNAVAILABLE")

    def list_runs(self, *, cursor, limit, state, profile):
        raise ReadBackendError("RUN_STORE_UNAVAILABLE")


class _UnavailableCancelIntentRepository:
    def request_cancel(self, run_id: str):
        raise ReadBackendError("CANCEL_STORE_UNAVAILABLE")


class _UnavailableRetainedFixtureIndex:
    def list_retained_fixtures(self, *, cursor, limit, scope, date_from, date_to):
        raise ReadBackendError("RETAINED_FIXTURE_INDEX_UNAVAILABLE")


class _UnavailableExportRepository:
    def create_export(self, request: ExportRequest):
        raise ReadBackendError("EXPORT_STORE_UNAVAILABLE")

    def get_export(self, export_id: str):
        raise ReadBackendError("EXPORT_STORE_UNAVAILABLE")


class AthenaReadService:
    """Provider-free application boundary for versioned reads and intent."""

    MAX_EVENT_PAGE = 200
    MAX_PAGE = 100
    MAX_RECEIPT_BYTES = 1_000_000

    def __init__(self, *, run_repository: RunReadRepository, cancel_repository: CancelIntentRepository,
                 fixture_index: RetainedFixtureIndex, export_repository: ExportRepository):
        if any(value is None for value in (run_repository, cancel_repository, fixture_index, export_repository)):
            raise ValueError("explicit read-service ports are required")
        self.run_repository = run_repository
        self.cancel_repository = cancel_repository
        self.fixture_index = fixture_index
        self.export_repository = export_repository

    @classmethod
    def unavailable(cls) -> "AthenaReadService":
        """Build the truthful supported desktop service before D4/D5 storage."""
        return cls(
            run_repository=_UnavailableRunReadRepository(),
            cancel_repository=_UnavailableCancelIntentRepository(),
            fixture_index=_UnavailableRetainedFixtureIndex(),
            export_repository=_UnavailableExportRepository(),
        )

    @staticmethod
    def _backend_error(exc: Exception, fallback: str) -> ReadServiceError:
        if isinstance(exc, ReadBackendError):
            return ReadServiceError(exc.code)
        return ReadServiceError(fallback)

    def get_run_snapshot(self, run_id: str) -> RunSnapshotRecord:
        _require_run_id(run_id)
        try:
            snapshot = self.run_repository.get_run_snapshot(run_id)
        except Exception as exc:
            raise self._backend_error(exc, "RUN_STORE_UNAVAILABLE") from None
        if snapshot is None:
            raise ReadServiceError("RUN_NOT_FOUND")
        if type(snapshot) is not RunSnapshotRecord or snapshot.run_id != run_id:
            raise ReadServiceError("RUN_STORE_UNAVAILABLE")
        return snapshot

    def list_run_events(self, run_id: str, *, after_sequence: int = 0, limit: int = 50) -> RunEventPage:
        _require_run_id(run_id)
        if type(after_sequence) is not int or after_sequence < 0:
            raise ReadServiceError("INVALID_CURSOR")
        if type(limit) is not int or not 1 <= limit <= self.MAX_EVENT_PAGE:
            raise ReadServiceError("INVALID_LIMIT")
        try:
            page = self.run_repository.list_run_events(run_id, after_sequence=after_sequence, limit=limit)
        except Exception as exc:
            raise self._backend_error(exc, "RUN_STORE_UNAVAILABLE") from None
        if page is None:
            raise ReadServiceError("RUN_NOT_FOUND")
        if type(page) is not RunEventPage or len(page.events) > limit:
            raise ReadServiceError("RUN_STORE_UNAVAILABLE")
        previous = after_sequence
        for event in page.events:
            if type(event) is not RunEventRecord or event.sequence <= previous:
                raise ReadServiceError("RUN_STORE_UNAVAILABLE")
            previous = event.sequence
        return page

    def get_verified_receipt(self, run_id: str) -> VerifiedReceiptView:
        _require_run_id(run_id)
        try:
            observation = self.run_repository.get_receipt_observation(run_id)
        except Exception as exc:
            raise self._backend_error(exc, "RUN_STORE_UNAVAILABLE") from None
        if observation is None:
            raise ReadServiceError("RUN_NOT_FOUND")
        if type(observation) is not ReceiptObservation or observation.run_id != run_id:
            raise ReadServiceError("RECEIPT_INTEGRITY_BLOCKED")
        diagnostic_id = observation.diagnostic_id
        if observation.run_state not in _RECEIPT_TERMINAL_STATES or observation.receipt_bytes is None:
            raise ReadServiceError("RECEIPT_NOT_PRODUCED", diagnostic_id=diagnostic_id)
        raw = observation.receipt_bytes
        if len(raw) > self.MAX_RECEIPT_BYTES:
            raise ReadServiceError("RECEIPT_INTEGRITY_BLOCKED", diagnostic_id=diagnostic_id)
        try:
            receipt = RunReceipt.from_json_bytes(raw)
        except Exception:
            raise ReadServiceError("RECEIPT_INTEGRITY_BLOCKED", diagnostic_id=diagnostic_id) from None
        try:
            if receipt.wager_placed is not False:
                raise ValueError("receipt wager result is not safe")
            if receipt.counts["selected_leg_count"] != len(receipt.selected_legs):
                raise ValueError("receipt selected count is inconsistent")
            delivery_state: Literal["NOT_REQUESTED", "NOT_PRODUCED", "RESULT_RECORDED"]
            if not receipt.request.create_share_code:
                delivery_state = "NOT_REQUESTED"
            elif receipt.share_code_result is None:
                delivery_state = "NOT_PRODUCED"
            else:
                delivery_state = "RESULT_RECORDED"
            return VerifiedReceiptView(
                receipt_sha256=hashlib.sha256(raw).hexdigest(),
                status=receipt.status,
                observed_at=receipt.observed_at,
                exact_commit_sha=receipt.exact_commit_sha,
                request_identity_ref=receipt.request.canonical_sha256,
                target_legs=receipt.request.target_legs,
                selected_leg_count=receipt.counts["selected_leg_count"],
                shortfall=receipt.shortfall,
                delivery_state=delivery_state,
                wager_placed=False,
            )
        except Exception:
            raise ReadServiceError("RECEIPT_INTEGRITY_BLOCKED", diagnostic_id=diagnostic_id) from None

    def list_runs(self, *, cursor: str | None = None, limit: int = 50,
                  state: RunState | None = None, profile: RunProfile | None = None) -> RunHistoryPage:
        _require_cursor(cursor)
        if type(limit) is not int or not 1 <= limit <= self.MAX_PAGE:
            raise ReadServiceError("INVALID_LIMIT")
        if state is not None and state not in _RUN_STATES:
            raise ReadServiceError("INVALID_FILTER")
        if profile is not None and profile not in {"MAIN", "SHADOW"}:
            raise ReadServiceError("INVALID_FILTER")
        try:
            page = self.run_repository.list_runs(cursor=cursor, limit=limit, state=state, profile=profile)
        except Exception as exc:
            raise self._backend_error(exc, "RUN_STORE_UNAVAILABLE") from None
        if type(page) is not RunHistoryPage or len(page.items) > limit:
            raise ReadServiceError("RUN_STORE_UNAVAILABLE")
        if page.next_cursor is not None and page.next_cursor == cursor:
            raise ReadServiceError("RUN_STORE_UNAVAILABLE")
        return page

    def list_retained_fixtures(self, *, cursor: str | None = None, limit: int = 50,
                               scope: Literal["club", "international"] | None = None,
                               date_from: date | None = None, date_to: date | None = None) -> RetainedFixturePage:
        _require_cursor(cursor)
        if type(limit) is not int or not 1 <= limit <= self.MAX_PAGE:
            raise ReadServiceError("INVALID_LIMIT")
        if scope is not None and scope not in {"club", "international"}:
            raise ReadServiceError("INVALID_FILTER")
        if (date_from is None) != (date_to is None):
            raise ReadServiceError("INVALID_FILTER")
        if date_from is not None:
            if type(date_from) is not date or type(date_to) is not date or date_from > date_to:
                raise ReadServiceError("INVALID_FILTER")
            if date_to - date_from > timedelta(days=31):
                raise ReadServiceError("INVALID_FILTER")
        try:
            page = self.fixture_index.list_retained_fixtures(
                cursor=cursor, limit=limit, scope=scope, date_from=date_from, date_to=date_to
            )
        except Exception as exc:
            raise self._backend_error(exc, "RETAINED_FIXTURE_INDEX_UNAVAILABLE") from None
        if type(page) is not RetainedFixturePage or len(page.items) > limit:
            raise ReadServiceError("RETAINED_FIXTURE_INDEX_UNAVAILABLE")
        if page.next_cursor is not None and page.next_cursor == cursor:
            raise ReadServiceError("RETAINED_FIXTURE_INDEX_UNAVAILABLE")
        return page

    def request_cancel(self, run_id: str) -> CancelIntentResult:
        _require_run_id(run_id)
        try:
            result = self.cancel_repository.request_cancel(run_id)
        except Exception as exc:
            raise self._backend_error(exc, "CANCEL_STORE_UNAVAILABLE") from None
        if result is None:
            raise ReadServiceError("RUN_NOT_FOUND")
        if type(result) is not CancelIntentResult or result.run_id != run_id:
            raise ReadServiceError("CANCEL_STORE_UNAVAILABLE")
        return result

    def create_export(self, request: ExportRequest) -> ExportRecord:
        if type(request) is not ExportRequest:
            raise ReadServiceError("INVALID_EXPORT_REQUEST")
        try:
            record = self.export_repository.create_export(request)
        except Exception as exc:
            raise self._backend_error(exc, "EXPORT_STORE_UNAVAILABLE") from None
        if (type(record) is not ExportRecord or record.kind != request.kind
                or record.redaction_mode != request.redaction_mode
                or record.run_id != request.run_id or record.receipt_sha256 != request.receipt_sha256):
            raise ReadServiceError("EXPORT_STORE_UNAVAILABLE")
        return record

    def get_export(self, export_id: str) -> ExportRecord:
        _require_export_id(export_id)
        try:
            record = self.export_repository.get_export(export_id)
        except Exception as exc:
            raise self._backend_error(exc, "EXPORT_STORE_UNAVAILABLE") from None
        if record is None:
            raise ReadServiceError("EXPORT_NOT_FOUND")
        if type(record) is not ExportRecord or record.export_id != export_id:
            raise ReadServiceError("EXPORT_STORE_UNAVAILABLE")
        return record


__all__ = [
    "AthenaReadService", "CancelDisposition", "CancelIntentRepository", "CancelIntentResult",
    "EventKind", "ExportKind", "ExportRecord", "ExportRepository", "ExportRequest",
    "ReadBackendError", "ReadServiceError", "ReceiptObservation", "ReceiptState",
    "RedactionMode", "RetainedFixtureIndex", "RetainedFixturePage", "RetainedFixtureRecord",
    "RunEventPage", "RunEventPayload", "RunEventRecord", "RunHistoryEntry", "RunHistoryPage",
    "RunProfile", "RunReadRepository", "RunSnapshotRecord", "RunState", "VerifiedReceiptView",
]
