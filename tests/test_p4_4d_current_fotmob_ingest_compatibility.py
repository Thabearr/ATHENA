from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import audit_p4_3_workflow_retirement_ledger as retirement
from scripts import audit_p4_4d_current_fotmob_ingest_compatibility as audit


def _receipt() -> dict:
    return json.loads(audit.RECEIPT_PATH.read_text(encoding="utf-8"))


def _rehash(value: dict) -> None:
    unsigned = {key: item for key, item in value.items() if key != "canonical_sha256"}
    value["canonical_sha256"] = hashlib.sha256(
        retirement.canonical_json_bytes(unsigned)
    ).hexdigest()


def test_p4_4d_architecture_receipt_and_live_boundary_pass() -> None:
    receipt = audit.audit()
    assert receipt["repository_base_main_sha"] == audit.BASE_MAIN
    assert receipt["workflow_tree_sha1_before"] == receipt["workflow_tree_sha1_after"]
    assert receipt["workflow_count_before"] == receipt["workflow_count_after"] == 38
    assert receipt["workflow_evolution_transition_count_before"] == receipt["workflow_evolution_transition_count_after"] == 4
    assert receipt["legacy_workflow_retirement_authorized"] is False
    assert receipt["full_legacy_request_contract_equivalence_claimed"] is False


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("p4_4c_receipt_sha256", "f" * 64),
        ("p4_4c_migration_review_sha256", "f" * 64),
        ("workflow_evolution_ledger_sha256", "f" * 64),
        ("p4_3_retirement_ledger_sha256", "f" * 64),
        ("workflow_count_after", 39),
        ("workflow_evolution_transition_count_after", 5),
        ("provider_request_count_by_adapter", 1),
        ("provider_acquisition_during_pr", True),
        ("workflow_dispatch_during_pr", True),
        ("full_legacy_request_contract_equivalence_claimed", True),
        ("noncanonical_timezone_or_ccode3_supported", True),
        ("legacy_workflow_retirement_authorized", True),
        ("legacy_workflow_modified", True),
        ("canonical_ingest_workflow_modified", True),
        ("canonical_ingest_request_schema_modified", True),
        ("model_feature_authority", True),
        ("probability_authority", True),
        ("pricing_authority", True),
        ("routing_authority", True),
        ("portfolio_authority", True),
        ("share_code_authority", True),
        ("login", True),
        ("cookies", True),
        ("wallet", True),
        ("staking", True),
        ("wager", True),
        ("backfill_authority", True),
        ("p4_4_overall_complete", True),
        ("architecture_checkpoint_e_fully_claimed", True),
    ],
)
def test_self_rehashed_semantic_mutations_are_rejected(field: str, replacement) -> None:
    mutated = copy.deepcopy(_receipt())
    if field == "provider_request_count_by_adapter":
        field = "provider_request_count_by_adapter"
    mutated[field] = replacement
    _rehash(mutated)
    with pytest.raises(audit.P44DCompatibilityAuditError):
        audit.validate_receipt(mutated, check_live=False)


def test_workflow_identities_and_evolution_evidence_are_pinned() -> None:
    receipt = _receipt()
    assert receipt["legacy_current_reviewed_workflow_identity"] == audit.LEGACY_IDENTITY
    assert receipt["canonical_ingest_workflow_identity"] == audit.INGEST_IDENTITY
    assert Path(audit.INGEST_PATH).is_file()
    assert audit._source_identity(audit.LEGACY_PATH) == audit.LEGACY_IDENTITY
    assert audit._source_identity(audit.INGEST_PATH) == audit.INGEST_IDENTITY


def test_exact_base_ancestry_accepts_shallow_synthetic_merge_checkout(monkeypatch) -> None:
    monkeypatch.setattr(
        audit.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=128, stdout=b"", stderr=b"missing base object"),
    )
    monkeypatch.setattr(
        audit,
        "_git",
        lambda *args: (audit.BASE_MAIN + " " + "f" * 40).encode("ascii"),
    )

    audit._require_exact_base_ancestry()


def test_exact_base_ancestry_rejects_shallow_checkout_with_wrong_parent(monkeypatch) -> None:
    monkeypatch.setattr(
        audit.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=128, stdout=b"", stderr=b"missing base object"),
    )
    monkeypatch.setattr(
        audit,
        "_git",
        lambda *args: ("e" * 40 + " " + "f" * 40).encode("ascii"),
    )

    with pytest.raises(audit.P44DCompatibilityAuditError, match="not based on exact reviewed main"):
        audit._require_exact_base_ancestry()


def test_exact_base_ancestry_accepts_shallow_pull_request_event_binding(monkeypatch, tmp_path) -> None:
    head_sha = "a" * 40
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps(
            {
                "pull_request": {
                    "base": {"ref": "main", "sha": audit.BASE_MAIN},
                    "head": {"sha": head_sha},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setenv("GITHUB_SHA", head_sha)
    monkeypatch.setattr(
        audit.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=128, stdout=b"", stderr=b"missing base object"),
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


@pytest.mark.parametrize(
    ("base_sha", "current_sha"),
    [("b" * 40, "a" * 40), (audit.BASE_MAIN, "c" * 40)],
)
def test_exact_base_ancestry_rejects_shallow_pull_request_event_mismatch(
    monkeypatch, tmp_path, base_sha: str, current_sha: str
) -> None:
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps(
            {
                "pull_request": {
                    "base": {"ref": "main", "sha": base_sha},
                    "head": {"sha": "a" * 40},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    monkeypatch.setattr(
        audit.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=128, stdout=b"", stderr=b"missing base object"),
    )
    monkeypatch.setattr(
        audit,
        "_git",
        lambda *args: (
            ("e" * 40 + " " + "f" * 40).encode("ascii")
            if args[:3] == ("show", "-s", "--format=%P")
            else current_sha.encode("ascii")
        ),
    )

    with pytest.raises(audit.P44DCompatibilityAuditError, match="not based on exact reviewed main"):
        audit._require_exact_base_ancestry()
