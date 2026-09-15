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


def _afc_wrapper(*, group_name: str, name: str, matches: list[dict]) -> dict:
    return {
        "ccode": "INT",
        "groupName": group_name,
        "id": adapter.REVIEWED_AFC_CL2_DUPLICATE_GROUP_WRAPPER_ID,
        "internalRank": 0,
        "isGroup": True,
        "matches": matches,
        "name": name,
        "parentLeagueId": adapter.REVIEWED_AFC_CL2_DUPLICATE_GROUP_PARENT_LEAGUE_ID,
        "parentLeagueName": adapter.REVIEWED_AFC_CL2_DUPLICATE_GROUP_PARENT_LEAGUE_NAME,
        "primaryId": adapter.REVIEWED_AFC_CL2_DUPLICATE_GROUP_PRIMARY_ID,
        "simpleLeague": False,
    }


def _afc_match(*, fixture_id: int, home_id: int, away_id: int, kickoff: str) -> dict:
    kickoff_utc = dt.datetime.fromisoformat(kickoff[:-1] + "+00:00")
    match = _match(
        fixture_id=fixture_id,
        home_id=home_id,
        away_id=away_id,
        kickoff=kickoff,
        display_time=kickoff_utc.strftime("%d.%m.%Y %H:%M"),
        timestamp_ms=int(kickoff_utc.timestamp() * 1_000),
    )
    match["leagueId"] = adapter.REVIEWED_AFC_CL2_DUPLICATE_GROUP_WRAPPER_ID
    return match


def _afc_payload(*, request_date: str) -> dict:
    labels = (
        adapter.REVIEWED_AFC_CL2_DUPLICATE_GROUP_20260916_LABEL_PAIRS
        if request_date == "20260916"
        else adapter.REVIEWED_AFC_CL2_DUPLICATE_GROUP_20260917_LABEL_PAIRS
    )
    kickoff_date = f"{request_date[:4]}-{request_date[4:6]}-{request_date[6:]}"
    wrappers = []
    for index, (group_name, name) in enumerate(labels):
        fixtures = [
            _afc_match(
                fixture_id=6_054_000 + index * 10 + offset,
                home_id=70_000 + index * 10 + offset,
                away_id=80_000 + index * 10 + offset,
                kickoff=f"{kickoff_date}T{10 + offset:02d}:00:00.000Z",
            )
            for offset in range(2)
        ]
        wrappers.append(_afc_wrapper(group_name=group_name, name=name, matches=fixtures))
    return {"date": request_date, "leagues": wrappers}


@pytest.mark.parametrize(
    ("request_date", "expected_ids"),
    (
        ("20260916", (6_054_000, 6_054_010, 6_054_020, 6_054_030, 6_054_001, 6_054_011, 6_054_021, 6_054_031)),
        ("20260917", (6_054_000, 6_054_010, 6_054_020, 6_054_001, 6_054_011, 6_054_021)),
    ),
)
def test_reviewed_afc_cl2_duplicate_group_wrappers_qualify_only_for_each_exact_date(
    request_date: str,
    expected_ids: tuple[int, ...],
) -> None:
    payload = _afc_payload(request_date=request_date)
    raw = _raw(payload)
    manifest = _manifest(raw, request_date=request_date)

    rows = adapter.qualify_capture_fixtures(raw, manifest)

    assert tuple(item.fixture_id for item in rows) == expected_ids
    assert {item.wrapper_id for item in rows} == {1000001775}
    assert {item.provider_primary_id for item in rows} == {9469}
    assert {item.capture_raw_sha256 for item in rows} == {manifest.raw_sha256}
    assert {item.capture_manifest_sha256 for item in rows} == {
        capture_contract.sha256_data_matches_capture_manifest(manifest)
    }


@pytest.mark.parametrize("request_date", ("20260915", "20260918"))
def test_afc_cl2_duplicate_group_wrapper_rejects_unreviewed_dates(request_date: str) -> None:
    payload = _afc_payload(request_date="20260916")
    payload["date"] = request_date
    raw = _raw(payload)

    with pytest.raises(
        adapter.FreshHoldoutCaptureQualificationAdapterError,
        match="escaped exact request date",
    ):
        adapter.qualify_capture_fixtures(raw, _manifest(raw, request_date=request_date))


