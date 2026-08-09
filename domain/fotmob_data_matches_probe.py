"""Deterministic receipts for the unsigned FotMob data-matches route probe."""

from __future__ import annotations

import dataclasses
import datetime
import enum
import hashlib
import json
import re
import types
from typing import Any, Mapping, Tuple
from urllib.parse import urlencode


SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-data-matches-probe-v1"
ALLOWED_HOST = "www.fotmob.com"
HTTPS_PORT = 443
ALLOWED_PATH = "/api/data/matches"
MAX_SAMPLE_BYTES = 4096
USER_AGENT = "ATHENA/1.0"
MEDIA_EXPECTATION = "application/json"
REQUEST_HEADERS: Tuple[Tuple[str, str], ...] = (
    ("Accept", MEDIA_EXPECTATION),
    ("User-Agent", USER_AGENT),
)

_DATE_RE = re.compile(r"^[0-9]{8}$", flags=re.ASCII)
_TIMEZONE_RE = re.compile(
    r"^[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*$",
    flags=re.ASCII,
)
_CCODE3_RE = re.compile(r"^[A-Z]{3}$", flags=re.ASCII)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "application_signature_reproduction_authorized",
        "cookie_use_authorized",
        "browser_impersonation_authorized",
        "fixture_capture_authorized",
        "fixture_parsing_authorized",
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


class FotMobDataMatchesProbeError(ValueError):
    """Raised when the transparent data-matches probe fails closed."""


class ProbeTransportOutcome(str, enum.Enum):
    RESPONSE_RECEIVED = "RESPONSE_RECEIVED"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"


def validate_request_date(value: Any) -> str:
    if not isinstance(value, str) or _DATE_RE.fullmatch(value) is None:
        raise FotMobDataMatchesProbeError(
            "request date must be exactly YYYYMMDD ASCII digits"
        )
    try:
        parsed = datetime.datetime.strptime(value, "%Y%m%d").date()
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobDataMatchesProbeError(
            "request date must be a valid Gregorian date"
        ) from exc
    if parsed.strftime("%Y%m%d") != value:
        raise FotMobDataMatchesProbeError(
            "request date must be canonical YYYYMMDD"
        )
    return value


def validate_timezone(value: Any) -> str:
    if not isinstance(value, str):
        raise FotMobDataMatchesProbeError("timezone must be an exact string")
    if not value or value != value.strip() or len(value) > 64:
        raise FotMobDataMatchesProbeError(
            "timezone must be an unpadded string of at most 64 characters"
        )
    if not value.isascii() or _TIMEZONE_RE.fullmatch(value) is None:
        raise FotMobDataMatchesProbeError(
            "timezone must use the reviewed ASCII IANA-style form"
        )
    return value


def validate_ccode3(value: Any) -> str:
    if not isinstance(value, str) or _CCODE3_RE.fullmatch(value) is None:
        raise FotMobDataMatchesProbeError(
            "ccode3 must be exactly three uppercase ASCII letters"
        )
    return value


def ordered_query_parameters(
    request_date: Any,
    timezone: Any,
    ccode3: Any,
) -> Tuple[Tuple[str, str], ...]:
    return (
        ("date", validate_request_date(request_date)),
        ("timezone", validate_timezone(timezone)),
        ("ccode3", validate_ccode3(ccode3)),
    )


def serialize_query(
    request_date: Any,
    timezone: Any,
    ccode3: Any,
) -> str:
    try:
        return urlencode(
            ordered_query_parameters(request_date, timezone, ccode3),
            doseq=False,
        )
    except FotMobDataMatchesProbeError:
        raise
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobDataMatchesProbeError("query serialization failed") from exc


def request_target(
    request_date: Any,
    timezone: Any,
    ccode3: Any,
) -> str:
    return f"{ALLOWED_PATH}?{serialize_query(request_date, timezone, ccode3)}"


def request_headers() -> Tuple[Tuple[str, str], ...]:
    return REQUEST_HEADERS


def sha256_bytes(content: Any) -> str:
    if type(content) is not bytes:
        raise FotMobDataMatchesProbeError("SHA-256 input must be exact bytes")
    return hashlib.sha256(content).hexdigest()


def _utc(value: Any) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise FotMobDataMatchesProbeError("observed_at must be a datetime")
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            raise FotMobDataMatchesProbeError(
                "observed_at must be timezone-aware"
            )
        return value.astimezone(datetime.timezone.utc)
    except FotMobDataMatchesProbeError:
        raise
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobDataMatchesProbeError("observed_at is invalid") from exc


