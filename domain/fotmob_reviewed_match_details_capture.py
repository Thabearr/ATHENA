"""Self-validating raw capture contract for reviewed FotMob match details.

This boundary accepts only an exact PR #49 request plan plus exact full response
bytes. It records provenance and raw-byte identity without parsing football
semantics, performing network I/O, or writing files.
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import re
import types
from collections.abc import Mapping
from typing import Any

from domain.fotmob_data_matches_capture import validate_json_content_type
from domain.fotmob_reviewed_match_details_probe import (
    FotMobMatchDetailsProbePlan,
    FotMobReviewedMatchDetailsProbeError,
    canonical_match_details_probe_plan_bytes,
)
from domain.fixture_catalog import serialize_utc


SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-reviewed-match-details-capture-v1"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
RAW_FILENAME = "response.json"
MANIFEST_FILENAME = "manifest.json"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "network_transport_authorized",
        "filesystem_write_authorized",
        "response_body_parsing_authorized",
        "source_qualification_authorized",
        "football_semantics_authorized",
        "intelligence_fact_authorized",
        "intelligence_snapshot_authorized",
        "model_feature_authorized",
        "probability_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
    }
)


class FotMobReviewedMatchDetailsCaptureError(ValueError):
    """Raised when reviewed match-details raw capture state fails closed."""


def _strict_sha256(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise FotMobReviewedMatchDetailsCaptureError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _strict_utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise FotMobReviewedMatchDetailsCaptureError(f"{label} must be a datetime")
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            raise FotMobReviewedMatchDetailsCaptureError(
                f"{label} must be timezone-aware"
            )
        normalized = value.astimezone(datetime.timezone.utc)
    except FotMobReviewedMatchDetailsCaptureError:
        raise
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobReviewedMatchDetailsCaptureError(f"{label} is invalid") from exc
    return normalized


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(_SAFETY_KEYS)}


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise FotMobReviewedMatchDetailsCaptureError("safety keys mismatch")
    detached: dict[str, bool] = {}
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise FotMobReviewedMatchDetailsCaptureError(
                f"safety[{key!r}] must be exact bool False"
            )
        detached[key] = False
    return types.MappingProxyType(detached)


def _revalidate_plan(
    plan: Any,
    plan_bytes: Any,
) -> tuple[FotMobMatchDetailsProbePlan, bytes, str]:
    if type(plan) is not FotMobMatchDetailsProbePlan:
        raise FotMobReviewedMatchDetailsCaptureError(
            "plan must be exact FotMobMatchDetailsProbePlan"
        )
    if type(plan_bytes) is not bytes:
        raise FotMobReviewedMatchDetailsCaptureError(
            "plan_bytes must be exact immutable bytes"
        )
    try:
        supplied_bytes = canonical_match_details_probe_plan_bytes(plan)
        rebuilt = dataclasses.replace(plan)
        rebuilt_bytes = canonical_match_details_probe_plan_bytes(rebuilt)
    except (
        FotMobReviewedMatchDetailsProbeError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise FotMobReviewedMatchDetailsCaptureError(
            "PR #49 request plan failed current exact revalidation"
        ) from exc
    if supplied_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsCaptureError(
            "supplied PR #49 plan differs from its exact semantic rebuild"
        )
    if plan_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsCaptureError(
            "plan_bytes are not the exact canonical PR #49 plan bytes"
        )
    return rebuilt, rebuilt_bytes, hashlib.sha256(rebuilt_bytes).hexdigest()


@dataclasses.dataclass(frozen=True)
class CapturedFotMobReviewedMatchDetailsResponse:
    """Exact unparsed bytes and transport metadata supplied to this boundary."""

    status: int
    content_type: str
    content_length: int | None
    body: bytes
    observed_at: datetime.datetime
    network_acquisition_performed: bool

    def __post_init__(self) -> None:
        try:
            if type(self.status) is not int or self.status != 200:
                raise FotMobReviewedMatchDetailsCaptureError(
                    "status must be exact integer 200"
                )
            try:
                content_type = validate_json_content_type(self.content_type)
            except ValueError as exc:
                raise FotMobReviewedMatchDetailsCaptureError(str(exc)) from exc
            if self.content_length is not None and (
                type(self.content_length) is not int or self.content_length < 0
            ):
                raise FotMobReviewedMatchDetailsCaptureError(
                    "content_length must be an exact non-negative integer or None"
                )
            if type(self.body) is not bytes:
                raise FotMobReviewedMatchDetailsCaptureError("body must be exact bytes")
            if not self.body:
                raise FotMobReviewedMatchDetailsCaptureError("body must not be empty")
            if len(self.body) > MAX_RESPONSE_BYTES:
                raise FotMobReviewedMatchDetailsCaptureError(
                    "body exceeds the 8 MiB raw capture limit"
                )
            if self.content_length is not None and self.content_length != len(self.body):
                raise FotMobReviewedMatchDetailsCaptureError(
                    "content_length does not match exact body size"
                )
            observed_at = _strict_utc(self.observed_at, "observed_at")
            if type(self.network_acquisition_performed) is not bool:
                raise FotMobReviewedMatchDetailsCaptureError(
                    "network_acquisition_performed must be exact bool"
                )
            object.__setattr__(self, "content_type", content_type)
            object.__setattr__(self, "observed_at", observed_at)
        except FotMobReviewedMatchDetailsCaptureError:
            raise
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
            raise FotMobReviewedMatchDetailsCaptureError(
                f"invalid captured response: {type(exc).__name__}"
            ) from exc


@dataclasses.dataclass(frozen=True)
class FotMobReviewedMatchDetailsCaptureManifest:
    """Detached manifest for exact raw match-details evidence bytes."""

    schema_version: int
    dataset_name: str
    plan: FotMobMatchDetailsProbePlan
    plan_bytes: bytes
    plan_sha256: str
    fixture_identifier: str
    source_match_id: str
    kickoff: datetime.datetime
    request_started_at: datetime.datetime
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
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise FotMobReviewedMatchDetailsCaptureError(
                "schema_version must be exact integer 1"
            )
        if self.dataset_name != DATASET_NAME:
            raise FotMobReviewedMatchDetailsCaptureError("dataset_name mismatch")
        plan, plan_bytes, plan_sha = _revalidate_plan(self.plan, self.plan_bytes)
        if self.plan_sha256 != plan_sha:
            raise FotMobReviewedMatchDetailsCaptureError(
                "plan_sha256 does not match exact canonical PR #49 plan bytes"
            )
        if self.fixture_identifier != plan.fixture_identifier:
            raise FotMobReviewedMatchDetailsCaptureError(
                "fixture_identifier does not match exact PR #49 plan"
            )
        if self.source_match_id != plan.source_match_id:
            raise FotMobReviewedMatchDetailsCaptureError(
                "source_match_id does not match exact PR #49 plan"
            )
        kickoff = _strict_utc(self.kickoff, "kickoff")
        started = _strict_utc(self.request_started_at, "request_started_at")
        if kickoff != plan.kickoff or started != plan.request_started_at:
            raise FotMobReviewedMatchDetailsCaptureError(
                "capture timing identity does not match exact PR #49 plan"
            )
        if type(self.status) is not int or self.status != 200:
            raise FotMobReviewedMatchDetailsCaptureError(
                "status must be exact integer 200"
            )
        try:
            content_type = validate_json_content_type(self.content_type)
        except ValueError as exc:
            raise FotMobReviewedMatchDetailsCaptureError(str(exc)) from exc
        if self.content_length is not None and (
            type(self.content_length) is not int or self.content_length < 0
        ):
            raise FotMobReviewedMatchDetailsCaptureError(
                "content_length must be an exact non-negative integer or None"
            )
        observed_at = _strict_utc(self.observed_at, "observed_at")
        if observed_at < started:
            raise FotMobReviewedMatchDetailsCaptureError(
                "observed_at must not predate request_started_at"
            )
        if observed_at >= kickoff:
            raise FotMobReviewedMatchDetailsCaptureError(
                "observed_at must be strictly before fixture kickoff"
            )
        if type(self.network_acquisition_performed) is not bool:
            raise FotMobReviewedMatchDetailsCaptureError(
                "network_acquisition_performed must be exact bool"
            )
        if self.raw_file_name != RAW_FILENAME:
            raise FotMobReviewedMatchDetailsCaptureError(
                "raw_file_name must be response.json"
            )
        raw_sha = _strict_sha256(self.raw_sha256, "raw_sha256")
        if type(self.raw_size) is not int or not 0 < self.raw_size <= MAX_RESPONSE_BYTES:
            raise FotMobReviewedMatchDetailsCaptureError(
                "raw_size must be an exact positive integer within 8 MiB"
            )
        if self.content_length is not None and self.content_length != self.raw_size:
            raise FotMobReviewedMatchDetailsCaptureError(
                "content_length must match raw_size"
            )
        safety = _validate_safety(self.safety)
        object.__setattr__(self, "plan", plan)
        object.__setattr__(self, "plan_bytes", plan_bytes)
        object.__setattr__(self, "kickoff", kickoff)
        object.__setattr__(self, "request_started_at", started)
        object.__setattr__(self, "content_type", content_type)
        object.__setattr__(self, "observed_at", observed_at)
        object.__setattr__(self, "raw_sha256", raw_sha)
        object.__setattr__(self, "safety", safety)

    def to_dict(self) -> dict[str, Any]:
        try:
            plan_payload = json.loads(self.plan_bytes.decode("utf-8"))
        except (UnicodeError, ValueError, TypeError) as exc:
            raise FotMobReviewedMatchDetailsCaptureError(
                "stored canonical plan bytes are not valid JSON"
            ) from exc
        if type(plan_payload) is not dict:
            raise FotMobReviewedMatchDetailsCaptureError(
                "stored canonical plan payload must be a JSON object"
            )
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "plan_sha256": self.plan_sha256,
            "plan_size": len(self.plan_bytes),
            "plan": plan_payload,
            "fixture_identifier": self.fixture_identifier,
            "source_match_id": self.source_match_id,
            "kickoff": serialize_utc(self.kickoff),
            "request_started_at": serialize_utc(self.request_started_at),
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


@dataclasses.dataclass(frozen=True)
class FotMobReviewedMatchDetailsRawCapture:
    """Exact raw bytes coupled to their self-validating detached manifest."""

    raw_bytes: bytes
    manifest: FotMobReviewedMatchDetailsCaptureManifest

    def __post_init__(self) -> None:
        if type(self.raw_bytes) is not bytes:
            raise FotMobReviewedMatchDetailsCaptureError(
                "raw_bytes must be exact immutable bytes"
            )
        if type(self.manifest) is not FotMobReviewedMatchDetailsCaptureManifest:
            raise FotMobReviewedMatchDetailsCaptureError(
                "manifest must be exact FotMobReviewedMatchDetailsCaptureManifest"
            )
        try:
            manifest = dataclasses.replace(self.manifest)
        except (
            FotMobReviewedMatchDetailsCaptureError,
            AttributeError,
            KeyError,
            TypeError,
            ValueError,
            OverflowError,
        ) as exc:
            raise FotMobReviewedMatchDetailsCaptureError(
                "capture manifest failed current exact revalidation"
            ) from exc
        if not self.raw_bytes or len(self.raw_bytes) > MAX_RESPONSE_BYTES:
            raise FotMobReviewedMatchDetailsCaptureError(
                "raw_bytes must be non-empty and within 8 MiB"
            )
        if len(self.raw_bytes) != manifest.raw_size:
            raise FotMobReviewedMatchDetailsCaptureError(
                "raw_bytes size does not match manifest"
            )
        if hashlib.sha256(self.raw_bytes).hexdigest() != manifest.raw_sha256:
            raise FotMobReviewedMatchDetailsCaptureError(
                "raw_bytes SHA-256 does not match manifest"
            )
        object.__setattr__(self, "manifest", manifest)


def build_reviewed_match_details_raw_capture(
    *,
    plan: Any,
    plan_bytes: Any,
    response: Any,
) -> FotMobReviewedMatchDetailsRawCapture:
    """Bind exact full response bytes to one exact currently valid PR #49 plan."""

    rebuilt_plan, exact_plan_bytes, plan_sha = _revalidate_plan(plan, plan_bytes)
    if type(response) is not CapturedFotMobReviewedMatchDetailsResponse:
        raise FotMobReviewedMatchDetailsCaptureError(
            "response must be exact CapturedFotMobReviewedMatchDetailsResponse"
        )
    response = dataclasses.replace(response)
    if response.observed_at < rebuilt_plan.request_started_at:
        raise FotMobReviewedMatchDetailsCaptureError(
            "observed_at must not predate request_started_at"
        )
    if response.observed_at >= rebuilt_plan.kickoff:
        raise FotMobReviewedMatchDetailsCaptureError(
            "observed_at must be strictly before fixture kickoff"
        )
    raw_sha = hashlib.sha256(response.body).hexdigest()
    manifest = FotMobReviewedMatchDetailsCaptureManifest(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        plan=rebuilt_plan,
        plan_bytes=exact_plan_bytes,
        plan_sha256=plan_sha,
        fixture_identifier=rebuilt_plan.fixture_identifier,
        source_match_id=rebuilt_plan.source_match_id,
        kickoff=rebuilt_plan.kickoff,
        request_started_at=rebuilt_plan.request_started_at,
        status=response.status,
        content_type=response.content_type,
        content_length=response.content_length,
        observed_at=response.observed_at,
        network_acquisition_performed=response.network_acquisition_performed,
        raw_file_name=RAW_FILENAME,
        raw_sha256=raw_sha,
        raw_size=len(response.body),
        safety=_default_safety(),
    )
    return FotMobReviewedMatchDetailsRawCapture(
        raw_bytes=response.body,
        manifest=manifest,
    )


