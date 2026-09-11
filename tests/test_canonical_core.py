from __future__ import annotations

import ast
import dataclasses
from datetime import timedelta
from pathlib import Path

import pytest

from domain import canonical_core as core
from domain import component_authority_registry as registry_module
from domain import market_router_canonical_adapter as router
from domain import portfolio_optimizer as portfolio
from domain import price_all
from domain import run_contracts
from domain import sportybet_share_code as share_code
from tests.test_current_direct_provider_live_quote_mapping_consumption import EVALUATION
from tests.test_portfolio_optimizer import _canonical_input
from tests.test_price_all import _build, _candidate
from tests.test_sportybet_share_code import _offline_success


ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / "domain/canonical_core.py"
REGIME = "CURRENT_SPORTYBET_PROVIDER"


def _manifest(*, profile: str = "SHADOW", share_code_generation: bool = False) -> run_contracts.AuthorityManifest:
    return run_contracts.AuthorityManifest(
        authority_profile=profile,
        mode="AS_OF_REPLAY",
        provider_acquisition=False,
        share_code_generation=share_code_generation,
        login=False,
        cookies=False,
        wallet=False,
        staking=False,
        wager=False,
    )


def _core(*, share_code_generation: bool = False) -> core.CanonicalCoreBindings:
    return core.resolve_canonical_core(
        _manifest(share_code_generation=share_code_generation), regime_id=REGIME
    )


def test_contract_and_shadow_resolution_bind_exact_five_champions() -> None:
    assert core.validate_canonical_core_contract()["canonical_core_contract_sha256"] == core.EXPECTED_CONTRACT_SHA256
    bindings = _core()
    assert bindings.schema_version == 1
    assert bindings.policy_id == core.POLICY_ID
    assert bindings.authority_profile == "SHADOW"
    assert tuple(item.responsibility_id for item in bindings.records) == core.CANONICAL_RESPONSIBILITIES
    assert len(bindings.records) == 5
    assert all(item.allowed_profiles == ("SHADOW",) and item.main_authority is False for item in bindings.records)
    assert bindings.canonical_sha256 == core.canonical_sha256({key: value for key, value in bindings.to_dict().items() if key != "canonical_sha256"})


def test_main_and_unknown_or_incompatible_resolution_fail_closed() -> None:
    with pytest.raises(core.CanonicalCoreError, match="resolution failed closed"):
        core.resolve_canonical_core(_manifest(profile="MAIN"), regime_id=REGIME)
    with pytest.raises(core.CanonicalCoreError, match="resolution failed closed"):
        core.resolve_canonical_core(_manifest(), regime_id="UNKNOWN_REGIME")
    with pytest.raises(core.CanonicalCoreError, match="resolution failed closed"):
        core.resolve_canonical_core(_manifest(), regime_id=REGIME, required_schema_version=2)


@pytest.mark.parametrize("responsibility_id", core.CANONICAL_RESPONSIBILITIES)
def test_each_missing_champion_fails_closed(responsibility_id: str) -> None:
    loaded = registry_module.load_default_registry()
    reduced = registry_module.ComponentAuthorityRegistry(
        records=tuple(item for item in loaded.records if item.responsibility_id != responsibility_id)
    )
    with pytest.raises(core.CanonicalCoreError, match="resolution failed closed"):
        core._resolve_canonical_core_with_registry_for_test(
            _manifest(), regime_id=REGIME, registry=reduced
        )


def test_registry_contract_and_artifact_tamper_fail_closed() -> None:
    loaded = registry_module.load_default_registry()
    original = next(item for item in loaded.records if item.responsibility_id == "market_router")
    altered = dataclasses.replace(original, contract_sha256="0" * 64)
    bad = registry_module.ComponentAuthorityRegistry(
        records=tuple(altered if item is original else item for item in loaded.records)
    )
    with pytest.raises(core.CanonicalCoreError, match="contract identity drifted"):
        core._resolve_canonical_core_with_registry_for_test(
            _manifest(), regime_id=REGIME, registry=bad
        )

    altered_blob = dataclasses.replace(original, artifact_git_blob_sha="0" * 40)
    bad_blob = registry_module.ComponentAuthorityRegistry(
        records=tuple(altered_blob if item is original else item for item in loaded.records)
    )
    with pytest.raises(core.CanonicalCoreError, match="source artifact identity drifted"):
        core._resolve_canonical_core_with_registry_for_test(
            _manifest(), regime_id=REGIME, registry=bad_blob
        )


def test_resolution_is_deterministic_and_registry_order_is_not_authority() -> None:
    loaded = registry_module.load_default_registry()
    reordered = registry_module.ComponentAuthorityRegistry(
        records=tuple(reversed(loaded.records)),
        aliases=tuple(reversed(loaded.aliases)),
    )
    first = core._resolve_canonical_core_with_registry_for_test(
        _manifest(), regime_id=REGIME, registry=loaded
    )
    second = core._resolve_canonical_core_with_registry_for_test(
        _manifest(), regime_id=REGIME, registry=reordered
    )
    assert first.to_dict() == second.to_dict()
    assert first.canonical_sha256 == second.canonical_sha256
    with pytest.raises(core.CanonicalCoreError, match="builder-only"):
        core.CanonicalCoreBindings()


