from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from scripts import audit_p4_workflow_evolution_ledger as evolution
from scripts import audit_p4_3_workflow_retirement_ledger as retirement


BASE = "2571354d9f5b4c1a90932fc36f6dbf6115a8bbd6"
RECEIPT_PATH = Path("artifacts/architecture/fresh_holdout_release_visibility_race_hotfix_v1.json")
TRANSPORT = "scripts/run_fotmob_fresh_holdout_release_receipt_mirror.py"
TRANSPORT_FIXTURE = Path(
    "tests/fixtures/architecture/revised_modules/"
    "run_fotmob_fresh_holdout_release_receipt_mirror-pre-visibility-race-fix.py"
)
WORKFLOW_FIXTURES = {
    ".github/workflows/bridge-fotmob-fresh-holdout-continuity-receipts.yml": Path(
        "tests/fixtures/architecture/revised_workflows/"
        "bridge-fotmob-fresh-holdout-continuity-receipts-pre-visibility-race-fix.yml"
    ),
    ".github/workflows/fotmob-utc-native-xg-fresh-holdout-release-receipts.yml": Path(
        "tests/fixtures/architecture/revised_workflows/"
        "fotmob-utc-native-xg-fresh-holdout-release-receipts-pre-visibility-race-fix.yml"
    ),
}


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _git_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def _canonical_sha(value: dict) -> str:
    body = {key: child for key, child in value.items() if key != "canonical_sha256"}
    raw = (json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
    return hashlib.sha256(raw).hexdigest()


def test_hotfix_receipt_is_canonical_and_binds_bounded_visibility_policy() -> None:
    receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
    assert receipt["canonical_sha256"] == _canonical_sha(receipt)
    assert receipt["repository_base_main_sha"] == BASE
    assert receipt["root_cause"] == "GITHUB_RELEASE_ASSET_EVENTUAL_CONSISTENCY_VISIBILITY_RACE"
    assert (receipt["visibility_attempts"], receipt["visibility_interval_seconds"], receipt["visibility_max_wait_seconds"]) == (31, 2, 60)
    assert receipt["archive_absence_retryable"] is True
    assert receipt["receipt_post_upload_absence_retryable"] is True
    assert receipt["concurrent_receipt_upload_race_retryable"] is True
    assert receipt["duplicate_asset_retryable"] is False
    assert receipt["integrity_mismatch_retryable"] is False
    assert receipt["provenance_mismatch_retryable"] is False
    assert receipt["receipt_second_upload_allowed"] is False
    assert receipt["receipt_exact_byte_verification_required"] is True


def test_exact_old_transport_and_workflow_bytes_are_preserved() -> None:
    receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
    transport_bytes = TRANSPORT_FIXTURE.read_bytes()
    assert _git_blob(transport_bytes) == receipt["transport_blob_before"]
    assert hashlib.sha256(transport_bytes).hexdigest() == receipt["transport_before_fixture_sha256"]
    assert receipt["transport_blob_before"] == "f0b836304b1d46877e0396ea7a532c24b46a3d16"
    assert _git("rev-parse", f"HEAD:{TRANSPORT}") == receipt["transport_blob_after"]
    for workflow, fixture in WORKFLOW_FIXTURES.items():
        raw = fixture.read_bytes()
        assert _git_blob(raw) == _git("rev-parse", f"HEAD:{fixture.as_posix()}")
        assert _git_blob(raw) == receipt[
            "bridge_workflow_blob_before" if "bridge-" in workflow else "release_receipts_workflow_blob_before"
        ]
        assert _git("rev-parse", f"HEAD:{workflow}") == receipt[
            "bridge_workflow_blob_after" if "bridge-" in workflow else "release_receipts_workflow_blob_after"
        ]


def test_two_reviewed_maintenance_transitions_are_exact_and_count_neutral() -> None:
    receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
    ledger = evolution.validate_current_state()
    phase_snapshot = json.loads(Path(
        "artifacts/architecture/p4_workflow_evolution_snapshots/"
        "fresh_holdout_release_visibility_race_release_receipts_v1.json"
    ).read_text(encoding="utf-8"))
    assert len(phase_snapshot["transitions"]) == receipt["workflow_evolution_transition_count"] == 2
    assert phase_snapshot["canonical_sha256"] == receipt["workflow_evolution_ledger_sha256"]
    assert phase_snapshot["current_live_workflow_count"] == receipt["workflow_count_after"] == 37
    assert phase_snapshot["current_workflow_tree_sha1"] == receipt["workflow_tree_after_sha1"]
    assert phase_snapshot["transitions"] == ledger["transitions"][:2]
    assert [item["transition_id"] for item in phase_snapshot["transitions"]] == [
        "P44A1_FH_VISIBILITY_BRIDGE_V1",
        "P44A1_FH_VISIBILITY_RELEASE_RECEIPTS_V1",
    ]
    assert all(item["operation"] == "MAINTENANCE_REVISE" for item in phase_snapshot["transitions"])
    assert all(item["canonical_family"] == "PROTECTED_RESEARCH" for item in phase_snapshot["transitions"])
    assert all(item["maintenance_contract"]["baseline_origin"] == "P4_3A_SURVIVOR" for item in phase_snapshot["transitions"])
    assert all(item["before"] != item["after"] for item in phase_snapshot["transitions"])
    assert all(item["workflow_path"] in WORKFLOW_FIXTURES for item in phase_snapshot["transitions"])
    assert retirement.validate_retirement_history()["canonical_sha256"] == "afa4a082f5225d83ca1ab32aab396b02bedf6f43dc57b6467a4187a720a0d56a"


def test_hotfix_changes_only_two_workflow_pins_and_preserves_all_other_guarded_sources() -> None:
    receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
    ledger = evolution.validate_current_state()
    changed = {
        item["workflow_path"]
        for item in ledger["transitions"]
        if item["operation"] == "MAINTENANCE_REVISE"
    }
    assert changed == set(WORKFLOW_FIXTURES)
    phase_snapshot = json.loads(Path(
        "artifacts/architecture/p4_workflow_evolution_snapshots/"
        "fresh_holdout_release_visibility_race_release_receipts_v1.json"
    ).read_text(encoding="utf-8"))
    assert phase_snapshot["current_live_workflow_count"] == receipt["workflow_count_after"] == 37
    assert phase_snapshot["current_workflow_tree_sha1"] == receipt["workflow_tree_after_sha1"]
    assert phase_snapshot["transitions"] == ledger["transitions"][:2]
    assert len(list(Path(".github/workflows").glob("*.yml"))) == ledger["current_live_workflow_count"]
    assert _git("rev-parse", "HEAD:scripts/mirror_fotmob_fresh_holdout_release_receipt.py") == receipt["frozen_core_mirror_blob_after"]
    assert _git("rev-parse", "HEAD:.github/workflows/fotmob-utc-native-xg-fresh-holdout.yml") == receipt["collection_workflow_blob_unchanged"]
    assert _git("rev-parse", "HEAD:.github/workflows/watch-fotmob-fresh-holdout-scheduler-liveness.yml") == receipt["watchdog_workflow_blob_unchanged"]
    assert _git("rev-parse", "HEAD:.github/workflows/audit-fotmob-utc-native-xg-fresh-holdout-lineage.yml") == receipt["lineage_audit_workflow_blob_unchanged"]
    assert _git("rev-parse", "HEAD:scripts/audit_fotmob_fresh_holdout_actions_lineage.py") == receipt["lineage_auditor_blob_unchanged"]
    for key in (
        "workflow_added", "workflow_deleted", "provider_acquisition", "backfill",
        "fresh_holdout_collection_triggered", "current_shadow_triggered", "p3_0_e1_triggered",
        "share_code_operation", "login", "cookies", "wallet", "staking", "wager_placed",
        "holdout_start_close_semantics_changed", "capture_schedule_semantics_changed",
        "prediction_semantics_changed", "feature_semantics_changed", "model_formula_changed",
        "pricing_changed", "router_changed", "portfolio_changed", "provider_semantics_changed",
        "authority_semantics_changed", "p4_4b_started", "p4_4_overall_complete",
        "architecture_checkpoint_e_fully_claimed",
    ):
        assert receipt[key] is False
    assert receipt["provider_request_count"] == 0
    assert receipt["workflow_revised_count"] == 2
