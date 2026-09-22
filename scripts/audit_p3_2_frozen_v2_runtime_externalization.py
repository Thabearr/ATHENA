from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain import (
    _market_router_v2_contracts as router_v2_contracts,
    _portfolio_optimizer_v2_direct_provider_contracts as portfolio_v2_contracts,
    _price_all_v2_direct_provider_contracts as price_v2_contracts,
    market_router_canonical_adapter,
    portfolio_optimizer,
    price_all,
)
from domain.component_authority_registry import load_default_registry
from domain.canonical_core import validate_canonical_core_contract


BASE_MAIN_SHA = "e79322c57dd9d46789c67de8c7425fa59c8640c1"
P31_RECEIPT_SHA256 = "f1fae3ed54c8afc632923156268bc4e70b748eb1ce9a8c3f1c822c965050a875"
REGISTRY_SHA256 = "d52fbb292ddaea9ba2e94fda036f715db5ced7248187814fd29ac7859de26104"
POLICY_ID = "ATHENA_P3_2_FROZEN_V2_RUNTIME_EXTERNALIZATION_V1"
CANONICAL_ROOTS = (
    "domain.market_router_canonical_adapter",
    "domain.portfolio_optimizer",
    "domain.price_all",
)
FORBIDDEN = (
    "domain.market_router_v2_direct_provider",
    "domain.portfolio_optimizer_v2_direct_provider",
    "domain.price_all_v2_direct_provider",
)
OWNER_IDENTITIES = {
    "price_all_and_de_vig": {
        "component_id": "domain.price_all",
        "contract_sha256": "30481bc9ebf442f0e664bcd14d2c6cd18026a42a35083d143db6366837b3d425",
        "artifact_git_blob_sha": "cf7214a6103d91a2974e3eb00c705f65c841d458",
    },
    "market_router": {
        "component_id": "domain.market_router_canonical_adapter",
        "contract_sha256": "85b4b5c712154f7d4708eb53e9cadfcb7c65dc21bdb12cd94cf1b8cd48795e32",
        "artifact_git_blob_sha": "3011b65fcd62e5ae91fcede967b8cba4f85cdda7",
    },
    "portfolio_optimizer": {
        "component_id": "domain.portfolio_optimizer",
        "contract_sha256": "916247c4a891e3c0a2b8205b9d33000987471a54107f2b3d508c8e5ab1e9a99c",
        "artifact_git_blob_sha": "d600d5d88baf5628df23441a9216c2fc68352e45",
    },
}
FROZEN_V2_SHA256 = {
    "price_all": "b5e3c063ac8b4e9fc1521cabbfe1da873a67b70efc67bc08d8ada61f2024e599",
    "router": "071d1246ee285634af5598b66872fb27c683f2d13ab14dc25b31de90b72195de",
    "portfolio": "919149759ffc9aabef2fefe7c6e0db72d697ebd1ffe33205054fc3ffb4f785fd",
}
CURRENT_V3_SHA256 = {
    "price_all": "30481bc9ebf442f0e664bcd14d2c6cd18026a42a35083d143db6366837b3d425",
    "router": "61a90a29495399668e19ae4a149527abea98c172d7bdacf1a1b521776b4d771a",
    "portfolio": "4dc8be4e0a9f607b6c0804048bb326c0aa342d37fe540abbcd3e1b3a5f6a6dad",
}
TEST_PATHS = (
    "tests/test_p3_2_frozen_v2_runtime_externalization.py",
    "tests/test_price_all_v2_direct_provider.py",
    "tests/test_price_all_v3_current_provider.py",
    "tests/test_price_all.py",
    "tests/test_market_router_v2_direct_provider.py",
    "tests/test_market_router_v3_current_provider.py",
    "tests/test_market_router_canonical_adapter.py",
    "tests/test_portfolio_optimizer_v2_direct_provider.py",
    "tests/test_portfolio_optimizer_v3_current_provider.py",
    "tests/test_portfolio_optimizer.py",
    "tests/test_p3_0_legacy_canonical_comparator.py",
    "tests/test_p3_0_replay_corpus.py",
    "tests/test_p3_0_canonical_pre_router_pipeline.py",
    "tests/test_prediction_service_canonical_router_migration.py",
    "tests/test_p3_1_main_caller_migration.py",
    "tests/test_canonical_core.py",
    "tests/test_current_shadow_canonical_core_adapter.py",
    "tests/test_current_shadow_canonical_core_registry_aliases.py",
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=False
    )
    if completed.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed: {completed.stderr.strip()}")
    return completed.stdout.strip()


