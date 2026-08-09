"""Strict contracts for exact raw FotMob public date-page captures."""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import pathlib
import re
import types
from typing import Any, Mapping, Tuple


SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-date-page-capture-v1"
ALLOWED_HOST = "www.fotmob.com"
HTTPS_PORT = 443
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
RAW_FILENAME = "page.html"
MANIFEST_FILENAME = "manifest.json"
REQUEST_HEADERS: Tuple[Tuple[str, str], ...] = (
    ("Accept", "text/html,application/xhtml+xml"),
    ("User-Agent", "ATHENA/1.0"),
)

_DATE_RE = re.compile(r"^[0-9]{8}$", flags=re.ASCII)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "html_capture_authorized",
        "html_parsing_authorized",
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


class FotMobPageCaptureError(ValueError):
    """Raised when page-capture data or provenance fails closed."""


def validate_request_date(value: Any) -> str:
    if not isinstance(value, str) or _DATE_RE.fullmatch(value) is None:
        raise FotMobPageCaptureError(
            "request date must be exactly YYYYMMDD ASCII digits"
        )
    try:
        parsed = datetime.datetime.strptime(value, "%Y%m%d").date()
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobPageCaptureError(
            "request date must be a valid Gregorian date"
        ) from exc
    if parsed.strftime("%Y%m%d") != value:
        raise FotMobPageCaptureError("request date must be canonical YYYYMMDD")
    return value


def request_target(request_date: Any) -> str:
    return f"/?date={validate_request_date(request_date)}"


def _utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise FotMobPageCaptureError(f"{label} must be a datetime")
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            raise FotMobPageCaptureError(f"{label} must be timezone-aware")
        return value.astimezone(datetime.timezone.utc)
    except FotMobPageCaptureError:
        raise
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobPageCaptureError(f"{label} is invalid") from exc


