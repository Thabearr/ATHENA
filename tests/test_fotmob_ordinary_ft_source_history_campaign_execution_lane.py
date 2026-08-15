from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/execute-fotmob-ordinary-ft-source-history-campaign.yml"
DOC = ROOT / "docs/fotmob_ordinary_ft_source_history_campaign_execution_lane.md"


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_execution_lane_is_issue_comment_only_and_owner_controlled() -> None:
    text = _workflow()
    assert "issue_comment:" in text
    assert "types: [created]" in text
    assert "pull_request:" not in text
    assert "push:" not in text
    assert "schedule:" not in text
    assert "workflow_dispatch:" not in text
    assert "github.event.issue.number == 103" in text
    assert "github.event.comment.user.login == 'Thabearr'" in text
    assert "github.event.comment.body, '/athena-run-fotmob-history'" in text
    assert "confirm: EXECUTE_4410_LIVE_CAPTURES" in text


def test_execution_lane_is_one_shot_and_requires_merged_control_pr() -> None:
    text = _workflow()
    assert "Campaign control PR must already be merged and closed." in text
    assert "ATHENA_FOTMOB_HISTORY_EXECUTION_ATTEMPT_V1" in text
    assert "A prior campaign execution attempt marker already exists" in text
    assert "automatic replay is forbidden" in text
    assert "cancel-in-progress: false" in text


def test_execution_lane_pins_exact_reviewed_runner_and_capture_blobs() -> None:
    text = _workflow()
    for blob in (
        "533b339bcb2d6721dae55c699327b53eabbffb09",
        "6f067b8f069a760248a3b0b624c88d4f91aaa7ef",
        "39541b351d2990f7ebb9572a8c9c674c85864284",
        "10b8858ab62f2708bd564d578a627c43718e5a12",
        "ca2149395de868104666620173b55a880b10c729",
    ):
        assert blob in text
    assert "persist-credentials: false" in text


def test_execution_lane_uses_only_full_reviewed_live_command() -> None:
    text = _workflow()
    assert (
        "python scripts/run_fotmob_ordinary_ft_source_history_acquisition.py \\\n            --execute-live-network"
        in text
    )
    assert "--max-successful-slots" not in text
    assert "timeout-minutes: 330" in text
    assert "completed_slots': 4410" in text
    assert "total_slots': 4410" in text
    assert "campaign index does not contain exactly 4410 successful slot entries" in text


def test_execution_lane_permissions_and_evidence_are_fail_closed() -> None:
    text = _workflow()
    assert "contents: read" in text
    assert "issues: write" in text
    assert "contents: write" not in text
    assert "actions/upload-artifact@v4" in text
    assert "id: upload" in text
    assert "if: always()" in text
    assert "retention-days: 30" in text
    assert "athena-research-cache.tar.gz" in text
    assert "historical_coverage_claimed_by_workflow': False" in text
    assert "downstream_authority_granted': False" in text
    assert "PACKAGE_OUTCOME: ${{ steps.package.outcome }}" in text
    assert "UPLOAD_OUTCOME: ${{ steps.upload.outcome }}" in text
    assert "process.env.PACKAGE_OUTCOME === 'success'" in text
    assert "process.env.UPLOAD_OUTCOME === 'success'" in text
    assert "EXECUTION_NOT_QUALIFIED_REVIEW_ARTIFACT_BEFORE_ANY_RETRY" in text


def test_execution_lane_documentation_keeps_capability_boundary_closed() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "does not itself execute the campaign" in text
    assert "does **not** promote `historical_coverage`" in text
    assert "Model, probability, pricing, selection, production, and BET authority remain false" in text
    assert "reviewed campaign execution receipt/assessment" in text
