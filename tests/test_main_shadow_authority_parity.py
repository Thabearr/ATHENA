"""P0.3 authority/parity contract tests; no ATHENA runtime is imported."""
from __future__ import annotations

import hashlib
import ast
import json
import socket
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from scripts import validate_main_shadow_authority_parity as validator

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/architecture/main-shadow-authority-parity-v1.json"
INVENTORY = ROOT / "artifacts/architecture/repository-architecture-inventory-v1.json"
INVENTORY_RELATIVE_PATH = "artifacts/architecture/repository-architecture-inventory-v1.json"


def _payload() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def _committed_inventory_bytes() -> bytes:
    """Use the immutable tracked P0.2 blob, not a restored test-cache copy."""
    return subprocess.run(
        ["git", "show", f"HEAD:{INVENTORY_RELATIVE_PATH}"],
        check=True,
        cwd=ROOT,
        capture_output=True,
    ).stdout


def _validate(payload: dict, tmp_path: Path) -> dict:
    candidate = tmp_path / "contract.json"
    candidate.write_bytes(validator.canonical_json_bytes(payload))
    inventory = tmp_path / "inventory.json"
    inventory.write_bytes(_committed_inventory_bytes())
    return validator.validate_contract(candidate, inventory)


def _fails(payload: dict, tmp_path: Path) -> None:
    with pytest.raises(validator.ValidationError):
        _validate(payload, tmp_path)


def _assignment(payload: dict, component_id: str) -> dict:
    return next(item for item in payload["reviewed_module_assignments"] if item["component_id"] == component_id)


def test_baseline_contract_is_valid_and_deterministic(tmp_path: Path) -> None:
    payload = _payload()
    first = _validate(payload, tmp_path)
    second = _validate(payload, tmp_path)
    assert first == second
    assert first["contract_sha256"] == hashlib.sha256(CONTRACT.read_bytes()).hexdigest()
    assert CONTRACT.read_bytes() == validator.canonical_json_bytes(payload)


def test_inventory_digest_rejects_semantic_mutation_but_tolerates_checkout_eol(tmp_path: Path) -> None:
    crlf_inventory = tmp_path / "inventory-crlf.json"
    crlf_inventory.write_bytes(_committed_inventory_bytes().replace(b"\n", b"\r\n"))
    assert validator.validate_contract(CONTRACT, crlf_inventory)["supported_root_count"] == 6
    changed_inventory = tmp_path / "inventory-changed.json"
    changed_inventory.write_bytes(_committed_inventory_bytes().replace(b"ATHENA_REPOSITORY_ARCHITECTURE_INVENTORY_V1", b"ATHENA_REPOSITORY_ARCHITECTURE_INVENTORY_X1"))
    with pytest.raises(validator.ValidationError, match="wrong P0 inventory digest"):
        validator.validate_contract(CONTRACT, changed_inventory)


@pytest.mark.parametrize(("mutate", "label"), [
    (lambda p: p.__setitem__("schema_version", 2), "wrong schema"),
    (lambda p: p.__setitem__("policy_id", "WRONG"), "wrong policy"),
    (lambda p: p["p0_inventory_evidence"].__setitem__("json_sha256", "0" * 64), "wrong inventory digest"),
    (lambda p: p.__setitem__("authority_profile_vocabulary", ["UNKNOWN"]), "wrong authority vocabulary"),
    (lambda p: p["execution_profiles"].pop("MAIN"), "missing MAIN"),
    (lambda p: p["execution_profiles"]["MAIN"].__setitem__("may_activate_unpromoted_challenger", True), "main challenger"),
    (lambda p: p["execution_profiles"]["SHADOW"].__setitem__("production_authority", True), "shadow production"),
    (lambda p: p["execution_profiles"]["SHADOW"].__setitem__("wager", True), "shadow wager"),
    (lambda p: p["promotion_policy"].__setitem__("holdout_pass_is_sufficient_for_promotion", True), "holdout promotion"),
    (lambda p: p["promotion_policy"].__setitem__("share_code_success_is_sufficient_for_promotion", True), "share code promotion"),
    (lambda p: p["promotion_policy"].__setitem__("backtest_win_is_sufficient_for_promotion", True), "backtest promotion"),
    (lambda p: p["promotion_policy"].__setitem__("explicit_promotion_pr_required", False), "missing promotion PR"),
    (lambda p: p["safety_boundary"].__setitem__("wager", True), "wager safety"),
])
def test_core_fail_closed_mutations(mutate, label: str, tmp_path: Path) -> None:
    payload = _payload()
    mutate(payload)
    _fails(payload, tmp_path)


