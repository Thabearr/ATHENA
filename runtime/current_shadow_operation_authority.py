"""Authenticated nested Current Shadow authority and typed source GET port.

The context file and environment/argv selectors carry no independent authority.
The app DB event, parent startup gate, exact attempt lease and current child
process identity are revalidated at every operation boundary.
"""
from __future__ import annotations

import contextvars
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import stat
import sys
import threading
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from domain.run_contracts import canonical_json_bytes


POLICY_ID = "ATHENA_E3_CURRENT_SHADOW_OPERATION_AUTHORITY_V1"
CONTEXT_FILENAME = "athena-current-shadow-operation-context.json"
OPERATION_KIND = "CURRENT_SHADOW_PROVIDER_GET_V1"
MAX_CONTEXT_BYTES = 65_536
MAX_PROVIDER_OPERATION_SEQUENCE = 16_384
GITHUB_LINEAGE_JSON = "GITHUB_LINEAGE_JSON"
GITHUB_LINEAGE_ARTIFACT_ZIP = "GITHUB_LINEAGE_ARTIFACT_ZIP"
GITHUB_LINEAGE_RELEASE_ASSET = "GITHUB_LINEAGE_RELEASE_ASSET"
GITHUB_LINEAGE_REDIRECT_BINARY = "GITHUB_LINEAGE_REDIRECT_BINARY"
GITHUB_API_ORIGIN = "https://api.github.com"
GITHUB_API_JSON_HEADERS = (
    ("Accept", "application/vnd.github+json"),
    ("User-Agent", "ATHENA-CurrentShadow"),
)
GITHUB_ARTIFACT_HEADERS = (
    ("Accept", "application/vnd.github+json"),
    ("User-Agent", "ATHENA-CurrentShadow"),
)
GITHUB_RELEASE_HEADERS = (
    ("Accept", "application/octet-stream"),
    ("User-Agent", "ATHENA-CurrentShadow"),
)
GITHUB_REDIRECT_HEADERS = (("Accept", "application/octet-stream"),)
MAX_GITHUB_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_GITHUB_REDIRECT_BYTES = 8192
GITHUB_REDIRECT_HOSTS = frozenset({
    "objects.githubusercontent.com",
    "productionresultssa0.blob.core.windows.net",
    "release-assets.githubusercontent.com",
})
_CONTEXT_FIELDS = {
    "schema_version", "policy_id", "run_id", "attempt_id", "worker_instance_id",
    "lease_sha256", "request_sha256", "envelope_sha256", "command_sha256",
    "gate_sha256", "source_identity_sha256", "allowed_dates", "release_identity_kind",
    "release_identity_id", "source_revision",
    "operation", "mode", "profile", "intent_id", "data_root", "parent_pid",
    "parent_process_locator", "child_pid", "child_process_identity",
    "worker_executable_path", "worker_executable_sha256",
}
_SHA256 = re.compile(r"[0-9a-f]{64}", re.ASCII)
_AUTHORITY_FACTORY_TOKEN = object()
_ACTIVE_AUTHORITY: contextvars.ContextVar["CurrentShadowOperationAuthority | None"] = (
    contextvars.ContextVar("athena_current_shadow_operation_authority", default=None)
)
_PRODUCT_SCOPE_LOCK = threading.Lock()
_PRODUCT_SCOPE_USERS = 0


class ProductOperationAuthorityError(RuntimeError):
    """A product GET or evidence publication was not durably authorized."""


@dataclass(frozen=True)
class ProviderGetResponse:
    """Bound exact response bytes plus transport metadata, before source parsing."""

    body: bytes
    status: int
    observed_at: str
    content_type: str | None = None
    content_length: int | None = None
    content_length_header: str | None = None
    location: str | None = None
    operation_id: str | None = None

    def __post_init__(self) -> None:
        if (type(self.body) is not bytes or type(self.status) is not int
                or not 100 <= self.status <= 599 or type(self.observed_at) is not str
                or (self.content_type is not None and type(self.content_type) is not str)
                or (self.content_length is not None and type(self.content_length) is not int)
            or (self.content_length is not None and self.content_length < 0)
                or (self.content_length_header is not None
                    and type(self.content_length_header) is not str)
                or (self.location is not None and type(self.location) is not str)
                or (self.operation_id is not None and type(self.operation_id) is not str)):
            raise ProductOperationAuthorityError("provider response is outside the exact bounded schema")
        if (len(self.observed_at) > 32
                or (self.content_type is not None and len(self.content_type) > 256)
                or (self.content_length_header is not None
                    and (len(self.content_length_header) > 32
                         or any(ord(ch) < 32 or ord(ch) > 126
                                for ch in self.content_length_header)))
                or (self.location is not None
                    and (not self.location or len(self.location) > MAX_GITHUB_REDIRECT_BYTES
                         or any(ord(ch) < 32 or ord(ch) == 127 for ch in self.location)))
                or (self.operation_id is not None and len(self.operation_id) > 128)):
            raise ProductOperationAuthorityError("provider response metadata exceeds its fixed bound")
        try:
            parsed = datetime.fromisoformat(self.observed_at[:-1] + "+00:00")
        except ValueError as exc:
            raise ProductOperationAuthorityError("provider response timestamp is invalid") from exc
        if (not self.observed_at.endswith("Z") or parsed.utcoffset() != timezone.utc.utcoffset(parsed)
                or parsed.isoformat(timespec="microseconds").replace("+00:00", "Z") != self.observed_at):
            raise ProductOperationAuthorityError("provider response timestamp is not canonical UTC")