def test_public_resolution_rejects_forged_main_promoted_registry() -> None:
    loaded = registry_module.load_default_registry()
    forged = registry_module.ComponentAuthorityRegistry(
        records=tuple(
            dataclasses.replace(
                item,
                allowed_profiles=("MAIN", "SHADOW"),
                promotion_state=registry_module.APPROVED_FOR_MAIN,
                main_authority=True,
            )
            for item in loaded.records
        )
    )
    assert forged.canonical_sha256 != loaded.canonical_sha256
    with pytest.raises(TypeError, match="unexpected keyword argument 'registry'"):
        core.resolve_canonical_core(
            _manifest(profile="MAIN"), regime_id=REGIME, registry=forged
        )


def test_replay_stage_adapters_match_direct_canonical_interfaces(monkeypatch: pytest.MonkeyPatch) -> None:
    bindings = _core()
    source_bundle, _ = _build(monkeypatch)
    direct_price = price_all.price_all_as_of((_candidate(),), source_bundle, evaluation_time=EVALUATION)
    core_price = bindings.price_all_as_of((_candidate(),), source_bundle, evaluation_time=EVALUATION)
    assert core_price.to_dict() == direct_price.to_dict()
    assert core_price.canonical_sha256 == direct_price.canonical_sha256

    _source, direct_router = _canonical_input(monkeypatch)
    wrapped_price = direct_router._price_all_evaluation
    direct_route = router.route(wrapped_price, fixture_state=direct_router._fixture_state, evaluation_time=direct_router.evaluation_time)
    core_route = bindings.route_as_of(wrapped_price, fixture_state=direct_router._fixture_state, evaluation_time=direct_router.evaluation_time)
    assert core_route.to_dict() == direct_route.to_dict()
    assert core_route.canonical_sha256 == direct_route.canonical_sha256

    when = EVALUATION + timedelta(seconds=20)
    direct_portfolio = portfolio.optimize_portfolio_as_of((core_route,), target_legs=25, evaluation_time=when)
    core_portfolio = bindings.optimize_portfolio_as_of((core_route,), target_legs=25, evaluation_time=when)
    assert core_portfolio.to_dict() == direct_portfolio.to_dict()
    assert core_portfolio.canonical_sha256 == direct_portfolio.canonical_sha256
    assert core_portfolio.selected_count == 1
    assert core_portfolio.shortfall == 24


def test_offline_share_code_adapter_requires_explicit_synthetic_operations(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bindings = _core(share_code_generation=True)
    _source, decision = _canonical_input(monkeypatch)
    selected = portfolio.optimize_portfolio_as_of((decision,), target_legs=25, evaluation_time=EVALUATION + timedelta(seconds=20))
    provider_bindings = share_code.build_provider_bindings(selected)
    observed, semantic_resolver, roundtrip_transport = _offline_success(provider_bindings)
    result = bindings.create_share_code_as_of(
        selected, provider_bindings, output_dir=tmp_path, evaluation_time=EVALUATION + timedelta(seconds=30),
        semantic_resolver=semantic_resolver, roundtrip_transport=roundtrip_transport,
    )
    assert type(result) is share_code.VerifiedShareCode
    assert result.selected_leg_count == selected.selected_count == 1
    assert result.shortfall == selected.shortfall == 24
    assert result.to_dict()["exact_create_reload_equality"] is True
    assert result.to_dict()["wager_placed"] is False
    assert observed["semantic_calls"] == observed["transport_calls"] == 1

    without_delivery_capability = _core()
    with pytest.raises(core.CanonicalCoreError, match="does not permit share-code"):
        without_delivery_capability.create_share_code_as_of(
            selected, provider_bindings, output_dir=tmp_path / "denied",
            evaluation_time=EVALUATION + timedelta(seconds=30),
            semantic_resolver=semantic_resolver, roundtrip_transport=roundtrip_transport,
        )


def test_core_import_boundary_has_no_shadow_or_acquisition_or_sensitive_authority() -> None:
    text = CORE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(text)
    imported = set()
    domain_members = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(item.name for item in node.names)
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            if node.module == "domain":
                domain_members.update(item.name for item in node.names)
    forbidden = {
        "domain.current_shadow_all_market_price_all", "domain.current_shadow_all_market_router",
        "domain.current_shadow_all_market_portfolio", "domain.current_shadow_all_market_share_code",
        "domain.current_shadow_all_market_runner", "requests", "selenium", "playwright",
    }
    assert not (forbidden & imported)
    assert {
        "provider_market_semantics", "price_all", "market_router_canonical_adapter",
        "portfolio_optimizer", "sportybet_share_code",
    } <= domain_members
