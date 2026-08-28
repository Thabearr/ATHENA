from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from domain import fotmob_fixture_catalog_handoff as handoff_module
from domain import sportybet_current_event_discovery as discovery
from domain import sportybet_live_event_quote_evidence as live_event
from domain._sportybet_current_event_discovery_contracts import (
    DIRECT_EVENT_CONTRACT_SHA256,
    EXPECTED_CONTRACT_SHA256,
    FOTMOB_HANDOFF_DATASET_NAME,
    FOTMOB_HANDOFF_SCHEMA_VERSION,
    NEXT_BOUNDARY,
    calculate_current_event_discovery_contract_sha256,
    validate_current_event_discovery_contract,
)
from domain.fotmob_fixture_candidate_review import (
    build_fotmob_fixture_candidate_review_bundle,
)
from tests import test_fotmob_fixture_catalog_handoff as handoff_helpers

UTC = timezone.utc
OBSERVED = datetime(2026, 8, 15, 10, 0, tzinfo=UTC)
KICKOFF = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


def _event(
    *,
    event_id: str = "sr:match:123",
    home: str = "Home FC",
    away: str = "Away FC",
    kickoff: datetime = KICKOFF,
    booking_status: str = "Available",
    status=0,
    match_status: str = "Not Started",
    competition_name: str | None = None,
):
    row = {
        "eventId": event_id,
        "sportId": "sr:sport:1",
        "homeTeamName": home,
        "awayTeamName": away,
        "estimateStartTime": int(kickoff.timestamp() * 1000),
        "bookingStatus": booking_status,
        "status": status,
        "matchStatus": match_status,
    }
    if competition_name is not None:
        row["tournamentName"] = competition_name
    return row


