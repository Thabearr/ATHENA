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


def test_current_a2_inventory_extends_immutable_generations_eight_and_nine_through_v67():
    chain = boundary.discover_inventory_generations()
    assert [generation for generation, _ in chain] == list(range(1, 72))
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
    v30 = boundary.read_generation(boundary.inventory_generation_path(30))
    assert v30["canonical_sha256"] == "bd4ea91731b2819911051cea90d09cff880194022082e5bb7c3637409cdba4d0"
    assert v30["predecessor_inventory"] == {
        "path": boundary.inventory_generation_path(29),
        "canonical_sha256": "9ef0aa423204ccab1090a7059e821de4cf0e8cf1ad531040ce60c448d140f2a2",
        "generation": 29,
        "rewritten": False,
    }
    v36 = boundary.read_generation(boundary.inventory_generation_path(36))
    assert v36["canonical_sha256"] == "04be46014ba688351f88a5fdb2b58d29455f24de6a1d0ca5a51a24c9763e1224"
    v37 = boundary.read_generation(boundary.inventory_generation_path(37))
    assert v37["canonical_sha256"] == "33ed379bb8941fbfd1672fcb2d69543c5970a17471ccde3de4d85293f822b79e"
    v38 = boundary.read_generation(boundary.inventory_generation_path(38))
    assert v38["canonical_sha256"] == "c0169b031d7451b0182a42416cf84a97687bbda47004b41c5ce5c2f022882e88"
    v40 = boundary.read_generation(boundary.inventory_generation_path(40))
    assert v40["canonical_sha256"] == "64bbe0f42d0874442a39d9e35f77a100d5da17ecbc1538b25c5e4a38405e56bb"
    v41 = boundary.read_generation(boundary.inventory_generation_path(41))
    assert v41["canonical_sha256"] == "13d9db97b050184621ed34427e787272ce222f6263e66d3d232a0a2148b62335"
    v42 = boundary.read_generation(boundary.inventory_generation_path(42))
    assert v42["canonical_sha256"] == "4b7b7cd3dbedc6226c12fb3bca9d957e2b03061d7f7bf75e39a360579c829edc"
    v43 = boundary.read_generation(boundary.inventory_generation_path(43))
    assert v43["canonical_sha256"] == "31e6b8c511028503731e1024b3d4d05ff4be06e683afd67029f1bd04b5d7571c"
    v44 = boundary.read_generation(boundary.inventory_generation_path(44))
    assert v44["canonical_sha256"] == "d810f6c3b43fbb1ecda844236416fa84c8bdfab511e1a6f2752847d34210f41e"
    v45 = boundary.read_generation(boundary.inventory_generation_path(45))
    assert v45["canonical_sha256"] == "242ff9e70f605c0031d3513262bdc2ed7553fee0f071efb33915976478ccb9ba"
    v46 = boundary.read_generation(boundary.inventory_generation_path(46))
    assert v46["canonical_sha256"] == "dd6dd1c658710933ebc5ff50894b5b4cf61091b2b57dc0694b87c9d2a6ded6d3"
    latest = boundary.authenticate_inventory()
    assert latest["generation"] == 71
    assert latest["predecessor_inventory"] == {
        "path": boundary.inventory_generation_path(70),
        "canonical_sha256": "bc12c07f2d840be6abf77f2ec2bea1ffca8b34256b5c293db67dfbbf5b3909a5",
        "generation": 70,
        "rewritten": False,
    }
