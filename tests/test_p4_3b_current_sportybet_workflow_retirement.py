"""Hosted, offline proof of the single owner-reviewed P4.3B retirement."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import audit_p4_2_athena_run_workflow as p42
from scripts import audit_p4_3b_current_sportybet_workflow_retirement as audit


def test_only_reviewed_workflow_is_absent_and_historical_fixture_is_exact() -> None:
    matrix = audit.verify_frozen_history()
    audit.verify_retirement_tree(matrix)
    raw = audit.verify_historical_fixture()
    # P4.3B retains its historical 40->39 transition; current cumulative state
    # is lower because P4.3C separately retires two spent V1 evidence workflows.
    assert len(list(Path(".github/workflows").glob("*.yml"))) == 37
    assert not Path(audit.TARGET).exists()
    assert Path(audit.FIXTURE).is_file()
    assert not audit.FIXTURE.startswith(".github/workflows/")
    assert hashlib.sha256(raw).hexdigest() == audit.TARGET_SOURCE_SHA256
    assert audit._git_blob_sha1(raw) == audit.TARGET_BLOB_SHA1
    assert all(Path(path).is_file() for path in audit.PROTECTED)


def test_historical_fixture_drift_fails_closed() -> None:
    raw = audit.verify_historical_fixture()
    changed = bytes([raw[0] ^ 1]) + raw[1:]
    with pytest.raises(audit.P43BRetirementError, match="historical fixture SHA-256 drifted"):
        audit.verify_historical_fixture(changed)


def test_main_successor_equivalence_for_1_20_50_and_invalid_bounds() -> None:
    proof = audit.prove_main_successor()
    assert [item["target_size"] for item in proof["targets"]] == [1, 20, 50]
    assert proof["network_attempt_count"] == 0
    assert proof["reviewed_main_boundary_called_for_each_target"] is True
    assert proof["durable_request_evidence_preserved"] is True
    assert proof["legacy_invalid_targets_rejected"] == [0, 51]
    assert proof["invalid_target_text_rejected"] == ["0", "51", "020", "20 ", "20.0", "abc"]
    for item in proof["targets"]:
        audit.validate_equivalence_projection(item["projection"], item["target_size"])
        assert item["projection"]["selected_leg_count"] == 0
        assert item["projection"]["shortfall"] == item["target_size"]
        assert item["projection"]["share_code_result"] is None


@pytest.mark.parametrize("field,value", [
    ("provider_acquisition", True),
    ("current_provider_execution", True),
    ("share_code_generation", True),
    ("selected_leg_count", 1),
    ("share_code_result", {"code": "untrusted"}),
    ("wager_placed", True),
])
def test_adversarial_equivalence_projection_cannot_hide_authority(field: str, value: object) -> None:
    baseline = {
        "requested_target": 20,
        "legacy_status": "NO_CODE_CURRENT_PHASE6_AUTHORITY_REQUIRED",
        "canonical_status": "MAIN_PHASE6_AUTHORITY_REQUIRED",
        "blocked_at": audit.BLOCKED_AT,
        "provider_acquisition": False,
        "current_provider_execution": False,
        "share_code_generation": False,
        "selected_leg_count": 0,
        "shortfall": 20,
        "share_code_result": None,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "wager_placed": False,
        "legacy_payload_preserved": True,
        "durable_request_evidence_preserved": True,
    }
    baseline[field] = value
    with pytest.raises(audit.P43BRetirementError, match="fail-closed equivalence failed"):
        audit.validate_equivalence_projection(baseline, 20)


def test_permissions_and_artifact_successor_are_explicit() -> None:
    comparison = audit.verify_permissions_and_artifacts()
    assert comparison["legacy_permissions"] == {"contents": "read"}
    assert comparison["canonical_permissions"] == {"contents": "read", "actions": "read"}
    assert comparison["legacy_timeout_minutes"] == 15
    assert comparison["canonical_timeout_minutes"] == 90
    assert comparison["legacy_artifact_name"] == "current-sportybet-accumulator-request"
    assert comparison["canonical_artifact_name_pattern"] == "athena-run-${{ github.run_id }}"
    assert comparison["artifact_retention_days"] == 30


def test_p42_historical_receipt_and_retired_blob_still_verify() -> None:
    committed = p42.verify_committed_receipt()
    assert committed["canonical_sha256"] == audit.P42_SHA
    assert p42.verify_preserved_historical_sources()[audit.TARGET] == audit.TARGET_BLOB_SHA1


def test_p43b_receipt_binds_single_deletion_rollback_and_safety() -> None:
    committed = json.loads(audit.RECEIPT.read_bytes())
    assert audit.canonical_sha256(committed) == committed["canonical_sha256"]
    assert audit.check(write_receipt=False) == committed
    assert committed["repository_base_main_sha"] == audit.BASE_MAIN_SHA
    assert committed["p4_3a_matrix_sha256"] == audit.MATRIX_SHA
    assert committed["p4_3a_receipt_sha256"] == audit.P43A_SHA
    assert committed["p4_2_receipt_sha256"] == audit.P42_SHA
    assert committed["retired_workflow_path"] == audit.TARGET
    assert committed["historical_fixture_path"] == audit.FIXTURE
    assert committed["rollback_tag"] == audit.ROLLBACK_TAG
    assert committed["rollback_commit_sha"] == audit.BASE_MAIN_SHA
    assert committed["rollback_tag_remote_verified_before_deletion"] is True
    assert committed["workflow_count_before"] == 40
    assert committed["workflow_count_after"] == 39
    assert committed["unique_required_capability_lost"] is False
    assert committed["equivalence_proven"] is True
    assert committed["p4_3b_retirement_gate_satisfied"] is True
    assert committed["architecture_checkpoint_e_fully_claimed"] is False
    assert committed["p4_4_started"] is False
    for flag in (
        "workflow_dispatch_triggered", "provider_acquisition", "current_shadow_triggered",
        "fresh_holdout_triggered", "p3_0_e1_triggered", "real_share_code_operation",
        "login", "cookies", "wallet", "staking", "wager_placed",
        "model_formula_changed", "probability_formula_changed", "calibration_formula_changed",
        "price_all_formula_changed", "router_formula_changed", "portfolio_formula_changed",
        "provider_semantics_changed", "share_code_semantics_changed",
    ):
        assert committed[flag] is False


def test_no_current_documentation_instructs_use_of_retired_workflow() -> None:
    current = Path("docs/current_sportybet_end_to_end.md").read_text(encoding="utf-8")
    assert "workflow was retired in P4.3B" in current
    assert "hosted workflow exposes the same target" not in current
    for path in ("docs/architecture/athena_run_workflow.md", "docs/architecture/workflow_capability_matrix.md"):
        source = Path(path).read_text(encoding="utf-8")
        assert "P4.3B" in source
        assert "Current Shadow" in source
