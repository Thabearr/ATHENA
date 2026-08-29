from __future__ import annotations

import hashlib
import inspect
from pathlib import Path
from typing import Any

import pytest

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


def _continuity_audit_inputs(*, current_sha: str = SHA):
    """Build one real PR151-shaped continuity artifact for raw-audit replay."""
    from tests.test_fotmob_fresh_holdout_actions_lineage_audit import (
        committed,
        evidence_bundle,
    )

    slot = "2026-08-19T00:07:00Z"
    bundle = evidence_bundle(456, slot, rows=[committed(slot)])
    watchdog = {**_watchdog(), "head_sha": SHA, "created_at": "2026-08-18T23:56:42Z"}
    dispatch = {
        **_dispatch(),
        "head_sha": SHA,
        "created_at": "2026-08-19T00:07:08Z",
        "status": "completed",
        "conclusion": "success",
    }
    dispatch["display_title"] = dispatch["display_title"].replace(
        "target=2026-08-29T07:07:00Z", "target=2026-08-19T00:07:00Z"
    )
    artifact = {
        "id": 9001,
        "name": bundle["artifact_name"],
        "expired": False,
        "digest": bundle["zip_digest"],
    }
    release = {
        "assets": [
            {
                "id": 9101,
                "name": bundle["artifact_name"],
                "state": "uploaded",
                "size": len(bundle["archive"]),
            },
            {
                "id": 9102,
                "name": bundle["artifact_name"] + ".receipt.json",
                "state": "uploaded",
                "size": len(bundle["receipt"]),
            },
        ]
    }
    return {
        "watchdog": watchdog,
        "dispatch": dispatch,
        "bundle": bundle,
        "artifact": artifact,
        "release": release,
        "readers": {
            "get_main_ref": lambda: {"object": {"sha": current_sha}},
            "get_runs_page": lambda _page, _per_page: {
                "workflow_runs": [dispatch]
            },
            "get_run_by_id": lambda run_id: watchdog,
            "get_run_artifacts": lambda run_id: {"artifacts": [artifact]},
            "download_artifact_zip": lambda _artifact_id: bundle["zip"],
            "get_release": lambda _tag: release,
            "download_release_asset": lambda asset_id: (
                bundle["archive"] if asset_id == 9101 else bundle["receipt"]
            ),
            "get_run_jobs": lambda _run_id: _watchdog_jobs(),
        },
    }


def test_projection_consumes_exact_run_reader_before_frozen_raw_delegate(monkeypatch):
    # Call the actual frozen audit implementation. If the projection-only
    # reader leaks through, Python raises for the unsupported keyword.
    monkeypatch.setattr(
        projection, "_ORIGINAL_AUDIT_ACTIONS_LINEAGE", audit.audit_actions_lineage
    )
    kwargs = _call_kwargs()
    kwargs["get_run_by_id"] = lambda _run_id: _watchdog()

    result = projection._audit_actions_lineage_compatible(**kwargs)

    assert "verified_prospective_continuity_dispatch_count" not in result
    assert "get_run_by_id" not in inspect.signature(
        audit.audit_actions_lineage
    ).parameters


def test_schedule_only_projection_preserves_pre_continuity_output_schema(monkeypatch):
    expected = {
        "audit_state": "VERIFIED_COMPLETE_TO_LATEST_OBSERVED_RUN",
        "runs": [
            {
                "run_id": 455,
                "nominal_slot_utc": "2026-08-19T00:07:00Z",
            }
        ],
        "verified_ambiguous_no_acquisition_count": 0,
        "projected_ambiguous_no_acquisition_runs": [],
        "verified_preacquisition_control_failure_count": 0,
        "projected_preacquisition_control_failure_runs": [],
    }

    monkeypatch.setattr(
        projection,
        "_ORIGINAL_AUDIT_ACTIONS_LINEAGE",
        lambda **_kwargs: {
            key: ([dict(item) for item in value] if key == "runs" else value)
            for key, value in expected.items()
        },
    )

    result = projection._audit_actions_lineage_compatible(**_call_kwargs())

    assert result == expected
    assert "verified_prospective_continuity_dispatch_count" not in result
    assert "execution_provenance" not in result["runs"][0]


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

    kwargs = _call_kwargs()
    # Keep this fixture on the committed-artifact branch; the separate
    # zero-artifact continuity lane is tested below.
    kwargs["get_run_artifacts"] = lambda _run_id: {
        "artifacts": [{"id": 1, "name": "committed"}]
    }
    result = projection._audit_actions_lineage_compatible(**kwargs)

    assert calls == ["/repos/Thabearr/ATHENA/actions/runs/123"]
    assert result["verified_prospective_continuity_dispatch_count"] == 1
    assert result["runs"][0]["execution_provenance"] == (
        "PROSPECTIVE_CONTINUITY_DISPATCH"
    )


