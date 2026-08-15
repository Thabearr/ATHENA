"""Live executor for the frozen FotMob ordinary-FT source-history campaign.

The runner reuses the reviewed single-request data-matches transport. Network
execution requires an explicit flag. Campaign state is resumable from canonical
append-only research evidence plus one durable in-flight attempt marker that
prevents crash/restart from silently repeating an unaccounted request.
"""

from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path as _BootstrapPath

    _REPOSITORY_ROOT = _BootstrapPath(__file__).resolve().parents[1]
    if str(_REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPOSITORY_ROOT))

import argparse
import contextlib
import datetime
import hashlib
import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable, Iterator

import domain.fotmob_data_matches_capture as capture_contract
import domain.fotmob_ordinary_ft_source_history_acquisition_protocol as pr101
from domain.fotmob_data_matches_capture import (
    FotMobDataMatchesCaptureError,
    parse_utc_timestamp,
    serialize_utc,
    sha256_data_matches_capture_manifest,
    verify_data_matches_capture_directory,
)
from domain.fotmob_ordinary_ft_source_history_acquisition_runner import (
    CAMPAIGN_INDEX_FILENAME,
    CAMPAIGN_LOCK_FILENAME,
    CAMPAIGN_ROOT_RELATIVE,
    CCODE3,
    FAILURE_JOURNAL_FILENAME,
    NEXT_REQUIRED_BOUNDARY,
    RUNNER_ID,
    TIMEZONE,
    CampaignProgress,
    CampaignSlot,
    FotMobOrdinaryFtSourceHistoryAcquisitionRunnerError,
    FotMobOrdinaryFtSourceHistoryPairWindowError,
    build_attempt_failed_entry,
    build_slot_blocked_entry,
    build_slot_succeeded_entry,
    campaign_progress,
    canonical_campaign_journal_entry_bytes,
    parse_campaign_evidence_bytes,
    runner_state,
    seconds_until_next_request_eligible,
    validate_success_observation,
)
import scripts.capture_fotmob_data_matches as capture_runtime


EXPECTED_CAPTURE_SCRIPT_BLOB_SHA = "10b8858ab62f2708bd564d578a627c43718e5a12"
EXPECTED_CAPTURE_CONTRACT_BLOB_SHA = "ca2149395de868104666620173b55a880b10c729"
MAX_WAIT_RECHECKS = 8

INFLIGHT_ATTEMPT_FILENAME = "inflight-attempt.json"
INFLIGHT_ATTEMPT_SCHEMA_VERSION = 1
MAX_INFLIGHT_ATTEMPT_BYTES = 4096
_INFLIGHT_KEYS = frozenset(
    {
        "schema_version",
        "runner_id",
        "evidence_sequence",
        "previous_entry_sha256",
        "request_date",
        "slot",
        "attempt",
        "attempt_started_at_utc",
        "intent_sha256",
    }
)
_ZERO_SHA256 = "0" * 64
_HEX = frozenset("0123456789abcdef")


class FotMobOrdinaryFtSourceHistoryAcquisitionLiveRunnerError(RuntimeError):
    """Raised when the controlled campaign executor cannot safely continue."""


def _error(message: str) -> FotMobOrdinaryFtSourceHistoryAcquisitionLiveRunnerError:
    return FotMobOrdinaryFtSourceHistoryAcquisitionLiveRunnerError(message)


def _utc_clock() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _bounded_failure(error: BaseException) -> str:
    message = " ".join(str(error).split())
    return f"{type(error).__name__}: {message[:360]}"


