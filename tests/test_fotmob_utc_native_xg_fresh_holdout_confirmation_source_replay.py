from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import tarfile

import pytest

import domain.fotmob_utc_native_expected_goals_fresh_holdout as fresh
import domain.fotmob_utc_native_expected_goals_fresh_holdout_activation_runner as runner
import domain.fotmob_utc_native_expected_goals_fresh_holdout_collection_control as control
import domain.fotmob_utc_native_expected_goals_fresh_holdout_confirmation_evaluator as evaluator
import scripts.replay_fotmob_utc_native_xg_fresh_holdout_confirmation as replay


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _utc_text(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _fixture() -> fresh.QualifiedCaptureFixture:
    return fresh.QualifiedCaptureFixture(
        fixture_id=700001,
        provider_primary_id=47,
        wrapper_id=800001,
        home_team_id=900001,
        away_team_id=900002,
        kickoff_utc=control.holdout_start_utc() + dt.timedelta(days=3, hours=18),
        capture_observed_at=control.holdout_start_utc() + dt.timedelta(days=3, hours=12),
        capture_manifest_sha256="1" * 64,
        capture_raw_sha256="2" * 64,
    )


def _write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(_canonical(row) for row in rows))


def _make_bundle(
    tmp_path: Path,
    *,
    include_missing_assessment: bool = False,
    corrupt_close: bool = False,
    bad_checkpoint_count: bool = False,
) -> tuple[Path, Path]:
    source = tmp_path / "source"
    state = source / control.CONTROL_ROOT_RELATIVE
    state.mkdir(parents=True)

    close = control.hard_close_utc()
    close_state = control.evaluate_close_control_state((), boundary=close)
    close_row: dict[str, object] = {
        "schema_version": 1,
        "event": "COUNT_ONLY_CLOSE_EVALUATION",
        **close_state.to_dict(),
        "outcome_or_performance_input_used": False,
    }
    if corrupt_close:
        close_row["coverage_sha256"] = "f" * 64

    final_slot = control.settlement_tail_end_utc() + dt.timedelta(minutes=7)
    committed_at = final_slot + dt.timedelta(minutes=1)
    run_id = 424242
    compact = final_slot.strftime("%Y%m%dT%H%M%SZ")
    asset_name = f"success-{compact}-run-{run_id}.tar.gz"
    year, week, _weekday = final_slot.isocalendar()
    release_tag = f"athena-fresh-holdout-evidence-{year}-W{week:02d}"
    committed_row = {
        "schema_version": 1,
        "event": "TICK_COMMITTED",
        "scheduled_for_utc": _utc_text(final_slot),
        "phase": control.ControlPhase.COLLECTION_COMPLETE.value,
        "committed_at_utc": _utc_text(committed_at),
        "request_dates": [],
        "network_request_count": 0,
        "network_acquisition_performed": False,
        "durable_release_tag": release_tag,
        "durable_asset_name": asset_name,
        "nominal_schedule_time_used_as_observation_time": False,
        "backfill_or_retrofill_performed": False,
        "outcome_or_performance_input_used_for_close": False,
    }
    control_rows = [close_row, committed_row]
    _write_rows(state / control.CONTROL_JOURNAL_FILENAME, control_rows)

    prediction_rows: list[dict[str, object]] = []
    if include_missing_assessment:
        assessment = fresh.FreshPredictionAssessment(
            disposition=fresh.PredictionDisposition.MISSING_REVIEWED_FEATURES,
            fixture=_fixture(),
            missing_feature_ids=("home_form",),
            sealed_prediction=None,
        )
        prediction_rows.append(
            runner._prediction_row(assessment, release_tag, asset_name)
        )
        _write_rows(state / control.PREDICTION_JOURNAL_FILENAME, prediction_rows)

    checkpoint = {
        "schema_version": 1,
        "runner_id": runner.RUNNER_ID,
        "last_committed_scheduled_for_utc": _utc_text(final_slot),
        "phase": control.ControlPhase.COLLECTION_COMPLETE.value,
        "capture_count": 0,
        "prediction_count": 0,
        "settled_or_terminal_count": 0,
        "control_event_count": len(control_rows) + (1 if bad_checkpoint_count else 0),
        "durable_release_tag": release_tag,
        "durable_asset_name": asset_name,
    }
    (state / control.CHECKPOINT_FILENAME).write_bytes(_canonical(checkpoint))

    archive_path = tmp_path / asset_name
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(state, arcname=control.CONTROL_ROOT_RELATIVE)
    archive_raw = archive_path.read_bytes()
    receipt = {
        "durable_asset_name": asset_name,
        "durable_asset_sha256": hashlib.sha256(archive_raw).hexdigest(),
        "durable_asset_size_bytes": len(archive_raw),
        "durable_release_tag": release_tag,
        "nominal_scheduled_for_utc": _utc_text(final_slot),
        "tick_committed": True,
        "tick_exit_code": 0,
        "workflow_run_id": run_id,
    }
    receipt_path = tmp_path / f"{asset_name}.receipt.json"
    receipt_path.write_bytes(_canonical(receipt))
    return archive_path, receipt_path


