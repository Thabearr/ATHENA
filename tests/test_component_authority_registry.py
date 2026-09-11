from __future__ import annotations

import dataclasses
import json
from pathlib import Path
import subprocess

import pytest

from domain import component_authority_registry as registry
from domain import market_router_canonical_adapter as router
from domain import portfolio_optimizer as portfolio
from domain import price_all
from domain import provider_market_semantics as provider_semantics
from domain import sportybet_share_code as share_code


ROOT = Path(__file__).resolve().parents[1]
REGIME = "CURRENT_SPORTYBET_PROVIDER"
P2_1_COMPATIBILITY_ALIASES = (
    {
        "alias_id": "domain.current_shadow_all_market_portfolio",
        "target_component_id": "domain.portfolio_optimizer",
    },
    {
        "alias_id": "domain.current_shadow_all_market_price_all",
        "target_component_id": "domain.price_all",
    },
    {
        "alias_id": "domain.current_shadow_all_market_router",
        "target_component_id": "domain.market_router_canonical_adapter",
    },
)


def _git_blob_sha(path: Path) -> str:
    relative = path.resolve().relative_to(ROOT).as_posix()
    completed = subprocess.run(
        ["git", "-C", str(ROOT), "hash-object", "--path", relative, "--filters", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _record(
    *,
    component_id: str = "domain.synthetic_component",
    responsibility_id: str = "market_router",
    regime_id: str = "SYNTHETIC_REGIME",
    role: str = registry.CHAMPION,
    allowed_profiles: tuple[str, ...] = (registry.SHADOW,),
    promotion_state: str = registry.REGISTERED_CHAMPION,
    main_authority: bool = False,
    schema_versions: tuple[int, ...] = (1,),
) -> registry.ComponentAuthorityRecord:
    return registry.ComponentAuthorityRecord(
        responsibility_id=responsibility_id,
        regime_id=regime_id,
        component_id=component_id,
        contract_sha256="a" * 64,
        artifact_git_blob_sha="b" * 40,
        role=role,
        allowed_profiles=allowed_profiles,
        promotion_state=promotion_state,
        main_authority=main_authority,
        compatible_schema_versions=schema_versions,
    )


def test_registry_contract_and_default_source_are_exact() -> None:
    assert registry.calculate_registry_contract_sha256() == registry.EXPECTED_REGISTRY_CONTRACT_SHA256
    assert registry.validate_registry_contract() == registry.EXPECTED_REGISTRY_CONTRACT_SHA256

    loaded = registry.load_default_registry()
    assert loaded.source_controlled_writes_only is True
    assert loaded.runtime_mutation_allowed is False
    assert tuple(item.to_dict() for item in loaded.aliases) == P2_1_COMPATIBILITY_ALIASES
    assert loaded.to_dict()["registry_contract_sha256"] == registry.EXPECTED_REGISTRY_CONTRACT_SHA256

    source = json.loads(registry.DEFAULT_REGISTRY_PATH.read_text(encoding="utf-8"))
    assert source["source_controlled_writes_only"] is True
    assert source["runtime_mutation_allowed"] is False
    assert tuple(source["aliases"]) == P2_1_COMPATIBILITY_ALIASES
    assert registry.ComponentAuthorityRegistry.from_dict(source).to_dict() == loaded.to_dict()


def test_default_registry_binds_exact_p1_3_through_p2_0_component_contracts() -> None:
    loaded = registry.load_default_registry()
    expected = {
        "delivery_share_code_transport": (
            "domain.sportybet_share_code",
            share_code.EXPECTED_CONTRACT_SHA256,
            ROOT / "domain/sportybet_share_code.py",
        ),
        "market_router": (
            "domain.market_router_canonical_adapter",
            router.EXPECTED_CONTRACT_SHA256,
            ROOT / "domain/market_router_canonical_adapter.py",
        ),
        "portfolio_optimizer": (
            "domain.portfolio_optimizer",
            portfolio.EXPECTED_CONTRACT_SHA256,
            ROOT / "domain/portfolio_optimizer.py",
        ),
        "provider_market_semantics": (
            "domain.provider_market_semantics",
            provider_semantics.EXPECTED_CONTRACT_SHA256,
            ROOT / "domain/provider_market_semantics.py",
        ),
        "price_all_and_de_vig": (
            "domain.price_all",
            price_all.IMPLEMENTATION_CONTRACT_SHA256,
            ROOT / "domain/price_all.py",
        ),
    }
    assert {item.responsibility_id for item in loaded.records} == set(expected)
    assert len(loaded.records) == len(expected) == 5

    for item in loaded.records:
        component_id, contract_sha256, path = expected[item.responsibility_id]
        assert item.regime_id == REGIME
        assert item.component_id == component_id
        assert item.contract_sha256 == contract_sha256
        assert item.artifact_git_blob_sha == _git_blob_sha(path)
        assert item.role == registry.CHAMPION
        assert item.allowed_profiles == (registry.SHADOW,)
        assert item.promotion_state == registry.REGISTERED_CHAMPION
        assert item.main_authority is False
        assert item.compatible_schema_versions == (1,)


def test_each_seeded_responsibility_has_one_shadow_champion_and_zero_main_authority() -> None:
    loaded = registry.load_default_registry()
    for item in loaded.records:
        resolved = loaded.resolve_champion(
            item.responsibility_id,
            item.regime_id,
            profile=registry.SHADOW,
            required_schema_version=1,
        )
        assert resolved is item
        with pytest.raises(
            registry.ComponentAuthorityRegistryError,
            match="not eligible for requested profile|APPROVED_FOR_MAIN",
        ):
            loaded.resolve_champion(
                item.responsibility_id,
                item.regime_id,
                profile=registry.MAIN,
                required_schema_version=1,
            )

    assert all(item.main_authority is False for item in loaded.records)
    assert loaded.resolve_research_challengers(
        "market_router",
        REGIME,
        profile=registry.SHADOW,
        required_schema_version=1,
    ) == ()


def test_registration_never_implies_main_promotion() -> None:
    unpromoted = _record(
        allowed_profiles=(registry.MAIN, registry.SHADOW),
        promotion_state=registry.REGISTERED_CHAMPION,
        main_authority=False,
    )
    loaded = registry.ComponentAuthorityRegistry(records=(unpromoted,))
    with pytest.raises(
        registry.ComponentAuthorityRegistryError,
        match="APPROVED_FOR_MAIN",
    ):
        loaded.resolve_champion(
            unpromoted.responsibility_id,
            unpromoted.regime_id,
            profile=registry.MAIN,
            required_schema_version=1,
        )

    approved = _record(
        component_id="domain.synthetic_approved_component",
        allowed_profiles=(registry.MAIN, registry.SHADOW),
        promotion_state=registry.APPROVED_FOR_MAIN,
        main_authority=True,
    )
    approved_registry = registry.ComponentAuthorityRegistry(records=(approved,))
    assert approved_registry.resolve_champion(
        approved.responsibility_id,
        approved.regime_id,
        profile=registry.MAIN,
        required_schema_version=1,
    ) is approved


def test_research_challenger_is_structurally_shadow_only() -> None:
    challenger = _record(
        component_id="domain.synthetic_challenger",
        role=registry.RESEARCH_CHALLENGER,
        promotion_state=registry.REGISTERED_CHALLENGER,
    )
    loaded = registry.ComponentAuthorityRegistry(records=(challenger,))
    assert loaded.resolve_research_challengers(
        challenger.responsibility_id,
        challenger.regime_id,
        profile=registry.SHADOW,
        required_schema_version=1,
    ) == (challenger,)

    with pytest.raises(registry.ComponentAuthorityRegistryError, match="SHADOW-only"):
        loaded.resolve_research_challengers(
            challenger.responsibility_id,
            challenger.regime_id,
            profile=registry.MAIN,
            required_schema_version=1,
        )
    with pytest.raises(registry.ComponentAuthorityRegistryError, match="SHADOW-only"):
        _record(
            component_id="domain.bad_main_challenger",
            role=registry.RESEARCH_CHALLENGER,
            allowed_profiles=(registry.MAIN, registry.SHADOW),
            promotion_state=registry.REGISTERED_CHALLENGER,
        )
    with pytest.raises(registry.ComponentAuthorityRegistryError, match="MAIN authority"):
        _record(
            component_id="domain.bad_authoritative_challenger",
            role=registry.RESEARCH_CHALLENGER,
            promotion_state=registry.REGISTERED_CHALLENGER,
            main_authority=True,
        )


def test_duplicate_or_ambiguous_authority_fails_closed() -> None:
    first = _record(component_id="domain.first_champion")
    second = _record(component_id="domain.second_champion")
    with pytest.raises(registry.ComponentAuthorityRegistryError, match="ambiguous champion"):
        registry.ComponentAuthorityRegistry(records=(first, second))

    duplicate_component = dataclasses.replace(
        first,
        responsibility_id="portfolio_optimizer",
    )
    with pytest.raises(registry.ComponentAuthorityRegistryError, match="duplicate component"):
        registry.ComponentAuthorityRegistry(records=(first, duplicate_component))


def test_unknown_component_and_incompatible_schema_fail_closed() -> None:
    champion = _record(schema_versions=(1,))
    loaded = registry.ComponentAuthorityRegistry(records=(champion,))

    with pytest.raises(registry.ComponentAuthorityRegistryError, match="unknown component"):
        loaded.resolve_component("domain.not_registered")
    with pytest.raises(registry.ComponentAuthorityRegistryError, match="schema is incompatible"):
        loaded.resolve_champion(
            champion.responsibility_id,
            champion.regime_id,
            profile=registry.SHADOW,
            required_schema_version=2,
        )
    with pytest.raises(registry.ComponentAuthorityRegistryError, match="no champion registered"):
        loaded.resolve_champion(
            "portfolio_optimizer",
            champion.regime_id,
            profile=registry.SHADOW,
            required_schema_version=1,
        )


def test_aliases_are_one_way_and_cannot_own_authority() -> None:
    champion = _record(component_id="domain.canonical_component")
    alias = registry.ComponentAuthorityAlias(
        alias_id="domain.legacy_alias",
        target_component_id=champion.component_id,
    )
    loaded = registry.ComponentAuthorityRegistry(records=(champion,), aliases=(alias,))
    assert loaded.resolve_component(alias.alias_id) is champion
    assert loaded.resolve_component(champion.component_id) is champion
    assert loaded.aliases[0].to_dict() == {
        "alias_id": alias.alias_id,
        "target_component_id": champion.component_id,
    }

    with pytest.raises(registry.ComponentAuthorityRegistryError, match="targets unknown"):
        registry.ComponentAuthorityRegistry(
            records=(champion,),
            aliases=(
                registry.ComponentAuthorityAlias(
                    alias_id="domain.bad_alias",
                    target_component_id="domain.missing_component",
                ),
            ),
        )
    with pytest.raises(registry.ComponentAuthorityRegistryError, match="shadowing"):
        registry.ComponentAuthorityRegistry(
            records=(champion,),
            aliases=(
                registry.ComponentAuthorityAlias(
                    alias_id=champion.component_id,
                    target_component_id="domain.other_component",
                ),
            ),
        )


def test_registry_objects_are_immutable_and_module_has_no_runtime_write_path() -> None:
    loaded = registry.load_default_registry()
    with pytest.raises(dataclasses.FrozenInstanceError):
        loaded.runtime_mutation_allowed = True
    with pytest.raises(dataclasses.FrozenInstanceError):
        loaded.records[0].main_authority = True

    source = (ROOT / "domain/component_authority_registry.py").read_text(encoding="utf-8")
    assert ".write_text(" not in source
    assert ".write_bytes(" not in source
    assert "os.environ" not in source
    assert "subprocess" not in source
    assert "requests" not in source
    assert "urllib" not in source


def test_json_object_key_order_is_not_authority_but_field_sets_remain_exact() -> None:
    loaded = registry.load_default_registry()
    payload = loaded.to_dict()

    reordered_records = [
        dict(reversed(list(item.items()))) for item in payload["records"]
    ]
    reordered_top = dict(reversed(list(payload.items())))
    reordered_top["records"] = reordered_records

    rebuilt = registry.ComponentAuthorityRegistry.from_dict(reordered_top)
    assert rebuilt.to_dict() == loaded.to_dict()

    raw = json.dumps(reordered_top, separators=(",", ":")).encode("utf-8")
    rebuilt_from_json = registry.ComponentAuthorityRegistry.from_json_bytes(raw)
    assert rebuilt_from_json.to_dict() == loaded.to_dict()

    alias = registry.ComponentAuthorityAlias.from_dict(
        {
            "target_component_id": "domain.synthetic_component",
            "alias_id": "domain.synthetic_alias",
        }
    )
    assert alias.to_dict() == {
        "alias_id": "domain.synthetic_alias",
        "target_component_id": "domain.synthetic_component",
    }

    bad_record = dict(reordered_records[0])
    bad_record["unexpected"] = True
    with pytest.raises(registry.ComponentAuthorityRegistryError, match="record fields drifted"):
        registry.ComponentAuthorityRecord.from_dict(bad_record)

    missing_top = dict(reordered_top)
    missing_top.pop("aliases")
    with pytest.raises(registry.ComponentAuthorityRegistryError, match="registry fields drifted"):
        registry.ComponentAuthorityRegistry.from_dict(missing_top)


def test_duplicate_json_keys_and_contract_identity_drift_are_rejected() -> None:
    raw = registry.DEFAULT_REGISTRY_PATH.read_bytes()
    loaded = registry.ComponentAuthorityRegistry.from_json_bytes(raw)
    payload = loaded.to_dict()
    payload["registry_contract_sha256"] = "0" * 64
    with pytest.raises(registry.ComponentAuthorityRegistryError, match="contract identity"):
        registry.ComponentAuthorityRegistry.from_dict(payload)

    duplicate = (
        b'{"schema_version":1,"schema_version":1,'
        b'"policy_id":"ATHENA_COMPONENT_AUTHORITY_REGISTRY_V1"}'
    )
    with pytest.raises(registry.ComponentAuthorityRegistryError, match="duplicate JSON object key"):
        registry.ComponentAuthorityRegistry.from_json_bytes(duplicate)
