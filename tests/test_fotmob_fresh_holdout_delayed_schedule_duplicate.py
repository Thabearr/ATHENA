from __future__ import annotations

import datetime as dt

import pytest

from domain import fotmob_utc_native_expected_goals_fresh_holdout_schedule_recovery as recovery


UTC = dt.timezone.utc


def _restored(slot: dt.datetime):
    return recovery.RestoredFailureLineage(
        predecessor_run_id=123,
        predecessor_conclusion="success",
        predecessor_asset_name="success-20260904T193700Z-run-123.tar.gz",
        last_committed_utc=slot,
        last_attempted_utc=slot,
        skipped_preacquisition_failure_run_ids=(),
    )


def test_delayed_natural_schedule_may_resolve_exact_already_committed_slot_for_noop() -> None:
    slot = dt.datetime(2026, 9, 4, 19, 37, tzinfo=UTC)
    created = dt.datetime(2026, 9, 4, 19, 49, 32, tzinfo=UTC)
    nominal, nominal_text, _tag, _success, _failure = (
        recovery.resolve_nominal_schedule_slot_from_lineage(
            "37 * * * *",
            created,
            _restored(slot),
        )
    )
    assert nominal == slot
    assert nominal_text == "2026-09-04T19:37:00.000000Z"


def test_delayed_duplicate_projection_does_not_relax_backward_lineage() -> None:
    committed = dt.datetime(2026, 9, 4, 20, 7, tzinfo=UTC)
    created = dt.datetime(2026, 9, 4, 19, 49, 32, tzinfo=UTC)
    with pytest.raises(Exception, match="not after last committed slot"):
        recovery.resolve_nominal_schedule_slot_from_lineage(
            "37 * * * *",
            created,
            _restored(committed),
        )
