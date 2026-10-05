"""Offline assertions for B2 source, GitHub metadata, and trigger authority."""
from copy import deepcopy
from pathlib import Path

import pytest

from scripts import audit_core_01d_ci_offline_transport_boundary as boundary
from scripts import audit_core_01d_historical_warehouse_transfer_authority_b2 as b2
from scripts import audit_core_01d_checkpoint_e_completion_v2 as completion_v2


@pytest.fixture(scope="module")
def receipt():
    assert b2.audit()["result"] == "PASS"
    return boundary.read(b2.RECEIPT_PATH)


def _rows(receipt):
    return {(row["workflow_path"], row["trigger_kind"]): row for row in receipt["review_rows"]}


def test_b2_source_identity_tolerates_checkout_eol_conversion(monkeypatch):
    target = next(iter(b2.SOURCE_PINS))
    original = Path.read_bytes

    def crlf_view(path):
        raw = original(path)
        if Path(path) == b2.ROOT / target:
            return raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        return raw

    monkeypatch.setattr(Path, "read_bytes", crlf_view)
    observed = b2.source_identity(target)
    expected_blob, expected_sha = b2.SOURCE_PINS[target]
    assert observed == {
        "path": target,
        "git_blob_sha1": expected_blob,
        "normalized_source_sha256": expected_sha,
    }


def test_exact_five_trigger_surfaces_and_current_unknown_set(receipt):
    assert b2.TARGET_KEYS == (
        (b2.WAREHOUSE, "pull_request"),
        (b2.WAREHOUSE, "push"),
        (b2.WAREHOUSE, "workflow_dispatch"),
        (b2.TRANSFER, "push"),
        (b2.TRANSFER, "workflow_dispatch"),
    )
    rows = _rows(receipt)
    assert set(rows) == set(b2.TARGET_KEYS)
    assert all(row["review"]["status"] == "RESOLVED" for row in rows.values())
    assert receipt["scope"]["target_surface_count"] == 5
    assert receipt["scope"]["global_unknown_before"] == 25
    assert receipt["scope"]["global_unknown_after"] == 20
    assert len(receipt["scope"]["remaining_unknown_keys"]) == 20


def test_warehouse_three_events_remain_distinct_and_live(receipt):
    rows = _rows(receipt)
    pr = rows[(b2.WAREHOUSE, "pull_request")]
    push = rows[(b2.WAREHOUSE, "push")]
    dispatch = rows[(b2.WAREHOUSE, "workflow_dispatch")]
    assert pr["current_reachability"]["status"] == "CONDITIONALLY_REACHABLE"
    assert "PULL_REQUEST_TARGETS_MAIN" in pr["current_reachability"]["event_condition"]
    assert push["current_reachability"]["status"] == "CONDITIONALLY_REACHABLE"
    assert "PUSH_TO_MAIN" in push["current_reachability"]["event_condition"]
    assert dispatch["current_reachability"]["status"] == "MANUALLY_REACHABLE"
    for row in (pr, push, dispatch):
        auth = row["current_declared_trigger_authority"]
        assert auth["historical_data_acquisition_authority"] == "PUBLIC_HISTORICAL_DATASET_HTTP_READ_AND_LOCAL_IMPORT"
        assert auth["current_provider_acquisition_authority"].startswith("NONE_NO_DIRECT_FOTMOB")
        assert auth["sportsbook_read_authority"] == auth["share_code_authority"] == auth["wager_authority"] == "NONE"
        assert auth["persistent_canonical_database_write_authority"].startswith("NONE;")
        assert auth["github_artifact_write_authority"].startswith("RUN_SCOPED_HISTORICAL_SQLITE")
        assert row["permissions_and_credentials"]["workflow"] == {"contents": "read"}
        assert row["retained_product_disposition"] == "CURRENT_HISTORICAL_DATASET_PRODUCER; NO_RETAINED_NONEXECUTABLE_CLASSIFICATION"


