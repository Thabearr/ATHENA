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
