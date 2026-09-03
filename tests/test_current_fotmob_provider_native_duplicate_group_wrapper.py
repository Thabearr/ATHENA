from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json

import pytest

import domain.current_fotmob_provider_native_qualification as current


UTC = dt.timezone.utc
MANIFEST_SHA = "1" * 64


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
                group_name="A",
                name="Women's World Cup U20 Grp. A",
                matches=[
                    _match(
                        fixture_id=5_849_638,
                        home_id=2_057_970,
                        away_id=2_057_964,
                        kickoff="2026-09-05T13:00:00.000Z",
                    )
                ],
            ),
            _wrapper(
                group_name="B",
                name="Women's World Cup U20 Grp. B",
                matches=[
                    _match(
                        fixture_id=5_849_963,
                        home_id=1_459_880,
                        away_id=2_058_007,
                        kickoff="2026-09-05T13:00:00.000Z",
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


def _qualify(payload: dict):
    raw = _raw(payload)
    raw_sha = hashlib.sha256(raw).hexdigest()
    return current._qualify_reviewed_duplicate_group_wrapper_payload(
        raw,
        capture_observed_at=dt.datetime(2026, 9, 3, 17, 57, 49, tzinfo=UTC),
        capture_manifest_sha256=MANIFEST_SHA,
        capture_raw_sha256=raw_sha,
        request_date=current.REVIEWED_DUPLICATE_GROUP_WRAPPER_REQUEST_DATE,
    ), raw_sha


def test_reviewed_duplicate_group_wrapper_preserves_original_capture_identity():
    rows, raw_sha = _qualify(_payload())

    assert [row.fixture_id for row in rows] == [5_849_638, 5_849_963]
    assert {row.wrapper_id for row in rows} == {
        current.REVIEWED_DUPLICATE_GROUP_WRAPPER_ID
    }
    assert {row.provider_primary_id for row in rows} == {
        current.REVIEWED_DUPLICATE_GROUP_PRIMARY_ID
    }
    assert all(row.capture_raw_sha256 == raw_sha for row in rows)
    assert all(row.capture_manifest_sha256 == MANIFEST_SHA for row in rows)


def test_unreviewed_duplicate_wrapper_id_still_fails_closed():
    payload = _payload()
    for league in payload["leagues"]:
        league["id"] = 99_999
        league["primaryId"] = 99_999
        for match in league["matches"]:
            match["leagueId"] = 99_999

    with pytest.raises(
        current.CurrentFotMobProviderNativeQualificationError,
        match="unreviewed duplicate competition wrapper id",
    ):
        _qualify(payload)


def test_reviewed_duplicate_wrapper_cannot_expand_to_third_group():
    payload = _payload()
    third = copy.deepcopy(payload["leagues"][1])
    third["groupName"] = "C"
    third["name"] = "Women's World Cup U20 Grp. C"
    third["matches"][0]["id"] = 5_849_999
    payload["leagues"].append(third)

    with pytest.raises(
        current.CurrentFotMobProviderNativeQualificationError,
        match="occurrence count changed",
    ):
        _qualify(payload)


def test_reviewed_duplicate_wrapper_labels_are_exact_not_fuzzy():
    payload = _payload()
    payload["leagues"][1]["groupName"] = "B "

    with pytest.raises(
        current.CurrentFotMobProviderNativeQualificationError,
        match="groupName set changed",
    ):
        _qualify(payload)


def test_reviewed_duplicate_wrapper_still_rejects_duplicate_fixture_identity():
    payload = _payload()
    payload["leagues"][1]["matches"][0]["id"] = 5_849_638

    with pytest.raises(
        current.CurrentFotMobProviderNativeQualificationError,
        match="fixture id duplicated in one capture",
    ):
        _qualify(payload)


def test_reviewed_duplicate_wrapper_is_bound_to_exact_request_date():
    payload = _payload()
    raw = _raw(payload)

    with pytest.raises(
        current.CurrentFotMobProviderNativeQualificationError,
        match="escaped exact request date",
    ):
        current._qualify_reviewed_duplicate_group_wrapper_payload(
            raw,
            capture_observed_at=dt.datetime(2026, 9, 3, 17, 57, 49, tzinfo=UTC),
            capture_manifest_sha256=MANIFEST_SHA,
            capture_raw_sha256=hashlib.sha256(raw).hexdigest(),
            request_date="20260906",
        )
