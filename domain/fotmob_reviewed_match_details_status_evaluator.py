"""Deterministic evidence-status evaluation for reviewed FotMob match details.

PR #61 consumes the complete exact PR #52 -> PR #60 chain and applies PR #60's
reviewed freshness policy at one explicit UTC classification timestamp.  The
resulting dispositions are evidence-evaluation candidates only; this boundary
does not create or mutate any Fixture Intelligence fact status.
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
)
from domain.fotmob_reviewed_match_details_status_classification_policy import (
    CONFLICT_POLICY,
    FotMobReviewedMatchDetailsStatusClassificationPolicyError,
    ReviewedMatchDetailsStatusClassificationPolicy,
    StatusClassificationPolicyDisposition,
    canonical_reviewed_match_details_status_classification_policy_bytes,
    revalidate_reviewed_match_details_status_classification_policy,
)
from domain.fotmob_reviewed_match_details_status_classification_policy_semantics import (
    FRESHNESS_COMPARISON,
    FotMobReviewedMatchDetailsFreshnessComparisonError,
    is_within_reviewed_freshness_window,
)

SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-reviewed-match-details-status-evaluation-v1"
EVALUATION_SCOPE = "EXACT_POLICY_OBSERVATION_ONLY"

_SHA_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_FIXTURE_RE = re.compile(r"^FOTMOB:([1-9][0-9]*)$", flags=re.ASCII)
_FIELD_RE = re.compile(r"^[-a-zA-Z0-9_]+$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "fact_status_mutation_authorized",
        "supported_fact_authorized",
        "stale_fact_authorized",
        "conflicted_fact_authorized",
        "conflict_aggregation_authorized",
        "conflict_resolution_authorized",
        "source_wide_qualification_authorized",
        "intelligence_snapshot_authorized",
        "model_feature_authorized",
        "probability_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
        "network_acquisition_authorized",
    }
)


class FotMobReviewedMatchDetailsStatusEvaluationError(ValueError):
    """Raised when exact deterministic status evaluation cannot be proven."""


class StatusEvaluationDisposition(str, enum.Enum):
    """Evidence-evaluation outcomes; these are deliberately not PR #30 statuses."""

    FRESH_QUALIFIED = "FRESH_QUALIFIED"
    STALE_QUALIFIED = "STALE_QUALIFIED"
    BLOCKED_BY_QUALIFICATION = "BLOCKED_BY_QUALIFICATION"


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        raise FotMobReviewedMatchDetailsStatusEvaluationError(
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
        raise FotMobReviewedMatchDetailsStatusEvaluationError(
            f"{label} must be a non-empty exact trimmed string within {maximum} characters"
        )
    return value


def _utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise FotMobReviewedMatchDetailsStatusEvaluationError(
            f"{label} must be a datetime"
        )
    if value.tzinfo is not datetime.timezone.utc:
        raise FotMobReviewedMatchDetailsStatusEvaluationError(
            f"{label} must already use exact datetime.timezone.utc"
        )
    return value


def _iso(value: datetime.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _default_safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise FotMobReviewedMatchDetailsStatusEvaluationError("safety keys mismatch")
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise FotMobReviewedMatchDetailsStatusEvaluationError(
                f"safety[{key!r}] must be exact bool False"
            )
    return _default_safety()


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
        raise FotMobReviewedMatchDetailsStatusEvaluationError(
            "status-evaluation serialization failed"
        ) from exc


def _decision_key(
    category: IntelligenceCategory,
    field: str,
    source_reference: str,
) -> tuple[str, str, str]:
    return (category.value, field, source_reference)


@dataclasses.dataclass(frozen=True)
class RecordedMatchDetailsStatusEvaluationDecision:
    """Detached deterministic result for one exact PR #60 policy decision."""

    category: IntelligenceCategory
    field: str
    source_reference: str
    fact_sha256: str
    qualification_disposition: FieldEvidenceQualificationDisposition
    policy_disposition: StatusClassificationPolicyDisposition
    evaluation_disposition: StatusEvaluationDisposition
    fresh_until: datetime.datetime | None
    rationale: str

    def __post_init__(self) -> None:
        if not isinstance(self.category, IntelligenceCategory):
            raise FotMobReviewedMatchDetailsStatusEvaluationError(
                "category must be IntelligenceCategory"
            )
        field = _text(self.field, "field", 128)
        if _FIELD_RE.fullmatch(field) is None:
            raise FotMobReviewedMatchDetailsStatusEvaluationError(
                "field must match the Fixture Intelligence field contract"
            )
        source_reference = _text(self.source_reference, "source_reference", 512)
        fact_sha256 = _sha(self.fact_sha256, "fact_sha256")
        if not isinstance(
            self.qualification_disposition,
            FieldEvidenceQualificationDisposition,
        ):
            raise FotMobReviewedMatchDetailsStatusEvaluationError(
                "qualification_disposition must be FieldEvidenceQualificationDisposition"
            )
        if not isinstance(self.policy_disposition, StatusClassificationPolicyDisposition):
            raise FotMobReviewedMatchDetailsStatusEvaluationError(
                "policy_disposition must be StatusClassificationPolicyDisposition"
            )
        if not isinstance(self.evaluation_disposition, StatusEvaluationDisposition):
            raise FotMobReviewedMatchDetailsStatusEvaluationError(
                "evaluation_disposition must be StatusEvaluationDisposition"
            )
        fresh_until = self.fresh_until
        if fresh_until is not None:
            fresh_until = _utc(fresh_until, "fresh_until")
        rationale = _text(self.rationale, "rationale", 1024)

        if (
            self.policy_disposition
            is StatusClassificationPolicyDisposition.BLOCKED_BY_QUALIFICATION
        ):
            if (
                self.qualification_disposition
                is not FieldEvidenceQualificationDisposition.REJECTED
                or self.evaluation_disposition
                is not StatusEvaluationDisposition.BLOCKED_BY_QUALIFICATION
                or fresh_until is not None
            ):
                raise FotMobReviewedMatchDetailsStatusEvaluationError(
                    "blocked policy decisions must remain rejected, blocked and deadline-free"
                )
        else:
            if (
                self.qualification_disposition
                is not FieldEvidenceQualificationDisposition.QUALIFIED
                or self.evaluation_disposition
                not in (
                    StatusEvaluationDisposition.FRESH_QUALIFIED,
                    StatusEvaluationDisposition.STALE_QUALIFIED,
                )
                or fresh_until is None
            ):
                raise FotMobReviewedMatchDetailsStatusEvaluationError(
                    "eligible policy decisions must remain qualified with an exact freshness result"
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
            "policy_disposition": self.policy_disposition.value,
            "evaluation_disposition": self.evaluation_disposition.value,
            "fresh_until": None if self.fresh_until is None else _iso(self.fresh_until),
            "rationale": self.rationale,
        }


@dataclasses.dataclass(frozen=True)
class ReviewedMatchDetailsStatusEvaluation:
    """Detached exact-observation evaluation artifact; it promotes no fact status."""

    schema_version: int
    dataset_name: str
    evaluation_scope: str
    freshness_comparison: str
    conflict_policy: str
    policy_sha256: str
    policy_size: int
    fixture_identifier: str
    source_match_id: str
    kickoff: datetime.datetime
    observed_at: datetime.datetime
    qualification_reviewed_at: datetime.datetime
    policy_reviewed_at: datetime.datetime
    classified_at: datetime.datetime
    raw_sha256: str
    evidence_file_path: str
    source_provider: str
    source_role: SourceRole
    decisions: tuple[RecordedMatchDetailsStatusEvaluationDecision, ...]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise FotMobReviewedMatchDetailsStatusEvaluationError("schema_version mismatch")
        if self.dataset_name != DATASET_NAME:
            raise FotMobReviewedMatchDetailsStatusEvaluationError("dataset_name mismatch")
        if self.evaluation_scope != EVALUATION_SCOPE:
            raise FotMobReviewedMatchDetailsStatusEvaluationError(
                "evaluation_scope must remain EXACT_POLICY_OBSERVATION_ONLY"
            )
        if self.freshness_comparison != FRESHNESS_COMPARISON:
            raise FotMobReviewedMatchDetailsStatusEvaluationError(
                "freshness_comparison must remain the exact reviewed PR #60 rule"
            )
        if self.conflict_policy != CONFLICT_POLICY:
            raise FotMobReviewedMatchDetailsStatusEvaluationError(
                "conflict_policy must preserve differing qualified values"
            )
        _sha(self.policy_sha256, "policy_sha256")
        if type(self.policy_size) is not int or self.policy_size <= 0:
            raise FotMobReviewedMatchDetailsStatusEvaluationError(
                "policy_size must be an exact positive integer"
            )

        fixture_identifier = _text(self.fixture_identifier, "fixture_identifier", 512)
        source_match_id = _text(self.source_match_id, "source_match_id", 256)
        match = _FIXTURE_RE.fullmatch(fixture_identifier)
        if match is None or match.group(1) != source_match_id:
            raise FotMobReviewedMatchDetailsStatusEvaluationError(
                "fixture_identifier/source_match_id mismatch"
            )

        kickoff = _utc(self.kickoff, "kickoff")
        observed_at = _utc(self.observed_at, "observed_at")
        qualification_reviewed_at = _utc(
            self.qualification_reviewed_at,
            "qualification_reviewed_at",
        )
        policy_reviewed_at = _utc(self.policy_reviewed_at, "policy_reviewed_at")
        classified_at = _utc(self.classified_at, "classified_at")
        if observed_at >= kickoff:
            raise FotMobReviewedMatchDetailsStatusEvaluationError(
                "observed_at must remain strictly before kickoff"
            )
        if qualification_reviewed_at < observed_at or qualification_reviewed_at >= kickoff:
            raise FotMobReviewedMatchDetailsStatusEvaluationError(
                "qualification_reviewed_at chronology mismatch"
            )
        if policy_reviewed_at < qualification_reviewed_at or policy_reviewed_at >= kickoff:
            raise FotMobReviewedMatchDetailsStatusEvaluationError(
                "policy_reviewed_at chronology mismatch"
            )
        if classified_at < policy_reviewed_at or classified_at >= kickoff:
            raise FotMobReviewedMatchDetailsStatusEvaluationError(
                "classified_at must not precede policy review and must remain before kickoff"
            )

        raw_sha256 = _sha(self.raw_sha256, "raw_sha256")
        evidence_file_path = _text(self.evidence_file_path, "evidence_file_path", 1024)
        source_provider = _text(self.source_provider, "source_provider", 128)
        if self.source_role is not SourceRole.PRIMARY_FOOTBALL_CONTEXT:
            raise FotMobReviewedMatchDetailsStatusEvaluationError(
                "source_role must remain PRIMARY_FOOTBALL_CONTEXT"
            )

        if type(self.decisions) is not tuple or not self.decisions:
            raise FotMobReviewedMatchDetailsStatusEvaluationError(
                "decisions must be a non-empty immutable tuple"
            )
        if any(
            type(item) is not RecordedMatchDetailsStatusEvaluationDecision
            for item in self.decisions
        ):
            raise FotMobReviewedMatchDetailsStatusEvaluationError(
                "decisions must contain exact recorded evaluation values"
            )
        try:
            rebuilt_decisions = tuple(dataclasses.replace(item) for item in self.decisions)
        except (
            FotMobReviewedMatchDetailsStatusEvaluationError,
            AttributeError,
            TypeError,
            ValueError,
        ) as exc:
            raise FotMobReviewedMatchDetailsStatusEvaluationError(
                "nested evaluation decision failed invariant revalidation"
            ) from exc

        expected = tuple(sorted(rebuilt_decisions, key=lambda item: item.key))
        if rebuilt_decisions != expected:
            raise FotMobReviewedMatchDetailsStatusEvaluationError(
                "decisions must be deterministically sorted"
            )
        keys = tuple(item.key for item in rebuilt_decisions)
        if len(set(keys)) != len(keys):
            raise FotMobReviewedMatchDetailsStatusEvaluationError(
                "decisions must target unique exact facts"
            )
        fact_hashes = tuple(item.fact_sha256 for item in rebuilt_decisions)
        if len(set(fact_hashes)) != len(fact_hashes):
            raise FotMobReviewedMatchDetailsStatusEvaluationError(
                "recorded fact_sha256 values must be unique"
            )

        source_prefix = f"FOTMOB_MATCH_DETAILS:{source_match_id}:/"
        for item in rebuilt_decisions:
            if not item.source_reference.startswith(source_prefix):
                raise FotMobReviewedMatchDetailsStatusEvaluationError(
                    "recorded source_reference does not match exact source fixture"
                )
            if item.fresh_until is not None:
                try:
                    is_fresh = is_within_reviewed_freshness_window(
                        classified_at=classified_at,
                        observed_at=observed_at,
                        policy_reviewed_at=policy_reviewed_at,
                        fresh_until=item.fresh_until,
                        kickoff=kickoff,
                    )
                except FotMobReviewedMatchDetailsFreshnessComparisonError as exc:
                    raise FotMobReviewedMatchDetailsStatusEvaluationError(
                        "recorded freshness chronology failed exact PR #60 semantics"
                    ) from exc
                expected_disposition = (
                    StatusEvaluationDisposition.FRESH_QUALIFIED
                    if is_fresh
                    else StatusEvaluationDisposition.STALE_QUALIFIED
                )
                if item.evaluation_disposition is not expected_disposition:
                    raise FotMobReviewedMatchDetailsStatusEvaluationError(
                        "recorded evaluation disposition disagrees with exact PR #60 freshness semantics"
                    )

        safety = _validate_safety(self.safety)
        object.__setattr__(self, "fixture_identifier", fixture_identifier)
        object.__setattr__(self, "source_match_id", source_match_id)
        object.__setattr__(self, "kickoff", kickoff)
        object.__setattr__(self, "observed_at", observed_at)
        object.__setattr__(self, "qualification_reviewed_at", qualification_reviewed_at)
        object.__setattr__(self, "policy_reviewed_at", policy_reviewed_at)
        object.__setattr__(self, "classified_at", classified_at)
        object.__setattr__(self, "raw_sha256", raw_sha256)
        object.__setattr__(self, "evidence_file_path", evidence_file_path)
        object.__setattr__(self, "source_provider", source_provider)
        object.__setattr__(self, "decisions", rebuilt_decisions)
        object.__setattr__(self, "safety", safety)

    @property
    def fresh_qualified_count(self) -> int:
        return sum(
            item.evaluation_disposition is StatusEvaluationDisposition.FRESH_QUALIFIED
            for item in self.decisions
        )

    @property
    def stale_qualified_count(self) -> int:
        return sum(
            item.evaluation_disposition is StatusEvaluationDisposition.STALE_QUALIFIED
            for item in self.decisions
        )

    @property
    def blocked_count(self) -> int:
        return sum(
            item.evaluation_disposition
            is StatusEvaluationDisposition.BLOCKED_BY_QUALIFICATION
            for item in self.decisions
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "evaluation_scope": self.evaluation_scope,
            "freshness_comparison": self.freshness_comparison,
            "conflict_policy": self.conflict_policy,
            "policy_sha256": self.policy_sha256,
            "policy_size": self.policy_size,
            "fixture_identifier": self.fixture_identifier,
            "source_match_id": self.source_match_id,
            "kickoff": _iso(self.kickoff),
            "observed_at": _iso(self.observed_at),
            "qualification_reviewed_at": _iso(self.qualification_reviewed_at),
            "policy_reviewed_at": _iso(self.policy_reviewed_at),
            "classified_at": _iso(self.classified_at),
            "raw_sha256": self.raw_sha256,
            "evidence_file_path": self.evidence_file_path,
            "source_provider": self.source_provider,
            "source_role": self.source_role.value,
            "fresh_qualified_count": self.fresh_qualified_count,
            "stale_qualified_count": self.stale_qualified_count,
            "blocked_count": self.blocked_count,
            "decisions": [item.to_dict() for item in self.decisions],
            "safety": dict(self.safety),
        }


def _revalidate_policy(
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
) -> tuple[ReviewedMatchDetailsStatusClassificationPolicy, bytes]:
    if type(policy) is not ReviewedMatchDetailsStatusClassificationPolicy:
        raise FotMobReviewedMatchDetailsStatusEvaluationError(
            "policy must be exact PR #60 policy"
        )
    if type(policy_bytes) is not bytes:
        raise FotMobReviewedMatchDetailsStatusEvaluationError(
            "policy_bytes must be exact immutable bytes"
        )
    try:
        rebuilt = revalidate_reviewed_match_details_status_classification_policy(
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
            policy=policy,
            policy_bytes=policy_bytes,
        )
        exact_bytes = canonical_reviewed_match_details_status_classification_policy_bytes(
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
        raise FotMobReviewedMatchDetailsStatusEvaluationError(
            "PR #60 policy failed exact full-chain revalidation"
        ) from exc
    if exact_bytes != policy_bytes:
        raise FotMobReviewedMatchDetailsStatusEvaluationError(
            "policy_bytes differ from exact PR #60 full-chain rebuild"
        )
    return rebuilt, exact_bytes


def evaluate_reviewed_match_details_status_policy(
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
    classified_at: Any,
) -> ReviewedMatchDetailsStatusEvaluation:
    """Evaluate exact PR #60 policy without creating PR #30 statuses."""

    rebuilt_policy, exact_policy_bytes = _revalidate_policy(
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
        policy=policy,
        policy_bytes=policy_bytes,
    )
    classified_at = _utc(classified_at, "classified_at")
    if classified_at < rebuilt_policy.policy_reviewed_at or classified_at >= rebuilt_policy.kickoff:
        raise FotMobReviewedMatchDetailsStatusEvaluationError(
            "classified_at must not precede PR #60 policy review and must remain before kickoff"
        )

    recorded: list[RecordedMatchDetailsStatusEvaluationDecision] = []
    for item in rebuilt_policy.decisions:
        if (
            item.disposition
            is StatusClassificationPolicyDisposition.BLOCKED_BY_QUALIFICATION
        ):
            recorded.append(
                RecordedMatchDetailsStatusEvaluationDecision(
                    category=item.category,
                    field=item.field,
                    source_reference=item.source_reference,
                    fact_sha256=item.fact_sha256,
                    qualification_disposition=item.qualification_disposition,
                    policy_disposition=item.disposition,
                    evaluation_disposition=StatusEvaluationDisposition.BLOCKED_BY_QUALIFICATION,
                    fresh_until=None,
                    rationale=item.rationale,
                )
            )
            continue

        if item.fresh_until is None:
            raise FotMobReviewedMatchDetailsStatusEvaluationError(
                "eligible PR #60 policy decision is missing fresh_until"
            )
        try:
            is_fresh = is_within_reviewed_freshness_window(
                classified_at=classified_at,
                observed_at=rebuilt_policy.observed_at,
                policy_reviewed_at=rebuilt_policy.policy_reviewed_at,
                fresh_until=item.fresh_until,
                kickoff=rebuilt_policy.kickoff,
            )
        except FotMobReviewedMatchDetailsFreshnessComparisonError as exc:
            raise FotMobReviewedMatchDetailsStatusEvaluationError(
                "PR #60 freshness semantics rejected classification chronology"
            ) from exc
        recorded.append(
            RecordedMatchDetailsStatusEvaluationDecision(
                category=item.category,
                field=item.field,
                source_reference=item.source_reference,
                fact_sha256=item.fact_sha256,
                qualification_disposition=item.qualification_disposition,
                policy_disposition=item.disposition,
                evaluation_disposition=(
                    StatusEvaluationDisposition.FRESH_QUALIFIED
                    if is_fresh
                    else StatusEvaluationDisposition.STALE_QUALIFIED
                ),
                fresh_until=item.fresh_until,
                rationale=item.rationale,
            )
        )

    return ReviewedMatchDetailsStatusEvaluation(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        evaluation_scope=EVALUATION_SCOPE,
        freshness_comparison=FRESHNESS_COMPARISON,
        conflict_policy=CONFLICT_POLICY,
        policy_sha256=hashlib.sha256(exact_policy_bytes).hexdigest(),
        policy_size=len(exact_policy_bytes),
        fixture_identifier=rebuilt_policy.fixture_identifier,
        source_match_id=rebuilt_policy.source_match_id,
        kickoff=rebuilt_policy.kickoff,
        observed_at=rebuilt_policy.observed_at,
        qualification_reviewed_at=rebuilt_policy.qualification_reviewed_at,
        policy_reviewed_at=rebuilt_policy.policy_reviewed_at,
        classified_at=classified_at,
        raw_sha256=rebuilt_policy.raw_sha256,
        evidence_file_path=rebuilt_policy.evidence_file_path,
        source_provider=rebuilt_policy.source_provider,
        source_role=rebuilt_policy.source_role,
        decisions=tuple(recorded),
        safety=_default_safety(),
    )


def canonical_reviewed_match_details_status_evaluation_bytes(value: Any) -> bytes:
    if type(value) is not ReviewedMatchDetailsStatusEvaluation:
        raise FotMobReviewedMatchDetailsStatusEvaluationError(
            "value must be exact ReviewedMatchDetailsStatusEvaluation"
        )
    try:
        rebuilt = dataclasses.replace(value)
        return _canonical_json_bytes(rebuilt.to_dict())
    except FotMobReviewedMatchDetailsStatusEvaluationError:
        raise
    except (TypeError, ValueError, OverflowError, AttributeError) as exc:
        raise FotMobReviewedMatchDetailsStatusEvaluationError(
            "status evaluation canonicalization failed"
        ) from exc


def revalidate_reviewed_match_details_status_evaluation(
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
    evaluation: Any,
    evaluation_bytes: Any,
) -> ReviewedMatchDetailsStatusEvaluation:
    """Replay PR #52 -> PR #61 before consuming an evaluation artifact."""

    if type(evaluation) is not ReviewedMatchDetailsStatusEvaluation:
        raise FotMobReviewedMatchDetailsStatusEvaluationError(
            "evaluation must be exact ReviewedMatchDetailsStatusEvaluation"
        )
    if type(evaluation_bytes) is not bytes:
        raise FotMobReviewedMatchDetailsStatusEvaluationError(
            "evaluation_bytes must be exact immutable bytes"
        )
    try:
        supplied_bytes = canonical_reviewed_match_details_status_evaluation_bytes(
            evaluation
        )
        rebuilt = evaluate_reviewed_match_details_status_policy(
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
            policy=policy,
            policy_bytes=policy_bytes,
            classified_at=evaluation.classified_at,
        )
        rebuilt_bytes = canonical_reviewed_match_details_status_evaluation_bytes(rebuilt)
    except (
        FotMobReviewedMatchDetailsStatusEvaluationError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise FotMobReviewedMatchDetailsStatusEvaluationError(
            "PR #61 evaluation failed exact full-chain revalidation"
        ) from exc
    if supplied_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsStatusEvaluationError(
            "supplied PR #61 evaluation differs from exact full-chain rebuild"
        )
    if evaluation_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsStatusEvaluationError(
            "evaluation_bytes are not exact canonical PR #61 bytes"
        )
    return rebuilt


def sha256_reviewed_match_details_status_evaluation(value: Any) -> str:
    return hashlib.sha256(
        canonical_reviewed_match_details_status_evaluation_bytes(value)
    ).hexdigest()


__all__ = [
    "DATASET_NAME",
    "EVALUATION_SCOPE",
    "SCHEMA_VERSION",
    "FotMobReviewedMatchDetailsStatusEvaluationError",
    "RecordedMatchDetailsStatusEvaluationDecision",
    "ReviewedMatchDetailsStatusEvaluation",
    "StatusEvaluationDisposition",
    "canonical_reviewed_match_details_status_evaluation_bytes",
    "evaluate_reviewed_match_details_status_policy",
    "revalidate_reviewed_match_details_status_evaluation",
    "sha256_reviewed_match_details_status_evaluation",
]
