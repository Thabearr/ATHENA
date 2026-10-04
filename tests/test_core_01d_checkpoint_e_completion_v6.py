from __future__ import annotations

from copy import deepcopy

import pytest

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
from scripts import audit_core_01d_checkpoint_e_completion_v5 as v5
from scripts import audit_core_01d_checkpoint_e_completion_v6 as v6
from scripts import audit_core_01d_owner_one_shot_issue_comment_authority_b3 as b3


def test_completion_v6_is_a_four_surface_overlay_over_immutable_v5():
    parent = boundary.read(v5.RECEIPT_PATH)
    current = boundary.read(v6.RECEIPT_PATH)
    assert parent["canonical_sha256"] == v6.PARENT_SHA
    assert parent["scope"]["remaining_global_unreviewed_surface_count"] == 20
    assert parent["scope"]["inherited_unreviewed_count"] == 25
    assert current["scope"]["target_surface_count"] == 4
    assert current["scope"]["resolved_target_count"] == 4
    assert current["scope"]["partial_target_count"] == 0
    assert current["scope"]["remaining_global_unreviewed_surface_count"] == 16
    assert current["checkpoint_e_status"] == current["p4_4_status"] == "INCOMPLETE"
    assert current["checkpoint_criteria"]["all_retained_workflow_authority_and_dynamic_reachability_review_complete"] is False
    assert current["checkpoint_criteria"]["no_unknown_current_artifact_or_notification_authority"] is False


def test_completion_v6_preserves_every_non_target_unknown_row_unchanged():
    parent = boundary.read(v5.RECEIPT_PATH)
    current = boundary.read(v6.RECEIPT_PATH)
    resolved_keys = {(path, event) for path, event in current["scope"]["target_keys"]}
    expected = [row for row in parent["unreviewed_authority_surfaces"]
                if (row["workflow_path"], row["trigger_kind"]) not in resolved_keys]
    assert current["unreviewed_authority_surfaces"] == expected
    assert len(expected) == 16
    assert current["unresolved_target_keys"] == []


def test_completion_v6_historical_and_retention_facts_are_unchanged():
    parent = boundary.read(v5.RECEIPT_PATH)
    current = boundary.read(v6.RECEIPT_PATH)
    for field in (
        "workflow_count", "trigger_surface_count", "workflow_tree_before_sha1", "workflow_tree_after_sha1",
        "evolution_ledger_before_sha256", "evolution_ledger_after_sha256", "transition_count",
        "retirement_ledger_sha256", "retired_workflow_count", "live_missing_artifact_relation_count",
        "historical_missing_artifact_relation_count", "retention_blockers_A_B_C_D",
    ):
        assert current[field] == parent[field]
    assert current["live_missing_artifact_relation_count"] == 0
    assert current["historical_missing_artifact_relation_count"] == 14
    assert current["retention_blockers_A_B_C_D"] == "CLOSED_WITH_HISTORICAL_LIMITATIONS_PRESERVED"
    assert current["workflow_edit_count"] == current["trigger_edit_count"] == 0
    assert current["workflow_retirement_count"] == current["workflow_deletion_count"] == 0
    assert current["caller_migration_count"] == 0


@pytest.mark.parametrize("mutation", ["criterion11", "criterion14", "complete", "drop_unknown", "wrong_count"])
def test_completion_v6_rejects_false_completion_or_unknown_surface_loss(mutation):
    current = boundary.read(v6.RECEIPT_PATH)
    mutant = deepcopy(current)
    if mutation == "criterion11":
        mutant["checkpoint_criteria"]["all_retained_workflow_authority_and_dynamic_reachability_review_complete"] = True
    elif mutation == "criterion14":
        mutant["checkpoint_criteria"]["no_unknown_current_artifact_or_notification_authority"] = True
    elif mutation == "complete":
        mutant["checkpoint_e_status"] = mutant["p4_4_status"] = "COMPLETE"
    elif mutation == "drop_unknown":
        mutant["unreviewed_authority_surfaces"].pop()
    else:
        mutant["scope"]["remaining_global_unreviewed_surface_count"] = 15
    with pytest.raises(AssertionError):
        v6.validate_receipt(mutant, expected=current, raw=boundary.canonical(mutant))


def test_completion_v6_uses_exact_b3_receipt_identity_and_keeps_exactly_sixteen_unknowns():
    current = boundary.read(v6.RECEIPT_PATH)
    review = boundary.read(b3.RECEIPT_PATH)
    assert current["b3_review"]["canonical_sha256"] == review["canonical_sha256"]
    assert current["scope"]["target_keys"] == [[path, event] for path, event in sorted(v6.TARGET_KEYS)]
    assert current["scope"]["remaining_global_unreviewed_surface_count"] == 20 - review["resolved_target_count"]
    assert current["scope"]["remaining_global_unreviewed_surface_count"] == 16
