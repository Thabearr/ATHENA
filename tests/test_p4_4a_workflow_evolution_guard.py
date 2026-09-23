"""P4.4A receipt, historical continuity, and zero-workflow-change checks."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import audit_p4_4a_workflow_evolution_guard as audit
from scripts import audit_p4_workflow_evolution_ledger as evolution
from scripts import audit_p4_3_workflow_retirement_ledger as retirement
from scripts import audit_p4_3a_workflow_capability_census as p43a
from scripts import audit_p4_3b_current_sportybet_workflow_retirement as p43b
from scripts import audit_p4_3c_spent_v1_evidence_workflow_retirement as p43c
from scripts import audit_p4_3d_retirement_audit_extensibility as p43d
from scripts import audit_p4_2_athena_run_workflow as p42


def test_p44a_receipt_and_zero_transition_checkpoint() -> None:
    receipt = audit.check()
    ledger = evolution.validate_current_state()
    assert receipt["canonical_sha256"] == retirement.canonical_sha256(receipt)
    assert receipt["workflow_evolution_ledger_sha256"] == ledger["canonical_sha256"]
    assert receipt["workflow_evolution_transition_count"] == len(ledger["transitions"]) == 0
    assert receipt["live_workflow_count_before"] == receipt["live_workflow_count_after"] == 37
    assert receipt["workflow_tree_before_sha1"] == receipt["workflow_tree_after_sha1"] == evolution.BASE_WORKFLOW_TREE_SHA1
    assert receipt["p4_4a_exit_gate_satisfied"] is True
    assert receipt["p4_4_overall_complete"] is False
    assert receipt["architecture_checkpoint_e_fully_claimed"] is False
    assert receipt["source_review_counter_while_unmerged"] == "0/5"
    assert receipt["source_review_counter_if_merged"] == "1/5"
    assert not Path(".github/workflows/athena-ingest.yml").exists()


def test_immutable_history_and_current_retirement_state() -> None:
    history = retirement.validate_retirement_history()
    assert history["current_retired_workflow_count"] == 3
    assert history["current_live_workflow_count"] == 37
    for key, (path, sha) in audit.FROZEN_SHA.items():
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        assert payload["canonical_sha256"] == sha == retirement.canonical_sha256(payload), key
    assert len(retirement.load_baseline()[0]["workflow_rows"]) == 40


def test_workflow_yaml_tree_and_protected_paths_are_unchanged() -> None:
    ledger = evolution.validate_current_state()
    assert ledger["current_workflow_tree_sha1"] == evolution.BASE_WORKFLOW_TREE_SHA1
    assert len(list(Path(".github/workflows").glob("*.yml"))) == 37
    assert not evolution._git("diff", "--", ".github/workflows")
    baseline = evolution.baseline_state(retirement.validate_retirement_history())
    for path in evolution.PROTECTED:
        assert path in baseline
        raw = Path(path).read_bytes().replace(b"\r\n", b"\n")
        assert evolution.source_identity(raw) == baseline[path]


def test_historical_audits_accept_the_new_current_state() -> None:
    assert p43a.check(write_receipt=False)["matrix_row_count"] == 40
    assert p43b.check()["canonical_sha256"] == retirement.P43B_RECEIPT_SHA256
    assert p43c.check()["canonical_sha256"] == retirement.P43C_RECEIPT_SHA256
    assert p43d.check()["canonical_sha256"] == evolution.P43D_RECEIPT_SHA256
    p42.verify_committed_receipt()


def test_receipt_cannot_claim_live_or_sensitive_authority() -> None:
    receipt = audit.check()
    for field in (
        "workflow_yaml_changed", "workflow_added", "workflow_revised", "workflow_deleted",
        "athena_ingest_workflow_created", "p4_4_ingest_live_acquisition_enabled",
        "p4_4_scheduled_acquisition_enabled", "provider_acquisition", "workflow_dispatch_triggered",
        "current_shadow_triggered", "fresh_holdout_triggered", "p3_0_e1_triggered",
        "real_share_code_operation", "login", "cookies", "wallet", "staking", "wager_placed",
        "model_formula_changed", "router_formula_changed", "portfolio_formula_changed",
        "provider_semantics_changed", "authority_semantics_changed",
    ):
        assert receipt[field] is False, field


def test_offline_audit_does_not_need_network(monkeypatch: pytest.MonkeyPatch) -> None:
    import socket
    attempts = []
    def forbidden(*args, **kwargs):
        attempts.append((args, kwargs))
        raise AssertionError("network access forbidden")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    assert audit.check()["p4_4a_exit_gate_satisfied"] is True
    assert attempts == []
