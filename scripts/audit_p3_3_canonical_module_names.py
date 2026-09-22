"""Audit and record the deterministic P3.3 canonical-module-name boundary."""
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

from domain.component_authority_registry import (  # noqa: E402
    ComponentAuthorityRegistry,
    load_default_registry,
)


SCHEMA_VERSION = 1
POLICY_ID = "ATHENA_P3_3_MODULE_CANONICALIZATION_V1"
BASE_MAIN_SHA = "f1e4b453ab4d6f490c3b674c477ec17e32d03f92"
P3_2_REPOSITORY_BASE_MAIN_SHA = "e79322c57dd9d46789c67de8c7425fa59c8640c1"
P3_2_RECEIPT_CANONICAL_SHA256 = (
    "0743e9b73d1a712a638c10866b3cc7f3e989605412786f8c91d115cc617abffd"
)
P3_2_RECEIPT_SOURCE_SHA256 = (
    "8b9330b75ad2ccfce312f751bcc694b39af7c401f3e25b7668b2f1492f9051ea"
)
P3_2_POLICY_VECTOR_CANONICAL_SHA256 = (
    "a7609c359410c5d0d1b1aff4c04ee71a115b07c30e28bfac89eeb5a02f185da3"
)
P3_2_RECEIPT_PATH = (
    ROOT / "artifacts/architecture/p3_2_frozen_v2_runtime_externalization_v1.json"
)
P0_2_RUNTIME_ARTIFACT = ROOT / "artifacts/architecture/runtime-reachability-v1.json"
ROUTER_V1_CLASSIFICATION_PATH = (
    ROOT / "tests/fixtures/architecture/p3_3_router_v1_caller_classification_v1.json"
)
REGISTRY_PATH = ROOT / "config/architecture/component-authority-registry-v1.json"
DEFAULT_OUTPUT = ROOT / "artifacts/architecture/p3_3_module_canonicalization_v1.json"

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

EXACT_RENAME_MAP = {
    "domain/market_router.py": "domain/_historical_market_router_v1.py",
    "domain/market_router_canonical_adapter.py": "domain/market_router.py",
    "domain/market_router_v3_current_provider.py": "domain/_market_router_current_provider.py",
    "domain/portfolio_optimizer_v3_current_provider.py": "domain/_portfolio_optimizer_current_provider.py",
    "domain/price_all_v3_current_provider.py": "domain/_price_all_current_provider.py",
}

COMPATIBILITY_SHIMS = {
    "domain.market_router_canonical_adapter": "domain.market_router",
    "domain.market_router_v3_current_provider": "domain._market_router_current_provider",
    "domain.portfolio_optimizer_v3_current_provider": "domain._portfolio_optimizer_current_provider",
    "domain.price_all_v3_current_provider": "domain._price_all_current_provider",
}

EXPECTED_REGISTRY_BEFORE_SHA256 = (
    "d52fbb292ddaea9ba2e94fda036f715db5ced7248187814fd29ac7859de26104"
)
EXPECTED_REGISTRY_AFTER_SHA256 = (
    "74e79e216497c2e7f31a51e278251a5c62645e1085d04ebb8712022658f8f109"
)

EXPECTED_CONTRACT_HASHES = {
    "canonical": {
        "canonical_core": "af4a73f8852893e7391ae85bac092105d305fa5b9e77af273809fcdcb3dc4c4a",
        "market_router": "85b4b5c712154f7d4708eb53e9cadfcb7c65dc21bdb12cd94cf1b8cd48795e32",
        "portfolio_optimizer": "916247c4a891e3c0a2b8205b9d33000987471a54107f2b3d508c8e5ab1e9a99c",
        "price_all": "30481bc9ebf442f0e664bcd14d2c6cd18026a42a35083d143db6366837b3d425",
    },
    "v2": {
        "market_router": "071d1246ee285634af5598b66872fb27c683f2d13ab14dc25b31de90b72195de",
        "portfolio_optimizer": "919149759ffc9aabef2fefe7c6e0db72d697ebd1ffe33205054fc3ffb4f785fd",
        "price_all": "b5e3c063ac8b4e9fc1521cabbfe1da873a67b70efc67bc08d8ada61f2024e599",
    },
    "v3": {
        "market_router": "61a90a29495399668e19ae4a149527abea98c172d7bdacf1a1b521776b4d771a",
        "portfolio_optimizer": "4dc8be4e0a9f607b6c0804048bb326c0aa342d37fe540abbcd3e1b3a5f6a6dad",
        "price_all": "30481bc9ebf442f0e664bcd14d2c6cd18026a42a35083d143db6366837b3d425",
    },
}

