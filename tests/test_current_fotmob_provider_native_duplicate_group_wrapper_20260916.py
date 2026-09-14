from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json

import pytest

import domain.current_fotmob_provider_native_qualification as current


UTC = dt.timezone.utc
MANIFEST_SHA = (
    current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260916_SOURCE_MANIFEST_SHA256
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
        "parentLeagueId": (
            current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260916_PARENT_LEAGUE_ID
        ),
        "parentLeagueName": (
            current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260916_PARENT_LEAGUE_NAME
        ),
        "primaryId": current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260916_PRIMARY_ID,
        "simpleLeague": False,
    }


def _payload() -> dict:
    return {
        "leagues": [
            _wrapper(
                group_name="E",
                name="AFC Champions League Two E",
                matches=[
                    _match(
                        fixture_id=6_136_069,
                        home_id=92_630,
                        away_id=165_196,
                        kickoff="2026-09-16T10:00:00.000Z",
                    ),
                    _match(
                        fixture_id=6_054_692,
                        home_id=743_070,
                        away_id=6_230,
                        kickoff="2026-09-16T12:15:00.000Z",
                    ),
                ],
            ),
            _wrapper(
                group_name="A",
                name="AFC Champions League Two A",
                matches=[
                    _match(
                        fixture_id=6_054_373,
                        home_id=102_122,
                        away_id=101_713,
                        kickoff="2026-09-16T16:00:00.000Z",
                    ),
                    _match(
                        fixture_id=6_054_372,
                        home_id=1_288_463,
                        away_id=102_153,
                        kickoff="2026-09-16T16:00:00.000Z",
                    ),
                ],
            ),
            _wrapper(
                group_name="C",
                name="AFC Champions League Two C",
                matches=[
                    _match(
                        fixture_id=6_054_493,
                        home_id=101_748,
                        away_id=205_686,
                        kickoff="2026-09-16T16:00:00.000Z",
                    ),
                    _match(
                        fixture_id=6_054_494,
                        home_id=101_898,
                        away_id=101_665,
                        kickoff="2026-09-16T18:15:00.000Z",
                    ),
                ],
            ),
            _wrapper(
                group_name="D",
                name="AFC Champions League Two D",
                matches=[
                    _match(
                        fixture_id=6_054_508,
                        home_id=101_688,
                        away_id=165_184,
                        kickoff="2026-09-16T16:00:00.000Z",
                    ),
                    _match(
                        fixture_id=6_054_509,
                        home_id=101_655,
                        away_id=101_759,
                        kickoff="2026-09-16T18:15:00.000Z",
                    ),
                ],
            ),
        ]
    }


def _raw(payload: dict) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _qualify(payload: dict, *, request_date: str = "20260916"):
    raw = _raw(payload)
    raw_sha = hashlib.sha256(raw).hexdigest()
    return current._qualify_reviewed_duplicate_group_wrapper_payload(
        raw,
        capture_observed_at=dt.datetime(2026, 9, 12, 23, 46, 59, tzinfo=UTC),
        capture_manifest_sha256=MANIFEST_SHA,
        capture_raw_sha256=raw_sha,
        request_date=request_date,
    ), raw_sha


def _fails(payload: dict, *, match: str, request_date: str = "20260916") -> None:
    with pytest.raises(
        current.CurrentFotMobProviderNativeQualificationError,
        match=match,
    ):
        _qualify(payload, request_date=request_date)


def test_reviewed_20260916_evidence_pins_exact_fresh_diagnostic():
    assert current.REVIEWED_DUPLICATE_GROUP_WRAPPER_COMPATIBILITY_ID == (
        "CURRENT_FOTMOB_REVIEWED_DUPLICATE_GROUP_WRAPPER_20260905_20260906_"
        "20260907_20260916_20260917_V5"
    )
    assert current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260916_SOURCE_RUN_ID == 34726297627
    assert (
        current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260916_SOURCE_ARTIFACT_ID
        == 10307887933
    )
    assert (
        current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260916_SOURCE_ARTIFACT_SHA256
        == "5a3d57265916bd6cdcd9de073516fb9100485548656b93f034098d5ec08ac87c"
    )
    assert (
        current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260916_SOURCE_MANIFEST_SHA256
        == "771b64cc425eb83fae82828fa27c37ebb111056864c169288bd708bbc8ea9ba5"
    )
    assert (
        current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260916_SOURCE_RAW_SHA256
        == "d1584eaa90e32bb56b4c4ccd8b26fd0e7854df2894c7847f075a17367f228944"
    )
    assert (
        current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260916_SOURCE_OBSERVED_AT
        == "2026-09-12T23:46:59.868786Z"
    )
    assert current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260916_REQUEST_DATE == "20260916"


