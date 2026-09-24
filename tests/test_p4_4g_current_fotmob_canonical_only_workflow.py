from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import audit_p4_4g_current_fotmob_canonical_only_workflow as audit
from scripts import audit_p4_workflow_evolution_ledger as evolution


def _receipt() -> dict:
    return audit.expected_receipt()


def _rehash(value: dict) -> None:
    value["canonical_sha256"] = evolution.canonical_sha256(value)


def test_p4_4g_transition_and_cumulative_snapshot_are_exact() -> None:
    ledger, snapshot, receipt = audit.build_evidence()
    transition = ledger["transitions"][5]
    assert snapshot == ledger
    assert len(ledger["transitions"]) == 6
    assert ledger["current_live_workflow_count"] == 38
    assert ledger["current_p4_3_retired_workflow_count"] == 3
    assert transition["transition_id"] == audit.TRANSITION_ID
    assert transition["operation"] == "MAINTENANCE_REVISE"
    assert transition["phase_id"] == "P4.4G"
    assert transition["workflow_path"] == audit.WORKFLOW_PATH
    assert transition["canonical_family"] == "ATHENA_INGEST_FUTURE"
    assert transition["before"] == audit.WORKFLOW_BEFORE
    assert transition["after"] == audit.WORKFLOW_AFTER
    assert transition["maintenance_contract"] == evolution.MAINTENANCE_CONTRACT
    assert transition["historical_before_fixture"]["path"] == audit.FIXTURE_PATH
    assert receipt["workflow_evolution_ledger_sha256"] == ledger["canonical_sha256"]
    assert evolution.receipt_evidence_body_sha256(receipt) == transition["evidence_body_sha256"]
    assert receipt["reviewed_workflow_transition"] == {
        key: value for key, value in transition.items() if key != "evidence_body_sha256"
    }


def test_p4_4g_receipt_binds_history_and_scope_narrowing() -> None:
    receipt = audit.validate_receipt(_receipt())
    assert receipt["workflow_run_history_path"] == audit.HISTORY_PATH.as_posix()
    assert receipt["workflow_run_history_sha256"] == audit.HISTORY_SHA256
    assert receipt["historical_workflow_run_count"] == 12
    assert receipt["historical_workflow_dispatch_run_count"] == 12
    assert receipt["historical_exact_utc_nga_run_count"] == 12
    assert receipt["historical_noncanonical_timezone_or_ccode3_run_count"] == 0
    assert receipt["history_is_not_future_capability_authority"] is True
    assert receipt["legacy_noncanonical_lane_retained"] is False
    assert receipt["legacy_live_issuer_still_reachable_from_workflow"] is False
    assert receipt["legacy_cli_retained"] is True
    assert receipt["legacy_cli_modified"] is False
    assert receipt["legacy_cli_deletion_authorized"] is False
    assert receipt["full_legacy_workflow_equivalence_claimed"] is False
    assert receipt["legacy_workflow_retirement_authorized"] is False
    assert receipt["noncanonical_workflow_request_policy"] == "FAIL_CLOSED_NO_PROVIDER_ACQUISITION"
    assert receipt["noncanonical_failure_receipt_binds_request"] is True
    assert receipt["noncanonical_provider_request_count"] == 0
    assert receipt["workflow_supported_provider_scope_narrowed"] is True
    assert receipt["owner_merge_required_to_activate_scope_narrowing"] is True
    assert receipt["provider_acquisition_during_pr"] is False
    assert receipt["provider_request_count_during_pr"] == 0
    assert receipt["workflow_dispatch_during_pr"] is False
    assert receipt["new_live_operational_proof_required"] is False
    assert receipt["p4_4f_operational_proof_reused"] is True
    assert receipt["source_review_counter_while_unmerged"] == "3/5"
    assert receipt["source_review_counter_if_merged"] == "4/5"
    assert receipt["p4_4_overall_complete"] is False
    assert receipt["architecture_checkpoint_e_complete"] is False
    assert all(receipt[field] is False for field in audit.FALSE_AUTHORITY_FIELDS)


def test_p4_4g_history_evidence_is_exact_utc_nga_only() -> None:
    history = audit._check_history_evidence()
    assert history["api_reported_total_count"] == 12
    assert history["all_api_returned_runs_included"] is True
    assert history["observed_run_count"] == 12
    assert history["successful_run_count"] == 11
    assert history["failed_run_count"] == 1
    assert history["run_inputs_observed_from_authenticated_job_logs"] is True
    assert history["provider_acquisition_performed_by_review"] is False
    assert history["workflow_dispatch_performed_by_review"] is False
    assert {row["timezone"] for row in history["runs"]} == {"UTC"}
    assert {row["ccode3"] for row in history["runs"]} == {"NGA"}