def parse_utc_timestamp(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise FotMobPageCaptureError(
            f"{label} must be a timezone-aware ISO-8601 string"
        )
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return _utc(datetime.datetime.fromisoformat(text), label)
    except FotMobPageCaptureError:
        raise
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobPageCaptureError(f"{label} is invalid ISO-8601") from exc


def serialize_utc(value: Any) -> str:
    return _utc(value, "timestamp").isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def validate_html_content_type(value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise FotMobPageCaptureError("Content-Type must identify HTML")
    parts = value.split(";")
    if parts[0].strip().lower() != "text/html":
        raise FotMobPageCaptureError("Content-Type must be text/html")
    if any(not part.strip() for part in parts[1:]):
        raise FotMobPageCaptureError("Content-Type parameters are malformed")
    return value


def sha256_bytes(content: Any) -> str:
    if type(content) is not bytes:
        raise FotMobPageCaptureError("SHA-256 input must be exact bytes")
    return hashlib.sha256(content).hexdigest()


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise FotMobPageCaptureError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _content_length(value: Any) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise FotMobPageCaptureError(
            "content_length must be an exact non-negative integer or None"
        )
    if value > MAX_RESPONSE_BYTES:
        raise FotMobPageCaptureError("content_length exceeds the 8 MiB limit")
    return value


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(_SAFETY_KEYS)}


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise FotMobPageCaptureError("safety keys mismatch")
    detached: dict[str, bool] = {}
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise FotMobPageCaptureError(f"safety[{key!r}] must be exact bool False")
        detached[key] = False
    return types.MappingProxyType(dict(detached))


@dataclasses.dataclass(frozen=True)
class CapturedFotMobPageResponse:
    status: int
    content_type: str
    content_length: int | None
    body: bytes
    observed_at: datetime.datetime
    network_acquisition_performed: bool

    def __post_init__(self) -> None:
        try:
            if type(self.status) is not int or self.status != 200:
                raise FotMobPageCaptureError("status must be exact integer 200")
            content_type = validate_html_content_type(self.content_type)
            content_length = _content_length(self.content_length)
            if type(self.body) is not bytes:
                raise FotMobPageCaptureError("body must be exact bytes")
            if not self.body:
                raise FotMobPageCaptureError("body must not be empty")
            if len(self.body) > MAX_RESPONSE_BYTES:
                raise FotMobPageCaptureError("body exceeds the 8 MiB limit")
            if content_length is not None and content_length != len(self.body):
                raise FotMobPageCaptureError("Content-Length does not match body size")
            observed_at = _utc(self.observed_at, "observed_at")
            if type(self.network_acquisition_performed) is not bool:
                raise FotMobPageCaptureError(
                    "network_acquisition_performed must be exact bool"
                )
            object.__setattr__(self, "content_type", content_type)
            object.__setattr__(self, "content_length", content_length)
            object.__setattr__(self, "observed_at", observed_at)
        except FotMobPageCaptureError:
            raise
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
            raise FotMobPageCaptureError(
                f"invalid captured page response: {type(exc).__name__}"
            ) from exc


@dataclasses.dataclass(frozen=True)
class FotMobPageCaptureManifest:
    schema_version: int
    dataset_name: str
    request_date: str
    host: str
    request_target: str
    request_headers: Tuple[Tuple[str, str], ...]
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
                raise FotMobPageCaptureError("schema_version must be exact integer 1")
            if self.dataset_name != DATASET_NAME:
                raise FotMobPageCaptureError(f"dataset_name must be {DATASET_NAME}")
            date = validate_request_date(self.request_date)
            if self.host != ALLOWED_HOST:
                raise FotMobPageCaptureError("host must be www.fotmob.com")
            if self.request_target != request_target(date):
                raise FotMobPageCaptureError("request_target mismatch")
            if type(self.request_headers) is not tuple or self.request_headers != REQUEST_HEADERS:
                raise FotMobPageCaptureError("request_headers mismatch")
            if type(self.status) is not int or self.status != 200:
                raise FotMobPageCaptureError("status must be exact integer 200")
            content_type = validate_html_content_type(self.content_type)
            content_length = _content_length(self.content_length)
            observed_at = _utc(self.observed_at, "observed_at")
            if type(self.network_acquisition_performed) is not bool:
                raise FotMobPageCaptureError(
                    "network_acquisition_performed must be exact bool"
                )
            if self.raw_file_name != RAW_FILENAME:
                raise FotMobPageCaptureError("raw_file_name must be page.html")
            raw_sha256 = _sha256(self.raw_sha256, "raw_sha256")
            if type(self.raw_size) is not int or not 0 < self.raw_size <= MAX_RESPONSE_BYTES:
                raise FotMobPageCaptureError(
                    "raw_size must be an exact positive integer within 8 MiB"
                )
            if content_length is not None and content_length != self.raw_size:
                raise FotMobPageCaptureError("content_length must match raw_size")
            safety = _validate_safety(self.safety)
            object.__setattr__(self, "request_date", date)
            object.__setattr__(self, "content_type", content_type)
            object.__setattr__(self, "content_length", content_length)
            object.__setattr__(self, "observed_at", observed_at)
            object.__setattr__(self, "raw_sha256", raw_sha256)
            object.__setattr__(self, "safety", safety)
        except FotMobPageCaptureError:
            raise
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
            raise FotMobPageCaptureError(
                f"invalid page capture manifest: {type(exc).__name__}"
            ) from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "request_date": self.request_date,
            "host": self.host,
            "request_target": self.request_target,
            "request_headers": [list(item) for item in self.request_headers],
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


def build_page_capture_manifest(
    response: Any,
    *,
    request_date: str,
) -> FotMobPageCaptureManifest:
    if not isinstance(response, CapturedFotMobPageResponse):
        raise FotMobPageCaptureError("response must be CapturedFotMobPageResponse")
    response = CapturedFotMobPageResponse(
        status=response.status,
        content_type=response.content_type,
        content_length=response.content_length,
        body=response.body,
        observed_at=response.observed_at,
        network_acquisition_performed=response.network_acquisition_performed,
    )
    return FotMobPageCaptureManifest(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        request_date=validate_request_date(request_date),
        host=ALLOWED_HOST,
        request_target=request_target(request_date),
        request_headers=REQUEST_HEADERS,
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


def page_capture_manifest_to_dict(manifest: Any) -> dict[str, Any]:
    if not isinstance(manifest, FotMobPageCaptureManifest):
        raise FotMobPageCaptureError("manifest must be FotMobPageCaptureManifest")
    return manifest.to_dict()


def canonical_page_capture_manifest_bytes(manifest: Any) -> bytes:
    if not isinstance(manifest, FotMobPageCaptureManifest):
        raise FotMobPageCaptureError("manifest must be FotMobPageCaptureManifest")
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
        raise FotMobPageCaptureError("manifest serialization failed") from exc


def sha256_page_capture_manifest(manifest: Any) -> str:
    return sha256_bytes(canonical_page_capture_manifest_bytes(manifest))


def capture_identifier(
    *, request_date: Any, observed_at: Any, raw_sha256: Any
) -> str:
    identity = {
        "request_date": validate_request_date(request_date),
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
            raise FotMobPageCaptureError(f"duplicate manifest key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise FotMobPageCaptureError(f"invalid manifest constant: {value}")


def strict_json_loads(raw: Any) -> Any:
    if type(raw) is not bytes:
        raise FotMobPageCaptureError("manifest must be exact bytes")
    try:
        text = raw.decode("utf-8", errors="strict")
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except FotMobPageCaptureError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobPageCaptureError("manifest is not strict UTF-8 JSON") from exc


_MANIFEST_KEYS = frozenset(
    field.name for field in dataclasses.fields(FotMobPageCaptureManifest)
)


def manifest_from_mapping(value: Any) -> FotMobPageCaptureManifest:
    if not isinstance(value, Mapping) or set(value) != _MANIFEST_KEYS:
        raise FotMobPageCaptureError("manifest keys mismatch")
    headers = value.get("request_headers")
    if not isinstance(headers, list) or any(
        not isinstance(item, list) or len(item) != 2 for item in headers
    ):
        raise FotMobPageCaptureError("manifest request_headers must be pairs")
    try:
        return FotMobPageCaptureManifest(
            schema_version=value["schema_version"],
            dataset_name=value["dataset_name"],
            request_date=value["request_date"],
            host=value["host"],
            request_target=value["request_target"],
            request_headers=tuple(tuple(item) for item in headers),
            status=value["status"],
            content_type=value["content_type"],
            content_length=value["content_length"],
            observed_at=parse_utc_timestamp(value["observed_at"], "observed_at"),
            network_acquisition_performed=value["network_acquisition_performed"],
            raw_file_name=value["raw_file_name"],
            raw_sha256=value["raw_sha256"],
            raw_size=value["raw_size"],
            safety=value["safety"],
        )
    except FotMobPageCaptureError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobPageCaptureError("manifest is invalid") from exc


def _reject_symlink_components(path: pathlib.Path, label: str) -> None:
    absolute = path if path.is_absolute() else pathlib.Path.cwd() / path
    current = pathlib.Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise FotMobPageCaptureError(f"{label} contains a forbidden symlink")


def verify_page_capture_directory(
    capture_directory: pathlib.Path,
    *,
    allowed_root: pathlib.Path,
    require_network_acquisition_performed: bool = True,
) -> FotMobPageCaptureManifest:
    """Verify byte, schema, hash, and provenance consistency without network."""

    if type(require_network_acquisition_performed) is not bool:
        raise FotMobPageCaptureError("network provenance requirement must be exact bool")
    try:
        root = pathlib.Path(allowed_root)
        capture = pathlib.Path(capture_directory)
    except (TypeError, ValueError) as exc:
        raise FotMobPageCaptureError("capture paths are invalid") from exc
    _reject_symlink_components(root, "allowed root")
    _reject_symlink_components(capture, "capture directory")
    if root.is_symlink() or not root.is_dir():
        raise FotMobPageCaptureError("allowed root must be a non-symlink directory")
    if capture.is_symlink() or not capture.is_dir():
        raise FotMobPageCaptureError("capture directory must be non-symlink directory")
    root_resolved = root.resolve(strict=True)
    capture_resolved = capture.resolve(strict=True)
    try:
        relative = capture_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise FotMobPageCaptureError("capture directory is outside allowed root") from exc
    if len(relative.parts) != 2:
        raise FotMobPageCaptureError("capture directory layout must be YYYYMMDD/<id>")
    entries = {entry.name for entry in capture_resolved.iterdir()}
    if entries != {RAW_FILENAME, MANIFEST_FILENAME}:
        raise FotMobPageCaptureError("capture must contain exactly page.html and manifest.json")
    raw_path = capture_resolved / RAW_FILENAME
    manifest_path = capture_resolved / MANIFEST_FILENAME
    if raw_path.is_symlink() or not raw_path.is_file():
        raise FotMobPageCaptureError("page.html must be a regular non-symlink file")
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise FotMobPageCaptureError("manifest.json must be a regular non-symlink file")
    try:
        raw = raw_path.read_bytes()
        manifest_bytes = manifest_path.read_bytes()
    except OSError as exc:
        raise FotMobPageCaptureError("capture files could not be read") from exc
    manifest = manifest_from_mapping(strict_json_loads(manifest_bytes))
    if manifest.request_date != relative.parts[0]:
        raise FotMobPageCaptureError("manifest date does not match directory")
    expected_id = capture_identifier(
        request_date=manifest.request_date,
        observed_at=manifest.observed_at,
        raw_sha256=manifest.raw_sha256,
    )
    if relative.parts[1] != expected_id:
        raise FotMobPageCaptureError("capture identifier mismatch")
    if manifest.raw_file_name != RAW_FILENAME:
        raise FotMobPageCaptureError("manifest raw filename mismatch")
    if len(raw) != manifest.raw_size:
        raise FotMobPageCaptureError("raw byte size mismatch")
    if sha256_bytes(raw) != manifest.raw_sha256:
        raise FotMobPageCaptureError("raw SHA-256 mismatch")
    if manifest.network_acquisition_performed is not require_network_acquisition_performed:
        raise FotMobPageCaptureError("network acquisition provenance state mismatch")
    expected = build_page_capture_manifest(
        CapturedFotMobPageResponse(
            status=manifest.status,
            content_type=manifest.content_type,
            content_length=manifest.content_length,
            body=raw,
            observed_at=manifest.observed_at,
            network_acquisition_performed=manifest.network_acquisition_performed,
        ),
        request_date=manifest.request_date,
    )
    if expected != manifest:
        raise FotMobPageCaptureError("manifest does not match raw capture")
    if canonical_page_capture_manifest_bytes(expected) != manifest_bytes:
        raise FotMobPageCaptureError("manifest bytes are not canonical")
    return manifest


__all__ = [
    "ALLOWED_HOST",
    "CapturedFotMobPageResponse",
    "DATASET_NAME",
    "FotMobPageCaptureError",
    "FotMobPageCaptureManifest",
    "HTTPS_PORT",
    "MANIFEST_FILENAME",
    "MAX_RESPONSE_BYTES",
    "RAW_FILENAME",
    "REQUEST_HEADERS",
    "SCHEMA_VERSION",
    "build_page_capture_manifest",
    "canonical_page_capture_manifest_bytes",
    "capture_identifier",
    "manifest_from_mapping",
    "page_capture_manifest_to_dict",
    "parse_utc_timestamp",
    "request_target",
    "serialize_utc",
    "sha256_bytes",
    "sha256_page_capture_manifest",
    "strict_json_loads",
    "validate_html_content_type",
    "validate_request_date",
    "verify_page_capture_directory",
]
