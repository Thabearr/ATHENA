"""Offline verifier for persisted reviewed FotMob match-details evidence.

This boundary verifies only historical file integrity and the canonical PR #50
manifest envelope written by PR #51. It deliberately does not replay mutable
upstream capability state and does not parse football semantics from the raw
response body.
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
from domain.fotmob_reviewed_match_details_capture import (
    DATASET_NAME as SOURCE_DATASET_NAME,
    MANIFEST_FILENAME,
    MAX_RESPONSE_BYTES,
    RAW_FILENAME,
    SCHEMA_VERSION as SOURCE_SCHEMA_VERSION,
)

SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-reviewed-match-details-persisted-evidence-v1"
MAX_MANIFEST_BYTES = 1024 * 1024

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_FIXTURE_RE = re.compile(r"^FOTMOB:([1-9][0-9]*)$", flags=re.ASCII)
_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "dataset_name",
        "plan_sha256",
        "plan_size",
        "plan",
        "fixture_identifier",
        "source_match_id",
        "kickoff",
        "request_started_at",
        "status",
        "content_type",
        "content_length",
        "observed_at",
        "network_acquisition_performed",
        "raw_file_name",
        "raw_sha256",
        "raw_size",
        "safety",
    }
)
_CAPTURE_SAFETY_KEYS = frozenset(
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
_RECEIPT_SAFETY_KEYS = frozenset(
    {
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


class FotMobReviewedMatchDetailsPersistedEvidenceError(ValueError):
    """Raised when historical persisted match-details evidence fails closed."""


def _reject_duplicate_keys(pairs: list[tuple[Any, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str:
            raise FotMobReviewedMatchDetailsPersistedEvidenceError(
                "manifest JSON object keys must be strings"
            )
        if key in result:
            raise FotMobReviewedMatchDetailsPersistedEvidenceError(
                f"duplicate manifest JSON key: {key}"
            )
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise FotMobReviewedMatchDetailsPersistedEvidenceError(
        f"invalid manifest JSON constant: {value}"
    )


def _strict_manifest_json(manifest_bytes: Any) -> tuple[dict[str, Any], bytes]:
    if type(manifest_bytes) is not bytes:
        raise FotMobReviewedMatchDetailsPersistedEvidenceError(
            "manifest_bytes must be exact immutable bytes"
        )
    if not manifest_bytes or len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise FotMobReviewedMatchDetailsPersistedEvidenceError(
            "manifest_bytes must be non-empty and at most 1 MiB"
        )
    try:
        text = manifest_bytes.decode("utf-8", errors="strict")
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except FotMobReviewedMatchDetailsPersistedEvidenceError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobReviewedMatchDetailsPersistedEvidenceError(
            "manifest is not strict UTF-8 JSON"
        ) from exc
    if type(payload) is not dict:
        raise FotMobReviewedMatchDetailsPersistedEvidenceError(
            "manifest root must be a JSON object"
        )
    try:
        canonical = (
            json.dumps(
                payload,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobReviewedMatchDetailsPersistedEvidenceError(
            "manifest canonicalization failed"
        ) from exc
    if manifest_bytes != canonical:
        raise FotMobReviewedMatchDetailsPersistedEvidenceError(
            "manifest_bytes are not exact canonical PR #50 manifest bytes"
        )
    return payload, canonical


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise FotMobReviewedMatchDetailsPersistedEvidenceError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _positive_int(value: Any, label: str, maximum: int | None = None) -> int:
    if type(value) is not int or value <= 0:
        raise FotMobReviewedMatchDetailsPersistedEvidenceError(
            f"{label} must be an exact positive integer"
        )
    if maximum is not None and value > maximum:
        raise FotMobReviewedMatchDetailsPersistedEvidenceError(
            f"{label} exceeds its allowed maximum"
        )
    return value


def _nonnegative_int_or_none(value: Any, label: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise FotMobReviewedMatchDetailsPersistedEvidenceError(
            f"{label} must be an exact non-negative integer or None"
        )
    return value


def _utc_text(value: Any, label: str) -> datetime.datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise FotMobReviewedMatchDetailsPersistedEvidenceError(
            f"{label} must be a canonical UTC Z timestamp string"
        )
    try:
        parsed = datetime.datetime.fromisoformat(value[:-1] + "+00:00")
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobReviewedMatchDetailsPersistedEvidenceError(
            f"{label} is not a valid UTC timestamp"
        ) from exc
    if parsed.tzinfo is not datetime.timezone.utc:
        parsed = parsed.astimezone(datetime.timezone.utc)
    return parsed


def _validate_capture_safety(value: Any) -> None:
    if type(value) is not dict or set(value) != _CAPTURE_SAFETY_KEYS:
        raise FotMobReviewedMatchDetailsPersistedEvidenceError(
            "persisted capture safety keys mismatch"
        )
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise FotMobReviewedMatchDetailsPersistedEvidenceError(
                f"persisted capture safety[{key!r}] must be exact bool False"
            )


def _default_receipt_safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_RECEIPT_SAFETY_KEYS)})


@dataclasses.dataclass(frozen=True)
class VerifiedPersistedFotMobMatchDetailsEvidence:
    schema_version: int
    dataset_name: str
    source_dataset_name: str
    source_schema_version: int
    manifest_sha256: str
    manifest_size: int
    raw_sha256: str
    raw_size: int
    fixture_identifier: str
    source_match_id: str
    kickoff: datetime.datetime
    request_started_at: datetime.datetime
    observed_at: datetime.datetime
    status: int
    content_type: str
    content_length: int | None
    network_acquisition_performed: bool
    raw_file_name: str
    manifest_file_name: str
    plan_sha256: str
    plan_size: int
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise FotMobReviewedMatchDetailsPersistedEvidenceError(
                "schema_version must be exact integer 1"
            )
        if self.dataset_name != DATASET_NAME:
            raise FotMobReviewedMatchDetailsPersistedEvidenceError("dataset_name mismatch")
        if self.source_dataset_name != SOURCE_DATASET_NAME:
            raise FotMobReviewedMatchDetailsPersistedEvidenceError(
                "source_dataset_name must be the PR #50 capture dataset"
            )
        if type(self.source_schema_version) is not int or self.source_schema_version != SOURCE_SCHEMA_VERSION:
            raise FotMobReviewedMatchDetailsPersistedEvidenceError(
                "source_schema_version mismatch"
            )
        _sha(self.manifest_sha256, "manifest_sha256")
        _positive_int(self.manifest_size, "manifest_size", MAX_MANIFEST_BYTES)
        _sha(self.raw_sha256, "raw_sha256")
        _positive_int(self.raw_size, "raw_size", MAX_RESPONSE_BYTES)
        if type(self.fixture_identifier) is not str:
            raise FotMobReviewedMatchDetailsPersistedEvidenceError(
                "fixture_identifier must be an exact string"
            )
        match = _FIXTURE_RE.fullmatch(self.fixture_identifier)
        if match is None or self.source_match_id != match.group(1):
            raise FotMobReviewedMatchDetailsPersistedEvidenceError(
                "fixture_identifier/source_match_id mismatch"
            )
        for label in ("kickoff", "request_started_at", "observed_at"):
            value = getattr(self, label)
            if not isinstance(value, datetime.datetime) or value.tzinfo is not datetime.timezone.utc:
                raise FotMobReviewedMatchDetailsPersistedEvidenceError(
                    f"{label} must be exact timezone.utc datetime"
                )
        if self.request_started_at >= self.kickoff:
            raise FotMobReviewedMatchDetailsPersistedEvidenceError(
                "request_started_at must be strictly before kickoff"
            )
        if self.observed_at < self.request_started_at or self.observed_at >= self.kickoff:
            raise FotMobReviewedMatchDetailsPersistedEvidenceError(
                "observed_at timing is outside reviewed pre-kickoff bounds"
            )
        if type(self.status) is not int or self.status != 200:
            raise FotMobReviewedMatchDetailsPersistedEvidenceError(
                "status must be exact integer 200"
            )
        try:
            validated_content_type = validate_json_content_type(self.content_type)
        except ValueError as exc:
            raise FotMobReviewedMatchDetailsPersistedEvidenceError(str(exc)) from exc
        content_length = _nonnegative_int_or_none(self.content_length, "content_length")
        if content_length is not None and content_length != self.raw_size:
            raise FotMobReviewedMatchDetailsPersistedEvidenceError(
                "content_length must match raw_size when present"
            )
        if type(self.network_acquisition_performed) is not bool or self.network_acquisition_performed is not True:
            raise FotMobReviewedMatchDetailsPersistedEvidenceError(
                "network_acquisition_performed must be exact bool True"
            )
        if self.raw_file_name != RAW_FILENAME or self.manifest_file_name != MANIFEST_FILENAME:
            raise FotMobReviewedMatchDetailsPersistedEvidenceError(
                "persisted file names must match the reviewed PR #50 contract"
            )
        _sha(self.plan_sha256, "plan_sha256")
        _positive_int(self.plan_size, "plan_size", MAX_MANIFEST_BYTES)
        if not isinstance(self.safety, Mapping) or set(self.safety) != _RECEIPT_SAFETY_KEYS:
            raise FotMobReviewedMatchDetailsPersistedEvidenceError("receipt safety keys mismatch")
        for key, item in self.safety.items():
            if type(item) is not bool or item is not False:
                raise FotMobReviewedMatchDetailsPersistedEvidenceError(
                    f"receipt safety[{key!r}] must be exact bool False"
                )
        object.__setattr__(self, "content_type", validated_content_type)
        object.__setattr__(self, "content_length", content_length)
        object.__setattr__(
            self,
            "safety",
            types.MappingProxyType({key: False for key in sorted(_RECEIPT_SAFETY_KEYS)}),
        )

    def to_dict(self) -> dict[str, Any]:
        def iso(value: datetime.datetime) -> str:
            return value.isoformat().replace("+00:00", "Z")

        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "source_dataset_name": self.source_dataset_name,
            "source_schema_version": self.source_schema_version,
            "manifest_sha256": self.manifest_sha256,
            "manifest_size": self.manifest_size,
            "raw_sha256": self.raw_sha256,
            "raw_size": self.raw_size,
            "fixture_identifier": self.fixture_identifier,
            "source_match_id": self.source_match_id,
            "kickoff": iso(self.kickoff),
            "request_started_at": iso(self.request_started_at),
            "observed_at": iso(self.observed_at),
            "status": self.status,
            "content_type": self.content_type,
            "content_length": self.content_length,
            "network_acquisition_performed": self.network_acquisition_performed,
            "raw_file_name": self.raw_file_name,
            "manifest_file_name": self.manifest_file_name,
            "plan_sha256": self.plan_sha256,
            "plan_size": self.plan_size,
            "safety": dict(self.safety),
        }


def verify_persisted_match_details_evidence(
    *,
    manifest_bytes: Any,
    raw_bytes: Any,
) -> VerifiedPersistedFotMobMatchDetailsEvidence:
    """Verify exact historical PR #51 output bytes without semantic promotion."""

    payload, canonical_manifest = _strict_manifest_json(manifest_bytes)
    if set(payload) != _MANIFEST_KEYS:
        raise FotMobReviewedMatchDetailsPersistedEvidenceError(
            "manifest top-level keys do not match the PR #50 contract"
        )
    if payload.get("schema_version") != SOURCE_SCHEMA_VERSION or payload.get("dataset_name") != SOURCE_DATASET_NAME:
        raise FotMobReviewedMatchDetailsPersistedEvidenceError(
            "manifest dataset/schema identity mismatch"
        )
    if type(payload.get("plan")) is not dict:
        raise FotMobReviewedMatchDetailsPersistedEvidenceError(
            "historical plan provenance must be a JSON object"
        )
    plan_sha = _sha(payload.get("plan_sha256"), "plan_sha256")
    plan_size = _positive_int(payload.get("plan_size"), "plan_size", MAX_MANIFEST_BYTES)
    fixture_identifier = payload.get("fixture_identifier")
    source_match_id = payload.get("source_match_id")
    if type(fixture_identifier) is not str or type(source_match_id) is not str:
        raise FotMobReviewedMatchDetailsPersistedEvidenceError(
            "fixture/source match identity must be exact strings"
        )
    fixture_match = _FIXTURE_RE.fullmatch(fixture_identifier)
    if fixture_match is None or fixture_match.group(1) != source_match_id:
        raise FotMobReviewedMatchDetailsPersistedEvidenceError(
            "fixture_identifier/source_match_id mismatch"
        )
    kickoff = _utc_text(payload.get("kickoff"), "kickoff")
    started = _utc_text(payload.get("request_started_at"), "request_started_at")
    observed = _utc_text(payload.get("observed_at"), "observed_at")
    if started >= kickoff or observed < started or observed >= kickoff:
        raise FotMobReviewedMatchDetailsPersistedEvidenceError(
            "persisted capture timing is outside reviewed pre-kickoff bounds"
        )
    if payload.get("status") != 200:
        raise FotMobReviewedMatchDetailsPersistedEvidenceError(
            "persisted capture requires exact HTTP 200"
        )
    try:
        content_type = validate_json_content_type(payload.get("content_type"))
    except ValueError as exc:
        raise FotMobReviewedMatchDetailsPersistedEvidenceError(str(exc)) from exc
    content_length = _nonnegative_int_or_none(payload.get("content_length"), "content_length")
    if payload.get("network_acquisition_performed") is not True:
        raise FotMobReviewedMatchDetailsPersistedEvidenceError(
            "persisted evidence must record network acquisition performed"
        )
    if payload.get("raw_file_name") != RAW_FILENAME:
        raise FotMobReviewedMatchDetailsPersistedEvidenceError(
            "raw_file_name must be response.json"
        )
    raw_sha = _sha(payload.get("raw_sha256"), "raw_sha256")
    raw_size = _positive_int(payload.get("raw_size"), "raw_size", MAX_RESPONSE_BYTES)
    _validate_capture_safety(payload.get("safety"))

    if type(raw_bytes) is not bytes:
        raise FotMobReviewedMatchDetailsPersistedEvidenceError(
            "raw_bytes must be exact immutable bytes"
        )
    if not raw_bytes or len(raw_bytes) > MAX_RESPONSE_BYTES:
        raise FotMobReviewedMatchDetailsPersistedEvidenceError(
            "raw_bytes must be non-empty and within 8 MiB"
        )
    if len(raw_bytes) != raw_size:
        raise FotMobReviewedMatchDetailsPersistedEvidenceError(
            "raw_bytes size does not match persisted manifest"
        )
    if hashlib.sha256(raw_bytes).hexdigest() != raw_sha:
        raise FotMobReviewedMatchDetailsPersistedEvidenceError(
            "raw_bytes SHA-256 does not match persisted manifest"
        )
    if content_length is not None and content_length != raw_size:
        raise FotMobReviewedMatchDetailsPersistedEvidenceError(
            "content_length must match exact persisted raw size"
        )

    return VerifiedPersistedFotMobMatchDetailsEvidence(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        source_dataset_name=SOURCE_DATASET_NAME,
        source_schema_version=SOURCE_SCHEMA_VERSION,
        manifest_sha256=hashlib.sha256(canonical_manifest).hexdigest(),
        manifest_size=len(canonical_manifest),
        raw_sha256=raw_sha,
        raw_size=raw_size,
        fixture_identifier=fixture_identifier,
        source_match_id=source_match_id,
        kickoff=kickoff,
        request_started_at=started,
        observed_at=observed,
        status=200,
        content_type=content_type,
        content_length=content_length,
        network_acquisition_performed=True,
        raw_file_name=RAW_FILENAME,
        manifest_file_name=MANIFEST_FILENAME,
        plan_sha256=plan_sha,
        plan_size=plan_size,
        safety=_default_receipt_safety(),
    )


