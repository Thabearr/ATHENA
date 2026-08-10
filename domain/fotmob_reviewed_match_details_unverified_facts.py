"""Adapt exact reviewed FotMob match-details candidates into PR #30 facts.

This boundary consumes the complete exact PR #52 -> #55 chain and produces
FixtureIntelligenceFact objects whose status remains UNVERIFIED.  It does not
qualify the source, create a Fixture Intelligence snapshot, or authorize any
model/pricing/betting behavior.
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import math
import re
import types
from collections.abc import Mapping
from typing import Any

from domain.fixture_intelligence import (
    FixtureIntelligenceError,
    FixtureIntelligenceFact,
    IntelligenceFactStatus,
    SourceRole,
)
from domain.fotmob_reviewed_match_details_capture import RAW_FILENAME
from domain.fotmob_reviewed_match_details_unverified_candidates import (
    FotMobReviewedMatchDetailsUnverifiedCandidateError,
    ReviewedMatchDetailsUnverifiedCandidateBundle,
    SOURCE_PROVIDER,
    UnverifiedMatchDetailsCandidate,
    build_reviewed_match_details_unverified_candidates,
    canonical_reviewed_match_details_unverified_candidate_bundle_bytes,
)

SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-reviewed-match-details-unverified-facts-v1"
EVIDENCE_ROOT = ".cache/athena-research/fotmob-reviewed-match-details-captures"

_SHA_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "source_qualification_authorized",
        "supported_status_authorized",
        "intelligence_snapshot_authorized",
        "model_feature_authorized",
        "probability_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
    }
)


class FotMobReviewedMatchDetailsUnverifiedFactError(ValueError):
    """Raised when exact UNVERIFIED fact adaptation cannot be proven."""


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        raise FotMobReviewedMatchDetailsUnverifiedFactError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime) or value.tzinfo is not datetime.timezone.utc:
        raise FotMobReviewedMatchDetailsUnverifiedFactError(
            f"{label} must use exact datetime.timezone.utc"
        )
    return value


def _default_safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise FotMobReviewedMatchDetailsUnverifiedFactError("safety keys mismatch")
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise FotMobReviewedMatchDetailsUnverifiedFactError(
                f"safety[{key!r}] must be exact bool False"
            )
    return _default_safety()


def _scalar(value: Any) -> str | int | float | bool:
    if type(value) is bool:
        return value
    if type(value) is int:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise FotMobReviewedMatchDetailsUnverifiedFactError(
                "fact value must remain a finite reviewed scalar"
            )
        return value
    if type(value) is str:
        return value
    raise FotMobReviewedMatchDetailsUnverifiedFactError(
        "fact value must remain a reviewed STRING/INTEGER/NUMBER/BOOLEAN scalar"
    )


def _evidence_file_path(
    bundle: ReviewedMatchDetailsUnverifiedCandidateBundle,
) -> str:
    observed = _utc(bundle.observed_at, "candidate observed_at")
    timestamp = observed.strftime("%Y%m%dT%H%M%S%fZ")
    identifier = f"{bundle.source_match_id}--{timestamp}--{bundle.raw_sha256}"
    return f"{EVIDENCE_ROOT}/{identifier}/{RAW_FILENAME}"


def _fact_from_candidate(
    candidate: UnverifiedMatchDetailsCandidate,
    *,
    evidence_file_path: str,
) -> FixtureIntelligenceFact:
    return FixtureIntelligenceFact(
        category=candidate.category,
        field=candidate.field,
        status=IntelligenceFactStatus.UNVERIFIED,
        value=_scalar(candidate.value),
        source_provider=candidate.source_provider,
        source_role=candidate.source_role,
        source_reference=candidate.source_reference,
        observed_at=candidate.observed_at,
        evidence_file_path=evidence_file_path,
        evidence_sha256=candidate.evidence_sha256,
        notes=None,
    )


def _facts_from_candidates(
    bundle: ReviewedMatchDetailsUnverifiedCandidateBundle,
    *,
    evidence_file_path: str,
) -> tuple[FixtureIntelligenceFact, ...]:
    try:
        facts = tuple(
            _fact_from_candidate(item, evidence_file_path=evidence_file_path)
            for item in bundle.candidates
        )
    except FixtureIntelligenceError as exc:
        raise FotMobReviewedMatchDetailsUnverifiedFactError(
            "PR #55 candidate cannot satisfy the exact PR #30 fact contract"
        ) from exc
    return tuple(
        sorted(
            facts,
            key=lambda fact: (
                fact.category.value,
                fact.field,
                fact.source_reference,
            ),
        )
    )


def _fact_dict(fact: FixtureIntelligenceFact) -> dict[str, Any]:
    value = _scalar(fact.value)
    return {
        "category": fact.category.value,
        "field": fact.field,
        "status": fact.status.value,
        "value": value,
        "source_provider": fact.source_provider,
        "source_role": fact.source_role.value,
        "source_reference": fact.source_reference,
        "observed_at": fact.observed_at.isoformat().replace("+00:00", "Z"),
        "evidence_file_path": fact.evidence_file_path,
        "evidence_sha256": fact.evidence_sha256,
        "notes": fact.notes,
    }


def _revalidate_candidate_bundle(
    *,
    evidence: Any,
    evidence_receipt_bytes: Any,
    manifest_bytes: Any,
    raw_bytes: Any,
    assessment: Any,
    assessment_bytes: Any,
    review: Any,
    review_bytes: Any,
    candidate_bundle: Any,
    candidate_bundle_bytes: Any,
) -> tuple[ReviewedMatchDetailsUnverifiedCandidateBundle, bytes]:
    if type(candidate_bundle) is not ReviewedMatchDetailsUnverifiedCandidateBundle:
        raise FotMobReviewedMatchDetailsUnverifiedFactError(
            "candidate_bundle must be exact PR #55 candidate bundle"
        )
    if type(candidate_bundle_bytes) is not bytes:
        raise FotMobReviewedMatchDetailsUnverifiedFactError(
            "candidate_bundle_bytes must be exact immutable bytes"
        )
    try:
        supplied_bytes = canonical_reviewed_match_details_unverified_candidate_bundle_bytes(
            candidate_bundle
        )
        rebuilt = build_reviewed_match_details_unverified_candidates(
            evidence=evidence,
            evidence_receipt_bytes=evidence_receipt_bytes,
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            review=review,
            review_bytes=review_bytes,
        )
        rebuilt_bytes = canonical_reviewed_match_details_unverified_candidate_bundle_bytes(
            rebuilt
        )
    except (
        FotMobReviewedMatchDetailsUnverifiedCandidateError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise FotMobReviewedMatchDetailsUnverifiedFactError(
            "PR #55 candidate bundle failed exact full-chain revalidation"
        ) from exc
    if supplied_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsUnverifiedFactError(
            "supplied PR #55 candidate bundle differs from exact semantic rebuild"
        )
    if candidate_bundle_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsUnverifiedFactError(
            "candidate_bundle_bytes are not exact canonical PR #55 bytes"
        )
    return rebuilt, rebuilt_bytes


@dataclasses.dataclass(frozen=True)
class ReviewedMatchDetailsUnverifiedFactBundle:
    schema_version: int
    dataset_name: str
    candidate_bundle_sha256: str
    candidate_bundle_size: int
    candidate_bundle: ReviewedMatchDetailsUnverifiedCandidateBundle
    evidence_file_path: str
    facts: tuple[FixtureIntelligenceFact, ...]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise FotMobReviewedMatchDetailsUnverifiedFactError("schema_version mismatch")
        if self.dataset_name != DATASET_NAME:
            raise FotMobReviewedMatchDetailsUnverifiedFactError("dataset_name mismatch")
        _sha(self.candidate_bundle_sha256, "candidate_bundle_sha256")
        if type(self.candidate_bundle_size) is not int or self.candidate_bundle_size <= 0:
            raise FotMobReviewedMatchDetailsUnverifiedFactError(
                "candidate_bundle_size must be an exact positive integer"
            )
        if type(self.candidate_bundle) is not ReviewedMatchDetailsUnverifiedCandidateBundle:
            raise FotMobReviewedMatchDetailsUnverifiedFactError(
                "candidate_bundle must remain exact PR #55 type"
            )
        try:
            candidate_bundle = dataclasses.replace(self.candidate_bundle)
            candidate_bytes = canonical_reviewed_match_details_unverified_candidate_bundle_bytes(
                candidate_bundle
            )
        except (
            FotMobReviewedMatchDetailsUnverifiedCandidateError,
            AttributeError,
            KeyError,
            TypeError,
            ValueError,
            OverflowError,
        ) as exc:
            raise FotMobReviewedMatchDetailsUnverifiedFactError(
                "embedded PR #55 candidate bundle failed invariant revalidation"
            ) from exc
        if len(candidate_bytes) != self.candidate_bundle_size:
            raise FotMobReviewedMatchDetailsUnverifiedFactError(
                "candidate_bundle_size does not match embedded PR #55 canonical bytes"
            )
        if hashlib.sha256(candidate_bytes).hexdigest() != self.candidate_bundle_sha256:
            raise FotMobReviewedMatchDetailsUnverifiedFactError(
                "candidate_bundle_sha256 does not match embedded PR #55 canonical bytes"
            )

        expected_path = _evidence_file_path(candidate_bundle)
        if type(self.evidence_file_path) is not str or self.evidence_file_path != expected_path:
            raise FotMobReviewedMatchDetailsUnverifiedFactError(
                "evidence_file_path must equal the exact PR #50 durable response.json path"
            )

        if type(self.facts) is not tuple or not self.facts:
            raise FotMobReviewedMatchDetailsUnverifiedFactError(
                "facts must be a non-empty immutable tuple"
            )
        if any(type(item) is not FixtureIntelligenceFact for item in self.facts):
            raise FotMobReviewedMatchDetailsUnverifiedFactError(
                "facts must contain exact FixtureIntelligenceFact values"
            )
        try:
            rebuilt_facts = tuple(dataclasses.replace(item) for item in self.facts)
        except (FixtureIntelligenceError, AttributeError, TypeError, ValueError) as exc:
            raise FotMobReviewedMatchDetailsUnverifiedFactError(
                "embedded Fixture Intelligence fact failed PR #30 invariant revalidation"
            ) from exc

        expected_facts = _facts_from_candidates(
            candidate_bundle,
            evidence_file_path=expected_path,
        )
        if len(rebuilt_facts) != len(expected_facts):
            raise FotMobReviewedMatchDetailsUnverifiedFactError(
                "fact count must equal exact PR #55 candidate count"
            )
        supplied_payload = tuple(_fact_dict(item) for item in rebuilt_facts)
        expected_payload = tuple(_fact_dict(item) for item in expected_facts)
        if supplied_payload != expected_payload:
            raise FotMobReviewedMatchDetailsUnverifiedFactError(
                "facts differ from exact status-preserving PR #55 candidate mapping"
            )
        for fact in rebuilt_facts:
            if fact.status is not IntelligenceFactStatus.UNVERIFIED:
                raise FotMobReviewedMatchDetailsUnverifiedFactError(
                    "every adapted fact must remain exact UNVERIFIED"
                )
            if fact.source_provider != SOURCE_PROVIDER:
                raise FotMobReviewedMatchDetailsUnverifiedFactError(
                    "fact source_provider must remain exact reviewed match-details provider"
                )
            if fact.source_role is not SourceRole.PRIMARY_FOOTBALL_CONTEXT:
                raise FotMobReviewedMatchDetailsUnverifiedFactError(
                    "fact source_role must remain PRIMARY_FOOTBALL_CONTEXT"
                )

        safety = _validate_safety(self.safety)
        object.__setattr__(self, "candidate_bundle", candidate_bundle)
        object.__setattr__(self, "facts", rebuilt_facts)
        object.__setattr__(self, "safety", safety)

    @property
    def fixture_identifier(self) -> str:
        """Exact source-scoped fixture identity inherited from PR #55."""

        return self.candidate_bundle.fixture_identifier

    @property
    def source_match_id(self) -> str:
        """Exact FotMob source match ID inherited from PR #55."""

        return self.candidate_bundle.source_match_id

    @property
    def kickoff(self) -> datetime.datetime:
        """Exact reviewed fixture kickoff inherited from PR #55."""

        return self.candidate_bundle.kickoff

    @property
    def observed_at(self) -> datetime.datetime:
        """Exact raw-evidence observation time inherited from PR #55."""

        return self.candidate_bundle.observed_at

    @property
    def raw_sha256(self) -> str:
        """Exact raw-evidence SHA-256 inherited from PR #55."""

        return self.candidate_bundle.raw_sha256

    def to_dict(self) -> dict[str, Any]:
        def iso(value: datetime.datetime) -> str:
            return value.isoformat().replace("+00:00", "Z")

        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "candidate_bundle_sha256": self.candidate_bundle_sha256,
            "candidate_bundle_size": self.candidate_bundle_size,
            "fixture_identifier": self.fixture_identifier,
            "source_match_id": self.source_match_id,
            "kickoff": iso(self.kickoff),
            "observed_at": iso(self.observed_at),
            "raw_sha256": self.raw_sha256,
            "candidate_bundle": self.candidate_bundle.to_dict(),
            "evidence_file_path": self.evidence_file_path,
            "facts": [_fact_dict(item) for item in self.facts],
            "safety": dict(self.safety),
        }


