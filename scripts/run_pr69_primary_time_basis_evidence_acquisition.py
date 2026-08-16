"""Live executor for the reviewed PR69 primary time-basis evidence campaign.

The module is inert on import. Live transport requires explicit authorization and uses
only the exact four PR124 football-data.co.uk targets. Public live entry points bind the
reviewed HTTPS transport and real wall-clock timing sources directly; synthetic fetchers
and clocks exist only behind internal test seams. Campaign evidence is append-only,
resumable, and fail-closed around any request whose durable outcome is uncertain.
"""
from __future__ import annotations

if __package__ in {None, ""}:
    import sys as _bootstrap_sys
    from pathlib import Path as _BootstrapPath

    _REPOSITORY_ROOT = _BootstrapPath(__file__).resolve().parents[1]
    if str(_REPOSITORY_ROOT) not in _bootstrap_sys.path:
        _bootstrap_sys.path.insert(0, str(_REPOSITORY_ROOT))

import argparse
import contextlib
import dataclasses
import datetime
import hashlib
import http.client
import json
import os
import ssl
import stat
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Iterator

from domain import pr69_primary_time_basis_evidence_acquisition_runner as contract

UTC = datetime.timezone.utc
NETWORK_TIMEOUT_SECONDS = 30.0
INFLIGHT_ATTEMPT_FILENAME = "inflight-attempt.json"
INFLIGHT_SCHEMA_VERSION = 1
MAX_INFLIGHT_BYTES = 4096
MAX_WAIT_RECHECKS = 8
REQUEST_HEADERS = contract.REQUEST_HEADERS
SELECTED_RESPONSE_HEADERS = frozenset(contract.SELECTED_RESPONSE_HEADERS)
_INFLIGHT_KEYS = frozenset({
    "schema_version", "runner_id", "evidence_sequence", "previous_entry_sha256",
    "target_id", "slot", "attempt", "intent_started_at_utc", "intent_sha256",
})


class PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(RuntimeError):
    """Raised when the controlled live executor cannot continue safely."""