def test_cleanup_is_not_inferred_from_authority(tmp_path: Path) -> None:
    payload = _payload()
    _assignment(payload, "engine.market_selector")["cleanup_disposition"] = "DELETE"
    _fails(payload, tmp_path)


def test_all_supported_roots_are_covered_and_correctly_classified() -> None:
    payload = _payload()
    assignments = {item["component_id"]: item for item in payload["reviewed_module_assignments"]}
    inventory = json.loads(_committed_inventory_bytes().decode("utf-8"))
    roots = {item["root_identifier"] for item in inventory["supported_roots"]}
    assert roots <= assignments.keys()
    assert assignments["build_acca"]["authority_profile"] == "MAIN_ONLY"
    assert assignments["build_acca"]["canonical_status"] != "CANONICAL_SHARED"
    for root in ("scripts.execute_current_shadow_request", "scripts.restore_current_shadow_history_prime_artifact", "scripts.send_current_shadow_email"):
        assert assignments[root]["authority_profile"] == "SHADOW_ONLY"
    for root in ("scripts.run_fotmob_utc_native_xg_fresh_holdout_tick", "scripts.run_fotmob_fresh_holdout_release_receipt_mirror"):
        assert assignments[root]["authority_profile"] == "UNKNOWN"


def test_shadow_runner_and_transitional_pipeline_are_not_canonical() -> None:
    payload = _payload()
    assert _assignment(payload, "domain.current_shadow_all_market_runner")["authority_profile"] == "SHADOW_ONLY"
    for component in ("domain.current_shadow_all_market_price_all", "domain.current_shadow_all_market_router", "domain.current_shadow_all_market_portfolio", "domain.current_shadow_all_market_share_code"):
        assignment = _assignment(payload, component)
        assert assignment["authority_profile"] == "SHADOW_ONLY"
        assert assignment["canonical_status"] == "TRANSITIONAL_PROFILE_SPECIFIC_IMPLEMENTATION"
        assert assignment["review_state"] == "KNOWN_PARITY_GAP"
    for component in ("domain.price_all_v3_current_provider", "domain.market_router_v3_current_provider", "domain.portfolio_optimizer_v3_current_provider"):
        assert _assignment(payload, component)["canonical_status"] == "CANONICAL_PROMOTION_CANDIDATE_UNPROVEN"
    for component in ("engine.market_selector", "services.prediction_service"):
        assert _assignment(payload, component)["review_state"] == "LEGACY_REACHABILITY_REVIEW_REQUIRED"


def test_fresh_holdout_is_protected_not_a_challenger(tmp_path: Path) -> None:
    payload = _payload()
    protected = {item["component_id"]: item for item in payload["protected_research_infrastructure"]}
    for component in ("scripts.run_fotmob_utc_native_xg_fresh_holdout_tick", "scripts.run_fotmob_fresh_holdout_release_receipt_mirror"):
        assert protected[component]["authority_profile"] == "UNKNOWN"
        assert protected[component]["deletion_allowed"] is False
    protected["scripts.run_fotmob_utc_native_xg_fresh_holdout_tick"]["deletion_allowed"] = True
    _fails(payload, tmp_path)


def _valid_deviation(payload: dict) -> dict:
    return {
        "automatic_promotion": False,
        "baseline_component_id": "baseline.price_all",
        "challenger_authority_profile": "RESEARCH_CHALLENGER",
        "challenger_component_id": "challenger.price_all",
        "deviation_id": "test-price-all-challenger",
        "evidence_status": "REGISTERED_RESEARCH_ONLY",
        "main_authority": False,
        "production_selection_authority": False,
        "promotion_pr_required": True,
        "research_only": True,
        "responsibility_id": "price_all_and_de_vig",
        "review_required": True,
    }


def test_registered_challenger_is_rejected_until_a_later_registry_pr(tmp_path: Path) -> None:
    payload = _payload()
    payload["active_shadow_deviations"] = [_valid_deviation(payload)]
    _fails(payload, tmp_path)


@pytest.mark.parametrize("field,value", [
    ("baseline_component_id", ""), ("challenger_component_id", ""),
    ("main_authority", True), ("automatic_promotion", True),
    ("production_selection_authority", True),
])
def test_unsafe_challenger_deviation_rejected(field: str, value, tmp_path: Path) -> None:
    payload = _payload()
    deviation = _valid_deviation(payload)
    deviation[field] = value
    payload["active_shadow_deviations"] = [deviation]
    _fails(payload, tmp_path)