def _raw(
    events,
    *,
    competition: str | None = "League Ω",
    tournament_id: str = "sr:tournament:10",
    grouped: bool = True,
):
    event_rows = list(events)
    if grouped:
        tournament = {"id": tournament_id, "events": event_rows}
        if competition is not None:
            tournament["name"] = competition
        data = {"tournaments": [tournament]}
    else:
        data = event_rows
    return (
        json.dumps(
            {"bizCode": 10000, "data": data},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _single_handoff():
    bundle, review, _candidate = handoff_helpers._approved_single()
    return handoff_module.build_fotmob_fixture_catalog_handoff(bundle, review)


def _multi_handoff_same_identity():
    source = handoff_helpers._source(count=2)
    first = handoff_helpers._candidate(source, match_id=1001)
    second = handoff_helpers._candidate(source, match_id=1002)
    bundle = handoff_helpers._bundle((source,), (first, second))
    review = build_fotmob_fixture_candidate_review_bundle(
        bundle,
        (
            handoff_helpers._decision(first, minute=30),
            handoff_helpers._decision(second, minute=31),
        ),
    )
    return handoff_module.build_fotmob_fixture_catalog_handoff(bundle, review)


def _capture(monkeypatch, tmp_path: Path, raw: bytes, *, observed_at=OBSERVED):
    monkeypatch.setattr(
        discovery,
        "_network_fetch",
        lambda: (raw, 200, observed_at),
    )
    return discovery.capture_current_event_evidence(
        repository_root=tmp_path,
        execute_live_network=True,
    )


def _live(monkeypatch, tmp_path: Path, raw: bytes, handoff=None, *, now=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    handoff = handoff or _single_handoff()
    monkeypatch.setattr(
        discovery,
        "_network_fetch",
        lambda: (raw, 200, OBSERVED),
    )
    monkeypatch.setattr(
        discovery,
        "_now_utc",
        lambda: now or (OBSERVED + timedelta(seconds=5)),
    )
    return discovery.capture_and_reconcile_current_events(
        repository_root=tmp_path,
        fotmob_catalog_handoff=handoff,
        execute_live_network=True,
    )


def test_contract_pins_direct_event_and_fotmob_handoff_identities():
    identities = validate_current_event_discovery_contract()
    assert DIRECT_EVENT_CONTRACT_SHA256 == live_event.EXPECTED_CONTRACT_SHA256
    assert identities["direct_event_contract_sha256"] == (
        "b888cebab6447cd4072d823dab67b56f1f75f72eb72d67b692d47a4378b27555"
    )
    assert FOTMOB_HANDOFF_DATASET_NAME == "athena-fotmob-fixture-catalog-handoff-v1"
    assert FOTMOB_HANDOFF_SCHEMA_VERSION == 1
    assert calculate_current_event_discovery_contract_sha256() == EXPECTED_CONTRACT_SHA256


def test_request_is_exact_anonymous_football_sport_scope():
    assert discovery.request_target() == (
        "/api/ng/factsCenter/wapConfigurableUpcomingEvents?sportId=sr%3Asport%3A1"
    )
    assert "_t=" not in discovery.request_target()
    headers = dict(discovery.REQUEST_HEADERS)
    assert headers["OperId"] == "2"
    assert "Cookie" not in headers and "Authorization" not in headers


def test_live_discovery_reconciles_one_exact_current_event_and_preserves_provenance(
    monkeypatch, tmp_path
):
    result = _live(monkeypatch, tmp_path, _raw([_event()]))
    assert result.status == discovery.LIVE_STATUS
    assert result.proof_mode == discovery.LIVE_PROOF_MODE
    assert result.observation_age_seconds == pytest.approx(5.0)
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.disposition is (
        discovery.CurrentEventReconciliationDisposition.UNIQUE_EXACT_MATCH_RECONCILED
    )
    assert row.fixture_reconciliation_authorized is True
    assert row.matched_fotmob_fixture_id == "1001"
    assert row.home_team_name == "Home FC"
    assert row.away_team_name == "Away FC"
    assert row.competition_name == "League Ω"
    assert row.kickoff_utc == KICKOFF
    assert result.authority["current_event_discovery"] is True
    assert result.authority["fixture_reconciliation"] is True
    assert result.authority["canonical_market_mapping"] is False
    assert result.authority["price_all"] is False
    assert result.authority["market_router"] is False
    assert result.authority["portfolio_optimization"] is False
    assert result.authority["sportybet_execution"] is False
    assert result.authority["bet"] is False
    assert result.next_boundary == NEXT_BOUNDARY
    assert result.to_dict()["wager_placed"] is False
    assert len(result.source_raw_sha256) == 64
    assert len(result.source_manifest_sha256) == 64
    assert len(result.source_inventory_sha256) == 64
    assert len(result.fotmob_handoff_sha256) == 64


def test_response_completion_time_is_not_relabelled_as_provider_timestamp(monkeypatch, tmp_path):
    directory, manifest = _capture(monkeypatch, tmp_path, _raw([_event()]))
    inventory = discovery.build_current_event_inventory(
        directory,
        repository_root=tmp_path,
    )
    assert manifest.observed_at == OBSERVED
    assert manifest.provider_event_timestamp is None
    assert manifest.provider_snapshot_id is None
    assert inventory.observed_at == OBSERVED
    assert inventory.provider_event_timestamp is None
    assert inventory.provider_snapshot_id is None
    assert manifest.observation_authority == discovery.OBSERVATION_AUTHORITY


def test_exact_case_mismatch_does_not_fuzzy_match(monkeypatch, tmp_path):
    result = _live(
        monkeypatch,
        tmp_path,
        _raw([_event(home="home fc")]),
    )
    row = result.rows[0]
    assert row.disposition is discovery.CurrentEventReconciliationDisposition.NO_EXACT_MATCH
    assert row.fixture_reconciliation_authorized is False
    assert row.matched_fotmob_fixture_id is None


def test_reversed_home_away_does_not_match(monkeypatch, tmp_path):
    result = _live(
        monkeypatch,
        tmp_path,
        _raw([_event(home="Away FC", away="Home FC")]),
    )
    assert result.rows[0].disposition is (
        discovery.CurrentEventReconciliationDisposition.NO_EXACT_MATCH
    )


def test_competition_mismatch_and_missing_competition_remain_explicit(monkeypatch, tmp_path):
    mismatch = _live(
        monkeypatch,
        tmp_path / "mismatch",
        _raw([_event()], competition="Different League"),
    )
    assert mismatch.rows[0].disposition is (
        discovery.CurrentEventReconciliationDisposition.NO_EXACT_MATCH
    )

    missing = _live(
        monkeypatch,
        tmp_path / "missing",
        _raw([_event()], competition=None, grouped=False),
    )
    assert missing.rows[0].competition_name is None
    assert missing.rows[0].disposition is (
        discovery.CurrentEventReconciliationDisposition.COMPETITION_IDENTITY_UNAVAILABLE
    )


def test_one_second_kickoff_difference_does_not_round_or_tolerate(monkeypatch, tmp_path):
    result = _live(
        monkeypatch,
        tmp_path,
        _raw([_event(kickoff=KICKOFF + timedelta(seconds=1))]),
    )
    assert result.rows[0].disposition is (
        discovery.CurrentEventReconciliationDisposition.NO_EXACT_MATCH
    )


def test_nonbookable_provider_event_is_retained_but_not_authorized(monkeypatch, tmp_path):
    result = _live(
        monkeypatch,
        tmp_path,
        _raw([_event(booking_status="Unavailable")]),
    )
    row = result.rows[0]
    assert row.prematch_bookable_observed is False
    assert row.disposition is (
        discovery.CurrentEventReconciliationDisposition.PROVIDER_EVENT_NOT_PREMATCH_BOOKABLE
    )
    assert row.fixture_reconciliation_authorized is False


def test_event_at_minimum_kickoff_lead_is_not_authorized(monkeypatch, tmp_path):
    kickoff = OBSERVED + timedelta(seconds=125)
    source = handoff_helpers._source()
    candidate = handoff_helpers._candidate(source, hour=10)
    # The stock helper only varies hours. Build a reviewed input with a kickoff that
    # exactly matches our sub-minute provider test by replacing the candidate itself.
    candidate = dataclasses.replace(candidate, kickoff_utc=kickoff)
    bundle = handoff_helpers._bundle((source,), (candidate,))
    review = build_fotmob_fixture_candidate_review_bundle(
        bundle, (handoff_helpers._decision(candidate),)
    )
    handoff = handoff_module.build_fotmob_fixture_catalog_handoff(bundle, review)
    result = _live(
        monkeypatch,
        tmp_path,
        _raw([_event(kickoff=kickoff)]),
        handoff=handoff,
        now=OBSERVED + timedelta(seconds=5),
    )
    assert result.rows[0].kickoff_lead_seconds == pytest.approx(120.0)
    assert result.rows[0].disposition is (
        discovery.CurrentEventReconciliationDisposition.PROVIDER_EVENT_TOO_CLOSE_TO_KICKOFF
    )


def test_two_provider_events_targeting_same_fotmob_fixture_are_ambiguous(monkeypatch, tmp_path):
    result = _live(
        monkeypatch,
        tmp_path,
        _raw([_event(event_id="sr:match:123"), _event(event_id="sr:match:124")]),
    )
    assert len(result.rows) == 2
    assert result.matched_rows == ()
    assert {
        row.disposition for row in result.rows
    } == {
        discovery.CurrentEventReconciliationDisposition.AMBIGUOUS_PROVIDER_EVENT_FOR_FIXTURE
    }
    assert all(row.fixture_reconciliation_authorized is False for row in result.rows)


def test_one_provider_event_matching_two_fotmob_ids_is_ambiguous(monkeypatch, tmp_path):
    result = _live(
        monkeypatch,
        tmp_path,
        _raw([_event()]),
        handoff=_multi_handoff_same_identity(),
    )
    row = result.rows[0]
    assert row.exact_fotmob_match_count == 2
    assert row.disposition is (
        discovery.CurrentEventReconciliationDisposition.AMBIGUOUS_FOTMOB_MATCH
    )
    assert row.matched_fotmob_fixture_id is None
    assert row.fixture_reconciliation_authorized is False


def test_stale_source_cannot_be_replayed_as_current_fixture_reconciliation(monkeypatch, tmp_path):
    directory, _manifest = _capture(monkeypatch, tmp_path, _raw([_event()]))
    with pytest.raises(discovery.SportyBetCurrentEventDiscoveryError, match="maximum observation age"):
        discovery.replay_current_event_fixture_reconciliation(
            evidence_directory=directory,
            repository_root=tmp_path,
            fotmob_catalog_handoff=_single_handoff(),
            evaluation_time=OBSERVED + timedelta(seconds=901),
        )


def test_evaluation_time_before_response_completion_fails_closed(monkeypatch, tmp_path):
    directory, _manifest = _capture(monkeypatch, tmp_path, _raw([_event()]))
    with pytest.raises(discovery.SportyBetCurrentEventDiscoveryError, match="predates"):
        discovery.replay_current_event_fixture_reconciliation(
            evidence_directory=directory,
            repository_root=tmp_path,
            fotmob_catalog_handoff=_single_handoff(),
            evaluation_time=OBSERVED - timedelta(microseconds=1),
        )


def test_identical_duplicate_event_objects_are_deduped(monkeypatch, tmp_path):
    event = _event()
    result = _live(monkeypatch, tmp_path, _raw([event, dict(event)]))
    assert len(result.rows) == 1
    assert result.rows[0].fixture_reconciliation_authorized is True


def test_conflicting_duplicate_event_id_fails_closed(monkeypatch, tmp_path):
    with pytest.raises(discovery.SportyBetCurrentEventDiscoveryError, match="conflicting duplicate"):
        _live(
            monkeypatch,
            tmp_path,
            _raw([_event(), _event(home="Other Home")]),
        )


def test_successful_empty_provider_response_is_explicit_zero_event_inventory(monkeypatch, tmp_path):
    result = _live(monkeypatch, tmp_path, _raw([], grouped=False))
    assert result.rows == ()
    assert result.matched_rows == ()
    assert result.to_dict()["event_count"] == 0
    assert result.to_dict()["matched_count"] == 0


def test_live_network_requires_exact_opt_in(monkeypatch, tmp_path):
    monkeypatch.setattr(
        discovery,
        "_network_fetch",
        lambda: (_raw([_event()]), 200, OBSERVED),
    )
    with pytest.raises(discovery.SportyBetCurrentEventDiscoveryError, match="execute_live_network=True"):
        discovery.capture_current_event_evidence(
            repository_root=tmp_path,
            execute_live_network=False,
        )


def test_reconciliation_is_builder_only_and_public_tamper_fails_reconstruction(monkeypatch, tmp_path):
    with pytest.raises(discovery.SportyBetCurrentEventDiscoveryError, match="builder-only"):
        discovery.SportyBetCurrentEventFixtureReconciliation()
    result = _live(monkeypatch, tmp_path, _raw([_event()]))
    with pytest.raises(discovery.SportyBetCurrentEventDiscoveryError):
        dataclasses.replace(result, status="FORGED")
    object.__setattr__(result, "status", "FORGED")
    with pytest.raises(discovery.SportyBetCurrentEventDiscoveryError, match="differs"):
        discovery.verify_current_event_fixture_reconciliation(result)


def test_raw_evidence_tamper_fails_verification(monkeypatch, tmp_path):
    result = _live(monkeypatch, tmp_path, _raw([_event()]))
    raw_path = result._evidence_directory / discovery.RAW_FILENAME
    raw_path.write_bytes(_raw([_event(home="Tampered FC")]))
    with pytest.raises(discovery.SportyBetCurrentEventDiscoveryError, match="raw response identity"):
        discovery.verify_current_event_fixture_reconciliation(result)


def test_replay_is_deterministic_and_retains_as_of_status(monkeypatch, tmp_path):
    directory, _manifest = _capture(monkeypatch, tmp_path, _raw([_event()]))
    handoff = _single_handoff()
    evaluation_time = OBSERVED + timedelta(seconds=10)
    first = discovery.replay_current_event_fixture_reconciliation(
        evidence_directory=directory,
        repository_root=tmp_path,
        fotmob_catalog_handoff=handoff,
        evaluation_time=evaluation_time,
    )
    second = discovery.replay_current_event_fixture_reconciliation(
        evidence_directory=directory,
        repository_root=tmp_path,
        fotmob_catalog_handoff=handoff,
        evaluation_time=evaluation_time,
    )
    assert first.status == discovery.REPLAY_STATUS
    assert first.proof_mode == discovery.REPLAY_PROOF_MODE
    assert first.canonical_sha256 == second.canonical_sha256
    assert discovery.verify_current_event_fixture_reconciliation(first).canonical_sha256 == (
        first.canonical_sha256
    )
