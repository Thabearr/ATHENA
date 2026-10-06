from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess

import pytest

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
from scripts import audit_core_01d_owner_one_shot_issue_comment_authority_b3 as b3


EXPECTED_KEYS = {
    (".github/workflows/execute-fotmob-ordinary-ft-source-history-campaign.yml", "issue_comment"),
    (".github/workflows/execute-fotmob-utc-native-expected-goals-model-validation.yml", "issue_comment"),
    (".github/workflows/execute-fotmob-utc-native-successor-feature-qualification-v2.yml", "issue_comment"),
    (".github/workflows/execute-pr69-primary-time-basis-evidence-campaign-v2.yml", "issue_comment"),
}


def row_by_pr(receipt, pr):
    return next(row for row in receipt["review_rows"] if row["current_control_state"]["control_pr_number"] == pr)


def test_source_identity_tolerates_checkout_eol_conversion_without_weakening_git_blob_pin(monkeypatch):
    target = next(iter(b3.SOURCE_PINS))
    original = Path.read_bytes

    def crlf_view(path):
        raw = original(path)
        if Path(path) == b3.ROOT / target:
            return raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        return raw

    monkeypatch.setattr(Path, "read_bytes", crlf_view)
    observed = b3.source_identity(target)
    expected_blob, expected_sha = b3.SOURCE_PINS[target]
    assert observed == {
        "path": target,
        "git_blob_sha1": expected_blob,
        "normalized_source_sha256": expected_sha,
    }


def test_b3_scope_is_exactly_four_issue_comment_surfaces():
    receipt = boundary.read(b3.RECEIPT_PATH)
    keys = {(row["identity"]["workflow_path"], row["identity"]["trigger_kind"])
            for row in receipt["review_rows"]}
    assert keys == EXPECTED_KEYS
    assert receipt["target_surface_count"] == 4
    assert receipt["resolved_target_count"] == 4
    assert receipt["partial_target_count"] == 0


def test_source_inventory_binds_only_target_workflow_sources_and_reviewed_callees():
    inventory = boundary.read(b3.SOURCE_INVENTORY_PATH)
    assert inventory["base_main_sha"] == b3.BASE_MAIN
    assert inventory["base_tree_sha"] == b3.BASE_TREE
    assert inventory["target_surface_count"] == 4
    assert len(inventory["source_identities"]) == len(b3.SOURCE_PINS)
    surfaces = {row["surface_key"]: row for row in inventory["target_surfaces"]}
    assert set(surfaces) == {path + "#" + event for path, event in EXPECTED_KEYS}
    for key, row in surfaces.items():
        assert row["trigger_contract"]["event"] == "issue_comment"
        assert row["trigger_contract"]["types"] == ["created"]
        assert row["trigger_contract"]["owner_login"] == "Thabearr"
        assert row["trigger_contract"]["exact_body_framing"] == "THREE_NONEMPTY_TRIMMED_LINES_COMMAND_MAIN_SHA_CONFIRM"
        assert row["trigger_contract"]["live_control_pr_conversation_locked"] is False
        assert row["source_identity"]["git_blob_sha1"] == b3.SOURCE_PINS[row["source_identity"]["path"]][0]
        assert row["trigger_contract"]["job_steps"]
        assert row["out_of_scope_sibling_trigger_review"] == "NOT_RECLASSIFIED_BY_B3"


def test_merged_control_prs_remain_physically_reachable_and_attempt_markers_are_present():
    receipt = boundary.read(b3.RECEIPT_PATH)
    for row in receipt["review_rows"]:
        state = row["current_control_state"]
        assert state["control_pr"]["state"] == "closed"
        assert state["control_pr"]["merged"] is True
        assert state["control_pr_issue_state"] == "closed"
        assert state["control_pr_conversation_locked"] is False
        assert row["reachability"]["declared_event_surface_reachability"] == "PHYSICALLY_REACHABLE_OWNER_COMMENT_EVENT"
        assert state["marker_currently_present"] is True
        assert state["attempt_marker_comment"]["author_login"] == "github-actions[bot]"
        assert state["attempt_marker_comment"]["created_at"] == state["attempt_marker_comment"]["updated_at"]
        assert state["control_comment_mutation_residual"] == "CONTROL_COMMENT_MUTATION_RESIDUAL_NOT_PROVEN_IMPOSSIBLE"
        assert row["reachability"]["historical_actions_rerun_residual"] == "HISTORICAL_ACTIONS_RERUN_RESIDUAL_NOT_PROVEN_ABSENT"