def test_direct_projection_cli_authenticates_continuity_from_exact_run_endpoint(
    monkeypatch, capsys
):
    values = _continuity_audit_inputs()
    readers = values["readers"]
    source_endpoint = "/repos/Thabearr/ATHENA/actions/runs/123"
    calls: list[str] = []

    def fake_json(endpoint: str):
        calls.append(endpoint)
        if endpoint.endswith("/git/ref/heads/main"):
            return {"object": {"sha": SHA}}
        if "/actions/workflows/" in endpoint:
            return {"workflow_runs": [values["dispatch"]]}
        if endpoint == source_endpoint:
            return values["watchdog"]
        if endpoint == source_endpoint + "/jobs?filter=latest&per_page=100":
            return _watchdog_jobs()
        if endpoint.endswith("/actions/runs/456/artifacts"):
            return {"artifacts": [values["artifact"]]}
        if "/releases/tags/" in endpoint:
            return values["release"]
        raise AssertionError(f"unexpected GitHub JSON read: {endpoint}")

    def fake_download(endpoint: str) -> bytes:
        calls.append(endpoint)
        if endpoint.endswith("/actions/artifacts/9001/zip"):
            return values["bundle"]["zip"]
        if endpoint.endswith("/releases/assets/9101"):
            return values["bundle"]["archive"]
        if endpoint.endswith("/releases/assets/9102"):
            return values["bundle"]["receipt"]
        raise AssertionError(f"unexpected GitHub binary read: {endpoint}")

    monkeypatch.setenv("GH_TOKEN", "test-token")
    monkeypatch.setattr(audit, "_gh_json", fake_json)
    monkeypatch.setattr(projection.pr175, "_gh_download_compatible", fake_download)
    original_workflow = audit.WORKFLOW_BLOB_SHA
    original_failure = audit.FAILURE_LINEAGE_BLOB_SHA
    original_entrypoint = audit.audit_actions_lineage
    try:
        assert projection.main([
            "--repository",
            "Thabearr/ATHENA",
            "--expected-main-sha",
            SHA,
        ]) == 0
    finally:
        audit.WORKFLOW_BLOB_SHA = original_workflow
        audit.FAILURE_LINEAGE_BLOB_SHA = original_failure
        audit.audit_actions_lineage = original_entrypoint

    output = capsys.readouterr().out
    assert '"verified_prospective_continuity_dispatch_count":1' in output
    assert source_endpoint in calls
    assert source_endpoint + "/jobs?filter=latest&per_page=100" in calls
    assert not any(
        "actions/workflows/watch-fotmob-fresh-holdout-scheduler-liveness" in call
        for call in calls
    )


def test_real_projected_audit_admits_separate_watchdog_workflow_once(monkeypatch):
    values = _continuity_audit_inputs()
    calls: list[int] = []
    readers = values["readers"]

    def source_reader(run_id: int):
        calls.append(run_id)
        return readers["get_run_by_id"](run_id)

    monkeypatch.setattr(
        projection, "_ORIGINAL_AUDIT_ACTIONS_LINEAGE", audit.audit_actions_lineage
    )
    result = projection._audit_actions_lineage_compatible(
        repository="Thabearr/ATHENA",
        expected_main_sha=SHA,
        get_main_ref=readers["get_main_ref"],
        get_runs_page=readers["get_runs_page"],
        get_run_by_id=source_reader,
        get_run_artifacts=readers["get_run_artifacts"],
        download_artifact_zip=readers["download_artifact_zip"],
        get_release=readers["get_release"],
        download_release_asset=readers["download_release_asset"],
        get_run_jobs=readers["get_run_jobs"],
        verify_dependencies=False,
    )

    assert calls == [123]
    assert result["verified_completed_run_count"] == 1
    assert result["verified_prospective_continuity_dispatch_count"] == 1
    assert [record["run_id"] for record in result["runs"]] == [456]
    assert result["runs"][0]["execution_provenance"] == (
        "PROSPECTIVE_CONTINUITY_DISPATCH"
    )


