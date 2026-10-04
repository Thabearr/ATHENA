"""Adversarial offline tests for B4's nine current SportyBet trigger surfaces."""
from __future__ import annotations

from copy import deepcopy

import pytest

from scripts import audit_core_01d_sportybet_current_trigger_authority_b4 as b4


@pytest.fixture(scope="module")
def receipt():
    return b4.boundary.read(b4.RECEIPT_PATH)


def _row(receipt, path_suffix: str, event: str):
    return next(row for row in receipt["review_rows"]
                if row["identity"]["workflow_path"].endswith(path_suffix)
                and row["identity"]["trigger_kind"] == event)


def test_exact_nine_surface_scope_and_completion_v6_inheritance(receipt):
    keys = [(row["identity"]["workflow_path"], row["identity"]["trigger_kind"])
            for row in receipt["review_rows"]]
    assert len(keys) == len(set(keys)) == 9
    assert set(keys) == set(b4.TARGETS)
    assert all(path != ".github/workflows/pr258-sportybet-live-transport-proof.yml"
               or event == "workflow_dispatch" for path, event in keys)
    assert receipt["scope"] == {
        "inherited_unresolved_surface_count": 16,
        "target_surface_count": 9,
        "resolved_target_count": 9,
        "partial_target_count": 0,
        "global_unresolved_before": 16,
        "global_unresolved_after": 7,
        "target_keys": [[path, event] for path, event in b4.TARGETS],
    }


@pytest.mark.parametrize("path,event", b4.TARGETS)
def test_each_target_has_source_identity_contract_reachability_and_authority(receipt, path, event):
    row = next(r for r in receipt["review_rows"]
               if (r["identity"]["workflow_path"], r["identity"]["trigger_kind"]) == (path, event))
    assert row["identity"]["git_blob_sha1"] == b4.SOURCE_PINS[path][0]
    assert row["identity"]["normalized_source_sha256"] == b4.SOURCE_PINS[path][1]
    assert row["reachability"]["physical_trigger_runtime_authority"] == b4.TARGET_REACHABILITY[(path, event)]
    assert row["reachability"]["repository_caller_state"] == "NO_CURRENT_REPOSITORY_CALLER_FOUND_SOURCE_SCAN"
    assert row["review"] == {"status": "RESOLVED", "blocker": None}
    assert row["authority"]["sportybet_login_authority"] == "NO_SOURCE_PATH"
    assert row["authority"]["sportybet_cookie_authority"] == "NO_SOURCE_PATH"
    assert row["authority"]["sportybet_wallet_authority"] == "NO_SOURCE_PATH"
    assert row["authority"]["sportybet_stake_submission_authority"] == "NO_SOURCE_PATH"
    assert row["authority"]["sportybet_wager_authority"] == "NO_SOURCE_PATH"
    assert row["authority"]["github_actions_artifact_write_authority"] == "RUN_SCOPED_ARTIFACT_UPLOAD"
    assert row["authority"]["github_branch_or_repository_write_authority"] == "NONE_CONTENTS_READ_ONLY_TOKEN"
    assert row["support_disposition"]["product_supported_current_operation_dependency"] == "NONE_RETAINED_RESEARCH_ONLY"
    assert row["support_disposition"]["physical_trigger_runtime_authority"] == b4.TARGET_REACHABILITY[(path, event)]


def test_path_filtered_pr_surfaces_remain_conditionally_reachable_and_manual_surfaces_remain_manual(receipt):
    for suffix in ("create-saturday-2026-08-22-sportybet-direct-20-code.yml",
                   "probe-sportybet-direct-20-markets.yml", "prove-sportybet-direct-share-code.yml"):
        row = _row(receipt, suffix, "pull_request")
        assert row["reachability"]["physical_trigger_runtime_authority"] == "CONDITIONALLY_REACHABLE_PULL_REQUEST_PATH_FILTERED"
        assert row["trigger_contract"]["branch_filters"] == ["main"]
        assert len(row["trigger_contract"]["path_filters"]) == 4
    for path, event in b4.TARGETS:
        if event == "workflow_dispatch":
            row = next(r for r in receipt["review_rows"] if r["identity"]["workflow_path"] == path and r["identity"]["trigger_kind"] == event)
            assert row["reachability"]["physical_trigger_runtime_authority"] == "MANUALLY_REACHABLE_WORKFLOW_DISPATCH"
            assert row["reachability"]["manual_control_plane_state"] == "DECLARED_AND_MANUALLY_REACHABLE"
    prb = _row(receipt, "prb-sportybet-semantic-registry-proof.yml", "pull_request")
    assert prb["trigger_contract"]["head_ref_guard"] == "github.head_ref == 'feat/prb-sportybet-semantic-registry'"
    assert prb["reachability"]["physical_trigger_runtime_authority"] == "CONDITIONALLY_REACHABLE_PULL_REQUEST_EXACT_HEAD_REF"
    assert "recreatable" in prb["reachability"]["reason"]


def test_direct_share_post_is_mutation_not_wager_and_probe_is_get_only(receipt):
    create = _row(receipt, "create-saturday-2026-08-22-sportybet-direct-20-code.yml", "workflow_dispatch")["authority"]
    one_leg = _row(receipt, "prove-sportybet-direct-share-code.yml", "pull_request")["authority"]
    for authority in (create, one_leg):
        assert authority["sportybet_share_code_create_authority"] == "YES_CURRENTLY_REACHABLE_UNDER_DECLARED_TRIGGER"
        assert authority["sportybet_share_code_reload_authority"] == "YES_CURRENTLY_REACHABLE_UNDER_DECLARED_TRIGGER"
        assert authority["sportybet_wager_authority"] == "NO_SOURCE_PATH"
    probe = _row(receipt, "probe-sportybet-direct-20-markets.yml", "workflow_dispatch")["authority"]
    assert probe["sportybet_market_read_authority"] == "YES_CURRENTLY_REACHABLE_UNDER_DECLARED_TRIGGER"
    assert probe["sportybet_share_code_create_authority"] == "NO_SOURCE_PATH"
    assert probe["sportybet_share_code_reload_authority"] == "NO_SOURCE_PATH"
    assert probe["sportybet_wager_authority"] == "NO_SOURCE_PATH"