def worker_executable_identity() -> tuple[str, str]:
    """Return the exact interpreter path and bytes SHA used by the child argv."""
    try:
        executable = Path(sys.executable).resolve(strict=True)
        if not executable.is_file() or executable.is_symlink():
            raise OSError("interpreter is not a regular file")
        digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    except OSError as exc:
        raise ProductOperationAuthorityError("worker executable identity is unavailable") from exc
    return os.fspath(executable), digest


def context_path(command: Any) -> Path:
    from runtime.worker_launcher import WorkerCommand

    if type(command) is not WorkerCommand:
        raise ProductOperationAuthorityError("exact worker command is required")
    return command.run_directory / CONTEXT_FILENAME


def _open_private_exclusive(path: Path) -> int:
    """Create a new capability with owner-only access on POSIX and Windows."""
    if os.name != "nt":
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        return os.open(path, flags, 0o600)

    import ctypes
    import msvcrt
    from ctypes import wintypes

    class _SecurityAttributes(ctypes.Structure):
        _fields_ = [
            ("nLength", wintypes.DWORD),
            ("lpSecurityDescriptor", ctypes.c_void_p),
            ("bInheritHandle", wintypes.BOOL),
        ]

    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    descriptor = ctypes.c_void_p()
    convert = advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD)]
    convert.restype = wintypes.BOOL
    if not convert("D:P(A;;FA;;;OW)", 1, ctypes.byref(descriptor), None):
        raise OSError(ctypes.get_last_error(), "could not build owner-only context ACL")
    attributes = _SecurityAttributes(ctypes.sizeof(_SecurityAttributes), descriptor, False)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                       ctypes.POINTER(_SecurityAttributes), wintypes.DWORD,
                       wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    handle = create(os.fspath(path), 0x40000000, 0, ctypes.byref(attributes),
                    1, 0x80, None)  # GENERIC_WRITE, CREATE_NEW, FILE_ATTRIBUTE_NORMAL
    invalid = ctypes.c_void_p(-1).value
    if not handle or handle == invalid:
        error = ctypes.get_last_error()
        kernel.LocalFree(descriptor)
        raise OSError(error, "owner-only context creation failed", os.fspath(path))
    try:
        descriptor_fd = msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_BINARY)
        handle = None  # open_osfhandle owns it from here
        return descriptor_fd
    finally:
        if handle not in (None, 0, invalid):
            kernel.CloseHandle(handle)
        kernel.LocalFree(descriptor)


def build_context_document(
    *, command: Any, gate: Mapping[str, Any], gate_bytes: bytes, data_root: Path,
    child_pid: int, child_process_identity: Mapping[str, Any],
    worker_executable_path: str, worker_executable_sha256: str,
    source_identity_sha256: str, allowed_dates: tuple[str, ...],
) -> dict[str, Any]:
    """Build the bounded no-token context linked later by one DB event."""
    from runtime.worker_launcher import WorkerCommand

    if (type(command) is not WorkerCommand or type(gate) is not dict
            or type(gate_bytes) is not bytes or canonical_json_bytes(dict(gate)) != gate_bytes
            or type(child_pid) is not int or child_pid <= 0
            or type(child_process_identity) is not dict
            or child_process_identity.get("pid") != child_pid
            or type(worker_executable_path) is not str
            or type(worker_executable_sha256) is not str
            or _SHA256.fullmatch(worker_executable_sha256) is None
            or type(source_identity_sha256) is not str
            or _SHA256.fullmatch(source_identity_sha256) is None
            or type(allowed_dates) is not tuple or not 1 <= len(allowed_dates) <= 7
            or any(type(value) is not str or not re.fullmatch(
                r"[0-9]{8}", value, re.ASCII
            ) for value in allowed_dates)
            or tuple(sorted(set(allowed_dates))) != allowed_dates):
        raise ProductOperationAuthorityError("nested worker context inputs are invalid")
    return {
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "run_id": gate["run_id"],
        "attempt_id": gate["attempt_id"],
        "worker_instance_id": gate["worker_instance_id"],
        "lease_sha256": gate["lease_sha256"],
        "request_sha256": command.request_artifact_id,
        "envelope_sha256": gate["envelope_sha256"],
        "command_sha256": hashlib.sha256(command.canonical_bytes).hexdigest(),
        "gate_sha256": hashlib.sha256(gate_bytes).hexdigest(),
        "source_identity_sha256": source_identity_sha256,
        "allowed_dates": list(allowed_dates),
        "release_identity_kind": command.release_identity_kind,
        "release_identity_id": command.release_identity_id,
        "source_revision": command.release_identity_id,
        "operation": "CURRENT_SHADOW_REQUEST",
        "mode": "research_shadow",
        "profile": "SHADOW",
        "intent_id": "CURRENT_SHADOW_SOURCE_ACQUISITION_V1",
        "data_root": os.fspath(data_root.resolve(strict=True)),
        "parent_pid": gate["pid"],
        "parent_process_locator": gate["process_locator"],
        "child_pid": child_pid,
        "child_process_identity": dict(child_process_identity),
        "worker_executable_path": worker_executable_path,
        "worker_executable_sha256": worker_executable_sha256,
    }


