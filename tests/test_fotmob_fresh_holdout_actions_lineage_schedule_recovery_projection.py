from __future__ import annotations

from typing import Any

import scripts.audit_fotmob_fresh_holdout_actions_lineage as audit
import scripts.audit_fotmob_fresh_holdout_actions_lineage_schedule_recovery_projection as projection


def _run(run_id: int, *, conclusion: str = "success") -> dict[str, Any]:
    return {
        "id": run_id,
        "name": audit.WORKFLOW_NAME,
        "path": audit.WORKFLOW_PATH,
        "event": "schedule",
        "head_branch": "main",
        "status": "completed",
        "conclusion": conclusion,
        "created_at": "2026-08-24T07:15:21Z",
        "head_sha": "a" * 40,
    }


def _safe_noop_jobs() -> dict[str, Any]:
    import domain.fotmob_utc_native_expected_goals_fresh_holdout_schedule_recovery as recovery

    return {
        "jobs": [
            {
                "name": "execute fresh holdout tick",
                "status": "completed",
                "conclusion": "success",
                "steps": [
                    {
                        "name": name,
                        "status": "completed",
                        "conclusion": conclusion,
                    }
                    for name, conclusion in recovery._NO_ACQUISITION_REQUIRED_STEP_OUTCOMES.items()
                ],
            }
        ]
    }


def test_projection_excludes_only_proven_ambiguous_no_acquisition_run(monkeypatch):
    noop = _run(101)
    normal = _run(102)
    observed: dict[str, bool] = {}

    def fake_engine(**kwargs):
        observed["noop_candidate"] = audit._run_is_collection_candidate(noop)
        observed["normal_candidate"] = audit._run_is_collection_candidate(normal)
        assert kwargs["get_run_artifacts"](101) == {"artifacts": []}
        return {"audit_state": "VERIFIED_COMPLETE_TO_LATEST_OBSERVED_RUN"}

    monkeypatch.setattr(projection, "_ORIGINAL_AUDIT_ACTIONS_LINEAGE", fake_engine)

    def artifacts(run_id: int):
        if run_id == 101:
            return {"artifacts": []}
        return {"artifacts": [{"id": 1, "name": "canonical"}]}

    result = projection._audit_actions_lineage_compatible(
        repository="Thabearr/ATHENA",
        expected_main_sha="b" * 40,
        get_main_ref=lambda: {"sha": "b" * 40},
        get_runs_page=lambda _page, _per_page: {"workflow_runs": []},
        get_run_artifacts=artifacts,
        download_artifact_zip=lambda _artifact_id: b"unused",
        get_release=lambda _tag: {},
        download_release_asset=lambda _asset_id: b"unused",
        get_run_jobs=lambda _run_id: _safe_noop_jobs(),
        verify_dependencies=False,
    )

    assert observed == {"noop_candidate": False, "normal_candidate": True}
    assert result["verified_ambiguous_no_acquisition_count"] == 1
    assert result["projected_ambiguous_no_acquisition_runs"][0]["run_id"] == 101
    assert (
        result["projected_ambiguous_no_acquisition_runs"][0]["evidence_state"]
        == "VERIFIED_AMBIGUOUS_NO_ACQUISITION"
    )


def test_projection_keeps_unproven_green_zero_artifact_run_as_candidate(monkeypatch):
    unsafe = _run(103)
    observed: dict[str, bool] = {}

    def fake_engine(**_kwargs):
        observed["candidate"] = audit._run_is_collection_candidate(unsafe)
        return {"audit_state": "PARTIAL_UNVERIFIED_GITHUB_LINEAGE"}

    monkeypatch.setattr(projection, "_ORIGINAL_AUDIT_ACTIONS_LINEAGE", fake_engine)
    jobs = _safe_noop_jobs()
    jobs["jobs"][0]["steps"] = [
        step
        for step in jobs["jobs"][0]["steps"]
        if step["name"] != "Acknowledge ambiguous schedule without acquisition"
    ]

    result = projection._audit_actions_lineage_compatible(
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

    assert observed == {"candidate": True}
    assert result["verified_ambiguous_no_acquisition_count"] == 0
    assert result["projected_ambiguous_no_acquisition_runs"] == []


def test_projection_contains_no_provider_or_write_transport():
    from pathlib import Path

    text = Path(
        "scripts/audit_fotmob_fresh_holdout_actions_lineage_schedule_recovery_projection.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "requests.",
        "urllib",
        "curl ",
        "wget ",
        "gh release",
        "rerun",
        "backfill_authorized = True",
        "pricing_authorized = True",
        "selection_authorized = True",
        "bet_authorized = True",
    ):
        assert forbidden not in text
