from __future__ import annotations

import datetime as dt

import pytest

from domain import fotmob_fresh_holdout_continuity as continuity


SHA = "a" * 40


def _watchdog(*, created_at: str, run_id: int = 123, sha: str = SHA):
    return {
        "id": run_id,
        "name": continuity.WATCHDOG_WORKFLOW_NAME,
        "path": continuity.WATCHDOG_WORKFLOW_PATH,
        "event": "schedule",
        "head_branch": "main",
        "head_sha": sha,
        "created_at": created_at,
        "status": "in_progress",
    }


def _watchdog_jobs(*, run_id: int = 123, sha: str = SHA):
    return {
        "jobs": [
            {
                "run_id": run_id,
                "workflow_name": continuity.WATCHDOG_WORKFLOW_NAME,
                "name": continuity.WATCHDOG_JOB_NAME,
                "head_branch": "main",
                "head_sha": sha,
                "status": "completed",
                "conclusion": "success",
                "created_at": "2026-08-29T07:03:04Z",
                "steps": [
                    {
                        "name": name,
                        "status": "completed",
                        "conclusion": "success",
                    }
                    for name in continuity.WATCHDOG_PROSPECTIVE_DISPATCH_REQUIRED_STEPS
                ],
            }
        ]
    }


def _dispatch(
    *,
    created_at: str,
    sha: str = SHA,
    workflow_id: int = continuity.PRIMARY_WORKFLOW_ID,
):
    return {
        "id": 456,
        "workflow_id": workflow_id,
        "name": (
            "ATHENA fresh-holdout workflow_dispatch source=123 "
            "target=2026-08-29T07:07:00Z cron=7 * * * * "
            f"confirm={continuity.CONTINUITY_CONFIRMATION}"
        ),
        "path": continuity.PRIMARY_WORKFLOW_PATH,
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": sha,
        "created_at": created_at,
        "status": "in_progress",
    }


def test_planner_derives_only_future_primary_lattice_occurrence() -> None:
    plan = continuity.plan_from_watchdog_created_at("2026-08-29T06:56:42Z")
    assert plan.target_slot_text == "2026-08-29T07:07:00Z"
    assert plan.target_cron == "7 * * * *"

    plan = continuity.plan_from_watchdog_created_at("2026-08-29T07:03:02Z")
    assert plan.target_slot_text == "2026-08-29T07:07:00Z"

    plan = continuity.plan_from_watchdog_created_at("2026-08-29T07:36:01Z")
    assert plan.target_slot_text == "2026-08-29T08:07:00Z"
    assert plan.target_cron == "7 * * * *"


def test_continuity_dispatch_requires_real_natural_watchdog_source() -> None:
    watchdog = _watchdog(created_at="2026-08-29T06:56:42Z")
    dispatch = _dispatch(created_at="2026-08-29T07:07:08Z")
    plan = continuity.validate_continuity_dispatch(
        watchdog_run=watchdog,
        dispatch_run=dispatch,
        source_watchdog_run_id=123,
        current_main_sha=SHA,
        requested_target_slot="2026-08-29T07:07:00Z",
        requested_target_cron="7 * * * *",
        confirmation=continuity.CONTINUITY_CONFIRMATION,
    )
    assert plan.target_slot_text == "2026-08-29T07:07:00Z"

    forged = {**watchdog, "event": "workflow_dispatch"}
    with pytest.raises(
        continuity.FreshHoldoutContinuityError,
        match="naturally scheduled watchdog run",
    ):
        continuity.validate_continuity_dispatch(
            watchdog_run=forged,
            dispatch_run=dispatch,
            source_watchdog_run_id=123,
            current_main_sha=SHA,
            requested_target_slot="2026-08-29T07:07:00Z",
            requested_target_cron="7 * * * *",
            confirmation=continuity.CONTINUITY_CONFIRMATION,
        )


