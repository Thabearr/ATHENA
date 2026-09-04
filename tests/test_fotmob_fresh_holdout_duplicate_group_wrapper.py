from __future__ import annotations

import copy
import datetime as dt
import json

import pytest

import domain.fotmob_data_matches_capture as capture_contract
import domain.fotmob_fresh_holdout_capture_qualification_adapter as adapter
import domain.fotmob_utc_native_expected_goals_fresh_holdout as fresh


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


def _manifest(raw: bytes, *, request_date: str = "20260905"):
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
        request_date=request_date,
        timezone="UTC",
        ccode3="NGA",
    )


def _match(
    *,
    fixture_id: int,
    home_id: int,
    away_id: int,
    kickoff: str,
    display_time: str,
    timestamp_ms: int,
) -> dict:
    return {
        "id": fixture_id,
        "leagueId": adapter.REVIEWED_DUPLICATE_GROUP_WRAPPER_ID,
        "time": display_time,
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
            "utcTime": kickoff,
            "halfs": {"firstHalfStarted": display_time + ":00"},
            "periodLength": 45,
            "started": False,
            "cancelled": False,
            "finished": False,
        },
        "timeTS": timestamp_ms,
    }


def _wrapper(*, group_name: str, name: str, matches: list[dict]) -> dict:
    return {
        "isGroup": True,
        "groupName": group_name,
        "ccode": "INT",
        "id": adapter.REVIEWED_DUPLICATE_GROUP_WRAPPER_ID,
        "primaryId": adapter.REVIEWED_DUPLICATE_GROUP_PRIMARY_ID,
        "name": name,
        "matches": matches,
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
                matches=[
                    _match(
                        fixture_id=5_849_638,
                        home_id=2_057_970,
                        away_id=2_057_964,
                        kickoff="2026-09-05T13:00:00.000Z",
                        display_time="05.09.2026 15:00",
                        timestamp_ms=1_788_613_200_000,
                    ),
                    _match(
                        fixture_id=5_849_639,
                        home_id=2_057_966,
                        away_id=2_057_968,
                        kickoff="2026-09-05T16:00:00.000Z",
                        display_time="05.09.2026 18:00",
                        timestamp_ms=1_788_624_000_000,
                    ),
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
                        display_time="05.09.2026 15:00",
                        timestamp_ms=1_788_613_200_000,
                    ),
                    _match(
                        fixture_id=5_849_964,
                        home_id=2_058_009,
                        away_id=2_058_010,
                        kickoff="2026-09-05T16:00:00.000Z",
                        display_time="05.09.2026 18:00",
                        timestamp_ms=1_788_624_000_000,
                    ),
                ],
            ),
        ],
    }


def test_reviewed_duplicate_group_wrapper_qualifies_without_merging_group_labels():
    payload = _payload()
    raw = _raw(payload)
    manifest = _manifest(raw)

    with pytest.raises(fresh.FotMobFreshHoldoutError):
        fresh.qualify_capture_fixtures(raw, manifest)

    rows = adapter.qualify_capture_fixtures(raw, manifest)

    assert [row.fixture_id for row in rows] == [
        5_849_638,
        5_849_963,
        5_849_639,
        5_849_964,
    ]
    assert {row.wrapper_id for row in rows} == {10369}
    assert {row.provider_primary_id for row in rows} == {10369}
    assert all(row.capture_raw_sha256 == manifest.raw_sha256 for row in rows)
    assert all(
        row.capture_manifest_sha256
        == capture_contract.sha256_data_matches_capture_manifest(manifest)
        for row in rows
    )

    partitions = adapter._partition_reviewed_duplicate_group_structural_payloads(
        payload,
        request_date="20260905",
    )
    assert len(partitions) == 2
    assert [part[0]["leagues"][0]["groupName"] for part in partitions] == ["A", "B"]
    assert all(len(part[0]["leagues"]) == 1 for part in partitions)


def test_unreviewed_duplicate_wrapper_id_still_fails_closed():
    payload = _payload()
    for league in payload["leagues"]:
        league["id"] = 99_999
        league["primaryId"] = 99_999
        for match in league["matches"]:
            match["leagueId"] = 99_999
    raw = _raw(payload)

    with pytest.raises(
        adapter.FreshHoldoutCaptureQualificationAdapterError,
        match="unreviewed duplicate competition wrapper id",
    ):
        adapter.qualify_capture_fixtures(raw, _manifest(raw))