def test_warehouse_path_inputs_concurrency_and_public_sources_are_pinned(receipt):
    inv = boundary.read(b2.SOURCE_INVENTORY_PATH)
    contracts = inv["trigger_contracts"]
    dispatch = contracts[b2.WAREHOUSE + "#workflow_dispatch"]["trigger_declaration"]["inputs"]
    assert dispatch["include_statsbomb"]["default"] == "true"
    assert dispatch["include_statsbomb"]["type"] == "boolean"
    assert dispatch["start_year"]["default"] == "1993"
    assert dispatch["end_year"]["default"] == "2026"
    for event in ("pull_request", "push"):
        trigger = contracts[b2.WAREHOUSE + "#" + event]["trigger_declaration"]
        assert trigger["branches"] == ["main"]
        assert ".github/workflows/build-historical-warehouse.yml" in trigger["paths"]
        assert len(trigger["paths"]) > 10
    concurrency = contracts[b2.WAREHOUSE + "#push"]["workflow_concurrency"]
    assert concurrency["cancel-in-progress"] == "true"
    sources = {row["source_file"]: row for row in inv["public_data_sources"]}
    assert "https://huggingface.co/datasets/eatpizzanot/soccer-dataset/resolve/main" in sources["scripts/import_current_soccer_datalake.py"]["endpoint"]
    assert any(row["source_file"] == "scripts/enrich_statsbomb_history.py" for row in inv["public_data_sources"])
    assert all("fotmob" not in repr(row).lower() and "sportybet" not in repr(row).lower()
               for row in inv["public_data_sources"])
    assert receipt["review_rows"][0]["current_declared_trigger_authority"]["network_authority_summary"].startswith("PUBLIC_HUGGINGFACE")


def test_warehouse_local_database_and_actions_artifacts_are_not_canonical_store(receipt):
    row = _rows(receipt)[(b2.WAREHOUSE, "push")]
    authority = row["current_declared_trigger_authority"]
    assert authority["local_runner_database_write_authority"] == "LOCAL_RUNNER_DATABASE_ATHENA_HISTORY_DB_SQLITE_AND_LOCAL_EXPORTS"
    assert authority["persistent_canonical_database_write_authority"] == (
        "NONE; RUNNER_LOCAL_SQLITE_IS_PUBLISHED_ONLY_AS_ACTIONS_ARTIFACT")
    assert authority["github_artifact_write_authority"].endswith("RETENTION_30_DAYS")
    assert authority["github_branch_write_authority"] == "NONE_CONTENTS_READ_ONLY"


def test_transfer_both_triggers_are_physically_reachable_with_early_pointer_write(receipt):
    rows = _rows(receipt)
    for event in ("push", "workflow_dispatch"):
        row = rows[(b2.TRANSFER, event)]
        assert row["review"]["status"] == "RESOLVED"
        assert row["retained_product_disposition"].startswith("RETAINED_NONEXECUTABLE_HISTORICAL_TRANSFER")
        assert row["current_reachability"]["status"] in {"CONDITIONALLY_REACHABLE", "MANUALLY_REACHABLE"}
        assert row["current_declared_trigger_authority"]["github_branch_write_authority"].startswith("FORCE_PUSH_ONLY_FIXED_BRANCH")
        assert row["dynamic_reachability"]["pointer_branch_write_precedes_validation"] is True
        assert row["dynamic_reachability"]["source_run_id_cross_validation"] == "NONE_SOURCE_RUN_ID_IS_POINTER_METADATA_ONLY"
        assert row["current_declared_trigger_authority"]["external_storage_write_authority"] == "NONE_NO_DRIVE_API_OR_EXTERNAL_STORAGE_CALL"
        assert row["current_declared_trigger_authority"]["github_artifact_write_authority"].startswith("RUN_SCOPED_MANIFEST_AND_23_PART")
    push = rows[(b2.TRANSFER, "push")]
    assert push["trigger_contract"]["path_filter"] == [b2.TRANSFER]
    manual = rows[(b2.TRANSFER, "workflow_dispatch")]
    assert manual["trigger_contract"]["inputs"]["source_run_id"]["default"] == "32628985683"
    assert manual["trigger_contract"]["inputs"]["source_artifact_id"]["default"] == "9491418446"


