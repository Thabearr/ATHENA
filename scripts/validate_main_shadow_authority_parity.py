"""Fail-closed validator for the P0.3 Main/Shadow authority contract.

This validator reads only the versioned contract and immutable P0.2 JSON
inventory.  It deliberately imports no ATHENA runtime module and has no
network, provider, database, cache, workflow, or secret access.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
POLICY_ID = "ATHENA_MAIN_SHADOW_AUTHORITY_PARITY_V1"
EXPECTED_BASE_MAIN = "147c09d058e8609ef11296bd7e0f74e4c6626b63"
EXPECTED_INVENTORY_SHA256 = "a77617557659c8d8a7a5e6887ba65529a87f5f7c229113a36ca6d2f9f2a26a4a"
EXPECTED_INVENTORY_SOURCE_COMMIT = "e04cbbeaeff999a1e5dd3ff7891857b4813a7fac"
AUTHORITY_PROFILES = (
    "SHARED_CANONICAL", "MAIN_ONLY", "SHADOW_ONLY", "RESEARCH_CHALLENGER",
    "HISTORICAL_EVIDENCE", "UNKNOWN",
)
RESPONSIBILITY_IDS = (
    "fixture_identity", "source_evidence_and_lineage", "fixture_state_schema",
    "provider_market_semantics", "provider_quote_identity_and_freshness",
    "settlement_semantics", "request_date_and_target_semantics",
    "champion_feature_interface", "champion_probability_interface",
    "calibration_interface", "market_projection", "price_all_and_de_vig",
    "market_router", "portfolio_optimizer", "delivery_share_code_transport",
    "run_receipt_and_observability",
)
PARITY_MODES = ("EXACT_SHARED_BASELINE", "SHARED_BASELINE_REGISTERED_CHALLENGER_ALLOWED")
OWNER_STATUSES = (
    "RESOLVED_SHARED_CANONICAL", "PENDING_CANONICAL_PROMOTION",
    "PENDING_SHARED_CORE_EXTRACTION", "PENDING_LEGACY_MIGRATION",
)
EXACT_SHARED_RESPONSIBILITIES = frozenset({
    "fixture_identity", "source_evidence_and_lineage", "fixture_state_schema",
    "provider_market_semantics", "provider_quote_identity_and_freshness",
    "settlement_semantics", "request_date_and_target_semantics",
    "delivery_share_code_transport", "run_receipt_and_observability",
})
CHALLENGER_CAPABLE_RESPONSIBILITIES = frozenset(set(RESPONSIBILITY_IDS) - EXACT_SHARED_RESPONSIBILITIES)
REQUIRED_ASSIGNMENTS = frozenset({
    "build_acca", "domain.current_shadow_all_market_runner",
    "domain.current_shadow_all_market_price_all", "domain.current_shadow_all_market_router",
    "domain.current_shadow_all_market_portfolio", "domain.current_shadow_all_market_share_code",
    "domain.price_all_v3_current_provider", "domain.market_router_v3_current_provider",
    "domain.portfolio_optimizer_v3_current_provider", "engine.market_selector",
    "services.prediction_service", "scripts.execute_current_shadow_request",
    "scripts.restore_current_shadow_history_prime_artifact", "scripts.send_current_shadow_email",
    "scripts.run_fotmob_utc_native_xg_fresh_holdout_tick",
    "scripts.run_fotmob_fresh_holdout_release_receipt_mirror",
})
REQUIRED_GAPS = frozenset({
    "main_shadow_pipeline_not_yet_one_shared_core", "current_shadow_profile_specific_price_all",
    "current_shadow_profile_specific_router", "current_shadow_profile_specific_portfolio",
    "current_shadow_profile_specific_share_code", "v3_current_provider_price_all_candidate_unproven",
    "v3_current_provider_router_candidate_unproven", "v3_current_provider_portfolio_candidate_unproven",
})
SAFETY_KEYS = frozenset({"cookies", "login", "provider_create_reload_verification_is_wager", "shadow_production_portfolio_authority", "shadow_production_pricing_authority", "shadow_production_router_authority", "shadow_production_selection_authority", "share_code_is_wager", "staking", "wager", "wallet"})
TOP_LEVEL_KEYS = frozenset({"active_shadow_deviations", "authority_profile_vocabulary", "contract_base_main", "execution_profiles", "known_parity_gaps", "p0_inventory_evidence", "policy_id", "promotion_policy", "protected_research_infrastructure", "request_semantics", "reviewed_module_assignments", "safety_boundary", "schema_version", "shadow_deviation_policy", "shared_responsibilities"})
PROTECTED_RULES = frozenset({"ACTIVE_PROSPECTIVE_RESEARCH", "NO_DELETION_AUTHORITY", "NO_MIGRATION_WITHOUT_EXPERIMENT_REVIEW", "NO_SYNTHETIC_BACKFILL", "NO_AUTOMATIC_PROMOTION"})
PROMOTION_LIFECYCLE = ("REGISTERED_CHALLENGER", "SHADOW_EVALUATION", "PROSPECTIVE_WALK_FORWARD_EVIDENCE", "REVIEW_REQUIRED", "EXPLICIT_PROMOTION_PR", "MAIN")
EXPECTED_OWNER_STATUS_BY_RESPONSIBILITY = {
    "calibration_interface": "PENDING_SHARED_CORE_EXTRACTION", "champion_feature_interface": "PENDING_SHARED_CORE_EXTRACTION", "champion_probability_interface": "PENDING_SHARED_CORE_EXTRACTION", "delivery_share_code_transport": "PENDING_SHARED_CORE_EXTRACTION", "fixture_identity": "PENDING_SHARED_CORE_EXTRACTION", "fixture_state_schema": "PENDING_SHARED_CORE_EXTRACTION", "market_projection": "PENDING_SHARED_CORE_EXTRACTION", "market_router": "PENDING_CANONICAL_PROMOTION", "portfolio_optimizer": "PENDING_CANONICAL_PROMOTION", "price_all_and_de_vig": "PENDING_CANONICAL_PROMOTION", "provider_market_semantics": "PENDING_SHARED_CORE_EXTRACTION", "provider_quote_identity_and_freshness": "PENDING_SHARED_CORE_EXTRACTION", "request_date_and_target_semantics": "PENDING_LEGACY_MIGRATION", "run_receipt_and_observability": "PENDING_SHARED_CORE_EXTRACTION", "settlement_semantics": "PENDING_SHARED_CORE_EXTRACTION", "source_evidence_and_lineage": "PENDING_SHARED_CORE_EXTRACTION",
}
EXPECTED_GAP_SEMANTICS = {
    "main_shadow_pipeline_not_yet_one_shared_core": {
        "affected_responsibility_ids": ["fixture_state_schema", "price_all_and_de_vig", "market_router", "portfolio_optimizer", "delivery_share_code_transport"],
        "current_main_state": "SUPPORTED_LEGACY_MAIN_ENTRYPOINT_WITHOUT_PROVEN_SHARED_CORE",
        "current_shadow_state": "CURRENT_SHADOW_RESEARCH_PIPELINE_EXISTS_SEPARATELY",
        "production_authority_change": False, "resolution_completion_wave": "P3",
        "resolution_start_wave": "P1", "status": "UNRESOLVED_PREEXISTING",
    },
    "current_shadow_profile_specific_price_all": {
        "affected_responsibility_ids": ["price_all_and_de_vig"],
        "current_main_state": "NO_PROVEN_SHARED_CANONICAL_PRICE_ALL_OWNER",
        "current_shadow_state": "TRANSITIONAL_PROFILE_SPECIFIC_IMPLEMENTATION",
        "production_authority_change": False, "resolution_completion_wave": "P2",
        "resolution_start_wave": "P2", "status": "UNRESOLVED_PREEXISTING",
    },
    "current_shadow_profile_specific_router": {
        "affected_responsibility_ids": ["market_router"],
        "current_main_state": "NO_PROVEN_SHARED_CANONICAL_ROUTER_OWNER",
        "current_shadow_state": "TRANSITIONAL_PROFILE_SPECIFIC_IMPLEMENTATION",
        "production_authority_change": False, "resolution_completion_wave": "P2",
        "resolution_start_wave": "P2", "status": "UNRESOLVED_PREEXISTING",
    },
    "current_shadow_profile_specific_portfolio": {
        "affected_responsibility_ids": ["portfolio_optimizer"],
        "current_main_state": "NO_PROVEN_SHARED_CANONICAL_PORTFOLIO_OWNER",
        "current_shadow_state": "TRANSITIONAL_PROFILE_SPECIFIC_IMPLEMENTATION",
        "production_authority_change": False, "resolution_completion_wave": "P2",
        "resolution_start_wave": "P2", "status": "UNRESOLVED_PREEXISTING",
    },
    "current_shadow_profile_specific_share_code": {
        "affected_responsibility_ids": ["delivery_share_code_transport"],
        "current_main_state": "NO_PROVEN_SHARED_CANONICAL_DELIVERY_OWNER",
        "current_shadow_state": "TRANSITIONAL_PROFILE_SPECIFIC_IMPLEMENTATION",
        "production_authority_change": False, "resolution_completion_wave": "P2",
        "resolution_start_wave": "P2", "status": "UNRESOLVED_PREEXISTING",
    },
    "v3_current_provider_price_all_candidate_unproven": {
        "affected_responsibility_ids": ["price_all_and_de_vig"],
        "current_main_state": "LEGACY_MAIN_OWNER_REQUIRES_REACHABILITY_REVIEW",
        "current_shadow_state": "V3_CURRENT_PROVIDER_PRICE_ALL_CANDIDATE_UNPROVEN",
        "production_authority_change": False, "resolution_completion_wave": "P2",
        "resolution_start_wave": "P1", "status": "UNRESOLVED_PREEXISTING",
    },
    "v3_current_provider_router_candidate_unproven": {
        "affected_responsibility_ids": ["market_router"],
        "current_main_state": "LEGACY_MAIN_OWNER_REQUIRES_REACHABILITY_REVIEW",
        "current_shadow_state": "V3_CURRENT_PROVIDER_ROUTER_CANDIDATE_UNPROVEN",
        "production_authority_change": False, "resolution_completion_wave": "P2",
        "resolution_start_wave": "P1", "status": "UNRESOLVED_PREEXISTING",
    },
    "v3_current_provider_portfolio_candidate_unproven": {
        "affected_responsibility_ids": ["portfolio_optimizer"],
        "current_main_state": "LEGACY_MAIN_OWNER_REQUIRES_REACHABILITY_REVIEW",
        "current_shadow_state": "V3_CURRENT_PROVIDER_PORTFOLIO_CANDIDATE_UNPROVEN",
        "production_authority_change": False, "resolution_completion_wave": "P2",
        "resolution_start_wave": "P1", "status": "UNRESOLVED_PREEXISTING",
    },
}
EXPECTED_ASSIGNMENT_POLICY = {
    "build_acca": {"authority_profile": "MAIN_ONLY", "canonical_status": "SUPPORTED_LEGACY", "cleanup_disposition": "UNCLASSIFIED", "component_id": "build_acca", "component_path": "build_acca.py", "observed_production_authority_state": "SEPARATELY_GOVERNED", "production_authority_granted_by_this_contract": False, "review_state": "SUPPORTED_LEGACY_MAIN_ENTRYPOINT"},
    "domain.current_shadow_all_market_runner": {"authority_profile": "SHADOW_ONLY", "canonical_status": "PROFILE_ORCHESTRATION", "cleanup_disposition": "UNCLASSIFIED", "component_id": "domain.current_shadow_all_market_runner", "component_path": "domain/current_shadow_all_market_runner.py", "observed_production_authority_state": "PROVEN_FALSE", "production_authority_granted_by_this_contract": False, "review_state": "RESEARCH_SHADOW_ONLY"},
    "domain.current_shadow_all_market_price_all": {"authority_profile": "SHADOW_ONLY", "canonical_status": "TRANSITIONAL_PROFILE_SPECIFIC_IMPLEMENTATION", "cleanup_disposition": "UNCLASSIFIED", "component_id": "domain.current_shadow_all_market_price_all", "component_path": "domain/current_shadow_all_market_price_all.py", "future_shared_responsibility": "price_all_and_de_vig", "observed_production_authority_state": "PROVEN_FALSE", "production_authority_granted_by_this_contract": False, "review_state": "KNOWN_PARITY_GAP"},
    "domain.current_shadow_all_market_router": {"authority_profile": "SHADOW_ONLY", "canonical_status": "TRANSITIONAL_PROFILE_SPECIFIC_IMPLEMENTATION", "cleanup_disposition": "UNCLASSIFIED", "component_id": "domain.current_shadow_all_market_router", "component_path": "domain/current_shadow_all_market_router.py", "future_shared_responsibility": "market_router", "observed_production_authority_state": "PROVEN_FALSE", "production_authority_granted_by_this_contract": False, "review_state": "KNOWN_PARITY_GAP"},
    "domain.current_shadow_all_market_portfolio": {"authority_profile": "SHADOW_ONLY", "canonical_status": "TRANSITIONAL_PROFILE_SPECIFIC_IMPLEMENTATION", "cleanup_disposition": "UNCLASSIFIED", "component_id": "domain.current_shadow_all_market_portfolio", "component_path": "domain/current_shadow_all_market_portfolio.py", "future_shared_responsibility": "portfolio_optimizer", "observed_production_authority_state": "PROVEN_FALSE", "production_authority_granted_by_this_contract": False, "review_state": "KNOWN_PARITY_GAP"},
    "domain.current_shadow_all_market_share_code": {"authority_profile": "SHADOW_ONLY", "canonical_status": "TRANSITIONAL_PROFILE_SPECIFIC_IMPLEMENTATION", "cleanup_disposition": "UNCLASSIFIED", "component_id": "domain.current_shadow_all_market_share_code", "component_path": "domain/current_shadow_all_market_share_code.py", "future_shared_responsibility": "delivery_share_code_transport", "observed_production_authority_state": "PROVEN_FALSE", "production_authority_granted_by_this_contract": False, "review_state": "KNOWN_PARITY_GAP"},
    "domain.price_all_v3_current_provider": {"authority_profile": "UNKNOWN", "canonical_status": "CANONICAL_PROMOTION_CANDIDATE_UNPROVEN", "cleanup_disposition": "UNCLASSIFIED", "component_id": "domain.price_all_v3_current_provider", "component_path": "domain/price_all_v3_current_provider.py", "observed_production_authority_state": "UNKNOWN", "production_authority_granted_by_this_contract": False, "review_state": "CANONICAL_PROMOTION_CANDIDATE_UNPROVEN"},
    "domain.market_router_v3_current_provider": {"authority_profile": "UNKNOWN", "canonical_status": "CANONICAL_PROMOTION_CANDIDATE_UNPROVEN", "cleanup_disposition": "UNCLASSIFIED", "component_id": "domain.market_router_v3_current_provider", "component_path": "domain/market_router_v3_current_provider.py", "observed_production_authority_state": "UNKNOWN", "production_authority_granted_by_this_contract": False, "review_state": "CANONICAL_PROMOTION_CANDIDATE_UNPROVEN"},
    "domain.portfolio_optimizer_v3_current_provider": {"authority_profile": "UNKNOWN", "canonical_status": "CANONICAL_PROMOTION_CANDIDATE_UNPROVEN", "cleanup_disposition": "UNCLASSIFIED", "component_id": "domain.portfolio_optimizer_v3_current_provider", "component_path": "domain/portfolio_optimizer_v3_current_provider.py", "observed_production_authority_state": "UNKNOWN", "production_authority_granted_by_this_contract": False, "review_state": "CANONICAL_PROMOTION_CANDIDATE_UNPROVEN"},
    "engine.market_selector": {"authority_profile": "UNKNOWN", "canonical_status": "UNRESOLVED", "cleanup_disposition": "UNCLASSIFIED", "component_id": "engine.market_selector", "component_path": "engine/market_selector.py", "observed_production_authority_state": "UNKNOWN", "production_authority_granted_by_this_contract": False, "review_state": "LEGACY_REACHABILITY_REVIEW_REQUIRED"},
    "services.prediction_service": {"authority_profile": "UNKNOWN", "canonical_status": "UNRESOLVED", "cleanup_disposition": "UNCLASSIFIED", "component_id": "services.prediction_service", "component_path": "services/prediction_service.py", "observed_production_authority_state": "UNKNOWN", "production_authority_granted_by_this_contract": False, "review_state": "LEGACY_REACHABILITY_REVIEW_REQUIRED"},
    "scripts.execute_current_shadow_request": {"authority_profile": "SHADOW_ONLY", "canonical_status": "PROFILE_ORCHESTRATION", "cleanup_disposition": "UNCLASSIFIED", "component_id": "scripts.execute_current_shadow_request", "component_path": "scripts/execute_current_shadow_request.py", "observed_production_authority_state": "PROVEN_FALSE", "production_authority_granted_by_this_contract": False, "review_state": "RESEARCH_SHADOW_ONLY"},
    "scripts.restore_current_shadow_history_prime_artifact": {"authority_profile": "SHADOW_ONLY", "canonical_status": "PROFILE_ORCHESTRATION", "cleanup_disposition": "UNCLASSIFIED", "component_id": "scripts.restore_current_shadow_history_prime_artifact", "component_path": "scripts/restore_current_shadow_history_prime_artifact.py", "observed_production_authority_state": "PROVEN_FALSE", "production_authority_granted_by_this_contract": False, "review_state": "RESEARCH_SHADOW_ONLY"},
    "scripts.send_current_shadow_email": {"authority_profile": "SHADOW_ONLY", "canonical_status": "PROFILE_ORCHESTRATION", "cleanup_disposition": "UNCLASSIFIED", "component_id": "scripts.send_current_shadow_email", "component_path": "scripts/send_current_shadow_email.py", "observed_production_authority_state": "PROVEN_FALSE", "production_authority_granted_by_this_contract": False, "review_state": "RESEARCH_SHADOW_ONLY"},
    "scripts.run_fotmob_utc_native_xg_fresh_holdout_tick": {"authority_profile": "UNKNOWN", "canonical_status": "RESEARCH_INFRASTRUCTURE", "cleanup_disposition": "UNCLASSIFIED", "component_id": "scripts.run_fotmob_utc_native_xg_fresh_holdout_tick", "component_path": "scripts/run_fotmob_utc_native_xg_fresh_holdout_tick.py", "observed_production_authority_state": "PROVEN_FALSE", "production_authority_granted_by_this_contract": False, "review_state": "PROTECTED_RESEARCH_INFRASTRUCTURE"},
    "scripts.run_fotmob_fresh_holdout_release_receipt_mirror": {"authority_profile": "UNKNOWN", "canonical_status": "RESEARCH_INFRASTRUCTURE", "cleanup_disposition": "UNCLASSIFIED", "component_id": "scripts.run_fotmob_fresh_holdout_release_receipt_mirror", "component_path": "scripts/run_fotmob_fresh_holdout_release_receipt_mirror.py", "observed_production_authority_state": "PROVEN_FALSE", "production_authority_granted_by_this_contract": False, "review_state": "PROTECTED_RESEARCH_INFRASTRUCTURE"},
}


class ValidationError(ValueError):
    """A policy or immutable-evidence condition was not proven."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _read_json(path: Path) -> tuple[bytes, dict[str, Any]]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"invalid JSON: {path}") from exc
    _require(isinstance(value, dict), f"JSON root must be an object: {path}")
    return raw, value


