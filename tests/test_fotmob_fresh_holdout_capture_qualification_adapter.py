from __future__ import annotations

import datetime as dt
import json

import pytest

import domain.fotmob_data_matches_capture as capture_contract
import domain.fotmob_fresh_holdout_capture_qualification_adapter as adapter
import domain.fotmob_utc_native_expected_goals_fresh_holdout as fresh
import scripts.run_fotmob_utc_native_xg_fresh_holdout_tick as tick_cli


UTC = dt.timezone.utc
REQUEST_DATE = "20260822"
KICKOFF = "2026-08-22T18:00:00.000Z"
KICKOFF_MS = 1787421600000
OBSERVED = dt.datetime(2026, 8, 22, 15, 55, 11, tzinfo=UTC)


def _raw(value) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _manifest(raw: bytes, *, network: bool = True):
    response = capture_contract.CapturedFotMobDataMatchesResponse(
        status=200,
        content_type="application/json; charset=utf-8",
        content_length=len(raw),
        body=raw,
        observed_at=OBSERVED,
        network_acquisition_performed=network,
    )
    return capture_contract.build_data_matches_capture_manifest(
        response,
        request_date=REQUEST_DATE,
        timezone="UTC",
        ccode3="NGA",
    )


def _payload(
    *,
    eliminated_team_id=10084,
    include_extra_halfs: bool = True,
) -> dict:
    halfs = {
        "firstHalfStarted": "22.08.2026 18:00:00",
        "secondHalfStarted": "22.08.2026 19:00:00",
    }
    if include_extra_halfs:
        halfs.update(
            {
                "firstExtraHalfStarted": "22.08.2026 19:50:00",
                "secondExtraHalfStarted": "22.08.2026 20:05:00",
            }
        )
    return {
        "date": REQUEST_DATE,
        "leagues": [
            {
                "ccode": "ENG",
                "id": 42,
                "internalRank": 1,
                "matches": [
                    {
                        "away": {
                            "id": 12,
                            "longName": "Away",
                            "name": "Away",
                            "penScore": 0,
                            "redCards": 0,
                            "score": 1,
                        },
                        "eliminatedTeamId": eliminated_team_id,
                        "home": {
                            "id": 11,
                            "longName": "Home",
                            "name": "Home",
                            "penScore": 0,
                            "redCards": 1,
                            "score": 2,
                        },
                        "id": 1001,
                        "leagueId": 42,
                        "status": {
                            "awarded": False,
                            "cancelled": False,
                            "finished": True,
                            "halfs": halfs,
                            "liveTime": {
                                "addedTime": 0,
                                "basePeriod": 90,
                                "long": "",
                                "longKey": "",
                                "maxTime": 90,
                                "short": "",
                                "shortKey": "",
                            },
                            "numberOfAwayRedCards": 0,
                            "numberOfHomeRedCards": 1,
                            "ongoing": False,
                            "periodLength": 45,
                            "reason": {
                                "long": "Full-Time",
                                "longKey": "finished",
                                "short": "FT",
                                "shortKey": "fulltime_short",
                            },
                            "scoreStr": "2 - 1",
                            "started": True,
                            "utcTime": KICKOFF,
                        },
                        "statusId": 6,
                        "time": "22.08.2026 18:00",
                        "timeTS": KICKOFF_MS,
                        "tournamentStage": "",
                    }
                ],
                "name": "Example competition",
                "primaryId": 42,
                "simpleLeague": False,
            }
        ],
    }


def test_adapter_receipt_binds_observed_failure_evidence_and_grants_no_authority() -> None:
    receipt = adapter.adapter_receipt()
    assert receipt["source_workflow_run_id"] == 32583079461
    assert receipt["source_actions_artifact_id"] == 9478318255
    assert receipt["source_actions_artifact_name"] == (
        "failure-20260822T153700Z-run-32583079461.tar.gz"
    )
    assert receipt["reviewed_extra_halfs_keys"] == [
        "firstExtraHalfStarted",
        "secondExtraHalfStarted",
    ]
    assert receipt["compatibility_projection_is_not_source_evidence"] is True
    assert receipt["original_network_capture_lineage_preserved_in_returned_fixtures"] is True
    assert receipt["network_acquisition_performed"] is False
    assert all(value is False for value in receipt["safety"].values())


