"""Deterministic runner contract for the reviewed FotMob ordinary-FT history campaign.

PR #102 implements scheduling, resumable append-only campaign evidence, attempt
accounting, and pair-window gates for the exact PR #101 acquisition protocol.
This module is deliberately network-free. The thin script layer performs live
transport by reusing the already-reviewed data-matches capture implementation.

Implementation does not execute the campaign, prove historical coverage, parse
fixtures, materialize history, or authorize model/probability/pricing/selection/
production/betting paths.
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import re
import types
from collections.abc import Mapping, Sequence
from typing import Any

import domain.fotmob_ordinary_ft_source_history_acquisition_protocol as pr101
from domain.fotmob_data_matches_capture import parse_utc_timestamp, serialize_utc


SCHEMA_VERSION = 1
RUNNER_ID = "REVIEWED_FOTMOB_ORDINARY_FT_SOURCE_HISTORY_ACQUISITION_RUNNER_V1"
RUNNER_SCOPE = "DETERMINISTIC_RESUMABLE_ACQUISITION_ORCHESTRATION_ONLY"
RUNNER_STATE = "IMPLEMENTED_NOT_EXECUTED_HISTORICAL_COVERAGE_UNPROVEN"
REPOSITORY_MAIN_SHA = "dfd8d6e932078df917ea720b3e1f4c67ccb1639d"

PR101_PROTOCOL_BLOB_SHA = "39541b351d2990f7ebb9572a8c9c674c85864284"
PR101_PROTOCOL_SHA256 = "cfd8542df66c9e8fbe748f0559d67c336d41e441f3b4de8d6601ac1087cad3a6"
PR101_PROTOCOL_SIZE = 8511

TIMEZONE = "UTC"
CCODE3 = "NGA"
CAPTURE_SLOT_LABELS = ("A", "B")
CAPTURE_SLOTS_PER_DATE = 2
REQUIRED_DATE_COUNT = 2205
REQUIRED_SUCCESSFUL_CAPTURE_COUNT = 4410
MINIMUM_PAIR_SEPARATION_SECONDS = 300
MAXIMUM_PAIR_SEPARATION_SECONDS = 86400
MINIMUM_INTER_REQUEST_SECONDS = 1.0
MAXIMUM_ATTEMPTS_PER_SLOT = 3
RETRY_DELAYS_SECONDS = (60, 300)

CAMPAIGN_ROOT_RELATIVE = ".cache/athena-research/fotmob-ordinary-ft-source-history-campaign-v1"
CAMPAIGN_INDEX_FILENAME = "campaign-index.jsonl"
FAILURE_JOURNAL_FILENAME = "failure-journal.jsonl"
CAMPAIGN_LOCK_FILENAME = "runner.lock"
MAX_EVIDENCE_FILE_BYTES = 64 * 1024 * 1024
MAX_ENTRY_BYTES = 8192
MAX_ERROR_MESSAGE_CHARS = 512

NEXT_REQUIRED_BOUNDARY = (
    "EXECUTE_REVIEWED_FOTMOB_ORDINARY_FT_SOURCE_HISTORY_ACQUISITION_CAMPAIGN"
)

ZERO_SHA256 = "0" * 64
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_CAPTURE_ID_RE = re.compile(r"^[0-9a-f]{24}$", flags=re.ASCII)
_ERROR_KIND_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$", flags=re.ASCII)
_ENTRY_TYPES = frozenset({"SLOT_SUCCEEDED", "ATTEMPT_FAILED", "SLOT_BLOCKED"})
_SUCCESS_DETAIL_KEYS = frozenset(
    {"capture_id", "raw_sha256", "raw_size", "manifest_sha256", "observed_at_utc"}
)
_FAILURE_DETAIL_KEYS = frozenset(
    {"error_kind", "error_message", "capture_id", "manifest_sha256"}
)
_ENTRY_KEYS = frozenset(
    {
        "schema_version",
        "runner_id",
        "sequence",
        "previous_entry_sha256",
        "event_type",
        "request_date",
        "slot",
        "attempt",
        "attempt_started_at_utc",
        "recorded_at_utc",
        "detail",
        "entry_sha256",
    }
)


class FotMobOrdinaryFtSourceHistoryAcquisitionRunnerError(ValueError):
    """Raised when runner state or campaign evidence fails closed."""


class FotMobOrdinaryFtSourceHistoryPairWindowError(
    FotMobOrdinaryFtSourceHistoryAcquisitionRunnerError
):
    """Raised when a slot-B observation cannot satisfy the frozen pair window."""

    def __init__(self, reason: str, message: str) -> None:
        if not isinstance(reason, str) or not reason:
            raise TypeError("pair-window reason must be non-empty text")
        super().__init__(message)
        self.reason = reason


def _error(message: str) -> FotMobOrdinaryFtSourceHistoryAcquisitionRunnerError:
    return FotMobOrdinaryFtSourceHistoryAcquisitionRunnerError(message)


def _canonical(value: Any) -> bytes:
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
        raise _error("campaign evidence serialization failed") from exc


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return types.MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _sha256(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise _error(f"{label} must be exactly 64 lowercase hexadecimal characters")
    return value


def _capture_id(value: Any) -> str:
    if type(value) is not str or _CAPTURE_ID_RE.fullmatch(value) is None:
        raise _error("capture_id must be exactly 24 lowercase hexadecimal characters")
    return value


def _utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise _error(f"{label} must be a timezone-aware datetime")
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            raise _error(f"{label} must be a timezone-aware datetime")
        return value.astimezone(datetime.timezone.utc)
    except FotMobOrdinaryFtSourceHistoryAcquisitionRunnerError:
        raise
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise _error(f"{label} is invalid") from exc


def _timestamp(value: Any, label: str) -> datetime.datetime:
    try:
        return parse_utc_timestamp(value, label)
    except Exception as exc:
        raise _error(f"{label} must be a valid timezone-aware UTC timestamp") from exc


def _serialized(value: Any, label: str) -> str:
    try:
        return serialize_utc(_utc(value, label))
    except Exception as exc:
        if isinstance(exc, FotMobOrdinaryFtSourceHistoryAcquisitionRunnerError):
            raise
        raise _error(f"{label} is invalid") from exc


def _error_text(value: Any) -> str:
    if type(value) is not str:
        raise _error("error_message must be exact text")
    collapsed = " ".join(value.split())
    if not collapsed:
        raise _error("error_message must not be empty")
    return collapsed[:MAX_ERROR_MESSAGE_CHARS]


def _error_kind(value: Any) -> str:
    if type(value) is not str or _ERROR_KIND_RE.fullmatch(value) is None:
        raise _error("error_kind must be 1-64 uppercase ASCII identifier characters")
    return value


def _verify_upstream() -> pr101.FotMobOrdinaryFtSourceHistoryAcquisitionProtocol:
    if (pr101.PROTOCOL_SHA256, pr101.PROTOCOL_SIZE) != (
        PR101_PROTOCOL_SHA256,
        PR101_PROTOCOL_SIZE,
    ):
        raise _error("PR101 acquisition protocol identity changed")
    try:
        value = pr101.build_fotmob_ordinary_ft_source_history_acquisition_protocol()
        exact = pr101.canonical_fotmob_ordinary_ft_source_history_acquisition_protocol_bytes(
            value
        )
    except Exception as exc:
        raise _error("PR101 acquisition protocol no longer revalidates") from exc
    if hashlib.sha256(exact).hexdigest() != PR101_PROTOCOL_SHA256 or len(exact) != PR101_PROTOCOL_SIZE:
        raise _error("PR101 canonical acquisition protocol changed")
    if value.next_required_boundary != (
        "IMPLEMENT_REVIEWED_FOTMOB_ORDINARY_FT_SOURCE_HISTORY_ACQUISITION_RUNNER"
    ):
        raise _error("PR101 next runner boundary changed")
    request = dict(value.request_identity)
    if request.get("timezone") != TIMEZONE or request.get("ccode3") != CCODE3:
        raise _error("PR101 request identity changed")
    interval = dict(value.acquisition_interval)
    if interval.get("inclusive_calendar_date_count") != REQUIRED_DATE_COUNT:
        raise _error("PR101 acquisition date count changed")
    schedule = dict(value.capture_schedule)
    expected_schedule = {
        "capture_slots_per_date": CAPTURE_SLOTS_PER_DATE,
        "slot_labels": CAPTURE_SLOT_LABELS,
        "pass_order": "ALL_SLOT_A_DATES_ASCENDING_THEN_ALL_SLOT_B_DATES_ASCENDING",
        "minimum_same_date_slot_separation_seconds": MINIMUM_PAIR_SEPARATION_SECONDS,
        "maximum_same_date_slot_separation_seconds": MAXIMUM_PAIR_SEPARATION_SECONDS,
        "minimum_inter_request_seconds": MINIMUM_INTER_REQUEST_SECONDS,
        "maximum_attempts_per_slot": MAXIMUM_ATTEMPTS_PER_SLOT,
        "retry_delays_seconds": RETRY_DELAYS_SECONDS,
        "required_successful_capture_count": REQUIRED_SUCCESSFUL_CAPTURE_COUNT,
        "failed_attempts_count_as_success": False,
    }
    if schedule != expected_schedule:
        raise _error("PR101 capture schedule changed")
    if value.network_acquisition_performed is not False or value.campaign_runner_implemented is not False:
        raise _error("PR101 pre-execution state changed")
    if type(value.history_rows_materialized) is not int or value.history_rows_materialized != 0:
        raise _error("PR101 history materialization state changed")
    if any(flag is not False for flag in value.safety.values()):
        raise _error("PR101 safety state changed")
    return value


@dataclasses.dataclass(frozen=True)
class CampaignSlot:
    ordinal: int
    request_date: str
    slot: str

    def __post_init__(self) -> None:
        if type(self.ordinal) is not int or self.ordinal <= 0:
            raise _error("slot ordinal must be an exact positive integer")
        if (
            type(self.request_date) is not str
            or len(self.request_date) != 8
            or not self.request_date.isascii()
            or not self.request_date.isdigit()
        ):
            raise _error("slot request_date must be canonical YYYYMMDD")
        if self.slot not in CAPTURE_SLOT_LABELS:
            raise _error("slot label must be exactly A or B")


@dataclasses.dataclass(frozen=True)
class CampaignProgress:
    completed_slots: int
    total_slots: int
    next_slot: CampaignSlot | None
    next_attempt: int | None
    blocked: bool
    block_reason: str | None

    @property
    def complete(self) -> bool:
        return self.completed_slots == self.total_slots and not self.blocked


def campaign_dates() -> tuple[str, ...]:
    value = _verify_upstream()
    interval = dict(value.acquisition_interval)
    try:
        start = datetime.date.fromisoformat(interval["start_source_local_date"])
        end = datetime.date.fromisoformat(interval["end_source_local_date"])
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("PR101 acquisition interval is invalid") from exc
    if end < start:
        raise _error("PR101 acquisition interval is reversed")
    count = (end - start).days + 1
    if count != REQUIRED_DATE_COUNT:
        raise _error("PR101 acquisition interval no longer has 2205 dates")
    return tuple(
        (start + datetime.timedelta(days=offset)).strftime("%Y%m%d")
        for offset in range(count)
    )


def campaign_slots() -> tuple[CampaignSlot, ...]:
    dates = campaign_dates()
    slots: list[CampaignSlot] = []
    ordinal = 1
    for label in CAPTURE_SLOT_LABELS:
        for request_date in dates:
            slots.append(CampaignSlot(ordinal=ordinal, request_date=request_date, slot=label))
            ordinal += 1
    if len(slots) != REQUIRED_SUCCESSFUL_CAPTURE_COUNT:
        raise _error("campaign plan no longer has exactly 4410 slots")
    return tuple(slots)


def _slot_matches(left: CampaignSlot, right: CampaignSlot) -> bool:
    return (
        left.ordinal == right.ordinal
        and left.request_date == right.request_date
        and left.slot == right.slot
    )


def _entry_base(
    *,
    sequence: int,
    previous_entry_sha256: str,
    event_type: str,
    slot: CampaignSlot,
    attempt: int,
    attempt_started_at: datetime.datetime | None,
    recorded_at: datetime.datetime,
    detail: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "runner_id": RUNNER_ID,
        "sequence": sequence,
        "previous_entry_sha256": previous_entry_sha256,
        "event_type": event_type,
        "request_date": slot.request_date,
        "slot": slot.slot,
        "attempt": attempt,
        "attempt_started_at_utc": (
            None if attempt_started_at is None else _serialized(attempt_started_at, "attempt_started_at")
        ),
        "recorded_at_utc": _serialized(recorded_at, "recorded_at"),
        "detail": _plain(detail),
    }


def _seal(base: Mapping[str, Any]) -> Mapping[str, Any]:
    plain = _plain(base)
    entry_sha256 = hashlib.sha256(_canonical(plain)).hexdigest()
    sealed = {**plain, "entry_sha256": entry_sha256}
    line = _canonical(sealed)
    if len(line) > MAX_ENTRY_BYTES:
        raise _error("campaign evidence entry exceeds size limit")
    return _freeze(sealed)


def canonical_campaign_journal_entry_bytes(entry: Mapping[str, Any]) -> bytes:
    plain = _validate_entry_shape(entry)
    line = _canonical(plain)
    if len(line) > MAX_ENTRY_BYTES:
        raise _error("campaign evidence entry exceeds size limit")
    return line


def _validate_entry_shape(value: Any) -> dict[str, Any]:
    plain = _plain(value)
    if type(plain) is not dict or set(plain) != _ENTRY_KEYS:
        raise _error("campaign evidence entry keys mismatch")
    if type(plain["schema_version"]) is not int or plain["schema_version"] != SCHEMA_VERSION:
        raise _error("campaign evidence schema_version mismatch")
    if plain["runner_id"] != RUNNER_ID:
        raise _error("campaign evidence runner_id mismatch")
    if type(plain["sequence"]) is not int or plain["sequence"] <= 0:
        raise _error("campaign evidence sequence must be an exact positive integer")
    _sha256(plain["previous_entry_sha256"], "previous_entry_sha256")
    event_type = plain["event_type"]
    if event_type not in _ENTRY_TYPES:
        raise _error("campaign evidence event_type is invalid")
    request_date = plain["request_date"]
    if (
        type(request_date) is not str
        or len(request_date) != 8
        or not request_date.isascii()
        or not request_date.isdigit()
    ):
        raise _error("campaign evidence request_date must be canonical YYYYMMDD")
    if plain["slot"] not in CAPTURE_SLOT_LABELS:
        raise _error("campaign evidence slot must be exactly A or B")
    attempt = plain["attempt"]
    if type(attempt) is not int:
        raise _error("campaign evidence attempt must be an exact integer")
    recorded = _timestamp(plain["recorded_at_utc"], "recorded_at_utc")
    started_raw = plain["attempt_started_at_utc"]
    if event_type == "SLOT_BLOCKED":
        if attempt != 0 or started_raw is not None:
            raise _error("SLOT_BLOCKED must use attempt zero and no attempt start")
    else:
        if not 1 <= attempt <= MAXIMUM_ATTEMPTS_PER_SLOT:
            raise _error("attempt event must be within the frozen 1..3 range")
        started = _timestamp(started_raw, "attempt_started_at_utc")
        if recorded < started:
            raise _error("campaign event recorded_at precedes attempt start")
    detail = plain["detail"]
    if type(detail) is not dict:
        raise _error("campaign evidence detail must be an object")
    if event_type == "SLOT_SUCCEEDED":
        if set(detail) != _SUCCESS_DETAIL_KEYS:
            raise _error("success detail keys mismatch")
        _capture_id(detail["capture_id"])
        _sha256(detail["raw_sha256"], "raw_sha256")
        _sha256(detail["manifest_sha256"], "manifest_sha256")
        if type(detail["raw_size"]) is not int or detail["raw_size"] <= 0:
            raise _error("raw_size must be an exact positive integer")
        observed = _timestamp(detail["observed_at_utc"], "observed_at_utc")
        if recorded < observed:
            raise _error("success record precedes capture observation")
    else:
        if set(detail) != _FAILURE_DETAIL_KEYS:
            raise _error("failure detail keys mismatch")
        _error_kind(detail["error_kind"])
        if _error_text(detail["error_message"]) != detail["error_message"]:
            raise _error("error_message must already be canonical bounded text")
        if detail["capture_id"] is not None:
            _capture_id(detail["capture_id"])
        if detail["manifest_sha256"] is not None:
            _sha256(detail["manifest_sha256"], "manifest_sha256")
    _sha256(plain["entry_sha256"], "entry_sha256")
    unsigned = dict(plain)
    claimed = unsigned.pop("entry_sha256")
    expected = hashlib.sha256(_canonical(unsigned)).hexdigest()
    if claimed != expected:
        raise _error("campaign evidence entry SHA-256 mismatch")
    return plain


def _strict_json_line(line: bytes) -> dict[str, Any]:
    if type(line) is not bytes or not line.endswith(b"\n") or len(line) > MAX_ENTRY_BYTES:
        raise _error("campaign evidence line framing is invalid")
    try:
        text = line.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _error("campaign evidence must be UTF-8") from exc

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in items:
            if key in result:
                raise _error("campaign evidence JSON contains duplicate keys")
            result[key] = item
        return result

    def constant(token: str) -> None:
        raise _error(f"campaign evidence JSON constant {token!r} is forbidden")

    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except FotMobOrdinaryFtSourceHistoryAcquisitionRunnerError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise _error("campaign evidence JSON is invalid") from exc
    plain = _validate_entry_shape(value)
    if _canonical(plain) != line:
        raise _error("campaign evidence line is not canonical JSON")
    return plain


def _parse_stream(content: Any, allowed_types: frozenset[str]) -> list[Mapping[str, Any]]:
    if type(content) is not bytes:
        raise _error("campaign evidence file content must be exact bytes")
    if len(content) > MAX_EVIDENCE_FILE_BYTES:
        raise _error("campaign evidence file exceeds size limit")
    if not content:
        return []
    if not content.endswith(b"\n"):
        raise _error("campaign evidence file has a torn trailing entry")
    entries: list[Mapping[str, Any]] = []
    previous_sequence = 0
    for line in content.splitlines(keepends=True):
        plain = _strict_json_line(line)
        if plain["event_type"] not in allowed_types:
            raise _error("campaign evidence event is stored in the wrong file")
        if plain["sequence"] <= previous_sequence:
            raise _error("campaign evidence file sequence must increase")
        previous_sequence = plain["sequence"]
        entries.append(_freeze(plain))
    return entries


def parse_campaign_evidence_bytes(
    campaign_index_bytes: bytes,
    failure_journal_bytes: bytes,
) -> tuple[Mapping[str, Any], ...]:
    _verify_upstream()
    successes = _parse_stream(campaign_index_bytes, frozenset({"SLOT_SUCCEEDED"}))
    failures = _parse_stream(
        failure_journal_bytes, frozenset({"ATTEMPT_FAILED", "SLOT_BLOCKED"})
    )
    merged = sorted([*successes, *failures], key=lambda item: item["sequence"])
    validate_campaign_entries(merged)
    return tuple(merged)


def split_campaign_evidence_bytes(
    entries: Sequence[Mapping[str, Any]],
) -> tuple[bytes, bytes]:
    validated = validate_campaign_entries(entries)
    index_parts: list[bytes] = []
    failure_parts: list[bytes] = []
    for entry in validated:
        encoded = canonical_campaign_journal_entry_bytes(entry)
        if entry["event_type"] == "SLOT_SUCCEEDED":
            index_parts.append(encoded)
        else:
            failure_parts.append(encoded)
    index = b"".join(index_parts)
    failures = b"".join(failure_parts)
    if len(index) > MAX_EVIDENCE_FILE_BYTES or len(failures) > MAX_EVIDENCE_FILE_BYTES:
        raise _error("campaign evidence serialization exceeds file size limit")
    return index, failures


def _observation_for(
    entries: Sequence[Mapping[str, Any]], request_date: str, slot_label: str
) -> datetime.datetime | None:
    for entry in entries:
        if (
            entry["event_type"] == "SLOT_SUCCEEDED"
            and entry["request_date"] == request_date
            and entry["slot"] == slot_label
        ):
            return _timestamp(entry["detail"]["observed_at_utc"], "observed_at_utc")
    return None


def validate_success_observation(
    entries: Sequence[Mapping[str, Any]],
    slot: CampaignSlot,
    observed_at: datetime.datetime,
) -> None:
    validated = validate_campaign_entries(entries)
    progress = campaign_progress(validated, _already_validated=True)
    if progress.next_slot is None or not _slot_matches(slot, progress.next_slot):
        raise _error("success observation does not target the exact next campaign slot")
    observed = _utc(observed_at, "observed_at")
    if slot.slot == "A":
        return
    first = _observation_for(validated, slot.request_date, "A")
    if first is None:
        raise _error("slot B cannot proceed without a qualified slot A observation")
    delta = (observed - first).total_seconds()
    if delta < MINIMUM_PAIR_SEPARATION_SECONDS:
        raise FotMobOrdinaryFtSourceHistoryPairWindowError(
            "PAIR_OBSERVATION_TOO_EARLY",
            "slot B observation is earlier than the frozen 300-second separation",
        )
    if delta > MAXIMUM_PAIR_SEPARATION_SECONDS:
        raise FotMobOrdinaryFtSourceHistoryPairWindowError(
            "PAIR_OBSERVATION_TOO_LATE",
            "slot B observation exceeds the frozen 86400-second separation",
        )


def validate_campaign_entries(
    entries: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    _verify_upstream()
    if isinstance(entries, (str, bytes, bytearray)) or not isinstance(entries, Sequence):
        raise _error("campaign entries must be a sequence")
    normalized = tuple(_freeze(_validate_entry_shape(entry)) for entry in entries)
    plan = campaign_slots()
    expected_index = 0
    failures_for_current = 0
    terminal_reason: str | None = None
    previous_hash = ZERO_SHA256
    previous_recorded: datetime.datetime | None = None
    successes: dict[tuple[str, str], Mapping[str, Any]] = {}

    for offset, entry in enumerate(normalized, start=1):
        if terminal_reason is not None:
            raise _error("campaign evidence continues after a terminal blocker")
        if entry["sequence"] != offset:
            raise _error("campaign evidence global sequence has a gap or duplicate")
        if entry["previous_entry_sha256"] != previous_hash:
            raise _error("campaign evidence hash chain is broken")
        if expected_index >= len(plan):
            raise _error("campaign evidence continues after all slots succeeded")
        expected = plan[expected_index]
        actual = CampaignSlot(
            ordinal=expected.ordinal,
            request_date=entry["request_date"],
            slot=entry["slot"],
        )
        if not _slot_matches(actual, expected):
            raise _error("campaign evidence violates frozen pass order")
        recorded = _timestamp(entry["recorded_at_utc"], "recorded_at_utc")
        if previous_recorded is not None and recorded < previous_recorded:
            raise _error("campaign evidence recorded timestamps move backwards")
        previous_recorded = recorded

        event_type = entry["event_type"]
        if event_type == "ATTEMPT_FAILED":
            expected_attempt = failures_for_current + 1
            if entry["attempt"] != expected_attempt:
                raise _error("failed attempt number is not contiguous for current slot")
            failures_for_current += 1
            if failures_for_current == MAXIMUM_ATTEMPTS_PER_SLOT:
                terminal_reason = "ATTEMPTS_EXHAUSTED"
        elif event_type == "SLOT_BLOCKED":
            if entry["attempt"] != 0:
                raise _error("blocked slot must use attempt zero")
            terminal_reason = entry["detail"]["error_kind"]
        else:
            expected_attempt = failures_for_current + 1
            if entry["attempt"] != expected_attempt:
                raise _error("successful attempt number is not contiguous for current slot")
            if expected_attempt > MAXIMUM_ATTEMPTS_PER_SLOT:
                raise _error("success cannot occur after attempt exhaustion")
            key = (entry["request_date"], entry["slot"])
            if key in successes:
                raise _error("campaign slot success is duplicated")
            observed = _timestamp(entry["detail"]["observed_at_utc"], "observed_at_utc")
            if entry["slot"] == "B":
                first_entry = successes.get((entry["request_date"], "A"))
                if first_entry is None:
                    raise _error("slot B success has no slot A success evidence")
                first = _timestamp(
                    first_entry["detail"]["observed_at_utc"], "observed_at_utc"
                )
                separation = (observed - first).total_seconds()
                if not (
                    MINIMUM_PAIR_SEPARATION_SECONDS
                    <= separation
                    <= MAXIMUM_PAIR_SEPARATION_SECONDS
                ):
                    raise _error("successful A/B observations violate frozen pair separation")
            successes[key] = entry
            expected_index += 1
            failures_for_current = 0

        previous_hash = entry["entry_sha256"]

    return normalized


def campaign_progress(
    entries: Sequence[Mapping[str, Any]],
    *,
    _already_validated: bool = False,
) -> CampaignProgress:
    normalized = tuple(entries) if _already_validated else validate_campaign_entries(entries)
    plan = campaign_slots()
    completed = sum(1 for entry in normalized if entry["event_type"] == "SLOT_SUCCEEDED")
    if completed > len(plan):
        raise _error("completed slot count exceeds frozen campaign size")
    if normalized and normalized[-1]["event_type"] == "SLOT_BLOCKED":
        return CampaignProgress(
            completed_slots=completed,
            total_slots=len(plan),
            next_slot=plan[completed] if completed < len(plan) else None,
            next_attempt=None,
            blocked=True,
            block_reason=normalized[-1]["detail"]["error_kind"],
        )
    current_failures = 0
    for entry in reversed(normalized):
        if entry["event_type"] == "SLOT_SUCCEEDED":
            break
        if entry["event_type"] == "ATTEMPT_FAILED":
            current_failures += 1
    if current_failures >= MAXIMUM_ATTEMPTS_PER_SLOT:
        return CampaignProgress(
            completed_slots=completed,
            total_slots=len(plan),
            next_slot=plan[completed] if completed < len(plan) else None,
            next_attempt=None,
            blocked=True,
            block_reason="ATTEMPTS_EXHAUSTED",
        )
    next_slot = plan[completed] if completed < len(plan) else None
    return CampaignProgress(
        completed_slots=completed,
        total_slots=len(plan),
        next_slot=next_slot,
        next_attempt=(None if next_slot is None else current_failures + 1),
        blocked=False,
        block_reason=None,
    )


def _previous_hash(entries: Sequence[Mapping[str, Any]]) -> str:
    return ZERO_SHA256 if not entries else _sha256(entries[-1]["entry_sha256"], "entry_sha256")


def _require_current(
    entries: Sequence[Mapping[str, Any]], slot: CampaignSlot, attempt: int | None
) -> tuple[Mapping[str, Any], ...]:
    normalized = validate_campaign_entries(entries)
    progress = campaign_progress(normalized, _already_validated=True)
    if progress.complete:
        raise _error("campaign is already complete")
    if progress.blocked:
        raise _error("campaign is blocked and cannot append another attempt")
    if progress.next_slot is None or not _slot_matches(slot, progress.next_slot):
        raise _error("entry does not target the exact next frozen campaign slot")
    if attempt is not None and progress.next_attempt != attempt:
        raise _error("entry attempt does not match the exact next attempt")
    return normalized


def build_attempt_failed_entry(
    entries: Sequence[Mapping[str, Any]],
    *,
    slot: CampaignSlot,
    attempt: int,
    attempt_started_at: datetime.datetime,
    recorded_at: datetime.datetime,
    error_kind: str,
    error_message: str,
    capture_id: str | None = None,
    manifest_sha256: str | None = None,
) -> Mapping[str, Any]:
    normalized = _require_current(entries, slot, attempt)
    detail = {
        "error_kind": _error_kind(error_kind),
        "error_message": _error_text(error_message),
        "capture_id": None if capture_id is None else _capture_id(capture_id),
        "manifest_sha256": (
            None if manifest_sha256 is None else _sha256(manifest_sha256, "manifest_sha256")
        ),
    }
    base = _entry_base(
        sequence=len(normalized) + 1,
        previous_entry_sha256=_previous_hash(normalized),
        event_type="ATTEMPT_FAILED",
        slot=slot,
        attempt=attempt,
        attempt_started_at=attempt_started_at,
        recorded_at=recorded_at,
        detail=detail,
    )
    entry = _seal(base)
    validate_campaign_entries((*normalized, entry))
    return entry


def build_slot_succeeded_entry(
    entries: Sequence[Mapping[str, Any]],
    *,
    slot: CampaignSlot,
    attempt: int,
    attempt_started_at: datetime.datetime,
    recorded_at: datetime.datetime,
    capture_id: str,
    raw_sha256: str,
    raw_size: int,
    manifest_sha256: str,
    observed_at: datetime.datetime,
) -> Mapping[str, Any]:
    normalized = _require_current(entries, slot, attempt)
    validate_success_observation(normalized, slot, observed_at)
    if type(raw_size) is not int or raw_size <= 0:
        raise _error("raw_size must be an exact positive integer")
    detail = {
        "capture_id": _capture_id(capture_id),
        "raw_sha256": _sha256(raw_sha256, "raw_sha256"),
        "raw_size": raw_size,
        "manifest_sha256": _sha256(manifest_sha256, "manifest_sha256"),
        "observed_at_utc": _serialized(observed_at, "observed_at"),
    }
    base = _entry_base(
        sequence=len(normalized) + 1,
        previous_entry_sha256=_previous_hash(normalized),
        event_type="SLOT_SUCCEEDED",
        slot=slot,
        attempt=attempt,
        attempt_started_at=attempt_started_at,
        recorded_at=recorded_at,
        detail=detail,
    )
    entry = _seal(base)
    validate_campaign_entries((*normalized, entry))
    return entry


def build_slot_blocked_entry(
    entries: Sequence[Mapping[str, Any]],
    *,
    slot: CampaignSlot,
    recorded_at: datetime.datetime,
    error_kind: str,
    error_message: str,
    capture_id: str | None = None,
    manifest_sha256: str | None = None,
) -> Mapping[str, Any]:
    normalized = _require_current(entries, slot, None)
    detail = {
        "error_kind": _error_kind(error_kind),
        "error_message": _error_text(error_message),
        "capture_id": None if capture_id is None else _capture_id(capture_id),
        "manifest_sha256": (
            None if manifest_sha256 is None else _sha256(manifest_sha256, "manifest_sha256")
        ),
    }
    base = _entry_base(
        sequence=len(normalized) + 1,
        previous_entry_sha256=_previous_hash(normalized),
        event_type="SLOT_BLOCKED",
        slot=slot,
        attempt=0,
        attempt_started_at=None,
        recorded_at=recorded_at,
        detail=detail,
    )
    entry = _seal(base)
    validate_campaign_entries((*normalized, entry))
    return entry


def seconds_until_inter_request_eligible(
    entries: Sequence[Mapping[str, Any]],
    now: datetime.datetime,
) -> float:
    normalized = validate_campaign_entries(entries)
    current = _utc(now, "now")
    latest_start: datetime.datetime | None = None
    for entry in reversed(normalized):
        raw = entry["attempt_started_at_utc"]
        if raw is not None:
            latest_start = _timestamp(raw, "attempt_started_at_utc")
            break
    if latest_start is None:
        return 0.0
    elapsed = (current - latest_start).total_seconds()
    if elapsed < 0:
        raise _error("runner clock precedes the latest recorded request start")
    return max(0.0, MINIMUM_INTER_REQUEST_SECONDS - elapsed)


def seconds_until_retry_eligible(
    entries: Sequence[Mapping[str, Any]],
    now: datetime.datetime,
) -> float:
    normalized = validate_campaign_entries(entries)
    if not normalized or normalized[-1]["event_type"] != "ATTEMPT_FAILED":
        return 0.0
    latest = normalized[-1]
    attempt = latest["attempt"]
    if attempt >= MAXIMUM_ATTEMPTS_PER_SLOT:
        raise _error("campaign is blocked by attempt exhaustion")
    current = _utc(now, "now")
    recorded = _timestamp(latest["recorded_at_utc"], "recorded_at_utc")
    elapsed = (current - recorded).total_seconds()
    if elapsed < 0:
        raise _error("runner clock precedes the latest failed-attempt record")
    delay = RETRY_DELAYS_SECONDS[attempt - 1]
    return max(0.0, float(delay) - elapsed)


def seconds_until_pair_eligible(
    entries: Sequence[Mapping[str, Any]],
    now: datetime.datetime,
) -> float:
    normalized = validate_campaign_entries(entries)
    progress = campaign_progress(normalized, _already_validated=True)
    if progress.complete:
        return 0.0
    if progress.blocked:
        raise _error("campaign is blocked")
    slot = progress.next_slot
    if slot is None or slot.slot == "A":
        return 0.0
    first = _observation_for(normalized, slot.request_date, "A")
    if first is None:
        raise _error("slot B cannot proceed without slot A observation")
    current = _utc(now, "now")
    elapsed = (current - first).total_seconds()
    if elapsed < 0:
        raise FotMobOrdinaryFtSourceHistoryPairWindowError(
            "RUNNER_CLOCK_PRECEDES_SLOT_A",
            "runner clock precedes the slot A observation",
        )
    if elapsed > MAXIMUM_PAIR_SEPARATION_SECONDS:
        raise FotMobOrdinaryFtSourceHistoryPairWindowError(
            "PAIR_WINDOW_EXPIRED_BEFORE_REQUEST",
            "slot B can no longer satisfy the frozen 86400-second pair window",
        )
    return max(0.0, MINIMUM_PAIR_SEPARATION_SECONDS - elapsed)


def seconds_until_next_request_eligible(
    entries: Sequence[Mapping[str, Any]],
    now: datetime.datetime,
) -> float:
    return max(
        seconds_until_inter_request_eligible(entries, now),
        seconds_until_pair_eligible(entries, now),
        seconds_until_retry_eligible(entries, now),
    )


def runner_state() -> Mapping[str, Any]:
    _verify_upstream()
    return _freeze(
        {
            "schema_version": SCHEMA_VERSION,
            "runner_id": RUNNER_ID,
            "runner_scope": RUNNER_SCOPE,
            "runner_state": RUNNER_STATE,
            "repository_main_sha": REPOSITORY_MAIN_SHA,
            "pr101_protocol_blob_sha": PR101_PROTOCOL_BLOB_SHA,
            "pr101_protocol_sha256": PR101_PROTOCOL_SHA256,
            "pr101_protocol_size": PR101_PROTOCOL_SIZE,
            "request_identity": {"timezone": TIMEZONE, "ccode3": CCODE3},
            "required_date_count": REQUIRED_DATE_COUNT,
            "required_successful_capture_count": REQUIRED_SUCCESSFUL_CAPTURE_COUNT,
            "campaign_root_relative": CAMPAIGN_ROOT_RELATIVE,
            "campaign_index_filename": CAMPAIGN_INDEX_FILENAME,
            "failure_journal_filename": FAILURE_JOURNAL_FILENAME,
            "network_acquisition_performed": False,
            "history_rows_materialized": 0,
            "historical_coverage_proven": False,
            "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
            "downstream_authority": {
                "source_history_completeness_proven": False,
                "model_authorized": False,
                "probability_authorized": False,
                "pricing_authorized": False,
                "selection_authorized": False,
                "production_authorized": False,
                "bet_authorized": False,
            },
        }
    )


__all__ = [
    "CAMPAIGN_INDEX_FILENAME",
    "CAMPAIGN_LOCK_FILENAME",
    "CAMPAIGN_ROOT_RELATIVE",
    "CAPTURE_SLOT_LABELS",
    "CCODE3",
    "CampaignProgress",
    "CampaignSlot",
    "FAILURE_JOURNAL_FILENAME",
    "FotMobOrdinaryFtSourceHistoryAcquisitionRunnerError",
    "FotMobOrdinaryFtSourceHistoryPairWindowError",
    "MAXIMUM_ATTEMPTS_PER_SLOT",
    "MAXIMUM_PAIR_SEPARATION_SECONDS",
    "MINIMUM_INTER_REQUEST_SECONDS",
    "MINIMUM_PAIR_SEPARATION_SECONDS",
    "NEXT_REQUIRED_BOUNDARY",
    "PR101_PROTOCOL_SHA256",
    "PR101_PROTOCOL_SIZE",
    "REQUIRED_DATE_COUNT",
    "REQUIRED_SUCCESSFUL_CAPTURE_COUNT",
    "RETRY_DELAYS_SECONDS",
    "RUNNER_ID",
    "RUNNER_SCOPE",
    "RUNNER_STATE",
    "SCHEMA_VERSION",
    "TIMEZONE",
    "build_attempt_failed_entry",
    "build_slot_blocked_entry",
    "build_slot_succeeded_entry",
    "campaign_dates",
    "campaign_progress",
    "campaign_slots",
    "canonical_campaign_journal_entry_bytes",
    "parse_campaign_evidence_bytes",
    "runner_state",
    "seconds_until_inter_request_eligible",
    "seconds_until_next_request_eligible",
    "seconds_until_pair_eligible",
    "seconds_until_retry_eligible",
    "split_campaign_evidence_bytes",
    "validate_campaign_entries",
    "validate_success_observation",
]
