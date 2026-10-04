"""Derive the current Checkpoint-E overlay after B5's four replay reviews."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from typing import Any

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
from scripts import audit_core_01d_checkpoint_e_completion_v7 as completion_v7
from scripts import audit_core_01d_frozen_artifact_replay_authority_b5 as b5

ROOT = boundary.ROOT
POLICY_ID = "ATHENA_CORE_01D_CHECKPOINT_E_COMPLETION_V8"
PARENT_PATH = completion_v7.RECEIPT_PATH
PARENT_SHA = "a047bcf6b5fadd2118f6c817b03a43312e0a9094a1269f4b6b22750c5e638512"
RECEIPT_PATH = "tests/fixtures/core_01d/core-01d-checkpoint-e-completion-v8.json"
TARGET_KEYS = set(b5.TARGETS)
EXPECTED_FINAL_KEYS = {
    (".github/workflows/port-02c-native-runtime.yml", "pull_request"),
    (".github/workflows/port-02c-native-runtime.yml", "workflow_dispatch"),
    (".github/workflows/validate-win-either-half-campaign-commitment.yml", "pull_request"),
}


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise AssertionError(reason)


def build_receipt() -> dict[str, Any]:
    parent = boundary.read(PARENT_PATH)
    require(parent.get("canonical_sha256") == PARENT_SHA, "immutable Completion V7 identity drift")
    completion_v7.audit()
    review = b5.validate_receipt()
    inherited = parent["unreviewed_authority_surfaces"]
    inherited_keys = {(row["workflow_path"], row["trigger_kind"]) for row in inherited}
    require(len(inherited) == 7 and len(inherited_keys) == 7,
            "Completion V7 unresolved surface census drift")
    require(TARGET_KEYS <= inherited_keys, "a B5 surface is not inherited as unresolved")
    resolved = {
        (row["identity"]["workflow_path"], row["identity"]["trigger_kind"])
        for row in review["review_rows"] if row["review"]["status"] == "RESOLVED"
    }
    require(resolved <= TARGET_KEYS, "B5 overlay added an out-of-scope surface")
    remaining = [deepcopy(row) for row in inherited
                 if (row["workflow_path"], row["trigger_kind"]) not in resolved]
    remaining_keys = {(row["workflow_path"], row["trigger_kind"]) for row in remaining}
    require(len(remaining) == 7 - len(resolved), "Completion V8 remaining count is not derived")
    require(not (remaining_keys & resolved), "a surface appears as both reviewed and unresolved")
    if len(resolved) == 4:
        require(remaining_keys == EXPECTED_FINAL_KEYS,
                "the exact three inherited non-B5 unknown surfaces changed")
    criteria = deepcopy(parent["checkpoint_criteria"])
    require(len(criteria) == 19, "Completion V7 criterion set drift")
    require(criteria["all_retained_workflow_authority_and_dynamic_reachability_review_complete"] is False,
            "B5 cannot complete criterion 11")
    require(criteria["no_unknown_current_artifact_or_notification_authority"] is False,
            "B5 cannot complete criterion 14")

    value = deepcopy(parent)
    value.update({
        "schema_version": 8,
        "policy_id": POLICY_ID,
        "base_main_sha": b5.BASE_MAIN,
        "base_tree_sha": b5.BASE_TREE,
        "predecessor_completion_v7": {"path": PARENT_PATH, "canonical_sha256": PARENT_SHA,
                                       "rewritten": False},
        "b5_review": {"path": b5.RECEIPT_PATH, "canonical_sha256": review["canonical_sha256"]},
        "b5_source_inventory": {"path": b5.SOURCE_INVENTORY_PATH,
                                "canonical_sha256": review["source_inventory"]["canonical_sha256"]},
        "a2_generation_7": deepcopy(review["a2_generation_7"]),
        "scope": {
            "inherited_unresolved_count": len(inherited),
            "target_surface_count": len(TARGET_KEYS),
            "resolved_target_count": len(resolved),
            "partial_target_count": len(TARGET_KEYS) - len(resolved),
            "remaining_global_unreviewed_surface_count": len(remaining),
            "target_keys": [[path, trigger] for path, trigger in b5.TARGETS],
        },
        "b5_reviewed_target_surfaces": [{
            "workflow_path": path,
            "trigger_kind": trigger,
            "review_status": next(
                row["review"]["status"] for row in review["review_rows"]
                if (row["identity"]["workflow_path"], row["identity"]["trigger_kind"]) == (path, trigger)
            ),
            "b5_receipt_sha256": review["canonical_sha256"],
        } for path, trigger in b5.TARGETS],
        "unresolved_b5_target_keys": [[path, trigger] for path, trigger in sorted(TARGET_KEYS - resolved)],
        "unreviewed_authority_surfaces": remaining,
        "checkpoint_criteria": criteria,
        "checkpoint_e_status": "INCOMPLETE",
        "p4_4_status": "INCOMPLETE",
        "workflow_edit_count": 0,
        "trigger_edit_count": 0,
        "workflow_retirement_count": 0,
        "workflow_deletion_count": 0,
        "caller_migration_count": 0,
        "source_review_counter_while_open": "4/5",
        "source_review_counter_if_owner_merges": "5/5",
        "mandatory_governing_source_reread_after_b5_merge": True,
        "do_not_start_b6_before_reread": True,
        "terminal": "CORE_01D_FROZEN_ARTIFACT_REPLAY_AUTHORITY_B5_REVIEW_READY_4_RESOLVED_DO_NOT_MERGE"
        if len(resolved) == 4 else "CORE_01D_FROZEN_ARTIFACT_REPLAY_AUTHORITY_B5_REVIEW_READY_PARTIAL_DO_NOT_MERGE",
    })
    return boundary.seal(value)


def validate_receipt(value: dict[str, Any] | None = None) -> dict[str, Any]:
    value = boundary.read(RECEIPT_PATH) if value is None else value
    require((ROOT / RECEIPT_PATH).read_bytes() == boundary.canonical(value),
            "Completion V8 is not canonical")
    require(value == build_receipt(), "Completion V8 differs from immutable V7 plus the B5 overlay")
    require(value["scope"]["remaining_global_unreviewed_surface_count"] ==
            7 - value["scope"]["resolved_target_count"],
            "Completion V8 unresolved count is not derived")
    require(value["checkpoint_e_status"] == value["p4_4_status"] == "INCOMPLETE",
            "B5 cannot complete Checkpoint E/P4.4")
    require(value["checkpoint_criteria"]["all_retained_workflow_authority_and_dynamic_reachability_review_complete"] is False
            and value["checkpoint_criteria"]["no_unknown_current_artifact_or_notification_authority"] is False,
            "Completion V8 criteria 11/14 must remain false")
    return value


def audit() -> dict[str, Any]:
    value = validate_receipt()
    return {
        "result": "PASS",
        "receipt_sha256": value["canonical_sha256"],
        "resolved_target_count": value["scope"]["resolved_target_count"],
        "remaining_unreviewed_surface_count": value["scope"]["remaining_global_unreviewed_surface_count"],
        "checkpoint_e": value["checkpoint_e_status"],
        "p4_4": value["p4_4_status"],
        "remaining_blockers": value["remaining_blocker_ids"],
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
