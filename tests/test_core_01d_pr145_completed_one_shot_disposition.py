"""Offline regressions for the PR145 completed/spent one-shot disposition."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import smtplib
import socket
import subprocess
import urllib.request

import pytest

from scripts import audit_core_01d_pr145_completed_one_shot_disposition as disposition
from scripts import audit_core_01d_retained_workflow_status_v3 as retained_v3


ROOT = Path(__file__).resolve().parents[1]
HISTORY_PATH = ROOT / retained_v3.HISTORY_FIXTURE_PATH


@pytest.fixture(scope="module")
def status_receipt():
    return retained_v3.build_receipt()


@pytest.fixture(scope="module")
def pass2_receipt(status_receipt):
    return disposition.build_receipt(status_receipt)


def test_fixture_preserves_exact_failed_pre_attempt_and_successful_one_shot_history():
    history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    retained_v3.validate_history(history)
    comments = {row["id"]: row for row in history["comments"]}
    runs = {row["id"]: row for row in history["runs"]}

    failed = comments[5317758294]["body"]
    assert comments[5317747534]["author_login"] == "Thabearr"
    assert runs[32046244761]["head_sha"] == "21bff3fe96e8c9b250c9776240ba7bede9f74c89"
    assert "attempt-marker-created: false" in failed
    assert "validator-executed: false" in failed
    assert "research-training-executed: false" in failed
    assert "failure-artifact-id: 9292984849" in failed
    assert "failure-artifact-sha256: 91965dee1fdb496e776a914de9a9e789a830141ea6b17276a7b1bade541835c1" in failed
    assert "state: FAILED_BEFORE_DURABLE_ATTEMPT_MARKER_NO_MODEL_VALIDATION_EXECUTED" in failed

    marker = comments[5318115383]["body"]
    result = comments[5318117332]["body"]
    assert comments[5318114406]["author_login"] == "Thabearr"
    assert runs[32049714066]["head_sha"] == "b8ddc00f7529c5533c9da2daad613d997498cbf2"
    assert runs[32049714066]["conclusion"] == "success"
    assert marker.startswith(retained_v3.ATTEMPT_MARKER)
    assert "run-id: 32049714066" in marker
    assert "command-comment-id: 5318114406" in marker
    for fact in (
        "runner-exit-code: 0",
        "artifact-download-outcome: success",
        "package-outcome: success",
        "artifact-upload-outcome: success",
        "verification-outcome: success",
        "state: EXECUTION_COMPLETED_REVIEWED_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_EVIDENCE_PRESERVED",
    ):
        assert fact in result


def test_result_review_and_next_boundary_bind_consumed_successful_execution(status_receipt):
    status = status_receipt
    review = status["pr145_result_review"]
    followup = status["pr145_next_boundary_protocol"]
    assert review["review_state"] == (
        "REVIEWED_MIXED_OR_WEAK_FOTMOB_UTC_NATIVE_SUCCESSOR_NOT_APPROVED"
    )
    assert review["source_artifact_id"] == 9275052993
    assert review["result_artifact"]["id"] == 9294215497
    assert review["result_receipt"]["sha256"] == (
        "1fffee7474ab37ee613e6a7943b57fd9231f6d6bdf53ffa6b13ee2b62ceca06a"
    )
    assert review["predictions"]["sha256"] == (
        "2f4939a8f2d41674660144f5315d2420ce2f006ce2b885e52c6655abd0e52420"
    )
    assert review["predictions"]["record_count"] == 6948
    assert review["successor_candidate_approved"] is False
    assert review["evaluation_labels_consumed"] is True
    assert review["all_authority_false"] is True
    assert followup["next_boundary"] == (
        "IMPLEMENT_REVIEWED_FRESH_HOLDOUT_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_"
        "CALIBRATION_AND_COMPETITION_IDENTITY_FOLLOWUP"
    )
    assert followup["protocol_state"] == (
        "PRE_REGISTERED_FRESH_HOLDOUT_CALIBRATION_AND_COMPETITION_IDENTITY_"
        "NOT_IMPLEMENTED_NOT_EXECUTED"
    )
    assert followup["executed_in_this_pass"] is False


def test_v3_reclassifies_only_pr145_relations_and_closes_only_blocker_b(status_receipt):
    status = status_receipt
    assert status["predecessor_v2"]["canonical_sha256"] == retained_v3.V2_RECEIPT_SHA256
    assert status["current_workflow_tree_sha1"] == retained_v3.WORKFLOW_TREE_SHA1
    assert status["current_evolution_ledger_sha256"] == retained_v3.EVOLUTION_LEDGER_SHA256
    assert status["evolution_transition_count"] == 14
    assert status["workflow_count"] == 39
    assert status["trigger_surface_count"] == 57
    assert status["artifact_workflow_edge_count"] == 12
    assert status["artifact_trigger_relationship_count"] == 14
    assert status["live_artifact_trigger_relationship_count"] == 2
    assert status["historical_or_spent_artifact_trigger_relationship_count"] == 12

    relations = {row["artifact_id"]: row for row in status["current_artifact_trigger_relationships"]}
    source = relations[9275052993]
    assert source["trigger_lifecycle"] == "CLOSED_OR_SPENT"
    assert source["retained_status"] == "SPENT_HISTORICAL_ONE_SHOT_RETAIN"
    assert source["dependency_type"] == "HARD_EXACT_HISTORICAL_REPLAY_SOURCE"
    assert source["authorizations"]["replay_authorized"] is False
    forensic = relations[9292984849]
    assert forensic["trigger_lifecycle"] == "CLOSED_OR_SPENT_FORENSIC_HISTORY"
    assert forensic["retained_status"] == "FORENSIC_PRE_ATTEMPT_HISTORY_RETAIN"
    assert forensic["dependency_type"] == "FORENSIC_RECONCILIATION_METADATA_ONLY"
    assert forensic["authorizations"]["replay_authorized"] is False

    blockers_closed = [row["id"] for row in status["closed_blockers"]]
    blockers_remaining = [row["id"] for row in status["remaining_blockers"]]
    assert blockers_closed == [
        "PROTECTED_FRESH_HOLDOUT_PR119_EXACT_FALLBACK_NOT_DURABLY_RECOVERED",
        "OWNER_GATED_PR145_FEATURE_EVIDENCE_NOT_DURABLY_RECOVERED",
    ]
    assert blockers_remaining == [
        "CANONICAL_HISTORY_TRANSFER_SOURCE_NOT_FULLY_DURABLE",
        "HISTORICAL_REPLAY_ARCHIVES_UNAVAILABLE",
    ]
    d_blocker = status["remaining_blockers"][1]
    assert {9275052993, 9292984849}.issubset(set(d_blocker["artifact_ids"]))
    assert status["checkpoint_e_status"] == status["p4_4_status"] == "INCOMPLETE"
    assert status["pr145_disposition"]["source_artifact_recovery_state"] == "METADATA_ONLY_NO_BYTES"
    assert status["pr145_disposition"]["replay_authorized"] is False


def test_missing_source_bytes_cannot_reopen_spent_lane_or_pending_first_execution(status_receipt):
    status = status_receipt
    assert status["pr145_disposition"]["state"] == "SPENT_HISTORICAL_ONE_SHOT_RETAIN"
    assert status["pr145_attempt_authority_spent"] is True
    assert status["pr145_disposition"]["source_artifact_recovery_state"] == "METADATA_ONLY_NO_BYTES"
    assert status["pr145_disposition"]["current_pr145_execution_dependency"] is False
    assert status["pr145_workflow_unchanged"] is True

    mutated = deepcopy(status)
    row, = [row for row in mutated["current_artifact_trigger_relationships"]
            if row["artifact_id"] == 9275052993]
    row["retained_status"] = "OWNER_GATED_RESEARCH_PENDING_EXACT_BYTES_RETAIN"
    row["trigger_lifecycle"] = "LIVE_OWNER_GATED"
    row["dependency_type"] = "HARD_EXACT_OWNER_GATED_RESEARCH_INPUT"
    mutated["canonical_sha256"] = retained_v3.sha256(
        retained_v3.canonical_bytes({key: item for key, item in mutated.items()
                                     if key != "canonical_sha256"})
    )
    with pytest.raises(retained_v3.RetainedWorkflowStatusV3Error):
        retained_v3.validate_receipt(mutated)


def test_result_artifact_empty_listing_is_limited_and_not_a_reopened_lane(status_receipt):
    history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    listing = history["successful_result_artifact_current_listing"]
    assert listing["state"] == "CURRENT_ACTIONS_ARTIFACT_LISTING_EMPTY"
    assert listing["total_count"] == 0
    assert listing["artifact_disappearance_time_known"] is False
    assert listing["artifact_disappearance_reason_known"] is False
    assert listing["external_durable_archive_checked"] is False
    assert listing["durable_byte_retention_reviewed"] is False
    observation, = status_receipt["separate_retention_observations"]
    assert observation["id"] == (
        "PR145_SUCCESSFUL_RESULT_ARTIFACT_CURRENTLY_UNAVAILABLE_RETENTION_NOT_REVIEWED"
    )
    assert observation["reopens_pr145_execution_lane"] is False


def test_v3_and_pass2_receipts_reject_completion_or_evidence_substitution_claims(
    status_receipt, pass2_receipt
):
    status = status_receipt
    mutated_status = deepcopy(status)
    mutated_status["checkpoint_e_status"] = "COMPLETE"
    with pytest.raises(retained_v3.RetainedWorkflowStatusV3Error):
        retained_v3.validate_receipt(mutated_status)

    pass2 = pass2_receipt
    assert pass2["terminal"] == (
        "CORE_01D_PR145_SPENT_ONE_SHOT_REVIEW_READY_BLOCKER_B_CLOSED_DO_NOT_MERGE"
    )
    assert pass2["actions"]["provider_action_count"] == 0
    assert pass2["actions"]["provider_acquisition_count"] == 0
    assert pass2["actions"]["pr145_execution_count"] == 0
    assert pass2["actions"]["model_training_count"] == 0
    assert set(pass2["actions"].values()) == {0}
    assert set(pass2["protected_semantic_delta"].values()) == {0}
    assert set(pass2["authority_action_counts"].values()) == {0}
    assert pass2["authority"] == dict.fromkeys(pass2["authority"], False)
    assert pass2["blockers"]["checkpoint_e"] == pass2["blockers"]["p4_4"] == "INCOMPLETE"

    mutated_pass2 = deepcopy(pass2)
    mutated_pass2["source_artifact"]["recovery_state"] = "EXACT_BYTES_RECOVERED"
    with pytest.raises(disposition.Pr145DispositionError):
        disposition.validate_receipt(mutated_pass2)


def test_pass2_audits_are_network_and_action_denied(monkeypatch):
    def deny(*_args, **_kwargs):
        raise AssertionError("live network or external action is forbidden in this test")

    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)
    monkeypatch.setattr(smtplib, "SMTP", deny)
    original_run = subprocess.run

    def guarded_run(command, *args, **kwargs):
        argv = [str(item).lower() for item in command]
        assert argv and argv[0] == "git", f"external action/process denied: {argv!r}"
        assert retained_v3.BASE_MAIN_SHA.lower() not in argv, (
            "receipt audits must not require ancestor Git objects in shallow CI"
        )
        forbidden = {
            "push", "pull", "fetch", "checkout", "reset", "clean", "commit", "merge",
            "dispatch", "rerun", "cancel", "upload", "release", "comment", "issue",
        }
        assert not forbidden.intersection(argv[1:]), f"mutating Git/action surface denied: {argv!r}"
        return original_run(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", guarded_run)
    # Audits use only local Git object/source reads. No validator or training module
    # is imported or called by either receipt builder.
    assert retained_v3.audit()["result"] == "PASS"
    assert disposition.audit()["result"] == "PASS"