def _module_path(module_name: str) -> Path | None:
    if not module_name.startswith("domain."):
        return None
    path = ROOT.joinpath(*module_name.split("."))
    source = path.with_suffix(".py")
    if source.is_file():
        return source
    initializer = path / "__init__.py"
    return initializer if initializer.is_file() else None


def _imports_from_ast(tree: ast.AST, module_name: str) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        candidates: set[str] = set()
        if isinstance(node, ast.Import):
            candidates.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                candidates.add(node.module)
                if node.module == "domain":
                    candidates.update(f"domain.{alias.name}" for alias in node.names)
                else:
                    candidates.update(
                        f"{node.module}.{alias.name}"
                        for alias in node.names
                        if _module_path(f"{node.module}.{alias.name}") is not None
                    )
            elif node.level and node.module:
                package_parts = module_name.rsplit(".", 1)[0].split(".")
                prefix = package_parts[: len(package_parts) - node.level + 1]
                candidates.add(".".join(prefix + node.module.split(".")))
        imports.update(
            name for name in candidates if name.startswith("domain.")
        )
    return imports


def _reachable_closure(roots: tuple[str, ...]) -> tuple[set[str], dict[str, set[str]]]:
    pending = list(roots)
    reached: set[str] = set()
    edges: dict[str, set[str]] = {}
    while pending:
        source = pending.pop()
        if source in reached:
            continue
        path = _module_path(source)
        if path is None:
            continue
        reached.add(source)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        children = {
            target
            for target in _imports_from_ast(tree, source)
            if _module_path(target) is not None
        }
        edges[source] = children
        pending.extend(sorted(children - reached))
    return reached, edges


def _base_source(module_name: str) -> str:
    relative_path = module_name.replace(".", "/") + ".py"
    return _git("show", f"{BASE_MAIN_SHA}:{relative_path}")


def _base_dependency_edges() -> list[dict[str, str]]:
    sources = (
        "domain.price_all_v3_current_provider",
        "domain.market_router_v3_current_provider",
        "domain._market_router_v2_contracts",
        "domain.portfolio_optimizer_v3_current_provider",
        "domain._portfolio_optimizer_v2_direct_provider_contracts",
    )
    edges: set[tuple[str, str]] = set()
    for source in sources:
        parsed = ast.parse(_base_source(source), filename=source)
        edges.update((source, target) for target in _imports_from_ast(parsed, source))
    required = {
        ("domain.price_all_v3_current_provider", "domain.price_all_v2_direct_provider"),
        ("domain.market_router_v3_current_provider", "domain.market_router_v2_direct_provider"),
        ("domain._market_router_v2_contracts", "domain.price_all_v2_direct_provider"),
        ("domain.portfolio_optimizer_v3_current_provider", "domain.portfolio_optimizer_v2_direct_provider"),
        ("domain.portfolio_optimizer_v3_current_provider", "domain._portfolio_optimizer_v2_direct_provider_contracts"),
        ("domain._portfolio_optimizer_v2_direct_provider_contracts", "domain._market_router_v2_contracts"),
    }
    missing = required - edges
    if missing:
        raise RuntimeError(f"base dependency edges were not found in git show: {sorted(missing)}")
    relevant = {
        edge for edge in edges
        if edge in required
        or edge[1] in FORBIDDEN
        or edge[1].endswith("_v2_contracts")
        or edge[1].endswith("_direct_provider_contracts")
    }
    return [{"from": left, "to": right} for left, right in sorted(relevant)]


