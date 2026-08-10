"""Explicit offline admission gate for a reviewed FotMob Fixture Catalog."""

from __future__ import annotations

import dataclasses
import datetime
import enum
import hashlib
import json
import re
import types
from collections.abc import Mapping
from typing import Any, Tuple

from domain.fixture_catalog import (
    FixtureCatalogResult,
    FixtureProvenanceRecord,
    build_manifest,
    build_strict_catalog,
    canonical_json_bytes,
    canonical_json_line_bytes,
    serialize_utc,
    sha256_bytes,
)
from domain.fotmob_fixture_catalog_handoff import (
    FotMobFixtureCatalogHandoff,
    sha256_fotmob_fixture_catalog_handoff,
)
from domain.source_capabilities import (
    CapabilityAvailability,
    SOURCE_CAPABILITY_REGISTRY,
)


SCHEMA_VERSION = 1
DATASET_NAME = "athena-reviewed-fixture-catalog-admission-v1"
REVIEWED_SOURCE_CAPABILITY = "fotmob_data_matches_reviewed_catalog"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "raw_capture_authorized",
        "automatic_review_authorized",
        "source_qualification_authorized",
        "global_identity_resolution_authorized",
        "intelligence_fact_authorized",
        "model_feature_authorized",
        "probability_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
    }
)
_EXPECTED_CAPABILITY_AVAILABILITY = {
    "full_time_score": CapabilityAvailability.NOT_CAPTURED,
    "half_time_score": CapabilityAvailability.NOT_CAPTURED,
    "event_timestamps": CapabilityAvailability.NOT_CAPTURED,
    "reliable_fixture_identity": CapabilityAvailability.CONFIRMED,
    "historical_coverage": CapabilityAvailability.UNKNOWN,
    "freshness_metadata": CapabilityAvailability.NOT_CAPTURED,
}


class ReviewedFixtureCatalogAdmissionError(ValueError):
    """Raised when a compiled reviewed catalog cannot be admitted exactly."""


class ReviewedFixtureCatalogAdmissionDisposition(str, enum.Enum):
    ADMITTED = "ADMITTED"
    REJECTED = "REJECTED"