PRESERVED_HISTORICAL_ARTIFACT_SHA256 = {
    "artifacts/architecture/p3_1_main_canonical_core_promotion_v1.json": (
        "a08d0966d82bcdc5573b61ef05c90cf7889c8dede7e3888a615fdbd2c5a43939"
    ),
    "artifacts/architecture/p3_1_main_caller_migration_v1.json": (
        "28a930d25288a8572be96711779dbf137911b2fa00bfe2883134290ec38850dc"
    ),
    "artifacts/architecture/p3_2_frozen_v2_runtime_externalization_v1.json": (
        "8b9330b75ad2ccfce312f751bcc694b39af7c401f3e25b7668b2f1492f9051ea"
    ),
    "artifacts/architecture/runtime-reachability-v1.json": (
        "a8ccb4c0c8ab2bea9bd133bb7fa7e155957bf1e38e5bf7ae6cccb4f44640f7e4"
    ),
    "config/architecture/architecture-boundary-policy-v1.json": (
        "f6aeac63c88e8dce7e52e278bd0e48b478ede9b56764a78051e500d70bcd6ee6"
    ),
    "config/architecture/main-shadow-authority-parity-v1.json": (
        "d4f525a0eb8d3ffe07e5b64a3452d758bc9e180c5b1db37feecbac1faf395bfe"
    ),
    "tests/fixtures/architecture/p3_2_frozen_v2_policy_vectors_v1.json": (
        "264b8998aba276fd9ed4fd82a66d902bbf2b47e0cbe4b5b2773fdde88add0f35"
    ),
}

PRESERVED_V2_BLOB_SHA = {
    "domain/market_router_v2_direct_provider.py": "9b6e887136835cbc9548056beea467d6d3dd12c8",
    "domain/portfolio_optimizer_v2_direct_provider.py": "04e6c751ab53b7e3310a4a1c263675fd444b4d1f",
    "domain/price_all_v2_direct_provider.py": "408dd50c5103032ab5e5879f65118b64513a41b1",
}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if type(value) is not dict:
        raise RuntimeError(f"expected a JSON object: {path}")
    return value


def _git_bytes(*args: str) -> bytes:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, check=False
    )
    if result.returncode:
        raise RuntimeError(
            f"git {' '.join(args)} failed: {result.stderr.decode(errors='replace').strip()}"
        )
    return result.stdout


def _git_text(*args: str) -> str:
    return _git_bytes(*args).decode("utf-8").strip()


def _module_path(module_name: str) -> Path | None:
    pieces = module_name.split(".")
    module_file = ROOT.joinpath(*pieces).with_suffix(".py")
    if module_file.is_file():
        return module_file
    package_file = ROOT.joinpath(*pieces, "__init__.py")
    return package_file if package_file.is_file() else None


def _package_name(module_name: str, source_path: Path) -> str:
    return module_name if source_path.name == "__init__.py" else module_name.rpartition(".")[0]


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
    return f"{package}.{node.module}" if node.module else package


def _prefix_modules(module_name: str) -> tuple[str, ...]:
    pieces = module_name.split(".")
    return tuple(".".join(pieces[:index]) for index in range(1, len(pieces) + 1))


def _direct_local_imports(module_name: str) -> frozenset[str]:
    source_path = _module_path(module_name)
    if source_path is None:
        raise RuntimeError(f"module does not resolve locally: {module_name}")
    tree = ast.parse(
        source_path.read_text(encoding="utf-8-sig"), filename=str(source_path)
    )
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.update(
                    prefix
                    for prefix in _prefix_modules(alias.name)
                    if _module_path(prefix) is not None
                )
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_from_base(module_name, source_path, node)
            imports.update(
                prefix
                for prefix in _prefix_modules(base)
                if _module_path(prefix) is not None
            )
            for alias in node.names:
                if alias.name == "*":
                    continue
                candidate = f"{base}.{alias.name}" if base else alias.name
                if _module_path(candidate) is not None:
                    imports.add(candidate)
    return frozenset(imports)


def _recursive_import_closure(root_module: str) -> frozenset[str]:
    pending = [root_module]
    visited: set[str] = set()
    while pending:
        module_name = pending.pop()
        if module_name in visited:
            continue
        if _module_path(module_name) is None:
            continue
        visited.add(module_name)
        pending.extend(sorted(_direct_local_imports(module_name) - visited))
    return frozenset(visited)


def _supported_roots() -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    artifact = _load_object(P0_2_RUNTIME_ARTIFACT)
    if artifact.get("policy_id") != "ATHENA_RUNTIME_REACHABILITY_V1":
        raise RuntimeError("frozen P0.2 runtime artifact policy drifted")
    p0_2_value = artifact.get("p0_2_supported_roots")
    if type(p0_2_value) is not list or len(p0_2_value) != 6:
        raise RuntimeError("frozen P0.2 supported-root set drifted")
    p0_2_roots = tuple(p0_2_value)
    if len(set(p0_2_roots)) != len(p0_2_roots):
        raise RuntimeError("frozen P0.2 supported roots are not unique")
    combined = tuple(sorted(set(CURRENT_SUPPORTED_ROOTS).union(p0_2_roots)))
    missing = tuple(root for root in combined if _module_path(root) is None)
    if missing:
        raise RuntimeError(f"supported roots do not resolve: {missing}")
    return CURRENT_SUPPORTED_ROOTS, p0_2_roots, combined


