"""Deterministic orchestration contract for PR69 primary time-basis evidence acquisition.

PR #125 implements only the runner required by the exact PR #124 protocol. Importing
this module performs no network access. It freezes campaign order, append-only evidence,
retry/pair timing, manifests, and fail-closed progress semantics before any execution.
"""
from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import re
import types
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import domain.pr69_primary_time_basis_evidence_acquisition_protocol as pr124

SCHEMA_VERSION = 1
RUNNER_ID = "REVIEWED_PR69_PRIMARY_TIME_BASIS_EVIDENCE_ACQUISITION_RUNNER_V1"
RUNNER_SCOPE = "DETERMINISTIC_RESUMABLE_PRIMARY_EVIDENCE_ACQUISITION_ORCHESTRATION_ONLY"
RUNNER_STATE = "IMPLEMENTED_NOT_EXECUTED_PRIMARY_TIME_BASIS_EVIDENCE_NOT_CAPTURED"
REPOSITORY_MAIN_SHA = "e094c53d9c881dc9d7a35c24ac85f733b7abe36e"
PR124_PROTOCOL_BLOB_SHA = "df1a25227b8fee5fbbb21dce7f5f8be5d2464954"
PR124_PROTOCOL_SHA256 = "28ec0a0208858ce3258a584bad1361577a0e202e5cbdb8eb9b13cdd47d7455a3"
PR124_PROTOCOL_SIZE = 9_039

PRIMARY_ORIGIN = "https://www.football-data.co.uk"
CAPTURE_ROOT_RELATIVE = ".cache/athena-research/pr69-primary-time-basis-evidence"
CAMPAIGN_INDEX_FILENAME = "campaign-index.jsonl"
FAILURE_JOURNAL_FILENAME = "failure-journal.jsonl"
RUNNER_LOCK_FILENAME = "runner.lock"
RAW_BODY_FILENAME = "response.bin"
MANIFEST_FILENAME = "manifest.json"
SLOT_LABELS = ("A", "B")
TARGET_COUNT = 4
REQUIRED_SUCCESSFUL_CAPTURE_COUNT = 8
MINIMUM_PAIR_SEPARATION_SECONDS = 300
MAXIMUM_PAIR_SEPARATION_SECONDS = 3600
MINIMUM_INTER_REQUEST_SECONDS = 1.0
MAXIMUM_ATTEMPTS_PER_SLOT = 3
RETRY_DELAYS_SECONDS = (60, 300)
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_ENTRY_BYTES = 16 * 1024
MAX_EVIDENCE_FILE_BYTES = 4 * 1024 * 1024
MAX_ERROR_MESSAGE_CHARS = 768
NEXT_REQUIRED_BOUNDARY = "EXECUTE_REVIEWED_PR69_PRIMARY_TIME_BASIS_EVIDENCE_ACQUISITION_CAMPAIGN"
ZERO_SHA256 = "0" * 64

