"""Research-only current Shadow Price-all for all 15 canonical markets (PR D/E).

The public current lane accepts only a builder-issued ``CurrentShadowPriceContext``.
That context source-replays PR-C current history, an exact current
FotMob<->SportyBet fixture reconciliation, and PR-B provider evidence. Callers
cannot provide raw xG, a mathematical PR-C scan, provider status strings, or a
prefiltered quote list.
"""
from __future__ import annotations

from typing import Any

from domain.markets import MARKET_REGISTRY, MarketId
from domain._all_market_shadow_types import ShadowDisposition
from domain._current_shadow_price_core import AUTHORITY_FLAGS, ShadowPriceDisposition, ShadowPriceError, _canonical_bytes
from domain._current_shadow_price_helpers import _empty_result, price_one
from domain._current_shadow_price_records import (
    ShadowPriceAllBundle,
    ShadowPriceResult,
    _issue_shadow_price_all_bundle,
)
from domain._current_shadow_quote_binding import (
    CurrentShadowPriceContext,
    build_current_shadow_exact_quotes,
    build_current_shadow_price_context,
    build_current_shadow_price_context_from_reconciliation,
    verify_current_shadow_price_context,
)


def _price_context(context: CurrentShadowPriceContext) -> ShadowPriceAllBundle:
    quotes = build_current_shadow_exact_quotes(context)
    results: list[ShadowPriceResult] = []
    seen_markets: set[MarketId] = set()

    for assessment in context.scan.market_assessments:
        seen_markets.add(assessment.market_id)
        if assessment.disposition not in {
            ShadowDisposition.ANALYTICAL_READY,
            ShadowDisposition.ANALYTICAL_READY_PROVIDER_BLOCKED,
        }:
            results.append(_empty_result(
                context=context,
                assessment=assessment,
                outcome_id=MARKET_REGISTRY[assessment.market_id].supported_outcomes[0],
                line=None,
                disposition=ShadowPriceDisposition.AUDIT_ONLY_UPSTREAM_BLOCKED,
                reason=assessment.blocker_reason or assessment.disposition.value,
                model_probability=None,
            ))
            continue
        if assessment.settlement_distributions:
            for item in assessment.settlement_distributions:
                results.append(price_one(
                    context=context,
                    assessment=assessment,
                    outcome_id=item.outcome_id,
                    line=getattr(item.settlement, "line", None),
                    model_probability=None,
                    quotes=quotes,
                ))
            continue
        for event in assessment.event_probabilities:
            results.append(price_one(
                context=context,
                assessment=assessment,
                outcome_id=event.outcome_id,
                line=event.line,
                model_probability=float(event.probability),
                quotes=quotes,
            ))

    if seen_markets != set(MarketId):
        missing = sorted(set(MarketId) - seen_markets, key=lambda item: item.value)
        raise ShadowPriceError(f"PR-C current scan missing markets: {missing}")

    ordered = tuple(sorted(results, key=lambda item: (
        item.market_id.value,
        item.outcome_id.value,
        -1.0 if item.line is None else item.line,
        item.disposition.value,
        item.quote_identity_sha256 or "",
    )))
    return _issue_shadow_price_all_bundle(
        fixture_identity=context.fixture_identity,
        evaluation_time=context.evaluation_time,
        prc_scan_sha256=context.prc_scan_sha256,
        provider_registry_sha256=context.provider_registry_sha256,
        fixture_reconciliation_sha256=context.fixture_reconciliation_sha256,
        current_mapping_rebind_sha256=context.current_mapping_rebind_sha256,
        bridge_bundle_sha256=context.bridge_bundle_sha256,
        quote_count=len(quotes),
        results=ordered,
        authority=AUTHORITY_FLAGS,
        _context=context,
    )


def price_all_shadow_fixture(context: CurrentShadowPriceContext) -> ShadowPriceAllBundle:
    verified = verify_current_shadow_price_context(context)
    return _price_context(verified)


def verify_shadow_price_all_bundle(value: Any) -> ShadowPriceAllBundle:
    if type(value) is not ShadowPriceAllBundle:
        raise ShadowPriceError("value must be exact ShadowPriceAllBundle")
    rebuilt = price_all_shadow_fixture(value._context)
    if _canonical_bytes(value.to_dict()) != _canonical_bytes(rebuilt.to_dict()):
        raise ShadowPriceError("Shadow Price-all bundle differs on exact source replay")
    return rebuilt


__all__ = [
    "CurrentShadowPriceContext",
    "ShadowPriceAllBundle",
    "build_current_shadow_price_context",
    "build_current_shadow_price_context_from_reconciliation",
    "price_all_shadow_fixture",
    "verify_shadow_price_all_bundle",
]
