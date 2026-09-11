"""P2.1 Current Shadow compatibility adapter into the shared canonical core.

Current Shadow still carries reviewed Shadow-specific source/context and receipt
shapes. P2.1 must not rewrite those shapes or the football/value/portfolio
formulas merely to migrate ownership. This adapter therefore resolves the
source-controlled SHADOW canonical-core binding first, proves the exact
registered owner for each migrated responsibility, proves that every retained
Shadow wrapper is a source-controlled one-way alias to that same owner, and only
then delegates to the already-reviewed compatibility implementation.

The adapter is intentionally one-way: Current Shadow may depend on this module,
but canonical modules never import Current Shadow orchestration. It performs no
provider acquisition, model inference, share-code transport, login, wallet,
staking or wagering. The legacy wrappers remain retained implementation
evidence until later differential-removal work; their registry aliases cannot
independently decide authority.
"""
from __future__ import annotations

from functools import lru_cache
from types import MappingProxyType
from typing import Any

from domain import canonical_core as _core
from domain import component_authority_registry as _registry
from domain import current_shadow_all_market_portfolio as _legacy_portfolio
from domain import current_shadow_all_market_price_all as _legacy_price
from domain import current_shadow_all_market_router as _legacy_router
from domain import run_contracts as _run_contracts
from domain._current_shadow_price_core import ShadowPriceError


POLICY_ID = "CURRENT_SHADOW_SHARED_CANONICAL_CORE_P2_1_COMPATIBILITY_V1"
REGIME_ID = _core.CURRENT_SPORTYBET_PROVIDER
EXPECTED_COMPONENTS = MappingProxyType(
    {
        "provider_market_semantics": "domain.provider_market_semantics",
        "price_all_and_de_vig": "domain.price_all",
        "market_router": "domain.market_router_canonical_adapter",
        "portfolio_optimizer": "domain.portfolio_optimizer",
        "delivery_share_code_transport": "domain.sportybet_share_code",
    }
)
COMPATIBILITY_ALIASES = MappingProxyType(
    {
        "domain.current_shadow_all_market_portfolio": "portfolio_optimizer",
        "domain.current_shadow_all_market_price_all": "price_all_and_de_vig",
        "domain.current_shadow_all_market_router": "market_router",
    }
)

AUTHORITY = MappingProxyType(
    {
        "shadow_profile_migration": True,
        "canonical_core_resolution": True,
        "canonical_owner_enforcement": True,
        "source_controlled_compatibility_aliases": True,
        "compatibility_delegation": True,
        "provider_acquisition": False,
        "football_probability_generation": False,
        "calibration": False,
        "main_authority": False,
        "automatic_promotion": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "bet": False,
        "wager_placed": False,
    }
)


class CurrentShadowCanonicalCoreAdapterError(ValueError):
    """The SHADOW profile could not prove its reviewed canonical-core binding."""


def _manifest() -> _run_contracts.AuthorityManifest:
    return _run_contracts.AuthorityManifest(
        authority_profile="SHADOW",
        mode="research_shadow",
        provider_acquisition=False,
        share_code_generation=True,
        login=False,
        cookies=False,
        wallet=False,
        staking=False,
        wager=False,
    )


def _validate_compatibility_aliases(bindings: _core.CanonicalCoreBindings) -> None:
    """Require each retained Shadow wrapper to alias the resolved champion.

    P1.7 aliases are source-controlled compatibility names, not authority
    records. Requiring alias resolution to return the exact record already held
    by the P2.0 core prevents a retained wrapper from becoming a second champion
    merely because P2.1 still needs its payload/receipt implementation.
    """

    try:
        registry = _registry.load_default_registry()
        for alias_id, responsibility_id in COMPATIBILITY_ALIASES.items():
            alias_record = registry.resolve_component(alias_id)
            owner_record = bindings.record_for(responsibility_id)
            if alias_record != owner_record:
                raise CurrentShadowCanonicalCoreAdapterError(
                    f"Current Shadow compatibility alias {alias_id} does not resolve "
                    "to the canonical-core owner"
                )
            if alias_record.component_id != EXPECTED_COMPONENTS[responsibility_id]:
                raise CurrentShadowCanonicalCoreAdapterError(
                    f"Current Shadow compatibility alias {alias_id} target drifted"
                )
    except _registry.ComponentAuthorityRegistryError as exc:
        raise CurrentShadowCanonicalCoreAdapterError(
            "Current Shadow compatibility alias resolution failed closed"
        ) from exc


