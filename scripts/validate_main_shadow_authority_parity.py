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
        _require(entry.get("current_owner_status") in OWNER_STATUSES, f"{rid}: invalid owner status")
        mode = entry.get("parity_requirement")
        _require(mode in PARITY_MODES, f"{rid}: invalid parity mode")
        _require(entry.get("shadow_deviation_policy") == ("FORBIDDEN" if mode == "EXACT_SHARED_BASELINE" else "REGISTERED_CHALLENGER_ONLY"), f"{rid}: invalid deviation policy")
        result[rid] = entry
    return result


def _validate_assignments(assignments: Any, inventory: dict[str, Any]) -> None:
    _require(isinstance(assignments, list), "reviewed_module_assignments must be a list")
    ids = [entry.get("component_id") for entry in assignments if isinstance(entry, dict)]
    _unique(ids, "module assignment")
    inventory_modules = {entry.get("module"): entry.get("path") for entry in inventory.get("python_modules", []) if isinstance(entry, dict)}
    for entry in assignments:
        _require(isinstance(entry, dict), "invalid module assignment")
        component = entry.get("component_id")
        _require(component in inventory_modules and inventory_modules[component] == entry.get("component_path"), f"assignment does not reference a P0.2 tracked module: {component}")
        role = entry.get("authority_profile")
        _require(role in AUTHORITY_PROFILES, f"unknown authority profile: {component}")
        _require(entry.get("cleanup_disposition") == "UNCLASSIFIED", f"cleanup disposition must remain independent: {component}")
        _require(entry.get("canonical_status") != "CANONICAL_SHARED" or role == "SHARED_CANONICAL", f"canonical status/role mismatch: {component}")
        if role == "SHARED_CANONICAL":
            _require(entry.get("main_shadow_shared_evidence") is True, f"SHARED_CANONICAL needs Main+Shadow evidence: {component}")
        if role == "MAIN_ONLY":
            _require(entry.get("canonical_status") != "CANONICAL_SHARED", f"MAIN_ONLY cannot own shared canonical baseline: {component}")
        if role == "SHADOW_ONLY":
            _require(entry.get("production_authority") is False, f"SHADOW_ONLY cannot have production authority: {component}")
        if role == "RESEARCH_CHALLENGER":
            _require(entry.get("main_authority") is False, f"RESEARCH_CHALLENGER cannot have Main authority: {component}")
    supported = inventory.get("supported_roots")
    _require(isinstance(supported, list), "inventory supported_roots missing")
    roots = {entry.get("root_identifier") for entry in supported if isinstance(entry, dict)}
    _require(len(roots) == 6, "P0.2 supported-root count changed")
    _require(roots <= set(ids), "every P0.2 supported root needs an explicit P0.3 assignment")
    by_id = {entry["component_id"]: entry for entry in assignments}
    _require(by_id["build_acca"]["authority_profile"] == "MAIN_ONLY", "build_acca must be MAIN_ONLY")
    _require(by_id["build_acca"]["canonical_status"] == "SUPPORTED_LEGACY", "build_acca must remain supported legacy")
    for component in ("scripts.execute_current_shadow_request", "scripts.restore_current_shadow_history_prime_artifact", "scripts.send_current_shadow_email"):
        _require(by_id[component]["authority_profile"] == "SHADOW_ONLY", f"{component} must be SHADOW_ONLY")
    for component in ("scripts.run_fotmob_utc_native_xg_fresh_holdout_tick", "scripts.run_fotmob_fresh_holdout_release_receipt_mirror"):
        _require(by_id[component]["authority_profile"] == "UNKNOWN", f"{component} must remain UNKNOWN")


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
    _require(required <= set(ids), "required fresh-holdout protection missing")
    for entry in entries:
        _require(entry.get("authority_profile") == "UNKNOWN", "protected infrastructure must not be made a challenger")
        _require(entry.get("cleanup_authority") == "NONE" and entry.get("deletion_allowed") is False, "protected infrastructure cannot gain deletion authority")
        _require(entry.get("protection_class") == "PROTECTED_RESEARCH_INFRASTRUCTURE", "invalid research protection class")
        _require(entry.get("reason") == "ACTIVE_PROSPECTIVE_EVIDENCE_CAMPAIGN", "invalid research protection reason")


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
    _require(hashlib.sha256(inventory_raw).hexdigest() == EXPECTED_INVENTORY_SHA256, "wrong P0 inventory digest")
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
    for entry in gaps:
        _require(entry.get("responsibility_id") in responsibilities and entry.get("status") == "UNRESOLVED_PREEXISTING" and entry.get("production_authority_change") is False and entry.get("required_resolution_wave") in {"P1", "P2", "P3"}, "invalid known parity gap")
    _validate_deviations(contract.get("active_shadow_deviations"), responsibilities)
    policy = contract.get("promotion_policy")
    _require(isinstance(policy, dict), "promotion_policy missing")
    for key in ("automatic_promotion", "backtest_win_is_sufficient_for_promotion", "holdout_pass_is_sufficient_for_promotion", "share_code_success_is_sufficient_for_promotion", "shadow_success_is_sufficient_for_promotion"):
        _require(policy.get(key) is False, f"{key} must be false")
    _require(policy.get("explicit_review_required") is True and policy.get("explicit_promotion_pr_required") is True, "explicit promotion review/PR required")
    safety = contract.get("safety_boundary")
    _require(isinstance(safety, dict) and all(safety.get(key) is False for key in safety), "safety authority must remain false")
    request = contract.get("request_semantics")
    _require(isinstance(request, dict) and request.get("parity_mode") == "EXACT_SHARED_BASELINE" and request.get("target_legs") == {"maximum": 50, "minimum": 1} and request.get("date_window_days") == {"maximum": 7, "minimum": 1} and request.get("target_legs_distinct_from_target_total_odds") is True and request.get("truthful_shortfall_permitted") is True, "invalid request semantics parity")
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
