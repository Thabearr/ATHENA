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


def test_bridge_pins_existing_reviewed_evidence_and_mirror_implementations() -> None:
    workflow = _workflow_text()
    for digest in (
        "f6d3e9e5e4c7306c13b2b618788811da4d2d41f8",
        "6d768a506d579ef88f1d321102cb9c53d846c72a",
        "1752fd5b96823f8b52e99a2dbbf84250676809d8",
        "ddabb6ae83cbe6c81c9264119a121a54715df960",
        "9e09e13d145f9ad2419b11073d4219aec14e54a8",
    ):
        assert digest in workflow
    assert (
        "python -m scripts.run_fotmob_fresh_holdout_release_receipt_mirror"
        in workflow
    )


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


def test_bridge_exactly_binds_bot_dispatched_continuity_identity() -> None:
    workflow = _workflow_text()
    assert 'run.get("event") == "workflow_dispatch"' in workflow
    assert 'run.get("head_branch") == "main"' in workflow
    assert 'run.get("head_sha") == watchdog_head_sha' in workflow
    assert 'run.get("name") == expected_name' in workflow
    assert 'run.get("display_title") == expected_name' in workflow
    assert "duplicate exact continuity dispatch runs detected" in workflow
    assert "transport._continuity_plan_from_run" in workflow
