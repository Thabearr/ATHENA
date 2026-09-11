from __future__ import annotations

import pytest

from domain import component_authority_registry as registry
from domain import current_shadow_canonical_core_adapter as adapter


def test_source_controlled_shadow_wrapper_aliases_resolve_to_exact_core_owners() -> None:
    adapter.clear_shadow_canonical_core_cache()
    bindings = adapter.resolve_shadow_canonical_core()
    source_registry = registry.load_default_registry()

    component_ids = {record.component_id for record in source_registry.records}
    assert set(adapter.COMPATIBILITY_ALIASES).isdisjoint(component_ids)

    for alias_id, responsibility_id in adapter.COMPATIBILITY_ALIASES.items():
        alias_record = source_registry.resolve_component(alias_id)
        owner_record = bindings.record_for(responsibility_id)
        assert alias_record == owner_record
        assert alias_record.component_id == adapter.EXPECTED_COMPONENTS[responsibility_id]
        assert alias_record.allowed_profiles == (registry.SHADOW,)
        assert alias_record.main_authority is False

    summary = adapter.canonical_core_summary()
    assert summary["compatibility_aliases"] == {
        alias_id: adapter.EXPECTED_COMPONENTS[responsibility_id]
        for alias_id, responsibility_id in adapter.COMPATIBILITY_ALIASES.items()
    }


def test_missing_source_controlled_shadow_alias_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_registry = registry.load_default_registry()
    without_aliases = registry.ComponentAuthorityRegistry(
        records=source_registry.records,
        aliases=(),
    )
    monkeypatch.setattr(registry, "load_default_registry", lambda: without_aliases)
    adapter.clear_shadow_canonical_core_cache()

    with pytest.raises(
        adapter.CurrentShadowCanonicalCoreAdapterError,
        match="compatibility alias resolution failed closed",
    ):
        adapter.resolve_shadow_canonical_core()


def test_shadow_alias_cannot_be_retargeted_to_another_registered_champion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_registry = registry.load_default_registry()
    aliases = []
    for item in source_registry.aliases:
        if item.alias_id == "domain.current_shadow_all_market_price_all":
            aliases.append(
                registry.ComponentAuthorityAlias(
                    alias_id=item.alias_id,
                    target_component_id="domain.portfolio_optimizer",
                )
            )
        else:
            aliases.append(item)
    drifted = registry.ComponentAuthorityRegistry(
        records=source_registry.records,
        aliases=tuple(aliases),
    )
    monkeypatch.setattr(registry, "load_default_registry", lambda: drifted)
    adapter.clear_shadow_canonical_core_cache()

    with pytest.raises(
        adapter.CurrentShadowCanonicalCoreAdapterError,
        match="does not resolve to the canonical-core owner",
    ):
        adapter.resolve_shadow_canonical_core()


def test_compatibility_aliases_do_not_expand_authority() -> None:
    source_registry = registry.load_default_registry()
    for alias_id in adapter.COMPATIBILITY_ALIASES:
        record = source_registry.resolve_component(alias_id)
        assert record.role == registry.CHAMPION
        assert record.promotion_state == registry.REGISTERED_CHAMPION
        assert record.allowed_profiles == (registry.SHADOW,)
        assert record.main_authority is False

    assert adapter.AUTHORITY["source_controlled_compatibility_aliases"] is True
    assert adapter.AUTHORITY["main_authority"] is False
    assert adapter.AUTHORITY["automatic_promotion"] is False
