from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest

from domain.fotmob_data_matches_capture import (
    CapturedFotMobDataMatchesResponse,
    build_data_matches_capture_manifest,
)
from domain.fotmob_fixture_candidates import build_fotmob_fixture_candidate_bundle
from domain.saturday_2026_08_22_fixture_universe import (
    DATASET_NAME,
    REQUEST_CCODE3,
    REQUEST_TIMEZONE,
    TARGET_FOLD_SIZE,
    TARGET_REQUEST_DATE,
    SaturdayFixtureUniverseError,
    build_saturday_fixture_universe,
    canonical_saturday_fixture_universe_bytes,
    safety_flags,
)


UTC = datetime.timezone.utc


def _epoch_ms(value: str) -> int:
    parsed = datetime.datetime.fromisoformat(value[:-1] + "+00:00")
    epoch = datetime.datetime(1970, 1, 1, tzinfo=UTC)
    delta = parsed - epoch
    return delta.days * 86_400_000 + delta.seconds * 1000


def _match(match_id: int, league_id: int, home: str, away: str, hour: int) -> dict:
    utc_time = f"2026-08-22T{hour:02d}:00:00.000Z"
    return {
        "away": {"id": match_id + 2000, "score": 0, "name": away, "longName": away},
        "eliminatedTeamId": None,
        "home": {"id": match_id + 1000, "score": 0, "name": home, "longName": home},
        "id": match_id,
        "leagueId": league_id,
        "status": {
            "utcTime": utc_time,
            "halfs": {"firstHalfStarted": ""},
            "periodLength": 45,
            "started": False,
            "cancelled": False,
            "finished": False,
        },
        "statusId": 1,
        "time": f"22.08.2026 {hour:02d}:00",
        "timeTS": _epoch_ms(utc_time),
        "tournamentStage": "",
    }


def _league(league_id: int, primary_id: int, name: str, match: dict) -> dict:
    return {
        "ccode": "ENG",
        "id": league_id,
        "internalRank": 1,
        "matches": [match],
        "name": name,
        "primaryId": primary_id,
        "simpleLeague": False,
    }


def _bundle(*, date: str = "20260822"):
    payload = {
        "date": date,
        "leagues": [
            _league(10, 10, "Premier League", _match(1001, 10, "Arsenal", "Leeds United", 14)),
            _league(20, 20, "Unknown Saturday League", _match(1002, 20, "Alpha", "Beta", 16)),
        ],
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    response = CapturedFotMobDataMatchesResponse(
        status=200,
        content_type="application/json; charset=utf-8",
        content_length=len(raw),
        body=raw,
        observed_at=datetime.datetime(2026, 8, 21, 5, 45, tzinfo=UTC),
        network_acquisition_performed=True,
    )
    manifest = build_data_matches_capture_manifest(
        response,
        request_date=date,
        timezone="UTC",
        ccode3="NGA",
    )
    return build_fotmob_fixture_candidate_bundle(((raw, manifest),))


def test_frozen_contract_and_downstream_authority_all_false():
    assert DATASET_NAME == "athena-saturday-2026-08-22-fixture-universe-v1"
    assert TARGET_REQUEST_DATE == "20260822"
    assert REQUEST_TIMEZONE == "UTC"
    assert REQUEST_CCODE3 == "NGA"
    assert TARGET_FOLD_SIZE == 20
    assert safety_flags()
    assert not any(safety_flags().values())


def test_builds_exact_literal_priority_inventory_without_inference():
    report = build_saturday_fixture_universe(_bundle())
    assert report["candidate_count"] == 2
    assert report["bootstrap_exact_name_match_count"] == 1
    assert report["unprioritized_literal_competition_count"] == 1
    assert report["enough_source_fixtures_for_requested_fold"] is False
    assert report["candidates"][0]["source_competition_name"] == "Premier League"
    assert report["candidates"][0]["bootstrap_league_rank"] == 1
    unknown = next(
        item
        for item in report["candidates"]
        if item["source_competition_name"] == "Unknown Saturday League"
    )
    assert unknown["bootstrap_exact_name_match"] is False
    assert unknown["bootstrap_league_name"] is None
    assert not any(report["safety"].values())


def test_canonical_bytes_are_stable_and_lf_terminated():
    report = build_saturday_fixture_universe(_bundle())
    first = canonical_saturday_fixture_universe_bytes(report)
    second = canonical_saturday_fixture_universe_bytes(report)
    assert first == second
    assert first.endswith(b"\n")
    assert json.loads(first)["requested_fold_size"] == 20


def test_wrong_request_date_fails_closed():
    with pytest.raises(SaturdayFixtureUniverseError, match="source request date"):
        build_saturday_fixture_universe(_bundle(date="20260821"))


def test_capture_workflow_is_owner_exact_head_and_no_write_authority():
    workflow = Path(
        ".github/workflows/capture-saturday-2026-08-22-fixture-universe.yml"
    ).read_text(encoding="utf-8")
    assert "github.actor == 'Thabearr'" in workflow
    assert "persist-credentials: false" in workflow
    assert "contents: read" in workflow
    assert "pull-requests: read" in workflow
    assert "contents: write" not in workflow
    assert "20260822" in workflow
    assert "--execute-live-network" in workflow
    assert "saturday-2026-08-22-fixture-universe-evidence" in workflow
    assert "bet authorization: false" in workflow
