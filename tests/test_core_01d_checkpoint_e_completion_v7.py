"""Adversarial tests for the additive B4 current Checkpoint-E overlay."""
from __future__ import annotations

from copy import deepcopy

import pytest

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
from scripts import audit_core_01d_checkpoint_e_completion_v6 as v6
from scripts import audit_core_01d_checkpoint_e_completion_v7 as v7
from scripts import audit_core_01d_sportybet_current_trigger_authority_b4 as b4


@pytest.fixture(scope="module")
def receipt():
    return boundary.read(v7.RECEIPT_PATH)


def test_v7_is_nine_surface_overlay_and_leaves_exact_seven_predecessor_rows(receipt):
    parent = boundary.read(v7.PARENT_PATH)
    assert parent["canonical_sha256"] == v7.PARENT_SHA
    inherited = {(row["workflow_path"], row["trigger_kind"]): row
                 for row in parent["unreviewed_authority_surfaces"]}
    targets = set(b4.TARGETS)
    remaining = {(row["workflow_path"], row["trigger_kind"]): row
                 for row in receipt["unreviewed_authority_surfaces"]}
    assert set(inherited) - targets == set(remaining)
    assert remaining == {key: inherited[key] for key in set(inherited) - targets}
    assert receipt["scope"]["inherited_unreviewed_count"] == 16
    assert receipt["scope"]["target_surface_count"] == 9
    assert receipt["scope"]["resolved_target_count"] == 9
    assert receipt["scope"]["partial_target_count"] == 0
    assert receipt["scope"]["remaining_global_unreviewed_surface_count"] == 7


def test_v7_preserves_currently_incomplete_checkpoint_and_historical_retention(receipt):
    assert receipt["checkpoint_e_status"] == receipt["p4_4_status"] == "INCOMPLETE"
    assert receipt["checkpoint_criteria"]["all_retained_workflow_authority_and_dynamic_reachability_review_complete"] is False
    assert receipt["checkpoint_criteria"]["no_unknown_current_artifact_or_notification_authority"] is False
    assert receipt["historical_missing_artifact_relation_count"] == 14
    assert receipt["live_missing_artifact_relation_count"] == 0
    assert receipt["retention_blockers_A_B_C_D"] == "CLOSED_WITH_HISTORICAL_LIMITATIONS_PRESERVED"
    assert receipt["workflow_retirement_count"] == receipt["workflow_deletion_count"] == receipt["caller_migration_count"] == 0


@pytest.mark.parametrize("mutation", [
    lambda r: r["unreviewed_authority_surfaces"].pop(),
    lambda r: r["unreviewed_authority_surfaces"][0].update(current_source_sha256="0" * 64),
    lambda r: r["checkpoint_criteria"].update(all_retained_workflow_authority_and_dynamic_reachability_review_complete=True),
    lambda r: r["checkpoint_criteria"].update(no_unknown_current_artifact_or_notification_authority=True),
    lambda r: r.update(checkpoint_e_status="COMPLETE"),
    lambda r: r.update(p4_4_status="COMPLETE"),
    lambda r: r["scope"].update(remaining_global_unreviewed_surface_count=6),
    lambda r: r["scope"].update(resolved_target_count=8),
])
def test_v7_rejects_completion_or_non_target_mutation(receipt, mutation):
    mutant = deepcopy(receipt)
    mutation(mutant)
    with pytest.raises(AssertionError):
        v7.validate_receipt(mutant)


def test_v7_binds_exact_b4_and_immutable_v6_identities(receipt):
    assert receipt["predecessor_completion_v6"] == {
        "path": v6.RECEIPT_PATH, "canonical_sha256": v7.PARENT_SHA, "rewritten": False
    }
    assert receipt["predecessor_b4_review"]["path"] == b4.RECEIPT_PATH
    assert receipt["predecessor_b4_review"]["canonical_sha256"] == b4.boundary.read(b4.RECEIPT_PATH)["canonical_sha256"]
    assert v7.audit()["remaining_unreviewed_surface_count"] == 7
