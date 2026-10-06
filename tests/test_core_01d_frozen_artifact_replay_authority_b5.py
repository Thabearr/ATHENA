from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
from scripts import audit_core_01d_frozen_artifact_replay_authority_b5 as b5


def test_b5_source_identity_tolerates_checkout_eol_conversion(monkeypatch):
    target = b5.TARGETS[0][0]
    original = Path.read_bytes

    def crlf_view(path):
        raw = original(path)
        if Path(path) == b5.ROOT / target:
            return raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        return raw

    monkeypatch.setattr(Path, "read_bytes", crlf_view)
    observed = b5._identity(target)
    expected_blob, expected_sha = b5.SOURCE_PINS[target]
    assert observed["git_blob_sha1"] == expected_blob
    assert observed["normalized_source_sha256"] == expected_sha


def test_exact_four_b5_surfaces_and_immutable_completion_v7_binding():
    assert len(b5.TARGETS) == 4
    assert len(set(b5.TARGETS)) == 4
    parent = boundary.read(b5.COMPLETION_V7_PATH)
    inherited = {(row["workflow_path"], row["trigger_kind"])
                 for row in parent["unreviewed_authority_surfaces"]}
    assert set(b5.TARGETS) <= inherited
    assert parent["canonical_sha256"] == b5.COMPLETION_V7_SHA
    assert (".github/workflows/verify-saturday-2026-08-22-reviewed-fixture-catalog.yml",
            "pull_request") not in set(b5.TARGETS)


def test_b5_receipt_resolves_only_targets_and_preserves_replay_limits():
    receipt = b5.validate_receipt()
    assert receipt["scope"] == {
        "inherited_unresolved_surface_count": 7,
        "target_surface_count": 4,
        "resolved_target_count": 4,
        "partial_target_count": 0,
        "global_unresolved_before": 7,
        "global_unresolved_after": 3,
        "target_keys": [[path, trigger] for path, trigger in b5.TARGETS],
    }
    by_pr = {row["event_contract"].get("control_pr"): row for row in receipt["review_rows"]}
    assert by_pr[193]["historical_guarded_capability"]["semantic_admission"] == "EXACT_OBSERVATION_ARRAY_ONLY"
    assert by_pr[193]["historical_guarded_capability"]["team_strength_feature_authority"] == "FALSE"
    assert by_pr[194]["historical_guarded_capability"]["team_strength_candidate_authority"] == \
        "CANDIDATE_MAPPING_ONLY_FEATURE_AUTHORITY_FALSE"
    assert by_pr[194]["historical_guarded_capability"]["team_strength_feature_authority"] == "FALSE"
    assert by_pr[197]["historical_guarded_capability"]["team_strength_feature_authority"] == \
        "YES_ONLY_IN_EXISTING_PR191_WRAPPER_AT_EXACT_FRESHNESS_INSTANT"
    for row in receipt["review_rows"][:3]:
        assert row["current_observed_control_state_authority"]["declared_event_surface"].startswith(
            "PHYSICALLY_REACHABLE_PULL_REQUEST")
        assert row["residuals"]["historical_source_artifact_absence"] == \
            "HISTORICAL_SOURCE_ARTIFACT_CURRENTLY_ABSENT_NOT_PROVEN_PERMANENT"
        assert row["residuals"]["historical_actions_rerun_residual"] == \
            "HISTORICAL_ACTIONS_RERUN_RESIDUAL_NOT_PROVEN_ABSENT"
        assert row["historical_guarded_capability"]["provider_acquisition"] == "NONE"