def _inventory_digest(raw: bytes) -> str:
    """Hash canonical P0.2 bytes, tolerating only transport-only endings.

    P0.2's published digest covers its terminal CRLF.  The tracked Git blob may
    carry the same terminal delimiter as LF.  These representations have
    identical JSON semantics; no other byte is repaired.
    """
    normalized = raw.replace(b"\r\n", b"\n")
    checkout_terminal = (
        normalized[:-1] + b"\r\n" if normalized.endswith(b"\n") else normalized
    )
    candidates = (raw, checkout_terminal)
    for candidate in candidates:
        digest = hashlib.sha256(candidate).hexdigest()
        if digest == EXPECTED_INVENTORY_SHA256:
            return digest
    return hashlib.sha256(raw).hexdigest()


def _unique(values: list[str], label: str) -> None:
    _require(len(values) == len(set(values)), f"duplicate {label}")


def _validate_profiles(profiles: Any) -> None:
    _require(isinstance(profiles, dict) and set(profiles) == {"MAIN", "SHADOW"}, "exactly MAIN and SHADOW execution profiles are required")
    main, shadow = profiles["MAIN"], profiles["SHADOW"]
    _require(main == {
        "automatic_promotion": False, "may_activate_unpromoted_challenger": False,
        "production_authority": True, "profile_id": "MAIN", "research_authority": False,
        "wager_authority_from_this_contract": False,
    }, "invalid MAIN execution profile")
    _require(shadow == {
        "automatic_promotion": False, "challenger_must_be_explicitly_registered": True,
        "cookies": False, "login": False, "may_activate_unpromoted_challenger": True,
        "production_authority": False, "profile_id": "SHADOW", "research_authority": True,
        "staking": False, "wager": False, "wallet": False,
    }, "invalid SHADOW execution profile")


