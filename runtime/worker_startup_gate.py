"""Exact worker admission gate written only after process ownership is bound."""
from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import Any

from domain.run_contracts import canonical_json_bytes
from runtime.worker_launcher import WorkerCommand


POLICY_ID = "ATHENA_E3_WORKER_STARTUP_GATE_V1"
FILENAME = "athena-worker-startup-gate.json"
_OWNER_KEYS = {"attempt_id", "worker_instance_id", "lease_sha256"}


class StartupGateError(ValueError):
    """The exact E3 worker handoff gate is missing or contradictory."""


def gate_bytes(*, command: WorkerCommand, pid: int, owner: dict[str, str],
               process_locator: dict[str, Any]) -> bytes:
    if type(command) is not WorkerCommand or type(pid) is not int or pid <= 0:
        raise StartupGateError("exact worker command and positive PID are required")
    if type(owner) is not dict or set(owner) != _OWNER_KEYS:
        raise StartupGateError("worker owner identity is not exact")
    if any(type(owner[key]) is not str or not owner[key] for key in owner):
        raise StartupGateError("worker owner identity is invalid")
    if type(process_locator) is not dict or process_locator.get("pid") != pid:
        raise StartupGateError("process locator does not bind the launched PID")
    return canonical_json_bytes({
        "policy_id": POLICY_ID,
        "run_id": _run_id_from_path(command.run_directory),
        "request_sha256": command.request_artifact_id,
        "pid": pid,
        **owner,
        "process_locator": process_locator,
    })


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


def wait_for_gate(command: WorkerCommand, *, timeout: float = 20.0,
                  sleeper=time.sleep, monotonic=time.monotonic) -> dict[str, Any]:
    """Block worker authority until the parent has durably bound its process."""
    if type(command) is not WorkerCommand or type(timeout) not in {int, float} or not 0 < timeout <= 60:
        raise StartupGateError("startup gate arguments are outside the bounded contract")
    path = command.run_directory / FILENAME
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if path.is_symlink():
            raise StartupGateError("startup gate must not be a link")
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            sleeper(0.05)
            continue
        except OSError as exc:
            raise StartupGateError("startup gate could not be read safely") from exc
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StartupGateError("startup gate JSON is invalid") from exc
        keys = {"policy_id", "run_id", "request_sha256", "pid", "attempt_id",
                "worker_instance_id", "lease_sha256", "process_locator"}
        if (type(value) is not dict or set(value) != keys
                or canonical_json_bytes(value) != raw
                or value["policy_id"] != POLICY_ID
                or value["run_id"] != _run_id_from_path(command.run_directory)
                or value["request_sha256"] != command.request_artifact_id
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
        from services.worker_process_control import WorkerProcessControl
        owner = {
            "run_id": value["run_id"],
            "attempt_id": value["attempt_id"],
            "worker_instance_id": value["worker_instance_id"],
            "lease_sha256": value["lease_sha256"],
        }
        if WorkerProcessControl.state(value["process_locator"], owner) != "ACTIVE":
            raise StartupGateError("startup gate process identity is stale or unowned")
        return value
    raise StartupGateError("process ownership was not bound before worker startup timeout")


def _run_id_from_path(path: Path) -> str:
    # Command directories are <data-root>/runs/<run-id>/<request-sha256>.
    run_id = path.parent.name
    if not run_id or run_id in {".", ".."} or "/" in run_id or "\\" in run_id:
        raise StartupGateError("worker run directory has no exact run identity")
    return run_id


__all__ = ["FILENAME", "POLICY_ID", "StartupGateError", "gate_bytes", "publish_gate", "wait_for_gate"]
