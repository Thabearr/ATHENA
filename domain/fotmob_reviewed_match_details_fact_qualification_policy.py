"""Policy-only qualification review for exact PR #57 match-details facts.

This boundary records reviewer eligibility, capture-age, and corroboration
requirements for the exact reviewed PR #57 fact bundle. It does not qualify the
source globally, change fact status, build a Fixture Intelligence snapshot, or
authorize model/pricing/betting behavior.
"""

from __future__ import annotations

import dataclasses
import datetime
import enum
import hashlib
import json
import re
import types
from collections.abc import Mapping
from typing import Any

from domain.fixture_intelligence import IntelligenceCategory, IntelligenceFactStatus
from domain.fotmob_reviewed_match_details_structure import JsonValueKind
from domain.fotmob_reviewed_match_details_unverified_facts import (
    FotMobReviewedMatchDetailsUnverifiedFactError,
    ReviewedMatchDetailsUnverifiedFactBundle,
    canonical_reviewed_match_details_unverified_fact_bundle_bytes,
    revalidate_reviewed_match_details_unverified_fact_bundle,
)

SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-reviewed-match-details-fact-qualification-policy-v1"
MAX_CAPTURE_AGE_SECONDS = 31_536_000
_FIELD_RE = re.compile(r"^[-a-zA-Z0-9_]+$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "global_source_qualification_authorized",
        "source_qualification_satisfied",
        "supported_status_authorized",
        "status_classification_authorized",
        "intelligence_snapshot_authorized",
        "model_feature_authorized",
        "probability_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
    }
)


class FotMobReviewedMatchDetailsFactQualificationPolicyError(ValueError):
    """Raised when a reviewed qualification policy cannot be proven exactly."""


class FactQualificationDisposition(str, enum.Enum):
    ELIGIBLE = "ELIGIBLE"
    REJECTED = "REJECTED"


def _text(value: Any, label: str, maximum: int, *, allow_empty: bool = False) -> str:
    if type(value) is not str or value != value.strip():
        raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
            f"{label} must be an exact trimmed string"
        )
    if (not allow_empty and not value) or len(value) > maximum:
        raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
            f"{label} length is outside reviewed bounds"
        )
    return value


def _utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime) or value.tzinfo is not datetime.timezone.utc:
        raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
            f"{label} must use exact datetime.timezone.utc"
        )
    return value


def _sha(value: Any, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _default_safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise FotMobReviewedMatchDetailsFactQualificationPolicyError("safety keys mismatch")
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
                f"safety[{key!r}] must be exact bool False"
            )
    return _default_safety()


@dataclasses.dataclass(frozen=True)
class MatchDetailsFactQualificationDecision:
    category: IntelligenceCategory
    field: str
    json_pointer: str
    expected_kind: JsonValueKind
    disposition: FactQualificationDisposition
    max_capture_age_seconds: int | None
    requires_independent_corroboration: bool
    notes: str

    def __post_init__(self) -> None:
        if not isinstance(self.category, IntelligenceCategory):
            raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
                "category must be IntelligenceCategory"
            )
        field = _text(self.field, "field", 128)
        if _FIELD_RE.fullmatch(field) is None:
            raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
                "field must match the Fixture Intelligence field contract"
            )
        pointer = _text(self.json_pointer, "json_pointer", 384)
        if not pointer.startswith("/") or "/*" in pointer or pointer.endswith("/*"):
            raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
                "json_pointer must remain an exact approved non-wildcard path"
            )
        if not isinstance(self.expected_kind, JsonValueKind):
            raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
                "expected_kind must be JsonValueKind"
            )
        if not isinstance(self.disposition, FactQualificationDisposition):
            raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
                "disposition must be FactQualificationDisposition"
            )
        if type(self.requires_independent_corroboration) is not bool:
            raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
                "requires_independent_corroboration must be exact bool"
            )
        notes = _text(self.notes, "notes", 1024, allow_empty=True)

        if self.disposition is FactQualificationDisposition.ELIGIBLE:
            if (
                type(self.max_capture_age_seconds) is not int
                or self.max_capture_age_seconds <= 0
                or self.max_capture_age_seconds > MAX_CAPTURE_AGE_SECONDS
            ):
                raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
                    "ELIGIBLE decision requires bounded positive max_capture_age_seconds"
                )
        else:
            if self.max_capture_age_seconds is not None:
                raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
                    "REJECTED decision must not carry max_capture_age_seconds"
                )
            if self.requires_independent_corroboration is not False:
                raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
                    "REJECTED decision cannot request corroboration"
                )

        object.__setattr__(self, "field", field)
        object.__setattr__(self, "json_pointer", pointer)
        object.__setattr__(self, "notes", notes)

    @property
    def target_key(self) -> tuple[str, str, str]:
        return (self.category.value, self.field, self.json_pointer)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "field": self.field,
            "json_pointer": self.json_pointer,
            "expected_kind": self.expected_kind.value,
            "disposition": self.disposition.value,
            "max_capture_age_seconds": self.max_capture_age_seconds,
            "requires_independent_corroboration": self.requires_independent_corroboration,
            "notes": self.notes,
        }