def test_terminal_empty_campaign_replays_to_frozen_insufficient_coverage(tmp_path: Path) -> None:
    archive, receipt = _make_bundle(tmp_path)

    result = replay.replay_fresh_holdout_confirmation(
        archive_path=archive,
        receipt_path=receipt,
    )

    assert result["replay_id"] == replay.REPLAY_ID
    assert result["source_counts"] == {
        "capture_rows": 0,
        "prediction_assessment_rows": 0,
        "sealed_complete_cases": 0,
        "identity_rows": 0,
        "terminal_rows": 0,
        "control_rows": 2,
    }
    confirmation = result["confirmation_result"]
    assert confirmation["result_state"] == evaluator.RESULT_INSUFFICIENT_COVERAGE
    assert confirmation["all_confirmation_gates_pass"] is False
    assert result["confirmation_result_sha256"] == (
        evaluator.sha256_fresh_holdout_confirmation_result(confirmation)
    )
    assert result["network_acquisition_performed"] is False
    assert result["model_or_calibration_refit_performed"] is False
    assert result["automatic_successor_approval"] is False
    assert result["pricing_authorized"] is False
    assert result["selection_authorized"] is False
    assert result["bet_authorized"] is False
    assert not any(result["safety"].values())


def test_missing_feature_assessment_is_reconstructed_not_silently_dropped(tmp_path: Path) -> None:
    archive, receipt = _make_bundle(tmp_path, include_missing_assessment=True)

    result = replay.replay_fresh_holdout_confirmation(
        archive_path=archive,
        receipt_path=receipt,
    )

    assert result["source_counts"]["prediction_assessment_rows"] == 1
    assert result["source_counts"]["sealed_complete_cases"] == 0
    confirmation = result["confirmation_result"]
    assert confirmation["prediction_assessment_count_before_close"] == 1
    assert confirmation["missing_feature_prediction_count"] == 1
    assert confirmation["missing_feature_id_counts"] == {"home_form": 1}


def test_receipt_must_bind_exact_archive_digest(tmp_path: Path) -> None:
    archive, receipt = _make_bundle(tmp_path)
    value = json.loads(receipt.read_bytes())
    value["durable_asset_sha256"] = "0" * 64
    receipt.write_bytes(_canonical(value))

    with pytest.raises(
        replay.FreshHoldoutConfirmationSourceReplayError,
        match="disagree with tick receipt SHA-256",
    ):
        replay.replay_fresh_holdout_confirmation(
            archive_path=archive,
            receipt_path=receipt,
        )


def test_noncanonical_receipt_fails_closed(tmp_path: Path) -> None:
    archive, receipt = _make_bundle(tmp_path)
    value = json.loads(receipt.read_bytes())
    receipt.write_text(json.dumps(value, indent=2), encoding="utf-8")

    with pytest.raises(
        replay.FreshHoldoutConfirmationSourceReplayError,
        match="canonical compact sorted-key JSON",
    ):
        replay.replay_fresh_holdout_confirmation(
            archive_path=archive,
            receipt_path=receipt,
        )


