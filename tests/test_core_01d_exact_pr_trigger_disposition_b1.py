"""Source and GitHub-metadata invariants for the exact-PR B1 review."""
from copy import deepcopy

import pytest

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
from scripts import audit_core_01d_checkpoint_e_completion_v2 as completion_v2
from scripts import audit_core_01d_exact_pr_trigger_disposition_b1 as b1


@pytest.fixture(scope="module")
def receipt():
    return b1.audit() and boundary.read(b1.RECEIPT_PATH)


def test_exact_seven_surface_scope_and_immutable_predecessors(receipt):
    assert len(b1.TARGET_KEYS) == 7
    assert len(set(b1.TARGET_KEYS)) == 7
    assert set((row["workflow_path"] + "#" + row["trigger_kind"])
               for row in receipt["review_rows"]) == set(b1.TARGET_KEYS)
    assert receipt["predecessors"]["completion_v3_sha256"] == b1.COMPLETION_V3_SHA
    assert receipt["predecessors"]["a2_v1_inventory_sha256"] == b1.V1_INVENTORY_SHA
    assert receipt["predecessors"]["a2_v2_inventory_sha256"] == b1.V2_INVENTORY_SHA


def test_seven_surfaces_resolve_event_reachability_separately_from_authority(receipt):
    assert receipt["scope"] == {
        "surface_count": 7, "workflow_count": 7, "target_keys": list(b1.TARGET_KEYS),
        "resolved_count": 7, "partial_count": 0,
    }
    rows = {row["live_bound_pr"]["exact_pr_number"]: row for row in receipt["review_rows"]}
    edited_prs = {192, 199}
    for pr_number, row in rows.items():
        reachability = row["reachability"]
        assert reachability["historical_actions_rerun_residual"] == b1.RERUN_RESIDUAL
        if pr_number in edited_prs:
            assert reachability["pull_request_event_may_be_delivered"] is True
            assert reachability["declared_trigger_current_reachability"] == (
                "CURRENT_EDIT_EVENT_MAY_BE_DELIVERED_BUT_MERGED_DRAFT_GUARD_BLOCKS_CAPTURE_AUTHORITY")
            expected_effect = (
                "NONE_DRAFT_GUARD_FAILS_CLOSED" if pr_number == 199 else
                "NO_PROVIDER_CAPTURE; ALWAYS_UPLOAD_ACTION_FAILS_ON_ABSENT_CAMPAIGN_PATH; STEP_SUMMARY_IS_WRITTEN"
            )
            assert reachability["current_external_capture_authority"] == expected_effect
            assert row["live_bound_pr"]["metadata"]["draft"] is False
            assert row["trigger_contract"]["draft_guard"] is True
            assert row["current_declared_pull_request_authority"]["provider_acquisition_authority"] == b1.CURRENT_EDIT_GUARD_BLOCKED
        else:
            assert reachability["pull_request_event_may_be_delivered"] is False
            assert reachability["declared_trigger_current_reachability"] == (
                "CURRENT_DECLARED_PULL_REQUEST_TRIGGER_SPENT_EXACT_MERGED_PR_BINDING")
            assert reachability["reopenability"] == "IMPOSSIBLE_AS_MERGED_PR"
        assert row["reachability"]["historical_actions_rerun_residual"] == b1.RERUN_RESIDUAL
        assert row["review"]["workflow_file_disposition"] == "NOT_CLASSIFIED_BY_THIS_TRIGGER_SURFACE_REVIEW"


