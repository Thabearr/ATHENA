"""P4.4A receipt, historical continuity, and zero-workflow-change checks."""
from __future__ import annotations

import copy
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

P44A_RECEIPT_SHA256 = "bd0471dc34327a16f1d501297d57017f90d535c25fbf418c772551d99d287720"
EVOLUTION_CHECKPOINT_SHA256 = "92f2e8a3dd4255bbf5dd75e6dbdd9878f4938ec91c22751e228bb079ffe32e9f"


def test_p44a_receipt_and_zero_transition_checkpoint() -> None:
    receipt = audit.check()
    ledger = evolution.validate_current_state()
    snapshot_bytes = audit.EVOLUTION_SNAPSHOT_PATH.read_bytes()
    current_bytes = evolution.LEDGER_PATH.read_bytes()
    snapshot = json.loads(snapshot_bytes)
    assert receipt["canonical_sha256"] == retirement.canonical_sha256(receipt)
    assert receipt["canonical_sha256"] == P44A_RECEIPT_SHA256
    assert receipt["workflow_evolution_checkpoint_path"] == audit.EVOLUTION_SNAPSHOT_PATH.as_posix()
    assert receipt["workflow_evolution_checkpoint_sha256"] == EVOLUTION_CHECKPOINT_SHA256
    assert receipt["current_workflow_evolution_ledger_sha256"] == EVOLUTION_CHECKPOINT_SHA256
    assert ledger["canonical_sha256"] == evolution.canonical_sha256(ledger)
    assert snapshot["canonical_sha256"] == EVOLUTION_CHECKPOINT_SHA256
    assert evolution.canonical_sha256(snapshot) == EVOLUTION_CHECKPOINT_SHA256
    assert snapshot["transitions"] == []
    assert snapshot["current_live_workflow_count"] == 37
    assert snapshot_bytes != current_bytes
    assert receipt["workflow_evolution_transition_count"] == 0
    assert len(ledger["transitions"]) == 2
    assert ledger["current_workflow_tree_sha1"] == "a40328bdc4d73de7c2bc152b8fb810dcbb439f8c"
    assert receipt["live_workflow_count_before"] == receipt["live_workflow_count_after"] == 37
    assert receipt["workflow_tree_before_sha1"] == receipt["workflow_tree_after_sha1"] == evolution.BASE_WORKFLOW_TREE_SHA1
    assert receipt["p4_4a_exit_gate_satisfied"] is True
    assert receipt["p4_4_overall_complete"] is False
    assert receipt["architecture_checkpoint_e_fully_claimed"] is False
    assert receipt["source_review_counter_while_unmerged"] == "0/5"
    assert receipt["source_review_counter_if_merged"] == "1/5"
    assert not Path(".github/workflows/athena-ingest.yml").exists()


def _synthetic_p43_extension():
    base = retirement._load_p43c_ledger_snapshot()
    current = copy.deepcopy(base)
    row = next(
        item for item in retirement.load_baseline()[0]["workflow_rows"]
        if item["workflow_path"] == ".github/workflows/athena-draft-ready-bridge.yml"
    )
    entry = {
        "workflow_path": row["workflow_path"],
        "git_blob_sha1": row["git_blob_sha1"],
        "source_sha256": row["source_sha256"],
        "fixture_path": "tests/fixtures/architecture/retired_workflows/synthetic-p43-test.yml",
        "retirement_phase": "P4.3_TEST_ONLY",
        "retirement_receipt_path": "artifacts/architecture/p4_3_test_only_retirement.json",
        "successor_workflow_path": ".github/workflows/athena-run.yml",
    }
    current["retirements"] = sorted([*current["retirements"], entry], key=lambda item: item["workflow_path"])
    current["retired_workflow_paths"] = sorted([*current["retired_workflow_paths"], row["workflow_path"]])
    current["current_retired_workflow_count"] = 4
    current["current_live_workflow_count"] = 36
    current["canonical_sha256"] = retirement.canonical_sha256(current)
    return base, current, entry


