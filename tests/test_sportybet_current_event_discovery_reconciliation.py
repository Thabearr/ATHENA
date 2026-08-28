from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import pytest

from domain import fotmob_fixture_catalog_handoff as handoff
from domain import sportybet_current_event_discovery_reconciliation as current
from domain import sportybet_live_event_quote_evidence as live
from domain.fotmob_fixture_candidate_review import (
    build_fotmob_fixture_candidate_review_bundle,
)
from tests import test_fotmob_fixture_catalog_handoff as fotmob_helpers

UTC = timezone.utc
KICKOFF = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
OBSERVED = datetime(2026, 8, 15, 10, 0, tzinfo=UTC)
EVENT = "sr:match:123456789"


def _fotmob_handoff(
    *,
    home: str = "Home FC",
    away: str = "Away FC",
    competition: str = "League Ω",
    match_id: int = 1001,
):
    source = fotmob_helpers._source()
    candidate = fotmob_helpers._candidate(
        source,
        match_id=match_id,
        competition=competition,
        home_name=home,
        away_name=away,
        hour=12,
    )
    bundle = fotmob_helpers._bundle((source,), (candidate,))
    review = build_fotmob_fixture_candidate_review_bundle(
        bundle,
        (fotmob_helpers._decision(candidate),),
    )
    return handoff.build_fotmob_fixture_catalog_handoff(bundle, review)


def _event(
    *,
    event_id: str = EVENT,
    home: str = "Home FC",
    away: str = "Away FC",
    kickoff: datetime = KICKOFF,
    status=0,
    booking_status: str = "Available",
    tournament_name: str | None = None,
):
    value = {
        "eventId": event_id,
        "homeTeamName": home,
        "awayTeamName": away,
        "estimateStartTime": int(kickoff.timestamp() * 1000),
        "status": status,
        "bookingStatus": booking_status,
        "matchStatus": "Not started" if status in (0, "0", None) else "Live",
    }
    if tournament_name is not None:
        value["tournamentName"] = tournament_name
    return value


