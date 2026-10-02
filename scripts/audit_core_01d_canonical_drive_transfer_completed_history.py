"""Authenticate the bounded canonical Drive transfer completed-history receipt."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from scripts import audit_core_01d_retained_workflow_status_v4 as v4
from scripts import audit_core_01d_retained_workflow_status_v3 as v3
from services import athena_artifact_role_resolver as roles

ROOT = Path(__file__).resolve().parents[1]
POLICY_ID = "ATHENA_CORE_01D_CANONICAL_DRIVE_TRANSFER_COMPLETED_HISTORY_V1"
RECEIPT_PATH = "artifacts/architecture/core_01d_canonical_drive_transfer_completed_history_v1.json"


def build_receipt(status: dict | None = None) -> dict:
    status = v4.build_receipt() if status is None else status
    snapshot = v4.authenticate_sources()
    receipt = {
        "schema_version": 1, "policy_id": POLICY_ID,
        "repository": "Thabearr/ATHENA", "master_issue": 337,
        "base_main_sha": v4.BASE_MAIN_SHA, "base_tree_sha": v4.BASE_TREE_SHA,
        "workflow_tree_before_sha1": v3.WORKFLOW_TREE_SHA1,
        "workflow_tree_after_sha1": v3.WORKFLOW_TREE_SHA1,
        "workflow_count": status["workflow_count"],
        "declared_trigger_surface_count": status["trigger_surface_count"],
        "retired_workflow_count": status["retired_workflow_count"],
        "evolution_ledger_before_sha256": v3.EVOLUTION_LEDGER_SHA256,
        "evolution_ledger_after_sha256": v3.EVOLUTION_LEDGER_SHA256,
        "evolution_transition_count": 14,
        "p4_3_retirement_ledger_sha256": v3.P43_LEDGER_SHA256,
        "retained_status_v3": {"path": v4.V3_PATH, "canonical_sha256": v4.V3_SHA256,
                               "rewritten": False},
        "retained_status_v4": {"path": v4.RECEIPT_PATH,
                               "canonical_sha256": status["canonical_sha256"]},
        "workflow": status["canonical_transfer_disposition"],
        "source_warehouse_run_id": v4.SOURCE_RUN_ID,
        "source_artifact_id": v4.ARTIFACT_ID,
        "expected_archive_name": "athena-history-canonical.zip",
        "expected_archive_bytes": 2149256220,
        "expected_archive_sha256": v4.ARCHIVE_SHA256,
        "historical_transfer_run": snapshot["historical_transfer_run"],
        "current_actions_availability": snapshot["current_actions_availability"],
        "historical_part_count": 23,
        "manifest_identity": snapshot["manifest_identity"],
        "external_drive_availability": snapshot["external_drive_availability"],
        "snapshot": {"path": v4.SNAPSHOT_PATH, "source_sha256": v4.SNAPSHOT_SHA256},
        "historical_transfer_completed": True,
        "current_supported_transfer_execution": False,
        "replay_authorized": False, "dispatch_authorized": False,
        "source_workflow_edited": False, "trigger_edited": False,
        "workflow_retired_or_deleted": False,
        "artifact_count": len(status["artifact_dispositions"]),
        "artifact_workflow_edge_count": status["artifact_workflow_edge_count"],
        "artifact_trigger_relationship_count": status["artifact_trigger_relationship_count"],
        "live_relation_count": status["live_artifact_trigger_relationship_count"],
        "historical_or_spent_relation_count": status["historical_or_spent_artifact_trigger_relationship_count"],
        "blockers": {"A": "CLOSED", "B": "CLOSED", "C": "CLOSED_AS_CURRENT_DEPENDENCY_ONLY",
                     "C_closed_as_current_dependency": True,
                     "D": "REMAINS_OPEN", "remaining_ids": [v4.BLOCKER_D],
                     "historical_retention_defect_remains": True},
        "actions": dict.fromkeys((
            "provider_acquisition", "provider_action", "sportsbook_network",
            "transfer_workflow_dispatch", "workflow_dispatch", "workflow_rerun_or_cancel",
            "drive_mutation", "gmail_mutation", "historical_warehouse_rebuild",
            "artifact_recreation", "source_artifact_regeneration", "evidence_regeneration",
            "evidence_substitution", "model_validation", "model_training", "smtp",
            "share_code", "email_send", "login", "cookies", "wallet", "stake", "wager",
            "workflow_edit", "trigger_edit", "workflow_deletion", "workflow_retirement",
        ), 0),
        "action_count_scope": (
            "Operational/provider/external mutation actions only; excludes authorized "
            "Git commits/push, PR creation and the single master-issue evidence comment."
        ),
        "protected_semantic_delta": status["protected_semantic_delta"],
        "checkpoint_e_status": "INCOMPLETE", "p4_4_status": "INCOMPLETE",
        "source_review_counter_while_open": "0/5",
        "source_review_counter_if_owner_merges": "1/5",
        "mandatory_source_reread_due": False,
        "governing_reread_completed_after_pr434_before_this_pass": True,
        "post_pr434_tests_gate": {"run_id": 37024924427, "name": "Tests", "event": "push",
                                  "head_sha": v4.BASE_MAIN_SHA, "conclusion": "success",
                                  "syntax": "success", "shards_1_through_8": "success",
                                  "aggregate": "success", "rerun_performed": False},
        "terminal": v4.TERMINAL,
    }
    return v4.seal(receipt)


def validate_receipt(value: dict, expected: dict | None = None) -> None:
    v4.require(value.get("canonical_sha256") == v4.sha256(v4.canonical_bytes(
        {k: v for k, v in value.items() if k != "canonical_sha256"})),
        "Pass-3 receipt self-hash mismatch")
    v4.require(value == (build_receipt() if expected is None else expected),
               "Pass-3 receipt differs from authenticated completed-history disposition")


def audit() -> dict:
    status = v4.build_receipt()
    v4.validate_receipt(roles.strict_json((ROOT / v4.RECEIPT_PATH).read_bytes()), status)
    value = roles.strict_json((ROOT / RECEIPT_PATH).read_bytes())
    validate_receipt(value, build_receipt(status))
    return {"result": "PASS", "policy_id": POLICY_ID,
            "receipt_sha256": value["canonical_sha256"],
            "v4_sha256": status["canonical_sha256"],
            "checkpoint_e": "INCOMPLETE", "p4_4": "INCOMPLETE",
            "remaining_blockers": [v4.BLOCKER_D], "terminal": v4.TERMINAL}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.write:
            value = build_receipt()
            (ROOT / RECEIPT_PATH).write_bytes(v4.canonical_bytes(value))
            result = {"result": "WROTE", "receipt_sha256": value["canonical_sha256"]}
        else:
            result = audit()
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, AssertionError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"result": "BLOCKED", "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
