from __future__ import annotations

import hashlib
import subprocess
from copy import deepcopy

import pytest

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
from scripts import audit_core_01d_port02c_trigger_authority_b6 as b6


_A2_PREDECESSOR_FILE_SHA256 = {
    1: "eb8e3f78a87836f328620cc1bf34f34c3e68da0c7700fea85eb476ff45793a97",
    2: "611dd630d2ea0223134f742192641988571d83350e30f016f804d6e43d437046",
    3: "bf9bac65b1f7c9d6ab7a60376f26076de634ae6a68d85a28e8aab4c27237e8da",
    4: "7e196ef2717e13adb253308bb3a0fbc2e0dd0545918bcc8ace89e34bed4be3e9",
    5: "750aeaf81d4ee3afc8b7ab13ebe41bb018bb22f5d6058a0532cf33e6eb20a54d",
    6: "4621db16b2f69502f28b5f04435c235c24d053bd36a53abd0c4f42a545f56872",
    7: "dbad92550fc0de2b99e7b4caa54aeecf2ba8855b944c552db854be3e236d0eca",
}


def test_b6_scope_is_exactly_two_port_triggers_and_excludes_win_either_half():
    receipt = b6.validate_receipt()
    assert b6.TARGETS == (
        (".github/workflows/port-02c-native-runtime.yml", "pull_request"),
        (".github/workflows/port-02c-native-runtime.yml", "workflow_dispatch"),
    )
    assert receipt["target_count"] == receipt["resolved_target_count"] == 2
    assert receipt["partial_target_count"] == 0
    assert receipt["global_unknown_before"] == 3
    assert receipt["global_unknown_after"] == 1
    assert {(row["workflow_path"], row["trigger_kind"])
            for row in receipt["remaining_unreviewed_surfaces"]} == {b6.WIN_EITHER_HALF}
    inventory_paths = {row["path"] for row in
                       boundary.read(b6.SOURCE_INVENTORY_PATH)["source_identities"]}
    assert b6.WIN_EITHER_HALF[0] not in inventory_paths


def test_depth_one_pr_checkout_uses_pinned_base_inventory_without_fetch(monkeypatch):
    original_git = b6._git

    def shallow_checkout_git(*args):
        if b6.BASE_MAIN in args:
            raise subprocess.CalledProcessError(128, ["git", *args])
        return original_git(*args)

    b6._base_tree_entries.cache_clear()
    b6._checkout_tree_entries.cache_clear()
    monkeypatch.setattr(b6, "_git", shallow_checkout_git)
    try:
        inventory = b6.build_source_inventory()
    finally:
        b6._base_tree_entries.cache_clear()
        b6._checkout_tree_entries.cache_clear()

    assert inventory["canonical_sha256"] == b6.SOURCE_INVENTORY_SHA
    assert inventory == boundary.read(b6.SOURCE_INVENTORY_PATH)


def test_depth_one_workflow_invariance_uses_pinned_checked_out_subtree(monkeypatch):
    original_git = b6._git

    def shallow_checkout_git(*args):
        if b6.BASE_MAIN in args:
            raise subprocess.CalledProcessError(128, ["git", *args])
        return original_git(*args)

    monkeypatch.setattr(b6, "_git", shallow_checkout_git)
    result = b6._validate_architecture_ledgers()

    assert result["workflow_tree_sha1"] == b6.WORKFLOW_TREE
    assert result["workflow_diff_count"] == 0
    assert result["transition_count"] == 14
    assert result["retired_workflow_count"] == 3


def test_trigger_surfaces_remain_separate_with_exact_current_reachability():
    receipt = b6.validate_receipt()
    rows = {row["identity"]["trigger_kind"]: row for row in receipt["review_rows"]}
    assert set(rows) == {"pull_request", "workflow_dispatch"}
    pr = rows["pull_request"]["trigger_contract"]["reachability"]
    dispatch = rows["workflow_dispatch"]["trigger_contract"]["reachability"]
    assert pr["classification"] == "CONDITIONALLY_REACHABLE_PULL_REQUEST_PATH_FILTERED"
    assert pr["base_branches"] == ["main"]
    assert tuple(pr["path_filters"]) == b6.EXPECTED_PR_PATHS
    assert pr["current"] is True and pr["spent_or_historical"] is False
    assert pr["exact_PR_bound"] is False and pr["retired"] is False
    assert dispatch["classification"] == "MANUALLY_REACHABLE_WORKFLOW_DISPATCH_REF_SELECTABLE"
    assert dispatch["declared_inputs"] == []
    assert dispatch["yaml_branch_filter"] is None
    assert dispatch["historical_non_main_branch_proves_ref_selectability"] == \
        "feat/port-02c-native-installed-runtime-slice"
    assert receipt["workflow_contract"]["same_job_body_reachable_from_both_triggers"] is True
    rows = {row["identity"]["trigger_kind"]: row for row in receipt["review_rows"]}
    assert rows["pull_request"]["manual_control_plane"]["this_surface_is_manual"] is False
    assert rows["pull_request"]["manual_control_plane"][
        "separate_workflow_dispatch_surface_remains_manual_ref_selectable"] is True
    assert rows["workflow_dispatch"]["manual_control_plane"]["this_surface_is_manual"] is True
    assert rows["workflow_dispatch"]["manual_control_plane"][
        "authority_independent_of_historical_rerun_residual"] is True
    assert rows["workflow_dispatch"]["manual_control_plane"][
        "historical_non_main_dispatch"]["branch"] == "feat/port-02c-native-installed-runtime-slice"


