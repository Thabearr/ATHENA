"""Offline, fail-closed regressions for Pass-3 history versus retention."""
from copy import deepcopy
import json
from pathlib import Path
import smtplib
import socket
import subprocess
import urllib.request

import pytest

from scripts import audit_core_01d_retained_workflow_status_v4 as v4
from scripts import audit_core_01d_canonical_drive_transfer_completed_history as transfer

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def status():
    return v4.build_receipt()


@pytest.fixture(scope="module")
def receipt(status):
    return transfer.build_receipt(status)


def test_exact_history_and_23_part_source_contract_survive_empty_current_listings():
    snapshot = v4.authenticate_sources()
    run = snapshot["historical_transfer_run"]
    assert run["id"] == 32635585415
    assert run["head_sha"] == "d2145f0e5ba74fb516797768f5d8a8681a3c3ffa"
    assert run["path"] == ".github/workflows/prepare-canonical-drive-transfer.yml"
    assert run["event"] == "push"
    assert run["status"] == "completed" and run["conclusion"] == "success"
    assert run["run_attempt"] == 1 and run["head_branch"] == "main"
    assert run["created_at"] == "2026-08-23T11:06:04Z"
    assert run["updated_at"] == "2026-08-23T11:07:16Z"
    manifest = snapshot["manifest_identity"]
    assert manifest["source_run_id"] == 32628985683
    assert manifest["source_artifact_id"] == 9491418446
    assert manifest["canonical_archive"] == "athena-history-canonical.zip"
    assert manifest["canonical_bytes"] == 2149256220
    assert manifest["canonical_sha256"] == v4.ARCHIVE_SHA256
    assert manifest["part_count"] == 23
    actions = snapshot["current_actions_availability"]
    assert actions["source_run"]["state"] == "SOURCE_ARTIFACT_CURRENT_ACTIONS_LISTING_EMPTY"
    assert actions["transfer_run"]["state"] == "TRANSFER_RUN_CURRENT_ACTIONS_LISTING_EMPTY"
    assert all(row["total_count"] == 0 and row["artifacts"] == [] for row in actions.values())


def test_external_copy_is_partial_prior_evidence_without_fresh_verification():
    snapshot = v4.authenticate_sources()
    drive = snapshot["external_drive_availability"]
    assert drive["visible_part_indexes"] == [f"{i:03d}" for i in range(11)] + ["022"]
    assert drive["missing_part_indexes"] == [f"{i:03d}" for i in range(11, 22)]
    assert drive["recovery_state"] == "PARTIAL_DURABLE_COPY_RECOVERED"
    assert drive["exact_archive_currently_reconstructable"] is False
    assert drive["parts_downloaded_or_rehashed_in_this_pass"] is False
    assert drive["folder_independently_listed_in_this_pass"] is False
    assert drive["provenance"]["external_recovery_report"]["sha256"] == (
        "0934cc3b511e8fee8e4fee24b0e89e0180f1869df0eec968f4718e67ba766e26"
    )
    assert snapshot["ci_requires_external_accounts"] is False
    assert snapshot["gmail_corroboration_used"] is False


def test_v4_changes_only_transfer_artifact_and_two_lifecycle_rows(status):
    old = v4.load_predecessor()
    assert old["canonical_sha256"] == v4.V3_SHA256
    assert len(status["artifact_dispositions"]) == 8
    assert status["artifact_workflow_edge_count"] == old["artifact_workflow_edge_count"] == 12
    assert status["artifact_trigger_relationship_count"] == old["artifact_trigger_relationship_count"] == 14
    assert status["live_artifact_trigger_relationship_count"] == 0
    assert status["historical_or_spent_artifact_trigger_relationship_count"] == 14
    for previous, current in zip(old["artifact_dispositions"], status["artifact_dispositions"]):
        if previous["artifact_id"] != 9491418446:
            assert current == previous
        else:
            for key in ("artifact_id", "run_id", "name", "expected_size_bytes", "expected_sha256",
                        "recovery_state", "parts_found", "missing_parts", "authorizations"):
                assert current[key] == previous[key]
            assert current["retained_status"] == "COMPLETED_HISTORICAL_TRANSFER_RETAIN"
            assert current["dependency_types"] == ["HISTORICAL_TRANSFER_LINEAGE_AND_RETENTION_ONLY"]
    for previous, current in zip(old["current_artifact_trigger_relationships"],
                                 status["current_artifact_trigger_relationships"]):
        if previous["artifact_id"] != 9491418446:
            assert current == previous
        else:
            assert current["trigger_lifecycle"] == "RETAINED_NONEXECUTABLE_HISTORY"
            assert current["dependency_type"] == "HISTORICAL_TRANSFER_LINEAGE_AND_RETENTION_ONLY"
            assert current["retained_status"] == "COMPLETED_HISTORICAL_TRANSFER_RETAIN"
            for key in ("logical_trigger_id", "event", "workflow_path", "workflow_source_sha256",
                        "artifact_reference_lines", "authorizations"):
                assert current[key] == previous[key]
            assert all(flag is False for flag in current["authorizations"].values())


