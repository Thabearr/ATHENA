from __future__ import annotations

from copy import deepcopy

import pytest

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
from scripts import audit_core_01d_checkpoint_e_completion_v8 as v8
from scripts import audit_core_01d_checkpoint_e_completion_v9 as v9
from scripts import audit_core_01d_port02c_trigger_authority_b6 as b6


def test_completion_v9_resolves_exactly_two_port_rows_and_preserves_the_win_row():
    value = v9.validate_receipt()
    assert value["predecessor_completion_v8"] == {
        "path": v8.RECEIPT_PATH,
        "canonical_sha256": v9.PARENT_SHA,
        "rewritten": False,
    }
    assert value["scope"] == {
        "inherited_unresolved_count": 3,
        "target_surface_count": 2,
        "resolved_target_count": 2,
        "partial_target_count": 0,
        "remaining_global_unreviewed_surface_count": 1,
        "target_keys": [[path, trigger] for path, trigger in b6.TARGETS],
    }
    parent = boundary.read(v8.RECEIPT_PATH)
    remaining = value["unreviewed_authority_surfaces"]
    inherited_win = next(row for row in parent["unreviewed_authority_surfaces"]
                         if (row["workflow_path"], row["trigger_kind"]) == b6.WIN_EITHER_HALF)
    assert remaining == [inherited_win]
    assert value["b6_reviewed_target_surfaces"] == [
        {"workflow_path": path, "trigger_kind": trigger, "review_status": "RESOLVED",
         "b6_receipt_sha256": value["b6_review"]["canonical_sha256"]}
        for path, trigger in b6.TARGETS
    ]
    assert value["unresolved_b6_target_keys"] == []


def test_completion_v9_keeps_criteria_incomplete_and_retention_history_unchanged():
    value = v9.validate_receipt()
    assert value["checkpoint_criteria"][
        "all_retained_workflow_authority_and_dynamic_reachability_review_complete"] is False
    assert value["checkpoint_criteria"][
        "no_unknown_current_artifact_or_notification_authority"] is False
    assert value["checkpoint_e_status"] == value["p4_4_status"] == "INCOMPLETE"
    assert value["historical_missing_artifact_relation_count"] == 14
    assert value["live_missing_artifact_relation_count"] == 0
    assert value["retention_blockers_A_B_C_D"] == "CLOSED_WITH_HISTORICAL_LIMITATIONS_PRESERVED"
    assert value["workflow_tree_before_sha1"] == value["workflow_tree_after_sha1"] == b6.WORKFLOW_TREE
    assert value["transition_count"] == 14
    assert value["retired_workflow_count"] == 3
    assert value["workflow_edit_count"] == value["trigger_edit_count"] == 0
    assert value["workflow_retirement_count"] == value["workflow_deletion_count"] == 0
    assert value["caller_migration_count"] == 0


def test_completion_v9_source_counter_and_final_review_boundary_are_explicit():
    value = v9.validate_receipt()
    assert value["source_review_counter_while_open"] == "0/5"
    assert value["source_review_counter_if_owner_merges"] == "1/5"
    assert value["mandatory_governing_source_reread_after_b6_merge"] == "NO"
    assert value["do_not_start_final_win_either_half_review_until_b6_owner_reviewed_merged_or_dispositioned"] is True
    assert value["terminal"] == \
        "CORE_01D_PORT02C_TRIGGER_AUTHORITY_B6_REVIEW_READY_2_RESOLVED_DO_NOT_MERGE"


@pytest.mark.parametrize("mutate", [
    lambda value: value["unreviewed_authority_surfaces"].pop(),
    lambda value: value["unreviewed_authority_surfaces"][0].update(current_source_sha256="changed"),
    lambda value: value["checkpoint_criteria"].update(
        all_retained_workflow_authority_and_dynamic_reachability_review_complete=True),
    lambda value: value["checkpoint_criteria"].update(
        no_unknown_current_artifact_or_notification_authority=True),
    lambda value: value.update(checkpoint_e_status="COMPLETE"),
    lambda value: value["scope"].update(remaining_global_unreviewed_surface_count=0),
    lambda value: value.update(source_review_counter_while_open="1/5"),
])
def test_completion_v9_rejects_scope_completion_or_counter_falsehoods(mutate):
    value = deepcopy(boundary.read(v9.RECEIPT_PATH))
    mutate(value)
    boundary.seal(value)
    with pytest.raises(AssertionError):
        v9.validate_receipt(value)


def test_current_master_and_historical_v2_still_authenticate():
    from scripts import audit_checkpoint_e_workflows as master
    from scripts import audit_core_01d_checkpoint_e_completion_v2 as historical_v2

    result = master.audit()
    assert result["current_completion_receipt_sha256"] == v9.audit()["receipt_sha256"]
    assert result["historical_completion_v2_receipt_sha256"] == \
        historical_v2.audit()["receipt_sha256"]
    assert result["remaining_unreviewed_surface_count"] == 1
    assert result["blockers"] == [
        "all_retained_workflow_authority_and_dynamic_reachability_review_complete",
        "no_unknown_current_artifact_or_notification_authority",
    ]
    assert result["checkpoint_e"] == result["p4_4"] == "INCOMPLETE"
    assert historical_v2.audit()["result"] == "PASS"
