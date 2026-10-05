"""Adversarial evidence tests for the final Win-Either-Half authority pass B7.

The full B7 receipt reconstruction is intentionally expensive because it authenticates
the complete immutable predecessor chain.  Authenticate it once per module, then make
all assertions against that exact authenticated document; individual tests still call
the cheap, source-local contract scanners where an independent source check matters.
"""
from __future__ import annotations

import json

import pytest

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
from scripts import audit_core_01d_win_either_half_trigger_authority_b7 as b7


@pytest.fixture(scope="module")
def authenticated_b7():
    audit = b7.audit()
    assert audit["result"] == "PASS"
    value = boundary.read(b7.RECEIPT_PATH)
    assert audit["receipt_sha256"] == value["canonical_sha256"]
    return value, audit


def test_b7_exact_single_surface_scope_and_zero_remaining(authenticated_b7):
    value, _ = authenticated_b7
    assert value["target_count"] == value["resolved_target_count"] == 1
    assert value["partial_target_count"] == 0
    assert value["global_unknown_before"] == 1
    assert value["global_unknown_after"] == 0
    assert value["target_keys"] == [[b7.WORKFLOW, "pull_request"]]
    assert value["remaining_unreviewed_surfaces"] == []
    assert value["criterion_11"] is True
    assert value["criterion_14"] is True
    assert value["checkpoint_e_status"] == value["p4_4_status"] == "COMPLETE"


def test_b7_trigger_is_current_path_filtered_pull_request_only():
    contract = b7._workflow_contract()
    assert contract["trigger_keys"] == ["pull_request"]
    pr = contract["pull_request"]
    assert pr["classification"] == "CONDITIONALLY_REACHABLE_PULL_REQUEST_PATH_FILTERED"
    assert pr["base_branches"] == ["main"]
    assert pr["paths"] == list(b7.EXPECTED_PR_PATHS)
    assert pr["current"] is True
    assert pr["spent_or_historical"] is False
    assert pr["exact_PR_bound"] is False
    assert pr["retired"] is False
    assert contract["direct_event_surface_requires_repository_caller"] is False


def test_b7_repository_token_cannot_write_and_checkout_credentials_are_disabled(authenticated_b7):
    value, _ = authenticated_b7
    contract = b7._workflow_contract()
    assert contract["permissions"] == {"contents": "read"}
    assert contract["checkouts"]["credentials_persist"] is False
    row = value["review_rows"][0]
    assert row["permissions_and_credentials"]["github_repository_write_authority"] == (
        "NO_SOURCE_PATH_AND_CREDENTIALS_DISABLED_CONTENTS_READ_ONLY"
    )
    assert row["write_authority"]["external_storage_write_authority"] == "NO_SOURCE_PATH"
    assert row["write_authority"]["release_publish_authority"] == "NO_SOURCE_PATH"


def test_b7_concurrency_has_no_configured_auto_cancel(authenticated_b7):
    value, _ = authenticated_b7
    concurrency = b7._workflow_contract()["concurrency"]
    assert concurrency["cancel_in_progress"] is False
    assert concurrency["platform_auto_cancel_authority"] == "NO_WORKFLOW_CONFIGURED_AUTO_CANCEL"
    assert value["actions"]["workflow_cancellations"] == 0


def test_b7_action_versions_and_manual_rerun_residual_are_explicit(authenticated_b7):
    value, _ = authenticated_b7
    row = value["review_rows"][0]
    assert row["action_versions"] == {
        "checkout": "actions/checkout@v4",
        "setup_python": "actions/setup-python@v5",
        "upload_artifact": "actions/upload-artifact@v4",
    }
    control = row["actions_control_plane"]
    assert control["workflow_dispatch_declared"] is False
    assert control["repository_dispatch_declared"] is False
    assert control["issue_comment_declared"] is False
    assert control["schedule_declared"] is False
    assert control["manual_rerun_residual"].startswith("KNOWN_GITHUB_ACTIONS_CONTROL_PLANE_CAPABILITY")
    assert control["b7_manual_reruns_performed"] == 0
    assert value["actions"]["workflow_reruns"] == 0


def test_b7_timing_attestation_is_conditional_run_scoped_and_not_product_authority(authenticated_b7):
    value, _ = authenticated_b7
    contract = b7._workflow_contract()
    artifact = contract["timing_attestation_artifact"]
    assert artifact == {
        "conditional": True,
        "guard": "env.ATTESTATION_CREATED == 'true'",
        "name": "win-either-half-campaign-commitment-${{ github.run_id }}",
        "retention_days": 90,
        "scope": "RUN_SCOPED_ACTIONS_ARTIFACT",
    }
    attestation = value["review_rows"][0]["attestation_authority"]
    assert attestation["declaration_mode_can_create_timing_attestation"] is True
    assert attestation["tooling_only_mode_creates_attestation"] is False
    assert attestation["bootstrap_mode_creates_attestation"] is False
    assert attestation["attestation_meaning"] == "TIMING_QUALIFICATION_ONLY"
    assert attestation["prospective_claim_authorized"] is False
    assert attestation["evidence_counting_authorized"] is False
    assert attestation["production_approval_authorized"] is False


