"""Strict evidence contract for public read-only SportyBet Lite HTML captures.

This module deliberately models source evidence only.  It does not authorize
bookmaker equivalence, pricing, selection, slip construction, or BET.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import enum
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import types
from typing import Any, Mapping, Tuple
from urllib.parse import urlencode


SCHEMA_VERSION = 1
DATASET_NAME = "athena-sportybet-lite-source-capture-v1"
PROVIDER = "SportyBet"
ALLOWED_HOST = "www.sportybet.com"
HTTPS_PORT = 443
INDEX_PATH = "/ng/lite"
EVENT_DETAIL_PATH = "/ng/lite/preMatch/detail"
FOOTBALL_SPORT_ID = "sr:sport:1"
DEFAULT_MARKET_GROUP = "Main"
REQUEST_HEADERS: Tuple[Tuple[str, str], ...] = (
    ("Accept", "text/html,application/xhtml+xml"),
    ("User-Agent", "ATHENA/1.0"),
)
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_MANIFEST_BYTES = 128 * 1024
RAW_FILENAME = "response.html"
MANIFEST_FILENAME = "manifest.json"
ALLOWED_OUTPUT_RELATIVE = Path(
    ".cache/athena-research/sportybet-live-source-captures"
)

_EVENT_ID_RE = re.compile(r"^sr:match:[1-9][0-9]*$", flags=re.ASCII)
_SPORT_ID_RE = re.compile(r"^sr:sport:[1-9][0-9]*$", flags=re.ASCII)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_MEDIA_TYPE_TOKEN_RE = re.compile(
    r"^[A-Za-z0-9!#$%&'*+.^_`|~-]+$", flags=re.ASCII
)
_SAFETY_KEYS = frozenset(
    {
        "bookmaker_equivalence_authorized",
        "booking_code_authorized",
        "canonical_market_mapping_authorized",
        "execution_bookmaker_authorized",
        "fixture_reconciliation_authorized",
        "model_integration_authorized",
        "pricing_authorized",
        "selection_authorized",
        "slip_construction_authorized",
        "slip_vetting_authorized",
        "sportybet_execution_authorized",
        "bet_authorized",
    }
)


class SportyBetLiteCaptureError(ValueError):
    """Raised when SportyBet source evidence fails closed."""


class SportyBetLiteRequestKind(str, enum.Enum):
    INDEX = "INDEX"
    EVENT_DETAIL = "EVENT_DETAIL"


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(_SAFETY_KEYS)}


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise SportyBetLiteCaptureError("safety keys mismatch")
    detached: dict[str, bool] = {}
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise SportyBetLiteCaptureError(
                f"safety[{key!r}] must be exact bool False"
            )
        detached[key] = False
    return types.MappingProxyType(detached)


def validate_event_id(value: Any) -> str:
    if not isinstance(value, str) or _EVENT_ID_RE.fullmatch(value) is None:
        raise SportyBetLiteCaptureError(
            "event_id must use exact provider-native sr:match:<positive integer> form"
        )
    return value


def validate_sport_id(value: Any) -> str:
    if not isinstance(value, str) or _SPORT_ID_RE.fullmatch(value) is None:
        raise SportyBetLiteCaptureError(
            "sport_id must use exact provider-native sr:sport:<positive integer> form"
        )
    return value


def _utc(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, dt.datetime):
        raise SportyBetLiteCaptureError(f"{label} must be a datetime")
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            raise SportyBetLiteCaptureError(f"{label} must be timezone-aware")
        return value.astimezone(dt.timezone.utc)
    except SportyBetLiteCaptureError:
        raise
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise SportyBetLiteCaptureError(f"{label} is invalid") from exc


def serialize_utc(value: Any) -> str:
    return _utc(value, "timestamp").isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def parse_utc_timestamp(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise SportyBetLiteCaptureError(
            f"{label} must be a timezone-aware ISO-8601 string"
        )
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return _utc(dt.datetime.fromisoformat(text), label)
    except SportyBetLiteCaptureError:
        raise
    except (TypeError, ValueError, OverflowError) as exc:
        raise SportyBetLiteCaptureError(f"{label} is invalid ISO-8601") from exc


def validate_html_content_type(value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise SportyBetLiteCaptureError("Content-Type must identify HTML")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise SportyBetLiteCaptureError(
            "Content-Type must not contain ASCII control characters"
        )
    parts = value.split(";")
    if parts[0].strip().lower() != "text/html":
        raise SportyBetLiteCaptureError("Content-Type must be text/html")
    parameter_names: set[str] = set()
    for raw_parameter in parts[1:]:
        parameter = raw_parameter.strip()
        if not parameter or parameter.count("=") != 1:
            raise SportyBetLiteCaptureError(
                "Content-Type parameters must use token=token syntax"
            )
        raw_name, raw_value = parameter.split("=", 1)
        name = raw_name.strip()
        parameter_value = raw_value.strip()
        if (
            _MEDIA_TYPE_TOKEN_RE.fullmatch(name) is None
            or _MEDIA_TYPE_TOKEN_RE.fullmatch(parameter_value) is None
        ):
            raise SportyBetLiteCaptureError(
                "Content-Type parameter names and values must be ASCII tokens"
            )
        canonical_name = name.lower()
        if canonical_name in parameter_names:
            raise SportyBetLiteCaptureError(
                "Content-Type parameter names must be unique"
            )
        parameter_names.add(canonical_name)
    return value


def sha256_bytes(content: Any) -> str:
    if type(content) is not bytes:
        raise SportyBetLiteCaptureError("SHA-256 input must be exact bytes")
    return hashlib.sha256(content).hexdigest()


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise SportyBetLiteCaptureError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def ordered_query_parameters(
    request_kind: SportyBetLiteRequestKind,
    *,
    event_id: str | None,
    sport_id: str | None,
    market_groups_name: str | None,
) -> Tuple[Tuple[str, str], ...]:
    if not isinstance(request_kind, SportyBetLiteRequestKind):
        raise SportyBetLiteCaptureError(
            "request_kind must be SportyBetLiteRequestKind"
        )
    if request_kind is SportyBetLiteRequestKind.INDEX:
        if event_id is not None or sport_id is not None or market_groups_name is not None:
            raise SportyBetLiteCaptureError(
                "INDEX request must not carry event, sport, or market-group parameters"
            )
        return ()
    event = validate_event_id(event_id)
    sport = validate_sport_id(sport_id)
    if market_groups_name != DEFAULT_MARKET_GROUP:
        raise SportyBetLiteCaptureError(
            f"market_groups_name must be exact {DEFAULT_MARKET_GROUP!r}"
        )
    return (
        ("eventId", event),
        ("marketGroupsName", market_groups_name),
        ("sportId", sport),
    )


def request_target(
    request_kind: SportyBetLiteRequestKind,
    *,
    event_id: str | None = None,
    sport_id: str | None = None,
    market_groups_name: str | None = None,
) -> str:
    parameters = ordered_query_parameters(
        request_kind,
        event_id=event_id,
        sport_id=sport_id,
        market_groups_name=market_groups_name,
    )
    if request_kind is SportyBetLiteRequestKind.INDEX:
        return INDEX_PATH
    return f"{EVENT_DETAIL_PATH}?{urlencode(parameters, doseq=False)}"


@dataclasses.dataclass(frozen=True)
class CapturedSportyBetLiteResponse:
    status: int
    content_type: str
    content_length: int | None
    body: bytes
    observed_at: dt.datetime
    network_acquisition_performed: bool

    def __post_init__(self) -> None:
        if type(self.status) is not int or self.status != 200:
            raise SportyBetLiteCaptureError("status must be exact integer 200")
        content_type = validate_html_content_type(self.content_type)
        if self.content_length is not None and (
            type(self.content_length) is not int
            or self.content_length < 0
            or self.content_length > MAX_RESPONSE_BYTES
        ):
            raise SportyBetLiteCaptureError(
                "content_length must be a bounded non-negative integer or None"
            )
        if type(self.body) is not bytes or not self.body:
            raise SportyBetLiteCaptureError("body must be non-empty exact bytes")
        if len(self.body) > MAX_RESPONSE_BYTES:
            raise SportyBetLiteCaptureError("body exceeds the 8 MiB limit")
        if self.content_length is not None and self.content_length != len(self.body):
            raise SportyBetLiteCaptureError(
                "Content-Length does not match body size"
            )
        observed_at = _utc(self.observed_at, "observed_at")
        if type(self.network_acquisition_performed) is not bool:
            raise SportyBetLiteCaptureError(
                "network_acquisition_performed must be exact bool"
            )
        object.__setattr__(self, "content_type", content_type)
        object.__setattr__(self, "observed_at", observed_at)


@dataclasses.dataclass(frozen=True)
class SportyBetLiteCaptureManifest:
    schema_version: int
    dataset_name: str
    provider: str
    request_kind: SportyBetLiteRequestKind
    host: str
    request_target: str
    request_headers: Tuple[Tuple[str, str], ...]
    event_id: str | None
    sport_id: str | None
    market_groups_name: str | None
    status: int
    content_type: str
    content_length: int | None
    observed_at: dt.datetime
    provider_quote_at: None
    provider_snapshot_id: None
    network_acquisition_performed: bool
    raw_file_name: str
    raw_sha256: str
    raw_size: int
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise SportyBetLiteCaptureError("schema_version mismatch")
        if self.dataset_name != DATASET_NAME:
            raise SportyBetLiteCaptureError("dataset_name mismatch")
        if self.provider != PROVIDER:
            raise SportyBetLiteCaptureError("provider must be SportyBet")
        if not isinstance(self.request_kind, SportyBetLiteRequestKind):
            raise SportyBetLiteCaptureError("request_kind is invalid")
        if self.host != ALLOWED_HOST:
            raise SportyBetLiteCaptureError("host must be www.sportybet.com")
        expected_target = request_target(
            self.request_kind,
            event_id=self.event_id,
            sport_id=self.sport_id,
            market_groups_name=self.market_groups_name,
        )
        if self.request_target != expected_target:
            raise SportyBetLiteCaptureError("request_target mismatch")
        if type(self.request_headers) is not tuple or self.request_headers != REQUEST_HEADERS:
            raise SportyBetLiteCaptureError("request_headers mismatch")
        if any(type(item) is not tuple or len(item) != 2 for item in self.request_headers):
            raise SportyBetLiteCaptureError("request_headers must be immutable pairs")
        if type(self.status) is not int or self.status != 200:
            raise SportyBetLiteCaptureError("status must be exact integer 200")
        content_type = validate_html_content_type(self.content_type)
        if self.content_length is not None and (
            type(self.content_length) is not int
            or self.content_length < 0
            or self.content_length > MAX_RESPONSE_BYTES
        ):
            raise SportyBetLiteCaptureError(
                "content_length must be a bounded non-negative integer or None"
            )
        observed_at = _utc(self.observed_at, "observed_at")
        if self.provider_quote_at is not None:
            raise SportyBetLiteCaptureError(
                "provider_quote_at is unproven for the reviewed Lite HTML surface"
            )
        if self.provider_snapshot_id is not None:
            raise SportyBetLiteCaptureError(
                "provider_snapshot_id is unproven for the reviewed Lite HTML surface"
            )
        if type(self.network_acquisition_performed) is not bool:
            raise SportyBetLiteCaptureError(
                "network_acquisition_performed must be exact bool"
            )
        if self.raw_file_name != RAW_FILENAME:
            raise SportyBetLiteCaptureError("raw_file_name mismatch")
        raw_sha256 = _sha256(self.raw_sha256, "raw_sha256")
        if type(self.raw_size) is not int or not 0 < self.raw_size <= MAX_RESPONSE_BYTES:
            raise SportyBetLiteCaptureError("raw_size is invalid")
        if self.content_length is not None and self.content_length != self.raw_size:
            raise SportyBetLiteCaptureError("content_length must match raw_size")
        safety = _validate_safety(self.safety)
        object.__setattr__(self, "content_type", content_type)
        object.__setattr__(self, "observed_at", observed_at)
        object.__setattr__(self, "raw_sha256", raw_sha256)
        object.__setattr__(self, "safety", safety)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "provider": self.provider,
            "request_kind": self.request_kind.value,
            "host": self.host,
            "request_target": self.request_target,
            "request_headers": [list(item) for item in self.request_headers],
            "event_id": self.event_id,
            "sport_id": self.sport_id,
            "market_groups_name": self.market_groups_name,
            "status": self.status,
            "content_type": self.content_type,
            "content_length": self.content_length,
            "observed_at": serialize_utc(self.observed_at),
            "provider_quote_at": None,
            "provider_snapshot_id": None,
            "network_acquisition_performed": self.network_acquisition_performed,
            "raw_file_name": self.raw_file_name,
            "raw_sha256": self.raw_sha256,
            "raw_size": self.raw_size,
            "safety": dict(self.safety),
        }


def build_capture_manifest(
    response: Any,
    *,
    request_kind: SportyBetLiteRequestKind,
    event_id: str | None = None,
    sport_id: str | None = None,
    market_groups_name: str | None = None,
) -> SportyBetLiteCaptureManifest:
    if not isinstance(response, CapturedSportyBetLiteResponse):
        raise SportyBetLiteCaptureError(
            "response must be CapturedSportyBetLiteResponse"
        )
    target = request_target(
        request_kind,
        event_id=event_id,
        sport_id=sport_id,
        market_groups_name=market_groups_name,
    )
    return SportyBetLiteCaptureManifest(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        provider=PROVIDER,
        request_kind=request_kind,
        host=ALLOWED_HOST,
        request_target=target,
        request_headers=REQUEST_HEADERS,
        event_id=event_id,
        sport_id=sport_id,
        market_groups_name=market_groups_name,
        status=response.status,
        content_type=response.content_type,
        content_length=response.content_length,
        observed_at=response.observed_at,
        provider_quote_at=None,
        provider_snapshot_id=None,
        network_acquisition_performed=response.network_acquisition_performed,
        raw_file_name=RAW_FILENAME,
        raw_sha256=sha256_bytes(response.body),
        raw_size=len(response.body),
        safety=_default_safety(),
    )


def canonical_manifest_bytes(manifest: Any) -> bytes:
    if not isinstance(manifest, SportyBetLiteCaptureManifest):
        raise SportyBetLiteCaptureError(
            "manifest must be SportyBetLiteCaptureManifest"
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
        raise SportyBetLiteCaptureError("manifest serialization failed") from exc


def capture_identifier(manifest: Any) -> str:
    if not isinstance(manifest, SportyBetLiteCaptureManifest):
        raise SportyBetLiteCaptureError(
            "manifest must be SportyBetLiteCaptureManifest"
        )
    identity = {
        "provider": manifest.provider,
        "request_target": manifest.request_target,
        "observed_at": serialize_utc(manifest.observed_at),
    }
    raw = json.dumps(
        identity,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(raw)[:24]


def _reject_duplicate_keys(pairs: list[tuple[Any, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SportyBetLiteCaptureError(f"duplicate manifest key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise SportyBetLiteCaptureError(f"invalid manifest constant: {value}")


def strict_json_loads(raw: Any) -> Any:
    if type(raw) is not bytes:
        raise SportyBetLiteCaptureError("manifest must be exact bytes")
    try:
        return json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except SportyBetLiteCaptureError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise SportyBetLiteCaptureError("manifest is not strict UTF-8 JSON") from exc


_MANIFEST_KEYS = frozenset(
    field.name for field in dataclasses.fields(SportyBetLiteCaptureManifest)
)


def manifest_from_mapping(value: Any) -> SportyBetLiteCaptureManifest:
    if not isinstance(value, Mapping) or set(value) != _MANIFEST_KEYS:
        raise SportyBetLiteCaptureError("manifest keys mismatch")
    headers = value.get("request_headers")
    if not isinstance(headers, list) or any(
        not isinstance(item, list) or len(item) != 2 for item in headers
    ):
        raise SportyBetLiteCaptureError("request_headers must be pairs")
    try:
        request_kind = SportyBetLiteRequestKind(value["request_kind"])
    except (TypeError, ValueError) as exc:
        raise SportyBetLiteCaptureError("request_kind is invalid") from exc
    return SportyBetLiteCaptureManifest(
        schema_version=value["schema_version"],
        dataset_name=value["dataset_name"],
        provider=value["provider"],
        request_kind=request_kind,
        host=value["host"],
        request_target=value["request_target"],
        request_headers=tuple(tuple(item) for item in headers),
        event_id=value["event_id"],
        sport_id=value["sport_id"],
        market_groups_name=value["market_groups_name"],
        status=value["status"],
        content_type=value["content_type"],
        content_length=value["content_length"],
        observed_at=parse_utc_timestamp(value["observed_at"], "observed_at"),
        provider_quote_at=value["provider_quote_at"],
        provider_snapshot_id=value["provider_snapshot_id"],
        network_acquisition_performed=value["network_acquisition_performed"],
        raw_file_name=value["raw_file_name"],
        raw_sha256=value["raw_sha256"],
        raw_size=value["raw_size"],
        safety=value["safety"],
    )


def _reject_symlink_components(path: Path, label: str) -> None:
    absolute = path if path.is_absolute() else Path.cwd() / path
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise SportyBetLiteCaptureError(
                f"{label} contains a forbidden symlink"
            )


def validate_output_root(
    output_root: Any,
    *,
    repository_root: Path,
) -> Path:
    repository = Path(repository_root).resolve(strict=True)
    expected = repository / ALLOWED_OUTPUT_RELATIVE
    try:
        supplied = Path(output_root)
    except (TypeError, ValueError) as exc:
        raise SportyBetLiteCaptureError("output root is invalid") from exc
    if ".." in supplied.parts:
        raise SportyBetLiteCaptureError("output root must not contain traversal")
    supplied_absolute = supplied if supplied.is_absolute() else repository / supplied
    _reject_symlink_components(supplied_absolute, "output root")
    if supplied_absolute.resolve(strict=False) != expected.resolve(strict=False):
        raise SportyBetLiteCaptureError(
            "output root must be .cache/athena-research/sportybet-live-source-captures"
        )
    if expected.exists() and (expected.is_symlink() or not expected.is_dir()):
        raise SportyBetLiteCaptureError(
            "output root must be a non-symlink directory"
        )
    return expected


def _read_regular(path: Path, *, maximum: int, label: str) -> bytes:
    if path.is_symlink():
        raise SportyBetLiteCaptureError(f"{label} must not be a symlink")
    try:
        meta = path.stat()
    except OSError as exc:
        raise SportyBetLiteCaptureError(f"{label} cannot be inspected") from exc
    if not stat.S_ISREG(meta.st_mode) or not 0 < meta.st_size <= maximum:
        raise SportyBetLiteCaptureError(f"{label} must be a bounded regular file")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise SportyBetLiteCaptureError(f"{label} cannot be read") from exc
    if not 0 < len(data) <= maximum:
        raise SportyBetLiteCaptureError(f"{label} size is invalid")
    return data


def verify_capture_directory(
    capture_directory: Any,
    *,
    allowed_root: Path,
    require_network_acquisition_performed: bool = True,
) -> SportyBetLiteCaptureManifest:
    if type(require_network_acquisition_performed) is not bool:
        raise SportyBetLiteCaptureError(
            "network provenance requirement must be exact bool"
        )
    capture = Path(capture_directory)
    root = Path(allowed_root)
    if ".." in capture.parts or ".." in root.parts:
        raise SportyBetLiteCaptureError("capture paths must not contain traversal")
    _reject_symlink_components(capture, "capture directory")
    _reject_symlink_components(root, "allowed root")
    try:
        resolved_root = root.resolve(strict=True)
        resolved_capture = capture.resolve(strict=True)
    except OSError as exc:
        raise SportyBetLiteCaptureError("capture path cannot be resolved") from exc
    try:
        resolved_capture.relative_to(resolved_root)
    except ValueError as exc:
        raise SportyBetLiteCaptureError("capture escapes allowed root") from exc
    if capture.is_symlink() or not capture.is_dir():
        raise SportyBetLiteCaptureError(
            "capture directory must be a non-symlink directory"
        )
    names = sorted(item.name for item in capture.iterdir())
    if names != [MANIFEST_FILENAME, RAW_FILENAME]:
        raise SportyBetLiteCaptureError("capture directory contents mismatch")
    raw = _read_regular(capture / RAW_FILENAME, maximum=MAX_RESPONSE_BYTES, label="raw response")
    manifest_raw = _read_regular(
        capture / MANIFEST_FILENAME,
        maximum=MAX_MANIFEST_BYTES,
        label="manifest",
    )
    manifest = manifest_from_mapping(strict_json_loads(manifest_raw))
    if manifest_raw != canonical_manifest_bytes(manifest):
        raise SportyBetLiteCaptureError("manifest bytes are not canonical")
    if sha256_bytes(raw) != manifest.raw_sha256 or len(raw) != manifest.raw_size:
        raise SportyBetLiteCaptureError("raw evidence identity mismatch")
    if require_network_acquisition_performed and not manifest.network_acquisition_performed:
        raise SportyBetLiteCaptureError("capture lacks required network provenance")
    return manifest


def _write_exclusive(path: Path, content: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise SportyBetLiteCaptureError(f"refusing to overwrite {path.name}") from exc
    except OSError as exc:
        raise SportyBetLiteCaptureError(f"could not durably write {path.name}") from exc


def store_capture(
    response: Any,
    *,
    request_kind: SportyBetLiteRequestKind,
    repository_root: Path,
    output_root: Path = ALLOWED_OUTPUT_RELATIVE,
    event_id: str | None = None,
    sport_id: str | None = None,
    market_groups_name: str | None = None,
) -> tuple[Path, SportyBetLiteCaptureManifest]:
    if not isinstance(response, CapturedSportyBetLiteResponse):
        raise SportyBetLiteCaptureError(
            "response must be CapturedSportyBetLiteResponse"
        )
    root = validate_output_root(output_root, repository_root=repository_root)
    manifest = build_capture_manifest(
        response,
        request_kind=request_kind,
        event_id=event_id,
        sport_id=sport_id,
        market_groups_name=market_groups_name,
    )
    capture_id = capture_identifier(manifest)
    capture_directory = root / capture_id
    if capture_directory.exists():
        existing = verify_capture_directory(
            capture_directory,
            allowed_root=root,
            require_network_acquisition_performed=False,
        )
        if existing.to_dict() != manifest.to_dict():
            raise SportyBetLiteCaptureError(
                "capture identifier collision with different manifest"
            )
        existing_raw = _read_regular(
            capture_directory / RAW_FILENAME,
            maximum=MAX_RESPONSE_BYTES,
            label="raw response",
        )
        if existing_raw != response.body:
            raise SportyBetLiteCaptureError(
                "capture identifier collision with different raw bytes"
            )
        return capture_directory, existing
    root.mkdir(parents=True, exist_ok=True)
    _reject_symlink_components(root, "output root")
    try:
        capture_directory.mkdir(exist_ok=False)
    except FileExistsError:
        return store_capture(
            response,
            request_kind=request_kind,
            repository_root=repository_root,
            output_root=output_root,
            event_id=event_id,
            sport_id=sport_id,
            market_groups_name=market_groups_name,
        )
    except OSError as exc:
        raise SportyBetLiteCaptureError("could not create capture directory") from exc
    try:
        _write_exclusive(capture_directory / RAW_FILENAME, response.body)
        _write_exclusive(
            capture_directory / MANIFEST_FILENAME,
            canonical_manifest_bytes(manifest),
        )
        verified = verify_capture_directory(
            capture_directory,
            allowed_root=root,
            require_network_acquisition_performed=False,
        )
        return capture_directory, verified
    except Exception:
        # Never silently reuse a partially-written directory.  Leaving it behind
        # is fail-closed evidence of an interrupted publication attempt.
        raise
