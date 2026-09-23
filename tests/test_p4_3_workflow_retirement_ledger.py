from __future__ import annotations

import json
import copy
from pathlib import Path

import pytest

from scripts import audit_p4_3_workflow_retirement_ledger as audit


def test_cumulative_ledger_counts_are_derived_from_reviewed_entries() -> None:
    ledger = audit.validate_ledger()
    matrix, _ = audit.load_baseline()
    live = sorted(path.as_posix() for path in Path(".github/workflows").glob("*.yml"))
    assert len(matrix["workflow_rows"]) == 40
    reviewed_count = len(ledger["retirements"])
    assert len(live) == ledger["current_live_workflow_count"] == 40 - reviewed_count
    assert ledger["current_retired_workflow_count"] == reviewed_count == 3
    assert set(live) == {row["workflow_path"] for row in matrix["workflow_rows"]} - set(ledger["retired_workflow_paths"])
    assert ledger["retired_workflow_paths"] == sorted(audit.RETIRED)


def test_each_retired_fixture_matches_immutable_matrix_identity() -> None:
    matrix, _ = audit.load_baseline()
    rows = {row["workflow_path"]: row for row in matrix["workflow_rows"]}
    for path, expected in audit.RETIRED.items():
        raw = Path(expected["fixture_path"]).read_bytes()
        assert audit._git_blob_sha1(raw) == expected["git_blob_sha1"] == rows[path]["git_blob_sha1"]
        assert audit._sha256(raw) == expected["source_sha256"] == rows[path]["source_sha256"]
        assert not Path(path).exists()


def test_unreviewed_fourth_disappearance_fails_closed() -> None:
    live = sorted(path.as_posix() for path in Path(".github/workflows").glob("*.yml"))
    with pytest.raises(audit.RetirementLedgerError, match="live workflow set"):
        audit.validate_ledger(workflow_paths=live[:-1])


def test_removing_the_p43b_ledger_entry_fails_closed() -> None:
    payload = json.loads(audit.LEDGER_PATH.read_text(encoding="utf-8"))
    payload["retirements"] = [entry for entry in payload["retirements"] if entry["retirement_phase"] != "P4.3B"]
    payload["canonical_sha256"] = audit.canonical_sha256(payload)
    with pytest.raises(audit.RetirementLedgerError, match="retired path set mismatch"):
        audit.validate_ledger(payload)


def test_ledger_p4_3a_and_p4_3b_receipts_are_immutable() -> None:
    ledger = audit.validate_ledger()
    assert ledger["baseline_matrix_sha256"] == audit.MATRIX_SHA256
    assert ledger["baseline_p4_3a_receipt_sha256"] == audit.P43A_RECEIPT_SHA256
    assert next(item for item in ledger["retirements"] if item["retirement_phase"] == "P4.3B")["retirement_receipt_sha256"] == audit.P43B_RECEIPT_SHA256


def _synthetic_extension(snapshot: dict) -> dict:
    current = copy.deepcopy(snapshot)
    matrix, _ = audit.load_baseline()
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
    current["retirements"].sort(key=lambda entry: entry["workflow_path"])
    current["retired_workflow_paths"] = sorted(entry["workflow_path"] for entry in current["retirements"])
    current["current_retired_workflow_count"] = len(current["retirements"])
    current["current_live_workflow_count"] = current["baseline_workflow_count"] - len(current["retirements"])
    current["canonical_sha256"] = audit.canonical_sha256(current)
    return current


def test_p43c_snapshot_accepts_identical_current_ledger_and_synthetic_extension() -> None:
    snapshot = json.loads(audit.P43C_LEDGER_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    current = audit.validate_ledger()
    audit.validate_historical_snapshot_extension(snapshot, current)
    extended = _synthetic_extension(snapshot)
    audit.validate_historical_snapshot_extension(snapshot, extended)
    assert extended["current_retired_workflow_count"] == 4
    assert extended["current_live_workflow_count"] == 36
    assert extended["canonical_sha256"] != snapshot["canonical_sha256"]
    # The historical receipt remains bound to the immutable snapshot, not this
    # test-only in-memory extension.
    p43c = json.loads(audit.P43C_RECEIPT_PATH.read_text(encoding="utf-8"))
    assert p43c["retirement_ledger_sha256"] == snapshot["canonical_sha256"]


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("fixture_path", "tests/fixtures/architecture/retired_workflows/drift.yml"),
        ("source_sha256", "0" * 64),
        ("git_blob_sha1", "0" * 40),
        ("retirement_phase", "P4.3D_REWRITTEN"),
        ("retirement_receipt_path", "artifacts/architecture/rewritten.json"),
        ("retirement_receipt_sha256", "f" * 64),
        ("successor_workflow_path", ".github/workflows/tests.yml"),
    ],
)
def test_snapshot_extension_rejects_mutated_historical_entry(field: str, replacement: str) -> None:
    snapshot = json.loads(audit.P43C_LEDGER_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    current = copy.deepcopy(snapshot)
    current["retirements"][0][field] = replacement
    current["canonical_sha256"] = audit.canonical_sha256(current)
    with pytest.raises(audit.RetirementLedgerError, match="rewrote historical retirement metadata"):
        audit.validate_historical_snapshot_extension(snapshot, current)


def test_snapshot_extension_rejects_removing_historical_retirement_and_bad_arithmetic() -> None:
    snapshot = json.loads(audit.P43C_LEDGER_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    removed = copy.deepcopy(snapshot)
    removed["retirements"].pop()
    removed["retired_workflow_paths"] = sorted(entry["workflow_path"] for entry in removed["retirements"])
    removed["current_retired_workflow_count"] = len(removed["retirements"])
    removed["current_live_workflow_count"] = 40 - len(removed["retirements"])
    removed["canonical_sha256"] = audit.canonical_sha256(removed)
    with pytest.raises(audit.RetirementLedgerError, match="removed a historical retirement"):
        audit.validate_historical_snapshot_extension(snapshot, removed)

    invalid = copy.deepcopy(snapshot)
    invalid["current_live_workflow_count"] += 1
    invalid["canonical_sha256"] = audit.canonical_sha256(invalid)
    with pytest.raises(audit.RetirementLedgerError, match="count arithmetic"):
        audit.validate_historical_snapshot_extension(snapshot, invalid)


def test_p43c_ledger_snapshot_is_exact_current_checkpoint() -> None:
    current_bytes = audit.LEDGER_PATH.read_bytes()
    snapshot_bytes = audit.P43C_LEDGER_SNAPSHOT_PATH.read_bytes()
    snapshot = json.loads(snapshot_bytes)
    assert snapshot_bytes == current_bytes
    assert snapshot["canonical_sha256"] == audit.P43C_LEDGER_SNAPSHOT_SHA256
    assert audit.canonical_sha256(snapshot) == audit.P43C_LEDGER_SNAPSHOT_SHA256