def serialize_utc(value: Any) -> str:
    return _utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _optional_header(value: Any, label: str, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise FotMobDataMatchesProbeError(f"{label} must be a string or None")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise FotMobDataMatchesProbeError(
            f"{label} is empty or exceeds {maximum} characters"
        )
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise FotMobDataMatchesProbeError(f"{label} contains control characters")
    return normalized


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(_SAFETY_KEYS)}


@dataclasses.dataclass(frozen=True)
class FotMobDataMatchesProbeReceipt:
    schema_version: int
    dataset_name: str
    request_date: str
    timezone: str
    ccode3: str
    host: str
    request_target: str
    request_headers: Tuple[Tuple[str, str], ...]
    x_mas_included: bool
    media_expectation: str
    transport_outcome: ProbeTransportOutcome
    status_code: int | None
    content_type: str | None
    content_length: int | None
    location: str | None
    observed_at: datetime.datetime
    sample_size: int
    sample_sha256: str | None
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        try:
            if type(self.schema_version) is not int or self.schema_version != 1:
                raise FotMobDataMatchesProbeError(
                    "schema_version must be exact integer 1"
                )
            if self.dataset_name != DATASET_NAME:
                raise FotMobDataMatchesProbeError("dataset_name mismatch")
            date = validate_request_date(self.request_date)
            zone = validate_timezone(self.timezone)
            country = validate_ccode3(self.ccode3)
            if self.host != ALLOWED_HOST:
                raise FotMobDataMatchesProbeError("host must be www.fotmob.com")
            expected_target = request_target(date, zone, country)
            if self.request_target != expected_target:
                raise FotMobDataMatchesProbeError(
                    "request_target does not match the fixed ordered query"
                )
            if type(self.request_headers) is not tuple or self.request_headers != REQUEST_HEADERS:
                raise FotMobDataMatchesProbeError(
                    "request_headers do not match the transparent profile"
                )
            if any(
                type(item) is not tuple or len(item) != 2
                for item in self.request_headers
            ):
                raise FotMobDataMatchesProbeError(
                    "request_headers must be immutable pairs"
                )
            if type(self.x_mas_included) is not bool or self.x_mas_included is not False:
                raise FotMobDataMatchesProbeError(
                    "x_mas_included must be exact bool False"
                )
            if self.media_expectation != MEDIA_EXPECTATION:
                raise FotMobDataMatchesProbeError(
                    "media_expectation must be application/json"
                )
            if not isinstance(self.transport_outcome, ProbeTransportOutcome):
                raise FotMobDataMatchesProbeError(
                    "transport_outcome must be ProbeTransportOutcome"
                )
            content_type = _optional_header(self.content_type, "content_type", 512)
            location = _optional_header(self.location, "location", 2048)
            if self.content_length is not None and (
                type(self.content_length) is not int or self.content_length < 0
            ):
                raise FotMobDataMatchesProbeError(
                    "content_length must be an exact non-negative integer or None"
                )
            observed_at = _utc(self.observed_at)
            if (
                type(self.sample_size) is not int
                or not 0 <= self.sample_size <= MAX_SAMPLE_BYTES
            ):
                raise FotMobDataMatchesProbeError(
                    "sample_size must be between 0 and 4096"
                )
            if self.transport_outcome is ProbeTransportOutcome.RESPONSE_RECEIVED:
                if type(self.status_code) is not int or not 100 <= self.status_code <= 599:
                    raise FotMobDataMatchesProbeError(
                        "response status_code must be an exact integer from 100 to 599"
                    )
                if (
                    not isinstance(self.sample_sha256, str)
                    or _SHA256_RE.fullmatch(self.sample_sha256) is None
                ):
                    raise FotMobDataMatchesProbeError(
                        "response sample_sha256 must be lowercase SHA-256"
                    )
            else:
                if any(
                    item is not None
                    for item in (
                        self.status_code,
                        content_type,
                        self.content_length,
                        location,
                        self.sample_sha256,
                    )
                ) or self.sample_size != 0:
                    raise FotMobDataMatchesProbeError(
                        "transport error receipt must not contain response metadata"
                    )
            if not isinstance(self.safety, Mapping) or set(self.safety) != _SAFETY_KEYS:
                raise FotMobDataMatchesProbeError("safety keys mismatch")
            detached: dict[str, bool] = {}
            for key, value in self.safety.items():
                if type(value) is not bool or value is not False:
                    raise FotMobDataMatchesProbeError(
                        f"safety[{key!r}] must be exact bool False"
                    )
                detached[key] = False
            object.__setattr__(self, "request_date", date)
            object.__setattr__(self, "timezone", zone)
            object.__setattr__(self, "ccode3", country)
            object.__setattr__(self, "content_type", content_type)
            object.__setattr__(self, "location", location)
            object.__setattr__(self, "observed_at", observed_at)
            object.__setattr__(
                self,
                "safety",
                types.MappingProxyType(dict(detached)),
            )
        except FotMobDataMatchesProbeError:
            raise
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
            raise FotMobDataMatchesProbeError(
                f"invalid data-matches probe receipt: {type(exc).__name__}"
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
            "media_expectation": self.media_expectation,
            "transport_outcome": self.transport_outcome.value,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "content_length": self.content_length,
            "location": self.location,
            "observed_at": serialize_utc(self.observed_at),
            "sample_size": self.sample_size,
            "sample_sha256": self.sample_sha256,
            "safety": dict(self.safety),
        }