def test_stored_count_only_close_is_revalidated(tmp_path: Path) -> None:
    archive, receipt = _make_bundle(tmp_path, corrupt_close=True)

    with pytest.raises(
        replay.FreshHoldoutConfirmationSourceReplayError,
        match="stored selected close disagrees",
    ):
        replay.replay_fresh_holdout_confirmation(
            archive_path=archive,
            receipt_path=receipt,
        )


def test_checkpoint_must_match_append_only_journal_counts(tmp_path: Path) -> None:
    archive, receipt = _make_bundle(tmp_path, bad_checkpoint_count=True)

    with pytest.raises(
        replay.FreshHoldoutConfirmationSourceReplayError,
        match="checkpoint disagrees",
    ):
        replay.replay_fresh_holdout_confirmation(
            archive_path=archive,
            receipt_path=receipt,
        )


def test_failure_named_archive_cannot_be_promoted_to_confirmation(tmp_path: Path) -> None:
    archive, receipt = _make_bundle(tmp_path)
    failure = archive.with_name(archive.name.replace("success-", "failure-", 1))
    failure.write_bytes(archive.read_bytes())
    value = json.loads(receipt.read_bytes())
    value["durable_asset_name"] = failure.name
    value["durable_asset_sha256"] = hashlib.sha256(failure.read_bytes()).hexdigest()
    replacement = tmp_path / f"{failure.name}.receipt.json"
    replacement.write_bytes(_canonical(value))

    with pytest.raises(
        replay.FreshHoldoutConfirmationSourceReplayError,
        match="canonical success archive name",
    ):
        replay.replay_fresh_holdout_confirmation(
            archive_path=failure,
            receipt_path=replacement,
        )


def test_receipt_nominal_slot_must_match_final_committed_state(tmp_path: Path) -> None:
    archive, receipt = _make_bundle(tmp_path)
    value = json.loads(receipt.read_bytes())
    shifted = control.settlement_tail_end_utc() + dt.timedelta(minutes=37)
    value["nominal_scheduled_for_utc"] = _utc_text(shifted)
    receipt.write_bytes(_canonical(value))

    with pytest.raises(
        replay.FreshHoldoutConfirmationSourceReplayError,
        match="success archive nominal slot disagrees",
    ):
        replay.replay_fresh_holdout_confirmation(
            archive_path=archive,
            receipt_path=receipt,
        )


def test_canonical_source_replay_hash_is_deterministic(tmp_path: Path) -> None:
    archive, receipt = _make_bundle(tmp_path)
    result = replay.replay_fresh_holdout_confirmation(
        archive_path=archive,
        receipt_path=receipt,
    )
    raw = replay.canonical_source_replay_result_bytes(result)
    assert raw.endswith(b"\n")
    assert replay.sha256_source_replay_result(result) == hashlib.sha256(raw).hexdigest()


def test_cli_output_is_no_overwrite(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    archive, receipt = _make_bundle(tmp_path)
    output = tmp_path / "result.json"

    assert replay.main(
        [
            "--archive",
            str(archive),
            "--receipt",
            str(receipt),
            "--output",
            str(output),
        ]
    ) == 0
    first = output.read_bytes()
    assert first == capsys.readouterr().out.encode("utf-8")

    assert replay.main(
        [
            "--archive",
            str(archive),
            "--receipt",
            str(receipt),
            "--output",
            str(output),
        ]
    ) == 1
    assert output.read_bytes() == first
    assert "output path already exists" in capsys.readouterr().out


def test_reviewed_dependency_pins_are_current() -> None:
    replay.verify_reviewed_dependencies()
    assert replay._blob(Path(runner.__file__)) == replay.PR151_RUNNER_BLOB_SHA
    assert replay._blob(Path(evaluator.__file__)) == replay.PR167_EVALUATOR_BLOB_SHA