def test_merged_edit_events_are_not_mislabeled_impossible(receipt):
    rows = {row["live_bound_pr"]["exact_pr_number"]: row for row in receipt["review_rows"]}
    pr199 = rows[199]
    assert pr199["reachability"]["execution_guard_after_merge"] == (
        "JOB_IF_REQUIRES_DRAFT_TRUE; CURRENT_PR_DRAFT_FALSE_SKIPS_CAPTURE_JOB")
    assert pr199["current_declared_pull_request_authority"]["provider_acquisition_authority"] == b1.CURRENT_EDIT_GUARD_BLOCKED
    assert pr199["current_declared_pull_request_authority"]["notification_authority"] == "GITHUB_SKIPPED_JOB_STATUS_ONLY"
    assert pr199["reachability"]["current_post_guard_effects"] == []
    pr192 = rows[192]
    assert pr192["reachability"]["execution_guard_after_merge"] == (
        "FIRST_GITHUB_SCRIPT_REQUIRES_PR_DRAFT_TRUE; CURRENT_PR_DRAFT_FALSE_FAILS_BEFORE_CHECKOUT_OR_PROVIDER; ALWAYS_UPLOAD_FAILS_NO_FILES; ALWAYS_SUMMARY_WRITES_STEP_SUMMARY")
    assert pr192["current_declared_pull_request_authority"]["notification_authority"] == "GITHUB_FAILED_CHECK_LOG_AND_STEP_SUMMARY_ONLY"
    assert pr192["current_declared_pull_request_authority"]["provider_acquisition_authority"] == b1.CURRENT_EDIT_GUARD_BLOCKED
    assert pr192["current_declared_pull_request_authority"]["artifact_write_authority"] == (
        "RUN_SCOPED_UPLOAD_ACTION_REACHABLE; CAMPAIGN_PATH_NOT_CREATED_AFTER_GUARD_FAILURE; IF_NO_FILES_FOUND_ERROR")
    assert [effect["effect"] for effect in pr192["reachability"]["current_post_guard_effects"]] == [
        "RUN_SCOPED_ARTIFACT_UPLOAD_ATTEMPT", "GITHUB_STEP_SUMMARY_WRITE"]
    uploader = pr192["reachability"]["current_post_guard_effects"][0]
    assert uploader["path"] == "campaign-artifact/"
    assert uploader["if_no_files_found"] == "error"
    assert uploader["result"] == "UPLOAD_FAILS_CLOSED_WITH_NO_CAMPAIGN_ARTIFACT"
    assert pr192["reachability"]["current_post_guard_effects"][1]["result"] == (
        "SUMMARY_RECORDS_GUARD_FAILURE_AND_UPLOAD_OUTCOME")
    assert not pr192["dynamic_reachability"]["external_api_mutations_on_current_declared_pull_request_event"]


def test_edited_event_guard_disposition_cannot_be_forged_as_spent(receipt):
    mutated = deepcopy(receipt)
    row = next(item for item in mutated["review_rows"]
               if item["live_bound_pr"]["exact_pr_number"] == 199)
    row["reachability"]["pull_request_event_may_be_delivered"] = False
    row["reachability"]["declared_trigger_current_reachability"] = (
        "CURRENT_DECLARED_PULL_REQUEST_TRIGGER_SPENT_EXACT_MERGED_PR_BINDING")
    with pytest.raises(AssertionError):
        b1.validate_receipt(mutated)


def test_historical_authority_is_not_erased_when_current_event_is_spent(receipt):
    rows = {row["workflow_path"]: row for row in receipt["review_rows"]}
    sportybet = rows[".github/workflows/pr258-sportybet-live-transport-proof.yml"]
    assert sportybet["historical_guarded_capability"]["sportsbook_read_authority"] == "SPORTYBET_PUBLIC_EVENT_AND_MARKET_READ"
    assert sportybet["historical_guarded_capability"]["share_code_authority"] == "ANONYMOUS_PROOF_CREATE_AND_RELOAD"
    assert sportybet["historical_guarded_capability"]["wager_authority"] == "NONE"
    assert sportybet["current_declared_pull_request_authority"]["sportsbook_read_authority"] == b1.CURRENT_SPENT
    assert sportybet["dynamic_reachability"]["external_api_mutations_historically_reachable"]
    assert not sportybet["dynamic_reachability"]["external_api_mutations_on_current_declared_pull_request_event"]
    fotmob = rows[".github/workflows/execute-fotmob-prospective-player-context-campaign.yml"]
    assert fotmob["historical_guarded_capability"]["provider_acquisition_authority"].startswith("FOTMOB_")
    assert fotmob["current_declared_pull_request_authority"]["provider_acquisition_authority"] == b1.CURRENT_EDIT_GUARD_BLOCKED
    saturday_capture = rows[".github/workflows/capture-saturday-2026-08-22-fixture-universe.yml"]
    assert saturday_capture["historical_guarded_capability"]["provider_acquisition_authority"] == "FOTMOB_READ_ONLY_SOURCE_CAPTURE"
    assert saturday_capture["current_declared_pull_request_authority"]["provider_acquisition_authority"] == b1.CURRENT_EDIT_GUARD_BLOCKED


