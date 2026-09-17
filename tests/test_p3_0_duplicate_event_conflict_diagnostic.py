from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import pytest

from domain import sportybet_current_event_discovery_reconciliation as reviewed
from scripts import p3_0_duplicate_event_conflict_diagnostic as diagnostic


UTC = timezone.utc
OBSERVED = datetime(2026, 9, 17, 17, 56, 20, tzinfo=UTC)
EVENT_ID = "sr:match:111111113759449"


def _event(
    *,
    away_team_name: str = "Away",
    raw_sha256: str = "a" * 64,
    observed_at: datetime = OBSERVED,
):
    return reviewed.SportyBetDiscoveredEvent(
        event_id=EVENT_ID,
        home_team_name="Home",
        away_team_name=away_team_name,
        competition_name="Reviewed League",
        competition_basis="EVENT_TOURNAMENT_NAME",
        kickoff_utc=datetime(2026, 9, 18, 18, 0, tzinfo=UTC),
        booking_status="Open",
        event_status=0,
        match_status="Not started",
        prematch_bookable_observed=True,
        source_page_num=1,
        source_raw_sha256=raw_sha256,
        source_observed_at=observed_at,
    )


def _diagnostic_payload(message: str):
    prefix = f"conflicting duplicate provider event identity: {EVENT_ID}; diagnostic="
    assert message.startswith(prefix)
    return json.loads(message.removeprefix(prefix))


def test_diagnostic_policy_is_pinned_to_the_failed_p3_capture():
    assert diagnostic.DIAGNOSTIC_POLICY_ID == (
        "ATHENA_P3_0_E1_CONFLICTING_PROVIDER_EVENT_IDENTITY_DIAGNOSTIC_V1"
    )
    assert diagnostic.DIAGNOSTIC_SOURCE_WORKFLOW_RUN_ID == 35255630033
    assert diagnostic.DIAGNOSTIC_SOURCE_ARTIFACT_ID == 10512920633
    assert diagnostic.DIAGNOSTIC_SOURCE_ARTIFACT_SHA256 == (
        "e95b2befcdc7ff4e5ff2fcc20ee15718028119fd37a1a8d63eb4f0df509a9869"
    )


def test_conflicting_duplicate_is_still_rejected_with_bounded_exact_field_diagnostic():
    first = _event()
    second = _event(
        away_team_name="Different Away",
        raw_sha256="b" * 64,
        observed_at=OBSERVED + timedelta(seconds=1),
    )
    original = reviewed._dedupe_events

    with diagnostic.scoped_duplicate_conflict_diagnostic():
        assert reviewed._dedupe_events is not original
        with pytest.raises(reviewed.SportyBetCurrentEventDiscoveryError) as caught:
            reviewed._dedupe_events((first, second))

    assert reviewed._dedupe_events is original
    message = str(caught.value)
    assert len(message) <= diagnostic.DIAGNOSTIC_MESSAGE_MAX_CHARS
    payload = _diagnostic_payload(message)
    assert payload["event_id"] == EVENT_ID
    assert payload["differing_fields"] == ["away_team_name"]
    assert payload["differences"] == {
        "away_team_name": ["Away", "Different Away"]
    }
    assert payload["first_source_raw_sha256"] == "a" * 64
    assert payload["second_source_raw_sha256"] == "b" * 64
    assert payload["first_source_observed_at"] == "2026-09-17T17:56:20.000000Z"
    assert payload["second_source_observed_at"] == "2026-09-17T17:56:21.000000Z"
    assert len(payload["first_identity_sha256"]) == 64
    assert len(payload["second_identity_sha256"]) == 64
    assert payload["first_identity_sha256"] != payload["second_identity_sha256"]


def test_exact_duplicate_semantics_are_unchanged_and_newest_source_is_retained():
    first = _event()
    second = _event(
        raw_sha256="b" * 64,
        observed_at=OBSERVED + timedelta(seconds=1),
    )

    with diagnostic.scoped_duplicate_conflict_diagnostic():
        result = reviewed._dedupe_events((first, second))

    assert result == (second,)


def test_large_conflicting_values_fall_back_without_truncating_the_json_diagnostic():
    first = _event(away_team_name="A" * 300)
    second = _event(
        away_team_name="B" * 300,
        raw_sha256="b" * 64,
        observed_at=OBSERVED + timedelta(seconds=1),
    )

    with diagnostic.scoped_duplicate_conflict_diagnostic():
        with pytest.raises(reviewed.SportyBetCurrentEventDiscoveryError) as caught:
            reviewed._dedupe_events((first, second))

    message = str(caught.value)
    assert len(message) <= diagnostic.DIAGNOSTIC_MESSAGE_MAX_CHARS
    payload = _diagnostic_payload(message)
    assert payload["event_id"] == EVENT_ID
    assert payload["differing_fields"] == ["away_team_name"]
    assert "differences" not in payload
    assert len(payload["first_identity_sha256"]) == 64
    assert len(payload["second_identity_sha256"]) == 64


def test_unscoped_reviewed_duplicate_error_remains_unmodified():
    first = _event()
    second = _event(
        away_team_name="Different Away",
        raw_sha256="b" * 64,
        observed_at=OBSERVED + timedelta(seconds=1),
    )

    with pytest.raises(
        reviewed.SportyBetCurrentEventDiscoveryError,
        match=f"conflicting duplicate provider event identity: {EVENT_ID}$",
    ):
        reviewed._dedupe_events((first, second))