def _candidate_key(candidate: Any) -> tuple[str, str, str]:
    return (candidate.category.value, candidate.field, candidate.json_pointer)


@dataclasses.dataclass(frozen=True)
class ReviewedMatchDetailsFactQualificationPolicy:
    schema_version: int
    dataset_name: str
    fact_bundle_sha256: str
    fact_bundle_size: int
    fact_bundle: ReviewedMatchDetailsUnverifiedFactBundle
    reviewed_at: datetime.datetime
    reviewer_reference: str
    decisions: tuple[MatchDetailsFactQualificationDecision, ...]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
                "schema_version mismatch"
            )
        if self.dataset_name != DATASET_NAME:
            raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
                "dataset_name mismatch"
            )
        _sha(self.fact_bundle_sha256, "fact_bundle_sha256")
        if type(self.fact_bundle_size) is not int or self.fact_bundle_size <= 0:
            raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
                "fact_bundle_size must be an exact positive integer"
            )
        if type(self.fact_bundle) is not ReviewedMatchDetailsUnverifiedFactBundle:
            raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
                "fact_bundle must remain exact PR #57 type"
            )
        try:
            fact_bundle = dataclasses.replace(self.fact_bundle)
            fact_bundle_bytes = canonical_reviewed_match_details_unverified_fact_bundle_bytes(
                fact_bundle
            )
        except (
            FotMobReviewedMatchDetailsUnverifiedFactError,
            AttributeError,
            KeyError,
            TypeError,
            ValueError,
            OverflowError,
        ) as exc:
            raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
                "embedded PR #57 fact bundle failed local invariant revalidation"
            ) from exc
        if len(fact_bundle_bytes) != self.fact_bundle_size:
            raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
                "fact_bundle_size does not match embedded PR #57 canonical bytes"
            )
        if hashlib.sha256(fact_bundle_bytes).hexdigest() != self.fact_bundle_sha256:
            raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
                "fact_bundle_sha256 does not match embedded PR #57 canonical bytes"
            )

        reviewed_at = _utc(self.reviewed_at, "reviewed_at")
        if reviewed_at < fact_bundle.observed_at:
            raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
                "reviewed_at must not predate exact evidence observation"
            )
        if reviewed_at >= fact_bundle.kickoff:
            raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
                "reviewed_at must remain strictly before fixture kickoff"
            )
        reviewer_reference = _text(
            self.reviewer_reference, "reviewer_reference", 256
        )

        if type(self.decisions) is not tuple or not self.decisions:
            raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
                "decisions must be a non-empty immutable tuple"
            )
        if any(
            type(item) is not MatchDetailsFactQualificationDecision
            for item in self.decisions
        ):
            raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
                "decisions must contain exact MatchDetailsFactQualificationDecision values"
            )
        try:
            decisions = tuple(dataclasses.replace(item) for item in self.decisions)
        except (
            FotMobReviewedMatchDetailsFactQualificationPolicyError,
            AttributeError,
            TypeError,
            ValueError,
        ) as exc:
            raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
                "qualification decision invariant revalidation failed"
            ) from exc
        expected_order = tuple(sorted(decisions, key=lambda item: item.target_key))
        if decisions != expected_order:
            raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
                "decisions must use deterministic target ordering"
            )
        decision_keys = [item.target_key for item in decisions]
        if len(set(decision_keys)) != len(decision_keys):
            raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
                "qualification decision targets must be unique"
            )

        candidate_map = {
            _candidate_key(candidate): candidate
            for candidate in fact_bundle.candidate_bundle.candidates
        }
        if set(decision_keys) != set(candidate_map):
            raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
                "qualification decisions must cover every and only exact PR #57 candidate"
            )
        for decision in decisions:
            candidate = candidate_map[decision.target_key]
            if decision.expected_kind is not candidate.json_kind:
                raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
                    "qualification expected_kind must equal exact PR #55 candidate kind"
                )

        if any(fact.status is not IntelligenceFactStatus.UNVERIFIED for fact in fact_bundle.facts):
            raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
                "qualification policy may consume UNVERIFIED PR #57 facts only"
            )

        safety = _validate_safety(self.safety)
        object.__setattr__(self, "fact_bundle", fact_bundle)
        object.__setattr__(self, "reviewed_at", reviewed_at)
        object.__setattr__(self, "reviewer_reference", reviewer_reference)
        object.__setattr__(self, "decisions", decisions)
        object.__setattr__(self, "safety", safety)

    @property
    def fixture_identifier(self) -> str:
        return self.fact_bundle.fixture_identifier

    @property
    def source_match_id(self) -> str:
        return self.fact_bundle.source_match_id

    @property
    def kickoff(self) -> datetime.datetime:
        return self.fact_bundle.kickoff

    @property
    def observed_at(self) -> datetime.datetime:
        return self.fact_bundle.observed_at

    @property
    def raw_sha256(self) -> str:
        return self.fact_bundle.raw_sha256

    def to_dict(self) -> dict[str, Any]:
        def iso(value: datetime.datetime) -> str:
            return value.isoformat().replace("+00:00", "Z")

        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "fact_bundle_sha256": self.fact_bundle_sha256,
            "fact_bundle_size": self.fact_bundle_size,
            "fixture_identifier": self.fixture_identifier,
            "source_match_id": self.source_match_id,
            "kickoff": iso(self.kickoff),
            "observed_at": iso(self.observed_at),
            "raw_sha256": self.raw_sha256,
            "fact_bundle": self.fact_bundle.to_dict(),
            "reviewed_at": iso(self.reviewed_at),
            "reviewer_reference": self.reviewer_reference,
            "decisions": [item.to_dict() for item in self.decisions],
            "safety": dict(self.safety),
        }


