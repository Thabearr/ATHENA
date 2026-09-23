from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import socket
from urllib import request as urllib_request

import pytest

from scripts import (
    audit_p4_2_athena_run_workflow as p42,
    audit_p4_3_workflow_retirement_ledger as ledger,
    audit_p4_3a_workflow_capability_census as p43a,
    audit_p4_3b_current_sportybet_workflow_retirement as p43b,
    audit_p4_3c_spent_v1_evidence_workflow_retirement as p43c,
    audit_p4_3d_retirement_audit_extensibility as audit,
)


PROTECTED = (
    ".github/workflows/athena-run.yml",
    ".github/workflows/current-shadow-all-market.yml",
    ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml",
    ".github/workflows/watch-fotmob-fresh-holdout-scheduler-liveness.yml",
    ".github/workflows/bridge-fotmob-fresh-holdout-continuity-receipts.yml",
    ".github/workflows/fotmob-utc-native-xg-fresh-holdout-release-receipts.yml",
    ".github/workflows/execute-fotmob-utc-native-successor-feature-qualification-v2.yml",
    ".github/workflows/execute-pr69-primary-time-basis-evidence-campaign-v2.yml",
    ".github/workflows/athena-draft-ready-bridge.yml",
)


def _synthetic_extension(snapshot: dict) -> dict:
    current = copy.deepcopy(snapshot)
    matrix, _ = ledger.load_baseline()
    path = ".github/workflows/athena-draft-ready-bridge.yml"
    row = next(item for item in matrix["workflow_rows"] if item["workflow_path"] == path)
    current["retirements"].append({
        "workflow_path": path,
        "git_blob_sha1": row["git_blob_sha1"],
        "source_sha256": row["source_sha256"],
        "fixture_path": "tests/fixtures/architecture/retired_workflows/p4-3d-synthetic.yml",
        "retirement_phase": "P4.3D_TEST_ONLY",
        "retirement_receipt_path": "artifacts/architecture/p4_3d_synthetic_test_only.json",
        "retirement_receipt_sha256": "a" * 64,
        "successor_workflow_path": ".github/workflows/athena-run.yml",
    })
    current["retirements"].sort(key=lambda item: item["workflow_path"])
    current["retired_workflow_paths"] = sorted(item["workflow_path"] for item in current["retirements"])
    current["current_retired_workflow_count"] = len(current["retirements"])
    current["current_live_workflow_count"] = current["baseline_workflow_count"] - len(current["retirements"])
    current["canonical_sha256"] = ledger.canonical_sha256(current)
    return current


def test_p43c_snapshot_and_receipts_remain_frozen() -> None:
    snapshot_bytes = ledger.P43C_LEDGER_SNAPSHOT_PATH.read_bytes()
    current_bytes = ledger.LEDGER_PATH.read_bytes()
    snapshot = json.loads(snapshot_bytes)
    current = ledger.validate_ledger()
    matrix, census = ledger.load_baseline()
    p43c_receipt = json.loads(p43c.RECEIPT_PATH.read_text(encoding="utf-8"))

    assert snapshot_bytes == current_bytes
    assert snapshot["canonical_sha256"] == ledger.P43C_LEDGER_SNAPSHOT_SHA256 == audit.LEDGER_SHA
    assert ledger.canonical_sha256(snapshot) == audit.LEDGER_SHA
    assert current["canonical_sha256"] == audit.LEDGER_SHA
    assert p43c_receipt["canonical_sha256"] == audit.P43C_SHA
    assert p43c_receipt["retirement_ledger_sha256"] == snapshot["canonical_sha256"]
    assert matrix["workflow_count"] == len(matrix["workflow_rows"]) == 40
    assert census["canonical_sha256"] == audit.P43A_RECEIPT_SHA


def test_current_checkpoint_counts_and_workflow_tree_are_unchanged() -> None:
    current = ledger.validate_ledger()
    live = sorted(path.as_posix() for path in Path(".github/workflows").glob("*.yml"))
    assert len(live) == current["current_live_workflow_count"] == 37
    assert current["current_retired_workflow_count"] == len(current["retirements"]) == 3
    assert len(ledger.load_baseline()[0]["workflow_rows"]) == 40
    assert audit._live_paths_at(audit.BASE_MAIN_SHA) == live == audit._live_paths_at("HEAD")
    assert not audit._git("diff", audit.BASE_MAIN_SHA, "HEAD", "--", ".github/workflows")
    assert not audit._git("diff", "--", ".github/workflows")


def test_p43a_current_count_uses_ledger_not_permanent_37() -> None:
    source = Path("scripts/audit_p4_3a_workflow_capability_census.py").read_text(encoding="utf-8")
    assert "expected_current_count = 40 - len(retired_paths)" in source
    assert "len(surviving_paths) != 37" not in source
    assert "len(worktree_paths) != 37" not in source
    receipt = p43a.check(write_receipt=False)
    assert receipt["matrix_row_count"] == 40


