from __future__ import annotations

import pytest

import scripts.audit_fotmob_fresh_holdout_actions_lineage as audit
import scripts.audit_fotmob_fresh_holdout_actions_lineage_schedule_recovery_projection as projection

# This regression contract must execute; skipping it would mask the continuity blocker.


def _bot() -> dict[str, object]:
    return {"login": "github-actions[bot]", "id": 41898282, "type": "Bot"}


def _queued_run() -> dict[str, object]:
    return {
        "id": 33931981258,
        "name": projection.continuity.PRIMARY_WORKFLOW_NAME,
        "display_title": projection.continuity.PRIMARY_WORKFLOW_NAME,
        "workflow_id": projection.continuity.PRIMARY_WORKFLOW_ID,
        "path": projection.continuity.PRIMARY_WORKFLOW_PATH,
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": "87991228755f49f0c6c87c0e8d241c02c1b29b9d",
        "status": "queued",
        "conclusion": None,
        "run_number": 462,
        "run_attempt": 1,
        "created_at": "2026-09-05T00:08:33Z",
        "updated_at": "2026-09-05T00:08:33Z",
        "run_started_at": "2026-09-05T00:08:33Z",
        "actor": _bot(),
        "triggering_actor": _bot(),
    }


def _empty_artifacts(_run_id: int) -> dict[str, object]:
    return {"total_count": 0, "artifacts": []}


def _empty_jobs(_run_id: int) -> dict[str, object]:
    return {"total_count": 0, "jobs": []}


def test_generic_title_queued_dispatch_is_transparent_only_with_zero_execution() -> None:
    assert projection._prove_queued_no_execution_dispatch(
        _queued_run(),
        get_run_artifacts=_empty_artifacts,
        get_run_jobs=_empty_jobs,
    ) is True


def test_generic_title_queued_dispatch_rejects_manual_actor() -> None:
    changed = {**_queued_run(), "actor": {"login": "Thabearr", "type": "User"}}
    with pytest.raises(
        audit.FreshHoldoutActionsLineageAuditError,
        match="queued no-execution dispatch actor drifted",
    ):
        projection._prove_queued_no_execution_dispatch(
            changed,
            get_run_artifacts=_empty_artifacts,
            get_run_jobs=_empty_jobs,
        )


def test_generic_title_queued_dispatch_rejects_execution_state_or_evidence() -> None:
    for changed in (
        {**_queued_run(), "status": "in_progress"},
        {**_queued_run(), "conclusion": "success"},
        {**_queued_run(), "run_attempt": 2},
    ):
        with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
            projection._prove_queued_no_execution_dispatch(
                changed,
                get_run_artifacts=_empty_artifacts,
                get_run_jobs=_empty_jobs,
            )

    with pytest.raises(
        audit.FreshHoldoutActionsLineageAuditError,
        match="unexpectedly acquired execution jobs",
    ):
        projection._prove_queued_no_execution_dispatch(
            _queued_run(),
            get_run_artifacts=_empty_artifacts,
            get_run_jobs=lambda _run_id: {"total_count": 1, "jobs": [{"id": 1}]},
        )

    with pytest.raises(
        audit.FreshHoldoutActionsLineageAuditError,
        match="unexpectedly acquired artifact evidence",
    ):
        projection._prove_queued_no_execution_dispatch(
            _queued_run(),
            get_run_artifacts=lambda _run_id: {
                "total_count": 1,
                "artifacts": [{"id": 1}],
            },
            get_run_jobs=_empty_jobs,
        )


def test_non_generic_dispatch_does_not_consume_no_execution_readers() -> None:
    other = {
        **_queued_run(),
        "display_title": (
            "ATHENA fresh-holdout workflow_dispatch source=33931272025 "
            "target=2026-09-05T00:07:00Z cron=7 * * * * "
            "confirm=PROSPECTIVE_ONLY_NO_BACKFILL_V1"
        ),
        "name": (
            "ATHENA fresh-holdout workflow_dispatch source=33931272025 "
            "target=2026-09-05T00:07:00Z cron=7 * * * * "
            "confirm=PROSPECTIVE_ONLY_NO_BACKFILL_V1"
        ),
    }
    touched = False

    def forbidden(_run_id: int):
        nonlocal touched
        touched = True
        raise AssertionError("grammar-valid dispatch must use continuity provenance replay")

    assert projection._prove_queued_no_execution_dispatch(
        other,
        get_run_artifacts=forbidden,
        get_run_jobs=forbidden,
    ) is False
    assert touched is False


def test_projection_removes_proven_queued_transport_before_continuity_grammar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _queued_run()
    monkeypatch.setattr(
        projection,
        "_ORIGINAL_RUN_IS_COLLECTION_CANDIDATE",
        lambda _run: False,
    )

    def fake_audit(**_kwargs):
        assert audit._run_is_collection_candidate(run) is False
        return {
            "runs": [],
            "audit_state": "VERIFIED_COMPLETE_ACTIONS_LINEAGE",
            "verified_preacquisition_control_failure_count": 0,
        }

    monkeypatch.setattr(projection, "_ORIGINAL_AUDIT_ACTIONS_LINEAGE", fake_audit)

    def forbidden_run_reader(_run_id: int):
        raise AssertionError("proven queued run must not enter continuity provenance replay")

    result = projection._audit_actions_lineage_compatible(
        repository="Thabearr/ATHENA",
        get_run_by_id=forbidden_run_reader,
        get_run_artifacts=_empty_artifacts,
        get_run_jobs=_empty_jobs,
        verify_dependencies=False,
    )

    assert result["verified_queued_no_execution_dispatch_count"] == 1
    [record] = result["projected_queued_no_execution_dispatch_runs"]
    assert record["run_id"] == 33931981258
    assert record["evidence_state"] == "VERIFIED_QUEUED_NO_EXECUTION_TRANSPORT"
    assert record["execution_provenance"] == (
        "PROSPECTIVE_CONTINUITY_DISPATCH_PENDING_NO_EXECUTION"
    )
    assert record["tick_committed"] is False
    assert record["release_state"] == "NOT_APPLICABLE_NO_ACQUISITION"