def canonical_reviewed_match_details_capture_manifest_bytes(value: Any) -> bytes:
    if type(value) is not FotMobReviewedMatchDetailsCaptureManifest:
        raise FotMobReviewedMatchDetailsCaptureError(
            "value must be exact FotMobReviewedMatchDetailsCaptureManifest"
        )
    try:
        return (
            json.dumps(
                value.to_dict(),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobReviewedMatchDetailsCaptureError(
            "capture manifest serialization failed"
        ) from exc


def sha256_reviewed_match_details_capture_manifest(value: Any) -> str:
    return hashlib.sha256(
        canonical_reviewed_match_details_capture_manifest_bytes(value)
    ).hexdigest()


def reviewed_match_details_capture_identifier(value: Any) -> str:
    if type(value) is not FotMobReviewedMatchDetailsRawCapture:
        raise FotMobReviewedMatchDetailsCaptureError(
            "value must be exact FotMobReviewedMatchDetailsRawCapture"
        )
    try:
        capture = dataclasses.replace(value)
    except (
        FotMobReviewedMatchDetailsCaptureError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise FotMobReviewedMatchDetailsCaptureError(
            "raw capture failed current exact revalidation"
        ) from exc
    timestamp = capture.manifest.observed_at.strftime("%Y%m%dT%H%M%S%fZ")
    return (
        f"{capture.manifest.source_match_id}--{timestamp}--"
        f"{capture.manifest.raw_sha256}"
    )


__all__ = [
    "CapturedFotMobReviewedMatchDetailsResponse",
    "DATASET_NAME",
    "FotMobReviewedMatchDetailsCaptureError",
    "FotMobReviewedMatchDetailsCaptureManifest",
    "FotMobReviewedMatchDetailsRawCapture",
    "MANIFEST_FILENAME",
    "MAX_RESPONSE_BYTES",
    "RAW_FILENAME",
    "SCHEMA_VERSION",
    "build_reviewed_match_details_raw_capture",
    "canonical_reviewed_match_details_capture_manifest_bytes",
    "reviewed_match_details_capture_identifier",
    "sha256_reviewed_match_details_capture_manifest",
]
