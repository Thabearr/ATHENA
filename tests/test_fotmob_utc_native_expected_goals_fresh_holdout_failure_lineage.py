from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import tarfile
import zipfile

import pytest

import domain.fotmob_data_matches_capture as capture_contract
import domain.fotmob_utc_native_expected_goals_fresh_holdout as fresh
import domain.fotmob_utc_native_expected_goals_fresh_holdout_activation_runner as runner
import domain.fotmob_utc_native_expected_goals_fresh_holdout_calibration_competition_protocol as pr148
import domain.fotmob_utc_native_expected_goals_fresh_holdout_collection_control as control
import domain.fotmob_utc_native_expected_goals_fresh_holdout_failure_lineage as lineage


UTC = dt.timezone.utc


def _repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    state = repo / control.CONTROL_ROOT_RELATIVE
    state.mkdir(parents=True, exist_ok=True)
    return repo, state


def _capture(
    tmp_path: Path,
    request_date: str,
    observed_at: dt.datetime,
) -> runner.CaptureEvidence:
    raw = json.dumps(
        {"leagues": [], "request_test_date": request_date},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    response = capture_contract.CapturedFotMobDataMatchesResponse(
        status=200,
        content_type="application/json",
        content_length=len(raw),
        body=raw,
        observed_at=observed_at,
        network_acquisition_performed=True,
    )
    manifest = capture_contract.build_data_matches_capture_manifest(
        response,
        request_date=request_date,
        timezone=control.REQUEST_TIMEZONE,
        ccode3=control.REQUEST_CCODE3,
    )
    directory = tmp_path / f"capture-{request_date}-{observed_at.hour}-{observed_at.minute}"
    directory.mkdir(parents=True, exist_ok=True)
    return runner.CaptureEvidence(directory, raw, manifest)


def _prediction(
    fixture_id: int,
    observed_at: dt.datetime,
    kickoff_utc: dt.datetime,
) -> fresh.SealedFreshPrediction:
    fixture = fresh.QualifiedCaptureFixture(
        fixture_id=fixture_id,
        provider_primary_id=99999,
        wrapper_id=5000,
        home_team_id=1,
        away_team_id=2,
        kickoff_utc=kickoff_utc,
        capture_observed_at=observed_at,
        capture_manifest_sha256="a" * 64,
        capture_raw_sha256="b" * 64,
    )
    features = {
        "home_elo": 1500.0,
        "away_elo": 1500.0,
        "home_form": 0.5,
        "away_form": 0.5,
        "fatigue": 0.0,
    }
    return fresh.SealedFreshPrediction(
        schema_version=1,
        implementation_state=fresh.IMPLEMENTATION_STATE,
        protocol_sha256=pr148.PROTOCOL_SHA256,
        holdout_start_utc=control.holdout_start_utc(),
        fixture=fixture,
        bootstrap_projection_sha256=fresh.BOOTSTRAP_PROJECTION_SHA256,
        history_prefix_sha256="c" * 64,
        history_prefix_count=100,
        feature_projection_sha256="d" * 64,
        features=features,
        rates=fresh._rates_from_features(features),
        safety={key: False for key in fresh.SAFETY_KEYS},
    )


def _append_prediction(state: Path, prediction: fresh.SealedFreshPrediction) -> None:
    assessment = fresh.FreshPredictionAssessment(
        disposition=fresh.PredictionDisposition.SEALED_COMPLETE_CASE,
        fixture=prediction.fixture,
        missing_feature_ids=(),
        sealed_prediction=prediction,
    )
    runner._append(
        state / control.PREDICTION_JOURNAL_FILENAME,
        runner._prediction_row(assessment, "tag", "asset"),
    )


def _commit_prior_tick(state: Path, scheduled: dt.datetime) -> None:
    runner._append(
        state / control.CONTROL_JOURNAL_FILENAME,
        {
            "schema_version": 1,
            "event": "TICK_COMMITTED",
            "scheduled_for_utc": runner._utc_text(scheduled),
            "phase": control.ControlPhase.PREDICTION_AND_SETTLEMENT_COLLECTION.value,
            "committed_at_utc": runner._utc_text(scheduled + dt.timedelta(minutes=5)),
            "request_dates": [],
            "network_request_count": 0,
            "network_acquisition_performed": False,
            "durable_release_tag": "athena-fresh-holdout-evidence-2026-W34",
            "durable_asset_name": "success-20260819T000700Z-run-9.tar.gz",
            "nominal_schedule_time_used_as_observation_time": False,
            "backfill_or_retrofill_performed": False,
            "outcome_or_performance_input_used_for_close": False,
        },
    )
    runner._checkpoint(
        state / control.CHECKPOINT_FILENAME,
        {
            "schema_version": 1,
            "runner_id": runner.RUNNER_ID,
            "last_committed_scheduled_for_utc": runner._utc_text(scheduled),
            "phase": control.ControlPhase.PREDICTION_AND_SETTLEMENT_COLLECTION.value,
            "capture_count": 0,
            "prediction_count": 0,
            "settled_or_terminal_count": 0,
            "control_event_count": 1,
            "durable_release_tag": "athena-fresh-holdout-evidence-2026-W34",
            "durable_asset_name": "success-20260819T000700Z-run-9.tar.gz",
        },
    )


def _artifact_zip(
    state: Path,
    *,
    run_id: int,
    nominal: dt.datetime,
    prefix: str,
) -> tuple[str, bytes, str]:
    tar_name = f"{prefix}-{nominal.strftime('%Y%m%dT%H%M%SZ')}-run-{run_id}.tar.gz"
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w:gz") as tar:
        for item in sorted(state.rglob("*")):
            arcname = str(item.relative_to(state.parents[2])).replace("\\", "/")
            tar.add(item, arcname=arcname)
    tar_bytes = tar_buffer.getvalue()
    tar_sha = hashlib.sha256(tar_bytes).hexdigest()

    receipt = {
        "schema_version": 1,
        "workflow_run_id": run_id,
        "nominal_scheduled_for_utc": runner._utc_text(nominal),
        "durable_release_tag": "athena-fresh-holdout-evidence-2026-W34",
        "durable_asset_name": tar_name,
        "durable_asset_sha256": tar_sha,
        "durable_asset_size_bytes": len(tar_bytes),
    }
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as archive:
        archive.writestr(tar_name, tar_bytes)
        archive.writestr(
            "fresh-holdout-tick-receipt.json",
            json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n",
        )
    zip_bytes = zip_buffer.getvalue()
    return tar_name, zip_bytes, hashlib.sha256(zip_bytes).hexdigest()


def test_reconcile_failed_tick_preserves_capture_and_post_seal_identity_without_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, state = _repo(tmp_path)
    sealed = _prediction(
        101,
        dt.datetime(2026, 8, 19, 0, 7, tzinfo=UTC),
        dt.datetime(2026, 8, 19, 2, 0, tzinfo=UTC),
    )
    _append_prediction(state, sealed)

    evidence = _capture(
        tmp_path,
        "20260819",
        dt.datetime(2026, 8, 19, 0, 37, tzinfo=UTC),
    )
    runner._stage(evidence, state / runner.WORKING_CAPTURE_DIRECTORY)
    observation = fresh.QualifiedCaptureFixture(
        fixture_id=101,
        provider_primary_id=sealed.fixture.provider_primary_id,
        wrapper_id=sealed.fixture.wrapper_id,
        home_team_id=sealed.fixture.home_team_id,
        away_team_id=sealed.fixture.away_team_id,
        kickoff_utc=sealed.fixture.kickoff_utc + dt.timedelta(minutes=5),
        capture_observed_at=evidence.manifest.observed_at,
        capture_manifest_sha256=runner._manifest_sha(evidence),
        capture_raw_sha256=evidence.manifest.raw_sha256,
    )
    monkeypatch.setattr(runner, "_qualify", lambda _evidence: (observation,))

    result = lineage.reconcile_staged_capture_lineage(
        durable_release_tag="athena-fresh-holdout-evidence-2026-W34",
        durable_asset_name="failure-20260819T003700Z-run-10.tar.gz",
        repository_root=repo,
    )
    assert result == {
        "captures_added": 1,
        "identity_rows_added": 1,
        "qualification_failures_added": 0,
    }
    capture_rows = runner._rows(state / control.CAPTURE_INDEX_FILENAME)
    identity_rows = runner._rows(state / control.POST_SEAL_IDENTITY_JOURNAL_FILENAME)
    control_rows = runner._rows(state / control.CONTROL_JOURNAL_FILENAME)
    assert len(capture_rows) == 1
    assert capture_rows[0]["preserved_from_uncommitted_tick"] is True
    assert len(identity_rows) == 1
    assert identity_rows[0]["fixture_id"] == 101
    assert not any(row.get("event") == "TICK_COMMITTED" for row in control_rows)

    second = lineage.reconcile_staged_capture_lineage(
        durable_release_tag="athena-fresh-holdout-evidence-2026-W34",
        durable_asset_name="failure-20260819T003700Z-run-10.tar.gz",
        repository_root=repo,
    )
    assert second == {
        "captures_added": 0,
        "identity_rows_added": 0,
        "qualification_failures_added": 0,
    }


def test_qualification_failure_still_preserves_raw_capture_lineage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, state = _repo(tmp_path)
    evidence = _capture(
        tmp_path,
        "20260819",
        dt.datetime(2026, 8, 19, 0, 37, tzinfo=UTC),
    )
    runner._stage(evidence, state / runner.WORKING_CAPTURE_DIRECTORY)

    def fail(_evidence):
        raise ValueError("synthetic qualification failure")

    monkeypatch.setattr(runner, "_qualify", fail)
    result = lineage.reconcile_staged_capture_lineage(
        durable_release_tag="athena-fresh-holdout-evidence-2026-W34",
        durable_asset_name="failure-20260819T003700Z-run-10.tar.gz",
        repository_root=repo,
    )
    assert result["captures_added"] == 1
    assert result["identity_rows_added"] == 0
    assert result["qualification_failures_added"] == 1
    assert len(runner._rows(state / control.CAPTURE_INDEX_FILENAME)) == 1
    control_rows = runner._rows(state / control.CONTROL_JOURNAL_FILENAME)
    assert [row["event"] for row in control_rows] == [
        "UNCOMMITTED_CAPTURE_QUALIFICATION_FAILED"
    ]
    assert control_rows[0]["tick_committed"] is False


def test_restore_newest_failed_artifact_carries_partial_state_and_does_not_fall_back(
    tmp_path: Path,
) -> None:
    source_repo, source_state = _repo(tmp_path / "source")
    prior_commit = dt.datetime(2026, 8, 19, 0, 7, tzinfo=UTC)
    failed_attempt = dt.datetime(2026, 8, 19, 0, 37, tzinfo=UTC)
    _commit_prior_tick(source_state, prior_commit)

    evidence = _capture(
        tmp_path / "captures",
        "20260819",
        failed_attempt + dt.timedelta(minutes=1),
    )
    runner._stage(evidence, source_state / runner.WORKING_CAPTURE_DIRECTORY)
    # Model a failure artifact created before the old runner appended capture-index.
    tar_name, zip_bytes, zip_sha = _artifact_zip(
        source_state,
        run_id=10,
        nominal=failed_attempt,
        prefix="failure",
    )

    prior_runs = [
        {"id": 10, "status": "completed", "conclusion": "failure"},
        {"id": 9, "status": "completed", "conclusion": "success"},
    ]
    artifact_metadata = {
        "artifacts": [
            {
                "id": 1001,
                "name": tar_name,
                "digest": f"sha256:{zip_sha}",
                "expired": False,
            }
        ]
    }
    queried: list[int] = []

    def get_artifacts(run_id: int):
        queried.append(run_id)
        if run_id != 10:
            raise AssertionError("older successful run must never be used")
        return artifact_metadata

    dest_repo, dest_state = _repo(tmp_path / "dest")
    restored = lineage.restore_latest_lineage_state(
        prior_runs=prior_runs,
        current_run_id=11,
        get_run_artifacts=get_artifacts,
        download_artifact_zip=lambda _artifact_id: zip_bytes,
        repository_root=dest_repo,
    )
    assert queried == [10]
    assert restored.predecessor_run_id == 10
    assert restored.predecessor_conclusion == "failure"
    assert restored.last_committed_utc == prior_commit
    assert restored.last_attempted_utc == failed_attempt
    # Restore reconciliation promotes the staged raw capture into evidence lineage.
    capture_rows = runner._rows(dest_state / control.CAPTURE_INDEX_FILENAME)
    assert len(capture_rows) == 1
    assert capture_rows[0]["manifest_sha256"] == runner._manifest_sha(evidence)
    control_rows = runner._rows(dest_state / control.CONTROL_JOURNAL_FILENAME)
    assert sum(row.get("event") == "TICK_COMMITTED" for row in control_rows) == 1


def test_schedule_resolution_uses_failed_attempt_as_occurrence_anchor() -> None:
    restored = lineage.RestoredFailureLineage(
        predecessor_run_id=10,
        predecessor_conclusion="failure",
        predecessor_asset_name="failure-20260819T003700Z-run-10.tar.gz",
        last_committed_utc=dt.datetime(2026, 8, 19, 0, 7, tzinfo=UTC),
        last_attempted_utc=dt.datetime(2026, 8, 19, 0, 37, tzinfo=UTC),
    )
    nominal, nominal_text, _tag, _success, _failure = (
        lineage.resolve_nominal_schedule_slot_from_lineage(
            "7 * * * *",
            dt.datetime(2026, 8, 19, 1, 10, tzinfo=UTC),
            restored,
        )
    )
    assert nominal == dt.datetime(2026, 8, 19, 1, 7, tzinfo=UTC)
    assert nominal_text == "2026-08-19T01:07:00.000000Z"


def test_workflow_restores_completed_failure_lineage_and_reconciles_before_packaging() -> None:
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml"
    ).read_text(encoding="utf-8")
    assert "status=success" not in workflow
    assert "restore_latest_lineage_state" in workflow
    assert "resolve_nominal_schedule_slot_from_lineage" in workflow
    assert "Reconcile any staged capture lineage" in workflow
    assert "reconcile_staged_capture_lineage" in workflow
    assert "nominal_scheduled_for_utc" in workflow
    assert "workflow_run_id" in workflow
