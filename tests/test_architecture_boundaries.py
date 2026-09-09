"""P0.4 architecture boundary tests; only static tooling is imported."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts import validate_architecture_boundaries as boundaries

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config/architecture/architecture-boundary-policy-v1.json"


def _policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def _modules(*module_ids: str) -> dict[str, str]:
    return {module: module.replace(".", "/") + ".py" for module in module_ids}


def _sources(modules: dict[str, str], source_module: str, source: str) -> dict[str, str]:
    result = {path: "" for path in modules.values()}
    result[modules[source_module]] = source
    return result


def _dependency(policy: dict, modules: dict[str, str], source_module: str, source: str, research: set[str] | None = None) -> list[dict]:
    return boundaries._dependency_violations(policy, modules, _sources(modules, source_module, source), research or set())


def test_real_policy_is_canonical_and_pinned() -> None:
    raw = POLICY_PATH.read_bytes()
    policy = _policy()
    assert raw == boundaries.canonical_json_bytes(policy)
    assert hashlib.sha256(raw).hexdigest()
    assert boundaries._validate_policy(policy)
    assert policy["approved_parallel_authority_adrs"] == []


@pytest.mark.parametrize(("field", "value"), [
    ("schema_version", 2),
    ("policy_id", "WRONG"),
    ("policy_base_main", "0" * 40),
    ("authority_contract_policy_id", "WRONG"),
    ("authority_contract_sha256", "0" * 64),
])
def test_upstream_anchor_mutations_fail(field: str, value) -> None:
    policy = _policy()
    policy[field] = value
    with pytest.raises(boundaries.BoundaryError):
        boundaries._validate_policy(policy)


@pytest.mark.parametrize(("candidate", "responsibility"), [
    ("domain.market_router_v4", "market_router"),
    ("domain.market_router_next", "market_router"),
    ("domain.market_router_current2", "market_router"),
    ("domain.price_all_v4", "price_all_and_de_vig"),
    ("domain.price_all_current2", "price_all_and_de_vig"),
    ("domain.portfolio_optimizer_v4", "portfolio_optimizer"),
    ("domain.portfolio_optimizer_rewrite", "portfolio_optimizer"),
])
def test_new_public_parallel_authority_requires_accepted_adr(candidate: str, responsibility: str) -> None:
    policy = _policy()
    families = boundaries._validate_policy(policy)
    modules = _modules(candidate)
    diagnostics = boundaries._parallel_authority_diagnostics(families, modules, set())
    assert diagnostics[0]["rule_id"] == "PARALLEL_AUTHORITY_REQUIRES_ACCEPTED_ADR"
    assert diagnostics[0]["responsibility_id"] == responsibility
    assert diagnostics[0]["candidate_module"] == candidate
    assert diagnostics[0]["required_adr_status"] == "ACCEPTED"


@pytest.mark.parametrize("helper", [
    "domain._market_router_fixture_helper",
    "domain._price_all_fixture_helper",
    "domain._portfolio_optimizer_fixture_helper",
])
def test_private_helpers_are_not_public_parallel_authority(helper: str) -> None:
    families = boundaries._validate_policy(_policy())
    assert boundaries._parallel_authority_diagnostics(families, _modules(helper), set()) == []


def test_baseline_family_matches_every_real_base_module() -> None:
    policy = _policy()
    families = boundaries._validate_policy(policy)
    base_modules = boundaries._module_index(ROOT, boundaries.EXPECTED_BASE_MAIN)
    for responsibility, family in families.items():
        assert boundaries._family_modules(base_modules, tuple(family["public_prefixes"])) == family["baseline_public_module_ids"]


@pytest.mark.parametrize(("source_module", "source"), [
    ("models.fixture_model", "from domain import current_shadow_all_market_share_code"),
    ("domain.prediction_engine", "from domain import current_shadow_sportybet_share_code"),
    ("models.fixture_model", 'import importlib\nimportlib.import_module("domain.current_shadow_all_market_share_code")'),
])
def test_model_probability_cannot_import_delivery(source_module: str, source: str) -> None:
    policy = _policy()
    modules = _modules(source_module, "domain.current_shadow_all_market_share_code", "domain.current_shadow_sportybet_share_code")
    diagnostics = _dependency(policy, modules, source_module, source)
    assert diagnostics and diagnostics[0]["rule_id"] == "MODEL_PROBABILITY_CANNOT_IMPORT_SPORTYBET_DELIVERY"


def test_model_provider_semantics_and_mentions_are_allowed() -> None:
    policy = _policy()
    modules = _modules("models.fixture_model", "domain.sportybet_current_provider_semantics")
    assert _dependency(policy, modules, "models.fixture_model", "from domain import sportybet_current_provider_semantics") == []
    assert _dependency(policy, modules, "models.fixture_model", '"share_code SportyBet delivery"\nvalue = "share_code"') == []


@pytest.mark.parametrize(("source_module", "source", "target"), [
    ("domain.price_all_v4", "from domain import portfolio_optimizer_v2_direct_provider", "domain.portfolio_optimizer_v2_direct_provider"),
    ("domain._price_all_fixture_core", "from domain import portfolio_optimizer_v2_direct_provider", "domain.portfolio_optimizer_v2_direct_provider"),
    ("domain.price_all_v4", "from domain import staking", "domain.staking"),
    ("domain.price_all_v4", "from domain import wager", "domain.wager"),
])
def test_pricing_cannot_import_portfolio_or_wager(source_module: str, source: str, target: str) -> None:
    policy = _policy()
    modules = _modules(source_module, target)
    diagnostics = _dependency(policy, modules, source_module, source)
    assert diagnostics and diagnostics[0]["rule_id"] == "PRICING_CANNOT_IMPORT_PORTFOLIO_OR_WAGER"


def test_pricing_can_import_provider_price_evidence() -> None:
    policy = _policy()
    modules = _modules("domain.price_all_v4", "domain.sportybet_price_all_direct_provider_quote_adapter")
    assert _dependency(policy, modules, "domain.price_all_v4", "from domain import sportybet_price_all_direct_provider_quote_adapter") == []


@pytest.mark.parametrize("target", ["domain.wallet", "domain.staking", "domain.wager", "domain.bookmaker.login"])
def test_research_orchestration_cannot_import_auth_or_wager(target: str) -> None:
    policy = _policy()
    source = "domain.current_shadow_all_market_runner"
    modules = _modules(source, target)
    statement = f"import {target}"
    diagnostics = _dependency(policy, modules, source, statement, {source})
    assert diagnostics and diagnostics[0]["rule_id"] == "RESEARCH_ORCHESTRATION_CANNOT_IMPORT_WAGER_AUTHORITY"


def test_research_orchestration_allows_anonymous_share_code_and_sportybet_token() -> None:
    policy = _policy()
    source = "domain.current_shadow_all_market_runner"
    target = "domain.current_shadow_all_market_share_code"
    modules = _modules(source, target)
    assert _dependency(policy, modules, source, f"from domain import current_shadow_all_market_share_code", {source}) == []


@pytest.mark.parametrize("source", [
    'import importlib as il\nil.import_module("domain.current_shadow_all_market_portfolio")',
    'from importlib import import_module as load\nload("domain.current_shadow_all_market_portfolio")',
    '__import__("domain.current_shadow_all_market_portfolio")',
])
def test_owned_literal_dynamic_imports_are_boundary_checked(source: str) -> None:
    policy = _policy()
    modules = _modules("domain.price_all_v4", "domain.current_shadow_all_market_portfolio")
    diagnostics = _dependency(policy, modules, "domain.price_all_v4", source)
    assert diagnostics and diagnostics[0]["rule_id"] == "PRICING_CANNOT_IMPORT_PORTFOLIO_OR_WAGER"


def test_relative_import_is_resolved_and_custom_loader_is_not_importlib() -> None:
    policy = _policy()
    modules = _modules("domain.price_all_v4", "domain.portfolio_optimizer_v2_direct_provider")
    relative = _dependency(policy, modules, "domain.price_all_v4", "from . import portfolio_optimizer_v2_direct_provider")
    assert relative and relative[0]["target_module"] == "domain.portfolio_optimizer_v2_direct_provider"
    assert _dependency(policy, modules, "domain.price_all_v4", 'custom_loader.import_module("domain.portfolio_optimizer_v2_direct_provider")') == []


def test_nonliteral_dynamic_import_in_controlled_source_fails_closed() -> None:
    policy = _policy()
    modules = _modules("domain.price_all_v4")
    diagnostics = _dependency(policy, modules, "domain.price_all_v4", 'import importlib\nimportlib.import_module(module_name)')
    assert diagnostics == [{"rule_id": "BOUNDARY_DYNAMIC_IMPORT_TARGET_UNPROVEN", "source_module": "domain.price_all_v4", "source_path": "domain/price_all_v4.py", "target_module": "<UNPROVEN>", "line_number": 2, "reason": "boundary-controlled source uses non-literal dynamic import"}]


def test_diagnostics_are_deterministic() -> None:
    policy = _policy()
    modules = _modules("domain.price_all_v4", "domain.portfolio_optimizer_v2_direct_provider", "domain.wager")
    source = "from domain import wager\nfrom domain import portfolio_optimizer_v2_direct_provider"
    assert _dependency(policy, modules, "domain.price_all_v4", source) == _dependency(policy, modules, "domain.price_all_v4", source)


def test_exact_head_baseline_has_no_violations_and_contract_is_unchanged() -> None:
    result = boundaries.validate_architecture_boundaries(ROOT, POLICY_PATH, "HEAD")
    assert result["resolved_ref"] == "d18976128b15d773b77487a361abe9781bd32cc3"
    assert result["forbidden_dependency_violation_count"] == 0
    assert result["baseline_parallel_authority_adr_count"] == 0
