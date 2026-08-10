"""Read-only verification boundary for canonical reviewed Fixture Intelligence bootstrap bytes."""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import re
import types
from collections.abc import Mapping
from typing import Any, Tuple

from domain.fixture_catalog import serialize_utc
from domain.reviewed_fixture_intelligence_bootstrap import (
    DATASET_NAME as BOOTSTRAP_DATASET_NAME,
    SCHEMA_VERSION as BOOTSTRAP_SCHEMA_VERSION,
    ReviewedFixtureIntelligenceBootstrap,
    ReviewedFixtureIntelligenceBootstrapError,
    ReviewedFixtureIntelligenceIdentity,
    canonical_reviewed_fixture_intelligence_bootstrap_bytes,
    sha256_reviewed_fixture_intelligence_bootstrap,
)


SCHEMA_VERSION = 1
DATASET_NAME = (
    "athena-reviewed-fixture-intelligence-bootstrap-artifact-verification-v1"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "raw_capture_authorized",
        "artifact_write_authorized",
        "automatic_review_authorized",
        "source_qualification_authorized",
        "global_identity_resolution_authorized",
        "match_detail_probe_authorized",
        "intelligence_fact_authorized",
        "intelligence_snapshot_authorized",
        "model_feature_authorized",
        "probability_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
    }
)


class ReviewedFixtureIntelligenceBootstrapArtifactError(ValueError):
    """Raised when canonical PR #47 bootstrap bytes cannot be verified."""


def _strict_sha256(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise ReviewedFixtureIntelligenceBootstrapArtifactError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _strict_utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise ReviewedFixtureIntelligenceBootstrapArtifactError(
            f"{label} must be a datetime"
        )
    if value.tzinfo is None or value.utcoffset() is None:
        raise ReviewedFixtureIntelligenceBootstrapArtifactError(
            f"{label} must be timezone-aware"
        )
    if value.tzinfo is not datetime.timezone.utc:
        raise ReviewedFixtureIntelligenceBootstrapArtifactError(
            f"{label} must already be normalized to datetime.timezone.utc"
        )
    return value


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(_SAFETY_KEYS)}


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise ReviewedFixtureIntelligenceBootstrapArtifactError(
            "safety keys mismatch"
        )
    detached: dict[str, bool] = {}
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise ReviewedFixtureIntelligenceBootstrapArtifactError(
                f"safety[{key!r}] must be exact bool False"
            )
        detached[key] = False
    return types.MappingProxyType(detached)


