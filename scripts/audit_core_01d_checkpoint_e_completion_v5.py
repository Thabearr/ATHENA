"""Authenticate the additive B2 Checkpoint-E authority overlay."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
from scripts import audit_core_01d_historical_warehouse_transfer_authority_b2 as b2

ROOT = boundary.ROOT
POLICY_ID = "ATHENA_CORE_01D_CHECKPOINT_E_COMPLETION_V5"
PARENT_PATH = b2.COMPLETION_V4_PATH
PARENT_SHA = b2.COMPLETION_V4_SHA
RECEIPT_PATH = "tests/fixtures/core_01d/core-01d-checkpoint-e-completion-v5.json"
TARGET_KEYS = set(b2.TARGET_KEYS)


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise AssertionError(reason)


def build_receipt() -> dict[str, object]:
    parent = boundary.read(PARENT_PATH)
    require(parent.get("canonical_sha256") == PARENT_SHA, "immutable Completion V4 identity drift")
    completion_v3 = boundary.read("artifacts/architecture/core_01d_checkpoint_e_completion_v3.json")
    require(completion_v3["canonical_sha256"] == b2.COMPLETION_V3_SHA,
            "immutable historical Completion V3 identity drift")
    b2.audit()
    review = boundary.read(b2.RECEIPT_PATH)
    inherited = parent["unreviewed_authority_surfaces"]
    inherited_keys = [(row["workflow_path"], row["trigger_kind"]) for row in inherited]
    require(len(inherited) == 25 and len(set(inherited_keys)) == 25,
            "Completion V4 unresolved surface census drift")
    require(TARGET_KEYS <= set(inherited_keys), "B2 target is not in the inherited unresolved set")
    rows = {(row["workflow_path"], row["trigger_kind"]): row for row in review["review_rows"]}
    require(set(rows) == TARGET_KEYS, "B2 receipt target key set drift")
    resolved = {key for key, row in rows.items() if row["review"]["status"] == "RESOLVED"}
    remaining = [deepcopy(row) for row in inherited if (row["workflow_path"], row["trigger_kind"]) not in resolved]
    require(len(remaining) == 25 - len(resolved), "remaining global unknown count is not derived")
    require(all((row["workflow_path"], row["trigger_kind"]) not in resolved for row in remaining),
            "surface duplicated in resolved and unresolved sets")
    criteria = deepcopy(parent["checkpoint_criteria"])
    require(len(criteria) == 19, "Completion V4 criterion set drift")
    require(criteria["all_retained_workflow_authority_and_dynamic_reachability_review_complete"] is False,
            "B2 cannot resolve global authority review")
    require(criteria["no_unknown_current_artifact_or_notification_authority"] is False,
            "B2 cannot resolve global unknown authority")
    summaries = [{
        "workflow_path": key[0],
        "trigger_kind": key[1],
        "current_reachability": rows[key]["current_reachability"]["status"],
        "review_status": rows[key]["review"]["status"],
        "receipt_sha256": review["canonical_sha256"],
    } for key in b2.TARGET_KEYS]
    return boundary.seal({
        "schema_version": 5,
        "policy_id": POLICY_ID,
        "repository": "Thabearr/ATHENA",
        "master_issue": 337,
        "base_main_sha": b2.BASE_MAIN,
        "base_tree_sha": b2.BASE_TREE,
        "predecessor_completion_v4": {"path": PARENT_PATH, "canonical_sha256": PARENT_SHA, "rewritten": False},
        "predecessor_completion_v2": deepcopy(completion_v3["predecessor_completion_v2"]),
        "predecessor_b1_review": {"path": b2.B1_RECEIPT_PATH, "canonical_sha256": b2.B1_RECEIPT_SHA, "rewritten": False},
        "retained_v5": deepcopy(completion_v3["retained_v5"]),
        "pass_a_review": deepcopy(completion_v3["pass_a_review"]),
        "a2_review": deepcopy(completion_v3["a2_review"]),
        "b2_review": {"path": b2.RECEIPT_PATH, "canonical_sha256": review["canonical_sha256"]},
        "b2_source_inventory": {"path": b2.SOURCE_INVENTORY_PATH,
                                 "canonical_sha256": review["source_inventory"]["canonical_sha256"]},
        "scope": {
            "inherited_unreviewed_count": len(inherited),
            "target_surface_count": len(TARGET_KEYS),
            "resolved_target_count": len(resolved),
            "partial_target_count": len(TARGET_KEYS) - len(resolved),
            "remaining_global_unreviewed_surface_count": len(remaining),
            "target_keys": [[path, event] for path, event in b2.TARGET_KEYS],
        },
        "remaining_unreviewed_surface_count": len(remaining),
        "reviewed_target_surfaces": summaries,
        "unresolved_target_keys": [[path, event] for path, event in sorted(TARGET_KEYS - resolved)],
        "unreviewed_authority_surfaces": remaining,
        "checkpoint_criteria": criteria,
        "checkpoint_e_status": "INCOMPLETE",
        "p4_4_status": "INCOMPLETE",
        "remaining_blocker_ids": deepcopy(parent["remaining_blocker_ids"]),
        "workflow_count": parent["workflow_count"],
        "trigger_surface_count": parent["trigger_surface_count"],
        "workflow_tree_before_sha1": parent["workflow_tree_before_sha1"],
        "workflow_tree_after_sha1": parent["workflow_tree_after_sha1"],
        "evolution_ledger_before_sha256": parent["evolution_ledger_before_sha256"],
        "evolution_ledger_after_sha256": parent["evolution_ledger_after_sha256"],
        "transition_count": parent["transition_count"],
        "retirement_ledger_sha256": parent["retirement_ledger_sha256"],
        "retired_workflow_count": parent["retired_workflow_count"],
        "live_missing_artifact_relation_count": parent["live_missing_artifact_relation_count"],
        "historical_missing_artifact_relation_count": parent["historical_missing_artifact_relation_count"],
        "retention_blockers_A_B_C_D": parent["retention_blockers_A_B_C_D"],
        "workflow_edit_count": 0,
        "trigger_edit_count": 0,
        "workflow_retirement_count": 0,
        "workflow_deletion_count": 0,
        "caller_migration_count": 0,
        "actions": b2.ZERO_ACTIONS,
        "source_review_counter_while_open": "1/5",
        "source_review_counter_if_owner_merges": "2/5",
        "mandatory_governing_source_reread_after_b2_merge": False,
        "terminal": ("CORE_01D_HISTORICAL_WAREHOUSE_TRANSFER_AUTHORITY_B2_REVIEW_READY_5_RESOLVED_DO_NOT_MERGE"
                     if len(resolved) == 5 else
                     "CORE_01D_HISTORICAL_WAREHOUSE_TRANSFER_AUTHORITY_B2_REVIEW_READY_PARTIAL_DO_NOT_MERGE"),
    })


def validate_receipt(value: dict[str, object], expected: dict[str, object] | None = None) -> None:
    require((ROOT / RECEIPT_PATH).read_bytes() == boundary.canonical(value), "Completion V5 is not canonical")
    require(value == (build_receipt() if expected is None else expected),
            "Completion V5 differs from immutable V4 plus the authenticated B2 overlay")
    require(value["scope"]["remaining_global_unreviewed_surface_count"] == 25 - value["scope"]["resolved_target_count"],
            "Completion V5 unknown count is not derived")
    require(value["checkpoint_e_status"] == value["p4_4_status"] == "INCOMPLETE",
            "B2 cannot complete Checkpoint E or P4.4")
    require(value["checkpoint_criteria"]["all_retained_workflow_authority_and_dynamic_reachability_review_complete"] is False
            and value["checkpoint_criteria"]["no_unknown_current_artifact_or_notification_authority"] is False,
            "global Checkpoint-E criteria 11 and 14 must remain false")


def audit() -> dict[str, object]:
    value = boundary.read(RECEIPT_PATH)
    validate_receipt(value)
    return {"result": "PASS", "receipt_sha256": value["canonical_sha256"],
            "resolved_target_count": value["scope"]["resolved_target_count"],
            "remaining_unreviewed_surface_count": value["scope"]["remaining_global_unreviewed_surface_count"],
            "remaining_blockers": value["remaining_blocker_ids"],
            "checkpoint_e": value["checkpoint_e_status"], "p4_4": value["p4_4_status"],
            "terminal": value["terminal"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.write:
        value = build_receipt()
        (ROOT / RECEIPT_PATH).write_bytes(boundary.canonical(value))
        print(value["canonical_sha256"])
    else:
        print(json.dumps(audit(), sort_keys=True))


if __name__ == "__main__":
    main()
