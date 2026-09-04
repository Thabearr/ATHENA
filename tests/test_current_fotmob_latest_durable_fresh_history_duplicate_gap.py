from __future__ import annotations

import copy
import datetime as dt

import pytest

import domain.current_fotmob_latest_durable_fresh_history as current
import scripts.audit_fotmob_fresh_holdout_actions_lineage as audit


UTC = dt.timezone.utc
FIRST = dt.datetime(2026, 8, 19, 0, 7, tzinfo=UTC)


def _utc(slot: int) -> str:
    return (FIRST + dt.timedelta(minutes=30 * slot)).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _commit(slot: int) -> dict:
    return {
        "schema_version": 1,
        "event": "TICK_COMMITTED",
        "scheduled_for_utc": _utc(slot),
        "committed_at_utc": _utc(slot),
    }


def _gap(first: int, last: int, detected: int, previous: int) -> dict:
    return {
        "schema_version": 1,
        "event": "SCHEDULER_GAP_RANGE",
        "detected_at_scheduled_for_utc": _utc(detected),
        "previous_committed_tick_utc": _utc(previous),
        "first_missing_tick_utc": _utc(first),
        "last_missing_tick_utc": _utc(last),
        "missing_tick_count": last - first + 1,
        "backfill_authorized": False,
    }


def _uncommitted() -> dict:
    return {
        "schema_version": 1,
        "event": "UNCOMMITTED_CAPTURE_QUALIFICATION_FAILED",
        "tick_committed": False,
        "backfill_authorized": False,
    }


def test_current_projection_accepts_only_exact_idempotent_duplicate_gap_before_next_commit():
    first_gap = _gap(1, 2, 3, 0)
    rows = (
        _commit(0),
        first_gap,
        _uncommitted(),
        copy.deepcopy(first_gap),
        _commit(3),
        _gap(4, 4, 5, 3),
        _commit(5),
    )

    committed, missing = current._validate_control_lineage_current_compatible(rows)

    assert committed == {0, 3, 5}
    assert missing == {1, 2, 4}


def test_current_projection_does_not_hide_mutated_same_detection_gap():
    first_gap = _gap(1, 2, 3, 0)
    mutated = copy.deepcopy(first_gap)
    mutated["missing_tick_count"] = 1

    with pytest.raises(
        audit.FreshHoldoutActionsLineageAuditError,
        match="scheduler gap range/count/detection/lineage semantics changed",
    ):
        current._validate_control_lineage_current_compatible(
            (_commit(0), first_gap, _uncommitted(), mutated)
        )


def test_current_projection_does_not_hide_duplicate_gap_after_commit_boundary():
    first_gap = _gap(1, 2, 3, 0)

    with pytest.raises(
        audit.FreshHoldoutActionsLineageAuditError,
        match="scheduler gap range/count/detection/lineage semantics changed",
    ):
        current._validate_control_lineage_current_compatible(
            (_commit(0), first_gap, _commit(3), copy.deepcopy(first_gap))
        )