def test_p4_4g_reuses_frozen_p4_4f_operational_proof_without_new_live_action() -> None:
    proof = audit._check_operational_proof()
    assert proof["compositional_operational_proof_complete"] is True
    assert proof["second_live_provider_attempt_performed"] is False
    assert proof["authorization"]["provider_request_budget"] == 1
    assert proof["live_attempt"]["provider_request_count"] == 1
    assert proof["live_attempt"]["retry_count"] == 0
    assert proof["live_attempt"]["workflow_dispatch_count"] == 0
    assert proof["offline_continuation"]["provider_request_count"] == 0
    assert proof["offline_continuation"]["provider_request_count_by_adapter"] == 0
    assert proof["offline_continuation"]["approved_count"] == 26
    assert proof["offline_continuation"]["wager_placed"] is False


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("p4_4f_receipt_sha256", "f" * 64),
        ("p4_4f_workflow_evolution_snapshot_sha256", "f" * 64),
        ("workflow_run_history_sha256", "f" * 64),
        ("workflow_before_identity", {"git_blob_sha1": "0" * 40, "source_sha256": "0" * 64}),
        ("workflow_after_identity", {"git_blob_sha1": "0" * 40, "source_sha256": "0" * 64}),
        ("workflow_count_after", 39),
        ("workflow_tree_sha1_after", "0" * 40),
        ("workflow_evolution_transition_count_after", 5),
        ("transition_operation", "REVISE"),
        ("legacy_noncanonical_lane_retained", True),
        ("legacy_live_issuer_still_reachable_from_workflow", True),
        ("legacy_cli_retained", False),
        ("legacy_cli_deletion_authorized", True),
        ("noncanonical_workflow_request_policy", "LEGACY_NETWORK_FALLBACK"),
        ("noncanonical_failure_receipt_binds_request", False),
        ("noncanonical_provider_request_count", 1),
        ("trigger_surface_changed", True),
        ("provider_acquisition_authority_changed", True),
        ("workflow_supported_provider_scope_narrowed", False),
        ("owner_merge_required_to_activate_scope_narrowing", False),
        ("provider_acquisition_during_pr", True),
        ("provider_request_count_during_pr", 1),
        ("workflow_dispatch_during_pr", True),
        ("new_live_operational_proof_required", True),
        ("p4_4f_operational_proof_reused", False),
        ("source_review_counter_while_unmerged", "4/5"),
        ("source_review_counter_if_merged", "5/5"),
        ("p4_4_overall_complete", True),
        ("architecture_checkpoint_e_complete", True),
        ("reviewed_workflow_transition", {}),
    ] + [(field, True) for field in audit.FALSE_AUTHORITY_FIELDS],
)
def test_self_rehashed_semantic_receipt_mutations_fail(field: str, replacement) -> None:
    mutated = copy.deepcopy(_receipt())
    mutated[field] = replacement
    _rehash(mutated)
    with pytest.raises(audit.P44GCanonicalOnlyWorkflowAuditError):
        audit.validate_receipt(mutated)


def test_exact_receipt_fields_and_duplicate_json_keys_fail(tmp_path: Path) -> None:
    value = copy.deepcopy(_receipt())
    value.pop("workflow_run_history_sha256")
    with pytest.raises(audit.P44GCanonicalOnlyWorkflowAuditError):
        audit.validate_receipt(value)

    raw = audit.canonical_json_bytes(_receipt())
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_bytes(
        raw.replace(
            b'{"acquisition_retry_added":false,',
            b'{"acquisition_retry_added":false,"acquisition_retry_added":false,',
            1,
        )
    )
    with pytest.raises(audit.P44GCanonicalOnlyWorkflowAuditError):
        audit.audit(duplicate, check_live=False)


def test_mutated_history_artifact_fails_closed(monkeypatch, tmp_path: Path) -> None:
    history = copy.deepcopy(audit._check_history_evidence())
    history["runs"][0]["timezone"] = "Europe/London"
    history["canonical_sha256"] = evolution.canonical_sha256(history)
    path = tmp_path / "history.json"
    path.write_bytes(audit.canonical_json_bytes(history))
    monkeypatch.setattr(audit, "HISTORY_PATH", path)
    with pytest.raises(audit.P44GCanonicalOnlyWorkflowAuditError):
        audit._check_history_evidence()


def test_historical_before_fixture_is_exact_p4_4f_workflow_bytes() -> None:
    raw = Path(audit.FIXTURE_PATH).read_bytes()
    assert evolution.source_identity(raw) == audit.WORKFLOW_BEFORE


def test_workflow_contract_is_canonical_or_fail_closed_only() -> None:
    audit._check_workflow_contract()


def test_caller_inventory_has_no_legacy_workflow_live_reference() -> None:
    audit._check_caller_inventory()


def test_p4_4g_live_audit_passes_after_reviewed_commit() -> None:
    receipt = audit.audit()
    assert receipt["canonical_sha256"] == audit.expected_receipt()["canonical_sha256"]


def test_shallow_pr_changed_path_fallback_still_requires_exact_base_event(
    monkeypatch, tmp_path: Path
) -> None:
    event_path = tmp_path / "event.json"
    synthetic_merge_sha = "b" * 40
    event = {
        "pull_request": {
            "base": {"ref": "main", "sha": audit.BASE_MAIN},
            "head": {"sha": "a" * 40},
        }
    }
    event_path.write_text(json.dumps(event), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setenv("GITHUB_SHA", synthetic_merge_sha)

    def fake_run(args, capture_output=False):
        if args[:2] == ["git", "diff"]:
            return SimpleNamespace(returncode=128, stdout=b"", stderr=b"invalid symmetric difference expression")
        if args[:2] == ["git", "cat-file"]:
            return SimpleNamespace(returncode=1, stdout=b"", stderr=b"missing base object")
        if args[1:3] == ["merge-base", "HEAD"]:
            return SimpleNamespace(returncode=1, stdout=b"", stderr=b"missing base object")
        raise AssertionError(args)

    def fake_git(*args):
        if args == ("show", "-s", "--format=%P", "HEAD"):
            return b""
        if args == ("rev-parse", "HEAD"):
            return synthetic_merge_sha.encode("ascii")
        raise AssertionError(args)

    monkeypatch.setattr(audit.subprocess, "run", fake_run)
    monkeypatch.setattr(audit, "_git", fake_git)
    assert audit._changed_paths_from_exact_base() is None

    event["pull_request"]["base"]["sha"] = "c" * 40
    event_path.write_text(json.dumps(event), encoding="utf-8")
    with pytest.raises(
        audit.P44GCanonicalOnlyWorkflowAuditError,
        match="not based on exact authoritative main",
    ):
        audit._changed_paths_from_exact_base()
