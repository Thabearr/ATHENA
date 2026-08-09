"""Strict contracts for exact raw FotMob data-matches captures."""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import pathlib
import re
import stat
import types
from typing import Any, Mapping, Tuple

from domain.fotmob_data_matches_probe import (
    ALLOWED_HOST,
    HTTPS_PORT,
    REQUEST_HEADERS,
    FotMobDataMatchesProbeError,
    request_target,
    validate_ccode3,
    validate_request_date,
    validate_timezone,
)


SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-data-matches-capture-v1"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
RAW_FILENAME = "response.json"
MANIFEST_FILENAME = "manifest.json"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MEDIA_TYPE_TOKEN_RE = re.compile(
    r"^[A-Za-z0-9!#$%&'*+.^_`|~-]+$",
    flags=re.ASCII,
)
_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "application_signature_reproduction_authorized",
        "cookie_use_authorized",
        "browser_impersonation_authorized",
        "raw_json_capture_authorized",
        "fixture_parsing_authorized",
        "fixture_extraction_authorized",
        "source_qualified",
        "fixture_promotion_authorized",
        "intelligence_authorized",
        "model_feature_authorized",
        "probability_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
    }
)


class FotMobDataMatchesCaptureError(ValueError):
    """Raised when data-matches capture evidence fails closed."""


def _request_values(
    request_date: Any,
    timezone: Any,
    ccode3: Any,
) -> tuple[str, str, str]:
    try:
        return (
            validate_request_date(request_date),
            validate_timezone(timezone),
            validate_ccode3(ccode3),
        )
    except FotMobDataMatchesProbeError as exc:
        raise FotMobDataMatchesCaptureError(str(exc)) from exc


def _target(request_date: Any, timezone: Any, ccode3: Any) -> str:
    date, zone, country = _request_values(request_date, timezone, ccode3)
    try:
        return request_target(date, zone, country)
    except FotMobDataMatchesProbeError as exc:
        raise FotMobDataMatchesCaptureError(str(exc)) from exc


def _utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise FotMobDataMatchesCaptureError(f"{label} must be a datetime")
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            raise FotMobDataMatchesCaptureError(f"{label} must be timezone-aware")
        return value.astimezone(datetime.timezone.utc)
    except FotMobDataMatchesCaptureError:
        raise
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobDataMatchesCaptureError(f"{label} is invalid") from exc


