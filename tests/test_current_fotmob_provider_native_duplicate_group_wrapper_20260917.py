from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json

import pytest

import domain.current_fotmob_provider_native_qualification as current


UTC = dt.timezone.utc
MANIFEST_SHA = (
    current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260917_SOURCE_MANIFEST_SHA256
)


def _match(*, fixture_id: int, home_id: int, away_id: int, kickoff: str) -> dict:
    return {
        "id": fixture_id,
        "leagueId": current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260916_ID,
        "home": {"id": home_id},
        "away": {"id": away_id},
        "status": {"utcTime": kickoff},
    }


def _wrapper(*, group_name: str, name: str, matches: list[dict]) -> dict:
    return {
        "ccode": "INT",
        "groupName": group_name,
        "id": current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260916_ID,
        "internalRank": 0,
        "isGroup": True,
        "matches": matches,
        "name": name,
        "parentLeagueId": current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260916_PARENT_LEAGUE_ID,
        "parentLeagueName": current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260916_PARENT_LEAGUE_NAME,
        "primaryId": current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260916_PRIMARY_ID,
        "simpleLeague": False,
    }


def _payload() -> dict:
    return {
        "leagues": [
            _wrapper(
                group_name="F",
                name="AFC Champions League Two F",
                matches=[
                    _match(fixture_id=6_054_751, home_id=67_366, away_id=165_250, kickoff="2026-09-17T10:00:00.000Z"),
                    _match(fixture_id=6_054_750, home_id=8_008, away_id=165_169, kickoff="2026-09-17T10:00:00.000Z"),
                ],
            ),
            _wrapper(
                group_name="G",
                name="AFC Champions League Two G",
                matches=[
                    _match(fixture_id=6_054_832, home_id=194_011, away_id=542_025, kickoff="2026-09-17T10:00:00.000Z"),
                    _match(fixture_id=6_054_833, home_id=6_628, away_id=67_386, kickoff="2026-09-17T12:15:00.000Z"),
                ],
            ),
            _wrapper(
                group_name="H",
                name="AFC Champions League Two H",
                matches=[
                    _match(fixture_id=6_054_844, home_id=165_165, away_id=164_734, kickoff="2026-09-17T12:15:00.000Z"),
                    _match(fixture_id=6_054_845, home_id=202_520, away_id=1_114_226, kickoff="2026-09-17T12:15:00.000Z"),
                ],
            ),
        ]
    }


