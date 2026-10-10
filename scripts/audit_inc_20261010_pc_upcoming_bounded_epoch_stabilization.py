#!/usr/bin/env python3
"""Offline audit for the October 10 pcUpcoming bounded epoch stabilization successor."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from domain import current_shadow_all_market_runner as runner
from domain import current_shadow_sportybet_pc_upcoming_reconciliation as runtime
from domain import current_shadow_sportybet_pc_upcoming_discovery as source
from scripts import audit_p4_4q_pc_upcoming_simple_tournament_identity as p44q
from scripts import verify_p3_0_e1_live_readiness as p3

RECEIPT_PATH = Path("artifacts/architecture/inc_20261010_pc_upcoming_bounded_epoch_stabilization_v1.json")
POLICY_ID = "ATHENA_INC_20261010_PC_UPCOMING_BOUNDED_EPOCH_STABILIZATION_V1"
BASE_MAIN_SHA = "74b07c74a946fd19a63f5695055b09668268aef2"
OLD_RUNTIME_SHA256 = "3cf597440422433e7c7e2246d33de4ece22e55395218f8bc2eb8950a361dd68a"
NEW_RUNTIME_SHA256 = "9dc0cfb362cf7008d28bcf029755b7361481b683e41155528f9607047773ceba"
P44Q_RECEIPT_SHA256 = "24ac836152c945754620bdd15f9c9436cc686e550b65127c88895902ddaebebe"
INCIDENT_RUNS = (38040206179, 38041391149)
INCIDENT_ARTIFACTS = (11665054308, 11665603012)

class PcUpcomingBoundedEpochAuditError(RuntimeError):
    pass

def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")

def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PcUpcomingBoundedEpochAuditError(message)

def _read_receipt(root: Path) -> dict[str, Any]:
    path = root / RECEIPT_PATH
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PcUpcomingBoundedEpochAuditError("successor receipt is unavailable") from exc
    _require(type(value) is dict, "successor receipt must be an object")
    semantic = dict(value)
    embedded = semantic.pop("canonical_sha256", None)
    _require(
        embedded == hashlib.sha256(_canonical(semantic)).hexdigest(),
        "successor receipt canonical SHA mismatch",
    )
    return value

def audit_historical(repository_root: str | Path = ".") -> dict[str, Any]:
    root = Path(repository_root)
    historical = p44q.audit_historical(root)
    _require(historical.get("receipt_sha256") == P44Q_RECEIPT_SHA256, "P4.4Q ancestry drifted")
    return {
        "status": "PASSED",
        "p4_4q_receipt_sha256": historical["receipt_sha256"],
    }

def audit_current(repository_root: str | Path = ".") -> dict[str, Any]:
    root = Path(repository_root)
    historical = audit_historical(root)
    receipt = _read_receipt(root)

    _require(receipt.get("schema_version") == 1, "successor receipt schema drifted")
    _require(receipt.get("policy_id") == POLICY_ID, "successor policy identity drifted")
    _require(receipt.get("repository") == "Thabearr/ATHENA", "repository identity drifted")
    _require(receipt.get("base_main_sha") == BASE_MAIN_SHA, "successor base main drifted")

    evidence = receipt.get("evidence_runs")
    _require(type(evidence) is list and len(evidence) == 2, "incident evidence set drifted")
    _require(tuple(row.get("run_id") for row in evidence) == INCIDENT_RUNS, "incident run IDs drifted")
    _require(tuple(row.get("artifact_id") for row in evidence) == INCIDENT_ARTIFACTS, "incident artifact IDs drifted")
    for row in evidence:
        _require(row.get("exact_commit_sha") == BASE_MAIN_SHA, "incident exact commit drifted")
        _require(row.get("status") == "RESEARCH_NO_CODE_SOURCE_INCOMPLETE", "incident status drifted")
        _require(row.get("failure") == runtime.INCOMPLETE_PAGINATION_STATE, "incident failure class drifted")
        _require(row.get("target_size") == 20 and row.get("selected_leg_count") == 0, "incident result drifted")
        _require(row.get("share_code") is None and row.get("wager_placed") is False, "incident authority/result drifted")

    runtime_policy = receipt.get("runtime_policy")
    _require(type(runtime_policy) is dict, "runtime policy receipt is missing")
    _require(runtime_policy.get("policy_id") == runtime.POLICY_ID, "runtime policy ID drifted")
    _require(runtime_policy.get("sha256_before") == OLD_RUNTIME_SHA256, "predecessor runtime SHA drifted")
    _require(runtime_policy.get("sha256_after") == NEW_RUNTIME_SHA256, "successor runtime SHA drifted")

    runtime.validate_contract()
    _require(runtime.calculate_policy_sha256() == NEW_RUNTIME_SHA256, "runtime calculated SHA drifted")
    _require(runtime.PINNED_POLICY_SHA256 == NEW_RUNTIME_SHA256, "runtime pinned SHA drifted")
    _require(runtime.MAX_CAPTURE_EPOCHS == 4, "runtime epoch bound drifted")
    _require(runtime.MAX_PAGES_PER_EPOCH == 20, "runtime page bound drifted")
    _require(runtime.MAX_SUCCESSFUL_PAGE_RESPONSES == 80, "runtime request bound drifted")
    _require(runtime.INTER_EPOCH_BACKOFF_SECONDS == 3, "runtime backoff drifted")

    stabilization = runtime._policy_payload().get("capture_stabilization", {})
    expected = {
        "recovery_semantics": "FRESH_CAPTURE_EPOCH_AFTER_EXACT_CROSS_PAGE_TOTALNUM_DRIFT",
        "exact_first_epoch_trigger": source.TOTALNUM_DRIFT_ERROR,
        "max_capture_epochs": 4,
        "max_pages_per_epoch": 20,
        "max_successful_page_responses": 80,
        "each_epoch_starts_at_page": 1,
        "inter_epoch_backoff_seconds": 3,
        "backoff_only_after_exact_totalnum_drift": True,
        "no_per_page_http_retry": True,
        "no_capture_epoch_beyond_bound": True,
        "failed_epoch_provider_absence_authority": False,
        "failed_epoch_identity_learning_authority": False,
        "failed_epoch_reconciliation_authority": False,
        "failed_epoch_selection_authority": False,
        "failed_epoch_pricing_authority": False,
        "failed_epoch_router_authority": False,
        "failed_epoch_portfolio_authority": False,
        "failed_epoch_delivery_authority": False,
        "cross_epoch_event_merge": False,
        "accepted_epoch_independently_source_v1_verified": True,
        "accepted_epoch_independently_runtime_complete": True,
        "source_fallback": False,
        "all_attempt_evidence_retained_under_source_evidence_root": True,
        "workflow_retry": False,
        "per_page_transport_retry": False,
        "provider_request_upper_bound": 80,
        "provider_request_upper_bound_is_finite": True,
    }
    _require(stabilization == expected, "bounded stabilization policy drifted")

    authority = receipt.get("authority")
    _require(type(authority) is dict and all(value is False for value in authority.values()), "implementation authority overclaimed")
    _require(receipt.get("merge_authorized") is False, "merge authority overclaimed")
    _require(receipt.get("live_proof_authorized") is False, "live proof authority overclaimed")
    _require(receipt.get("historical_ancestry", {}).get("historical_receipts_modified") is False, "historical receipt rewrite claimed")

    _require(runner.reconciliation is runtime and runner.upcoming_discovery is runtime, "active Current Shadow source owner changed")
    readiness = p3.check_f_upcoming_discovery_contract()
    _require(readiness.get("runtime_policy_sha256") == NEW_RUNTIME_SHA256, "P3 readiness pin is stale")

    for key in ("model", "pricing", "router", "portfolio", "login", "cookies", "wallet", "staking", "bet", "wager_placed"):
        _require(runtime.AUTHORITY[key] is False, f"runtime authority broadened: {key}")

    return {
        "status": "PASSED",
        "policy_id": POLICY_ID,
        "receipt_sha256": receipt["canonical_sha256"],
        "runtime_policy_id": runtime.POLICY_ID,
        "runtime_policy_sha256": runtime.PINNED_POLICY_SHA256,
        "max_capture_epochs": runtime.MAX_CAPTURE_EPOCHS,
        "max_successful_page_responses": runtime.MAX_SUCCESSFUL_PAGE_RESPONSES,
        "inter_epoch_backoff_seconds": runtime.INTER_EPOCH_BACKOFF_SECONDS,
        **historical,
    }

def audit(repository_root: str | Path = ".") -> dict[str, Any]:
    return audit_current(repository_root)

if __name__ == "__main__":
    print(json.dumps(audit(), sort_keys=True))
