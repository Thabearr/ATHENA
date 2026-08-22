from __future__ import annotations

import datetime as dt
import hashlib
import json

import pytest

import domain.fotmob_data_matches_capture as capture_contract
import domain.fotmob_fresh_holdout_capture_qualification_adapter as adapter
import domain.fotmob_utc_native_expected_goals_fresh_holdout_activation_runner as runner
import scripts.run_fotmob_utc_native_xg_fresh_holdout_tick as tick_cli


UTC = dt.timezone.utc


def _live_capture(*, unknown_status_key: bool = False):
    kickoff = dt.datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
    status = {
        "cancelled": False,
        "finished": True,
        "halfs": {
            "firstHalfStarted": "2026-08-22T12:00:00Z",
            "secondHalfStarted": "2026-08-22T13:00:00Z",
        },
        "periodLength": 45,
        "started": True,
        "utcTime": "2026-08-22T12:00:00Z",
        "awarded": False,
        "liveTime": {
            "addedTime": 0,
            "basePeriod": 90,
            "long": "Finished",
            "longKey": "finished",
            "maxTime": 90,
            "short": "FT",
            "shortKey": "finished_short",
        },
        "numberOfAwayRedCards": 0,
        "numberOfHomeRedCards": 0,
        "ongoing": False,
        "scoreStr": "2 - 1",
    }
    if unknown_status_key:
        status["unreviewedFutureField"] = "blocked"
    payload = {
        "date": "20260822",
        "leagues": [
            {
                "ccode": "ENG",
                "id": 47,
                "internalRank": 1,
                "matches": [
                    {
                        "away": {
                            "id": 22,
                            "longName": "Away FC",
                            "name": "Away",
                            "score": 1,
                            "redCards": 0,
                        },
                        "eliminatedTeamId": 22,
                        "home": {
                            "id": 11,
                            "longName": "Home FC",
                            "name": "Home",
                            "score": 2,
                            "redCards": 0,
                        },
                        "id": 123456,
                        "leagueId": 47,
                        "status": status,
                        "statusId": 6,
                        "time": "12:00",
                        "timeTS": int(kickoff.timestamp() * 1000),
                        "tournamentStage": "",
                    }
                ],
                "name": "Premier League",
                "primaryId": 47,
                "simpleLeague": True,
            }
        ],
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    response = capture_contract.CapturedFotMobDataMatchesResponse(
        status=200,
        content_type="application/json",
        content_length=len(raw),
        body=raw,
        observed_at=dt.datetime(2026, 8, 22, 14, 7, tzinfo=UTC),
        network_acquisition_performed=True,
    )
    manifest = capture_contract.build_data_matches_capture_manifest(
        response,
        request_date="20260822",
        timezone="UTC",
        ccode3="NGA",
    )
    return raw, manifest


def test_adapter_accepts_reviewed_terminal_fields_and_non_null_eliminated_team_id() -> None:
    raw, manifest = _live_capture()
    qualified = adapter.qualify_capture_fixtures(raw, manifest)
    assert len(qualified) == 1
    fixture = qualified[0]
    assert fixture.fixture_id == 123456
    assert fixture.provider_primary_id == 47
    assert fixture.wrapper_id == 47
    assert fixture.home_team_id == 11
    assert fixture.away_team_id == 22
    assert fixture.kickoff_utc == dt.datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
    assert fixture.capture_observed_at == manifest.observed_at
    assert fixture.capture_raw_sha256 == hashlib.sha256(raw).hexdigest()
    assert fixture.capture_manifest_sha256 == (
        capture_contract.sha256_data_matches_capture_manifest(manifest)
    )


def test_adapter_fails_closed_on_field_outside_reviewed_terminal_extension() -> None:
    raw, manifest = _live_capture(unknown_status_key=True)
    with pytest.raises(
        adapter.FreshHoldoutCaptureQualificationAdapterError,
        match="reviewed PR89 structural qualification failed",
    ):
        adapter.qualify_capture_fixtures(raw, manifest)


def test_adapter_requires_original_live_network_lineage() -> None:
    raw, manifest = _live_capture()
    projected = capture_contract.dataclasses.replace(
        manifest,
        network_acquisition_performed=False,
    )
    with pytest.raises(
        adapter.FreshHoldoutCaptureQualificationAdapterError,
        match="proven live network acquisition",
    ):
        adapter.qualify_capture_fixtures(raw, projected)


def test_cli_installs_reviewed_adapter_idempotently(monkeypatch: pytest.MonkeyPatch) -> None:
    original = runner._qualify
    monkeypatch.setattr(runner, "_qualify", original)
    tick_cli._install_reviewed_capture_qualifier()
    assert runner._qualify is tick_cli._reviewed_qualify
    tick_cli._install_reviewed_capture_qualifier()
    assert runner._qualify is tick_cli._reviewed_qualify


def test_cli_refuses_to_replace_unknown_qualifier_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "_qualify", lambda _evidence: ())
    with pytest.raises(
        runner.FreshHoldoutActivationError,
        match="qualifier hook changed",
    ):
        tick_cli._install_reviewed_capture_qualifier()
