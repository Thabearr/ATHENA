"""Fail-closed contracts for additive retained-workflow status evidence."""
from copy import deepcopy
import json
import subprocess

import pytest

from scripts import audit_core_01d_retained_workflow_status as audit


@pytest.fixture(scope="module")
def receipt():
    return json.loads((audit.ROOT / audit.RECEIPT_PATH).read_bytes())


@pytest.fixture(scope="module")
def expected():
    return audit.build_receipt()


def _relations(receipt, artifact_id=None):
    rows = receipt["retained_status_rows"]
    return [row for row in rows if artifact_id is None or row["artifact_id"] == artifact_id]


def _artifact(receipt, artifact_id):
    row, = [item for item in receipt["artifact_dispositions"]
            if item["artifact_id"] == artifact_id]
    return row


def test_source_derived_audit_passes_and_checkpoint_stays_open():
    result = audit.audit()
    assert result["result"] == "PASS"
    assert result["terminal"] == "CORE_01D_RETAINED_WORKFLOW_STATUS_REVIEW_READY_INCOMPLETE_DO_NOT_MERGE"
    assert result["checkpoint_e"] == result["p4_4"] == "INCOMPLETE"
    assert result["artifact_count"] == 8
    assert result["workflow_path_count"] == 11
    assert result["artifact_workflow_edge_count"] == 13
    assert result["artifact_trigger_relationship_count"] == 17
    assert result["live_relation_count"] == 7
    assert result["historical_relation_count"] == 10


def test_receipt_pins_exact_base_predecessors_and_external_reports(receipt, expected):
    audit.validate_receipt(receipt, expected)
    assert receipt["policy_id"] == "ATHENA_CORE_01D_RETAINED_WORKFLOW_STATUS_V1"
    assert receipt["exact_base_main_sha"] == "0e6d2c622ef7a12f82c4405d80906f49d97b523d"
    assert receipt["exact_base_tree_sha"] == "fed8664d63391aefdbd48197375e0ecf331b733c"
    assert receipt["source_review_counter_before_merge"] == "2/5"
    assert receipt["source_review_counter_if_owner_merges"] == "3/5"
    assert receipt["mandatory_source_reread_due"] is False
    assert receipt["predecessor_v2_matrix_sha256"] == audit.PREDECESSOR_V2_MATRIX_SHA256
    assert receipt["predecessor_v2_receipt_sha256"] == audit.PREDECESSOR_V2_RECEIPT_SHA256
    assert receipt["schedule_ownership_receipt_sha256"] == audit.SCHEDULE_OWNERSHIP_RECEIPT_SHA256
    assert receipt["external_review_report_sha256"] == audit.EXTERNAL_REPORTS


def test_source_inventory_rederives_reviewed_counts(receipt):
    inventory = receipt["source_reference_inventory"]
    assert inventory["scan_tree_sha"] == audit.BASE_MAIN_SHA
    assert inventory["all_repository_matching_line_count"] == 108
    assert inventory["workflow_matching_line_count"] == 27
    assert inventory["supporting_nonworkflow_matching_line_count"] == 81
    assert inventory["unique_workflow_path_count"] == 11
    assert inventory["artifact_workflow_edge_count"] == 13
    assert inventory["matching_lines_by_artifact"] == {
        "9249856559": 42, "9422055017": 11, "9437181220": 17,
        "9266604353": 11, "9274313978": 9, "9275052993": 8,
        "9292984849": 4, "9491418446": 6,
    }
    assert inventory["workflow_matching_lines_by_artifact"] == {
        "9249856559": 3, "9422055017": 3, "9437181220": 11,
        "9266604353": 3, "9274313978": 2, "9275052993": 2,
        "9292984849": 1, "9491418446": 2,
    }
    assert len(inventory["workflow_reference_edges"]) == 13
    assert len(inventory["reference_source_files"]) == 76
    assert inventory["reference_source_files_sha256"] == audit.EXPECTED_REFERENCE_SOURCE_FILES_SHA256
    assert receipt["workflow_source_inventory_sha256"]
    assert inventory["reference_inventory_sha256"]
    assert inventory["workflow_reference_inventory_sha256"]
    assert receipt["workflow_tree_sha1_before"] == receipt["workflow_tree_sha1_after"] == audit.WORKFLOW_TREE_SHA1


def test_shallow_checkout_uses_pinned_exact_base_source_inventory(monkeypatch, receipt):
    monkeypatch.setattr(audit, "_object_exists", lambda _revision: False)
    assert audit.build_receipt() == receipt