def _blob_at_base(path: str) -> str:
    return _git("rev-parse", f"{BASE_MAIN_SHA}:{path}")


def _current_blob(path: str) -> str:
    return _git("hash-object", path)


def _validate_p31_receipt() -> None:
    path = ROOT / "artifacts/architecture/p3_1_main_caller_migration_v1.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    digest = receipt.get("canonical_sha256")
    unsigned = dict(receipt)
    unsigned.pop("canonical_sha256", None)
    if digest != P31_RECEIPT_SHA256 or _sha256(unsigned) != digest:
        raise RuntimeError("P3.1 migration receipt identity drifted")


def _dynamic_import_proof() -> list[str]:
    code = r'''\
from datetime import timedelta
import json
import sys
from pytest import MonkeyPatch
from domain import price_all, market_router_canonical_adapter as router, portfolio_optimizer as portfolio
from domain import portfolio_optimizer_v3_current_provider as portfolio_v3
from domain.price_all import validate_price_all_contract
from domain.market_router_canonical_adapter import validate_canonical_market_router_contract
from domain.portfolio_optimizer import validate_portfolio_contract
from domain.canonical_core import validate_canonical_core_contract
from domain.run_contracts import AuthorityManifest

validate_canonical_core_contract()
for validate in (validate_price_all_contract, validate_canonical_market_router_contract, validate_portfolio_contract):
    validate()
for profile in ("MAIN", "SHADOW"):
    manifest = AuthorityManifest(
        authority_profile=profile,
        mode="p3_2_import_graph_audit",
        provider_acquisition=False,
        share_code_generation=False,
        login=False,
        cookies=False,
        wallet=False,
        staking=False,
        wager=False,
    )
    from domain.canonical_core import resolve_canonical_core
    resolve_canonical_core(manifest, regime_id="CURRENT_SPORTYBET_PROVIDER", required_schema_version=1)
forbidden = {
    "domain.price_all_v2_direct_provider",
    "domain.market_router_v2_direct_provider",
    "domain.portfolio_optimizer_v2_direct_provider",
}
assert not forbidden.intersection(sys.modules)
from tests.test_current_direct_provider_live_quote_mapping_consumption import EVALUATION
from tests.test_market_router_v3_current_provider import _fixture_state, _priced_match_result
from tests.test_portfolio_optimizer_v3_current_provider import _input as portfolio_input
monkeypatch = MonkeyPatch()
try:
    source_decision = _priced_match_result(monkeypatch, probability=0.60)
    canonical_price = price_all.PriceAllEvaluation._from_v3(source_decision)
    router_decision = router.route(
        canonical_price,
        fixture_state=_fixture_state(),
        evaluation_time=EVALUATION + timedelta(seconds=10),
    )
    portfolio.optimize_portfolio_as_of(
        (), target_legs=1,
        evaluation_time=EVALUATION + timedelta(seconds=20),
    )
    portfolio_v3.optimize_current_provider_portfolio_as_of(
        (portfolio_input(monkeypatch),), target_size=1,
        evaluation_time=EVALUATION + timedelta(seconds=20),
    )
finally:
    monkeypatch.undo()
loaded = sorted(forbidden.intersection(sys.modules))
assert not loaded
print(json.dumps(loaded))
'''
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("fresh-process dynamic proof failed:\n" + result.stdout + result.stderr)
    loaded = json.loads(result.stdout.strip().splitlines()[-1])
    if loaded:
        raise RuntimeError(f"forbidden v2 modules loaded in fresh process: {loaded}")
    return loaded