REQUEST_HEADERS = (
    ("Accept", "text/plain,text/html;q=0.9,*/*;q=0.1"),
    ("Accept-Encoding", "identity"),
    ("User-Agent", "ATHENA/1.0"),
)
SELECTED_RESPONSE_HEADERS = (
    "cache-control", "content-encoding", "content-length", "content-type", "date",
    "etag", "last-modified", "location", "server",
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_ERROR_KIND_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$", re.ASCII)
_TARGET_ID_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$", re.ASCII)
_EVENT_TYPES = frozenset({"SLOT_SUCCEEDED", "ATTEMPT_FAILED", "SLOT_BLOCKED"})
_ENTRY_KEYS = frozenset({
    "schema_version", "runner_id", "sequence", "previous_entry_sha256",
    "event_type", "target_id", "slot", "attempt", "attempt_started_at_utc",
    "recorded_at_utc", "detail", "entry_sha256",
})
_SUCCESS_DETAIL_KEYS = frozenset({
    "manifest_sha256", "raw_sha256", "raw_size", "observed_at_utc",
})
_FAILURE_DETAIL_KEYS = frozenset({"error_kind", "error_message"})
_MANIFEST_KEYS = frozenset({
    "schema_version", "runner_id", "protocol_sha256", "target_id", "slot", "attempt",
    "requested_url", "final_url", "request_method", "request_headers", "redirect_chain",
    "request_started_at_utc", "response_completed_at_utc", "observed_at_utc", "http_status",
    "tls_verified", "response_headers", "raw_filename", "raw_sha256", "raw_size",
})


class PR69PrimaryTimeBasisEvidenceAcquisitionRunnerError(ValueError):
    """Raised when runner state or campaign evidence fails closed."""


class PR69PrimaryTimeBasisEvidencePairWindowError(
    PR69PrimaryTimeBasisEvidenceAcquisitionRunnerError
):
    """Raised when slot B can no longer satisfy the frozen pair window."""

    def __init__(self, reason: str, message: str) -> None:
        if type(reason) is not str or not reason:
            raise TypeError("pair-window reason must be non-empty text")
        super().__init__(message)
        self.reason = reason


def _error(message: str) -> PR69PrimaryTimeBasisEvidenceAcquisitionRunnerError:
    return PR69PrimaryTimeBasisEvidenceAcquisitionRunnerError(message)


def canonical_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("runner evidence serialization failed") from exc


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
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


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def serialize_utc(value: datetime.datetime) -> str:
    if (
        not isinstance(value, datetime.datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise _error("timestamp must be timezone-aware")
    current = value.astimezone(datetime.timezone.utc)
    return current.isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_utc(value: Any, label: str) -> datetime.datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise _error(f"{label} must be canonical UTC text")
    try:
        parsed = datetime.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise _error(f"{label} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != datetime.timedelta(0):
        raise _error(f"{label} must be UTC")
    if serialize_utc(parsed) != value:
        raise _error(f"{label} must use canonical microsecond UTC format")
    return parsed


def _utc(value: Any, label: str) -> datetime.datetime:
    if (
        not isinstance(value, datetime.datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise _error(f"{label} must be timezone-aware")
    return value.astimezone(datetime.timezone.utc)


def validate_sha256(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise _error(f"{label} must be 64 lowercase hexadecimal characters")
    return value


def validate_error_kind(value: Any) -> str:
    if type(value) is not str or _ERROR_KIND_RE.fullmatch(value) is None:
        raise _error("error kind must be an uppercase identifier")
    return value


def normalize_error_message(value: Any) -> str:
    if type(value) is not str:
        raise _error("error message must be text")
    collapsed = " ".join(value.split()) or "unspecified acquisition failure"
    return collapsed[:MAX_ERROR_MESSAGE_CHARS]


def _verify_upstream() -> pr124.PR69PrimaryTimeBasisEvidenceAcquisitionProtocol:
    if _git_blob_sha(Path(pr124.__file__)) != PR124_PROTOCOL_BLOB_SHA:
        raise _error("PR124 protocol implementation blob changed")
    if (pr124.PROTOCOL_SHA256, pr124.PROTOCOL_SIZE) != (
        PR124_PROTOCOL_SHA256, PR124_PROTOCOL_SIZE
    ):
        raise _error("PR124 protocol identity changed")
    try:
        protocol = pr124.build_pr69_primary_time_basis_evidence_acquisition_protocol()
        exact = pr124.canonical_pr69_primary_time_basis_evidence_acquisition_protocol_bytes(
            protocol
        )
    except Exception as exc:
        raise _error("PR124 protocol no longer revalidates") from exc
    if (
        hashlib.sha256(exact).hexdigest() != PR124_PROTOCOL_SHA256
        or len(exact) != PR124_PROTOCOL_SIZE
    ):
        raise _error("PR124 canonical protocol bytes changed")
    if protocol.next_required_boundary != (
        "IMPLEMENT_REVIEWED_PR69_PRIMARY_TIME_BASIS_EVIDENCE_ACQUISITION_RUNNER"
    ):
        raise _error("PR124 runner boundary changed")
    expected_request = {
        "method": "GET",
        "scheme": "https",
        "host": "www.football-data.co.uk",
        "port": 443,
        "request_headers": REQUEST_HEADERS,
        "redirects_authorized": False,
        "cookies_authorized": False,
        "browser_impersonation_authorized": False,
        "proxy_evasion_authorized": False,
        "tls_verification_required": True,
    }
    if dict(protocol.request_identity) != expected_request:
        raise _error("PR124 request identity changed")
    expected_schedule = {
        "target_count": TARGET_COUNT,
        "capture_slots_per_target": 2,
        "slot_labels": SLOT_LABELS,
        "pass_order": (
            "ALL_TARGETS_SLOT_A_IN_FROZEN_ORDER_THEN_ALL_TARGETS_SLOT_B_IN_FROZEN_ORDER"
        ),
        "minimum_same_target_pair_separation_seconds": MINIMUM_PAIR_SEPARATION_SECONDS,
        "maximum_same_target_pair_separation_seconds": MAXIMUM_PAIR_SEPARATION_SECONDS,
        "minimum_inter_request_seconds": MINIMUM_INTER_REQUEST_SECONDS,
        "maximum_attempts_per_slot": MAXIMUM_ATTEMPTS_PER_SLOT,
        "retry_delays_seconds": RETRY_DELAYS_SECONDS,
        "required_successful_capture_count": REQUIRED_SUCCESSFUL_CAPTURE_COUNT,
        "failed_attempts_count_as_success": False,
    }
    if dict(protocol.capture_schedule) != expected_schedule:
        raise _error("PR124 capture schedule changed")
    capture = dict(protocol.capture_contract)
    if capture.get("capture_root") != CAPTURE_ROOT_RELATIVE:
        raise _error("PR124 capture root changed")
    if (capture.get("raw_body_filename"), capture.get("manifest_filename")) != (
        RAW_BODY_FILENAME, MANIFEST_FILENAME
    ):
        raise _error("PR124 capture filenames changed")
    if (capture.get("campaign_index_filename"), capture.get("failure_journal_filename")) != (
        CAMPAIGN_INDEX_FILENAME, FAILURE_JOURNAL_FILENAME
    ):
        raise _error("PR124 journal filenames changed")
    if capture.get("max_response_bytes") != MAX_RESPONSE_BYTES:
        raise _error("PR124 response size bound changed")
    if tuple(capture.get("accepted_http_statuses", ())) != (200,):
        raise _error("PR124 accepted status set changed")
    if tuple(capture.get("selected_response_headers", ())) != SELECTED_RESPONSE_HEADERS:
        raise _error("PR124 selected response headers changed")
    if capture.get("no_overwrite") is not True:
        raise _error("PR124 no-overwrite contract changed")
    if (
        protocol.network_acquisition_performed is not False
        or protocol.campaign_runner_implemented is not False
        or protocol.evidence_records_captured != 0
    ):
        raise _error("PR124 pre-execution state changed")
    if any(value is not False for value in protocol.safety.values()):
        raise _error("PR124 safety state changed")
    return protocol


@dataclasses.dataclass(frozen=True)
class CampaignSlot:
    ordinal: int
    target_id: str
    path: str
    content_type_prefix: str
    slot: str

    def __post_init__(self) -> None:
        if type(self.ordinal) is not int or self.ordinal < 1:
            raise _error("slot ordinal must be a positive integer")
        if type(self.target_id) is not str or _TARGET_ID_RE.fullmatch(self.target_id) is None:
            raise _error("target_id must be an uppercase identifier")
        if (
            type(self.path) is not str
            or not self.path.startswith("/")
            or "?" in self.path
            or "#" in self.path
        ):
            raise _error("target path must be a simple absolute path")
        if type(self.content_type_prefix) is not str or not self.content_type_prefix:
            raise _error("content type prefix must be non-empty text")
        if self.slot not in SLOT_LABELS:
            raise _error("slot must be exactly A or B")

    @property
    def requested_url(self) -> str:
        return PRIMARY_ORIGIN + self.path


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


def campaign_slots() -> tuple[CampaignSlot, ...]:
    protocol = _verify_upstream()
    if len(protocol.targets) != TARGET_COUNT:
        raise _error("PR124 target count changed")
    result: list[CampaignSlot] = []
    ordinal = 1
    for slot_label in SLOT_LABELS:
        for target in protocol.targets:
            result.append(
                CampaignSlot(
                    ordinal=ordinal,
                    target_id=target.target_id,
                    path=target.path,
                    content_type_prefix=target.content_type_prefix,
                    slot=slot_label,
                )
            )
            ordinal += 1
    if len(result) != REQUIRED_SUCCESSFUL_CAPTURE_COUNT:
        raise _error("campaign plan no longer has exactly eight slots")
    return tuple(result)


def _pairs(value: Any, label: str) -> list[list[str]]:
    if type(value) is not list:
        raise _error(f"{label} must be a JSON list")
    result: list[list[str]] = []
    for item in value:
        if (
            type(item) is not list
            or len(item) != 2
            or any(type(part) is not str for part in item)
        ):
            raise _error(f"{label} must contain exact two-text-item lists")
        result.append([item[0], item[1]])
    return result


def validate_manifest(
    value: Any, expected_slot: CampaignSlot | None = None
) -> Mapping[str, Any]:
    plain = _plain(value)
    if type(plain) is not dict or set(plain) != _MANIFEST_KEYS:
        raise _error("manifest keys changed")
    if (
        plain["schema_version"] != SCHEMA_VERSION
        or type(plain["schema_version"]) is not int
        or plain["runner_id"] != RUNNER_ID
    ):
        raise _error("manifest runner identity changed")
    if plain["protocol_sha256"] != PR124_PROTOCOL_SHA256:
        raise _error("manifest protocol identity changed")
    if (
        type(plain["target_id"]) is not str
        or _TARGET_ID_RE.fullmatch(plain["target_id"]) is None
    ):
        raise _error("manifest target identity is invalid")
    if plain["slot"] not in SLOT_LABELS:
        raise _error("manifest slot is invalid")
    if (
        type(plain["attempt"]) is not int
        or not 1 <= plain["attempt"] <= MAXIMUM_ATTEMPTS_PER_SLOT
    ):
        raise _error("manifest attempt is invalid")
    if plain["request_method"] != "GET":
        raise _error("manifest request method changed")
    if plain["requested_url"] != plain["final_url"]:
        raise _error("redirected final URL is not admissible")
    if not isinstance(plain["requested_url"], str) or not plain["requested_url"].startswith(
        PRIMARY_ORIGIN + "/"
    ):
        raise _error("manifest URL is outside primary origin")
    if _pairs(plain["request_headers"], "request_headers") != [
        list(item) for item in REQUEST_HEADERS
    ]:
        raise _error("manifest request headers changed")
    if plain["redirect_chain"] != []:
        raise _error("manifest redirect chain must be empty")
    if plain["tls_verified"] is not True or plain["http_status"] != 200:
        raise _error("manifest transport state is not admissible")
    headers = _pairs(plain["response_headers"], "response_headers")
    if any(name not in SELECTED_RESPONSE_HEADERS for name, _ in headers):
        raise _error("manifest contains an unreviewed response header")
    if plain["raw_filename"] != RAW_BODY_FILENAME:
        raise _error("manifest raw filename changed")
    validate_sha256(plain["raw_sha256"], "manifest raw sha256")
    if (
        type(plain["raw_size"]) is not int
        or not 0 < plain["raw_size"] <= MAX_RESPONSE_BYTES
    ):
        raise _error("manifest raw size is invalid")
    started = parse_utc(plain["request_started_at_utc"], "request_started_at_utc")
    completed = parse_utc(
        plain["response_completed_at_utc"], "response_completed_at_utc"
    )
    observed = parse_utc(plain["observed_at_utc"], "observed_at_utc")
    if not started <= completed <= observed:
        raise _error("manifest timestamps are out of order")
    if expected_slot is not None:
        if (plain["target_id"], plain["slot"], plain["requested_url"]) != (
            expected_slot.target_id,
            expected_slot.slot,
            expected_slot.requested_url,
        ):
            raise _error("manifest does not match planned slot")
        content_types = [value for name, value in headers if name == "content-type"]
        if len(content_types) != 1:
            raise _error("manifest must preserve exactly one Content-Type")
        media_type = content_types[0].split(";", 1)[0].strip().lower()
        if not media_type.startswith(expected_slot.content_type_prefix.lower()):
            raise _error("manifest Content-Type does not match target")
    return _freeze(plain)


def manifest_sha256(manifest: Mapping[str, Any]) -> str:
    checked = validate_manifest(manifest)
    return hashlib.sha256(canonical_bytes(_plain(checked))).hexdigest()


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
    if type(sequence) is not int or sequence <= 0:
        raise _error("entry sequence must be a positive integer")
    validate_sha256(previous_entry_sha256, "previous_entry_sha256")
    if event_type not in _EVENT_TYPES:
        raise _error("entry event type is invalid")
    return {
        "schema_version": SCHEMA_VERSION,
        "runner_id": RUNNER_ID,
        "sequence": sequence,
        "previous_entry_sha256": previous_entry_sha256,
        "event_type": event_type,
        "target_id": slot.target_id,
        "slot": slot.slot,
        "attempt": attempt,
        "attempt_started_at_utc": (
            None if attempt_started_at is None else serialize_utc(attempt_started_at)
        ),
        "recorded_at_utc": serialize_utc(recorded_at),
        "detail": _plain(detail),
    }


def _seal(base: Mapping[str, Any]) -> Mapping[str, Any]:
    plain = _plain(base)
    digest = hashlib.sha256(canonical_bytes(plain)).hexdigest()
    sealed = {**plain, "entry_sha256": digest}
    if len(canonical_bytes(sealed)) > MAX_ENTRY_BYTES:
        raise _error("campaign entry exceeds size limit")
    return _freeze(sealed)


def _validate_entry_shape(value: Any) -> dict[str, Any]:
    plain = _plain(value)
    if type(plain) is not dict or set(plain) != _ENTRY_KEYS:
        raise _error("campaign evidence entry keys mismatch")
    if (
        plain["schema_version"] != SCHEMA_VERSION
        or type(plain["schema_version"]) is not int
        or plain["runner_id"] != RUNNER_ID
    ):
        raise _error("campaign evidence identity mismatch")
    if type(plain["sequence"]) is not int or plain["sequence"] <= 0:
        raise _error("campaign sequence must be a positive integer")
    validate_sha256(plain["previous_entry_sha256"], "previous_entry_sha256")
    event_type = plain["event_type"]
    if event_type not in _EVENT_TYPES:
        raise _error("campaign event type is invalid")
    if (
        type(plain["target_id"]) is not str
        or _TARGET_ID_RE.fullmatch(plain["target_id"]) is None
    ):
        raise _error("campaign target identity is invalid")
    if plain["slot"] not in SLOT_LABELS:
        raise _error("campaign slot is invalid")
    attempt = plain["attempt"]
    recorded = parse_utc(plain["recorded_at_utc"], "recorded_at_utc")
    started_raw = plain["attempt_started_at_utc"]
    if event_type == "SLOT_BLOCKED":
        if attempt != 0 or started_raw is not None:
            raise _error("SLOT_BLOCKED must use attempt zero and no attempt start")
    else:
        if type(attempt) is not int or not 1 <= attempt <= MAXIMUM_ATTEMPTS_PER_SLOT:
            raise _error("attempt event must be within frozen 1..3 range")
        started = parse_utc(started_raw, "attempt_started_at_utc")
        if recorded < started:
            raise _error("campaign event recorded before attempt start")
    detail = plain["detail"]
    if type(detail) is not dict:
        raise _error("campaign detail must be an object")
    if event_type == "SLOT_SUCCEEDED":
        if set(detail) != _SUCCESS_DETAIL_KEYS:
            raise _error("success detail keys mismatch")
        validate_sha256(detail["manifest_sha256"], "manifest_sha256")
        validate_sha256(detail["raw_sha256"], "raw_sha256")
        if (
            type(detail["raw_size"]) is not int
            or not 0 < detail["raw_size"] <= MAX_RESPONSE_BYTES
        ):
            raise _error("success raw size is invalid")
        observed = parse_utc(detail["observed_at_utc"], "observed_at_utc")
        if recorded < observed:
            raise _error("success record precedes capture observation")
    else:
        if set(detail) != _FAILURE_DETAIL_KEYS:
            raise _error("failure detail keys mismatch")
        validate_error_kind(detail["error_kind"])
        if normalize_error_message(detail["error_message"]) != detail["error_message"]:
            raise _error("error message is not canonical bounded text")
    claimed = validate_sha256(plain["entry_sha256"], "entry_sha256")
    unsigned = dict(plain)
    unsigned.pop("entry_sha256")
    if hashlib.sha256(canonical_bytes(unsigned)).hexdigest() != claimed:
        raise _error("campaign entry hash mismatch")
    return plain


def canonical_campaign_entry_bytes(entry: Mapping[str, Any]) -> bytes:
    plain = _validate_entry_shape(entry)
    encoded = canonical_bytes(plain)
    if len(encoded) > MAX_ENTRY_BYTES:
        raise _error("campaign entry exceeds size limit")
    return encoded


def _strict_json_line(line: bytes) -> Mapping[str, Any]:
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
                raise _error("campaign JSON contains duplicate keys")
            result[key] = item
        return result

    def constant(token: str) -> None:
        raise _error(f"campaign JSON constant {token!r} is forbidden")

    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except PR69PrimaryTimeBasisEvidenceAcquisitionRunnerError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise _error("campaign JSON is invalid") from exc
    plain = _validate_entry_shape(value)
    if canonical_bytes(plain) != line:
        raise _error("campaign evidence line is not canonical JSON")
    return _freeze(plain)


def _parse_stream(content: Any, allowed: frozenset[str]) -> list[Mapping[str, Any]]:
    if type(content) is not bytes:
        raise _error("campaign evidence file must be exact bytes")
    if len(content) > MAX_EVIDENCE_FILE_BYTES:
        raise _error("campaign evidence file exceeds size limit")
    if not content:
        return []
    if not content.endswith(b"\n"):
        raise _error("campaign evidence file has a torn trailing entry")
    result: list[Mapping[str, Any]] = []
    previous_sequence = 0
    for line in content.splitlines(keepends=True):
        entry = _strict_json_line(line)
        if entry["event_type"] not in allowed:
            raise _error("campaign event is stored in the wrong evidence file")
        if entry["sequence"] <= previous_sequence:
            raise _error("per-file campaign sequence must increase")
        previous_sequence = entry["sequence"]
        result.append(entry)
    return result


def parse_campaign_evidence_bytes(
    campaign_index_bytes: bytes, failure_journal_bytes: bytes
) -> tuple[Mapping[str, Any], ...]:
    _verify_upstream()
    successes = _parse_stream(campaign_index_bytes, frozenset({"SLOT_SUCCEEDED"}))
    failures = _parse_stream(
        failure_journal_bytes, frozenset({"ATTEMPT_FAILED", "SLOT_BLOCKED"})
    )
    merged = sorted([*successes, *failures], key=lambda item: item["sequence"])
    return validate_campaign_entries(merged)


def split_campaign_evidence_bytes(
    entries: Sequence[Mapping[str, Any]],
) -> tuple[bytes, bytes]:
    normalized = validate_campaign_entries(entries)
    index_parts: list[bytes] = []
    failure_parts: list[bytes] = []
    for entry in normalized:
        encoded = canonical_campaign_entry_bytes(entry)
        if entry["event_type"] == "SLOT_SUCCEEDED":
            index_parts.append(encoded)
        else:
            failure_parts.append(encoded)
    index = b"".join(index_parts)
    failures = b"".join(failure_parts)
    if len(index) > MAX_EVIDENCE_FILE_BYTES or len(failures) > MAX_EVIDENCE_FILE_BYTES:
        raise _error("serialized campaign evidence exceeds file limit")
    return index, failures


def _slot_matches(entry: Mapping[str, Any], slot: CampaignSlot) -> bool:
    return entry["target_id"] == slot.target_id and entry["slot"] == slot.slot


def _observation_for(
    entries: Sequence[Mapping[str, Any]], target_id: str, slot_label: str
) -> datetime.datetime | None:
    for entry in entries:
        if (
            entry["event_type"] == "SLOT_SUCCEEDED"
            and entry["target_id"] == target_id
            and entry["slot"] == slot_label
        ):
            return parse_utc(entry["detail"]["observed_at_utc"], "observed_at_utc")
    return None


def validate_campaign_entries(
    entries: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    _verify_upstream()
    if isinstance(entries, (str, bytes, bytearray)) or not isinstance(entries, Sequence):
        raise _error("campaign entries must be a sequence")
    normalized = tuple(_freeze(_validate_entry_shape(entry)) for entry in entries)
    plan = campaign_slots()
    expected_slot_index = 0
    failed_attempts_for_current = 0
    terminal_reason: str | None = None
    previous_hash = ZERO_SHA256
    previous_recorded: datetime.datetime | None = None
    previous_request_started: datetime.datetime | None = None
    successes: dict[tuple[str, str], Mapping[str, Any]] = {}

    for offset, entry in enumerate(normalized, start=1):
        if terminal_reason is not None:
            raise _error("campaign evidence continues after terminal blocker")
        if entry["sequence"] != offset:
            raise _error("campaign global sequence has a gap or duplicate")
        if entry["previous_entry_sha256"] != previous_hash:
            raise _error("campaign hash chain is broken")
        if expected_slot_index >= len(plan):
            raise _error("campaign evidence continues after all slots succeeded")
        slot = plan[expected_slot_index]
        if not _slot_matches(entry, slot):
            raise _error("campaign evidence violates frozen pass order")
        recorded = parse_utc(entry["recorded_at_utc"], "recorded_at_utc")
        if previous_recorded is not None and recorded < previous_recorded:
            raise _error("campaign recorded timestamps move backwards")
        previous_recorded = recorded

        event_type = entry["event_type"]
        if event_type != "SLOT_BLOCKED":
            request_started = parse_utc(
                entry["attempt_started_at_utc"], "attempt_started_at_utc"
            )
            if previous_request_started is not None:
                separation = (request_started - previous_request_started).total_seconds()
                if separation < MINIMUM_INTER_REQUEST_SECONDS:
                    raise _error(
                        "campaign request starts violate frozen inter-request separation"
                    )
            if failed_attempts_for_current:
                previous_entry = normalized[offset - 2]
                if previous_entry["event_type"] != "ATTEMPT_FAILED":
                    raise _error("campaign retry does not follow a failed attempt")
                failed_attempt = previous_entry["attempt"]
                retry_anchor = parse_utc(
                    previous_entry["recorded_at_utc"], "retry recorded_at_utc"
                )
                retry_delay = RETRY_DELAYS_SECONDS[failed_attempt - 1]
                if request_started < retry_anchor + datetime.timedelta(seconds=retry_delay):
                    raise _error("campaign retry violates frozen durable retry delay")
            if slot.slot == "B":
                first_entry = successes.get((slot.target_id, "A"))
                if first_entry is None:
                    raise _error("slot B request has no slot A success evidence")
                first = parse_utc(
                    first_entry["detail"]["observed_at_utc"], "slot A observed_at"
                )
                pair_elapsed = (request_started - first).total_seconds()
                if not (
                    MINIMUM_PAIR_SEPARATION_SECONDS
                    <= pair_elapsed
                    <= MAXIMUM_PAIR_SEPARATION_SECONDS
                ):
                    raise _error("slot B request start violates frozen pair window")
            previous_request_started = request_started

        if event_type == "ATTEMPT_FAILED":
            expected_attempt = failed_attempts_for_current + 1
            if entry["attempt"] != expected_attempt:
                raise _error("failed attempt number is not contiguous for current slot")
            failed_attempts_for_current += 1
            if failed_attempts_for_current == MAXIMUM_ATTEMPTS_PER_SLOT:
                terminal_reason = "ATTEMPTS_EXHAUSTED"
        elif event_type == "SLOT_BLOCKED":
            terminal_reason = entry["detail"]["error_kind"]
        else:
            expected_attempt = failed_attempts_for_current + 1
            if entry["attempt"] != expected_attempt:
                raise _error("successful attempt is not contiguous for current slot")
            observed = parse_utc(entry["detail"]["observed_at_utc"], "observed_at_utc")
            if slot.slot == "B":
                first_entry = successes.get((slot.target_id, "A"))
                if first_entry is None:
                    raise _error("slot B success has no slot A success evidence")
                first = parse_utc(
                    first_entry["detail"]["observed_at_utc"], "slot A observed_at"
                )
                separation = (observed - first).total_seconds()
                if not (
                    MINIMUM_PAIR_SEPARATION_SECONDS
                    <= separation
                    <= MAXIMUM_PAIR_SEPARATION_SECONDS
                ):
                    raise _error("successful A/B observations violate frozen pair window")
            key = (slot.target_id, slot.slot)
            if key in successes:
                raise _error("campaign slot success is duplicated")
            successes[key] = entry
            expected_slot_index += 1
            failed_attempts_for_current = 0
        previous_hash = entry["entry_sha256"]
    return normalized


def campaign_progress(entries: Sequence[Mapping[str, Any]]) -> CampaignProgress:
    normalized = validate_campaign_entries(entries)
    plan = campaign_slots()
    completed = sum(
        1 for entry in normalized if entry["event_type"] == "SLOT_SUCCEEDED"
    )
    if completed > len(plan):
        raise _error("completed slot count exceeds campaign size")
    blocked = False
    block_reason: str | None = None
    current_failures = 0
    for entry in reversed(normalized):
        if entry["event_type"] == "SLOT_BLOCKED":
            blocked = True
            block_reason = entry["detail"]["error_kind"]
            break
        if entry["event_type"] == "ATTEMPT_FAILED":
            current_failures += 1
            if current_failures == MAXIMUM_ATTEMPTS_PER_SLOT:
                blocked = True
                block_reason = "ATTEMPTS_EXHAUSTED"
            continue
        break
    next_slot = None if completed == len(plan) else plan[completed]
    next_attempt = None if blocked or next_slot is None else current_failures + 1
    return CampaignProgress(
        completed_slots=completed,
        total_slots=len(plan),
        next_slot=next_slot,
        next_attempt=next_attempt,
        blocked=blocked,
        block_reason=block_reason,
    )


def _previous_hash(entries: Sequence[Mapping[str, Any]]) -> str:
    if not entries:
        return ZERO_SHA256
    return validate_sha256(entries[-1]["entry_sha256"], "entry_sha256")


def _require_current(
    entries: Sequence[Mapping[str, Any]], slot: CampaignSlot, attempt: int | None
) -> tuple[Mapping[str, Any], ...]:
    normalized = validate_campaign_entries(entries)
    progress = campaign_progress(normalized)
    if progress.complete:
        raise _error("campaign is already complete")
    if progress.blocked:
        raise _error("campaign is blocked")
    if progress.next_slot != slot:
        raise _error("entry does not target exact next campaign slot")
    if attempt is not None and progress.next_attempt != attempt:
        raise _error("entry attempt does not match exact next attempt")
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
) -> Mapping[str, Any]:
    normalized = _require_current(entries, slot, attempt)
    detail = {
        "error_kind": validate_error_kind(error_kind),
        "error_message": normalize_error_message(error_message),
    }
    entry = _seal(
        _entry_base(
            sequence=len(normalized) + 1,
            previous_entry_sha256=_previous_hash(normalized),
            event_type="ATTEMPT_FAILED",
            slot=slot,
            attempt=attempt,
            attempt_started_at=attempt_started_at,
            recorded_at=recorded_at,
            detail=detail,
        )
    )
    validate_campaign_entries((*normalized, entry))
    return entry


def build_slot_succeeded_entry(
    entries: Sequence[Mapping[str, Any]],
    *,
    slot: CampaignSlot,
    attempt: int,
    attempt_started_at: datetime.datetime,
    recorded_at: datetime.datetime,
    manifest_sha256: str,
    raw_sha256: str,
    raw_size: int,
    observed_at: datetime.datetime,
) -> Mapping[str, Any]:
    normalized = _require_current(entries, slot, attempt)
    observed = _utc(observed_at, "observed_at")
    if slot.slot == "B":
        first = _observation_for(normalized, slot.target_id, "A")
        if first is None:
            raise _error("slot B cannot succeed without slot A")
        separation = (observed - first).total_seconds()
        if separation < MINIMUM_PAIR_SEPARATION_SECONDS:
            raise PR69PrimaryTimeBasisEvidencePairWindowError(
                "PAIR_OBSERVATION_TOO_EARLY",
                "slot B observation is earlier than frozen 300-second separation",
            )
        if separation > MAXIMUM_PAIR_SEPARATION_SECONDS:
            raise PR69PrimaryTimeBasisEvidencePairWindowError(
                "PAIR_OBSERVATION_TOO_LATE",
                "slot B observation exceeds frozen 3600-second separation",
            )
    if type(raw_size) is not int or not 0 < raw_size <= MAX_RESPONSE_BYTES:
        raise _error("raw_size must be within frozen response bound")
    detail = {
        "manifest_sha256": validate_sha256(manifest_sha256, "manifest_sha256"),
        "raw_sha256": validate_sha256(raw_sha256, "raw_sha256"),
        "raw_size": raw_size,
        "observed_at_utc": serialize_utc(observed),
    }
    entry = _seal(
        _entry_base(
            sequence=len(normalized) + 1,
            previous_entry_sha256=_previous_hash(normalized),
            event_type="SLOT_SUCCEEDED",
            slot=slot,
            attempt=attempt,
            attempt_started_at=attempt_started_at,
            recorded_at=recorded_at,
            detail=detail,
        )
    )
    validate_campaign_entries((*normalized, entry))
    return entry


def build_slot_blocked_entry(
    entries: Sequence[Mapping[str, Any]],
    *,
    slot: CampaignSlot,
    recorded_at: datetime.datetime,
    error_kind: str,
    error_message: str,
) -> Mapping[str, Any]:
    normalized = _require_current(entries, slot, None)
    detail = {
        "error_kind": validate_error_kind(error_kind),
        "error_message": normalize_error_message(error_message),
    }
    entry = _seal(
        _entry_base(
            sequence=len(normalized) + 1,
            previous_entry_sha256=_previous_hash(normalized),
            event_type="SLOT_BLOCKED",
            slot=slot,
            attempt=0,
            attempt_started_at=None,
            recorded_at=recorded_at,
            detail=detail,
        )
    )
    validate_campaign_entries((*normalized, entry))
    return entry


def seconds_until_inter_request_eligible(
    entries: Sequence[Mapping[str, Any]], now: datetime.datetime
) -> float:
    normalized = validate_campaign_entries(entries)
    current = _utc(now, "now")
    latest: datetime.datetime | None = None
    for entry in reversed(normalized):
        raw = entry["attempt_started_at_utc"]
        if raw is not None:
            latest = parse_utc(raw, "attempt_started_at_utc")
            break
    if latest is None:
        return 0.0
    elapsed = (current - latest).total_seconds()
    if elapsed < 0:
        raise _error("runner clock precedes latest recorded request start")
    return max(0.0, MINIMUM_INTER_REQUEST_SECONDS - elapsed)


def seconds_until_retry_eligible(
    entries: Sequence[Mapping[str, Any]], now: datetime.datetime
) -> float:
    normalized = validate_campaign_entries(entries)
    if not normalized or normalized[-1]["event_type"] != "ATTEMPT_FAILED":
        return 0.0
    progress = campaign_progress(normalized)
    if progress.blocked:
        raise _error("campaign is blocked by attempt exhaustion")
    latest = normalized[-1]
    attempt = latest["attempt"]
    current = _utc(now, "now")
    recorded = parse_utc(latest["recorded_at_utc"], "recorded_at_utc")
    elapsed = (current - recorded).total_seconds()
    if elapsed < 0:
        raise _error("runner clock precedes latest failed attempt record")
    return max(0.0, float(RETRY_DELAYS_SECONDS[attempt - 1]) - elapsed)


def seconds_until_pair_eligible(
    entries: Sequence[Mapping[str, Any]], now: datetime.datetime
) -> float:
    normalized = validate_campaign_entries(entries)
    progress = campaign_progress(normalized)
    if progress.complete:
        return 0.0
    if progress.blocked or progress.next_slot is None:
        raise _error("campaign is blocked")
    slot = progress.next_slot
    if slot.slot == "A":
        return 0.0
    first = _observation_for(normalized, slot.target_id, "A")
    if first is None:
        raise _error("slot B cannot proceed without slot A observation")
    current = _utc(now, "now")
    elapsed = (current - first).total_seconds()
    if elapsed < 0:
        raise PR69PrimaryTimeBasisEvidencePairWindowError(
            "RUNNER_CLOCK_PRECEDES_SLOT_A",
            "runner clock precedes slot A observation",
        )
    if elapsed > MAXIMUM_PAIR_SEPARATION_SECONDS:
        raise PR69PrimaryTimeBasisEvidencePairWindowError(
            "PAIR_WINDOW_EXPIRED_BEFORE_REQUEST",
            "slot B can no longer satisfy frozen 3600-second pair window",
        )
    return max(0.0, MINIMUM_PAIR_SEPARATION_SECONDS - elapsed)


def seconds_until_next_request_eligible(
    entries: Sequence[Mapping[str, Any]], now: datetime.datetime
) -> float:
    return max(
        seconds_until_inter_request_eligible(entries, now),
        seconds_until_retry_eligible(entries, now),
        seconds_until_pair_eligible(entries, now),
    )


def runner_descriptor() -> Mapping[str, Any]:
    _verify_upstream()
    return _freeze(
        {
            "schema_version": SCHEMA_VERSION,
            "runner_id": RUNNER_ID,
            "runner_scope": RUNNER_SCOPE,
            "runner_state": RUNNER_STATE,
            "repository_main_sha": REPOSITORY_MAIN_SHA,
            "pr124_protocol_blob_sha": PR124_PROTOCOL_BLOB_SHA,
            "pr124_protocol_sha256": PR124_PROTOCOL_SHA256,
            "pr124_protocol_size": PR124_PROTOCOL_SIZE,
            "campaign_root": CAPTURE_ROOT_RELATIVE,
            "required_successful_capture_count": REQUIRED_SUCCESSFUL_CAPTURE_COUNT,
            "campaign_runner_implemented": True,
            "network_acquisition_performed": False,
            "semantic_extraction_performed": False,
            "historical_effective_scope_qualified": False,
            "pr69_source_local_time_basis_resolved": False,
            "pr80_constructor_input_authorized": False,
            "model_training_authorized": False,
            "probability_inference_authorized": False,
            "pricing_authorized": False,
            "selection_authorized": False,
            "production_approval_authorized": False,
            "bet_authorized": False,
            "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        }
    )
