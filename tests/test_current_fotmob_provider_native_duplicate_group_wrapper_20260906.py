from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json

import pytest

import domain.current_fotmob_provider_native_qualification as current


UTC = dt.timezone.utc
MANIFEST_SHA = "2" * 64


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
                group_name="C",
                name="Women's World Cup U20 Grp. C",
                matches=[
                    _match(
                        fixture_id=5_849_977,
                        home_id=1_459_883,
                        away_id=1_459_887,
                        kickoff="2026-09-06T13:00:00.000Z",
                    )
                ],
            ),
            _wrapper(
                group_name="D",
                name="Women's World Cup U20 Grp. D",
                matches=[
                    _match(
                        fixture_id=5_852_049,
                        home_id=1_459_879,
                        away_id=1_459_889,
                        kickoff="2026-09-06T13:00:00.000Z",
                    )
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
        capture_observed_at=dt.datetime(2026, 9, 4, 2, 30, 0, tzinfo=UTC),
        capture_manifest_sha256=MANIFEST_SHA,
        capture_raw_sha256=raw_sha,
        request_date=request_date,
    ), raw_sha


def test_reviewed_20260906_group_c_d_wrapper_preserves_original_capture_identity():
    rows, raw_sha = _qualify(
        _payload(),
        request_date=current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260906_REQUEST_DATE,
    )

    assert [row.fixture_id for row in rows] == [5_849_977, 5_852_049]
    assert {row.wrapper_id for row in rows} == {
        current.REVIEWED_DUPLICATE_GROUP_WRAPPER_ID
    }
    assert {row.provider_primary_id for row in rows} == {
        current.REVIEWED_DUPLICATE_GROUP_PRIMARY_ID
    }
    assert all(row.capture_raw_sha256 == raw_sha for row in rows)
    assert all(row.capture_manifest_sha256 == MANIFEST_SHA for row in rows)


def test_reviewed_20260906_group_c_d_wrapper_labels_are_exact_not_fuzzy():
    payload = _payload()
    payload["leagues"][0]["groupName"] = "C "

    with pytest.raises(
        current.CurrentFotMobProviderNativeQualificationError,
        match="label pairing changed",
    ):
        _qualify(
            payload,
            request_date=current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260906_REQUEST_DATE,
        )


def test_reviewed_group_shape_cannot_escape_its_exact_request_date():
    with pytest.raises(
        current.CurrentFotMobProviderNativeQualificationError,
        match="escaped exact request date",
    ):
        _qualify(
            _payload(),
            request_date=current.REVIEWED_DUPLICATE_GROUP_WRAPPER_REQUEST_DATE,
        )


def test_reviewed_20260906_group_c_d_wrapper_cannot_expand_to_third_group():
    payload = _payload()
    third = copy.deepcopy(payload["leagues"][1])
    third["groupName"] = "E"
    third["name"] = "Women's World Cup U20 Grp. E"
    third["matches"][0]["id"] = 5_852_099
    payload["leagues"].append(third)

    with pytest.raises(
        current.CurrentFotMobProviderNativeQualificationError,
        match="occurrence count changed",
    ):
        _qualify(
            payload,
            request_date=current.REVIEWED_DUPLICATE_GROUP_WRAPPER_20260906_REQUEST_DATE,
        )
