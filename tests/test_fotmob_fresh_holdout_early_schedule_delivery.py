from __future__ import annotations

import datetime as dt

import pytest

from domain import fotmob_fresh_holdout_continuity as continuity
from domain import fotmob_utc_native_expected_goals_fresh_holdout_schedule_recovery as recovery


UTC = dt.timezone.utc
MAIN_SHA = "a" * 40


def _restored(
    *,
    committed: dt.datetime | None = None,
    attempted: dt.datetime | None = None,
):
    return recovery.RestoredFailureLineage(
        predecessor_run_id=34152446780,
        predecessor_conclusion="success",
        predecessor_asset_name="success-20260907T183700Z-run-34152446780.tar.gz",
        last_committed_utc=committed,
        last_attempted_utc=attempted,
        skipped_preacquisition_failure_run_ids=(),
    )


def test_run_501_shape_waits_for_exact_upcoming_1907_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    created = dt.datetime(2026, 9, 7, 19, 5, 6, tzinfo=UTC)
    prior = dt.datetime(2026, 9, 7, 18, 37, tzinfo=UTC)
    now = dt.datetime(2026, 9, 7, 19, 5, 33, tzinfo=UTC)
    slept: list[float] = []

    monkeypatch.setattr(recovery, "_utc_now", lambda: now)
    monkeypatch.setattr(recovery, "_sleep", lambda seconds: slept.append(seconds))

    nominal, nominal_text, _tag, _success, _failure = (
        recovery.resolve_nominal_schedule_slot_from_lineage(
            "7 * * * *",
            created,
            _restored(committed=prior, attempted=prior),
        )
    )

    assert nominal == dt.datetime(2026, 9, 7, 19, 7, tzinfo=UTC)
    assert nominal_text == "2026-09-07T19:07:00.000000Z"
    assert slept == [pytest.approx(87.0)]


def test_early_delivery_does_not_sleep_when_job_reaches_resolver_after_nominal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = dt.datetime(2026, 9, 7, 19, 5, 6, tzinfo=UTC)
    prior = dt.datetime(2026, 9, 7, 18, 37, tzinfo=UTC)
    slept: list[float] = []

    monkeypatch.setattr(
        recovery,
        "_utc_now",
        lambda: dt.datetime(2026, 9, 7, 19, 7, 10, tzinfo=UTC),
    )
    monkeypatch.setattr(recovery, "_sleep", lambda seconds: slept.append(seconds))

    nominal, *_rest = recovery.resolve_nominal_schedule_slot_from_lineage(
        "7 * * * *",
        created,
        _restored(committed=prior, attempted=prior),
    )
    assert nominal == dt.datetime(2026, 9, 7, 19, 7, tzinfo=UTC)
    assert slept == []


def test_more_than_five_minutes_early_remains_fail_closed() -> None:
    created = dt.datetime(2026, 9, 7, 19, 1, 59, tzinfo=UTC)
    prior = dt.datetime(2026, 9, 7, 18, 37, tzinfo=UTC)

    with pytest.raises(Exception, match="not after last committed slot"):
        recovery.resolve_nominal_schedule_slot_from_lineage(
            "7 * * * *",
            created,
            _restored(committed=prior, attempted=prior),
        )


def test_early_projection_never_moves_at_or_behind_durable_attempt() -> None:
    created = dt.datetime(2026, 9, 7, 19, 5, 6, tzinfo=UTC)
    already_attempted = dt.datetime(2026, 9, 7, 19, 7, tzinfo=UTC)

    with pytest.raises(Exception, match="not after last committed slot"):
        recovery.resolve_nominal_schedule_slot_from_lineage(
            "7 * * * *",
            created,
            _restored(
                committed=already_attempted,
                attempted=already_attempted,
            ),
        )


def test_only_exact_reviewed_crons_can_use_early_projection() -> None:
    created = dt.datetime(2026, 9, 7, 19, 5, 6, tzinfo=UTC)
    prior = dt.datetime(2026, 9, 7, 18, 37, tzinfo=UTC)

    with pytest.raises(Exception):
        recovery.resolve_nominal_schedule_slot_from_lineage(
            "5 * * * *",
            created,
            _restored(committed=prior, attempted=prior),
        )


def _watchdog_run() -> dict[str, object]:
    return {
        "id": 123,
        "name": continuity.WATCHDOG_WORKFLOW_NAME,
        "path": continuity.WATCHDOG_WORKFLOW_PATH,
        "event": "schedule",
        "head_branch": "main",
        "head_sha": MAIN_SHA,
        "created_at": "2026-09-07T18:38:00Z",
    }


def _dispatch_run(created_at: str) -> dict[str, object]:
    plan = continuity.plan_from_watchdog_created_at("2026-09-07T18:38:00Z")
    return {
        "workflow_id": continuity.PRIMARY_WORKFLOW_ID,
        "name": (
            "ATHENA fresh-holdout workflow_dispatch "
            f"source=123 target={plan.target_slot_text} "
            f"cron={plan.target_cron} confirm={continuity.CONTINUITY_CONFIRMATION}"
        ),
        "path": continuity.PRIMARY_WORKFLOW_PATH,
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": MAIN_SHA,
        "created_at": created_at,
    }


def test_watchdog_recognizes_same_bounded_early_window_without_widening_dispatch_authority() -> None:
    assert continuity.MAXIMUM_NATURAL_PRIMARY_EARLY_SECONDS == 5 * 60
    assert continuity.MAXIMUM_DISPATCH_EARLY_SECONDS == 5 * 60
    assert (
        continuity.MAXIMUM_NATURAL_PRIMARY_EARLY_SECONDS
        == recovery.MAXIMUM_EARLY_SCHEDULE_LEAD_SECONDS
    )

    plan = continuity.plan_from_watchdog_created_at("2026-09-07T18:38:00Z")
    assert plan.target_slot_text == "2026-09-07T19:07:00Z"

    with pytest.raises(
        continuity.FreshHoldoutContinuityError,
        match="continuity dispatch was not created at the planned prospective slot",
    ):
        continuity.validate_continuity_dispatch(
            watchdog_run=_watchdog_run(),
            dispatch_run=_dispatch_run("2026-09-07T19:06:29Z"),
            source_watchdog_run_id=123,
            current_main_sha=MAIN_SHA,
            requested_target_slot=plan.target_slot_text,
            requested_target_cron=plan.target_cron,
            confirmation=continuity.CONTINUITY_CONFIRMATION,
        )

    accepted = continuity.validate_continuity_dispatch(
        watchdog_run=_watchdog_run(),
        dispatch_run=_dispatch_run("2026-09-07T19:06:30Z"),
        source_watchdog_run_id=123,
        current_main_sha=MAIN_SHA,
        requested_target_slot=plan.target_slot_text,
        requested_target_cron=plan.target_cron,
        confirmation=continuity.CONTINUITY_CONFIRMATION,
    )
    assert accepted == plan