def test_historical_continuity_uses_dispatch_sha_after_main_advances(monkeypatch):
    values = _continuity_audit_inputs(current_sha="b" * 40)
    readers = values["readers"]
    monkeypatch.setattr(
        projection, "_ORIGINAL_AUDIT_ACTIONS_LINEAGE", audit.audit_actions_lineage
    )

    result = projection._audit_actions_lineage_compatible(
        repository="Thabearr/ATHENA",
        expected_main_sha="b" * 40,
        get_main_ref=readers["get_main_ref"],
        get_runs_page=readers["get_runs_page"],
        get_run_by_id=readers["get_run_by_id"],
        get_run_artifacts=readers["get_run_artifacts"],
        download_artifact_zip=readers["download_artifact_zip"],
        get_release=readers["get_release"],
        download_release_asset=readers["download_release_asset"],
        get_run_jobs=readers["get_run_jobs"],
        verify_dependencies=False,
    )

    assert result["observed_main_sha"] == "b" * 40
    assert result["verified_prospective_continuity_dispatch_count"] == 1
    assert result["runs"][0]["head_sha"] == SHA


def test_natural_and_continuity_same_slot_fail_closed_without_double_evidence(
    monkeypatch,
):
    values = _continuity_audit_inputs()
    readers = values["readers"]
    from tests.test_fotmob_fresh_holdout_actions_lineage_audit import (
        committed,
        evidence_bundle,
        run,
    )

    slot = "2026-08-19T00:07:00Z"
    natural_bundle = evidence_bundle(455, slot, rows=[committed(slot)])
    natural = run(455, "2026-08-19T00:07:01Z", head_sha=SHA)
    dispatch = values["dispatch"]
    values["readers"]["get_runs_page"] = lambda _page, _per_page: {
        "workflow_runs": [natural, dispatch]
    }
    artifacts = {
        455: {
            "id": 9000,
            "name": natural_bundle["artifact_name"],
            "expired": False,
            "digest": natural_bundle["zip_digest"],
        },
        456: values["artifact"],
    }
    zips = {9000: natural_bundle["zip"], 9001: values["bundle"]["zip"]}
    release = {
        "assets": [
            {
                "id": 9201,
                "name": natural_bundle["artifact_name"],
                "state": "uploaded",
                "size": len(natural_bundle["archive"]),
            },
            {
                "id": 9202,
                "name": natural_bundle["artifact_name"] + ".receipt.json",
                "state": "uploaded",
                "size": len(natural_bundle["receipt"]),
            },
            *values["release"]["assets"],
        ]
    }
    values["readers"]["get_run_artifacts"] = lambda run_id: {
        "artifacts": [artifacts[run_id]]
    }
    values["readers"]["download_artifact_zip"] = lambda artifact_id: zips[
        artifact_id
    ]
    values["readers"]["get_release"] = lambda _tag: release
    values["readers"]["download_release_asset"] = lambda asset_id: (
        natural_bundle["archive"]
        if asset_id == 9201
        else natural_bundle["receipt"]
        if asset_id == 9202
        else values["bundle"]["archive"]
        if asset_id == 9101
        else values["bundle"]["receipt"]
    )
    monkeypatch.setattr(
        projection, "_ORIGINAL_AUDIT_ACTIONS_LINEAGE", audit.audit_actions_lineage
    )

    with pytest.raises(
        audit.FreshHoldoutActionsLineageAuditError,
        match="multiple verified workflow runs map to one nominal slot",
    ):
        projection._audit_actions_lineage_compatible(
            repository="Thabearr/ATHENA",
            expected_main_sha=SHA,
            get_main_ref=readers["get_main_ref"],
            get_runs_page=readers["get_runs_page"],
            get_run_by_id=readers["get_run_by_id"],
            get_run_artifacts=readers["get_run_artifacts"],
            download_artifact_zip=readers["download_artifact_zip"],
            get_release=readers["get_release"],
            download_release_asset=readers["download_release_asset"],
            get_run_jobs=readers["get_run_jobs"],
            verify_dependencies=False,
        )