def build_reviewed_match_details_unverified_fact_bundle(
    *,
    evidence: Any,
    evidence_receipt_bytes: Any,
    manifest_bytes: Any,
    raw_bytes: Any,
    assessment: Any,
    assessment_bytes: Any,
    review: Any,
    review_bytes: Any,
    candidate_bundle: Any,
    candidate_bundle_bytes: Any,
) -> ReviewedMatchDetailsUnverifiedFactBundle:
    """Map exact PR #55 candidates to PR #30 facts without upgrading trust."""

    rebuilt_candidates, exact_candidate_bytes = _revalidate_candidate_bundle(
        evidence=evidence,
        evidence_receipt_bytes=evidence_receipt_bytes,
        manifest_bytes=manifest_bytes,
        raw_bytes=raw_bytes,
        assessment=assessment,
        assessment_bytes=assessment_bytes,
        review=review,
        review_bytes=review_bytes,
        candidate_bundle=candidate_bundle,
        candidate_bundle_bytes=candidate_bundle_bytes,
    )
    evidence_file_path = _evidence_file_path(rebuilt_candidates)
    facts = _facts_from_candidates(
        rebuilt_candidates,
        evidence_file_path=evidence_file_path,
    )
    return ReviewedMatchDetailsUnverifiedFactBundle(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        candidate_bundle_sha256=hashlib.sha256(exact_candidate_bytes).hexdigest(),
        candidate_bundle_size=len(exact_candidate_bytes),
        candidate_bundle=rebuilt_candidates,
        evidence_file_path=evidence_file_path,
        facts=facts,
        safety=_default_safety(),
    )


