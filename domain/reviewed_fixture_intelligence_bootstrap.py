"""Verified fixture-identity bootstrap for the Fixture Intelligence boundary.

This module carries only fixture identity and kickoff from an exact PR #46
verified admission artifact and its exact canonical receipt bytes into a new
typed boundary. It does not create Fixture Intelligence facts or snapshots and
does not authorize downstream model, pricing, selection, or betting behavior.
"""

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
from domain.reviewed_fixture_catalog_admission import REVIEWED_SOURCE_CAPABILITY
from domain.reviewed_fixture_catalog_admission_artifact import (
    DATASET_NAME as VERIFIED_ADMISSION_ARTIFACT_DATASET_NAME,
    ReviewedFixtureCatalogAdmissionArtifactError,
    VerifiedReviewedFixtureCatalogAdmissionArtifact,
    canonical_verified_admission_artifact_receipt_bytes,
)


SCHEMA_VERSION = 1
DATASET_NAME = "athena-reviewed-fixture-intelligence-bootstrap-v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "raw_capture_authorized",
        "automatic_review_authorized",
        "global_identity_resolution_authorized",
        "intelligence_fact_authorized",
        "intelligence_snapshot_authorized",
        "model_feature_authorized",
        "probability_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
    }
)


class ReviewedFixtureIntelligenceBootstrapError(ValueError):
    """Raised when verified fixture identity cannot enter the bootstrap."""


def _strict_string(value: Any, label: str) -> str:
    if type(value) is not str or not value:
        raise ReviewedFixtureIntelligenceBootstrapError(
            f"{label} must be an exact non-empty string"
        )
    if value != value.strip():
        raise ReviewedFixtureIntelligenceBootstrapError(
            f"{label} must not contain surrounding whitespace"
        )
    return value


def _strict_sha256(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise ReviewedFixtureIntelligenceBootstrapError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _strict_utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise ReviewedFixtureIntelligenceBootstrapError(f"{label} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ReviewedFixtureIntelligenceBootstrapError(
            f"{label} must be timezone-aware"
        )
    if value.tzinfo is not datetime.timezone.utc:
        raise ReviewedFixtureIntelligenceBootstrapError(
            f"{label} must already be normalized to datetime.timezone.utc"
        )
    return value


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(_SAFETY_KEYS)}


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise ReviewedFixtureIntelligenceBootstrapError("safety keys mismatch")
    detached: dict[str, bool] = {}
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise ReviewedFixtureIntelligenceBootstrapError(
                f"safety[{key!r}] must be exact bool False"
            )
        detached[key] = False
    return types.MappingProxyType(detached)


def _revalidate_verified_artifact(
    value: Any,
    receipt_bytes: Any,
) -> tuple[VerifiedReviewedFixtureCatalogAdmissionArtifact, str]:
    if type(value) is not VerifiedReviewedFixtureCatalogAdmissionArtifact:
        raise ReviewedFixtureIntelligenceBootstrapError(
            "verified_artifact must be exact VerifiedReviewedFixtureCatalogAdmissionArtifact"
        )
    if type(receipt_bytes) is not bytes:
        raise ReviewedFixtureIntelligenceBootstrapError(
            "verification_receipt_bytes must be exact immutable bytes"
        )
    try:
        supplied_receipt = canonical_verified_admission_artifact_receipt_bytes(value)
        rebuilt = dataclasses.replace(value)
        rebuilt_receipt = canonical_verified_admission_artifact_receipt_bytes(rebuilt)
    except (ReviewedFixtureCatalogAdmissionArtifactError, TypeError, ValueError) as exc:
        raise ReviewedFixtureIntelligenceBootstrapError(
            "verified admission artifact failed exact PR #46 revalidation"
        ) from exc
    if supplied_receipt != rebuilt_receipt:
        raise ReviewedFixtureIntelligenceBootstrapError(
            "verified admission artifact differs from its exact PR #46 rebuild"
        )
    if receipt_bytes != supplied_receipt:
        raise ReviewedFixtureIntelligenceBootstrapError(
            "verification_receipt_bytes are not the exact canonical PR #46 receipt bytes"
        )
    if not rebuilt.admitted_fixtures:
        raise ReviewedFixtureIntelligenceBootstrapError(
            "verified admission artifact must expose admitted fixture identities"
        )
    receipt_sha = hashlib.sha256(receipt_bytes).hexdigest()
    _strict_sha256(receipt_sha, "verification_receipt_sha256")
    return rebuilt, receipt_sha


@dataclasses.dataclass(frozen=True)
class ReviewedFixtureIntelligenceIdentity:
    """One exact source-scoped fixture identity proven by PR #46 verification."""

    fixture_identifier: str
    kickoff: datetime.datetime
    admission_sha256: str
    verification_receipt_sha256: str

    def __post_init__(self) -> None:
        _strict_string(self.fixture_identifier, "fixture_identifier")
        if not self.fixture_identifier.startswith("FOTMOB:"):
            raise ReviewedFixtureIntelligenceBootstrapError(
                "fixture_identifier must remain source-scoped to FOTMOB"
            )
        object.__setattr__(self, "kickoff", _strict_utc(self.kickoff, "kickoff"))
        _strict_sha256(self.admission_sha256, "admission_sha256")
        _strict_sha256(
            self.verification_receipt_sha256,
            "verification_receipt_sha256",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_identifier": self.fixture_identifier,
            "kickoff": serialize_utc(self.kickoff),
            "admission_sha256": self.admission_sha256,
            "verification_receipt_sha256": self.verification_receipt_sha256,
        }


