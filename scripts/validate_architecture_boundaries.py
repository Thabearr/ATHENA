"""Fail-closed, exact-ref architecture boundary validation for P0.4.

This tooling imports only the reviewed P0.2 static-analysis helpers.  It never
imports ATHENA business/runtime modules, executes workflows, or uses a provider.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.audit_repository_architecture import (
    detect_dynamic_imports,
    list_tracked_files,
    parse_imports,
    path_to_module,
    read_files_at_ref,
    resolve_import,
    resolve_ref,
)

SCHEMA_VERSION = 1
POLICY_ID = "ATHENA_ARCHITECTURE_BOUNDARY_CI_V1"
EXPECTED_BASE_MAIN = "d18976128b15d773b77487a361abe9781bd32cc3"
AUTHORITY_CONTRACT_POLICY_ID = "ATHENA_MAIN_SHADOW_AUTHORITY_PARITY_V1"
AUTHORITY_CONTRACT_SHA256 = "d4f525a0eb8d3ffe07e5b64a3452d758bc9e180c5b1db37feecbac1faf395bfe"
AUTHORITY_CONTRACT_PATH = "config/architecture/main-shadow-authority-parity-v1.json"
P0_INVENTORY_PATH = "artifacts/architecture/repository-architecture-inventory-v1.json"
P0_INVENTORY_SHA256 = "a77617557659c8d8a7a5e6887ba65529a87f5f7c229113a36ca6d2f9f2a26a4a"
P0_INVENTORY_SOURCE_COMMIT = "e04cbbeaeff999a1e5dd3ff7891857b4813a7fac"
RULE_IDS = (
    "MODEL_PROBABILITY_CANNOT_IMPORT_SPORTYBET_DELIVERY",
    "PRICING_CANNOT_IMPORT_PORTFOLIO_OR_WAGER",
    "RESEARCH_ORCHESTRATION_CANNOT_IMPORT_WAGER_AUTHORITY",
)
TOP_LEVEL_KEYS = {
    "approved_parallel_authority_adrs", "authority_contract_path",
    "authority_contract_policy_id", "authority_contract_sha256",
    "authority_families", "delivery_target_module_ids", "delivery_target_tokens",
    "model_probability_parent_namespaces", "model_probability_tokens",
    "policy_base_main", "policy_id", "pricing_source_prefixes",
    "research_orchestration_selector", "rules", "schema_version",
    "wager_authority_tokens",
}
FAMILY_PREFIXES = {
    "market_router": ("domain.market_router", "domain.current_shadow_all_market_router"),
    "price_all_and_de_vig": ("domain.price_all", "domain.current_shadow_all_market_price_all"),
    "portfolio_optimizer": ("domain.portfolio_optimizer", "domain.current_shadow_all_market_portfolio"),
}
ADR_HEADINGS = (
    "Status", "Context", "Evidence", "Decision", "Alternatives considered",
    "Consequences", "Migration plan", "Rollback / revisit trigger",
)


class BoundaryError(ValueError):
    """The versioned policy or its evidence did not prove a safe boundary."""


class BoundaryViolation(BoundaryError):
    def __init__(self, diagnostics: list[dict[str, Any]]) -> None:
        self.diagnostics = _sorted_diagnostics(diagnostics)
        super().__init__("architecture boundary violation")


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BoundaryError(message)


def _read_policy(path: Path) -> tuple[bytes, dict[str, Any]]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BoundaryError(f"invalid policy JSON: {path}") from exc
    _require(isinstance(value, dict), "policy root must be an object")
    _require(raw == canonical_json_bytes(value), "policy JSON is not canonical deterministic bytes")
    return raw, value


def _is_boundary(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + "_") or module.startswith(prefix + ".")


def _is_public(module: str) -> bool:
    return not module.split(".")[-1].startswith("_")


def _module_index(repo_root: Path, sha: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in list_tracked_files(repo_root, sha):
        module = path_to_module(path)
        if module:
            _require(module not in result, f"duplicate canonical module ID at {sha}: {module}")
            result[module] = path
    return result


def _sorted_diagnostics(diagnostics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(diagnostics, key=lambda item: (
        item.get("rule_id", ""), item.get("source_path", item.get("candidate_path", "")),
        item.get("line_number", 0), item.get("target_module", item.get("candidate_module", "")),
    ))


def _family_modules(modules: dict[str, str], prefixes: tuple[str, ...]) -> list[str]:
    return sorted(module for module in modules if _is_public(module) and any(_is_boundary(module, prefix) for prefix in prefixes))


def _validate_policy(policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    _require(set(policy) == TOP_LEVEL_KEYS, "policy schema changed")
    _require(policy.get("schema_version") == SCHEMA_VERSION, "wrong schema version")
    _require(policy.get("policy_id") == POLICY_ID, "wrong policy ID")
    _require(policy.get("policy_base_main") == EXPECTED_BASE_MAIN, "wrong P0.4 base main")
    _require(policy.get("authority_contract_path") == AUTHORITY_CONTRACT_PATH, "wrong P0.3 contract path")
    _require(policy.get("authority_contract_policy_id") == AUTHORITY_CONTRACT_POLICY_ID, "wrong P0.3 policy ID")
    _require(policy.get("authority_contract_sha256") == AUTHORITY_CONTRACT_SHA256, "wrong P0.3 contract hash")
    _require(tuple(policy.get("rules", ())) == RULE_IDS, "unknown or reordered rule ID")
    for field in ("delivery_target_module_ids", "delivery_target_tokens", "model_probability_parent_namespaces", "model_probability_tokens", "pricing_source_prefixes", "wager_authority_tokens"):
        values = policy.get(field)
        _require(isinstance(values, list) and values and len(values) == len(set(values)) and all(isinstance(value, str) and value for value in values), f"invalid {field}")
    selector = policy.get("research_orchestration_selector")
    _require(selector == {"authority_profile": "SHADOW_ONLY", "canonical_status": "PROFILE_ORCHESTRATION"}, "invalid research orchestration selector")
    families = policy.get("authority_families")
    _require(isinstance(families, list) and len(families) == 3, "invalid authority family registry")
    by_responsibility: dict[str, dict[str, Any]] = {}
    for family in families:
        _require(isinstance(family, dict) and set(family) == {"baseline_public_module_ids", "public_prefixes", "responsibility_id"}, "invalid authority family schema")
        responsibility = family.get("responsibility_id")
        _require(responsibility in FAMILY_PREFIXES and responsibility not in by_responsibility, "unknown or duplicate authority family")
        _require(tuple(family.get("public_prefixes", ())) == FAMILY_PREFIXES[responsibility], f"reserved prefixes changed: {responsibility}")
        baseline = family.get("baseline_public_module_ids")
        _require(isinstance(baseline, list) and baseline == sorted(set(baseline)) and baseline, f"invalid baseline modules: {responsibility}")
        by_responsibility[responsibility] = family
    _require(set(by_responsibility) == set(FAMILY_PREFIXES), "authority family registry incomplete")
    adrs = policy.get("approved_parallel_authority_adrs")
    _require(isinstance(adrs, list), "approved ADR registry must be a list")
    return by_responsibility


def _validate_authority_contract(raw: bytes) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    _require(hashlib.sha256(raw).hexdigest() == AUTHORITY_CONTRACT_SHA256, "wrong P0.3 contract bytes")
    try:
        contract = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BoundaryError("invalid P0.3 contract JSON") from exc
    _require(isinstance(contract, dict) and contract.get("policy_id") == AUTHORITY_CONTRACT_POLICY_ID, "wrong P0.3 contract policy ID")
    _require(contract.get("active_shadow_deviations") == [], "P0.3 active Shadow deviations must remain zero")
    _require(
        contract.get("p0_inventory_evidence") == {
            "csv_sha256": "6585ab79b29e9a51751e4cc1060f6a20643457aff5090c436b8eaae451202e51",
            "json_sha256": P0_INVENTORY_SHA256,
            "source_commit": P0_INVENTORY_SOURCE_COMMIT,
        },
        "P0.3 does not pin the reviewed P0.2 inventory evidence",
    )
    assignments = contract.get("reviewed_module_assignments")
    _require(isinstance(assignments, list), "P0.3 assignments missing")
    return assignments, contract


def _p0_inventory_digest(raw: bytes) -> str:
    """Return P0.2's pinned digest, allowing only its terminal CRLF transport form."""
    normalized = raw.replace(b"\r\n", b"\n")
    checkout_terminal = normalized[:-1] + b"\r\n" if normalized.endswith(b"\n") else normalized
    for candidate in (raw, checkout_terminal):
        digest = hashlib.sha256(candidate).hexdigest()
        if digest == P0_INVENTORY_SHA256:
            return digest
    return hashlib.sha256(raw).hexdigest()