def _run_test_matrix() -> bool:
    missing = [name for name in TEST_PATHS if not (ROOT / name).is_file()]
    if missing:
        raise RuntimeError(f"required continuity test modules are missing: {missing}")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *TEST_PATHS],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("P3.2 continuity test matrix failed:\n" + result.stdout + result.stderr)
    return True


def build_receipt(*, run_tests: bool) -> dict[str, Any]:
    _validate_p31_receipt()
    registry = load_default_registry()
    if registry.canonical_sha256 != REGISTRY_SHA256:
        raise RuntimeError("component registry canonical SHA drifted")

    record_by_id = {item.responsibility_id: item for item in registry.records}
    registered = {}
    for responsibility, expected in OWNER_IDENTITIES.items():
        record = record_by_id[responsibility]
        actual = {
            "component_id": record.component_id,
            "contract_sha256": record.contract_sha256,
            "artifact_git_blob_sha": record.artifact_git_blob_sha,
        }
        if actual != expected:
            raise RuntimeError(f"registered owner identity drifted for {responsibility}: {actual}")
        registered[responsibility] = actual

    root_results: dict[str, list[str]] = {}
    all_edges: dict[str, set[str]] = {}
    for root in CANONICAL_ROOTS:
        reachable, edges = _reachable_closure((root,))
        root_results[root] = sorted(reachable.intersection(FORBIDDEN))
        all_edges.update(edges)
    if any(root_results.values()):
        raise RuntimeError(f"static canonical graph reaches frozen v2 runtime: {root_results}")
    for required in (
        "domain.price_all_v3_current_provider",
        "domain.market_router_v3_current_provider",
        "domain.portfolio_optimizer_v3_current_provider",
    ):
        if required not in all_edges:
            raise RuntimeError(f"canonical root no longer reaches expected migration-window source {required}")

    dynamic_forbidden = _dynamic_import_proof()
    current_registry_path = "config/architecture/component-authority-registry-v1.json"
    registry_changed = _current_blob(current_registry_path) != _blob_at_base(current_registry_path)
    if registry_changed:
        raise RuntimeError("component authority registry changed")

    owner_files_changed = False
    for record in registered.values():
        module_path = record["component_id"].replace(".", "/") + ".py"
        owner_files_changed = owner_files_changed or (
            _current_blob(module_path) != _blob_at_base(module_path)
        )
    if owner_files_changed:
        raise RuntimeError("a registered canonical owner file changed")

    implementation_paths = {
        "price_all": "domain/price_all_v2_direct_provider.py",
        "router": "domain/market_router_v2_direct_provider.py",
        "portfolio": "domain/portfolio_optimizer_v2_direct_provider.py",
    }
    implementation_changed = {
        key: _current_blob(path) != _blob_at_base(path)
        for key, path in implementation_paths.items()
    }
    if any(implementation_changed.values()):
        raise RuntimeError(f"a retained frozen v2 implementation changed: {implementation_changed}")
    if any(not (ROOT / path).is_file() for path in implementation_paths.values()):
        raise RuntimeError("a retained frozen v2 runtime module was deleted")

    price_v2_sha = price_v2_contracts.calculate_price_all_v2_contract_sha256()
    router_v2_sha = router_v2_contracts.calculate_market_router_v2_contract_sha256()
    portfolio_v2_sha = portfolio_v2_contracts.calculate_portfolio_optimizer_v2_contract_sha256()
    current_v2_hashes = {
        "price_all": price_v2_sha,
        "router": router_v2_sha,
        "portfolio": portfolio_v2_sha,
    }
    current_v3_hashes = {
        "price_all": __import__("domain.price_all_v3_current_provider", fromlist=["EXPECTED_CONTRACT_SHA256"]).calculate_price_all_v3_contract_sha256(),
        "router": __import__("domain.market_router_v3_current_provider", fromlist=["EXPECTED_CONTRACT_SHA256"]).calculate_market_router_v3_contract_sha256(),
        "portfolio": __import__("domain.portfolio_optimizer_v3_current_provider", fromlist=["EXPECTED_CONTRACT_SHA256"]).calculate_portfolio_optimizer_v3_contract_sha256(),
    }
    if current_v2_hashes != FROZEN_V2_SHA256:
        raise RuntimeError(f"frozen v2 identities drifted: {current_v2_hashes}")
    if current_v3_hashes != CURRENT_V3_SHA256:
        raise RuntimeError(f"current v3 identities drifted: {current_v3_hashes}")

    fixture_path = ROOT / "tests/fixtures/architecture/p3_2_frozen_v2_policy_vectors_v1.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    fixture_sha = fixture["canonical_sha256"]
    unsigned_fixture = dict(fixture)
    unsigned_fixture.pop("canonical_sha256", None)
    if _sha256(unsigned_fixture) != fixture_sha:
        raise RuntimeError("policy-vector fixture canonical SHA mismatch")
    if fixture["source_main_sha"] != BASE_MAIN_SHA:
        raise RuntimeError("policy vectors were not sourced from the required base main")

    base_edges = _base_dependency_edges()
    test_suite_passed = _run_test_matrix() if run_tests else False
    p3_2_exit_gate = (
        not any(root_results.values())
        and not dynamic_forbidden
        and test_suite_passed
        and not registry_changed
        and not owner_files_changed
        and not any(implementation_changed.values())
    )
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "repository_base_main_sha": BASE_MAIN_SHA,
        "p3_1_main_caller_migration_receipt_sha256": P31_RECEIPT_SHA256,
        "component_registry_canonical_sha256": REGISTRY_SHA256,
        "canonical_roots": list(CANONICAL_ROOTS),
        "forbidden_runtime_v2_modules": list(FORBIDDEN),
        "base_runtime_dependency_edges": base_edges,
        "final_static_forbidden_reachability": [],
        "final_static_forbidden_reachability_by_root": root_results,
        "final_dynamic_forbidden_sys_modules": dynamic_forbidden,
        "frozen_v2_contract_sha256": current_v2_hashes,
        "current_v3_contract_sha256": current_v3_hashes,
        "registered_canonical_owner_identities": registered,
        "registered_owner_files_changed": False,
        "registry_changed": False,
        "frozen_v2_implementation_files_changed": False,
        "frozen_v2_modules_deleted": False,
        "v3_modules_renamed": False,
        "differential_price_policy_vectors_passed": test_suite_passed,
        "differential_router_policy_vectors_passed": test_suite_passed,
        "differential_portfolio_policy_vectors_passed": test_suite_passed,
        "current_replay_suites_passed": test_suite_passed,
        "policy_vector_fixture_canonical_sha256": fixture_sha,
        "model_formula_changed": False,
        "probability_formula_changed": False,
        "calibration_formula_changed": False,
        "price_all_formula_changed": False,
        "router_formula_changed": False,
        "portfolio_formula_changed": False,
        "provider_semantics_changed": False,
        "share_code_semantics_changed": False,
        "provider_acquisition": False,
        "current_shadow_triggered": False,
        "fresh_holdout_triggered": False,
        "p3_0_e1_triggered": False,
        "share_code_operation": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "wager_placed": False,
        "p3_2_exit_gate_satisfied": p3_2_exit_gate,
        "next_required_step": "P3_3_RENAME_AND_CANONICALIZE_MODULES",
    }
    receipt["canonical_sha256"] = _sha256(receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit P3.2 frozen-v2 runtime externalization")
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Do not execute the local replay matrix; receipt exit gate will remain false.",
    )
    args = parser.parse_args()
    receipt = build_receipt(run_tests=not args.skip_tests)
    target = ROOT / "artifacts/architecture/p3_2_frozen_v2_runtime_externalization_v1.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(receipt["canonical_sha256"])
    print(f"p3_2_exit_gate_satisfied={receipt['p3_2_exit_gate_satisfied']}")
    return 0 if receipt["p3_2_exit_gate_satisfied"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
