from __future__ import annotations

import ast
import json
from pathlib import Path

from domain.ingest_contracts import FORBIDDEN_AUTHORITIES
from scripts import audit_p4_4b_athena_ingest_workflow as p44b
from scripts import audit_p4_4c_scheduled_ingest_and_migration_review as p44c
from scripts import audit_p4_workflow_evolution_ledger as evolution


INGEST_FILES = (
    "domain/ingest_contracts.py",
    "services/athena_ingest_service.py",
    "scripts/resolve_athena_ingest_workflow_request.py",
    "scripts/execute_athena_ingest_workflow.py",
    "scripts/replay_athena_ingest_artifact.py",
)


def test_ingest_code_has_no_betting_or_model_imports() -> None:
    forbidden = (
        "sportybet", "pricing", "router", "portfolio", "share_code",
        "prediction", "model_execution", "wallet", "wager", "stake",
    )
    for path in INGEST_FILES:
        tree = ast.parse(Path(path).read_text(encoding="utf-8"))
        imports = [
            node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        ] + [
            name.name for node in ast.walk(tree) if isinstance(node, ast.Import) for name in node.names
        ]
        assert not any(token in module.lower() for module in imports for token in forbidden), path


def test_ingest_authority_contract_denies_downstream_actions() -> None:
    assert set(FORBIDDEN_AUTHORITIES) >= {
        "fixture_selection_authority", "model_feature_authority", "probability_authority",
        "pricing_authority", "market_routing_authority", "portfolio_authority",
        "share_code_authority", "login", "cookies", "wallet", "staking", "wager",
    }


def test_reviewed_add_snapshot_and_receipt_bind_one_new_workflow() -> None:
    receipt = p44b.check()
    ledger = evolution.validate_current_state()
    snapshot = json.loads(p44b.SNAPSHOT.read_text(encoding="utf-8"))
    assert snapshot["transitions"] == ledger["transitions"][:3]
    assert receipt["workflow_evolution_ledger_sha256"] == snapshot["canonical_sha256"]
    assert receipt["workflow_git_blob_sha1"] == ledger["transitions"][2]["after"]["git_blob_sha1"]
    assert receipt["workflow_source_sha256"] == ledger["transitions"][2]["after"]["source_sha256"]
    assert ledger["current_live_workflow_count"] == 38
    assert len(ledger["transitions"]) == 4
    assert [item["transition_id"] for item in ledger["transitions"][:2]] == list(p44b.OLD_TRANSITION_IDS)
    assert ledger["transitions"][2]["operation"] == "ADD"
    assert ledger["transitions"][2]["before"] is None
    assert ledger["transitions"][2]["canonical_family"] == "ATHENA_INGEST"
    assert receipt["scheduled_acquisition_enabled"] is False
    assert receipt["production_database_path_added"] is False
    assert receipt["canonical_store_update_is_immutable_delta"] is True
    assert receipt["offline_replay_exit_gate_satisfied"] is True
    assert receipt["runtime_receipt_exact_commit_sha_required"] is True
    assert receipt["fail_closed_partial_receipt_required"] is True
    assert receipt["invalid_request_partial_receipt_supported"] is True
    assert receipt["timeout_partial_receipt_supported"] is True
    assert receipt["pre_receipt_lineage_gate_non_terminal"] is True
    assert receipt["executor_is_authoritative_pre_acquisition_lineage_gate"] is True
    assert receipt["lineage_mismatch_receipt_before_provider_acquisition"] is True
    assert receipt["ingest_service_budget_seconds"] == 900
    assert receipt["workflow_job_timeout_minutes"] == 20
    assert receipt["receipt_finalization_headroom_seconds"] == 300
    assert receipt["p4_4_overall_complete"] is False


def test_p4_4c_schedule_revision_and_migration_review_remain_narrow() -> None:
    receipt = p44c.check_historical()
    assert receipt["workflow_evolution_ledger_sha256"] == evolution.validate_current_state()["canonical_sha256"]
    assert receipt["schedule_cron"] == "0 8 * * *"
    assert receipt["scheduled_max_provider_requests"] == 1
    assert receipt["provider_request_count_during_pr"] == 0
    assert receipt["p4_3_retirements_added"] == 0
    assert receipt["legacy_ingest_workflows_retired"] == 0
    assert receipt["model_authority"] is False
    assert receipt["routing_authority"] is False
    assert receipt["portfolio_authority"] is False
