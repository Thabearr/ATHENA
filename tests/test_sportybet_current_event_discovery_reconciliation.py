from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from domain import sportybet_current_event_discovery_reconciliation as current
from domain import sportybet_live_event_quote_evidence as live
from domain.fixture_catalog import compile_fixture_catalog, sha256_bytes
from domain.fotmob_data_matches_capture import (
    CapturedFotMobDataMatchesResponse,
    build_data_matches_capture_manifest,
)
from domain.fotmob_fixture_candidate_review import (
    FixtureCandidateReviewDisposition,
    FotMobFixtureCandidateReviewDecision,
    build_fotmob_fixture_candidate_review_bundle,
    sha256_fotmob_fixture_candidate,
)
from domain.fotmob_fixture_candidates import build_fotmob_fixture_candidate_bundle
from domain.fotmob_fixture_catalog_handoff import (
    build_fotmob_fixture_catalog_handoff,
    sha256_fotmob_fixture_catalog_handoff,
)
from domain.reviewed_fixture_catalog_admission import (
    REVIEWED_SOURCE_CAPABILITY,
    ReviewedFixtureCatalogAdmissionDecision,
    ReviewedFixtureCatalogAdmissionDisposition,
    build_reviewed_fixture_catalog_admission,
    sha256_reviewed_fixture_catalog_admission,
    sha256_reviewed_source_capability,
)

UTC = timezone.utc
FOTMOB_OBSERVED = datetime(2026, 8, 15, 8, 0, tzinfo=UTC)
DISCOVERY_OBSERVED = datetime(2026, 8, 15, 10, 0, tzinfo=UTC)
DETAIL_OBSERVED = datetime(2026, 8, 15, 10, 0, 30, tzinfo=UTC)
EVALUATION = datetime(2026, 8, 15, 10, 0, 35, tzinfo=UTC)
KICKOFF = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
EVENT = "sr:match:123456789"


def _epoch_ms(value: datetime) -> int:
    return int(value.astimezone(UTC).timestamp() * 1000)


def _fotmob_match(
    match_id: int,
    *,
    home: str = "Home FC",
    away: str = "Away FC",
    kickoff: datetime = KICKOFF,
) -> dict:
    kickoff = kickoff.astimezone(UTC)
    return {
        "away": {"id": 202, "score": 0, "name": away, "longName": away},
        "eliminatedTeamId": None,
        "home": {"id": 101, "score": 0, "name": home, "longName": home},
        "id": match_id,
        "leagueId": 10,
        "status": {
            "utcTime": kickoff.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "halfs": {"firstHalfStarted": ""},
            "periodLength": 45,
            "started": False,
            "cancelled": False,
            "finished": False,
        },
        "statusId": 1,
        "time": kickoff.strftime("%d.%m.%Y %H:%M"),
        "timeTS": _epoch_ms(kickoff),
        "tournamentStage": "",
    }


