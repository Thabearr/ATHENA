from __future__ import annotations

import copy
import hashlib
import json

import pytest

from scripts import audit_p4_4f_current_fotmob_exact_lane_caller_migration as audit
from scripts import audit_p4_workflow_evolution_ledger as evolution


def _receipt() -> dict:
    return audit.expected_receipt()


def _rehash(value: dict) -> None:
    value["canonical_sha256"] = evolution.canonical_sha256(value)


def test_p4_4f_transition_and_cumulative_snapshot_are_exact() -> None:
    ledger, snapshot, receipt = audit.build_evidence()
    transition = ledger["transitions"][4]
    assert snapshot == ledger
    assert len(ledger["transitions"]) == 5
    assert ledger["current_live_workflow_count"] == 38
    assert ledger["current_p4_3_retired_workflow_count"] == 3
    assert transition["transition_id"] == audit.TRANSITION_ID
    assert transition["operation"] == "MAINTENANCE_REVISE"
    assert transition["phase_id"] == "P4.4F"
    assert transition["workflow_path"] == audit.WORKFLOW_PATH
    assert transition["canonical_family"] == "ATHENA_INGEST_FUTURE"
    assert transition["before"] == audit.WORKFLOW_BEFORE
    assert transition["after"] == audit.WORKFLOW_AFTER
    assert transition["maintenance_contract"] == evolution.MAINTENANCE_CONTRACT
    assert transition["historical_before_fixture"]["path"] == audit.FIXTURE_PATH
    assert transition["historical_before_fixture"]["git_blob_sha1"] == audit.WORKFLOW_BEFORE["git_blob_sha1"]
    assert receipt["workflow_evolution_ledger_sha256"] == ledger["canonical_sha256"]
    assert evolution.receipt_evidence_body_sha256(receipt) == transition["evidence_body_sha256"]
    assert receipt["reviewed_workflow_transition"] == {
        key: value for key, value in transition.items() if key != "evidence_body_sha256"
    }


def test_p4_4f_receipt_is_exact_and_honestly_awaits_operational_proof() -> None:
    receipt = audit.validate_receipt(_receipt())
    assert receipt["migration_scope"] == {
        "date_count": 1,
        "provider": "fotmob",
        "timezone": "UTC",
        "ccode3": "NGA",
    }
    assert receipt["legacy_noncanonical_lane_retained"] is True
    assert receipt["legacy_live_issuer_still_reachable"] is True
    assert receipt["full_legacy_workflow_equivalence_claimed"] is False
    assert receipt["legacy_workflow_retirement_authorized"] is False
    assert receipt["live_behavior_changes_if_merged"] is True
    assert receipt["operational_proof_required"] is True
    assert receipt["operational_proof_completed"] is False
    assert receipt["owner_operational_proof_authorization_received"] is False
    assert receipt["provider_request_count_during_pr"] == 0
    assert receipt["workflow_dispatch_during_pr"] is False
    assert receipt["source_review_counter_while_unmerged"] == "2/5"
    assert receipt["source_review_counter_if_merged"] == "3/5"
    assert all(receipt[field] is False for field in audit.FALSE_AUTHORITY_FIELDS)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("p4_4e_receipt_sha256", "f" * 64),
        ("p4_4d_receipt_sha256", "f" * 64),
        ("workflow_before_identity", {"git_blob_sha1": "0" * 40, "source_sha256": "0" * 64}),
        ("workflow_after_identity", {"git_blob_sha1": "0" * 40, "source_sha256": "0" * 64}),
        ("workflow_count_after", 39),
        ("workflow_tree_sha1_after", "0" * 40),
        ("workflow_evolution_transition_count_after", 6),
        ("transition_operation", "REVISE"),
        ("canonical_family", "ATHENA_INGEST"),
        ("legacy_noncanonical_lane_retained", False),
        ("legacy_live_issuer_still_reachable", False),
        ("full_legacy_workflow_equivalence_claimed", True),
        ("legacy_workflow_retirement_authorized", True),
        ("trigger_surface_changed", True),
        ("provider_acquisition_authority_changed", True),
        ("exact_utc_nga_provider_implementation_changed", False),
        ("live_behavior_changes_if_merged", False),
        ("artifact_name_preserved", False),
        ("artifact_retention_days", 30),
        ("execution_json_path", "somewhere-else"),
        ("canonical_source_copied_or_rewritten", True),
        ("acquisition_retry_added", True),
        ("fallback_after_canonical_acquisition", True),
        ("max_provider_requests_per_dispatch_path", 2),
        ("provider_acquisition_during_pr", True),
        ("provider_request_count_during_pr", 1),
        ("workflow_dispatch_during_pr", True),
        ("operational_proof_required", False),
        ("operational_proof_completed", True),
        ("owner_operational_proof_authorization_received", True),
        ("p4_4_overall_complete", True),
        ("architecture_checkpoint_e_complete", True),
        ("source_review_counter_while_unmerged", "3/5"),
        ("source_review_counter_if_merged", "4/5"),
        ("reviewed_workflow_transition", {}),
    ]
    + [(field, True) for field in audit.FALSE_AUTHORITY_FIELDS],
)
def test_self_rehashed_semantic_receipt_mutations_fail(field: str, replacement) -> None:
    mutated = copy.deepcopy(_receipt())
    mutated[field] = replacement
    _rehash(mutated)
    with pytest.raises(audit.P44FMigrationAuditError):
        audit.validate_receipt(mutated)


def test_exact_receipt_fields_and_duplicate_json_keys_fail(tmp_path) -> None:
    value = copy.deepcopy(_receipt())
    value.pop("operational_proof_required")
    with pytest.raises(audit.P44FMigrationAuditError):
        audit.validate_receipt(value)

    raw = audit.canonical_json_bytes(_receipt())
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_bytes(raw.replace(
        b'{"acquisition_retry_added":false,',
        b'{"acquisition_retry_added":false,"acquisition_retry_added":false,',
        1,
    ))
    with pytest.raises(audit.P44FMigrationAuditError):
        audit.audit(duplicate, check_live=False)


def test_historical_before_fixture_is_exact_git_blob_bytes() -> None:
    from pathlib import Path

    raw = Path(audit.FIXTURE_PATH).read_bytes()
    assert evolution.source_identity(raw) == audit.WORKFLOW_BEFORE


def test_p4_4f_live_audit_passes_after_reviewed_commit() -> None:
    receipt = audit.audit()
    assert receipt["canonical_sha256"] == audit.expected_receipt()["canonical_sha256"]


def test_workflow_contract_checker_enforces_disjoint_lanes() -> None:
    audit._check_workflow_contract()
