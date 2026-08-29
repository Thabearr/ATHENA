from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from domain import current_sportybet_semantic_registry as registry
from domain import sportybet_current_event_discovery_reconciliation as discovery


NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


def _event(
    event_id: str = "sr:match:99999999",
    *,
    observed_at: datetime = NOW,
    page_num: int = 1,
    raw_sha: str = "a" * 64,
    home_team_name: str = "Synthetic Home",
    away_team_name: str = "Synthetic Away",
    competition_name: str = "Synthetic League",
    kickoff_utc: datetime | None = None,
    booking_status: str = "Available",
    event_status: int = 0,
    match_status: str = "Not Started",
    prematch_bookable_observed: bool = True,
) -> discovery.SportyBetDiscoveredEvent:
    return discovery.SportyBetDiscoveredEvent(
        event_id=event_id,
        home_team_name=home_team_name,
        away_team_name=away_team_name,
        competition_name=competition_name,
        competition_basis="EVENT_LEAGUE_NAME",
        kickoff_utc=kickoff_utc or (NOW + timedelta(hours=2)),
        booking_status=booking_status,
        event_status=event_status,
        match_status=match_status,
        prematch_bookable_observed=prematch_bookable_observed,
        source_page_num=page_num,
        source_raw_sha256=raw_sha,
        source_observed_at=observed_at,
    )


def test_bounded_discovery_uses_newest_lifecycle_state_for_same_fixture() -> None:
    older = _event()
    newer = replace(
        older,
        booking_status="Unavailable",
        event_status=1,
        match_status="Live",
        prematch_bookable_observed=False,
        source_page_num=2,
        source_raw_sha256="b" * 64,
        source_observed_at=NOW + timedelta(seconds=1),
    )

    assert registry._dedupe_bounded_discovery_events((older, newer)) == (newer,)
    assert registry._dedupe_bounded_discovery_events((newer, older)) == (newer,)


def test_bounded_discovery_fails_closed_on_stable_fixture_conflict() -> None:
    first = _event()
    conflicting = replace(
        first,
        home_team_name="Different Home",
        source_page_num=2,
        source_raw_sha256="b" * 64,
        source_observed_at=NOW + timedelta(seconds=1),
    )

    with pytest.raises(
        registry.CurrentSportyBetSemanticRegistryError,
        match="conflicting bounded discovery fixture identity",
    ):
        registry._dedupe_bounded_discovery_events((first, conflicting))


def test_bounded_discovery_same_timestamp_state_collision_is_ambiguous() -> None:
    first = _event()
    collision = replace(
        first,
        booking_status="Unavailable",
        prematch_bookable_observed=False,
        source_page_num=2,
        source_raw_sha256="b" * 64,
    )

    with pytest.raises(
        registry.CurrentSportyBetSemanticRegistryError,
        match="ambiguous bounded discovery state collision",
    ):
        registry._dedupe_bounded_discovery_events((first, collision))


def test_bounded_discovery_exact_duplicate_same_timestamp_is_safe() -> None:
    first = _event()
    duplicate = replace(
        first,
        source_page_num=2,
        source_raw_sha256="b" * 64,
    )

    rows = registry._dedupe_bounded_discovery_events((first, duplicate))
    assert len(rows) == 1
    assert rows[0].identity_payload == first.identity_payload


def test_bounded_discovery_output_is_sorted_by_event_id() -> None:
    later_id = _event("sr:match:99999999")
    earlier_id = _event("sr:match:99999998", raw_sha="b" * 64)

    rows = registry._dedupe_bounded_discovery_events((later_id, earlier_id))
    assert tuple(item.event_id for item in rows) == (
        "sr:match:99999998",
        "sr:match:99999999",
    )
