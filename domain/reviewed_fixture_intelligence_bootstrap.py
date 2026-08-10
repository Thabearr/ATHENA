"""Reviewed fixture-identity bootstrap for the Fixture Intelligence boundary.

This module carries only already-admitted fixture identity and kickoff into a
new typed boundary.  It does not create Fixture Intelligence facts or
snapshots and does not authorize any downstream model, pricing, selection, or
betting behavior.
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
from domain.reviewed_fixture_catalog_admission import (
    REVIEWED_SOURCE_CAPABILITY,
    AdmittedFixtureIdentity,
    ReviewedFixtureCatalogAdmission,
    ReviewedFixtureCatalogAdmissionDisposition,
    ReviewedFixtureCatalogAdmissionError,
    canonical_reviewed_fixture_catalog_admission_bytes,
    sha256_reviewed_fixture_catalog_admission,
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
    """Raised when admitted fixture identity cannot enter the bootstrap."""


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


def _utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise ReviewedFixtureIntelligenceBootstrapError(f"{label} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ReviewedFixtureIntelligenceBootstrapError(
            f"{label} must be timezone-aware"
        )
    return value.astimezone(datetime.timezone.utc)


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


def _revalidate_admission(
    admission: Any,
) -> tuple[ReviewedFixtureCatalogAdmission, bytes, str]:
    if type(admission) is not ReviewedFixtureCatalogAdmission:
        raise ReviewedFixtureIntelligenceBootstrapError(
            "admission must be exact ReviewedFixtureCatalogAdmission"
        )
    try:
        revalidated = dataclasses.replace(admission)
        original_bytes = canonical_reviewed_fixture_catalog_admission_bytes(admission)
        rebuilt_bytes = canonical_reviewed_fixture_catalog_admission_bytes(revalidated)
    except ReviewedFixtureCatalogAdmissionError as exc:
        raise ReviewedFixtureIntelligenceBootstrapError(
            "reviewed Fixture Catalog admission failed exact revalidation"
        ) from exc
    if original_bytes != rebuilt_bytes:
        raise ReviewedFixtureIntelligenceBootstrapError(
            "reviewed Fixture Catalog admission changed during exact revalidation"
        )
    if (
        admission.decision.disposition
        is not ReviewedFixtureCatalogAdmissionDisposition.ADMITTED
    ):
        raise ReviewedFixtureIntelligenceBootstrapError(
            "only an ADMITTED reviewed Fixture Catalog may bootstrap Fixture Intelligence identity"
        )
    if not admission.admitted_fixtures:
        raise ReviewedFixtureIntelligenceBootstrapError(
            "an ADMITTED reviewed Fixture Catalog must expose admitted fixtures"
        )
    return (
        revalidated,
        original_bytes,
        sha256_reviewed_fixture_catalog_admission(admission),
    )


@dataclasses.dataclass(frozen=True)
class ReviewedFixtureIntelligenceIdentity:
    """One exact source-scoped fixture identity proven by a reviewed admission."""

    fixture_identifier: str
    kickoff: datetime.datetime
    admission_sha256: str

    def __post_init__(self) -> None:
        _strict_string(self.fixture_identifier, "fixture_identifier")
        if not self.fixture_identifier.startswith("FOTMOB:"):
            raise ReviewedFixtureIntelligenceBootstrapError(
                "fixture_identifier must remain source-scoped to FOTMOB"
            )
        object.__setattr__(self, "kickoff", _utc(self.kickoff, "kickoff"))
        _strict_sha256(self.admission_sha256, "admission_sha256")

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_identifier": self.fixture_identifier,
            "kickoff": serialize_utc(self.kickoff),
            "admission_sha256": self.admission_sha256,
        }


@dataclasses.dataclass(frozen=True)
class ReviewedFixtureIntelligenceBootstrap:
    """Self-validating identity-only handoff from PR #45 toward PR #30."""

    admission: ReviewedFixtureCatalogAdmission
    admission_sha256: str
    source_capability: str
    source_capability_sha256: str
    candidate_bundle_sha256: str
    review_bundle_sha256: str
    handoff_sha256: str
    catalog_sha256: str
    manifest_sha256: str
    admission_reviewed_at: datetime.datetime
    fixtures: Tuple[ReviewedFixtureIntelligenceIdentity, ...]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        revalidated, _admission_bytes, expected_admission_sha = _revalidate_admission(
            self.admission
        )
        decision = revalidated.decision

        expected_scalars = {
            "admission_sha256": expected_admission_sha,
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
                    f"{field_name} does not anchor the exact reviewed admission"
                )
        if self.source_capability != REVIEWED_SOURCE_CAPABILITY:
            raise ReviewedFixtureIntelligenceBootstrapError(
                "source_capability must be the reviewed FotMob catalog capability"
            )
        _strict_sha256(self.admission_sha256, "admission_sha256")
        _strict_sha256(self.source_capability_sha256, "source_capability_sha256")
        _strict_sha256(self.candidate_bundle_sha256, "candidate_bundle_sha256")
        _strict_sha256(self.review_bundle_sha256, "review_bundle_sha256")
        _strict_sha256(self.handoff_sha256, "handoff_sha256")
        _strict_sha256(self.catalog_sha256, "catalog_sha256")
        _strict_sha256(self.manifest_sha256, "manifest_sha256")

        reviewed_at = _utc(self.admission_reviewed_at, "admission_reviewed_at")
        if reviewed_at != decision.reviewed_at:
            raise ReviewedFixtureIntelligenceBootstrapError(
                "admission_reviewed_at must equal the exact catalog admission review time"
            )
        object.__setattr__(self, "admission_reviewed_at", reviewed_at)

        if type(self.fixtures) is not tuple or not self.fixtures:
            raise ReviewedFixtureIntelligenceBootstrapError(
                "fixtures must be a non-empty immutable tuple"
            )
        if any(type(item) is not ReviewedFixtureIntelligenceIdentity for item in self.fixtures):
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
                admission_sha256=expected_admission_sha,
            )
            for item in revalidated.admitted_fixtures
        )
        if self.fixtures != expected_fixtures:
            raise ReviewedFixtureIntelligenceBootstrapError(
                "fixtures must expose every and only identity from the reviewed admission"
            )
        ordered = tuple(
            sorted(self.fixtures, key=lambda item: (item.kickoff, item.fixture_identifier))
        )
        if self.fixtures != ordered:
            raise ReviewedFixtureIntelligenceBootstrapError(
                "fixtures must preserve deterministic admitted-catalog ordering"
            )
        if any(self.admission_reviewed_at >= item.kickoff for item in self.fixtures):
            raise ReviewedFixtureIntelligenceBootstrapError(
                "every bootstrapped fixture must remain prospective at admission review time"
            )

        object.__setattr__(self, "safety", _validate_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "dataset_name": DATASET_NAME,
            "admission_dataset_name": self.admission.to_dict()["dataset_name"],
            "admission_sha256": self.admission_sha256,
            "source_capability": self.source_capability,
            "source_capability_sha256": self.source_capability_sha256,
            "candidate_bundle_sha256": self.candidate_bundle_sha256,
            "review_bundle_sha256": self.review_bundle_sha256,
            "handoff_sha256": self.handoff_sha256,
            "catalog_sha256": self.catalog_sha256,
            "manifest_sha256": self.manifest_sha256,
            "admission_reviewed_at": serialize_utc(self.admission_reviewed_at),
            "fixture_count": len(self.fixtures),
            "fixtures": [item.to_dict() for item in self.fixtures],
            "safety": dict(self.safety),
        }


