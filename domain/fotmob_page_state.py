"""Strict offline assessment of reviewed FotMob Next.js date-page state."""

from __future__ import annotations

import dataclasses
import datetime
import enum
import hashlib
from html.parser import HTMLParser
import json
import re
import types
from typing import Any, Mapping

from domain.fotmob_page_capture import (
    DATASET_NAME as SOURCE_CAPTURE_DATASET_NAME,
    MAX_RESPONSE_BYTES,
    SCHEMA_VERSION as SOURCE_CAPTURE_SCHEMA_VERSION,
    FotMobPageCaptureError,
    FotMobPageCaptureManifest,
    serialize_utc,
    sha256_page_capture_manifest,
    validate_request_date,
)


SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-page-state-assessment-v1"
NEXT_DATA_ID = "__NEXT_DATA__"
NEXT_DATA_TYPE = "application/json"
FALLBACK_KEY = "notableMatches:en:USA"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFETY_KEYS = frozenset(
    {
        "network_authorized",
        "external_asset_retrieval_authorized",
        "script_execution_authorized",
        "dom_fixture_fallback_authorized",
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


class FotMobPageStateError(ValueError):
    """Raised when reviewed page-state evidence fails closed."""


class FotMobFixtureAvailability(str, enum.Enum):
    NO_FIXTURE_DATA = "NO_FIXTURE_DATA"


def _utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise FotMobPageStateError(f"{label} must be a datetime")
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            raise FotMobPageStateError(f"{label} must be timezone-aware")
        return value.astimezone(datetime.timezone.utc)
    except FotMobPageStateError:
        raise
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobPageStateError(f"{label} is invalid") from exc


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise FotMobPageStateError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _date(value: Any, label: str) -> str:
    try:
        return validate_request_date(value)
    except FotMobPageCaptureError as exc:
        raise FotMobPageStateError(f"{label} must be canonical YYYYMMDD") from exc


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(_SAFETY_KEYS)}


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise FotMobPageStateError("safety keys mismatch")
    detached: dict[str, bool] = {}
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise FotMobPageStateError(f"safety[{key!r}] must be exact bool False")
        detached[key] = False
    return types.MappingProxyType(dict(detached))


@dataclasses.dataclass(frozen=True)
class FotMobPageStateAssessment:
    schema_version: int
    dataset_name: str
    source_capture_dataset_name: str
    source_capture_schema_version: int
    source_capture_manifest_sha256: str
    source_raw_sha256: str
    source_raw_size: int
    source_observed_at: datetime.datetime
    request_date: str
    next_data_element_count: int
    next_data_id: str
    next_data_type: str
    next_data_query_date: str
    fallback_key: str
    match_count: int
    fixture_availability: FotMobFixtureAvailability
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        try:
            if type(self.schema_version) is not int or self.schema_version != 1:
                raise FotMobPageStateError("schema_version must be exact integer 1")
            if self.dataset_name != DATASET_NAME:
                raise FotMobPageStateError(f"dataset_name must be {DATASET_NAME}")
            if self.source_capture_dataset_name != SOURCE_CAPTURE_DATASET_NAME:
                raise FotMobPageStateError("source capture dataset must be PR #35 v1")
            if (
                type(self.source_capture_schema_version) is not int
                or self.source_capture_schema_version != SOURCE_CAPTURE_SCHEMA_VERSION
            ):
                raise FotMobPageStateError(
                    "source_capture_schema_version must be exact integer 1"
                )
            manifest_sha = _sha256(
                self.source_capture_manifest_sha256,
                "source_capture_manifest_sha256",
            )
            raw_sha = _sha256(self.source_raw_sha256, "source_raw_sha256")
            if (
                type(self.source_raw_size) is not int
                or not 0 < self.source_raw_size <= MAX_RESPONSE_BYTES
            ):
                raise FotMobPageStateError(
                    "source_raw_size must be an exact positive integer within 8 MiB"
                )
            observed_at = _utc(self.source_observed_at, "source_observed_at")
            request_date = _date(self.request_date, "request_date")
            query_date = _date(self.next_data_query_date, "next_data_query_date")
            if query_date != request_date:
                raise FotMobPageStateError(
                    "next_data_query_date must equal request_date"
                )
            if (
                type(self.next_data_element_count) is not int
                or self.next_data_element_count != 1
            ):
                raise FotMobPageStateError(
                    "next_data_element_count must be exact integer 1"
                )
            if self.next_data_id != NEXT_DATA_ID:
                raise FotMobPageStateError(f"next_data_id must be {NEXT_DATA_ID}")
            if self.next_data_type != NEXT_DATA_TYPE:
                raise FotMobPageStateError(
                    f"next_data_type must be {NEXT_DATA_TYPE}"
                )
            if self.fallback_key != FALLBACK_KEY:
                raise FotMobPageStateError(f"fallback_key must be {FALLBACK_KEY}")
            if type(self.match_count) is not int or self.match_count != 0:
                raise FotMobPageStateError("match_count must be exact integer 0")
            if self.fixture_availability is not FotMobFixtureAvailability.NO_FIXTURE_DATA:
                raise FotMobPageStateError(
                    "fixture_availability must be NO_FIXTURE_DATA"
                )
            safety = _validate_safety(self.safety)
            object.__setattr__(self, "source_capture_manifest_sha256", manifest_sha)
            object.__setattr__(self, "source_raw_sha256", raw_sha)
            object.__setattr__(self, "source_observed_at", observed_at)
            object.__setattr__(self, "request_date", request_date)
            object.__setattr__(self, "next_data_query_date", query_date)
            object.__setattr__(self, "safety", safety)
        except FotMobPageStateError:
            raise
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
            raise FotMobPageStateError(
                f"invalid FotMob page-state assessment: {type(exc).__name__}"
            ) from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "source_capture_dataset_name": self.source_capture_dataset_name,
            "source_capture_schema_version": self.source_capture_schema_version,
            "source_capture_manifest_sha256": self.source_capture_manifest_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "source_raw_size": self.source_raw_size,
            "source_observed_at": serialize_utc(self.source_observed_at),
            "request_date": self.request_date,
            "next_data_element_count": self.next_data_element_count,
            "next_data_id": self.next_data_id,
            "next_data_type": self.next_data_type,
            "next_data_query_date": self.next_data_query_date,
            "fallback_key": self.fallback_key,
            "match_count": self.match_count,
            "fixture_availability": self.fixture_availability.value,
            "safety": dict(self.safety),
        }