def test_reviewed_duplicate_wrapper_occurrence_count_and_labels_are_exact():
    payload = _payload()
    third = copy.deepcopy(payload["leagues"][1])
    third["groupName"] = "C"
    third["name"] = "Women's World Cup U20 Grp. C"
    third["matches"][0]["id"] = 5_849_999
    third["matches"][1]["id"] = 5_850_000
    payload["leagues"].append(third)
    raw = _raw(payload)
    with pytest.raises(
        adapter.FreshHoldoutCaptureQualificationAdapterError,
        match="occurrence count changed",
    ):
        adapter.qualify_capture_fixtures(raw, _manifest(raw))

    payload = _payload()
    payload["leagues"][1]["groupName"] = "B "
    raw = _raw(payload)
    with pytest.raises(
        adapter.FreshHoldoutCaptureQualificationAdapterError,
        match="label pairing changed",
    ):
        adapter.qualify_capture_fixtures(raw, _manifest(raw))


def test_reviewed_duplicate_wrapper_group_name_pairing_cannot_cross():
    payload = _payload()
    payload["leagues"][0]["name"], payload["leagues"][1]["name"] = (
        payload["leagues"][1]["name"],
        payload["leagues"][0]["name"],
    )
    raw = _raw(payload)

    with pytest.raises(
        adapter.FreshHoldoutCaptureQualificationAdapterError,
        match="label pairing changed",
    ):
        adapter.qualify_capture_fixtures(raw, _manifest(raw))


def test_reviewed_duplicate_wrapper_still_rejects_duplicate_fixture_id():
    payload = _payload()
    payload["leagues"][1]["matches"][0]["id"] = 5_849_638
    raw = _raw(payload)

    with pytest.raises(
        adapter.FreshHoldoutCaptureQualificationAdapterError,
        match="fixture id duplicated",
    ):
        adapter.qualify_capture_fixtures(raw, _manifest(raw))


def test_reviewed_duplicate_wrapper_is_bound_to_exact_request_date():
    payload = _payload()
    with pytest.raises(
        adapter.FreshHoldoutCaptureQualificationAdapterError,
        match="escaped exact request date",
    ):
        adapter._reviewed_duplicate_group_wrapper_present(
            payload,
            request_date="20260906",
        )


def test_reviewed_duplicate_wrapper_cannot_mix_with_spillover_policy():
    payload = _payload()
    match = payload["leagues"][0]["matches"][0]
    match["status"]["utcTime"] = "2026-09-04T23:30:00.000Z"
    match["timeTS"] = 1_788_564_600_000
    match["time"] = "05.09.2026 01:30"
    match["status"]["halfs"]["firstHalfStarted"] = "05.09.2026 01:30:00"
    raw = _raw(payload)

    with pytest.raises(
        adapter.FreshHoldoutCaptureQualificationAdapterError,
        match="cannot combine with previous-day spillover",
    ):
        adapter.qualify_capture_fixtures(raw, _manifest(raw))


def test_duplicate_group_receipt_binds_exact_failure_evidence_and_no_authority():
    receipt = adapter.adapter_receipt()
    assert receipt["adapter_id"] == "FOTMOB_FRESH_HOLDOUT_REVIEWED_SCHEMA_ADAPTER_V2"
    assert receipt["duplicate_group_source_workflow_run_id"] == 33823663641
    assert receipt["duplicate_group_source_actions_artifact_id"] == 9919255715
    assert receipt["duplicate_group_source_actions_artifact_sha256"] == (
        "792ddba3b8f4b38bc494f8d0a660a80dceb5c8c9f2a9bcdaf88cbba43ac5f43a"
    )
    assert receipt["duplicate_group_source_manifest_sha256"] == (
        "e34365e25fce42c7106e9c54b0fc1df77a97311cb499a5895c6322c8d7bb8781"
    )
    assert receipt["duplicate_group_source_raw_sha256"] == (
        "a19c50ca3c3e7c9c57d83f2b83a43d1cc3d75c92b9a788f25d74473de3ed0b19"
    )
    assert receipt["duplicate_group_request_date"] == "20260905"
    assert receipt["duplicate_group_wrapper_id"] == 10369
    assert receipt["duplicate_group_primary_id"] == 10369
    assert receipt["duplicate_group_label_pairs"] == [
        ["A", "Women's World Cup U20 Grp. A"],
        ["B", "Women's World Cup U20 Grp. B"],
    ]
    assert receipt["duplicate_group_wrappers_structurally_revalidated_separately"] is True
    assert receipt["duplicate_group_labels_not_merged_or_semantically_interpreted"] is True
    assert receipt["compatibility_projection_is_not_source_evidence"] is True
    assert all(value is False for value in receipt["safety"].values())
