"""Exact release-resource adapter resolution; no module-relative/Git fallback."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

import pytest

from domain import current_shadow_canonical_core_adapter as adapter
from domain import current_shadow_fresh_reprice_runtime as fresh
from runtime.release_identity import canonical_release_manifest_bytes, verify_installed_release
from runtime.resources import ResourceResolver
from scripts import build_dev_bundle

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = "config/architecture/component-authority-registry-v1.json"


@pytest.fixture(scope="module")
def staged(tmp_path_factory):
    root = tmp_path_factory.mktemp("adapter-release") / "bundle"
    metadata = build_dev_bundle.build(repo=ROOT, platform_tag="windows" if sys.platform == "win32" else "linux", output=root, freeze=False)
    return root, metadata["trusted_manifest_sha256"]


@pytest.fixture
def installed(staged, tmp_path):
    original, trusted = staged
    root = tmp_path / "release"
    shutil.copytree(original, root)
    identity = verify_installed_release(root, trusted)
    return identity, ResourceResolver.for_installed(identity)


def test_installed_matches_development_without_git_or_default_registry(installed, monkeypatch):
    adapter.clear_shadow_canonical_core_cache()
    development = adapter.resolve_shadow_canonical_core()
    identity, resources = installed
    calls = []
    def forbidden(*a, **k):
        calls.append("forbidden")
        raise AssertionError("installed resolution used checkout authority")
    monkeypatch.setattr(adapter._registry, "load_default_registry", forbidden)
    monkeypatch.setattr(adapter._core, "read_tracked_head_blob", forbidden)
    import runtime.source_identity as source
    monkeypatch.setattr(source, "read_tracked_head_blob", forbidden)
    import runtime.resources as resources_module
    monkeypatch.setattr(resources_module, "read_tracked_head_blob", forbidden)
    actual = adapter.resolve_shadow_canonical_core(release_identity=identity, resources=resources)
    assert actual.to_dict() == development.to_dict()
    assert actual.registry_canonical_sha256 == development.registry_canonical_sha256
    assert {r.responsibility_id: r.component_id for r in actual.records} == dict(adapter.EXPECTED_COMPONENTS)
    assert adapter.canonical_core_summary(release_identity=identity, resources=resources)["component_ids"] == dict(adapter.EXPECTED_COMPONENTS)
    assert calls == []
    assert (identity.release_root / REGISTRY).is_file()
    assert not (identity.release_root / "bin/athena-bundle/_internal" / REGISTRY).exists()
    # No installed cache: revalidation on a second invocation yields a new proof.
    assert adapter.resolve_shadow_canonical_core(release_identity=identity, resources=resources) is not actual
    adapter.clear_shadow_canonical_core_cache()


@pytest.mark.parametrize("mode", ["identity-only", "resolver-only", "different-identity", "wrong-type"])
def test_mixed_source_pair_rejected_before_execution(installed, mode):
    identity, resolver = installed
    if mode == "identity-only": pair = (identity, None)
    elif mode == "resolver-only": pair = (None, resolver)
    elif mode == "wrong-type": pair = (object(), resolver)
    else:
        second = verify_installed_release(identity.release_root, identity.manifest_sha256)
        pair = (second, resolver)
    with pytest.raises(adapter.CurrentShadowCanonicalCoreAdapterError):
        adapter.resolve_shadow_canonical_core(release_identity=pair[0], resources=pair[1])
    with pytest.raises(Exception, match="canonical Price-all owner resolution failed"):
        adapter.price_all_shadow_fixture(object(), release_identity=pair[0], resources=pair[1])


@pytest.mark.parametrize("mutation", ["missing", "tampered"])
def test_installed_registry_rechecked_after_verification(installed, mutation):
    identity, resolver = installed
    path = identity.release_root / REGISTRY
    if mutation == "missing": path.unlink()
    else: path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(adapter.CurrentShadowCanonicalCoreAdapterError):
        adapter.resolve_shadow_canonical_core(release_identity=identity, resources=resolver)


@pytest.mark.parametrize("mutation", ["wrong-role", "alias-drift", "canonical-drift"])
def test_trusted_manifest_cannot_override_registry_contract(installed, mutation):
    identity, _ = installed
    root = identity.release_root
    manifest = json.loads((root / "release-manifest.json").read_bytes())
    record = next(r for r in manifest["resources"] if r["logical_path"] == REGISTRY)
    if mutation == "wrong-role": record["role"] = "CONFIG"
    elif mutation == "canonical-drift": record["canonical_sha256"] = "0" * 64
    else:
        value = json.loads((root / REGISTRY).read_bytes())
        alias = next(a for a in value["aliases"] if a["alias_id"] == "domain.current_shadow_all_market_price_all")
        alias["target_component_id"] = "domain.portfolio_optimizer"
        raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        (root / REGISTRY).write_bytes(raw)
        record["byte_sha256"] = hashlib.sha256(raw).hexdigest()
        record["canonical_sha256"] = adapter._registry.ComponentAuthorityRegistry.from_json_bytes(raw).canonical_sha256
    raw = canonical_release_manifest_bytes(manifest)
    (root / "release-manifest.json").write_bytes(raw)
    checked = verify_installed_release(root, hashlib.sha256(raw).hexdigest())
    with pytest.raises(adapter.CurrentShadowCanonicalCoreAdapterError):
        adapter.resolve_shadow_canonical_core(release_identity=checked, resources=ResourceResolver.for_installed(checked))


def test_explicit_development_and_cache_clear():
    from runtime.release_identity import verify_development_checkout
    identity = verify_development_checkout(ROOT)
    resolver = ResourceResolver.for_development(identity)
    adapter.clear_shadow_canonical_core_cache()
    original = adapter.resolve_shadow_canonical_core()
    assert adapter.resolve_shadow_canonical_core() is original
    assert adapter.resolve_shadow_canonical_core(release_identity=identity, resources=resolver).to_dict() == original.to_dict()
    adapter.clear_shadow_canonical_core_cache()
    assert adapter.resolve_shadow_canonical_core() is not original


def test_fresh_incomplete_pair_rejected_before_evidence(installed):
    identity, _ = installed
    with pytest.raises(adapter.CurrentShadowCanonicalCoreAdapterError):
        fresh._refresh_selected_inputs(SimpleNamespace(router_inputs=()), repository_root=ROOT,
            runtime_bindings=object(), release_identity=identity)


@pytest.mark.parametrize("wrapper,owner", [
    ("price_all_shadow_fixture", "_legacy_price"), ("verify_shadow_price_all_bundle", "_legacy_price"),
    ("route_shadow_price_results", "_legacy_router"),
    ("build_shadow_portfolio_router_input", "_legacy_portfolio"),
    ("verify_shadow_portfolio_router_input", "_legacy_portfolio"), ("optimize_shadow_portfolio", "_legacy_portfolio"),
])
def test_each_wrapper_resolves_exact_installed_pair(installed, monkeypatch, wrapper, owner):
    identity, resources = installed
    resolve = adapter.resolve_shadow_canonical_core
    seen = []
    def record(**kwargs):
        assert kwargs["release_identity"] is identity
        assert kwargs["resources"] is resources
        seen.append(wrapper)
        return resolve(**kwargs)
    monkeypatch.setattr(adapter, "resolve_shadow_canonical_core", record)
    def delegate(*a, **k):
        assert "release_identity" not in k and "resources" not in k
        return "delegated"
    monkeypatch.setattr(getattr(adapter, owner), wrapper, delegate)
    assert getattr(adapter, wrapper)(object(), release_identity=identity, resources=resources) == "delegated"
    assert seen == [wrapper]