def _p0_inventory_modules(raw: bytes) -> dict[str, str]:
    _require(_p0_inventory_digest(raw) == P0_INVENTORY_SHA256, "wrong P0.2 inventory bytes")
    try:
        inventory = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BoundaryError("invalid P0.2 inventory JSON") from exc
    _require(isinstance(inventory, dict), "P0.2 inventory root must be an object")
    _require(inventory.get("source_commit") == P0_INVENTORY_SOURCE_COMMIT, "wrong P0.2 inventory source commit")
    records = inventory.get("python_modules")
    _require(isinstance(records, list), "P0.2 inventory python modules missing")
    modules: dict[str, str] = {}
    for record in records:
        _require(isinstance(record, dict), "invalid P0.2 module record")
        module, path = record.get("module"), record.get("path")
        _require(isinstance(module, str) and module and isinstance(path, str) and path, "invalid P0.2 module identity")
        _require(module not in modules, f"duplicate P0.2 module identity: {module}")
        modules[module] = path
    return modules


def _baseline_module_index(repo_root: Path, base_ref: str, exact_ref: str, tracked: set[str]) -> dict[str, str]:
    """Read the exact P0.4 base, or its P0.3-pinned immutable inventory in shallow CI.

    GitHub's Tests checkout can contain only the pull-request commit.  The
    fallback has authority only because P0.3 pins the P0.2 artifact bytes and
    source commit; it never consults untracked files or the working tree.
    """
    try:
        base_sha = resolve_ref(repo_root, base_ref)
    except RuntimeError:
        _require(P0_INVENTORY_PATH in tracked, "P0.2 inventory is not tracked at exact ref")
        raw = read_files_at_ref(repo_root, exact_ref, [P0_INVENTORY_PATH])[P0_INVENTORY_PATH]
        return _p0_inventory_modules(raw)
    _require(base_sha == EXPECTED_BASE_MAIN, "P0.4 policy base does not resolve exactly")
    return _module_index(repo_root, base_sha)


