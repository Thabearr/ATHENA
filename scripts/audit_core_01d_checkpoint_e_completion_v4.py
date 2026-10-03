"""Derive the current Checkpoint-E state after the bounded B1 surface review."""
from __future__ import annotations

import argparse
from copy import deepcopy

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
from scripts import audit_core_01d_exact_pr_trigger_disposition_b1 as b1

ROOT = boundary.ROOT
POLICY_ID = "ATHENA_CORE_01D_CHECKPOINT_E_COMPLETION_V4"
PARENT_PATH = boundary.COMPLETION_PATH
RECEIPT_PATH = "tests/fixtures/core_01d/core-01d-checkpoint-e-completion-v4.json"
EXPECTED_PARENT_SHA = "27516b35fb5e836ac2d851fa60e4300ebf347e00b00f3858b46671cd77af9d79"
TARGET_KEYS = set(b1.TARGET_KEYS)


def build_receipt() -> dict[str, object]:
    parent = boundary.read(PARENT_PATH)
    boundary.require(parent.get("canonical_sha256") == EXPECTED_PARENT_SHA,
                     "immutable Completion V3 identity drift")
    b1.audit()
    review = boundary.read(b1.RECEIPT_PATH)
    inherited = parent["unreviewed_authority_surfaces"]
    inherited_keys = [(row["workflow_path"], row["trigger_kind"]) for row in inherited]
    boundary.require(len(inherited) == 32 and len(set(inherited_keys)) == 32,
                     "Completion V3 unresolved surface census drift")
    target_keys = {(b1.TARGETS[key]["path"], "pull_request") for key in b1.TARGET_KEYS}
    boundary.require(target_keys <= set(inherited_keys), "a B1 target is not inherited unresolved")
    review_rows = {(row["workflow_path"], row["trigger_kind"]): row
                   for row in review["review_rows"]}
    boundary.require(set(review_rows) == target_keys, "B1 receipt target key set drift")
    resolved_keys = {key for key, row in review_rows.items() if row["review"]["status"] == "RESOLVED"}
    remaining = [deepcopy(row) for row in inherited
                 if (row["workflow_path"], row["trigger_kind"]) not in resolved_keys]
    criteria = deepcopy(parent["checkpoint_criteria"])
    boundary.require(len(criteria) == 19, "Completion V3 criterion set drift")
    criterion_11 = "all_retained_workflow_authority_and_dynamic_reachability_review_complete"
    criterion_14 = "no_unknown_current_artifact_or_notification_authority"
    boundary.require(criteria[criterion_11] is False and criteria[criterion_14] is False,
                     "B1 cannot make global authority criteria true")
    boundary.require(len(remaining) == 32 - len(resolved_keys),
                     "global unresolved count is not derived from resolved B1 rows")
    resolved_rows = []
    for key in sorted(resolved_keys):
        row = review_rows[key]
        resolved_rows.append({
            "workflow_path": key[0], "trigger_kind": key[1],
            "disposition": row["review"]["disposition"],
            "historical_actions_rerun_residual": row["reachability"]["historical_actions_rerun_residual"],
            "source_identity": row["source_identity"],
            "evidence_sha256": review["canonical_sha256"],
        })
    terminal = ("CORE_01D_EXACT_PR_TRIGGER_DISPOSITION_B1_REVIEW_READY_7_RESOLVED_DO_NOT_MERGE"
                if len(resolved_keys) == 7 else
                "CORE_01D_EXACT_PR_TRIGGER_DISPOSITION_B1_REVIEW_READY_PARTIAL_DO_NOT_MERGE")
    return boundary.seal({
        "schema_version": 4,
        "policy_id": POLICY_ID,
        "repository": "Thabearr/ATHENA",
        "master_issue": 337,
        "base_main_sha": b1.BASE_MAIN,
        "base_tree_sha": b1.BASE_TREE,
        "predecessor_completion_v3": {
            "path": PARENT_PATH,
            "canonical_sha256": EXPECTED_PARENT_SHA,
            "rewritten": False,
        },
        "b1_source_inventory": {
            "path": b1.SOURCE_INVENTORY_PATH,
            "canonical_sha256": review["source_inventory"]["canonical_sha256"],
        },
        "b1_review": {"path": b1.RECEIPT_PATH, "canonical_sha256": review["canonical_sha256"]},
        "scope": {
            "inherited_unreviewed_count": len(inherited),
            "target_surface_count": len(target_keys),
            "resolved_target_count": len(resolved_keys),
            "partial_target_count": len(target_keys) - len(resolved_keys),
            "remaining_global_unreviewed_surface_count": len(remaining),
            "target_keys": [[path, trigger] for path, trigger in sorted(target_keys)],
        },
        "resolved_target_surfaces": resolved_rows,
        "unresolved_target_keys": [[path, trigger] for path, trigger in sorted(target_keys - resolved_keys)],
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
        "actions": boundary.ZERO_ACTIONS,
        "workflow_edit_count": 0,
        "trigger_edit_count": 0,
        "workflow_retirement_count": 0,
        "workflow_deletion_count": 0,
        "source_review_counter_while_open": "0/5",
        "source_review_counter_if_owner_merges": "1/5",
        "mandatory_source_reread_after_b1_merge": False,
        "terminal": terminal,
    })


def validate_receipt(value: dict[str, object], expected: dict[str, object] | None = None) -> None:
    raw = (ROOT / RECEIPT_PATH).read_bytes()
    boundary.require(raw == boundary.canonical(value), "Completion V4 is not canonical")
    derived = build_receipt() if expected is None else expected
    boundary.require(value == derived, "Completion V4 differs from the source-derived B1 overlay")
    boundary.require(value["checkpoint_e_status"] == "INCOMPLETE" and value["p4_4_status"] == "INCOMPLETE",
                     "B1 cannot complete Checkpoint E/P4.4")
    boundary.require(value["checkpoint_criteria"]["all_retained_workflow_authority_and_dynamic_reachability_review_complete"] is False,
                     "criterion 11 must remain false with out-of-scope unknown surfaces")
    boundary.require(value["checkpoint_criteria"]["no_unknown_current_artifact_or_notification_authority"] is False,
                     "criterion 14 must remain false with out-of-scope unknown surfaces")


def audit() -> dict[str, object]:
    value = boundary.read(RECEIPT_PATH)
    validate_receipt(value)
    return {
        "result": "PASS",
        "receipt_sha256": value["canonical_sha256"],
        "resolved_target_count": value["scope"]["resolved_target_count"],
        "remaining_unreviewed_surface_count": value["scope"]["remaining_global_unreviewed_surface_count"],
        "criteria_11_and_14": False,
        "checkpoint_e_status": value["checkpoint_e_status"],
        "p4_4_status": value["p4_4_status"],
        "terminal": value["terminal"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emit-receipt", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.emit_receipt:
        value = build_receipt()
        (ROOT / RECEIPT_PATH).write_bytes(boundary.canonical(value))
        print(value["canonical_sha256"])
    else:
        print(boundary.canonical(audit()).decode(), end="")


if __name__ == "__main__":
    main()
