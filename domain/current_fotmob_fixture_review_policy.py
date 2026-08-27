"""Reviewed policy issuer for current FotMob fixture-identity decisions.

This boundary is intentionally narrower than the historical PR #41 human-review
contract.  PR #41 remains unchanged and continues to reject automatic promotion
on its own.  This module is a separately reviewed policy issuer which may create
individual PR #41 APPROVED decisions only when the exact current candidate:

* belongs to an already-reviewed exact FotMob source competition identity;
* is not blocked by PR #41's own conflict/string checks;
* was observed no later than the policy evaluation time; and
* remains sufficiently prospective for the configured minimum lead window.

The result grants only source-scoped fixture identity review.  It does not grant
team/competition global identity, Fixture Intelligence facts, model, pricing,
selection, SportyBet, or BET authority.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import types
from collections.abc import Mapping
from typing import Any

from config.competition_review_priority import (
    COMPETITION_REVIEW_PRIORITY_POLICY_VERSION,
    resolve_source_competition_review_priority,
)
from domain.fotmob_fixture_candidate_review import (
    FixtureCandidateReviewDisposition,
    FotMobFixtureCandidateReviewBundle,
    FotMobFixtureCandidateReviewDecision,
    FotMobFixtureCandidateReviewError,
    build_fotmob_fixture_candidate_review_bundle,
    canonical_fotmob_fixture_candidate_review_bundle_bytes,
    sha256_fotmob_fixture_candidate,
)
from domain.fotmob_fixture_candidates import (
    FotMobFixtureCandidateBundle,
    sha256_fotmob_fixture_candidate_bundle,
)


SCHEMA_VERSION = 1
DATASET_NAME = "athena-current-fotmob-fixture-review-policy-v1"
POLICY_ID = "ATHENA_PR243_CURRENT_FOTMOB_FIXTURE_IDENTITY_POLICY_V1"
REVIEWER_REFERENCE = "athena-policy:pr243-current-fotmob-fixture-identity-v1"
DEFAULT_MINIMUM_LEAD_SECONDS = 60 * 60

_SAFETY_KEYS = frozenset(
    {
        "global_team_identity_authorized",
        "global_competition_identity_authorized",
        "fixture_intelligence_fact_authorized",
        "fixture_intelligence_snapshot_authorized",
        "model_feature_authorized",
        "probability_authorized",
        "pricing_authorized",
        "selection_authorized",
        "sportybet_execution_authorized",
        "bet_authorized",
    }
)


class CurrentFotMobFixtureReviewPolicyError(ValueError):
    """Raised when the reviewed current fixture policy cannot fail closed."""


def _utc(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, dt.datetime):
        raise CurrentFotMobFixtureReviewPolicyError(f"{label} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise CurrentFotMobFixtureReviewPolicyError(
            f"{label} must be timezone-aware"
        )
    try:
        return value.astimezone(dt.timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CurrentFotMobFixtureReviewPolicyError(f"{label} is invalid") from exc


def _minimum_lead(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise CurrentFotMobFixtureReviewPolicyError(
            "minimum_lead_seconds must be an exact non-negative integer"
        )
    return value


def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise CurrentFotMobFixtureReviewPolicyError("safety keys mismatch")
    if any(type(item) is not bool or item is not False for item in value.values()):
        raise CurrentFotMobFixtureReviewPolicyError(
            "all downstream safety flags must remain exact false"
        )
    return _safety()


@dataclasses.dataclass(frozen=True)
class CurrentFotMobFixtureReviewPolicyResult:
    schema_version: int
    dataset_name: str
    policy_id: str
    competition_policy_version: str
    candidate_bundle_sha256: str
    reviewed_at: dt.datetime
    minimum_lead_seconds: int
    candidate_count: int
    exact_competition_identity_count: int
    pr41_blocked_count: int
    lead_window_excluded_count: int
    policy_approved_count: int
    review_bundle: FotMobFixtureCandidateReviewBundle
    review_bundle_sha256: str
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise CurrentFotMobFixtureReviewPolicyError("schema_version mismatch")
        if self.dataset_name != DATASET_NAME:
            raise CurrentFotMobFixtureReviewPolicyError("dataset_name mismatch")
        if self.policy_id != POLICY_ID:
            raise CurrentFotMobFixtureReviewPolicyError("policy_id mismatch")
        if self.competition_policy_version != COMPETITION_REVIEW_PRIORITY_POLICY_VERSION:
            raise CurrentFotMobFixtureReviewPolicyError(
                "competition policy version mismatch"
            )
        if (
            type(self.candidate_bundle_sha256) is not str
            or len(self.candidate_bundle_sha256) != 64
            or any(ch not in "0123456789abcdef" for ch in self.candidate_bundle_sha256)
        ):
            raise CurrentFotMobFixtureReviewPolicyError(
                "candidate_bundle_sha256 must be exact SHA-256"
            )
        reviewed_at = _utc(self.reviewed_at, "reviewed_at")
        minimum_lead = _minimum_lead(self.minimum_lead_seconds)
        for label in (
            "candidate_count",
            "exact_competition_identity_count",
            "pr41_blocked_count",
            "lead_window_excluded_count",
            "policy_approved_count",
        ):
            value = getattr(self, label)
            if type(value) is not int or value < 0:
                raise CurrentFotMobFixtureReviewPolicyError(
                    f"{label} must be exact non-negative integer"
                )
        if type(self.review_bundle) is not FotMobFixtureCandidateReviewBundle:
            raise CurrentFotMobFixtureReviewPolicyError(
                "review_bundle must be exact FotMobFixtureCandidateReviewBundle"
            )
        if self.review_bundle.candidate_bundle_sha256 != self.candidate_bundle_sha256:
            raise CurrentFotMobFixtureReviewPolicyError(
                "review bundle does not anchor candidate bundle"
            )
        exact_review_bytes = canonical_fotmob_fixture_candidate_review_bundle_bytes(
            self.review_bundle
        )
        expected_review_sha = hashlib.sha256(exact_review_bytes).hexdigest()
        if self.review_bundle_sha256 != expected_review_sha:
            raise CurrentFotMobFixtureReviewPolicyError(
                "review_bundle_sha256 mismatch"
            )
        if self.candidate_count != self.review_bundle.candidate_count:
            raise CurrentFotMobFixtureReviewPolicyError("candidate_count mismatch")
        if self.policy_approved_count != self.review_bundle.approved_count:
            raise CurrentFotMobFixtureReviewPolicyError(
                "policy_approved_count mismatch"
            )
        if self.review_bundle.rejected_count != 0:
            raise CurrentFotMobFixtureReviewPolicyError(
                "current policy must never manufacture REJECTED decisions"
            )
        if any(item.reviewer_reference != REVIEWER_REFERENCE for item in self.review_bundle.decisions):
            raise CurrentFotMobFixtureReviewPolicyError(
                "review bundle contains non-policy reviewer authority"
            )
        object.__setattr__(self, "reviewed_at", reviewed_at)
        object.__setattr__(self, "minimum_lead_seconds", minimum_lead)
        object.__setattr__(self, "safety", _validate_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "policy_id": self.policy_id,
            "competition_policy_version": self.competition_policy_version,
            "candidate_bundle_sha256": self.candidate_bundle_sha256,
            "reviewed_at": self.reviewed_at.isoformat().replace("+00:00", "Z"),
            "minimum_lead_seconds": self.minimum_lead_seconds,
            "candidate_count": self.candidate_count,
            "exact_competition_identity_count": self.exact_competition_identity_count,
            "pr41_blocked_count": self.pr41_blocked_count,
            "lead_window_excluded_count": self.lead_window_excluded_count,
            "policy_approved_count": self.policy_approved_count,
            "review_bundle_sha256": self.review_bundle_sha256,
            "review_bundle": self.review_bundle.to_dict(),
            "safety": dict(self.safety),
        }


def build_current_fotmob_fixture_review_policy_result(
    candidate_bundle: Any,
    *,
    reviewed_at: Any,
    minimum_lead_seconds: int = DEFAULT_MINIMUM_LEAD_SECONDS,
) -> CurrentFotMobFixtureReviewPolicyResult:
    """Issue exact PR #41 decisions under the separately reviewed PR243 policy."""

    if type(candidate_bundle) is not FotMobFixtureCandidateBundle:
        raise CurrentFotMobFixtureReviewPolicyError(
            "candidate_bundle must be exact FotMobFixtureCandidateBundle"
        )
    reviewed = _utc(reviewed_at, "reviewed_at")
    minimum_lead = _minimum_lead(minimum_lead_seconds)

    try:
        baseline = build_fotmob_fixture_candidate_review_bundle(candidate_bundle, ())
    except FotMobFixtureCandidateReviewError as exc:
        raise CurrentFotMobFixtureReviewPolicyError(
            "PR41 baseline blocker derivation failed"
        ) from exc
    blocked_keys = {item.candidate_key for item in baseline.blocked_candidates}

    exact_competition_count = 0
    blocked_count = 0
    lead_excluded = 0
    decisions: list[FotMobFixtureCandidateReviewDecision] = []
    lead_floor = reviewed + dt.timedelta(seconds=minimum_lead)

    for candidate in candidate_bundle.candidates:
        if candidate.source_observed_at > reviewed:
            raise CurrentFotMobFixtureReviewPolicyError(
                "candidate source observation is after policy reviewed_at"
            )
        priority = resolve_source_competition_review_priority(
            candidate.source_competition_ccode,
            candidate.source_competition_name,
        )
        if priority is None:
            continue
        exact_competition_count += 1
        candidate_sha = sha256_fotmob_fixture_candidate(candidate)
        candidate_key = (
            candidate.source_capture_manifest_sha256,
            candidate.source_match_id,
            candidate_sha,
        )
        if candidate_key in blocked_keys:
            blocked_count += 1
            continue
        if candidate.kickoff_utc < lead_floor:
            lead_excluded += 1
            continue
        decisions.append(
            FotMobFixtureCandidateReviewDecision(
                source_capture_manifest_sha256=candidate.source_capture_manifest_sha256,
                source_match_id=candidate.source_match_id,
                candidate_sha256=candidate_sha,
                disposition=FixtureCandidateReviewDisposition.APPROVED,
                reviewed_at=reviewed,
                reviewer_reference=REVIEWER_REFERENCE,
                notes=(
                    f"{POLICY_ID}; exact reviewed source competition "
                    f"{candidate.source_competition_ccode}:{candidate.source_competition_name}; "
                    f"canonical={priority.canonical_name}; rank={priority.rank}; "
                    f"minimum_lead_seconds={minimum_lead}"
                ),
            )
        )

    try:
        review_bundle = build_fotmob_fixture_candidate_review_bundle(
            candidate_bundle,
            tuple(decisions),
        )
    except FotMobFixtureCandidateReviewError as exc:
        raise CurrentFotMobFixtureReviewPolicyError(
            "policy decisions failed exact PR41 revalidation"
        ) from exc
    review_bytes = canonical_fotmob_fixture_candidate_review_bundle_bytes(review_bundle)
    return CurrentFotMobFixtureReviewPolicyResult(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        policy_id=POLICY_ID,
        competition_policy_version=COMPETITION_REVIEW_PRIORITY_POLICY_VERSION,
        candidate_bundle_sha256=sha256_fotmob_fixture_candidate_bundle(candidate_bundle),
        reviewed_at=reviewed,
        minimum_lead_seconds=minimum_lead,
        candidate_count=candidate_bundle.candidate_count,
        exact_competition_identity_count=exact_competition_count,
        pr41_blocked_count=blocked_count,
        lead_window_excluded_count=lead_excluded,
        policy_approved_count=review_bundle.approved_count,
        review_bundle=review_bundle,
        review_bundle_sha256=hashlib.sha256(review_bytes).hexdigest(),
        safety=_safety(),
    )


def canonical_current_fotmob_fixture_review_policy_result_bytes(value: Any) -> bytes:
    if type(value) is not CurrentFotMobFixtureReviewPolicyResult:
        raise CurrentFotMobFixtureReviewPolicyError(
            "value must be exact CurrentFotMobFixtureReviewPolicyResult"
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
        raise CurrentFotMobFixtureReviewPolicyError(
            "policy result serialization failed"
        ) from exc


__all__ = [
    "DATASET_NAME",
    "DEFAULT_MINIMUM_LEAD_SECONDS",
    "POLICY_ID",
    "REVIEWER_REFERENCE",
    "SCHEMA_VERSION",
    "CurrentFotMobFixtureReviewPolicyError",
    "CurrentFotMobFixtureReviewPolicyResult",
    "build_current_fotmob_fixture_review_policy_result",
    "canonical_current_fotmob_fixture_review_policy_result_bytes",
]