def _validate_responsibilities(responsibilities: Any) -> dict[str, dict[str, Any]]:
    _require(isinstance(responsibilities, list), "shared_responsibilities must be a list")
    ids = [entry.get("responsibility_id") for entry in responsibilities if isinstance(entry, dict)]
    _require(tuple(ids) == tuple(sorted(RESPONSIBILITY_IDS)), "shared responsibility IDs must be exact and deterministic")
    result: dict[str, dict[str, Any]] = {}
    for entry in responsibilities:
        _require(isinstance(entry, dict), "invalid responsibility")
        rid = entry["responsibility_id"]
        _require(entry.get("canonical_scope") == "SHARED", f"{rid}: canonical_scope must be SHARED")
        _require(entry.get("baseline_required_in_main") is True and entry.get("baseline_required_in_shadow") is True, f"{rid}: shared baseline required in both profiles")
        _require(entry.get("current_owner_status") == EXPECTED_OWNER_STATUS_BY_RESPONSIBILITY[rid], f"{rid}: reviewed owner status changed")
        expected_mode = "EXACT_SHARED_BASELINE" if rid in EXACT_SHARED_RESPONSIBILITIES else "SHARED_BASELINE_REGISTERED_CHALLENGER_ALLOWED"
        expected_policy = "FORBIDDEN" if rid in EXACT_SHARED_RESPONSIBILITIES else "REGISTERED_CHALLENGER_ONLY"
        _require(entry.get("parity_requirement") == expected_mode, f"{rid}: immutable parity mode changed")
        _require(entry.get("shadow_deviation_policy") == expected_policy, f"{rid}: immutable deviation policy changed")
        _require(entry.get("current_owner_status") != "RESOLVED_SHARED_CANONICAL", f"{rid}: no shared canonical owner is proven in P0.3")
        result[rid] = entry
    return result


