"""Completion V5 overlays only the exact five resolved B2 trigger surfaces."""
from copy import deepcopy

import pytest

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
from scripts import audit_core_01d_checkpoint_e_completion_v5 as current
from scripts import audit_core_01d_historical_warehouse_transfer_authority_b2 as b2


@pytest.fixture(scope="module")
def receipt():
    assert current.audit()["result"] == "PASS"
    return boundary.read(current.RECEIPT_PATH)


def test_v5_binds_immutable_v4_and_only_overlays_five_b2_keys(receipt):
    parent = boundary.read(current.PARENT_PATH)
    assert parent["canonical_sha256"] == current.PARENT_SHA
    assert receipt["predecessor_completion_v4"] == {
        "path": current.PARENT_PATH, "canonical_sha256": current.PARENT_SHA, "rewritten": False,
    }
    assert receipt["predecessor_b1_review"]["canonical_sha256"] == b2.B1_RECEIPT_SHA
    assert {tuple(key) for key in receipt["scope"]["target_keys"]} == set(b2.TARGET_KEYS)
    assert receipt["scope"]["inherited_unreviewed_count"] == 25
    assert receipt["scope"]["resolved_target_count"] == 5
    assert receipt["scope"]["partial_target_count"] == 0
    assert receipt["scope"]["remaining_global_unreviewed_surface_count"] == 20
    assert receipt["remaining_unreviewed_surface_count"] == 20
    expected = [row for row in parent["unreviewed_authority_surfaces"]
                if (row["workflow_path"], row["trigger_kind"]) not in set(b2.TARGET_KEYS)]
    assert receipt["unreviewed_authority_surfaces"] == expected


def test_v5_preserves_global_completion_and_retention_truth(receipt):
    parent = boundary.read(current.PARENT_PATH)
    assert receipt["checkpoint_criteria"] == parent["checkpoint_criteria"]
    assert receipt["checkpoint_criteria"]["all_retained_workflow_authority_and_dynamic_reachability_review_complete"] is False
    assert receipt["checkpoint_criteria"]["no_unknown_current_artifact_or_notification_authority"] is False
    assert receipt["checkpoint_e_status"] == receipt["p4_4_status"] == "INCOMPLETE"
    assert receipt["remaining_blocker_ids"] == parent["remaining_blocker_ids"]
    assert receipt["live_missing_artifact_relation_count"] == 0
    assert receipt["historical_missing_artifact_relation_count"] == 14
    assert receipt["retention_blockers_A_B_C_D"] == "CLOSED_WITH_HISTORICAL_LIMITATIONS_PRESERVED"


def test_v5_does_not_claim_workflow_retirement_deletion_or_caller_migration(receipt):
    assert receipt["workflow_edit_count"] == receipt["trigger_edit_count"] == 0
    assert receipt["workflow_retirement_count"] == receipt["workflow_deletion_count"] == 0
    assert receipt["caller_migration_count"] == 0
    assert receipt["workflow_count"] == 39 and receipt["trigger_surface_count"] == 57
    assert receipt["workflow_tree_before_sha1"] == receipt["workflow_tree_after_sha1"] == b2.WORKFLOW_TREE
    assert receipt["transition_count"] == 14
    assert receipt["retired_workflow_count"] == 3
    assert receipt["actions"] == b2.ZERO_ACTIONS


@pytest.mark.parametrize("mutation", [
    "drop_non_target", "change_non_target", "criterion11", "criterion14", "complete", "p44",
    "unknown_count", "add_target", "retire", "workflow_drift", "ledger_drift", "live_relation",
])
def test_falsified_completion_v5_is_rejected(receipt, mutation):
    changed = deepcopy(receipt)
    if mutation == "drop_non_target":
        changed["unreviewed_authority_surfaces"].pop()
    elif mutation == "change_non_target":
        changed["unreviewed_authority_surfaces"][0]["workflow_path"] = ".github/workflows/athena-run.yml"
    elif mutation == "criterion11":
        changed["checkpoint_criteria"]["all_retained_workflow_authority_and_dynamic_reachability_review_complete"] = True
    elif mutation == "criterion14":
        changed["checkpoint_criteria"]["no_unknown_current_artifact_or_notification_authority"] = True
    elif mutation == "complete":
        changed["checkpoint_e_status"] = "COMPLETE"
    elif mutation == "p44":
        changed["p4_4_status"] = "COMPLETE"
    elif mutation == "unknown_count":
        changed["scope"]["remaining_global_unreviewed_surface_count"] = 19
    elif mutation == "add_target":
        changed["scope"]["target_keys"].append([".github/workflows/athena-run.yml", "push"])
    elif mutation == "retire":
        changed["workflow_retirement_count"] = 1
    elif mutation == "workflow_drift":
        changed["workflow_tree_after_sha1"] = "0" * 40
    elif mutation == "ledger_drift":
        changed["transition_count"] = 15
    else:
        changed["live_missing_artifact_relation_count"] = 1
    with pytest.raises(AssertionError):
        current.validate_receipt(changed, expected=receipt)
