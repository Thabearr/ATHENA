from __future__ import annotations

from pathlib import Path


WORKFLOW = Path(
    ".github/workflows/bridge-fotmob-fresh-holdout-continuity-receipts.yml"
)


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_bridge_uses_natural_watchdog_completion_not_continuity_workflow_run() -> None:
    workflow = _workflow_text()
    assert "workflow_run:" in workflow
    assert "Watch FotMob Fresh-Holdout Scheduler Liveness" in workflow
    assert "github.event.workflow_run.event == 'schedule'" in workflow
    assert "github.event.workflow_run.conclusion == 'success'" in workflow
    assert "Bridge FotMob Fresh-Holdout Continuity Receipt Durability" in workflow
    assert "workflows:\n      - FotMob UTC-Native xG Fresh-Holdout Collection Runner" not in workflow


def test_bridge_has_exact_owner_only_manual_durability_recovery_surface() -> None:
    workflow = _workflow_text()
    assert "github.event.issue.number == 172" in workflow
    assert "github.event.comment.user.login == github.repository_owner" in workflow
    assert "/athena-mirror-fresh-holdout-continuity-receipt" in workflow
    assert "run-id: ([1-9][0-9]*)" in workflow
    assert "confirm: DURABILITY_ONLY_NO_ACQUISITION_V1" in workflow
    assert "durability bridge only accepts prospective continuity dispatch runs" in workflow


def test_bridge_pins_existing_reviewed_evidence_and_binding_implementations() -> None:
    workflow = _workflow_text()
    for digest in (
        "1efe1e34d4459b2aeea17d5da8ba77bd4e2442f2",
        "6d768a506d579ef88f1d321102cb9c53d846c72a",
        "14d6dd1000e934e21c12e64f41f67b78f2484278",
        "ddabb6ae83cbe6c81c9264119a121a54715df960",
        "f0b836304b1d46877e0396ea7a532c24b46a3d16",
        "0c99f01d38afaaad5f9deae67da441723ac0476e",
    ):
        assert digest in workflow
    assert (
        "python -m scripts.run_fotmob_fresh_holdout_release_receipt_mirror"
        in workflow
    )


def test_release_mirror_retains_the_exact_schedule_duplicate_zero_artifact_lane() -> None:
    mirror = Path("scripts/run_fotmob_fresh_holdout_release_receipt_mirror.py").read_text(
        encoding="utf-8"
    )
    assert "_prove_schedule_duplicate_no_acquisition_success" in mirror
    assert "VERIFIED_SCHEDULE_ALREADY_ATTEMPTED_NO_MIRROR_REQUIRED" in mirror


def test_bridge_is_durability_only_and_cannot_execute_collection_or_betting() -> None:
    workflow = _workflow_text()
    assert "actions: read" in workflow
    assert "contents: write" in workflow
    assert "issues: write" not in workflow
    assert "--execute-live-network" not in workflow
    assert "run_fotmob_utc_native_xg_fresh_holdout_tick.py" not in workflow
    assert "gh workflow run fotmob-utc-native-xg-fresh-holdout.yml" not in workflow
    assert "Provider acquisition: false" in workflow
    assert "Backfill: false" in workflow
    assert "Model/pricing/selection/BET authority change: false" in workflow


def test_bridge_uses_fail_closed_exact_or_generic_queued_binding() -> None:
    workflow = _workflow_text()
    assert (
        "import scripts.bind_fotmob_fresh_holdout_continuity_dispatch as dispatch_binding"
        in workflow
    )
    assert 'step.get("name") == dispatch_binding.DISPATCH_STEP_NAME' in workflow
    assert "dispatch_binding.select_dispatch_candidate(" in workflow
    assert "candidate.generic_queued_fallback" in workflow
    assert "dispatch_binding.prove_generic_queued_no_execution(" in workflow
    assert "/jobs?per_page=100" in workflow
    assert "/artifacts?per_page=100" in workflow
    assert "zero jobs and zero artifacts" in workflow
    assert "continuity dispatch binding failed closed" in workflow
    assert "transport._continuity_plan_from_run" in workflow


def test_watchdog_without_dispatch_is_green_noop_before_receipt_mirror() -> None:
    workflow = _workflow_text()
    assert 'step.get("name") == "Record prospective continuity dispatch request"' in workflow
    assert 'record.get("conclusion") == "skipped"' in workflow
    assert 'fh.write("bridge_required=false\\n")' in workflow
    assert "receipt bridge is a verified no-op" in workflow
    assert "if: steps.source.outputs.bridge_required == 'true'" in workflow
    assert "if: steps.source.outputs.bridge_required == 'false'" in workflow


def test_watchdog_noop_still_binds_exact_independent_job_provenance() -> None:
    workflow = _workflow_text()
    assert 'job.get("run_id") != watchdog_run_id' in workflow
    assert 'job.get("workflow_name") != continuity.WATCHDOG_WORKFLOW_NAME' in workflow
    assert 'job.get("head_branch") != "main"' in workflow
    assert 'job.get("head_sha") != watchdog_head_sha' in workflow
    assert 'job.get("status") != "completed"' in workflow
    assert 'job.get("conclusion") != "success"' in workflow
    assert "watchdog reviewed job did not complete successfully" in workflow


def test_watchdog_dispatch_requires_full_reviewed_jobs_provenance() -> None:
    workflow = _workflow_text()
    assert "continuity.validate_watchdog_source_jobs(" in workflow
    assert 'record.get("conclusion") != "success"' in workflow
    assert "watchdog dispatch-record step escaped success/skipped boundary" in workflow
    assert 'fh.write("bridge_required=true\\n")' in workflow


def test_bridge_wait_covers_observed_long_queue_plus_primary_execution_budget() -> None:
    workflow = _workflow_text()
    assert "timeout-minutes: 130" in workflow
    assert "for _attempt in range(3601):" in workflow
    assert "for _attempt in range(751):" not in workflow
    assert "for _attempt in range(301):" not in workflow
    assert "continuity collection run did not complete within reviewed wait" in workflow