def test_sibling_triggers_remain_unresolved_and_out_of_scope(receipt):
    expected = {
        ".github/workflows/pr258-sportybet-live-transport-proof.yml#workflow_dispatch": "UNRESOLVED_OUT_OF_SCOPE_INHERITED_UNCHANGED",
        ".github/workflows/verify-saturday-2026-08-22-reviewed-fixture-catalog.yml#push": "UNRESOLVED_OUT_OF_SCOPE_INHERITED_UNCHANGED",
    }
    assert receipt["sibling_trigger_isolation"] == expected
    assert receipt["scope"]["target_keys"] == list(b1.TARGET_KEYS)
    assert receipt["actions"] == b1.ZERO_ACTIONS


@pytest.mark.parametrize("path", [
    ".github/workflows/pr258-sportybet-live-transport-proof.yml#workflow_dispatch",
    ".github/workflows/verify-saturday-2026-08-22-reviewed-fixture-catalog.yml#push",
])
def test_sibling_cannot_be_inserted_as_a_resolved_target(receipt, path):
    mutated = deepcopy(receipt)
    mutated["scope"]["target_keys"].append(path)
    with pytest.raises(AssertionError):
        b1.validate_receipt(mutated)


@pytest.mark.parametrize("field,value", [
    ("merged", False),
    ("merged_at", None),
    ("closed_at", None),
    ("state", "open"),
    ("draft", False),
])
def test_forged_live_pr_state_fails_closed(receipt, field, value):
    mutated = deepcopy(receipt)
    row = next(item for item in mutated["review_rows"]
               if item["live_bound_pr"]["exact_pr_number"] == 258)
    row["live_bound_pr"]["metadata"][field] = value
    with pytest.raises(AssertionError):
        b1.validate_receipt(mutated)


@pytest.mark.parametrize("pr_number", [192, 199])
def test_edited_event_current_draft_state_cannot_be_forged(receipt, pr_number):
    mutated = deepcopy(receipt)
    row = next(item for item in mutated["review_rows"]
               if item["live_bound_pr"]["exact_pr_number"] == pr_number)
    row["live_bound_pr"]["metadata"]["draft"] = True
    with pytest.raises(AssertionError):
        b1.validate_receipt(mutated)


def test_exact_head_and_base_identity_are_bound(receipt):
    pr258 = next(row for row in receipt["review_rows"] if row["live_bound_pr"]["exact_pr_number"] == 258)
    assert pr258["live_bound_pr"]["metadata"]["head"]["sha"] == b1.PR_HEADS[258]
    assert pr258["live_bound_pr"]["metadata"]["head"]["repo"] == "Thabearr/ATHENA"
    for row in receipt["review_rows"]:
        pr = row["live_bound_pr"]["metadata"]
        assert pr["merged"] is True and pr["state"] == "closed"
        assert pr["head"]["sha"] == b1.PR_HEADS[row["live_bound_pr"]["exact_pr_number"]]


def test_all_historical_run_rows_are_success_or_the_recorded_skip(receipt):
    runs = [run for row in receipt["review_rows"] for run in row["historical_runs"]]
    assert {run["run_id"] for run in runs} == set(b1.EXPECTED_RUNS)
    assert all(run["read_only"] and run["event"] == "pull_request" for run in runs)
    assert all(run["conclusion"] in {"success", "skipped"} for run in runs)
    assert sum(run["conclusion"] == "skipped" for run in runs) == 1
    assert all(run["api_pull_request_links"] == [] for run in runs)
    assert all(run["pr_identity_match_basis"] == (
        "PULL_REQUEST_EVENT_AND_EXACT_HEAD_REPOSITORY_BRANCH_SHA_MATCH_BOUND_LIVE_PR")
        for run in runs)
    assert all(run["observed_at_utc"] for run in runs)


def test_evidence_is_canonical_and_source_bound(receipt):
    inventory = boundary.read(b1.SOURCE_INVENTORY_PATH)
    assert inventory["base_main_sha"] == b1.BASE_MAIN
    assert inventory["base_tree_sha"] == b1.BASE_TREE
    assert inventory["scope"]["target_keys"] == list(b1.TARGET_KEYS)
    assert len(inventory["current_source_identities"]) == len(b1.CURRENT_SOURCE_PATHS)
    assert all(row["git_blob_sha1"] and row["normalized_source_sha256"]
               for row in inventory["historical_pr_head_source_identities"])
    assert receipt["source_inventory"]["canonical_sha256"] == inventory["canonical_sha256"]


