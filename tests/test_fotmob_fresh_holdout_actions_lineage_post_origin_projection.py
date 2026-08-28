from __future__ import annotations

from typing import Any

import domain.fotmob_utc_native_expected_goals_fresh_holdout_failure_lineage as failure_lineage
import scripts.audit_fotmob_fresh_holdout_actions_lineage as audit
import scripts.audit_fotmob_fresh_holdout_actions_lineage_post_origin_projection as projection
import scripts.audit_fotmob_fresh_holdout_actions_lineage_schedule_recovery_projection as schedule_projection


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
        "head_sha": "a" * 40,
    }


def _safe_preacquisition_failure_jobs() -> dict[str, Any]:
    expected = failure_lineage._PREACQUISITION_ALLOWED_STEP_OUTCOMES[0]
    return {
        "jobs": [
            {
                "name": "execute fresh holdout tick",
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


def _kwargs(get_run_artifacts, get_run_jobs):
    return {
        "repository": "Thabearr/ATHENA",
        "expected_main_sha": "b" * 40,
        "get_main_ref": lambda: {"sha": "b" * 40},
        "get_runs_page": lambda _page, _per_page: {"workflow_runs": []},
        "get_run_artifacts": get_run_artifacts,
        "download_artifact_zip": lambda _artifact_id: b"unused",
        "get_release": lambda _tag: {},
        "download_release_asset": lambda _asset_id: b"unused",
        "get_run_jobs": get_run_jobs,
        "verify_dependencies": False,
    }


def test_projection_excludes_exact_post_origin_preacquisition_failure(monkeypatch):
    historical = _run(32322275920)
    observed: dict[str, bool] = {}

    def fake_base(**_kwargs):
        observed["candidate"] = schedule_projection._ORIGINAL_RUN_IS_COLLECTION_CANDIDATE(
            historical
        )
        return {
            "audit_state": "VERIFIED_COMPLETE_TO_LATEST_OBSERVED_RUN",
            "verified_preacquisition_control_failure_count": 2,
            "verified_ambiguous_no_acquisition_count": 1,
        }

    monkeypatch.setattr(projection, "_BASE_COMPATIBLE_AUDIT", fake_base)
    result = projection._audit_actions_lineage_compatible(
        **_kwargs(
            lambda _run_id: {"artifacts": []},
            lambda _run_id: _safe_preacquisition_failure_jobs(),
        )
    )

    assert observed == {"candidate": False}
    assert result["verified_preacquisition_control_failure_count"] == 3
    assert result["projected_post_origin_preacquisition_failure_count"] == 1
    record = result["projected_post_origin_preacquisition_failure_runs"][0]
    assert record["run_id"] == 32322275920
    assert record["evidence_state"] == "VERIFIED_PREACQUISITION_CONTROL_FAILURE"
    assert record["nominal_slot_utc"] is None
    assert record["tick_committed"] is False
    assert record["genesis_reopened"] is False


def test_projection_keeps_zero_artifact_failure_when_job_shape_is_not_proven(monkeypatch):
    unsafe = _run(32322275921)
    observed: dict[str, bool] = {}

    def fake_base(**_kwargs):
        observed["candidate"] = schedule_projection._ORIGINAL_RUN_IS_COLLECTION_CANDIDATE(
            unsafe
        )
        return {
            "audit_state": "PARTIAL_UNVERIFIED_GITHUB_LINEAGE",
            "verified_preacquisition_control_failure_count": 0,
            "verified_ambiguous_no_acquisition_count": 0,
        }

    monkeypatch.setattr(projection, "_BASE_COMPATIBLE_AUDIT", fake_base)
    jobs = _safe_preacquisition_failure_jobs()
    jobs["jobs"][0]["steps"][0]["conclusion"] = "success"
    result = projection._audit_actions_lineage_compatible(
        **_kwargs(
            lambda _run_id: {"artifacts": []},
            lambda _run_id: jobs,
        )
    )

    assert observed == {"candidate": True}
    assert result["verified_preacquisition_control_failure_count"] == 0
    assert result["projected_post_origin_preacquisition_failure_count"] == 0
    assert result["projected_post_origin_preacquisition_failure_runs"] == []


def test_projection_keeps_failure_with_any_artifact(monkeypatch):
    candidate = _run(32322275922)
    observed: dict[str, bool] = {}

    def fake_base(**_kwargs):
        observed["candidate"] = schedule_projection._ORIGINAL_RUN_IS_COLLECTION_CANDIDATE(
            candidate
        )
        return {
            "audit_state": "PARTIAL_UNVERIFIED_GITHUB_LINEAGE",
            "verified_preacquisition_control_failure_count": 0,
            "verified_ambiguous_no_acquisition_count": 0,
        }

    monkeypatch.setattr(projection, "_BASE_COMPATIBLE_AUDIT", fake_base)
    result = projection._audit_actions_lineage_compatible(
        **_kwargs(
            lambda _run_id: {"artifacts": [{"id": 1, "name": "evidence"}]},
            lambda _run_id: (_ for _ in ()).throw(AssertionError("jobs not required")),
        )
    )

    assert observed == {"candidate": True}
    assert result["projected_post_origin_preacquisition_failure_count"] == 0


def test_projection_restores_base_candidate_after_exception(monkeypatch):
    original = schedule_projection._ORIGINAL_RUN_IS_COLLECTION_CANDIDATE

    def explode(**_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(projection, "_BASE_COMPATIBLE_AUDIT", explode)
    try:
        projection._audit_actions_lineage_compatible(
            **_kwargs(
                lambda _run_id: {"artifacts": []},
                lambda _run_id: _safe_preacquisition_failure_jobs(),
            )
        )
    except RuntimeError as exc:
        assert str(exc) == "boom"
    else:
        raise AssertionError("expected fake base failure")
    assert schedule_projection._ORIGINAL_RUN_IS_COLLECTION_CANDIDATE is original


def test_projection_contains_no_provider_or_mutating_transport():
    from pathlib import Path

    text = Path(
        "scripts/audit_fotmob_fresh_holdout_actions_lineage_post_origin_projection.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "requests.",
        "urllib",
        "curl ",
        "wget ",
        "gh release",
        "rerun",
        "backfill_authorized = True",
        "production_authorized = True",
        "pricing_authorized = True",
        "selection_authorized = True",
        "bet_authorized = True",
    ):
        assert forbidden not in text
