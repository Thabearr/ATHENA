"""Policy-only status-classification handoff for reviewed FotMob match-details facts.

This boundary consumes the exact PR #52 -> PR #58 chain and records explicit
freshness deadlines for every exact PR #58 QUALIFIED observation. It does not
change any Fixture Intelligence fact status. REJECTED PR #58 observations are
mechanically blocked and cannot receive a freshness rule.
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

from domain.fixture_intelligence import IntelligenceCategory, SourceRole
from domain.fotmob_reviewed_match_details_field_evidence_qualification import (
    FieldEvidenceQualificationDisposition,
    FotMobReviewedMatchDetailsFieldEvidenceQualificationError,
    ReviewedMatchDetailsFieldEvidenceQualification,
    canonical_reviewed_match_details_field_evidence_qualification_bytes,
    revalidate_reviewed_match_details_field_evidence_qualification,
)
from domain.fotmob_reviewed_match_details_unverified_facts import (
    EVIDENCE_ROOT,
    SOURCE_PROVIDER,
)

SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-reviewed-match-details-status-classification-policy-v1"
POLICY_SCOPE = "EXACT_OBSERVATION_ONLY"
CONFLICT_POLICY = "PRESERVE_DIFFERING_QUALIFIED_VALUES"
RAW_FILENAME = "response.json"

_SHA_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_FIXTURE_RE = re.compile(r"^FOTMOB:([1-9][0-9]*)$", flags=re.ASCII)
_FIELD_RE = re.compile(r"^[-a-zA-Z0-9_]+$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "automatic_status_classification_authorized",
        "supported_status_authorized",
        "stale_status_authorized",
        "conflicted_status_authorized",
        "status_promotion_authorized",
        "conflict_resolution_authorized",
        "intelligence_snapshot_authorized",
        "model_feature_authorized",
        "probability_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
    }
)


class FotMobReviewedMatchDetailsStatusClassificationPolicyError(ValueError):
    """Raised when the exact classification-policy handoff cannot be proven."""


class StatusClassificationPolicyDisposition(str, enum.Enum):
    ELIGIBLE_FOR_LATER_CLASSIFICATION = "ELIGIBLE_FOR_LATER_CLASSIFICATION"
    BLOCKED_BY_QUALIFICATION = "BLOCKED_BY_QUALIFICATION"


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _text(value: Any, label: str, maximum: int) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
    ):
        raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
            f"{label} must be a non-empty exact trimmed string within {maximum} characters"
        )
    return value


def _utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
            f"{label} must be a datetime"
        )
    if value.tzinfo is not datetime.timezone.utc:
        raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
            f"{label} must already use exact datetime.timezone.utc"
        )
    return value


def _iso(value: datetime.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _default_safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
            "safety keys mismatch"
        )
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
                f"safety[{key!r}] must be exact bool False"
            )
    return _default_safety()


def _expected_evidence_file_path(
    source_match_id: str,
    observed_at: datetime.datetime,
    raw_sha256: str,
) -> str:
    timestamp = observed_at.strftime("%Y%m%dT%H%M%S%fZ")
    identifier = f"{source_match_id}--{timestamp}--{raw_sha256}"
    return f"{EVIDENCE_ROOT}/{identifier}/{RAW_FILENAME}"


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
            "status-classification policy serialization failed"
        ) from exc


def _decision_key(
    category: IntelligenceCategory,
    field: str,
    source_reference: str,
) -> tuple[str, str, str]:
    return (category.value, field, source_reference)


@dataclasses.dataclass(frozen=True)
class MatchDetailsFreshnessPolicyRule:
    """Reviewer-supplied freshness deadline for one exact QUALIFIED fact."""

    category: IntelligenceCategory
    field: str
    source_reference: str
    fresh_until: datetime.datetime
    rationale: str

    def __post_init__(self) -> None:
        if not isinstance(self.category, IntelligenceCategory):
            raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
                "category must be IntelligenceCategory"
            )
        field = _text(self.field, "field", 128)
        if _FIELD_RE.fullmatch(field) is None:
            raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
                "field must match the Fixture Intelligence field contract"
            )
        source_reference = _text(self.source_reference, "source_reference", 512)
        fresh_until = _utc(self.fresh_until, "fresh_until")
        rationale = _text(self.rationale, "rationale", 1024)
        object.__setattr__(self, "field", field)
        object.__setattr__(self, "source_reference", source_reference)
        object.__setattr__(self, "fresh_until", fresh_until)
        object.__setattr__(self, "rationale", rationale)

    @property
    def key(self) -> tuple[str, str, str]:
        return _decision_key(self.category, self.field, self.source_reference)


@dataclasses.dataclass(frozen=True)
class RecordedMatchDetailsStatusPolicyDecision:
    """Detached policy decision bound to one exact PR #58 fact hash."""

    category: IntelligenceCategory
    field: str
    source_reference: str
    fact_sha256: str
    qualification_disposition: FieldEvidenceQualificationDisposition
    disposition: StatusClassificationPolicyDisposition
    fresh_until: datetime.datetime | None
    rationale: str

    def __post_init__(self) -> None:
        if not isinstance(self.category, IntelligenceCategory):
            raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
                "recorded category must be IntelligenceCategory"
            )
        field = _text(self.field, "recorded field", 128)
        if _FIELD_RE.fullmatch(field) is None:
            raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
                "recorded field must match the Fixture Intelligence field contract"
            )
        source_reference = _text(
            self.source_reference,
            "recorded source_reference",
            512,
        )
        fact_sha256 = _sha(self.fact_sha256, "fact_sha256")
        if not isinstance(
            self.qualification_disposition,
            FieldEvidenceQualificationDisposition,
        ):
            raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
                "qualification_disposition must be FieldEvidenceQualificationDisposition"
            )
        if not isinstance(self.disposition, StatusClassificationPolicyDisposition):
            raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
                "disposition must be StatusClassificationPolicyDisposition"
            )
        fresh_until = self.fresh_until
        if fresh_until is not None:
            fresh_until = _utc(fresh_until, "recorded fresh_until")
        rationale = _text(self.rationale, "recorded rationale", 1024)

        if (
            self.qualification_disposition
            is FieldEvidenceQualificationDisposition.QUALIFIED
        ):
            if (
                self.disposition
                is not StatusClassificationPolicyDisposition.ELIGIBLE_FOR_LATER_CLASSIFICATION
                or fresh_until is None
            ):
                raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
                    "QUALIFIED observations require an eligible policy decision with fresh_until"
                )
        else:
            if (
                self.disposition
                is not StatusClassificationPolicyDisposition.BLOCKED_BY_QUALIFICATION
                or fresh_until is not None
            ):
                raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
                    "REJECTED observations must remain blocked and cannot receive fresh_until"
                )

        object.__setattr__(self, "field", field)
        object.__setattr__(self, "source_reference", source_reference)
        object.__setattr__(self, "fact_sha256", fact_sha256)
        object.__setattr__(self, "fresh_until", fresh_until)
        object.__setattr__(self, "rationale", rationale)

    @property
    def key(self) -> tuple[str, str, str]:
        return _decision_key(self.category, self.field, self.source_reference)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "field": self.field,
            "source_reference": self.source_reference,
            "fact_sha256": self.fact_sha256,
            "qualification_disposition": self.qualification_disposition.value,
            "disposition": self.disposition.value,
            "fresh_until": None if self.fresh_until is None else _iso(self.fresh_until),
            "rationale": self.rationale,
        }