def _git_blob_oid(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def _verify_runtime_pins() -> None:
    state = runner_state()
    if state["next_required_boundary"] != NEXT_REQUIRED_BOUNDARY:
        raise _error("runner-state next boundary changed")
    if pr101.CAPTURE_SCRIPT_BLOB_SHA != EXPECTED_CAPTURE_SCRIPT_BLOB_SHA:
        raise _error("PR101 capture-script blob identity changed")
    if pr101.CAPTURE_CONTRACT_BLOB_SHA != EXPECTED_CAPTURE_CONTRACT_BLOB_SHA:
        raise _error("PR101 capture-contract blob identity changed")
    try:
        runtime_blob = _git_blob_oid(Path(capture_runtime.__file__))
        contract_blob = _git_blob_oid(Path(capture_contract.__file__))
    except (OSError, TypeError, ValueError) as exc:
        raise _error("could not verify reviewed capture runtime files") from exc
    if runtime_blob != EXPECTED_CAPTURE_SCRIPT_BLOB_SHA:
        raise _error("reviewed capture runtime file changed")
    if contract_blob != EXPECTED_CAPTURE_CONTRACT_BLOB_SHA:
        raise _error("reviewed capture contract file changed")
    if capture_runtime.ALLOWED_OUTPUT_RELATIVE != Path(
        ".cache/athena-research/fotmob-data-matches-captures"
    ):
        raise _error("reviewed capture output root changed")


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _absolute_without_resolving_symlinks(path: Path) -> Path:
    return path if path.is_absolute() else Path.cwd() / path


def _reject_symlink_components(path: Path, label: str) -> None:
    absolute = _absolute_without_resolving_symlinks(path)
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise _error(f"{label} contains a forbidden symlink")


def validate_campaign_root(
    *,
    repository_root: Path | None = None,
) -> Path:
    try:
        supplied_repository = Path(repository_root or _repository_root())
    except (TypeError, ValueError) as exc:
        raise _error("repository root is invalid") from exc
    if supplied_repository.is_symlink():
        raise _error("repository root must not be a symlink")
    try:
        repository = supplied_repository.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise _error("repository root must already exist") from exc
    if not repository.is_dir():
        raise _error("repository root must be a directory")
    _reject_symlink_components(repository, "repository root")

    target = repository / Path(CAMPAIGN_ROOT_RELATIVE)
    _reject_symlink_components(target, "campaign root")
    if target.exists() and (target.is_symlink() or not target.is_dir()):
        raise _error("campaign root must be a non-symlink directory")
    try:
        target.resolve(strict=False).relative_to(repository)
    except (OSError, RuntimeError, ValueError) as exc:
        raise _error("campaign root must remain inside repository") from exc
    return target


def _ensure_campaign_root(*, repository_root: Path | None = None) -> Path:
    repository = Path(repository_root or _repository_root()).resolve(strict=True)
    root = validate_campaign_root(repository_root=repository)
    try:
        capture_runtime._ensure_directory_tree_durable(root, boundary=repository)
        capture_runtime._reject_symlink_components(root, "campaign root")
    except FotMobDataMatchesCaptureError as exc:
        raise _error(f"could not durably create campaign root: {exc}") from exc
    return root


def _regular_single_link(path: Path, label: str) -> None:
    if path.is_symlink():
        raise _error(f"{label} must not be a symlink")
    if not path.exists():
        return
    try:
        details = path.stat()
    except OSError as exc:
        raise _error(f"{label} metadata could not be read") from exc
    if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
        raise _error(f"{label} must be a single-link regular file")


def _evidence_path(root: Path, filename: str) -> Path:
    if filename not in {CAMPAIGN_INDEX_FILENAME, FAILURE_JOURNAL_FILENAME}:
        raise _error("campaign evidence filename is not authorized")
    path = root / filename
    if path.parent != root:
        raise _error("campaign evidence path escaped campaign root")
    _regular_single_link(path, "campaign evidence")
    return path


def _inflight_path(root: Path) -> Path:
    path = root / INFLIGHT_ATTEMPT_FILENAME
    if path.parent != root:
        raise _error("in-flight attempt path escaped campaign root")
    _regular_single_link(path, "in-flight attempt marker")
    return path


def _read_evidence_file(root: Path, filename: str) -> bytes:
    path = _evidence_path(root, filename)
    if not path.exists():
        return b""
    try:
        return path.read_bytes()
    except OSError as exc:
        raise _error(f"could not read {filename}") from exc


def load_campaign_entries(
    *,
    repository_root: Path | None = None,
    create_root: bool = False,
) -> tuple[Any, ...]:
    root = (
        _ensure_campaign_root(repository_root=repository_root)
        if create_root
        else validate_campaign_root(repository_root=repository_root)
    )
    if not root.exists():
        return ()
    index_bytes = _read_evidence_file(root, CAMPAIGN_INDEX_FILENAME)
    failure_bytes = _read_evidence_file(root, FAILURE_JOURNAL_FILENAME)
    try:
        return parse_campaign_evidence_bytes(index_bytes, failure_bytes)
    except FotMobOrdinaryFtSourceHistoryAcquisitionRunnerError as exc:
        raise _error(f"campaign evidence revalidation failed: {exc}") from exc


def _write_all(descriptor: int, content: bytes) -> None:
    offset = 0
    try:
        while offset < len(content):
            written = os.write(descriptor, content[offset:])
            if written <= 0:
                raise OSError("write made no progress")
            offset += written
        os.fsync(descriptor)
    except OSError as exc:
        raise _error("could not durably write campaign control/evidence") from exc


def _append_entry(
    entries: tuple[Any, ...],
    entry: Any,
    *,
    repository_root: Path | None = None,
) -> tuple[Any, ...]:
    root = _ensure_campaign_root(repository_root=repository_root)
    current = load_campaign_entries(repository_root=repository_root, create_root=True)
    if tuple(current) != tuple(entries):
        raise _error("campaign evidence changed concurrently before append")
    encoded = canonical_campaign_journal_entry_bytes(entry)
    filename = (
        CAMPAIGN_INDEX_FILENAME
        if entry["event_type"] == "SLOT_SUCCEEDED"
        else FAILURE_JOURNAL_FILENAME
    )
    path = _evidence_path(root, filename)
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise _error(f"could not open {filename} for append") from exc
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
            raise _error("campaign evidence descriptor is not a single-link regular file")
        _write_all(descriptor, encoded)
    finally:
        try:
            os.close(descriptor)
        except OSError as exc:
            raise _error("could not close campaign evidence descriptor") from exc
    try:
        capture_runtime._sync_directory(root)
    except FotMobDataMatchesCaptureError as exc:
        raise _error("could not durably synchronize campaign root") from exc

    expected = (*entries, entry)
    reloaded = load_campaign_entries(repository_root=repository_root, create_root=True)
    if tuple(reloaded) != tuple(expected):
        raise _error("campaign evidence did not revalidate after durable append")
    return reloaded


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    try:
        return (
            json.dumps(
                dict(value),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("in-flight attempt serialization failed") from exc


def _valid_sha(value: Any, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in _HEX for character in value)
    ):
        raise _error(f"{label} must be exactly 64 lowercase hexadecimal characters")
    return value


def _strict_json(content: bytes) -> dict[str, Any]:
    if type(content) is not bytes or not content or len(content) > MAX_INFLIGHT_ATTEMPT_BYTES:
        raise _error("in-flight attempt marker size/framing is invalid")
    if not content.endswith(b"\n"):
        raise _error("in-flight attempt marker is torn")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _error("in-flight attempt marker must be UTF-8") from exc

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in items:
            if key in result:
                raise _error("in-flight attempt marker contains duplicate JSON keys")
            result[key] = item
        return result

    def constant(token: str) -> None:
        raise _error(f"in-flight attempt marker constant {token!r} is forbidden")

    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except FotMobOrdinaryFtSourceHistoryAcquisitionLiveRunnerError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise _error("in-flight attempt marker JSON is invalid") from exc
    if type(value) is not dict:
        raise _error("in-flight attempt marker must be a JSON object")
    return value


def _validate_inflight_intent(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise _error("in-flight attempt marker must be a mapping")
    plain = dict(value)
    if set(plain) != _INFLIGHT_KEYS:
        raise _error("in-flight attempt marker keys mismatch")
    if plain["schema_version"] != INFLIGHT_ATTEMPT_SCHEMA_VERSION or type(plain["schema_version"]) is not int:
        raise _error("in-flight attempt marker schema_version mismatch")
    if plain["runner_id"] != RUNNER_ID:
        raise _error("in-flight attempt marker runner_id mismatch")
    if type(plain["evidence_sequence"]) is not int or plain["evidence_sequence"] < 0:
        raise _error("in-flight evidence_sequence must be an exact non-negative integer")
    _valid_sha(plain["previous_entry_sha256"], "previous_entry_sha256")
    request_date = plain["request_date"]
    if (
        type(request_date) is not str
        or len(request_date) != 8
        or not request_date.isascii()
        or not request_date.isdigit()
    ):
        raise _error("in-flight request_date must be canonical YYYYMMDD")
    if plain["slot"] not in {"A", "B"}:
        raise _error("in-flight slot must be exactly A or B")
    if type(plain["attempt"]) is not int or not 1 <= plain["attempt"] <= 3:
        raise _error("in-flight attempt must be exact integer 1..3")
    try:
        started = parse_utc_timestamp(
            plain["attempt_started_at_utc"], "attempt_started_at_utc"
        )
    except Exception as exc:
        raise _error("in-flight attempt_started_at_utc is invalid") from exc
    canonical_started = serialize_utc(started)
    if canonical_started != plain["attempt_started_at_utc"]:
        raise _error("in-flight attempt timestamp is not canonical UTC")
    claimed = _valid_sha(plain["intent_sha256"], "intent_sha256")
    unsigned = dict(plain)
    unsigned.pop("intent_sha256")
    expected = hashlib.sha256(_canonical_json(unsigned)).hexdigest()
    if claimed != expected:
        raise _error("in-flight attempt marker SHA-256 mismatch")
    return plain


def _load_inflight_intent(root: Path) -> dict[str, Any] | None:
    path = _inflight_path(root)
    if not path.exists():
        return None
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise _error("could not read in-flight attempt marker") from exc
    value = _strict_json(raw)
    plain = _validate_inflight_intent(value)
    if _canonical_json(plain) != raw:
        raise _error("in-flight attempt marker is not canonical JSON")
    return plain


def _previous_evidence_hash(entries: tuple[Any, ...]) -> str:
    if not entries:
        return _ZERO_SHA256
    return _valid_sha(entries[-1]["entry_sha256"], "entry_sha256")


def _build_inflight_intent(
    entries: tuple[Any, ...],
    *,
    slot: CampaignSlot,
    attempt: int,
    attempt_started_at: datetime.datetime,
) -> dict[str, Any]:
    progress = campaign_progress(entries)
    if progress.complete or progress.blocked:
        raise _error("cannot begin an attempt from completed/blocked campaign state")
    if progress.next_slot != slot or progress.next_attempt != attempt:
        raise _error("in-flight attempt does not match exact next campaign slot/attempt")
    try:
        started = serialize_utc(attempt_started_at)
    except Exception as exc:
        raise _error("in-flight attempt start must be timezone-aware") from exc
    unsigned = {
        "schema_version": INFLIGHT_ATTEMPT_SCHEMA_VERSION,
        "runner_id": RUNNER_ID,
        "evidence_sequence": len(entries),
        "previous_entry_sha256": _previous_evidence_hash(entries),
        "request_date": slot.request_date,
        "slot": slot.slot,
        "attempt": attempt,
        "attempt_started_at_utc": started,
    }
    return {
        **unsigned,
        "intent_sha256": hashlib.sha256(_canonical_json(unsigned)).hexdigest(),
    }


def _create_inflight_intent(
    entries: tuple[Any, ...],
    *,
    slot: CampaignSlot,
    attempt: int,
    attempt_started_at: datetime.datetime,
    root: Path,
) -> dict[str, Any]:
    intent = _validate_inflight_intent(
        _build_inflight_intent(
            entries,
            slot=slot,
            attempt=attempt,
            attempt_started_at=attempt_started_at,
        )
    )
    encoded = _canonical_json(intent)
    path = _inflight_path(root)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise _error("in-flight attempt marker already exists") from exc
    except OSError as exc:
        raise _error("could not create in-flight attempt marker") from exc
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
            raise _error("in-flight attempt descriptor is not a single-link regular file")
        _write_all(descriptor, encoded)
    finally:
        try:
            os.close(descriptor)
        except OSError as exc:
            raise _error("could not close in-flight attempt marker") from exc
    try:
        capture_runtime._sync_directory(root)
    except FotMobDataMatchesCaptureError as exc:
        raise _error("could not durably synchronize in-flight attempt marker") from exc
    persisted = _load_inflight_intent(root)
    if persisted != intent:
        raise _error("in-flight attempt marker did not revalidate after durable write")
    return intent


def _remove_inflight_intent(root: Path, expected: Mapping[str, Any]) -> None:
    path = _inflight_path(root)
    persisted = _load_inflight_intent(root)
    if persisted is None:
        raise _error("in-flight attempt marker disappeared before outcome commit")
    if persisted != dict(expected):
        raise _error("in-flight attempt marker changed before outcome commit")
    try:
        path.unlink()
        capture_runtime._sync_directory(root)
    except (OSError, FotMobDataMatchesCaptureError) as exc:
        raise _error("could not durably clear completed in-flight attempt marker") from exc


def _intent_matches_pending_state(
    entries: tuple[Any, ...], intent: Mapping[str, Any]
) -> bool:
    if len(entries) != intent["evidence_sequence"]:
        return False
    if _previous_evidence_hash(entries) != intent["previous_entry_sha256"]:
        return False
    progress = campaign_progress(entries)
    if progress.complete or progress.blocked or progress.next_slot is None:
        return False
    return (
        progress.next_slot.request_date == intent["request_date"]
        and progress.next_slot.slot == intent["slot"]
        and progress.next_attempt == intent["attempt"]
    )


def _intent_matches_recorded_outcome(
    entries: tuple[Any, ...], intent: Mapping[str, Any]
) -> bool:
    sequence = intent["evidence_sequence"]
    if len(entries) != sequence + 1:
        return False
    outcome = entries[-1]
    return (
        outcome["sequence"] == sequence + 1
        and outcome["previous_entry_sha256"] == intent["previous_entry_sha256"]
        and outcome["event_type"] in {"SLOT_SUCCEEDED", "ATTEMPT_FAILED"}
        and outcome["request_date"] == intent["request_date"]
        and outcome["slot"] == intent["slot"]
        and outcome["attempt"] == intent["attempt"]
        and outcome["attempt_started_at_utc"] == intent["attempt_started_at_utc"]
    )


def _reconcile_completed_inflight_marker(
    entries: tuple[Any, ...],
    *,
    root: Path,
) -> tuple[Any, ...]:
    intent = _load_inflight_intent(root)
    if intent is None:
        return entries
    if _intent_matches_recorded_outcome(entries, intent):
        _remove_inflight_intent(root, intent)
        return entries
    if _intent_matches_pending_state(entries, intent):
        raise _error(
            "UNRESOLVED_INFLIGHT_ATTEMPT_REQUIRES_RECONCILIATION: a request may "
            "have started without a durable campaign outcome; automatic retry is forbidden"
        )
    raise _error(
        "INFLIGHT_ATTEMPT_STATE_CONFLICT: marker and append-only campaign evidence disagree"
    )


def _inflight_status(
    entries: tuple[Any, ...],
    *,
    root: Path,
) -> dict[str, Any] | None:
    intent = _load_inflight_intent(root)
    if intent is None:
        return None
    if _intent_matches_recorded_outcome(entries, intent):
        reason = "RECORDED_OUTCOME_PENDING_SAFE_MARKER_CLEANUP"
    elif _intent_matches_pending_state(entries, intent):
        reason = "UNRESOLVED_INFLIGHT_ATTEMPT_REQUIRES_RECONCILIATION"
    else:
        reason = "INFLIGHT_ATTEMPT_STATE_CONFLICT"
    return {
        "reason": reason,
        "request_date": intent["request_date"],
        "slot": intent["slot"],
        "attempt": intent["attempt"],
        "attempt_started_at_utc": intent["attempt_started_at_utc"],
        "intent_sha256": intent["intent_sha256"],
    }


def _lock_payload() -> bytes:
    return (
        json.dumps(
            {"pid": os.getpid(), "runner_id": runner_state()["runner_id"]},
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


@contextlib.contextmanager
def campaign_lock(
    *,
    repository_root: Path | None = None,
) -> Iterator[Path]:
    root = _ensure_campaign_root(repository_root=repository_root)
    path = root / CAMPAIGN_LOCK_FILENAME
    if path.parent != root or path.is_symlink():
        raise _error("campaign lock path is invalid")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise _error(
            "campaign lock already exists; refuse concurrent execution or manually "
            "inspect and remove a confirmed-stale lock"
        ) from exc
    except OSError as exc:
        raise _error("could not create campaign lock") from exc
    try:
        try:
            _write_all(descriptor, _lock_payload())
        finally:
            os.close(descriptor)
        capture_runtime._sync_directory(root)
        yield root
    finally:
        cleanup_error: BaseException | None = None
        try:
            if path.is_symlink():
                raise _error("refusing to remove a symlink campaign lock")
            if path.exists():
                path.unlink()
                capture_runtime._sync_directory(root)
        except BaseException as exc:
            cleanup_error = exc
        if cleanup_error is not None:
            raise _error(
                f"campaign lock cleanup failed: {_bounded_failure(cleanup_error)}"
            ) from cleanup_error


def _wait_until_eligible(
    entries: tuple[Any, ...],
    *,
    clock: Callable[[], datetime.datetime],
    sleeper: Callable[[float], None],
) -> datetime.datetime:
    for _ in range(MAX_WAIT_RECHECKS):
        now = clock()
        wait_seconds = seconds_until_next_request_eligible(entries, now)
        if wait_seconds <= 0:
            return now
        sleeper(wait_seconds)
    raise _error("runner clock did not advance through the required wait interval")


def _verified_capture_evidence(
    *,
    capture_directory: Path,
    request_date: str,
    repository_root: Path,
) -> tuple[Any, str]:
    allowed_root = repository_root / capture_runtime.ALLOWED_OUTPUT_RELATIVE
    manifest = verify_data_matches_capture_directory(
        capture_directory,
        allowed_root=allowed_root,
        require_network_acquisition_performed=True,
    )
    if (
        manifest.request_date != request_date
        or manifest.timezone != TIMEZONE
        or manifest.ccode3 != CCODE3
    ):
        raise _error("persisted capture request identity differs from frozen campaign")
    manifest_sha256 = sha256_data_matches_capture_manifest(manifest)
    return manifest, manifest_sha256


def _record_failure(
    entries: tuple[Any, ...],
    *,
    slot: CampaignSlot,
    attempt: int,
    attempt_started_at: datetime.datetime,
    recorded_at: datetime.datetime,
    error_kind: str,
    error_message: str,
    repository_root: Path,
    capture_id: str | None = None,
    manifest_sha256: str | None = None,
) -> tuple[Any, ...]:
    entry = build_attempt_failed_entry(
        entries,
        slot=slot,
        attempt=attempt,
        attempt_started_at=attempt_started_at,
        recorded_at=recorded_at,
        error_kind=error_kind,
        error_message=error_message,
        capture_id=capture_id,
        manifest_sha256=manifest_sha256,
    )
    return _append_entry(entries, entry, repository_root=repository_root)


def _record_block(
    entries: tuple[Any, ...],
    *,
    slot: CampaignSlot,
    recorded_at: datetime.datetime,
    error_kind: str,
    error_message: str,
    repository_root: Path,
    capture_id: str | None = None,
    manifest_sha256: str | None = None,
) -> tuple[Any, ...]:
    entry = build_slot_blocked_entry(
        entries,
        slot=slot,
        recorded_at=recorded_at,
        error_kind=error_kind,
        error_message=error_message,
        capture_id=capture_id,
        manifest_sha256=manifest_sha256,
    )
    return _append_entry(entries, entry, repository_root=repository_root)


def _execute_next_slot_locked(
    *,
    repository_root: Path,
    fetcher: Callable[..., Any],
    writer: Callable[..., Any],
    verifier: Callable[..., Any],
    clock: Callable[[], datetime.datetime],
    sleeper: Callable[[float], None],
) -> CampaignProgress:
    root = _ensure_campaign_root(repository_root=repository_root)
    entries = load_campaign_entries(repository_root=repository_root, create_root=True)
    entries = _reconcile_completed_inflight_marker(entries, root=root)
    progress = campaign_progress(entries)
    if progress.complete:
        return progress
    if progress.blocked or progress.next_slot is None or progress.next_attempt is None:
        raise _error(f"campaign is blocked: {progress.block_reason}")

    while True:
        progress = campaign_progress(entries)
        if progress.blocked or progress.next_slot is None or progress.next_attempt is None:
            raise _error(f"campaign is blocked: {progress.block_reason}")
        slot = progress.next_slot
        attempt = progress.next_attempt

        try:
            eligible_at = _wait_until_eligible(entries, clock=clock, sleeper=sleeper)
        except FotMobOrdinaryFtSourceHistoryPairWindowError as exc:
            entries = _record_block(
                entries,
                slot=slot,
                recorded_at=clock(),
                error_kind=exc.reason,
                error_message=str(exc),
                repository_root=repository_root,
            )
            raise _error(f"campaign pair window blocked: {exc}") from exc

        attempt_started_at = eligible_at
        intent = _create_inflight_intent(
            entries,
            slot=slot,
            attempt=attempt,
            attempt_started_at=attempt_started_at,
            root=root,
        )
        capture_directory: Path | None = None
        manifest_sha256: str | None = None
        try:
            response = fetcher(
                request_date=slot.request_date,
                timezone=TIMEZONE,
                ccode3=CCODE3,
            )
            if getattr(response, "network_acquisition_performed", None) is not True:
                raise _error("live fetch did not preserve network acquisition provenance")
            capture_directory, _ = writer(
                response,
                request_date=slot.request_date,
                timezone=TIMEZONE,
                ccode3=CCODE3,
                repository_root=repository_root,
            )
            if not isinstance(capture_directory, Path):
                capture_directory = Path(capture_directory)
            manifest, manifest_sha256 = verifier(
                capture_directory=capture_directory,
                request_date=slot.request_date,
                repository_root=repository_root,
            )
            validate_success_observation(entries, slot, manifest.observed_at)
            entry = build_slot_succeeded_entry(
                entries,
                slot=slot,
                attempt=attempt,
                attempt_started_at=attempt_started_at,
                recorded_at=clock(),
                capture_id=capture_directory.name,
                raw_sha256=manifest.raw_sha256,
                raw_size=manifest.raw_size,
                manifest_sha256=manifest_sha256,
                observed_at=manifest.observed_at,
            )
            entries = _append_entry(entries, entry, repository_root=repository_root)
            _remove_inflight_intent(root, intent)
            return campaign_progress(entries)
        except FotMobOrdinaryFtSourceHistoryPairWindowError as exc:
            entries = _record_failure(
                entries,
                slot=slot,
                attempt=attempt,
                attempt_started_at=attempt_started_at,
                recorded_at=clock(),
                error_kind=exc.reason,
                error_message=str(exc),
                repository_root=repository_root,
                capture_id=(None if capture_directory is None else capture_directory.name),
                manifest_sha256=manifest_sha256,
            )
            _remove_inflight_intent(root, intent)
            progress = campaign_progress(entries)
            if exc.reason == "PAIR_OBSERVATION_TOO_LATE" and not progress.blocked:
                entries = _record_block(
                    entries,
                    slot=slot,
                    recorded_at=clock(),
                    error_kind="PAIR_WINDOW_EXPIRED_AFTER_CAPTURE",
                    error_message=(
                        "persisted capture exists but slot B can no longer satisfy "
                        "the frozen pair window"
                    ),
                    repository_root=repository_root,
                    capture_id=(None if capture_directory is None else capture_directory.name),
                    manifest_sha256=manifest_sha256,
                )
                raise _error("campaign pair window expired after durable capture") from exc
            if progress.blocked:
                raise _error(f"campaign is blocked: {progress.block_reason}") from exc
            continue
        except (
            FotMobDataMatchesCaptureError,
            capture_runtime.FotMobDataMatchesNetworkError,
            OSError,
            TimeoutError,
        ) as exc:
            entries = _record_failure(
                entries,
                slot=slot,
                attempt=attempt,
                attempt_started_at=attempt_started_at,
                recorded_at=clock(),
                error_kind="ACQUISITION_ATTEMPT_FAILED",
                error_message=_bounded_failure(exc),
                repository_root=repository_root,
                capture_id=(None if capture_directory is None else capture_directory.name),
                manifest_sha256=manifest_sha256,
            )
            _remove_inflight_intent(root, intent)
            progress = campaign_progress(entries)
            if progress.blocked:
                raise _error(f"campaign is blocked: {progress.block_reason}") from exc
            continue


def execute_next_campaign_slot(
    *,
    execute_live_network: bool,
    repository_root: Path | None = None,
    fetcher: Callable[..., Any] = capture_runtime.fetch_fotmob_data_matches,
    writer: Callable[..., Any] = capture_runtime.write_data_matches_capture_directory,
    verifier: Callable[..., Any] = _verified_capture_evidence,
    clock: Callable[[], datetime.datetime] = _utc_clock,
    sleeper: Callable[[float], None] | None = None,
) -> CampaignProgress:
    if execute_live_network is not True:
        raise _error("live network execution requires exact True authorization")
    _verify_runtime_pins()
    repository = Path(repository_root or _repository_root()).resolve(strict=True)
    if sleeper is None:
        import time

        sleeper = time.sleep
    with campaign_lock(repository_root=repository):
        return _execute_next_slot_locked(
            repository_root=repository,
            fetcher=fetcher,
            writer=writer,
            verifier=verifier,
            clock=clock,
            sleeper=sleeper,
        )


def execute_campaign(
    *,
    execute_live_network: bool,
    repository_root: Path | None = None,
    max_successful_slots: int | None = None,
    fetcher: Callable[..., Any] = capture_runtime.fetch_fotmob_data_matches,
    writer: Callable[..., Any] = capture_runtime.write_data_matches_capture_directory,
    verifier: Callable[..., Any] = _verified_capture_evidence,
    clock: Callable[[], datetime.datetime] = _utc_clock,
    sleeper: Callable[[float], None] | None = None,
) -> CampaignProgress:
    if execute_live_network is not True:
        raise _error("live network execution requires exact True authorization")
    if max_successful_slots is not None and (
        type(max_successful_slots) is not int or max_successful_slots <= 0
    ):
        raise _error("max_successful_slots must be an exact positive integer")
    _verify_runtime_pins()
    repository = Path(repository_root or _repository_root()).resolve(strict=True)
    if sleeper is None:
        import time

        sleeper = time.sleep

    with campaign_lock(repository_root=repository):
        root = _ensure_campaign_root(repository_root=repository)
        entries = load_campaign_entries(repository_root=repository, create_root=True)
        entries = _reconcile_completed_inflight_marker(entries, root=root)
        initial = campaign_progress(entries)
        if initial.blocked:
            raise _error(f"campaign is blocked: {initial.block_reason}")
        starting_completed = initial.completed_slots
        progress = initial
        while not progress.complete:
            if (
                max_successful_slots is not None
                and progress.completed_slots - starting_completed >= max_successful_slots
            ):
                break
            progress = _execute_next_slot_locked(
                repository_root=repository,
                fetcher=fetcher,
                writer=writer,
                verifier=verifier,
                clock=clock,
                sleeper=sleeper,
            )
        return progress


def campaign_status(*, repository_root: Path | None = None) -> dict[str, Any]:
    _verify_runtime_pins()
    root = validate_campaign_root(repository_root=repository_root)
    entries = load_campaign_entries(repository_root=repository_root, create_root=False)
    progress = campaign_progress(entries)
    state = runner_state()
    inflight = None if not root.exists() else _inflight_status(entries, root=root)
    effective_blocked = progress.blocked or inflight is not None
    block_reason = progress.block_reason if progress.blocked else (
        None if inflight is None else inflight["reason"]
    )
    return {
        "runner_id": state["runner_id"],
        "runner_state": state["runner_state"],
        "completed_slots": progress.completed_slots,
        "total_slots": progress.total_slots,
        "complete": progress.complete and inflight is None,
        "blocked": effective_blocked,
        "block_reason": block_reason,
        "next_slot": (
            None
            if progress.next_slot is None
            else {
                "ordinal": progress.next_slot.ordinal,
                "request_date": progress.next_slot.request_date,
                "slot": progress.next_slot.slot,
                "attempt": progress.next_attempt,
            }
        ),
        "inflight_attempt": inflight,
        "network_acquisition_performed_by_this_status_command": False,
        "historical_coverage_proven": False,
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Execute or inspect the exact reviewed FotMob ordinary-FT source-history "
            "acquisition campaign. Live execution is resumable and fail-closed."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--status",
        action="store_true",
        help="Revalidate and print campaign progress without network access",
    )
    mode.add_argument(
        "--execute-live-network",
        action="store_true",
        help="Authorize the frozen live FotMob campaign transport",
    )
    parser.add_argument(
        "--max-successful-slots",
        type=int,
        default=None,
        help="Optional positive chunk size for resumable live execution",
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    repository_root: Path | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.status and args.max_successful_slots is not None:
        parser.error("--max-successful-slots is valid only with --execute-live-network")
    try:
        if args.status:
            result: Any = campaign_status(repository_root=repository_root)
        else:
            progress = execute_campaign(
                execute_live_network=True,
                repository_root=repository_root,
                max_successful_slots=args.max_successful_slots,
            )
            result = {
                **campaign_status(repository_root=repository_root),
                "completed_slots_after_execution": progress.completed_slots,
            }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (
        FotMobOrdinaryFtSourceHistoryAcquisitionLiveRunnerError,
        FotMobOrdinaryFtSourceHistoryAcquisitionRunnerError,
        FotMobDataMatchesCaptureError,
    ) as exc:
        parser.exit(1, f"campaign runner failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