@lru_cache(maxsize=1)
def resolve_shadow_canonical_core() -> _core.CanonicalCoreBindings:
    """Resolve exactly the reviewed source-controlled SHADOW champion set."""

    try:
        bindings = _core.resolve_canonical_core(_manifest(), regime_id=REGIME_ID)
    except Exception as exc:
        raise CurrentShadowCanonicalCoreAdapterError(
            "Current Shadow canonical-core resolution failed closed"
        ) from exc
    if bindings.authority_profile != "SHADOW":
        raise CurrentShadowCanonicalCoreAdapterError(
            "Current Shadow canonical-core profile drifted"
        )
    if bindings.share_code_generation is not True:
        raise CurrentShadowCanonicalCoreAdapterError(
            "Current Shadow canonical-core delivery capability drifted"
        )
    actual = {
        record.responsibility_id: record.component_id for record in bindings.records
    }
    if actual != dict(EXPECTED_COMPONENTS):
        raise CurrentShadowCanonicalCoreAdapterError(
            "Current Shadow canonical-core component set drifted"
        )
    if any(
        record.allowed_profiles != ("SHADOW",) or record.main_authority is not False
        for record in bindings.records
    ):
        raise CurrentShadowCanonicalCoreAdapterError(
            "Current Shadow canonical-core authority escaped SHADOW-only state"
        )
    _validate_compatibility_aliases(bindings)
    return bindings


def clear_shadow_canonical_core_cache() -> None:
    """Test/process-reload hook; never mutates the source-controlled registry."""

    resolve_shadow_canonical_core.cache_clear()


def canonical_core_summary() -> MappingProxyType:
    bindings = resolve_shadow_canonical_core()
    return MappingProxyType(
        {
            "policy_id": POLICY_ID,
            "canonical_core_policy_id": bindings.policy_id,
            "canonical_core_sha256": bindings.canonical_sha256,
            "registry_canonical_sha256": bindings.registry_canonical_sha256,
            "authority_profile": bindings.authority_profile,
            "component_ids": dict(EXPECTED_COMPONENTS),
            "compatibility_aliases": {
                alias_id: EXPECTED_COMPONENTS[responsibility_id]
                for alias_id, responsibility_id in COMPATIBILITY_ALIASES.items()
            },
            "main_authority": False,
            "wager_placed": False,
        }
    )


def _require(responsibility_id: str) -> None:
    expected = EXPECTED_COMPONENTS[responsibility_id]
    try:
        record = resolve_shadow_canonical_core().record_for(responsibility_id)
    except (KeyError, _core.CanonicalCoreError, CurrentShadowCanonicalCoreAdapterError) as exc:
        raise CurrentShadowCanonicalCoreAdapterError(
            f"Current Shadow canonical responsibility {responsibility_id} is unavailable"
        ) from exc
    if (
        record.component_id != expected
        or record.allowed_profiles != ("SHADOW",)
        or record.main_authority is not False
    ):
        raise CurrentShadowCanonicalCoreAdapterError(
            f"Current Shadow canonical responsibility {responsibility_id} drifted"
        )


def _require_price_or_shadow_error() -> None:
    try:
        _require("price_all_and_de_vig")
    except CurrentShadowCanonicalCoreAdapterError as exc:
        raise ShadowPriceError("canonical Price-all owner resolution failed") from exc


def _require_router_or_shadow_error() -> None:
    try:
        _require("market_router")
    except CurrentShadowCanonicalCoreAdapterError as exc:
        raise ShadowPriceError("canonical Router owner resolution failed") from exc


def _require_portfolio_or_legacy_error() -> None:
    try:
        _require("portfolio_optimizer")
    except CurrentShadowCanonicalCoreAdapterError as exc:
        raise _legacy_portfolio.CurrentShadowPortfolioError(
            "canonical Portfolio owner resolution failed"
        ) from exc


# Retain the exact transitional types so existing timeout/reprice code can keep
# replaying old receipts while the ownership boundary moves to the shared core.
CurrentShadowPriceContext = _legacy_price.CurrentShadowPriceContext
ShadowPriceAllBundle = _legacy_price.ShadowPriceAllBundle
ShadowMarketRouterDecision = _legacy_router.ShadowMarketRouterDecision
ShadowPortfolioRouterInput = _legacy_portfolio.ShadowPortfolioRouterInput
ShadowPortfolioOptimization = _legacy_portfolio.ShadowPortfolioOptimization
CurrentShadowPortfolioError = _legacy_portfolio.CurrentShadowPortfolioError
MAX_QUOTE_AGE_SECONDS = _legacy_portfolio.MAX_QUOTE_AGE_SECONDS
reconciliation = _legacy_portfolio.reconciliation