def publish_context(path: Path, value: Mapping[str, Any]) -> bytes:
    """Publish canonical context once with owner-only creation permissions."""
    if not isinstance(path, Path) or path.name != CONTEXT_FILENAME:
        raise ProductOperationAuthorityError("nested context destination is not fixed")
    raw = canonical_json_bytes(dict(value))
    if len(raw) > MAX_CONTEXT_BYTES or path.is_symlink() or path.exists():
        raise ProductOperationAuthorityError("nested context exists, is linked or exceeds its bound")
    descriptor = -1
    try:
        descriptor = _open_private_exclusive(path)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise ProductOperationAuthorityError("nested context could not be published safely") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return raw


def read_context(path: Path, *, command: Any) -> tuple[dict[str, Any], bytes]:
    """Read the one exact canonical context without following links."""
    if path != context_path(command) or path.is_symlink() or bool(
        getattr(path, "is_junction", lambda: False)()
    ):
        raise ProductOperationAuthorityError("nested context path is not exact or is linked")
    descriptor = -1
    try:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ProductOperationAuthorityError("nested context must be a regular file")
        if os.name == "posix" and stat.S_IMODE(info.st_mode) & 0o077:
            raise ProductOperationAuthorityError("nested context permissions are too broad")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            raw = stream.read(MAX_CONTEXT_BYTES + 1)
    except ProductOperationAuthorityError:
        raise
    except OSError as exc:
        raise ProductOperationAuthorityError("nested context could not be read safely") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(raw) > MAX_CONTEXT_BYTES:
        raise ProductOperationAuthorityError("nested context exceeds its byte bound")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProductOperationAuthorityError("nested context JSON is invalid") from exc
    if (type(value) is not dict or set(value) != _CONTEXT_FIELDS
            or canonical_json_bytes(value) != raw
            or value["schema_version"] != 1 or value["policy_id"] != POLICY_ID
            or type(value["lease_sha256"]) is not str
            or _SHA256.fullmatch(value["lease_sha256"]) is None):
        raise ProductOperationAuthorityError("nested context schema or canonical bytes are invalid")
    return value, raw


