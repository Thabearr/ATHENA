from __future__ import annotations

import pytest

import scripts.audit_fotmob_fresh_holdout_actions_lineage as audit
import scripts.audit_fotmob_fresh_holdout_actions_lineage_schedule_recovery_projection as projection


def _legacy_run() -> dict[str, object]:
    return {
        "id": projection.LEGACY_QUEUED_NO_EXECUTION_RUN_ID,
        "name": projection.LEGACY_QUEUED_NO_EXECUTION_TITLE,
        "display_title": projection.LEGACY_QUEUED_NO_EXECUTION_TITLE,
        "workflow_id": projection.continuity.PRIMARY_WORKFLOW_ID,
        "path": projection.continuity.PRIMARY_WORKFLOW_PATH,
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": projection.LEGACY_QUEUED_NO_EXECUTION_HEAD_SHA,
        "status": "queued",
        "conclusion": None,
        "run_number": projection.LEGACY_QUEUED_NO_EXECUTION_RUN_NUMBER,
        "run_attempt": 1,
        "created_at": projection.LEGACY_QUEUED_NO_EXECUTION_CREATED_AT,
        "updated_at": projection.LEGACY_QUEUED_NO_EXECUTION_CREATED_AT,
        "run_started_at": projection.LEGACY_QUEUED_NO_EXECUTION_CREATED_AT,
    }


def _empty_artifacts(_run_id: int) -> dict[str, object]:
    return {"total_count": 0, "artifacts": []}


def _empty_jobs(_run_id: int) -> dict[str, object]:
    return {"total_count": 0, "jobs": []}


def test_exact_legacy_queued_dispatch_is_proven_only_with_zero_execution_evidence() -> None:
    assert projection._prove_exact_legacy_queued_no_execution_dispatch(
        _legacy_run(),
        get_run_artifacts=_empty_artifacts,
        get_run_jobs=_empty_jobs,
    ) is True


def test_legacy_queued_dispatch_metadata_drift_fails_closed() -> None:
    changed = {**_legacy_run(), "display_title": "changed"}
    with pytest.raises(
        audit.FreshHoldoutActionsLineageAuditError,
        match="legacy queued dispatch metadata drifted: display_title",
    ):
        projection._prove_exact_legacy_queued_no_execution_dispatch(
            changed,
            get_run_artifacts=_empty_artifacts,
            get_run_jobs=_empty_jobs,
        )


def test_legacy_queued_dispatch_rejects_any_job_or_artifact_appearance() -> None:
    with pytest.raises(
        audit.FreshHoldoutActionsLineageAuditError,
        match="unexpectedly acquired execution jobs",
    ):
        projection._prove_exact_legacy_queued_no_execution_dispatch(
            _legacy_run(),
            get_run_artifacts=_empty_artifacts,
            get_run_jobs=lambda _run_id: {"total_count": 1, "jobs": [{"id": 1}]},
        )

    with pytest.raises(
        audit.FreshHoldoutActionsLineageAuditError,
        match="unexpectedly acquired artifact evidence",
    ):
        projection._prove_exact_legacy_queued_no_execution_dispatch(
            _legacy_run(),
            get_run_artifacts=lambda _run_id: {
                "total_count": 1,
                "artifacts": [{"id": 1}],
            },
            get_run_jobs=_empty_jobs,
        )


def test_nonreviewed_dispatch_is_not_admitted_by_legacy_boundary() -> None:
    other = {**_legacy_run(), "id": projection.LEGACY_QUEUED_NO_EXECUTION_RUN_ID + 1}
    touched = False

    def forbidden(_run_id: int):
        nonlocal touched
        touched = True
        raise AssertionError("non-reviewed run must not consume legacy evidence readers")

    assert projection._prove_exact_legacy_queued_no_execution_dispatch(
        other,
        get_run_artifacts=forbidden,
        get_run_jobs=forbidden,
    ) is False
    assert touched is False


def test_projection_removes_exact_legacy_run_before_continuity_grammar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _legacy_run()
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
        raise AssertionError("legacy queued run must not enter continuity provenance replay")

    result = projection._audit_actions_lineage_compatible(
        repository="Thabearr/ATHENA",
        get_run_by_id=forbidden_run_reader,
        get_run_artifacts=_empty_artifacts,
        get_run_jobs=_empty_jobs,
        verify_dependencies=False,
    )

    assert result["verified_legacy_queued_no_execution_count"] == 1
    [record] = result["projected_legacy_queued_no_execution_runs"]
    assert record["run_id"] == projection.LEGACY_QUEUED_NO_EXECUTION_RUN_ID
    assert record["evidence_state"] == "VERIFIED_LEGACY_QUEUED_NO_EXECUTION"
    assert record["execution_provenance"] == (
        "PRE_CONTINUITY_LEGACY_WORKFLOW_DISPATCH_NO_EXECUTION"
    )
    assert record["tick_committed"] is False
    assert record["release_state"] == "NOT_APPLICABLE_NO_ACQUISITION"