def _validate_assignments(assignments: Any, inventory: dict[str, Any]) -> None:
    _require(isinstance(assignments, list), "reviewed_module_assignments must be a list")
    ids = [entry.get("component_id") for entry in assignments if isinstance(entry, dict)]
    _unique(ids, "module assignment")
    _require(set(ids) == REQUIRED_ASSIGNMENTS, "reviewed P0.3 assignment baseline changed")
    inventory_modules = {entry.get("module"): entry.get("path") for entry in inventory.get("python_modules", []) if isinstance(entry, dict)}
    for entry in assignments:
        _require(isinstance(entry, dict), "invalid module assignment")
        component = entry.get("component_id")
        expected = EXPECTED_ASSIGNMENT_POLICY.get(component)
        _require(expected is not None, f"unreviewed P0.3 assignment: {component}")
        _require(set(entry) == set(expected), f"invalid reviewed assignment schema: {component}")
        _require(entry == expected, f"reviewed assignment semantics changed: {component}")
        _require(component in inventory_modules and inventory_modules[component] == entry.get("component_path"), f"assignment does not reference a P0.2 tracked module: {component}")
        role = entry.get("authority_profile")
        _require(role in AUTHORITY_PROFILES, f"unknown authority profile: {component}")
        _require(entry.get("cleanup_disposition") == "UNCLASSIFIED", f"cleanup disposition must remain independent: {component}")
        _require("production_authority" not in entry, f"mixed production_authority field is forbidden: {component}")
        _require(entry.get("production_authority_granted_by_this_contract") is False, f"P0.3 grants no production authority: {component}")
        _require(entry.get("observed_production_authority_state") in {"SEPARATELY_GOVERNED", "PROVEN_FALSE", "UNKNOWN"}, f"invalid observed production authority state: {component}")
        _require(entry.get("canonical_status") != "CANONICAL_SHARED" or role == "SHARED_CANONICAL", f"canonical status/role mismatch: {component}")
        _require(role != "SHARED_CANONICAL", f"P0.3 has zero shared canonical assignments: {component}")
        if role == "MAIN_ONLY":
            _require(entry.get("canonical_status") != "CANONICAL_SHARED", f"MAIN_ONLY cannot own shared canonical baseline: {component}")
        if role == "SHADOW_ONLY":
            _require(entry.get("observed_production_authority_state") == "PROVEN_FALSE", f"SHADOW_ONLY must have proven-false observed authority: {component}")
        if role == "RESEARCH_CHALLENGER":
            _require(entry.get("main_authority") is False, f"RESEARCH_CHALLENGER cannot have Main authority: {component}")
    supported = inventory.get("supported_roots")
    _require(isinstance(supported, list), "inventory supported_roots missing")
    roots = {entry.get("root_identifier") for entry in supported if isinstance(entry, dict)}
    _require(len(roots) == 6, "P0.2 supported-root count changed")
    _require(roots <= set(ids), "every P0.2 supported root needs an explicit P0.3 assignment")