def test_continuity_dispatch_requires_exact_dynamic_run_name_and_workflow_id() -> None:
    watchdog = _watchdog(created_at="2026-08-29T06:56:42Z")
    dispatch = _dispatch(created_at="2026-08-29T07:07:08Z")

    wrong_name = {**dispatch, "name": continuity.PRIMARY_WORKFLOW_NAME}
    with pytest.raises(
        continuity.FreshHoldoutContinuityError,
        match="dispatch workflow run-name drifted",
    ):
        continuity.validate_continuity_dispatch(
            watchdog_run=watchdog,
            dispatch_run=wrong_name,
            source_watchdog_run_id=123,
            current_main_sha=SHA,
            requested_target_slot="2026-08-29T07:07:00Z",
            requested_target_cron="7 * * * *",
            confirmation=continuity.CONTINUITY_CONFIRMATION,
        )

    wrong_workflow = {
        **dispatch,
        "workflow_id": continuity.PRIMARY_WORKFLOW_ID + 1,
    }
    with pytest.raises(
        continuity.FreshHoldoutContinuityError,
        match="dispatch workflow id drifted",
    ):
        continuity.validate_continuity_dispatch(
            watchdog_run=watchdog,
            dispatch_run=wrong_workflow,
            source_watchdog_run_id=123,
            current_main_sha=SHA,
            requested_target_slot="2026-08-29T07:07:00Z",
            requested_target_cron="7 * * * *",
            confirmation=continuity.CONTINUITY_CONFIRMATION,
        )


def test_independent_jobs_prove_schedule_only_watchdog_dispatch_path() -> None:
    created = continuity.validate_watchdog_source_jobs(
        _watchdog_jobs(),
        expected_run_id=123,
        expected_main_sha=SHA,
    )
    assert created == dt.datetime(2026, 8, 29, 7, 3, 4, tzinfo=dt.timezone.utc)


def test_independent_jobs_fail_if_dispatch_record_step_did_not_succeed() -> None:
    jobs = _watchdog_jobs()
    steps = jobs["jobs"][0]["steps"]
    for step in steps:
        if step["name"] == "Record prospective continuity dispatch request":
            step["conclusion"] = "skipped"
    with pytest.raises(
        continuity.FreshHoldoutContinuityError,
        match="did not prove reviewed step",
    ):
        continuity.validate_watchdog_source_jobs(
            jobs,
            expected_run_id=123,
            expected_main_sha=SHA,
        )


def test_independent_jobs_fail_on_wrong_source_head() -> None:
    with pytest.raises(
        continuity.FreshHoldoutContinuityError,
        match="head differs",
    ):
        continuity.validate_watchdog_source_jobs(
            _watchdog_jobs(sha="b" * 40),
            expected_run_id=123,
            expected_main_sha=SHA,
        )


def test_caller_cannot_choose_an_old_or_different_slot() -> None:
    watchdog = _watchdog(created_at="2026-08-29T06:56:42Z")
    dispatch = _dispatch(created_at="2026-08-29T07:07:08Z")
    with pytest.raises(
        continuity.FreshHoldoutContinuityError,
        match="differs from deterministic watchdog plan",
    ):
        continuity.validate_continuity_dispatch(
            watchdog_run=watchdog,
            dispatch_run=dispatch,
            source_watchdog_run_id=123,
            current_main_sha=SHA,
            requested_target_slot="2026-08-29T06:37:00Z",
            requested_target_cron="37 * * * *",
            confirmation=continuity.CONTINUITY_CONFIRMATION,
        )


def test_dispatch_must_stay_on_same_exact_main_identity() -> None:
    watchdog = _watchdog(created_at="2026-08-29T06:56:42Z")
    changed = _dispatch(created_at="2026-08-29T07:07:08Z", sha="b" * 40)
    with pytest.raises(
        continuity.FreshHoldoutContinuityError,
        match="dispatch head differs from current main",
    ):
        continuity.validate_continuity_dispatch(
            watchdog_run=watchdog,
            dispatch_run=changed,
            source_watchdog_run_id=123,
            current_main_sha=SHA,
            requested_target_slot="2026-08-29T07:07:00Z",
            requested_target_cron="7 * * * *",
            confirmation=continuity.CONTINUITY_CONFIRMATION,
        )


