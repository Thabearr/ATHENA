"""Offline audit for the reviewed shared pcUpcoming runtime migration."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from domain import current_shadow_all_market_runner as runner
from domain import current_shadow_fixture_identity_compatibility as compatibility
from domain import current_shadow_fixture_identity_v2 as identity
from domain import current_shadow_sportybet_international_provider_family_bridge as bridge
from domain import current_shadow_sportybet_pc_upcoming_discovery as source
from domain import current_shadow_sportybet_pc_upcoming_reconciliation as runtime
from domain import current_shadow_sportybet_upcoming_reconciliation as historical_wap
from domain import current_shadow_sportybet_paginated_discovery_reconciliation as paginated
from domain import current_shadow_sportybet_catalog_fanout_reconciliation as fanout
from scripts import audit_post_p4_4l_pc_upcoming_shared_football_source as source_audit
from scripts import audit_post_p4_4l_international_provider_family_bridge as bridge_audit
from scripts import verify_p3_0_e1_live_readiness as p3


RECEIPT_PATH = Path("artifacts/architecture/post_p4_4l_pc_upcoming_runtime_migration_v1.json")
BASE_MAIN = "34cfe161edd9c3c56d0c284c0eaa6dfe56087336"
SOURCE_RECEIPT_SHA256 = "8dde6427c296d966ff8d7f4cdec33e57a8c4210e8ecdb37071af68b0ca75bb34"
BRIDGE_RECEIPT_SHA256 = "34c183b5274e9e2c3320b5a8d75a123b7ebed2405aa55cdfb1af7d59c2613aa2"
OLD_WAP_SOURCE_SHA256 = "90c14bd68ed6e8205c16fedfa815d120c53f2af1a3a8f362eee2702a4223b9ff"
OLD_WAP_COMPATIBILITY_SHA256 = "e0718a5e7c9e0c707ba5cc7369910f3ec371bd1a9f7520ab41aa30df69d0ab12"
HISTORICAL_IDENTITY_COMPATIBILITY_SHA256 = "dbef6539dd7c5d1c1589debe8daca9378ea2e0c0bb32acf3315a0d1a005c2b58"
HISTORICAL_RUNTIME_WRAPPER_SHA256 = "e44d8b3476118a094d3e59f885f7456c3aebc677c07d8eeefaa232df5bc6a43e"
EXPECTED_SOURCE_KEYS = {("INT", 9806), ("INT", 9807), ("INT", 9808), ("INT", 9821), ("INT", 10608), ("INT", 114)}


class PcUpcomingRuntimeMigrationAuditError(ValueError):
    """Raised when current runtime ownership or its evidence lineage drifts."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PcUpcomingRuntimeMigrationAuditError(message)


