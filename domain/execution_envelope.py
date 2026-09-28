"""Pure, versioned operation-intent and admission-preview contracts.

The V2 envelope binds exact canonical RunRequest V1 bytes to an explicit
operation intent and an immutable capability/source/time snapshot.  It does
not execute work or grant authority; preview evaluation only intersects the
request with the already-reviewed AuthorityManifest.
"""
from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Sequence

from domain.run_contracts import (
    AuthorityManifest,
    RunContractError,
    RunRequest,
    canonical_json_bytes,
    canonical_sha256,
)


EXECUTION_ENVELOPE_SCHEMA_VERSION = 2
EXECUTION_ENVELOPE_POLICY_ID = "ATHENA_EXECUTION_ENVELOPE_V2"
EXECUTION_ENVELOPE_CONTRACT = "ExecutionEnvelope"
EXECUTION_PREVIEW_SCHEMA_VERSION = 2
EXECUTION_PREVIEW_POLICY_ID = "ATHENA_EXECUTION_PREVIEW_V2"
EXECUTION_PREVIEW_CONTRACT = "ExecutionPreview"
REQUESTED_OPERATION_INTENT_CONTRACT = "RequestedOperationIntent"
SOURCE_RELEASE_IDENTITY_CONTRACT = "SourceReleaseIdentity"
ADMISSION_BLOCKER_CONTRACT = "AdmissionBlocker"

DATE_RESOLUTION_POLICY_ID = "ATHENA_REQUEST_DATE_RESOLUTION_LAGOS_V1"
DATE_RESOLUTION_TIMEZONE_ID = "Africa/Lagos"
PREVIEW_CLOCK_POLICY_ID = "ATHENA_INJECTED_PREVIEW_CLOCK_V1"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$", re.ASCII)
_SOURCE_KINDS = frozenset({"GIT_COMMIT", "SIGNED_RELEASE"})
_OPERATIONS = ("ACQUIRE_SOURCES", "CREATE_SHARE_CODE")
_OPERATION_CAPABILITIES = {
    "ACQUIRE_SOURCES": "provider_acquisition",
    "CREATE_SHARE_CODE": "share_code_generation",
}
_BLOCKER_REASON = "requested operation is not allowed by the bound capability manifest"


class ExecutionEnvelopeError(ValueError):
    """Raised when an operation-intent, envelope, or preview is invalid."""


