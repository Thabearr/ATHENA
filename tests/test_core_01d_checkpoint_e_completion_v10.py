"""Closure proofs for Checkpoint-E/P4.4 Completion V10.

Completion V10 authenticates the full immutable predecessor chain, so the expensive
closure audit is performed once per module.  Tests then assert independently against
the exact authenticated receipt and the current A2 inventory.
"""
from __future__ import annotations

import json

import pytest

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
from scripts import audit_core_01d_checkpoint_e_completion_v9 as v9
from scripts import audit_core_01d_checkpoint_e_completion_v10 as v10
from scripts import audit_core_01d_win_either_half_trigger_authority_b7 as b7


@pytest.fixture(scope="module")
def authenticated_v10():
    audit = v10.audit()
    assert audit["result"] == "PASS"
    value = boundary.read(v10.RECEIPT_PATH)
    assert audit["receipt_sha256"] == value["canonical_sha256"]
    return value, audit


def test_v10_derives_from_exact_immutable_v9_and_b7(authenticated_v10):
    value, _ = authenticated_v10
    assert value["predecessor_completion_v9"] == {
        "path": v9.RECEIPT_PATH,
        "canonical_sha256": v10.PARENT_SHA,
        "rewritten": False,
    }
    b7_receipt = boundary.read(b7.RECEIPT_PATH)
    assert value["b7_review"]["path"] == b7.RECEIPT_PATH
    assert value["b7_review"]["canonical_sha256"] == b7_receipt["canonical_sha256"]
    assert value["b7_source_inventory"] == {
        "path": b7.SOURCE_INVENTORY_PATH,
        "canonical_sha256": b7.SOURCE_INVENTORY_SHA,
    }


def test_v10_closes_the_exact_one_remaining_surface(authenticated_v10):
    value, _ = authenticated_v10
    parent = boundary.read(v9.RECEIPT_PATH)
    assert [(row["workflow_path"], row["trigger_kind"])
            for row in parent["unreviewed_authority_surfaces"]] == [b7.TARGET]
    assert value["scope"] == {
        "inherited_unresolved_count": 1,
        "target_surface_count": 1,
        "resolved_target_count": 1,
        "partial_target_count": 0,
        "remaining_global_unreviewed_surface_count": 0,
        "target_keys": [[b7.WORKFLOW, "pull_request"]],
    }
    assert value["unresolved_b7_target_keys"] == []
    assert value["unreviewed_authority_surfaces"] == []


def test_v10_all_checkpoint_criteria_are_true_and_blockers_are_empty(authenticated_v10):
    value, _ = authenticated_v10
    assert value["checkpoint_criteria"]
    assert all(flag is True for flag in value["checkpoint_criteria"].values())
    assert value["checkpoint_criteria"][
        "all_retained_workflow_authority_and_dynamic_reachability_review_complete"
    ] is True
    assert value["checkpoint_criteria"][
        "no_unknown_current_artifact_or_notification_authority"
    ] is True
    assert value["remaining_blocker_ids"] == []
    assert value["checkpoint_e_status"] == "COMPLETE"
    assert value["p4_4_status"] == "COMPLETE"


def test_v10_preserves_retention_and_workflow_lineage_invariants(authenticated_v10):
    value, _ = authenticated_v10
    assert value["historical_missing_artifact_relation_count"] == 14
    assert value["live_missing_artifact_relation_count"] == 0
    assert value["retention_blockers_A_B_C_D"] == "CLOSED_WITH_HISTORICAL_LIMITATIONS_PRESERVED"
    assert value["workflow_tree_before_sha1"] == b7.WORKFLOW_TREE
    assert value["workflow_tree_after_sha1"] == b7.WORKFLOW_TREE
    assert value["transition_count"] == 14
    assert value["retired_workflow_count"] == 3
    assert value["workflow_edit_count"] == 0
    assert value["trigger_edit_count"] == 0
    assert value["workflow_retirement_count"] == 0
    assert value["workflow_deletion_count"] == 0
    assert value["caller_migration_count"] == 0


def test_v10_binds_append_only_a2_generation_v9_to_v8(authenticated_v10):
    value, _ = authenticated_v10
    assert boundary.authenticate_inventory()["generation"] >= 9
    generation = b7.authenticated_historical_a2_v9()
    assert generation["generation"] == 9
    assert generation["predecessor_inventory"] == {
        "path": boundary.inventory_generation_path(8),
        "canonical_sha256": v10.A2_V8_SHA,
        "generation": 8,
        "rewritten": False,
    }
    assert value["a2_generation_9"] == {
        "path": boundary.inventory_generation_path(9),
        "canonical_sha256": generation["canonical_sha256"],
        "generation": 9,
        "predecessor": generation["predecessor_inventory"],
        "rewritten": False,
    }
    paths = {row["path"] for row in generation["source_identities"]}
    assert {
        "scripts/audit_core_01d_win_either_half_trigger_authority_b7.py",
        "scripts/audit_core_01d_checkpoint_e_completion_v10.py",
        "tests/test_core_01d_win_either_half_trigger_authority_b7.py",
        "tests/test_core_01d_checkpoint_e_completion_v10.py",
    } <= paths


def test_v10_is_canonical_review_ready_and_unmerged(authenticated_v10):
    value, audit = authenticated_v10
    raw = (boundary.ROOT / v10.RECEIPT_PATH).read_bytes()
    assert raw == boundary.canonical(value)
    assert value["canonical_sha256"] == boundary.seal(value)["canonical_sha256"]
    assert value["source_review_counter_while_open"] == "1/5"
    assert value["source_review_counter_if_owner_merges"] == "2/5"
    assert value["mandatory_governing_source_reread_after_b7_merge"] == "NO"
    assert value["terminal"] == "CORE_01D_CHECKPOINT_E_P4_4_COMPLETE_B7_REVIEW_READY_DO_NOT_MERGE"
    assert audit["checkpoint_e"] == audit["p4_4"] == "COMPLETE"
    assert audit["remaining_unreviewed_surface_count"] == 0
    assert audit["remaining_blockers"] == []
