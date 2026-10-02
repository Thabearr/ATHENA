"""Acceptance preserves missing bytes, historical meanings, and false authority."""
from copy import deepcopy
import json
import smtplib
import socket
import subprocess
import urllib.request

import pytest

from scripts import audit_core_01d_historical_retention_acceptance as policy
from scripts import audit_core_01d_retained_workflow_status_v5 as v5


@pytest.fixture(scope="module")
def receipts():
    old = policy.predecessor()
    accepted = policy.build_receipt(old)
    retained = v5.build_receipt(old, accepted)
    return old, accepted, retained


def test_nine_observations_are_timestamped_read_only_empty_without_inference():
    snapshot = policy.load_snapshot()
    assert [(r["run_id"], r["expected_historical_artifact_id"]) for r in snapshot["actions_observations"]] == policy.PAIRS
    assert all(r["state"] == "CURRENT_ACTIONS_ARTIFACT_LISTING_EMPTY"
               and r["total_count"] == 0 and r["artifacts"] == []
               and r["read_only"] is True and r["observed_at_utc"].endswith("Z")
               and r["disappearance_cause_date_or_actor_inferred"] is False
               for r in snapshot["actions_observations"])
    external = snapshot["canonical_history_external_availability"]
    assert external["recovery_state"] == "PARTIAL_DURABLE_COPY_RECOVERED"
    assert external["visible_part_indexes"] == [f"{i:03d}" for i in range(11)] + ["022"]
    assert external["missing_part_indexes"] == [f"{i:03d}" for i in range(11, 22)]
    assert external["exact_archive_currently_reconstructable"] is False
    assert external["parts_downloaded_or_rehashed_in_this_pass"] is False
    assert external["provenance"]["external_recovery_report"]["sha256"] == "0934cc3b511e8fee8e4fee24b0e89e0180f1869df0eec968f4718e67ba766e26"


def test_v5_preserves_eight_artifacts_and_all_fourteen_relationships(receipts):
    old, accepted, retained = receipts
    assert old["canonical_sha256"] == policy.V4_SHA
    assert retained["artifact_dispositions"] == old["artifact_dispositions"]
    assert retained["current_artifact_trigger_relationships"] == old["current_artifact_trigger_relationships"]
    assert len(retained["artifact_dispositions"]) == 8
    assert retained["artifact_workflow_edge_count"] == 12
    assert retained["artifact_trigger_relationship_count"] == 14
    assert retained["live_artifact_trigger_relationship_count"] == 0
    assert retained["historical_or_spent_artifact_trigger_relationship_count"] == 14
    assert retained["remaining_blocker_ids"] == [] and retained["remaining_blocker_family"] is None
    assert retained["completion_authority"] is False
    assert retained["checkpoint_e_status"] == "CANDIDATE_COMPLETE_SUBJECT_TO_INDEPENDENT_AUDIT"
    assert len(accepted["artifact_retentions"]) == 9
    assert accepted["blocker_D"]["state"] == "CLOSED_BY_OWNER_RETENTION_LIMITATION_ACCEPTANCE"
    for row in accepted["artifact_retentions"]:
        assert row["retention_disposition"] == "ACCEPTED_HISTORICAL_RETENTION_LIMITATION"
        assert row["exact_bytes_recovered"] is row["replay_available"] is row["supported_current_runtime_dependency"] is False
        assert row["historical_claims_preserved"] is True
        assert row["checkpoint_e_blocking"] is False
        assert all(row[k] is False for k in policy.NO_AUTHORITY)
        assert row["future_exact_recovery"] == "ADDITIVE_IF_LATER_DISCOVERED_DO_NOT_REWRITE_HISTORY"


@pytest.mark.parametrize("artifact_id,key", [
    (9249856559, "fixed_projection_is_original_zip_recovery"),
    (9422055017, "pr193_derived_output_is_raw_source"),
    (9437181220, "pr202_catalog_admission_proven"),
    (9266604353, "metadata_reconciliation_is_v1_bytes_or_semantic_qualification"),
    (9274313978, "qualification_success"), (9275052993, "raw_source_recovered"),
    (9275052993, "pr145_successor_approved"), (9292984849, "validator_input"),
    (9292984849, "success_evidence"), (9491418446, "fully_recovered"),
    (9491418446, "exact_archive_reconstructable"),
    (9294215497, "source_controlled_review_is_byte_equivalent_zip_substitute"),
    (9294215497, "successor_approved"),
])
def test_resealed_historical_falsehoods_are_rejected(receipts, artifact_id, key):
    _, expected, _ = receipts
    forged = deepcopy(expected)
    row = next(r for r in forged["artifact_retentions"] if r["artifact_id"] == artifact_id)
    row["historical_truth"][key] = True
    policy.seal(forged)
    with pytest.raises(policy.RetentionAcceptanceError):
        policy.validate_receipt(forged, expected)