def test_current_terminal_shape_qualifies_without_rewriting_original_lineage() -> None:
    raw = _raw(_payload())
    manifest = _manifest(raw)

    # The frozen PR39 candidate path cannot consume this exact source shape.
    with pytest.raises(fresh.FotMobFreshHoldoutError):
        fresh.qualify_capture_fixtures(raw, manifest)

    rows = adapter.qualify_capture_fixtures(raw, manifest)
    assert len(rows) == 1
    row = rows[0]
    assert (
        row.fixture_id,
        row.provider_primary_id,
        row.wrapper_id,
        row.home_team_id,
        row.away_team_id,
    ) == (1001, 42, 42, 11, 12)
    assert row.capture_raw_sha256 == manifest.raw_sha256
    assert row.capture_manifest_sha256 == (
        capture_contract.sha256_data_matches_capture_manifest(manifest)
    )
    assert row.capture_observed_at == manifest.observed_at


def test_reviewed_extra_half_keys_are_structural_strings_only() -> None:
    payload = _payload()
    payload["leagues"][0]["matches"][0]["status"]["halfs"][
        "firstExtraHalfStarted"
    ] = None
    raw = _raw(payload)
    with pytest.raises(
        adapter.FreshHoldoutCaptureQualificationAdapterError,
        match="firstExtraHalfStarted must be an exact string",
    ):
        adapter.qualify_capture_fixtures(raw, _manifest(raw))


def test_unreviewed_extra_half_key_still_fails_closed() -> None:
    payload = _payload()
    payload["leagues"][0]["matches"][0]["status"]["halfs"][
        "thirdExtraHalfStarted"
    ] = "22.08.2026 20:20:00"
    raw = _raw(payload)
    with pytest.raises(
        adapter.FreshHoldoutCaptureQualificationAdapterError,
        match="reviewed PR89->PR87->PR39 structural chain failed",
    ):
        adapter.qualify_capture_fixtures(raw, _manifest(raw))


def test_unreviewed_terminal_key_still_fails_closed() -> None:
    payload = _payload()
    payload["leagues"][0]["matches"][0]["status"]["futureUnreviewedField"] = True
    raw = _raw(payload)
    with pytest.raises(
        adapter.FreshHoldoutCaptureQualificationAdapterError,
        match="reviewed PR89->PR87->PR39 structural chain failed",
    ):
        adapter.qualify_capture_fixtures(raw, _manifest(raw))


def test_existing_reviewed_chain_still_accepts_capture_without_extra_half_keys() -> None:
    raw = _raw(_payload(include_extra_halfs=False))
    rows = adapter.qualify_capture_fixtures(raw, _manifest(raw))
    assert [row.fixture_id for row in rows] == [1001]


def test_adapter_rejects_duplicate_json_keys_and_non_network_manifest() -> None:
    duplicate = b'{"date":"20260822","date":"20260822","leagues":[]}'
    with pytest.raises(
        adapter.FreshHoldoutCaptureQualificationAdapterError,
        match="duplicate JSON key",
    ):
        adapter.qualify_capture_fixtures(duplicate, _manifest(duplicate))

    raw = _raw(_payload())
    with pytest.raises(
        adapter.FreshHoldoutCaptureQualificationAdapterError,
        match="actual reviewed network capture",
    ):
        adapter.qualify_capture_fixtures(raw, _manifest(raw, network=False))


def test_dependency_pin_drift_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adapter, "PR89_IMPLEMENTATION_BLOB_SHA", "0" * 40)
    with pytest.raises(
        adapter.FreshHoldoutCaptureQualificationAdapterError,
        match="PR89 eliminatedTeamId extension implementation blob changed",
    ):
        adapter.verify_reviewed_dependencies()


def test_cli_scopes_adapter_to_one_tick_and_restores_frozen_qualifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = fresh.qualify_capture_fixtures
    seen = {}

    def fake_execute(**kwargs):
        seen["qualifier"] = fresh.qualify_capture_fixtures
        seen["kwargs"] = kwargs
        return {"ok": True}

    monkeypatch.setattr(tick_cli.runner, "execute_collection_tick", fake_execute)
    result = tick_cli._execute_collection_tick_with_reviewed_adapter(probe="value")
    assert result == {"ok": True}
    assert seen["qualifier"] is adapter.qualify_capture_fixtures
    assert seen["kwargs"] == {"probe": "value"}
    assert fresh.qualify_capture_fixtures is original


def test_cli_restores_frozen_qualifier_when_tick_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = fresh.qualify_capture_fixtures

    def fail_execute(**_kwargs):
        assert fresh.qualify_capture_fixtures is adapter.qualify_capture_fixtures
        raise RuntimeError("synthetic tick failure")

    monkeypatch.setattr(tick_cli.runner, "execute_collection_tick", fail_execute)
    with pytest.raises(RuntimeError, match="synthetic tick failure"):
        tick_cli._execute_collection_tick_with_reviewed_adapter()
    assert fresh.qualify_capture_fixtures is original
