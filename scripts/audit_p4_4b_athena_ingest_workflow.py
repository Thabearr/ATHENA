"""Offline audit and one-time evidence builder for the P4.4B ingest ADD."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys

from scripts import audit_p4_workflow_evolution_ledger as evolution
from scripts import audit_p4_3_workflow_retirement_ledger as retirement


BASE_MAIN = "cb273ad4d0ca44f5b5fb8615ab99f1b9432dc8a3"
OLD_LEDGER_SHA = "d3ff3df8221e177460193afa093df158bcf2f045a07082f2b3e336c6b21093c6"
BEFORE_TREE = "a40328bdc4d73de7c2bc152b8fb810dcbb439f8c"
WORKFLOW = ".github/workflows/athena-ingest.yml"
SNAPSHOT = Path("artifacts/architecture/p4_workflow_evolution_snapshots/p4_4b_athena_ingest_workflow_v1.json")
RECEIPT = Path("artifacts/architecture/p4_4b_athena_ingest_workflow_v1.json")
TRANSITION_ID = "P44B_ATHENA_INGEST_ADD_V1"
POLICY_ID = "ATHENA_P4_4B_CANONICAL_INGEST_WORKFLOW_V1"
OLD_TRANSITION_IDS = (
    "P44A1_FH_VISIBILITY_BRIDGE_V1",
    "P44A1_FH_VISIBILITY_RELEASE_RECEIPTS_V1",
)
FROZEN = {
    "p4_4a_receipt_sha256": (
        "artifacts/architecture/p4_4a_workflow_evolution_guard_v1.json",
        "bd0471dc34327a16f1d501297d57017f90d535c25fbf418c772551d99d287720",
    ),
    "p4_4a1_receipt_sha256": (
        "artifacts/architecture/p4_4a1_baseline_workflow_maintenance_revision_authority_v1.json",
        "0a3833622c94f71dce0524cb9da9f77653e5f2de29d192d0a0f2e02565e4c18b",
    ),
    "fresh_holdout_hotfix_receipt_sha256": (
        "artifacts/architecture/fresh_holdout_release_visibility_race_hotfix_v1.json",
        "123e70e702a3254d7d954a78ffd2f1cecb4f513972308bee5cdff618bc7a9f1d",
    ),
}


def _git(*args: str) -> bytes:
    return subprocess.run(["git", *args], check=True, capture_output=True).stdout


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _frozen() -> dict[str, str]:
    result = {}
    for key, (path, expected) in FROZEN.items():
        value = _load(Path(path))
        if value.get("canonical_sha256") != expected or evolution.canonical_sha256(value) != expected:
            raise AssertionError(f"frozen evidence identity changed: {path}")
        result[key] = expected
    if retirement.validate_retirement_history()["canonical_sha256"] != evolution.BASE_RETIREMENT_LEDGER_SHA256:
        raise AssertionError("P4.3 retirement ledger changed")
    return result


def _workflow_tree_from_index() -> str:
    tree = _git("write-tree").decode("ascii").strip()
    return _git("rev-parse", f"{tree}:.github/workflows").decode("ascii").strip()


def _base_ledger() -> dict:
    raw = _git("show", f"{BASE_MAIN}:{evolution.LEDGER_PATH.as_posix()}")
    ledger = json.loads(raw)
    if ledger.get("canonical_sha256") != OLD_LEDGER_SHA or evolution.canonical_sha256(ledger) != OLD_LEDGER_SHA:
        raise AssertionError("P4.4B base evolution ledger identity changed")
    if len(ledger["transitions"]) != 2 or tuple(
        item["transition_id"] for item in ledger["transitions"]
    ) != OLD_TRANSITION_IDS or ledger["current_workflow_tree_sha1"] != BEFORE_TREE:
        raise AssertionError("P4.4B base transitions/tree changed")
    return ledger


def build_evidence() -> tuple[dict, dict]:
    if _git("rev-parse", "origin/main").decode("ascii").strip() != BASE_MAIN:
        raise AssertionError("authoritative main moved")
    frozen = _frozen()
    base = _base_ledger()
    index_raw = _git("show", f":{WORKFLOW}")
    identity = evolution.source_identity(index_raw)
    final_tree = _workflow_tree_from_index()
    transition = {
        "transition_id": TRANSITION_ID, "operation": "ADD", "workflow_path": WORKFLOW,
        "before": None, "after": identity, "phase_id": "P4.4B",
        "canonical_family": "ATHENA_INGEST",
        "evidence_receipt_path": RECEIPT.as_posix(),
        "checkpoint_snapshot_path": SNAPSHOT.as_posix(),
    }
    receipt = {
        "schema_version": 1, "policy_id": POLICY_ID,
        "repository_base_main_sha": BASE_MAIN,
        "reviewed_workflow_transition": copy.deepcopy(transition),
        "workflow_path": WORKFLOW, "workflow_git_blob_sha1": identity["git_blob_sha1"],
        "workflow_source_sha256": identity["source_sha256"],
        "workflow_trigger_surface": ["workflow_dispatch"],
        "scheduled_acquisition_enabled": False,
        "provider_scope": ["fotmob"], "timezone": "UTC", "ccode3": "NGA",
        "max_dates": 7, "max_provider_requests": 7, "provider_http_timeout_seconds": 30,
        "permissions": {"contents": "read"},
        "concurrency_group": "athena-ingest-fotmob", "cancel_in_progress": False,
        "job_timeout_minutes": 20, "artifact_name_pattern": "athena-ingest-${{ github.run_id }}",
        "artifact_retention_days": 30,
        "artifact_content": [
            "resolved-ingest-request.json", "canonical-store-update.json",
            "ingest-receipt.json", "replay-manifest.json", "sources/fotmob/",
        ],
        "offline_replay_supported": True,
        "offline_replay_requires_network": False,
        "offline_replay_exit_gate_satisfied": True,
        "runtime_receipt_exact_commit_sha_required": True,
        "fail_closed_partial_receipt_required": True,
        "invalid_request_partial_receipt_supported": True,
        "timeout_partial_receipt_supported": True,
        "pre_receipt_lineage_gate_non_terminal": True,
        "executor_is_authoritative_pre_acquisition_lineage_gate": True,
        "lineage_mismatch_receipt_before_provider_acquisition": True,
        "ingest_service_budget_seconds": 900,
        "workflow_job_timeout_minutes": 20,
        "receipt_finalization_headroom_seconds": 300,
        "production_database_path_added": False,
        "canonical_store_update_is_immutable_delta": True,
        "routing_authority": False, "portfolio_authority": False,
        "share_code_authority": False, "login": False, "cookies": False,
        "wallet": False, "staking": False, "wager": False,
        "model_authority": False,
        "provider_acquisition_during_pr": False,
        "provider_request_count_during_pr": 0,
        "workflow_dispatch_during_pr": False,
        "fresh_holdout_changed": False, "current_shadow_changed": False,
        "transition_id": TRANSITION_ID,
        "transition_count_before": 2, "transition_count_after": 3,
        "workflow_count_before": 37, "workflow_count_after": 38,
        "workflow_additions": 1, "workflow_revisions": 0, "workflow_deletions": 0,
        "workflow_tree_before_sha1": BEFORE_TREE,
        "workflow_tree_after_sha1": final_tree,
        "p4_3_retirement_ledger_sha256": evolution.BASE_RETIREMENT_LEDGER_SHA256,
        "legacy_ingest_workflows_retired": False,
        "p4_4_overall_complete": False,
        "architecture_checkpoint_e_fully_claimed": False,
        "next_required_step": "P4_4C_SCHEDULED_INGEST_ACTIVATION_AND_CAPABILITY_MIGRATION_REVIEW",
        "source_review_counter_while_unmerged": "3/5",
        "source_review_counter_if_merged": "4/5",
        **frozen,
        "workflow_evolution_ledger_sha256": "0" * 64,
    }
    transition["evidence_body_sha256"] = evolution.receipt_evidence_body_sha256(receipt)
    ledger = copy.deepcopy(base)
    ledger["transitions"].append(transition)
    ledger["current_live_workflow_count"] = 38
    ledger["current_workflow_tree_sha1"] = final_tree
    ledger["canonical_sha256"] = evolution.canonical_sha256(ledger)
    receipt["workflow_evolution_ledger_sha256"] = ledger["canonical_sha256"]
    receipt["canonical_sha256"] = evolution.canonical_sha256(receipt)
    return ledger, receipt


def write_evidence() -> None:
    if SNAPSHOT.exists() or RECEIPT.exists():
        if not (SNAPSHOT.is_file() and RECEIPT.is_file()):
            raise AssertionError("incomplete P4.4B evidence cannot be regenerated")
        existing_snapshot = _load(SNAPSHOT)
        existing_receipt = _load(RECEIPT)
        existing_ledger = _load(evolution.LEDGER_PATH)
        base = _base_ledger()
        if (
            existing_snapshot.get("canonical_sha256") != evolution.canonical_sha256(existing_snapshot)
            or existing_receipt.get("canonical_sha256") != evolution.canonical_sha256(existing_receipt)
            or existing_snapshot != existing_ledger
            or existing_ledger.get("transitions", [])[:2] != base.get("transitions")
            or len(existing_ledger.get("transitions", [])) != 3
            or existing_ledger["transitions"][2].get("transition_id") != TRANSITION_ID
            or existing_ledger["transitions"][2].get("workflow_path") != WORKFLOW
            or existing_ledger["transitions"][2].get("operation") != "ADD"
            or existing_receipt.get("workflow_evolution_ledger_sha256") != existing_ledger.get("canonical_sha256")
        ):
            raise AssertionError("existing P4.4B evidence is not a valid current ADD checkpoint")
    ledger, receipt = build_evidence()
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_bytes(evolution.canonical_json_bytes(ledger))
    RECEIPT.write_bytes(evolution.canonical_json_bytes(receipt))
    evolution.LEDGER_PATH.write_bytes(evolution.canonical_json_bytes(ledger))


def check() -> dict:
    frozen = _frozen()
    receipt = _load(RECEIPT)
    snapshot = _load(SNAPSHOT)
    current = evolution.validate_current_state()
    if snapshot.get("canonical_sha256") != evolution.canonical_sha256(snapshot):
        raise AssertionError("P4.4B phase snapshot hash mismatch")
    if receipt.get("canonical_sha256") != evolution.canonical_sha256(receipt):
        raise AssertionError("P4.4B receipt self-hash mismatch")
    if receipt.get("workflow_evolution_ledger_sha256") != snapshot["canonical_sha256"]:
        raise AssertionError("P4.4B receipt does not bind phase snapshot")
    if snapshot.get("transitions") != current["transitions"][:3]:
        raise AssertionError("P4.4B transition ancestry changed")
    transition = snapshot["transitions"][2]
    if transition["transition_id"] != TRANSITION_ID or transition["workflow_path"] != WORKFLOW:
        raise AssertionError("P4.4B ADD identity changed")
    if receipt.get("reviewed_workflow_transition") != {
        key: value for key, value in transition.items() if key != "evidence_body_sha256"
    }:
        raise AssertionError("P4.4B receipt transition intent changed")
    if evolution.receipt_evidence_body_sha256(receipt) != transition["evidence_body_sha256"]:
        raise AssertionError("P4.4B evidence body hash mismatch")
    if receipt.get("workflow_git_blob_sha1") != transition["after"]["git_blob_sha1"]:
        raise AssertionError("P4.4B workflow blob binding changed")
    if receipt.get("workflow_source_sha256") != transition["after"]["source_sha256"]:
        raise AssertionError("P4.4B workflow source binding changed")
    for key, value in frozen.items():
        if receipt.get(key) != value:
            raise AssertionError(f"P4.4B frozen evidence binding changed: {key}")
    for key in (
        "scheduled_acquisition_enabled", "offline_replay_requires_network",
        "production_database_path_added", "routing_authority", "portfolio_authority",
        "share_code_authority", "login", "cookies", "wallet", "staking", "wager",
        "model_authority", "provider_acquisition_during_pr", "workflow_dispatch_during_pr",
        "fresh_holdout_changed", "current_shadow_changed", "legacy_ingest_workflows_retired",
        "p4_4_overall_complete", "architecture_checkpoint_e_fully_claimed",
    ):
        if receipt.get(key) is not False:
            raise AssertionError(f"P4.4B safety flag changed: {key}")
    for key in (
        "runtime_receipt_exact_commit_sha_required", "fail_closed_partial_receipt_required",
        "invalid_request_partial_receipt_supported", "timeout_partial_receipt_supported",
        "pre_receipt_lineage_gate_non_terminal",
        "executor_is_authoritative_pre_acquisition_lineage_gate",
        "lineage_mismatch_receipt_before_provider_acquisition",
    ):
        if receipt.get(key) is not True:
            raise AssertionError(f"P4.4B durable receipt capability missing: {key}")
    if (
        receipt.get("ingest_service_budget_seconds") != 900
        or receipt.get("workflow_job_timeout_minutes") != 20
        or receipt.get("receipt_finalization_headroom_seconds") != 300
    ):
        raise AssertionError("P4.4B service/finalization budget changed")
    if receipt.get("workflow_count_before") != 37 or receipt.get("workflow_count_after") != 38:
        raise AssertionError("P4.4B workflow count changed")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--write-evidence", action="store_true")
    args = parser.parse_args()
    try:
        if args.write_evidence:
            write_evidence()
        else:
            check()
        return 0
    except (AssertionError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"P4.4B audit failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