def test_historical_capability_is_preserved_and_separated_from_current_marker_block():
    receipt = boundary.read(b3.RECEIPT_PATH)
    ordinary = row_by_pr(receipt, 103)
    feature = row_by_pr(receipt, 139)
    model = row_by_pr(receipt, 145)
    pr69 = row_by_pr(receipt, 130)
    assert ordinary["historical_guarded_capability"]["provider_acquisition"] == "FOTMOB_DATA_MATCHES_LIVE_SOURCE_CAPTURE_4410_SLOTS"
    assert feature["historical_guarded_capability"]["provider_acquisition"] == "NONE_NO_PROVIDER_NETWORK"
    assert feature["historical_guarded_capability"]["github_actions_artifact_payload_read"] == "EXACT_PR119_ARTIFACT_PAYLOAD_READ"
    assert model["historical_guarded_capability"]["model_or_research_execution"] == "SOURCE_BOUND_RESEARCH_MODEL_VALIDATION_AND_TRAINING"
    assert pr69["historical_guarded_capability"]["public_historical_source_acquisition"] == "FOOTBALL_DATA_CO_UK_EIGHT_SLOT_LIVE_CAPTURE"
    for row in receipt["review_rows"]:
        assert row["reachability"]["current_guarded_high_risk_execution_reachability"].startswith("BLOCKED_BY_")
        assert row["reachability"]["artifact_availability_used_as_primary_guard"] is False
        assert row["historical_guarded_capability"]["production_authority"].startswith("NONE")
        assert row["historical_guarded_capability"]["wager_stake_wallet"] == "NONE"
        assert row["historical_guarded_capability"]["external_storage_write"] == "NONE"


def test_guard_order_preserves_pr130_pre_marker_metadata_read():
    receipt = boundary.read(b3.RECEIPT_PATH)
    for pr in (103, 139, 145):
        row = row_by_pr(receipt, pr)
        ops = [entry["operation"] for entry in row["guard_order"]]
        marker_index = next(i for i, operation in enumerate(ops)
                            if "marker" in operation and "read" in operation and "checked" in operation)
        assert marker_index < ops.index("exact main checkout")
        if pr == 139:
            assert ops.index("exact main checkout") < ops.index("source artifact metadata read") < ops.index("exact artifact payload download")
        if pr == 145:
            assert ops.index("exact main checkout") < ops.index("historical source artifact metadata read") < ops.index("exact source artifact payload download") < ops.index("research model-validation/training boundary")
        assert row["dynamic_reachability"]["marker_check_precedes_high_risk_execution_boundary"] is True
    row = row_by_pr(receipt, 130)
    ops = [entry["operation"] for entry in row["guard_order"]]
    assert ops.index("prior V1 Actions artifact metadata read before current marker") < ops.index("current V2 marker comments read and checked")
    assert row["dynamic_reachability"]["PR130_artifact_metadata_read_precedes_marker_check"] is True
    assert row["current_observed_control_state_authority"]["github_actions_artifact_metadata_read"] == "PRIOR_ARTIFACT_GET_BY_ID_9266604353_BEFORE_MARKER"
    observation = boundary.read(b3.SOURCE_INVENTORY_PATH)["github_read_only_metadata"]["current_pr130_prior_artifact_metadata_observation"]
    assert observation["metadata_get_state"] == "CURRENT_ACTIONS_ARTIFACT_METADATA_GET_404_NOT_FOUND"
    assert observation["run_listing_total_count"] == 0
    assert observation["payload_downloaded"] is False
    assert observation["used_as_primary_replay_guard"] is False