class CurrentShadowOperationAuthority:
    """Process-local facade whose only production factory authenticates DB context."""

    def __init__(self, *, repository: Any, command: Any, gate: dict[str, Any],
                 gate_bytes: bytes, context: dict[str, Any], _factory_token=None):
        if _factory_token is not _AUTHORITY_FACTORY_TOKEN:
            raise ProductOperationAuthorityError(
                "Current Shadow authority can only be created by the authenticated child factory"
            )
        self._repository = repository
        self._command = command
        self._gate = gate
        self._gate_bytes = gate_bytes
        self._context = context
        self._sequence = 0
        self._sequence_lock = threading.Lock()
        self._publish_sequence = 0
        self._redirect_targets: dict[str, str] = {}

    @classmethod
    def _from_authenticated_child(
        cls, *, repository: Any, command: Any, gate: dict[str, Any],
        gate_bytes: bytes, context: dict[str, Any], context_bytes: bytes,
    ):
        repository.verify_current_shadow_supervisor_context(
            context=context, context_bytes=context_bytes, command=command,
            gate=gate, gate_bytes=gate_bytes,
        )
        return cls(
            repository=repository, command=command, gate=gate,
            gate_bytes=gate_bytes, context=context,
            _factory_token=_AUTHORITY_FACTORY_TOKEN,
        )

    def perform_get(
        self, *, provider: str, request_target: str, logical_id: str,
        headers: tuple[tuple[str, str], ...], timeout_seconds: int,
        maximum_bytes: int, origin: str | None = None,
        redirect_parent_operation_id: str | None = None,
        redirect_target_sha256: str | None = None,
        _transport_target: str | None = None,
    ) -> ProviderGetResponse:
        """Reserve PREPARED, commit one SENT permit, then issue the fixed GET."""
        with self._sequence_lock:
            operation_sequence = self._sequence + 1
            intent = _build_provider_get_intent(
                self._context, provider=provider, request_target=request_target,
                logical_id=logical_id, headers=headers, timeout_seconds=timeout_seconds,
                maximum_bytes=maximum_bytes, sequence=operation_sequence,
                origin=origin,
                redirect_parent_operation_id=redirect_parent_operation_id,
                redirect_target_sha256=redirect_target_sha256,
            )
            raw_intent = canonical_json_bytes(intent)
            operation_key = provider_get_idempotency_key(self._context, intent)
            operation_id = self._repository.prepare_current_shadow_provider_get(
                context=self._context, command=self._command, gate=self._gate,
                gate_bytes=self._gate_bytes, intent=intent, intent_bytes=raw_intent,
                idempotency_key=operation_key,
            )
            self._sequence = operation_sequence
        if not self._repository.authorize_current_shadow_provider_get_sent(
            context=self._context, command=self._command, gate=self._gate,
            gate_bytes=self._gate_bytes, operation_id=operation_id,
        ):
            raise ProductOperationAuthorityError("durable cancellation blocked provider GET before SENT")
        try:
            response = (
                _fixed_provider_get(intent)
                if _transport_target is None
                else _fixed_provider_get(intent, transport_target=_transport_target)
            )
            if type(response) is not ProviderGetResponse or len(response.body) > maximum_bytes:
                raise ProductOperationAuthorityError("provider GET response exceeded its exact byte contract")
            self._repository.confirm_current_shadow_provider_get(
                context=self._context, command=self._command, gate=self._gate,
                gate_bytes=self._gate_bytes, operation_id=operation_id,
                intent=intent, response=response,
            )
            if response.location is not None:
                self._redirect_targets[operation_id] = response.location
            return ProviderGetResponse(
                body=response.body, status=response.status, observed_at=response.observed_at,
                content_type=response.content_type, content_length=response.content_length,
                content_length_header=response.content_length_header,
                location=response.location, operation_id=operation_id,
            )
        except BaseException:
            try:
                self._repository.mark_current_shadow_provider_get_unknown(
                    context=self._context, command=self._command, gate=self._gate,
                    gate_bytes=self._gate_bytes, operation_id=operation_id,
                    error_code="PROVIDER_GET_TRANSPORT_UNKNOWN",
                )
            except Exception:
                # A durable SENT row is already uncertain and recovery keeps it
                # OUTCOME_UNKNOWN. Never invoke the transport again.
                pass
            raise

    def github_lineage_json(self, *, request_target: str) -> bytes:
        """Read one exact PR151 GitHub metadata endpoint through the GET ledger."""
        response = self.perform_get(
            provider=GITHUB_LINEAGE_JSON, request_target=request_target,
            logical_id="github-api:" + hashlib.sha256(request_target.encode("ascii")).hexdigest(),
            headers=GITHUB_API_JSON_HEADERS, timeout_seconds=45,
            maximum_bytes=MAX_GITHUB_RESPONSE_BYTES,
        )
        if response.status != 200 or response.location is not None:
            raise ProductOperationAuthorityError("fixed GitHub lineage metadata GET failed closed")
        return response.body

    def github_lineage_binary(self, *, request_target: str, accept: str) -> bytes:
        """Read one fixed lineage artifact, separately fencing a signed redirect."""
        if accept == "application/vnd.github+json":
            provider, headers = GITHUB_LINEAGE_ARTIFACT_ZIP, GITHUB_ARTIFACT_HEADERS
            prefix = "github-artifact-zip:"
        elif accept == "application/octet-stream":
            provider, headers = GITHUB_LINEAGE_RELEASE_ASSET, GITHUB_RELEASE_HEADERS
            prefix = "github-release-asset:"
        else:
            raise ProductOperationAuthorityError("GitHub binary media type is outside its fixed policy")
        operation_identity = hashlib.sha256(request_target.encode("ascii")).hexdigest()
        response = self.perform_get(
            provider=provider, request_target=request_target,
            logical_id=prefix + operation_identity, headers=headers,
            timeout_seconds=45, maximum_bytes=MAX_GITHUB_RESPONSE_BYTES,
        )
        if response.status == 200 and response.location is None:
            return response.body
        if (response.status not in {301, 302, 303, 307, 308}
                or response.location is None or response.operation_id is None):
            raise ProductOperationAuthorityError("GitHub lineage artifact response is not an approved download")
        return self._follow_github_artifact_redirect(response)

    def _follow_github_artifact_redirect(self, response: ProviderGetResponse) -> bytes:
        """Consume only the exact redirect observed by this authority instance."""
        if type(response) is not ProviderGetResponse or response.operation_id is None:
            raise ProductOperationAuthorityError("GitHub redirect lacks its exact parent operation")
        location = self._redirect_targets.pop(response.operation_id, None)
        if location is None or location != response.location:
            raise ProductOperationAuthorityError("GitHub redirect was missing, reused or changed")
        parsed = urlsplit(location)
        host = parsed.hostname
        target_hash = _validated_github_redirect_location(location)
        result = self.perform_get(
            provider=GITHUB_LINEAGE_REDIRECT_BINARY,
            request_target=parsed.path,
            logical_id="github-redirect:" + response.operation_id,
            headers=GITHUB_REDIRECT_HEADERS, timeout_seconds=45,
            maximum_bytes=MAX_GITHUB_RESPONSE_BYTES,
            origin=f"https://{host}",
            redirect_parent_operation_id=response.operation_id,
            redirect_target_sha256=target_hash,
            _transport_target=location,
        )
        if result.status != 200 or result.location is not None:
            raise ProductOperationAuthorityError("GitHub artifact redirect response was not an exact body")
        return result.body

    def publish_evidence(self, *, evidence_kind: str, publish: Callable[[], Any]) -> Any:
        """Publish one bounded local source artifact in cancel-serialized DB time."""
        if type(evidence_kind) is not str or not re.fullmatch(
            r"[A-Z][A-Z0-9_]{0,63}", evidence_kind, re.ASCII
        ) or not callable(publish):
            raise ProductOperationAuthorityError("evidence publication label/callback is invalid")
        with self._sequence_lock:
            self._publish_sequence += 1
            sequence = self._publish_sequence
        return self._repository.publish_current_shadow_evidence(
            context=self._context, command=self._command, gate=self._gate,
            gate_bytes=self._gate_bytes, evidence_kind=evidence_kind,
            sequence=sequence, publish=publish,
        )

