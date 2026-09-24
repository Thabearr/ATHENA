from __future__ import annotations

import json
from pathlib import Path

from scripts import audit_p4_3_workflow_retirement_ledger as retirement
from scripts import audit_p4_4b_athena_ingest_workflow as p44b
from scripts import audit_p4_4c_scheduled_ingest_and_migration_review as p44c
from scripts import audit_p4_workflow_evolution_ledger as evolution


def test_migration_review_covers_exact_five_frozen_rows_without_equivalence() -> None:
    review = json.loads(p44c.MIGRATION_PATH.read_text(encoding="utf-8"))
    assert review["canonical_sha256"] == evolution.canonical_sha256(review)
    assert review["p4_3a_matrix_sha256"] == retirement.MATRIX_SHA256
    assert [row["workflow_path"] for row in review["workflow_rows"]] == list(p44c.EXPECTED_PATHS)
    assert review["reviewed_workflow_count"] == 5
    assert review["equivalence_claim_count"] == 0
    assert review["retirement_authorization_count"] == 0
    for row in review["workflow_rows"]:
        assert row["path_exists"] is True
        assert row["frozen_p4_3a_source_identity"] == row["current_live_source_identity"]
        assert row["equivalence_claimed"] is False
        assert row["retirement_authorized"] is False
        assert row["latest_run"] is not None
        assert row["latest_successful_run"] is not None


def test_p4_4c_appends_only_ordinary_ingest_revise_and_preserves_history() -> None:
    receipt = p44c.check()
    ledger = evolution.validate_current_state()
    snapshot = json.loads(p44c.SNAPSHOT_PATH.read_text(encoding="utf-8"))
    p44b_snapshot = json.loads(p44b.SNAPSHOT.read_text(encoding="utf-8"))
    assert ledger["transitions"][:3] == p44b_snapshot["transitions"]
    assert snapshot == ledger
    assert len(ledger["transitions"]) == 4
    transition = ledger["transitions"][3]
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