def _static_closure_proof() -> dict[str, Any]:
    current_roots, p0_2_roots, combined = _supported_roots()
    closure_by_root: dict[str, list[str]] = {}
    violations: dict[str, list[str]] = {}
    for root in combined:
        closure = _recursive_import_closure(root)
        closure_by_root[root] = sorted(closure)
        reached = sorted(closure.intersection(FORBIDDEN_DEPRECATED_BUSINESS_MODULES))
        if reached:
            violations[root] = reached
    if violations:
        raise RuntimeError(f"supported roots reach forbidden modules: {violations}")
    canonical_reachability = {
        root: implementation in closure_by_root[root]
        for root, implementation in CANONICAL_CURRENT_IMPLEMENTATIONS.items()
    }
    if not all(canonical_reachability.values()):
        raise RuntimeError(
            f"canonical roots do not reach private implementations: {canonical_reachability}"
        )
    return {
        "current_supported_roots": list(current_roots),
        "p0_2_supported_roots": list(p0_2_roots),
        "combined_supported_roots": list(combined),
        "closure_by_root": closure_by_root,
        "forbidden_reachability_by_root": {root: [] for root in combined},
        "canonical_private_implementation_reachability": canonical_reachability,
    }


def _validate_rename_surface() -> dict[str, Any]:
    for former, replacement in EXACT_RENAME_MAP.items():
        if not (ROOT / former).is_file() or not (ROOT / replacement).is_file():
            raise RuntimeError(f"rename surface is incomplete: {former} -> {replacement}")
    for canonical, implementation in CANONICAL_CURRENT_IMPLEMENTATIONS.items():
        imports = _direct_local_imports(canonical)
        if implementation not in imports:
            raise RuntimeError(f"{canonical} does not directly import {implementation}")
    for shim, replacement in COMPATIBILITY_SHIMS.items():
        imports = _direct_local_imports(shim)
        if replacement not in imports:
            raise RuntimeError(f"compatibility shim {shim} does not import {replacement}")

    historical_path = ROOT / "domain/_historical_market_router_v1.py"
    base_router = _git_bytes("show", f"{BASE_MAIN_SHA}:domain/market_router.py").decode("utf-8")
    historical = historical_path.read_text(encoding="utf-8-sig")

    def without_docstring(source: str, filename: str) -> str:
        tree = ast.parse(source, filename=filename)
        if (
            tree.body
            and isinstance(tree.body[0], ast.Expr)
            and isinstance(tree.body[0].value, ast.Constant)
            and isinstance(tree.body[0].value.value, str)
        ):
            tree.body.pop(0)
        return ast.dump(tree, annotate_fields=True, include_attributes=False)

    historical_body_preserved = without_docstring(
        base_router, "base:domain/market_router.py"
    ) == without_docstring(historical, str(historical_path))
    if not historical_body_preserved:
        raise RuntimeError("historical Router-v1 implementation body drifted during rename")

    offline_imports = {
        module: sorted(_direct_local_imports(module))
        for module in ("domain.accumulator_optimizer", "scripts.evaluate_market_router")
    }
    if any(
        "domain._historical_market_router_v1" not in imports
        for imports in offline_imports.values()
    ):
        raise RuntimeError("classified Router-v1 offline callers were not moved to history")
    return {
        "rename_map": dict(EXACT_RENAME_MAP),
        "canonical_current_implementations": dict(CANONICAL_CURRENT_IMPLEMENTATIONS),
        "compatibility_shims": dict(COMPATIBILITY_SHIMS),
        "historical_router_v1_body_preserved": historical_body_preserved,
        "historical_router_v1_offline_imports": offline_imports,
    }


def _validate_router_v1_classification(p0_2_roots: list[str]) -> dict[str, Any]:
    classification = _load_object(ROUTER_V1_CLASSIFICATION_PATH)
    if (
        classification.get("policy_id")
        != "ATHENA_P3_3_ROUTER_V1_CALLER_CLASSIFICATION_V1"
        or classification.get("repository_base_main_sha") != BASE_MAIN_SHA
        or classification.get("supported_roots") != p0_2_roots
        or classification.get("supported_router_v1_caller_count") != 0
        or classification.get("router_v1_supported_caller_blocker") is not False
        or classification.get("classification_complete_before_source_edits") is not True
    ):
        raise RuntimeError("Router-v1 caller classification drifted")
    callers = classification.get("router_v1_route_market_candidates_callers")
    if type(callers) is not list or {row.get("caller") for row in callers} != {
        "domain.accumulator_optimizer",
        "scripts.evaluate_market_router",
    }:
        raise RuntimeError("Router-v1 classified caller set drifted")
    if any(row.get("supported_root_reachable") is not False for row in callers):
        raise RuntimeError("a classified Router-v1 caller is supported-root reachable")
    return classification


