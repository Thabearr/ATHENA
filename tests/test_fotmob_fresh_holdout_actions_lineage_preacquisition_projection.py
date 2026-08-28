from __future__ import annotations

from typing import Any

import scripts.audit_fotmob_fresh_holdout_actions_lineage as audit
import scripts.audit_fotmob_fresh_holdout_actions_lineage_schedule_recovery_projection as projection


def _run(run_id: int, *, conclusion: str = "failure") -> dict[str, Any]:
    return {
        "id": run_id,
        "name": audit.WORKFLOW_NAME,
        "path": audit.WORKFLOW_PATH,
        "event": "schedule",
        "head_branch": "main",
        "status": "completed",
        "conclusion": conclusion,
        "created_at": "2026-08-20T01:47:16Z",
        "head_sha": "1fff09329978ecf18befc0a77ad5f8ae6f8f9495",
    }


def _preacquisition_jobs(*, proved: bool = True) -> dict[str, Any]:
    expected = dict(audit.failure_lineage._PREACQUISITION_ALLOWED_STEP_OUTCOMES[0])
    if not proved:
        expected["Restore newest durable lineage and resolve schedule slot"] = "success"
        expected["Restore or materialize PR119 bootstrap projection"] = "success"
    return {
        "jobs": [
            {
                "name": audit.failure_lineage._PREACQUISITION_JOB_NAME,
                "status": "completed",
                "conclusion": "failure",
                "steps": [
                    {
                        "name": name,
                        "status": "completed",
                        "conclusion": conclusion,
                    }
                    for name, conclusion in expected.items()
                ],
            }
        ]
    }


def _call_projection(monkeypatch, fake_engine, jobs):
    monkeypatch.setattr(projection, "_ORIGINAL_AUDIT_ACTIONS_LINEAGE", fake_engine)
    return projection._audit_actions_lineage_compatible(
        repository="Thabearr/ATHENA",
        expected_main_sha="b" * 40,
        get_main_ref=lambda: {"sha": "b" * 40},
        get_runs_page=lambda _page, _per_page: {"workflow_runs": []},
        get_run_artifacts=lambda _run_id: {"artifacts": []},
        download_artifact_zip=lambda _artifact_id: b"unused",
        get_release=lambda _tag: {},
        download_release_asset=lambda _asset_id: b"unused",
        get_run_jobs=lambda _run_id: jobs,
        verify_dependencies=False,
    )


def test_run_32322275920_is_transparent_after_canonical_lineage_closed(monkeypatch):
    target = _run(32322275920)
    observed: dict[str, bool] = {}

    def fake_engine(**_kwargs):
        observed["candidate"] = audit._run_is_collection_candidate(target)
        return {
            "audit_state": "VERIFIED_COMPLETE_TO_LATEST_OBSERVED_RUN",
            "campaign_origin_recovery_state": audit.CAMPAIGN_ORIGIN_RECOVERY_CLOSED,
            "verified_preacquisition_control_failure_count": 0,
        }

    result = _call_projection(monkeypatch, fake_engine, _preacquisition_jobs())

    assert observed == {"candidate": False}
    assert result["verified_preacquisition_control_failure_count"] == 1
    assert result["campaign_origin_recovery_state"] == (
        audit.CAMPAIGN_ORIGIN_RECOVERY_CLOSED
    )
    assert result["audit_state"] == "VERIFIED_COMPLETE_TO_LATEST_OBSERVED_RUN"
    projected = result["projected_preacquisition_control_failure_runs"]
    assert len(projected) == 1
    assert projected[0]["run_id"] == 32322275920
    assert projected[0]["evidence_state"] == (
        "VERIFIED_PREACQUISITION_CONTROL_FAILURE"
    )
    assert projected[0]["tick_committed"] is False
    assert projected[0]["nominal_slot_utc"] is None


def test_projected_preacquisition_failure_before_genesis_keeps_partial_state(monkeypatch):
    target = _run(200)

    def fake_engine(**_kwargs):
        assert audit._run_is_collection_candidate(target) is False
        return {
            "audit_state": "NO_COMPLETED_CAMPAIGN_EVIDENCE",
            "campaign_origin_recovery_state": audit.CAMPAIGN_ORIGIN_RECOVERY_OPEN,
            "verified_preacquisition_control_failure_count": 0,
        }

    result = _call_projection(monkeypatch, fake_engine, _preacquisition_jobs())

    assert result["verified_preacquisition_control_failure_count"] == 1
    assert result["campaign_origin_recovery_state"] == (
        audit.CAMPAIGN_ORIGIN_RECOVERY_OPEN
    )
    assert result["audit_state"] == "PARTIAL_UNVERIFIED_GITHUB_LINEAGE"


def test_unproven_zero_artifact_failure_remains_fail_closed_candidate(monkeypatch):
    target = _run(201)
    observed: dict[str, bool] = {}

    def fake_engine(**_kwargs):
        observed["candidate"] = audit._run_is_collection_candidate(target)
        return {
            "audit_state": "PARTIAL_UNVERIFIED_GITHUB_LINEAGE",
            "campaign_origin_recovery_state": audit.CAMPAIGN_ORIGIN_RECOVERY_CLOSED,
            "verified_preacquisition_control_failure_count": 0,
        }

    result = _call_projection(
        monkeypatch,
        fake_engine,
        _preacquisition_jobs(proved=False),
    )

    assert observed == {"candidate": True}
    assert result["verified_preacquisition_control_failure_count"] == 0
    assert result["projected_preacquisition_control_failure_runs"] == []
    assert result["audit_state"] == "PARTIAL_UNVERIFIED_GITHUB_LINEAGE"