def _validate_protected(entries: Any) -> None:
    _require(isinstance(entries, list), "protected_research_infrastructure must be a list")
    ids = [entry.get("component_id") for entry in entries if isinstance(entry, dict)]
    _unique(ids, "protected research entry")
    required = {
        ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml",
        ".github/workflows/bridge-fotmob-fresh-holdout-continuity-receipts.yml",
        "scripts.run_fotmob_utc_native_xg_fresh_holdout_tick",
        "scripts.run_fotmob_fresh_holdout_release_receipt_mirror",
    }
    _require(set(ids) == required, "required fresh-holdout protection baseline changed")
    for entry in entries:
        _require(entry.get("authority_profile") == "UNKNOWN", "protected infrastructure must not be made a challenger")
        _require(entry.get("cleanup_authority") == "NONE" and entry.get("deletion_allowed") is False, "protected infrastructure cannot gain deletion authority")
        _require(entry.get("protection_class") == "PROTECTED_RESEARCH_INFRASTRUCTURE", "invalid research protection class")
        _require(entry.get("reason") == "ACTIVE_PROSPECTIVE_EVIDENCE_CAMPAIGN", "invalid research protection reason")
        _require(frozenset(entry.get("rules", [])) == PROTECTED_RULES, "protected research rules changed")