@dataclasses.dataclass(frozen=True)
class ReviewedMatchDetailsStatusClassificationPolicy:
    """Detached policy artifact; it authorizes no fact-status mutation."""

    schema_version: int
    dataset_name: str
    policy_scope: str
    conflict_policy: str
    qualification_sha256: str
    qualification_size: int
    fixture_identifier: str
    source_match_id: str
    kickoff: datetime.datetime
    observed_at: datetime.datetime
    qualification_reviewed_at: datetime.datetime
    policy_reviewed_at: datetime.datetime
    raw_sha256: str
    evidence_file_path: str
    source_provider: str
    source_role: SourceRole
    reviewer_reference: str
    decisions: tuple[RecordedMatchDetailsStatusPolicyDecision, ...]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
                "schema_version mismatch"
            )
        if self.dataset_name != DATASET_NAME:
            raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
                "dataset_name mismatch"
            )
        if self.policy_scope != POLICY_SCOPE:
            raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
                "policy_scope must remain EXACT_OBSERVATION_ONLY"
            )
        if self.conflict_policy != CONFLICT_POLICY:
            raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
                "conflict_policy must preserve differing qualified values"
            )
        _sha(self.qualification_sha256, "qualification_sha256")
        if type(self.qualification_size) is not int or self.qualification_size <= 0:
            raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
                "qualification_size must be an exact positive integer"
            )

        fixture_identifier = _text(self.fixture_identifier, "fixture_identifier", 512)
        source_match_id = _text(self.source_match_id, "source_match_id", 256)
        match = _FIXTURE_RE.fullmatch(fixture_identifier)
        if match is None or match.group(1) != source_match_id:
            raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
                "fixture_identifier/source_match_id mismatch"
            )

        kickoff = _utc(self.kickoff, "kickoff")
        observed_at = _utc(self.observed_at, "observed_at")
        qualification_reviewed_at = _utc(
            self.qualification_reviewed_at,
            "qualification_reviewed_at",
        )
        policy_reviewed_at = _utc(self.policy_reviewed_at, "policy_reviewed_at")
        if observed_at >= kickoff:
            raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
                "observed_at must remain strictly before kickoff"
            )
        if qualification_reviewed_at < observed_at or qualification_reviewed_at >= kickoff:
            raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
                "qualification_reviewed_at chronology mismatch"
            )
        if policy_reviewed_at < qualification_reviewed_at or policy_reviewed_at >= kickoff:
            raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
                "policy_reviewed_at must follow qualification and remain before kickoff"
            )

        raw_sha256 = _sha(self.raw_sha256, "raw_sha256")
        evidence_file_path = _text(
            self.evidence_file_path,
            "evidence_file_path",
            1024,
        )
        if evidence_file_path != _expected_evidence_file_path(
            source_match_id,
            observed_at,
            raw_sha256,
        ):
            raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
                "evidence_file_path must match exact durable capture identity"
            )
        if self.source_provider != SOURCE_PROVIDER:
            raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
                "source_provider mismatch"
            )
        if self.source_role is not SourceRole.PRIMARY_FOOTBALL_CONTEXT:
            raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
                "source_role must remain PRIMARY_FOOTBALL_CONTEXT"
            )
        reviewer_reference = _text(
            self.reviewer_reference,
            "reviewer_reference",
            256,
        )

        if type(self.decisions) is not tuple or not self.decisions:
            raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
                "decisions must be a non-empty immutable tuple"
            )
        if any(
            type(item) is not RecordedMatchDetailsStatusPolicyDecision
            for item in self.decisions
        ):
            raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
                "decisions must contain exact recorded policy values"
            )
        try:
            rebuilt_decisions = tuple(dataclasses.replace(item) for item in self.decisions)
        except (
            FotMobReviewedMatchDetailsStatusClassificationPolicyError,
            AttributeError,
            TypeError,
            ValueError,
        ) as exc:
            raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
                "nested policy decision failed invariant revalidation"
            ) from exc

        expected = tuple(sorted(rebuilt_decisions, key=lambda item: item.key))
        if rebuilt_decisions != expected:
            raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
                "decisions must be deterministically sorted"
            )
        keys = tuple(item.key for item in rebuilt_decisions)
        if len(set(keys)) != len(keys):
            raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
                "decisions must target unique exact facts"
            )
        fact_hashes = tuple(item.fact_sha256 for item in rebuilt_decisions)
        if len(set(fact_hashes)) != len(fact_hashes):
            raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
                "recorded fact_sha256 values must be unique"
            )

        source_prefix = f"FOTMOB_MATCH_DETAILS:{source_match_id}:/"
        for item in rebuilt_decisions:
            if not item.source_reference.startswith(source_prefix):
                raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
                    "recorded source_reference does not match exact source fixture"
                )
            if item.fresh_until is not None:
                if item.fresh_until < observed_at or item.fresh_until >= kickoff:
                    raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
                        "fresh_until must not precede observation and must remain before kickoff"
                    )

        safety = _validate_safety(self.safety)
        object.__setattr__(self, "fixture_identifier", fixture_identifier)
        object.__setattr__(self, "source_match_id", source_match_id)
        object.__setattr__(self, "kickoff", kickoff)
        object.__setattr__(self, "observed_at", observed_at)
        object.__setattr__(self, "qualification_reviewed_at", qualification_reviewed_at)
        object.__setattr__(self, "policy_reviewed_at", policy_reviewed_at)
        object.__setattr__(self, "raw_sha256", raw_sha256)
        object.__setattr__(self, "evidence_file_path", evidence_file_path)
        object.__setattr__(self, "reviewer_reference", reviewer_reference)
        object.__setattr__(self, "decisions", rebuilt_decisions)
        object.__setattr__(self, "safety", safety)

    @property
    def eligible_count(self) -> int:
        return sum(
            item.disposition
            is StatusClassificationPolicyDisposition.ELIGIBLE_FOR_LATER_CLASSIFICATION
            for item in self.decisions
        )

    @property
    def blocked_count(self) -> int:
        return sum(
            item.disposition
            is StatusClassificationPolicyDisposition.BLOCKED_BY_QUALIFICATION
            for item in self.decisions
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "policy_scope": self.policy_scope,
            "conflict_policy": self.conflict_policy,
            "qualification_sha256": self.qualification_sha256,
            "qualification_size": self.qualification_size,
            "fixture_identifier": self.fixture_identifier,
            "source_match_id": self.source_match_id,
            "kickoff": _iso(self.kickoff),
            "observed_at": _iso(self.observed_at),
            "qualification_reviewed_at": _iso(self.qualification_reviewed_at),
            "policy_reviewed_at": _iso(self.policy_reviewed_at),
            "raw_sha256": self.raw_sha256,
            "evidence_file_path": self.evidence_file_path,
            "source_provider": self.source_provider,
            "source_role": self.source_role.value,
            "reviewer_reference": self.reviewer_reference,
            "eligible_count": self.eligible_count,
            "blocked_count": self.blocked_count,
            "decisions": [item.to_dict() for item in self.decisions],
            "safety": dict(self.safety),
        }