def parse_utc_timestamp(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise FotMobDataMatchesCaptureError(
            f"{label} must be a timezone-aware ISO-8601 string"
        )
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return _utc(datetime.datetime.fromisoformat(text), label)
    except FotMobDataMatchesCaptureError:
        raise
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobDataMatchesCaptureError(f"{label} is invalid ISO-8601") from exc


def serialize_utc(value: Any) -> str:
    return _utc(value, "timestamp").isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def validate_json_content_type(value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise FotMobDataMatchesCaptureError("Content-Type must identify JSON")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise FotMobDataMatchesCaptureError(
            "Content-Type must not contain ASCII control characters"
        )
    parts = value.split(";")
    if parts[0].strip().lower() != "application/json":
        raise FotMobDataMatchesCaptureError("Content-Type must be application/json")
    parameter_names: set[str] = set()
    for raw_parameter in parts[1:]:
        parameter = raw_parameter.strip()
        if not parameter or parameter.count("=") != 1:
            raise FotMobDataMatchesCaptureError(
                "Content-Type parameters must use token=token syntax"
            )
        raw_name, raw_parameter_value = parameter.split("=", 1)
        name = raw_name.strip()
        parameter_value = raw_parameter_value.strip()
        if (
            _MEDIA_TYPE_TOKEN_RE.fullmatch(name) is None
            or _MEDIA_TYPE_TOKEN_RE.fullmatch(parameter_value) is None
        ):
            raise FotMobDataMatchesCaptureError(
                "Content-Type parameter names and values must be ASCII tokens"
            )
        canonical_name = name.lower()
        if canonical_name in parameter_names:
            raise FotMobDataMatchesCaptureError(
                "Content-Type parameter names must be unique"
            )
        parameter_names.add(canonical_name)
    return value


def sha256_bytes(content: Any) -> str:
    if type(content) is not bytes:
        raise FotMobDataMatchesCaptureError("SHA-256 input must be exact bytes")
    return hashlib.sha256(content).hexdigest()


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise FotMobDataMatchesCaptureError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _content_length(value: Any) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise FotMobDataMatchesCaptureError(
            "content_length must be an exact non-negative integer or None"
        )
    if value > MAX_RESPONSE_BYTES:
        raise FotMobDataMatchesCaptureError("content_length exceeds the 8 MiB limit")
    return value


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(_SAFETY_KEYS)}


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise FotMobDataMatchesCaptureError("safety keys mismatch")
    detached: dict[str, bool] = {}
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise FotMobDataMatchesCaptureError(
                f"safety[{key!r}] must be exact bool False"
            )
        detached[key] = False
    return types.MappingProxyType(dict(detached))


@dataclasses.dataclass(frozen=True)
class CapturedFotMobDataMatchesResponse:
    status: int
    content_type: str
    content_length: int | None
    body: bytes
    observed_at: datetime.datetime
    network_acquisition_performed: bool

    def __post_init__(self) -> None:
        try:
            if type(self.status) is not int or self.status != 200:
                raise FotMobDataMatchesCaptureError(
                    "status must be exact integer 200"
                )
            content_type = validate_json_content_type(self.content_type)
            content_length = _content_length(self.content_length)
            if type(self.body) is not bytes:
                raise FotMobDataMatchesCaptureError("body must be exact bytes")
            if not self.body:
                raise FotMobDataMatchesCaptureError("body must not be empty")
            if len(self.body) > MAX_RESPONSE_BYTES:
                raise FotMobDataMatchesCaptureError("body exceeds the 8 MiB limit")
            if content_length is not None and content_length != len(self.body):
                raise FotMobDataMatchesCaptureError(
                    "Content-Length does not match body size"
                )
            observed_at = _utc(self.observed_at, "observed_at")
            if type(self.network_acquisition_performed) is not bool:
                raise FotMobDataMatchesCaptureError(
                    "network_acquisition_performed must be exact bool"
                )
            object.__setattr__(self, "content_type", content_type)
            object.__setattr__(self, "content_length", content_length)
            object.__setattr__(self, "observed_at", observed_at)
        except FotMobDataMatchesCaptureError:
            raise
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
            raise FotMobDataMatchesCaptureError(
                f"invalid captured data-matches response: {type(exc).__name__}"
            ) from exc


@dataclasses.dataclass(frozen=True)
class FotMobDataMatchesCaptureManifest:
    schema_version: int
    dataset_name: str
    request_date: str
    timezone: str
    ccode3: str
    host: str
    request_target: str
    request_headers: Tuple[Tuple[str, str], ...]
    x_mas_included: bool
    status: int
    content_type: str
    content_length: int | None
    observed_at: datetime.datetime
    network_acquisition_performed: bool
    raw_file_name: str
    raw_sha256: str
    raw_size: int
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        try:
            if type(self.schema_version) is not int or self.schema_version != 1:
                raise FotMobDataMatchesCaptureError(
                    "schema_version must be exact integer 1"
                )
            if self.dataset_name != DATASET_NAME:
                raise FotMobDataMatchesCaptureError(
                    f"dataset_name must be {DATASET_NAME}"
                )
            date, zone, country = _request_values(
                self.request_date, self.timezone, self.ccode3
            )
            if self.host != ALLOWED_HOST:
                raise FotMobDataMatchesCaptureError("host must be www.fotmob.com")
            if self.request_target != _target(date, zone, country):
                raise FotMobDataMatchesCaptureError("request_target mismatch")
            if (
                type(self.request_headers) is not tuple
                or self.request_headers != REQUEST_HEADERS
                or any(
                    type(item) is not tuple or len(item) != 2
                    for item in self.request_headers
                )
            ):
                raise FotMobDataMatchesCaptureError("request_headers mismatch")
            if type(self.x_mas_included) is not bool or self.x_mas_included is not False:
                raise FotMobDataMatchesCaptureError(
                    "x_mas_included must be exact bool False"
                )
            if type(self.status) is not int or self.status != 200:
                raise FotMobDataMatchesCaptureError(
                    "status must be exact integer 200"
                )
            content_type = validate_json_content_type(self.content_type)
            content_length = _content_length(self.content_length)
            observed_at = _utc(self.observed_at, "observed_at")
            if type(self.network_acquisition_performed) is not bool:
                raise FotMobDataMatchesCaptureError(
                    "network_acquisition_performed must be exact bool"
                )
            if self.raw_file_name != RAW_FILENAME:
                raise FotMobDataMatchesCaptureError(
                    "raw_file_name must be response.json"
                )
            raw_sha256 = _sha256(self.raw_sha256, "raw_sha256")
            if (
                type(self.raw_size) is not int
                or not 0 < self.raw_size <= MAX_RESPONSE_BYTES
            ):
                raise FotMobDataMatchesCaptureError(
                    "raw_size must be an exact positive integer within 8 MiB"
                )
            if content_length is not None and content_length != self.raw_size:
                raise FotMobDataMatchesCaptureError(
                    "content_length must match raw_size"
                )
            safety = _validate_safety(self.safety)
            object.__setattr__(self, "request_date", date)
            object.__setattr__(self, "timezone", zone)
            object.__setattr__(self, "ccode3", country)
            object.__setattr__(self, "content_type", content_type)
            object.__setattr__(self, "content_length", content_length)
            object.__setattr__(self, "observed_at", observed_at)
            object.__setattr__(self, "raw_sha256", raw_sha256)
            object.__setattr__(self, "safety", safety)
        except FotMobDataMatchesCaptureError:
            raise
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
            raise FotMobDataMatchesCaptureError(
                f"invalid data-matches capture manifest: {type(exc).__name__}"
            ) from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "request_date": self.request_date,
            "timezone": self.timezone,
            "ccode3": self.ccode3,
            "host": self.host,
            "request_target": self.request_target,
            "request_headers": [list(item) for item in self.request_headers],
            "x_mas_included": self.x_mas_included,
            "status": self.status,
            "content_type": self.content_type,
            "content_length": self.content_length,
            "observed_at": serialize_utc(self.observed_at),
            "network_acquisition_performed": self.network_acquisition_performed,
            "raw_file_name": self.raw_file_name,
            "raw_sha256": self.raw_sha256,
            "raw_size": self.raw_size,
            "safety": dict(self.safety),
        }