def test_transfer_archive_identity_order_and_current_empty_listings_are_preserved(receipt):
    assert receipt["canonical_archive_contract"] == {
        "name": "athena-history-canonical.zip", "bytes": 2149256220,
        "sha256": "a783886d0906e357e26851fcb3eb182bb06bdcc184d21f2b6578bb3d1fa61511",
        "source_run_id_default": "32628985683", "source_artifact_id_default": "9491418446",
        "part_count": 23, "pointer_branch": "automation/canonical-drive-transfer-pointer",
    }
    inventory = boundary.read(b2.SOURCE_INVENTORY_PATH)
    assert receipt["source_inventory"]["canonical_sha256"] == inventory["canonical_sha256"]
    order = inventory["trigger_contracts"][b2.TRANSFER + "#workflow_dispatch"]["steps"]
    names = [row["name"] for row in order]
    assert names.index("Publish run pointer") < names.index("Download canonical artifact archive exactly as stored by GitHub")
    assert names.index("Download canonical artifact archive exactly as stored by GitHub") < names.index("Upload transfer manifest")
    assert names.index("Upload canonical part 000") < names.index("Mark run pointer completed")
    listing = receipt["current_actions_artifact_listings"]
    assert len(listing["records"]) == 4
    assert all(row["state"] == "CURRENT_ACTIONS_ARTIFACT_LISTING_EMPTY" and row["total_count"] == 0
               and row["payload_downloaded"] is False and row["disappearance_cause_inferred"] is False
               for row in listing["records"])


def test_historical_success_is_distinct_from_empty_current_artifact_listing(receipt):
    runs = {row["run_id"]: row for row in receipt["historical_github_run_metadata"]["runs"]}
    transfer = runs[32635585415]
    assert transfer["workflow_path"] == b2.TRANSFER
    assert transfer["event"] == "push" and transfer["head_sha"] == "d2145f0e5ba74fb516797768f5d8a8681a3c3ffa"
    assert transfer["status"] == "completed" and transfer["conclusion"] == "success"
    source = runs[32628985683]
    assert source["workflow_path"] == b2.WAREHOUSE and source["conclusion"] == "success"
    assert receipt["current_actions_artifact_listings"]["empty_listing_does_not_infer_disappearance_cause"] is True


def test_no_repository_caller_does_not_erase_manual_github_authority(receipt):
    discovery = boundary.read(b2.SOURCE_INVENTORY_PATH)["repository_caller_discovery"]
    assert discovery["current_repository_callers"] == []
    assert discovery["result"] == "NO_CURRENT_REPOSITORY_CALLER_FOUND_SOURCE_SCAN"
    assert discovery["external_or_manual_github_dispatch_authority"] == "NOT_NEGATED_BY_ABSENCE_OF_REPOSITORY_CALLERS"
    assert _rows(receipt)[(b2.TRANSFER, "workflow_dispatch")]["current_reachability"]["manual_authority"] is True


@pytest.mark.parametrize("mutation", [
    "drop_target", "add_sibling", "warehouse_no_network", "warehouse_canonical_write",
    "transfer_drive_write", "transfer_pointer_after_validation", "wrong_pointer_branch",
    "wrong_archive_sha", "wrong_archive_size", "erase_transfer_dispatch",
    "claim_complete", "change_count", "workflow_edit", "nonzero_live_action",
])
def test_tampered_or_overbroad_b2_receipt_is_rejected(receipt, mutation):
    changed = deepcopy(receipt)
    rows = _rows(changed)
    if mutation == "drop_target":
        changed["review_rows"].pop()
    elif mutation == "add_sibling":
        changed["review_rows"].append(deepcopy(changed["review_rows"][0]))
    elif mutation == "warehouse_no_network":
        rows[(b2.WAREHOUSE, "push")]["current_declared_trigger_authority"]["historical_data_acquisition_authority"] = "NONE"
    elif mutation == "warehouse_canonical_write":
        rows[(b2.WAREHOUSE, "push")]["current_declared_trigger_authority"]["persistent_canonical_database_write_authority"] = "WRITE"
    elif mutation == "transfer_drive_write":
        rows[(b2.TRANSFER, "workflow_dispatch")]["current_declared_trigger_authority"]["external_storage_write_authority"] = "GOOGLE_DRIVE_WRITE"
    elif mutation == "transfer_pointer_after_validation":
        rows[(b2.TRANSFER, "push")]["dynamic_reachability"]["pointer_branch_write_precedes_validation"] = False
    elif mutation == "wrong_pointer_branch":
        rows[(b2.TRANSFER, "push")]["dynamic_reachability"]["pointer_branch"] = "main"
    elif mutation == "wrong_archive_sha":
        changed["canonical_archive_contract"]["sha256"] = "0" * 64
    elif mutation == "wrong_archive_size":
        changed["canonical_archive_contract"]["bytes"] += 1
    elif mutation == "erase_transfer_dispatch":
        rows[(b2.TRANSFER, "workflow_dispatch")]["current_reachability"]["status"] = "UNREACHABLE"
    elif mutation == "claim_complete":
        changed["checkpoint_e_status"] = changed["p4_4_status"] = "COMPLETE"
    elif mutation == "change_count":
        changed["scope"]["global_unknown_after"] = 19
    elif mutation == "workflow_edit":
        changed["workflow_edit_count"] = 1
    else:
        changed["actions"]["workflow_dispatch"] = 1
    with pytest.raises(AssertionError):
        b2.validate_receipt(changed, expected=receipt)


