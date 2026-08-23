from __future__ import annotations

import datetime as dt
import json

import pytest

import domain.fotmob_data_matches_capture as capture_contract
import domain.fotmob_data_matches_eliminated_team_id_value_domain_extension as pr89
import domain.fotmob_fresh_holdout_capture_qualification_adapter as pr208_adapter
import domain.fotmob_fresh_holdout_request_date_spillover_adapter as adapter
import domain.fotmob_fresh_holdout_request_date_spillover_settlement_adapter as settlement_bridge
import domain.fotmob_utc_native_expected_goals_fresh_holdout as fresh


UTC = dt.timezone.utc
REQUEST_DATE = "20260823"
OBSERVED = dt.datetime(2026, 8, 23, 2, 13, 12, tzinfo=UTC)
TARGET_KICKOFF = "2026-08-23T18:00:00.000Z"
TARGET_KICKOFF_MS = 1787508000000
SPILLOVER_KICKOFF = "2026-08-22T23:30:00.000Z"
SPILLOVER_KICKOFF_MS = 1787441400000


def _raw(value: object) -> bytes:
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
        request_date=REQUEST_DATE,
        timezone="UTC",
        ccode3="NGA",
    )


def _match(
    *,
    fixture_id: int,
    kickoff: str,
    kickoff_ms: int,
    display_time: str,
    home_id: int,
    away_id: int,
) -> dict:
    return {
        "away": {
            "id": away_id,
            "longName": f"Away {away_id}",
            "name": f"Away {away_id}",
            "score": 0,
        },
        "eliminatedTeamId": None,
        "home": {
            "id": home_id,
            "longName": f"Home {home_id}",
            "name": f"Home {home_id}",
            "score": 0,
        },
        "id": fixture_id,
        "leagueId": 42,
        "status": {
            "cancelled": False,
            "finished": False,
            "halfs": {"firstHalfStarted": "23.08.2026 00:00:00"},
            "periodLength": 45,
            "started": False,
            "utcTime": kickoff,
        },
        "statusId": 1,
        "time": display_time,
        "timeTS": kickoff_ms,
        "tournamentStage": "",
    }


def _payload(*, include_spillover: bool = True) -> dict:
    matches = [
        _match(
            fixture_id=2001,
            kickoff=TARGET_KICKOFF,
            kickoff_ms=TARGET_KICKOFF_MS,
            display_time="23.08.2026 18:00",
            home_id=11,
            away_id=12,
        )
    ]
    if include_spillover:
        matches.append(
            _match(
                fixture_id=2002,
                kickoff=SPILLOVER_KICKOFF,
                kickoff_ms=SPILLOVER_KICKOFF_MS,
                display_time="23.08.2026 01:30",
                home_id=21,
                away_id=22,
            )
        )
    return {
        "date": REQUEST_DATE,
        "leagues": [
            {
                "ccode": "ENG",
                "id": 42,
                "internalRank": 1,
                "matches": matches,
                "name": "Example",
                "primaryId": 42,
                "simpleLeague": False,
            }
        ],
    }


def test_receipt_binds_preserved_failure_and_grants_no_authority() -> None:
    receipt = adapter.adapter_receipt()
    assert receipt["source_workflow_run_id"] == 32612280129
    assert receipt["source_actions_artifact_id"] == 9485854548
    assert receipt["source_request_date"] == REQUEST_DATE
    assert receipt["source_spillover_fixture_ids"] == [1000008693, 1000014538]
    assert receipt["spillover_excluded_from_fresh_candidate_population"] is True
    assert receipt["all_utc_date_partitions_revalidated_through_pr89_pr87_pr39"] is True
    assert receipt["validation_projections_are_not_source_evidence"] is True
    assert receipt["network_acquisition_performed"] is False
    assert all(value is False for value in receipt["safety"].values())