def test_historical_inventory_forward_authenticates_supplementary_receipt():
    from scripts.audit_checkpoint_e_workflows import verified_additive_artifact_paths

    assert audit.RECEIPT_PATH in verified_additive_artifact_paths()


def test_all_eight_exact_artifact_identities_and_recovery_states(receipt):
    expected_identities = {
        9249856559: (31887523012, "fotmob-ordinary-ft-source-history-campaign-31887523012", 61886753,
                     "7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f"),
        9422055017: (32410775191, "fotmob-prospective-player-context-evidence", 974969,
                     "db5dc12b8863cbac15f210e018ddf0af9b9011a6ad8c3958a473a597254f44b5"),
        9437181220: (32455713912, None, None,
                     "360aac588f049fe6b0437c43e060b317edd12aaf4672db93ebe2fca42de00589"),
        9266604353: (31953949073, "pr69-primary-time-basis-evidence-campaign-31953949073", None,
                     "ce87f13cb72a917c0a01e4bbede87e4123d85861d5ee1cd98667bb802d380db7"),
        9274313978: (31987862156, "fotmob-utc-native-feature-qualification-31987862156", 2388,
                     "1a46808c8ee4d21ab67ec03b1fd6c0a80e79fadf04933092e7a106522e31c337"),
        9275052993: (31990121181, "fotmob-utc-native-feature-qualification-v2-31990121181", 23349191,
                     "f69ffad8f47faadb3ec743c96efa35fb6f4b43776a7650cf0414fb40455d29eb"),
        9292984849: (32046244761, None, None,
                     "91965dee1fdb496e776a914de9a9e789a830141ea6b17276a7b1bade541835c1"),
        9491418446: (32628985683, "athena-history-canonical.zip", 2149256220,
                     "a783886d0906e357e26851fcb3eb182bb06bdcc184d21f2b6578bb3d1fa61511"),
    }
    assert len(receipt["artifact_dispositions"]) == 8
    for artifact_id, identity in expected_identities.items():
        row = _artifact(receipt, artifact_id)
        assert (row["run_id"], row["name"], row["expected_size_bytes"], row["expected_sha256"]) == identity
    assert sum(row["recovery_state"] == "METADATA_ONLY_NO_BYTES" for row in receipt["artifact_dispositions"]) == 7
    assert sum(row["recovery_state"] == "PARTIAL_DURABLE_COPY_RECOVERED" for row in receipt["artifact_dispositions"]) == 1
    assert receipt["exact_archive_recovered_count"] == 0


def test_exactly_seventeen_unique_relationships_and_closed_status_vocabulary(receipt):
    rows = receipt["retained_status_rows"]
    assert len(rows) == 17
    keys = [(row["artifact_id"], row["workflow_path"], row["event"], row["qualifier"])
            for row in rows]
    assert len(keys) == len(set(keys))
    assert len({row["logical_trigger_id"] for row in rows}) == 15
    assert receipt["live_artifact_trigger_relationship_count"] == 7
    assert receipt["historical_or_spent_artifact_trigger_relationship_count"] == 10
    assert receipt["live_logical_trigger_path_count"] == 6
    assert receipt["closed_or_spent_logical_trigger_path_count"] == 9
    assert set(receipt["retained_status_vocabulary"]) == {
        "PROTECTED_RESEARCH_RETAIN_FAIL_CLOSED",
        "SPENT_HISTORICAL_ONE_SHOT_RETAIN",
        "CLOSED_HISTORICAL_PR_VERIFIER_RETAIN",
        "HISTORICAL_GATE_FAILED_ADMISSION_UNPROVEN_RETAIN",
        "OWNER_GATED_RESEARCH_PENDING_EXACT_BYTES_RETAIN",
        "FORENSIC_PRE_ATTEMPT_HISTORY_RETAIN",
        "ADMINISTRATIVE_TRANSFER_PENDING_COMPLETE_ARCHIVE_RETAIN",
    }
    assert all(row["classification_basis"].endswith("VOLATILE_ACTIONS_STATE_EXCLUDED") for row in rows)


