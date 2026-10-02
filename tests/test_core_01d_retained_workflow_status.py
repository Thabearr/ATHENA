"""Fail-closed tests for immutable retained-status V1 and current V2."""
from copy import deepcopy
import json

import pytest

from scripts import audit_core_01d_retained_workflow_status_v2 as audit
from scripts import audit_core_01d_retained_workflow_status as v1


def _relations(receipt, artifact_id=None):
    rows = receipt["current_artifact_trigger_relationships"]
    return [row for row in rows if artifact_id is None or row["artifact_id"] == artifact_id]


def _artifact(receipt, artifact_id):
    row, = [item for item in receipt["artifact_dispositions"]
            if item["artifact_id"] == artifact_id]
    return row


def test_current_v2_audit_passes_and_checkpoint_stays_incomplete():
    result = audit.audit()
    assert result["result"] == "PASS"
    assert result["terminal"] == "CORE_01D_PR119_RELEASE_ONLY_BOOTSTRAP_REVIEW_READY_INCOMPLETE_DO_NOT_MERGE"
    assert result["checkpoint_e"] == result["p4_4"] == "INCOMPLETE"
    assert result["evolution_transition_count"] == 14
    assert result["workflow_count"] == 39
    assert result["trigger_surface_count"] == 57
    assert result["missing_artifact_count"] == 8
    assert result["artifact_workflow_edge_count"] == 12
    assert result["artifact_trigger_relationship_count"] == 14
    assert result["live_relation_count"] == 4
    assert result["historical_relation_count"] == 10


def test_retained_status_v1_is_immutable_before_state():
    raw = (v1.ROOT / v1.RECEIPT_PATH).read_bytes()
    value = v1._strict_json(raw, v1.RECEIPT_PATH)
    assert raw.replace(b"\r\n", b"\n") == v1.canonical_bytes(value)
    assert value["canonical_sha256"] == audit.V1_RECEIPT_SHA256
    assert v1.self_sha(value) == audit.V1_RECEIPT_SHA256
    assert value["policy_id"] == "ATHENA_CORE_01D_RETAINED_WORKFLOW_STATUS_V1"
    assert value["evolution_transition_count"] == 13
    assert value["reviewed_artifact_trigger_relationship_count"] == 17
    assert value["checkpoint_e_status"] == value["p4_4_status"] == "INCOMPLETE"


def test_v1_audit_reports_immutable_historical_input_after_transition_14():
    result = v1.audit()
    assert result["result"] == "PASS"
    assert result["historical_snapshot"] is True
    assert result["receipt_sha256"] == audit.V1_RECEIPT_SHA256
    assert result["evolution_transition_count"] == 13


def test_v2_binds_v1_and_derives_the_current_relationship_counts():
    receipt = audit.build_receipt()
    assert receipt["predecessor_v1"] == {
        "path": audit.V1_RECEIPT_PATH,
        "canonical_sha256": audit.V1_RECEIPT_SHA256,
        "state": "IMMUTABLE_PRE_PASS_1_BEFORE_STATE",
    }
    assert receipt["missing_artifact_count"] == 8
    assert receipt["exact_archive_recovered_count"] == 0
    assert receipt["partial_durable_copy_count"] == 1
    assert receipt["workflow_count"] == 39
    assert receipt["trigger_surface_count"] == 57
    assert receipt["artifact_workflow_edge_count"] == 12
    assert receipt["artifact_trigger_relationship_count"] == 14
    assert receipt["live_artifact_trigger_relationship_count"] == 4
    assert receipt["historical_or_spent_artifact_trigger_relationship_count"] == 10
    assert receipt["source_review_counter_while_open"] == "3/5"
    assert receipt["source_review_counter_if_owner_merges"] == "4/5"
    assert receipt["mandatory_source_reread_due"] is False


def test_artifact_924_stays_unrecovered_and_only_pr139_relation_remains():
    receipt = audit.build_receipt()
    artifact = _artifact(receipt, 9249856559)
    assert artifact["recovery_state"] == "METADATA_ONLY_NO_BYTES"
    assert artifact["expected_sha256"] == "7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f"
    assert artifact["expected_size_bytes"] == 61_886_753
    assert artifact["dependency_types"] == ["HARD_EXACT_REPLAY_SOURCE"]
    relations = _relations(receipt, 9249856559)
    assert len(relations) == 1
    assert relations[0]["workflow_path"] == ".github/workflows/execute-fotmob-utc-native-successor-feature-qualification-v2.yml"
    assert relations[0]["retained_status"] == "SPENT_HISTORICAL_ONE_SHOT_RETAIN"
    assert relations[0]["dependency_type"] == "HARD_EXACT_REPLAY_SOURCE"
    assert not any(
        row["workflow_path"] == audit.FRESH_WORKFLOW for row in relations
    )