def test_frozen_pr208_reproduces_request_date_failure_but_spillover_adapter_qualifies_target_only() -> None:
    raw = _raw(_payload())
    manifest = _manifest(raw)
    with pytest.raises(pr208_adapter.FreshHoldoutCaptureQualificationAdapterError):
        pr208_adapter.qualify_capture_fixtures(raw, manifest)

    rows = adapter.qualify_capture_fixtures(raw, manifest)
    assert [row.fixture_id for row in rows] == [2001]
    assert rows[0].kickoff_utc == dt.datetime(2026, 8, 23, 18, tzinfo=UTC)
    assert rows[0].capture_raw_sha256 == manifest.raw_sha256
    assert rows[0].capture_manifest_sha256 == (
        capture_contract.sha256_data_matches_capture_manifest(manifest)
    )
    assert rows[0].capture_observed_at == manifest.observed_at


def test_all_partitions_are_structurally_revalidated_before_request_partition_receipt_returns() -> None:
    raw = _raw(_payload())
    assessment = adapter.assess_pr89_request_date_partition(raw, _manifest(raw))
    assert (
        assessment.status
        is pr89.EliminatedTeamIdValueDomainStatus.QUALIFIED_STRUCTURAL_ELIMINATED_TEAM_ID_VALUE_DOMAIN
    )
    assert assessment.request_date == REQUEST_DATE
    assert assessment.match_count == 1
    assert assessment.status_reason_semantics_qualified is False
    assert assessment.final_result_semantics_qualified is False


def test_no_spillover_delegates_exactly_to_pr208() -> None:
    raw = _raw(_payload(include_spillover=False))
    manifest = _manifest(raw)
    expected = pr208_adapter.qualify_capture_fixtures(raw, manifest)
    actual = adapter.qualify_capture_fixtures(raw, manifest)
    assert actual == expected


def test_spillover_requires_previous_utc_date_and_provider_display_date_equal_request_date() -> None:
    payload = _payload()
    spillover = payload["leagues"][0]["matches"][1]
    spillover["time"] = "22.08.2026 23:30"
    raw = _raw(payload)
    with pytest.raises(
        adapter.FreshHoldoutRequestDateSpilloverAdapterError,
        match="provider display date equal request date",
    ):
        adapter.qualify_capture_fixtures(raw, _manifest(raw))

    payload = _payload()
    spillover = payload["leagues"][0]["matches"][1]
    spillover["status"]["utcTime"] = "2026-08-21T23:30:00.000Z"
    spillover["timeTS"] = 1787355000000
    raw = _raw(payload)
    with pytest.raises(
        adapter.FreshHoldoutRequestDateSpilloverAdapterError,
        match="immediately-previous-UTC-date spillover",
    ):
        adapter.qualify_capture_fixtures(raw, _manifest(raw))


def test_spillover_partition_still_rejects_timestamp_mismatch_and_unknown_structure() -> None:
    payload = _payload()
    payload["leagues"][0]["matches"][1]["timeTS"] += 1000
    raw = _raw(payload)
    with pytest.raises(
        adapter.FreshHoldoutRequestDateSpilloverAdapterError,
        match="structural partition failed",
    ):
        adapter.qualify_capture_fixtures(raw, _manifest(raw))

    payload = _payload()
    payload["leagues"][0]["matches"][1]["status"]["futureUnknown"] = True
    raw = _raw(payload)
    with pytest.raises(
        adapter.FreshHoldoutRequestDateSpilloverAdapterError,
        match="structural partition failed",
    ):
        adapter.qualify_capture_fixtures(raw, _manifest(raw))


def test_settlement_bridge_is_pr212_compatible_and_uses_partition_validation() -> None:
    raw = _raw(_payload())
    manifest = _manifest(raw)
    proxy = settlement_bridge.build_pr89_settlement_compatibility_proxy()
    assessment = proxy.assess_fotmob_data_matches_eliminated_team_id_value_domain(
        raw,
        manifest,
    )
    assert assessment.request_date == REQUEST_DATE
    assert assessment.match_count == 1
    assert assessment.status_reason_semantics_qualified is False
    assert assessment.final_result_semantics_qualified is False


def test_dependency_pin_drift_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adapter, "PR208_ADAPTER_BLOB_SHA", "0" * 40)
    with pytest.raises(
        adapter.FreshHoldoutRequestDateSpilloverAdapterError,
        match="PR208 adapter implementation blob changed",
    ):
        adapter.verify_reviewed_dependencies()
