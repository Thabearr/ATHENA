from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest

from config.competition_review_priority import (
    COMPETITION_REVIEW_PRIORITY_POLICY_VERSION,
    CompetitionKind,
)
from domain.fotmob_data_matches_capture import (
    CapturedFotMobDataMatchesResponse,
    build_data_matches_capture_manifest,
)
from domain.fotmob_fixture_candidates import build_fotmob_fixture_candidate_bundle
from domain.saturday_2026_08_22_fixture_universe import (
    DATASET_NAME,
    REQUEST_CCODE3,
    REQUEST_TIMEZONE,
    SCHEMA_VERSION,
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


def _match(
    match_id: int,
    league_id: int,
    home: str,
    away: str,
    hour: int,
    *,
    date: str = "20260822",
) -> dict:
    utc_time = f"{date[:4]}-{date[4:6]}-{date[6:]}T{hour:02d}:00:00.000Z"
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
        "time": f"{date[6:]}.{date[4:6]}.{date[:4]} {hour:02d}:00",
        "timeTS": _epoch_ms(utc_time),
        "tournamentStage": "",
    }


def _league(
    league_id: int,
    primary_id: int,
    name: str,
    match: dict,
    *,
    ccode: str,
) -> dict:
    return {
        "ccode": ccode,
        "id": league_id,
        "internalRank": 1,
        "matches": [match],
        "name": name,
        "primaryId": primary_id,
        "simpleLeague": False,
    }


def _bundle(*, date: str = "20260822", leagues: list[dict] | None = None):
    if leagues is None:
        leagues = [
            _league(
                10,
                10,
                "Premier League",
                _match(1001, 10, "Arsenal", "Leeds United", 14, date=date),
                ccode="ENG",
            ),
            _league(
                20,
                20,
                "Unknown Saturday League",
                _match(1002, 20, "Alpha", "Beta", 16, date=date),
                ccode="ENG",
            ),
        ]
    payload = {"date": date, "leagues": leagues}
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
    assert SCHEMA_VERSION == 2
    assert DATASET_NAME == "athena-saturday-2026-08-22-fixture-universe-v2"
    assert TARGET_REQUEST_DATE == "20260822"
    assert REQUEST_TIMEZONE == "UTC"
    assert REQUEST_CCODE3 == "NGA"
    assert TARGET_FOLD_SIZE == 20
    assert safety_flags()
    assert not any(safety_flags().values())


def test_builds_exact_source_identity_priority_inventory_without_inference():
    report = build_saturday_fixture_universe(_bundle())
    assert report["competition_review_priority_policy_version"] == (
        COMPETITION_REVIEW_PRIORITY_POLICY_VERSION
    )
    assert report["candidate_count"] == 2
    assert report["competition_review_source_identity_match_count"] == 1
    assert report["unprioritized_source_competition_count"] == 1
    assert report["prioritized_competition_counts"] == {"Premier League": 1}
    assert report["source_competition_counts"] == {
        "ENG|Premier League": 1,
        "ENG|Unknown Saturday League": 1,
    }
    premier = report["candidates"][0]
    assert premier["competition_review_name"] == "Premier League"
    assert premier["competition_review_rank"] == 1
    assert premier["competition_review_kind"] == CompetitionKind.DOMESTIC_LEAGUE.value
    unknown = report["candidates"][1]
    assert unknown["competition_review_source_identity_match"] is False
    assert unknown["competition_review_rank"] == 999
    assert not any(report["safety"].values())


def test_major_cup_sits_below_portugal_turkey_eredivisie_and_above_belgium_scotland():
    leagues = [
        _league(
            10,
            42,
            "DFB Pokal",
            _match(1301, 10, "Wehen Wiesbaden", "Leverkusen", 11),
            ccode="GER",
        ),
        _league(
            20,
            57,
            "Eredivisie",
            _match(1302, 20, "Ajax", "Utrecht", 12),
            ccode="NED",
        ),
        _league(
            30,
            61,
            "Liga Portugal",
            _match(1303, 30, "Benfica", "Braga", 13),
            ccode="POR",
        ),
        _league(
            40,
            71,
            "Super Lig",
            _match(1304, 40, "Galatasaray", "Trabzonspor", 14),
            ccode="TUR",
        ),
        _league(
            50,
            40,
            "Belgian Pro League",
            _match(1305, 50, "Genk", "Gent", 15),
            ccode="BEL",
        ),
        _league(
            60,
            64,
            "Premiership",
            _match(1306, 60, "Rangers", "St. Mirren", 16),
            ccode="SCO",
        ),
    ]
    report = build_saturday_fixture_universe(_bundle(leagues=leagues))
    assert [item["competition_review_name"] for item in report["candidates"]] == [
        "Primeira Liga",
        "Süper Lig",
        "Eredivisie",
        "DFB-Pokal",
        "Belgian Pro League",
        "Scottish Premiership",
    ]
    assert [item["competition_review_rank"] for item in report["candidates"]] == [
        6,
        7,
        8,
        9,
        10,
        11,
    ]
    cup = next(item for item in report["candidates"] if item["competition_review_name"] == "DFB-Pokal")
    assert cup["competition_review_kind"] == CompetitionKind.DOMESTIC_CUP.value


def test_unreviewed_cup_is_not_promoted_because_it_is_a_cup():
    leagues = [
        _league(
            10,
            999,
            "Super Cup",
            _match(1401, 10, "Team A", "Team B", 15),
            ccode="GER",
        )
    ]
    report = build_saturday_fixture_universe(_bundle(leagues=leagues))
    item = report["candidates"][0]
    assert item["competition_review_source_identity_match"] is False
    assert item["competition_review_rank"] == 999
    assert report["prioritized_competition_counts"] == {}


def test_generic_same_name_foreign_competitions_do_not_borrow_priority():
    leagues = [
        _league(10, 263, "Premier League", _match(1101, 10, "Belshina", "Gomel", 11), ccode="BLR"),
        _league(20, 246, "Serie A", _match(1102, 20, "Cuenca", "Manta", 13), ccode="ECU"),
        _league(30, 38, "Bundesliga", _match(1103, 30, "Altach", "Hartberg", 15), ccode="AUT"),
        _league(40, 47, "Premier League", _match(1104, 40, "Everton", "Palace", 16), ccode="ENG"),
    ]
    report = build_saturday_fixture_universe(_bundle(leagues=leagues))
    assert report["competition_review_source_identity_match_count"] == 1
    assert report["unprioritized_source_competition_count"] == 3
    assert report["prioritized_competition_counts"] == {"Premier League": 1}
    foreign = [
        item for item in report["candidates"] if item["source_competition_ccode"] != "ENG"
    ]
    assert all(item["competition_review_rank"] == 999 for item in foreign)


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