def build_response_receipt(
    *,
    request_date: str,
    timezone: str,
    ccode3: str,
    status_code: int,
    content_type: str | None,
    content_length: int | None,
    location: str | None,
    observed_at: datetime.datetime,
    sample: bytes,
) -> FotMobDataMatchesProbeReceipt:
    if type(sample) is not bytes or len(sample) > MAX_SAMPLE_BYTES:
        raise FotMobDataMatchesProbeError(
            "sample must be exact bytes of at most 4096 bytes"
        )
    return FotMobDataMatchesProbeReceipt(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        request_date=request_date,
        timezone=timezone,
        ccode3=ccode3,
        host=ALLOWED_HOST,
        request_target=request_target(request_date, timezone, ccode3),
        request_headers=REQUEST_HEADERS,
        x_mas_included=False,
        media_expectation=MEDIA_EXPECTATION,
        transport_outcome=ProbeTransportOutcome.RESPONSE_RECEIVED,
        status_code=status_code,
        content_type=content_type,
        content_length=content_length,
        location=location,
        observed_at=observed_at,
        sample_size=len(sample),
        sample_sha256=sha256_bytes(sample),
        safety=_default_safety(),
    )


def build_transport_error_receipt(
    *,
    request_date: str,
    timezone: str,
    ccode3: str,
    observed_at: datetime.datetime,
) -> FotMobDataMatchesProbeReceipt:
    return FotMobDataMatchesProbeReceipt(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        request_date=request_date,
        timezone=timezone,
        ccode3=ccode3,
        host=ALLOWED_HOST,
        request_target=request_target(request_date, timezone, ccode3),
        request_headers=REQUEST_HEADERS,
        x_mas_included=False,
        media_expectation=MEDIA_EXPECTATION,
        transport_outcome=ProbeTransportOutcome.TRANSPORT_ERROR,
        status_code=None,
        content_type=None,
        content_length=None,
        location=None,
        observed_at=observed_at,
        sample_size=0,
        sample_sha256=None,
        safety=_default_safety(),
    )


def data_matches_probe_receipt_to_dict(
    receipt: Any,
) -> dict[str, Any]:
    if not isinstance(receipt, FotMobDataMatchesProbeReceipt):
        raise FotMobDataMatchesProbeError(
            "receipt must be FotMobDataMatchesProbeReceipt"
        )
    return receipt.to_dict()


def canonical_data_matches_probe_receipt_bytes(receipt: Any) -> bytes:
    if not isinstance(receipt, FotMobDataMatchesProbeReceipt):
        raise FotMobDataMatchesProbeError(
            "receipt must be FotMobDataMatchesProbeReceipt"
        )
    try:
        return (
            json.dumps(
                receipt.to_dict(),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobDataMatchesProbeError("receipt serialization failed") from exc


def sha256_data_matches_probe_receipt(receipt: Any) -> str:
    return sha256_bytes(canonical_data_matches_probe_receipt_bytes(receipt))


__all__ = [
    "ALLOWED_HOST",
    "ALLOWED_PATH",
    "DATASET_NAME",
    "FotMobDataMatchesProbeError",
    "FotMobDataMatchesProbeReceipt",
    "HTTPS_PORT",
    "MAX_SAMPLE_BYTES",
    "MEDIA_EXPECTATION",
    "ProbeTransportOutcome",
    "REQUEST_HEADERS",
    "SCHEMA_VERSION",
    "USER_AGENT",
    "build_response_receipt",
    "build_transport_error_receipt",
    "canonical_data_matches_probe_receipt_bytes",
    "data_matches_probe_receipt_to_dict",
    "ordered_query_parameters",
    "request_headers",
    "request_target",
    "serialize_query",
    "sha256_bytes",
    "sha256_data_matches_probe_receipt",
    "validate_ccode3",
    "validate_request_date",
    "validate_timezone",
]