def test_pr258_and_prb_keep_distinct_read_and_mutation_authority(receipt):
    pr258 = _row(receipt, "pr258-sportybet-live-transport-proof.yml", "workflow_dispatch")
    assert pr258["reachability"]["sibling_trigger_state"] == "PR258_PULL_REQUEST_RESOLVED_BY_B1_OUT_OF_SCOPE"
    for field in ("sportybet_upcoming_discovery_read_authority", "sportybet_event_detail_read_authority",
                  "sportybet_share_code_create_authority", "sportybet_share_code_reload_authority"):
        assert pr258["authority"][field] == "YES_CURRENTLY_REACHABLE_UNDER_DECLARED_TRIGGER"
    for field in ("model_authority", "production_selection_authority", "fixture_reconciliation_authority",
                  "sportybet_wager_authority"):
        assert pr258["authority"][field] == "NO_SOURCE_PATH"
    for event in ("pull_request", "workflow_dispatch"):
        prb = _row(receipt, "prb-sportybet-semantic-registry-proof.yml", event)["authority"]
        assert prb["sportybet_upcoming_discovery_read_authority"] == "BOUNDED_ANONYMOUS_DISCOVERY_GET"
        assert prb["sportybet_event_detail_read_authority"] == "BOUNDED_ANONYMOUS_EVENT_DETAIL_GET"
        assert prb["sportybet_share_code_create_authority"] == "NO_SOURCE_PATH"
        assert prb["sportybet_share_code_reload_authority"] == "NO_SOURCE_PATH"
        assert "GITHUB_GIT_LS_REMOTE_READ_ON_MANUAL_BASE_FALLBACK" in prb["network_authority_summary"]
        assert prb["github_branch_or_repository_write_authority"] == "NONE_CONTENTS_READ_ONLY_TOKEN"


def test_history_is_only_historical_metadata_and_not_current_transport_proof(receipt):
    assert len(receipt["source_inventory"]["canonical_sha256"]) == 64
    assert receipt["actions"] == b4.ZERO_ACTIONS
    for row in receipt["review_rows"]:
        observation = row["historical_run_metadata"]
        assert observation["read_only"] is True
        assert observation["interpretation"] == "HISTORICAL_RUN_METADATA_ONLY_NOT_CURRENT_AUTHORITY_OR_CURRENT_PROVIDER_PROOF"
        assert row["reachability"]["historical_actions_rerun_residual"] == "HISTORICAL_ACTIONS_RERUN_RESIDUAL_NOT_PROVEN_ABSENT"
    scan = b4.boundary.read(b4.SOURCE_INVENTORY_PATH)["repository_caller_scan"]
    assert scan["result"] == "NO_CURRENT_REPOSITORY_CALLER_FOUND_SOURCE_SCAN"
    assert scan["external_manual_dispatch_authority"] == "PRESERVED_NOT_ERASED_BY_NO_REPOSITORY_CALLER"


@pytest.mark.parametrize("mutation", [
    lambda r: r["review_rows"].pop(),
    lambda r: r["review_rows"].append(deepcopy(r["review_rows"][0])),
    lambda r: r["review_rows"][0]["reachability"].update(physical_trigger_runtime_authority="SPENT"),
    lambda r: r["review_rows"][1]["authority"].update(sportybet_wager_authority="YES"),
    lambda r: r["review_rows"][0]["authority"].update(sportybet_share_code_create_authority="NO_SOURCE_PATH"),
    lambda r: r["review_rows"][5]["authority"].update(sportybet_share_code_create_authority="YES_CURRENTLY_REACHABLE_UNDER_DECLARED_TRIGGER"),
    lambda r: r["review_rows"][3]["authority"].update(sportybet_share_code_create_authority="YES_CURRENTLY_REACHABLE_UNDER_DECLARED_TRIGGER"),
    lambda r: r.update(checkpoint_e_status="COMPLETE"),
])
def test_b4_receipt_mutations_are_rejected(receipt, mutation):
    mutant = deepcopy(receipt)
    mutation(mutant)
    with pytest.raises(AssertionError):
        b4.validate_receipt(mutant)


def test_source_inventory_mutations_and_workflow_source_drift_fail_closed():
    inventory = b4.boundary.read(b4.SOURCE_INVENTORY_PATH)
    mutant = deepcopy(inventory)
    mutant["target_keys"].pop()
    with pytest.raises(AssertionError):
        b4.validate_source_inventory(mutant)
    assert b4.validate_source_inventory(inventory)["source_count"] == len(b4.SOURCE_PINS)


def test_b4_never_changes_workflow_or_authorizes_live_operations(receipt):
    assert receipt["workflow_tree_sha1"] == b4.WORKFLOW_TREE
    assert receipt["workflow_edit_count"] == receipt["trigger_edit_count"] == 0
    assert receipt["retirement_count"] == receipt["deletion_count"] == receipt["caller_migration_count"] == 0
    assert set(receipt["actions"].values()) == {0}
    assert receipt["criterion_11"] is False and receipt["criterion_14"] is False
    assert receipt["checkpoint_e_status"] == receipt["p4_4_status"] == "INCOMPLETE"