def _record_summary(registry: ComponentAuthorityRegistry) -> dict[str, dict[str, Any]]:
    fields = (
        "component_id",
        "contract_sha256",
        "artifact_git_blob_sha",
        "role",
        "allowed_profiles",
        "promotion_state",
        "main_authority",
        "compatible_schema_versions",
    )
    return {
        record.responsibility_id: {
            field: (
                list(getattr(record, field))
                if field in {"allowed_profiles", "compatible_schema_versions"}
                else getattr(record, field)
            )
            for field in fields
        }
        for record in sorted(registry.records, key=lambda item: item.responsibility_id)
    }


def _registry_proof() -> dict[str, Any]:
    before_bytes = _git_bytes(
        "show", f"{BASE_MAIN_SHA}:config/architecture/component-authority-registry-v1.json"
    )
    before = ComponentAuthorityRegistry.from_json_bytes(before_bytes)
    after = load_default_registry()
    if before.canonical_sha256 != EXPECTED_REGISTRY_BEFORE_SHA256:
        raise RuntimeError("pre-P3.3 registry identity drifted")
    if after.canonical_sha256 != EXPECTED_REGISTRY_AFTER_SHA256:
        raise RuntimeError("post-P3.3 registry identity drifted")

    before_records = {item.responsibility_id: item for item in before.records}
    after_records = {item.responsibility_id: item for item in after.records}
    if set(before_records) != set(after_records):
        raise RuntimeError("registry responsibility set changed")
    invariant_fields = (
        "responsibility_id",
        "regime_id",
        "contract_sha256",
        "role",
        "allowed_profiles",
        "promotion_state",
        "main_authority",
        "compatible_schema_versions",
    )
    for responsibility, old in before_records.items():
        new = after_records[responsibility]
        if any(getattr(old, field) != getattr(new, field) for field in invariant_fields):
            raise RuntimeError(f"registry authority metadata changed: {responsibility}")
        module_path = ROOT.joinpath(*new.component_id.split(".")).with_suffix(".py")
        if not module_path.is_file():
            raise RuntimeError(f"registered owner source is absent: {new.component_id}")
        if _git_text("hash-object", str(module_path)) != new.artifact_git_blob_sha:
            raise RuntimeError(f"registered owner artifact identity drifted: {new.component_id}")

    if (
        before_records["market_router"].component_id
        != "domain.market_router_canonical_adapter"
        or after_records["market_router"].component_id != "domain.market_router"
    ):
        raise RuntimeError("Router registry owner was not mechanically rebound")
    expected_aliases = {
        "domain.current_shadow_all_market_portfolio": "domain.portfolio_optimizer",
        "domain.current_shadow_all_market_price_all": "domain.price_all",
        "domain.current_shadow_all_market_router": "domain.market_router",
        "domain.market_router_canonical_adapter": "domain.market_router",
    }
    actual_aliases = {item.alias_id: item.target_component_id for item in after.aliases}
    if actual_aliases != expected_aliases:
        raise RuntimeError(f"post-P3.3 registry aliases drifted: {actual_aliases}")
    return {
        "registry_before_sha256": before.canonical_sha256,
        "registry_after_sha256": after.canonical_sha256,
        "owners_before": _record_summary(before),
        "owners_after": _record_summary(after),
        "authority_metadata_changed": False,
        "router_owner_rebound": True,
        "aliases_after": dict(sorted(actual_aliases.items())),
    }


def _contract_hash_proof() -> dict[str, dict[str, str]]:
    from domain import canonical_core, market_router, portfolio_optimizer, price_all
    from domain import _market_router_current_provider as router_v3
    from domain import _portfolio_optimizer_current_provider as portfolio_v3
    from domain import _price_all_current_provider as price_v3
    from domain import _market_router_v2_contracts as router_v2
    from domain import _portfolio_optimizer_v2_direct_provider_contracts as portfolio_v2
    from domain import _price_all_v2_direct_provider_contracts as price_v2

    price_identity = price_all.validate_price_all_contract()
    router_identity = market_router.validate_canonical_market_router_contract()
    portfolio_identity = portfolio_optimizer.validate_portfolio_contract()
    core_identity = canonical_core.validate_canonical_core_contract()
    actual = {
        "canonical": {
            "canonical_core": core_identity["canonical_core_contract_sha256"],
            "market_router": router_identity["canonical_market_router_contract_sha256"],
            "portfolio_optimizer": portfolio_identity["canonical_portfolio_contract_sha256"],
            "price_all": price_identity["implementation_contract_sha256"],
        },
        "v2": {
            "market_router": router_v2.calculate_market_router_v2_contract_sha256(),
            "portfolio_optimizer": portfolio_v2.calculate_portfolio_optimizer_v2_contract_sha256(),
            "price_all": price_v2.calculate_price_all_v2_contract_sha256(),
        },
        "v3": {
            "market_router": router_v3.calculate_market_router_v3_contract_sha256(),
            "portfolio_optimizer": portfolio_v3.calculate_portfolio_optimizer_v3_contract_sha256(),
            "price_all": price_v3.calculate_price_all_v3_contract_sha256(),
        },
    }
    if actual != EXPECTED_CONTRACT_HASHES:
        raise RuntimeError(f"P3.3 contract identity drifted: {actual}")
    return actual