def test_b7_has_no_application_provider_transport_path(authenticated_b7):
    value, _ = authenticated_b7
    scan = b7._assert_no_application_network_imports()
    assert scan["forbidden_import_hits"] == []
    assert set(scan["forbidden_application_network_roots"]) == {
        "aiohttp", "httpx", "requests", "socket", "urllib"
    }
    row = value["review_rows"][0]
    assert row["network_authority"]["current_provider_acquisition"] == "NONE_IN_VALIDATION_PATH"
    assert row["network_authority"]["application_validation_network_imports"] == (
        "NONE_IN_REVIEWED_STAGE_5B1_TO_5B4_SOURCE_PATH"
    )


def test_b7_market_model_selection_delivery_and_wager_authority_remain_disabled(authenticated_b7):
    value, _ = authenticated_b7
    authority = value["review_rows"][0]["model_market_delivery_and_wager"]
    domain = authority["domain_authority"]
    assert domain["prospective_claim_authorized"] is False
    assert domain["evidence_counting_authorized"] is False
    assert domain["selected_offset_seconds"] is None
    assert domain["production_approval_authorized"] is False
    assert set(domain["markets"]) == {"HOME_WIN_EITHER_HALF", "AWAY_WIN_EITHER_HALF"}
    for market in domain["markets"].values():
        assert market["campaign_status"] == "DISABLED"
        assert market["pricing_authority"] == "NOT_AUTHORIZED"
        assert market["selection_authority"] == "NOT_AUTHORIZED"
    assert authority["production_model_authority"] == "NO"
    assert authority["production_probability_authority"] == "NO"
    assert authority["production_selection_authority"] == "NO"
    assert authority["provider_calls"] == 0
    assert authority["share_code_create_or_reload"] == 0
    assert authority["login_actions"] == 0
    assert authority["cookie_actions"] == 0
    assert authority["wallet_actions"] == 0
    assert authority["stake_actions"] == 0
    assert authority["wager_actions"] == 0


def test_b7_actions_and_workflow_semantic_delta_are_zero(authenticated_b7):
    value, _ = authenticated_b7
    assert set(value["actions"].values()) == {0}
    assert value["workflow_edit_count"] == 0
    assert value["trigger_edit_count"] == 0
    assert value["workflow_retirement_count"] == 0
    assert value["workflow_deletion_count"] == 0
    assert value["caller_migration_count"] == 0
    invariants = value["workflow_evolution_and_retirement_invariants"]
    assert invariants["workflow_tree_sha1"] == b7.WORKFLOW_TREE
    assert invariants["workflow_diff_count"] == 0
    assert invariants["transition_count"] == 14
    assert invariants["retired_workflow_count"] == 3


def test_b7_source_inventory_is_exact_and_immutable():
    value = b7.validate_source_inventory()
    assert value["canonical_sha256"] == b7.SOURCE_INVENTORY_SHA
    assert value["base_main_sha"] == b7.BASE_MAIN
    assert value["base_tree_sha"] == b7.BASE_TREE
    assert value["workflow_tree_sha1"] == b7.WORKFLOW_TREE
    assert {row["path"] for row in value["source_identities"]} == set(b7.SOURCE_PATHS)
    workflow = next(row for row in value["source_identities"] if row["path"] == b7.WORKFLOW)
    assert workflow["git_blob_sha1"] == b7.WORKFLOW_BLOB
    assert workflow["normalized_source_sha256"] == b7.WORKFLOW_SOURCE_SHA256


def test_b7_receipt_is_canonical_self_hashed_and_audited(authenticated_b7):
    value, audit = authenticated_b7
    raw = (b7.ROOT / b7.RECEIPT_PATH).read_bytes()
    assert raw == boundary.canonical(value)
    assert value["canonical_sha256"] == boundary.seal(value)["canonical_sha256"]
    assert audit["result"] == "PASS"
    assert audit["receipt_sha256"] == value["canonical_sha256"]


def test_b7_counter_and_terminal_are_review_ready_unmerged_only(authenticated_b7):
    value, _ = authenticated_b7
    assert value["source_review_counter_while_open"] == "1/5"
    assert value["source_review_counter_if_owner_merges"] == "2/5"
    assert value["mandatory_governing_source_reread_after_b7_merge"] == "NO"
    assert value["terminal"].endswith("DO_NOT_MERGE")
