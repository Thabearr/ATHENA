from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

import domain.fotmob_utc_native_expected_goals_fresh_holdout_activation_runner as runner
import domain.fotmob_utc_native_expected_goals_fresh_holdout_failure_lineage as base_lineage
import domain.fotmob_utc_native_expected_goals_fresh_holdout_schedule_recovery as recovery


UTC = dt.timezone.utc


def _run(run_id: int, *, conclusion: str = "success") -> dict[str, object]:
    return {
        "id": run_id,
        "status": "completed",
        "conclusion": conclusion,
        "event": "schedule",
        "head_branch": "main",
        "created_at": "2026-08-24T07:15:21Z",
    }


def _safe_noop_jobs() -> dict[str, object]:
    steps = [
        {
            "name": name,
            "status": "completed",
            "conclusion": conclusion,
        }
        for name, conclusion in recovery._NO_ACQUISITION_REQUIRED_STEP_OUTCOMES.items()
    ]
    return {
        "jobs": [
            {
                "name": "execute fresh holdout tick",
                "status": "completed",
                "conclusion": "success",
                "steps": steps,
            }
        ]
    }


def test_exact_ambiguity_error_is_the_only_benign_no_acquisition_case() -> None:
    ambiguous = runner.FreshHoldoutActivationError(
        "ambiguous schedule occurrence: multiple candidate slots "
        "(2026-08-24T06:07:00+00:00, 2026-08-24T07:07:00+00:00) "
        "occurred between last committed 2026-08-24T05:37:00+00:00 "
        "and trigger 2026-08-24T07:15:21+00:00"
    )
    assert recovery.is_ambiguous_schedule_occurrence_error(ambiguous) is True
    assert (
        recovery.is_ambiguous_schedule_occurrence_error(
            runner.FreshHoldoutActivationError("checkpoint disagrees")
        )
        is False
    )
    assert recovery.is_ambiguous_schedule_occurrence_error(RuntimeError(str(ambiguous))) is False


def test_green_ambiguous_noop_requires_zero_artifacts_and_exact_skipped_path() -> None:
    run = _run(100)
    assert recovery._prove_ambiguous_no_acquisition_success(
        run,
        {"artifacts": []},
        lambda _run_id: _safe_noop_jobs(),
    ) is True

    jobs = _safe_noop_jobs()
    job = jobs["jobs"][0]
    assert isinstance(job, dict)
    steps = job["steps"]
    assert isinstance(steps, list)
    for step in steps:
        if step["name"] == "Execute reviewed fresh-holdout collection tick":
            step["conclusion"] = "success"
    assert recovery._prove_ambiguous_no_acquisition_success(
        run,
        {"artifacts": []},
        lambda _run_id: jobs,
    ) is False

    assert recovery._prove_ambiguous_no_acquisition_success(
        run,
        {"artifacts": [{"name": "unexpected"}]},
        lambda _run_id: _safe_noop_jobs(),
    ) is False


def test_restore_filters_proven_green_noop_and_marks_it_as_elapsed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    canonical_name = "success-20260824T053700Z-run-90.tar.gz"

    def fake_restore(**kwargs):
        captured["prior_runs"] = kwargs["prior_runs"]
        return base_lineage.RestoredFailureLineage(
            predecessor_run_id=90,
            predecessor_conclusion="success",
            predecessor_asset_name=canonical_name,
            last_committed_utc=dt.datetime(2026, 8, 24, 5, 37, tzinfo=UTC),
            last_attempted_utc=dt.datetime(2026, 8, 24, 5, 37, tzinfo=UTC),
        )

    monkeypatch.setattr(recovery.lineage, "restore_latest_lineage_state", fake_restore)

    def artifacts(run_id: int):
        if run_id == 100:
            return {"artifacts": []}
        if run_id == 90:
            return {"artifacts": [{"name": canonical_name, "expired": False}]}
        raise AssertionError(run_id)

    restored = recovery.restore_latest_lineage_state(
        prior_runs=[_run(100), _run(90)],
        current_run_id=101,
        get_run_artifacts=artifacts,
        download_artifact_zip=lambda _artifact_id: b"unused",
        get_run_jobs=lambda _run_id: _safe_noop_jobs(),
    )
    filtered = captured["prior_runs"]
    assert isinstance(filtered, list)
    assert [row["id"] for row in filtered] == [90]
    assert restored.predecessor_run_id == 90
    assert restored.skipped_preacquisition_failure_run_ids == (100,)


def test_unproven_green_zero_artifact_run_is_not_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_restore(**kwargs):
        captured["prior_runs"] = kwargs["prior_runs"]
        return base_lineage.RestoredFailureLineage(None, None, None, None, None)

    monkeypatch.setattr(recovery.lineage, "restore_latest_lineage_state", fake_restore)
    unsafe_jobs = _safe_noop_jobs()
    job = unsafe_jobs["jobs"][0]
    assert isinstance(job, dict)
    steps = job["steps"]
    assert isinstance(steps, list)
    steps[:] = [
        step
        for step in steps
        if step["name"] != "Acknowledge ambiguous schedule without acquisition"
    ]

    restored = recovery.restore_latest_lineage_state(
        prior_runs=[_run(100), _run(90)],
        current_run_id=101,
        get_run_artifacts=lambda _run_id: {"artifacts": []},
        download_artifact_zip=lambda _artifact_id: b"unused",
        get_run_jobs=lambda _run_id: unsafe_jobs,
    )
    filtered = captured["prior_runs"]
    assert isinstance(filtered, list)
    assert [row["id"] for row in filtered] == [100, 90]
    assert restored.skipped_preacquisition_failure_run_ids == ()


def test_workflow_has_explicit_ambiguous_no_acquisition_lane() -> None:
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml"
    ).read_text(encoding="utf-8")
    assert "fresh_holdout_schedule_recovery as lineage" in workflow
    assert "schedule_disposition=AMBIGUOUS_NO_ACQUISITION" in workflow
    assert 'disposition = "RESOLVED"' in workflow
    assert 'fh.write(f"schedule_disposition={disposition}\\n")' in workflow
    assert "Acknowledge ambiguous schedule without acquisition" in workflow
    assert "steps.state.outputs.schedule_disposition == 'RESOLVED'" in workflow
    assert "refusing to fabricate a nominal slot or backfill evidence" in workflow
