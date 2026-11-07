from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts import audit_p4_3a_workflow_capability_census as audit
from scripts import audit_p4_3_workflow_retirement_ledger as retirement
from scripts import audit_p4_workflow_evolution_ledger as evolution
from scripts import capture_p4_3_workflow_capability_matrix as capture


MATRIX = Path("artifacts/architecture/p4_3_workflow_capability_matrix_v1.json")
RECEIPT = Path("artifacts/architecture/p4_3a_workflow_capability_census_v1.json")


@pytest.fixture(scope="module")
def matrix() -> dict:
    return json.loads(MATRIX.read_text(encoding="utf-8"))


def test_matrix_has_exactly_40_sorted_historical_workflows(matrix: dict) -> None:
    rows = matrix["workflow_rows"]
    assert matrix["workflow_count"] == 40
    assert len(rows) == 40
    assert [row["workflow_path"] for row in rows] == sorted(row["workflow_path"] for row in rows)
    assert len({row["workflow_path"] for row in rows}) == 40
    audit.validate_matrix(matrix)


def test_workflow_tree_unchanged_and_each_row_binds_source_identity(matrix: dict) -> None:
    # The frozen census remains 40 rows; current count follows the validated
    # cumulative ledger instead of being frozen to one later checkpoint.
    audit.validate_matrix(matrix)
    from scripts import audit_p4_3_workflow_retirement_ledger as ledger_audit
    from scripts import audit_p4_workflow_evolution_ledger as evolution_audit

    ledger = ledger_audit.validate_retirement_history()
    evolution = evolution_audit.validate_current_state(retirement_ledger=ledger)
    assert matrix["workflow_count"] == 40
    assert len(audit._worktree_workflows()) == evolution["current_live_workflow_count"]
    assert ledger["current_live_workflow_count"] == 40 - len(ledger["retired_workflow_paths"])


def test_yaml_loader_preserves_github_actions_on_key(matrix: dict) -> None:
    for row in matrix["workflow_rows"]:
        from scripts import audit_p4_3_workflow_retirement_ledger as ledger_audit

        ledger = ledger_audit.validate_ledger()
        raw = ledger_audit.resolve_reviewed_workflow_source(row["workflow_path"], ledger=ledger)
        parsed = yaml.load(raw.decode("utf-8"), Loader=yaml.BaseLoader)
        assert "on" in parsed
        assert isinstance(parsed["on"], dict)
        assert row["trigger_types"] == sorted(parsed["on"].keys())


def test_required_fields_and_controlled_vocabularies(matrix: dict) -> None:
    for row in matrix["workflow_rows"]:
        assert audit.REQUIRED_ROW_FIELDS <= row.keys()
        assert row["successor_family"] in capture.ALLOWED_FAMILIES
        assert row["history_status"] in audit.ALLOWED_HISTORY
        assert row["disposition"] in audit.ALLOWED_DISPOSITIONS
        assert row["retirement_eligible"] is False
        assert row["dependency_evidence"]["consumer_sources"] is not None


def test_no_p4_3a_row_claims_successor_equivalence(matrix: dict) -> None:
    rows = matrix["workflow_rows"]
    assert len(rows) == 40
    assert all(row["capability_mapping"]["equivalence_claimed"] is False for row in rows)
    assert sum(row["capability_mapping"]["equivalence_claimed"] is True for row in rows) == 0

    for row in rows:
        if row["successor_family"] in {
            "ATHENA_INGEST_FUTURE", "ATHENA_RETRAIN_FUTURE", "ATHENA_BACKTEST_FUTURE",
            "RETAIN_PENDING_AUDIT", "PROTECTED_RESEARCH",
        } or row["disposition"] in {
            "RETAIN_HISTORICAL_EVIDENCE_PENDING_AUDIT", "RETAIN_PROTECTED_RESEARCH",
        }:
            assert row["capability_mapping"]["equivalence_claimed"] is False