def _research_sources(assignments: list[dict[str, Any]], selector: dict[str, str]) -> set[str]:
    result: set[str] = set()
    for entry in assignments:
        _require(isinstance(entry, dict), "invalid P0.3 assignment")
        if entry.get("authority_profile") == selector["authority_profile"] and entry.get("canonical_status") == selector["canonical_status"]:
            component = entry.get("component_id")
            _require(isinstance(component, str) and component, "P0.3 orchestration component missing")
            result.add(component)
    _require(result, "P0.3 research orchestration selector resolved no sources")
    return result


def _tokenized(module: str, tokens: list[str]) -> bool:
    expected = set(tokens)
    return any(
        component in expected or any(part in expected for part in component.split("_"))
        for component in module.split(".")
    )


def _is_model_probability(module: str, policy: dict[str, Any]) -> bool:
    parts = module.split(".")
    if not parts or parts[0] not in policy["model_probability_parent_namespaces"]:
        return False
    return parts[0] == "models" or _tokenized(module, policy["model_probability_tokens"])


def _is_pricing(module: str, policy: dict[str, Any]) -> bool:
    return any(
        module.startswith(prefix) if prefix.endswith("_") else _is_boundary(module, prefix)
        for prefix in policy["pricing_source_prefixes"]
    )


def _is_delivery(module: str, policy: dict[str, Any]) -> bool:
    return module in set(policy["delivery_target_module_ids"]) or _tokenized(module, policy["delivery_target_tokens"])


def _is_portfolio(module: str) -> bool:
    return _is_boundary(module, "domain.portfolio_optimizer") or _is_boundary(module, "domain._portfolio_optimizer") or _is_boundary(module, "domain.current_shadow_all_market_portfolio")


