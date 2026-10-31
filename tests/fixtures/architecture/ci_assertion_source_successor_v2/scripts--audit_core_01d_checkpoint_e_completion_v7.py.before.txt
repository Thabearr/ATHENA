"""Derive current Checkpoint-E authority status after B4's nine-surface review."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from typing import Any

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
from scripts import audit_core_01d_checkpoint_e_completion_v6 as completion_v6
from scripts import audit_core_01d_sportybet_current_trigger_authority_b4 as b4

ROOT = boundary.ROOT
POLICY_ID = "ATHENA_CORE_01D_CHECKPOINT_E_COMPLETION_V7"
PARENT_PATH = completion_v6.RECEIPT_PATH
PARENT_SHA = "9ec9debf1bfb3effbeeafb0f9a2a8f184fe131fa228d0b4778ee73974517d64d"
RECEIPT_PATH = "tests/fixtures/core_01d/core-01d-checkpoint-e-completion-v7.json"
TARGET_KEYS = set(b4.TARGETS)


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise AssertionError(reason)


def build_receipt() -> dict[str, Any]:
    parent = boundary.read(PARENT_PATH)
    require(parent.get("canonical_sha256") == PARENT_SHA, "immutable Completion V6 identity drift")
    completion_v6.audit()
    review = b4.validate_receipt()
    inherited = parent["unreviewed_authority_surfaces"]
    inherited_keys = {(row["workflow_path"], row["trigger_kind"]) for row in inherited}
    require(len(inherited) == 16 and len(inherited_keys) == 16, "Completion V6 unresolved set drift")
    require(TARGET_KEYS <= inherited_keys, "a B4 surface is not inherited as unresolved")
    resolved = {(row["identity"]["workflow_path"], row["identity"]["trigger_kind"])
                for row in review["review_rows"] if row["review"]["status"] == "RESOLVED"}
    require(resolved <= TARGET_KEYS, "B4 overlay added an out-of-scope surface")
    remaining = [deepcopy(row) for row in inherited if (row["workflow_path"], row["trigger_kind"]) not in resolved]
    require(len(remaining) == 16 - len(resolved), "Completion V7 remaining count is not derived")
    require(not ({(row["workflow_path"], row["trigger_kind"]) for row in remaining} & resolved),
            "a surface appears as both reviewed and unresolved")
    criteria = deepcopy(parent["checkpoint_criteria"])
    require(len(criteria) == 19, "Completion V6 criterion set drift")
    require(criteria["all_retained_workflow_authority_and_dynamic_reachability_review_complete"] is False,
            "B4 cannot complete criterion 11")
    require(criteria["no_unknown_current_artifact_or_notification_authority"] is False,
            "B4 cannot complete criterion 14")
    return boundary.seal({
        "schema_version": 7, "policy_id": POLICY_ID, "repository": "Thabearr/ATHENA", "master_issue": 337,
        "base_main_sha": b4.BASE_MAIN, "base_tree_sha": b4.BASE_TREE,
        "predecessor_completion_v6": {"path": PARENT_PATH, "canonical_sha256": PARENT_SHA, "rewritten": False},
        "predecessor_b4_review": {"path": b4.RECEIPT_PATH, "canonical_sha256": review["canonical_sha256"]},
        "predecessor_b4_source_inventory": {"path": b4.SOURCE_INVENTORY_PATH,
                                             "canonical_sha256": review["source_inventory"]["canonical_sha256"]},
        "scope": {
            "inherited_unreviewed_count": len(inherited), "target_surface_count": len(TARGET_KEYS),
            "resolved_target_count": len(resolved), "partial_target_count": len(TARGET_KEYS) - len(resolved),
            "remaining_global_unreviewed_surface_count": len(remaining),
            "target_keys": [[path, event] for path, event in b4.TARGETS],
        },
        "reviewed_target_surfaces": [{
            "workflow_path": path, "trigger_kind": event,
            "physical_trigger_runtime_authority": b4.TARGET_REACHABILITY[(path, event)],
            "review_status": next(row["review"]["status"] for row in review["review_rows"]
                                  if (row["identity"]["workflow_path"], row["identity"]["trigger_kind"]) == (path, event)),
            "b4_receipt_sha256": review["canonical_sha256"],
        } for path, event in b4.TARGETS],
        "unresolved_target_keys": [[path, event] for path, event in sorted(TARGET_KEYS - resolved)],
        "unreviewed_authority_surfaces": remaining,
        "checkpoint_criteria": criteria,
        "predecessor_completion_v2": deepcopy(parent["predecessor_completion_v2"]),
        "retained_v5": deepcopy(parent["retained_v5"]),
        "pass_a_review": deepcopy(parent["pass_a_review"]),
        "a2_review": deepcopy(parent["a2_review"]),
        "checkpoint_e_status": "INCOMPLETE", "p4_4_status": "INCOMPLETE",
        "remaining_blocker_ids": deepcopy(parent["remaining_blocker_ids"]),
        "workflow_count": parent["workflow_count"], "trigger_surface_count": parent["trigger_surface_count"],
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
        "workflow_edit_count": 0, "trigger_edit_count": 0, "workflow_retirement_count": 0,
        "workflow_deletion_count": 0, "caller_migration_count": 0,
        "actions": b4.ZERO_ACTIONS,
        "source_review_counter_while_open": "3/5", "source_review_counter_if_owner_merges": "4/5",
        "mandatory_governing_source_reread_after_b4_merge": False,
        "terminal": "CORE_01D_SPORTYBET_CURRENT_TRIGGER_AUTHORITY_B4_REVIEW_READY_9_RESOLVED_DO_NOT_MERGE"
        if len(resolved) == 9 else "CORE_01D_SPORTYBET_CURRENT_TRIGGER_AUTHORITY_B4_REVIEW_READY_PARTIAL_DO_NOT_MERGE",
    })


def validate_receipt(value: dict[str, Any] | None = None) -> dict[str, Any]:
    value = boundary.read(RECEIPT_PATH) if value is None else value
    require((ROOT / RECEIPT_PATH).read_bytes() == boundary.canonical(value), "Completion V7 is not canonical")
    require(value == build_receipt(), "Completion V7 differs from immutable V6 plus the authenticated B4 overlay")
    require(value["scope"]["remaining_global_unreviewed_surface_count"] == 16 - value["scope"]["resolved_target_count"],
            "Completion V7 unresolved count is not derived")
    require(value["checkpoint_e_status"] == value["p4_4_status"] == "INCOMPLETE", "B4 cannot complete Checkpoint E/P4.4")
    require(value["checkpoint_criteria"]["all_retained_workflow_authority_and_dynamic_reachability_review_complete"] is False
            and value["checkpoint_criteria"]["no_unknown_current_artifact_or_notification_authority"] is False,
            "Completion V7 criteria 11/14 must remain false")
    return value


def audit() -> dict[str, Any]:
    value = validate_receipt()
    return {"result": "PASS", "receipt_sha256": value["canonical_sha256"],
            "resolved_target_count": value["scope"]["resolved_target_count"],
            "remaining_unreviewed_surface_count": value["scope"]["remaining_global_unreviewed_surface_count"],
            "checkpoint_e": value["checkpoint_e_status"], "p4_4": value["p4_4_status"],
            "remaining_blockers": value["remaining_blocker_ids"], "terminal": value["terminal"]}


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