def build_reviewed_fixture_intelligence_bootstrap(
    admission: Any,
) -> ReviewedFixtureIntelligenceBootstrap:
    """Build the identity-only bootstrap from one exact admitted catalog."""

    revalidated, _admission_bytes, admission_sha = _revalidate_admission(admission)
    decision = revalidated.decision
    fixtures = tuple(
        ReviewedFixtureIntelligenceIdentity(
            fixture_identifier=item.fixture_identifier,
            kickoff=item.kickoff,
            admission_sha256=admission_sha,
        )
        for item in revalidated.admitted_fixtures
    )
    return ReviewedFixtureIntelligenceBootstrap(
        admission=admission,
        admission_sha256=admission_sha,
        source_capability=decision.source_capability,
        source_capability_sha256=decision.source_capability_sha256,
        candidate_bundle_sha256=decision.candidate_bundle_sha256,
        review_bundle_sha256=decision.review_bundle_sha256,
        handoff_sha256=decision.handoff_sha256,
        catalog_sha256=decision.catalog_sha256,
        manifest_sha256=decision.manifest_sha256,
        admission_reviewed_at=decision.reviewed_at,
        fixtures=fixtures,
        safety=_default_safety(),
    )


def resolve_reviewed_fixture_intelligence_identity(
    bootstrap: Any,
    fixture_identifier: Any,
) -> ReviewedFixtureIntelligenceIdentity:
    """Resolve one exact admitted identity; no aliases or fuzzy matching are allowed."""

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
            "fixture_identifier is not an exact admitted Fixture Intelligence bootstrap identity"
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