def test_proven_continuity_duplicate_no_acquisition_is_not_lineage_evidence(
    monkeypatch,
):
    values = _continuity_audit_inputs()
    readers = values["readers"]
    import domain.fotmob_utc_native_expected_goals_fresh_holdout_schedule_recovery as recovery
    import scripts.audit_fotmob_fresh_holdout_actions_lineage as raw_audit

    dispatch_jobs = {
        "jobs": [
            {
                "name": raw_audit.failure_lineage._PREACQUISITION_JOB_NAME,
                "status": "completed",
                "conclusion": "success",
                "steps": [
                    {
                        "name": name,
                        "status": "completed",
                        "conclusion": outcome,
                    }
                    for name, outcome in recovery._CONTINUITY_NO_ACQUISITION_REQUIRED_STEP_OUTCOMES.items()
                ],
            }
        ]
    }
    readers["get_run_artifacts"] = lambda run_id: (
        {"artifacts": []} if run_id == 456 else {"artifacts": [values["artifact"]]}
    )
    readers["get_run_jobs"] = lambda run_id: (
        dispatch_jobs if run_id == 456 else _watchdog_jobs()
    )
    monkeypatch.setattr(
        projection, "_ORIGINAL_AUDIT_ACTIONS_LINEAGE", audit.audit_actions_lineage
    )

    result = projection._audit_actions_lineage_compatible(
        repository="Thabearr/ATHENA",
        expected_main_sha=SHA,
        get_main_ref=readers["get_main_ref"],
        get_runs_page=readers["get_runs_page"],
        get_run_by_id=readers["get_run_by_id"],
        get_run_artifacts=readers["get_run_artifacts"],
        download_artifact_zip=readers["download_artifact_zip"],
        get_release=readers["get_release"],
        download_release_asset=readers["download_release_asset"],
        get_run_jobs=readers["get_run_jobs"],
        verify_dependencies=False,
    )

    assert result["verified_continuity_duplicate_no_acquisition_count"] == 1
    assert result["projected_continuity_duplicate_no_acquisition_runs"][0][
        "execution_provenance"
    ] == "PROSPECTIVE_CONTINUITY_DISPATCH_NO_ACQUISITION"
    assert result["runs"] == []
    assert result["verified_completed_run_count"] == 0


