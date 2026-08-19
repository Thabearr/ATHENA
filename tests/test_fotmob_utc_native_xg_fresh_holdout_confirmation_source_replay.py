from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
import tarfile

import pytest

import domain.fotmob_utc_native_expected_goals_fresh_holdout as fresh
import domain.fotmob_utc_native_expected_goals_fresh_holdout_activation_runner as runner
import domain.fotmob_utc_native_expected_goals_fresh_holdout_collection_control as control
import domain.fotmob_utc_native_expected_goals_fresh_holdout_confirmation_evaluator as evaluator
import scripts.replay_fotmob_utc_native_xg_fresh_holdout_confirmation as replay


FEATURES = {
    "home_elo": 1300.0,
    "away_elo": 1300.0,
    "home_form": 0.2,
    "away_form": 0.2,
    "fatigue": 0.0,
}


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


def _sealed_prediction() -> fresh.SealedFreshPrediction:
    fixture = _fixture()
    return fresh.SealedFreshPrediction(
        schema_version=1,
        implementation_state=fresh.IMPLEMENTATION_STATE,
        protocol_sha256=fresh.pr148.PROTOCOL_SHA256,
        holdout_start_utc=control.holdout_start_utc(),
        fixture=fixture,
        bootstrap_projection_sha256=fresh.BOOTSTRAP_PROJECTION_SHA256,
        history_prefix_sha256="3" * 64,
        history_prefix_count=1,
        feature_projection_sha256="4" * 64,
        features=dict(FEATURES),
        rates=fresh._rates_from_features(FEATURES),
        safety={key: False for key in fresh.SAFETY_KEYS},
    )


def _capture_row(*, raw_sha: str = "2" * 64) -> dict[str, object]:
    fixture = _fixture()
    return {
        "schema_version": 1,
        "request_date": "20260822",
        "timezone": control.REQUEST_TIMEZONE,
        "ccode3": control.REQUEST_CCODE3,
        "observed_at": _utc_text(fixture.capture_observed_at),
        "raw_sha256": raw_sha,
        "raw_size": 101,
        "manifest_sha256": fixture.capture_manifest_sha256,
        "working_capture_relative": "working-captures/20260822/capture-1",
        "durable_release_tag": "athena-fresh-holdout-evidence-2026-W34",
        "durable_asset_name": "failure-20260822T120700Z-run-1.tar.gz",
        "network_acquisition_performed": True,
        "preserved_from_uncommitted_tick": True,
    }


def _identity_row() -> dict[str, object]:
    fixture = _fixture()
    return {
        "schema_version": 1,
        "fixture_id": fixture.fixture_id,
        "capture_manifest_sha256": fixture.capture_manifest_sha256,
        "observation": fixture.to_dict(),
    }


def _write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(_canonical(row) for row in rows))


