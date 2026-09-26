from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts import audit_p4_3_workflow_retirement_ledger as retirement
from scripts import audit_p4_4b_athena_ingest_workflow as p44b
from scripts import audit_p4_4c_scheduled_ingest_and_migration_review as p44c
from scripts import audit_p4_4g_current_fotmob_canonical_only_workflow as p44g
from scripts import audit_p4_workflow_evolution_ledger as evolution


def test_migration_review_covers_exact_five_frozen_rows_without_equivalence() -> None:
    review = json.loads(p44c.MIGRATION_PATH.read_text(encoding="utf-8"))
    assert review["canonical_sha256"] == evolution.canonical_sha256(review)
    assert review["p4_3a_matrix_sha256"] == retirement.MATRIX_SHA256
    assert [row["workflow_path"] for row in review["workflow_rows"]] == list(p44c.EXPECTED_PATHS)
    assert review["reviewed_workflow_count"] == 5
    assert review["equivalence_claim_count"] == 0
    assert review["retirement_authorization_count"] == 0
    assert review["run_history_snapshot"] == {
        "captured_at_utc": p44c.RUN_HISTORY_CAPTURED_AT_UTC,
        "semantics": "LATEST_OBSERVED_AT_CAPTURE_NOT_A_LIVE_POINTER",
        "read_only": True,
        "post_capture_runs_do_not_invalidate_snapshot": True,
    }
    for row in review["workflow_rows"]:
        assert row["path_exists"] is True
        assert row["frozen_p4_3a_source_identity"] == row["current_live_source_identity"]
        assert row["equivalence_claimed"] is False
        assert row["retirement_authorized"] is False
        assert row["latest_run_observed_at_capture"] == p44c.RUN_HISTORY[row["workflow_path"]]["latest_run_observed_at_capture"]
        assert row["latest_successful_run_observed_at_capture"] == p44c.RUN_HISTORY[row["workflow_path"]]["latest_successful_run_observed_at_capture"]


def test_p4_4c_appends_only_ordinary_ingest_revise_and_preserves_history() -> None:
    receipt = p44c.check_historical()
    ledger = evolution.validate_current_state()
    snapshot = json.loads(p44c.SNAPSHOT_PATH.read_text(encoding="utf-8"))
    p44b_snapshot = json.loads(p44b.SNAPSHOT.read_text(encoding="utf-8"))
    assert ledger["transitions"][:3] == p44b_snapshot["transitions"]
    assert ledger["transitions"][:4] == snapshot["transitions"]
    assert len(snapshot["transitions"]) == 4
    assert len(ledger["transitions"]) == 7
    assert ledger["transitions"][5]["transition_id"] == p44g.TRANSITION_ID
    assert ledger["transitions"][6]["transition_id"] == (
        "P44M_ATHENA_RUN_PC_UPCOMING_EVIDENCE_PRESERVATION_V1"
    )
    transition = snapshot["transitions"][3]
    assert transition["transition_id"] == "P44C_ATHENA_INGEST_SCHEDULE_REVISE_V1"
    assert transition["operation"] == "REVISE"
    assert transition["workflow_path"] == ".github/workflows/athena-ingest.yml"
    assert transition["canonical_family"] == "ATHENA_INGEST"
    assert transition["before"] == {
        "git_blob_sha1": p44c.P44B_WORKFLOW_BLOB,
        "source_sha256": p44c.P44B_WORKFLOW_SOURCE,
    }
    assert transition["after"] == p44c._current_identity(transition["workflow_path"])
    assert receipt["workflow_evolution_ledger_sha256"] == snapshot["canonical_sha256"]
    assert receipt["migration_review_artifact_sha256"] == json.loads(
        p44c.MIGRATION_PATH.read_text(encoding="utf-8")
    )["canonical_sha256"]
    assert receipt["scheduled_acquisition_enabled"] is True
    assert receipt["schedule_cron"] == "0 8 * * *"
    assert receipt["scheduled_date_count"] == 1
    assert receipt["scheduled_max_provider_requests"] == 1
    assert receipt["manual_max_dates"] == 7
    assert receipt["acquisition_retry_count"] == 0
    assert receipt["workflow_count_before"] == receipt["workflow_count_after"] == 38
    assert receipt["transition_count_before"] == 3
    assert receipt["transition_count_after"] == 4
    assert receipt["provider_acquisition_during_pr"] is False
    assert receipt["provider_request_count_during_pr"] == 0
    assert receipt["automatic_acquisition_active_on_main_while_pr_open"] is False
    assert receipt["p4_4_overall_complete"] is False
    assert receipt["architecture_checkpoint_e_fully_claimed"] is False