def test_concurrency_cancel_in_progress_is_platform_authority_not_explicit_api_cancel():
    receipt = b6.validate_receipt()
    concurrency = receipt["workflow_contract"]["concurrency"]
    assert concurrency["group"] == \
        "port-02c-${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}"
    assert concurrency["cancel_in_progress"] is True
    assert concurrency["authority"] == "YES_PLATFORM_MANAGED_SAME_GROUP_CANCEL_IN_PROGRESS"
    assert concurrency["pull_request_group_key"] == "github.event.pull_request.number"
    assert concurrency["manual_non_pr_group_key"] == "github.ref"
    assert concurrency["explicit_api_cancel_source_path"] is False
    assert receipt["manual_cancel_count"] == 0
    assert receipt["workflow_contract"]["pull_request"]["classification"] != \
        receipt["workflow_contract"]["workflow_dispatch"]["classification"]


def test_toolchain_network_is_separate_from_the_qualification_transport_sentinel():
    receipt = b6.validate_receipt()
    for row in receipt["review_rows"]:
        network = row["network_authority"]
        assert network["workflow_infrastructure_network"] == "YES"
        assert network["build_toolchain_network"] == "YES_PIP_ACTIONS_AND_PACKAGE_INDEX_TRANSPORT"
        assert network["runtime_qualification_outbound_network"] == "DENIED_AND_INSTRUMENTED"
        assert network["current_provider_acquisition"] == "NONE_IN_QUALIFICATION_PATH"
        assert network["historical_provider_evidence_consumption"] == "YES_RETAINED_SOURCE_ONLY"
    assert receipt["runtime_source_contract"]["qualifier_transport_sentinel"] == [
        "socket.connect", "socket.connect_ex", "socket.create_connection", "urllib.request.urlopen"
    ]
    assert receipt["runtime_source_contract"]["nested_retained_replay_guards"] is True


def test_build_git_subprocesses_are_local_read_only_and_checkout_credential_is_not_write_authority():
    receipt = b6.validate_receipt()
    runtime = receipt["runtime_source_contract"]
    assert runtime["build_git_authority"] == "LOCAL_GIT_REPOSITORY_READ_ONLY"
    assert runtime["entire_repo_bundled"] is False
    assert runtime["entire_venv_bundled"] is False
    assert runtime["first_launch_pip_install"] is False
    assert {"ls-files", "status", "rev-parse", "show", "ls-tree"} <= \
        set(runtime["build_git_commands"])
    assert {"cat-file", "hash-object"} <= set(runtime["build_git_commands"])
    for row in receipt["review_rows"]:
        authority = row["permissions_and_credentials"]
        assert authority["permissions"] == {"contents": "read"}
        assert authority["checkout_token_material"] == \
            "PRESENT_BY_DEFAULT_CHECKOUT_CREDENTIAL_BEHAVIOR"
        assert authority["checkout_token_permission"] == "contents:read"
        assert authority["github_repository_write_authority"] == \
            "NO_SOURCE_PATH_AND_TOKEN_CONTENTS_READ_ONLY"


def test_retained_provider_evidence_is_not_new_provider_acquisition():
    receipt = b6.validate_receipt()
    replay_source = (b6.ROOT / "scripts/port_02c_offline_composed_replay.py").read_text()
    assert "require_network_acquisition_performed=True" in replay_source
    for row in receipt["review_rows"]:
        delivery = row["delivery_and_wager"]
        assert row["network_authority"]["historical_provider_evidence_consumption"] == \
            "YES_RETAINED_SOURCE_ONLY"
        assert row["network_authority"]["current_provider_acquisition"] == \
            "NONE_IN_QUALIFICATION_PATH"
        assert delivery["provider_calls"] == 0
        assert delivery["network_attempts"] == 0