def test_fixed_release_role_is_exact_and_does_not_claim_source_zip_recovery():
    receipt = audit.build_receipt()
    role = receipt["current_protected_bootstrap_role"]
    assert role["workflow_path"] == audit.FRESH_WORKFLOW
    assert {(row["event"], row["qualifier"]) for row in role["triggers"]} == {
        ("schedule", "cron 7 * * * *"),
        ("schedule", "cron 37 * * * *"),
        ("workflow_dispatch", "authenticated continuity dispatch"),
    }
    assert role["role_id"] == "PR119_BOOTSTRAP"
    assert role["source_kind"] == "FIXED_RELEASE"
    assert role["fixed_release_identity"] == {
        "repository": "Thabearr/ATHENA",
        "tag": "athena-fresh-holdout-bootstrap-v1",
        "release_name": "PR119 Materialized Bootstrap Projection",
        "release_id": 373205103,
        "draft": False,
        "prerelease": False,
        "asset_id": 521090702,
        "asset_name": "pr119-materialized.ndjson",
        "asset_state": "uploaded",
        "asset_size_bytes": 10_545_099,
        "asset_digest": "sha256:e5b78163a5eb68000b9a60dda97f04cac2a970f9cf2aaf588233151e586be8c2",
        "payload_sha256": "e5b78163a5eb68000b9a60dda97f04cac2a970f9cf2aaf588233151e586be8c2",
        "row_count": 21_326,
    }
    assert role["authority_classification"] == "EXACT_FIXED_BOOTSTRAP_NO_NEW_AUTHORITY"
    assert role["provider_reacquisition_authorized"] is False
    assert role["provider_reacquisition_performed"] is False
    assert role["historical_source_zip_recovered"] is False
    assert role["historical_source_zip_recovery_state"] == "METADATA_ONLY_NO_BYTES"
    assert role["runtime_fallback_artifact_ids"] == []
    assert role["backfill_authorized"] is False
    assert role["live_protected_research_retained"] is True


def test_only_blocker_a_closes_and_remaining_blockers_stay_open():
    receipt = audit.build_receipt()
    assert [row["id"] for row in receipt["closed_blockers"]] == [
        "PROTECTED_FRESH_HOLDOUT_PR119_EXACT_FALLBACK_NOT_DURABLY_RECOVERED"
    ]
    assert [row["id"] for row in receipt["remaining_blockers"]] == [
        "OWNER_GATED_PR145_FEATURE_EVIDENCE_NOT_DURABLY_RECOVERED",
        "CANONICAL_HISTORY_TRANSFER_SOURCE_NOT_FULLY_DURABLE",
        "HISTORICAL_REPLAY_ARCHIVES_UNAVAILABLE",
    ]
    assert receipt["checkpoint_e_status"] == receipt["p4_4_status"] == "INCOMPLETE"


@pytest.mark.parametrize(
    "mutation",
    [
        "recovered_zip",
        "provider_reacquisition",
        "backfill",
        "delete_blocker_b",
        "checkpoint_complete",
        "p44_complete",
        "runtime_fallback",
        "transition_count",
        "volatile_status",
    ],
)
def test_rehashed_authority_or_completion_mutations_are_rejected(mutation):
    changed = deepcopy(audit.build_receipt())
    role = changed["current_protected_bootstrap_role"]
    if mutation == "recovered_zip":
        role["historical_source_zip_recovered"] = True
    elif mutation == "provider_reacquisition":
        role["provider_reacquisition_authorized"] = True
    elif mutation == "backfill":
        role["backfill_authorized"] = True
    elif mutation == "delete_blocker_b":
        changed["remaining_blockers"].pop(0)
    elif mutation == "checkpoint_complete":
        changed["checkpoint_e_status"] = "COMPLETE"
    elif mutation == "p44_complete":
        changed["p4_4_status"] = "COMPLETE"
    elif mutation == "runtime_fallback":
        role["runtime_fallback_artifact_ids"] = [9249856559]
    elif mutation == "transition_count":
        changed["evolution_transition_id"] = "TRANSITION_15"
    elif mutation == "volatile_status":
        changed["volatile_run_state_used_for_static_classification"] = True
    audit.seal(changed)
    with pytest.raises(audit.RetainedWorkflowStatusV2Error):
        audit.validate_receipt(changed, audit.build_receipt())


def test_current_status_excludes_volatile_runtime_and_live_side_effects():
    receipt = audit.build_receipt()
    assert receipt["volatile_runtime_observations_included"] is False
    assert receipt["volatile_run_state_used_for_static_classification"] is False
    for key in (
        "provider_action_count",
        "workflow_dispatch_action_count",
        "workflow_rerun_or_cancel_action_count",
        "evidence_regeneration_count",
        "share_code_action_count",
        "email_action_count",
        "login_cookie_wallet_stake_wager_action_count",
    ):
        assert receipt[key] == 0
    assert set(receipt["semantic_delta"].values()) == {0}


def test_checkpoint_e_authenticates_current_v2_and_pass1_additive_artifacts():
    from scripts.audit_checkpoint_e_workflows import verified_additive_artifact_paths

    paths = verified_additive_artifact_paths()
    assert audit.RECEIPT_PATH in paths
    assert "artifacts/architecture/core_01d_fresh_holdout_pr119_release_only_bootstrap_v1.json" in paths
    assert "artifacts/architecture/p4_workflow_evolution_snapshots/core_01d_fresh_holdout_pr119_release_only_bootstrap_v1.json" in paths