def test_historical_completion_projection_accepts_only_post_v2_inventory_sources():
    latest = boundary.authenticate_inventory()
    v2 = boundary.read_generation(boundary.inventory_generation_path(2))
    v2_paths = {
        row["path"] for row in v2["source_identities"]
    }
    latest_paths = {row["path"] for row in latest["source_identities"]}
    added = latest_paths - v2_paths
    assert added == {
        "database/app_migrations.py",
        "database/app_migration_evidence.py",
        "database/app_repository.py",
        "services/app_preview_store.py",
        "tests/test_data_01a_app_schema.py",
        "scripts/audit_data_01a_app_schema_core.py",
        "api/app_factory.py",
        "runtime/local_session.py",
        "services/athena_capability_service.py",
        "scripts/audit_app_01a_local_shell.py",
        "tests/test_app_01a_local_shell.py",
        "scripts/audit_core_01d_checkpoint_e_completion_v4.py",
        "scripts/audit_core_01d_exact_pr_trigger_disposition_b1.py",
        "tests/test_core_01d_checkpoint_e_completion_v4.py",
        "tests/test_core_01d_exact_pr_trigger_disposition_b1.py",
        "scripts/audit_core_01d_historical_warehouse_transfer_authority_b2.py",
        "scripts/audit_core_01d_checkpoint_e_completion_v5.py",
        "tests/test_core_01d_historical_warehouse_transfer_authority_b2.py",
        "tests/test_core_01d_checkpoint_e_completion_v5.py",
        "scripts/audit_core_01d_owner_one_shot_issue_comment_authority_b3.py",
        "scripts/audit_core_01d_checkpoint_e_completion_v6.py",
        "tests/test_core_01d_owner_one_shot_issue_comment_authority_b3.py",
        "tests/test_core_01d_checkpoint_e_completion_v6.py",
        "scripts/audit_core_01d_sportybet_current_trigger_authority_b4.py",
        "scripts/audit_core_01d_checkpoint_e_completion_v7.py",
        "tests/test_core_01d_sportybet_current_trigger_authority_b4.py",
        "tests/test_core_01d_checkpoint_e_completion_v7.py",
        "scripts/audit_core_01d_frozen_artifact_replay_authority_b5.py",
        "scripts/audit_core_01d_checkpoint_e_completion_v8.py",
        "tests/test_core_01d_frozen_artifact_replay_authority_b5.py",
        "tests/test_core_01d_checkpoint_e_completion_v8.py",
        "scripts/audit_core_01d_port02c_trigger_authority_b6.py",
        "scripts/audit_core_01d_checkpoint_e_completion_v9.py",
        "tests/test_core_01d_port02c_trigger_authority_b6.py",
        "tests/test_core_01d_checkpoint_e_completion_v9.py",
        "scripts/audit_core_01d_win_either_half_trigger_authority_b7.py",
        "scripts/audit_core_01d_checkpoint_e_completion_v10.py",
        "tests/test_core_01d_win_either_half_trigger_authority_b7.py",
        "tests/test_core_01d_checkpoint_e_completion_v10.py",
        "api/schemas.py",
        "api/v1/__init__.py",
        "api/v1/run_previews.py",
        "services/athena_preview_service.py",
        "tests/test_app_01b_preview_admission.py",
        "api/v1/common.py",
        "api/v1/exports.py",
        "api/v1/fixtures.py",
        "api/v1/runs.py",
        "services/athena_read_service.py",
        "tests/test_app_01c_versioned_read_api.py",
    }
    original_tree = boundary.git("ls-tree", "-r", "HEAD")
    projected = completion_v2.a2_historical_projection(original_tree)
    projected_paths = {line.split(b"\t", 1)[1].strip().decode()
                       for line in projected.splitlines() if b"\t" in line}
    assert added.isdisjoint(projected_paths)
    assert completion_v2.B1_ADDITIVE_EVIDENCE_PATHS.isdisjoint(projected_paths)
    assert ".github/workflows/athena-run.yml" in projected_paths


def test_no_replay_or_mutation_authority_was_exercised(receipt):
    assert all(value == 0 for value in receipt["actions"].values())
    assert receipt["workflow_edit_count"] == receipt["trigger_edit_count"] == 0
    assert receipt["workflow_retirement_count"] == receipt["workflow_deletion_count"] == 0
    assert receipt["checkpoint_e_status"] == receipt["p4_4_status"] == "INCOMPLETE"
    assert receipt["criteria_11_and_14_remain_false"] is True
