"""Frozen time-comparison semantics for PR #60 freshness policy.

This module answers only whether an explicit classification timestamp is inside
an exact reviewed freshness window. It does not create or mutate any Fixture
Intelligence status.
"""

from __future__ import annotations

import datetime
from typing import Any

FRESHNESS_COMPARISON = "POLICY_REVIEWED_AT_LE_CLASSIFIED_AT_LE_FRESH_UNTIL"


class FotMobReviewedMatchDetailsFreshnessComparisonError(ValueError):
    """Raised when exact PR #60 time-comparison semantics cannot be applied."""


def _utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise FotMobReviewedMatchDetailsFreshnessComparisonError(
            f"{label} must be a datetime"
        )
    if value.tzinfo is not datetime.timezone.utc:
        raise FotMobReviewedMatchDetailsFreshnessComparisonError(
            f"{label} must already use exact datetime.timezone.utc"
        )
    return value


def is_within_reviewed_freshness_window(
    *,
    classified_at: Any,
    observed_at: Any,
    policy_reviewed_at: Any,
    fresh_until: Any,
    kickoff: Any,
) -> bool:
    """Return True exactly when policy time <= classification <= deadline.

    All timestamps must be exact UTC and prospective for the same observation.
    Equality at ``fresh_until`` is intentionally fresh; one microsecond later
    is stale for a later evaluator. Classification before the reviewed policy
    exists fails closed. This function itself emits no status.
    """

    classified = _utc(classified_at, "classified_at")
    observed = _utc(observed_at, "observed_at")
    policy_reviewed = _utc(policy_reviewed_at, "policy_reviewed_at")
    deadline = _utc(fresh_until, "fresh_until")
    fixture_kickoff = _utc(kickoff, "kickoff")

    if observed >= fixture_kickoff:
        raise FotMobReviewedMatchDetailsFreshnessComparisonError(
            "observed_at must remain strictly before kickoff"
        )
    if policy_reviewed < observed or policy_reviewed >= fixture_kickoff:
        raise FotMobReviewedMatchDetailsFreshnessComparisonError(
            "policy_reviewed_at must not precede observation and must remain before kickoff"
        )
    if deadline < observed or deadline >= fixture_kickoff:
        raise FotMobReviewedMatchDetailsFreshnessComparisonError(
            "fresh_until must not precede observation and must remain before kickoff"
        )
    if classified < policy_reviewed or classified >= fixture_kickoff:
        raise FotMobReviewedMatchDetailsFreshnessComparisonError(
            "classified_at must not precede policy review and must remain before kickoff"
        )

    return classified <= deadline


__all__ = [
    "FRESHNESS_COMPARISON",
    "FotMobReviewedMatchDetailsFreshnessComparisonError",
    "is_within_reviewed_freshness_window",
]