def _dependency_violations(
    policy: dict[str, Any], modules: dict[str, str], sources: dict[str, str], research_sources: set[str],
) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    known_modules = set(modules)
    controlled = sorted(module for module in modules if _is_model_probability(module, policy) or _is_pricing(module, policy) or module in research_sources)
    for source_module in controlled:
        source_path = modules[source_module]
        source = sources[source_path]
        imports, import_diagnostics = parse_imports(source, source_path)
        if import_diagnostics:
            raise BoundaryError(f"unable to parse boundary-controlled source: {source_path}")
        for record in imports:
            relative_diagnostics: list[dict[str, Any]] = []
            targets = resolve_import(record, source_module, known_modules, relative_diagnostics, source_path)
            if relative_diagnostics:
                raise BoundaryError(f"BOUNDARY_RELATIVE_IMPORT_TARGET_UNPROVEN: {source_path}:{record['lineno']}")
            for target in targets:
                rule_id = ""
                reason = ""
                if _is_model_probability(source_module, policy) and _is_delivery(target, policy):
                    rule_id, reason = RULE_IDS[0], "model/probability imports SportyBet delivery"
                elif _is_pricing(source_module, policy) and _is_portfolio(target):
                    rule_id, reason = RULE_IDS[1], "pricing imports portfolio authority"
                elif _is_pricing(source_module, policy) and _tokenized(target, policy["wager_authority_tokens"]):
                    rule_id, reason = RULE_IDS[1], "pricing imports wager authority"
                elif source_module in research_sources and _tokenized(target, policy["wager_authority_tokens"]):
                    rule_id, reason = RULE_IDS[2], "research orchestration imports authenticated or wager authority"
                if rule_id:
                    diagnostics.append({"rule_id": rule_id, "source_module": source_module, "source_path": source_path, "target_module": target, "line_number": record["lineno"], "reason": reason})
        for dynamic in detect_dynamic_imports(source, source_path):
            if not dynamic["is_literal"]:
                diagnostics.append({"rule_id": "BOUNDARY_DYNAMIC_IMPORT_TARGET_UNPROVEN", "source_module": source_module, "source_path": source_path, "target_module": "<UNPROVEN>", "line_number": dynamic["lineno"], "reason": "boundary-controlled source uses non-literal dynamic import"})
                continue
            target = dynamic["literal_target"]
            if target not in known_modules:
                continue
            rule_id = ""
            reason = ""
            if _is_model_probability(source_module, policy) and _is_delivery(target, policy):
                rule_id, reason = RULE_IDS[0], "model/probability dynamically imports SportyBet delivery"
            elif _is_pricing(source_module, policy) and _is_portfolio(target):
                rule_id, reason = RULE_IDS[1], "pricing dynamically imports portfolio authority"
            elif _is_pricing(source_module, policy) and _tokenized(target, policy["wager_authority_tokens"]):
                rule_id, reason = RULE_IDS[1], "pricing dynamically imports wager authority"
            elif source_module in research_sources and _tokenized(target, policy["wager_authority_tokens"]):
                rule_id, reason = RULE_IDS[2], "research orchestration dynamically imports authenticated or wager authority"
            if rule_id:
                diagnostics.append({"rule_id": rule_id, "source_module": source_module, "source_path": source_path, "target_module": target, "line_number": dynamic["lineno"], "reason": reason})
    return diagnostics


def _approved_adr_modules(policy: dict[str, Any], tracked: set[str], contents: dict[str, bytes], families: dict[str, dict[str, Any]]) -> set[str]:
    approved: set[str] = set()
    seen_ids: set[str] = set()
    for entry in policy["approved_parallel_authority_adrs"]:
        required = {"adr_id", "adr_path", "status", "responsibility_id", "approved_module_ids"}
        _require(isinstance(entry, dict) and set(entry) == required, "invalid ADR policy schema")
        adr_id, adr_path = entry.get("adr_id"), entry.get("adr_path")
        _require(isinstance(adr_id, str) and adr_id and adr_id not in seen_ids, "duplicate or invalid ADR ID")
        seen_ids.add(adr_id)
        _require(entry.get("status") == "ACCEPTED", "ADR policy status must be ACCEPTED")
        _require(isinstance(adr_path, str) and adr_path.startswith("docs/architecture/adrs/") and adr_path.split("/")[-1].startswith(adr_id), "ADR path is outside approved directory")
        _require(adr_path in tracked and adr_path in contents, "ADR is not tracked at exact ref")
        text = contents[adr_path].decode("utf-8", errors="strict")
        _require("## Status" in text and "Accepted" in text, "ADR document status is not Accepted")
        _require(all(f"## {heading}" in text for heading in ADR_HEADINGS), "ADR document lacks required v2 sections")
        responsibility = entry.get("responsibility_id")
        _require(responsibility in families, "ADR has unknown responsibility")
        module_ids = entry.get("approved_module_ids")
        _require(isinstance(module_ids, list) and module_ids and module_ids == sorted(set(module_ids)), "invalid ADR approved module IDs")
        for module in module_ids:
            _require(isinstance(module, str) and module and "*" not in module and not any(char in module for char in "[](){}?+|\\"), "wildcard or malformed ADR module ID")
            _require(any(_is_boundary(module, prefix) for prefix in families[responsibility]["public_prefixes"]), "ADR approves module outside its responsibility family")
            _require(module not in approved, "new authority module approved by multiple ADRs")
            approved.add(module)
    return approved


