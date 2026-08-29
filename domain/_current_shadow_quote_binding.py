"""Source-bound ShadowExactQuote issuance (PR D).

Canonical market/outcome/line/status come only from typed PR-B
ProviderSemanticObservation. Inventory supplies odds + source SHAs.
Callers cannot relabel a native selection to a different MarketId.
"""
from __future__ import annotations

from typing import Optional, Sequence

from domain.markets import MarketId, OutcomeId
from domain._current_shadow_price_core import (
    SOURCE_BOUND_ISSUANCE_TOKEN,
    ShadowPriceError,
    _sha256,
)
from domain._current_shadow_price_records import ShadowExactQuote
from domain.current_sportybet_semantic_registry import (
    CurrentSportyBetSemanticRegistry,
    ProviderCoverageRecord,
    ProviderSemanticObservation,
    ProviderSemanticStatus,
)
from domain.sportybet_live_event_quote_evidence import (
    SportyBetLiveEventQuoteInventory,
)


def _observation_identity(obs: ProviderSemanticObservation) -> str:
    return _sha256(
        {
            "provider_event_id": obs.provider_event_id,
            "provider_market_id": obs.provider_market_id,
            "provider_specifier": obs.provider_specifier,
            "provider_outcome_id": obs.provider_outcome_id,
            "market_id": obs.canonical_market_id.value,
            "outcome_id": obs.canonical_outcome_id.value,
            "line": obs.line,
            "source_inventory_sha256": obs.source_inventory_sha256,
        }
    )


def _line_float(line: Optional[str]) -> Optional[float]:
    if line is None:
        return None
    return float(line)


def build_shadow_exact_quote(
    *,
    inventory: SportyBetLiveEventQuoteInventory,
    observation: ProviderSemanticObservation,
    coverage_status: ProviderSemanticStatus,
    registry_coverage_identity: Optional[str] = None,
) -> ShadowExactQuote:
    """Issue one quote by joining inventory selection to a typed PR-B observation.

    Canonical market/outcome/line are taken exclusively from the observation.
    Native selection identity must match the observation exactly. Source SHAs
    on the observation must agree with the inventory.
    """

    if type(inventory) is not SportyBetLiveEventQuoteInventory:
        raise ShadowPriceError("inventory must be exact SportyBetLiveEventQuoteInventory")
    if type(observation) is not ProviderSemanticObservation:
        raise ShadowPriceError("observation must be exact ProviderSemanticObservation")
    if type(coverage_status) is not ProviderSemanticStatus:
        raise ShadowPriceError("coverage_status must be exact ProviderSemanticStatus")

    if observation.provider_event_id != inventory.event_id:
        raise ShadowPriceError("observation provider_event_id does not match inventory")
    if observation.source_event_detail_raw_sha256 != inventory.source_raw_sha256:
        raise ShadowPriceError("observation source_event_detail_raw_sha256 disagrees with inventory")
    if observation.source_manifest_sha256 != inventory.source_manifest_sha256:
        raise ShadowPriceError("observation source_manifest_sha256 disagrees with inventory")
    if observation.source_inventory_sha256 != inventory.canonical_sha256:
        raise ShadowPriceError("observation source_inventory_sha256 disagrees with inventory")

    key = (
        observation.provider_event_id,
        observation.provider_market_id,
        observation.provider_specifier,
        observation.provider_outcome_id,
    )
    owned = None
    for item in inventory.selections:
        if item.selection_identity == key:
            owned = item
            break
    if owned is None:
        raise ShadowPriceError("observation native selection is not present in inventory")
    if not owned.bookable or not observation.bookable:
        raise ShadowPriceError("selection/observation is not bookable")
    if owned.market_name != observation.provider_market_name:
        raise ShadowPriceError("provider_market_name mismatch")
    if owned.outcome_name != observation.provider_outcome_name:
        raise ShadowPriceError("provider_outcome_name mismatch")
    if owned.odds_decimal <= 1.0:
        raise ShadowPriceError("odds must be > 1")

    return ShadowExactQuote(
        fixture_identity=observation.fixture_identity,
        provider_event_id=owned.event_id,
        market_id=observation.canonical_market_id,
        outcome_id=observation.canonical_outcome_id,
        line=_line_float(observation.line),
        provider_market_id=owned.market_id,
        provider_market_name=owned.market_name,
        provider_specifier=owned.specifier,
        provider_outcome_id=owned.outcome_id,
        provider_outcome_name=owned.outcome_name,
        decimal_odds=owned.odds_decimal,
        observed_at=inventory.observed_at,
        source_raw_sha256=inventory.source_raw_sha256,
        source_manifest_sha256=inventory.source_manifest_sha256,
        source_inventory_sha256=inventory.canonical_sha256,
        provider_semantic_status=coverage_status.value,
        source_bound_issuance=SOURCE_BOUND_ISSUANCE_TOKEN,
        odds_raw=owned.odds_raw,
        observation_identity_sha256=_observation_identity(observation),
        registry_coverage_identity=registry_coverage_identity,
        bookable=True,
    )


def build_shadow_exact_quotes_from_registry(
    *,
    inventory: SportyBetLiveEventQuoteInventory,
    registry: CurrentSportyBetSemanticRegistry,
    fixture_identity: str,
) -> tuple[ShadowExactQuote, ...]:
    """Issue all source-bound quotes for one fixture from typed PR-B coverage."""

    if type(registry) is not CurrentSportyBetSemanticRegistry:
        raise ShadowPriceError("registry must be exact CurrentSportyBetSemanticRegistry")
    quotes: list[ShadowExactQuote] = []
    for coverage in registry.coverage:
        if type(coverage) is not ProviderCoverageRecord:
            continue
        if coverage.fixture_identity != fixture_identity:
            continue
        if coverage.provider_semantic_status not in {
            ProviderSemanticStatus.SUPPORTED,
            ProviderSemanticStatus.SUPPORTED_WITH_EXACT_LINE_POLICY,
        }:
            continue
        for obs in coverage.observations:
            if obs.fixture_identity != fixture_identity:
                continue
            if obs.provider_event_id != inventory.event_id:
                continue
            try:
                quotes.append(
                    build_shadow_exact_quote(
                        inventory=inventory,
                        observation=obs,
                        coverage_status=coverage.provider_semantic_status,
                        registry_coverage_identity=None,
                    )
                )
            except ShadowPriceError:
                continue
    return tuple(quotes)


__all__ = [
    "build_shadow_exact_quote",
    "build_shadow_exact_quotes_from_registry",
]