def _build_provider_get_intent(
    context: Mapping[str, Any], *, provider: str, request_target: str,
    logical_id: str, headers: tuple[tuple[str, str], ...], timeout_seconds: int,
    maximum_bytes: int, sequence: int, origin: str | None = None,
    redirect_parent_operation_id: str | None = None,
    redirect_target_sha256: str | None = None,
) -> dict[str, Any]:
    """Validate fixed origin, route, semantic sequence and transport bounds."""
    if (type(provider) is not str or type(logical_id) is not str
            or not logical_id or len(logical_id) > 256
            or any(ord(character) < 32 or ord(character) > 126 for character in logical_id)
            or type(sequence) is not int
            or not 1 <= sequence <= MAX_PROVIDER_OPERATION_SEQUENCE):
        raise ProductOperationAuthorityError("provider and logical operation identity are required")
    if (type(request_target) is not str or len(request_target) > 4096
            or not request_target.startswith("/") or "#" in request_target):
        raise ProductOperationAuthorityError("provider request target is not normalized")
    if (type(headers) is not tuple or any(type(row) is not tuple or len(row) != 2
            or any(type(value) is not str for value in row) for row in headers)):
        raise ProductOperationAuthorityError("provider headers must be the fixed typed tuple")
    intent_extra: dict[str, Any] = {}
    try:
        if provider == "FOTMOB_DATA_MATCHES":
            from domain.fotmob_data_matches_capture import (
                ALLOWED_HOST, MAX_RESPONSE_BYTES,
            )
            from scripts.capture_fotmob_data_matches import (
                REQUEST_HEADERS, REQUEST_TIMEOUT_SECONDS,
                request_target as fotmob_target, _validated_inputs,
            )
            date, zone, country = _validated_inputs(logical_id, "UTC", "NGA")
            if date not in context.get("allowed_dates", ()):
                raise ValueError("FotMob date is outside the admitted request")
            expected = fotmob_target(date, zone, country)
            origin, path, policy, host = (
                "https://" + ALLOWED_HOST, expected, "FOTMOB_DATA_MATCHES_V1", ALLOWED_HOST,
            )
            fixed_headers, fixed_timeout, fixed_maximum = (
                tuple(REQUEST_HEADERS), REQUEST_TIMEOUT_SECONDS, MAX_RESPONSE_BYTES,
            )
        elif provider == "SPORTYBET_PC_UPCOMING":
            from datetime import datetime, timezone
            from domain import current_shadow_sportybet_pc_upcoming_discovery as source
            match = re.fullmatch(r"epoch:([1-4]):page:([1-9][0-9]?)", logical_id, re.ASCII)
            if match is None:
                raise ValueError("page identity")
            page_num = int(match.group(2))
            nonce_match = re.search(r"(?:\?|&)_t=([1-9][0-9]*)$", request_target, re.ASCII)
            if nonce_match is None:
                raise ValueError("page nonce")
            nonce = int(nonce_match.group(1))
            expected = source.request_target(page_num, nonce)
            source._validate_target(expected, page_num=page_num, observed_at=datetime.now(timezone.utc))
            origin, path, policy, host = (
                source.ORIGIN, expected, "SPORTYBET_PC_UPCOMING_V1", "www.sportybet.com",
            )
            fixed_headers, fixed_timeout, fixed_maximum = (
                tuple(source.REQUEST_HEADERS), source.REQUEST_TIMEOUT_SECONDS,
                source.MAX_RESPONSE_BYTES,
            )
        elif provider == "SPORTYBET_EVENT_DETAIL":
            from domain import sportybet_live_event_quote_evidence as source
            event_id = logical_id.removeprefix("event:")
            if not logical_id.startswith("event:") or source._event_id(event_id) != event_id:
                raise ValueError("event identity")
            expected = source.request_target(event_id)
            origin, path, policy, host = (
                source.ORIGIN, expected, "SPORTYBET_EVENT_DETAIL_V1", "www.sportybet.com",
            )
            fixed_headers, fixed_timeout, fixed_maximum = (
                tuple(source.REQUEST_HEADERS), 45, source.MAX_RESPONSE_BYTES,
            )
        elif provider == GITHUB_LINEAGE_JSON:
            _validate_github_api_target(request_target, route="JSON")
            if logical_id != "github-api:" + hashlib.sha256(request_target.encode("ascii")).hexdigest():
                raise ValueError("GitHub metadata idempotency identity")
            expected = request_target
            origin, path, policy, host = (
                GITHUB_API_ORIGIN, request_target, "GITHUB_PR151_LINEAGE_JSON_V1",
                "api.github.com",
            )
            fixed_headers, fixed_timeout, fixed_maximum = (
                GITHUB_API_JSON_HEADERS, 45, MAX_GITHUB_RESPONSE_BYTES,
            )
        elif provider == GITHUB_LINEAGE_ARTIFACT_ZIP:
            _validate_github_api_target(request_target, route="ARTIFACT_ZIP")
            if logical_id != "github-artifact-zip:" + hashlib.sha256(
                    request_target.encode("ascii")).hexdigest():
                raise ValueError("GitHub Actions artifact idempotency identity")
            expected = request_target
            origin, path, policy, host = (
                GITHUB_API_ORIGIN, request_target, "GITHUB_PR151_ACTIONS_ARTIFACT_ZIP_V1",
                "api.github.com",
            )
            fixed_headers, fixed_timeout, fixed_maximum = (
                GITHUB_ARTIFACT_HEADERS, 45, MAX_GITHUB_RESPONSE_BYTES,
            )
        elif provider == GITHUB_LINEAGE_RELEASE_ASSET:
            _validate_github_api_target(request_target, route="RELEASE_ASSET")
            if logical_id != "github-release-asset:" + hashlib.sha256(
                    request_target.encode("ascii")).hexdigest():
                raise ValueError("GitHub release asset idempotency identity")
            expected = request_target
            origin, path, policy, host = (
                GITHUB_API_ORIGIN, request_target, "GITHUB_PR151_RELEASE_ASSET_V1",
                "api.github.com",
            )
            fixed_headers, fixed_timeout, fixed_maximum = (
                GITHUB_RELEASE_HEADERS, 45, MAX_GITHUB_RESPONSE_BYTES,
            )
        elif provider == GITHUB_LINEAGE_REDIRECT_BINARY:
            parsed_origin = urlsplit(origin or "")
            host = parsed_origin.hostname
            if (parsed_origin.scheme != "https" or host not in GITHUB_REDIRECT_HOSTS
                    or parsed_origin.username is not None or parsed_origin.password is not None
                    or parsed_origin.port not in (None, 443) or parsed_origin.path
                    or parsed_origin.query or parsed_origin.fragment
                    or type(redirect_parent_operation_id) is not str
                    or re.fullmatch(
                        r"provider-get-[0-9a-f]{64}",
                        redirect_parent_operation_id, re.ASCII,
                    ) is None
                    or logical_id != "github-redirect:" + redirect_parent_operation_id
                    or type(redirect_target_sha256) is not str
                    or _SHA256.fullmatch(redirect_target_sha256) is None
                    or "?" in request_target or "#" in request_target):
                raise ProductOperationAuthorityError(
                    "GitHub signed redirect intent is outside its fixed policy"
                )
            expected = request_target
            origin, path, policy = (
                "https://" + host, request_target, "GITHUB_PR151_ARTIFACT_REDIRECT_V1",
            )
            fixed_headers, fixed_timeout, fixed_maximum = (
                GITHUB_REDIRECT_HEADERS, 45, MAX_GITHUB_RESPONSE_BYTES,
            )
            intent_extra = {
                "redirect_parent_operation_id": redirect_parent_operation_id,
                "redirect_target_sha256": redirect_target_sha256,
            }
        else:
            raise ProductOperationAuthorityError("provider kind is outside product GET allowlist")
    except ProductOperationAuthorityError:
        raise
    except Exception as exc:
        raise ProductOperationAuthorityError("provider GET target failed source validation") from exc
    if (request_target != expected or headers != fixed_headers
            or timeout_seconds != fixed_timeout or maximum_bytes != fixed_maximum):
        raise ProductOperationAuthorityError("provider GET differs from the exact reviewed transport policy")
    parsed = urlsplit(origin)
    if (parsed.scheme != "https" or parsed.hostname != host or parsed.username is not None
            or parsed.password is not None or parsed.port not in (None, 443)):
        raise ProductOperationAuthorityError("provider origin is outside its fixed HTTPS allowlist")
    return {
        "schema_version": 1,
        "operation_kind": OPERATION_KIND,
        "method": "GET",
        "provider": provider,
        "origin": origin,
        "request_target": request_target,
        "logical_id": logical_id,
        "sequence": sequence,
        "headers": [[name, value] for name, value in fixed_headers],
        "timeout_seconds": fixed_timeout,
        "maximum_bytes": fixed_maximum,
        "redirect_policy": "DENY",
        "retry_policy": "NEVER",
        "run_id": context["run_id"],
        "attempt_id": context["attempt_id"],
        "worker_instance_id": context["worker_instance_id"],
        "lease_sha256": context["lease_sha256"],
        "request_sha256": context["request_sha256"],
        "envelope_sha256": context["envelope_sha256"],
        "release_identity_kind": context["release_identity_kind"],
        "release_identity_id": context["release_identity_id"],
        "source_revision": context["source_revision"],
        "source_identity_sha256": context["source_identity_sha256"],
        "profile": context["profile"],
        "intent_id": context["intent_id"],
        "retrieval_policy_id": policy,
        **intent_extra,
    }