def _parallel_authority_diagnostics(families: dict[str, dict[str, Any]], modules: dict[str, str], approved: set[str]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for responsibility, family in families.items():
        allowed = set(family["baseline_public_module_ids"]) | {
            module for module in approved
            if any(_is_boundary(module, prefix) for prefix in family["public_prefixes"])
        }
        for candidate in _family_modules(modules, tuple(family["public_prefixes"])):
            if candidate not in allowed:
                diagnostics.append({"rule_id": "PARALLEL_AUTHORITY_REQUIRES_ACCEPTED_ADR", "responsibility_id": responsibility, "candidate_module": candidate, "candidate_path": modules[candidate], "line_number": 0, "required_adr_status": "ACCEPTED", "reason": "new public authority family member lacks an accepted exact ADR"})
    return diagnostics


def validate_architecture_boundaries(repo_root: Path, policy_path: Path, ref: str) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    sha = resolve_ref(repo_root, ref)
    raw_policy, policy = _read_policy(policy_path)
    families = _validate_policy(policy)
    tracked = set(list_tracked_files(repo_root, sha))
    try:
        policy_relative = policy_path.resolve().relative_to(repo_root).as_posix()
    except ValueError as exc:
        raise BoundaryError("policy path must be repository-local") from exc
    _require(policy_relative in tracked, "policy is not tracked at exact ref")
    exact_policy = read_files_at_ref(repo_root, sha, [policy_relative])[policy_relative]
    _require(exact_policy == raw_policy, "policy bytes do not match exact ref")
    _require(AUTHORITY_CONTRACT_PATH in tracked, "P0.3 contract is not tracked at exact ref")
    authority_raw = read_files_at_ref(repo_root, sha, [AUTHORITY_CONTRACT_PATH])[AUTHORITY_CONTRACT_PATH]
    assignments, _authority_contract = _validate_authority_contract(authority_raw)
    modules = _module_index(repo_root, sha)
    base_modules = _baseline_module_index(repo_root, policy["policy_base_main"], sha, tracked)
    for responsibility, family in families.items():
        observed = _family_modules(base_modules, tuple(family["public_prefixes"]))
        _require(observed == family["baseline_public_module_ids"], f"baseline family list does not match P0.4 base: {responsibility}")
    source_modules = set(module for module in modules if _is_model_probability(module, policy) or _is_pricing(module, policy))
    research_sources = _research_sources(assignments, policy["research_orchestration_selector"])
    _require(research_sources <= set(modules), "P0.3 research orchestration source absent at exact ref")
    source_modules |= research_sources
    source_paths = sorted(modules[module] for module in source_modules)
    contents = read_files_at_ref(repo_root, sha, source_paths)
    adr_paths = [entry["adr_path"] for entry in policy["approved_parallel_authority_adrs"] if isinstance(entry, dict) and isinstance(entry.get("adr_path"), str)]
    if adr_paths:
        contents.update(read_files_at_ref(repo_root, sha, adr_paths))
    approved = _approved_adr_modules(policy, tracked, contents, families)
    diagnostics = _parallel_authority_diagnostics(families, modules, approved)
    source_text = {path: contents[path].decode("utf-8", errors="strict") for path in source_paths}
    diagnostics.extend(_dependency_violations(policy, modules, source_text, research_sources))
    if diagnostics:
        raise BoundaryViolation(diagnostics)
    return {"policy_id": POLICY_ID, "policy_sha256": hashlib.sha256(raw_policy).hexdigest(), "resolved_ref": sha, "baseline_parallel_authority_adr_count": len(policy["approved_parallel_authority_adrs"]), "forbidden_dependency_violation_count": 0}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        result = validate_architecture_boundaries(args.repo_root, args.policy, args.ref)
    except BoundaryViolation as exc:
        print(json.dumps({"diagnostics": exc.diagnostics}, ensure_ascii=False, sort_keys=True))
        return 2
    except (OSError, RuntimeError, BoundaryError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