def _revalidate_fact_bundle(
    *,
    evidence: Any,
    evidence_receipt_bytes: Any,
    manifest_bytes: Any,
    raw_bytes: Any,
    assessment: Any,
    assessment_bytes: Any,
    review: Any,
    review_bytes: Any,
    fact_bundle: Any,
    fact_bundle_bytes: Any,
) -> tuple[ReviewedMatchDetailsUnverifiedFactBundle, bytes]:
    if type(fact_bundle_bytes) is not bytes:
        raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
            "fact_bundle_bytes must be exact immutable bytes"
        )
    try:
        rebuilt = revalidate_reviewed_match_details_unverified_fact_bundle(
            evidence=evidence,
            evidence_receipt_bytes=evidence_receipt_bytes,
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            review=review,
            review_bytes=review_bytes,
            fact_bundle=fact_bundle,
            fact_bundle_bytes=fact_bundle_bytes,
        )
        exact_bytes = canonical_reviewed_match_details_unverified_fact_bundle_bytes(
            rebuilt
        )
    except FotMobReviewedMatchDetailsUnverifiedFactError as exc:
        raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
            "PR #57 fact bundle failed exact full-chain revalidation"
        ) from exc
    return rebuilt, exact_bytes


def build_reviewed_match_details_fact_qualification_policy(
    *,
    evidence: Any,
    evidence_receipt_bytes: Any,
    manifest_bytes: Any,
    raw_bytes: Any,
    assessment: Any,
    assessment_bytes: Any,
    review: Any,
    review_bytes: Any,
    fact_bundle: Any,
    fact_bundle_bytes: Any,
    decisions: Any,
    reviewed_at: Any,
    reviewer_reference: Any,
) -> ReviewedMatchDetailsFactQualificationPolicy:
    """Record policy requirements without changing fact trust/status."""

    rebuilt_fact_bundle, exact_fact_bundle_bytes = _revalidate_fact_bundle(
        evidence=evidence,
        evidence_receipt_bytes=evidence_receipt_bytes,
        manifest_bytes=manifest_bytes,
        raw_bytes=raw_bytes,
        assessment=assessment,
        assessment_bytes=assessment_bytes,
        review=review,
        review_bytes=review_bytes,
        fact_bundle=fact_bundle,
        fact_bundle_bytes=fact_bundle_bytes,
    )
    if type(decisions) is not tuple or not decisions:
        raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
            "decisions must be a non-empty immutable tuple"
        )
    try:
        rebuilt_decisions = tuple(dataclasses.replace(item) for item in decisions)
    except (
        FotMobReviewedMatchDetailsFactQualificationPolicyError,
        AttributeError,
        TypeError,
        ValueError,
    ) as exc:
        raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
            "qualification decisions failed exact reconstruction"
        ) from exc
    sorted_decisions = tuple(sorted(rebuilt_decisions, key=lambda item: item.target_key))
    return ReviewedMatchDetailsFactQualificationPolicy(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        fact_bundle_sha256=hashlib.sha256(exact_fact_bundle_bytes).hexdigest(),
        fact_bundle_size=len(exact_fact_bundle_bytes),
        fact_bundle=rebuilt_fact_bundle,
        reviewed_at=reviewed_at,
        reviewer_reference=reviewer_reference,
        decisions=sorted_decisions,
        safety=_default_safety(),
    )


