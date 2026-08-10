"""Read-only verification boundary for canonical reviewed Fixture Catalog admission bytes."""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import re
import types
from collections.abc import Mapping
from typing import Any

from domain.fixture_catalog import serialize_utc
from domain.reviewed_fixture_catalog_admission import (
    REVIEWED_SOURCE_CAPABILITY,
    AdmittedFixtureIdentity,
    ReviewedFixtureCatalogAdmission,
    ReviewedFixtureCatalogAdmissionDisposition,
    ReviewedFixtureCatalogAdmissionError,
    build_reviewed_fixture_catalog_admission,
    canonical_reviewed_fixture_catalog_admission_bytes,
    sha256_reviewed_fixture_catalog_admission,
)


SCHEMA_VERSION = 1
DATASET_NAME = "athena-reviewed-fixture-catalog-admission-artifact-verification-v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "artifact_write_authorized",
        "automatic_review_authorized",
        "source_qualification_authorized",
        "global_identity_resolution_authorized",
        "fixture_intelligence_bootstrap_authorized",
        "intelligence_fact_authorized",
        "model_feature_authorized",
        "probability_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
    }
)


class ReviewedFixtureCatalogAdmissionArtifactError(ValueError):
    """Raised when canonical admission bytes cannot be independently verified."""


def _strict_sha256(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise ReviewedFixtureCatalogAdmissionArtifactError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise ReviewedFixtureCatalogAdmissionArtifactError(f"{label} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ReviewedFixtureCatalogAdmissionArtifactError(f"{label} must be timezone-aware")
    if value.tzinfo is not datetime.timezone.utc:
        raise ReviewedFixtureCatalogAdmissionArtifactError(
            f"{label} must already be normalized to UTC using datetime.timezone.utc"
        )
    return value


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(_SAFETY_KEYS)}


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise ReviewedFixtureCatalogAdmissionArtifactError("safety keys mismatch")
    detached: dict[str, bool] = {}
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise ReviewedFixtureCatalogAdmissionArtifactError(
                f"safety[{key!r}] must be exact bool False"
            )
        detached[key] = False
    return types.MappingProxyType(detached)


def _revalidate_admission(value: Any) -> ReviewedFixtureCatalogAdmission:
    if type(value) is not ReviewedFixtureCatalogAdmission:
        raise ReviewedFixtureCatalogAdmissionArtifactError(
            "admission must be exact ReviewedFixtureCatalogAdmission"
        )
    try:
        rebuilt = build_reviewed_fixture_catalog_admission(
            value.handoff,
            value.fixture_catalog_result,
            value.decision,
        )
    except ReviewedFixtureCatalogAdmissionError as exc:
        raise ReviewedFixtureCatalogAdmissionArtifactError(
            "reviewed Fixture Catalog admission failed current semantic revalidation: "
            f"{exc}"
        ) from exc
    if rebuilt.decision.disposition is not ReviewedFixtureCatalogAdmissionDisposition.ADMITTED:
        raise ReviewedFixtureCatalogAdmissionArtifactError(
            "only an ADMITTED reviewed Fixture Catalog may produce a verified artifact"
        )
    if not rebuilt.admitted_fixtures:
        raise ReviewedFixtureCatalogAdmissionArtifactError(
            "ADMITTED reviewed Fixture Catalog exposes no fixture identities"
        )
    try:
        supplied_bytes = canonical_reviewed_fixture_catalog_admission_bytes(value)
        rebuilt_bytes = canonical_reviewed_fixture_catalog_admission_bytes(rebuilt)
    except ReviewedFixtureCatalogAdmissionError as exc:
        raise ReviewedFixtureCatalogAdmissionArtifactError(
            "reviewed Fixture Catalog admission canonical comparison failed"
        ) from exc
    if supplied_bytes != rebuilt_bytes:
        raise ReviewedFixtureCatalogAdmissionArtifactError(
            "supplied admission object differs from the exact semantic rebuild"
        )
    return rebuilt


@dataclasses.dataclass(frozen=True)
class VerifiedReviewedFixtureCatalogAdmissionArtifact:
    """Immutable receipt proving exact canonical bytes matched a live PR #45 admission."""

    admission: ReviewedFixtureCatalogAdmission
    artifact_bytes: bytes
    admission_sha256: str
    verified_at: datetime.datetime
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        rebuilt = _revalidate_admission(self.admission)
        if type(self.artifact_bytes) is not bytes:
            raise ReviewedFixtureCatalogAdmissionArtifactError(
                "artifact_bytes must be exact immutable bytes"
            )
        _strict_sha256(self.admission_sha256, "admission_sha256")
        verified_at = _utc(self.verified_at, "verified_at")
        if verified_at < rebuilt.decision.reviewed_at:
            raise ReviewedFixtureCatalogAdmissionArtifactError(
                "verified_at must not predate the catalog admission review"
            )

        canonical = canonical_reviewed_fixture_catalog_admission_bytes(rebuilt)
        if self.artifact_bytes != canonical:
            raise ReviewedFixtureCatalogAdmissionArtifactError(
                "artifact bytes are not the exact canonical bytes of the revalidated admission"
            )
        expected_sha = sha256_reviewed_fixture_catalog_admission(rebuilt)
        if self.admission_sha256 != expected_sha:
            raise ReviewedFixtureCatalogAdmissionArtifactError(
                "admission_sha256 does not match the exact canonical admission bytes"
            )
        if rebuilt.decision.source_capability != REVIEWED_SOURCE_CAPABILITY:
            raise ReviewedFixtureCatalogAdmissionArtifactError(
                "revalidated admission source capability mismatch"
            )

        object.__setattr__(self, "admission", rebuilt)
        object.__setattr__(self, "verified_at", verified_at)
        object.__setattr__(self, "safety", _validate_safety(self.safety))

    @property
    def admitted_fixtures(self) -> tuple[AdmittedFixtureIdentity, ...]:
        """Expose only the identities already admitted by PR #45."""

        return self.admission.admitted_fixtures

    def to_dict(self) -> dict[str, Any]:
        decision = self.admission.decision
        return {
            "schema_version": SCHEMA_VERSION,
            "dataset_name": DATASET_NAME,
            "admission_sha256": self.admission_sha256,
            "artifact_size": len(self.artifact_bytes),
            "source_capability": decision.source_capability,
            "source_capability_sha256": decision.source_capability_sha256,
            "admission_reviewed_at": serialize_utc(decision.reviewed_at),
            "verified_at": serialize_utc(self.verified_at),
            "disposition": decision.disposition.value,
            "admitted_fixture_count": len(self.admitted_fixtures),
            "admitted_fixtures": [item.to_dict() for item in self.admitted_fixtures],
            "safety": dict(self.safety),
        }


def verify_reviewed_fixture_catalog_admission_artifact(
    admission: Any,
    artifact_bytes: Any,
    *,
    verified_at: Any,
) -> VerifiedReviewedFixtureCatalogAdmissionArtifact:
    """Verify exact canonical admission bytes without writing or activating them."""

    if type(admission) is not ReviewedFixtureCatalogAdmission:
        raise ReviewedFixtureCatalogAdmissionArtifactError(
            "admission must be exact ReviewedFixtureCatalogAdmission"
        )
    if type(artifact_bytes) is not bytes:
        raise ReviewedFixtureCatalogAdmissionArtifactError(
            "artifact_bytes must be exact immutable bytes"
        )
    rebuilt = _revalidate_admission(admission)
    canonical = canonical_reviewed_fixture_catalog_admission_bytes(rebuilt)
    admission_sha256 = hashlib.sha256(canonical).hexdigest()
    return VerifiedReviewedFixtureCatalogAdmissionArtifact(
        admission=rebuilt,
        artifact_bytes=artifact_bytes,
        admission_sha256=admission_sha256,
        verified_at=verified_at,
        safety=_default_safety(),
    )


def canonical_verified_admission_artifact_receipt_bytes(value: Any) -> bytes:
    """Return deterministic audit bytes for the verification receipt, not the admission."""

    if type(value) is not VerifiedReviewedFixtureCatalogAdmissionArtifact:
        raise ReviewedFixtureCatalogAdmissionArtifactError(
            "value must be exact VerifiedReviewedFixtureCatalogAdmissionArtifact"
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
        raise ReviewedFixtureCatalogAdmissionArtifactError(
            "verification receipt serialization failed"
        ) from exc


def sha256_verified_admission_artifact_receipt(value: Any) -> str:
    return hashlib.sha256(
        canonical_verified_admission_artifact_receipt_bytes(value)
    ).hexdigest()


__all__ = [
    "DATASET_NAME",
    "ReviewedFixtureCatalogAdmissionArtifactError",
    "SCHEMA_VERSION",
    "VerifiedReviewedFixtureCatalogAdmissionArtifact",
    "canonical_verified_admission_artifact_receipt_bytes",
    "sha256_verified_admission_artifact_receipt",
    "verify_reviewed_fixture_catalog_admission_artifact",
]