def canonical_reviewed_match_details_unverified_fact_bundle_bytes(value: Any) -> bytes:
    if type(value) is not ReviewedMatchDetailsUnverifiedFactBundle:
        raise FotMobReviewedMatchDetailsUnverifiedFactError(
            "value must be exact ReviewedMatchDetailsUnverifiedFactBundle"
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
    except FotMobReviewedMatchDetailsUnverifiedFactError:
        raise
    except (TypeError, ValueError, OverflowError, AttributeError) as exc:
        raise FotMobReviewedMatchDetailsUnverifiedFactError(
            "UNVERIFIED fact bundle canonicalization failed"
        ) from exc


def sha256_reviewed_match_details_unverified_fact_bundle(value: Any) -> str:
    return hashlib.sha256(
        canonical_reviewed_match_details_unverified_fact_bundle_bytes(value)
    ).hexdigest()


__all__ = [
    "DATASET_NAME",
    "EVIDENCE_ROOT",
    "SCHEMA_VERSION",
    "FotMobReviewedMatchDetailsUnverifiedFactError",
    "ReviewedMatchDetailsUnverifiedFactBundle",
    "build_reviewed_match_details_unverified_fact_bundle",
    "canonical_reviewed_match_details_unverified_fact_bundle_bytes",
    "sha256_reviewed_match_details_unverified_fact_bundle",
]
