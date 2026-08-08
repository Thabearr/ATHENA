"""Deterministic receipts for transparent, one-shot FotMob route probes."""

from __future__ import annotations

import dataclasses
import datetime
import enum
import hashlib
import json
import re
import types
from typing import Any, Mapping, Tuple


SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-source-probe-v1"
ALLOWED_HOST = "www.fotmob.com"
HTTPS_PORT = 443
MAX_SAMPLE_BYTES = 4096
USER_AGENT = "ATHENA/1.0"

_DATE_RE = re.compile(r"^[0-9]{8}$", flags=re.ASCII)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class FotMobSourceProbeError(ValueError):
    """Raised when a source-probe contract fails closed."""


class FotMobProbeRoute(str, enum.Enum):
    MATCHES_API = "matches_api"
    DATE_WEB_PAGE = "date_web_page"


class ProbeTransportOutcome(str, enum.Enum):
    RESPONSE_RECEIVED = "RESPONSE_RECEIVED"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"


class ProbeMediaExpectation(str, enum.Enum):
    JSON = "JSON"
    HTML = "HTML"


_MATCHES_HEADERS: Tuple[Tuple[str, str], ...] = (
    ("Accept", "application/json"),
    ("User-Agent", USER_AGENT),
)
_WEB_HEADERS: Tuple[Tuple[str, str], ...] = (
    ("Accept", "text/html,application/xhtml+xml"),
    ("User-Agent", USER_AGENT),
)
_SAFETY_KEYS = frozenset(
    {
        "network_probe_authorized",
        "fixture_capture_authorized",
        "scraping_authorized",
        "browser_impersonation_authorized",
        "browser_automation_authorized",
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


def validate_probe_date(value: Any) -> str:
    if not isinstance(value, str) or _DATE_RE.fullmatch(value) is None:
        raise FotMobSourceProbeError(
            "probe date must be exactly YYYYMMDD ASCII digits"
        )
    try:
        parsed = datetime.datetime.strptime(value, "%Y%m%d").date()
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobSourceProbeError(
            "probe date must be a valid Gregorian date"
        ) from exc
    if parsed.strftime("%Y%m%d") != value:
        raise FotMobSourceProbeError("probe date must be canonical YYYYMMDD")
    return value


def request_target_for_route(route: Any, request_date: Any) -> str:
    if not isinstance(route, FotMobProbeRoute):
        raise FotMobSourceProbeError("route must be FotMobProbeRoute")
    date = validate_probe_date(request_date)
    if route is FotMobProbeRoute.MATCHES_API:
        return f"/api/matches?date={date}"
    return f"/?date={date}"


def request_headers_for_route(route: Any) -> Tuple[Tuple[str, str], ...]:
    if not isinstance(route, FotMobProbeRoute):
        raise FotMobSourceProbeError("route must be FotMobProbeRoute")
    return _MATCHES_HEADERS if route is FotMobProbeRoute.MATCHES_API else _WEB_HEADERS


def media_expectation_for_route(route: Any) -> ProbeMediaExpectation:
    if not isinstance(route, FotMobProbeRoute):
        raise FotMobSourceProbeError("route must be FotMobProbeRoute")
    if route is FotMobProbeRoute.MATCHES_API:
        return ProbeMediaExpectation.JSON
    return ProbeMediaExpectation.HTML


def sha256_bytes(content: Any) -> str:
    if type(content) is not bytes:
        raise FotMobSourceProbeError("SHA-256 input must be exact bytes")
    return hashlib.sha256(content).hexdigest()


def _utc(value: Any) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise FotMobSourceProbeError("observed_at must be a datetime")
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            raise FotMobSourceProbeError("observed_at must be timezone-aware")
        return value.astimezone(datetime.timezone.utc)
    except FotMobSourceProbeError:
        raise
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobSourceProbeError("observed_at is invalid") from exc


def serialize_utc(value: Any) -> str:
    return _utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _optional_header(value: Any, label: str, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise FotMobSourceProbeError(f"{label} must be a string or None")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise FotMobSourceProbeError(f"{label} is empty or exceeds {maximum} chars")
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise FotMobSourceProbeError(f"{label} contains control characters")
    return normalized


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(_SAFETY_KEYS)}


@dataclasses.dataclass(frozen=True)
class FotMobSourceProbeReceipt:
    schema_version: int
    dataset_name: str
    route: FotMobProbeRoute
    request_date: str
    host: str
    request_target: str
    request_headers: Tuple[Tuple[str, str], ...]
    media_expectation: ProbeMediaExpectation
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
            if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
                raise FotMobSourceProbeError("schema_version must be exact integer 1")
            if self.dataset_name != DATASET_NAME:
                raise FotMobSourceProbeError("dataset_name mismatch")
            if not isinstance(self.route, FotMobProbeRoute):
                raise FotMobSourceProbeError("route must be FotMobProbeRoute")
            date = validate_probe_date(self.request_date)
            if self.host != ALLOWED_HOST:
                raise FotMobSourceProbeError("host must be www.fotmob.com")
            expected_target = request_target_for_route(self.route, date)
            if self.request_target != expected_target:
                raise FotMobSourceProbeError("request_target does not match route and date")
            expected_headers = request_headers_for_route(self.route)
            if type(self.request_headers) is not tuple or self.request_headers != expected_headers:
                raise FotMobSourceProbeError("request_headers do not match truthful route profile")
            if any(type(item) is not tuple or len(item) != 2 for item in self.request_headers):
                raise FotMobSourceProbeError("request_headers must be immutable pairs")
            if self.media_expectation is not media_expectation_for_route(self.route):
                raise FotMobSourceProbeError("media_expectation does not match route")
            if not isinstance(self.transport_outcome, ProbeTransportOutcome):
                raise FotMobSourceProbeError(
                    "transport_outcome must be ProbeTransportOutcome"
                )
            content_type = _optional_header(self.content_type, "content_type", 512)
            location = _optional_header(self.location, "location", 2048)
            if self.content_length is not None and (
                type(self.content_length) is not int or self.content_length < 0
            ):
                raise FotMobSourceProbeError(
                    "content_length must be an exact non-negative integer or None"
                )
            observed = _utc(self.observed_at)
            if type(self.sample_size) is not int or not 0 <= self.sample_size <= MAX_SAMPLE_BYTES:
                raise FotMobSourceProbeError("sample_size must be between 0 and 4096")
            if self.transport_outcome is ProbeTransportOutcome.RESPONSE_RECEIVED:
                if type(self.status_code) is not int or not 100 <= self.status_code <= 599:
                    raise FotMobSourceProbeError(
                        "response status_code must be an exact integer from 100 to 599"
                    )
                if not isinstance(self.sample_sha256, str) or _SHA256_RE.fullmatch(
                    self.sample_sha256
                ) is None:
                    raise FotMobSourceProbeError(
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
                    raise FotMobSourceProbeError(
                        "transport error receipt must not contain response metadata"
                    )
            if not isinstance(self.safety, Mapping) or set(self.safety) != _SAFETY_KEYS:
                raise FotMobSourceProbeError("safety keys mismatch")
            detached: dict[str, bool] = {}
            for key, value in self.safety.items():
                if type(value) is not bool or value is not False:
                    raise FotMobSourceProbeError(
                        f"safety[{key!r}] must be exact bool False"
                    )
                detached[key] = False
            object.__setattr__(self, "request_date", date)
            object.__setattr__(self, "content_type", content_type)
            object.__setattr__(self, "location", location)
            object.__setattr__(self, "observed_at", observed)
            object.__setattr__(self, "safety", types.MappingProxyType(dict(detached)))
        except FotMobSourceProbeError:
            raise
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
            raise FotMobSourceProbeError(
                f"invalid source probe receipt: {type(exc).__name__}"
            ) from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "route": self.route.value,
            "request_date": self.request_date,
            "host": self.host,
            "request_target": self.request_target,
            "request_headers": [list(item) for item in self.request_headers],
            "media_expectation": self.media_expectation.value,
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
    route: FotMobProbeRoute,
    request_date: str,
    status_code: int,
    content_type: str | None,
    content_length: int | None,
    location: str | None,
    observed_at: datetime.datetime,
    sample: bytes,
) -> FotMobSourceProbeReceipt:
    if type(sample) is not bytes or len(sample) > MAX_SAMPLE_BYTES:
        raise FotMobSourceProbeError("sample must be exact bytes of at most 4096 bytes")
    return FotMobSourceProbeReceipt(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        route=route,
        request_date=request_date,
        host=ALLOWED_HOST,
        request_target=request_target_for_route(route, request_date),
        request_headers=request_headers_for_route(route),
        media_expectation=media_expectation_for_route(route),
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
    route: FotMobProbeRoute,
    request_date: str,
    observed_at: datetime.datetime,
) -> FotMobSourceProbeReceipt:
    return FotMobSourceProbeReceipt(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        route=route,
        request_date=request_date,
        host=ALLOWED_HOST,
        request_target=request_target_for_route(route, request_date),
        request_headers=request_headers_for_route(route),
        media_expectation=media_expectation_for_route(route),
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


def source_probe_receipt_to_dict(receipt: Any) -> dict[str, Any]:
    if not isinstance(receipt, FotMobSourceProbeReceipt):
        raise FotMobSourceProbeError("receipt must be FotMobSourceProbeReceipt")
    return receipt.to_dict()


def canonical_source_probe_bytes(receipt: Any) -> bytes:
    if not isinstance(receipt, FotMobSourceProbeReceipt):
        raise FotMobSourceProbeError("receipt must be FotMobSourceProbeReceipt")
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
        raise FotMobSourceProbeError("receipt serialization failed") from exc


def sha256_source_probe_receipt(receipt: Any) -> str:
    return sha256_bytes(canonical_source_probe_bytes(receipt))


__all__ = [
    "ALLOWED_HOST",
    "DATASET_NAME",
    "FotMobProbeRoute",
    "FotMobSourceProbeError",
    "FotMobSourceProbeReceipt",
    "HTTPS_PORT",
    "MAX_SAMPLE_BYTES",
    "ProbeMediaExpectation",
    "ProbeTransportOutcome",
    "SCHEMA_VERSION",
    "USER_AGENT",
    "build_response_receipt",
    "build_transport_error_receipt",
    "canonical_source_probe_bytes",
    "media_expectation_for_route",
    "request_headers_for_route",
    "request_target_for_route",
    "sha256_bytes",
    "sha256_source_probe_receipt",
    "source_probe_receipt_to_dict",
    "validate_probe_date",
]