def _validate_github_api_target(request_target: str, *, route: str) -> None:
    """Accept only the exact fixed ATHENA PR151 lineage endpoint vocabulary."""
    if (type(request_target) is not str or len(request_target) > 512
            or not request_target.startswith("/repos/Thabearr/ATHENA/")
            or "#" in request_target or "@" in request_target):
        raise ProductOperationAuthorityError(
            "GitHub lineage API target is outside the fixed repository"
        )
    if route == "JSON":
        fixed_paths = {"/repos/Thabearr/ATHENA/git/ref/heads/main"}
        if request_target in fixed_paths:
            return
        runs = re.fullmatch(
            r"/repos/Thabearr/ATHENA/actions/workflows/"
            r"fotmob-utc-native-xg-fresh-holdout\.yml/runs\?per_page=100&page=([1-9][0-9]*)",
            request_target, re.ASCII,
        )
        run = re.fullmatch(
            r"/repos/Thabearr/ATHENA/actions/runs/([1-9][0-9]*)",
            request_target, re.ASCII,
        )
        artifacts = re.fullmatch(
            r"/repos/Thabearr/ATHENA/actions/runs/([1-9][0-9]*)/artifacts",
            request_target, re.ASCII,
        )
        jobs = re.fullmatch(
            r"/repos/Thabearr/ATHENA/actions/runs/([1-9][0-9]*)/jobs"
            r"\?filter=latest&per_page=100",
            request_target, re.ASCII,
        )
        release = re.fullmatch(
            r"/repos/Thabearr/ATHENA/releases/tags/"
            r"([A-Za-z0-9][A-Za-z0-9._-]{0,159})",
            request_target, re.ASCII,
        )
        if ((runs is not None and int(runs.group(1)) <= 100)
                or run is not None or artifacts is not None
                or jobs is not None or release is not None):
            return
    elif route == "ARTIFACT_ZIP":
        if re.fullmatch(
            r"/repos/Thabearr/ATHENA/actions/artifacts/[1-9][0-9]*/zip",
            request_target, re.ASCII,
        ):
            return
    elif route == "RELEASE_ASSET":
        if re.fullmatch(
            r"/repos/Thabearr/ATHENA/releases/assets/[1-9][0-9]*",
            request_target, re.ASCII,
        ):
            return
    raise ProductOperationAuthorityError(
        "GitHub lineage API route is not in the PR151 GET allowlist"
    )


