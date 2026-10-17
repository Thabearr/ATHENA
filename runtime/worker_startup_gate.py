"""Exact worker admission gate written only after process ownership is bound."""
from __future__ import annotations

import json
import hashlib
import hmac
import os
from pathlib import Path
import stat
import time
from typing import Any

from domain.run_contracts import canonical_json_bytes
from runtime.worker_launcher import WorkerCommand


POLICY_ID = "ATHENA_E3_WORKER_STARTUP_GATE_V1"
FILENAME = "athena-worker-startup-gate.json"
_OWNER_KEYS = {"attempt_id", "worker_instance_id", "lease_sha256"}
_GATE_FIELDS = {
    "policy_id", "run_id", "request_sha256", "envelope_sha256",
    "command_sha256", "operation", "mode", "release_identity_kind",
    "release_identity_id", "pid", "attempt_id", "worker_instance_id",
    "lease_sha256", "process_locator", "authenticator_sha256",
}


class StartupGateError(ValueError):
    """The exact E3 worker handoff gate is missing or contradictory."""


def read_gate_document(path: Path) -> tuple[dict[str, Any], bytes]:
    """Read one bounded canonical gate without following links or junctions."""
    if not isinstance(path, Path) or path.name != FILENAME:
        raise StartupGateError("startup gate path is not the fixed filename")
    if path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)()):
        raise StartupGateError("startup gate must not be a link")
    descriptor = -1
    try:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise StartupGateError("startup gate must be a regular file")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            raw = stream.read(65537)
    except StartupGateError:
        raise
    except OSError as exc:
        raise StartupGateError("startup gate could not be read safely") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(raw) > 65536:
        raise StartupGateError("startup gate exceeds its reviewed byte bound")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StartupGateError("startup gate JSON is invalid") from exc
    if (type(value) is not dict or set(value) != _GATE_FIELDS
            or canonical_json_bytes(value) != raw):
        raise StartupGateError("startup gate bytes are not one canonical document")
    return value, raw


def gate_bytes(*, command: WorkerCommand, pid: int, owner: dict[str, str],
               process_locator: dict[str, Any], lease_token: str,
               envelope_sha256: str) -> bytes:
    if type(command) is not WorkerCommand or type(pid) is not int or pid <= 0:
        raise StartupGateError("exact worker command and positive PID are required")
    if type(owner) is not dict or set(owner) != _OWNER_KEYS:
        raise StartupGateError("worker owner identity is not exact")
    if any(type(owner[key]) is not str or not owner[key] for key in owner):
        raise StartupGateError("worker owner identity is invalid")
    if (type(lease_token) is not str or not lease_token
            or hashlib.sha256(lease_token.encode("utf-8")).hexdigest() != owner["lease_sha256"]):
        raise StartupGateError("worker startup lease authenticator is invalid")
    if (type(envelope_sha256) is not str or len(envelope_sha256) != 64
            or any(char not in "0123456789abcdef" for char in envelope_sha256)):
        raise StartupGateError("worker startup envelope identity is invalid")
    if (type(process_locator) is not dict or process_locator.get("pid") != pid
            or process_locator.get("attempt_id") != owner["attempt_id"]
            or process_locator.get("worker_instance_id") != owner["worker_instance_id"]
            or process_locator.get("lease_sha256") != owner["lease_sha256"]):
        raise StartupGateError("process locator does not bind the launched PID")
    payload = {
        "policy_id": POLICY_ID,
        "run_id": _run_id_from_path(command.run_directory),
        "request_sha256": command.request_artifact_id,
        "envelope_sha256": envelope_sha256,
        "command_sha256": hashlib.sha256(command.canonical_bytes).hexdigest(),
        "operation": command.operation,
        "mode": command.mode,
        "release_identity_kind": command.release_identity_kind,
        "release_identity_id": command.release_identity_id,
        "pid": pid,
        **owner,
        "process_locator": process_locator,
    }
    mac = hmac.new(lease_token.encode("utf-8"), canonical_json_bytes(payload), hashlib.sha256).hexdigest()
    return canonical_json_bytes({**payload, "authenticator_sha256": mac})


