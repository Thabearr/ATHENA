"""Reviewed, allowlisted process launch boundary for ATHENA workers.

This module owns process transport only.  It does not decide business success,
retry, or Current Shadow timeout policy.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Sequence

from domain.run_contracts import RunContractError, RunRequest, canonical_json_bytes
from domain.execution_envelope import ExecutionEnvelope, ExecutionEnvelopeError
from runtime.release_identity import (
    DevelopmentCheckoutIdentity,
    InstalledReleaseIdentity,
    ReleaseIdentityError,
    ReleaseManifestError,
    verify_development_checkout,
    verify_installed_release,
)
from runtime.resources import ResourceResolver, WritableRoots


WORKER_COMMAND_SCHEMA_VERSION = 1
WORKER_COMMAND_POLICY_ID = "ATHENA_WORKER_COMMAND_V1"
WORKER_COMMAND_FILENAME = "athena-worker-command.json"
WORKER_REQUEST_FILENAME = "athena-run-request.json"
WORKER_ENVELOPE_FILENAME = "athena-execution-envelope-v2.json"
WORKER_OFFLINE_PROBE_FILENAME = "athena-worker-offline-probe.json"
WORKER_PROVENANCE_FILENAME = "athena-worker-launch-provenance.json"
WORKER_OPERATIONS = ("CURRENT_SHADOW_REQUEST", "OFFLINE_IDENTITY_PROBE")
WORKER_MODE_BY_OPERATION = {
    "CURRENT_SHADOW_REQUEST": "research_shadow",
    "OFFLINE_IDENTITY_PROBE": "offline_identity_probe",
}

_SHA1_RE = re.compile(r"^[0-9a-f]{40}$", re.ASCII)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_COMMAND_FIELDS = frozenset(
    {
        "schema_version",
        "policy_id",
        "operation",
        "mode",
        "run_directory",
        "request_artifact_id",
        "envelope_artifact_id",
        "release_identity_kind",
        "release_identity_id",
    }
)


class WorkerLaunchError(ValueError):
    """The reviewed worker command or its bound local inputs are invalid."""


def _reject_constant(value: str) -> None:
    raise WorkerLaunchError(f"non-finite JSON constant is forbidden: {value}")


def _strict_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise WorkerLaunchError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _is_link_or_junction(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        checker = getattr(path, "is_junction", None)
        return bool(checker()) if callable(checker) else False
    except OSError as exc:
        raise WorkerLaunchError("filesystem link state could not be checked") from exc


def _reject_link_components(path: Path) -> None:
    if not path.is_absolute() or any(part == ".." for part in path.parts):
        raise WorkerLaunchError("path must be absolute and contain no traversal")
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current = current / component
        if current.exists() or current.is_symlink():
            if _is_link_or_junction(current):
                raise WorkerLaunchError("path must not contain a symlink or junction")


def _resolved_directory(path_value: Any, label: str) -> Path:
    if not isinstance(path_value, Path):
        raise WorkerLaunchError(f"{label} must be pathlib.Path")
    _reject_link_components(path_value)
    try:
        resolved = path_value.resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise WorkerLaunchError(f"{label} must resolve to an existing directory") from exc
    if not resolved.is_dir():
        raise WorkerLaunchError(f"{label} must be a directory")
    return resolved


def _regular_file(path: Path, *, label: str) -> Path:
    _reject_link_components(path)
    try:
        resolved = path.resolve(strict=True)
        mode = resolved.stat().st_mode
    except (OSError, ValueError) as exc:
        raise WorkerLaunchError(f"{label} is missing or unreadable") from exc
    if not stat.S_ISREG(mode):
        raise WorkerLaunchError(f"{label} must be a regular file")
    return resolved


def _is_contained(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _sha256(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise WorkerLaunchError(f"{label} must be lowercase SHA-256")
    return value


def _sha1(value: Any, label: str) -> str:
    if type(value) is not str or _SHA1_RE.fullmatch(value) is None:
        raise WorkerLaunchError(f"{label} must be lowercase Git commit SHA-1")
    return value


@dataclass(frozen=True)
class WorkerCommand:
    """Exact command evidence for one allowlisted worker operation."""

    operation: str
    mode: str
    run_directory: Path
    request_artifact_id: str
    envelope_artifact_id: str | None
    release_identity_kind: str
    release_identity_id: str
    schema_version: int = WORKER_COMMAND_SCHEMA_VERSION
    policy_id: str = WORKER_COMMAND_POLICY_ID

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != WORKER_COMMAND_SCHEMA_VERSION:
            raise WorkerLaunchError("worker command schema version is unsupported")
        if self.policy_id != WORKER_COMMAND_POLICY_ID:
            raise WorkerLaunchError("worker command policy identity is unsupported")
        if type(self.operation) is not str or self.operation not in WORKER_OPERATIONS:
            raise WorkerLaunchError("worker operation is outside the exact allowlist")
        if type(self.mode) is not str or self.mode != WORKER_MODE_BY_OPERATION[self.operation]:
            raise WorkerLaunchError("worker mode does not match the reviewed operation")
        object.__setattr__(self, "run_directory", _resolved_directory(self.run_directory, "run_directory"))
        _sha256(self.request_artifact_id, "request_artifact_id")
        if self.envelope_artifact_id is not None:
            _sha256(self.envelope_artifact_id, "envelope_artifact_id")
        if self.release_identity_kind == "DEVELOPMENT_CHECKOUT":
            _sha1(self.release_identity_id, "development release_identity_id")
        elif self.release_identity_kind == "INSTALLED_RELEASE":
            _sha256(self.release_identity_id, "installed release_identity_id")
        else:
            raise WorkerLaunchError("release identity kind is unsupported")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "operation": self.operation,
            "mode": self.mode,
            "run_directory": str(self.run_directory),
            "request_artifact_id": self.request_artifact_id,
            "envelope_artifact_id": self.envelope_artifact_id,
            "release_identity_kind": self.release_identity_kind,
            "release_identity_id": self.release_identity_id,
        }

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())

    @classmethod
    def from_dict(cls, value: Any) -> "WorkerCommand":
        if type(value) is not dict or set(value) != _COMMAND_FIELDS:
            raise WorkerLaunchError("worker command fields are not exact")
        return cls(
            schema_version=value["schema_version"],
            policy_id=value["policy_id"],
            operation=value["operation"],
            mode=value["mode"],
            run_directory=Path(value["run_directory"]) if type(value["run_directory"]) is str else value["run_directory"],
            request_artifact_id=value["request_artifact_id"],
            envelope_artifact_id=value["envelope_artifact_id"],
            release_identity_kind=value["release_identity_kind"],
            release_identity_id=value["release_identity_id"],
        )

    @classmethod
    def from_json_bytes(cls, raw: bytes) -> "WorkerCommand":
        if type(raw) is not bytes:
            raise WorkerLaunchError("worker command input must be exact bytes")
        try:
            value = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_strict_object,
                parse_constant=_reject_constant,
            )
        except WorkerLaunchError:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WorkerLaunchError("worker command JSON is invalid") from exc
        command = cls.from_dict(value)
        if command.canonical_bytes != raw:
            raise WorkerLaunchError("worker command bytes are not canonical")
        return command


@dataclass(frozen=True)
class InstalledWorkerExecutable:
    """Separately supplied worker binary pinned for synthetic installed tests."""

    path: Path
    expected_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path) or not self.path.is_absolute():
            raise WorkerLaunchError("installed worker executable path must be absolute")
        if any(part == ".." for part in self.path.parts):
            raise WorkerLaunchError("installed worker executable path cannot traverse")
        _sha256(self.expected_sha256, "worker executable expected_sha256")


@dataclass(frozen=True)
class WorkerProcessResult:
    returncode: int
    stdout: str
    stderr: str

    def __post_init__(self) -> None:
        if type(self.returncode) is not int:
            raise WorkerLaunchError("worker return code must be an exact integer")
        if type(self.stdout) is not str or type(self.stderr) is not str:
            raise WorkerLaunchError("worker stdout and stderr must be captured text")


class WorkerProcessHandle:
    """Own one child process without business interpretation or retry."""

    def __init__(self, process: Any) -> None:
        self._process = process

    @property
    def pid(self) -> int | None:
        value = getattr(self._process, "pid", None)
        return value if type(value) is int else None

    def poll(self) -> int | None:
        value = self._process.poll()
        if value is not None and type(value) is not int:
            raise WorkerLaunchError("worker process returned an invalid exit code")
        return value

    def communicate(self) -> WorkerProcessResult:
        stdout, stderr = self._process.communicate()
        result = WorkerProcessResult(self._process.returncode, stdout or "", stderr or "")
        return result

    def request_cancel(self) -> bool:
        """Request a cooperative process signal; this never schedules a retry."""

        if self.poll() is not None:
            return False
        try:
            if os.name == "nt":
                self._process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                self._process.send_signal(signal.SIGTERM)
        except (OSError, ValueError, AttributeError) as exc:
            raise WorkerLaunchError("worker cancellation signal could not be requested") from exc
        return True


def _spawn_process(argv: Sequence[str], *, cwd: Path, shell: bool, **kwargs: Any) -> Any:
    """Private OS-process seam, replaced only by deterministic tests."""

    if shell is not False:
        raise WorkerLaunchError("worker process shell execution is forbidden")
    return subprocess.Popen(list(argv), cwd=str(cwd), shell=False, **kwargs)


def _process_group_options() -> dict[str, Any]:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _publish_or_match(path: Path, payload: bytes) -> None:
    """Publish exact bytes once; accept only byte-identical existing evidence."""

    if path.exists() or path.is_symlink():
        existing_path = _regular_file(path, label="existing worker evidence")
        try:
            existing = existing_path.read_bytes()
        except OSError as exc:
            raise WorkerLaunchError("existing worker evidence could not be read") from exc
        if existing != payload:
            raise WorkerLaunchError("contradictory existing worker evidence")
        return
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            try:
                existing = _regular_file(path, label="existing worker evidence").read_bytes()
            except OSError as exc:
                raise WorkerLaunchError("existing worker command evidence could not be read") from exc
            if existing != payload:
                raise WorkerLaunchError("contradictory existing worker command evidence")
    except WorkerLaunchError:
        raise
    except OSError as exc:
        raise WorkerLaunchError("worker command evidence could not be published safely") from exc
    finally:
        temporary.unlink(missing_ok=True)


def persist_worker_command(command: WorkerCommand) -> Path:
    if type(command) is not WorkerCommand:
        raise WorkerLaunchError("exact WorkerCommand is required")
    path = command.run_directory / WORKER_COMMAND_FILENAME
    _publish_or_match(path, command.canonical_bytes)
    return path


def read_bound_request(command: WorkerCommand) -> RunRequest:
    if type(command) is not WorkerCommand:
        raise WorkerLaunchError("exact WorkerCommand is required")
    if command.run_directory.name != command.request_artifact_id:
        raise WorkerLaunchError("run directory must be the exact request-SHA directory")
    request_path = _regular_file(command.run_directory / WORKER_REQUEST_FILENAME, label="request artifact")
    try:
        payload = request_path.read_bytes()
        request = RunRequest.from_json_bytes(payload)
    except (OSError, RunContractError) as exc:
        raise WorkerLaunchError("request artifact is not an exact canonical RunRequest") from exc
    if payload != canonical_json_bytes(request):
        raise WorkerLaunchError("request artifact bytes are not canonical")
    if hashlib.sha256(payload).hexdigest() != command.request_artifact_id:
        raise WorkerLaunchError("request artifact identity does not match worker command")
    if command.envelope_artifact_id is not None:
        envelope_path = _regular_file(
            command.run_directory / WORKER_ENVELOPE_FILENAME,
            label="execution envelope artifact",
        )
        try:
            envelope_payload = envelope_path.read_bytes()
            envelope = ExecutionEnvelope.from_json_bytes(envelope_payload)
        except (OSError, ExecutionEnvelopeError) as exc:
            raise WorkerLaunchError("execution envelope artifact is invalid") from exc
        if (
            envelope.canonical_sha256 != command.envelope_artifact_id
            or envelope.request_bytes != payload
        ):
            raise WorkerLaunchError("execution envelope artifact does not bind the exact request")
    if command.operation == "CURRENT_SHADOW_REQUEST":
        if (
            request.authority_profile != "SHADOW"
            or request.mode != "research_shadow"
            or request.bookie != "sportybet"
            or request.place_wager is not False
            or type(request.create_share_code) is not bool
        ):
            raise WorkerLaunchError("Current Shadow command is not bound to a supported RunRequest")
    return request


@dataclass(frozen=True, init=False)
class WorkerLauncher:
    """One public launch seam for DevelopmentCheckout and InstalledRelease."""

    identity: DevelopmentCheckoutIdentity | InstalledReleaseIdentity
    worker_executable: InstalledWorkerExecutable | None
    writable_roots: WritableRoots | None

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise WorkerLaunchError("construct WorkerLauncher with a verified identity")

    @classmethod
    def _create(
        cls,
        identity: DevelopmentCheckoutIdentity | InstalledReleaseIdentity,
        worker_executable: InstalledWorkerExecutable | None,
        writable_roots: WritableRoots | None = None,
    ) -> "WorkerLauncher":
        value = object.__new__(cls)
        object.__setattr__(value, "identity", identity)
        object.__setattr__(value, "worker_executable", worker_executable)
        object.__setattr__(value, "writable_roots", writable_roots)
        return value

    @classmethod
    def for_development(cls, identity: DevelopmentCheckoutIdentity) -> "WorkerLauncher":
        if type(identity) is not DevelopmentCheckoutIdentity:
            raise WorkerLaunchError("exact DevelopmentCheckoutIdentity is required")
        try:
            ResourceResolver.for_development(identity)
        except (ReleaseIdentityError, ValueError) as exc:
            raise WorkerLaunchError("DevelopmentCheckout identity is no longer valid") from exc
        return cls._create(identity, None)

    @classmethod
    def for_installed(
        cls,
        identity: InstalledReleaseIdentity,
        *,
        worker_executable: InstalledWorkerExecutable,
        writable_roots: WritableRoots,
    ) -> "WorkerLauncher":
        if type(identity) is not InstalledReleaseIdentity:
            raise WorkerLaunchError("exact InstalledReleaseIdentity is required")
        if type(worker_executable) is not InstalledWorkerExecutable:
            raise WorkerLaunchError("exact InstalledWorkerExecutable is required")
        if type(writable_roots) is not WritableRoots:
            raise WorkerLaunchError("exact PORT-02A WritableRoots are required for installed launch")
        if writable_roots.installed_release_root != identity.release_root:
            raise WorkerLaunchError("WritableRoots must bind the same installed release root")
        return cls._create(identity, worker_executable, writable_roots)

    def _reverify_identity(self, command: WorkerCommand) -> Path:
        if type(self.identity) is DevelopmentCheckoutIdentity:
            if self.worker_executable is not None or self.writable_roots is not None:
                raise WorkerLaunchError("DevelopmentCheckout cannot configure an installed worker")
            try:
                current = verify_development_checkout(self.identity.repository_root)
            except ReleaseIdentityError as exc:
                raise WorkerLaunchError("DevelopmentCheckout release identity could not be reverified") from exc
            if (
                current.head_commit_sha != self.identity.head_commit_sha
                or command.release_identity_kind != "DEVELOPMENT_CHECKOUT"
                or command.release_identity_id != current.head_commit_sha
            ):
                raise WorkerLaunchError("worker command DevelopmentCheckout identity mismatch")
            return current.repository_root

        if type(self.identity) is InstalledReleaseIdentity:
            if self.worker_executable is None:
                raise WorkerLaunchError("InstalledRelease requires a separately pinned worker executable")
            if type(self.writable_roots) is not WritableRoots:
                raise WorkerLaunchError("InstalledRelease requires exact PORT-02A WritableRoots")
            if self.writable_roots.installed_release_root != self.identity.release_root:
                raise WorkerLaunchError("InstalledRelease WritableRoots identity mismatch")
            try:
                current = verify_installed_release(
                    self.identity.release_root,
                    self.identity.manifest_sha256,
                )
            except (ReleaseIdentityError, ReleaseManifestError) as exc:
                raise WorkerLaunchError("InstalledRelease identity could not be reverified") from exc
            if (
                current.release_root != self.identity.release_root
                or current.manifest_sha256 != self.identity.manifest_sha256
                or command.release_identity_kind != "INSTALLED_RELEASE"
                or command.release_identity_id != current.manifest_sha256
            ):
                raise WorkerLaunchError("worker command InstalledRelease identity mismatch")
            return current.release_root
        raise WorkerLaunchError("launcher identity type is unsupported")

    def _verify_installed_worker(self, release_root: Path, run_directory: Path) -> Path:
        executable = self.worker_executable
        if type(executable) is not InstalledWorkerExecutable:
            raise WorkerLaunchError("InstalledRelease requires a separately pinned worker executable")
        resolved = _regular_file(executable.path, label="installed worker executable")
        try:
            approved_root = (release_root / "bin").resolve(strict=True)
        except OSError as exc:
            raise WorkerLaunchError("installed worker executable root is missing") from exc
        try:
            resolved.relative_to(approved_root)
        except ValueError as exc:
            raise WorkerLaunchError("installed worker executable must be inside release_root/bin") from exc
        if hashlib.sha256(resolved.read_bytes()).hexdigest() != executable.expected_sha256:
            raise WorkerLaunchError("installed worker executable SHA-256 mismatch")
        if type(self.writable_roots) is not WritableRoots:
            raise WorkerLaunchError("installed launch lost its PORT-02A WritableRoots")
        writable_roots = (
            self.writable_roots.data_root,
            self.writable_roots.cache_root,
            self.writable_roots.state_root,
        )
        if not any(_is_contained(root, run_directory) for root in writable_roots):
            raise WorkerLaunchError("installed worker run directory is outside configured writable roots")
        return resolved

    def launch(self, command: WorkerCommand) -> WorkerProcessHandle:
        if type(command) is not WorkerCommand:
            raise WorkerLaunchError("exact WorkerCommand is required")
        launch_root = self._reverify_identity(command)
        read_bound_request(command)
        executable = None
        if type(self.identity) is InstalledReleaseIdentity:
            executable = self._verify_installed_worker(launch_root, command.run_directory)
        command_path = persist_worker_command(command)
        if type(self.identity) is DevelopmentCheckoutIdentity:
            argv = [
                os.fspath(sys.executable),
                "-m",
                "runtime.worker_entry",
                "--command-file",
                os.fspath(command_path),
                "--development-root",
                os.fspath(launch_root),
            ]
            cwd = launch_root
            process_options = _process_group_options()
        else:
            if executable is None:
                raise WorkerLaunchError("installed worker executable was not verified")
            if command.release_identity_kind != "INSTALLED_RELEASE":
                raise WorkerLaunchError("installed launcher received non-installed command")
            argv = [
                os.fspath(executable),
                "--command-file",
                os.fspath(command_path),
                "--release-root",
                os.fspath(launch_root),
                "--trusted-manifest-sha256",
                self.identity.manifest_sha256,
            ]
            cwd = launch_root
            process_options = _process_group_options()
        if any(type(item) is not str for item in argv):
            raise WorkerLaunchError("worker argv must be exact text elements")
        try:
            process = _spawn_process(
                argv,
                cwd=cwd,
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                **process_options,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise WorkerLaunchError("worker process could not be created") from exc
        return WorkerProcessHandle(process)


def build_offline_probe_documents(command: WorkerCommand) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return deterministic semantic probe evidence and distinct provenance."""

    if type(command) is not WorkerCommand or command.operation != "OFFLINE_IDENTITY_PROBE":
        raise WorkerLaunchError("offline identity probe requires its exact allowlisted command")
    semantic: dict[str, Any] = {
        "schema_version": 1,
        "policy_id": "ATHENA_WORKER_OFFLINE_IDENTITY_PROBE_V1",
        "operation": command.operation,
        "mode": command.mode,
        "request_artifact_id": command.request_artifact_id,
        "envelope_artifact_id": command.envelope_artifact_id,
        "run_directory_identity": command.request_artifact_id,
        "provider_calls": 0,
        "delivery_calls": 0,
        "wager": False,
    }
    semantic["canonical_sha256"] = hashlib.sha256(canonical_json_bytes(semantic)).hexdigest()
    provenance: dict[str, Any] = {
        "schema_version": 1,
        "policy_id": "ATHENA_WORKER_LAUNCH_PROVENANCE_V1",
        "release_identity_kind": command.release_identity_kind,
        "release_identity_id": command.release_identity_id,
        "semantic_probe_sha256": semantic["canonical_sha256"],
    }
    provenance["canonical_sha256"] = hashlib.sha256(canonical_json_bytes(provenance)).hexdigest()
    return semantic, provenance


__all__ = [
    "InstalledWorkerExecutable",
    "WORKER_COMMAND_FILENAME",
    "WORKER_COMMAND_POLICY_ID",
    "WORKER_COMMAND_SCHEMA_VERSION",
    "WORKER_ENVELOPE_FILENAME",
    "WORKER_MODE_BY_OPERATION",
    "WORKER_OFFLINE_PROBE_FILENAME",
    "WORKER_OPERATIONS",
    "WORKER_PROVENANCE_FILENAME",
    "WorkerCommand",
    "WorkerLaunchError",
    "WorkerLauncher",
    "WorkerProcessHandle",
    "WorkerProcessResult",
    "build_offline_probe_documents",
    "persist_worker_command",
    "read_bound_request",
]