def _exact_bool(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise ExecutionEnvelopeError(f"{label} must be exact bool")
    return value


def _exact_text(value: Any, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ExecutionEnvelopeError(f"{label} must be exact non-empty text")
    return value


def _exact_sha256(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise ExecutionEnvelopeError(f"{label} must be lowercase SHA-256 text")
    return value


def _exact_datetime(value: Any, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ExecutionEnvelopeError(f"{label} must be timezone-aware datetime")
    try:
        return value.astimezone(timezone.utc)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ExecutionEnvelopeError(f"{label} is invalid") from exc


def _timestamp(value: datetime) -> str:
    return _exact_datetime(value, "timestamp").isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_timestamp(value: Any, label: str) -> datetime:
    text = _exact_text(value, label)
    if not text.endswith("Z"):
        raise ExecutionEnvelopeError(f"{label} must be canonical UTC text ending Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ExecutionEnvelopeError(f"{label} is not valid ISO-8601 UTC") from exc
    normalized = _exact_datetime(parsed, label)
    if _timestamp(normalized) != text:
        raise ExecutionEnvelopeError(f"{label} is not canonical microsecond UTC text")
    return normalized


def _reject_constant(value: str) -> None:
    raise ExecutionEnvelopeError(f"non-finite JSON constant is forbidden: {value}")


def _strict_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ExecutionEnvelopeError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _load_json(raw: bytes) -> Any:
    if type(raw) is not bytes:
        raise ExecutionEnvelopeError("canonical envelope input must be bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ExecutionEnvelopeError("canonical envelope is not UTF-8") from exc
    try:
        return json.loads(text, object_pairs_hook=_strict_object, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise ExecutionEnvelopeError("canonical envelope JSON is invalid") from exc


@dataclass(frozen=True)
class RequestedOperationIntent:
    """Owner-requested operations, independent from the execution profile."""

    acquire_sources: bool
    create_share_code: bool
    place_wager: bool

    def __post_init__(self) -> None:
        _exact_bool(self.acquire_sources, "acquire_sources")
        _exact_bool(self.create_share_code, "create_share_code")
        _exact_bool(self.place_wager, "place_wager")
        if self.place_wager is not False:
            raise ExecutionEnvelopeError("AUTH-01A operation intent cannot request wager placement")

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": REQUESTED_OPERATION_INTENT_CONTRACT,
            "acquire_sources": self.acquire_sources,
            "create_share_code": self.create_share_code,
            "place_wager": self.place_wager,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "RequestedOperationIntent":
        if type(value) is not dict or set(value) != {
            "contract", "acquire_sources", "create_share_code", "place_wager"
        }:
            raise ExecutionEnvelopeError("RequestedOperationIntent fields drifted")
        if value["contract"] != REQUESTED_OPERATION_INTENT_CONTRACT:
            raise ExecutionEnvelopeError("RequestedOperationIntent contract identity drifted")
        return cls(
            acquire_sources=value["acquire_sources"],
            create_share_code=value["create_share_code"],
            place_wager=value["place_wager"],
        )


@dataclass(frozen=True)
class SourceReleaseIdentity:
    """Typed source identity that supports Git now and signed releases later."""

    kind: str
    value: str

    def __post_init__(self) -> None:
        if type(self.kind) is not str or self.kind not in _SOURCE_KINDS:
            raise ExecutionEnvelopeError("source identity kind is unknown")
        value = _exact_text(self.value, "source identity value")
        if not value.isascii() or not value.isprintable():
            raise ExecutionEnvelopeError("source identity value must be printable ASCII")
        if self.kind == "GIT_COMMIT" and _GIT_SHA_RE.fullmatch(value) is None:
            raise ExecutionEnvelopeError("GIT_COMMIT source identity must be lowercase 40-hex SHA")

    def to_dict(self) -> dict[str, str]:
        return {
            "contract": SOURCE_RELEASE_IDENTITY_CONTRACT,
            "kind": self.kind,
            "value": self.value,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "SourceReleaseIdentity":
        if type(value) is not dict or set(value) != {"contract", "kind", "value"}:
            raise ExecutionEnvelopeError("SourceReleaseIdentity fields drifted")
        if value["contract"] != SOURCE_RELEASE_IDENTITY_CONTRACT:
            raise ExecutionEnvelopeError("SourceReleaseIdentity contract identity drifted")
        return cls(kind=value["kind"], value=value["value"])


@dataclass(frozen=True)
class ExecutionEnvelope:
    """Immutable V2 admission contract binding exact V1 request bytes."""

    request_bytes: bytes
    request_sha256: str
    requested_operations: RequestedOperationIntent
    requested_operations_sha256: str
    authority_manifest: AuthorityManifest
    authority_manifest_sha256: str
    resolved_request_dates: tuple[str, ...]
    date_resolution_policy_id: str
    date_resolution_timezone_id: str
    clock_policy_id: str
    clock_observed_at: datetime
    source_identity: SourceReleaseIdentity
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if type(self.request_bytes) is not bytes:
            raise ExecutionEnvelopeError("request_bytes must be exact bytes")
        try:
            request = RunRequest.from_json_bytes(self.request_bytes)
        except RunContractError as exc:
            raise ExecutionEnvelopeError("embedded RunRequest V1 bytes are invalid") from exc
        if canonical_json_bytes(request) != self.request_bytes:
            raise ExecutionEnvelopeError("embedded RunRequest bytes are not canonical")
        _exact_sha256(self.request_sha256, "request_sha256")
        if hashlib.sha256(self.request_bytes).hexdigest() != self.request_sha256:
            raise ExecutionEnvelopeError("request SHA-256 does not bind exact request bytes")
        if type(self.requested_operations) is not RequestedOperationIntent:
            raise ExecutionEnvelopeError("requested_operations must be exact RequestedOperationIntent")
        _exact_sha256(self.requested_operations_sha256, "requested_operations_sha256")
        if canonical_sha256(self.requested_operations) != self.requested_operations_sha256:
            raise ExecutionEnvelopeError("requested-operation SHA-256 does not bind its payload")
        if type(self.authority_manifest) is not AuthorityManifest:
            raise ExecutionEnvelopeError("authority_manifest must be exact AuthorityManifest")
        _exact_sha256(self.authority_manifest_sha256, "authority_manifest_sha256")
        if canonical_sha256(self.authority_manifest) != self.authority_manifest_sha256:
            raise ExecutionEnvelopeError("capability SHA-256 does not bind its payload")
        if (
            self.authority_manifest.authority_profile != request.authority_profile
            or self.authority_manifest.mode != request.mode
        ):
            raise ExecutionEnvelopeError("capability identity does not match the bound RunRequest")
        intent = self.requested_operations
        if intent.create_share_code is not request.create_share_code:
            raise ExecutionEnvelopeError("operation intent conflicts with the bound RunRequest delivery field")
        if request.place_wager is not False or intent.place_wager is not False:
            raise ExecutionEnvelopeError("AUTH-01A envelope cannot authorize wager placement")
        if type(self.resolved_request_dates) is not tuple or any(
            type(day) is not str for day in self.resolved_request_dates
        ):
            raise ExecutionEnvelopeError("resolved_request_dates must be an exact tuple of date text")
        expected_dates = tuple(day.isoformat() for day in request.dates)
        if self.resolved_request_dates != expected_dates:
            raise ExecutionEnvelopeError("resolved dates do not exactly bind the RunRequest")
        if self.date_resolution_policy_id != DATE_RESOLUTION_POLICY_ID:
            raise ExecutionEnvelopeError("date-resolution policy identity drifted")
        if self.date_resolution_timezone_id != DATE_RESOLUTION_TIMEZONE_ID:
            raise ExecutionEnvelopeError("date-resolution timezone identity drifted")
        if self.clock_policy_id != PREVIEW_CLOCK_POLICY_ID:
            raise ExecutionEnvelopeError("preview clock policy identity drifted")
        if type(self.source_identity) is not SourceReleaseIdentity:
            raise ExecutionEnvelopeError("source_identity must be exact SourceReleaseIdentity")
        clock_observed_at = _exact_datetime(self.clock_observed_at, "clock_observed_at")
        issued_at = _exact_datetime(self.issued_at, "issued_at")
        expires_at = _exact_datetime(self.expires_at, "expires_at")
        if clock_observed_at != issued_at:
            raise ExecutionEnvelopeError("issued_at must equal the bound preview clock observation")
        if expires_at <= issued_at:
            raise ExecutionEnvelopeError("expires_at must be later than issued_at")
        object.__setattr__(self, "clock_observed_at", clock_observed_at)
        object.__setattr__(self, "issued_at", issued_at)
        object.__setattr__(self, "expires_at", expires_at)

    @property
    def request(self) -> RunRequest:
        return RunRequest.from_json_bytes(self.request_bytes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": EXECUTION_ENVELOPE_SCHEMA_VERSION,
            "policy_id": EXECUTION_ENVELOPE_POLICY_ID,
            "contract": EXECUTION_ENVELOPE_CONTRACT,
            "request_bytes_base64": base64.b64encode(self.request_bytes).decode("ascii"),
            "request_sha256": self.request_sha256,
            "requested_operations": self.requested_operations.to_dict(),
            "requested_operations_sha256": self.requested_operations_sha256,
            "authority_manifest": self.authority_manifest.to_dict(),
            "authority_manifest_sha256": self.authority_manifest_sha256,
            "resolved_request_dates": list(self.resolved_request_dates),
            "date_resolution_policy_id": self.date_resolution_policy_id,
            "date_resolution_timezone_id": self.date_resolution_timezone_id,
            "clock_policy_id": self.clock_policy_id,
            "clock_observed_at": _timestamp(self.clock_observed_at),
            "source_identity": self.source_identity.to_dict(),
            "issued_at": _timestamp(self.issued_at),
            "expires_at": _timestamp(self.expires_at),
        }

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self)

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()

    @classmethod
    def from_request_bytes(
        cls,
        *,
        request_bytes: bytes,
        requested_operations: RequestedOperationIntent,
        authority_manifest: AuthorityManifest,
        source_identity: SourceReleaseIdentity,
        date_resolution_policy_id: str,
        date_resolution_timezone_id: str,
        clock_policy_id: str,
        clock_observed_at: datetime,
        issued_at: datetime,
        expires_at: datetime,
    ) -> "ExecutionEnvelope":
        try:
            request = RunRequest.from_json_bytes(request_bytes)
        except (RunContractError, TypeError) as exc:
            raise ExecutionEnvelopeError("request_bytes must contain exact canonical RunRequest V1 bytes") from exc
        return cls(
            request_bytes=request_bytes,
            request_sha256=hashlib.sha256(request_bytes).hexdigest(),
            requested_operations=requested_operations,
            requested_operations_sha256=canonical_sha256(requested_operations),
            authority_manifest=authority_manifest,
            authority_manifest_sha256=canonical_sha256(authority_manifest),
            resolved_request_dates=tuple(day.isoformat() for day in request.dates),
            date_resolution_policy_id=date_resolution_policy_id,
            date_resolution_timezone_id=date_resolution_timezone_id,
            clock_policy_id=clock_policy_id,
            clock_observed_at=clock_observed_at,
            source_identity=source_identity,
            issued_at=issued_at,
            expires_at=expires_at,
        )

    @classmethod
    def from_dict(cls, value: Any) -> "ExecutionEnvelope":
        required = {
            "schema_version", "policy_id", "contract", "request_bytes_base64",
            "request_sha256", "requested_operations", "requested_operations_sha256",
            "authority_manifest", "authority_manifest_sha256", "resolved_request_dates",
            "date_resolution_policy_id", "date_resolution_timezone_id", "clock_policy_id",
            "clock_observed_at", "source_identity", "issued_at", "expires_at",
        }
        if type(value) is not dict or set(value) != required:
            raise ExecutionEnvelopeError("ExecutionEnvelope fields drifted")
        if type(value["schema_version"]) is not int or value["schema_version"] != EXECUTION_ENVELOPE_SCHEMA_VERSION:
            raise ExecutionEnvelopeError("ExecutionEnvelope schema version drifted")
        if value["policy_id"] != EXECUTION_ENVELOPE_POLICY_ID or value["contract"] != EXECUTION_ENVELOPE_CONTRACT:
            raise ExecutionEnvelopeError("ExecutionEnvelope policy/contract identity drifted")
        encoded = value["request_bytes_base64"]
        if type(encoded) is not str:
            raise ExecutionEnvelopeError("request_bytes_base64 must be exact text")
        try:
            request_bytes = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ExecutionEnvelopeError("request_bytes_base64 is invalid") from exc
        if base64.b64encode(request_bytes).decode("ascii") != encoded:
            raise ExecutionEnvelopeError("request_bytes_base64 is not canonical")
        if type(value["resolved_request_dates"]) is not list:
            raise ExecutionEnvelopeError("resolved_request_dates must be a JSON list")
        if type(value["authority_manifest"]) is not dict:
            raise ExecutionEnvelopeError("authority_manifest must be a JSON object")
        try:
            manifest = AuthorityManifest.from_dict(value["authority_manifest"])
        except RunContractError as exc:
            raise ExecutionEnvelopeError("authority_manifest is invalid") from exc
        return cls(
            request_bytes=request_bytes,
            request_sha256=value["request_sha256"],
            requested_operations=RequestedOperationIntent.from_dict(value["requested_operations"]),
            requested_operations_sha256=value["requested_operations_sha256"],
            authority_manifest=manifest,
            authority_manifest_sha256=value["authority_manifest_sha256"],
            resolved_request_dates=tuple(value["resolved_request_dates"]),
            date_resolution_policy_id=value["date_resolution_policy_id"],
            date_resolution_timezone_id=value["date_resolution_timezone_id"],
            clock_policy_id=value["clock_policy_id"],
            clock_observed_at=_parse_timestamp(value["clock_observed_at"], "clock_observed_at"),
            source_identity=SourceReleaseIdentity.from_dict(value["source_identity"]),
            issued_at=_parse_timestamp(value["issued_at"], "issued_at"),
            expires_at=_parse_timestamp(value["expires_at"], "expires_at"),
        )

    @classmethod
    def from_json_bytes(cls, raw: bytes) -> "ExecutionEnvelope":
        envelope = cls.from_dict(_load_json(raw))
        if envelope.canonical_bytes != raw:
            raise ExecutionEnvelopeError("ExecutionEnvelope JSON bytes are not canonical")
        return envelope


@dataclass(frozen=True)
class AdmissionBlocker:
    """Structured, non-secret blocker emitted by pure capability intersection."""

    code: str
    operation: str
    capability: str
    reason: str

    def __post_init__(self) -> None:
        if self.code != "REQUEST_AUTHORITY_MISMATCH":
            raise ExecutionEnvelopeError("unknown admission blocker code")
        if self.operation not in _OPERATIONS:
            raise ExecutionEnvelopeError("unknown blocked operation")
        if self.capability != _OPERATION_CAPABILITIES[self.operation]:
            raise ExecutionEnvelopeError("blocker capability does not match operation")
        if self.reason != _BLOCKER_REASON:
            raise ExecutionEnvelopeError("blocker reason is not the reviewed safe reason")

    def to_dict(self) -> dict[str, str]:
        return {
            "contract": ADMISSION_BLOCKER_CONTRACT,
            "code": self.code,
            "operation": self.operation,
            "capability": self.capability,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "AdmissionBlocker":
        if type(value) is not dict or set(value) != {"contract", "code", "operation", "capability", "reason"}:
            raise ExecutionEnvelopeError("AdmissionBlocker fields drifted")
        if value["contract"] != ADMISSION_BLOCKER_CONTRACT:
            raise ExecutionEnvelopeError("AdmissionBlocker contract identity drifted")
        return cls(code=value["code"], operation=value["operation"], capability=value["capability"], reason=value["reason"])


@dataclass(frozen=True)
class ExecutionPreview:
    """Pure immutable admission result; this value never dispatches work."""

    execution_envelope_sha256: str
    request_sha256: str
    requested_operations: RequestedOperationIntent
    authority_manifest: AuthorityManifest
    authority_manifest_sha256: str
    allowed_operations: tuple[str, ...]
    denied_operations: tuple[str, ...]
    blockers: tuple[AdmissionBlocker, ...]
    source_identity: SourceReleaseIdentity
    expires_at: datetime

    def __post_init__(self) -> None:
        _exact_sha256(self.execution_envelope_sha256, "execution_envelope_sha256")
        _exact_sha256(self.request_sha256, "request_sha256")
        if type(self.requested_operations) is not RequestedOperationIntent:
            raise ExecutionEnvelopeError("preview requested_operations must be exact intent")
        if type(self.authority_manifest) is not AuthorityManifest:
            raise ExecutionEnvelopeError("preview authority_manifest must be exact AuthorityManifest")
        _exact_sha256(self.authority_manifest_sha256, "authority_manifest_sha256")
        if canonical_sha256(self.authority_manifest) != self.authority_manifest_sha256:
            raise ExecutionEnvelopeError("preview capability identity SHA-256 mismatch")
        if type(self.source_identity) is not SourceReleaseIdentity:
            raise ExecutionEnvelopeError("preview source_identity must be exact SourceReleaseIdentity")
        if type(self.allowed_operations) is not tuple or type(self.denied_operations) is not tuple:
            raise ExecutionEnvelopeError("preview operation decisions must be exact tuples")
        if type(self.blockers) is not tuple or any(type(item) is not AdmissionBlocker for item in self.blockers):
            raise ExecutionEnvelopeError("preview blockers must be exact AdmissionBlocker tuple")
        expected_allowed, expected_denied, expected_blockers = _intersect(
            self.requested_operations, self.authority_manifest
        )
        if self.allowed_operations != expected_allowed or self.denied_operations != expected_denied:
            raise ExecutionEnvelopeError("preview operation decisions do not match bound capability intersection")
        if tuple(item.to_dict() for item in self.blockers) != tuple(item.to_dict() for item in expected_blockers):
            raise ExecutionEnvelopeError("preview blockers do not match bound capability intersection")
        object.__setattr__(self, "expires_at", _exact_datetime(self.expires_at, "expires_at"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": EXECUTION_PREVIEW_SCHEMA_VERSION,
            "policy_id": EXECUTION_PREVIEW_POLICY_ID,
            "contract": EXECUTION_PREVIEW_CONTRACT,
            "execution_envelope_sha256": self.execution_envelope_sha256,
            "request_sha256": self.request_sha256,
            "requested_operations": self.requested_operations.to_dict(),
            "authority_manifest": self.authority_manifest.to_dict(),
            "authority_manifest_sha256": self.authority_manifest_sha256,
            "allowed_operations": list(self.allowed_operations),
            "denied_operations": list(self.denied_operations),
            "blockers": [item.to_dict() for item in self.blockers],
            "source_identity": self.source_identity.to_dict(),
            "expires_at": _timestamp(self.expires_at),
        }

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self)

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()

    @classmethod
    def from_dict(cls, value: Any) -> "ExecutionPreview":
        required = {
            "schema_version", "policy_id", "contract", "execution_envelope_sha256",
            "request_sha256", "requested_operations", "authority_manifest",
            "authority_manifest_sha256", "allowed_operations", "denied_operations",
            "blockers", "source_identity", "expires_at",
        }
        if type(value) is not dict or set(value) != required:
            raise ExecutionEnvelopeError("ExecutionPreview fields drifted")
        if type(value["schema_version"]) is not int or value["schema_version"] != EXECUTION_PREVIEW_SCHEMA_VERSION:
            raise ExecutionEnvelopeError("ExecutionPreview schema version drifted")
        if value["policy_id"] != EXECUTION_PREVIEW_POLICY_ID or value["contract"] != EXECUTION_PREVIEW_CONTRACT:
            raise ExecutionEnvelopeError("ExecutionPreview policy/contract identity drifted")
        if type(value["authority_manifest"]) is not dict:
            raise ExecutionEnvelopeError("preview authority_manifest must be a JSON object")
        try:
            manifest = AuthorityManifest.from_dict(value["authority_manifest"])
        except RunContractError as exc:
            raise ExecutionEnvelopeError("preview authority_manifest is invalid") from exc
        if type(value["allowed_operations"]) is not list or type(value["denied_operations"]) is not list or type(value["blockers"]) is not list:
            raise ExecutionEnvelopeError("preview decision fields must be JSON lists")
        return cls(
            execution_envelope_sha256=value["execution_envelope_sha256"],
            request_sha256=value["request_sha256"],
            requested_operations=RequestedOperationIntent.from_dict(value["requested_operations"]),
            authority_manifest=manifest,
            authority_manifest_sha256=value["authority_manifest_sha256"],
            allowed_operations=tuple(value["allowed_operations"]),
            denied_operations=tuple(value["denied_operations"]),
            blockers=tuple(AdmissionBlocker.from_dict(item) for item in value["blockers"]),
            source_identity=SourceReleaseIdentity.from_dict(value["source_identity"]),
            expires_at=_parse_timestamp(value["expires_at"], "expires_at"),
        )

    @classmethod
    def from_json_bytes(cls, raw: bytes) -> "ExecutionPreview":
        preview = cls.from_dict(_load_json(raw))
        if preview.canonical_bytes != raw:
            raise ExecutionEnvelopeError("ExecutionPreview JSON bytes are not canonical")
        return preview


def _intersect(
    intent: RequestedOperationIntent,
    manifest: AuthorityManifest,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[AdmissionBlocker, ...]]:
    requested = {
        "ACQUIRE_SOURCES": intent.acquire_sources,
        "CREATE_SHARE_CODE": intent.create_share_code,
    }
    allowed: list[str] = []
    denied: list[str] = []
    blockers: list[AdmissionBlocker] = []
    for operation in _OPERATIONS:
        if requested[operation] is not True:
            continue
        capability = _OPERATION_CAPABILITIES[operation]
        if getattr(manifest, capability) is True:
            allowed.append(operation)
        else:
            denied.append(operation)
            blockers.append(
                AdmissionBlocker(
                    code="REQUEST_AUTHORITY_MISMATCH",
                    operation=operation,
                    capability=capability,
                    reason=_BLOCKER_REASON,
                )
            )
    return tuple(allowed), tuple(denied), tuple(blockers)


def evaluate_execution_envelope(envelope: ExecutionEnvelope) -> ExecutionPreview:
    """Evaluate requested external operations against bound capabilities only."""
    if type(envelope) is not ExecutionEnvelope:
        raise ExecutionEnvelopeError("preview requires exact ExecutionEnvelope")
    allowed, denied, blockers = _intersect(envelope.requested_operations, envelope.authority_manifest)
    return ExecutionPreview(
        execution_envelope_sha256=envelope.canonical_sha256,
        request_sha256=envelope.request_sha256,
        requested_operations=envelope.requested_operations,
        authority_manifest=envelope.authority_manifest,
        authority_manifest_sha256=envelope.authority_manifest_sha256,
        allowed_operations=allowed,
        denied_operations=denied,
        blockers=blockers,
        source_identity=envelope.source_identity,
        expires_at=envelope.expires_at,
    )


__all__ = [
    "DATE_RESOLUTION_POLICY_ID",
    "DATE_RESOLUTION_TIMEZONE_ID",
    "EXECUTION_ENVELOPE_CONTRACT",
    "EXECUTION_ENVELOPE_POLICY_ID",
    "EXECUTION_ENVELOPE_SCHEMA_VERSION",
    "EXECUTION_PREVIEW_CONTRACT",
    "EXECUTION_PREVIEW_POLICY_ID",
    "EXECUTION_PREVIEW_SCHEMA_VERSION",
    "ExecutionEnvelope",
    "ExecutionEnvelopeError",
    "ExecutionPreview",
    "PREVIEW_CLOCK_POLICY_ID",
    "RequestedOperationIntent",
    "SourceReleaseIdentity",
    "evaluate_execution_envelope",
]
