from __future__ import annotations

from domain import fotmob_utc_native_expected_goals_fresh_holdout_schedule_recovery as recovery


RUN_ID = 456


def _run() -> dict:
    return {
        "id": RUN_ID,
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
        "head_branch": "main",
        "created_at": "2026-08-29T07:07:08Z",
    }


def _jobs() -> dict:
    return {
        "jobs": [
            {
                "name": "execute fresh holdout tick",
                "status": "completed",
                "conclusion": "success",
                "steps": [
                    {
                        "name": name,
                        "status": "completed",
                        "conclusion": conclusion,
                    }
                    for name, conclusion in (
                        recovery._CONTINUITY_NO_ACQUISITION_REQUIRED_STEP_OUTCOMES.items()
                    )
                ],
            }
        ]
    }


def _failed_run() -> dict:
    return {**_run(), "conclusion": "failure"}


def _failed_jobs(pattern_index: int) -> dict:
    outcomes = recovery._CONTINUITY_PREACQUISITION_ALLOWED_STEP_OUTCOMES[
        pattern_index
    ]
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
                    for name, conclusion in outcomes.items()
                ],
            }
        ]
    }


def test_duplicate_continuity_noop_requires_authenticated_source_step() -> None:
    artifacts = {"artifacts": []}
    jobs = _jobs()
    assert recovery._prove_continuity_duplicate_no_acquisition_success(
        _run(),
        artifacts,
        lambda run_id: jobs if run_id == RUN_ID else {},
    ) is True

    for step in jobs["jobs"][0]["steps"]:
        if step["name"] == "Authenticate continuity dispatch source":
            step["conclusion"] = "skipped"
            break
    else:
        raise AssertionError("reviewed duplicate proof omitted authentication step")

    assert recovery._prove_continuity_duplicate_no_acquisition_success(
        _run(),
        artifacts,
        lambda run_id: jobs if run_id == RUN_ID else {},
    ) is False


def test_continuity_preacquisition_failure_proof_covers_only_reviewed_early_failures() -> None:
    artifacts = {"artifacts": []}
    for pattern_index in range(
        len(recovery._CONTINUITY_PREACQUISITION_ALLOWED_STEP_OUTCOMES)
    ):
        jobs = _failed_jobs(pattern_index)
        assert recovery._prove_continuity_preacquisition_control_failure(
            _failed_run(),
            artifacts,
            lambda run_id, jobs=jobs: jobs if run_id == RUN_ID else {},
        ) is True

    escaped = _failed_jobs(2)
    for step in escaped["jobs"][0]["steps"]:
        if step["name"] == "Execute reviewed fresh-holdout collection tick":
            step["conclusion"] = "failure"
    assert recovery._prove_continuity_preacquisition_control_failure(
        _failed_run(),
        artifacts,
        lambda run_id: escaped if run_id == RUN_ID else {},
    ) is False


def test_restore_steps_across_proven_continuity_preacquisition_failure(monkeypatch) -> None:
    failed = _failed_run()
    jobs = _failed_jobs(0)

    def fake_base_restore(**kwargs):
        assert kwargs["prior_runs"] == []
        return recovery.lineage.RestoredFailureLineage(
            None,
            None,
            None,
            None,
            None,
        )

    monkeypatch.setattr(recovery.lineage, "restore_latest_lineage_state", fake_base_restore)
    result = recovery.restore_latest_lineage_state(
        prior_runs=[failed],
        current_run_id=999,
        get_run_artifacts=lambda run_id: {"artifacts": []},
        download_artifact_zip=lambda artifact_id: b"unused",
        get_run_jobs=lambda run_id: jobs if run_id == RUN_ID else {},
    )

    assert result.skipped_preacquisition_failure_run_ids == (RUN_ID,)
