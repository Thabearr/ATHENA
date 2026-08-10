from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from domain.fotmob_reviewed_match_details_status_classification_policy_semantics import (
    FRESHNESS_COMPARISON,
    FotMobReviewedMatchDetailsFreshnessComparisonError,
    is_within_reviewed_freshness_window,
)


UTC = datetime.timezone.utc


def _times():
    observed = datetime.datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
    deadline = datetime.datetime(2026, 8, 10, 14, 0, tzinfo=UTC)
    kickoff = datetime.datetime(2026, 8, 10, 15, 0, tzinfo=UTC)
    return observed, deadline, kickoff


def test_freshness_deadline_is_inclusive_and_one_microsecond_later_is_not() -> None:
    observed, deadline, kickoff = _times()

    assert FRESHNESS_COMPARISON == "CLASSIFIED_AT_LE_FRESH_UNTIL"
    assert is_within_reviewed_freshness_window(
        classified_at=deadline,
        observed_at=observed,
        fresh_until=deadline,
        kickoff=kickoff,
    ) is True
    assert is_within_reviewed_freshness_window(
        classified_at=deadline + datetime.timedelta(microseconds=1),
        observed_at=observed,
        fresh_until=deadline,
        kickoff=kickoff,
    ) is False


def test_classification_before_observation_or_at_after_kickoff_fails_closed() -> None:
    observed, deadline, kickoff = _times()

    for invalid in (
        observed - datetime.timedelta(microseconds=1),
        kickoff,
        kickoff + datetime.timedelta(microseconds=1),
    ):
        with pytest.raises(
            FotMobReviewedMatchDetailsFreshnessComparisonError,
            match="classified_at",
        ):
            is_within_reviewed_freshness_window(
                classified_at=invalid,
                observed_at=observed,
                fresh_until=deadline,
                kickoff=kickoff,
            )


def test_invalid_deadline_or_observation_chronology_fails_closed() -> None:
    observed, _, kickoff = _times()

    for invalid_deadline in (
        observed - datetime.timedelta(microseconds=1),
        kickoff,
        kickoff + datetime.timedelta(microseconds=1),
    ):
        with pytest.raises(
            FotMobReviewedMatchDetailsFreshnessComparisonError,
            match="fresh_until",
        ):
            is_within_reviewed_freshness_window(
                classified_at=observed,
                observed_at=observed,
                fresh_until=invalid_deadline,
                kickoff=kickoff,
            )

    with pytest.raises(
        FotMobReviewedMatchDetailsFreshnessComparisonError,
        match="observed_at",
    ):
        is_within_reviewed_freshness_window(
            classified_at=kickoff,
            observed_at=kickoff,
            fresh_until=kickoff,
            kickoff=kickoff,
        )


def test_all_timestamps_require_exact_datetime_timezone_utc() -> None:
    observed, deadline, kickoff = _times()
    plus_one = datetime.timezone(datetime.timedelta(hours=1))

    with pytest.raises(
        FotMobReviewedMatchDetailsFreshnessComparisonError,
        match="exact datetime.timezone.utc",
    ):
        is_within_reviewed_freshness_window(
            classified_at=deadline.replace(tzinfo=plus_one),
            observed_at=observed,
            fresh_until=deadline,
            kickoff=kickoff,
        )


def test_semantics_module_has_no_status_fact_snapshot_or_network_side_effects() -> None:
    module_path = (
        Path(__file__).parents[1]
        / "domain"
        / "fotmob_reviewed_match_details_status_classification_policy_semantics.py"
    )
    source = module_path.read_text(encoding="utf-8")

    forbidden = (
        "FixtureIntelligenceFact",
        "IntelligenceFactStatus",
        "SOURCE_CAPABILITY_REGISTRY",
        "build_snapshot",
        "requests.",
        "httpx.",
        "aiohttp.",
        "socket.",
    )
    for token in forbidden:
        assert token not in source