def _read_json(root: Path, path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads((root / path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PcUpcomingRuntimeMigrationAuditError(f"{label} is unavailable or malformed") from exc
    _require(type(value) is dict, f"{label} must be an object")
    return value


def validate_receipt(receipt: Any) -> str:
    _require(type(receipt) is dict, "runtime migration receipt must be an object")
    embedded = receipt.get("canonical_sha256")
    _require(type(embedded) is str and len(embedded) == 64, "runtime receipt SHA is missing")
    semantic = dict(receipt)
    semantic.pop("canonical_sha256", None)
    actual = hashlib.sha256(_canonical(semantic)).hexdigest()
    _require(actual == embedded, "runtime migration receipt canonical SHA mismatch")
    _require(receipt.get("schema_version") == 1, "runtime receipt schema drifted")
    _require(receipt.get("repository") == "Thabearr/ATHENA", "runtime receipt repository drifted")
    _require(receipt.get("base_main_sha") == BASE_MAIN, "runtime receipt base SHA drifted")
    _require(receipt.get("source_review_counter_while_unmerged") == "2/5", "runtime receipt counter drifted")

    source_lineage = receipt.get("pc_upcoming_source")
    _require(type(source_lineage) is dict, "pcUpcoming source lineage missing")
    _require(source_lineage == {
        "policy_id": source.POLICY_ID,
        "policy_sha256": "63799058bec00abefb8d9b2ec9ba6dcad0c6e4775a54f17b07c0018e543ec075",
        "receipt_sha256": SOURCE_RECEIPT_SHA256,
        "endpoint": "/api/ng/factsCenter/pcUpcomingEvents",
        "source_method": "PUBLIC_ANONYMOUS_FACTS_CENTER_PC_UPCOMING_EVENTS_GET",
    }, "immutable PR #405 source ancestry drifted")
    bridge_lineage = receipt.get("international_provider_family_bridge")
    _require(type(bridge_lineage) is dict, "international bridge lineage missing")
    _require(bridge_lineage == {
        "policy_id": bridge.POLICY_ID,
        "policy_sha256": bridge.PINNED_POLICY_SHA256,
        "receipt_sha256": BRIDGE_RECEIPT_SHA256,
        "reviewed_source_keys": [list(key) for key in sorted(EXPECTED_SOURCE_KEYS)],
    }, "immutable PR #406 bridge ancestry/mappings drifted")
    _require(receipt.get("v2_semantic_registry_sha256") == identity.REGISTRY_SHA256 == identity.registry_sha256(), "V2 semantic registry pin drifted")
    _require(receipt.get("v2_seed_registry_sha256") == identity.SEED_REGISTRY_SHA256 == identity.seed_registry_sha256(), "V2 seed registry changed")
    _require(receipt.get("identity_compatibility_sha256") == HISTORICAL_IDENTITY_COMPATIBILITY_SHA256, "historical identity compatibility pin drifted")

    old_source = receipt.get("retained_old_wap_source")
    _require(type(old_source) is dict and old_source == {
        "policy_id": "ATHENA_CURRENT_SHADOW_UPCOMING_DISCOVERY_V1",
        "upstream_source_contract_sha256": OLD_WAP_SOURCE_SHA256,
        "current_compatibility_sha256": OLD_WAP_COMPATIBILITY_SHA256,
        "status": "RETAINED_HISTORICAL_RUNTIME_SOURCE_NOT_CURRENT_OWNER",
    }, "old WAP historical-source lineage/status drifted")
    runtime_row = receipt.get("runtime_wrapper")
    _require(type(runtime_row) is dict and runtime_row == {
        "policy_id": runtime.POLICY_ID,
        "policy_sha256": HISTORICAL_RUNTIME_WRAPPER_SHA256,
        "source_method": source.SOURCE_METHOD,
        "endpoint": source.SOURCE_PATH,
        "pagination_complete_required": True,
        "partial_pagination_provider_absence_authority": False,
        "direct_event_contract_sha256": runtime.DIRECT_EVENT_CONTRACT_SHA256,
    }, "runtime wrapper identity/completeness contract drifted")
    _require(receipt.get("current_shadow_runtime_source_changed") is True, "Current Shadow migration not recorded")
    _require(receipt.get("p3_runtime_source_changed") is True, "P3 migration not recorded")
    _require(receipt.get("current_shadow_and_p3_share_source") is True, "shared Current Shadow/P3 source not recorded")
    _require(receipt.get("old_wap_source_retained_historical") is True, "historical WAP retention not recorded")
    _require(receipt.get("paginated_runtime_authority") is False and receipt.get("fanout_runtime_authority") is False, "retired discovery authority broadened")
    _require(receipt.get("international_mappings_unchanged") is True and receipt.get("team_seeds_added") is False, "international mapping/team seed scope changed")
    _require(receipt.get("identity_state_schema_version") == 2, "identity state schema changed")
    _require(receipt.get("historical_p4_4l_and_provider_receipts_rewritten") is False, "historical receipt rewrite claimed")
    _require(receipt.get("runtime_capability") == dict(runtime.AUTHORITY), "runtime capability profile drifted")

    expected_false = {
        "model_authority_changed": False,
        "pricing_algorithm_changed": False,
        "router_algorithm_changed": False,
        "portfolio_algorithm_changed": False,
        "main_authority": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "bet": False,
        "wager_placed": False,
        "provider_acquisition_during_implementation": False,
        "workflow_dispatch_during_implementation": False,
        "live_proof_during_implementation": False,
        "share_code_action_during_implementation": False,
        "wager_action_during_implementation": False,
        "next_live_proof_authorized": False,
        "p4_4_complete": False,
        "architecture_checkpoint_e_complete": False,
    }
    _require(receipt.get("authority_and_actions") == expected_false, "runtime or implementation authority was broadened")
    return embedded


def audit(repository_root: str | Path = ".") -> dict[str, Any]:
    root = Path(repository_root)
    receipt = _read_json(root, RECEIPT_PATH, "runtime migration architecture receipt")
    receipt_sha = validate_receipt(receipt)
    from scripts import audit_p4_4n_sportybet_team_label_shape_compatibility as p44n
    p44n_state = p44n.audit(root)

    # These validators authenticate the historical receipts themselves. Their
    # old-owner assertions remain facts about those receipts, not today's owner.
    source_receipt = _read_json(
        root, source_audit.RECEIPT_PATH, "historical PR #405 source receipt"
    )
    source_receipt_sha = source_audit.validate_receipt(source_receipt)
    _require(source_receipt_sha == SOURCE_RECEIPT_SHA256, "historical PR #405 receipt changed")
    bridge_receipt = _read_json(
        root, bridge_audit.RECEIPT_PATH, "historical PR #406 bridge receipt"
    )
    bridge_receipt_sha = bridge_audit.validate_receipt(bridge_receipt)
    _require(bridge_receipt_sha == BRIDGE_RECEIPT_SHA256, "historical PR #406 receipt changed")

    runtime.validate_contract()
    _require(runner.reconciliation is runtime and runner.upcoming_discovery is runtime,
             "Current Shadow runner does not use the reviewed pcUpcoming wrapper")
    _require(runtime.POLICY_ID == receipt["runtime_wrapper"]["policy_id"], "runner policy differs from receipt")
    _require(runtime.PINNED_POLICY_SHA256 == p44n_state["runtime_wrapper_sha256"], "runner hash differs from P4.4N current-state supersession")
    _require(historical_wap.CURRENT_SHADOW_UPCOMING_POLICY_ID == "ATHENA_CURRENT_SHADOW_UPCOMING_DISCOVERY_V1",
             "historical WAP source identity was deleted or rewritten")
    _require(historical_wap.UPSTREAM_UPCOMING_SOURCE_CONTRACT_SHA256 == OLD_WAP_SOURCE_SHA256
             and historical_wap.CURRENT_SHADOW_UPCOMING_COMPATIBILITY_SHA256 == p44n_state["retained_wap_compatibility_sha256"],
             "historical WAP source or P4.4N-superseded current compatibility identity drifted")
    _require(source.PINNED_POLICY_SHA256 == source_lineage_sha(receipt), "PR #405 source contract pin drifted")
    _require(bridge.PINNED_POLICY_SHA256 == receipt["international_provider_family_bridge"]["policy_sha256"],
             "PR #406 bridge policy pin drifted")

    source_text = Path(runner.__file__).read_text(encoding="utf-8")
    _require("capture_current_paginated_discovery" not in source_text and "capture_catalog_fanout" not in source_text,
             "runner contains a forbidden fallback source")
    _require("current_shadow_sportybet_upcoming_reconciliation" not in source_text,
             "old WAP module is still imported by the active runner")
    _require(runtime._policy_payload()["runtime_pagination"]["partial_capture_provider_absence_authority"] is False,
             "partial pagination gained provider-absence authority")
    _require(runtime._policy_payload()["fixed_query"] == {
        "sportId": "sr:sport:1",
        "marketId": "1",
        "pageSize": 100,
        "todayGames": "false",
        "timeline": 48,
        "pageNum": "CONTIGUOUS_1_THROUGH_CEIL_PROVIDER_TOTAL_NUM_OVER_PAGE_SIZE",
        "_t": "RESPONSE_SCOPED_NONCE",
    }, "pcUpcoming runtime query semantics drifted")

    p3_source = p3.check_f_upcoming_discovery_contract()
    p3_shared = p3.check_i_pre_router_pipeline_readiness(root)
    _require(p3_source["runtime_policy_id"] == runtime.POLICY_ID
             and p3_source["runtime_policy_sha256"] == runtime.PINNED_POLICY_SHA256,
             "P3 readiness does not pin the runtime wrapper")
    _require(p3_shared["canonical_strategy_id"] == runtime.POLICY_ID
             and p3_shared["canonical_source_method"] == source.SOURCE_METHOD
             and p3_shared["supported_and_p3_strategy_unified"] is True
             and p3_shared["paginated_runtime_reconciliation_authority"] is False
             and p3_shared["catalog_fanout_runtime_authority"] is False,
             "SUPPORTED_REQUEST and P3 are not the same source owner")
    _require(p3.check_g_fanout_request_scope_validation()["global_echo_rejection_verified"] is True,
             "historical tournament-fanout global-echo rejection regressed")
    _require(paginated.validate_contract()["contract_sha256"] == paginated.EXPECTED_CONTRACT_SHA256,
             "historical paginated contract identity changed")
    _require(fanout.validate_contract()["contract_sha256"] == fanout.EXPECTED_CONTRACT_SHA256,
             "historical fanout contract identity changed")

    return {
        "status": "PASSED",
        "runtime_policy_id": runtime.POLICY_ID,
        "runtime_policy_sha256": runtime.PINNED_POLICY_SHA256,
        "source_policy_sha256": source.PINNED_POLICY_SHA256,
        "bridge_policy_sha256": bridge.PINNED_POLICY_SHA256,
        "migration_receipt_sha256": receipt_sha,
        "historical_source_receipt_sha256": source_receipt_sha,
        "historical_bridge_receipt_sha256": bridge_receipt_sha,
        "p4_4n_receipt_sha256": p44n_state["receipt_sha256"],
        "current_shadow_and_p3_shared_source": True,
        "pagination_complete_required": True,
        "old_wap_retained_historical": True,
        "provider_acquisition_used": False,
        "workflow_dispatch_used": False,
    }


def source_lineage_sha(receipt: dict[str, Any]) -> str:
    return receipt["pc_upcoming_source"]["policy_sha256"]


if __name__ == "__main__":
    print(json.dumps(audit(), sort_keys=True))