def test_auditor_names_workflow_with_false_equivalence_claim(matrix: dict) -> None:
    corrupted = dict(matrix)
    corrupted["workflow_rows"] = [dict(row) for row in matrix["workflow_rows"]]
    row = corrupted["workflow_rows"][0]
    row["capability_mapping"] = dict(row["capability_mapping"], equivalence_claimed=True)
    corrupted["canonical_sha256"] = capture.canonical_sha256(corrupted)
    with pytest.raises(AssertionError, match=row["workflow_path"]):
        audit.validate_matrix(corrupted)


def test_all_without_success_rows_require_owner_review(matrix: dict) -> None:
    rows = matrix["workflow_rows"]
    no_success = [r for r in rows if r["history_status"] != "HAS_SUCCESSFUL_RUN"]
    assert len(no_success) == 5
    assert all(r["owner_review_required"] is True for r in no_success)
    assert all(r["retirement_eligible"] is False for r in no_success)
    assert {r["workflow_path"] for r in no_success} == {
        ".github/workflows/athena-run.yml",
        ".github/workflows/athena-draft-ready-bridge.yml",
        ".github/workflows/current-sportybet-accumulator.yml",
        ".github/workflows/execute-fotmob-utc-native-successor-feature-qualification.yml",
        ".github/workflows/execute-pr69-primary-time-basis-evidence-campaign.yml",
    }
    for row in no_success:
        if row["latest_run"] is not None:
            assert row["latest_run"]["run_id"] > 0
            assert row["latest_run"]["url"]
            assert row["latest_run"]["conclusion"] != "success"


def test_current_sportybet_no_run_blocker_is_captured_honestly(matrix: dict) -> None:
    row = next(r for r in matrix["workflow_rows"] if r["workflow_path"].endswith("current-sportybet-accumulator.yml"))
    assert row["history_status"] == "NO_RUN_HISTORY_OWNER_REVIEW_REQUIRED"
    assert row["last_successful_run"] is None
    assert row["latest_run"] is None
    assert row["owner_review_required"] is True
    assert row["retirement_eligible"] is False
    assert row["disposition"] == "RETAIN_NO_RUN_HISTORY_OWNER_REVIEW_REQUIRED"
    assert row["successor_family"] == "ATHENA_RUN"
    assert row["capability_mapping"]["mapping"] == [
        "target_size -> target_legs", "days=today", "target_total_odds=null",
        "bookie=sportybet", "profile=main",
    ]
    assert row["capability_mapping"]["equivalence_claimed"] is False
    assert row["dependency_evidence"]["artifact_consumer_exists"] is False
    assert row["dependency_evidence"]["workflow_run_dependency_references"] == []


def test_current_shadow_and_protected_holdout_are_retained(matrix: dict) -> None:
    by_path = {r["workflow_path"]: r for r in matrix["workflow_rows"]}
    shadow = by_path[".github/workflows/current-shadow-all-market.yml"]
    assert shadow["disposition"] == "RETAIN_ACTIVE_PENDING_CANONICAL_SHADOW_MIGRATION"
    assert shadow["successor_family"] == "ATHENA_RUN"
    assert shadow["successor_workflow_path"] == ".github/workflows/athena-run.yml"
    assert shadow["capability_mapping"]["equivalence_claimed"] is False
    assert shadow["retirement_eligible"] is False
    assert len(shadow["retirement_blockers"]) >= 5
    assert shadow["dependency_evidence"]["artifact_consumer_exists"] is True
    protected = {
        ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml",
        ".github/workflows/watch-fotmob-fresh-holdout-scheduler-liveness.yml",
        ".github/workflows/bridge-fotmob-fresh-holdout-continuity-receipts.yml",
        ".github/workflows/fotmob-utc-native-xg-fresh-holdout-release-receipts.yml",
    }
    for path in protected:
        assert by_path[path]["fresh_holdout_protected"] is True
        assert by_path[path]["disposition"] == "RETAIN_PROTECTED_RESEARCH"
        assert by_path[path]["retirement_eligible"] is False
        assert by_path[path]["capability_mapping"]["equivalence_claimed"] is False
    assert by_path[".github/workflows/athena-run.yml"]["disposition"] == "CANONICAL_RETAIN"
    assert by_path[".github/workflows/athena-run.yml"]["capability_mapping"]["equivalence_claimed"] is False


