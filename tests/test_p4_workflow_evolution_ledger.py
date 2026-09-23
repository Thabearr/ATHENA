"""Fail-closed, offline tests for post-P4.3 workflow evolution authority."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts import audit_p4_workflow_evolution_ledger as audit
from scripts import audit_p4_3_workflow_retirement_ledger as retirement


NEW_PATH = ".github/workflows/athena-ingest.yml"
EVIDENCE_PATH = "artifacts/architecture/p4_4b_ingest_evidence_v1.json"
FIXTURE = "tests/fixtures/architecture/retired_workflows/athena-ingest.yml"


def _baseline() -> tuple[dict, set[str]]:
    history = retirement.validate_retirement_history()
    matrix, _ = retirement.load_baseline()
    return audit.baseline_state(history), {row["workflow_path"] for row in matrix["workflow_rows"]}


def _transition(operation: str, *, path: str = NEW_PATH, before=None, after=None, identifier="P44B_1", fixture=None):
    transition = {
        "transition_id": identifier,
        "operation": operation,
        "workflow_path": path,
        "before": before,
        "after": after,
        "phase_id": "P4.4B",
        "canonical_family": "ATHENA_INGEST",
        "evidence_receipt_path": EVIDENCE_PATH,
        "evidence_body_sha256": "",
    }
    if fixture is not None:
        transition["historical_fixture"] = fixture
    receipt = {
        "schema_version": 1,
        "policy_id": "SYNTHETIC_TEST_ONLY",
        "reviewed_workflow_transition": {key: value for key, value in transition.items() if key != "evidence_body_sha256"},
        "workflow_evolution_ledger_sha256": "a" * 64,
    }
    transition["evidence_body_sha256"] = audit.receipt_evidence_body_sha256(receipt)
    receipt["canonical_sha256"] = audit.canonical_sha256(receipt)
    return transition, receipt


def _evaluate(transitions, receipts):
    baseline, frozen = _baseline()
    return audit.apply_transitions(baseline, transitions, frozen_baseline_paths=frozen, evidence_receipts=receipts)


def test_initial_ledger_is_exact_37_workflow_checkpoint() -> None:
    ledger = audit.validate_current_state()
    assert ledger["transitions"] == []
    assert ledger["current_live_workflow_count"] == 37
    assert ledger["current_workflow_tree_sha1"] == audit.BASE_WORKFLOW_TREE_SHA1
    assert ledger["canonical_sha256"] == audit.canonical_sha256(ledger)
    assert not Path(NEW_PATH).exists()
    assert retirement.validate_retirement_history()["canonical_sha256"] == audit.BASE_RETIREMENT_LEDGER_SHA256


def test_unreviewed_add_is_rejected_but_exact_reviewed_add_is_accepted() -> None:
    baseline, _ = _baseline()
    invented = dict(baseline)
    new_identity = audit.source_identity(b"name: synthetic ingest\n")
    invented[NEW_PATH] = new_identity
    with pytest.raises(audit.WorkflowEvolutionError, match="live workflow set"):
        audit.validate_current_state(workflow_paths=[*baseline, NEW_PATH])
    with pytest.raises(audit.WorkflowEvolutionError, match="live workflow set"):
        audit.validate_derived_tree(baseline, invented)
    add, receipt = _transition("ADD", after=new_identity)
    derived = _evaluate([add], {EVIDENCE_PATH: receipt})
    assert derived == invented
    audit.validate_derived_tree(derived, invented)
    assert len(derived) == 38


def test_add_identity_and_reviewed_receipt_are_required() -> None:
    identity = audit.source_identity(b"name: synthetic ingest\n")
    add, receipt = _transition("ADD", after=identity)
    with pytest.raises(audit.WorkflowEvolutionError, match="receipt is required"):
        _evaluate([add], {})
    bad = copy.deepcopy(add)
    bad["after"]["source_sha256"] = "b" * 64
    with pytest.raises(audit.WorkflowEvolutionError, match="exact operation"):
        _evaluate([bad], {EVIDENCE_PATH: receipt})
    with pytest.raises(audit.WorkflowEvolutionError, match="identity"):
        audit.validate_derived_tree({NEW_PATH: identity}, {NEW_PATH: audit.source_identity(b"drift")})


def test_add_existing_baseline_or_duplicate_identifier_fails() -> None:
    baseline, _ = _baseline()
    old_path = ".github/workflows/athena-run.yml"
    add, receipt = _transition("ADD", path=old_path, after=baseline[old_path])
    with pytest.raises(audit.WorkflowEvolutionError, match="already existed or is frozen"):
        _evaluate([add], {EVIDENCE_PATH: receipt})
    first, receipt = _transition("ADD", after=audit.source_identity(b"one"))
    second, _ = _transition("ADD", after=audit.source_identity(b"two"))
    with pytest.raises(audit.WorkflowEvolutionError, match="duplicate"):
        _evaluate([first, second], {EVIDENCE_PATH: receipt})


def test_revise_chains_only_a_ledger_added_path() -> None:
    before = audit.source_identity(b"one")
    after = audit.source_identity(b"two")
    add, add_receipt = _transition("ADD", after=before)
    revise, revise_receipt = _transition("REVISE", before=before, after=after, identifier="P44B_2")
    revise["evidence_receipt_path"] = "artifacts/architecture/p4_4c_revision_evidence_v1.json"
    revise_receipt["reviewed_workflow_transition"]["evidence_receipt_path"] = revise["evidence_receipt_path"]
    revise["evidence_body_sha256"] = audit.receipt_evidence_body_sha256(revise_receipt)
    revise_receipt["canonical_sha256"] = audit.canonical_sha256(revise_receipt)
    receipts = {EVIDENCE_PATH: add_receipt, revise["evidence_receipt_path"]: revise_receipt}
    assert _evaluate([add, revise], receipts)[NEW_PATH] == after
    with pytest.raises(audit.WorkflowEvolutionError, match="live ledger-added"):
        _evaluate([revise, add], receipts)
    wrong = copy.deepcopy(revise)
    wrong["before"] = audit.source_identity(b"wrong")
    with pytest.raises(audit.WorkflowEvolutionError, match="exact operation"):
        _evaluate([add, wrong], receipts)
    with pytest.raises(audit.WorkflowEvolutionError, match="live ledger-added"):
        _evaluate([revise], receipts)


def test_frozen_survivor_cannot_be_revised_or_retired() -> None:
    baseline, _ = _baseline()
    path = ".github/workflows/athena-run.yml"
    revise, receipt = _transition("REVISE", path=path, before=baseline[path], after=audit.source_identity(b"changed"))
    with pytest.raises(audit.WorkflowEvolutionError, match="live ledger-added"):
        _evaluate([revise], {EVIDENCE_PATH: receipt})
    retire, receipt = _transition("RETIRE", path=path, before=baseline[path], fixture={"path": FIXTURE, **baseline[path]})
    with pytest.raises(audit.WorkflowEvolutionError, match="live ledger-added"):
        _evaluate([retire], {EVIDENCE_PATH: receipt})


def test_retire_added_path_requires_exact_fixture_and_before_identity() -> None:
    identity = audit.source_identity(b"one")
    add, add_receipt = _transition("ADD", after=identity)
    retire, retire_receipt = _transition("RETIRE", before=identity, identifier="P44B_2", fixture={"path": FIXTURE, **identity})
    retire["evidence_receipt_path"] = "artifacts/architecture/p4_4c_retirement_evidence_v1.json"
    retire_receipt["reviewed_workflow_transition"]["evidence_receipt_path"] = retire["evidence_receipt_path"]
    retire["evidence_body_sha256"] = audit.receipt_evidence_body_sha256(retire_receipt)
    retire_receipt["canonical_sha256"] = audit.canonical_sha256(retire_receipt)
    receipts = {EVIDENCE_PATH: add_receipt, retire["evidence_receipt_path"]: retire_receipt}
    baseline, _ = _baseline()
    assert _evaluate([add, retire], receipts) == baseline
    drift = copy.deepcopy(retire)
    drift["historical_fixture"]["source_sha256"] = "0" * 64
    with pytest.raises(audit.WorkflowEvolutionError, match="exact operation"):
        _evaluate([add, drift], receipts)


def test_evidence_hash_excludes_only_backlink_and_self_hash() -> None:
    add, receipt = _transition("ADD", after=audit.source_identity(b"one"))
    digest = add["evidence_body_sha256"]
    altered = dict(receipt, workflow_evolution_ledger_sha256="b" * 64)
    altered["canonical_sha256"] = audit.canonical_sha256(altered)
    assert audit.receipt_evidence_body_sha256(altered) == digest
    altered["reviewed_workflow_transition"] = dict(altered["reviewed_workflow_transition"], phase_id="P4.4C")
    assert audit.receipt_evidence_body_sha256(altered) != digest


def test_unknown_or_missing_paths_fail_closed() -> None:
    baseline, _ = _baseline()
    missing = dict(baseline)
    missing.pop(".github/workflows/athena-run.yml")
    with pytest.raises(audit.WorkflowEvolutionError, match="live workflow set"):
        audit.validate_derived_tree(baseline, missing)
    extra = dict(baseline, **{NEW_PATH: audit.source_identity(b"one")})
    with pytest.raises(audit.WorkflowEvolutionError, match="live workflow set"):
        audit.validate_derived_tree(baseline, extra)


def test_baseline_and_ledger_have_frozen_evidence_identity() -> None:
    ledger = json.loads(audit.LEDGER_PATH.read_text(encoding="utf-8"))
    assert ledger["p4_3a_matrix_sha256"] == retirement.MATRIX_SHA256
    assert ledger["p4_3_retirement_ledger_sha256"] == audit.BASE_RETIREMENT_LEDGER_SHA256
    assert ledger["p4_3d_receipt_sha256"] == audit.P43D_RECEIPT_SHA256
