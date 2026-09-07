from __future__ import annotations

import datetime as dt

import pytest

from domain import fotmob_utc_native_expected_goals_fresh_holdout_schedule_recovery as recovery


UTC = dt.timezone.utc


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