def canonical_persisted_match_details_evidence_receipt_bytes(value: Any) -> bytes:
    if type(value) is not VerifiedPersistedFotMobMatchDetailsEvidence:
        raise FotMobReviewedMatchDetailsPersistedEvidenceError(
            "value must be exact VerifiedPersistedFotMobMatchDetailsEvidence"
        )
    try:
        rebuilt = dataclasses.replace(value)
        return (
            json.dumps(
                rebuilt.to_dict(),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except FotMobReviewedMatchDetailsPersistedEvidenceError:
        raise
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobReviewedMatchDetailsPersistedEvidenceError(
            "persisted evidence receipt serialization failed"
        ) from exc


def sha256_persisted_match_details_evidence_receipt(value: Any) -> str:
    return hashlib.sha256(
        canonical_persisted_match_details_evidence_receipt_bytes(value)
    ).hexdigest()


__all__ = [
    "DATASET_NAME",
    "MAX_MANIFEST_BYTES",
    "SCHEMA_VERSION",
    "FotMobReviewedMatchDetailsPersistedEvidenceError",
    "VerifiedPersistedFotMobMatchDetailsEvidence",
    "canonical_persisted_match_details_evidence_receipt_bytes",
    "sha256_persisted_match_details_evidence_receipt",
    "verify_persisted_match_details_evidence",
]