def _strict_sha256(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise ReviewedFixtureCatalogAdmissionError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _strict_git_sha(value: Any, label: str) -> str:
    if type(value) is not str or _GIT_SHA_RE.fullmatch(value) is None:
        raise ReviewedFixtureCatalogAdmissionError(
            f"{label} must be exactly 40 lowercase hexadecimal characters"
        )
    return value


def _strict_string(value: Any, label: str, *, non_empty: bool = True) -> str:
    if type(value) is not str:
        raise ReviewedFixtureCatalogAdmissionError(f"{label} must be an exact string")
    if non_empty and not value:
        raise ReviewedFixtureCatalogAdmissionError(f"{label} must be non-empty")
    if value != value.strip():
        raise ReviewedFixtureCatalogAdmissionError(
            f"{label} must not contain surrounding whitespace"
        )
    return value


def _utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise ReviewedFixtureCatalogAdmissionError(f"{label} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ReviewedFixtureCatalogAdmissionError(f"{label} must be timezone-aware")
    return value.astimezone(datetime.timezone.utc)


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(_SAFETY_KEYS)}


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise ReviewedFixtureCatalogAdmissionError("safety keys mismatch")
    detached: dict[str, bool] = {}
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise ReviewedFixtureCatalogAdmissionError(
                f"safety[{key!r}] must be exact bool False"
            )
        detached[key] = False
    return types.MappingProxyType(detached)


def _reviewed_source_capability_payload() -> dict[str, Any]:
    capability = SOURCE_CAPABILITY_REGISTRY.get(REVIEWED_SOURCE_CAPABILITY)
    if capability is None:
        raise ReviewedFixtureCatalogAdmissionError(
            "reviewed FotMob source capability is not registered"
        )
    if capability.source != REVIEWED_SOURCE_CAPABILITY:
        raise ReviewedFixtureCatalogAdmissionError(
            "reviewed FotMob source capability identity mismatch"
        )
    for field_name, expected in _EXPECTED_CAPABILITY_AVAILABILITY.items():
        if getattr(capability, field_name) is not expected:
            raise ReviewedFixtureCatalogAdmissionError(
                f"reviewed FotMob capability {field_name} no longer matches the identity-only PR #44 profile"
            )
    payload = capability.to_dict()
    if type(payload) is not dict or payload.get("source") != REVIEWED_SOURCE_CAPABILITY:
        raise ReviewedFixtureCatalogAdmissionError(
            "reviewed FotMob capability serialization is invalid"
        )
    return payload


def canonical_reviewed_source_capability_bytes() -> bytes:
    try:
        return (
            json.dumps(
                _reviewed_source_capability_payload(),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ReviewedFixtureCatalogAdmissionError(
            "reviewed FotMob capability serialization failed"
        ) from exc


def sha256_reviewed_source_capability() -> str:
    return hashlib.sha256(canonical_reviewed_source_capability_bytes()).hexdigest()


def _assert_compiler_matches_handoff(
    handoff: FotMobFixtureCatalogHandoff,
    result: FixtureCatalogResult,
) -> None:
    expected: dict[str, dict[str, Any]] = {}
    for item in handoff.catalog_inputs:
        payload = item.to_catalog_input_dict()
        source_id = payload["source_fixture_identifier"]
        if type(source_id) is not str or not source_id:
            raise ReviewedFixtureCatalogAdmissionError(
                "reviewed handoff source fixture identifier is invalid"
            )
        if source_id in expected:
            raise ReviewedFixtureCatalogAdmissionError(
                "reviewed handoff contains duplicate source fixture identifiers"
            )
        expected[source_id] = payload
    if len(result.records) != len(expected):
        raise ReviewedFixtureCatalogAdmissionError(
            "compiled fixture count does not match the reviewed handoff"
        )
    seen: set[str] = set()
    for record in result.records:
        payload = expected.get(record.source_fixture_identifier)
        if payload is None:
            raise ReviewedFixtureCatalogAdmissionError(
                "compiled catalog contains a fixture absent from the reviewed handoff"
            )
        if record.source_fixture_identifier in seen:
            raise ReviewedFixtureCatalogAdmissionError(
                "compiled catalog contains a duplicate source fixture identifier"
            )
        seen.add(record.source_fixture_identifier)
        if not all(
            (
                record.fixture_identifier
                == f"FOTMOB:{record.source_fixture_identifier}",
                record.home_team == payload["home_team"],
                record.away_team == payload["away_team"],
                record.competition == payload["competition"],
                serialize_utc(record.kickoff) == payload["kickoff"],
                record.source_reference == payload["source_reference"],
                serialize_utc(record.reviewed_at) == payload["reviewed_at"],
                record.evidence_file_path == payload["evidence_file_path"],
                record.evidence_sha256 == payload["evidence_sha256"],
            )
        ):
            raise ReviewedFixtureCatalogAdmissionError(
                "compiled catalog data differs from the reviewed handoff"
            )
    if seen != set(expected):
        raise ReviewedFixtureCatalogAdmissionError(
            "compiled catalog does not cover the exact reviewed handoff"
        )


def _validate_compilation(result: Any, handoff: Any) -> None:
    if type(handoff) is not FotMobFixtureCatalogHandoff:
        raise ReviewedFixtureCatalogAdmissionError(
            "handoff must be exact FotMobFixtureCatalogHandoff"
        )
    if type(result) is not FixtureCatalogResult:
        raise ReviewedFixtureCatalogAdmissionError(
            "fixture_catalog_result must be exact FixtureCatalogResult"
        )
    _reviewed_source_capability_payload()

    if type(result.records) is not tuple or not result.records:
        raise ReviewedFixtureCatalogAdmissionError(
            "compiled records must be a non-empty immutable tuple"
        )
    if any(type(record) is not FixtureProvenanceRecord for record in result.records):
        raise ReviewedFixtureCatalogAdmissionError(
            "compiled records contain an invalid provenance record"
        )
    ordered = tuple(
        sorted(result.records, key=lambda item: (item.kickoff, item.fixture_identifier))
    )
    if result.records != ordered:
        raise ReviewedFixtureCatalogAdmissionError(
            "compiled records must preserve deterministic catalog ordering"
        )
    if type(result.minimum_lead_seconds) is not int or result.minimum_lead_seconds < 0:
        raise ReviewedFixtureCatalogAdmissionError(
            "minimum_lead_seconds must be an exact non-negative integer"
        )
    normalized_as_of = _utc(result.as_of, "fixture_catalog_result.as_of")
    if result.as_of != normalized_as_of:
        raise ReviewedFixtureCatalogAdmissionError(
            "fixture_catalog_result.as_of must already be normalized to UTC"
        )
    _strict_git_sha(result.generator_commit, "fixture_catalog_result.generator_commit")
    if type(result.tracked_worktree_clean) is not bool or not result.tracked_worktree_clean:
        raise ReviewedFixtureCatalogAdmissionError(
            "compiled catalog must come from an exactly clean tracked worktree"
        )

    minimum_kickoff = normalized_as_of + datetime.timedelta(
        seconds=result.minimum_lead_seconds
    )
    for record in ordered:
        if record.reviewed_at > normalized_as_of:
            raise ReviewedFixtureCatalogAdmissionError(
                "compiled record reviewed_at must not be after compiler as_of"
            )
        if record.kickoff < minimum_kickoff:
            raise ReviewedFixtureCatalogAdmissionError(
                "compiled record no longer satisfies its declared minimum lead time"
            )

    expected_normalized_input = b"".join(
        canonical_json_line_bytes(record.provenance_entry()) for record in ordered
    )
    if result.normalized_input_bytes != expected_normalized_input:
        raise ReviewedFixtureCatalogAdmissionError(
            "compiler normalized input bytes do not match provenance records"
        )
    expected_normalized_sha = sha256_bytes(expected_normalized_input)
    if result.normalized_input_sha256 != expected_normalized_sha:
        raise ReviewedFixtureCatalogAdmissionError(
            "compiler normalized input SHA-256 does not match exact bytes"
        )

    expected_catalog = build_strict_catalog(ordered)
    expected_catalog_bytes = canonical_json_bytes(expected_catalog)
    if result.catalog != expected_catalog or result.catalog_bytes != expected_catalog_bytes:
        raise ReviewedFixtureCatalogAdmissionError(
            "catalog object or canonical bytes do not match compiled provenance"
        )

    expected_manifest = build_manifest(
        records=ordered,
        catalog_bytes=expected_catalog_bytes,
        normalized_input_bytes=expected_normalized_input,
        as_of=normalized_as_of,
        minimum_lead_seconds=result.minimum_lead_seconds,
        generator_commit=result.generator_commit,
        tracked_worktree_clean=True,
    )
    expected_manifest_bytes = canonical_json_bytes(expected_manifest)
    if result.manifest != expected_manifest or result.manifest_bytes != expected_manifest_bytes:
        raise ReviewedFixtureCatalogAdmissionError(
            "manifest object or canonical bytes do not match compiled provenance"
        )

    _assert_compiler_matches_handoff(handoff, result)


@dataclasses.dataclass(frozen=True)
class ReviewedFixtureCatalogAdmissionDecision:
    candidate_bundle_sha256: str
    review_bundle_sha256: str
    handoff_sha256: str
    catalog_sha256: str
    manifest_sha256: str
    source_capability: str
    source_capability_sha256: str
    disposition: ReviewedFixtureCatalogAdmissionDisposition
    reviewed_at: datetime.datetime
    reviewer_reference: str
    notes: str = ""

    def __post_init__(self) -> None:
        _strict_sha256(self.candidate_bundle_sha256, "candidate_bundle_sha256")
        _strict_sha256(self.review_bundle_sha256, "review_bundle_sha256")
        _strict_sha256(self.handoff_sha256, "handoff_sha256")
        _strict_sha256(self.catalog_sha256, "catalog_sha256")
        _strict_sha256(self.manifest_sha256, "manifest_sha256")
        if self.source_capability != REVIEWED_SOURCE_CAPABILITY:
            raise ReviewedFixtureCatalogAdmissionError(
                f"source_capability must be exactly {REVIEWED_SOURCE_CAPABILITY}"
            )
        _strict_sha256(self.source_capability_sha256, "source_capability_sha256")
        if not isinstance(self.disposition, ReviewedFixtureCatalogAdmissionDisposition):
            raise ReviewedFixtureCatalogAdmissionError(
                "disposition must be ReviewedFixtureCatalogAdmissionDisposition"
            )
        object.__setattr__(self, "reviewed_at", _utc(self.reviewed_at, "reviewed_at"))
        _strict_string(self.reviewer_reference, "reviewer_reference")
        _strict_string(self.notes, "notes", non_empty=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_bundle_sha256": self.candidate_bundle_sha256,
            "review_bundle_sha256": self.review_bundle_sha256,
            "handoff_sha256": self.handoff_sha256,
            "catalog_sha256": self.catalog_sha256,
            "manifest_sha256": self.manifest_sha256,
            "source_capability": self.source_capability,
            "source_capability_sha256": self.source_capability_sha256,
            "disposition": self.disposition.value,
            "reviewed_at": serialize_utc(self.reviewed_at),
            "reviewer_reference": self.reviewer_reference,
            "notes": self.notes,
        }


@dataclasses.dataclass(frozen=True)
class AdmittedFixtureIdentity:
    fixture_identifier: str
    kickoff: datetime.datetime

    def __post_init__(self) -> None:
        _strict_string(self.fixture_identifier, "fixture_identifier")
        if not self.fixture_identifier.startswith("FOTMOB:"):
            raise ReviewedFixtureCatalogAdmissionError(
                "admitted fixture_identifier must remain source-scoped to FOTMOB"
            )
        object.__setattr__(self, "kickoff", _utc(self.kickoff, "kickoff"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_identifier": self.fixture_identifier,
            "kickoff": serialize_utc(self.kickoff),
        }


@dataclasses.dataclass(frozen=True)
class ReviewedFixtureCatalogAdmission:
    handoff: FotMobFixtureCatalogHandoff
    fixture_catalog_result: FixtureCatalogResult
    decision: ReviewedFixtureCatalogAdmissionDecision
    admitted_fixtures: Tuple[AdmittedFixtureIdentity, ...]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        _validate_compilation(self.fixture_catalog_result, self.handoff)
        if type(self.decision) is not ReviewedFixtureCatalogAdmissionDecision:
            raise ReviewedFixtureCatalogAdmissionError(
                "decision must be exact ReviewedFixtureCatalogAdmissionDecision"
            )
        if type(self.admitted_fixtures) is not tuple:
            raise ReviewedFixtureCatalogAdmissionError(
                "admitted_fixtures must be an immutable tuple"
            )
        if any(type(item) is not AdmittedFixtureIdentity for item in self.admitted_fixtures):
            raise ReviewedFixtureCatalogAdmissionError(
                "admitted_fixtures contains an invalid fixture identity"
            )

        handoff = self.handoff
        result = self.fixture_catalog_result
        decision = self.decision
        expected_hashes = {
            "candidate_bundle_sha256": handoff.candidate_bundle_sha256,
            "review_bundle_sha256": handoff.review_bundle_sha256,
            "handoff_sha256": sha256_fotmob_fixture_catalog_handoff(handoff),
            "catalog_sha256": sha256_bytes(result.catalog_bytes),
            "manifest_sha256": sha256_bytes(result.manifest_bytes),
            "source_capability_sha256": sha256_reviewed_source_capability(),
        }
        for field_name, expected in expected_hashes.items():
            if getattr(decision, field_name) != expected:
                raise ReviewedFixtureCatalogAdmissionError(
                    f"admission decision {field_name} does not anchor the exact reviewed catalog"
                )
        if decision.source_capability != REVIEWED_SOURCE_CAPABILITY:
            raise ReviewedFixtureCatalogAdmissionError(
                "admission decision source capability mismatch"
            )

        latest_upstream_review = max(record.reviewed_at for record in result.records)
        if decision.reviewed_at < result.as_of:
            raise ReviewedFixtureCatalogAdmissionError(
                "admission reviewed_at must not predate compiler as_of"
            )
        if decision.reviewed_at < latest_upstream_review:
            raise ReviewedFixtureCatalogAdmissionError(
                "admission reviewed_at must not predate upstream fixture review"
            )

        expected_admitted = tuple(
            AdmittedFixtureIdentity(
                fixture_identifier=record.fixture_identifier,
                kickoff=record.kickoff,
            )
            for record in result.records
        )
        if decision.disposition is ReviewedFixtureCatalogAdmissionDisposition.ADMITTED:
            if decision.reviewed_at >= min(item.kickoff for item in expected_admitted):
                raise ReviewedFixtureCatalogAdmissionError(
                    "an ADMITTED catalog must remain prospective at admission time"
                )
            if self.admitted_fixtures != expected_admitted:
                raise ReviewedFixtureCatalogAdmissionError(
                    "ADMITTED disposition must expose every and only compiled fixture identity"
                )
        else:
            if self.admitted_fixtures:
                raise ReviewedFixtureCatalogAdmissionError(
                    "REJECTED disposition must expose zero admitted fixture identities"
                )

        object.__setattr__(self, "safety", _validate_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        result = self.fixture_catalog_result
        handoff = self.handoff
        return {
            "schema_version": SCHEMA_VERSION,
            "dataset_name": DATASET_NAME,
            "source_capability": REVIEWED_SOURCE_CAPABILITY,
            "source_capability_sha256": self.decision.source_capability_sha256,
            "candidate_bundle_sha256": handoff.candidate_bundle_sha256,
            "review_bundle_sha256": handoff.review_bundle_sha256,
            "handoff_sha256": sha256_fotmob_fixture_catalog_handoff(handoff),
            "catalog_sha256": sha256_bytes(result.catalog_bytes),
            "manifest_sha256": sha256_bytes(result.manifest_bytes),
            "compiler_normalized_input_sha256": result.normalized_input_sha256,
            "generator_commit": result.generator_commit,
            "compiler_as_of": serialize_utc(result.as_of),
            "minimum_lead_seconds": result.minimum_lead_seconds,
            "compiled_fixture_count": len(result.records),
            "disposition": self.decision.disposition.value,
            "admitted_fixture_count": len(self.admitted_fixtures),
            "decision": self.decision.to_dict(),
            "admitted_fixtures": [item.to_dict() for item in self.admitted_fixtures],
            "safety": dict(self.safety),
        }


def build_reviewed_fixture_catalog_admission(
    handoff: Any,
    fixture_catalog_result: Any,
    decision: Any,
) -> ReviewedFixtureCatalogAdmission:
    """Admit or reject one exact reviewed catalog without downstream activation."""

    if type(handoff) is not FotMobFixtureCatalogHandoff:
        raise ReviewedFixtureCatalogAdmissionError(
            "handoff must be exact FotMobFixtureCatalogHandoff"
        )
    if type(fixture_catalog_result) is not FixtureCatalogResult:
        raise ReviewedFixtureCatalogAdmissionError(
            "fixture_catalog_result must be exact FixtureCatalogResult"
        )
    if type(decision) is not ReviewedFixtureCatalogAdmissionDecision:
        raise ReviewedFixtureCatalogAdmissionError(
            "decision must be exact ReviewedFixtureCatalogAdmissionDecision"
        )
    admitted = ()
    if decision.disposition is ReviewedFixtureCatalogAdmissionDisposition.ADMITTED:
        admitted = tuple(
            AdmittedFixtureIdentity(
                fixture_identifier=record.fixture_identifier,
                kickoff=record.kickoff,
            )
            for record in fixture_catalog_result.records
        )
    return ReviewedFixtureCatalogAdmission(
        handoff=handoff,
        fixture_catalog_result=fixture_catalog_result,
        decision=decision,
        admitted_fixtures=admitted,
        safety=_default_safety(),
    )


def canonical_reviewed_fixture_catalog_admission_bytes(value: Any) -> bytes:
    if type(value) is not ReviewedFixtureCatalogAdmission:
        raise ReviewedFixtureCatalogAdmissionError(
            "value must be exact ReviewedFixtureCatalogAdmission"
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
        raise ReviewedFixtureCatalogAdmissionError(
            "admission serialization failed"
        ) from exc


def sha256_reviewed_fixture_catalog_admission(value: Any) -> str:
    return hashlib.sha256(
        canonical_reviewed_fixture_catalog_admission_bytes(value)
    ).hexdigest()


__all__ = [
    "AdmittedFixtureIdentity",
    "DATASET_NAME",
    "REVIEWED_SOURCE_CAPABILITY",
    "ReviewedFixtureCatalogAdmission",
    "ReviewedFixtureCatalogAdmissionDecision",
    "ReviewedFixtureCatalogAdmissionDisposition",
    "ReviewedFixtureCatalogAdmissionError",
    "SCHEMA_VERSION",
    "build_reviewed_fixture_catalog_admission",
    "canonical_reviewed_fixture_catalog_admission_bytes",
    "canonical_reviewed_source_capability_bytes",
    "sha256_reviewed_fixture_catalog_admission",
    "sha256_reviewed_source_capability",
]