def test_fresh_holdout_crons_dispatch_and_no_backfill_are_protected(receipt):
    rows = _relations(receipt, 9249856559)
    fresh = [row for row in rows if row["workflow_path"].endswith("fotmob-utc-native-xg-fresh-holdout.yml")]
    assert {(row["event"], row["qualifier"]) for row in fresh} == {
        ("schedule", "cron 7 * * * *"),
        ("schedule", "cron 37 * * * *"),
        ("workflow_dispatch", "continuity inputs and exact prospective-only confirmation"),
    }
    assert all(row["retained_status"] == "PROTECTED_RESEARCH_RETAIN_FAIL_CLOSED" for row in fresh)
    workflow = (audit.ROOT / ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml").read_text()
    assert "PROSPECTIVE_ONLY_NO_BACKFILL_V1" in workflow
    assert _artifact(receipt, 9249856559)["distinct_successor_evidence"]["is_substitute"] is False
    assert "CONDITIONAL_EXACT_FALLBACK" in _artifact(receipt, 9249856559)["dependency_types"]


def test_pr139_pr130_spent_and_historical_verifiers_retained(receipt):
    assert len([row for row in _relations(receipt, 9249856559)
                if row["retained_status"] == "SPENT_HISTORICAL_ONE_SHOT_RETAIN"]) == 1
    assert len(_relations(receipt, 9266604353)) == 1
    assert _relations(receipt, 9266604353)[0]["retained_status"] == "SPENT_HISTORICAL_ONE_SHOT_RETAIN"
    assert _relations(receipt, 9274313978)[0]["retained_status"] == "SPENT_HISTORICAL_ONE_SHOT_RETAIN"
    assert {row["qualifier"].split()[0] for artifact_id in (9422055017, 9437181220)
            for row in _relations(receipt, artifact_id)
            if row["event"] == "pull_request"} >= {"PR193", "PR194", "PR197", "PR200", "PR201", "PR202"}


def test_pr202_merge_push_is_unproven_not_admitted(receipt):
    row, = [row for row in _relations(receipt, 9437181220) if row["event"] == "push"]
    artifact = _artifact(receipt, 9437181220)
    assert row["retained_status"] == "HISTORICAL_GATE_FAILED_ADMISSION_UNPROVEN_RETAIN"
    assert "candidate" in artifact["missing_evidence_effect"].lower()
    assert "admission" in artifact["missing_evidence_effect"].lower()
    assert "approval gate" in artifact["retained_reason"]


def test_pr145_owner_gated_exact_input_and_forensic_not_input(receipt):
    research = _relations(receipt, 9275052993)
    forensic = _relations(receipt, 9292984849)
    assert len(research) == len(forensic) == 1
    assert research[0]["retained_status"] == "OWNER_GATED_RESEARCH_PENDING_EXACT_BYTES_RETAIN"
    assert research[0]["dependency_type"] == "HARD_EXACT_OWNER_GATED_RESEARCH_INPUT"
    assert forensic[0]["retained_status"] == "FORENSIC_PRE_ATTEMPT_HISTORY_RETAIN"
    assert forensic[0]["dependency_type"] == "FORENSIC_RECONCILIATION_METADATA_ONLY"
    assert "not a validator input" in forensic[0]["retained_reason"]
    assert "did not execute" in _artifact(receipt, 9292984849)["evidence_authority"]


def test_canonical_transfer_is_retained_until_complete_exact_archive(receipt):
    artifact = _artifact(receipt, 9491418446)
    expected_missing = [f"{number:03d}" for number in range(11, 22)]
    assert artifact["missing_parts"] == expected_missing
    assert artifact["parts_found"] == [f"{number:03d}" for number in list(range(11)) + [22]]
    assert artifact["recovery_state"] == "PARTIAL_DURABLE_COPY_RECOVERED"
    assert artifact["retained_status"] == "ADMINISTRATIVE_TRANSFER_PENDING_COMPLETE_ARCHIVE_RETAIN"
    assert len(_relations(receipt, 9491418446)) == 2
    assert all(row["dependency_type"] == "HARD_EXACT_TRANSFER_SOURCE"
               for row in _relations(receipt, 9491418446))


def test_all_rows_deny_retirement_replay_and_other_authority(receipt):
    for row in [*receipt["retained_status_rows"], *receipt["artifact_dispositions"]]:
        assert row["authorizations"] == audit.NO_AUTHORITY
    assert receipt["retirement_authorized"] is False
    assert receipt["workflow_deletion_count"] == 0
    assert receipt["trigger_change_count"] == 0
    assert receipt["caller_migration_count"] == 0
    assert receipt["provider_action_count"] == 0
    assert receipt["workflow_dispatch_action_count"] == 0
    assert receipt["workflow_rerun_or_cancel_action_count"] == 0
    assert receipt["evidence_regeneration_count"] == 0
    assert receipt["share_code_action_count"] == receipt["email_action_count"] == 0
    assert receipt["login_cookie_wallet_stake_wager_action_count"] == 0
    assert set(receipt["protected_semantic_delta"].values()) == {0}
    assert receipt["evidence_substitution_count"] == receipt["synthetic_backfill_count"] == 0
    assert receipt["authorizations"] == audit.NO_AUTHORITY
    assert receipt["consumer_contract_change_authorized"] is False
    assert receipt["consumer_contract_change_gate"].startswith("SEPARATE_OWNER_APPROVED")


@pytest.mark.parametrize("mutation", [
    "retirement", "deletion", "trigger", "caller", "reacquisition", "substitution",
    "backfill", "replay", "checkpoint_complete", "p44_complete", "workflow_source",
])
def test_rehashed_dangerous_mutations_are_rejected(receipt, expected, mutation):
    changed = deepcopy(receipt)
    if mutation == "retirement": changed["retirement_authorized"] = True
    elif mutation == "deletion": changed["retained_status_rows"][0]["authorizations"]["deletion_authorized"] = True
    elif mutation == "trigger": changed["retained_status_rows"][0]["authorizations"]["trigger_change_authorized"] = True
    elif mutation == "caller": changed["retained_status_rows"][0]["authorizations"]["caller_migration_authorized"] = True
    elif mutation == "reacquisition": changed["retained_status_rows"][0]["authorizations"]["provider_reacquisition_authorized"] = True
    elif mutation == "substitution": changed["artifact_dispositions"][0]["authorizations"]["evidence_substitution_authorized"] = True
    elif mutation == "backfill": changed["artifact_dispositions"][0]["authorizations"]["synthetic_backfill_authorized"] = True
    elif mutation == "replay": changed["retained_status_rows"][0]["authorizations"]["replay_authorized"] = True
    elif mutation == "checkpoint_complete": changed["checkpoint_e_status"] = "COMPLETE"
    elif mutation == "p44_complete": changed["p4_4_status"] = "COMPLETE"
    elif mutation == "workflow_source": changed["workflow_source_changed"] = True
    audit.seal(changed)
    with pytest.raises(audit.RetainedWorkflowStatusError):
        audit.validate_receipt(changed, expected)


def test_volatile_runtime_observations_cannot_define_static_classification(receipt):
    assert receipt["volatile_runtime_observations_included"] is False
    assert receipt["volatile_run_state_used_for_static_classification"] is False
    assert all(row["classification_basis"] ==
               "STATIC_SOURCE_AND_REVIEWED_DISPOSITION; VOLATILE_ACTIONS_STATE_EXCLUDED"
               for row in receipt["retained_status_rows"])


def test_workflows_and_evolution_ledger_are_unchanged():
    assert audit._git("rev-parse", "HEAD:.github/workflows").decode().strip() == audit.WORKFLOW_TREE_SHA1
    if audit._object_exists(audit.BASE_MAIN_SHA):
        workflow_diff = subprocess.run(
            ["git", "diff", "--exit-code", audit.BASE_MAIN_SHA, "HEAD", "--", ".github/workflows"],
            cwd=audit.ROOT, capture_output=True,
        )
        assert workflow_diff.returncode == 0, workflow_diff.stderr.decode("utf-8", "replace")
        ledger_base_oid = audit._git(
            "rev-parse", f"{audit.BASE_MAIN_SHA}:{audit.EVOLUTION_PATH}"
        ).decode().strip()
        assert audit._worktree_blob(audit.EVOLUTION_PATH) == ledger_base_oid
    working_diff = subprocess.run(
        ["git", "diff", "--exit-code", "--", ".github/workflows"],
        cwd=audit.ROOT, capture_output=True,
    )
    assert working_diff.returncode == 0, working_diff.stderr.decode("utf-8", "replace")
    ledger = audit._read_repo_json(audit.EVOLUTION_PATH)
    assert ledger["canonical_sha256"] == audit.EVOLUTION_LEDGER_SHA256
    assert len(ledger["transitions"]) == 13
    assert audit._worktree_blob(audit.EVOLUTION_PATH) == audit._git(
        "rev-parse", f"HEAD:{audit.EVOLUTION_PATH}"
    ).decode().strip()
