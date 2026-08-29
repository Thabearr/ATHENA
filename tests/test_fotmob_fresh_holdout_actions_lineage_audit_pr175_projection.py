from pathlib import Path

import pytest
import yaml

from domain import fotmob_fresh_holdout_continuity as continuity
import scripts.audit_fotmob_fresh_holdout_actions_lineage as audit
import scripts.audit_fotmob_fresh_holdout_actions_lineage_pr175_projection as projection
import scripts.audit_fotmob_fresh_holdout_actions_lineage_schedule_recovery_projection as recovery_projection


WORKFLOW = Path(
    ".github/workflows/audit-fotmob-utc-native-xg-fresh-holdout-lineage.yml"
)
COLLECTION_WORKFLOW = Path(
    ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml"
)
FAILURE_LINEAGE = Path(
    "domain/fotmob_utc_native_expected_goals_fresh_holdout_failure_lineage.py"
)
SCHEDULE_RECOVERY = Path(
    "domain/fotmob_utc_native_expected_goals_fresh_holdout_schedule_recovery.py"
)
PROJECTION_SCRIPT = Path(
    "scripts/audit_fotmob_fresh_holdout_actions_lineage_pr175_projection.py"
)
RECOVERY_PROJECTION_SCRIPT = Path(
    "scripts/audit_fotmob_fresh_holdout_actions_lineage_schedule_recovery_projection.py"
)
AUDIT_SCRIPT = Path("scripts/audit_fotmob_fresh_holdout_actions_lineage.py")
SHA = "a" * 40


