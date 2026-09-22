"""P3.3 static import-closure checks for canonical module names.

These checks inspect source only. They deliberately do not import supported
runtime roots, so no provider, Shadow, Holdout, or other application workflow can
be executed while testing the namespace boundary.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
P0_2_RUNTIME_ARTIFACT = ROOT / "artifacts/architecture/runtime-reachability-v1.json"

CURRENT_SUPPORTED_ROOTS = (
    "domain.price_all",
    "domain.market_router",
    "domain.portfolio_optimizer",
    "domain.canonical_core",
    "services.main_canonical_prediction_adapter",
    "services.prediction_service",
    "domain.current_shadow_canonical_core_adapter",
    "domain.current_shadow_all_market_runner",
    "domain.current_sportybet_accumulator_request",
    "app",
    "build_acca",
)

FORBIDDEN_DEPRECATED_BUSINESS_MODULES = frozenset(
    {
        "domain.price_all_v2_direct_provider",
        "domain.market_router_v2_direct_provider",
        "domain.portfolio_optimizer_v2_direct_provider",
        "domain.price_all_v3_current_provider",
        "domain.market_router_v3_current_provider",
        "domain.portfolio_optimizer_v3_current_provider",
        "domain.market_router_canonical_adapter",
        "domain._historical_market_router_v1",
    }
)

# These are narrow frozen-policy/contract packages, not runtime business
# implementations. Keep the deny list exact instead of banning every name that
# happens to contain "v2".
ALLOWED_NARROW_V2_CONTRACT_MODULES = frozenset(
    {
        "domain._price_all_v2_direct_provider_contracts",
        "domain._market_router_v2_contracts",
        "domain._portfolio_optimizer_v2_direct_provider_contracts",
    }
)

CANONICAL_CURRENT_IMPLEMENTATIONS = {
    "domain.price_all": "domain._price_all_current_provider",
    "domain.market_router": "domain._market_router_current_provider",
    "domain.portfolio_optimizer": "domain._portfolio_optimizer_current_provider",
}


def _module_path(module_name: str) -> Path | None:
    """Return the repository-local source file for a dotted Python module."""
    parts = module_name.split(".")
    module_file = ROOT.joinpath(*parts).with_suffix(".py")
    if module_file.is_file():
        return module_file
    package_file = ROOT.joinpath(*parts, "__init__.py")
    if package_file.is_file():
        return package_file
    return None


def _package_name(module_name: str, source_path: Path) -> str:
    if source_path.name == "__init__.py":
        return module_name
    return module_name.rpartition(".")[0]


def _resolve_from_base(
    module_name: str, source_path: Path, node: ast.ImportFrom
) -> str:
    if node.level == 0:
        return node.module or ""

    package = _package_name(module_name, source_path)
    if not package:
        return ""
    for _ in range(node.level - 1):
        package = package.rpartition(".")[0]
    if not package:
        return node.module or ""
    if node.module:
        return f"{package}.{node.module}"
    return package


def _prefix_modules(module_name: str) -> tuple[str, ...]:
    pieces = module_name.split(".")
    return tuple(".".join(pieces[:index]) for index in range(1, len(pieces) + 1))


def _recursive_import_closure(root_module: str) -> frozenset[str]:
    """Follow repository-local absolute and relative AST imports recursively."""
    pending = [root_module]
    visited: set[str] = set()

    def enqueue_if_local(module_name: str) -> None:
        if module_name and _module_path(module_name) is not None:
            pending.append(module_name)

    while pending:
        module_name = pending.pop()
        if module_name in visited:
            continue
        source_path = _module_path(module_name)
        if source_path is None:
            continue
        visited.add(module_name)
        try:
            source_tree = ast.parse(
                source_path.read_text(encoding="utf-8-sig"), filename=str(source_path)
            )
        except (OSError, SyntaxError) as exc:
            raise AssertionError(f"cannot parse supported import source {source_path}: {exc}") from exc

        for node in ast.walk(source_tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for prefix in _prefix_modules(alias.name):
                        enqueue_if_local(prefix)
            elif isinstance(node, ast.ImportFrom):
                base_module = _resolve_from_base(module_name, source_path, node)
                for prefix in _prefix_modules(base_module):
                    enqueue_if_local(prefix)
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    imported_module = (
                        f"{base_module}.{alias.name}" if base_module else alias.name
                    )
                    enqueue_if_local(imported_module)

    return frozenset(visited)


def _supported_roots() -> tuple[str, ...]:
    artifact = json.loads(P0_2_RUNTIME_ARTIFACT.read_text(encoding="utf-8"))
    assert artifact["policy_id"] == "ATHENA_RUNTIME_REACHABILITY_V1"
    p0_2_roots = artifact["p0_2_supported_roots"]
    assert isinstance(p0_2_roots, list) and p0_2_roots
    assert len(p0_2_roots) == len(set(p0_2_roots))
    roots = tuple(sorted(set(CURRENT_SUPPORTED_ROOTS).union(p0_2_roots)))
    missing = sorted(root for root in roots if _module_path(root) is None)
    assert not missing, f"supported roots do not resolve to repository modules: {missing}"
    return roots


def test_supported_current_roots_do_not_reach_deprecated_or_historical_modules():
    roots = _supported_roots()
    violations: dict[str, list[str]] = {}
    closures: dict[str, frozenset[str]] = {}

    for root in roots:
        closure = _recursive_import_closure(root)
        closures[root] = closure
        reached = sorted(closure.intersection(FORBIDDEN_DEPRECATED_BUSINESS_MODULES))
        if reached:
            violations[root] = reached

    assert not violations, (
        "supported current roots statically reach deprecated business modules or "
        f"historical Router-v1: {violations}"
    )


def test_canonical_roots_reach_private_unversioned_current_implementations():
    for canonical_root, implementation in CANONICAL_CURRENT_IMPLEMENTATIONS.items():
        closure = _recursive_import_closure(canonical_root)
        assert implementation in closure, (
            f"{canonical_root} does not reach its private current implementation "
            f"{implementation}"
        )


def test_narrow_v2_contract_packages_are_not_classified_as_forbidden_runtime_modules():
    assert not (
        ALLOWED_NARROW_V2_CONTRACT_MODULES
        & FORBIDDEN_DEPRECATED_BUSINESS_MODULES
    )
    canonical_closures = {
        root: _recursive_import_closure(root)
        for root in CANONICAL_CURRENT_IMPLEMENTATIONS
    }
    # The Price-All and Router contracts are needed directly by their current
    # owners; Portfolio's policy contract is likewise consumed by its owner.
    assert "domain._price_all_v2_direct_provider_contracts" in canonical_closures[
        "domain.price_all"
    ]
    assert "domain._market_router_v2_contracts" in canonical_closures[
        "domain.market_router"
    ]
    assert "domain._portfolio_optimizer_v2_direct_provider_contracts" in canonical_closures[
        "domain.portfolio_optimizer"
    ]
