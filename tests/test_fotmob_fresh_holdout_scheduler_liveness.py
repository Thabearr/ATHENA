from __future__ import annotations

import datetime as dt

import pytest

from scripts.check_fotmob_fresh_holdout_scheduler_liveness import (
    ACTIVE_RUN_PRESENT,
    ENABLE_DISABLED,
    HEALTHY,
    PRIMARY_WORKFLOW_NAME,
    PRIMARY_WORKFLOW_PATH,
    REREGISTER_STALE_ACTIVE,
    SchedulerLivenessError,
    decide_scheduler_liveness,
)


NOW = dt.datetime(2026, 8, 28, 23, 34, tzinfo=dt.timezone.utc)


def _workflow(*, state: str = "active") -> dict[str, object]:
    return {
        "id": 336875088,
        "name": PRIMARY_WORKFLOW_NAME,
        "path": PRIMARY_WORKFLOW_PATH,
        "state": state,
    }


def _run(
    run_id: int,
    created_at: str,
    *,
    status: str = "completed",
    event: str = "schedule",
) -> dict[str, object]:
    return {
        "id": run_id,
        "name": PRIMARY_WORKFLOW_NAME,
        "path": PRIMARY_WORKFLOW_PATH,
        "event": event,
        "status": status,
        "created_at": created_at,
    }


def _runs(*rows: dict[str, object]) -> dict[str, object]:
    return {"workflow_runs": list(rows)}


def test_recent_scheduled_delivery_is_healthy_without_mutation():
    result = decide_scheduler_liveness(
        workflow=_workflow(),
        runs_response=_runs(_run(10, "2026-08-28T22:59:07Z")),
        now=NOW,
    )
    assert result["decision"] == HEALTHY
    assert result["control_plane_mutation_required"] is False
    assert result["provider_network_acquisition_authorized"] is False
    assert result["backfill_authorized"] is False
    assert result["production_authority_changed"] is False


def test_in_progress_schedule_prevents_control_plane_mutation_even_when_old():
    result = decide_scheduler_liveness(
        workflow=_workflow(),
        runs_response=_runs(
            _run(11, "2026-08-28T20:00:00Z", status="in_progress"),
            _run(10, "2026-08-28T19:00:00Z"),
        ),
        now=NOW,
    )
    assert result["decision"] == ACTIVE_RUN_PRESENT
    assert result["control_plane_mutation_required"] is False


def test_disabled_primary_workflow_requires_enable_only():
    result = decide_scheduler_liveness(
        workflow=_workflow(state="disabled_manually"),
        runs_response=_runs(_run(10, "2026-08-28T18:59:07Z")),
        now=NOW,
    )
    assert result["decision"] == ENABLE_DISABLED
    assert result["control_plane_mutation_required"] is True


def test_stale_active_primary_requires_schedule_reregistration():
    result = decide_scheduler_liveness(
        workflow=_workflow(),
        runs_response=_runs(_run(33201796983, "2026-08-28T18:59:07Z")),
        now=NOW,
    )
    assert result["decision"] == REREGISTER_STALE_ACTIVE
    assert result["latest_schedule_run_id"] == 33201796983
    assert result["control_plane_mutation_required"] is True
    assert result["provider_network_acquisition_authorized"] is False
    assert result["backfill_authorized"] is False


def test_non_schedule_runs_cannot_mask_missing_schedule_delivery():
    result = decide_scheduler_liveness(
        workflow=_workflow(),
        runs_response=_runs(
            _run(12, "2026-08-28T23:20:00Z", event="workflow_dispatch"),
            _run(10, "2026-08-28T18:59:07Z"),
        ),
        now=NOW,
    )
    assert result["decision"] == REREGISTER_STALE_ACTIVE
    assert result["latest_schedule_run_id"] == 10


def test_malformed_or_drifted_metadata_fails_closed():
    with pytest.raises(SchedulerLivenessError, match="primary workflow path drifted"):
        decide_scheduler_liveness(
            workflow={**_workflow(), "path": ".github/workflows/other.yml"},
            runs_response=_runs(),
            now=NOW,
        )

    with pytest.raises(SchedulerLivenessError, match="in the future"):
        decide_scheduler_liveness(
            workflow=_workflow(),
            runs_response=_runs(_run(10, "2026-08-29T00:00:00Z")),
            now=NOW,
        )


def test_threshold_does_not_repair_at_exactly_ninety_minutes():
    result = decide_scheduler_liveness(
        workflow=_workflow(),
        runs_response=_runs(_run(10, "2026-08-28T22:04:00Z")),
        now=NOW,
        stale_minutes=90,
    )
    assert result["decision"] == HEALTHY