def build_data_matches_capture_manifest(
    response: Any,
    *,
    request_date: Any,
    timezone: Any,
    ccode3: Any,
) -> FotMobDataMatchesCaptureManifest:
    if not isinstance(response, CapturedFotMobDataMatchesResponse):
        raise FotMobDataMatchesCaptureError(
            "response must be CapturedFotMobDataMatchesResponse"
        )
    response = CapturedFotMobDataMatchesResponse(
        status=response.status,
        content_type=response.content_type,
        content_length=response.content_length,
        body=response.body,
        observed_at=response.observed_at,
        network_acquisition_performed=response.network_acquisition_performed,
    )
    date, zone, country = _request_values(request_date, timezone, ccode3)
    return FotMobDataMatchesCaptureManifest(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        request_date=date,
        timezone=zone,
        ccode3=country,
        host=ALLOWED_HOST,
        request_target=_target(date, zone, country),
        request_headers=REQUEST_HEADERS,
        x_mas_included=False,
        status=response.status,
        content_type=response.content_type,
        content_length=response.content_length,
        observed_at=response.observed_at,
        network_acquisition_performed=response.network_acquisition_performed,
        raw_file_name=RAW_FILENAME,
        raw_sha256=sha256_bytes(response.body),
        raw_size=len(response.body),
        safety=_default_safety(),
    )


def data_matches_capture_manifest_to_dict(manifest: Any) -> dict[str, Any]:
    if not isinstance(manifest, FotMobDataMatchesCaptureManifest):
        raise FotMobDataMatchesCaptureError(
            "manifest must be FotMobDataMatchesCaptureManifest"
        )
    return manifest.to_dict()