def test_exact_source_inventory_and_all_live_side_effect_sentinels(receipt):
    inventory = boundary.read(b2.SOURCE_INVENTORY_PATH)
    assert inventory["canonical_sha256"] == receipt["source_inventory"]["canonical_sha256"]
    assert len(inventory["source_identities"]) == len(b2.SOURCE_PINS)
    assert {row["path"] for row in inventory["source_identities"]} == set(b2.SOURCE_PINS)
    assert all(row["git_blob_sha1"] and row["normalized_source_sha256"] for row in inventory["source_identities"])
    a2_v4 = boundary.read(b2.V4_INVENTORY_PATH)
    assert receipt["a2_inventory_successor"] == {
        "path": b2.V4_INVENTORY_PATH,
        "generation": 4,
        "canonical_sha256": a2_v4["canonical_sha256"],
        "predecessor_path": b2.V3_INVENTORY_PATH,
        "predecessor_canonical_sha256": b2.A2_V3_SHA,
        "predecessor_rewritten": False,
    }
    assert a2_v4["predecessor_inventory"]["rewritten"] is False
    assert receipt["actions"] == b2.ZERO_ACTIONS
    assert receipt["workflow_edit_count"] == receipt["trigger_edit_count"] == 0
    assert receipt["workflow_retirement_count"] == receipt["workflow_deletion_count"] == 0
    assert receipt["protected_model_router_portfolio_semantic_delta"] == 0
    assert boundary.git("rev-parse", "HEAD:.github/workflows").decode().strip() == b2.WORKFLOW_TREE


def test_completion_v2_additive_projection_allowlist_is_exact_and_narrow():
    expected = {
        "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v3.json",
        "tests/fixtures/core_01d/exact-pr-trigger-disposition-b1-source-inventory-v1.json",
        "tests/fixtures/core_01d/core-01d-exact-pr-trigger-disposition-b1-v1.json",
        "tests/fixtures/core_01d/core-01d-checkpoint-e-completion-v4.json",
        "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v4.json",
        b2.SOURCE_INVENTORY_PATH,
        b2.RECEIPT_PATH,
        "tests/fixtures/core_01d/core-01d-checkpoint-e-completion-v5.json",
        "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v5.json",
        "tests/fixtures/core_01d/owner-one-shot-issue-comment-authority-b3-source-inventory-v1.json",
        "tests/fixtures/core_01d/core-01d-owner-one-shot-issue-comment-authority-b3-v1.json",
        "tests/fixtures/core_01d/core-01d-checkpoint-e-completion-v6.json",
        "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v6.json",
        "tests/fixtures/core_01d/sportybet-current-trigger-authority-b4-source-inventory-v1.json",
        "tests/fixtures/core_01d/core-01d-sportybet-current-trigger-authority-b4-v1.json",
        "tests/fixtures/core_01d/core-01d-checkpoint-e-completion-v7.json",
        "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v7.json",
        "tests/fixtures/core_01d/frozen-artifact-replay-authority-b5-source-inventory-v1.json",
        "tests/fixtures/core_01d/core-01d-frozen-artifact-replay-authority-b5-v1.json",
        "tests/fixtures/core_01d/core-01d-checkpoint-e-completion-v8.json",
        "tests/fixtures/core_01d/ci-offline-transport-boundary-source-inventory-v8.json",
        "tests/fixtures/core_01d/port02c-trigger-authority-b6-source-inventory-v1.json",
        "tests/fixtures/core_01d/core-01d-port02c-trigger-authority-b6-v1.json",
        "tests/fixtures/core_01d/core-01d-checkpoint-e-completion-v9.json",
    }
    assert completion_v2.B1_ADDITIVE_EVIDENCE_PATHS == expected
    assert not any("*" in path for path in completion_v2.B1_ADDITIVE_EVIDENCE_PATHS)
