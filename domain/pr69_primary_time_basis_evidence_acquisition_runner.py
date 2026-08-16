"""Deterministic runner contract for PR69 primary time-basis evidence acquisition.

PR #125 implements orchestration and evidence validation for the exact PR #124
protocol. Importing this module performs no network access. Live transport exists only
in the thin script layer and requires an explicit execution acknowledgement.
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
MAX_ERROR_MESSAGE_CHARS = 768
NEXT_REQUIRED_BOUNDARY = "EXECUTE_REVIEWED_PR69_PRIMARY_TIME_BASIS_EVIDENCE_ACQUISITION_CAMPAIGN"

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
_SUCCESS_KEYS = frozenset({
    "schema_version", "runner_id", "sequence", "previous_entry_sha256",
    "event_type", "target_id", "slot", "attempt", "attempt_started_at_utc",
    "recorded_at_utc", "manifest_sha256", "raw_sha256", "raw_size",
    "observed_at_utc", "entry_sha256",
})
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
        return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                           separators=(",", ":")) + "\n").encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("runner evidence serialization failed") from exc


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def serialize_utc(value: datetime.datetime) -> str:
    if not isinstance(value, datetime.datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise _error("timestamp must be timezone-aware")
    value = value.astimezone(datetime.timezone.utc)
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


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


def _sha(value: Any, label: str) -> str:
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
        exact = pr124.canonical_pr69_primary_time_basis_evidence_acquisition_protocol_bytes(protocol)
    except Exception as exc:
        raise _error("PR124 protocol no longer revalidates") from exc
    if hashlib.sha256(exact).hexdigest() != PR124_PROTOCOL_SHA256 or len(exact) != PR124_PROTOCOL_SIZE:
        raise _error("PR124 canonical protocol bytes changed")
    if protocol.next_required_boundary != (
        "IMPLEMENT_REVIEWED_PR69_PRIMARY_TIME_BASIS_EVIDENCE_ACQUISITION_RUNNER"
    ):
        raise _error("PR124 runner boundary changed")
    request = dict(protocol.request_identity)
    expected_request = {
        "method": "GET", "scheme": "https", "host": "www.football-data.co.uk", "port": 443,
        "request_headers": REQUEST_HEADERS, "redirects_authorized": False,
        "cookies_authorized": False, "browser_impersonation_authorized": False,
        "proxy_evasion_authorized": False, "tls_verification_required": True,
    }
    if request != expected_request:
        raise _error("PR124 request identity changed")
    schedule = dict(protocol.capture_schedule)
    expected_schedule = {
        "target_count": TARGET_COUNT, "capture_slots_per_target": 2, "slot_labels": SLOT_LABELS,
        "pass_order": "ALL_TARGETS_SLOT_A_IN_FROZEN_ORDER_THEN_ALL_TARGETS_SLOT_B_IN_FROZEN_ORDER",
        "minimum_same_target_pair_separation_seconds": MINIMUM_PAIR_SEPARATION_SECONDS,
        "maximum_same_target_pair_separation_seconds": MAXIMUM_PAIR_SEPARATION_SECONDS,
        "minimum_inter_request_seconds": MINIMUM_INTER_REQUEST_SECONDS,
        "maximum_attempts_per_slot": MAXIMUM_ATTEMPTS_PER_SLOT,
        "retry_delays_seconds": RETRY_DELAYS_SECONDS,
        "required_successful_capture_count": REQUIRED_SUCCESSFUL_CAPTURE_COUNT,
        "failed_attempts_count_as_success": False,
    }
    if schedule != expected_schedule:
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
    if protocol.network_acquisition_performed is not False or protocol.campaign_runner_implemented is not False:
        raise _error("PR124 pre-execution state changed")
    if protocol.evidence_records_captured != 0:
        raise _error("PR124 evidence count changed")
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
        if type(self.path) is not str or not self.path.startswith("/") or "?" in self.path or "#" in self.path:
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
    blocked: bool
    block_reason: str | None

    @property
    def complete(self) -> bool:
        return self.completed_slots == self.total_slots and not self.blocked


def campaign_slots() -> tuple[CampaignSlot, ...]:
    protocol = _verify_upstream()
    if len(protocol.targets) != TARGET_COUNT:
        raise _error("PR124 target count changed")
    slots: list[CampaignSlot] = []
    ordinal = 0
    for slot_label in SLOT_LABELS:
        for target in protocol.targets:
            ordinal += 1
            slots.append(CampaignSlot(
                ordinal=ordinal, target_id=target.target_id, path=target.path,
                content_type_prefix=target.content_type_prefix, slot=slot_label,
            ))
    if len(slots) != REQUIRED_SUCCESSFUL_CAPTURE_COUNT:
        raise _error("campaign plan no longer has eight slots")
    return tuple(slots)


def manifest_sha256(manifest: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(dict(manifest))).hexdigest()


def _pairs(value: Any, label: str) -> list[list[str]]:
    if not isinstance(value, list):
        raise _error(f"{label} must be a JSON list")
    checked: list[list[str]] = []
    for pair in value:
        if not isinstance(pair, list) or len(pair) != 2 or not all(type(item) is str for item in pair):
            raise _error(f"{label} must contain exact two-text-item lists")
        checked.append([pair[0], pair[1]])
    return checked


def validate_manifest(value: Any, expected_slot: CampaignSlot | None = None) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _error("manifest must be an object")
    manifest = dict(value)
    if set(manifest) != _MANIFEST_KEYS:
        raise _error("manifest keys changed")
    if manifest["schema_version"] != SCHEMA_VERSION or manifest["runner_id"] != RUNNER_ID:
        raise _error("manifest runner identity changed")
    if manifest["protocol_sha256"] != PR124_PROTOCOL_SHA256:
        raise _error("manifest protocol identity changed")
    if type(manifest["target_id"]) is not str or _TARGET_ID_RE.fullmatch(manifest["target_id"]) is None:
        raise _error("manifest target identity is invalid")
    if manifest["slot"] not in SLOT_LABELS:
        raise _error("manifest slot is invalid")
    if type(manifest["attempt"]) is not int or not 1 <= manifest["attempt"] <= MAXIMUM_ATTEMPTS_PER_SLOT:
        raise _error("manifest attempt is invalid")
    if manifest["request_method"] != "GET" or manifest["requested_url"] != manifest["final_url"]:
        raise _error("manifest request/final URL is invalid")
    if not manifest["requested_url"].startswith(PRIMARY_ORIGIN + "/"):
        raise _error("manifest URL is outside the primary origin")
    if _pairs(manifest["request_headers"], "request_headers") != [list(item) for item in REQUEST_HEADERS]:
        raise _error("manifest request headers changed")
    if manifest["redirect_chain"] != [] or manifest["tls_verified"] is not True or manifest["http_status"] != 200:
        raise _error("manifest transport state is not admissible")
    response_headers = _pairs(manifest["response_headers"], "response_headers")
    if any(name not in SELECTED_RESPONSE_HEADERS for name, _ in response_headers):
        raise _error("manifest contains an unreviewed response header")
    if manifest["raw_filename"] != RAW_BODY_FILENAME:
        raise _error("manifest raw filename changed")
    _sha(manifest["raw_sha256"], "manifest raw sha256")
    if type(manifest["raw_size"]) is not int or not 0 < manifest["raw_size"] <= MAX_RESPONSE_BYTES:
        raise _error("manifest raw size is invalid")
    started = parse_utc(manifest["request_started_at_utc"], "request_started_at_utc")
    completed = parse_utc(manifest["response_completed_at_utc"], "response_completed_at_utc")
    observed = parse_utc(manifest["observed_at_utc"], "observed_at_utc")
    if not started <= completed <= observed:
        raise _error("manifest timestamps are out of order")
    if expected_slot is not None:
        if (manifest["target_id"], manifest["slot"], manifest["requested_url"]) != (
            expected_slot.target_id, expected_slot.slot, expected_slot.requested_url
        ):
            raise _error("manifest does not match planned slot")
        content_types = [v for n, v in response_headers if n == "content-type"]
        if len(content_types) != 1:
            raise _error("manifest must preserve exactly one Content-Type")
        media_type = content_types[0].split(";", 1)[0].strip().lower()
        if not media_type.startswith(expected_slot.content_type_prefix.lower()):
            raise _error("manifest Content-Type does not match target")
    return types.MappingProxyType(manifest)


def build_success_entry(*, sequence: int, previous_entry_sha256: str,
                        slot: CampaignSlot, manifest: Mapping[str, Any],
                        manifest_hash: str, recorded_at: datetime.datetime) -> Mapping[str, Any]:
    checked = validate_manifest(manifest, slot)
    if type(sequence) is not int or sequence < 1:
        raise _error("sequence must be a positive integer")
    previous = _sha(previous_entry_sha256, "previous entry sha256")
    body = {
        "schema_version": SCHEMA_VERSION, "runner_id": RUNNER_ID, "sequence": sequence,
        "previous_entry_sha256": previous, "event_type": "SLOT_SUCCEEDED",
        "target_id": slot.target_id, "slot": slot.slot, "attempt": checked["attempt"],
        "attempt_started_at_utc": checked["request_started_at_utc"],
        "recorded_at_utc": serialize_utc(recorded_at),
        "manifest_sha256": _sha(manifest_hash, "manifest sha256"),
        "raw_sha256": checked["raw_sha256"], "raw_size": checked["raw_size"],
        "observed_at_utc": checked["observed_at_utc"],
    }
    body["entry_sha256"] = hashlib.sha256(canonical_bytes(body)).hexdigest()
    return types.MappingProxyType(body)


def validate_success_entries(entries: Sequence[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    plan = campaign_slots()
    if len(entries) > len(plan):
        raise _error("campaign index has too many successes")
    previous = "0" * 64
    checked_entries: list[Mapping[str, Any]] = []
    for index, raw in enumerate(entries):
        if not isinstance(raw, Mapping) or set(raw) != _SUCCESS_KEYS:
            raise _error("campaign success entry keys changed")
        entry = dict(raw)
        if (entry["schema_version"], entry["runner_id"], entry["event_type"]) != (
            SCHEMA_VERSION, RUNNER_ID, "SLOT_SUCCEEDED"
        ):
            raise _error("campaign success entry identity changed")
        slot = plan[index]
        if (entry["sequence"], entry["target_id"], entry["slot"]) != (
            index + 1, slot.target_id, slot.slot
        ):
            raise _error("campaign success order changed")
        if entry["previous_entry_sha256"] != previous:
            raise _error("campaign success hash chain is broken")
        supplied = _sha(entry["entry_sha256"], "entry sha256")
        without = dict(entry)
        without.pop("entry_sha256")
        if hashlib.sha256(canonical_bytes(without)).hexdigest() != supplied:
            raise _error("campaign success entry hash mismatch")
        if type(entry["attempt"]) is not int or not 1 <= entry["attempt"] <= MAXIMUM_ATTEMPTS_PER_SLOT:
            raise _error("campaign attempt is invalid")
        parse_utc(entry["attempt_started_at_utc"], "attempt_started_at_utc")
        parse_utc(entry["recorded_at_utc"], "recorded_at_utc")
        parse_utc(entry["observed_at_utc"], "observed_at_utc")
        _sha(entry["manifest_sha256"], "manifest sha256")
        _sha(entry["raw_sha256"], "raw sha256")
        if type(entry["raw_size"]) is not int or not 0 < entry["raw_size"] <= MAX_RESPONSE_BYTES:
            raise _error("campaign raw size is invalid")
        previous = supplied
        checked_entries.append(types.MappingProxyType(entry))
    return tuple(checked_entries)


def campaign_progress(entries: Sequence[Mapping[str, Any]], *, blocked: bool = False,
                      block_reason: str | None = None) -> CampaignProgress:
    checked = validate_success_entries(entries)
    plan = campaign_slots()
    if blocked and (type(block_reason) is not str or not block_reason):
        raise _error("blocked progress requires a reason")
    return CampaignProgress(
        completed_slots=len(checked), total_slots=len(plan),
        next_slot=None if len(checked) == len(plan) else plan[len(checked)],
        blocked=blocked, block_reason=block_reason,
    )


def slot_a_observed_at(entries: Sequence[Mapping[str, Any]], target_id: str) -> datetime.datetime | None:
    for entry in validate_success_entries(entries):
        if entry["target_id"] == target_id and entry["slot"] == "A":
            return parse_utc(entry["observed_at_utc"], "slot A observed_at")
    return None


def pair_wait_seconds(entries: Sequence[Mapping[str, Any]], slot: CampaignSlot,
                      now: datetime.datetime) -> float:
    if slot.slot != "B":
        return 0.0
    a_time = slot_a_observed_at(entries, slot.target_id)
    if a_time is None:
        raise PR69PrimaryTimeBasisEvidencePairWindowError(
            "PAIR_A_MISSING", "slot B cannot run before slot A"
        )
    if not isinstance(now, datetime.datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise _error("pair-window clock must be timezone-aware")
    current = now.astimezone(datetime.timezone.utc)
    elapsed = (current - a_time).total_seconds()
    if elapsed > MAXIMUM_PAIR_SEPARATION_SECONDS:
        raise PR69PrimaryTimeBasisEvidencePairWindowError(
            "PAIR_WINDOW_EXPIRED", "slot B pair window expired"
        )
    return max(0.0, MINIMUM_PAIR_SEPARATION_SECONDS - elapsed)


def runner_descriptor() -> Mapping[str, Any]:
    _verify_upstream()
    return types.MappingProxyType({
        "schema_version": SCHEMA_VERSION, "runner_id": RUNNER_ID,
        "runner_scope": RUNNER_SCOPE, "runner_state": RUNNER_STATE,
        "repository_main_sha": REPOSITORY_MAIN_SHA,
        "pr124_protocol_blob_sha": PR124_PROTOCOL_BLOB_SHA,
        "pr124_protocol_sha256": PR124_PROTOCOL_SHA256,
        "pr124_protocol_size": PR124_PROTOCOL_SIZE,
        "campaign_root": CAPTURE_ROOT_RELATIVE,
        "required_successful_capture_count": REQUIRED_SUCCESSFUL_CAPTURE_COUNT,
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
    })
