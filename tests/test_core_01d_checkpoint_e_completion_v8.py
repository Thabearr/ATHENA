from __future__ import annotations

from copy import deepcopy

import pytest

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
from scripts import audit_core_01d_checkpoint_e_completion_v8 as v8


def test_completion_v8_derives_four_resolved_and_exact_three_remaining():
    value = v8.validate_receipt()
    assert value["predecessor_completion_v7"]["canonical_sha256"] == v8.PARENT_SHA
    assert value["scope"]["inherited_unresolved_count"] == 7
    assert value["scope"]["target_surface_count"] == 4
    assert value["scope"]["resolved_target_count"] == 4
    assert value["scope"]["partial_target_count"] == 0
    assert value["scope"]["remaining_global_unreviewed_surface_count"] == 3
    assert {(row["workflow_path"], row["trigger_kind"])
            for row in value["unreviewed_authority_surfaces"]} == v8.EXPECTED_FINAL_KEYS


def test_completion_v8_keeps_global_criteria_false_and_source_reread_due_after_merge():
    value = v8.validate_receipt()
    assert value["checkpoint_criteria"]["all_retained_workflow_authority_and_dynamic_reachability_review_complete"] is False
    assert value["checkpoint_criteria"]["no_unknown_current_artifact_or_notification_authority"] is False
    assert value["checkpoint_e_status"] == value["p4_4_status"] == "INCOMPLETE"
    assert value["source_review_counter_while_open"] == "4/5"
    assert value["source_review_counter_if_owner_merges"] == "5/5"
    assert value["mandatory_governing_source_reread_after_b5_merge"] is True
    assert value["do_not_start_b6_before_reread"] is True
    assert value["retention_blockers_A_B_C_D"] == "CLOSED_WITH_HISTORICAL_LIMITATIONS_PRESERVED"
    assert value["live_missing_artifact_relation_count"] == 0
    assert value["historical_missing_artifact_relation_count"] == 14


@pytest.mark.parametrize("mutate", [
    lambda value: value["unreviewed_authority_surfaces"].pop(),
    lambda value: value["unreviewed_authority_surfaces"][0].update(current_source_sha256="forged"),
    lambda value: value["checkpoint_criteria"].update(all_retained_workflow_authority_and_dynamic_reachability_review_complete=True),
    lambda value: value["checkpoint_criteria"].update(no_unknown_current_artifact_or_notification_authority=True),
    lambda value: value.update(checkpoint_e_status="COMPLETE"),
    lambda value: value["scope"].update(remaining_global_unreviewed_surface_count=2),
])
def test_false_completion_or_non_target_mutation_fails_closed(mutate):
    value = deepcopy(boundary.read(v8.RECEIPT_PATH))
    mutate(value)
    with pytest.raises(AssertionError):
        v8.validate_receipt(value)