def _synthetic_evolution_after_p43(current_p43):
    current = json.loads(audit.EVOLUTION_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    current["current_p4_3_retired_workflow_count"] = 4
    current["current_p4_3_retirement_ledger_sha256"] = current_p43["canonical_sha256"]
    current["current_p4_3_retirement_ledger_snapshot_path"] = "artifacts/architecture/p4_3_retirement_ledger_snapshots/p4_3d_synthetic_test.json"
    current["current_p4_3_retirement_ledger_snapshot_sha256"] = current_p43["canonical_sha256"]
    current["current_live_workflow_count"] = 36
    current["current_workflow_tree_sha1"] = "2" * 40
    current["canonical_sha256"] = evolution.canonical_sha256(current)
    return current


def test_immutable_history_and_current_retirement_state() -> None:
    history = retirement.validate_retirement_history()
    assert history["canonical_sha256"] == retirement.P43C_LEDGER_SNAPSHOT_SHA256
    assert retirement.LEDGER_PATH.read_bytes() == retirement.P43C_LEDGER_SNAPSHOT_PATH.read_bytes()
    assert history["current_retired_workflow_count"] == 3
    assert history["current_live_workflow_count"] == 37
    for key, (path, sha) in audit.FROZEN_SHA.items():
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        assert payload["canonical_sha256"] == sha == retirement.canonical_sha256(payload), key
    assert len(retirement.load_baseline()[0]["workflow_rows"]) == 40


def test_workflow_yaml_tree_and_protected_paths_are_unchanged() -> None:
    ledger = evolution.validate_current_state()
    assert ledger["current_workflow_tree_sha1"] == "a40328bdc4d73de7c2bc152b8fb810dcbb439f8c"
    assert len(list(Path(".github/workflows").glob("*.yml"))) == 37
    assert not evolution._git("diff", "--", ".github/workflows")
    baseline = evolution.baseline_state(retirement.validate_retirement_history())
    latest = {
        item["workflow_path"]: item["after"]
        for item in ledger["transitions"]
    }
    for path in evolution.PROTECTED:
        assert path in baseline
        raw = Path(path).read_bytes().replace(b"\r\n", b"\n")
        assert evolution.source_identity(raw) == latest.get(path, baseline[path])


def test_historical_audits_accept_the_new_current_state() -> None:
    assert p43a.check(write_receipt=False)["matrix_row_count"] == 40
    assert p43b.check()["canonical_sha256"] == retirement.P43B_RECEIPT_SHA256
    assert p43c.check()["canonical_sha256"] == retirement.P43C_RECEIPT_SHA256
    assert p43d.check()["canonical_sha256"] == evolution.P43D_RECEIPT_SHA256
    p42.verify_committed_receipt()


def test_p44a_historical_audit_accepts_future_reviewed_p43_retirement() -> None:
    receipt_bytes = audit.RECEIPT_PATH.read_bytes()
    receipt = json.loads(receipt_bytes)
    base_p43, current_p43, entry = _synthetic_p43_extension()
    expected_entries = [*retirement._expected_entries(), entry]
    retirement.validate_reviewed_retirement_entries(base_p43, current_p43, expected_entries=expected_entries)
    current_evolution = _synthetic_evolution_after_p43(current_p43)
    snapshot = json.loads(audit.EVOLUTION_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    audit.verify_historical_checkpoint(
        receipt,
        snapshot,
        current_evolution,
        current_p43,
        base_p43,
        current_p43,
    )
    assert receipt["live_workflow_count_after"] == 37
    assert receipt["workflow_evolution_transition_count"] == 0
    assert current_evolution["current_live_workflow_count"] == 36
    assert current_evolution["canonical_sha256"] != receipt["workflow_evolution_checkpoint_sha256"]
    with pytest.raises(retirement.RetirementLedgerError, match="reviewed evidence"):
        retirement.validate_reviewed_retirement_entries(
            base_p43, current_p43, expected_entries=retirement._expected_entries()
        )
    changed = copy.deepcopy(current_p43)
    historical_path = base_p43["retired_workflow_paths"][0]
    changed_entry = next(entry for entry in changed["retirements"] if entry["workflow_path"] == historical_path)
    changed_entry["source_sha256"] = "f" * 64
    changed["canonical_sha256"] = retirement.canonical_sha256(changed)
    with pytest.raises(retirement.RetirementLedgerError):
        audit.verify_historical_checkpoint(
            receipt,
            snapshot,
            current_evolution,
            changed,
            base_p43,
            changed,
        )
    assert audit.RECEIPT_PATH.read_bytes() == receipt_bytes


def test_p44a_historical_audit_accepts_future_reviewed_ingest_add() -> None:
    receipt_bytes = audit.RECEIPT_PATH.read_bytes()
    receipt = json.loads(receipt_bytes)
    p43 = retirement._load_p43c_ledger_snapshot()
    snapshot = json.loads(audit.EVOLUTION_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    after_raw = b"name: synthetic reviewed ingest\n"
    after = evolution.source_identity(after_raw)
    transition = {
        "transition_id": "P44B_SYNTHETIC_ADD",
        "operation": "ADD",
        "workflow_path": ".github/workflows/athena-ingest.yml",
        "before": None,
        "after": after,
        "phase_id": "P4.4B_TEST_ONLY",
        "canonical_family": "ATHENA_INGEST",
        "evidence_receipt_path": "artifacts/architecture/p4_4b_synthetic_evidence.json",
        "checkpoint_snapshot_path": "artifacts/architecture/p4_workflow_evolution_snapshots/p4_4b_synthetic_add.json",
        "evidence_body_sha256": "",
    }
    intent = {key: value for key, value in transition.items() if key != "evidence_body_sha256"}
    phase_receipt = {
        "schema_version": 1,
        "policy_id": "ATHENA_SYNTHETIC_TEST_ONLY",
        "reviewed_workflow_transition": intent,
        "workflow_evolution_ledger_sha256": "0" * 64,
    }
    transition["evidence_body_sha256"] = evolution.receipt_evidence_body_sha256(phase_receipt)
    phase_snapshot = copy.deepcopy(snapshot)
    phase_snapshot["transitions"] = [transition]
    phase_snapshot["current_live_workflow_count"] = 38
    phase_snapshot["current_workflow_tree_sha1"] = "3" * 40
    phase_snapshot["canonical_sha256"] = evolution.canonical_sha256(phase_snapshot)
    phase_receipt["workflow_evolution_ledger_sha256"] = phase_snapshot["canonical_sha256"]
    phase_receipt["canonical_sha256"] = evolution.canonical_sha256(phase_receipt)
    current = copy.deepcopy(phase_snapshot)
    current["current_workflow_tree_sha1"] = "4" * 40
    current["canonical_sha256"] = evolution.canonical_sha256(current)
    evolution.validate_transition_checkpoints(
        [transition],
        current,
        receipts={transition["evidence_receipt_path"]: phase_receipt},
        snapshots={transition["checkpoint_snapshot_path"]: phase_snapshot},
        current_retirement=p43,
        current_retirement_snapshot=p43,
    )
    derived = evolution.apply_transitions(
        evolution.baseline_state(p43),
        [transition],
        frozen_baseline_paths={row["workflow_path"] for row in retirement.load_baseline()[0]["workflow_rows"]},
        evidence_receipts={transition["evidence_receipt_path"]: phase_receipt},
    )
    assert derived[transition["workflow_path"]] == after
    audit.verify_historical_checkpoint(receipt, snapshot, current, p43, p43, p43)
    assert receipt["workflow_evolution_transition_count"] == 0
    assert receipt["live_workflow_count_after"] == 37
    assert current["current_live_workflow_count"] == 38
    assert current["canonical_sha256"] != receipt["workflow_evolution_checkpoint_sha256"]
    mutated_snapshot = copy.deepcopy(snapshot)
    mutated_snapshot["base_main_sha"] = "0" * 40
    mutated_snapshot["canonical_sha256"] = evolution.canonical_sha256(mutated_snapshot)
    with pytest.raises(AssertionError):
        audit.verify_historical_checkpoint(receipt, mutated_snapshot, current, p43, p43, p43)
    assert audit.RECEIPT_PATH.read_bytes() == receipt_bytes


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
