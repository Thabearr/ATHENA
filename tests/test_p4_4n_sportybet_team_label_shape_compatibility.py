from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import audit_p4_4n_sportybet_team_label_shape_compatibility as audit


def test_p4_4n_receipt_and_current_contract_supersession_are_exact():
    result = audit.audit(Path.cwd())
    assert result["status"] == "PASSED"
    assert result["policy_id"] == "ATHENA_P4_4N_SPORTYBET_TEAM_LABEL_SHAPE_COMPATIBILITY_V1"
    assert result["team_label_policy_sha256"] == (
        "0c382ec8b12d802879a51b766daae8f655dd5b371509653e56a13190a85c6c7b"
    )
    assert result["identity_compatibility_sha256"] == (
        "2fdbb8165262f6e633ee48276aea57c9235699272235798e1cef12fdc714ae04"
    )
    assert result["runtime_wrapper_sha256"] == (
        "dac1f99da0b536b3808f8c7e41f66ad501101871d811131f8ede9e5dc99d4a5f"
    )
    assert result["historical_runtime_wrapper_sha256"] == (
        "fd203fc4b857bb3c5faa22536e87e1bc214cd4fdcf79ec5b6c4c681cd9d0cf73"
    )
    assert result["historical_evidence_examples"] == 6
    assert result["historical_evidence_captures"] == 5
    assert result["admitted_shape"] == "EXACTLY_ONE_TRAILING_ASCII_U_0020_ONLY"
    assert result["provider_acquisition"] == 0
    assert result["workflow_dispatch"] == 0


def test_p4_4n_receipt_canonical_hash_fails_closed(tmp_path: Path):
    path = tmp_path / audit.RECEIPT_PATH
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"schema_version": 1, "policy_id": audit.POLICY_ID, "canonical_sha256": "0" * 64}),
        encoding="utf-8",
    )
    with pytest.raises(audit.P44NError, match="canonical SHA mismatch"):
        audit._receipt(tmp_path)


def test_p4_4n_pins_prove_cascade_and_unchanged_sources():
    receipt = audit._receipt(Path.cwd())
    audit._verify_pins(receipt)
    assert receipt["pc_upcoming_source_sha256_before"] == receipt["pc_upcoming_source_sha256_after"]
    assert receipt["international_bridge_sha256_before"] == receipt["international_bridge_sha256_after"]
    assert receipt["v2_semantic_registry_sha256_before"] == receipt["v2_semantic_registry_sha256_after"]
    assert receipt["v2_seed_registry_sha256_before"] == receipt["v2_seed_registry_sha256_after"]
    assert receipt["runtime_source_owner"]["changed"] is False
    assert receipt["p3_source_owner"]["changed"] is False


def test_historical_receipt_hashes_remain_immutable():
    receipt = audit._receipt(Path.cwd())
    audit._verify_history_and_workflow(Path.cwd(), receipt)
    assert set(receipt["historical_receipts"]) == set(audit.HISTORICAL_RECEIPTS)