def _preservation_proof() -> dict[str, Any]:
    historical_artifacts: dict[str, dict[str, Any]] = {}
    for relative, expected_sha in PRESERVED_HISTORICAL_ARTIFACT_SHA256.items():
        source = _git_bytes("show", f"{BASE_MAIN_SHA}:{relative}")
        if hashlib.sha256(source).hexdigest() != expected_sha:
            raise RuntimeError(f"historical artifact source identity drifted: {relative}")
        working = (ROOT / relative).read_bytes().replace(b"\r\n", b"\n")
        if working != source:
            raise RuntimeError(f"historical artifact changed: {relative}")
        historical_artifacts[relative] = {
            "sha256": expected_sha,
            "preserved": True,
        }

    v2_files: dict[str, dict[str, Any]] = {}
    for relative, expected_blob in PRESERVED_V2_BLOB_SHA.items():
        base_blob = _git_text("rev-parse", f"{BASE_MAIN_SHA}:{relative}")
        current_blob = _git_text("hash-object", relative)
        if base_blob != expected_blob or current_blob != expected_blob:
            raise RuntimeError(f"retained v2 implementation changed: {relative}")
        v2_files[relative] = {
            "git_blob_sha": expected_blob,
            "preserved": True,
        }
    return {
        "historical_artifacts": historical_artifacts,
        "retained_v2_implementation_files": v2_files,
        "old_historical_receipts_changed": False,
        "p0_5_artifact_changed": False,
        "p3_1_promotion_receipt_changed": False,
        "p3_1_migration_receipt_changed": False,
        "p3_2_receipt_changed": False,
        "p3_2_vector_fixture_changed": False,
        "p0_3_authority_parity_artifact_changed": False,
        "p0_4_baseline_rewritten": False,
    }


def _validate_p3_2_receipt() -> dict[str, Any]:
    receipt = _load_object(P3_2_RECEIPT_PATH)
    unsigned = dict(receipt)
    digest = unsigned.pop("canonical_sha256", None)
    if (
        receipt.get("repository_base_main_sha") != P3_2_REPOSITORY_BASE_MAIN_SHA
        or digest != P3_2_RECEIPT_CANONICAL_SHA256
        or _canonical_sha256(unsigned) != digest
        or receipt.get("p3_2_exit_gate_satisfied") is not True
    ):
        raise RuntimeError("P3.2 receipt identity or exit gate drifted")
    source = _git_bytes("show", f"{BASE_MAIN_SHA}:{P3_2_RECEIPT_PATH.relative_to(ROOT).as_posix()}")
    if hashlib.sha256(source).hexdigest() != P3_2_RECEIPT_SOURCE_SHA256:
        raise RuntimeError("P3.2 source artifact SHA-256 drifted")
    vector_path = ROOT / "tests/fixtures/architecture/p3_2_frozen_v2_policy_vectors_v1.json"
    vectors = _load_object(vector_path)
    unsigned_vectors = dict(vectors)
    vector_digest = unsigned_vectors.pop("canonical_sha256", None)
    if (
        vector_digest != P3_2_POLICY_VECTOR_CANONICAL_SHA256
        or _canonical_sha256(unsigned_vectors) != vector_digest
    ):
        raise RuntimeError("P3.2 policy-vector fixture identity drifted")
    return {
        "repository_base_main_sha": P3_2_REPOSITORY_BASE_MAIN_SHA,
        "receipt_canonical_sha256": digest,
        "receipt_source_sha256": P3_2_RECEIPT_SOURCE_SHA256,
        "policy_vector_canonical_sha256": vector_digest,
        "exit_gate_satisfied": True,
    }


