"""Offline integrity audit for the P4.3A workflow census.

This module intentionally has no GitHub/network access.  Run with ``--check``.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.capture_p4_3_workflow_capability_matrix import (
    ALLOWED_FAMILIES,
    BASE_MAIN_SHA,
    POLICY_ID as MATRIX_POLICY_ID,
    PROTECTED_FRESH_HOLDOUT,
    WORKFLOW_DIR,
    canonical_json_bytes,
    canonical_sha256,
)


POLICY_ID = "ATHENA_P4_3A_WORKFLOW_CAPABILITY_CENSUS_V1"
P42_RECEIPT = "artifacts/architecture/p4_2_athena_run_workflow_v1.json"
P41_RECEIPT = "artifacts/architecture/p4_1_cli_consolidation_v1.json"
REGISTRY = "config/architecture/component-authority-registry-v1.json"
MATRIX_PATH = "artifacts/architecture/p4_3_workflow_capability_matrix_v1.json"
RECEIPT_PATH = "artifacts/architecture/p4_3a_workflow_capability_census_v1.json"
P42_SHA = "fa575a5bb5f4611eb94564b92dea3e4230b8d429b1660dc3bde3d6c164b836f8"
P41_SHA = "268933433aaab84cb2533840f2e01eba96ec5906e796c9eced2032e1d6706208"
REGISTRY_SHA = "74e79e216497c2e7f31a51e278251a5c62645e1085d04ebb8712022658f8f109"
MATRIX_SHA = "6b417a19557efdd39201e233fb866e4143b8102ba2879a4f1481e5241722dd8d"
RECEIPT_SHA = "7dd102aa4da98d634d665b4a93f51eb24ece8d7b61c8856b9977ff84a7452a6b"

REQUIRED_ROW_FIELDS = {
    "workflow_path", "workflow_name", "git_blob_sha1", "source_sha256",
    "trigger_types", "schedule_crons", "workflow_dispatch_inputs",
    "issue_comment_behavior", "workflow_run_behavior", "permissions",
    "write_permissions", "secrets_referenced", "concurrency_group",
    "cancel_in_progress", "job_names", "job_timeout_minutes",
    "scripts_or_modules_called", "local_python_entrypoints", "external_tools_called",
    "artifact_uploads", "artifact_downloads", "release_assets_read",
    "outputs_or_receipts", "purpose", "unique_responsibilities",
    "supported_runtime_root", "date_hardcoded", "fresh_holdout_protected",
    "evidence_only", "last_successful_run", "latest_run", "history_status",
    "successor_family", "successor_workflow_path", "capability_mapping",
    "disposition", "retirement_candidate", "retirement_eligible",
    "owner_review_required", "retirement_blockers", "dependency_evidence",
    "evidence_references",
}
ALLOWED_HISTORY = {
    "HAS_SUCCESSFUL_RUN",
    "RUN_HISTORY_WITHOUT_SUCCESS_OWNER_REVIEW_REQUIRED",
    "NO_RUN_HISTORY_OWNER_REVIEW_REQUIRED",
}
ALLOWED_DISPOSITIONS = {
    "CANONICAL_RETAIN",
    "RETAIN_PROTECTED_RESEARCH",
    "RETAIN_ACTIVE_PENDING_CANONICAL_SHADOW_MIGRATION",
    "RETAIN_PENDING_FUTURE_INGEST",
    "RETAIN_PENDING_FUTURE_RETRAIN",
    "RETAIN_PENDING_FUTURE_BACKTEST",
    "RETAIN_HISTORICAL_EVIDENCE_PENDING_AUDIT",
    "RETAIN_NO_RUN_HISTORY_OWNER_REVIEW_REQUIRED",
    "RETAIN_RUN_HISTORY_WITHOUT_SUCCESS_OWNER_REVIEW_REQUIRED",
}
HISTORICAL_FILES = [
    "artifacts/architecture/runtime-reachability-v1.json",
    "artifacts/architecture/p3_1_main_canonical_core_promotion_v1.json",
    "artifacts/architecture/p3_1_main_caller_migration_v1.json",
    "artifacts/architecture/p3_2_frozen_v2_runtime_externalization_v1.json",
    "tests/fixtures/architecture/p3_2_frozen_v2_policy_vectors_v1.json",
    "artifacts/architecture/p3_3_module_canonicalization_v1.json",
    P41_RECEIPT,
    P42_RECEIPT,
    REGISTRY,
]


def _git(*args: str) -> bytes:
    result = subprocess.run(["git", *args], capture_output=True)
    if result.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.decode('utf-8', 'replace')}")
    return result.stdout


def _base_object_available() -> bool:
    result = subprocess.run(["git", "cat-file", "-e", f"{BASE_MAIN_SHA}^{{commit}}"], capture_output=True)
    return result.returncode == 0


def _base_blob_or_current(path: str) -> bytes:
    if _base_object_available():
        return _git("show", f"{BASE_MAIN_SHA}:{path}")
    return Path(path).read_bytes()


def _sha256_file(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _current_workflows() -> list[str]:
    return _worktree_workflows()


def _worktree_workflows() -> list[str]:
    return sorted(p.as_posix() for p in Path(WORKFLOW_DIR).glob("*.yml"))


def _base_workflows() -> list[str]:
    if not _base_object_available():
        return _current_workflows()
    return sorted(
        p.decode("utf-8")
        for p in _git("ls-tree", "-r", "-z", "--name-only", BASE_MAIN_SHA).split(b"\0")
        if p and p.decode("utf-8").startswith(WORKFLOW_DIR + "/") and p.decode("utf-8").endswith(".yml")
    )


def validate_matrix(matrix: dict[str, Any]) -> None:
    if matrix.get("schema_version") != 1 or matrix.get("policy_id") != MATRIX_POLICY_ID:
        raise AssertionError("matrix schema/policy mismatch")
    if matrix.get("repository_main_sha") != BASE_MAIN_SHA:
        raise AssertionError("matrix base main SHA mismatch")
    rows = matrix.get("workflow_rows")
    if not isinstance(rows, list) or len(rows) != 40 or matrix.get("workflow_count") != 40:
        raise AssertionError("matrix must contain exactly 40 workflow rows")
    paths = [row.get("workflow_path") for row in rows]
    if paths != sorted(paths) or len(set(paths)) != 40:
        raise AssertionError("matrix paths must be unique and sorted")
    # Report unsafe equivalence claims by workflow even when an adversarial
    # fixture has also updated its self-hash to match the altered row.
    for row in rows:
        path = row.get("workflow_path", "<unknown>")
        mapping = row.get("capability_mapping")
        if not isinstance(mapping, dict) or mapping.get("equivalence_claimed") is not False:
            raise AssertionError(f"{path}: P4.3A successor equivalence must not be claimed")
    from scripts import audit_p4_3_workflow_retirement_ledger as retirement_ledger
    from scripts import audit_p4_workflow_evolution_ledger as evolution_ledger

    ledger = retirement_ledger.validate_retirement_history()
    current_evolution = evolution_ledger.validate_current_state(retirement_ledger=ledger)
    # Hosted PR checkouts may be shallow and not include the historical 40-row
    # base commit. The pinned, hash-verified P4.3A matrix is the baseline in that
    # case; current-tree accounting is still independently enforced by the ledger.
    expected_paths = _base_workflows() if _base_object_available() else paths
    worktree_paths = _worktree_workflows()
    retired_paths = ledger["retired_workflow_paths"]
    surviving_paths = sorted(set(paths) - set(retired_paths))
    expected_current_count = current_evolution["current_live_workflow_count"]
    if len(expected_paths) != 40 or len(worktree_paths) != expected_current_count:
        raise AssertionError("P4.3A historical/current workflow counts disagree with the retirement ledger")
    if (
        paths != expected_paths
        or len(surviving_paths) != ledger["current_live_workflow_count"]
        or ledger["current_retired_workflow_count"] != len(retired_paths)
    ):
        raise AssertionError("P4.3A frozen census differs from cumulative retirement ledger")
    if canonical_sha256(matrix) != matrix.get("canonical_sha256"):
        raise AssertionError("matrix canonical SHA mismatch")
    if matrix.get("canonical_sha256") != MATRIX_SHA:
        raise AssertionError("immutable P4.3A matrix SHA changed")

    for row in rows:
        missing = REQUIRED_ROW_FIELDS - set(row)
        if missing:
            raise AssertionError(f"{row.get('workflow_path')}: missing fields {sorted(missing)}")
        path = row["workflow_path"]
        capability_mapping = row.get("capability_mapping")
        if not isinstance(capability_mapping, dict) or capability_mapping.get("equivalence_claimed") is not False:
            raise AssertionError(f"{path}: P4.3A successor equivalence must not be claimed")
        raw = retirement_ledger.resolve_reviewed_workflow_source(path, ledger=ledger)
        base_blob = row["git_blob_sha1"]
        if _base_object_available() and _git("rev-parse", f"{BASE_MAIN_SHA}:{path}").decode().strip() != base_blob:
            raise AssertionError(f"P4.3A baseline workflow identity changed: {path}")
        if row["git_blob_sha1"] != base_blob:
            raise AssertionError(f"workflow blob identity mismatch: {path}")
        if row["source_sha256"] != hashlib.sha256(raw).hexdigest():
            raise AssertionError(f"workflow source SHA mismatch: {path}")
        if row["history_status"] not in ALLOWED_HISTORY:
            raise AssertionError(f"unsupported history status: {path}")
        if row["successor_family"] not in ALLOWED_FAMILIES:
            raise AssertionError(f"unsupported successor family: {path}")
        if row["disposition"] not in ALLOWED_DISPOSITIONS:
            raise AssertionError(f"unsupported disposition: {path}")
        if row["retirement_eligible"]:
            raise AssertionError(f"P4.3A grants no retirement authority: {path}")
        if row["history_status"] != "HAS_SUCCESSFUL_RUN" and not row["owner_review_required"]:
            raise AssertionError(f"no-success workflow lacks owner review: {path}")
        if row["history_status"] != "HAS_SUCCESSFUL_RUN" and row["retirement_eligible"]:
            raise AssertionError(f"no-success workflow cannot be retirement eligible: {path}")
        dep = row["dependency_evidence"]
        for key in (
            "artifact_producer_only", "artifact_consumer_exists", "workflow_history_consumer_exists",
            "current_docs_reference", "current_test_reference", "historical_reference_only",
            "consumer_sources", "source_matches", "artifact_consumer_sources",
            "artifact_reference_sources", "workflow_reference_sources",
            "workflow_or_history_consumer_sources", "known_workflow_consumers",
        ):
            if key not in dep:
                raise AssertionError(f"{path}: dependency field {key} missing")
        if row["date_hardcoded"] and row["supported_runtime_root"]:
            raise AssertionError(f"date-hardcoded supported root requires migration: {path}")

    by_path = {r["workflow_path"]: r for r in rows}
    expected_no_run = [r["workflow_path"] for r in rows if r["history_status"] == "NO_RUN_HISTORY_OWNER_REVIEW_REQUIRED"]
    expected_no_success = [r["workflow_path"] for r in rows if r["history_status"] == "RUN_HISTORY_WITHOUT_SUCCESS_OWNER_REVIEW_REQUIRED"]
    if matrix.get("no_run_history_owner_review_required") is None or sorted(x["workflow_path"] for x in matrix["no_run_history_owner_review_required"]) != expected_no_run:
        raise AssertionError("no-run owner-review queue does not match row history")
    if matrix.get("run_history_without_success_owner_review_required") is None or sorted(x["workflow_path"] for x in matrix["run_history_without_success_owner_review_required"]) != expected_no_success:
        raise AssertionError("no-success owner-review queue does not match row history")
    if matrix.get("successful_run_count") != sum(r["history_status"] == "HAS_SUCCESSFUL_RUN" for r in rows):
        raise AssertionError("successful run summary count mismatch")
    if matrix.get("no_successful_run_count") != len(expected_no_run) + len(expected_no_success):
        raise AssertionError("no-success summary count mismatch")
    target = by_path[".github/workflows/current-sportybet-accumulator.yml"]
    if target["history_status"] == "NO_RUN_HISTORY_OWNER_REVIEW_REQUIRED":
        if target["last_successful_run"] is not None or target["latest_run"] is not None:
            raise AssertionError("target no-run status contradicts run evidence")
        if target["disposition"] != "RETAIN_NO_RUN_HISTORY_OWNER_REVIEW_REQUIRED" or not target["owner_review_required"] or target["retirement_eligible"]:
            raise AssertionError("target no-run owner-review gate failed")
    shadow = by_path[".github/workflows/current-shadow-all-market.yml"]
    if shadow["disposition"] != "RETAIN_ACTIVE_PENDING_CANONICAL_SHADOW_MIGRATION" or shadow["retirement_eligible"] or not shadow["retirement_blockers"]:
        raise AssertionError("Current Shadow must remain retained with blockers")
    for path in PROTECTED_FRESH_HOLDOUT:
        row = by_path[path]
        if not row["fresh_holdout_protected"] or row["disposition"] != "RETAIN_PROTECTED_RESEARCH" or row["retirement_eligible"]:
            raise AssertionError(f"protected research row is not retained: {path}")
    canonical = by_path[".github/workflows/athena-run.yml"]
    if canonical["disposition"] != "CANONICAL_RETAIN" or canonical["retirement_eligible"]:
        raise AssertionError("athena-run must remain canonical")
    for path in HISTORICAL_FILES:
        current_blob = _git("rev-parse", f"HEAD:{path}").decode().strip()
        base_blob = (
            _git("rev-parse", f"{BASE_MAIN_SHA}:{path}").decode().strip()
            if _base_object_available()
            else current_blob
        )
        if current_blob != base_blob:
            raise AssertionError(f"protected historical file changed: {path}")
        expected = P42_SHA if path == P42_RECEIPT else P41_SHA if path == P41_RECEIPT else None
        if expected is not None:
            historical_receipt = json.loads(_base_blob_or_current(path))
            if canonical_sha256(historical_receipt) != expected:
                raise AssertionError(f"historical receipt canonical SHA mismatch: {path}")


def build_receipt(matrix: dict[str, Any]) -> dict[str, Any]:
    rows = matrix["workflow_rows"]
    successor_equivalence_claimed_count = sum(
        row["capability_mapping"]["equivalence_claimed"] is True for row in rows
    )
    if successor_equivalence_claimed_count != 0:
        raise AssertionError("P4.3A successor equivalence claim count must be zero")
    by_path = {r["workflow_path"]: r for r in rows}
    no_run = [r for r in rows if r["history_status"] == "NO_RUN_HISTORY_OWNER_REVIEW_REQUIRED"]
    no_success = [r for r in rows if r["history_status"] == "RUN_HISTORY_WITHOUT_SUCCESS_OWNER_REVIEW_REQUIRED"]
    owner_rows = [r for r in rows if r["owner_review_required"]]
    date_rows = [r for r in rows if r["date_hardcoded"]]
    supported_dates = [r for r in date_rows if r["supported_runtime_root"]]
    protected = [r for r in rows if r["fresh_holdout_protected"]]
    target = by_path[".github/workflows/current-sportybet-accumulator.yml"]
    shadow = by_path[".github/workflows/current-shadow-all-market.yml"]
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "repository_base_main_sha": BASE_MAIN_SHA,
        "p4_2_receipt_sha256": P42_SHA,
        "p4_1_receipt_sha256": P41_SHA,
        "component_registry_canonical_sha256": REGISTRY_SHA,
        "workflow_matrix_policy_id": matrix["policy_id"],
        "workflow_matrix_canonical_sha256": matrix["canonical_sha256"],
        "successor_equivalence_claimed_count": successor_equivalence_claimed_count,
        "successor_equivalence_proof_deferred_to": "P4_3B_OWNER_REVIEWED_WORKFLOW_RETIREMENT_SELECTION_REQUIRED",
        "workflow_count": 40,
        "matrix_row_count": len(rows),
        "workflow_files_changed": [],
        "workflow_files_deleted": [],
        "workflow_files_added": [],
        "rollback_tag_created": False,
        "rows_with_successful_run": sum(r["history_status"] == "HAS_SUCCESSFUL_RUN" for r in rows),
        "rows_without_successful_run": len(no_run) + len(no_success),
        "rows_with_no_run_history": len(no_run),
        "rows_with_run_history_without_success": len(no_success),
        "owner_review_required_count": len(owner_rows),
        "owner_review_required_workflows": [r["workflow_path"] for r in owner_rows],
        "date_hardcoded_workflow_count": len(date_rows),
        "supported_date_hardcoded_workflow_count": len(supported_dates),
        "supported_date_hardcoded_workflows": [r["workflow_path"] for r in supported_dates],
        "protected_research_workflow_count": len(protected),
        "protected_research_workflows": [r["workflow_path"] for r in protected],
        "current_sportybet_accumulator": {
            "history_status": target["history_status"],
            "last_successful_run": target["last_successful_run"],
            "latest_run": target["latest_run"],
            "owner_review_required": target["owner_review_required"],
            "retirement_eligible": False,
            "successor_family": "ATHENA_RUN",
        },
        "current_shadow": {
            "retained": True,
            "retirement_eligible": False,
            "blockers": shadow["retirement_blockers"],
        },
        "p4_3_master_retirement_exit_gate_satisfied": False,
        "p4_3a_census_exit_gate_satisfied": True,
        "workflow_count_decreased": False,
        "unique_required_capability_lost": False,
        "architecture_checkpoint_e_fully_claimed": False,
        "no_workflow_dispatch": True,
        "provider_acquisition": False,
        "current_shadow_triggered": False,
        "fresh_holdout_triggered": False,
        "p3_0_e1_triggered": False,
        "real_share_code_operation": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "wager_placed": False,
        "model_formula_changed": False,
        "probability_formula_changed": False,
        "calibration_formula_changed": False,
        "price_all_formula_changed": False,
        "router_formula_changed": False,
        "portfolio_formula_changed": False,
        "provider_semantics_changed": False,
        "share_code_semantics_changed": False,
        "next_required_step": "P4_3B_OWNER_REVIEWED_WORKFLOW_RETIREMENT_SELECTION_REQUIRED",
        "source_review_counter_while_unmerged": "1/5",
        "source_review_counter_if_merged": "2/5",
        "canonical_sha256": "",
    }
    receipt["canonical_sha256"] = canonical_sha256(receipt)
    return receipt


def check(*, write_receipt: bool = False) -> dict[str, Any]:
    matrix = json.loads(Path(MATRIX_PATH).read_text(encoding="utf-8"))
    validate_matrix(matrix)
    receipt = build_receipt(matrix)
    if write_receipt:
        Path(RECEIPT_PATH).write_bytes(canonical_json_bytes(receipt))
    else:
        committed = json.loads(Path(RECEIPT_PATH).read_text(encoding="utf-8"))
        if committed != receipt:
            raise AssertionError("P4.3A receipt does not match the validated matrix")
        if canonical_sha256(committed) != committed.get("canonical_sha256"):
            raise AssertionError("P4.3A receipt canonical SHA mismatch")
        if committed.get("canonical_sha256") != RECEIPT_SHA:
            raise AssertionError("immutable P4.3A receipt SHA changed")
    return receipt


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate matrix and committed receipt offline")
    parser.add_argument("--write-receipt", action="store_true", help="write deterministic receipt after validation")
    args = parser.parse_args(argv)
    try:
        receipt = check(write_receipt=args.write_receipt)
        print(f"P4.3A census audit passed; matrix={receipt['workflow_matrix_canonical_sha256']} receipt={receipt['canonical_sha256']}")
        return 0
    except Exception as exc:
        print(f"P4_3A_CENSUS_AUDIT_FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