def test_snapshot_extension_accepts_equality_and_test_only_append_without_receipt_rewrite() -> None:
    snapshot = json.loads(ledger.P43C_LEDGER_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    current = ledger.validate_ledger()
    ledger.validate_historical_snapshot_extension(snapshot, current)
    synthetic = _synthetic_extension(snapshot)
    ledger.validate_historical_snapshot_extension(snapshot, synthetic)
    receipt = json.loads(p43c.RECEIPT_PATH.read_text(encoding="utf-8"))
    assert synthetic["current_retired_workflow_count"] == 4
    assert synthetic["current_live_workflow_count"] == 36
    assert receipt["retirement_ledger_sha256"] == snapshot["canonical_sha256"]
    assert receipt["retirement_ledger_sha256"] != synthetic["canonical_sha256"]


def test_p43c_audit_is_frozen_and_keeps_verifying_v1_fixtures_and_v2_identities() -> None:
    before = p43c.RECEIPT_PATH.read_bytes()
    receipt = p43c.check()
    assert receipt["canonical_sha256"] == audit.P43C_SHA
    assert receipt["workflow_count_before"] == 39
    assert receipt["workflow_count_after"] == 37
    assert receipt["workflow_count_decreased_by"] == 2
    assert receipt["cumulative_retired_workflow_count"] == 3
    for path in sorted(p43c.TARGETS):
        proof = p43c.verify_target(path)
        assert proof["historical_fixture_sha256"] == p43c.TARGETS[path]["source_sha256"]
        assert proof["successor_v2"]["required_reconciliation_bindings_verified"] is True
    with pytest.raises(p43c.P43CRetirementError, match="write mode is disabled"):
        p43c.check(write=True)
    assert p43c.RECEIPT_PATH.read_bytes() == before


def test_reviewed_source_resolver_loads_live_and_retired_sources_and_rejects_unknown() -> None:
    current = ledger.validate_ledger()
    live_path = ".github/workflows/athena-run.yml"
    retired_path = ".github/workflows/current-sportybet-accumulator.yml"
    live = ledger.resolve_reviewed_workflow_source(live_path, ledger=current)
    retired = ledger.resolve_reviewed_workflow_source(retired_path, ledger=current)
    assert hashlib.sha256(live).hexdigest() == next(
        row["source_sha256"] for row in ledger.load_baseline()[0]["workflow_rows"] if row["workflow_path"] == live_path
    )
    assert hashlib.sha256(retired).hexdigest() == ledger.RETIRED[retired_path]["source_sha256"]
    with pytest.raises(ledger.RetirementLedgerError, match="absent from the frozen P4.3A matrix"):
        ledger.resolve_reviewed_workflow_source(".github/workflows/unreviewed.yml", ledger=current)


def test_reviewed_source_resolver_rejects_fixture_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    current = ledger.validate_ledger()
    fixture = Path(ledger.RETIRED[".github/workflows/current-sportybet-accumulator.yml"]["fixture_path"])
    original = Path.read_bytes

    def changed_bytes(path: Path) -> bytes:
        raw = original(path)
        return raw + b"\n" if path == fixture else raw

    monkeypatch.setattr(Path, "read_bytes", changed_bytes)
    with pytest.raises(ledger.RetirementLedgerError, match="fixture identity differs from baseline"):
        ledger.resolve_reviewed_workflow_source(".github/workflows/current-sportybet-accumulator.yml", ledger=current)


def test_frozen_prior_phase_audits_pass() -> None:
    p43a.check(write_receipt=False)
    p43b.check()
    p42.verify_committed_receipt()
    p42.verify_preserved_historical_sources()
    p42.verify_retired_workflow_historical_fixtures()


def test_protected_and_successor_workflow_blobs_match_base() -> None:
    for path in PROTECTED:
        assert Path(path).is_file()
        assert audit._blob(audit.BASE_MAIN_SHA, path) == audit._blob("HEAD", path)


def test_p43d_receipt_hash_and_no_retirement_state() -> None:
    receipt = audit.check()
    assert receipt["canonical_sha256"] == ledger.canonical_sha256(receipt)
    assert receipt["workflow_yaml_changed"] is False
    assert receipt["workflow_added"] is False
    assert receipt["workflow_deleted"] is False
    assert receipt["retirement_performed"] is False
    assert receipt["live_workflow_count_before"] == receipt["live_workflow_count_after"] == 37
    assert receipt["retired_workflow_count_before"] == receipt["retired_workflow_count_after"] == 3
    assert receipt["p4_3d_exit_gate_satisfied"] is True
    assert receipt["architecture_checkpoint_e_fully_claimed"] is False
    assert receipt["p4_4_started"] is False
    assert receipt["mandatory_source_reread_required_after_merge"] is True
    assert receipt["source_review_counter_while_unmerged"] == "4/5"
    assert receipt["source_review_counter_if_merged"] == "5/5"


def test_p43d_audit_and_all_nested_proofs_make_no_network_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("P4.3D offline audit attempted network access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib_request, "urlopen", forbidden)
    assert audit.check()["network_attempt_count"] == 0


def test_checkpoint_audit_receipt_files_are_byte_identical_to_base() -> None:
    for path in audit.FROZEN_CANONICAL_FILES:
        assert audit._blob(audit.BASE_MAIN_SHA, path) == audit._blob("HEAD", path)
    assert audit._blob(audit.BASE_MAIN_SHA, str(ledger.LEDGER_PATH)) == audit._blob(
        "HEAD", str(ledger.LEDGER_PATH)
    )
