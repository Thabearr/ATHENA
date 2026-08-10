"""Frozen time-comparison semantics for PR #60 freshness policy.

This module answers only whether an explicit classification timestamp is inside
an exact reviewed freshness window. It does not create or mutate any Fixture
Intelligence status.
"""

from __future__ import annotations

import datetime
from typing import Any

FRESHNESS_COMPARISON = "CLASSIFIED_AT_LE_FRESH_UNTIL"


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
    fresh_until: Any,
    kickoff: Any,
) -> bool:
    """Return True exactly when ``classified_at <= fresh_until``.

    All timestamps must be exact UTC and prospective for the same observation.
    Equality at ``fresh_until`` is intentionally fresh; one microsecond later
    is stale for a later evaluator. This function itself emits no status.
    """

    classified = _utc(classified_at, "classified_at")
    observed = _utc(observed_at, "observed_at")
    deadline = _utc(fresh_until, "fresh_until")
    fixture_kickoff = _utc(kickoff, "kickoff")

    if observed >= fixture_kickoff:
        raise FotMobReviewedMatchDetailsFreshnessComparisonError(
            "observed_at must remain strictly before kickoff"
        )
    if deadline < observed or deadline >= fixture_kickoff:
        raise FotMobReviewedMatchDetailsFreshnessComparisonError(
            "fresh_until must not precede observation and must remain before kickoff"
        )
    if classified < observed or classified >= fixture_kickoff:
        raise FotMobReviewedMatchDetailsFreshnessComparisonError(
            "classified_at must not precede observation and must remain before kickoff"
        )

    return classified <= deadline


__all__ = [
    "FRESHNESS_COMPARISON",
    "FotMobReviewedMatchDetailsFreshnessComparisonError",
    "is_within_reviewed_freshness_window",
]
