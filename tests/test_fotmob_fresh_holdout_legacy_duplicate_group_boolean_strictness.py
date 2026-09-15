from __future__ import annotations

import datetime as dt
import json

import pytest

import domain.fotmob_data_matches_capture as capture_contract
import domain.fotmob_fresh_holdout_capture_qualification_adapter as adapter


UTC = dt.timezone.utc
OBSERVED = dt.datetime(2026, 9, 4, 0, 59, 19, 213485, tzinfo=UTC)


def _raw(value: dict) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _manifest(raw: bytes):
    response = capture_contract.CapturedFotMobDataMatchesResponse(
        status=200,
        content_type="application/json; charset=utf-8",
        content_length=len(raw),
        body=raw,
        observed_at=OBSERVED,
        network_acquisition_performed=True,
    )
    return capture_contract.build_data_matches_capture_manifest(
        response,
        request_date="20260905",
        timezone="UTC",
        ccode3="NGA",
    )


def _match(*, fixture_id: int, home_id: int, away_id: int) -> dict:
    return {
        "id": fixture_id,
        "leagueId": adapter.REVIEWED_DUPLICATE_GROUP_WRAPPER_ID,
        "time": "05.09.2026 15:00",
        "home": {
            "id": home_id,
            "score": 0,
            "name": f"Home {home_id}",
            "longName": f"Home {home_id}",
        },
        "away": {
            "id": away_id,
            "score": 0,
            "name": f"Away {away_id}",
            "longName": f"Away {away_id}",
        },
        "eliminatedTeamId": None,
        "statusId": 1,
        "tournamentStage": "1",
        "status": {
            "utcTime": "2026-09-05T13:00:00.000Z",
            "halfs": {"firstHalfStarted": "05.09.2026 15:00:00"},
            "periodLength": 45,
            "started": False,
            "cancelled": False,
            "finished": False,
        },
        "timeTS": 1_788_613_200_000,
    }


def _wrapper(*, group_name: str, name: str, fixture_id: int, home_id: int, away_id: int) -> dict:
    return {
        "isGroup": True,
        "groupName": group_name,
        "ccode": "INT",
        "id": adapter.REVIEWED_DUPLICATE_GROUP_WRAPPER_ID,
        "primaryId": adapter.REVIEWED_DUPLICATE_GROUP_PRIMARY_ID,
        "name": name,
        "matches": [
            _match(
                fixture_id=fixture_id,
                home_id=home_id,
                away_id=away_id,
            )
        ],
        "parentLeagueName": adapter.REVIEWED_DUPLICATE_GROUP_PARENT_LEAGUE_NAME,
        "internalRank": 0,
        "simpleLeague": False,
    }


def _payload() -> dict:
    return {
        "date": "20260905",
        "leagues": [
            _wrapper(
                group_name="A",
                name="Women's World Cup U20 Grp. A",
                fixture_id=5_849_638,
                home_id=2_057_970,
                away_id=2_057_964,
            ),
            _wrapper(
                group_name="B",
                name="Women's World Cup U20 Grp. B",
                fixture_id=5_849_963,
                home_id=1_459_880,
                away_id=2_058_007,
            ),
        ],
    }


@pytest.mark.parametrize(
    ("field", "numeric_bool"),
    (
        ("isGroup", 1),
        ("simpleLeague", 0),
    ),
)
def test_legacy_10369_numeric_boolean_substitutions_fail_closed(
    field: str,
    numeric_bool: int,
) -> None:
    payload = _payload()
    payload["leagues"][0][field] = numeric_bool
    raw = _raw(payload)

    with pytest.raises(
        adapter.FreshHoldoutCaptureQualificationAdapterError,
        match="reviewed PR89->PR87->PR39 structural chain failed",
    ):
        adapter.qualify_capture_fixtures(raw, _manifest(raw))