def _discovery_raw(
    events,
    *,
    tournament_name: str | None = "League Ω",
):
    if tournament_name is None:
        data = list(events)
    else:
        data = [{"name": tournament_name, "events": list(events)}]
    return json.dumps(
        {"bizCode": 10000, "data": data},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _empty_discovery_raw():
    return b'{"bizCode":10000,"data":[]}'


def _detail_raw(
    *,
    event_id: str = EVENT,
    home: str = "Home FC",
    away: str = "Away FC",
    kickoff: datetime = KICKOFF,
    status=0,
):
    event = _event(
        event_id=event_id,
        home=home,
        away=away,
        kickoff=kickoff,
        status=status,
        tournament_name="League Ω",
    )
    event["markets"] = [
        {
            "id": "1",
            "desc": "1X2",
            "outcomes": [
                {"id": "1", "desc": "1", "odds": "2", "isActive": 1},
                {"id": "X", "desc": "X", "odds": "3", "isActive": 1},
                {"id": "2", "desc": "2", "odds": "4", "isActive": 1},
            ],
        }
    ]
    return json.dumps(
        {"bizCode": 10000, "data": {"event": event}},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _install_discovery(monkeypatch, pages):
    def fetch(page_num):
        raw = pages.get(page_num, _empty_discovery_raw())
        return raw, 200, OBSERVED + timedelta(seconds=page_num)

    monkeypatch.setattr(current, "_network_fetch_page", fetch)


def _install_detail(monkeypatch, raw=None, observed=None):
    raw = _detail_raw() if raw is None else raw
    observed = OBSERVED + timedelta(seconds=30) if observed is None else observed

    def fetch(event_id):
        assert event_id == EVENT
        return raw, 200, observed

    monkeypatch.setattr(live, "_network_fetch", fetch)


def test_contract_pins_pr246_pr250_and_fotmob_handoff():
    identities = current.validate_current_event_discovery_contract()
    assert identities["live_event_source_contract_sha256"] == (
        "b888cebab6447cd4072d823dab67b56f1f75f72eb72d67b692d47a4378b27555"
    )
    assert identities["portfolio_optimizer_v2_contract_sha256"] == (
        "919149759ffc9aabef2fefe7c6e0db72d697ebd1ffe33205054fc3ffb4f785fd"
    )
    assert current.calculate_current_event_discovery_contract_sha256() == (
        current.EXPECTED_CONTRACT_SHA256
    )
    assert current.NEXT_BOUNDARY == (
        "CURRENT_DIRECT_PROVIDER_CANONICAL_MARKET_MAPPING_REBIND_REQUIRED"
    )


def test_discovery_capture_preserves_pages_and_replays_exactly(monkeypatch, tmp_path):
    _install_discovery(
        monkeypatch,
        {1: _discovery_raw([_event()]), 2: _empty_discovery_raw()},
    )
    directory, manifest = current.capture_current_event_discovery(
        repository_root=tmp_path,
        execute_live_network=True,
    )
    assert manifest.dataset_name == current.DISCOVERY_DATASET_NAME
    assert len(manifest.pages) == 2
    assert len(manifest.events) == 1
    event = manifest.events[0]
    assert event.event_id == EVENT
    assert event.home_team_name == "Home FC"
    assert event.away_team_name == "Away FC"
    assert event.competition_name == "League Ω"
    assert event.kickoff_utc == KICKOFF
    assert event.prematch_bookable_observed is True
    assert current.verify_current_event_discovery(
        directory, repository_root=tmp_path
    ).to_dict() == manifest.to_dict()


def test_exact_discovery_plus_pr246_detail_authorizes_fixture_reconciliation(
    monkeypatch, tmp_path
):
    _install_discovery(
        monkeypatch,
        {1: _discovery_raw([_event()]), 2: _empty_discovery_raw()},
    )
    _install_detail(monkeypatch)
    result = current.discover_and_reconcile_current_events(
        repository_root=tmp_path,
        fotmob_catalog_handoff=_fotmob_handoff(),
        execute_live_network=True,
    )
    assert result.status == current.STATUS
    assert result.authorized_reconciliation_count == 1
    assert result.reconciliation_count == 1
    row = result.results[0]
    assert row.disposition is (
        current.CurrentEventReconciliationDisposition.UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED
    )
    assert row.fixture_reconciliation_authorized is True
    assert row.matched_fotmob_fixture_id == "1001"
    assert row.matched_home_team == "Home FC"
    assert row.matched_away_team == "Away FC"
    assert row.matched_competition == "League Ω"
    assert row.matched_kickoff_utc == KICKOFF
    assert row.direct_event_manifest_sha256 is not None
    assert row.direct_event_inventory_sha256 is not None
    assert row.direct_event_raw_sha256 is not None
    assert result.authority["fixture_reconciliation"] is True
    assert result.authority["canonical_market_mapping"] is False
    assert result.authority["price_all"] is False
    assert result.authority["market_router"] is False
    assert result.authority["portfolio_optimization"] is False
    assert result.authority["sportybet_execution"] is False
    assert result.authority["bet"] is False
    assert result.to_dict()["wager_placed"] is False
    assert current.verify_current_event_discovery_reconciliation_bundle(
        result
    ).canonical_sha256 == result.canonical_sha256


def test_competition_must_be_proven_before_matching(monkeypatch, tmp_path):
    _install_discovery(
        monkeypatch,
        {1: _discovery_raw([_event()], tournament_name=None), 2: _empty_discovery_raw()},
    )

    def forbidden(_event_id):
        raise AssertionError("detail endpoint must not run for unproven competition")

    monkeypatch.setattr(live, "_network_fetch", forbidden)
    result = current.discover_and_reconcile_current_events(
        repository_root=tmp_path,
        fotmob_catalog_handoff=_fotmob_handoff(),
        execute_live_network=True,
    )
    assert result.authorized_reconciliation_count == 0
    assert result.results[0].disposition is (
        current.CurrentEventReconciliationDisposition.PROVIDER_COMPETITION_UNPROVEN
    )


def test_case_sensitive_team_mismatch_never_fuzzy_matches(monkeypatch, tmp_path):
    _install_discovery(
        monkeypatch,
        {
            1: _discovery_raw([_event(home="home fc")]),
            2: _empty_discovery_raw(),
        },
    )

    def forbidden(_event_id):
        raise AssertionError("detail endpoint must not run without exact FotMob match")

    monkeypatch.setattr(live, "_network_fetch", forbidden)
    result = current.discover_and_reconcile_current_events(
        repository_root=tmp_path,
        fotmob_catalog_handoff=_fotmob_handoff(),
        execute_live_network=True,
    )
    assert result.results[0].disposition is (
        current.CurrentEventReconciliationDisposition.NO_EXACT_REVIEWED_FOTMOB_MATCH
    )
    assert result.results[0].fixture_reconciliation_authorized is False


def test_full_utc_mismatch_never_rounds_or_uses_tolerance(monkeypatch, tmp_path):
    _install_discovery(
        monkeypatch,
        {
            1: _discovery_raw([_event(kickoff=KICKOFF + timedelta(seconds=1))]),
            2: _empty_discovery_raw(),
        },
    )
    result = current.discover_and_reconcile_current_events(
        repository_root=tmp_path,
        fotmob_catalog_handoff=_fotmob_handoff(),
        execute_live_network=True,
    )
    assert result.results[0].disposition is (
        current.CurrentEventReconciliationDisposition.NO_EXACT_REVIEWED_FOTMOB_MATCH
    )


def test_direct_detail_identity_drift_fails_closed(monkeypatch, tmp_path):
    _install_discovery(
        monkeypatch,
        {1: _discovery_raw([_event()]), 2: _empty_discovery_raw()},
    )
    _install_detail(monkeypatch, raw=_detail_raw(home="Different Home"))
    result = current.discover_and_reconcile_current_events(
        repository_root=tmp_path,
        fotmob_catalog_handoff=_fotmob_handoff(),
        execute_live_network=True,
    )
    assert result.authorized_reconciliation_count == 0
    assert result.results[0].disposition is (
        current.CurrentEventReconciliationDisposition.DIRECT_EVENT_DETAIL_CONFIRMATION_FAILED
    )
    assert result.results[0].direct_event_manifest_sha256 is None


def test_live_or_unavailable_discovery_event_never_authorizes(monkeypatch, tmp_path):
    _install_discovery(
        monkeypatch,
        {
            1: _discovery_raw([_event(status=1)]),
            2: _empty_discovery_raw(),
        },
    )
    result = current.discover_and_reconcile_current_events(
        repository_root=tmp_path,
        fotmob_catalog_handoff=_fotmob_handoff(),
        execute_live_network=True,
    )
    assert result.results[0].disposition is (
        current.CurrentEventReconciliationDisposition.DISCOVERY_EVENT_NOT_PREMATCH_BOOKABLE
    )


def test_cross_page_event_identity_drift_is_rejected(monkeypatch, tmp_path):
    _install_discovery(
        monkeypatch,
        {
            1: _discovery_raw([_event()]),
            2: _discovery_raw([_event(away="Changed Away")]),
        },
    )
    with pytest.raises(current.SportyBetCurrentEventDiscoveryError, match="identity drifted"):
        current.capture_current_event_discovery(
            repository_root=tmp_path,
            execute_live_network=True,
        )


def test_tampered_discovery_raw_page_fails_replay(monkeypatch, tmp_path):
    _install_discovery(
        monkeypatch,
        {1: _discovery_raw([_event()]), 2: _empty_discovery_raw()},
    )
    directory, _ = current.capture_current_event_discovery(
        repository_root=tmp_path,
        execute_live_network=True,
    )
    page = directory / "page-0001.raw.json"
    page.write_bytes(page.read_bytes() + b" ")
    with pytest.raises(current.SportyBetCurrentEventDiscoveryError, match="identity mismatch"):
        current.verify_current_event_discovery(directory, repository_root=tmp_path)


def test_builder_only_and_public_bundle_tamper_fail_reconstruction(monkeypatch, tmp_path):
    with pytest.raises(current.SportyBetCurrentEventDiscoveryError, match="issued only"):
        current.SportyBetCurrentEventDiscoveryReconciliationBundle()

    _install_discovery(
        monkeypatch,
        {1: _discovery_raw([_event()]), 2: _empty_discovery_raw()},
    )
    _install_detail(monkeypatch)
    result = current.discover_and_reconcile_current_events(
        repository_root=tmp_path,
        fotmob_catalog_handoff=_fotmob_handoff(),
        execute_live_network=True,
    )
    object.__setattr__(result, "status", "TAMPERED")
    with pytest.raises(current.SportyBetCurrentEventDiscoveryError, match="differs from exact source replay"):
        current.verify_current_event_discovery_reconciliation_bundle(result)


def test_network_acquisition_requires_explicit_true(tmp_path):
    with pytest.raises(current.SportyBetCurrentEventDiscoveryError, match="execute_live_network=True"):
        current.capture_current_event_discovery(
            repository_root=tmp_path,
            execute_live_network=False,
        )