def _dynamic_subprocess_proof() -> dict[str, Any]:
    code = r'''
from datetime import timedelta
import json
from pathlib import Path
import socket
import sys
import tempfile

network_attempts = []
def reject_network(*args, **kwargs):
    network_attempts.append(repr((args, kwargs)))
    raise AssertionError("network access is forbidden in the P3.3 audit")
socket.create_connection = reject_network
socket.socket.connect = reject_network

from pytest import MonkeyPatch
from domain import canonical_core, market_router, portfolio_optimizer, price_all
from domain import _portfolio_optimizer_current_provider as portfolio_implementation
from domain import current_shadow_canonical_core_adapter as shadow_adapter
from domain import current_sportybet_accumulator_request as current_request
from domain import sportybet_current_event_discovery_reconciliation as current_reconciliation
from domain.fixture_intelligence import build_snapshot
from domain.fixture_state_v2 import build_fixture_state_v2_snapshot
from domain.markets import MarketId, OutcomeId
from domain.run_contracts import AuthorityManifest
from models.prediction import Prediction
from services import main_canonical_prediction_adapter as presentation

price_identity = price_all.validate_price_all_contract()
router_identity = market_router.validate_canonical_market_router_contract()
portfolio_identity = portfolio_optimizer.validate_portfolio_contract()
core_identity = canonical_core.validate_canonical_core_contract()

def manifest(profile):
    return AuthorityManifest(
        authority_profile=profile,
        mode="p3_3_module_canonicalization_audit",
        provider_acquisition=False,
        share_code_generation=False,
        login=False,
        cookies=False,
        wallet=False,
        staking=False,
        wager=False,
    )

bindings = {
    profile: canonical_core.resolve_canonical_core(
        manifest(profile),
        regime_id=canonical_core.CURRENT_SPORTYBET_PROVIDER,
        required_schema_version=1,
    )
    for profile in ("MAIN", "SHADOW")
}
assert bindings["MAIN"].record_for("market_router").component_id == "domain.market_router"
assert bindings["SHADOW"].record_for("market_router").component_id == "domain.market_router"
assert presentation.resolve_main_canonical_core().authority_profile == "MAIN"
assert shadow_adapter.resolve_shadow_canonical_core().authority_profile == "SHADOW"

from tests._market_router_helpers import _CONTEXT_BINDINGS, _fact
from tests._price_all_helpers import phase6_candidate
from tests.test_current_direct_provider_live_quote_mapping_consumption import (
    EVALUATION,
    EVENT,
    FIXTURE,
    KICKOFF,
    _build as build_price_source,
    _inventory,
    _mapped_row,
    _selection,
    _source_mapping,
)

patcher = MonkeyPatch()
try:
    selections = (
        _selection(market_id="1", market_name="Match Result", specifier=None, outcome_id="1", outcome_name="Home", odds_raw="2.00", decimal_odds=2.0),
        _selection(market_id="1", market_name="Match Result", specifier=None, outcome_id="X", outcome_name="Draw", odds_raw="4.00", decimal_odds=4.0),
        _selection(market_id="1", market_name="Match Result", specifier=None, outcome_id="2", outcome_name="Away", odds_raw="4.00", decimal_odds=4.0),
    )
    inventory = _inventory(*selections)
    mapped = tuple(
        _mapped_row(
            inventory,
            market_id="1",
            market_name="Match Result",
            specifier=None,
            outcome_id=provider_outcome,
            outcome_name=name,
            canonical_market=MarketId.MATCH_RESULT,
            canonical_outcome=outcome,
            line=None,
        )
        for provider_outcome, name, outcome in (
            ("1", "Home", OutcomeId.HOME),
            ("X", "Draw", OutcomeId.DRAW),
            ("2", "Away", OutcomeId.AWAY),
        )
    )
    price_source, _calls = build_price_source(
        patcher,
        inventory=inventory,
        source_mapping=_source_mapping(inventory, *mapped),
    )
    candidate = phase6_candidate(
        MarketId.MATCH_RESULT,
        OutcomeId.HOME,
        None,
        (0.60, 0.22, 0.18),
        fixture_id=FIXTURE,
        event_id=EVENT,
    )[0]
    canonical_price = price_all.price_all_as_of(
        (candidate,),
        price_source,
        evaluation_time=EVALUATION,
    )
    facts = tuple(
        _fact(category, field, value, marker=str(index))
        for index, (category, field, value) in enumerate(_CONTEXT_BINDINGS)
    )
    fixture_state = build_fixture_state_v2_snapshot(
        build_snapshot(
            FIXTURE,
            KICKOFF,
            EVALUATION - timedelta(minutes=1),
            facts,
        )
    )
    route = market_router.route(
        canonical_price,
        fixture_state=fixture_state,
        evaluation_time=EVALUATION + timedelta(seconds=10),
    )
    source_evaluation = route._source_decision.price_all_evaluation
    retained = source_evaluation._source_bundle._source_mapping._current_bundle
    retained.rows = (
        current_reconciliation.CurrentEventReconciliationRow(
            event_id=EVENT,
            home_team_name=source_evaluation.home_team_name,
            away_team_name=source_evaluation.away_team_name,
            competition_name="Reviewed League",
            kickoff_utc=KICKOFF,
            discovery_observed_at=source_evaluation.discovery_observed_at,
            discovery_age_seconds=source_evaluation.discovery_age_seconds,
            kickoff_lead_seconds=source_evaluation.kickoff_lead_seconds,
            disposition=current_reconciliation.CurrentEventReconciliationDisposition.UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILED,
            exact_fotmob_match_count=1,
            matched_fotmob_fixture_id=FIXTURE,
            direct_event_observed_at=source_evaluation.direct_event_observed_at,
            direct_event_age_seconds=source_evaluation.direct_event_age_seconds,
            direct_event_manifest_sha256=source_evaluation.current_manifest_sha256,
            direct_event_inventory_sha256=source_evaluation.current_inventory_sha256,
            direct_event_raw_sha256=source_evaluation.current_raw_sha256,
            fixture_reconciliation_authorized=True,
        ),
    )
    retained.canonical_sha256 = source_evaluation.source_current_reconciliation_sha256
    patcher.setattr(
        portfolio_implementation.current_recon,
        "verify_current_event_discovery_reconciliation_bundle",
        lambda value: retained
        if value is retained
        else (_ for _ in ()).throw(AssertionError("unexpected reconciliation bundle")),
    )
    selected = portfolio_optimizer.optimize_portfolio_as_of(
        (route,),
        target_legs=1,
        evaluation_time=EVALUATION + timedelta(seconds=20),
    )
    prediction = Prediction(
        fixture_id=6001,
        league="Synthetic League",
        home_team="Legacy Home",
        away_team="Legacy Away",
        home_strength=70.0,
        away_strength=30.0,
        home_xg=1.5,
        away_xg=0.7,
        expected_goals=2.2,
    )
    projected = presentation.project_canonical_router_decision(prediction, route)
    dependencies = dict(current_request.validate_current_request_dependencies())
    with tempfile.TemporaryDirectory(prefix="athena-p3-3-audit-") as temporary:
        request_result = current_request.execute_current_accumulator_request(
            target_size=20,
            output_dir=Path(temporary),
        )
finally:
    patcher.undo()

assert selected.selected_count == 1
assert selected.shortfall == 0
assert projected.recommended_market != presentation.NO_RECOMMENDATION
assert request_result.status == current_request.STATUS_PHASE6_AUTHORITY_REQUIRED
assert request_result.real_current_provider_execution_attempted is False
assert request_result.wager_placed is False
assert not network_attempts

forbidden = {
    "domain.price_all_v2_direct_provider",
    "domain.market_router_v2_direct_provider",
    "domain.portfolio_optimizer_v2_direct_provider",
    "domain.price_all_v3_current_provider",
    "domain.market_router_v3_current_provider",
    "domain.portfolio_optimizer_v3_current_provider",
    "domain.market_router_canonical_adapter",
    "domain._historical_market_router_v1",
}
loaded_forbidden = sorted(forbidden.intersection(sys.modules))
assert not loaded_forbidden, loaded_forbidden
print(json.dumps({
    "canonical_contracts_validated": {
        "canonical_core": core_identity["canonical_core_contract_sha256"],
        "market_router": router_identity["canonical_market_router_contract_sha256"],
        "portfolio_optimizer": portfolio_identity["canonical_portfolio_contract_sha256"],
        "price_all": price_identity["implementation_contract_sha256"],
    },
    "core_profiles_resolved": sorted(bindings),
    "shadow_adapter_resolved": True,
    "main_presentation_recommendation": projected.recommended_market,
    "offline_price_router_portfolio_selected_count": selected.selected_count,
    "offline_price_router_portfolio_shortfall": selected.shortfall,
    "current_request_dependencies": dependencies,
    "current_request_status": request_result.status,
    "current_request_blocked_at": request_result.blocked_at,
    "real_current_provider_execution_attempted": False,
    "network_attempt_count": len(network_attempts),
    "forbidden_sys_modules": loaded_forbidden,
    "wager_placed": False,
}, sort_keys=True))
'''
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            "fresh-process P3.3 proof failed:\n" + result.stdout + result.stderr
        )
    try:
        proof = json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise RuntimeError("fresh-process P3.3 proof returned invalid output") from exc
    if proof.get("forbidden_sys_modules") != [] or proof.get("network_attempt_count") != 0:
        raise RuntimeError(f"fresh-process isolation proof failed: {proof}")
    return proof