def build_current_shadow_price_context(*args: Any, **kwargs: Any) -> Any:
    # Source/context construction remains a SHADOW orchestration concern in P2.1.
    return _legacy_price.build_current_shadow_price_context(*args, **kwargs)


def build_current_shadow_price_context_from_reconciliation(*args: Any, **kwargs: Any) -> Any:
    # Source/context construction remains a SHADOW orchestration concern in P2.1.
    return _legacy_price.build_current_shadow_price_context_from_reconciliation(
        *args, **kwargs
    )


def verify_current_shadow_price_context(value: Any) -> Any:
    return _legacy_price.verify_current_shadow_price_context(value)


def _with_price_context_verifier(callable_obj: Any, *args: Any, **kwargs: Any) -> Any:
    """Honor the worker's exact price-context verification reuse seam.

    Before P2.1 the runner exported the legacy Price-all module directly, so a
    worker monkeypatch of ``runner.price_module.verify_current_shadow_price_context``
    also changed the verifier used internally by ``price_all_shadow_fixture``.
    The compatibility adapter preserves that behavior by installing the current
    adapter-level verifier only for the duration of the delegated call.
    """

    original = _legacy_price.verify_current_shadow_price_context
    _legacy_price.verify_current_shadow_price_context = verify_current_shadow_price_context
    try:
        return callable_obj(*args, **kwargs)
    finally:
        _legacy_price.verify_current_shadow_price_context = original


def price_all_shadow_fixture(context: Any) -> Any:
    """Compatibility execution guarded by the canonical Price-all owner."""

    _require_price_or_shadow_error()
    return _with_price_context_verifier(_legacy_price.price_all_shadow_fixture, context)


def verify_shadow_price_all_bundle(value: Any) -> Any:
    _require_price_or_shadow_error()
    return _with_price_context_verifier(_legacy_price.verify_shadow_price_all_bundle, value)


def route_shadow_price_results(value: Any) -> Any:
    """Compatibility execution guarded by the canonical Router owner."""

    _require_router_or_shadow_error()
    return _legacy_router.route_shadow_price_results(value)


def _with_portfolio_reconciliation(callable_obj: Any, *args: Any, **kwargs: Any) -> Any:
    """Honor the existing worker's bounded reconciliation monkeypatch seam."""

    original = _legacy_portfolio.reconciliation
    _legacy_portfolio.reconciliation = reconciliation
    try:
        return callable_obj(*args, **kwargs)
    finally:
        _legacy_portfolio.reconciliation = original


def build_shadow_portfolio_router_input(*args: Any, **kwargs: Any) -> Any:
    _require_portfolio_or_legacy_error()
    return _with_portfolio_reconciliation(
        _legacy_portfolio.build_shadow_portfolio_router_input, *args, **kwargs
    )


def verify_shadow_portfolio_router_input(value: Any) -> Any:
    _require_portfolio_or_legacy_error()
    return _with_portfolio_reconciliation(
        _legacy_portfolio.verify_shadow_portfolio_router_input, value
    )


def optimize_shadow_portfolio(*args: Any, **kwargs: Any) -> Any:
    """Compatibility execution guarded by the canonical Portfolio owner."""

    _require_portfolio_or_legacy_error()
    return _with_portfolio_reconciliation(
        _legacy_portfolio.optimize_shadow_portfolio, *args, **kwargs
    )


def _diagnostics(*args: Any, **kwargs: Any) -> Any:
    # Diagnostics are descriptive only; keep exact existing serialization and
    # do not repeatedly resolve Git-bound component identities per fixture.
    return _legacy_portfolio._diagnostics(*args, **kwargs)


__all__ = [
    "AUTHORITY",
    "COMPATIBILITY_ALIASES",
    "CurrentShadowCanonicalCoreAdapterError",
    "CurrentShadowPortfolioError",
    "CurrentShadowPriceContext",
    "EXPECTED_COMPONENTS",
    "MAX_QUOTE_AGE_SECONDS",
    "POLICY_ID",
    "REGIME_ID",
    "ShadowMarketRouterDecision",
    "ShadowPortfolioOptimization",
    "ShadowPortfolioRouterInput",
    "ShadowPriceAllBundle",
    "_diagnostics",
    "build_current_shadow_price_context",
    "build_current_shadow_price_context_from_reconciliation",
    "build_shadow_portfolio_router_input",
    "canonical_core_summary",
    "clear_shadow_canonical_core_cache",
    "optimize_shadow_portfolio",
    "price_all_shadow_fixture",
    "reconciliation",
    "resolve_shadow_canonical_core",
    "route_shadow_price_results",
    "verify_current_shadow_price_context",
    "verify_shadow_portfolio_router_input",
    "verify_shadow_price_all_bundle",
]