def test_afc_cl2_duplicate_group_wrapper_rejects_count_labels_and_metadata_drift() -> None:
    payload = _afc_payload(request_date="20260916")
    payload["leagues"].pop()
    raw = _raw(payload)
    with pytest.raises(adapter.FreshHoldoutCaptureQualificationAdapterError, match="occurrence count"):
        adapter.qualify_capture_fixtures(raw, _manifest(raw, request_date="20260916"))

    payload = _afc_payload(request_date="20260917")
    payload["leagues"][0]["name"] += " "
    raw = _raw(payload)
    with pytest.raises(adapter.FreshHoldoutCaptureQualificationAdapterError, match="label pairing"):
        adapter.qualify_capture_fixtures(raw, _manifest(raw, request_date="20260917"))

    payload = _afc_payload(request_date="20260916")
    payload["leagues"][0]["parentLeagueId"] = 9470
    raw = _raw(payload)
    with pytest.raises(adapter.FreshHoldoutCaptureQualificationAdapterError, match="parentLeagueId"):
        adapter.qualify_capture_fixtures(raw, _manifest(raw, request_date="20260916"))


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("primaryId", 9470),
        ("parentLeagueName", "AFC Champions League Two "),
        ("ccode", "int"),
        ("internalRank", 1),
        ("isGroup", False),
        ("simpleLeague", True),
    ),
)
def test_afc_cl2_duplicate_group_wrapper_rejects_every_fixed_metadata_drift(
    field: str,
    value: object,
) -> None:
    payload = _afc_payload(request_date="20260916")
    payload["leagues"][0][field] = value
    raw = _raw(payload)

    with pytest.raises(adapter.FreshHoldoutCaptureQualificationAdapterError, match=field):
        adapter.qualify_capture_fixtures(raw, _manifest(raw, request_date="20260916"))


def test_afc_cl2_duplicate_group_wrapper_rejects_cross_pairing_wrong_20260917_count_and_match_league_id() -> None:
    payload = _afc_payload(request_date="20260916")
    payload["leagues"][0]["name"], payload["leagues"][1]["name"] = (
        payload["leagues"][1]["name"],
        payload["leagues"][0]["name"],
    )
    raw = _raw(payload)
    with pytest.raises(adapter.FreshHoldoutCaptureQualificationAdapterError, match="label pairing"):
        adapter.qualify_capture_fixtures(raw, _manifest(raw, request_date="20260916"))

    payload = _afc_payload(request_date="20260917")
    extra = copy.deepcopy(payload["leagues"][2])
    extra["groupName"] = "I"
    extra["name"] = "AFC Champions League Two I"
    payload["leagues"].append(extra)
    raw = _raw(payload)
    with pytest.raises(adapter.FreshHoldoutCaptureQualificationAdapterError, match="occurrence count"):
        adapter.qualify_capture_fixtures(raw, _manifest(raw, request_date="20260917"))

    payload = _afc_payload(request_date="20260917")
    payload["leagues"][0]["matches"][0]["leagueId"] = 9469
    raw = _raw(payload)
    with pytest.raises(
        adapter.FreshHoldoutCaptureQualificationAdapterError,
        match="PR89->PR87->PR39 structural chain failed",
    ):
        adapter.qualify_capture_fixtures(raw, _manifest(raw, request_date="20260917"))


