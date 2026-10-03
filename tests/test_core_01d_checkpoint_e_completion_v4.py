"""The B1 overlay resolves only proven exact-PR trigger surfaces."""
from copy import deepcopy

import pytest

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
from scripts import audit_core_01d_checkpoint_e_completion_v4 as current


@pytest.fixture(scope="module")
def receipt():
    return current.audit() and boundary.read(current.RECEIPT_PATH)


def test_v4_resolves_only_the_seven_b1_keys_and_derives_remaining_count(receipt):
    parent = boundary.read(current.PARENT_PATH)
    target_keys = set(tuple(key) for key in receipt["scope"]["target_keys"])
    resolved = { (row["workflow_path"], row["trigger_kind"])
                 for row in receipt["resolved_target_surfaces"] }
    assert len(target_keys) == 7
    assert resolved == target_keys
    assert receipt["scope"]["inherited_unreviewed_count"] == 32
    assert receipt["scope"]["resolved_target_count"] == 7
    assert receipt["scope"]["remaining_global_unreviewed_surface_count"] == 25
    assert receipt["unreviewed_authority_surfaces"] == [
        row for row in parent["unreviewed_authority_surfaces"]
        if (row["workflow_path"], row["trigger_kind"]) not in resolved
    ]


def test_v3_predecessor_and_global_completion_truth_are_immutable(receipt):
    parent = boundary.read(current.PARENT_PATH)
    assert parent["canonical_sha256"] == current.EXPECTED_PARENT_SHA
    assert receipt["predecessor_completion_v3"] == {
        "path": current.PARENT_PATH,
        "canonical_sha256": current.EXPECTED_PARENT_SHA,
        "rewritten": False,
    }
    criteria = receipt["checkpoint_criteria"]
    assert criteria["all_retained_workflow_authority_and_dynamic_reachability_review_complete"] is False
    assert criteria["no_unknown_current_artifact_or_notification_authority"] is False
    assert receipt["checkpoint_e_status"] == receipt["p4_4_status"] == "INCOMPLETE"
    assert receipt["remaining_blocker_ids"] == parent["remaining_blocker_ids"]


@pytest.mark.parametrize("mutation", [
    "drop_non_target", "change_non_target", "criterion11", "criterion14",
    "complete", "p44", "unknown_count", "add_target", "retirement",
])
def test_falsified_completion_v4_is_rejected(receipt, mutation):
    value = deepcopy(receipt)
    if mutation == "drop_non_target":
        value["unreviewed_authority_surfaces"].pop()
    elif mutation == "change_non_target":
        value["unreviewed_authority_surfaces"][0]["workflow_path"] = ".github/workflows/athena-run.yml"
    elif mutation == "criterion11":
        value["checkpoint_criteria"]["all_retained_workflow_authority_and_dynamic_reachability_review_complete"] = True
    elif mutation == "criterion14":
        value["checkpoint_criteria"]["no_unknown_current_artifact_or_notification_authority"] = True
    elif mutation == "complete":
        value["checkpoint_e_status"] = "COMPLETE"
    elif mutation == "p44":
        value["p4_4_status"] = "COMPLETE"
    elif mutation == "unknown_count":
        value["scope"]["remaining_global_unreviewed_surface_count"] = 24
    elif mutation == "add_target":
        value["scope"]["target_keys"].append([".github/workflows/athena-run.yml", "push"])
    else:
        value["workflow_retirement_count"] = 1
    value = boundary.seal(value)
    with pytest.raises(AssertionError):
        current.validate_receipt(value, expected=receipt)


def test_checkpoint_completion_does_not_claim_retirement_or_deletion(receipt):
    assert receipt["workflow_count"] == 39
    assert receipt["trigger_surface_count"] == 57
    assert receipt["workflow_tree_before_sha1"] == receipt["workflow_tree_after_sha1"] == current.b1.WORKFLOW_TREE
    assert receipt["transition_count"] == 14
    assert receipt["retired_workflow_count"] == 3
    assert receipt["workflow_retirement_count"] == receipt["workflow_deletion_count"] == 0
    assert receipt["live_missing_artifact_relation_count"] == 0
    assert receipt["historical_missing_artifact_relation_count"] == 14
    assert receipt["actions"] == boundary.ZERO_ACTIONS