def test_catalog_current_and_historical_runs_are_distinguished():
    receipt = b5.validate_receipt()
    row = receipt["review_rows"][3]
    current = row["current_control_state"]["ordinary_main_push_run"]
    historical = row["current_control_state"]["exact_merge_historical_run"]
    assert current["run_id"] == 37176160133
    assert current["steps"]["Stop unrelated main pushes cleanly"] == "success"
    assert current["steps"]["Download exact PR199 source artifact for merged replay"] == "skipped"
    assert historical["run_id"] == 32467715248
    assert historical["steps"]["Require separate exact-byte admission review"] == "failure"
    assert historical["steps"]["Store source-replayed exact catalog admission"] == "skipped"
    approval = row["current_control_state"]["post_failure_approval_comment"]
    assert approval["id"] == 5368504537
    assert row["current_control_state"]["later_exact_merge_store_execution"].startswith("NOT_OBSERVED")
    assert row["residuals"]["exact_merge_sha_repush"] == \
        "EXACT_HISTORICAL_MERGE_SHA_REPUSH_RESIDUAL_NOT_PROVEN_IMPOSSIBLE"
    assert row["residuals"]["historical_actions_rerun"] == \
        "HISTORICAL_ACTIONS_RERUN_RESIDUAL_NOT_PROVEN_ABSENT"
    assert row["dynamic_reachability"]["local_runner_writes"]
    assert row["dynamic_reachability"]["github_branch_write"] == "NONE"


def test_live_action_sentinels_remain_zero_and_completion_stays_incomplete():
    receipt = b5.validate_receipt()
    assert all(value == 0 for value in receipt["actions"].values())
    assert receipt["criterion_11"] is False
    assert receipt["criterion_14"] is False
    assert receipt["checkpoint_e_status"] == "INCOMPLETE"
    assert receipt["p4_4_status"] == "INCOMPLETE"
    assert receipt["source_review_counter_while_open"] == "4/5"
    assert receipt["source_review_counter_if_owner_merges"] == "5/5"
    assert receipt["mandatory_governing_source_reread_after_b5_merge"] is True
    assert receipt["do_not_start_b6_before_reread"] is True


@pytest.mark.parametrize("changed", [
    lambda value: value["review_rows"][0]["historical_guarded_capability"].update(provider_acquisition="FOTMOB_ACQUISITION"),
    lambda value: value["review_rows"][2]["historical_guarded_capability"].update(team_strength_feature_authority="FALSE"),
    lambda value: value["review_rows"][3]["current_control_state"].update(later_exact_merge_store_execution="PROVEN"),
    lambda value: value["review_rows"][3]["dynamic_reachability"].update(github_branch_write="YES"),
    lambda value: value["review_rows"].pop(),
])
def test_receipt_mutations_fail_closed(changed):
    value = deepcopy(boundary.read(b5.RECEIPT_PATH))
    changed(value)
    with pytest.raises(AssertionError):
        b5.validate_receipt(value)


def test_current_a2_inventory_extends_immutable_generations_eight_and_nine_with_v18():
    chain = boundary.discover_inventory_generations()
    assert [generation for generation, _ in chain] == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18]
    v8 = boundary.read(boundary.inventory_generation_path(8))
    assert v8["generation"] == 8
    assert v8["canonical_sha256"] == "856129ba6eafb0281f10a16639f26fd477b2ba6a2fb00957ee79fa539539412d"
    assert v8["predecessor_inventory"] == {
        "path": b5.A2_V7_PATH,
        "canonical_sha256": "fdb9534212e814f6ac5a8a5c6f52af73354eef0029e3dbb5466dc32d6f252794",
        "generation": 7,
        "rewritten": False,
    }
    v10 = boundary.read_generation(boundary.inventory_generation_path(10))
    assert v10["canonical_sha256"] == "9b5ca4fc23fee7f5100f3ad9d9dafce4bd1fc580c77d546ff285284a2507f475"
    latest = boundary.authenticate_inventory()
    assert latest["generation"] == 18
    assert latest["predecessor_inventory"] == {
        "path": boundary.inventory_generation_path(17),
        "canonical_sha256": "f1007c2ac4e149298027c010569ba1b802c1b71cd59f5bdbd4956f1483ee9c68",
        "generation": 17,
        "rewritten": False,
    }
