"""Derive Checkpoint-E completion V10 from immutable V9 plus final B7 review."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from typing import Any

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
from scripts import audit_core_01d_checkpoint_e_completion_v9 as completion_v9
from scripts import audit_core_01d_win_either_half_trigger_authority_b7 as b7

ROOT = boundary.ROOT
POLICY_ID = "ATHENA_CORE_01D_CHECKPOINT_E_COMPLETION_V10"
PARENT_PATH = completion_v9.RECEIPT_PATH
PARENT_SHA = "e587da6b663a7f98fda4aa3d8be53525a35354a7b2a2ff51b8cae86adfa47177"
A2_V8_SHA = "856129ba6eafb0281f10a16639f26fd477b2ba6a2fb00957ee79fa539539412d"
RECEIPT_PATH = "tests/fixtures/core_01d/core-01d-checkpoint-e-completion-v10.json"
TARGET_KEY = b7.TARGET


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise AssertionError(reason)


def build_receipt() -> dict[str, Any]:
    parent = completion_v9.validate_receipt()
    require(parent.get("canonical_sha256") == PARENT_SHA,
            "immutable Completion V9 identity drift")
    review = b7.validate_receipt()
    inherited = parent["unreviewed_authority_surfaces"]
    inherited_keys = {(row["workflow_path"], row["trigger_kind"]) for row in inherited}
    require(len(inherited) == 1 and inherited_keys == {TARGET_KEY},
            "Completion V9 must expose exactly the final Win-Either-Half surface")
    resolved = {
        (row["identity"]["workflow_path"], row["identity"]["trigger_kind"])
        for row in review["review_rows"] if row["status"] == "RESOLVED"
    }
    require(resolved == {TARGET_KEY}, "B7 must resolve exactly the inherited final surface")
    require(review["global_unknown_before"] == 1 and review["global_unknown_after"] == 0
            and review["remaining_unreviewed_surfaces"] == [],
            "B7 does not prove a one-to-zero authority closure")

    criteria = deepcopy(parent["checkpoint_criteria"])
    false_before = {key for key, value in criteria.items() if value is False}
    require(false_before == {
        "all_retained_workflow_authority_and_dynamic_reachability_review_complete",
        "no_unknown_current_artifact_or_notification_authority",
    }, "Completion V9 false-criterion set changed")
    criteria["all_retained_workflow_authority_and_dynamic_reachability_review_complete"] = True
    criteria["no_unknown_current_artifact_or_notification_authority"] = True
    require(criteria and all(value is True for value in criteria.values()),
            "Completion V10 cannot close while any checkpoint criterion is false")

    a2_v8 = boundary.read(boundary.inventory_generation_path(8))
    require(a2_v8.get("canonical_sha256") == A2_V8_SHA and a2_v8.get("generation") == 8,
            "immutable A2 V8 identity drift")
    a2_v9 = b7.authenticated_historical_a2_v9()
    require(a2_v9.get("generation") == 9, "Completion V10 requires immutable B7 A2 generation V9")
    require(a2_v9.get("predecessor_inventory") == {
        "path": boundary.inventory_generation_path(8),
        "canonical_sha256": A2_V8_SHA,
        "generation": 8,
        "rewritten": False,
    }, "A2 V9 predecessor binding is not exact immutable V8")

    require(parent["remaining_blocker_ids"] == [
        "all_retained_workflow_authority_and_dynamic_reachability_review_complete",
        "no_unknown_current_artifact_or_notification_authority",
    ], "Completion V9 blocker set changed")
    require(parent["checkpoint_e_status"] == parent["p4_4_status"] == "INCOMPLETE",
            "Completion V9 must remain incomplete")
    require(review["criterion_11"] is True and review["criterion_14"] is True
            and review["checkpoint_e_status"] == review["p4_4_status"] == "COMPLETE",
            "B7 review did not close the final authority criteria")

    value = deepcopy(parent)
    value.update({
        "schema_version": 10,
        "policy_id": POLICY_ID,
        "base_main_sha": b7.BASE_MAIN,
        "base_tree_sha": b7.BASE_TREE,
        "predecessor_completion_v9": {
            "path": PARENT_PATH,
            "canonical_sha256": PARENT_SHA,
            "rewritten": False,
        },
        "b7_review": {
            "path": b7.RECEIPT_PATH,
            "canonical_sha256": review["canonical_sha256"],
        },
        "b7_source_inventory": {
            "path": b7.SOURCE_INVENTORY_PATH,
            "canonical_sha256": review["source_inventory"]["canonical_sha256"],
        },
        "a2_generation_9": {
            "path": boundary.inventory_generation_path(9),
            "canonical_sha256": a2_v9["canonical_sha256"],
            "generation": 9,
            "predecessor": deepcopy(a2_v9["predecessor_inventory"]),
            "rewritten": False,
        },
        "scope": {
            "inherited_unresolved_count": 1,
            "target_surface_count": 1,
            "resolved_target_count": 1,
            "partial_target_count": 0,
            "remaining_global_unreviewed_surface_count": 0,
            "target_keys": [[TARGET_KEY[0], TARGET_KEY[1]]],
        },
        "b7_reviewed_target_surfaces": [{
            "workflow_path": TARGET_KEY[0],
            "trigger_kind": TARGET_KEY[1],
            "review_status": "RESOLVED",
            "b7_receipt_sha256": review["canonical_sha256"],
        }],
        "unresolved_b7_target_keys": [],
        "unreviewed_authority_surfaces": [],
        "checkpoint_criteria": criteria,
        "remaining_blocker_ids": [],
        "checkpoint_e_status": "COMPLETE",
        "p4_4_status": "COMPLETE",
        "workflow_edit_count": 0,
        "trigger_edit_count": 0,
        "workflow_retirement_count": 0,
        "workflow_deletion_count": 0,
        "caller_migration_count": 0,
        "source_review_counter_while_open": "1/5",
        "source_review_counter_if_owner_merges": "2/5",
        "mandatory_governing_source_reread_after_b7_merge": "NO",
        "terminal": "CORE_01D_CHECKPOINT_E_P4_4_COMPLETE_B7_REVIEW_READY_DO_NOT_MERGE",
    })
    return boundary.seal(value)


def validate_receipt(value: dict[str, Any] | None = None) -> dict[str, Any]:
    value = boundary.read(RECEIPT_PATH) if value is None else value
    require((ROOT / RECEIPT_PATH).read_bytes() == boundary.canonical(value),
            "Completion V10 is not canonical")
    expected = build_receipt()
    require(value == expected, "Completion V10 differs from immutable V9 plus B7")
    require(value["scope"] == {
        "inherited_unresolved_count": 1,
        "target_surface_count": 1,
        "resolved_target_count": 1,
        "partial_target_count": 0,
        "remaining_global_unreviewed_surface_count": 0,
        "target_keys": [[TARGET_KEY[0], TARGET_KEY[1]]],
    }, "Completion V10 scope/count derivation drift")
    require(value["unreviewed_authority_surfaces"] == []
            and value["remaining_blocker_ids"] == [],
            "Completion V10 must have no unresolved authority surfaces or blockers")
    require(all(flag is True for flag in value["checkpoint_criteria"].values()),
            "Completion V10 contains a false checkpoint criterion")
    require(value["checkpoint_e_status"] == value["p4_4_status"] == "COMPLETE",
            "Completion V10 must close Checkpoint E and P4.4")
    require(value["historical_missing_artifact_relation_count"] == 14
            and value["live_missing_artifact_relation_count"] == 0
            and value["retention_blockers_A_B_C_D"] == "CLOSED_WITH_HISTORICAL_LIMITATIONS_PRESERVED",
            "Completion V10 changed inherited retention state")
    require(value["workflow_tree_before_sha1"] == value["workflow_tree_after_sha1"] == b7.WORKFLOW_TREE
            and value["transition_count"] == 14
            and value["retired_workflow_count"] == 3
            and value["workflow_retirement_count"] == 0
            and value["workflow_deletion_count"] == 0
            and value["trigger_edit_count"] == 0,
            "Completion V10 changed workflow/evolution/retirement invariants")
    return value


def audit() -> dict[str, Any]:
    value = validate_receipt()
    return {
        "result": "PASS",
        "receipt_sha256": value["canonical_sha256"],
        "resolved_target_count": 1,
        "remaining_unreviewed_surface_count": 0,
        "remaining": [],
        "remaining_blockers": [],
        "checkpoint_e": "COMPLETE",
        "p4_4": "COMPLETE",
        "criterion_11": True,
        "criterion_14": True,
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
