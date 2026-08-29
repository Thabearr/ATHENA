"""Source-bound ShadowExactQuote issuance (PR D)."""
from __future__ import annotations

from typing import Mapping, Optional, Sequence

from domain.markets import MarketId, OutcomeId
from domain._current_shadow_price_types import (
    SOURCE_BOUND_ISSUANCE_TOKEN,
    ShadowExactQuote,
    ShadowPriceError,
    _sha256,
)
from domain.sportybet_live_event_quote_evidence import (
    SportyBetLiveEventQuoteInventory,
    SportyBetLiveEventSelection,
)


def _observation_identity(
    *,
    provider_event_id: str,
    provider_market_id: str,
    provider_specifier: Optional[str],
    provider_outcome_id: str,
    market_id: MarketId,
    outcome_id: OutcomeId,
    line: Optional[float],
    source_inventory_sha256: str,
) -> str:
    return _sha256(
        {
            "provider_event_id": provider_event_id,
            "provider_market_id": provider_market_id,
            "provider_specifier": provider_specifier,
            "provider_outcome_id": provider_outcome_id,
            "market_id": market_id.value,
            "outcome_id": outcome_id.value,
            "line": line,
            "source_inventory_sha256": source_inventory_sha256,
        }
    )


def build_shadow_exact_quote(
    *,
    inventory: SportyBetLiveEventQuoteInventory,
    selection: SportyBetLiveEventSelection,
    fixture_identity: str,
    market_id: MarketId,
    outcome_id: OutcomeId,
    line: Optional[float],
    provider_semantic_status: str,
    observation_identity_sha256: Optional[str] = None,
    registry_coverage_identity: Optional[str] = None,
) -> ShadowExactQuote:
    """Issue one source-bound quote by joining inventory selection to canonical identity.

    The selection must exist in the provided inventory with exact native identity.
    Source SHAs come only from the inventory — callers cannot supply alternate hashes.
    """

    if type(inventory) is not SportyBetLiveEventQuoteInventory:
        raise ShadowPriceError("inventory must be exact SportyBetLiveEventQuoteInventory")
    if type(selection) is not SportyBetLiveEventSelection:
        raise ShadowPriceError("selection must be exact SportyBetLiveEventSelection")
    if selection not in inventory.selections and selection.selection_identity not in {
        s.selection_identity for s in inventory.selections
    }:
        raise ShadowPriceError("selection is not present in the provided inventory")
    owned = None
    for item in inventory.selections:
        if item.selection_identity == selection.selection_identity:
            owned = item
            break
    if owned is None:
        raise ShadowPriceError("selection identity not found in inventory")
    if owned.event_id != inventory.event_id:
        raise ShadowPriceError("selection event_id does not match inventory event_id")
    if not owned.bookable:
        raise ShadowPriceError("selection is not bookable")
    inv_sha = inventory.canonical_sha256
    obs = observation_identity_sha256 or _observation_identity(
        provider_event_id=owned.event_id,
        provider_market_id=owned.market_id,
        provider_specifier=owned.specifier,
        provider_outcome_id=owned.outcome_id,
        market_id=market_id,
        outcome_id=outcome_id,
        line=line,
        source_inventory_sha256=inv_sha,
    )
    return ShadowExactQuote(
        fixture_identity=fixture_identity,
        provider_event_id=owned.event_id,
        market_id=market_id,
        outcome_id=outcome_id,
        line=line,
        provider_market_id=owned.market_id,
        provider_market_name=owned.market_name,
        provider_specifier=owned.specifier,
        provider_outcome_id=owned.outcome_id,
        provider_outcome_name=owned.outcome_name,
        decimal_odds=owned.odds_decimal,
        observed_at=inventory.observed_at,
        source_raw_sha256=inventory.source_raw_sha256,
        source_manifest_sha256=inventory.source_manifest_sha256,
        source_inventory_sha256=inv_sha,
        provider_semantic_status=provider_semantic_status,
        source_bound_issuance=SOURCE_BOUND_ISSUANCE_TOKEN,
        odds_raw=owned.odds_raw,
        observation_identity_sha256=obs,
        registry_coverage_identity=registry_coverage_identity,
        bookable=True,
    )


def build_shadow_exact_quotes_from_observations(
    *,
    inventory: SportyBetLiveEventQuoteInventory,
    fixture_identity: str,
    observations: Sequence[Mapping[str, object]],
) -> tuple[ShadowExactQuote, ...]:
    """Join PR-B-style observation maps to exact inventory selections."""

    if type(inventory) is not SportyBetLiveEventQuoteInventory:
        raise ShadowPriceError("inventory must be exact SportyBetLiveEventQuoteInventory")
    by_id = {s.selection_identity: s for s in inventory.selections}
    quotes: list[ShadowExactQuote] = []
    for obs in observations:
        market_id = obs["market_id"]
        outcome_id = obs["outcome_id"]
        if type(market_id) is not MarketId or type(outcome_id) is not OutcomeId:
            raise ShadowPriceError("observation market/outcome must be typed")
        key = (
            str(obs["provider_event_id"]) if "provider_event_id" in obs else inventory.event_id,
            str(obs["provider_market_id"]),
            obs.get("provider_specifier"),
            str(obs["provider_outcome_id"]),
        )
        if key[0] != inventory.event_id:
            raise ShadowPriceError("observation provider_event_id does not match inventory")
        for field, inv_val in (
            ("source_raw_sha256", inventory.source_raw_sha256),
            ("source_manifest_sha256", inventory.source_manifest_sha256),
        ):
            claimed = obs.get(field)
            if claimed is not None and claimed != inv_val:
                raise ShadowPriceError(f"observation {field} disagrees with inventory")
        claimed_inv = obs.get("source_inventory_sha256")
        if claimed_inv is not None and claimed_inv != inventory.canonical_sha256:
            raise ShadowPriceError("observation inventory SHA disagrees with inventory")
        selection = by_id.get(key)  # type: ignore[arg-type]
        if selection is None:
            raise ShadowPriceError(f"no inventory selection for observation key {key}")
        if selection.market_name != str(obs.get("provider_market_name", selection.market_name)):
            raise ShadowPriceError("provider_market_name mismatch")
        if selection.outcome_name != str(obs.get("provider_outcome_name", selection.outcome_name)):
            raise ShadowPriceError("provider_outcome_name mismatch")
        line = obs.get("line")
        line_f = None if line is None else float(line)  # type: ignore[arg-type]
        quotes.append(
            build_shadow_exact_quote(
                inventory=inventory,
                selection=selection,
                fixture_identity=fixture_identity,
                market_id=market_id,
                outcome_id=outcome_id,
                line=line_f,
                provider_semantic_status=str(obs["provider_semantic_status"]),
                observation_identity_sha256=obs.get("observation_identity_sha256"),  # type: ignore[arg-type]
                registry_coverage_identity=obs.get("registry_coverage_identity"),  # type: ignore[arg-type]
            )
        )
    return tuple(quotes)


__all__ = [
    "build_shadow_exact_quote",
    "build_shadow_exact_quotes_from_observations",
]