def publish_gate(path: Path, raw: bytes) -> None:
    if not isinstance(path, Path) or path.name != FILENAME or type(raw) is not bytes:
        raise StartupGateError("startup gate destination is not exact")
    if path.is_symlink() or path.exists():
        raise StartupGateError("startup gate already exists or is linked")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def wait_for_gate(command: WorkerCommand, *, resources: Any,
                  timeout: float = 20.0,
                  sleeper=time.sleep, monotonic=time.monotonic) -> dict[str, Any]:
    """Block product work until the exact DB owner and process gate authenticate."""
    from runtime.resources import ResourceResolver

    if (type(command) is not WorkerCommand or type(resources) is not ResourceResolver
            or type(timeout) not in {int, float} or not 0 < timeout <= 60):
        raise StartupGateError("startup gate arguments are outside the bounded contract")
    path = command.run_directory / FILENAME
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)()):
            raise StartupGateError("startup gate must not be a link")
        try:
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags)
            try:
                if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                    raise StartupGateError("startup gate must be a regular file")
                with os.fdopen(descriptor, "rb") as stream:
                    descriptor = -1
                    raw = stream.read(65537)
                if len(raw) > 65536:
                    raise StartupGateError("startup gate exceeds its reviewed byte bound")
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
        except FileNotFoundError:
            sleeper(0.05)
            continue
        except StartupGateError:
            raise
        except OSError as exc:
            raise StartupGateError("startup gate could not be read safely") from exc
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StartupGateError("startup gate JSON is invalid") from exc
        if (type(value) is not dict or set(value) != _GATE_FIELDS
                or canonical_json_bytes(value) != raw
                or value["policy_id"] != POLICY_ID
                or value["run_id"] != _run_id_from_path(command.run_directory)
                or value["request_sha256"] != command.request_artifact_id
                or value["command_sha256"] != hashlib.sha256(command.canonical_bytes).hexdigest()
                or value["operation"] != command.operation
                or value["mode"] != command.mode
                or value["release_identity_kind"] != command.release_identity_kind
                or value["release_identity_id"] != command.release_identity_id
                or value["pid"] != os.getpid()
                or type(value["attempt_id"]) is not str or not value["attempt_id"]
                or type(value["worker_instance_id"]) is not str or not value["worker_instance_id"]
                or type(value["lease_sha256"]) is not str
                or len(value["lease_sha256"]) != 64
                or any(char not in "0123456789abcdef" for char in value["lease_sha256"])
                or type(value["process_locator"]) is not dict
                or value["process_locator"].get("pid") != os.getpid()
                or value["process_locator"].get("attempt_id") != value["attempt_id"]
                or value["process_locator"].get("worker_instance_id") != value["worker_instance_id"]
                or value["process_locator"].get("lease_sha256") != value["lease_sha256"]):
            raise StartupGateError("startup gate does not bind this worker and request")
        from database.run_repository import DurableRunRepository
        try:
            data_root = _data_root_from_path(command.run_directory)
            repository = DurableRunRepository.for_worker_data_root(resources, data_root)
            repository.verify_worker_startup_gate(command=command, gate=value, gate_bytes=raw)
        except Exception as exc:
            raise StartupGateError("startup gate owner or durable admission is invalid") from exc
        return value
    raise StartupGateError("process ownership was not bound before worker startup timeout")


def _run_id_from_path(path: Path) -> str:
    # Command directories are <data-root>/runs/<run-id>/<request-sha256>.
    run_id = path.parent.name
    if not run_id or run_id in {".", ".."} or "/" in run_id or "\\" in run_id:
        raise StartupGateError("worker run directory has no exact run identity")
    return run_id


def _data_root_from_path(path: Path) -> Path:
    """Resolve only the reviewed <data-root>/runs/<run-id>/<request-sha> shape."""
    if (not isinstance(path, Path) or len(path.parents) < 3
            or path.parent.parent.name != "runs"):
        raise StartupGateError("worker run directory is outside the product data-root layout")
    root = path.parents[2]
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise StartupGateError("worker data root is not a regular directory")
    return root


__all__ = [
    "FILENAME", "POLICY_ID", "StartupGateError", "gate_bytes", "publish_gate",
    "read_gate_document", "wait_for_gate",
]
