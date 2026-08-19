from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

import domain.fotmob_utc_native_expected_goals_fresh_holdout_activation_runner as runner
import domain.fotmob_utc_native_expected_goals_fresh_holdout_collection_control as control
import domain.fotmob_utc_native_expected_goals_fresh_holdout_failure_lineage as lineage


UTC = dt.timezone.utc


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    return repo


def _run(run_id: int, created_at: str) -> dict[str, object]:
    return {
        "id": run_id,
        "status": "completed",
        "conclusion": "failure",
        "created_at": created_at,
        "event": "schedule",
        "head_branch": "main",
    }


def _jobs(
    *,
    restore: str,
    bootstrap: str,
    tick: str = "skipped",
    reconcile: str = "skipped",
) -> dict[str, object]:
    conclusions = {
        "Restore newest durable lineage and resolve schedule slot": restore,
        "Restore or materialize PR119 bootstrap projection": bootstrap,
        "Execute reviewed fresh-holdout collection tick": tick,
        "Reconcile any staged capture lineage": reconcile,
    }
    return {
        "jobs": [
            {
                "name": "execute fresh holdout tick",
                "status": "completed",
                "conclusion": "failure",
                "steps": [
                    {
                        "name": name,
                        "status": "completed",
                        "conclusion": conclusion,
                    }
                    for name, conclusion in conclusions.items()
                ],
            }
        ]
    }


def _restore(
    tmp_path: Path,
    *,
    prior_runs: list[dict[str, object]],
    artifacts: dict[int, dict[str, object]],
    jobs_by_run: dict[int, dict[str, object]],
) -> lineage.RestoredFailureLineage:
    return lineage.restore_latest_lineage_state(
        prior_runs=prior_runs,
        current_run_id=999,
        get_run_artifacts=lambda run_id: artifacts[run_id],
        download_artifact_zip=lambda _artifact_id: b"unused",
        get_run_jobs=lambda run_id: jobs_by_run[run_id],
        repository_root=_repo(tmp_path),
    )


def test_zero_artifact_bootstrap_failure_may_join_campaign_origin_recovery(
    tmp_path: Path,
) -> None:
    restored = _restore(
        tmp_path,
        prior_runs=[
            _run(13, "2026-08-19T09:44:00Z"),
            _run(12, "2026-08-19T09:08:00Z"),
            _run(10, "2026-08-18T23:55:00Z"),
        ],
        artifacts={
            13: {"artifacts": []},
            12: {"artifacts": []},
        },
        jobs_by_run={
            13: _jobs(restore="failure", bootstrap="skipped"),
            12: _jobs(restore="success", bootstrap="failure"),
        },
    )

    assert restored.predecessor_run_id is None
    assert restored.last_committed_utc is None
    assert restored.last_attempted_utc is None
    assert restored.skipped_preacquisition_failure_run_ids == (13, 12)


def test_bootstrap_failure_recovery_records_dead_slot_as_missing_not_backfilled(
    tmp_path: Path,
) -> None:
    restored = _restore(
        tmp_path,
        prior_runs=[
            _run(12, "2026-08-19T09:08:00Z"),
            _run(10, "2026-08-18T23:55:00Z"),
        ],
        artifacts={12: {"artifacts": []}},
        jobs_by_run={12: _jobs(restore="success", bootstrap="failure")},
    )

    nominal, nominal_text, _tag, _success, _failure = (
        lineage.resolve_nominal_schedule_slot_from_lineage(
            "7 * * * *",
            dt.datetime(2026, 8, 19, 11, 35, tzinfo=UTC),
            restored,
        )
    )
    assert nominal == dt.datetime(2026, 8, 19, 11, 7, tzinfo=UTC)
    assert nominal_text == "2026-08-19T11:07:00.000000Z"

    state = _repo(tmp_path / "gap") / control.CONTROL_ROOT_RELATIVE
    state.mkdir(parents=True, exist_ok=True)
    control_path = state / control.CONTROL_JOURNAL_FILENAME
    runner._gap((), nominal, control_path)
    rows = runner._rows(control_path)

    assert len(rows) == 1
    row = rows[0]
    assert row["event"] == "SCHEDULER_GAP_RANGE"
    assert row["first_missing_tick_utc"] == "2026-08-19T00:07:00.000000Z"
    assert row["last_missing_tick_utc"] == "2026-08-19T10:37:00.000000Z"
    assert row["missing_tick_count"] == 22
    assert row["backfill_authorized"] is False


def test_bootstrap_failure_that_entered_collection_remains_hard_stop(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        lineage.FreshHoldoutFailureLineageError,
        match="must have exactly one canonical state artifact, found 0",
    ):
        _restore(
            tmp_path,
            prior_runs=[_run(12, "2026-08-19T09:08:00Z")],
            artifacts={12: {"artifacts": []}},
            jobs_by_run={
                12: _jobs(
                    restore="success",
                    bootstrap="failure",
                    tick="failure",
                )
            },
        )


def test_restore_success_bootstrap_success_without_artifact_is_hard_stop(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        lineage.FreshHoldoutFailureLineageError,
        match="must have exactly one canonical state artifact, found 0",
    ):
        _restore(
            tmp_path,
            prior_runs=[_run(12, "2026-08-19T09:08:00Z")],
            artifacts={12: {"artifacts": []}},
            jobs_by_run={12: _jobs(restore="success", bootstrap="success")},
        )


def test_bootstrap_failure_with_any_artifact_is_hard_stop(tmp_path: Path) -> None:
    with pytest.raises(lineage.FreshHoldoutFailureLineageError):
        _restore(
            tmp_path,
            prior_runs=[_run(12, "2026-08-19T09:08:00Z")],
            artifacts={
                12: {
                    "artifacts": [
                        {
                            "id": 7,
                            "name": "unexpected-bootstrap-failure.zip",
                            "expired": False,
                        }
                    ]
                }
            },
            jobs_by_run={12: _jobs(restore="success", bootstrap="failure")},
        )