@pytest.mark.parametrize("key", [*policy.NO_AUTHORITY, "exact_bytes_recovered", "supported_current_runtime_dependency", "replay_available"])
def test_resealed_recovery_or_execution_authority_is_rejected(receipts, key):
    _, expected, _ = receipts
    forged = deepcopy(expected)
    forged["artifact_retentions"][0][key] = True
    policy.seal(forged)
    with pytest.raises(policy.RetentionAcceptanceError):
        policy.validate_receipt(forged, expected)


def test_pr145_completion_failure_success_and_separate_result_remain_distinct(receipts):
    _, accepted, _ = receipts
    rows = {r["artifact_id"]: r for r in accepted["artifact_retentions"]}
    assert rows[9275052993]["historical_truth"]["pr145_one_shot_completed"] is True
    assert rows[9292984849]["historical_truth"]["marker_checkout_download_validator_or_training_executed"] is False
    result = rows[9294215497]
    assert result["historical_source"]["outside_original_eight_artifact_mission"] is True
    assert result["historical_truth"]["review_state"] == "REVIEWED_MIXED_OR_WEAK_FOTMOB_UTC_NATIVE_SUCCESSOR_NOT_APPROVED"
    assert result["historical_source"]["historical_result_identity"]["sha256"] == "e9eac385a66df04bf28e7d69062e55db516829e94405e4a8def0e4d6a346d6c5"
    assert result["historical_truth"]["predictions"]["record_count"] == 6948
    forged = deepcopy(accepted)
    next(r for r in forged["artifact_retentions"] if r["artifact_id"] == 9275052993)["historical_truth"]["pr145_one_shot_completed"] = False
    policy.seal(forged)
    with pytest.raises(policy.RetentionAcceptanceError):
        policy.validate_receipt(forged, accepted)


@pytest.mark.parametrize("mutation", ["reappeared", "expiry", "deleted_by", "wrong_run", "drive_complete"])
def test_snapshot_mutations_require_new_evidence_review(mutation):
    value = json.loads((policy.ROOT / policy.SNAPSHOT_PATH).read_text())
    if mutation == "drive_complete":
        value["canonical_history_external_availability"]["missing_part_indexes"] = []
    elif mutation == "reappeared":
        value["actions_observations"][0]["artifacts"] = [{"id": 9249856559}]
    elif mutation == "wrong_run":
        value["actions_observations"][0]["run_id"] = 1
    else:
        value["actions_observations"][0][mutation] = "unsupported inference"
    with pytest.raises(policy.RetentionAcceptanceError):
        policy.validate_snapshot(value)


def test_v5_cannot_rewrite_relations_or_become_completion_authority(receipts):
    _, _, expected = receipts
    for mutation in ("authority", "artifact", "live"):
        forged = deepcopy(expected)
        if mutation == "authority": forged["completion_authority"] = True
        elif mutation == "artifact": forged["artifact_dispositions"][0]["recovery_state"] = "FULLY_RECOVERED"
        else: forged["current_artifact_trigger_relationships"][0]["trigger_lifecycle"] = "LIVE_ADMINISTRATIVE_TRANSFER"
        policy.seal(forged)
        with pytest.raises(policy.RetentionAcceptanceError):
            v5.validate_receipt(forged, expected)


def test_policy_build_is_offline_and_cannot_call_operational_commands(monkeypatch):
    def deny(*args, **kwargs): raise AssertionError("network/operational action forbidden")
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)
    monkeypatch.setattr(smtplib, "SMTP", deny)
    original = subprocess.run
    def git_read_only(command, *args, **kwargs):
        assert command[0] == "git"
        assert command[1] in {"show", "rev-parse", "hash-object", "cat-file", "ls-tree", "diff", "log"}
        return original(command, *args, **kwargs)
    monkeypatch.setattr(subprocess, "run", git_read_only)
    result = policy.build_receipt()
    assert all(value == 0 for value in result["actions"].values())


def test_committed_retention_and_v5_audits_pass():
    assert policy.audit()["result"] == v5.audit()["result"] == "PASS"
