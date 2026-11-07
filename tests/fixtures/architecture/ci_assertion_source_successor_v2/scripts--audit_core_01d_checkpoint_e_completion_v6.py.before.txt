"""Derive current Checkpoint-E status after the bounded B3 surface review."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
from scripts import audit_core_01d_checkpoint_e_completion_v5 as completion_v5
from scripts import audit_core_01d_owner_one_shot_issue_comment_authority_b3 as b3

ROOT = boundary.ROOT
POLICY_ID = "ATHENA_CORE_01D_CHECKPOINT_E_COMPLETION_V6"
PARENT_PATH = completion_v5.RECEIPT_PATH
PARENT_SHA = "5655dca85b67ec1a3367a7c5bfa08dfebda0caccb4830e75b23f6cca4ff82d88"
RECEIPT_PATH = "tests/fixtures/core_01d/core-01d-checkpoint-e-completion-v6.json"
TARGET_KEYS = {(b3.TARGETS[key]["path"], "issue_comment") for key in b3.TARGETS}


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def build_receipt() -> dict[str, object]:
    parent = boundary.read(PARENT_PATH)
    require(parent.get("canonical_sha256") == PARENT_SHA, "immutable Completion V5 identity drift")
    b3.authenticate_predecessor_chain()
    b3.audit()
    review = boundary.read(b3.RECEIPT_PATH)
    inherited = parent["unreviewed_authority_surfaces"]
    inherited_keys = [(row["workflow_path"], row["trigger_kind"]) for row in inherited]
    require(len(inherited) == 20 and len(set(inherited_keys)) == 20,
            "Completion V5 unresolved surface census drift")
    require(TARGET_KEYS <= set(inherited_keys), "a B3 target is not an inherited unresolved surface")
    rows = {(row["identity"]["workflow_path"], row["identity"]["trigger_kind"]): row
            for row in review["review_rows"]}
    require(set(rows) == TARGET_KEYS, "B3 review target set drift")
    resolved = {key for key, row in rows.items() if row["review"]["status"] == "RESOLVED"}
    remaining = [deepcopy(row) for row in inherited if (row["workflow_path"], row["trigger_kind"]) not in resolved]
    require(len(remaining) == 20 - len(resolved), "global unresolved count is not derived from B3 rows")
    require(not ({(row["workflow_path"], row["trigger_kind"]) for row in remaining} & resolved),
            "surface is duplicated in reviewed and unresolved sets")
    criteria = deepcopy(parent["checkpoint_criteria"])
    require(len(criteria) == 19, "Completion V5 criterion set drift")
    require(criteria["all_retained_workflow_authority_and_dynamic_reachability_review_complete"] is False,
            "B3 cannot resolve global criterion 11")
    require(criteria["no_unknown_current_artifact_or_notification_authority"] is False,
            "B3 cannot resolve global criterion 14")
    summaries = [{
        "workflow_path": key[0],
        "trigger_kind": key[1],
        "declared_event_surface_reachability": rows[key]["reachability"]["declared_event_surface_reachability"],
        "guarded_high_risk_reachability": rows[key]["reachability"]["current_guarded_high_risk_execution_reachability"],
        "review_status": rows[key]["review"]["status"],
        "b3_receipt_sha256": review["canonical_sha256"],
    } for key in sorted(TARGET_KEYS)]
    return boundary.seal({
        "schema_version": 6,
        "policy_id": POLICY_ID,
        "repository": "Thabearr/ATHENA",
        "master_issue": 337,
        "base_main_sha": b3.BASE_MAIN,
        "base_tree_sha": b3.BASE_TREE,
        "predecessor_completion_v5": {"path": PARENT_PATH, "canonical_sha256": PARENT_SHA, "rewritten": False},
        "predecessor_completion_v2": deepcopy(parent["predecessor_completion_v2"]),
        "retained_v5": deepcopy(parent["retained_v5"]),
        "pass_a_review": deepcopy(parent["pass_a_review"]),
        "a2_review": deepcopy(parent["a2_review"]),
        "b3_source_inventory": {"path": b3.SOURCE_INVENTORY_PATH,
                                "canonical_sha256": review["source_inventory"]["canonical_sha256"]},
        "b3_review": {"path": b3.RECEIPT_PATH, "canonical_sha256": review["canonical_sha256"]},
        "scope": {
            "inherited_unreviewed_count": len(inherited),
            "target_surface_count": len(TARGET_KEYS),
            "resolved_target_count": len(resolved),
            "partial_target_count": len(TARGET_KEYS) - len(resolved),
            "remaining_global_unreviewed_surface_count": len(remaining),
            "target_keys": [[path, event] for path, event in sorted(TARGET_KEYS)],
        },
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
        "actions": b3.ZERO_ACTIONS,
        "source_review_counter_while_open": "2/5",
        "source_review_counter_if_owner_merges": "3/5",
        "mandatory_governing_source_reread_after_b3_merge": False,
        "terminal": ("CORE_01D_OWNER_ONE_SHOT_ISSUE_COMMENT_AUTHORITY_B3_REVIEW_READY_4_RESOLVED_DO_NOT_MERGE"
                     if len(resolved) == 4 else
                     "CORE_01D_OWNER_ONE_SHOT_ISSUE_COMMENT_AUTHORITY_B3_REVIEW_READY_PARTIAL_DO_NOT_MERGE"),
    })


def validate_receipt(value: dict[str, object], expected: dict[str, object] | None = None,
                     raw: bytes | None = None) -> None:
    raw = (ROOT / RECEIPT_PATH).read_bytes() if raw is None else raw
    require(raw == boundary.canonical(value), "Completion V6 is not canonical")
    require(value == (build_receipt() if expected is None else expected),
            "Completion V6 differs from immutable V5 plus resolved B3 overlay")
    require(value["scope"]["remaining_global_unreviewed_surface_count"] ==
            value["scope"]["inherited_unreviewed_count"] - value["scope"]["resolved_target_count"],
            "Completion V6 unresolved count is not derived")
    require(value["checkpoint_e_status"] == value["p4_4_status"] == "INCOMPLETE",
            "B3 cannot complete Checkpoint E/P4.4")
    require(value["checkpoint_criteria"]["all_retained_workflow_authority_and_dynamic_reachability_review_complete"] is False
            and value["checkpoint_criteria"]["no_unknown_current_artifact_or_notification_authority"] is False,
            "Completion V6 criteria 11 and 14 must remain false")
    require(value["scope"]["remaining_global_unreviewed_surface_count"] == 16,
            "B3 must preserve the exact 16 inherited non-target unknowns")


def audit() -> dict[str, object]:
    value = boundary.read(RECEIPT_PATH)
    validate_receipt(value)
    return {
        "result": "PASS", "receipt_sha256": value["canonical_sha256"],
        "resolved_target_count": value["scope"]["resolved_target_count"],
        "remaining_unreviewed_surface_count": value["scope"]["remaining_global_unreviewed_surface_count"],
        "criteria_11_and_14": False, "checkpoint_e_status": value["checkpoint_e_status"],
        "p4_4_status": value["p4_4_status"], "checkpoint_e": value["checkpoint_e_status"],
        "p4_4": value["p4_4_status"], "remaining_blockers": value["remaining_blocker_ids"],
        "terminal": value["terminal"],
    }


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