def test_exact_shared_deviation_and_duplicate_ids_rejected(tmp_path: Path) -> None:
    payload = _payload()
    deviation = _valid_deviation(payload)
    deviation["responsibility_id"] = "fixture_identity"
    payload["active_shadow_deviations"] = [deviation]
    _fails(payload, tmp_path)
    payload = _payload()
    payload["active_shadow_deviations"] = [_valid_deviation(payload), _valid_deviation(payload)]
    _fails(payload, tmp_path)


def test_duplicate_gap_and_assignment_and_unknown_responsibility_rejected(tmp_path: Path) -> None:
    payload = _payload()
    payload["known_parity_gaps"].append(deepcopy(payload["known_parity_gaps"][0]))
    _fails(payload, tmp_path)
    payload = _payload()
    payload["reviewed_module_assignments"].append(deepcopy(payload["reviewed_module_assignments"][0]))
    _fails(payload, tmp_path)
    payload = _payload()
    payload["known_parity_gaps"][0]["responsibility_id"] = "unknown"
    _fails(payload, tmp_path)


def test_shared_canonical_requires_joint_evidence_and_main_only_cannot_claim_it(tmp_path: Path) -> None:
    payload = _payload()
    entry = _assignment(payload, "build_acca")
    entry["canonical_status"] = "CANONICAL_SHARED"
    _fails(payload, tmp_path)
    payload = _payload()
    entry = _assignment(payload, "domain.price_all_v3_current_provider")
    entry["authority_profile"] = "SHARED_CANONICAL"
    entry["canonical_status"] = "CANONICAL_SHARED"
    _fails(payload, tmp_path)


def test_request_semantics_are_exact_shared() -> None:
    request = _payload()["request_semantics"]
    assert request["parity_mode"] == "EXACT_SHARED_BASELINE"
    assert request["target_legs"] == {"maximum": 50, "minimum": 1}
    assert request["date_window_days"] == {"maximum": 7, "minimum": 1}
    assert request["target_legs_distinct_from_target_total_odds"] is True
    assert request["truthful_shortfall_permitted"] is True


@pytest.mark.parametrize("responsibility", [
    "fixture_identity", "provider_market_semantics",
    "provider_quote_identity_and_freshness", "settlement_semantics",
    "delivery_share_code_transport",
])
def test_exact_shared_responsibilities_cannot_become_challenger_capable(responsibility: str, tmp_path: Path) -> None:
    payload = _payload()
    entry = next(item for item in payload["shared_responsibilities"] if item["responsibility_id"] == responsibility)
    entry["parity_requirement"] = "SHARED_BASELINE_REGISTERED_CHALLENGER_ALLOWED"
    entry["shadow_deviation_policy"] = "REGISTERED_CHALLENGER_ONLY"
    _fails(payload, tmp_path)


def test_baseline_gap_and_assignment_registries_cannot_be_removed(tmp_path: Path) -> None:
    payload = _payload()
    payload["known_parity_gaps"] = []
    _fails(payload, tmp_path)
    payload = _payload()
    payload["reviewed_module_assignments"] = [x for x in payload["reviewed_module_assignments"] if x["component_id"] != "domain.current_shadow_all_market_runner"]
    _fails(payload, tmp_path)


def test_closed_owner_and_safety_schema_cannot_be_faked(tmp_path: Path) -> None:
    payload = _payload()
    payload["shared_responsibilities"][0]["current_owner_status"] = "RESOLVED_SHARED_CANONICAL"
    _fails(payload, tmp_path)
    payload = _payload()
    payload["safety_boundary"] = {}
    _fails(payload, tmp_path)
    payload = _payload()
    payload["safety_boundary"]["wager"] = "false"
    _fails(payload, tmp_path)


def test_lifecycle_request_protection_and_top_level_schema_are_frozen(tmp_path: Path) -> None:
    payload = _payload()
    payload["promotion_policy"]["lifecycle"].reverse()
    _fails(payload, tmp_path)
    payload = _payload()
    payload["request_semantics"]["concrete_date_resolution_before_orchestration"] = False
    _fails(payload, tmp_path)
    payload = _payload()
    payload["protected_research_infrastructure"][0]["rules"].remove("NO_SYNTHETIC_BACKFILL")
    _fails(payload, tmp_path)
    payload = _payload()
    payload["unknown"] = True
    _fails(payload, tmp_path)


def test_validator_uses_no_network_or_business_runtime(monkeypatch, tmp_path: Path) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("network access is forbidden")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    before = set(sys.modules)
    assert _validate(_payload(), tmp_path)["supported_root_count"] == 6
    imported = set(sys.modules) - before
    assert not any(name.startswith(("domain.", "engine.", "services.")) for name in imported)
    source = Path(validator.__file__).read_text(encoding="utf-8")
    assert all(
        not (isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in {"domain", "engine", "services"})
        for node in ast.walk(ast.parse(source))
    )