def canonical_reviewed_match_details_fact_qualification_policy_bytes(
    value: Any,
) -> bytes:
    if type(value) is not ReviewedMatchDetailsFactQualificationPolicy:
        raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
            "value must be exact ReviewedMatchDetailsFactQualificationPolicy"
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
    except FotMobReviewedMatchDetailsFactQualificationPolicyError:
        raise
    except (TypeError, ValueError, OverflowError, AttributeError) as exc:
        raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
            "qualification policy canonicalization failed"
        ) from exc


def revalidate_reviewed_match_details_fact_qualification_policy(
    *,
    evidence: Any,
    evidence_receipt_bytes: Any,
    manifest_bytes: Any,
    raw_bytes: Any,
    assessment: Any,
    assessment_bytes: Any,
    review: Any,
    review_bytes: Any,
    fact_bundle: Any,
    fact_bundle_bytes: Any,
    policy: Any,
    policy_bytes: Any,
) -> ReviewedMatchDetailsFactQualificationPolicy:
    """Rebuild exact policy against the full PR #52→#57 evidence chain."""

    if type(policy) is not ReviewedMatchDetailsFactQualificationPolicy:
        raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
            "policy must be exact ReviewedMatchDetailsFactQualificationPolicy"
        )
    if type(policy_bytes) is not bytes:
        raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
            "policy_bytes must be exact immutable bytes"
        )
    try:
        supplied_bytes = canonical_reviewed_match_details_fact_qualification_policy_bytes(
            policy
        )
        rebuilt = build_reviewed_match_details_fact_qualification_policy(
            evidence=evidence,
            evidence_receipt_bytes=evidence_receipt_bytes,
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            review=review,
            review_bytes=review_bytes,
            fact_bundle=fact_bundle,
            fact_bundle_bytes=fact_bundle_bytes,
            decisions=policy.decisions,
            reviewed_at=policy.reviewed_at,
            reviewer_reference=policy.reviewer_reference,
        )
        rebuilt_bytes = canonical_reviewed_match_details_fact_qualification_policy_bytes(
            rebuilt
        )
    except FotMobReviewedMatchDetailsFactQualificationPolicyError:
        raise
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
            "qualification policy failed exact full-chain reconstruction"
        ) from exc
    if supplied_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
            "supplied qualification policy differs from exact full-chain rebuild"
        )
    if policy_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsFactQualificationPolicyError(
            "policy_bytes are not exact canonical qualification policy bytes"
        )
    return rebuilt


def sha256_reviewed_match_details_fact_qualification_policy(value: Any) -> str:
    return hashlib.sha256(
        canonical_reviewed_match_details_fact_qualification_policy_bytes(value)
    ).hexdigest()


__all__ = [
    "DATASET_NAME",
    "MAX_CAPTURE_AGE_SECONDS",
    "SCHEMA_VERSION",
    "FactQualificationDisposition",
    "FotMobReviewedMatchDetailsFactQualificationPolicyError",
    "MatchDetailsFactQualificationDecision",
    "ReviewedMatchDetailsFactQualificationPolicy",
    "build_reviewed_match_details_fact_qualification_policy",
    "canonical_reviewed_match_details_fact_qualification_policy_bytes",
    "revalidate_reviewed_match_details_fact_qualification_policy",
    "sha256_reviewed_match_details_fact_qualification_policy",
]