@dataclasses.dataclass(frozen=True)
class ReviewedFixtureIntelligenceBootstrap:
    """Self-validating identity-only handoff from PR #46 toward PR #30."""

    verified_artifact: VerifiedReviewedFixtureCatalogAdmissionArtifact
    verification_receipt_bytes: bytes
    verification_receipt_sha256: str
    admission_sha256: str
    source_capability: str
    source_capability_sha256: str
    candidate_bundle_sha256: str
    review_bundle_sha256: str
    handoff_sha256: str
    catalog_sha256: str
    manifest_sha256: str
    admission_reviewed_at: datetime.datetime
    artifact_verified_at: datetime.datetime
    fixtures: Tuple[ReviewedFixtureIntelligenceIdentity, ...]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        revalidated, expected_receipt_sha = _revalidate_verified_artifact(
            self.verified_artifact,
            self.verification_receipt_bytes,
        )
        admission = revalidated.admission
        decision = admission.decision

        expected_scalars = {
            "verification_receipt_sha256": expected_receipt_sha,
            "admission_sha256": revalidated.admission_sha256,
            "source_capability": decision.source_capability,
            "source_capability_sha256": decision.source_capability_sha256,
            "candidate_bundle_sha256": decision.candidate_bundle_sha256,
            "review_bundle_sha256": decision.review_bundle_sha256,
            "handoff_sha256": decision.handoff_sha256,
            "catalog_sha256": decision.catalog_sha256,
            "manifest_sha256": decision.manifest_sha256,
        }
        for field_name, expected in expected_scalars.items():
            if getattr(self, field_name) != expected:
                raise ReviewedFixtureIntelligenceBootstrapError(
                    f"{field_name} does not anchor the exact verified admission artifact"
                )
        if self.source_capability != REVIEWED_SOURCE_CAPABILITY:
            raise ReviewedFixtureIntelligenceBootstrapError(
                "source_capability must be the reviewed FotMob catalog capability"
            )
        for field_name in (
            "verification_receipt_sha256",
            "admission_sha256",
            "source_capability_sha256",
            "candidate_bundle_sha256",
            "review_bundle_sha256",
            "handoff_sha256",
            "catalog_sha256",
            "manifest_sha256",
        ):
            _strict_sha256(getattr(self, field_name), field_name)

        reviewed_at = _strict_utc(self.admission_reviewed_at, "admission_reviewed_at")
        verified_at = _strict_utc(self.artifact_verified_at, "artifact_verified_at")
        if reviewed_at != decision.reviewed_at:
            raise ReviewedFixtureIntelligenceBootstrapError(
                "admission_reviewed_at must equal the exact catalog admission review time"
            )
        if verified_at != revalidated.verified_at:
            raise ReviewedFixtureIntelligenceBootstrapError(
                "artifact_verified_at must equal the exact PR #46 verification time"
            )

        if type(self.fixtures) is not tuple or not self.fixtures:
            raise ReviewedFixtureIntelligenceBootstrapError(
                "fixtures must be a non-empty immutable tuple"
            )
        if any(
            type(item) is not ReviewedFixtureIntelligenceIdentity
            for item in self.fixtures
        ):
            raise ReviewedFixtureIntelligenceBootstrapError(
                "fixtures must contain exact ReviewedFixtureIntelligenceIdentity values"
            )
        identifiers = tuple(item.fixture_identifier for item in self.fixtures)
        if len(identifiers) != len(set(identifiers)):
            raise ReviewedFixtureIntelligenceBootstrapError(
                "fixtures must not contain duplicate fixture identifiers"
            )

        expected_fixtures = tuple(
            ReviewedFixtureIntelligenceIdentity(
                fixture_identifier=item.fixture_identifier,
                kickoff=item.kickoff,
                admission_sha256=revalidated.admission_sha256,
                verification_receipt_sha256=expected_receipt_sha,
            )
            for item in revalidated.admitted_fixtures
        )
        if self.fixtures != expected_fixtures:
            raise ReviewedFixtureIntelligenceBootstrapError(
                "fixtures must expose every and only identity from the verified admission artifact"
            )
        ordered = tuple(
            sorted(self.fixtures, key=lambda item: (item.kickoff, item.fixture_identifier))
        )
        if self.fixtures != ordered:
            raise ReviewedFixtureIntelligenceBootstrapError(
                "fixtures must preserve deterministic admitted-catalog ordering"
            )
        if any(verified_at >= item.kickoff for item in self.fixtures):
            raise ReviewedFixtureIntelligenceBootstrapError(
                "every bootstrapped fixture must remain prospective at PR #46 verification time"
            )

        object.__setattr__(self, "admission_reviewed_at", reviewed_at)
        object.__setattr__(self, "artifact_verified_at", verified_at)
        object.__setattr__(self, "safety", _validate_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        # Deliberately serialize only detached captured fields. Historical
        # bootstrap bytes must not depend on later mutation of nested objects.
        return {
            "schema_version": SCHEMA_VERSION,
            "dataset_name": DATASET_NAME,
            "verification_dataset_name": VERIFIED_ADMISSION_ARTIFACT_DATASET_NAME,
            "verification_receipt_sha256": self.verification_receipt_sha256,
            "verification_receipt_size": len(self.verification_receipt_bytes),
            "admission_sha256": self.admission_sha256,
            "source_capability": self.source_capability,
            "source_capability_sha256": self.source_capability_sha256,
            "candidate_bundle_sha256": self.candidate_bundle_sha256,
            "review_bundle_sha256": self.review_bundle_sha256,
            "handoff_sha256": self.handoff_sha256,
            "catalog_sha256": self.catalog_sha256,
            "manifest_sha256": self.manifest_sha256,
            "admission_reviewed_at": serialize_utc(self.admission_reviewed_at),
            "artifact_verified_at": serialize_utc(self.artifact_verified_at),
            "fixture_count": len(self.fixtures),
            "fixtures": [item.to_dict() for item in self.fixtures],
            "safety": dict(self.safety),
        }


def build_reviewed_fixture_intelligence_bootstrap(
    verified_artifact: Any,
    verification_receipt_bytes: Any,
) -> ReviewedFixtureIntelligenceBootstrap:
    """Build identity-only bootstrap from exact PR #46 object and receipt bytes."""

    revalidated, receipt_sha = _revalidate_verified_artifact(
        verified_artifact,
        verification_receipt_bytes,
    )
    admission = revalidated.admission
    decision = admission.decision
    fixtures = tuple(
        ReviewedFixtureIntelligenceIdentity(
            fixture_identifier=item.fixture_identifier,
            kickoff=item.kickoff,
            admission_sha256=revalidated.admission_sha256,
            verification_receipt_sha256=receipt_sha,
        )
        for item in revalidated.admitted_fixtures
    )
    return ReviewedFixtureIntelligenceBootstrap(
        verified_artifact=verified_artifact,
        verification_receipt_bytes=verification_receipt_bytes,
        verification_receipt_sha256=receipt_sha,
        admission_sha256=revalidated.admission_sha256,
        source_capability=decision.source_capability,
        source_capability_sha256=decision.source_capability_sha256,
        candidate_bundle_sha256=decision.candidate_bundle_sha256,
        review_bundle_sha256=decision.review_bundle_sha256,
        handoff_sha256=decision.handoff_sha256,
        catalog_sha256=decision.catalog_sha256,
        manifest_sha256=decision.manifest_sha256,
        admission_reviewed_at=decision.reviewed_at,
        artifact_verified_at=revalidated.verified_at,
        fixtures=fixtures,
        safety=_default_safety(),
    )


def resolve_reviewed_fixture_intelligence_identity(
    bootstrap: Any,
    fixture_identifier: Any,
) -> ReviewedFixtureIntelligenceIdentity:
    """Resolve one exact verified identity; no aliases or fuzzy matching."""

    if type(bootstrap) is not ReviewedFixtureIntelligenceBootstrap:
        raise ReviewedFixtureIntelligenceBootstrapError(
            "bootstrap must be exact ReviewedFixtureIntelligenceBootstrap"
        )
    identifier = _strict_string(fixture_identifier, "fixture_identifier")
    matches = tuple(
        item for item in bootstrap.fixtures if item.fixture_identifier == identifier
    )
    if len(matches) != 1:
        raise ReviewedFixtureIntelligenceBootstrapError(
            "fixture_identifier is not an exact verified Fixture Intelligence bootstrap identity"
        )
    return matches[0]


def canonical_reviewed_fixture_intelligence_bootstrap_bytes(value: Any) -> bytes:
    if type(value) is not ReviewedFixtureIntelligenceBootstrap:
        raise ReviewedFixtureIntelligenceBootstrapError(
            "value must be exact ReviewedFixtureIntelligenceBootstrap"
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
        raise ReviewedFixtureIntelligenceBootstrapError(
            "bootstrap serialization failed"
        ) from exc


def sha256_reviewed_fixture_intelligence_bootstrap(value: Any) -> str:
    return hashlib.sha256(
        canonical_reviewed_fixture_intelligence_bootstrap_bytes(value)
    ).hexdigest()


__all__ = [
    "DATASET_NAME",
    "ReviewedFixtureIntelligenceBootstrap",
    "ReviewedFixtureIntelligenceBootstrapError",
    "ReviewedFixtureIntelligenceIdentity",
    "SCHEMA_VERSION",
    "build_reviewed_fixture_intelligence_bootstrap",
    "canonical_reviewed_fixture_intelligence_bootstrap_bytes",
    "resolve_reviewed_fixture_intelligence_identity",
    "sha256_reviewed_fixture_intelligence_bootstrap",
]