def _validated_github_redirect_location(location: str) -> str:
    """Validate a one-hop signed GitHub URL and return only its non-secret digest."""
    if type(location) is not str or not location or len(location) > MAX_GITHUB_REDIRECT_BYTES:
        raise ProductOperationAuthorityError("GitHub artifact redirect is outside its bound")
    parsed = urlsplit(location)
    if (parsed.scheme != "https" or parsed.hostname not in GITHUB_REDIRECT_HOSTS
            or parsed.username is not None or parsed.password is not None
            or parsed.port not in (None, 443) or parsed.fragment
            or not parsed.path.startswith("/") or not parsed.query
            or any(ord(character) < 32 or ord(character) == 127 for character in location)):
        raise ProductOperationAuthorityError("GitHub artifact redirect origin is outside its fixed set")
    return hashlib.sha256(location.encode("utf-8")).hexdigest()


def _fixed_provider_get(
    intent: Mapping[str, Any], *, transport_target: str | None = None,
) -> ProviderGetResponse:
    """Issue exactly the already validated GET: no proxy, redirect or retry path."""
    if (type(intent) is not dict or intent.get("method") != "GET"
            or intent.get("redirect_policy") != "DENY"
            or intent.get("retry_policy") != "NEVER"):
        raise ProductOperationAuthorityError("provider transport requires one exact GET intent")
    origin = urlsplit(intent.get("origin", ""))
    host = origin.hostname
    expected_host = {
        "FOTMOB_DATA_MATCHES": "www.fotmob.com",
        "SPORTYBET_PC_UPCOMING": "www.sportybet.com",
        "SPORTYBET_EVENT_DETAIL": "www.sportybet.com",
        GITHUB_LINEAGE_JSON: "api.github.com",
        GITHUB_LINEAGE_ARTIFACT_ZIP: "api.github.com",
        GITHUB_LINEAGE_RELEASE_ASSET: "api.github.com",
    }.get(intent.get("provider"))
    redirect_request = intent.get("provider") == GITHUB_LINEAGE_REDIRECT_BINARY
    if redirect_request:
        expected_host = host
    if (origin.scheme != "https" or host != expected_host
            or origin.username is not None or origin.password is not None
            or origin.port not in (None, 443)
            or (redirect_request and host not in GITHUB_REDIRECT_HOSTS)):
        raise ProductOperationAuthorityError("provider transport origin is outside the fixed HTTPS set")
    target = intent.get("request_target")
    if redirect_request:
        if type(transport_target) is not str:
            raise ProductOperationAuthorityError("signed GitHub redirect transport target is absent")
        parsed_target = urlsplit(transport_target)
        if (parsed_target.scheme != "https" or parsed_target.hostname != host
                or parsed_target.username is not None or parsed_target.password is not None
                or parsed_target.port not in (None, 443) or parsed_target.fragment
                or parsed_target.path != target
                or hashlib.sha256(transport_target.encode("utf-8")).hexdigest()
                    != intent.get("redirect_target_sha256")):
            raise ProductOperationAuthorityError(
                "signed GitHub redirect target differs from its digest-bound intent"
            )
        # HTTPSConnection sends an origin-form request target. Passing the
        # signed absolute URL here would use proxy-form syntax on a direct
        # connection and can fail or be interpreted differently by servers.
        target = parsed_target.path
        if parsed_target.query:
            target += "?" + parsed_target.query
    elif transport_target is not None:
        raise ProductOperationAuthorityError("non-redirect provider request carried an alternate target")
    maximum = intent.get("maximum_bytes")
    timeout = intent.get("timeout_seconds")
    target_bound = MAX_GITHUB_REDIRECT_BYTES if redirect_request else 4096
    if (type(target) is not str or not target.startswith("/") or len(target) > target_bound
            or type(maximum) is not int or not 1 <= maximum <= 16 * 1024 * 1024
            or type(timeout) is not int or not 1 <= timeout <= 60):
        raise ProductOperationAuthorityError("provider transport bounds are invalid")
    rows = intent.get("headers")
    if (type(rows) is not list or len(rows) > 32 or any(
            type(row) is not list or len(row) != 2
            or any(type(value) is not str for value in row)
            for row in rows)):
        raise ProductOperationAuthorityError("provider transport headers are invalid")
    connection = None
    try:
        connection = http.client.HTTPSConnection(host, 443, timeout=timeout)
        connection.putrequest("GET", target, skip_accept_encoding=True)
        for name, value in rows:
            connection.putheader(name, value)
        if intent.get("provider") in {
                GITHUB_LINEAGE_JSON, GITHUB_LINEAGE_ARTIFACT_ZIP,
                GITHUB_LINEAGE_RELEASE_ASSET,
        }:
            token = os.environ.get("GH_TOKEN")
            if (type(token) is not str or not token or len(token) > 4096
                    or any(ord(character) < 33 or ord(character) > 126 for character in token)):
                raise ProductOperationAuthorityError(
                    "fixed GitHub lineage token is unavailable or malformed"
                )
            connection.putheader("Authorization", "Bearer " + token)
        connection.endheaders()
        response = connection.getresponse()
        body = bytearray()
        while len(body) <= maximum:
            chunk = response.read(min(64 * 1024, maximum + 1 - len(body)))
            if type(chunk) is not bytes:
                raise ProductOperationAuthorityError("provider response chunk is not exact bytes")
            if not chunk:
                break
            body.extend(chunk)
        observed_at = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
            "+00:00", "Z",
        )
        content_type = response.getheader("Content-Type")
        content_length_header = response.getheader("Content-Length")
        location = response.getheader("Location")
        try:
            content_length = int(content_length_header) if content_length_header is not None else None
        except (TypeError, ValueError):
            content_length = None
        return ProviderGetResponse(
            body=bytes(body), status=int(response.status), observed_at=observed_at,
            content_type=content_type, content_length=content_length,
            content_length_header=content_length_header, location=location,
        )
    except ProductOperationAuthorityError:
        raise
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        raise ProductOperationAuthorityError("bounded provider GET transport failed") from exc
    finally:
        if connection is not None:
            try:
                connection.close()
            except OSError:
                pass


