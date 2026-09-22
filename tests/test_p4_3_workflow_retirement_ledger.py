from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import audit_p4_3_workflow_retirement_ledger as audit


def test_cumulative_ledger_is_exactly_three_retirements_and_37_live_workflows() -> None:
    ledger = audit.validate_ledger()
    matrix, _ = audit.load_baseline()
    live = sorted(path.as_posix() for path in Path(".github/workflows").glob("*.yml"))
    assert len(matrix["workflow_rows"]) == 40
    assert len(live) == ledger["current_live_workflow_count"] == 37
    assert ledger["current_retired_workflow_count"] == 3
    assert set(live) == {row["workflow_path"] for row in matrix["workflow_rows"]} - set(audit.RETIRED)
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
    with pytest.raises(audit.RetirementLedgerError, match="entries do not match"):
        audit.validate_ledger(payload)


def test_ledger_p4_3a_and_p4_3b_receipts_are_immutable() -> None:
    ledger = audit.validate_ledger()
    assert ledger["baseline_matrix_sha256"] == audit.MATRIX_SHA256
    assert ledger["baseline_p4_3a_receipt_sha256"] == audit.P43A_RECEIPT_SHA256
    assert next(item for item in ledger["retirements"] if item["retirement_phase"] == "P4.3B")["retirement_receipt_sha256"] == audit.P43B_RECEIPT_SHA256