def test_reviewed_20260916_afc_cl_two_shape_preserves_provider_lineage():
    rows, raw_sha = _qualify(_payload())

    assert [row.fixture_id for row in rows] == [
        6_136_069,
        6_054_692,
        6_054_372,
        6_054_373,
        6_054_493,
        6_054_508,
        6_054_494,
        6_054_509,
    ]
    assert {row.wrapper_id for row in rows} == {
        current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260916_ID
    }
    assert {row.provider_primary_id for row in rows} == {
        current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260916_PRIMARY_ID
    }
    assert all(row.capture_raw_sha256 == raw_sha for row in rows)
    assert all(row.capture_manifest_sha256 == MANIFEST_SHA for row in rows)


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda payload: payload["leagues"][1].__setitem__("groupName", "A "), "label pairing changed"),
        (
            lambda payload: payload["leagues"][0].__setitem__(
                "name", "AFC Champions League Two A"
            ),
            "label pairing changed",
        ),
        (
            lambda payload: payload["leagues"][0].__setitem__("primaryId", 9470),
            "primaryId changed",
        ),
        (
            lambda payload: payload["leagues"][0].__setitem__("parentLeagueId", 9470),
            "parentLeagueId changed",
        ),
        (
            lambda payload: payload["leagues"][0].__setitem__(
                "parentLeagueName", "AFC Champions League Three"
            ),
            "parentLeagueName changed",
        ),
        (lambda payload: payload["leagues"][0].__setitem__("ccode", "NGA"), "ccode changed"),
        (lambda payload: payload["leagues"][0].__setitem__("isGroup", False), "isGroup=true"),
        (lambda payload: payload["leagues"][0].__setitem__("internalRank", 1), "opaque metadata changed"),
        (lambda payload: payload["leagues"][0].__setitem__("simpleLeague", True), "opaque metadata changed"),
        (lambda payload: payload["leagues"][0].__setitem__("unexpected", True), "key set changed"),
        (lambda payload: payload["leagues"][0].pop("parentLeagueId"), "key set changed"),
    ],
)
def test_reviewed_20260916_wrapper_fields_fail_closed(mutate, match):
    payload = _payload()
    mutate(payload)
    _fails(payload, match=match)


def test_reviewed_20260916_shape_cannot_escape_exact_request_date():
    _fails(_payload(), request_date="20260917", match="occurrence count changed")


def test_reviewed_20260916_shape_requires_exactly_four_wrappers():
    payload = _payload()
    payload["leagues"].pop()
    _fails(payload, match="occurrence count changed")

    payload = _payload()
    fifth = copy.deepcopy(payload["leagues"][0])
    fifth["groupName"] = "F"
    fifth["name"] = "AFC Champions League Two F"
    payload["leagues"].append(fifth)
    _fails(payload, match="occurrence count changed")


def test_reviewed_20260916_metadata_difference_outside_labels_fails_closed():
    payload = _payload()
    payload["leagues"][3]["parentLeagueId"] = 9470
    _fails(payload, match="parentLeagueId changed")


def test_reviewed_20260916_match_replay_still_rejects_duplicate_fixture_ids():
    payload = _payload()
    payload["leagues"][3]["matches"][1]["id"] = payload["leagues"][0]["matches"][0]["id"]
    _fails(payload, match="fixture id duplicated")


def test_reviewed_20260916_match_replay_still_rejects_wrong_containing_wrapper_id():
    payload = _payload()
    payload["leagues"][0]["matches"][0]["leagueId"] = 1
    _fails(payload, match="does not equal containing")


def test_mixed_duplicate_wrapper_ids_still_fail_at_generic_boundary():
    payload = _payload()
    payload["leagues"].extend([{"id": 10369}, {"id": 10369}])

    _fails(payload, match="unreviewed duplicate competition wrapper id")


def test_another_duplicate_wrapper_id_alongside_20260916_still_fails_closed():
    payload = _payload()
    payload["leagues"].extend([{"id": 777}, {"id": 777}])

    _fails(payload, match="unreviewed duplicate competition wrapper id")