def _raw(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _qualify(payload: dict, *, request_date: str = "20260917"):
    raw = _raw(payload)
    raw_sha = hashlib.sha256(raw).hexdigest()
    return current._qualify_reviewed_duplicate_group_wrapper_payload(
        raw,
        capture_observed_at=dt.datetime(2026, 9, 13, tzinfo=UTC),
        capture_manifest_sha256=MANIFEST_SHA,
        capture_raw_sha256=raw_sha,
        request_date=request_date,
    ), raw_sha


def _fails(payload: dict, *, match: str, request_date: str = "20260917") -> None:
    with pytest.raises(
        current.CurrentFotMobProviderNativeQualificationError,
        match=match,
    ):
        _qualify(payload, request_date=request_date)


def test_reviewed_20260917_evidence_pins_and_exact_fgh_shape():
    assert current.REVIEWED_DUPLICATE_GROUP_WRAPPER_COMPATIBILITY_ID == (
        "CURRENT_FOTMOB_REVIEWED_DUPLICATE_GROUP_WRAPPER_20260905_20260906_"
        "20260907_20260916_20260917_V5"
    )
    assert current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260917_SOURCE_RUN_ID == 34761226581
    assert current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260917_SOURCE_ARTIFACT_ID == 10319156348
    assert current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260917_SOURCE_ARTIFACT_SHA256 == "690c3e2c2e17fff7589ed7305abbc608dc19f3ede0bb09c82319a9d4476d1c40"
    assert current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260917_SOURCE_RAW_SHA256 == "714b9a570fc47f852de00b52ff6aa1d380723c8ce465a4d934909b49a0bdb0f4"
    assert current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260917_SOURCE_MANIFEST_SHA256 == "d4552fd99683bd078241d6730bbe851cd76902e4e469a250022aa2a58cc46dee"
    assert current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260917_SOURCE_OBSERVED_AT == "2026-09-13T13:56:40.410882Z"
    assert current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260917_REQUEST_DATE == "20260917"
    assert current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260917_OCCURRENCE_COUNT == 3
    assert current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260917_LABEL_PAIRS == (
        ("F", "AFC Champions League Two F"),
        ("G", "AFC Champions League Two G"),
        ("H", "AFC Champions League Two H"),
    )

    rows, raw_sha = _qualify(_payload())
    assert [row.fixture_id for row in rows] == [
        6_054_750,
        6_054_751,
        6_054_832,
        6_054_833,
        6_054_844,
        6_054_845,
    ]
    assert {row.wrapper_id for row in rows} == {
        current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260916_ID
    }
    assert {row.provider_primary_id for row in rows} == {
        current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260916_PRIMARY_ID
    }
    assert all(row.capture_raw_sha256 == raw_sha for row in rows)
    assert all(row.capture_manifest_sha256 == MANIFEST_SHA for row in rows)


def test_reviewed_20260917_shape_is_jointly_bound_to_date_and_labels():
    _fails(_payload(), request_date="20260918", match="escaped exact request date")

    acde = _payload()
    for league, group_name in zip(acde["leagues"], ("A", "C", "D"), strict=True):
        league["groupName"] = group_name
        league["name"] = f"AFC Champions League Two {group_name}"
    _fails(acde, match="label pairing changed")

    _fails(_payload(), request_date="20260916", match="occurrence count changed")


def test_reviewed_20260917_shape_requires_exactly_three_wrappers():
    payload = _payload()
    payload["leagues"].pop()
    _fails(payload, match="occurrence count changed")

    payload = _payload()
    fourth = copy.deepcopy(payload["leagues"][0])
    fourth["groupName"] = "I"
    fourth["name"] = "AFC Champions League Two I"
    payload["leagues"].append(fourth)
    _fails(payload, match="occurrence count changed")


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda payload: payload["leagues"][0].__setitem__("groupName", "F "), "label pairing changed"),
        (lambda payload: payload["leagues"][0].__setitem__("name", "AFC Champions League Two G"), "label pairing changed"),
        (lambda payload: payload["leagues"][0].__setitem__("primaryId", 9470), "primaryId changed"),
        (lambda payload: payload["leagues"][0].__setitem__("parentLeagueId", 9470), "parentLeagueId changed"),
        (lambda payload: payload["leagues"][0].__setitem__("parentLeagueName", "AFC Champions League Three"), "parentLeagueName changed"),
        (lambda payload: payload["leagues"][0].__setitem__("ccode", "NGA"), "ccode changed"),
        (lambda payload: payload["leagues"][0].__setitem__("isGroup", False), "isGroup=true"),
        (lambda payload: payload["leagues"][0].__setitem__("internalRank", 1), "opaque metadata changed"),
        (lambda payload: payload["leagues"][0].__setitem__("simpleLeague", True), "opaque metadata changed"),
        (lambda payload: payload["leagues"][0].__setitem__("unexpected", True), "key set changed"),
        (lambda payload: payload["leagues"][0].pop("parentLeagueId"), "key set changed"),
        (lambda payload: payload["leagues"][1].__setitem__("parentLeagueId", 9470), "parentLeagueId changed"),
    ],
)
def test_reviewed_20260917_wrapper_fields_fail_closed(mutate, match):
    payload = _payload()
    mutate(payload)
    _fails(payload, match=match)


def test_reviewed_20260917_reuses_strict_fixture_replay():
    payload = _payload()
    payload["leagues"][1]["matches"][0]["id"] = payload["leagues"][0]["matches"][0]["id"]
    _fails(payload, match="fixture id duplicated")

    payload = _payload()
    payload["leagues"][0]["matches"][0]["leagueId"] = 1
    _fails(payload, match="does not equal")


def test_reviewed_20260917_rejects_unreviewed_or_mixed_duplicate_sets():
    payload = _payload()
    payload["leagues"].extend([{"id":777}, {"id":777}])
    _fails(payload, match="unreviewed duplicate competition wrapper id")

    payload = _payload()
    payload["leagues"].extend([{"id":10_369}, {"id":10_369}])
    _fails(payload, match="unreviewed duplicate competition wrapper id")