def provider_get_idempotency_key(context: Mapping[str, Any], intent: Mapping[str, Any]) -> str:
    """One logical source operation can be authorized only once per admitted run."""
    identity = canonical_json_bytes({
        "schema_version": 1,
        "run_id": context["run_id"],
        "provider": intent["provider"],
        "logical_id": intent["logical_id"],
    })
    return "CSGET-" + hashlib.sha256(identity).hexdigest()


def current_product_authority() -> CurrentShadowOperationAuthority | None:
    """Return installed authority, denying legacy fallback inside product scope."""
    authority = _ACTIVE_AUTHORITY.get()
    if authority is not None:
        return authority
    with _PRODUCT_SCOPE_LOCK:
        required = _PRODUCT_SCOPE_USERS > 0
    if required:
        raise ProductOperationAuthorityError(
            "product worker lost its authenticated operation context"
        )
    return None


def publish_product_evidence(*, evidence_kind: str, publish: Callable[[], Any]) -> Any:
    """Use the cancel-serialized product writer when the authenticated context is active."""
    authority = current_product_authority()
    if authority is None:
        return publish()
    return authority.publish_evidence(evidence_kind=evidence_kind, publish=publish)


def install_product_authority(authority: CurrentShadowOperationAuthority):
    """Internal contextvar seam; caller must already authenticate exact DB context."""
    global _PRODUCT_SCOPE_USERS
    if type(authority) is not CurrentShadowOperationAuthority:
        raise ProductOperationAuthorityError("authenticated product authority is required")
    token = _ACTIVE_AUTHORITY.set(authority)
    with _PRODUCT_SCOPE_LOCK:
        _PRODUCT_SCOPE_USERS += 1
    return token


def reset_product_authority(token: contextvars.Token) -> None:
    global _PRODUCT_SCOPE_USERS
    _ACTIVE_AUTHORITY.reset(token)
    with _PRODUCT_SCOPE_LOCK:
        _PRODUCT_SCOPE_USERS -= 1
        if _PRODUCT_SCOPE_USERS < 0:
            _PRODUCT_SCOPE_USERS = 0
            raise ProductOperationAuthorityError("product operation context scope underflow")


__all__ = [
    "CONTEXT_FILENAME", "CurrentShadowOperationAuthority", "OPERATION_KIND", "POLICY_ID",
    "ProductOperationAuthorityError", "ProviderGetResponse", "build_context_document",
    "context_path", "current_product_authority", "install_product_authority",
    "publish_context", "publish_product_evidence", "read_context",
    "reset_product_authority", "worker_executable_identity",
]