def build_receipt() -> dict[str, Any]:
    p3_2 = _validate_p3_2_receipt()
    static = _static_closure_proof()
    rename = _validate_rename_surface()
    classification = _validate_router_v1_classification(static["p0_2_supported_roots"])
    registry = _registry_proof()
    contracts = _contract_hash_proof()
    preserved = _preservation_proof()
    dynamic = _dynamic_subprocess_proof()

    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "repository_base_main_sha": BASE_MAIN_SHA,
        "p3_2": p3_2,
        "explicit_current_supported_roots": static["current_supported_roots"],
        "frozen_p0_2_supported_roots": static["p0_2_supported_roots"],
        "combined_supported_roots": static["combined_supported_roots"],
        "forbidden_deprecated_business_modules": sorted(
            FORBIDDEN_DEPRECATED_BUSINESS_MODULES
        ),
        "allowed_narrow_v2_contract_modules": sorted(ALLOWED_NARROW_V2_CONTRACT_MODULES),
        "static_import_closure_by_root": static["closure_by_root"],
        "static_forbidden_reachability_by_root": static[
            "forbidden_reachability_by_root"
        ],
        "canonical_private_implementation_reachability": static[
            "canonical_private_implementation_reachability"
        ],
        "exact_rename_map": rename["rename_map"],
        "canonical_current_implementations": rename[
            "canonical_current_implementations"
        ],
        "deprecated_compatibility_shims": rename["compatibility_shims"],
        "historical_router_v1_body_preserved": rename[
            "historical_router_v1_body_preserved"
        ],
        "historical_router_v1_offline_imports": rename[
            "historical_router_v1_offline_imports"
        ],
        "router_v1_caller_classification": classification,
        "router_v1_caller_classification_canonical_sha256": _canonical_sha256(
            classification
        ),
        "historical_router_v1_supported_current_root": False,
        "component_registry_before_sha256": registry["registry_before_sha256"],
        "component_registry_after_sha256": registry["registry_after_sha256"],
        "registered_owners_before": registry["owners_before"],
        "registered_owners_after": registry["owners_after"],
        "registry_aliases_after": registry["aliases_after"],
        "registry_authority_metadata_changed": registry[
            "authority_metadata_changed"
        ],
        "promotion_metadata_changed": False,
        "main_shadow_profile_eligibility_changed": False,
        "router_registry_owner_rebound": registry["router_owner_rebound"],
        "unchanged_contract_sha256": contracts,
        "preserved_historical_artifacts": preserved["historical_artifacts"],
        "preserved_v2_implementation_files": preserved[
            "retained_v2_implementation_files"
        ],
        "old_historical_receipts_changed": preserved[
            "old_historical_receipts_changed"
        ],
        "p0_5_artifact_changed": preserved["p0_5_artifact_changed"],
        "p3_1_promotion_receipt_changed": preserved[
            "p3_1_promotion_receipt_changed"
        ],
        "p3_1_migration_receipt_changed": preserved[
            "p3_1_migration_receipt_changed"
        ],
        "p3_2_receipt_changed": preserved["p3_2_receipt_changed"],
        "p3_2_vector_fixture_changed": preserved[
            "p3_2_vector_fixture_changed"
        ],
        "p0_3_authority_parity_artifact_changed": preserved[
            "p0_3_authority_parity_artifact_changed"
        ],
        "p0_4_baseline_rewritten": preserved["p0_4_baseline_rewritten"],
        "p3_2_policy_vector_canonical_sha256": p3_2[
            "policy_vector_canonical_sha256"
        ],
        "fresh_subprocess_proof": dynamic,
        "final_static_forbidden_reachability": [],
        "final_dynamic_forbidden_sys_modules": dynamic["forbidden_sys_modules"],
        "model_formula_changed": False,
        "probability_formula_changed": False,
        "calibration_formula_changed": False,
        "price_all_formula_changed": False,
        "router_formula_changed": False,
        "portfolio_formula_changed": False,
        "provider_semantics_changed": False,
        "share_code_semantics_changed": False,
        "provider_acquisition": False,
        "network_access": False,
        "current_shadow_triggered": False,
        "fresh_holdout_triggered": False,
        "p3_0_e1_triggered": False,
        "share_code_operation": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "wager_placed": False,
        "historical_modules_deleted": False,
        "v2_modules_deleted": False,
        "compatibility_shim_retirement_deferred": True,
        "compatibility_shim_retirement_deferred_to_later_cleanup": True,
        "compatibility_shim_retirement_authorized": False,
        "compatibility_shims_are_authority": False,
        "p3_3_exit_gate_satisfied": True,
        "next_required_step": "P4_1_CLI_CONSOLIDATION_REQUIRED",
    }
    receipt["canonical_sha256"] = _canonical_sha256(receipt)
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the verified deterministic receipt to its canonical artifact path.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    receipt = build_receipt()
    if args.write:
        DEFAULT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_OUTPUT.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {DEFAULT_OUTPUT}")
    print(receipt["canonical_sha256"])
    print(f"p3_3_exit_gate_satisfied={receipt['p3_3_exit_gate_satisfied']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