class _NextDataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.payloads: list[str] = []
        self._parts: list[str] | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag != "script":
            return
        names = [name for name, _ in attrs]
        for identity_name in ("id", "type"):
            if names.count(identity_name) > 1:
                raise FotMobPageStateError(
                    f"script has duplicate {identity_name} attribute"
                )
        values = dict(attrs)
        if values.get("id") != NEXT_DATA_ID:
            return
        if values.get("type") != NEXT_DATA_TYPE:
            raise FotMobPageStateError(
                "__NEXT_DATA__ script type must be application/json"
            )
        if "src" in values:
            raise FotMobPageStateError("__NEXT_DATA__ script must be inline")
        if self._parts is not None:
            raise FotMobPageStateError("nested __NEXT_DATA__ script is invalid")
        self._parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._parts is not None:
            self.payloads.append("".join(self._parts))
            self._parts = None

    def handle_data(self, data: str) -> None:
        if self._parts is not None:
            self._parts.append(data)

    def close(self) -> None:
        super().close()
        if self._parts is not None:
            raise FotMobPageStateError("__NEXT_DATA__ script is not closed")


def _extract_next_data(raw_html: bytes) -> str:
    try:
        text = raw_html.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise FotMobPageStateError("raw page must be strict UTF-8") from exc
    parser = _NextDataParser()
    try:
        parser.feed(text)
        parser.close()
    except FotMobPageStateError:
        raise
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobPageStateError("raw page HTML structure is invalid") from exc
    if len(parser.payloads) != 1:
        raise FotMobPageStateError(
            "raw page must contain exactly one qualifying __NEXT_DATA__ element"
        )
    return parser.payloads[0]