def test_historical_run_comment_linkage_and_marker_search_are_exact():
    inventory = boundary.read(b3.SOURCE_INVENTORY_PATH)
    metadata = inventory["github_read_only_metadata"]
    assert {row["control_pr_number"]: row["count"] for row in metadata["attempt_marker_prefix_searches"]} == {
        103: 1, 139: 1, 145: 1, 130: 1,
    }
    for row in boundary.read(b3.RECEIPT_PATH)["review_rows"]:
        target = next(item for item in b3.TARGETS.values() if item["pr"] == row["current_control_state"]["control_pr_number"])
        assert row["current_control_state"]["historical_run"]["run_id"] == target["run_id"]
        assert row["current_control_state"]["historical_run"]["conclusion"] == "success"
        assert row["current_control_state"]["historical_run"]["head_sha"] == target["run_head"]
        assert target["marker_prefix"] in row["current_control_state"]["attempt_marker_comment"]["body"]


def test_b3_receipt_canonical_and_zero_live_action_attestation():
    receipt = boundary.read(b3.RECEIPT_PATH)
    assert (b3.ROOT / b3.RECEIPT_PATH).read_bytes() == boundary.canonical(receipt)
    assert receipt["actions"] == b3.ZERO_ACTIONS
    assert receipt["workflow_edit_count"] == receipt["trigger_edit_count"] == 0
    assert receipt["workflow_retirement_count"] == receipt["workflow_deletion_count"] == 0
    assert receipt["caller_migration_count"] == 0
    assert receipt["workflow_tree_before_sha1"] == receipt["workflow_tree_after_sha1"] == b3.WORKFLOW_TREE
    assert receipt["evolution_ledger_before_sha256"] == receipt["evolution_ledger_after_sha256"] == b3.EVOLUTION_SHA
    assert receipt["evolution_transition_count_before"] == receipt["evolution_transition_count_after"] == 14
    assert receipt["retirement_ledger_sha256_before"] == receipt["retirement_ledger_sha256_after"] == b3.RETIREMENT_SHA


def test_mutations_to_scope_current_reachability_or_pr130_guard_order_are_rejected():
    receipt = boundary.read(b3.RECEIPT_PATH)
    mutant = deepcopy(receipt)
    mutant["review_rows"][0]["reachability"]["declared_event_surface_reachability"] = "UNREACHABLE_BECAUSE_CONTROL_PR_MERGED"
    with pytest.raises(AssertionError):
        b3.validate_receipt(mutant, expected=receipt, raw=boundary.canonical(mutant))

    mutant = deepcopy(receipt)
    pr130 = next(row for row in mutant["review_rows"] if row["identity"]["workflow_path"].endswith("pr69-primary-time-basis-evidence-campaign-v2.yml"))
    pr130["dynamic_reachability"]["PR130_artifact_metadata_read_precedes_marker_check"] = False
    with pytest.raises(AssertionError):
        b3.validate_receipt(mutant, expected=receipt, raw=boundary.canonical(mutant))


def test_workflow_tree_is_unchanged_and_the_a2_generation_chain_is_contiguous():
    chain = boundary.load_inventory_generations()
    assert [i for i, _ in enumerate(chain, 1)] == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22]
    v10 = boundary.read_generation(boundary.inventory_generation_path(10))
    assert v10["canonical_sha256"] == "9b5ca4fc23fee7f5100f3ad9d9dafce4bd1fc580c77d546ff285284a2507f475"
    latest = chain[-1][1]
    assert latest["generation"] == 22
    assert latest["predecessor_inventory"]["generation"] == 21
    assert latest["predecessor_inventory"]["path"] == boundary.inventory_generation_path(21)
    assert latest["predecessor_inventory"]["canonical_sha256"] == "d45fc6b1c747af4860ac877c0b60af5f8ca27479a2bb138b5b21f77dd1434ee2"
    assert latest["predecessor_inventory"]["rewritten"] is False
    assert boundary.authenticate_inventory() == latest
    assert subprocess.check_output(["git", "rev-parse", "HEAD:.github/workflows"], cwd=b3.ROOT).decode().strip() == b3.WORKFLOW_TREE
    assert subprocess.run(["git", "diff", "--quiet", "HEAD", "--", ".github/workflows"], cwd=b3.ROOT).returncode == 0