def _detach_identity(
    value: Any,
) -> ReviewedFixtureIntelligenceIdentity:
    if type(value) is not ReviewedFixtureIntelligenceIdentity:
        raise ReviewedFixtureIntelligenceBootstrapArtifactError(
            "fixtures must contain exact ReviewedFixtureIntelligenceIdentity values"
        )
    try:
        return ReviewedFixtureIntelligenceIdentity(
            fixture_identifier=value.fixture_identifier,
            kickoff=value.kickoff,
            admission_sha256=value.admission_sha256,
            verification_receipt_sha256=value.verification_receipt_sha256,
        )
    except (
        ReviewedFixtureIntelligenceBootstrapError,
        AttributeError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise ReviewedFixtureIntelligenceBootstrapArtifactError(
            "fixture identity failed exact PR #47 validation"
        ) from exc


def _revalidate_bootstrap(
    value: Any,
) -> ReviewedFixtureIntelligenceBootstrap:
    if type(value) is not ReviewedFixtureIntelligenceBootstrap:
        raise ReviewedFixtureIntelligenceBootstrapArtifactError(
            "bootstrap must be exact ReviewedFixtureIntelligenceBootstrap"
        )
    try:
        supplied_bytes = canonical_reviewed_fixture_intelligence_bootstrap_bytes(
            value
        )
        rebuilt = dataclasses.replace(value)
        rebuilt_bytes = canonical_reviewed_fixture_intelligence_bootstrap_bytes(
            rebuilt
        )
    except (
        ReviewedFixtureIntelligenceBootstrapError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise ReviewedFixtureIntelligenceBootstrapArtifactError(
            "reviewed Fixture Intelligence bootstrap failed exact PR #47 revalidation"
        ) from exc
    if supplied_bytes != rebuilt_bytes:
        raise ReviewedFixtureIntelligenceBootstrapArtifactError(
            "supplied bootstrap object differs from the exact PR #47 rebuild"
        )
    if not rebuilt.fixtures:
        raise ReviewedFixtureIntelligenceBootstrapArtifactError(
            "revalidated bootstrap exposes no fixture identities"
        )
    return rebuilt


@dataclasses.dataclass(frozen=True)
class VerifiedReviewedFixtureIntelligenceBootstrapArtifact:
    """Immutable receipt proving exact canonical PR #47 bootstrap bytes matched."""

    schema_version: int
    dataset_name: str
    bootstrap_schema_version: int
    bootstrap_dataset_name: str
    bootstrap: ReviewedFixtureIntelligenceBootstrap
    artifact_bytes: bytes
    bootstrap_sha256: str
    upstream_verification_receipt_sha256: str
    admission_sha256: str
    source_capability: str
    source_capability_sha256: str
    candidate_bundle_sha256: str
    review_bundle_sha256: str
    handoff_sha256: str
    catalog_sha256: str
    manifest_sha256: str
    admission_reviewed_at: datetime.datetime
    upstream_artifact_verified_at: datetime.datetime
    fixtures: Tuple[ReviewedFixtureIntelligenceIdentity, ...]
    verified_at: datetime.datetime
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise ReviewedFixtureIntelligenceBootstrapArtifactError(
                "schema_version must be exact integer 1"
            )
        if self.dataset_name != DATASET_NAME:
            raise ReviewedFixtureIntelligenceBootstrapArtifactError(
                "dataset_name mismatch"
            )
        if (
            type(self.bootstrap_schema_version) is not int
            or self.bootstrap_schema_version != BOOTSTRAP_SCHEMA_VERSION
        ):
            raise ReviewedFixtureIntelligenceBootstrapArtifactError(
                "bootstrap_schema_version does not match the exact PR #47 contract"
            )
        if self.bootstrap_dataset_name != BOOTSTRAP_DATASET_NAME:
            raise ReviewedFixtureIntelligenceBootstrapArtifactError(
                "bootstrap_dataset_name does not match the exact PR #47 contract"
            )

        rebuilt = _revalidate_bootstrap(self.bootstrap)
        if type(self.artifact_bytes) is not bytes:
            raise ReviewedFixtureIntelligenceBootstrapArtifactError(
                "artifact_bytes must be exact immutable bytes"
            )

        expected_scalars = {
            "upstream_verification_receipt_sha256": rebuilt.verification_receipt_sha256,
            "admission_sha256": rebuilt.admission_sha256,
            "source_capability": rebuilt.source_capability,
            "source_capability_sha256": rebuilt.source_capability_sha256,
            "candidate_bundle_sha256": rebuilt.candidate_bundle_sha256,
            "review_bundle_sha256": rebuilt.review_bundle_sha256,
            "handoff_sha256": rebuilt.handoff_sha256,
            "catalog_sha256": rebuilt.catalog_sha256,
            "manifest_sha256": rebuilt.manifest_sha256,
        }
        for field_name, expected in expected_scalars.items():
            if getattr(self, field_name) != expected:
                raise ReviewedFixtureIntelligenceBootstrapArtifactError(
                    f"{field_name} does not anchor the exact PR #47 bootstrap"
                )

        for field_name in (
            "bootstrap_sha256",
            "upstream_verification_receipt_sha256",
            "admission_sha256",
            "source_capability_sha256",
            "candidate_bundle_sha256",
            "review_bundle_sha256",
            "handoff_sha256",
            "catalog_sha256",
            "manifest_sha256",
        ):
            _strict_sha256(getattr(self, field_name), field_name)

        admission_reviewed_at = _strict_utc(
            self.admission_reviewed_at,
            "admission_reviewed_at",
        )
        upstream_verified_at = _strict_utc(
            self.upstream_artifact_verified_at,
            "upstream_artifact_verified_at",
        )
        verified_at = _strict_utc(self.verified_at, "verified_at")
        if admission_reviewed_at != rebuilt.admission_reviewed_at:
            raise ReviewedFixtureIntelligenceBootstrapArtifactError(
                "admission_reviewed_at does not match the exact PR #47 bootstrap"
            )
        if upstream_verified_at != rebuilt.artifact_verified_at:
            raise ReviewedFixtureIntelligenceBootstrapArtifactError(
                "upstream_artifact_verified_at does not match the exact PR #47 bootstrap"
            )
        if verified_at < upstream_verified_at:
            raise ReviewedFixtureIntelligenceBootstrapArtifactError(
                "verified_at must not predate the PR #46 artifact verification time"
            )

        expected_fixtures = tuple(_detach_identity(item) for item in rebuilt.fixtures)
        if type(self.fixtures) is not tuple or not self.fixtures:
            raise ReviewedFixtureIntelligenceBootstrapArtifactError(
                "fixtures must be a non-empty immutable tuple"
            )
        if self.fixtures != expected_fixtures:
            raise ReviewedFixtureIntelligenceBootstrapArtifactError(
                "fixtures must expose every and only identity from the exact PR #47 bootstrap"
            )

        canonical = canonical_reviewed_fixture_intelligence_bootstrap_bytes(rebuilt)
        if self.artifact_bytes != canonical:
            raise ReviewedFixtureIntelligenceBootstrapArtifactError(
                "artifact bytes are not the exact canonical bytes of the revalidated PR #47 bootstrap"
            )
        expected_sha = sha256_reviewed_fixture_intelligence_bootstrap(rebuilt)
        if self.bootstrap_sha256 != expected_sha:
            raise ReviewedFixtureIntelligenceBootstrapArtifactError(
                "bootstrap_sha256 does not match the exact canonical PR #47 bootstrap bytes"
            )

        object.__setattr__(self, "bootstrap", rebuilt)
        object.__setattr__(self, "admission_reviewed_at", admission_reviewed_at)
        object.__setattr__(
            self,
            "upstream_artifact_verified_at",
            upstream_verified_at,
        )
        object.__setattr__(self, "verified_at", verified_at)
        object.__setattr__(self, "fixtures", expected_fixtures)
        object.__setattr__(self, "safety", _validate_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        # Serialize only detached fields. Historical receipt bytes must remain
        # stable if upstream objects or module constants later change.
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "bootstrap_schema_version": self.bootstrap_schema_version,
            "bootstrap_dataset_name": self.bootstrap_dataset_name,
            "bootstrap_sha256": self.bootstrap_sha256,
            "artifact_size": len(self.artifact_bytes),
            "upstream_verification_receipt_sha256": (
                self.upstream_verification_receipt_sha256
            ),
            "admission_sha256": self.admission_sha256,
            "source_capability": self.source_capability,
            "source_capability_sha256": self.source_capability_sha256,
            "candidate_bundle_sha256": self.candidate_bundle_sha256,
            "review_bundle_sha256": self.review_bundle_sha256,
            "handoff_sha256": self.handoff_sha256,
            "catalog_sha256": self.catalog_sha256,
            "manifest_sha256": self.manifest_sha256,
            "admission_reviewed_at": serialize_utc(self.admission_reviewed_at),
            "upstream_artifact_verified_at": serialize_utc(
                self.upstream_artifact_verified_at
            ),
            "verified_at": serialize_utc(self.verified_at),
            "fixture_count": len(self.fixtures),
            "fixtures": [item.to_dict() for item in self.fixtures],
            "safety": dict(self.safety),
        }


def verify_reviewed_fixture_intelligence_bootstrap_artifact(
    bootstrap: Any,
    artifact_bytes: Any,
    *,
    verified_at: Any,
) -> VerifiedReviewedFixtureIntelligenceBootstrapArtifact:
    """Verify exact canonical PR #47 bootstrap bytes without writing or using them."""

    if type(bootstrap) is not ReviewedFixtureIntelligenceBootstrap:
        raise ReviewedFixtureIntelligenceBootstrapArtifactError(
            "bootstrap must be exact ReviewedFixtureIntelligenceBootstrap"
        )
    if type(artifact_bytes) is not bytes:
        raise ReviewedFixtureIntelligenceBootstrapArtifactError(
            "artifact_bytes must be exact immutable bytes"
        )
    rebuilt = _revalidate_bootstrap(bootstrap)
    canonical = canonical_reviewed_fixture_intelligence_bootstrap_bytes(rebuilt)
    fixtures = tuple(_detach_identity(item) for item in rebuilt.fixtures)
    return VerifiedReviewedFixtureIntelligenceBootstrapArtifact(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        bootstrap_schema_version=BOOTSTRAP_SCHEMA_VERSION,
        bootstrap_dataset_name=BOOTSTRAP_DATASET_NAME,
        bootstrap=rebuilt,
        artifact_bytes=artifact_bytes,
        bootstrap_sha256=hashlib.sha256(canonical).hexdigest(),
        upstream_verification_receipt_sha256=rebuilt.verification_receipt_sha256,
        admission_sha256=rebuilt.admission_sha256,
        source_capability=rebuilt.source_capability,
        source_capability_sha256=rebuilt.source_capability_sha256,
        candidate_bundle_sha256=rebuilt.candidate_bundle_sha256,
        review_bundle_sha256=rebuilt.review_bundle_sha256,
        handoff_sha256=rebuilt.handoff_sha256,
        catalog_sha256=rebuilt.catalog_sha256,
        manifest_sha256=rebuilt.manifest_sha256,
        admission_reviewed_at=rebuilt.admission_reviewed_at,
        upstream_artifact_verified_at=rebuilt.artifact_verified_at,
        fixtures=fixtures,
        verified_at=verified_at,
        safety=_default_safety(),
    )


def canonical_verified_bootstrap_artifact_receipt_bytes(value: Any) -> bytes:
    """Return deterministic audit bytes for this verification receipt."""

    if type(value) is not VerifiedReviewedFixtureIntelligenceBootstrapArtifact:
        raise ReviewedFixtureIntelligenceBootstrapArtifactError(
            "value must be exact VerifiedReviewedFixtureIntelligenceBootstrapArtifact"
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
        raise ReviewedFixtureIntelligenceBootstrapArtifactError(
            "bootstrap verification receipt serialization failed"
        ) from exc


def sha256_verified_bootstrap_artifact_receipt(value: Any) -> str:
    return hashlib.sha256(
        canonical_verified_bootstrap_artifact_receipt_bytes(value)
    ).hexdigest()


__all__ = [
    "DATASET_NAME",
    "ReviewedFixtureIntelligenceBootstrapArtifactError",
    "SCHEMA_VERSION",
    "VerifiedReviewedFixtureIntelligenceBootstrapArtifact",
    "canonical_verified_bootstrap_artifact_receipt_bytes",
    "sha256_verified_bootstrap_artifact_receipt",
    "verify_reviewed_fixture_intelligence_bootstrap_artifact",
]