def test_c_closes_only_as_dependency_and_d_preserves_all_retention_defects(status, receipt):
    assert status["closed_blocker_ids"] == [
        "PROTECTED_FRESH_HOLDOUT_PR119_EXACT_FALLBACK_NOT_DURABLY_RECOVERED",
        "OWNER_GATED_PR145_FEATURE_EVIDENCE_NOT_DURABLY_RECOVERED",
        "CANONICAL_HISTORY_TRANSFER_SOURCE_NOT_FULLY_DURABLE",
    ]
    assert status["closed_blockers"][-1]["closed_as_current_dependency"] is True
    assert status["closed_blockers"][-1]["archive_recovered"] is False
    assert status["remaining_blocker_ids"] == ["HISTORICAL_REPLAY_ARCHIVES_UNAVAILABLE"]
    blocker, = status["remaining_blockers"]
    assert set(blocker["artifact_ids"]) == {
        9249856559, 9422055017, 9437181220, 9266604353,
        9274313978, 9275052993, 9292984849, 9491418446,
    }
    assert blocker["canonical_history_retention_defect"]["exact_archive_currently_reconstructable"] is False
    assert blocker["separate_retention_observations"][0]["artifact_id"] == 9294215497
    assert status["checkpoint_e_status"] == status["p4_4_status"] == "INCOMPLETE"
    assert receipt["blockers"]["D"] == "REMAINS_OPEN"
    assert receipt["historical_transfer_completed"] is True
    assert receipt["current_supported_transfer_execution"] is False
    assert receipt["replay_authorized"] is receipt["dispatch_authorized"] is False


@pytest.mark.parametrize("index", [0, 1])
def test_resealed_live_transfer_row_is_rejected(status, index):
    forged = deepcopy(status)
    rows = [row for row in forged["current_artifact_trigger_relationships"] if row["artifact_id"] == 9491418446]
    rows[index]["trigger_lifecycle"] = "LIVE_ADMINISTRATIVE_TRANSFER"
    v4.seal(forged)
    with pytest.raises(v4.TransferHistoryError):
        v4.validate_receipt(forged, status)


@pytest.mark.parametrize("mutation", ["recovered", "complete", "remove_d", "replay", "dispatch", "deleted"])
def test_resealed_false_recovery_completion_or_authority_is_rejected(receipt, mutation):
    forged = deepcopy(receipt)
    if mutation == "recovered":
        forged["external_drive_availability"]["recovery_state"] = "FULLY_RECOVERED"
    elif mutation == "complete":
        forged["checkpoint_e_status"] = forged["p4_4_status"] = "COMPLETE"
    elif mutation == "remove_d":
        forged["blockers"]["remaining_ids"] = []
    elif mutation == "deleted":
        forged["workflow_retired_or_deleted"] = True
    else:
        forged[mutation + "_authorized"] = True
    v4.seal(forged)
    with pytest.raises(v4.TransferHistoryError):
        transfer.validate_receipt(forged, receipt)


@pytest.mark.parametrize("mutation", ["full_copy", "expiry", "actor", "never_existed", "failed_run"])
def test_current_listing_cannot_rewrite_history_or_infer_disappearance(mutation):
    snapshot = json.loads((ROOT / v4.SNAPSHOT_PATH).read_text())
    if mutation == "full_copy":
        snapshot["external_drive_availability"]["missing_part_indexes"] = []
    elif mutation == "failed_run":
        snapshot["historical_transfer_run"]["conclusion"] = "failure"
    else:
        snapshot["current_actions_availability"]["source_run"][mutation] = "unsupported claim"
    with pytest.raises(v4.TransferHistoryError):
        v4.validate_snapshot(snapshot)


def test_source_and_evolution_immutability(status):
    assert status["current_workflow_tree_sha1"] == "9b08653f1a12bb1b3d964fbd910396ff955740da"
    assert status["current_evolution_ledger_sha256"] == "73e1eb3fe6593558c821600dd0f103353d45c15a139ab470a996c7cbb35da531"
    assert status["evolution_transition_count"] == 14
    assert status["workflow_count"] == 39 and status["trigger_surface_count"] == 57
    assert status["retired_workflow_count"] == 3
    identity = v4.v3._source_identity(v4.WORKFLOW)
    assert identity["git_blob_sha1"] == v4.WORKFLOW_BLOB
    assert identity["source_sha256"] == v4.WORKFLOW_SHA256
    assert status["canonical_transfer_disposition"]["physical_trigger_count"] == 2


def test_network_and_operational_actions_are_denied_during_offline_audit(monkeypatch, status):
    def denied(*args, **kwargs):
        raise AssertionError("network/provider/email/workflow mutation is forbidden")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(urllib.request, "urlopen", denied)
    monkeypatch.setattr(smtplib, "SMTP", denied)
    original = subprocess.run

    def git_reads_only(command, *args, **kwargs):
        assert command[0] == "git"
        assert command[1] in {"show", "rev-parse", "hash-object", "cat-file", "ls-tree", "diff", "log"}
        return original(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", git_reads_only)
    expected = transfer.build_receipt(status)
    assert all(count == 0 for count in expected["actions"].values())
    assert all(delta == 0 for delta in expected["protected_semantic_delta"].values())


def test_committed_receipts_are_authenticated():
    assert v4.audit()["result"] == "PASS"
    assert transfer.audit()["result"] == "PASS"


def test_checkpoint_additive_seam_preserves_v4_but_delegates_current_status():
    from scripts import audit_checkpoint_e_workflows as checkpoint
    paths = checkpoint.verified_additive_artifact_paths()
    assert v4.RECEIPT_PATH in paths and transfer.RECEIPT_PATH in paths
    result = checkpoint.audit()
    from scripts import audit_core_01d_checkpoint_e_completion_v2 as completion
    assert result["blockers"] == completion.audit()["remaining_blockers"]
    assert result["current_live_missing_artifact_relation_count"] == 0
    assert result["checkpoint_e"] == result["p4_4"] == "COMPLETE"