def test_current_history_snapshot_records_and_replays_exact_source_run_without_network(
    monkeypatch,
):
    import domain.current_fotmob_latest_durable_fresh_history as latest
    import scripts.audit_fotmob_fresh_holdout_actions_lineage as raw_audit

    watchdog = {
        "id": 123,
        "name": continuity.WATCHDOG_WORKFLOW_NAME,
        "path": continuity.WATCHDOG_WORKFLOW_PATH,
        "event": "schedule",
        "head_branch": "main",
        "head_sha": SHA,
        "created_at": "2026-08-29T07:03:02Z",
    }
    dispatch = {"id": 456, "event": "workflow_dispatch", "head_sha": SHA}

    def replayable_audit(**kwargs):
        assert kwargs["get_main_ref"]() == {"object": {"sha": SHA}}
        assert kwargs["get_runs_page"](1, 100) == {
            "workflow_runs": [dispatch]
        }
        assert kwargs["get_run_by_id"](123) == watchdog
        assert kwargs["get_run_jobs"](123) == _watchdog_jobs()
        return {
            "schema_version": raw_audit.SCHEMA_VERSION,
            "audit_id": raw_audit.AUDIT_ID,
            "repository": "Thabearr/ATHENA",
            "expected_main_sha": SHA,
            "observed_main_sha": SHA,
            "runs": [],
            "safety": {key: False for key in raw_audit.SAFETY_KEYS},
        }

    monkeypatch.setattr(latest, "_run_reviewed_projected_audit", replayable_audit)
    recorder = latest._ReadRecorder()
    captured = latest._run_reviewed_projected_audit(
        expected_main_sha=SHA,
        get_main_ref=lambda: recorder.json(
            "main_ref", lambda: {"object": {"sha": SHA}}
        ),
        get_runs_page=lambda page, per_page: recorder.json(
            f"runs:{page}:{per_page}", lambda: {"workflow_runs": [dispatch]}
        ),
        get_run_by_id=lambda run_id: recorder.json(
            f"run:{run_id}", lambda: watchdog
        ),
        get_run_artifacts=lambda run_id: recorder.json(
            f"artifacts:{run_id}", lambda: {"artifacts": []}
        ),
        download_artifact_zip=lambda artifact_id: recorder.binary(
            f"artifact_zip:{artifact_id}", lambda: b"unused"
        ),
        get_release=lambda tag: recorder.json(f"release:{tag}", lambda: {}),
        download_release_asset=lambda asset_id: recorder.binary(
            f"release_asset:{asset_id}", lambda: b"unused"
        ),
        get_run_jobs=lambda run_id: recorder.json(
            f"jobs:{run_id}", lambda: _watchdog_jobs()
        ),
    )
    evidence = latest.GitHubActionsLineageEvidenceBundle(
        expected_main_sha=SHA,
        reads=recorder.freeze(),
        audit_result_bytes=latest._canonical(captured),
    )

    monkeypatch.setattr(
        latest.lineage_audit,
        "_gh_json",
        lambda _endpoint: (_ for _ in ()).throw(
            AssertionError("snapshot replay attempted an uncaptured GitHub read")
        ),
    )
    replay, consumed = latest._replay_audit_from_evidence(
        expected_main_sha=SHA,
        reads=evidence.reads,
    )
    assert "run:123" in {item.key for item in evidence.reads}
    assert replay == captured
    assert consumed == {item.key for item in evidence.reads}


@pytest.mark.parametrize("mutation", ["wrong_source_id", "wrong_source_sha", "bad_title"])
def test_invalid_continuity_provenance_fails_closed(monkeypatch, mutation):
    values = _continuity_audit_inputs()
    dispatch = values["dispatch"]
    readers = values["readers"]
    if mutation == "wrong_source_id":
        dispatch["display_title"] = dispatch["display_title"].replace(
            "source=123", "source=999"
        )
    elif mutation == "wrong_source_sha":
        values["watchdog"]["head_sha"] = "b" * 40
    else:
        dispatch["display_title"] = "manual workflow dispatch"

    monkeypatch.setattr(
        projection, "_ORIGINAL_AUDIT_ACTIONS_LINEAGE", audit.audit_actions_lineage
    )
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        projection._audit_actions_lineage_compatible(
            repository="Thabearr/ATHENA",
            expected_main_sha=SHA,
            get_main_ref=readers["get_main_ref"],
            get_runs_page=readers["get_runs_page"],
            get_run_by_id=readers["get_run_by_id"],
            get_run_artifacts=readers["get_run_artifacts"],
            download_artifact_zip=readers["download_artifact_zip"],
            get_release=readers["get_release"],
            download_release_asset=readers["download_release_asset"],
            get_run_jobs=readers["get_run_jobs"],
            verify_dependencies=False,
        )


def test_raw_audit_source_remains_schedule_only_and_unmodified():
    text = RAW_AUDIT.read_text(encoding="utf-8")
    assert 'run.get("event") == "schedule"' in text
    assert "get_run_by_id" not in text


def test_raw_audit_blob_pin_remains_unchanged():
    raw = RAW_AUDIT.read_bytes()
    digest = hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()
    assert digest == "e3cdb18845403d92f94933f68c2bd06e55660de0"


def test_current_history_projection_pin_matches_final_projection_blob():
    import domain.current_fotmob_latest_durable_fresh_history as latest

    projection_path = Path(
        "scripts/audit_fotmob_fresh_holdout_actions_lineage_schedule_recovery_projection.py"
    )
    raw = projection_path.read_bytes()
    digest = hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()
    assert latest.SCHEDULE_RECOVERY_PROJECTION_BLOB_SHA == digest