def _revalidate_qualification(
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
    qualification: Any,
    qualification_bytes: Any,
) -> tuple[ReviewedMatchDetailsFieldEvidenceQualification, bytes]:
    if type(qualification) is not ReviewedMatchDetailsFieldEvidenceQualification:
        raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
            "qualification must be exact PR #58 qualification"
        )
    if type(qualification_bytes) is not bytes:
        raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
            "qualification_bytes must be exact immutable bytes"
        )
    try:
        rebuilt = revalidate_reviewed_match_details_field_evidence_qualification(
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
            qualification=qualification,
            qualification_bytes=qualification_bytes,
        )
        exact_bytes = canonical_reviewed_match_details_field_evidence_qualification_bytes(
            rebuilt
        )
    except (
        FotMobReviewedMatchDetailsFieldEvidenceQualificationError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
            "PR #58 qualification failed exact full-chain revalidation"
        ) from exc
    if exact_bytes != qualification_bytes:
        raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
            "qualification_bytes differ from exact PR #58 rebuild"
        )
    return rebuilt, exact_bytes


def build_reviewed_match_details_status_classification_policy(
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
    qualification: Any,
    qualification_bytes: Any,
    freshness_rules: Any,
    policy_reviewed_at: Any,
    reviewer_reference: Any,
) -> ReviewedMatchDetailsStatusClassificationPolicy:
    """Record freshness/conflict policy without changing any fact status."""

    rebuilt, exact_qualification_bytes = _revalidate_qualification(
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
        qualification=qualification,
        qualification_bytes=qualification_bytes,
    )

    policy_reviewed_at = _utc(policy_reviewed_at, "policy_reviewed_at")
    reviewer_reference = _text(reviewer_reference, "reviewer_reference", 256)
    if policy_reviewed_at < rebuilt.reviewed_at or policy_reviewed_at >= rebuilt.kickoff:
        raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
            "policy_reviewed_at must follow PR #58 review and remain before kickoff"
        )

    if type(freshness_rules) is not tuple:
        raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
            "freshness_rules must be an exact immutable tuple"
        )
    if any(type(item) is not MatchDetailsFreshnessPolicyRule for item in freshness_rules):
        raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
            "freshness_rules must contain exact MatchDetailsFreshnessPolicyRule values"
        )
    try:
        rebuilt_rules = tuple(dataclasses.replace(item) for item in freshness_rules)
    except (
        FotMobReviewedMatchDetailsStatusClassificationPolicyError,
        AttributeError,
        TypeError,
        ValueError,
    ) as exc:
        raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
            "freshness rule failed invariant revalidation"
        ) from exc

    expected_rules = tuple(sorted(rebuilt_rules, key=lambda item: item.key))
    if rebuilt_rules != expected_rules:
        raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
            "freshness_rules must be deterministically sorted"
        )
    rule_keys = tuple(item.key for item in rebuilt_rules)
    if len(set(rule_keys)) != len(rule_keys):
        raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
            "freshness_rules must target unique exact facts"
        )

    qualified = tuple(
        item
        for item in rebuilt.decisions
        if item.disposition is FieldEvidenceQualificationDisposition.QUALIFIED
    )
    qualified_keys = {item.key for item in qualified}
    if set(rule_keys) != qualified_keys:
        raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
            "freshness_rules must cover every and only PR #58 QUALIFIED fact"
        )
    rule_by_key = {item.key: item for item in rebuilt_rules}

    recorded: list[RecordedMatchDetailsStatusPolicyDecision] = []
    for item in rebuilt.decisions:
        if item.disposition is FieldEvidenceQualificationDisposition.QUALIFIED:
            rule = rule_by_key[item.key]
            if rule.fresh_until < rebuilt.observed_at or rule.fresh_until >= rebuilt.kickoff:
                raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
                    "fresh_until must not precede observation and must remain before kickoff"
                )
            recorded.append(
                RecordedMatchDetailsStatusPolicyDecision(
                    category=item.category,
                    field=item.field,
                    source_reference=item.source_reference,
                    fact_sha256=item.fact_sha256,
                    qualification_disposition=item.disposition,
                    disposition=StatusClassificationPolicyDisposition.ELIGIBLE_FOR_LATER_CLASSIFICATION,
                    fresh_until=rule.fresh_until,
                    rationale=rule.rationale,
                )
            )
        else:
            recorded.append(
                RecordedMatchDetailsStatusPolicyDecision(
                    category=item.category,
                    field=item.field,
                    source_reference=item.source_reference,
                    fact_sha256=item.fact_sha256,
                    qualification_disposition=item.disposition,
                    disposition=StatusClassificationPolicyDisposition.BLOCKED_BY_QUALIFICATION,
                    fresh_until=None,
                    rationale=item.rationale,
                )
            )

    return ReviewedMatchDetailsStatusClassificationPolicy(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        policy_scope=POLICY_SCOPE,
        conflict_policy=CONFLICT_POLICY,
        qualification_sha256=hashlib.sha256(exact_qualification_bytes).hexdigest(),
        qualification_size=len(exact_qualification_bytes),
        fixture_identifier=rebuilt.fixture_identifier,
        source_match_id=rebuilt.source_match_id,
        kickoff=rebuilt.kickoff,
        observed_at=rebuilt.observed_at,
        qualification_reviewed_at=rebuilt.reviewed_at,
        policy_reviewed_at=policy_reviewed_at,
        raw_sha256=rebuilt.raw_sha256,
        evidence_file_path=rebuilt.evidence_file_path,
        source_provider=rebuilt.source_provider,
        source_role=rebuilt.source_role,
        reviewer_reference=reviewer_reference,
        decisions=tuple(recorded),
        safety=_default_safety(),
    )