def _validate_deviations(deviations: Any, responsibilities: dict[str, dict[str, Any]]) -> None:
    _require(isinstance(deviations, list), "active_shadow_deviations must be a list")
    ids = [entry.get("deviation_id") for entry in deviations if isinstance(entry, dict)]
    _unique(ids, "deviation ID")
    required = {
        "deviation_id", "responsibility_id", "baseline_component_id", "challenger_component_id",
        "challenger_authority_profile", "research_only", "main_authority",
        "production_selection_authority", "automatic_promotion", "evidence_status",
        "review_required", "promotion_pr_required",
    }
    for entry in deviations:
        _require(isinstance(entry, dict) and required <= set(entry), "incomplete registered Shadow deviation")
        rid = entry["responsibility_id"]
        _require(rid in responsibilities, "unregistered responsibility in Shadow deviation")
        _require(responsibilities[rid]["parity_requirement"] == "SHARED_BASELINE_REGISTERED_CHALLENGER_ALLOWED", "deviation forbidden for exact-shared responsibility")
        _require(bool(entry["baseline_component_id"]) and bool(entry["challenger_component_id"]), "deviation needs baseline and challenger identities")
        _require(entry["challenger_authority_profile"] == "RESEARCH_CHALLENGER", "invalid challenger authority")
        _require(entry["research_only"] is True and entry["main_authority"] is False and entry["production_selection_authority"] is False and entry["automatic_promotion"] is False and entry["review_required"] is True and entry["promotion_pr_required"] is True, "unsafe Shadow challenger deviation")