def _make_bundle(
    tmp_path: Path,
    *,
    include_missing_assessment: bool = False,
    corrupt_close: bool = False,
    bad_checkpoint_count: bool = False,
    duplicate_commit: bool = False,
    post_commit_control: bool = False,
    include_unanchored_identity: bool = False,
    duplicate_capture_manifest: bool = False,
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
    committed_row: dict[str, object] = {
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
    control_rows: list[dict[str, object]] = [close_row]
    if duplicate_commit:
        control_rows.append(dict(committed_row))
    control_rows.append(committed_row)
    if post_commit_control:
        control_rows.append(
            {
                "schema_version": 1,
                "event": "SCHEDULER_GAP_RANGE",
                "detected_at_scheduled_for_utc": _utc_text(final_slot),
                "previous_committed_tick_utc": None,
                "first_missing_tick_utc": _utc_text(control.holdout_start_utc() + dt.timedelta(minutes=7)),
                "last_missing_tick_utc": _utc_text(control.holdout_start_utc() + dt.timedelta(minutes=7)),
                "missing_tick_count": 1,
                "backfill_authorized": False,
            }
        )
    _write_rows(state / control.CONTROL_JOURNAL_FILENAME, control_rows)

    prediction_rows: list[dict[str, object]] = []
    if include_missing_assessment:
        assessment = fresh.FreshPredictionAssessment(
            disposition=fresh.PredictionDisposition.MISSING_REVIEWED_FEATURES,
            fixture=_fixture(),
            missing_feature_ids=("home_form",),
            sealed_prediction=None,
        )
        prediction_rows.append(runner._prediction_row(assessment, release_tag, asset_name))
        _write_rows(state / control.PREDICTION_JOURNAL_FILENAME, prediction_rows)

    capture_rows: list[dict[str, object]] = []
    if duplicate_capture_manifest:
        observed = control.holdout_start_utc() + dt.timedelta(days=3, hours=12)
        for index, raw_sha in enumerate(("2" * 64, "3" * 64), start=1):
            capture_rows.append(
                {
                    "schema_version": 1,
                    "request_date": "20260822",
                    "timezone": control.REQUEST_TIMEZONE,
                    "ccode3": control.REQUEST_CCODE3,
                    "observed_at": _utc_text(observed + dt.timedelta(minutes=index)),
                    "raw_sha256": raw_sha,
                    "raw_size": 100 + index,
                    "manifest_sha256": "1" * 64,
                    "working_capture_relative": f"working-captures/20260822/capture-{index}",
                    "durable_release_tag": release_tag,
                    "durable_asset_name": asset_name,
                    "network_acquisition_performed": True,
                }
            )
        _write_rows(state / control.CAPTURE_INDEX_FILENAME, capture_rows)

    if include_unanchored_identity:
        _write_rows(
            state / control.POST_SEAL_IDENTITY_JOURNAL_FILENAME,
            [_identity_row()],
        )

    checkpoint = {
        "schema_version": 1,
        "runner_id": runner.RUNNER_ID,
        "last_committed_scheduled_for_utc": _utc_text(final_slot),
        "phase": control.ControlPhase.COLLECTION_COMPLETE.value,
        "capture_count": len(capture_rows),
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
        "schema_version": 1,
        "runner_id": runner.RUNNER_ID,
        "runner_state": runner.RUNNER_STATE,
        "scheduled_for_utc": _utc_text(final_slot),
        "phase": control.ControlPhase.COLLECTION_COMPLETE.value,
        "committed_at_utc": _utc_text(committed_at),
        "request_dates": [],
        "network_request_count": 0,
        "network_acquisition_performed": False,
        "fresh_holdout_collection_started_by_this_run": False,
        "durable_release_tag": release_tag,
        "durable_asset_name": asset_name,
        "next_required_boundary": runner.NEXT_REQUIRED_BOUNDARY,
        "safety": {key: False for key in runner.SAFETY_KEYS},
        "workflow_run_id": run_id,
        "workflow_event_schedule": "7 * * * *",
        "nominal_scheduled_for_utc": _utc_text(final_slot),
        "durable_asset_sha256": hashlib.sha256(archive_raw).hexdigest(),
        "durable_asset_size_bytes": len(archive_raw),
        "tick_exit_code": 0,
        "tick_committed": True,
        "failure_lineage_reconcile_outcome": "skipped",
    }
    assert set(receipt) == replay.TERMINAL_RECEIPT_KEYS
    receipt_path = tmp_path / f"{asset_name}.receipt.json"
    receipt_path.write_bytes(_canonical(receipt))
    return archive_path, receipt_path


def _rewrite_receipt(receipt: Path, **changes: object) -> None:
    value = json.loads(receipt.read_bytes())
    value.update(changes)
    receipt.write_bytes(_canonical(value))


def test_terminal_empty_campaign_replays_to_frozen_insufficient_coverage(tmp_path: Path) -> None:
    archive, receipt = _make_bundle(tmp_path)

    result = replay.replay_fresh_holdout_confirmation(
        archive_path=archive,
        receipt_path=receipt,
    )

    assert result["replay_id"] == replay.REPLAY_ID
    assert result["source_scope"] == replay.SOURCE_SCOPE
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
    assert result["durable_state_journals_replayed"] is True
    assert result["provider_raw_capture_rederivation_performed"] is False
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


def test_unanchored_post_seal_identity_observation_fails_closed(tmp_path: Path) -> None:
    archive, receipt = _make_bundle(tmp_path, include_unanchored_identity=True)

    with pytest.raises(
        replay.FreshHoldoutConfirmationSourceReplayError,
        match="lacks a sealed prediction|not anchored to capture index",
    ):
        replay.replay_fresh_holdout_confirmation(archive_path=archive, receipt_path=receipt)


def test_duplicate_capture_manifest_lineage_fails_closed(tmp_path: Path) -> None:
    archive, receipt = _make_bundle(tmp_path, duplicate_capture_manifest=True)

    with pytest.raises(
        replay.FreshHoldoutConfirmationSourceReplayError,
        match="capture index duplicated a manifest",
    ):
        replay.replay_fresh_holdout_confirmation(archive_path=archive, receipt_path=receipt)


def test_identity_anchor_must_match_capture_raw_sha_and_time() -> None:
    prediction = _sealed_prediction()
    with pytest.raises(
        replay.FreshHoldoutConfirmationSourceReplayError,
        match="raw SHA disagrees with capture index",
    ):
        replay._verify_durable_cross_journal_lineage(
            capture_rows=(_capture_row(raw_sha="3" * 64),),
            identity_rows=(_identity_row(),),
            control_rows=(),
            settlement_rows=(),
            sealed_map={prediction.fixture.fixture_id: prediction},
        )


def test_identity_observation_must_reference_sealed_population() -> None:
    with pytest.raises(
        replay.FreshHoldoutConfirmationSourceReplayError,
        match="lacks a sealed prediction",
    ):
        replay._verify_durable_cross_journal_lineage(
            capture_rows=(_capture_row(),),
            identity_rows=(_identity_row(),),
            control_rows=(),
            settlement_rows=(),
            sealed_map={},
        )


def test_unknown_control_event_cannot_be_ignored() -> None:
    with pytest.raises(
        replay.FreshHoldoutConfirmationSourceReplayError,
        match="control event escaped reviewed durable-state vocabulary",
    ):
        replay._verify_durable_cross_journal_lineage(
            capture_rows=(),
            identity_rows=(),
            control_rows=({"schema_version": 1, "event": "FORGED_CONTROL_EVENT"},),
            settlement_rows=(),
            sealed_map={},
        )


def test_failed_tick_qualification_event_must_bind_preserved_capture() -> None:
    fixture = _fixture()
    event = {
        "schema_version": 1,
        "event": "UNCOMMITTED_CAPTURE_QUALIFICATION_FAILED",
        "capture_manifest_sha256": fixture.capture_manifest_sha256,
        "capture_raw_sha256": "3" * 64,
        "observed_at": _utc_text(fixture.capture_observed_at),
        "detail": "synthetic qualification failure",
        "tick_committed": False,
        "backfill_authorized": False,
    }
    with pytest.raises(
        replay.FreshHoldoutConfirmationSourceReplayError,
        match="failed-capture qualification event disagrees with capture index",
    ):
        replay._verify_durable_cross_journal_lineage(
            capture_rows=(_capture_row(),),
            identity_rows=(),
            control_rows=(event,),
            settlement_rows=(),
            sealed_map={},
        )


def test_terminal_prediction_sha_must_bind_sealed_prediction() -> None:
    prediction = _sealed_prediction()
    row = runner._terminal_row(
        prediction,
        "UNRESOLVED_AT_SETTLEMENT_TAIL",
        "synthetic terminal",
        "athena-fresh-holdout-evidence-2026-W34",
        "success-20261118T000700Z-run-1.tar.gz",
    )
    row["prediction_sha256"] = "0" * 64
    with pytest.raises(
        replay.FreshHoldoutConfirmationSourceReplayError,
        match="terminal settlement prediction SHA disagrees with prediction journal",
    ):
        replay._verify_durable_cross_journal_lineage(
            capture_rows=(),
            identity_rows=(),
            control_rows=(),
            settlement_rows=(row,),
            sealed_map={prediction.fixture.fixture_id: prediction},
        )


def test_receipt_must_bind_exact_archive_digest(tmp_path: Path) -> None:
    archive, receipt = _make_bundle(tmp_path)
    _rewrite_receipt(receipt, durable_asset_sha256="0" * 64)

    with pytest.raises(
        replay.FreshHoldoutConfirmationSourceReplayError,
        match="disagree with tick receipt SHA-256",
    ):
        replay.replay_fresh_holdout_confirmation(archive_path=archive, receipt_path=receipt)


def test_noncanonical_receipt_fails_closed(tmp_path: Path) -> None:
    archive, receipt = _make_bundle(tmp_path)
    value = json.loads(receipt.read_bytes())
    receipt.write_text(json.dumps(value, indent=2), encoding="utf-8")

    with pytest.raises(
        replay.FreshHoldoutConfirmationSourceReplayError,
        match="canonical compact sorted-key JSON",
    ):
        replay.replay_fresh_holdout_confirmation(archive_path=archive, receipt_path=receipt)


def test_receipt_key_set_is_exact(tmp_path: Path) -> None:
    archive, receipt = _make_bundle(tmp_path)
    _rewrite_receipt(receipt, ignored_forged_field="must not be ignored")

    with pytest.raises(
        replay.FreshHoldoutConfirmationSourceReplayError,
        match="key set changed",
    ):
        replay.replay_fresh_holdout_confirmation(archive_path=archive, receipt_path=receipt)


def test_receipt_must_be_exact_terminal_runner_receipt(tmp_path: Path) -> None:
    archive, receipt = _make_bundle(tmp_path)
    _rewrite_receipt(receipt, runner_id="FORGED_RUNNER")

    with pytest.raises(
        replay.FreshHoldoutConfirmationSourceReplayError,
        match="runner_id changed",
    ):
        replay.replay_fresh_holdout_confirmation(archive_path=archive, receipt_path=receipt)


def test_receipt_cron_identity_must_match_nominal_slot(tmp_path: Path) -> None:
    archive, receipt = _make_bundle(tmp_path)
    _rewrite_receipt(receipt, workflow_event_schedule="37 * * * *")

    with pytest.raises(
        replay.FreshHoldoutConfirmationSourceReplayError,
        match="cron identity disagrees",
    ):
        replay.replay_fresh_holdout_confirmation(archive_path=archive, receipt_path=receipt)


def test_terminal_receipt_cannot_claim_provider_requests(tmp_path: Path) -> None:
    archive, receipt = _make_bundle(tmp_path)
    _rewrite_receipt(
        receipt,
        network_request_count=1,
        network_acquisition_performed=True,
    )

    with pytest.raises(
        replay.FreshHoldoutConfirmationSourceReplayError,
        match="unexpectedly records network requests",
    ):
        replay.replay_fresh_holdout_confirmation(archive_path=archive, receipt_path=receipt)


def test_stored_count_only_close_is_revalidated(tmp_path: Path) -> None:
    archive, receipt = _make_bundle(tmp_path, corrupt_close=True)

    with pytest.raises(
        replay.FreshHoldoutConfirmationSourceReplayError,
        match="stored selected close disagrees",
    ):
        replay.replay_fresh_holdout_confirmation(archive_path=archive, receipt_path=receipt)


def test_checkpoint_must_match_append_only_journal_counts(tmp_path: Path) -> None:
    archive, receipt = _make_bundle(tmp_path, bad_checkpoint_count=True)

    with pytest.raises(
        replay.FreshHoldoutConfirmationSourceReplayError,
        match="checkpoint disagrees",
    ):
        replay.replay_fresh_holdout_confirmation(archive_path=archive, receipt_path=receipt)


def test_duplicate_committed_slot_cannot_be_sorted_away(tmp_path: Path) -> None:
    archive, receipt = _make_bundle(tmp_path, duplicate_commit=True)

    with pytest.raises(
        replay.FreshHoldoutConfirmationSourceReplayError,
        match="committed tick journal is duplicated or out of order",
    ):
        replay.replay_fresh_holdout_confirmation(archive_path=archive, receipt_path=receipt)


def test_terminal_commit_must_remain_final_control_row(tmp_path: Path) -> None:
    archive, receipt = _make_bundle(tmp_path, post_commit_control=True)

    with pytest.raises(
        replay.FreshHoldoutConfirmationSourceReplayError,
        match="terminal TICK_COMMITTED must be the final control journal row",
    ):
        replay.replay_fresh_holdout_confirmation(archive_path=archive, receipt_path=receipt)


def test_receipt_committed_at_must_match_terminal_control_row(tmp_path: Path) -> None:
    archive, receipt = _make_bundle(tmp_path)
    value = json.loads(receipt.read_bytes())
    committed = dt.datetime.fromisoformat(
        value["committed_at_utc"].replace("Z", "+00:00")
    )
    _rewrite_receipt(receipt, committed_at_utc=_utc_text(committed + dt.timedelta(seconds=1)))

    with pytest.raises(
        replay.FreshHoldoutConfirmationSourceReplayError,
        match="receipt committed_at disagrees",
    ):
        replay.replay_fresh_holdout_confirmation(archive_path=archive, receipt_path=receipt)


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
        replay.replay_fresh_holdout_confirmation(archive_path=failure, receipt_path=replacement)


def test_receipt_nominal_slot_must_match_archive_name(tmp_path: Path) -> None:
    archive, receipt = _make_bundle(tmp_path)
    shifted = control.settlement_tail_end_utc() + dt.timedelta(minutes=37)
    _rewrite_receipt(
        receipt,
        nominal_scheduled_for_utc=_utc_text(shifted),
        scheduled_for_utc=_utc_text(shifted),
        workflow_event_schedule="37 * * * *",
    )

    with pytest.raises(
        replay.FreshHoldoutConfirmationSourceReplayError,
        match="success archive nominal slot disagrees",
    ):
        replay.replay_fresh_holdout_confirmation(archive_path=archive, receipt_path=receipt)


def test_canonical_source_replay_hash_is_deterministic(tmp_path: Path) -> None:
    archive, receipt = _make_bundle(tmp_path)
    result = replay.replay_fresh_holdout_confirmation(archive_path=archive, receipt_path=receipt)
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