def test_delivery_owner_resolution_does_not_claim_share_code_execution():
    receipt = b6.validate_receipt()
    for row in receipt["review_rows"]:
        delivery = row["delivery_and_wager"]
        assert delivery["canonical_component_resolution_includes_delivery_owner"] is True
        assert delivery["canonical_delivery_component_owner"] == "domain.sportybet_share_code"
        assert delivery["share_code_generation_execution"] == \
            "NOT_EXERCISED_AND_NETWORK_GUARDED"
        assert delivery["create_share_code"] is False
        assert delivery["place_wager"] is False
        assert delivery["delivery_calls"] == 0
        assert delivery["wager_authority"] == "NO"
        assert delivery["live_delivery_authority"] == "NO_EXECUTED_DELIVERY"


def test_local_price_router_portfolio_replay_does_not_gain_production_authority():
    receipt = b6.validate_receipt()
    port = boundary.read(b6.PORT_RECEIPT_PATH)
    assert port["qualification"]["production_model_authority"] is False
    assert port["qualification"]["production_probability_authority"] is False
    for row in receipt["review_rows"]:
        replay = row["retained_composition"]
        assert replay["local_offline_business_logic_replay"] == "YES"
        assert replay["price_all_router_portfolio"] == "RETAINED_QUALIFICATION_ONLY_LOCAL_REPLAY"
        assert replay["production_model_authority"] == "NO"
        assert replay["production_probability_authority"] == "NO"
        assert replay["production_selection_authority"] == "NO"
        assert replay["complete_current_history_reconstruction"] is False


def test_filesystem_native_process_artifact_and_external_write_authorities_are_separate():
    receipt = b6.validate_receipt()
    for row in receipt["review_rows"]:
        assert row["local_filesystem_and_process_authority"]["filesystem_write"].startswith("YES_")
        assert row["local_filesystem_and_process_authority"]["native_subprocess"] == "YES"
        writes = row["write_authority"]
        assert writes["github_actions_artifact_write_authority"] == "YES_RUN_SCOPED"
        assert writes["github_repository_write_authority"] == \
            "NO_SOURCE_PATH_AND_TOKEN_CONTENTS_READ_ONLY"
        assert writes["external_storage_write_authority"] == "NO_SOURCE_PATH"
        assert writes["release_publish_authority"] == "NO_SOURCE_PATH"
    contract = receipt["workflow_contract"]
    assert contract["actions_artifact"] == {
        "name": "port02c-${{ matrix.os }}-evidence",
        "retention_days": 14,
        "authority": "YES_RUN_SCOPED",
    }


def test_historical_windows_host_and_local_windows_11_evidence_are_not_conflated():
    receipt = b6.validate_receipt()
    history = receipt["historical_actions_metadata"]
    assert history["id"] == 36792107722
    assert history["event"] == "workflow_dispatch"
    assert history["head_branch"] == "feat/port-02c-native-installed-runtime-slice"
    assert history["status"] == "completed"
    assert history["conclusion"] == "success"
    assert history["jobs"] == {"native slice (windows)": "success", "native slice (linux)": "success"}
    assert history["rerun_residual"] == "HISTORICAL_ACTIONS_RERUN_RESIDUAL_NOT_PROVEN_ABSENT"
    assert history["artifact_payloads_downloaded"] is False
    port = boundary.read(b6.PORT_RECEIPT_PATH)
    windows = port["cross_platform_parity"]["hosted_windows_packaging_regression"]
    platforms = {row["platform"]: row for row in port["platforms"]}
    assert windows["windows_11_proof"] is False
    assert platforms["windows"]["evidence_source"] == "LOCAL_WINDOWS_11_NATIVE"
    assert platforms["linux"]["evidence_source"] == "GITHUB_ACTIONS_UBUNTU_24_04_NATIVE"


def test_current_product_release_support_and_no_caller_or_retirement_are_preserved():
    receipt = b6.validate_receipt()
    scan = receipt["repository_caller_scan"]
    assert receipt["repository_caller_scan"]["result"] == \
        "NO_CURRENT_REPOSITORY_CALLER_FOUND_SOURCE_SCAN"
    assert set(scan["search_dimensions"]) == {
        "workflow_call", "workflow_run", "GitHub workflow dispatch API",
        "gh workflow run", "subprocess dispatch wrappers", "issue_comment bridges",
    }
    for row in receipt["review_rows"]:
        product = row["product_release_disposition"]
        assert product["release_qualification_capability"] == \
            "CURRENT_RETAINED_SUPPORTED_ENGINEERING_GATE"
        assert product["end_user_runtime_execution"] == "NOT_THIS_WORKFLOW"
        assert product["physical_trigger_runtime_authority"] == \
            "CURRENT_CONDITIONAL_OR_MANUAL_CI_QUALIFICATION"
        assert product["retirement_authorized"] is False