def _fotmob_capture(
    *,
    match_ids: tuple[int, ...] = (1001,),
    home: str = "Home FC",
    away: str = "Away FC",
    competition: str = "League Ω",
    kickoff: datetime = KICKOFF,
):
    payload = {
        "date": kickoff.astimezone(UTC).strftime("%Y%m%d"),
        "leagues": [
            {
                "ccode": "NGA",
                "id": 10,
                "internalRank": 1,
                "matches": [
                    _fotmob_match(match_id, home=home, away=away, kickoff=kickoff)
                    for match_id in match_ids
                ],
                "name": competition,
                "primaryId": 10,
                "simpleLeague": False,
            }
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    response = CapturedFotMobDataMatchesResponse(
        status=200,
        content_type="application/json; charset=utf-8",
        content_length=len(raw),
        body=raw,
        observed_at=FOTMOB_OBSERVED,
        network_acquisition_performed=True,
    )
    manifest = build_data_matches_capture_manifest(
        response,
        request_date=payload["date"],
        timezone="UTC",
        ccode3="NGA",
    )
    return raw, manifest


def _fotmob_admission(
    tmp_path: Path,
    *,
    match_ids: tuple[int, ...] = (1001,),
    home: str = "Home FC",
    away: str = "Away FC",
    competition: str = "League Ω",
    kickoff: datetime = KICKOFF,
    disposition: ReviewedFixtureCatalogAdmissionDisposition = (
        ReviewedFixtureCatalogAdmissionDisposition.ADMITTED
    ),
):
    capture = _fotmob_capture(
        match_ids=match_ids,
        home=home,
        away=away,
        competition=competition,
        kickoff=kickoff,
    )
    candidate_bundle = build_fotmob_fixture_candidate_bundle((capture,))
    decisions = tuple(
        FotMobFixtureCandidateReviewDecision(
            source_capture_manifest_sha256=candidate.source_capture_manifest_sha256,
            source_match_id=candidate.source_match_id,
            candidate_sha256=sha256_fotmob_fixture_candidate(candidate),
            disposition=FixtureCandidateReviewDisposition.APPROVED,
            reviewed_at=datetime(2026, 8, 15, 8, 30, tzinfo=UTC),
            reviewer_reference="operator:pr251-fixture-review",
            notes="explicit reviewed FotMob fixture identity",
        )
        for candidate in candidate_bundle.candidates
    )
    review_bundle = build_fotmob_fixture_candidate_review_bundle(
        candidate_bundle,
        decisions,
    )
    handoff = build_fotmob_fixture_catalog_handoff(candidate_bundle, review_bundle)
    raw = capture[0]
    for item in handoff.catalog_inputs:
        evidence_path = tmp_path / item.evidence_file_path
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_bytes(raw)
    input_path = tmp_path / "reviewed-fotmob.jsonl"
    input_path.write_bytes(handoff.catalog_input_jsonl_bytes)
    result = compile_fixture_catalog(
        input_path=input_path,
        evidence_root=tmp_path,
        as_of=datetime(2026, 8, 15, 9, 0, tzinfo=UTC),
        minimum_lead_seconds=120,
        code_state={
            "evidence_git_head_sha": "a" * 40,
            "tracked_worktree_clean": True,
        },
    )
    decision = ReviewedFixtureCatalogAdmissionDecision(
        candidate_bundle_sha256=handoff.candidate_bundle_sha256,
        review_bundle_sha256=handoff.review_bundle_sha256,
        handoff_sha256=sha256_fotmob_fixture_catalog_handoff(handoff),
        catalog_sha256=sha256_bytes(result.catalog_bytes),
        manifest_sha256=sha256_bytes(result.manifest_bytes),
        source_capability=REVIEWED_SOURCE_CAPABILITY,
        source_capability_sha256=sha256_reviewed_source_capability(),
        disposition=disposition,
        reviewed_at=datetime(2026, 8, 15, 9, 30, tzinfo=UTC),
        reviewer_reference="operator:pr251-catalog-admission",
        notes="catalog identity admitted before current provider reconciliation",
    )
    admission = build_reviewed_fixture_catalog_admission(handoff, result, decision)
    return admission, (capture,)


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
        "sportId": "sr:sport:1",
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


def _discovery_raw(events, *, tournament_name: str | None = "League Ω") -> bytes:
    if tournament_name is None:
        data = list(events)
    else:
        data = [{"name": tournament_name, "events": list(events)}]
    return json.dumps(
        {"bizCode": 10000, "data": data},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _empty_discovery_raw() -> bytes:
    return b'{"bizCode":10000,"data":[]}'


def _detail_raw(
    *,
    event_id: str = EVENT,
    home: str = "Home FC",
    away: str = "Away FC",
    kickoff: datetime = KICKOFF,
    status=0,
    booking_status: str = "Available",
) -> bytes:
    event = _event(
        event_id=event_id,
        home=home,
        away=away,
        kickoff=kickoff,
        status=status,
        booking_status=booking_status,
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


def _install_discovery(monkeypatch, events, *, tournament_name="League Ω", observed=DISCOVERY_OBSERVED):
    pages = {
        1: _discovery_raw(events, tournament_name=tournament_name),
        2: _empty_discovery_raw(),
    }

    def fetch(page_num):
        raw = pages.get(page_num, _empty_discovery_raw())
        return raw, 200, observed + timedelta(seconds=page_num - 1)

    monkeypatch.setattr(current, "_network_fetch_page", fetch)


def _install_detail(monkeypatch, *, raw=None, observed=DETAIL_OBSERVED):
    raw = _detail_raw() if raw is None else raw

    def fetch(event_id):
        payload = json.loads(raw)
        assert event_id == payload["data"]["event"]["eventId"]
        return raw, 200, observed

    monkeypatch.setattr(live, "_network_fetch", fetch)


def _run(
    monkeypatch,
    tmp_path: Path,
    *,
    events=None,
    tournament_name="League Ω",
    admission=None,
    captures=None,
    detail_raw=None,
    discovery_observed=DISCOVERY_OBSERVED,
    detail_observed=DETAIL_OBSERVED,
    evaluation=EVALUATION,
):
    tmp_path.mkdir(parents=True, exist_ok=True)
    if admission is None or captures is None:
        admission, captures = _fotmob_admission(tmp_path)
    _install_discovery(
        monkeypatch,
        [_event()] if events is None else events,
        tournament_name=tournament_name,
        observed=discovery_observed,
    )
    _install_detail(monkeypatch, raw=detail_raw, observed=detail_observed)
    monkeypatch.setattr(current, "_now_utc", lambda: evaluation)
    return current.discover_and_reconcile_current_events(
        repository_root=tmp_path,
        fotmob_admission_value=admission,
        fotmob_captures=captures,
        execute_live_network=True,
    )


def test_contract_pins_pr246_pr250_raw_fotmob_replay_and_exact_hash():
    identities = current.validate_current_event_discovery_contract()
    assert identities["live_event_source_contract_sha256"] == (
        "b888cebab6447cd4072d823dab67b56f1f75f72eb72d67b692d47a4378b27555"
    )
    assert identities["portfolio_optimizer_v2_contract_sha256"] == (
        "919149759ffc9aabef2fefe7c6e0db72d697ebd1ffe33205054fc3ffb4f785fd"
    )
    assert current.FOTMOB_SOURCE_REPLAY_POLICY == (
        "RAW_FOTMOB_CAPTURE_PLUS_EXPLICIT_REVIEW_PLUS_ADMITTED_CATALOG_REDERIVATION_REQUIRED"
    )
    assert current.calculate_current_event_discovery_contract_sha256() == (
        "64c7a2b71304f94a39de7e608be1f76a10e14a1a52a338f89d1c695ba0e5f1ee"
    )
    assert current.EXPECTED_CONTRACT_SHA256 == (
        current.calculate_current_event_discovery_contract_sha256()
    )
    assert current.NEXT_BOUNDARY == (
        "CURRENT_DIRECT_PROVIDER_CANONICAL_MARKET_MAPPING_REBIND_REQUIRED"
    )


def test_request_is_exact_anonymous_football_paginated_scope():
    assert current.request_target(1) == (
        "/api/ng/factsCenter/liveOrPrematchEvents?"
        "sportId=sr%3Asport%3A1&pageSize=100&pageNum=1"
    )
    headers = dict(current.REQUEST_HEADERS)
    assert headers["OperId"] == "2"
    assert "Cookie" not in headers and "Authorization" not in headers


def test_unique_exact_raw_source_replayed_match_authorizes_fixture_only(monkeypatch, tmp_path):
    admission, captures = _fotmob_admission(tmp_path)
    result = _run(
        monkeypatch,
        tmp_path,
        admission=admission,
        captures=captures,
    )
    assert result.status == current.STATUS
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.disposition is (
        current.CurrentEventReconciliationDisposition.UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED
    )
    assert row.fixture_reconciliation_authorized is True
    assert row.matched_fotmob_fixture_id == "1001"
    assert row.discovery_age_seconds == pytest.approx(35.0)
    assert row.direct_event_age_seconds == pytest.approx(5.0)
    assert row.direct_event_manifest_sha256 is not None
    assert row.direct_event_inventory_sha256 is not None
    assert row.direct_event_raw_sha256 is not None
    assert result.source_fotmob_admission_sha256 == (
        sha256_reviewed_fixture_catalog_admission(admission)
    )
    assert len(result.fotmob_capture_identities) == 1
    assert result.authority["current_event_discovery"] is True
    assert result.authority["current_event_detail_confirmation"] is True
    assert result.authority["fixture_reconciliation"] is True
    for key in (
        "canonical_market_mapping",
        "price_all",
        "market_router",
        "portfolio_optimization",
        "final_selection",
        "accumulator_slip_construction",
        "sportybet_execution",
        "staking",
        "bet",
    ):
        assert result.authority[key] is False
    assert result.to_dict()["provider_event_timestamp"] is None
    assert result.to_dict()["provider_snapshot_id"] is None
    assert result.to_dict()["wager_placed"] is False
    assert current.verify_current_event_discovery_reconciliation_bundle(result).to_dict() == result.to_dict()


def test_mismatched_raw_fotmob_capture_cannot_reuse_admission(monkeypatch, tmp_path):
    admission, _captures = _fotmob_admission(tmp_path / "admitted")
    other_capture = _fotmob_capture(home="Other Home FC")
    _install_discovery(monkeypatch, [_event()])
    _install_detail(monkeypatch)
    monkeypatch.setattr(current, "_now_utc", lambda: EVALUATION)
    with pytest.raises(current.SportyBetCurrentEventDiscoveryError, match="exact deterministic derivative"):
        current.discover_and_reconcile_current_events(
            repository_root=tmp_path,
            fotmob_admission_value=admission,
            fotmob_captures=(other_capture,),
            execute_live_network=True,
        )


def test_rejected_fotmob_admission_cannot_authorize(monkeypatch, tmp_path):
    admission, captures = _fotmob_admission(
        tmp_path,
        disposition=ReviewedFixtureCatalogAdmissionDisposition.REJECTED,
    )
    _install_discovery(monkeypatch, [_event()])
    _install_detail(monkeypatch)
    monkeypatch.setattr(current, "_now_utc", lambda: EVALUATION)
    with pytest.raises(current.SportyBetCurrentEventDiscoveryError, match="exact ADMITTED"):
        current.discover_and_reconcile_current_events(
            repository_root=tmp_path,
            fotmob_admission_value=admission,
            fotmob_captures=captures,
            execute_live_network=True,
        )


def test_empty_fotmob_capture_population_fails_closed(monkeypatch, tmp_path):
    admission, _captures = _fotmob_admission(tmp_path)
    with pytest.raises(current.SportyBetCurrentEventDiscoveryError, match="non-empty sequence"):
        current.discover_and_reconcile_current_events(
            repository_root=tmp_path,
            fotmob_admission_value=admission,
            fotmob_captures=(),
            execute_live_network=True,
        )


def test_case_reversal_competition_and_one_second_kickoff_are_not_fuzzy(monkeypatch, tmp_path):
    for index, event in enumerate(
        (
            _event(home="home fc"),
            _event(home="Away FC", away="Home FC"),
            _event(kickoff=KICKOFF + timedelta(seconds=1)),
        )
    ):
        root = tmp_path / str(index)
        result = _run(monkeypatch, root, events=[event])
        assert result.rows[0].disposition is (
            current.CurrentEventReconciliationDisposition.NO_EXACT_REVIEWED_FOTMOB_MATCH
        )
        assert result.rows[0].fixture_reconciliation_authorized is False
    mismatch = _run(
        monkeypatch,
        tmp_path / "competition",
        events=[_event()],
        tournament_name="Different League",
    )
    assert mismatch.rows[0].disposition is (
        current.CurrentEventReconciliationDisposition.NO_EXACT_REVIEWED_FOTMOB_MATCH
    )


def test_missing_or_conflicted_provider_competition_never_reconciles(monkeypatch, tmp_path):
    missing = _run(
        monkeypatch,
        tmp_path / "missing",
        events=[_event(tournament_name=None)],
        tournament_name=None,
    )
    assert missing.rows[0].competition_name is None
    assert missing.rows[0].disposition is (
        current.CurrentEventReconciliationDisposition.PROVIDER_COMPETITION_UNPROVEN
    )
    conflicted = _run(
        monkeypatch,
        tmp_path / "conflicted",
        events=[_event(tournament_name="Event League")],
        tournament_name="Envelope League",
    )
    assert conflicted.rows[0].competition_name is None
    assert conflicted.rows[0].disposition is (
        current.CurrentEventReconciliationDisposition.PROVIDER_COMPETITION_UNPROVEN
    )


def test_one_provider_event_matching_two_admitted_fotmob_fixtures_is_ambiguous(monkeypatch, tmp_path):
    admission, captures = _fotmob_admission(tmp_path, match_ids=(1001, 1002))
    result = _run(
        monkeypatch,
        tmp_path,
        admission=admission,
        captures=captures,
    )
    row = result.rows[0]
    assert row.exact_fotmob_match_count == 2
    assert row.disposition is (
        current.CurrentEventReconciliationDisposition.AMBIGUOUS_EXACT_REVIEWED_FOTMOB_MATCH
    )
    assert row.direct_event_manifest_sha256 is None


def test_two_provider_event_ids_targeting_one_fotmob_fixture_are_all_ambiguous(monkeypatch, tmp_path):
    result = _run(
        monkeypatch,
        tmp_path,
        events=[_event(event_id=EVENT), _event(event_id="sr:match:123456790")],
    )
    assert len(result.rows) == 2
    assert result.matched_rows == ()
    assert {row.disposition for row in result.rows} == {
        current.CurrentEventReconciliationDisposition.AMBIGUOUS_PROVIDER_EVENT_FOR_FIXTURE
    }
    assert all(row.direct_event_manifest_sha256 is None for row in result.rows)


def test_discovery_and_direct_detail_freshness_are_both_required(monkeypatch, tmp_path):
    stale_discovery = _run(
        monkeypatch,
        tmp_path / "discovery",
        evaluation=DISCOVERY_OBSERVED + timedelta(seconds=901),
    )
    assert stale_discovery.rows[0].disposition is (
        current.CurrentEventReconciliationDisposition.DISCOVERY_EVIDENCE_STALE
    )
    stale_detail = _run(
        monkeypatch,
        tmp_path / "detail",
        detail_observed=EVALUATION - timedelta(seconds=901),
    )
    assert stale_detail.rows[0].disposition is (
        current.CurrentEventReconciliationDisposition.DIRECT_EVENT_DETAIL_STALE
    )


def test_event_at_exact_minimum_kickoff_lead_is_not_authorized(monkeypatch, tmp_path):
    kickoff = EVALUATION + timedelta(seconds=current.MINIMUM_LEAD_SECONDS)
    admission, captures = _fotmob_admission(tmp_path, kickoff=kickoff)
    result = _run(
        monkeypatch,
        tmp_path,
        events=[_event(kickoff=kickoff)],
        admission=admission,
        captures=captures,
        detail_raw=_detail_raw(kickoff=kickoff),
        evaluation=EVALUATION,
    )
    assert result.rows[0].kickoff_lead_seconds == pytest.approx(120.0)
    assert result.rows[0].disposition is (
        current.CurrentEventReconciliationDisposition.PROVIDER_EVENT_TOO_CLOSE_TO_KICKOFF
    )


def test_direct_detail_identity_mismatch_fails_reconciliation(monkeypatch, tmp_path):
    result = _run(
        monkeypatch,
        tmp_path,
        detail_raw=_detail_raw(home="Different Home FC"),
    )
    row = result.rows[0]
    assert row.disposition is (
        current.CurrentEventReconciliationDisposition.DIRECT_EVENT_DETAIL_IDENTITY_MISMATCH
    )
    assert row.fixture_reconciliation_authorized is False


def test_direct_detail_nonbookable_fails_reconciliation(monkeypatch, tmp_path):
    result = _run(
        monkeypatch,
        tmp_path,
        detail_raw=_detail_raw(booking_status="Unavailable"),
    )
    assert result.rows[0].disposition is (
        current.CurrentEventReconciliationDisposition.DIRECT_EVENT_DETAIL_NOT_PREMATCH_BOOKABLE
    )


def test_successful_empty_provider_feed_is_explicit_zero_event_evidence(monkeypatch, tmp_path):
    admission, captures = _fotmob_admission(tmp_path)
    _install_discovery(monkeypatch, [], tournament_name=None)
    monkeypatch.setattr(current, "_now_utc", lambda: EVALUATION)
    result = current.discover_and_reconcile_current_events(
        repository_root=tmp_path,
        fotmob_admission_value=admission,
        fotmob_captures=captures,
        execute_live_network=True,
    )
    assert result.rows == ()
    assert result.matched_rows == ()
    assert result.authority["current_event_discovery"] is True
    assert result.authority["current_event_detail_confirmation"] is False
    assert result.authority["fixture_reconciliation"] is False
    assert result.to_dict()["event_count"] == 0


def test_discovery_capture_requires_terminal_empty_page_and_replays_raw(monkeypatch, tmp_path):
    _install_discovery(monkeypatch, [_event()])
    directory, manifest = current.capture_current_event_discovery(
        repository_root=tmp_path,
        execute_live_network=True,
    )
    assert len(manifest.pages) == 2
    assert manifest.pages[-1].event_count == 0
    assert current.verify_current_event_discovery(
        directory,
        repository_root=tmp_path,
    ).to_dict() == manifest.to_dict()
    first_page = directory / current.PAGE_FILENAME_TEMPLATE.format(page_num=1)
    first_page.write_bytes(_discovery_raw([_event(home="Tampered FC")]))
    with pytest.raises(current.SportyBetCurrentEventDiscoveryError, match="raw page identity"):
        current.verify_current_event_discovery(directory, repository_root=tmp_path)


def test_conflicting_duplicate_provider_event_identity_fails_closed(monkeypatch, tmp_path):
    pages = {
        1: _discovery_raw([_event()]),
        2: _discovery_raw([_event(home="Other Home FC")]),
        3: _empty_discovery_raw(),
    }

    def fetch(page_num):
        return pages[page_num], 200, DISCOVERY_OBSERVED + timedelta(seconds=page_num)

    monkeypatch.setattr(current, "_network_fetch_page", fetch)
    with pytest.raises(current.SportyBetCurrentEventDiscoveryError, match="conflicting duplicate"):
        current.capture_current_event_discovery(
            repository_root=tmp_path,
            execute_live_network=True,
        )


def test_caller_cannot_run_network_without_exact_opt_in(monkeypatch, tmp_path):
    admission, captures = _fotmob_admission(tmp_path)
    with pytest.raises(current.SportyBetCurrentEventDiscoveryError, match="execute_live_network=True"):
        current.discover_and_reconcile_current_events(
            repository_root=tmp_path,
            fotmob_admission_value=admission,
            fotmob_captures=captures,
            execute_live_network=False,
        )


def test_bundle_is_builder_only_and_tamper_fails_exact_source_replay(monkeypatch, tmp_path):
    with pytest.raises(current.SportyBetCurrentEventDiscoveryError, match="builder-only"):
        current.SportyBetCurrentEventDiscoveryReconciliationBundle()
    result = _run(monkeypatch, tmp_path)
    with pytest.raises(current.SportyBetCurrentEventDiscoveryError):
        dataclasses.replace(result, status="FORGED")
    object.__setattr__(result, "status", "FORGED")
    with pytest.raises(current.SportyBetCurrentEventDiscoveryError, match="differs"):
        current.verify_current_event_discovery_reconciliation_bundle(result)
