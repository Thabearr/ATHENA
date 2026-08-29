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


def _dispatch(*, created_at: str, sha: str = SHA):
    return {
        "id": 456,
        "name": continuity.PRIMARY_WORKFLOW_NAME,
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