@pytest.mark.parametrize(
    "mutator",
    [
        lambda review, row: row["latest_run_observed_at_capture"].__setitem__("run_id", 1),
        lambda review, row: row["known_workflow_consumers"].append(".github/workflows/unreviewed.yml"),
        lambda review, row: row["artifact_upload_names"].append("invented-artifact"),
        lambda review, row: row.__setitem__("canonical_athena_ingest_coverage_assessment", "equivalent"),
        lambda review, row: row["exact_unresolved_differences"].clear(),
        lambda review, row: row.__setitem__("reviewed_disposition", "RETIRE"),
        lambda review, row: row.__setitem__("equivalence_claimed", True),
        lambda review, row: row.__setitem__("retirement_authorized", True),
    ],
    ids=["run-id", "workflow-consumer", "artifact-name", "coverage", "differences", "disposition", "equivalence", "retirement"],
)
def test_mutated_migration_evidence_fails_even_after_self_hash_recalculation(mutator) -> None:
    review = copy.deepcopy(json.loads(p44c.MIGRATION_PATH.read_text(encoding="utf-8")))
    row = review["workflow_rows"][0]
    mutator(review, row)
    review["canonical_sha256"] = evolution.canonical_sha256(review)
    with pytest.raises(AssertionError):
        p44c._validate_migration_review(review)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_acquisition_trigger_surface_changed", False),
        ("automatic_provider_acquisition_authority_added_if_merged", False),
        ("manual_provider_acquisition_authority_changed", True),
        ("non_ingest_authority_expansion", True),
        ("new_provider_family_added", True),
        ("sportybet_authority_added", True),
        ("model_authority", True),
        ("routing_authority", True),
        ("portfolio_authority", True),
        ("share_code_authority", True),
        ("login", True),
        ("cookies", True),
        ("wallet", True),
        ("staking", True),
        ("wager", True),
        ("backfill_authority", True),
    ],
)
def test_authority_claim_mutations_fail_even_after_receipt_self_hash_recalculation(field, value) -> None:
    receipt = copy.deepcopy(json.loads(p44c.RECEIPT_PATH.read_text(encoding="utf-8")))
    receipt[field] = value
    receipt["canonical_sha256"] = evolution.canonical_sha256(receipt)
    with pytest.raises(AssertionError):
        p44c._validate_receipt_semantics(receipt)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda plan: plan["source_rollback_target"].__setitem__("git_blob_sha1", "0" * 40),
        lambda plan: plan.__setitem__("automatic_legacy_fallback", True),
        lambda plan: plan.__setitem__("backfill_authority", True),
        lambda plan: plan.pop("preserve_migration_review"),
        lambda plan: plan.__setitem__("source_rollback_operation", "RESTORE_WITHOUT_REVIEW"),
    ],
    ids=["rollback-target", "legacy-fallback", "backfill", "missing-preservation", "wrong-operation"],
)
def test_rollback_plan_mutations_fail_even_after_receipt_self_hash_recalculation(mutator) -> None:
    receipt = copy.deepcopy(json.loads(p44c.RECEIPT_PATH.read_text(encoding="utf-8")))
    mutator(receipt["rollback_plan"])
    receipt["canonical_sha256"] = evolution.canonical_sha256(receipt)
    with pytest.raises(AssertionError):
        p44c._validate_receipt_semantics(receipt)


def test_migration_review_does_not_change_retirement_ledger_or_workflow_count() -> None:
    history = retirement.validate_retirement_history()
    current = evolution.validate_current_state()
    assert history["canonical_sha256"] == p44c.P43_LEDGER_SHA256
    assert history["current_retired_workflow_count"] == 3
    assert current["current_live_workflow_count"] == 38
    assert Path(".github/workflows/athena-ingest.yml").is_file()
    assert not any(
        row["retirement_authorized"] or row["equivalence_claimed"]
        for row in json.loads(p44c.MIGRATION_PATH.read_text(encoding="utf-8"))["workflow_rows"]
    )