def canonical_reviewed_match_details_status_classification_policy_bytes(
    value: Any,
) -> bytes:
    if type(value) is not ReviewedMatchDetailsStatusClassificationPolicy:
        raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
            "value must be exact ReviewedMatchDetailsStatusClassificationPolicy"
        )
    try:
        rebuilt = dataclasses.replace(value)
        return _canonical_json_bytes(rebuilt.to_dict())
    except FotMobReviewedMatchDetailsStatusClassificationPolicyError:
        raise
    except (TypeError, ValueError, OverflowError, AttributeError) as exc:
        raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
            "status-classification policy canonicalization failed"
        ) from exc


def revalidate_reviewed_match_details_status_classification_policy(
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
    qualification: Any,
    qualification_bytes: Any,
    policy: Any,
    policy_bytes: Any,
) -> ReviewedMatchDetailsStatusClassificationPolicy:
    """Replay PR #52 -> PR #60 before consuming a policy artifact."""

    if type(policy) is not ReviewedMatchDetailsStatusClassificationPolicy:
        raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
            "policy must be exact ReviewedMatchDetailsStatusClassificationPolicy"
        )
    if type(policy_bytes) is not bytes:
        raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
            "policy_bytes must be exact immutable bytes"
        )
    try:
        supplied_bytes = canonical_reviewed_match_details_status_classification_policy_bytes(
            policy
        )
        freshness_rules = tuple(
            MatchDetailsFreshnessPolicyRule(
                category=item.category,
                field=item.field,
                source_reference=item.source_reference,
                fresh_until=item.fresh_until,
                rationale=item.rationale,
            )
            for item in policy.decisions
            if item.disposition
            is StatusClassificationPolicyDisposition.ELIGIBLE_FOR_LATER_CLASSIFICATION
        )
        rebuilt = build_reviewed_match_details_status_classification_policy(
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
            qualification=qualification,
            qualification_bytes=qualification_bytes,
            freshness_rules=freshness_rules,
            policy_reviewed_at=policy.policy_reviewed_at,
            reviewer_reference=policy.reviewer_reference,
        )
        rebuilt_bytes = canonical_reviewed_match_details_status_classification_policy_bytes(
            rebuilt
        )
    except (
        FotMobReviewedMatchDetailsStatusClassificationPolicyError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
            "PR #60 policy failed exact full-chain revalidation"
        ) from exc
    if supplied_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
            "supplied PR #60 policy differs from exact full-chain rebuild"
        )
    if policy_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsStatusClassificationPolicyError(
            "policy_bytes are not exact canonical PR #60 bytes"
        )
    return rebuilt


def sha256_reviewed_match_details_status_classification_policy(value: Any) -> str:
    return hashlib.sha256(
        canonical_reviewed_match_details_status_classification_policy_bytes(value)
    ).hexdigest()


__all__ = [
    "CONFLICT_POLICY",
    "DATASET_NAME",
    "POLICY_SCOPE",
    "SCHEMA_VERSION",
    "FotMobReviewedMatchDetailsStatusClassificationPolicyError",
    "MatchDetailsFreshnessPolicyRule",
    "RecordedMatchDetailsStatusPolicyDecision",
    "ReviewedMatchDetailsStatusClassificationPolicy",
    "StatusClassificationPolicyDisposition",
    "build_reviewed_match_details_status_classification_policy",
    "canonical_reviewed_match_details_status_classification_policy_bytes",
    "revalidate_reviewed_match_details_status_classification_policy",
    "sha256_reviewed_match_details_status_classification_policy",
]