def _reject_duplicate_json_keys(pairs: list[tuple[Any, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FotMobPageStateError(f"duplicate __NEXT_DATA__ JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise FotMobPageStateError(f"invalid __NEXT_DATA__ JSON constant: {value}")


def _strict_next_data_json(text: str) -> Mapping[str, Any]:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant,
        )
    except FotMobPageStateError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobPageStateError("__NEXT_DATA__ is not strict JSON") from exc
    if not isinstance(value, Mapping):
        raise FotMobPageStateError("__NEXT_DATA__ top level must be an object")
    return value


def _mapping_child(parent: Mapping[str, Any], key: str, label: str) -> Mapping[str, Any]:
    if key not in parent:
        raise FotMobPageStateError(f"{label} is missing")
    child = parent[key]
    if not isinstance(child, Mapping):
        raise FotMobPageStateError(f"{label} must be an object")
    return child


def _revalidate_source_manifest(value: Any) -> FotMobPageCaptureManifest:
    if not isinstance(value, FotMobPageCaptureManifest):
        raise FotMobPageStateError(
            "source_manifest must be FotMobPageCaptureManifest"
        )
    try:
        return dataclasses.replace(value)
    except FotMobPageCaptureError as exc:
        raise FotMobPageStateError("source manifest is invalid") from exc
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobPageStateError("source manifest is invalid") from exc


def assess_fotmob_page_state(
    raw_html: bytes,
    source_manifest: FotMobPageCaptureManifest,
) -> FotMobPageStateAssessment:
    """Assess only the reviewed empty Next.js fixture-state path."""

    if type(raw_html) is not bytes:
        raise FotMobPageStateError("raw_html must be exact bytes")
    if not raw_html:
        raise FotMobPageStateError("raw_html must not be empty")
    if len(raw_html) > MAX_RESPONSE_BYTES:
        raise FotMobPageStateError("raw_html exceeds the 8 MiB limit")
    manifest = _revalidate_source_manifest(source_manifest)
    raw_sha = hashlib.sha256(raw_html).hexdigest()
    if len(raw_html) != manifest.raw_size:
        raise FotMobPageStateError("raw_html size does not match source manifest")
    if raw_sha != manifest.raw_sha256:
        raise FotMobPageStateError("raw_html SHA-256 does not match source manifest")

    payload = _strict_next_data_json(_extract_next_data(raw_html))
    query = _mapping_child(payload, "query", "query")
    if "date" not in query:
        raise FotMobPageStateError("query.date is missing")
    query_date = query["date"]
    if not isinstance(query_date, str):
        raise FotMobPageStateError("query.date must be an exact string")
    if query_date != manifest.request_date:
        raise FotMobPageStateError("query.date does not match source request date")

    props = _mapping_child(payload, "props", "props")
    page_props = _mapping_child(props, "pageProps", "props.pageProps")
    fallback = _mapping_child(
        page_props,
        "fallback",
        "props.pageProps.fallback",
    )
    notable = _mapping_child(
        fallback,
        FALLBACK_KEY,
        f"props.pageProps.fallback[{FALLBACK_KEY!r}]",
    )
    if "matches" not in notable:
        raise FotMobPageStateError("reviewed notableMatches container lacks matches")
    matches = notable["matches"]
    if not isinstance(matches, list):
        raise FotMobPageStateError("reviewed notableMatches matches must be a list")
    if matches:
        raise FotMobPageStateError(
            "non-empty FotMob notableMatches schema is unreviewed"
        )

    return FotMobPageStateAssessment(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        source_capture_dataset_name=manifest.dataset_name,
        source_capture_schema_version=manifest.schema_version,
        source_capture_manifest_sha256=sha256_page_capture_manifest(manifest),
        source_raw_sha256=manifest.raw_sha256,
        source_raw_size=manifest.raw_size,
        source_observed_at=manifest.observed_at,
        request_date=manifest.request_date,
        next_data_element_count=1,
        next_data_id=NEXT_DATA_ID,
        next_data_type=NEXT_DATA_TYPE,
        next_data_query_date=query_date,
        fallback_key=FALLBACK_KEY,
        match_count=0,
        fixture_availability=FotMobFixtureAvailability.NO_FIXTURE_DATA,
        safety=_default_safety(),
    )


def page_state_assessment_to_dict(
    assessment: FotMobPageStateAssessment,
) -> dict[str, Any]:
    if not isinstance(assessment, FotMobPageStateAssessment):
        raise FotMobPageStateError(
            "assessment must be FotMobPageStateAssessment"
        )
    return assessment.to_dict()


def canonical_page_state_assessment_bytes(
    assessment: FotMobPageStateAssessment,
) -> bytes:
    if not isinstance(assessment, FotMobPageStateAssessment):
        raise FotMobPageStateError(
            "assessment must be FotMobPageStateAssessment"
        )
    try:
        return (
            json.dumps(
                assessment.to_dict(),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobPageStateError("assessment serialization failed") from exc


def sha256_page_state_assessment(
    assessment: FotMobPageStateAssessment,
) -> str:
    return hashlib.sha256(canonical_page_state_assessment_bytes(assessment)).hexdigest()


__all__ = [
    "DATASET_NAME",
    "FALLBACK_KEY",
    "NEXT_DATA_ID",
    "NEXT_DATA_TYPE",
    "SCHEMA_VERSION",
    "FotMobFixtureAvailability",
    "FotMobPageStateAssessment",
    "FotMobPageStateError",
    "assess_fotmob_page_state",
    "canonical_page_state_assessment_bytes",
    "page_state_assessment_to_dict",
    "sha256_page_state_assessment",
]