def test_afc_cl2_duplicate_group_wrapper_rejects_key_drift_fixture_duplication_and_mixed_ids() -> None:
    payload = _afc_payload(request_date="20260916")
    payload["leagues"][0]["unexpected"] = True
    raw = _raw(payload)
    with pytest.raises(adapter.FreshHoldoutCaptureQualificationAdapterError, match="key set"):
        adapter.qualify_capture_fixtures(raw, _manifest(raw, request_date="20260916"))

    payload = _afc_payload(request_date="20260916")
    del payload["leagues"][0]["parentLeagueId"]
    raw = _raw(payload)
    with pytest.raises(adapter.FreshHoldoutCaptureQualificationAdapterError, match="key set"):
        adapter.qualify_capture_fixtures(raw, _manifest(raw, request_date="20260916"))

    payload = _afc_payload(request_date="20260916")
    payload["leagues"][1]["matches"][0]["id"] = payload["leagues"][0]["matches"][0]["id"]
    raw = _raw(payload)
    with pytest.raises(adapter.FreshHoldoutCaptureQualificationAdapterError, match="fixture id duplicated"):
        adapter.qualify_capture_fixtures(raw, _manifest(raw, request_date="20260916"))

    payload = _afc_payload(request_date="20260916")
    for league in payload["leagues"][:2]:
        league["id"] = adapter.REVIEWED_DUPLICATE_GROUP_WRAPPER_ID
        league["primaryId"] = adapter.REVIEWED_DUPLICATE_GROUP_PRIMARY_ID
        for match in league["matches"]:
            match["leagueId"] = adapter.REVIEWED_DUPLICATE_GROUP_WRAPPER_ID
    raw = _raw(payload)
    with pytest.raises(
        adapter.FreshHoldoutCaptureQualificationAdapterError,
        match="unreviewed duplicate competition wrapper id",
    ):
        adapter.qualify_capture_fixtures(raw, _manifest(raw, request_date="20260916"))


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
    assert receipt["adapter_id"] == "FOTMOB_FRESH_HOLDOUT_REVIEWED_SCHEMA_ADAPTER_V4"
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
    assert receipt["afc_cl2_duplicate_group_wrapper_id"] == 1000001775
    assert receipt["afc_cl2_duplicate_group_primary_id"] == 9469
    assert receipt["afc_cl2_duplicate_group_parent_league_id"] == 9469
    assert receipt["afc_cl2_duplicate_group_wrapper_keys"] == [
        "ccode",
        "groupName",
        "id",
        "internalRank",
        "isGroup",
        "matches",
        "name",
        "parentLeagueId",
        "parentLeagueName",
        "primaryId",
        "simpleLeague",
    ]
    assert receipt["afc_cl2_duplicate_group_reviewed_shapes"] == [
        {
            "request_date": "20260916",
            "occurrence_count": 4,
            "label_pairs": [
                ["A", "AFC Champions League Two A"],
                ["C", "AFC Champions League Two C"],
                ["D", "AFC Champions League Two D"],
                ["E", "AFC Champions League Two E"],
            ],
            "source_workflow_run_id": 34726297627,
            "source_actions_artifact_id": 10307887933,
            "source_actions_artifact_sha256": "5a3d57265916bd6cdcd9de073516fb9100485548656b93f034098d5ec08ac87c",
            "source_observed_at": "2026-09-12T23:46:59.868786Z",
            "source_manifest_sha256": "771b64cc425eb83fae82828fa27c37ebb111056864c169288bd708bbc8ea9ba5",
            "source_raw_sha256": "d1584eaa90e32bb56b4c4ccd8b26fd0e7854df2894c7847f075a17367f228944",
        },
        {
            "request_date": "20260917",
            "occurrence_count": 3,
            "label_pairs": [
                ["F", "AFC Champions League Two F"],
                ["G", "AFC Champions League Two G"],
                ["H", "AFC Champions League Two H"],
            ],
            "source_workflow_run_id": 34761226581,
            "source_actions_artifact_id": 10319156348,
            "source_actions_artifact_sha256": "690c3e2c2e17fff7589ed7305abbc608dc19f3ede0bb09c82319a9d4476d1c40",
            "source_observed_at": "2026-09-13T13:56:40.410882Z",
            "source_manifest_sha256": "d4552fd99683bd078241d6730bbe851cd76902e4e469a250022aa2a58cc46dee",
            "source_raw_sha256": "714b9a570fc47f852de00b52ff6aa1d380723c8ce465a4d934909b49a0bdb0f4",
        },
    ]
    assert receipt["afc_cl2_fresh_holdout_blocker"] == {
        "workflow_run_id": 34940212010,
        "actions_artifact_id": 10385590240,
        "actions_artifact_sha256": "63fc9616ed2271e2bbe5dd25ea1e730481cb42caac4619f92f98b457a0e6121c",
        "inner_tar_sha256": "cc21ff1ffaea813abfd8fcd5e01e44614b7f1728b628e98e64b68b345f05223d",
        "request_date": "20260916",
        "observed_at": "2026-09-15T07:16:47.081203Z",
        "manifest_sha256": "4c0217c1c436ca883c4759296421d1a91d74f20467ce8204ac0d2f6b7283ea0c",
        "raw_sha256": "174c3ddcd14b7b32e433ab501d2603c1b3905fd80cc1870ffab47f68c3c216a3",
    }
    assert receipt["compatibility_projection_is_not_source_evidence"] is True
    assert receipt["duplicate_group_labels_are_opaque"] is True
    assert receipt["football_semantics_not_promoted"] is True
    assert receipt["compatibility_projection_is_not_source_evidence"] is True
    assert all(value is False for value in receipt["safety"].values())