def validate_contract(contract_path: Path, inventory_path: Path) -> dict[str, Any]:
    contract_raw, contract = _read_json(contract_path)
    inventory_raw, inventory = _read_json(inventory_path)
    _require(contract_raw == canonical_json_bytes(contract), "contract JSON is not canonical deterministic bytes")
    _require(set(contract) == TOP_LEVEL_KEYS, "top-level contract schema changed")
    _require(_inventory_digest(inventory_raw) == EXPECTED_INVENTORY_SHA256, "wrong P0 inventory digest")
    _require(contract.get("schema_version") == SCHEMA_VERSION, "invalid schema version")
    _require(contract.get("policy_id") == POLICY_ID, "invalid policy ID")
    _require(contract.get("contract_base_main") == EXPECTED_BASE_MAIN, "wrong contract base main")
    evidence = contract.get("p0_inventory_evidence")
    _require(evidence == {"csv_sha256": "6585ab79b29e9a51751e4cc1060f6a20643457aff5090c436b8eaae451202e51", "json_sha256": EXPECTED_INVENTORY_SHA256, "source_commit": EXPECTED_INVENTORY_SOURCE_COMMIT}, "wrong P0 inventory evidence")
    _require(inventory.get("source_commit") == EXPECTED_INVENTORY_SOURCE_COMMIT, "wrong inventory source commit")
    _require(tuple(contract.get("authority_profile_vocabulary", [])) == AUTHORITY_PROFILES, "authority-profile vocabulary must be exact")
    _validate_profiles(contract.get("execution_profiles"))
    responsibilities = _validate_responsibilities(contract.get("shared_responsibilities"))
    _validate_assignments(contract.get("reviewed_module_assignments"), inventory)
    _validate_protected(contract.get("protected_research_infrastructure"))
    gaps = contract.get("known_parity_gaps")
    _require(isinstance(gaps, list), "known_parity_gaps must be a list")
    gap_ids = [entry.get("gap_id") for entry in gaps if isinstance(entry, dict)]
    _unique(gap_ids, "parity-gap ID")
    _require(set(gap_ids) == REQUIRED_GAPS, "required baseline parity gaps changed")
    for entry in gaps:
        _require(set(entry) == {"gap_id", "affected_responsibility_ids", "current_main_state", "current_shadow_state", "status", "production_authority_change", "resolution_start_wave", "resolution_completion_wave"}, "invalid known parity gap schema")
        affected = entry.get("affected_responsibility_ids")
        _require(isinstance(affected, list) and affected and set(affected) <= set(responsibilities), "invalid parity-gap responsibilities")
        _require(entry.get("status") == "UNRESOLVED_PREEXISTING" and entry.get("production_authority_change") is False, "invalid known parity gap authority")
        waves = {"P1": 1, "P2": 2, "P3": 3}
        _require(entry.get("resolution_start_wave") in waves and entry.get("resolution_completion_wave") in waves and waves[entry["resolution_start_wave"]] <= waves[entry["resolution_completion_wave"]], "invalid parity-gap waves")
        expected = {"gap_id": entry["gap_id"], **EXPECTED_GAP_SEMANTICS[entry["gap_id"]]}
        _require(entry == expected, "reviewed parity-gap semantics changed")
    pipeline = next(item for item in gaps if item["gap_id"] == "main_shadow_pipeline_not_yet_one_shared_core")
    _require(pipeline["resolution_start_wave"] == "P1" and pipeline["resolution_completion_wave"] == "P3", "pipeline gap must span P1 through P3")
    _require(contract.get("active_shadow_deviations") == [], "P0.3 permits no active Shadow deviations")
    deviation_policy = contract.get("shadow_deviation_policy")
    _require(deviation_policy == {"activation_requires_registered_baseline": True, "activation_requires_registered_challenger": True, "activation_requires_research_challenger_role": True, "activation_requires_review": True, "allowed_parity_mode": "SHARED_BASELINE_REGISTERED_CHALLENGER_ALLOWED", "automatic_promotion": False, "required_fields": ["deviation_id", "responsibility_id", "baseline_component_id", "challenger_component_id", "challenger_authority_profile", "research_only", "main_authority", "production_selection_authority", "automatic_promotion", "evidence_status", "review_required", "promotion_pr_required"]}, "invalid Shadow deviation policy")
    policy = contract.get("promotion_policy")
    _require(isinstance(policy, dict) and set(policy) == {"automatic_promotion", "backtest_win_is_sufficient_for_promotion", "explicit_promotion_pr_required", "explicit_review_required", "holdout_pass_is_sufficient_for_promotion", "lifecycle", "shadow_success_is_sufficient_for_promotion", "share_code_success_is_sufficient_for_promotion"}, "promotion_policy schema changed")
    for key in ("automatic_promotion", "backtest_win_is_sufficient_for_promotion", "holdout_pass_is_sufficient_for_promotion", "share_code_success_is_sufficient_for_promotion", "shadow_success_is_sufficient_for_promotion"):
        _require(policy.get(key) is False, f"{key} must be false")
    _require(policy.get("explicit_review_required") is True and policy.get("explicit_promotion_pr_required") is True, "explicit promotion review/PR required")
    _require(tuple(policy.get("lifecycle", ())) == PROMOTION_LIFECYCLE, "promotion lifecycle changed")
    safety = contract.get("safety_boundary")
    _require(isinstance(safety, dict) and set(safety) == SAFETY_KEYS and all(value is False for value in safety.values()), "safety authority must remain false")
    request = contract.get("request_semantics")
    _require(request == {"concrete_date_resolution_before_orchestration": True, "date_window_days": {"maximum": 7, "minimum": 1}, "parity_mode": "EXACT_SHARED_BASELINE", "responsibility_id": "request_date_and_target_semantics", "target_legs": {"maximum": 50, "minimum": 1}, "target_legs_distinct_from_target_total_odds": True, "truthful_shortfall_permitted": True, "weekday_names_resolve_to_concrete_dates": True}, "invalid request semantics parity")
    return {"contract_sha256": hashlib.sha256(contract_raw).hexdigest(), "policy_id": POLICY_ID, "supported_root_count": 6}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = validate_contract(args.contract, args.inventory)
    except (OSError, ValidationError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