class PrimaryEvidenceRequestError(PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError):
    """A known request/response failure that may be durably journaled and retried."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = contract.validate_error_kind(kind)


@dataclasses.dataclass(frozen=True)
class FetchResult:
    slot: contract.CampaignSlot
    attempt: int
    raw_body: bytes
    manifest: Mapping[str, Any]


def _error(message: str) -> PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError:
    return PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError(message)


def _clock() -> datetime.datetime:
    return datetime.datetime.now(tz=UTC)


def _bounded_failure(exc: BaseException) -> str:
    return contract.normalize_error_message(f"{type(exc).__name__}: {exc}")


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


def _load_kernel32() -> Any:
    try:
        import ctypes
        import ctypes.wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.argtypes = [
            ctypes.wintypes.LPCWSTR,
            ctypes.wintypes.DWORD,
            ctypes.wintypes.DWORD,
            ctypes.c_void_p,
            ctypes.wintypes.DWORD,
            ctypes.wintypes.DWORD,
            ctypes.wintypes.HANDLE,
        ]
        kernel32.CreateFileW.restype = ctypes.wintypes.HANDLE
        kernel32.FlushFileBuffers.argtypes = [ctypes.wintypes.HANDLE]
        kernel32.FlushFileBuffers.restype = ctypes.wintypes.BOOL
        kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
        kernel32.CloseHandle.restype = ctypes.wintypes.BOOL
        return kernel32
    except (AttributeError, ImportError, OSError):
        return None


def _sync_directory(path: Path) -> None:
    if os.name == "nt":
        kernel32 = _load_kernel32()
        if kernel32 is None:
            raise _error(f"cannot prove directory durability on Windows: {path}")
        try:
            import ctypes
            import ctypes.wintypes

            handle = kernel32.CreateFileW(
                str(path), 0xC0000000, 0x00000007, None, 3, 0x02000000, None
            )
            invalid = {
                None, 0, -1, ctypes.c_void_p(-1).value,
                ctypes.wintypes.HANDLE(-1).value,
            }
        except (AttributeError, ImportError, OSError, TypeError, ValueError) as exc:
            raise _error(f"could not open directory for synchronization: {path}") from exc
        if handle in invalid:
            raise _error(f"could not open directory for synchronization: {path}")
        failures: list[str] = []
        try:
            if not kernel32.FlushFileBuffers(handle):
                failures.append("FlushFileBuffers failed")
        finally:
            if not kernel32.CloseHandle(handle):
                failures.append("CloseHandle failed")
        if failures:
            raise _error(
                f"could not durably synchronize directory {path}: {'; '.join(failures)}"
            )
        return
    if os.name != "posix":
        raise _error(f"directory durability is unsupported on platform {os.name!r}")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(str(path), flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise _error(f"could not durably synchronize directory {path}") from exc


def _ensure_directory_tree(target: Path, *, boundary: Path) -> None:
    try:
        relative = target.relative_to(boundary)
    except ValueError as exc:
        raise _error("output directory escaped repository boundary") from exc
    current = boundary
    _sync_directory(current)
    for part in relative.parts:
        child = current / part
        if child.exists() or child.is_symlink():
            if child.is_symlink() or not child.is_dir():
                raise _error(f"output component is not a regular directory: {child}")
        else:
            child.mkdir()
            _sync_directory(current)
        _sync_directory(child)
        current = child


def validate_campaign_root(*, repository_root: Path | None = None) -> Path:
    try:
        supplied = Path(repository_root or _repository_root())
    except (TypeError, ValueError) as exc:
        raise _error("repository root is invalid") from exc
    if supplied.is_symlink():
        raise _error("repository root must not be a symlink")
    try:
        repository = supplied.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise _error("repository root must already exist") from exc
    if not repository.is_dir():
        raise _error("repository root must be a directory")
    _reject_symlink_components(repository, "repository root")
    root = repository / contract.CAPTURE_ROOT_RELATIVE
    _reject_symlink_components(root, "campaign root")
    if root.exists() and (root.is_symlink() or not root.is_dir()):
        raise _error("campaign root must be a non-symlink directory")
    try:
        root.resolve(strict=False).relative_to(repository)
    except (OSError, RuntimeError, ValueError) as exc:
        raise _error("campaign root must remain inside repository") from exc
    return root


def _ensure_campaign_root(*, repository_root: Path | None = None) -> Path:
    repository = Path(repository_root or _repository_root()).resolve(strict=True)
    root = validate_campaign_root(repository_root=repository)
    _ensure_directory_tree(root, boundary=repository)
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
    if filename not in {
        contract.CAMPAIGN_INDEX_FILENAME,
        contract.FAILURE_JOURNAL_FILENAME,
    }:
        raise _error("campaign evidence filename is not authorized")
    path = root / filename
    if path.parent != root:
        raise _error("campaign evidence path escaped campaign root")
    _regular_single_link(path, "campaign evidence")
    return path


def _inflight_path(root: Path) -> Path:
    path = root / INFLIGHT_ATTEMPT_FILENAME
    if path.parent != root:
        raise _error("inflight marker escaped campaign root")
    _regular_single_link(path, "inflight marker")
    return path


def _lock_path(root: Path) -> Path:
    path = root / contract.RUNNER_LOCK_FILENAME
    if path.parent != root:
        raise _error("runner lock escaped campaign root")
    _regular_single_link(path, "runner lock")
    return path


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
        raise _error("could not durably write campaign evidence") from exc


def _write_exclusive(path: Path, content: bytes) -> None:
    if type(content) is not bytes:
        raise _error("evidence content must be exact bytes")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise _error(f"refusing to overwrite evidence: {path}") from exc
    except OSError as exc:
        raise _error(f"could not create evidence: {path}") from exc
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
            raise _error("new evidence descriptor is not a single-link regular file")
        _write_all(descriptor, content)
    finally:
        try:
            os.close(descriptor)
        except OSError as exc:
            raise _error("could not close evidence descriptor") from exc
    _sync_directory(path.parent)


def _strict_json(content: bytes, label: str, max_bytes: int) -> Mapping[str, Any]:
    if type(content) is not bytes or not content or len(content) > max_bytes:
        raise _error(f"{label} size/framing is invalid")
    if not content.endswith(b"\n"):
        raise _error(f"{label} has a torn trailing record")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _error(f"{label} must be UTF-8") from exc

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise _error(f"{label} contains duplicate JSON keys")
            result[key] = value
        return result

    def constant(token: str) -> None:
        raise _error(f"{label} constant {token!r} is forbidden")

    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise _error(f"{label} JSON is invalid") from exc
    if type(value) is not dict:
        raise _error(f"{label} must contain a JSON object")
    if contract.canonical_bytes(value) != content:
        raise _error(f"{label} is not canonical JSON")
    return value


def _read_evidence_file(root: Path, filename: str) -> bytes:
    path = _evidence_path(root, filename)
    if not path.exists():
        return b""
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise _error(f"could not read {filename}") from exc
    if len(content) > contract.MAX_EVIDENCE_FILE_BYTES:
        raise _error(f"{filename} exceeds evidence file bound")
    return content


def load_campaign_entries(
    *, repository_root: Path | None = None, create_root: bool = False
) -> tuple[Mapping[str, Any], ...]:
    root = (
        _ensure_campaign_root(repository_root=repository_root)
        if create_root
        else validate_campaign_root(repository_root=repository_root)
    )
    if not root.exists():
        return ()
    try:
        return contract.parse_campaign_evidence_bytes(
            _read_evidence_file(root, contract.CAMPAIGN_INDEX_FILENAME),
            _read_evidence_file(root, contract.FAILURE_JOURNAL_FILENAME),
        )
    except contract.PR69PrimaryTimeBasisEvidenceAcquisitionRunnerError as exc:
        raise _error(f"campaign evidence revalidation failed: {exc}") from exc


def _append_entry(
    entries: tuple[Mapping[str, Any], ...],
    entry: Mapping[str, Any],
    *,
    repository_root: Path,
) -> tuple[Mapping[str, Any], ...]:
    root = _ensure_campaign_root(repository_root=repository_root)
    current = load_campaign_entries(repository_root=repository_root, create_root=True)
    if tuple(current) != tuple(entries):
        raise _error("campaign evidence changed concurrently before append")
    encoded = contract.canonical_campaign_entry_bytes(entry)
    filename = (
        contract.CAMPAIGN_INDEX_FILENAME
        if entry["event_type"] == "SLOT_SUCCEEDED"
        else contract.FAILURE_JOURNAL_FILENAME
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
            raise _error("campaign evidence descriptor is not single-link regular file")
        _write_all(descriptor, encoded)
    finally:
        try:
            os.close(descriptor)
        except OSError as exc:
            raise _error("could not close campaign evidence descriptor") from exc
    _sync_directory(root)
    expected = (*entries, entry)
    reloaded = load_campaign_entries(repository_root=repository_root, create_root=True)
    if tuple(reloaded) != tuple(expected):
        raise _error("campaign evidence did not revalidate after append")
    return reloaded


@contextlib.contextmanager
def campaign_lock(*, repository_root: Path | None = None) -> Iterator[Path]:
    root = _ensure_campaign_root(repository_root=repository_root)
    path = _lock_path(root)
    payload = contract.canonical_bytes(
        {"pid": os.getpid(), "runner_id": contract.RUNNER_ID}
    )
    _write_exclusive(path, payload)
    try:
        yield root
    finally:
        cleanup_error: BaseException | None = None
        try:
            if path.is_symlink():
                raise _error("refusing to remove symlink runner lock")
            if path.exists():
                path.unlink()
                _sync_directory(root)
        except BaseException as exc:
            cleanup_error = exc
        if cleanup_error is not None:
            raise _error(
                f"runner lock cleanup failed: {_bounded_failure(cleanup_error)}"
            ) from cleanup_error


def _previous_hash(entries: Sequence[Mapping[str, Any]]) -> str:
    if not entries:
        return contract.ZERO_SHA256
    return contract.validate_sha256(entries[-1]["entry_sha256"], "entry_sha256")


def _build_inflight_intent(
    entries: tuple[Mapping[str, Any], ...],
    *,
    slot: contract.CampaignSlot,
    attempt: int,
    intent_started_at: datetime.datetime,
) -> Mapping[str, Any]:
    progress = contract.campaign_progress(entries)
    if (
        progress.complete
        or progress.blocked
        or progress.next_slot != slot
        or progress.next_attempt != attempt
    ):
        raise _error("inflight attempt does not match exact pending campaign state")
    unsigned = {
        "schema_version": INFLIGHT_SCHEMA_VERSION,
        "runner_id": contract.RUNNER_ID,
        "evidence_sequence": len(entries),
        "previous_entry_sha256": _previous_hash(entries),
        "target_id": slot.target_id,
        "slot": slot.slot,
        "attempt": attempt,
        "intent_started_at_utc": contract.serialize_utc(intent_started_at),
    }
    return {
        **unsigned,
        "intent_sha256": hashlib.sha256(contract.canonical_bytes(unsigned)).hexdigest(),
    }


def _validate_inflight(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _error("inflight marker must be a mapping")
    plain = dict(value)
    if set(plain) != _INFLIGHT_KEYS:
        raise _error("inflight marker keys mismatch")
    if (
        type(plain["schema_version"]) is not int
        or plain["schema_version"] != INFLIGHT_SCHEMA_VERSION
        or plain["runner_id"] != contract.RUNNER_ID
    ):
        raise _error("inflight marker identity mismatch")
    if type(plain["evidence_sequence"]) is not int or plain["evidence_sequence"] < 0:
        raise _error("inflight evidence sequence is invalid")
    contract.validate_sha256(
        plain["previous_entry_sha256"], "previous_entry_sha256"
    )
    if type(plain["target_id"]) is not str or not plain["target_id"]:
        raise _error("inflight target identity is invalid")
    if plain["slot"] not in contract.SLOT_LABELS:
        raise _error("inflight slot is invalid")
    if (
        type(plain["attempt"]) is not int
        or not 1 <= plain["attempt"] <= contract.MAXIMUM_ATTEMPTS_PER_SLOT
    ):
        raise _error("inflight attempt is invalid")
    contract.parse_utc(plain["intent_started_at_utc"], "intent_started_at_utc")
    claimed = contract.validate_sha256(plain["intent_sha256"], "intent_sha256")
    unsigned = dict(plain)
    unsigned.pop("intent_sha256")
    if hashlib.sha256(contract.canonical_bytes(unsigned)).hexdigest() != claimed:
        raise _error("inflight marker hash mismatch")
    return plain


def _load_inflight(root: Path) -> Mapping[str, Any] | None:
    path = _inflight_path(root)
    if not path.exists():
        return None
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise _error("could not read inflight marker") from exc
    value = _strict_json(raw, "inflight marker", MAX_INFLIGHT_BYTES)
    return _validate_inflight(value)


def _create_inflight(
    entries: tuple[Mapping[str, Any], ...],
    *,
    slot: contract.CampaignSlot,
    attempt: int,
    intent_started_at: datetime.datetime,
    root: Path,
) -> Mapping[str, Any]:
    intent = _validate_inflight(
        _build_inflight_intent(
            entries,
            slot=slot,
            attempt=attempt,
            intent_started_at=intent_started_at,
        )
    )
    encoded = contract.canonical_bytes(dict(intent))
    _write_exclusive(_inflight_path(root), encoded)
    persisted = _load_inflight(root)
    if persisted is None or dict(persisted) != dict(intent):
        raise _error("inflight marker did not revalidate after durable write")
    return intent


def _remove_inflight(root: Path, expected: Mapping[str, Any]) -> None:
    path = _inflight_path(root)
    persisted = _load_inflight(root)
    if persisted is None:
        raise _error("inflight marker disappeared before outcome commit")
    if dict(persisted) != dict(expected):
        raise _error("inflight marker changed before outcome commit")
    try:
        path.unlink()
        _sync_directory(root)
    except OSError as exc:
        raise _error("could not durably clear inflight marker") from exc


def _intent_matches_pending(
    entries: tuple[Mapping[str, Any], ...], intent: Mapping[str, Any]
) -> bool:
    if len(entries) != intent["evidence_sequence"]:
        return False
    if _previous_hash(entries) != intent["previous_entry_sha256"]:
        return False
    progress = contract.campaign_progress(entries)
    if progress.complete or progress.blocked or progress.next_slot is None:
        return False
    return (
        progress.next_slot.target_id == intent["target_id"]
        and progress.next_slot.slot == intent["slot"]
        and progress.next_attempt == intent["attempt"]
    )


def _intent_matches_recorded_outcome(
    entries: tuple[Mapping[str, Any], ...], intent: Mapping[str, Any]
) -> bool:
    sequence = intent["evidence_sequence"]
    if len(entries) != sequence + 1:
        return False
    outcome = entries[-1]
    if outcome["event_type"] not in {"SLOT_SUCCEEDED", "ATTEMPT_FAILED"}:
        return False
    try:
        intent_started = contract.parse_utc(
            intent["intent_started_at_utc"], "intent_started_at_utc"
        )
        actual_started = contract.parse_utc(
            outcome["attempt_started_at_utc"], "attempt_started_at_utc"
        )
    except contract.PR69PrimaryTimeBasisEvidenceAcquisitionRunnerError:
        return False
    return (
        outcome["sequence"] == sequence + 1
        and outcome["previous_entry_sha256"] == intent["previous_entry_sha256"]
        and outcome["target_id"] == intent["target_id"]
        and outcome["slot"] == intent["slot"]
        and outcome["attempt"] == intent["attempt"]
        and actual_started >= intent_started
    )


def _reconcile_completed_inflight(
    entries: tuple[Mapping[str, Any], ...], *, root: Path
) -> tuple[Mapping[str, Any], ...]:
    intent = _load_inflight(root)
    if intent is None:
        return entries
    if _intent_matches_recorded_outcome(entries, intent):
        _remove_inflight(root, intent)
        return entries
    if _intent_matches_pending(entries, intent):
        raise _error(
            "UNRESOLVED_INFLIGHT_ATTEMPT_REQUIRES_RECONCILIATION: request may "
            "have started without a durable campaign outcome; automatic retry forbidden"
        )
    raise _error(
        "INFLIGHT_ATTEMPT_STATE_CONFLICT: marker and append-only evidence disagree"
    )


def _inflight_status(
    entries: tuple[Mapping[str, Any], ...], *, root: Path
) -> Mapping[str, Any] | None:
    intent = _load_inflight(root)
    if intent is None:
        return None
    if _intent_matches_recorded_outcome(entries, intent):
        reason = "RECORDED_OUTCOME_PENDING_SAFE_MARKER_CLEANUP"
    elif _intent_matches_pending(entries, intent):
        reason = "UNRESOLVED_INFLIGHT_ATTEMPT_REQUIRES_RECONCILIATION"
    else:
        reason = "INFLIGHT_ATTEMPT_STATE_CONFLICT"
    return {
        "reason": reason,
        "target_id": intent["target_id"],
        "slot": intent["slot"],
        "attempt": intent["attempt"],
        "intent_started_at_utc": intent["intent_started_at_utc"],
        "intent_sha256": intent["intent_sha256"],
    }


def _capture_directory(root: Path, slot: contract.CampaignSlot) -> Path:
    target = root / slot.target_id
    directory = target / slot.slot
    if target.parent != root or directory.parent != target:
        raise _error("capture directory escaped frozen root")
    return directory


def _validate_no_unindexed_capture(
    entries: tuple[Mapping[str, Any], ...], *, root: Path
) -> None:
    """Reject any capture-tree state not justified by the append-only journal.

    This scans the entire frozen tree rather than only the next campaign slot. A future
    slot, partial target, extra file/directory, or post-completion orphan is therefore a
    blocker before any subsequent network request can start.
    """
    plan = contract.campaign_slots()
    target_slots: dict[str, set[str]] = {}
    for slot in plan:
        target_slots.setdefault(slot.target_id, set()).add(slot.slot)
    success_keys = {
        (entry["target_id"], entry["slot"])
        for entry in entries
        if entry["event_type"] == "SLOT_SUCCEEDED"
    }
    allowed_root_files = {
        contract.CAMPAIGN_INDEX_FILENAME,
        contract.FAILURE_JOURNAL_FILENAME,
        contract.RUNNER_LOCK_FILENAME,
        INFLIGHT_ATTEMPT_FILENAME,
    }
    try:
        root_children = tuple(root.iterdir())
    except OSError as exc:
        raise _error("campaign capture tree could not be enumerated") from exc

    for child in root_children:
        if child.name in allowed_root_files:
            continue
        if child.name not in target_slots:
            raise _error(
                "UNINDEXED_CAPTURE_REQUIRES_RECONCILIATION: unexpected campaign "
                f"root entry {child.name!r} is not authorized"
            )
        if child.is_symlink() or not child.is_dir():
            raise _error(
                "UNINDEXED_CAPTURE_REQUIRES_RECONCILIATION: target capture entry "
                "must be a non-symlink directory"
            )
        try:
            slot_children = tuple(child.iterdir())
        except OSError as exc:
            raise _error("target capture directory could not be enumerated") from exc
        for slot_child in slot_children:
            key = (child.name, slot_child.name)
            if slot_child.name not in target_slots[child.name] or key not in success_keys:
                raise _error(
                    "UNINDEXED_CAPTURE_REQUIRES_RECONCILIATION: unindexed or "
                    f"unexpected capture slot {child.name}/{slot_child.name} exists"
                )
            if slot_child.is_symlink() or not slot_child.is_dir():
                raise _error(
                    "UNINDEXED_CAPTURE_REQUIRES_RECONCILIATION: indexed capture slot "
                    "must remain a non-symlink directory"
                )
        if not any(target_id == child.name for target_id, _ in success_keys):
            raise _error(
                "UNINDEXED_CAPTURE_REQUIRES_RECONCILIATION: target directory exists "
                "without any indexed successful capture"
            )

    for target_id, slot_label in success_keys:
        directory = root / target_id / slot_label
        if directory.is_symlink() or not directory.is_dir():
            raise _error("indexed capture directory is missing or invalid")


def _load_manifest(path: Path, slot: contract.CampaignSlot) -> tuple[Mapping[str, Any], bytes]:
    _regular_single_link(path, "capture manifest")
    if not path.exists():
        raise _error("capture manifest is missing")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise _error("could not read capture manifest") from exc
    value = _strict_json(raw, "capture manifest", contract.MAX_ENTRY_BYTES)
    checked = contract.validate_manifest(value, slot)
    return checked, raw


def _verify_capture(
    root: Path, slot: contract.CampaignSlot
) -> tuple[Mapping[str, Any], str]:
    directory = _capture_directory(root, slot)
    if directory.is_symlink() or not directory.is_dir():
        raise _error("capture directory is missing or invalid")
    try:
        names = {entry.name for entry in directory.iterdir()}
    except OSError as exc:
        raise _error("capture directory could not be enumerated") from exc
    expected_names = {contract.RAW_BODY_FILENAME, contract.MANIFEST_FILENAME}
    if names != expected_names:
        raise _error("capture directory contains missing or unexpected evidence files")
    raw_path = directory / contract.RAW_BODY_FILENAME
    manifest_path = directory / contract.MANIFEST_FILENAME
    _regular_single_link(raw_path, "raw response")
    if not raw_path.exists():
        raise _error("raw response is missing")
    manifest, manifest_raw = _load_manifest(manifest_path, slot)
    try:
        raw = raw_path.read_bytes()
    except OSError as exc:
        raise _error("could not read raw response") from exc
    if (
        len(raw) != manifest["raw_size"]
        or hashlib.sha256(raw).hexdigest() != manifest["raw_sha256"]
    ):
        raise _error("raw response no longer matches capture manifest")
    return manifest, hashlib.sha256(manifest_raw).hexdigest()


def _verify_indexed_captures(
    root: Path, entries: tuple[Mapping[str, Any], ...]
) -> None:
    plan = contract.campaign_slots()
    successes = [entry for entry in entries if entry["event_type"] == "SLOT_SUCCEEDED"]
    for index, entry in enumerate(successes):
        manifest, manifest_hash = _verify_capture(root, plan[index])
        detail = entry["detail"]
        if (
            entry["attempt"] != manifest["attempt"]
            or detail["manifest_sha256"] != manifest_hash
            or detail["raw_sha256"] != manifest["raw_sha256"]
            or detail["raw_size"] != manifest["raw_size"]
            or detail["observed_at_utc"] != manifest["observed_at_utc"]
        ):
            raise _error("campaign index does not match durable capture evidence")


def write_capture(
    result: FetchResult, *, repository_root: Path
) -> tuple[Mapping[str, Any], str]:
    if not isinstance(result, FetchResult):
        raise _error("capture result has wrong type")
    if type(result.raw_body) is not bytes or not result.raw_body:
        raise _error("capture raw body must be non-empty exact bytes")
    checked = contract.validate_manifest(result.manifest, result.slot)
    if (
        checked["attempt"] != result.attempt
        or checked["raw_size"] != len(result.raw_body)
        or checked["raw_sha256"] != hashlib.sha256(result.raw_body).hexdigest()
    ):
        raise _error("capture result raw body differs from its manifest")
    root = _ensure_campaign_root(repository_root=repository_root)
    target = root / result.slot.target_id
    _ensure_directory_tree(target, boundary=root)
    directory = _capture_directory(root, result.slot)
    if directory.exists() or directory.is_symlink():
        raise _error("capture slot already exists and will not be overwritten")
    directory.mkdir()
    _sync_directory(target)
    _sync_directory(directory)
    raw_path = directory / contract.RAW_BODY_FILENAME
    manifest_path = directory / contract.MANIFEST_FILENAME
    _write_exclusive(raw_path, result.raw_body)
    manifest_raw = contract.canonical_bytes(dict(checked))
    _write_exclusive(manifest_path, manifest_raw)
    _sync_directory(directory)
    return checked, hashlib.sha256(manifest_raw).hexdigest()


def _record_failure(
    entries: tuple[Mapping[str, Any], ...],
    *,
    slot: contract.CampaignSlot,
    attempt: int,
    attempt_started_at: datetime.datetime,
    recorded_at: datetime.datetime,
    error_kind: str,
    error_message: str,
    repository_root: Path,
) -> tuple[Mapping[str, Any], ...]:
    entry = contract.build_attempt_failed_entry(
        entries,
        slot=slot,
        attempt=attempt,
        attempt_started_at=attempt_started_at,
        recorded_at=recorded_at,
        error_kind=error_kind,
        error_message=error_message,
    )
    return _append_entry(entries, entry, repository_root=repository_root)


def _record_block(
    entries: tuple[Mapping[str, Any], ...],
    *,
    slot: contract.CampaignSlot,
    recorded_at: datetime.datetime,
    error_kind: str,
    error_message: str,
    repository_root: Path,
) -> tuple[Mapping[str, Any], ...]:
    entry = contract.build_slot_blocked_entry(
        entries,
        slot=slot,
        recorded_at=recorded_at,
        error_kind=error_kind,
        error_message=error_message,
    )
    return _append_entry(entries, entry, repository_root=repository_root)


def _validate_clock_not_before_durable_evidence(
    entries: tuple[Mapping[str, Any], ...], now: datetime.datetime
) -> None:
    if not entries:
        return
    current = contract.parse_utc(contract.serialize_utc(now), "now")
    durable_times: list[datetime.datetime] = []
    for entry in entries:
        durable_times.append(
            contract.parse_utc(entry["recorded_at_utc"], "recorded_at_utc")
        )
        if entry["attempt_started_at_utc"] is not None:
            durable_times.append(
                contract.parse_utc(
                    entry["attempt_started_at_utc"], "attempt_started_at_utc"
                )
            )
        if entry["event_type"] == "SLOT_SUCCEEDED":
            durable_times.append(
                contract.parse_utc(
                    entry["detail"]["observed_at_utc"], "observed_at_utc"
                )
            )
    latest = max(durable_times)
    if current < latest:
        raise contract.PR69PrimaryTimeBasisEvidenceAcquisitionRunnerError(
            "runner clock precedes latest durable campaign evidence timestamp"
        )


def _wait_until_eligible(
    entries: tuple[Mapping[str, Any], ...],
    *,
    clock: Callable[[], datetime.datetime],
    sleeper: Callable[[float], None],
) -> datetime.datetime:
    for _ in range(MAX_WAIT_RECHECKS):
        now = clock()
        _validate_clock_not_before_durable_evidence(entries, now)
        wait = contract.seconds_until_next_request_eligible(entries, now)
        if wait <= 0:
            return now
        sleeper(wait)
    raise _error("runner clock did not advance through required wait interval")


def _validate_request_still_eligible(
    entries: tuple[Mapping[str, Any], ...],
    *,
    intent_started_at: datetime.datetime,
    request_started_at: datetime.datetime,
) -> None:
    """Revalidate timing after durable inflight persistence and before network I/O."""
    intent = contract.parse_utc(
        contract.serialize_utc(intent_started_at), "intent_started_at"
    )
    current = contract.parse_utc(
        contract.serialize_utc(request_started_at), "request_started_at"
    )
    if current < intent:
        raise contract.PR69PrimaryTimeBasisEvidenceAcquisitionRunnerError(
            "runner clock precedes durable inflight intent timestamp"
        )
    _validate_clock_not_before_durable_evidence(entries, current)
    wait = contract.seconds_until_next_request_eligible(entries, current)
    if wait > 0:
        raise contract.PR69PrimaryTimeBasisEvidenceAcquisitionRunnerError(
            "request lost timing eligibility after durable inflight persistence"
        )


def fetch_primary_evidence(
    *,
    slot: contract.CampaignSlot,
    attempt: int,
    request_started_at: datetime.datetime,
    clock: Callable[[], datetime.datetime] = _clock,
    connection_factory: Callable[..., Any] | None = None,
) -> FetchResult:
    if type(attempt) is not int or not 1 <= attempt <= contract.MAXIMUM_ATTEMPTS_PER_SLOT:
        raise PrimaryEvidenceRequestError("INVALID_ATTEMPT", "attempt is outside frozen bounds")
    started = request_started_at.astimezone(UTC)
    factory = connection_factory or http.client.HTTPSConnection
    connection: Any = None
    try:
        context = ssl.create_default_context()
        try:
            connection = factory(
                "www.football-data.co.uk",
                443,
                timeout=NETWORK_TIMEOUT_SECONDS,
                context=context,
            )
        except TypeError:
            connection = factory(
                "www.football-data.co.uk", 443, NETWORK_TIMEOUT_SECONDS
            )
        connection.putrequest("GET", slot.path, skip_accept_encoding=True)
        for name, value in REQUEST_HEADERS:
            connection.putheader(name, value)
        connection.endheaders()
        response = connection.getresponse()
        status = int(response.status)
        headers = [
            (str(name).lower(), str(value))
            for name, value in response.getheaders()
            if str(name).lower() in SELECTED_RESPONSE_HEADERS
        ]
        if status != 200:
            raise PrimaryEvidenceRequestError(
                "HTTP_STATUS", f"unexpected HTTP status {status}"
            )
        content_types = [value for name, value in headers if name == "content-type"]
        if len(content_types) != 1:
            raise PrimaryEvidenceRequestError(
                "CONTENT_TYPE", "response must contain exactly one Content-Type"
            )
        media_type = content_types[0].split(";", 1)[0].strip().lower()
        if not media_type.startswith(slot.content_type_prefix.lower()):
            raise PrimaryEvidenceRequestError(
                "CONTENT_TYPE", f"unexpected Content-Type {content_types[0]!r}"
            )
        encodings = [
            value.strip().lower()
            for name, value in headers
            if name == "content-encoding"
        ]
        if any(value not in ("", "identity") for value in encodings):
            raise PrimaryEvidenceRequestError(
                "CONTENT_ENCODING", "compressed response is not admissible"
            )
        lengths = [value.strip() for name, value in headers if name == "content-length"]
        declared: int | None = None
        if lengths:
            if len(lengths) != 1 or not lengths[0].isdigit():
                raise PrimaryEvidenceRequestError(
                    "CONTENT_LENGTH", "invalid Content-Length"
                )
            declared = int(lengths[0])
            if declared > contract.MAX_RESPONSE_BYTES:
                raise PrimaryEvidenceRequestError(
                    "BODY_TOO_LARGE", "declared response exceeds frozen limit"
                )
        raw = response.read(contract.MAX_RESPONSE_BYTES + 1)
        if not raw:
            raise PrimaryEvidenceRequestError(
                "EMPTY_BODY", "primary evidence response is empty"
            )
        if len(raw) > contract.MAX_RESPONSE_BYTES:
            raise PrimaryEvidenceRequestError(
                "BODY_TOO_LARGE", "response exceeds frozen limit"
            )
        if declared is not None and declared != len(raw):
            raise PrimaryEvidenceRequestError(
                "CONTENT_LENGTH", "Content-Length does not match exact body"
            )
        completed = clock().astimezone(UTC)
        observed = clock().astimezone(UTC)
        manifest = {
            "schema_version": contract.SCHEMA_VERSION,
            "runner_id": contract.RUNNER_ID,
            "protocol_sha256": contract.PR124_PROTOCOL_SHA256,
            "target_id": slot.target_id,
            "slot": slot.slot,
            "attempt": attempt,
            "requested_url": slot.requested_url,
            "final_url": slot.requested_url,
            "request_method": "GET",
            "request_headers": [list(item) for item in REQUEST_HEADERS],
            "redirect_chain": [],
            "request_started_at_utc": contract.serialize_utc(started),
            "response_completed_at_utc": contract.serialize_utc(completed),
            "observed_at_utc": contract.serialize_utc(observed),
            "http_status": 200,
            "tls_verified": True,
            "response_headers": [list(item) for item in headers],
            "raw_filename": contract.RAW_BODY_FILENAME,
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "raw_size": len(raw),
        }
        return FetchResult(
            slot=slot,
            attempt=attempt,
            raw_body=raw,
            manifest=contract.validate_manifest(manifest, slot),
        )
    except PrimaryEvidenceRequestError:
        raise
    except (OSError, ssl.SSLError, http.client.HTTPException, TimeoutError) as exc:
        raise PrimaryEvidenceRequestError(
            "NETWORK_FAILURE", _bounded_failure(exc)
        ) from exc
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def _execute_next_slot_locked(
    *,
    repository_root: Path,
    root: Path,
    fetcher: Callable[..., FetchResult],
    clock: Callable[[], datetime.datetime],
    sleeper: Callable[[float], None],
) -> contract.CampaignProgress:
    """Internal orchestration seam.

    Trusted callers must pass ``fetch_primary_evidence``. Tests may exercise the state
    machine with a synthetic fetcher only by calling this private seam in temporary roots.
    """
    entries = load_campaign_entries(repository_root=repository_root, create_root=True)
    _verify_indexed_captures(root, entries)
    entries = _reconcile_completed_inflight(entries, root=root)
    _validate_no_unindexed_capture(entries, root=root)
    progress = contract.campaign_progress(entries)
    if progress.complete:
        return progress
    if progress.blocked or progress.next_slot is None or progress.next_attempt is None:
        raise _error(f"campaign is blocked: {progress.block_reason}")

    while True:
        progress = contract.campaign_progress(entries)
        if progress.blocked or progress.next_slot is None or progress.next_attempt is None:
            raise _error(f"campaign is blocked: {progress.block_reason}")
        slot = progress.next_slot
        attempt = progress.next_attempt
        try:
            intent_time = _wait_until_eligible(
                entries, clock=clock, sleeper=sleeper
            )
        except contract.PR69PrimaryTimeBasisEvidencePairWindowError as exc:
            entries = _record_block(
                entries,
                slot=slot,
                recorded_at=clock(),
                error_kind=exc.reason,
                error_message=str(exc),
                repository_root=repository_root,
            )
            raise _error(f"campaign pair window blocked: {exc}") from exc

        intent = _create_inflight(
            entries,
            slot=slot,
            attempt=attempt,
            intent_started_at=intent_time,
            root=root,
        )
        attempt_started_at = clock().astimezone(UTC)
        try:
            _validate_request_still_eligible(
                entries,
                intent_started_at=intent_time,
                request_started_at=attempt_started_at,
            )
        except contract.PR69PrimaryTimeBasisEvidencePairWindowError as exc:
            _remove_inflight(root, intent)
            entries = _record_block(
                entries,
                slot=slot,
                recorded_at=attempt_started_at,
                error_kind=exc.reason,
                error_message=str(exc),
                repository_root=repository_root,
            )
            raise _error(
                f"campaign pair window blocked before request: {exc}"
            ) from exc
        except contract.PR69PrimaryTimeBasisEvidenceAcquisitionRunnerError:
            _remove_inflight(root, intent)
            raise

        try:
            result = fetcher(
                slot=slot,
                attempt=attempt,
                request_started_at=attempt_started_at,
                clock=clock,
            )
        except PrimaryEvidenceRequestError as exc:
            entries = _record_failure(
                entries,
                slot=slot,
                attempt=attempt,
                attempt_started_at=attempt_started_at,
                recorded_at=clock(),
                error_kind=exc.kind,
                error_message=str(exc),
                repository_root=repository_root,
            )
            _remove_inflight(root, intent)
            progress = contract.campaign_progress(entries)
            if progress.blocked:
                raise _error(f"campaign is blocked: {progress.block_reason}") from exc
            continue

        observed = contract.parse_utc(
            result.manifest["observed_at_utc"], "observed_at_utc"
        )
        try:
            if slot.slot == "B":
                # Validate pair timing before publishing raw bytes for this slot. A response
                # outside the window remains a failed request attempt, not a valid capture.
                contract.build_slot_succeeded_entry(
                    entries,
                    slot=slot,
                    attempt=attempt,
                    attempt_started_at=attempt_started_at,
                    recorded_at=max(clock(), observed),
                    manifest_sha256=contract.manifest_sha256(result.manifest),
                    raw_sha256=result.manifest["raw_sha256"],
                    raw_size=result.manifest["raw_size"],
                    observed_at=observed,
                )
        except contract.PR69PrimaryTimeBasisEvidencePairWindowError as exc:
            entries = _record_failure(
                entries,
                slot=slot,
                attempt=attempt,
                attempt_started_at=attempt_started_at,
                recorded_at=clock(),
                error_kind=exc.reason,
                error_message=str(exc),
                repository_root=repository_root,
            )
            _remove_inflight(root, intent)
            progress = contract.campaign_progress(entries)
            if exc.reason == "PAIR_OBSERVATION_TOO_LATE" and not progress.blocked:
                entries = _record_block(
                    entries,
                    slot=slot,
                    recorded_at=clock(),
                    error_kind="PAIR_WINDOW_EXPIRED_AFTER_RESPONSE",
                    error_message=(
                        "slot B response arrived after frozen 3600-second pair window"
                    ),
                    repository_root=repository_root,
                )
                raise _error("campaign pair window expired after response") from exc
            if progress.blocked:
                raise _error(f"campaign is blocked: {progress.block_reason}") from exc
            continue

        # From this point onward, any exception is an indeterminate durability outcome.
        # The inflight marker intentionally remains so restart cannot issue a duplicate
        # request. No failure entry is fabricated when publication state is uncertain.
        manifest, manifest_hash = write_capture(
            result, repository_root=repository_root
        )
        entry = contract.build_slot_succeeded_entry(
            entries,
            slot=slot,
            attempt=attempt,
            attempt_started_at=attempt_started_at,
            recorded_at=clock(),
            manifest_sha256=manifest_hash,
            raw_sha256=manifest["raw_sha256"],
            raw_size=manifest["raw_size"],
            observed_at=observed,
        )
        entries = _append_entry(entries, entry, repository_root=repository_root)
        _remove_inflight(root, intent)
        return contract.campaign_progress(entries)


def execute_next_campaign_slot(
    *,
    execute_live_network: bool,
    repository_root: Path | None = None,
    clock: Callable[[], datetime.datetime] = _clock,
    sleeper: Callable[[float], None] | None = None,
) -> contract.CampaignProgress:
    """Execute one trusted campaign slot using only reviewed transport and timing."""
    if execute_live_network is not True:
        raise _error("live network execution requires exact True authorization")
    if clock is not _clock or (sleeper is not None and sleeper is not time.sleep):
        raise _error("trusted live execution forbids clock or sleeper injection")
    contract.runner_descriptor()
    repository = Path(repository_root or _repository_root()).resolve(strict=True)
    if sleeper is None:
        sleeper = time.sleep
    with campaign_lock(repository_root=repository) as root:
        return _execute_next_slot_locked(
            repository_root=repository,
            root=root,
            fetcher=fetch_primary_evidence,
            clock=_clock,
            sleeper=time.sleep,
        )


def execute_campaign(
    *,
    execute_live_network: bool,
    repository_root: Path | None = None,
    max_successful_slots: int | None = None,
    clock: Callable[[], datetime.datetime] = _clock,
    sleeper: Callable[[float], None] | None = None,
) -> contract.CampaignProgress:
    """Execute the trusted reviewed campaign using only reviewed transport and timing."""
    if execute_live_network is not True:
        raise _error("live network execution requires exact True authorization")
    if clock is not _clock or (sleeper is not None and sleeper is not time.sleep):
        raise _error("trusted live execution forbids clock or sleeper injection")
    if max_successful_slots is not None and (
        type(max_successful_slots) is not int or max_successful_slots <= 0
    ):
        raise _error("max_successful_slots must be an exact positive integer")
    contract.runner_descriptor()
    repository = Path(repository_root or _repository_root()).resolve(strict=True)
    if sleeper is None:
        sleeper = time.sleep
    with campaign_lock(repository_root=repository) as root:
        entries = load_campaign_entries(repository_root=repository, create_root=True)
        _verify_indexed_captures(root, entries)
        entries = _reconcile_completed_inflight(entries, root=root)
        _validate_no_unindexed_capture(entries, root=root)
        initial = contract.campaign_progress(entries)
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
                root=root,
                fetcher=fetch_primary_evidence,
                clock=_clock,
                sleeper=time.sleep,
            )
        return progress


def campaign_status(*, repository_root: Path | None = None) -> Mapping[str, Any]:
    contract.runner_descriptor()
    root = validate_campaign_root(repository_root=repository_root)
    entries = load_campaign_entries(repository_root=repository_root, create_root=False)
    progress = contract.campaign_progress(entries)
    inflight = None if not root.exists() else _inflight_status(entries, root=root)
    if root.exists():
        _verify_indexed_captures(root, entries)
        if inflight is None:
            try:
                _validate_no_unindexed_capture(entries, root=root)
            except PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError as exc:
                inflight = {
                    "reason": "UNINDEXED_CAPTURE_REQUIRES_RECONCILIATION",
                    "detail": str(exc),
                }
    blocked = progress.blocked or inflight is not None
    reason = progress.block_reason if progress.blocked else (
        None if inflight is None else inflight["reason"]
    )
    pairs: list[dict[str, Any]] = []
    for slot in contract.campaign_slots():
        if slot.slot != "A":
            continue
        first = next((
            contract.parse_utc(entry["detail"]["observed_at_utc"], "observed_at_utc")
            for entry in entries
            if entry["event_type"] == "SLOT_SUCCEEDED"
            and entry["target_id"] == slot.target_id
            and entry["slot"] == "A"
        ), None)
        second = next((
            contract.parse_utc(entry["detail"]["observed_at_utc"], "observed_at_utc")
            for entry in entries
            if entry["event_type"] == "SLOT_SUCCEEDED"
            and entry["target_id"] == slot.target_id
            and entry["slot"] == "B"
        ), None)
        first_entry = next((
            entry for entry in entries
            if entry["event_type"] == "SLOT_SUCCEEDED"
            and entry["target_id"] == slot.target_id
            and entry["slot"] == "A"
        ), None)
        second_entry = next((
            entry for entry in entries
            if entry["event_type"] == "SLOT_SUCCEEDED"
            and entry["target_id"] == slot.target_id
            and entry["slot"] == "B"
        ), None)
        pairs.append({
            "target_id": slot.target_id,
            "slot_a_raw_sha256": (
                None if first_entry is None else first_entry["detail"]["raw_sha256"]
            ),
            "slot_b_raw_sha256": (
                None if second_entry is None else second_entry["detail"]["raw_sha256"]
            ),
            "raw_pair_identical": (
                None if first_entry is None or second_entry is None
                else first_entry["detail"]["raw_sha256"]
                == second_entry["detail"]["raw_sha256"]
            ),
            "separation_seconds": (
                None if first is None or second is None
                else (second - first).total_seconds()
            ),
        })
    return {
        "runner_id": contract.RUNNER_ID,
        "runner_state": contract.RUNNER_STATE,
        "campaign_runner_implemented": True,
        "completed_slots": progress.completed_slots,
        "total_slots": progress.total_slots,
        "complete": progress.complete and inflight is None,
        "blocked": blocked,
        "block_reason": reason,
        "next_slot": (
            None if progress.next_slot is None else {
                "ordinal": progress.next_slot.ordinal,
                "target_id": progress.next_slot.target_id,
                "slot": progress.next_slot.slot,
                "attempt": progress.next_attempt,
            }
        ),
        "inflight_attempt": inflight,
        "pair_drift_table": pairs,
        "network_acquisition_performed_by_this_status_command": False,
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
        "next_required_boundary": contract.NEXT_REQUIRED_BOUNDARY,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Execute or inspect the exact reviewed PR69 primary time-basis evidence "
            "acquisition campaign."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--status",
        action="store_true",
        help="revalidate campaign state without network access",
    )
    mode.add_argument(
        "--execute-reviewed-protocol",
        action="store_true",
        help="explicitly authorize the frozen eight-slot live network campaign",
    )
    parser.add_argument(
        "--max-successful-slots",
        type=int,
        default=None,
        help="optional positive chunk size for resumable live execution",
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=None,
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.status and args.max_successful_slots is not None:
        parser.error("--max-successful-slots is valid only during live execution")
    try:
        if args.status:
            result: Any = campaign_status(repository_root=args.repository_root)
        else:
            progress = execute_campaign(
                execute_live_network=True,
                repository_root=args.repository_root,
                max_successful_slots=args.max_successful_slots,
            )
            result = {
                **dict(campaign_status(repository_root=args.repository_root)),
                "completed_slots_after_execution": progress.completed_slots,
            }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (
        PR69PrimaryTimeBasisEvidenceAcquisitionLiveRunnerError,
        contract.PR69PrimaryTimeBasisEvidenceAcquisitionRunnerError,
    ) as exc:
        parser.exit(1, f"campaign runner failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())