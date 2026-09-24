from __future__ import annotations

import copy
import hashlib
import json

import pytest

from scripts import audit_p4_4e_current_fotmob_ingest_issuer as audit
from scripts import audit_p4_3_workflow_retirement_ledger as retirement


def _receipt() -> dict:
    return json.loads(audit.RECEIPT_PATH.read_text(encoding="utf-8"))


def _rehash(value: dict) -> None:
    unsigned = {key: item for key, item in value.items() if key != "canonical_sha256"}
    value["canonical_sha256"] = hashlib.sha256(
        retirement.canonical_json_bytes(unsigned)
    ).hexdigest()


def test_p4_4e_receipt_and_frozen_architecture_boundary_pass() -> None:
    receipt = audit.audit()
    assert receipt["repository_base_main_sha"] == audit.BASE_MAIN
    assert receipt["p4_4d_receipt_sha256"] == audit.P44D_RECEIPT_SHA256
    assert receipt["workflow_tree_sha1_before"] == receipt["workflow_tree_sha1_after"]
    assert receipt["workflow_count_before"] == receipt["workflow_count_after"] == 38
    assert receipt["workflow_evolution_transition_count_before"] == receipt["workflow_evolution_transition_count_after"] == 4
    assert receipt["workflow_yaml_modified"] is False
    assert receipt["live_caller_migrated"] is False
    assert receipt["legacy_workflow_retirement_authorized"] is False
    assert receipt["full_legacy_workflow_equivalence_claimed"] is False


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("repository_base_main_sha", "f" * 40),
        ("p4_4d_receipt_sha256", "f" * 64),
        ("workflow_tree_sha1_after", "f" * 40),
        ("workflow_count_after", 39),
        ("workflow_evolution_ledger_sha256", "f" * 64),
        ("workflow_evolution_transition_count_after", 5),
        ("p4_3_retirement_ledger_sha256", "f" * 64),
        ("canonical_artifact_root", "somewhere-else"),
        ("issuer_date_count_exact", 2),
        ("successful_path_canonical_provider_request_count", 2),
        ("provider_request_count_by_adapter", 1),
        ("acquisition_retry_count", 1),
        ("published_artifact_overwrite_allowed", True),
        ("source_bytes_copied_by_adapter", True),
        ("source_bytes_rewritten_by_adapter", True),
        ("pr243_policy_bounds_overridable", True),
        ("new_seam_has_cli", True),
        ("new_seam_workflow_caller_count", 1),
        ("exact_main_lineage_required", False),
        ("shared_canonical_ingest_service_used", False),
        ("p4_4d_compatibility_adapter_used", False),
        ("direct_provider_transport_duplicated_by_issuer", True),
        ("workflow_yaml_modified", True),
        ("canonical_ingest_request_schema_modified", True),
        ("canonical_ingest_runtime_modified", True),
        ("legacy_issuer_modified", True),
        ("live_caller_migrated", True),
        ("live_legacy_workflow_activated_on_new_seam", True),
        ("no_supported_live_caller_references_new_issuer", False),
        ("new_issuer_live_caller_count", 1),
        ("provider_acquisition_during_pr", True),
        ("provider_request_count_during_pr", 1),
        ("workflow_dispatch_during_pr", True),
        ("workflow_activation_during_pr", True),
        ("legacy_workflow_retirement_authorized", True),
        ("new_provider_family_authorized", True),
        ("non_ingest_authority_expansion", True),
        ("full_legacy_workflow_equivalence_claimed", True),
        ("noncanonical_timezone_or_ccode3_supported", True),
        ("fixture_selection_authority", True),
        ("fixture_intelligence_fact_authority", True),
        ("fixture_intelligence_snapshot_authority", True),
        ("model_feature_authority", True),
        ("probability_authority", True),
        ("pricing_authority", True),
        ("routing_authority", True),
        ("portfolio_authority", True),
        ("share_code_authority", True),
        ("account_authority", True),
        ("login_authority", True),
        ("cookies_authority", True),
        ("wallet_authority", True),
        ("staking_authority", True),
        ("wager_authority", True),
        ("backfill_authority", True),
        ("p4_4_overall_complete", True),
        ("architecture_checkpoint_e_complete", True),
        ("source_review_counter_while_unmerged", "2/5"),
        ("source_review_counter_if_merged", "3/5"),
    ],
)
def test_self_rehashed_semantic_mutations_fail(field: str, replacement) -> None:
    mutated = copy.deepcopy(_receipt())
    mutated[field] = replacement
    _rehash(mutated)
    with pytest.raises(audit.P44EIngestIssuerAuditError):
        audit.validate_receipt(mutated, check_live=False)