def test_dispatch_timing_is_bounded_around_planned_slot() -> None:
    watchdog = _watchdog(created_at="2026-08-29T06:56:42Z")
    late = _dispatch(created_at="2026-08-29T07:12:01Z")
    with pytest.raises(
        continuity.FreshHoldoutContinuityError,
        match="not created at the planned prospective slot",
    ):
        continuity.validate_continuity_dispatch(
            watchdog_run=watchdog,
            dispatch_run=late,
            source_watchdog_run_id=123,
            current_main_sha=SHA,
            requested_target_slot="2026-08-29T07:07:00Z",
            requested_target_cron="7 * * * *",
            confirmation=continuity.CONTINUITY_CONFIRMATION,
        )


def test_wait_helper_refuses_past_slot_instead_of_backfilling() -> None:
    plan = continuity.plan_from_watchdog_created_at("2026-08-29T06:56:42Z")
    assert continuity.seconds_until_target(
        plan,
        now=dt.datetime(2026, 8, 29, 7, 6, tzinfo=dt.timezone.utc),
    ) == 60
    with pytest.raises(
        continuity.FreshHoldoutContinuityError,
        match="already in the past",
    ):
        continuity.seconds_until_target(
            plan,
            now=dt.datetime(2026, 8, 29, 7, 8, tzinfo=dt.timezone.utc),
        )


def test_dispatch_check_waits_through_natural_primary_grace_only() -> None:
    plan = continuity.plan_from_watchdog_created_at("2026-08-29T07:03:02Z")
    assert continuity.seconds_until_dispatch_check(
        plan,
        now=dt.datetime(2026, 8, 29, 7, 3, 2, tzinfo=dt.timezone.utc),
    ) == 328
    assert continuity.seconds_until_dispatch_check(
        plan,
        now=dt.datetime(2026, 8, 29, 7, 8, 30, tzinfo=dt.timezone.utc),
    ) == 0
    with pytest.raises(
        continuity.FreshHoldoutContinuityError,
        match="window already expired",
    ):
        continuity.seconds_until_dispatch_check(
            plan,
            now=dt.datetime(2026, 8, 29, 7, 12, 1, tzinfo=dt.timezone.utc),
        )


def test_durable_targets_are_bound_to_exact_future_slot_and_run() -> None:
    plan = continuity.plan_from_watchdog_created_at("2026-08-29T07:03:02Z")
    nominal, release, success, failure = continuity.durable_targets_for_plan(
        plan,
        run_id=456,
    )
    assert nominal == "2026-08-29T07:07:00.000000Z"
    assert release == "athena-fresh-holdout-evidence-2026-W35"
    assert success == "success-20260829T070700Z-run-456.tar.gz"
    assert failure == "failure-20260829T070700Z-run-456.tar.gz"

    with pytest.raises(
        continuity.FreshHoldoutContinuityError,
        match="workflow run id",
    ):
        continuity.durable_targets_for_plan(plan, run_id=0)


def test_durable_last_attempted_prevents_duplicate_same_slot_acquisition() -> None:
    target = "2026-08-29T07:07:00Z"
    assert continuity.lineage_already_attempted_target(
        last_attempted_utc="2026-08-29T07:07:00Z",
        target_slot=target,
    ) is True
    assert continuity.lineage_already_attempted_target(
        last_attempted_utc="2026-08-29T06:37:00Z",
        target_slot=target,
    ) is False
    assert continuity.lineage_already_attempted_target(
        last_attempted_utc=None,
        target_slot=target,
    ) is False
