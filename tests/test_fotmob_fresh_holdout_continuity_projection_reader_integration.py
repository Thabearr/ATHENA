from __future__ import annotations

from pathlib import Path
from typing import Any

from domain import fotmob_fresh_holdout_continuity as continuity
import scripts.audit_fotmob_fresh_holdout_actions_lineage as audit
import scripts.audit_fotmob_fresh_holdout_actions_lineage_schedule_recovery_projection as projection


SHA = "a" * 40
RAW_AUDIT = Path("scripts/audit_fotmob_fresh_holdout_actions_lineage.py")


def _watchdog() -> dict[str, Any]:
    return {
        "id": 123,
        "name": continuity.WATCHDOG_WORKFLOW_NAME,
        "path": continuity.WATCHDOG_WORKFLOW_PATH,
        "event": "schedule",
        "head_branch": "main",
        "head_sha": SHA,
        "created_at": "2026-08-29T07:03:02Z",
        "status": "completed",
        "conclusion": "success",
    }


def _dispatch() -> dict[str, Any]:
    return {
        "id": 456,
        "name": continuity.PRIMARY_WORKFLOW_NAME,
        "path": continuity.PRIMARY_WORKFLOW_PATH,
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": SHA,
        "created_at": "2026-08-29T07:07:08Z",
        "status": "completed",
        "conclusion": "success",
        "display_title": (
            "ATHENA fresh-holdout workflow_dispatch source=123 "
            "target=2026-08-29T07:07:00Z cron=7 * * * * "
            "confirm=PROSPECTIVE_ONLY_NO_BACKFILL_V1"
        ),
    }


def _watchdog_jobs() -> dict[str, Any]:
    return {
        "jobs": [
            {
                "run_id": 123,
                "workflow_name": continuity.WATCHDOG_WORKFLOW_NAME,
                "name": continuity.WATCHDOG_JOB_NAME,
                "head_branch": "main",
                "head_sha": SHA,
                "status": "completed",
                "conclusion": "success",
                "created_at": "2026-08-29T07:03:04Z",
                "steps": [
                    {"name": name, "status": "completed", "conclusion": "success"}
                    for name in continuity.WATCHDOG_PROSPECTIVE_DISPATCH_REQUIRED_STEPS
                ],
            }
        ]
    }


def _call_kwargs() -> dict[str, Any]:
    return {
        "repository": "Thabearr/ATHENA",
        "expected_main_sha": SHA,
        "get_main_ref": lambda: {"object": {"sha": SHA}},
        "get_runs_page": lambda _page, _per_page: {"workflow_runs": []},
        "get_run_artifacts": lambda _run_id: {"artifacts": []},
        "download_artifact_zip": lambda _artifact_id: b"unused",
        "get_release": lambda _tag: {},
        "download_release_asset": lambda _asset_id: b"unused",
        "get_run_jobs": lambda _run_id: _watchdog_jobs(),
        "verify_dependencies": False,
    }


def test_projection_consumes_exact_run_reader_before_frozen_raw_delegate(monkeypatch):
    received: dict[str, Any] = {}

    def raw_signature(
        *,
        repository,
        expected_main_sha,
        get_main_ref,
        get_runs_page,
        get_run_artifacts,
        download_artifact_zip,
        get_release,
        download_release_asset,
        get_run_jobs=None,
        verify_dependencies=True,
        repository_root=None,
    ):
        received["repository"] = repository
        return {"audit_state": "NO_COMPLETED_CAMPAIGN_EVIDENCE", "runs": []}

    monkeypatch.setattr(projection, "_ORIGINAL_AUDIT_ACTIONS_LINEAGE", raw_signature)
    kwargs = _call_kwargs()
    kwargs["get_run_by_id"] = lambda _run_id: _watchdog()

    result = projection._audit_actions_lineage_compatible(**kwargs)

    assert received == {"repository": "Thabearr/ATHENA"}
    assert result["verified_prospective_continuity_dispatch_count"] == 0


def test_direct_projection_reader_fetches_exact_watchdog_run_only_for_continuity(
    monkeypatch,
):
    dispatch = _dispatch()
    calls: list[str] = []

    def fake_gh_json(endpoint: str):
        calls.append(endpoint)
        assert endpoint == "/repos/Thabearr/ATHENA/actions/runs/123"
        return _watchdog()

    def fake_engine(**_kwargs):
        assert audit._run_is_collection_candidate(dispatch) is True
        return {
            "audit_state": "VERIFIED_COMPLETE_TO_LATEST_OBSERVED_RUN",
            "runs": [
                {
                    "run_id": 456,
                    "nominal_slot_utc": "2026-08-29T07:07:00Z",
                }
            ],
        }

    monkeypatch.setattr(audit, "_gh_json", fake_gh_json)
    monkeypatch.setattr(projection, "_ORIGINAL_AUDIT_ACTIONS_LINEAGE", fake_engine)

    result = projection._audit_actions_lineage_compatible(**_call_kwargs())

    assert calls == ["/repos/Thabearr/ATHENA/actions/runs/123"]
    assert result["verified_prospective_continuity_dispatch_count"] == 1
    assert result["runs"][0]["execution_provenance"] == (
        "PROSPECTIVE_CONTINUITY_DISPATCH"
    )


def test_raw_audit_source_remains_schedule_only_and_unmodified():
    text = RAW_AUDIT.read_text(encoding="utf-8")
    assert 'run.get("event") == "schedule"' in text
    assert "get_run_by_id" not in text