def test_a2_generation_v8_is_immutable_prefix_and_b6_python_remains_in_latest_inventory():
    chain = boundary.load_inventory_generations()
    assert [path for path, _ in chain] == [boundary.inventory_generation_path(i) for i in range(1, 17)]
    for generation in range(1, 8):
        path = boundary.inventory_generation_path(generation)
        current_bytes = (b6.ROOT / path).read_bytes()
        assert hashlib.sha256(current_bytes).hexdigest() == \
            _A2_PREDECESSOR_FILE_SHA256[generation]
    for path, digest in boundary.PREDECESSORS.items():
        assert boundary.read(path)["canonical_sha256"] == digest
    v8 = boundary.read(boundary.inventory_generation_path(8))
    assert v8["generation"] == 8
    assert v8["canonical_sha256"] == "856129ba6eafb0281f10a16639f26fd477b2ba6a2fb00957ee79fa539539412d"
    assert v8["predecessor_inventory"] == {
        "path": b6.A2_V7_PATH,
        "canonical_sha256": b6.A2_V7_SHA,
        "generation": 7,
        "rewritten": False,
    }
    latest = boundary.authenticate_inventory()
    assert latest["generation"] == 16
    assert latest["predecessor_inventory"] == {
        "path": boundary.inventory_generation_path(15),
        "canonical_sha256": "25a5edf0aac9b67b3527e14e36d428cb975263d112a5f8f0d839ab7f833ad0d4",
        "generation": 15,
        "rewritten": False,
    }
    paths = {row["path"] for row in latest["source_identities"]}
    assert {
        "scripts/audit_core_01d_port02c_trigger_authority_b6.py",
        "scripts/audit_core_01d_checkpoint_e_completion_v9.py",
        "tests/test_core_01d_port02c_trigger_authority_b6.py",
        "tests/test_core_01d_checkpoint_e_completion_v9.py",
        "scripts/audit_checkpoint_e_workflows.py",
    } <= paths


def test_workflow_tree_evolution_retirement_and_live_action_invariants_are_zero():
    receipt = b6.validate_receipt()
    invariant = receipt["workflow_evolution_and_retirement_invariants"]
    assert invariant["workflow_tree_sha1"] == "9b08653f1a12bb1b3d964fbd910396ff955740da"
    assert invariant["workflow_diff_count"] == 0
    assert invariant["evolution_ledger_sha256"] == \
        "73e1eb3fe6593558c821600dd0f103353d45c15a139ab470a996c7cbb35da531"
    assert invariant["transition_count"] == 14
    assert invariant["retirement_ledger_sha256"] == \
        "afa4a082f5225d83ca1ab32aab396b02bedf6f43dc57b6467a4187a720a0d56a"
    assert invariant["retired_workflow_count"] == 3
    assert invariant["workflow_retirement_or_deletion_count"] == 0
    assert receipt["actions"] == b6.ZERO_ACTIONS
    assert receipt["manual_cancel_count"] == 0


@pytest.mark.parametrize("mutate", [
    lambda value: value["target_keys"].append(list(b6.WIN_EITHER_HALF)),
    lambda value: value["review_rows"][1]["identity"].update(trigger_kind="pull_request"),
    lambda value: value["review_rows"][0]["trigger_contract"]["reachability"].update(path_filters=[]),
    lambda value: value["review_rows"][1]["trigger_contract"]["reachability"].update(declared_inputs=["ref"]),
    lambda value: value["workflow_contract"]["concurrency"].update(cancel_in_progress=False),
    lambda value: value["review_rows"][0]["network_authority"].update(build_toolchain_network="NO_NETWORK"),
    lambda value: value["review_rows"][0]["network_authority"].update(current_provider_acquisition="YES"),
    lambda value: value["review_rows"][0]["delivery_and_wager"].update(delivery_calls=1),
    lambda value: value["review_rows"][0]["write_authority"].update(github_actions_artifact_write_authority="NO"),
    lambda value: value["review_rows"][0]["retained_composition"].update(production_probability_authority="YES"),
    lambda value: value["actions"].update(artifact_payload_downloads=1),
])
def test_resealed_scope_or_authority_falsehoods_fail_closed(mutate):
    value = deepcopy(boundary.read(b6.RECEIPT_PATH))
    mutate(value)
    boundary.seal(value)
    with pytest.raises(AssertionError):
        b6.validate_receipt(value)