def canonical_data_matches_capture_manifest_bytes(manifest: Any) -> bytes:
    if not isinstance(manifest, FotMobDataMatchesCaptureManifest):
        raise FotMobDataMatchesCaptureError(
            "manifest must be FotMobDataMatchesCaptureManifest"
        )
    try:
        return (
            json.dumps(
                manifest.to_dict(),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobDataMatchesCaptureError("manifest serialization failed") from exc


def sha256_data_matches_capture_manifest(manifest: Any) -> str:
    return sha256_bytes(canonical_data_matches_capture_manifest_bytes(manifest))


def capture_identifier(
    *,
    request_date: Any,
    timezone: Any,
    ccode3: Any,
    observed_at: Any,
    raw_sha256: Any,
) -> str:
    date, zone, country = _request_values(request_date, timezone, ccode3)
    identity = {
        "request_date": date,
        "timezone": zone,
        "ccode3": country,
        "observed_at": serialize_utc(observed_at),
        "raw_sha256": _sha256(raw_sha256, "raw_sha256"),
    }
    raw_identity = json.dumps(
        identity,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(raw_identity)[:24]


def _reject_duplicate_keys(pairs: list[tuple[Any, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FotMobDataMatchesCaptureError(f"duplicate manifest key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise FotMobDataMatchesCaptureError(f"invalid manifest constant: {value}")


def strict_manifest_json_loads(raw: Any) -> Any:
    if type(raw) is not bytes:
        raise FotMobDataMatchesCaptureError("manifest must be exact bytes")
    try:
        text = raw.decode("utf-8", errors="strict")
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except FotMobDataMatchesCaptureError:
        raise
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise FotMobDataMatchesCaptureError(
            "manifest is not strict UTF-8 JSON"
        ) from exc


_MANIFEST_KEYS = frozenset(
    field.name for field in dataclasses.fields(FotMobDataMatchesCaptureManifest)
)


def manifest_from_mapping(value: Any) -> FotMobDataMatchesCaptureManifest:
    if not isinstance(value, Mapping) or set(value) != _MANIFEST_KEYS:
        raise FotMobDataMatchesCaptureError("manifest keys mismatch")
    headers = value.get("request_headers")
    if not isinstance(headers, list) or any(
        not isinstance(item, list) or len(item) != 2 for item in headers
    ):
        raise FotMobDataMatchesCaptureError(
            "manifest request_headers must be pairs"
        )
    try:
        return FotMobDataMatchesCaptureManifest(
            schema_version=value["schema_version"],
            dataset_name=value["dataset_name"],
            request_date=value["request_date"],
            timezone=value["timezone"],
            ccode3=value["ccode3"],
            host=value["host"],
            request_target=value["request_target"],
            request_headers=tuple(tuple(item) for item in headers),
            x_mas_included=value["x_mas_included"],
            status=value["status"],
            content_type=value["content_type"],
            content_length=value["content_length"],
            observed_at=parse_utc_timestamp(value["observed_at"], "observed_at"),
            network_acquisition_performed=value[
                "network_acquisition_performed"
            ],
            raw_file_name=value["raw_file_name"],
            raw_sha256=value["raw_sha256"],
            raw_size=value["raw_size"],
            safety=value["safety"],
        )
    except FotMobDataMatchesCaptureError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobDataMatchesCaptureError("manifest is invalid") from exc


def _reject_symlink_components(path: pathlib.Path, label: str) -> None:
    absolute = path if path.is_absolute() else pathlib.Path.cwd() / path
    current = pathlib.Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise FotMobDataMatchesCaptureError(
                f"{label} contains a forbidden symlink"
            )


def _read_bounded_regular_file(
    path: pathlib.Path,
    *,
    maximum_bytes: int,
    label: str,
    require_non_empty: bool = True,
) -> bytes:
    if type(maximum_bytes) is not int or maximum_bytes <= 0:
        raise FotMobDataMatchesCaptureError(
            "maximum_bytes must be an exact positive integer"
        )
    if type(require_non_empty) is not bool:
        raise FotMobDataMatchesCaptureError(
            "require_non_empty must be exact bool"
        )
    try:
        candidate = pathlib.Path(path)
    except (TypeError, ValueError) as exc:
        raise FotMobDataMatchesCaptureError(f"{label} path is invalid") from exc
    if candidate.is_symlink():
        raise FotMobDataMatchesCaptureError(f"{label} must not be a symlink")
    try:
        metadata = candidate.stat()
    except OSError as exc:
        raise FotMobDataMatchesCaptureError(
            f"{label} could not be inspected"
        ) from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise FotMobDataMatchesCaptureError(f"{label} must be a regular file")
    if require_non_empty and metadata.st_size <= 0:
        raise FotMobDataMatchesCaptureError(f"{label} must not be empty")
    if metadata.st_size > maximum_bytes:
        raise FotMobDataMatchesCaptureError(
            f"{label} exceeds the {maximum_bytes}-byte verification limit"
        )
    try:
        with candidate.open("rb") as handle:
            content = handle.read(maximum_bytes + 1)
    except OSError as exc:
        raise FotMobDataMatchesCaptureError(f"{label} could not be read") from exc
    if type(content) is not bytes:
        raise FotMobDataMatchesCaptureError(
            f"{label} read did not return exact bytes"
        )
    if len(content) > maximum_bytes:
        raise FotMobDataMatchesCaptureError(
            f"{label} exceeds the {maximum_bytes}-byte verification limit"
        )
    if require_non_empty and not content:
        raise FotMobDataMatchesCaptureError(f"{label} must not be empty")
    return content


def verify_data_matches_capture_directory(
    capture_directory: pathlib.Path,
    *,
    allowed_root: pathlib.Path,
    require_network_acquisition_performed: bool = True,
) -> FotMobDataMatchesCaptureManifest:
    """Verify byte, schema, hash, and provenance consistency without network."""

    if type(require_network_acquisition_performed) is not bool:
        raise FotMobDataMatchesCaptureError(
            "network provenance requirement must be exact bool"
        )
    try:
        root = pathlib.Path(allowed_root)
        capture = pathlib.Path(capture_directory)
    except (TypeError, ValueError) as exc:
        raise FotMobDataMatchesCaptureError("capture paths are invalid") from exc
    _reject_symlink_components(root, "allowed root")
    _reject_symlink_components(capture, "capture directory")
    if root.is_symlink() or not root.is_dir():
        raise FotMobDataMatchesCaptureError(
            "allowed root must be a non-symlink directory"
        )
    if capture.is_symlink() or not capture.is_dir():
        raise FotMobDataMatchesCaptureError(
            "capture directory must be a non-symlink directory"
        )
    root_resolved = root.resolve(strict=True)
    capture_resolved = capture.resolve(strict=True)
    try:
        relative = capture_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise FotMobDataMatchesCaptureError(
            "capture directory is outside allowed root"
        ) from exc
    if len(relative.parts) != 2:
        raise FotMobDataMatchesCaptureError(
            "capture directory layout must be YYYYMMDD/<id>"
        )
    try:
        entries = {entry.name for entry in capture_resolved.iterdir()}
    except OSError as exc:
        raise FotMobDataMatchesCaptureError(
            "capture directory could not be inspected"
        ) from exc
    if entries != {RAW_FILENAME, MANIFEST_FILENAME}:
        raise FotMobDataMatchesCaptureError(
            "capture must contain exactly response.json and manifest.json"
        )
    raw = _read_bounded_regular_file(
        capture_resolved / RAW_FILENAME,
        maximum_bytes=MAX_RESPONSE_BYTES,
        label="response.json",
    )
    manifest_bytes = _read_bounded_regular_file(
        capture_resolved / MANIFEST_FILENAME,
        maximum_bytes=MAX_MANIFEST_BYTES,
        label="manifest.json",
    )
    manifest = manifest_from_mapping(strict_manifest_json_loads(manifest_bytes))
    if manifest.request_date != relative.parts[0]:
        raise FotMobDataMatchesCaptureError(
            "manifest date does not match directory"
        )
    expected_id = capture_identifier(
        request_date=manifest.request_date,
        timezone=manifest.timezone,
        ccode3=manifest.ccode3,
        observed_at=manifest.observed_at,
        raw_sha256=manifest.raw_sha256,
    )
    if relative.parts[1] != expected_id:
        raise FotMobDataMatchesCaptureError("capture identifier mismatch")
    if len(raw) != manifest.raw_size:
        raise FotMobDataMatchesCaptureError("raw byte size mismatch")
    if sha256_bytes(raw) != manifest.raw_sha256:
        raise FotMobDataMatchesCaptureError("raw SHA-256 mismatch")
    if (
        manifest.network_acquisition_performed
        is not require_network_acquisition_performed
    ):
        raise FotMobDataMatchesCaptureError(
            "network acquisition provenance state mismatch"
        )
    expected = build_data_matches_capture_manifest(
        CapturedFotMobDataMatchesResponse(
            status=manifest.status,
            content_type=manifest.content_type,
            content_length=manifest.content_length,
            body=raw,
            observed_at=manifest.observed_at,
            network_acquisition_performed=manifest.network_acquisition_performed,
        ),
        request_date=manifest.request_date,
        timezone=manifest.timezone,
        ccode3=manifest.ccode3,
    )
    if expected != manifest:
        raise FotMobDataMatchesCaptureError(
            "manifest does not match raw capture"
        )
    if canonical_data_matches_capture_manifest_bytes(expected) != manifest_bytes:
        raise FotMobDataMatchesCaptureError("manifest bytes are not canonical")
    return manifest


__all__ = [
    "ALLOWED_HOST",
    "CapturedFotMobDataMatchesResponse",
    "DATASET_NAME",
    "FotMobDataMatchesCaptureError",
    "FotMobDataMatchesCaptureManifest",
    "HTTPS_PORT",
    "MANIFEST_FILENAME",
    "MAX_MANIFEST_BYTES",
    "MAX_RESPONSE_BYTES",
    "RAW_FILENAME",
    "REQUEST_HEADERS",
    "SCHEMA_VERSION",
    "build_data_matches_capture_manifest",
    "canonical_data_matches_capture_manifest_bytes",
    "capture_identifier",
    "data_matches_capture_manifest_to_dict",
    "manifest_from_mapping",
    "parse_utc_timestamp",
    "serialize_utc",
    "sha256_bytes",
    "sha256_data_matches_capture_manifest",
    "strict_manifest_json_loads",
    "validate_json_content_type",
    "verify_data_matches_capture_directory",
]
