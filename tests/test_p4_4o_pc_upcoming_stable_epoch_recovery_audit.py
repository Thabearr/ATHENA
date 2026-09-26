from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import audit_p4_4o_pc_upcoming_stable_epoch_recovery as audit
from scripts import audit_p4_4n_sportybet_team_label_shape_compatibility as p44n


def test_p4_4o_receipt_and_current_runtime_supersession_are_exact():
    result = audit.audit(Path.cwd())
    assert result["status"] == "PASSED"
    assert result["policy_id"] == "ATHENA_P4_4O_PC_UPCOMING_STABLE_EPOCH_RECOVERY_V1"
    assert result["runtime_policy_id"] == "ATHENA_CURRENT_SHADOW_PC_UPCOMING_DISCOVERY_RECONCILIATION_V1"
    assert result["runtime_policy_sha256"] == (
        "dac1f99da0b536b3808f8c7e41f66ad501101871d811131f8ede9e5dc99d4a5f"
    )
    assert result["source_policy_sha256"] == (
        "63799058bec00abefb8d9b2ec9ba6dcad0c6e4775a54f17b07c0018e543ec075"
    )
    assert result["workflow_yaml_changed"] is False
    assert result["current_shadow_and_p3_shared_source"] is True


def test_p4_4n_history_keeps_its_then_current_runtime_hash_and_p4_4o_supersedes_it():
    historical = p44n.audit_historical(Path.cwd())
    assert historical["historical_runtime_wrapper_sha256"] == (
        "fd203fc4b857bb3c5faa22536e87e1bc214cd4fdcf79ec5b6c4c681cd9d0cf73"
    )
    current = p44n.audit(Path.cwd())
    assert current["runtime_wrapper_sha256"] == audit.runtime.PINNED_POLICY_SHA256
    assert current["historical_runtime_wrapper_sha256"] == historical["historical_runtime_wrapper_sha256"]
    assert current["p4_4o_receipt_sha256"] == audit._verify_receipt(Path.cwd())["canonical_sha256"]


def test_p4_4o_receipt_hash_rejects_unreviewed_mutation(tmp_path: Path):
    receipt = json.loads((Path.cwd() / audit.RECEIPT_PATH).read_text(encoding="utf-8"))
    receipt["recovery_policy"]["no_third_epoch"] = False
    path = tmp_path / audit.RECEIPT_PATH
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(audit.P44OError, match="canonical SHA mismatch"):
        audit._verify_receipt(tmp_path)


def test_failed_live_run_is_not_claimed_as_p4_4o_success_or_new_proof():
    receipt = audit._verify_receipt(Path.cwd())
    assert receipt["failed_proof_run"] == 36245444226
    assert receipt["failed_proof_artifact_id"] == 10907222195
    assert receipt["failed_proof_classification"].endswith("PC_UPCOMING_RUNTIME_PAGINATION_INCOMPLETE")
    assert receipt["successor_proof_complete"] is False
    assert receipt["successor_proof_rerun"] is False
    assert receipt["live_proof_during_implementation"] is False
    assert receipt["next_live_proof_authorized"] is False
