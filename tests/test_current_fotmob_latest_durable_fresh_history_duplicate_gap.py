from __future__ import annotations

import copy

import pytest

import domain.current_fotmob_latest_durable_fresh_history as current
import scripts.audit_fotmob_fresh_holdout_actions_lineage as audit


GAP = copy.deepcopy(current._CURRENT_REDUNDANT_GAP)


def _commit(slot: str) -> dict:
    return {
        "schema_version": 1,
        "event": "TICK_COMMITTED",
        "scheduled_for_utc": slot,
        "committed_at_utc": slot,
        "backfill_or_retrofill_performed": False,
        "nominal_schedule_time_used_as_observation_time": False,
    }


def _uncommitted() -> dict:
    return {
        "schema_version": 1,
        "event": "UNCOMMITTED_CAPTURE_QUALIFICATION_FAILED",
        "tick_committed": False,
        "backfill_authorized": False,
    }


def _observed_rows(*, include_second: bool = True) -> tuple[dict, ...]:
    rows = [
        _commit("2026-09-03T22:07:00.000000Z"),
        copy.deepcopy(GAP),
        _uncommitted(),
    ]
    if include_second:
        rows.append(copy.deepcopy(GAP))
    rows.append(_commit("2026-09-04T00:07:00.000000Z"))
    return tuple(rows)


def test_current_projection_accepts_exact_observed_duplicate_gap_before_next_commit():
    rows = _observed_rows()

    committed, missing = current._validate_control_lineage_current_compatible(rows)

    assert len(committed) == 2
    assert len(missing) == 3


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("missing_tick_count", 2),
        ("first_missing_tick_utc", "2026-09-03T23:07:00.000000Z"),
        ("last_missing_tick_utc", "2026-09-03T23:07:00.000000Z"),
        ("previous_committed_tick_utc", "2026-09-03T21:37:00.000000Z"),
        ("detected_at_scheduled_for_utc", "2026-09-04T00:37:00.000000Z"),
        ("backfill_authorized", True),
    ],
)
def test_current_projection_does_not_hide_mutated_observed_duplicate(field, value):
    rows = list(_observed_rows(include_second=False))
    mutated = copy.deepcopy(GAP)
    mutated[field] = value
    rows.insert(3, mutated)

    with pytest.raises(
        audit.FreshHoldoutActionsLineageAuditError,
        match="scheduler gap",
    ):
        current._validate_control_lineage_current_compatible(tuple(rows))


def test_current_projection_does_not_hide_duplicate_gap_after_commit_boundary():
    rows = list(_observed_rows(include_second=False))
    rows.insert(2, _commit("2026-09-03T22:37:00.000000Z"))
    rows.insert(3, copy.deepcopy(GAP))

    with pytest.raises(
        audit.FreshHoldoutActionsLineageAuditError,
        match="committed slot appears inside a durable scheduler gap",
    ):
        current._validate_control_lineage_current_compatible(tuple(rows))


def test_current_projection_rejects_unsupported_third_duplicate():
    rows = list(_observed_rows(include_second=False))
    rows.insert(3, copy.deepcopy(GAP))
    rows.insert(4, _uncommitted())
    rows.insert(5, copy.deepcopy(GAP))

    with pytest.raises(
        audit.FreshHoldoutActionsLineageAuditError,
        match="scheduler gap",
    ):
        current._validate_control_lineage_current_compatible(tuple(rows))


def test_current_projection_keeps_nonqualification_intervening_event_visible():
    rows = list(_observed_rows(include_second=False))
    rows.insert(3, {"schema_version": 1, "event": "UNKNOWN"})
    rows.insert(4, copy.deepcopy(GAP))

    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError, match="escaped reviewed vocabulary"):
        current._validate_control_lineage_current_compatible(tuple(rows))


@pytest.mark.parametrize("raises", [False, True])
def test_current_wrapper_restores_frozen_raw_validator(monkeypatch, raises):
    original = audit.validate_control_lineage
    monkeypatch.setattr(current, "_verify_current_projected_audit_dependencies", lambda *_: None)

    def fake_projection(**_kwargs):
        assert audit.validate_control_lineage is current._validate_control_lineage_current_compatible
        if raises:
            raise RuntimeError("expected")
        return {"ok": True}

    monkeypatch.setattr(current.recovery_projection, "_audit_actions_lineage_compatible", fake_projection)
    arguments = {
        "expected_main_sha": "0" * 40,
        "get_main_ref": lambda: {},
        "get_runs_page": lambda *_: {},
        "get_run_by_id": lambda *_: {},
        "get_run_artifacts": lambda *_: {},
        "download_artifact_zip": lambda *_: b"x",
        "get_release": lambda *_: {},
        "download_release_asset": lambda *_: b"x",
        "get_run_jobs": lambda *_: {},
    }

    if raises:
        with pytest.raises(current.CurrentLatestDurableFreshHistoryError):
            current._run_reviewed_projected_audit(**arguments)
    else:
        assert current._run_reviewed_projected_audit(**arguments) == {"ok": True}
    assert audit.validate_control_lineage is original