def test_date_hardcoded_workflows_are_explicit_and_not_supported_roots(matrix: dict) -> None:
    dated = [r for r in matrix["workflow_rows"] if r["date_hardcoded"]]
    assert matrix["date_hardcoded_workflow_count"] == len(dated)
    assert matrix["supported_date_hardcoded_workflow_count"] == 0
    assert matrix["supported_date_hardcoded_workflows"] == []
    assert all(not r["supported_runtime_root"] for r in dated)


def test_matrix_hash_and_p4_3a_receipt_integrity(matrix: dict) -> None:
    assert capture.canonical_sha256(matrix) == matrix["canonical_sha256"]
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    assert audit.canonical_sha256(receipt) == receipt["canonical_sha256"]
    assert receipt["workflow_matrix_canonical_sha256"] == matrix["canonical_sha256"]
    assert receipt["p4_3a_census_exit_gate_satisfied"] is True
    assert receipt["p4_3_master_retirement_exit_gate_satisfied"] is False
    assert receipt["successor_equivalence_claimed_count"] == 0
    assert receipt["successor_equivalence_proof_deferred_to"] == "P4_3B_OWNER_REVIEWED_WORKFLOW_RETIREMENT_SELECTION_REQUIRED"
    assert receipt["workflow_files_changed"] == []
    assert receipt["workflow_files_deleted"] == []
    assert receipt["workflow_files_added"] == []
    assert receipt["rollback_tag_created"] is False
    assert matrix["captured_at_utc"].endswith("Z")
    assert receipt["rows_with_successful_run"] == 35
    assert receipt["rows_with_no_run_history"] == 2
    assert receipt["rows_with_run_history_without_success"] == 3
    assert receipt["owner_review_required_count"] == 5


def test_offline_auditor_passes_and_historical_inputs_are_unchanged(matrix: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    # If normal tests ever try to call the live capture helper, fail immediately.
    monkeypatch.setattr(capture, "_gh_runs", lambda filename: (_ for _ in ()).throw(AssertionError(filename)))
    audit.validate_matrix(matrix)
    result = audit.check(write_receipt=False)
    assert result["workflow_count"] == 40
    assert result["p4_2_receipt_sha256"] == audit.P42_SHA
    assert result["p4_1_receipt_sha256"] == audit.P41_SHA
    assert result["component_registry_canonical_sha256"] == audit.REGISTRY_SHA


def test_original_p43a_source_uses_first_revision_fixture_in_shallow_checkout(
    matrix: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = ".github/workflows/athena-run.yml"
    row = next(item for item in matrix["workflow_rows"] if item["workflow_path"] == path)
    original = retirement.resolve_reviewed_workflow_source(path)
    fixture_path = "tests/fixtures/architecture/revised_workflows/athena-run-p43a-before.yml"
    transition = {
        "operation": "MAINTENANCE_REVISE",
        "workflow_path": path,
        "before": {
            "git_blob_sha1": row["git_blob_sha1"],
            "source_sha256": row["source_sha256"],
        },
        "historical_before_fixture": {
            "path": fixture_path,
            "git_blob_sha1": row["git_blob_sha1"],
            "source_sha256": row["source_sha256"],
        },
    }
    evolution_ledger = json.loads(
        Path("artifacts/architecture/p4_workflow_evolution_ledger_v1.json").read_text(encoding="utf-8")
    )
    evolution_ledger["transitions"] = [transition]
    monkeypatch.setattr(audit, "_base_object_available", lambda: False)

    resolved = evolution.resolve_p43a_historical_workflow_source(
        path,
        retirement_ledger=retirement.validate_retirement_history(),
        evolution_ledger=evolution_ledger,
        historical_fixture_bytes={fixture_path: original},
    )
    assert resolved == original
    assert evolution.source_identity(resolved) == {
        "git_blob_sha1": row["git_blob_sha1"],
        "source_sha256": row["source_sha256"],
    }
    with pytest.raises(evolution.WorkflowEvolutionError, match="historical fixture bytes differ"):
        evolution.resolve_p43a_historical_workflow_source(
            path,
            retirement_ledger=retirement.validate_retirement_history(),
            evolution_ledger=evolution_ledger,
            historical_fixture_bytes={fixture_path: original + b"one-byte-drift"},
        )
