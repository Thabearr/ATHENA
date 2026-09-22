from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

from scripts import audit_p3_1_main_caller_migration as audit


def _unsigned(payload: dict) -> dict:
    value = dict(payload)
    value.pop("canonical_sha256")
    return value


def test_migration_receipt_is_deterministic_and_hashes_unsigned_payload():
    first = audit.load_historical_migration_evidence()
    second = audit.load_historical_migration_evidence()
    assert first == second
    assert first["policy_id"] == "ATHENA_P3_1_MAIN_CALLER_MIGRATION_V1"
    assert first["schema_version"] == 1
    assert first["canonical_sha256"] == audit._canonical_sha256(_unsigned(first))
    assert first["p3_1_exit_gate_satisfied"] is True


def test_migration_receipt_binds_pr_a_registry_and_frozen_p05_history():
    payload = audit.load_historical_migration_evidence()
    assert payload["repository_base_main_sha"] == audit.BASE_MAIN_SHA
    assert payload["p3_1_pr_a_merge_commit_sha"] == audit.P3_1_PR_A_MERGE_COMMIT_SHA
    assert payload["p3_1_pr_a_promotion_receipt_sha256"] == audit.P3_1_PR_A_RECEIPT_SHA256
    assert payload["promoted_registry_canonical_sha256"] == audit.PROMOTED_REGISTRY_SHA256
    assert payload["historical_p0_5_artifact_preserved"] is True
    assert payload["historical_p0_5_market_selector_reachability"] is True
    source_bytes = subprocess.check_output([
        "git",
        "show",
        f"HEAD:{audit.HISTORICAL_P05_ARTIFACT.relative_to(audit.REPOSITORY_ROOT).as_posix()}",
    ])
    assert hashlib.sha256(source_bytes).hexdigest() == (
        audit.HISTORICAL_P05_ARTIFACT_SHA256
    )
    assert audit.HISTORICAL_P05_ARTIFACT.read_bytes().replace(b"\r\n", b"\n") == source_bytes
    assert payload["current_build_acca_market_selector_executed_count"] == 0


def test_selected_no_bet_and_no_router_cases_are_explicitly_fail_closed_or_projected():
    payload = audit.load_historical_migration_evidence()
    selected = payload["selected_case"]
    no_bet = payload["no_bet_case"]
    no_router = payload["no_router_decision_case"]
    assert selected["legacy_prediction_output_shape_preserved"] is True
    assert selected["canonical_selection"] == {
        "line": None,
        "market_id": "MATCH_RESULT",
        "outcome_id": "HOME",
    }
    assert selected["recommended_market"] == "Home Win"
    assert selected["market_confidence"] == 60.0
    assert selected["ranked_market_count"] == 1
    assert no_bet["recommended_market"] == "No Recommendation"
    assert no_bet["market_confidence"] == 0.0
    assert no_bet["ranked_market_count"] == 0
    assert no_router["recommended_market"] == "No Recommendation"
    assert no_router["market_confidence"] == 0.0
    assert no_router["ranked_market_count"] == 0
    assert all(
        case["market_selector_executed_count"] == 0
        for case in (selected, no_bet, no_router)
    )


def test_migration_receipt_records_scope_and_safety_guards():
    payload = audit.load_historical_migration_evidence()
    assert payload["caller_migration_performed"] is True
    assert payload["market_selector_removed"] is False
    assert payload["market_selector_supported_runtime_execution"] is False
    for key in (
        "provider_acquisition",
        "current_shadow_triggered",
        "fresh_holdout_triggered",
        "share_code_generation",
        "login",
        "cookies",
        "wallet",
        "staking",
        "wager_placed",
        "model_formula_changed",
        "probability_formula_changed",
        "calibration_formula_changed",
        "price_all_formula_changed",
        "router_formula_changed",
        "portfolio_formula_changed",
    ):
        assert payload[key] is False
    assert payload["current_prediction_service_market_selector_executed_count"] == 0
    assert payload["canonical_router_decision_verification_observed"] is True
    assert payload["main_canonical_core_resolution_observed"] is True


def test_committed_receipt_matches_deterministic_audit_output():
    committed = json.loads(Path(audit.DEFAULT_OUTPUT).read_bytes())
    assert committed == audit.load_historical_migration_evidence()