def test_extra_or_missing_receipt_fields_fail() -> None:
    value = copy.deepcopy(_receipt())
    value.pop("live_caller_migrated")
    with pytest.raises(audit.P44EIngestIssuerAuditError):
        audit.validate_receipt(value, check_live=False)


def test_receipt_duplicate_keys_and_noncanonical_bytes_fail(tmp_path) -> None:
    raw = audit.RECEIPT_PATH.read_bytes()
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_bytes(raw.replace(
        b'{"account_authority":false,',
        b'{"account_authority":false,"account_authority":false,',
        1,
    ))
    with pytest.raises(audit.P44EIngestIssuerAuditError):
        audit.audit(duplicate, check_live=False)
    noncanonical = tmp_path / "noncanonical.json"
    noncanonical.write_bytes(b" " + raw)
    with pytest.raises(audit.P44EIngestIssuerAuditError):
        audit.audit(noncanonical, check_live=False)
    value = copy.deepcopy(_receipt())
    value["extra"] = False
    _rehash(value)
    with pytest.raises(audit.P44EIngestIssuerAuditError):
        audit.validate_receipt(value, check_live=False)


def test_protected_source_identities_match_reviewed_base() -> None:
    for path, expected in audit.EXPECTED_IDENTITIES.items():
        assert audit._source_identity(path) == expected


def test_p4_4d_architecture_audit_still_passes() -> None:
    from scripts import audit_p4_4d_current_fotmob_ingest_compatibility as p44d

    # P4.4D's receipt is immutable evidence; its old branch-base ancestry check
    # is not the P4.4E branch ancestry check.
    assert p44d.audit(check_live=False)["canonical_sha256"] == audit.P44D_RECEIPT_SHA256


def test_exact_p4_4e_base_ancestry_accepts_shallow_pr_event(monkeypatch, tmp_path) -> None:
    head_sha = "a" * 40
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps({
            "pull_request": {
                "base": {"ref": "main", "sha": audit.BASE_MAIN},
                "head": {"sha": head_sha},
            }
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setenv("GITHUB_SHA", head_sha)
    monkeypatch.setattr(
        audit.subprocess,
        "run",
        lambda *args, **kwargs: type("Result", (), {"returncode": 128, "stdout": b""})(),
    )
    monkeypatch.setattr(
        audit,
        "_git",
        lambda *args: (
            ("e" * 40 + " " + "f" * 40).encode("ascii")
            if args[:3] == ("show", "-s", "--format=%P")
            else head_sha.encode("ascii")
        ),
    )
    audit._require_exact_base_ancestry()


def test_exact_p4_4e_base_ancestry_rejects_wrong_shallow_pr_event(monkeypatch, tmp_path) -> None:
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps({
            "pull_request": {
                "base": {"ref": "main", "sha": "b" * 40},
                "head": {"sha": "a" * 40},
            }
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    monkeypatch.setattr(
        audit.subprocess,
        "run",
        lambda *args, **kwargs: type("Result", (), {"returncode": 128, "stdout": b""})(),
    )
    monkeypatch.setattr(
        audit,
        "_git",
        lambda *args: ("e" * 40 + " " + "f" * 40).encode("ascii"),
    )
    with pytest.raises(audit.P44EIngestIssuerAuditError, match="not based on exact reviewed main"):
        audit._require_exact_base_ancestry()
