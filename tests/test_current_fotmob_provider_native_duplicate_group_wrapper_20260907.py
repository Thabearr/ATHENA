from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json

import pytest

import domain.current_fotmob_provider_native_qualification as current


UTC = dt.timezone.utc
MANIFEST_SHA = current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260907_SOURCE_MANIFEST_SHA256


def _match(*, fixture_id: int, home_id: int, away_id: int, kickoff: str):
    return {
        "id": fixture_id,
        "leagueId": current.REVIEWED_DUPLICATE_GROUP_WRAPPER_ID,
        "home": {"id": home_id},
        "away": {"id": away_id},
        "status": {"utcTime": kickoff},
    }


def _wrapper(*, group_name: str, name: str, matches: list[dict]):
    return {
        "isGroup": True,
        "groupName": group_name,
        "ccode": "INT",
        "id": current.REVIEWED_DUPLICATE_GROUP_WRAPPER_ID,
        "primaryId": current.REVIEWED_DUPLICATE_GROUP_PRIMARY_ID,
        "name": name,
        "matches": matches,
        "parentLeagueName": current.REVIEWED_DUPLICATE_GROUP_PARENT_LEAGUE_NAME,
        "internalRank": 0,
        "simpleLeague": False,
    }


def _payload():
    return {
        "leagues": [
            _wrapper(
                group_name="E",
                name="Women's World Cup U20 Grp. E",
                matches=[
                    _match(
                        fixture_id=5_852_065,
                        home_id=1_619_799,
                        away_id=2_058_045,
                        kickoff="2026-09-07T13:00:00.000Z",
                    ),
                    _match(
                        fixture_id=5_852_066,
                        home_id=1_459_893,
                        away_id=1_459_884,
                        kickoff="2026-09-07T16:00:00.000Z",
                    ),
                ],
            ),
            _wrapper(
                group_name="F",
                name="Women's World Cup U20 Grp. F",
                matches=[
                    _match(
                        fixture_id=5_852_058,
                        home_id=2_058_053,
                        away_id=1_619_796,
                        kickoff="2026-09-07T13:00:00.000Z",
                    ),
                    _match(
                        fixture_id=5_852_059,
                        home_id=1_459_878,
                        away_id=1_459_882,
                        kickoff="2026-09-07T16:00:00.000Z",
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


def _qualify(payload: dict, *, request_date: str):
    raw = _raw(payload)
    raw_sha = hashlib.sha256(raw).hexdigest()
    return current._qualify_reviewed_duplicate_group_wrapper_payload(
        raw,
        capture_observed_at=dt.datetime(2026, 9, 5, 13, 12, 11, tzinfo=UTC),
        capture_manifest_sha256=MANIFEST_SHA,
        capture_raw_sha256=raw_sha,
        request_date=request_date,
    ), raw_sha


def test_reviewed_20260907_evidence_pins_exact_terminal_run():
    assert current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260907_SOURCE_RUN_ID == 33966871886
    assert current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260907_SOURCE_ARTIFACT_ID == 9970740888
    assert (
        current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260907_SOURCE_ARTIFACT_SHA256
        == "eb67df35875642f7422b6da3e3d04ef89fecd03b6288af17a17d92631ce350aa"
    )
    assert (
        current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260907_SOURCE_MANIFEST_SHA256
        == "77a503f509285a169c542bd3b625916a73ef844e3c2de5ddb3c1958c11279361"
    )
    assert (
        current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260907_SOURCE_RAW_SHA256
        == "2c5f0108a0ce2bcb94e85127256547c5ddb1608291a4f9ade3a459121f801861"
    )


def test_reviewed_20260907_group_e_f_wrapper_preserves_original_capture_identity():
    rows, raw_sha = _qualify(
        _payload(),
        request_date=current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260907_REQUEST_DATE,
    )

    assert [row.fixture_id for row in rows] == [
        5_852_058,
        5_852_065,
        5_852_059,
        5_852_066,
    ]
    assert {row.wrapper_id for row in rows} == {
        current.REVIEWED_DUPLICATE_GROUP_WRAPPER_ID
    }
    assert {row.provider_primary_id for row in rows} == {
        current.REVIEWED_DUPLICATE_GROUP_PRIMARY_ID
    }
    assert all(row.capture_raw_sha256 == raw_sha for row in rows)
    assert all(row.capture_manifest_sha256 == MANIFEST_SHA for row in rows)


def test_reviewed_20260907_group_e_f_wrapper_labels_are_exact_not_fuzzy():
    payload = _payload()
    payload["leagues"][0]["groupName"] = "E "

    with pytest.raises(
        current.CurrentFotMobProviderNativeQualificationError,
        match="label pairing changed",
    ):
        _qualify(
            payload,
            request_date=current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260907_REQUEST_DATE,
        )


def test_reviewed_20260907_group_shape_cannot_escape_its_exact_request_date():
    with pytest.raises(
        current.CurrentFotMobProviderNativeQualificationError,
        match="escaped exact request date",
    ):
        _qualify(
            _payload(),
            request_date=current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260906_REQUEST_DATE,
        )


def test_reviewed_20260907_group_e_f_wrapper_cannot_expand_to_third_group():
    payload = _payload()
    third = copy.deepcopy(payload["leagues"][1])
    third["groupName"] = "G"
    third["name"] = "Women's World Cup U20 Grp. G"
    third["matches"][0]["id"] = 5_852_099
    payload["leagues"].append(third)

    with pytest.raises(
        current.CurrentFotMobProviderNativeQualificationError,
        match="occurrence count changed",
    ):
        _qualify(
            payload,
            request_date=current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260907_REQUEST_DATE,
        )


def test_reviewed_20260907_group_e_f_wrapper_metadata_still_fails_closed():
    payload = _payload()
    payload["leagues"][1]["simpleLeague"] = True

    with pytest.raises(
        current.CurrentFotMobProviderNativeQualificationError,
        match="opaque metadata changed",
    ):
        _qualify(
            payload,
            request_date=current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260907_REQUEST_DATE,
        )