def _git_blob_sha(path: Path) -> str:
    import hashlib

    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def _continuity_runs(*, target: str = "2026-08-29T07:07:00Z"):
    watchdog = {
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
    dispatch = {
        "id": 456,
        "name": continuity.PRIMARY_WORKFLOW_NAME,
        "path": continuity.PRIMARY_WORKFLOW_PATH,
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": SHA,
        "created_at": "2026-08-29T07:07:08Z",
        "display_title": (
            "ATHENA fresh-holdout workflow_dispatch source=123 "
            f"target={target} cron=7 * * * * "
            "confirm=PROSPECTIVE_ONLY_NO_BACKFILL_V1"
        ),
    }
    jobs = {
        "jobs": [{
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
        }]
    }
    return watchdog, dispatch, jobs


def test_projection_proves_continuity_dispatch_before_candidate_admission():
    watchdog, dispatch, jobs = _continuity_runs()
    plan = recovery_projection._prove_continuity_candidate(
        dispatch,
        get_run_by_id=lambda run_id: watchdog,
        get_run_jobs=lambda run_id: jobs,
    )
    assert plan.target_slot_text == "2026-08-29T07:07:00Z"
    assert plan.target_cron == "7 * * * *"


@pytest.mark.parametrize("mutation", ["malformed_title", "wrong_watchdog", "wrong_target"])
def test_projection_rejects_unproven_continuity_dispatch(mutation: str):
    watchdog, dispatch, jobs = _continuity_runs()
    sources = {123: watchdog}
    if mutation == "malformed_title":
        dispatch["display_title"] = "manual dispatch"
    elif mutation == "wrong_watchdog":
        sources[123] = {**watchdog, "event": "workflow_dispatch"}
    else:
        dispatch["display_title"] = dispatch["display_title"].replace(
            "target=2026-08-29T07:07:00Z", "target=2026-08-29T06:37:00Z"
        )
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        recovery_projection._prove_continuity_candidate(
            dispatch,
            get_run_by_id=lambda run_id: sources[run_id],
            get_run_jobs=lambda run_id: jobs,
        )


def test_projection_retains_historical_pr175_pin_and_recovery_owns_current_workflow():
    assert projection.PRE_PR175_WORKFLOW_BLOB_SHA == audit.WORKFLOW_BLOB_SHA
    assert projection.PRE_PR175_WORKFLOW_BLOB_SHA == (
        "2310d2253b00b8ddd995d7a28e0d67e6ea9381dd"
    )
    assert projection.POST_PR175_WORKFLOW_BLOB_SHA == (
        "d48b1ff823277445e3b496876caca6b01480ece9"
    )
    assert (
        recovery_projection.PRE_AMBIGUOUS_NOOP_WORKFLOW_BLOB_SHA
        == projection.POST_PR175_WORKFLOW_BLOB_SHA
    )
    assert (
        recovery_projection.POST_AMBIGUOUS_NOOP_WORKFLOW_BLOB_SHA
        == _git_blob_sha(COLLECTION_WORKFLOW)
    )
    # Historical producer identity remains preserved as provenance, while the
    # recovery projection owns the exact current continuity-capable producer.
    assert "eb6cfd3966d7040f630fc3a51c6cad41b171bcfb" != (
        recovery_projection.POST_AMBIGUOUS_NOOP_WORKFLOW_BLOB_SHA
    )


def test_projection_pins_repaired_failure_lineage_without_changing_audit_engine():
    assert (
        projection.PRE_PREACQUISITION_FALLBACK_BLOB_SHA
        == audit.FAILURE_LINEAGE_BLOB_SHA
    )
    assert projection.POST_PREACQUISITION_FALLBACK_BLOB_SHA == _git_blob_sha(
        FAILURE_LINEAGE
    )
    assert projection.PRE_PREACQUISITION_FALLBACK_BLOB_SHA == (
        "2ae03405f63c0951eb61c4be0db1ba9dff318f21"
    )
    assert projection.POST_PREACQUISITION_FALLBACK_BLOB_SHA == (
        "692e3fe778e43ae4157e10882158f5dae08cb096"
    )
    assert recovery_projection.SCHEDULE_RECOVERY_BLOB_SHA == _git_blob_sha(
        SCHEDULE_RECOVERY
    )


def test_control_workflow_verifies_current_collection_and_projection_blobs():
    text = WORKFLOW.read_text(encoding="utf-8")
    parsed = yaml.safe_load(text)
    assert isinstance(parsed, dict)
    assert "eb6cfd3966d7040f630fc3a51c6cad41b171bcfb" in text
    assert _git_blob_sha(COLLECTION_WORKFLOW) in text
    assert "d48b1ff823277445e3b496876caca6b01480ece9" in text
    assert _git_blob_sha(PROJECTION_SCRIPT) in text
    assert _git_blob_sha(RECOVERY_PROJECTION_SCRIPT) in text
    assert _git_blob_sha(AUDIT_SCRIPT) in text
    assert _git_blob_sha(FAILURE_LINEAGE) in text
    assert _git_blob_sha(SCHEDULE_RECOVERY) in text
    assert "audit_fotmob_fresh_holdout_actions_lineage_schedule_recovery_projection.py" in text


def test_projection_delegates_to_unchanged_engine_with_compatible_binary_transport():
    text = PROJECTION_SCRIPT.read_text(encoding="utf-8")
    assert "unchanged audit engine" in text
    assert "byte-for-byte pinned" not in text
    assert "audit.WORKFLOW_BLOB_SHA = POST_PR175_WORKFLOW_BLOB_SHA" in text
    assert (
        "audit.FAILURE_LINEAGE_BLOB_SHA = POST_PREACQUISITION_FALLBACK_BLOB_SHA"
        in text
    )
    assert "audit._gh_download = _gh_download_compatible" in text
    assert "audit.main(argv)" in text
    assert "application/vnd.github+json" in text
    assert "application/octet-stream" in text
    for forbidden in (
        "requests.",
        "urllib",
        "curl ",
        "wget ",
        "rerun",
        "backfill_authorized = True",
        "pricing_authorized = True",
        "selection_authorized = True",
        "bet_authorized = True",
    ):
        assert forbidden not in text


def test_transport_uses_json_media_type_for_actions_artifact_zip(monkeypatch):
    calls = []

    def fake_check_output(args):
        calls.append(args)
        return b"artifact-zip"

    monkeypatch.setattr(projection.subprocess, "check_output", fake_check_output)
    endpoint = "/repos/Thabearr/ATHENA/actions/artifacts/9366326461/zip"
    assert projection._gh_download_compatible(endpoint) == b"artifact-zip"
    assert calls == [[
        "gh", "api", "-H", "Accept: application/vnd.github+json", endpoint
    ]]


def test_transport_keeps_octet_stream_for_release_asset(monkeypatch):
    calls = []

    def fake_check_output(args):
        calls.append(args)
        return b"release-asset"

    monkeypatch.setattr(projection.subprocess, "check_output", fake_check_output)
    endpoint = "/repos/Thabearr/ATHENA/releases/assets/123456789"
    assert projection._gh_download_compatible(endpoint) == b"release-asset"
    assert calls == [[
        "gh", "api", "-H", "Accept: application/octet-stream", endpoint
    ]]


def test_transport_rejects_unreviewed_binary_endpoint():
    with pytest.raises(
        audit.FreshHoldoutActionsLineageAuditError,
        match="unsupported GitHub binary download endpoint",
    ):
        projection._gh_download_compatible(
            "/repos/Thabearr/ATHENA/actions/runs/32256052482/logs"
        )


def test_audit_control_permissions_remain_read_only_except_issue_result_comment():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "actions: read" in text
    assert "contents: read" in text
    assert "pull-requests: read" in text
    assert "issues: write" in text
    assert "actions: write" not in text
    assert "contents: write" not in text
    assert "provider-network-acquisition-performed-by-audit: false" in text
    assert "backfill-authorized: false" in text
    assert "pricing-authorized: false" in text
    assert "selection-authorized: false" in text
    assert "bet-authorized: false" in text
