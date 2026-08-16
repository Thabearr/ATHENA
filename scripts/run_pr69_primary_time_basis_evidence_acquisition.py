"""Live runner for the reviewed PR69 primary time-basis evidence campaign.

Import is inert. Network access requires ``execute_live_network=True`` or the CLI
``--execute-reviewed-protocol`` acknowledgement. The runner is intentionally narrow:
exactly four football-data.co.uk targets, two slots each, no redirects/cookies/browser
impersonation/proxies, and no semantic interpretation.
"""
from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime
import hashlib
import http.client
import json
import os
import ssl
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from domain import pr69_primary_time_basis_evidence_acquisition_runner as contract

UTC = datetime.timezone.utc
NETWORK_TIMEOUT_SECONDS = 30.0
SELECTED_RESPONSE_HEADERS = frozenset({
    "cache-control", "content-encoding", "content-length", "content-type", "date",
    "etag", "last-modified", "location", "server",
})
REQUEST_HEADERS = (
    ("Accept", "text/plain,text/html;q=0.9,*/*;q=0.1"),
    ("Accept-Encoding", "identity"),
    ("User-Agent", "ATHENA/1.0"),
)


class PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(RuntimeError):
    """Raised when live acquisition cannot proceed safely."""


class PrimaryEvidenceRequestError(PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError):
    """Retryable request/response failure before durable success publication."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclasses.dataclass(frozen=True)
class FetchResult:
    slot: contract.CampaignSlot
    attempt: int
    raw_body: bytes
    manifest: Mapping[str, Any]


def _now() -> datetime.datetime:
    return datetime.datetime.now(tz=UTC)


def _bounded_error(exc: BaseException) -> str:
    return contract.normalize_error_message(f"{type(exc).__name__}: {exc}")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(
                f"duplicate JSON key in evidence: {key}"
            )
        result[key] = value
    return result


def _decode_json_line(raw: bytes, label: str) -> Mapping[str, Any]:
    if not raw or len(raw) > contract.MAX_ENTRY_BYTES or not raw.endswith(b"\n"):
        raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(
            f"{label} is not one bounded canonical JSON line"
        )
    try:
        text = raw.decode("utf-8")
        value = json.loads(text, object_pairs_hook=_strict_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(
            f"{label} is malformed"
        ) from exc
    if not isinstance(value, Mapping):
        raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(
            f"{label} must contain a JSON object"
        )
    if contract.canonical_bytes(dict(value)) != raw:
        raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(
            f"{label} is not canonical JSON"
        )
    return value


def _sync_directory(path: Path) -> None:
    if os.name == "nt":
        try:
            import ctypes
            import ctypes.wintypes
        except (ImportError, AttributeError) as exc:
            raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(
                f"cannot prove directory durability on Windows: {path}"
            ) from exc
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel32.CreateFileW
        create.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.wintypes.DWORD,
                           ctypes.wintypes.DWORD, ctypes.c_void_p, ctypes.wintypes.DWORD,
                           ctypes.wintypes.DWORD, ctypes.wintypes.HANDLE]
        create.restype = ctypes.wintypes.HANDLE
        handle = create(str(path), 0xC0000000, 0x00000007, None, 3, 0x02000000, None)
        invalid = {None, 0, -1, ctypes.c_void_p(-1).value}
        if handle in invalid:
            raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(
                f"could not open directory for durable synchronization: {path}"
            )
        failures: list[str] = []
        try:
            if not kernel32.FlushFileBuffers(handle):
                failures.append("FlushFileBuffers failed")
        finally:
            if not kernel32.CloseHandle(handle):
                failures.append("CloseHandle failed")
        if failures:
            raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(
                f"could not durably synchronize directory {path}: {'; '.join(failures)}"
            )
        return
    if os.name != "posix":
        raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(
            f"unsupported durability platform: {os.name}"
        )
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(str(path), flags)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(
            f"could not durably synchronize directory: {path}"
        ) from exc


def _ensure_directory_tree(target: Path, boundary: Path) -> None:
    boundary = boundary.resolve(strict=True)
    try:
        relative = target.relative_to(boundary)
    except ValueError as exc:
        raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(
            "campaign root is outside repository"
        ) from exc
    current = boundary
    _sync_directory(current)
    for component in relative.parts:
        child = current / component
        if child.exists() or child.is_symlink():
            if child.is_symlink() or not child.is_dir():
                raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(
                    f"campaign path component is not a regular directory: {child}"
                )
        else:
            child.mkdir()
            _sync_directory(current)
        _sync_directory(child)
        current = child


def _root(repository_root: Path) -> Path:
    root = Path(repository_root).resolve(strict=True)
    if not root.is_dir():
        raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(
            "repository root must be a directory"
        )
    campaign = root / contract.CAPTURE_ROOT_RELATIVE
    _ensure_directory_tree(campaign, root)
    return campaign


def _write_exclusive(path: Path, content: bytes) -> None:
    try:
        handle = path.open("xb")
    except FileExistsError as exc:
        raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(
            f"refusing to overwrite evidence file: {path}"
        ) from exc
    try:
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        _sync_directory(path.parent)
    except Exception:
        raise


def _append_durable(path: Path, content: bytes) -> None:
    if not content.endswith(b"\n") or len(content) > contract.MAX_ENTRY_BYTES:
        raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(
            "journal entry is not a bounded JSON line"
        )
    with path.open("ab") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    _sync_directory(path.parent)


@contextlib.contextmanager
def _campaign_lock(root: Path, clock: Callable[[], datetime.datetime]):
    path = root / contract.RUNNER_LOCK_FILENAME
    payload = contract.canonical_bytes({
        "runner_id": contract.RUNNER_ID,
        "created_at_utc": contract.serialize_utc(clock()),
        "pid": os.getpid(),
    })
    _write_exclusive(path, payload)
    try:
        yield
    finally:
        try:
            path.unlink()
            _sync_directory(root)
        except FileNotFoundError:
            raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(
                "runner lock disappeared during execution"
            )


def _read_jsonl(path: Path) -> tuple[Mapping[str, Any], ...]:
    if not path.exists():
        return ()
    if path.is_symlink() or not path.is_file():
        raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(
            f"evidence journal is not a regular file: {path}"
        )
    raw = path.read_bytes()
    if len(raw) > 4 * 1024 * 1024:
        raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(
            f"evidence journal is unexpectedly large: {path.name}"
        )
    if raw and not raw.endswith(b"\n"):
        raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(
            f"evidence journal has an unterminated record: {path.name}"
        )
    return tuple(_decode_json_line(line + b"\n", f"{path.name} record")
                 for line in raw.splitlines() if line)


def load_success_entries(*, repository_root: Path) -> tuple[Mapping[str, Any], ...]:
    root = _root(repository_root)
    entries = _read_jsonl(root / contract.CAMPAIGN_INDEX_FILENAME)
    return contract.validate_success_entries(entries)


def load_failure_entries(*, repository_root: Path) -> tuple[Mapping[str, Any], ...]:
    root = _root(repository_root)
    return _read_jsonl(root / contract.FAILURE_JOURNAL_FILENAME)


def _slot_directory(root: Path, slot: contract.CampaignSlot) -> Path:
    return root / slot.target_id / slot.slot


def _load_manifest(path: Path, slot: contract.CampaignSlot) -> tuple[Mapping[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(
            "manifest is not a regular file"
        )
    raw = path.read_bytes()
    value = _decode_json_line(raw, "manifest")
    checked = contract.validate_manifest(value, slot)
    return checked, raw


def _verify_capture(root: Path, slot: contract.CampaignSlot) -> tuple[Mapping[str, Any], str]:
    directory = _slot_directory(root, slot)
    if directory.is_symlink() or not directory.is_dir():
        raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(
            f"capture directory is missing or invalid for {slot.target_id}/{slot.slot}"
        )
    raw_path = directory / contract.RAW_BODY_FILENAME
    manifest_path = directory / contract.MANIFEST_FILENAME
    if raw_path.is_symlink() or not raw_path.is_file():
        raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError("raw response is missing or invalid")
    manifest, manifest_raw = _load_manifest(manifest_path, slot)
    raw = raw_path.read_bytes()
    if len(raw) != manifest["raw_size"] or hashlib.sha256(raw).hexdigest() != manifest["raw_sha256"]:
        raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(
            "raw response no longer matches its manifest"
        )
    return manifest, hashlib.sha256(manifest_raw).hexdigest()


def _validate_index_against_captures(root: Path, entries: Sequence[Mapping[str, Any]]) -> None:
    plan = contract.campaign_slots()
    for index, entry in enumerate(contract.validate_success_entries(entries)):
        manifest, manifest_hash = _verify_capture(root, plan[index])
        if entry["manifest_sha256"] != manifest_hash or entry["raw_sha256"] != manifest["raw_sha256"] or entry["raw_size"] != manifest["raw_size"]:
            raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(
                "campaign index does not match durable capture evidence"
            )


def _append_success_from_capture(root: Path, slot: contract.CampaignSlot,
                                 entries: Sequence[Mapping[str, Any]],
                                 clock: Callable[[], datetime.datetime]) -> tuple[Mapping[str, Any], ...]:
    manifest, manifest_hash = _verify_capture(root, slot)
    previous = entries[-1]["entry_sha256"] if entries else "0" * 64
    entry = contract.build_success_entry(
        sequence=len(entries) + 1, previous_entry_sha256=previous, slot=slot,
        manifest=manifest, manifest_hash=manifest_hash, recorded_at=clock(),
    )
    _append_durable(root / contract.CAMPAIGN_INDEX_FILENAME, contract.canonical_bytes(dict(entry)))
    return contract.validate_success_entries(tuple(entries) + (entry,))


def _recover_completed_next_capture(root: Path, entries: Sequence[Mapping[str, Any]],
                                    clock: Callable[[], datetime.datetime]) -> tuple[Mapping[str, Any], ...]:
    plan = contract.campaign_slots()
    if len(entries) == len(plan):
        return tuple(entries)
    slot = plan[len(entries)]
    directory = _slot_directory(root, slot)
    if not directory.exists() and not directory.is_symlink():
        return tuple(entries)
    return _append_success_from_capture(root, slot, entries, clock)


def _failure_entry(*, slot: contract.CampaignSlot, attempt: int,
                   attempt_started_at: datetime.datetime, recorded_at: datetime.datetime,
                   kind: str, message: str) -> Mapping[str, Any]:
    contract._error_kind(kind)
    body = {
        "schema_version": contract.SCHEMA_VERSION, "runner_id": contract.RUNNER_ID,
        "event_type": "ATTEMPT_FAILED", "target_id": slot.target_id, "slot": slot.slot,
        "attempt": attempt, "attempt_started_at_utc": contract.serialize_utc(attempt_started_at),
        "recorded_at_utc": contract.serialize_utc(recorded_at), "error_kind": kind,
        "error_message": contract.normalize_error_message(message),
    }
    body["entry_sha256"] = hashlib.sha256(contract.canonical_bytes(body)).hexdigest()
    return body


def _journal_failure(root: Path, *, slot: contract.CampaignSlot, attempt: int,
                     attempt_started_at: datetime.datetime, recorded_at: datetime.datetime,
                     kind: str, message: str) -> None:
    entry = _failure_entry(slot=slot, attempt=attempt, attempt_started_at=attempt_started_at,
                           recorded_at=recorded_at, kind=kind, message=message)
    _append_durable(root / contract.FAILURE_JOURNAL_FILENAME, contract.canonical_bytes(dict(entry)))


def _all_attempt_starts(successes: Sequence[Mapping[str, Any]], failures: Sequence[Mapping[str, Any]]) -> list[datetime.datetime]:
    values: list[datetime.datetime] = []
    for entry in tuple(successes) + tuple(failures):
        raw = entry.get("attempt_started_at_utc")
        if type(raw) is str:
            values.append(contract.parse_utc(raw, "attempt_started_at_utc"))
    return values


def _wait_before_request(*, slot: contract.CampaignSlot, successes: Sequence[Mapping[str, Any]],
                         failures: Sequence[Mapping[str, Any]], clock: Callable[[], datetime.datetime],
                         sleeper: Callable[[float], None]) -> None:
    now = clock().astimezone(UTC)
    pair_wait = contract.pair_wait_seconds(successes, slot, now)
    starts = _all_attempt_starts(successes, failures)
    inter_wait = 0.0
    if starts:
        inter_wait = max(0.0, contract.MINIMUM_INTER_REQUEST_SECONDS - (now - max(starts)).total_seconds())
    wait = max(pair_wait, inter_wait)
    if wait > 0:
        sleeper(wait)
    if slot.slot == "B":
        # Recheck the upper bound immediately before the request.
        contract.pair_wait_seconds(successes, slot, clock().astimezone(UTC))


def fetch_primary_evidence(*, slot: contract.CampaignSlot, attempt: int,
                           request_started_at: datetime.datetime,
                           clock: Callable[[], datetime.datetime] = _now,
                           connection_factory: Callable[..., Any] | None = None) -> FetchResult:
    if type(attempt) is not int or not 1 <= attempt <= contract.MAXIMUM_ATTEMPTS_PER_SLOT:
        raise PrimaryEvidenceRequestError("INVALID_ATTEMPT", "attempt is outside frozen bounds")
    factory = connection_factory or http.client.HTTPSConnection
    connection = None
    try:
        context = ssl.create_default_context()
        try:
            connection = factory("www.football-data.co.uk", 443, timeout=NETWORK_TIMEOUT_SECONDS, context=context)
        except TypeError:
            connection = factory("www.football-data.co.uk", 443, NETWORK_TIMEOUT_SECONDS)
        connection.putrequest("GET", slot.path, skip_accept_encoding=True)
        for name, value in REQUEST_HEADERS:
            connection.putheader(name, value)
        connection.endheaders()
        response = connection.getresponse()
        status = int(response.status)
        headers = [(str(name).lower(), str(value)) for name, value in response.getheaders()
                   if str(name).lower() in SELECTED_RESPONSE_HEADERS]
        if status != 200:
            raise PrimaryEvidenceRequestError("HTTP_STATUS", f"unexpected HTTP status {status}")
        content_types = [value for name, value in headers if name == "content-type"]
        if len(content_types) != 1:
            raise PrimaryEvidenceRequestError("CONTENT_TYPE", "response must contain exactly one Content-Type")
        media_type = content_types[0].split(";", 1)[0].strip().lower()
        if not media_type.startswith(slot.content_type_prefix.lower()):
            raise PrimaryEvidenceRequestError("CONTENT_TYPE", f"unexpected Content-Type {content_types[0]!r}")
        encodings = [value.strip().lower() for name, value in headers if name == "content-encoding"]
        if any(value not in ("", "identity") for value in encodings):
            raise PrimaryEvidenceRequestError("CONTENT_ENCODING", "compressed response is not admissible")
        lengths = [value.strip() for name, value in headers if name == "content-length"]
        declared_length: int | None = None
        if lengths:
            if len(lengths) != 1 or not lengths[0].isdigit():
                raise PrimaryEvidenceRequestError("CONTENT_LENGTH", "invalid Content-Length")
            declared_length = int(lengths[0])
            if declared_length > contract.MAX_RESPONSE_BYTES:
                raise PrimaryEvidenceRequestError("BODY_TOO_LARGE", "declared response exceeds frozen limit")
        raw = response.read(contract.MAX_RESPONSE_BYTES + 1)
        if not raw:
            raise PrimaryEvidenceRequestError("EMPTY_BODY", "primary evidence response is empty")
        if len(raw) > contract.MAX_RESPONSE_BYTES:
            raise PrimaryEvidenceRequestError("BODY_TOO_LARGE", "response exceeds frozen limit")
        if declared_length is not None and declared_length != len(raw):
            raise PrimaryEvidenceRequestError("CONTENT_LENGTH", "Content-Length does not match exact body")
        completed_at = clock().astimezone(UTC)
        observed_at = clock().astimezone(UTC)
        raw_sha = hashlib.sha256(raw).hexdigest()
        manifest = {
            "schema_version": contract.SCHEMA_VERSION, "runner_id": contract.RUNNER_ID,
            "protocol_sha256": contract.PR124_PROTOCOL_SHA256, "target_id": slot.target_id,
            "slot": slot.slot, "attempt": attempt, "requested_url": slot.requested_url,
            "final_url": slot.requested_url, "request_method": "GET",
            "request_headers": [list(pair) for pair in REQUEST_HEADERS], "redirect_chain": [],
            "request_started_at_utc": contract.serialize_utc(request_started_at),
            "response_completed_at_utc": contract.serialize_utc(completed_at),
            "observed_at_utc": contract.serialize_utc(observed_at), "http_status": 200,
            "tls_verified": True, "response_headers": [list(pair) for pair in headers],
            "raw_filename": contract.RAW_BODY_FILENAME, "raw_sha256": raw_sha, "raw_size": len(raw),
        }
        checked = contract.validate_manifest(manifest, slot)
        return FetchResult(slot, attempt, raw, checked)
    except PrimaryEvidenceRequestError:
        raise
    except (OSError, ssl.SSLError, http.client.HTTPException, TimeoutError) as exc:
        raise PrimaryEvidenceRequestError("NETWORK_FAILURE", _bounded_error(exc)) from exc
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def write_capture(result: FetchResult, *, repository_root: Path) -> tuple[Mapping[str, Any], str]:
    if not isinstance(result, FetchResult):
        raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError("capture result has wrong type")
    root = _root(repository_root)
    target_dir = root / result.slot.target_id
    _ensure_directory_tree(target_dir, root)
    slot_dir = target_dir / result.slot.slot
    if slot_dir.exists() or slot_dir.is_symlink():
        raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(
            f"capture slot already exists and will not be overwritten: {result.slot.target_id}/{result.slot.slot}"
        )
    slot_dir.mkdir()
    _sync_directory(target_dir)
    _sync_directory(slot_dir)
    raw_path = slot_dir / contract.RAW_BODY_FILENAME
    manifest_path = slot_dir / contract.MANIFEST_FILENAME
    _write_exclusive(raw_path, result.raw_body)
    manifest_raw = contract.canonical_bytes(dict(result.manifest))
    _write_exclusive(manifest_path, manifest_raw)
    _sync_directory(slot_dir)
    return result.manifest, hashlib.sha256(manifest_raw).hexdigest()


def execute_next_campaign_slot(*, execute_live_network: bool, repository_root: Path,
                               fetcher: Callable[..., FetchResult] = fetch_primary_evidence,
                               clock: Callable[[], datetime.datetime] = _now,
                               sleeper: Callable[[float], None] = time.sleep) -> contract.CampaignProgress:
    if execute_live_network is not True:
        raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(
            "live acquisition requires exact True acknowledgement"
        )
    contract.runner_descriptor()
    root = _root(repository_root)
    with _campaign_lock(root, clock):
        successes = load_success_entries(repository_root=repository_root)
        _validate_index_against_captures(root, successes)
        successes = _recover_completed_next_capture(root, successes, clock)
        progress = contract.campaign_progress(successes)
        if progress.complete:
            return progress
        slot = progress.next_slot
        assert slot is not None
        failures = load_failure_entries(repository_root=repository_root)
        attempt = 1
        prior_same_slot = [entry for entry in failures if entry.get("target_id") == slot.target_id and entry.get("slot") == slot.slot]
        if prior_same_slot:
            attempts = [entry.get("attempt") for entry in prior_same_slot if type(entry.get("attempt")) is int]
            attempt = max(attempts or [0]) + 1
        if attempt > contract.MAXIMUM_ATTEMPTS_PER_SLOT:
            raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError("ATTEMPTS_EXHAUSTED")
        while attempt <= contract.MAXIMUM_ATTEMPTS_PER_SLOT:
            failures = load_failure_entries(repository_root=repository_root)
            _wait_before_request(slot=slot, successes=successes, failures=failures,
                                 clock=clock, sleeper=sleeper)
            started = clock().astimezone(UTC)
            try:
                result = fetcher(slot=slot, attempt=attempt, request_started_at=started, clock=clock)
            except PrimaryEvidenceRequestError as exc:
                _journal_failure(root, slot=slot, attempt=attempt, attempt_started_at=started,
                                 recorded_at=clock(), kind=exc.kind, message=str(exc))
                if attempt >= contract.MAXIMUM_ATTEMPTS_PER_SLOT:
                    raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError("ATTEMPTS_EXHAUSTED") from exc
                sleeper(float(contract.RETRY_DELAYS_SECONDS[attempt - 1]))
                attempt += 1
                continue
            if slot.slot == "B":
                a_time = contract.slot_a_observed_at(successes, slot.target_id)
                assert a_time is not None
                observed = contract.parse_utc(result.manifest["observed_at_utc"], "observed_at_utc")
                separation = (observed - a_time).total_seconds()
                if separation < contract.MINIMUM_PAIR_SEPARATION_SECONDS or separation > contract.MAXIMUM_PAIR_SEPARATION_SECONDS:
                    _journal_failure(root, slot=slot, attempt=attempt, attempt_started_at=started,
                                     recorded_at=clock(), kind="PAIR_WINDOW_VIOLATION",
                                     message=f"successful response observed outside frozen pair window: {separation:.6f}s")
                    raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(
                        "pair window violated during request"
                    )
            try:
                write_capture(result, repository_root=repository_root)
            except Exception as exc:
                _journal_failure(root, slot=slot, attempt=attempt, attempt_started_at=started,
                                 recorded_at=clock(), kind="DURABILITY_FAILURE", message=_bounded_error(exc))
                raise
            successes = _append_success_from_capture(root, slot, successes, clock)
            return contract.campaign_progress(successes)
        raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError("ATTEMPTS_EXHAUSTED")


def execute_campaign(*, execute_live_network: bool, repository_root: Path,
                     max_successful_slots: int | None = None,
                     fetcher: Callable[..., FetchResult] = fetch_primary_evidence,
                     clock: Callable[[], datetime.datetime] = _now,
                     sleeper: Callable[[float], None] = time.sleep) -> contract.CampaignProgress:
    if execute_live_network is not True:
        raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(
            "live acquisition requires exact True acknowledgement"
        )
    if max_successful_slots is not None and (type(max_successful_slots) is not int or max_successful_slots < 1):
        raise PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(
            "max_successful_slots must be a positive integer or None"
        )
    completed_before = len(load_success_entries(repository_root=repository_root))
    while True:
        progress = execute_next_campaign_slot(
            execute_live_network=True, repository_root=repository_root,
            fetcher=fetcher, clock=clock, sleeper=sleeper,
        )
        if progress.complete:
            return progress
        if max_successful_slots is not None and progress.completed_slots - completed_before >= max_successful_slots:
            return progress


def campaign_status(*, repository_root: Path) -> Mapping[str, Any]:
    contract.runner_descriptor()
    root = _root(repository_root)
    successes = load_success_entries(repository_root=repository_root)
    _validate_index_against_captures(root, successes)
    progress = contract.campaign_progress(successes)
    failures = load_failure_entries(repository_root=repository_root)
    pairs: list[dict[str, Any]] = []
    for target in (slot for slot in contract.campaign_slots() if slot.slot == "A"):
        a = contract.slot_a_observed_at(successes, target.target_id)
        b = next((contract.parse_utc(entry["observed_at_utc"], "observed_at_utc")
                  for entry in successes if entry["target_id"] == target.target_id and entry["slot"] == "B"), None)
        pairs.append({
            "target_id": target.target_id,
            "slot_a_observed_at_utc": None if a is None else contract.serialize_utc(a),
            "slot_b_observed_at_utc": None if b is None else contract.serialize_utc(b),
            "separation_seconds": None if a is None or b is None else (b - a).total_seconds(),
        })
    return {
        "runner_id": contract.RUNNER_ID, "runner_state": contract.RUNNER_STATE,
        "completed_slots": progress.completed_slots, "required_slots": progress.total_slots,
        "complete": progress.complete, "failure_attempts": len(failures), "pair_drift_table": pairs,
        "semantic_extraction_performed": False, "historical_effective_scope_qualified": False,
        "pr69_source_local_time_basis_resolved": False, "pr80_constructor_input_authorized": False,
        "model_training_authorized": False, "probability_inference_authorized": False,
        "pricing_authorized": False, "selection_authorized": False,
        "production_approval_authorized": False, "bet_authorized": False,
        "next_required_boundary": contract.NEXT_REQUIRED_BOUNDARY,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--execute-reviewed-protocol", action="store_true",
                        help="explicitly execute the reviewed eight-slot network campaign")
    parser.add_argument("--max-successful-slots", type=int, default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.execute_reviewed_protocol:
            result = execute_campaign(
                execute_live_network=True, repository_root=args.repository_root,
                max_successful_slots=args.max_successful_slots,
            )
            payload = dict(campaign_status(repository_root=args.repository_root))
            payload["completed_slots"] = result.completed_slots
        else:
            payload = dict(contract.runner_descriptor())
            payload["execution_requested"] = False
            payload["message"] = "No network acquisition performed; pass --execute-reviewed-protocol to execute the frozen campaign."
        sys.stdout.write(json.dumps(payload, sort_keys=True, indent=2) + "\n")
        return 0
    except Exception as exc:
        sys.stderr.write(_bounded_error(exc) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
