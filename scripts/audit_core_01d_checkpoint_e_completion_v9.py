"""Derive current Checkpoint-E completion V9 from immutable V8 plus B6."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from typing import Any

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
from scripts import audit_core_01d_checkpoint_e_completion_v8 as completion_v8
from scripts import audit_core_01d_port02c_trigger_authority_b6 as b6

ROOT = boundary.ROOT
POLICY_ID = "ATHENA_CORE_01D_CHECKPOINT_E_COMPLETION_V9"
PARENT_PATH = completion_v8.RECEIPT_PATH
PARENT_SHA = "b096669da119a2c82ea4bb9fdeb2d2c10e417ecf54c834a621f8e643b6da8c8a"
RECEIPT_PATH = "tests/fixtures/core_01d/core-01d-checkpoint-e-completion-v9.json"
TARGET_KEYS = set(b6.TARGETS)
WIN_EITHER_HALF = b6.WIN_EITHER_HALF
EXPECTED_FINAL_KEYS = {WIN_EITHER_HALF}


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise AssertionError(reason)


def build_receipt() -> dict[str, Any]:
    parent = completion_v8.validate_receipt()
    require(parent.get("canonical_sha256") == PARENT_SHA,
            "immutable Completion V8 identity drift")
    review = b6.validate_receipt()
    inherited = parent["unreviewed_authority_surfaces"]
    inherited_keys = {(row["workflow_path"], row["trigger_kind"]) for row in inherited}
    require(len(inherited) == 3 and inherited_keys == set((*b6.TARGETS, WIN_EITHER_HALF)),
            "Completion V8 unresolved surface census drift")
    resolved = {
        (row["identity"]["workflow_path"], row["identity"]["trigger_kind"])
        for row in review["review_rows"] if row["status"] == "RESOLVED"
    }
    require(resolved == TARGET_KEYS, "B6 completion overlay must resolve exactly both PORT-02C triggers")
    remaining = [deepcopy(row) for row in inherited
                 if (row["workflow_path"], row["trigger_kind"]) not in resolved]
    remaining_keys = {(row["workflow_path"], row["trigger_kind"]) for row in remaining}
    require(remaining_keys == EXPECTED_FINAL_KEYS and len(remaining) == 1,
            "Completion V9 must preserve the sole Win-Either-Half row unchanged")
    require(remaining[0] == next(row for row in inherited
                                 if (row["workflow_path"], row["trigger_kind"]) == WIN_EITHER_HALF),
            "Completion V9 changed Win-Either-Half semantics")
    criteria = deepcopy(parent["checkpoint_criteria"])
    require(criteria["all_retained_workflow_authority_and_dynamic_reachability_review_complete"] is False,
            "B6 cannot complete criterion 11 while the final surface remains")
    require(criteria["no_unknown_current_artifact_or_notification_authority"] is False,
            "B6 cannot complete criterion 14 while the final surface remains")
    a2_v8 = boundary.authenticate_inventory()
    require(a2_v8.get("generation") == 8, "Completion V9 requires A2 generation V8")
    require(a2_v8["predecessor_inventory"] == {
        "path": b6.A2_V7_PATH,
        "canonical_sha256": b6.A2_V7_SHA,
        "generation": 7,
        "rewritten": False,
    }, "A2 V8 predecessor binding changed")

    value = deepcopy(parent)
    value.update({
        "schema_version": 9,
        "policy_id": POLICY_ID,
        "base_main_sha": b6.BASE_MAIN,
        "base_tree_sha": b6.BASE_TREE,
        "predecessor_completion_v8": {
            "path": PARENT_PATH,
            "canonical_sha256": PARENT_SHA,
            "rewritten": False,
        },
        "b6_review": {
            "path": b6.RECEIPT_PATH,
            "canonical_sha256": review["canonical_sha256"],
        },
        "b6_source_inventory": {
            "path": b6.SOURCE_INVENTORY_PATH,
            "canonical_sha256": review["source_inventory"]["canonical_sha256"],
        },
        "a2_generation_8": {
            "path": boundary.inventory_generation_path(8),
            "canonical_sha256": a2_v8["canonical_sha256"],
            "generation": 8,
            "predecessor": deepcopy(a2_v8["predecessor_inventory"]),
            "rewritten": False,
        },
        "scope": {
            "inherited_unresolved_count": len(inherited),
            "target_surface_count": len(TARGET_KEYS),
            "resolved_target_count": len(resolved),
            "partial_target_count": len(TARGET_KEYS) - len(resolved),
            "remaining_global_unreviewed_surface_count": len(remaining),
            "target_keys": [[path, trigger] for path, trigger in b6.TARGETS],
        },
        "b6_reviewed_target_surfaces": [{
            "workflow_path": path,
            "trigger_kind": trigger,
            "review_status": "RESOLVED",
            "b6_receipt_sha256": review["canonical_sha256"],
        } for path, trigger in b6.TARGETS],
        "unresolved_b6_target_keys": [],
        "unreviewed_authority_surfaces": remaining,
        "checkpoint_criteria": criteria,
        "checkpoint_e_status": "INCOMPLETE",
        "p4_4_status": "INCOMPLETE",
        "workflow_edit_count": 0,
        "trigger_edit_count": 0,
        "workflow_retirement_count": 0,
        "workflow_deletion_count": 0,
        "caller_migration_count": 0,
        "source_review_counter_while_open": "0/5",
        "source_review_counter_if_owner_merges": "1/5",
        "mandatory_governing_source_reread_after_b6_merge": "NO",
        "do_not_start_final_win_either_half_review_until_b6_owner_reviewed_merged_or_dispositioned": True,
        "terminal": "CORE_01D_PORT02C_TRIGGER_AUTHORITY_B6_REVIEW_READY_2_RESOLVED_DO_NOT_MERGE",
    })
    return boundary.seal(value)


def validate_receipt(value: dict[str, Any] | None = None) -> dict[str, Any]:
    value = boundary.read(RECEIPT_PATH) if value is None else value
    require((ROOT / RECEIPT_PATH).read_bytes() == boundary.canonical(value),
            "Completion V9 is not canonical")
    expected = build_receipt()
    require(value == expected, "Completion V9 differs from immutable V8 plus the B6 overlay")
    require(value["scope"]["inherited_unresolved_count"] == 3
            and value["scope"]["target_surface_count"] == 2
            and value["scope"]["resolved_target_count"] == 2
            and value["scope"]["partial_target_count"] == 0
            and value["scope"]["remaining_global_unreviewed_surface_count"] == 1,
            "Completion V9 scope/count derivation drift")
    require({(row["workflow_path"], row["trigger_kind"])
             for row in value["unreviewed_authority_surfaces"]} == EXPECTED_FINAL_KEYS,
            "Completion V9 final unresolved set changed")
    require(value["checkpoint_e_status"] == value["p4_4_status"] == "INCOMPLETE"
            and value["checkpoint_criteria"]["all_retained_workflow_authority_and_dynamic_reachability_review_complete"] is False
            and value["checkpoint_criteria"]["no_unknown_current_artifact_or_notification_authority"] is False,
            "Completion V9 cannot complete Checkpoint E/P4.4 or criteria 11/14")
    require(value["historical_missing_artifact_relation_count"] == 14
            and value["live_missing_artifact_relation_count"] == 0
            and value["retention_blockers_A_B_C_D"] == "CLOSED_WITH_HISTORICAL_LIMITATIONS_PRESERVED",
            "Completion V9 changed inherited retention state")
    require(value["workflow_tree_before_sha1"] == value["workflow_tree_after_sha1"] == b6.WORKFLOW_TREE
            and value["transition_count"] == 14
            and value["retired_workflow_count"] == 3
            and value["workflow_retirement_count"] == 0
            and value["workflow_deletion_count"] == 0
            and value["trigger_edit_count"] == 0,
            "Completion V9 changed workflow/evolution/retirement invariants")
    return value


def audit() -> dict[str, Any]:
    value = validate_receipt()
    return {
        "result": "PASS",
        "receipt_sha256": value["canonical_sha256"],
        "resolved_target_count": value["scope"]["resolved_target_count"],
        "remaining_unreviewed_surface_count": value["scope"]["remaining_global_unreviewed_surface_count"],
        "remaining": value["unreviewed_authority_surfaces"],
        "remaining_blockers": value["remaining_blocker_ids"],
        "checkpoint_e": value["checkpoint_e_status"],
        "p4_4": value["p4_4_status"],
        "criterion_11": value["checkpoint_criteria"]["all_retained_workflow_authority_and_dynamic_reachability_review_complete"],
        "criterion_14": value["checkpoint_criteria"]["no_unknown_current_artifact_or_notification_authority"],
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
