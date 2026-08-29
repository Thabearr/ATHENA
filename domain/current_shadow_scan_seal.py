"""Seal PR-C current scans with CURRENT_SOURCE_BOUND lane (PR D)."""
from __future__ import annotations

from dataclasses import replace
from typing import Optional

from domain import current_fotmob_latest_durable_fresh_history as latest_history
from domain.current_all_market_shadow_probability_settlement import (
    scan_current_fixture_all_markets as _scan_current,
)
from domain.current_sportybet_semantic_registry import CurrentSportyBetSemanticRegistry
from domain._all_market_shadow_types import (
    SOURCE_LANE_CURRENT_SOURCE_BOUND,
    CurrentAllMarketShadowFixtureScan,
)


def scan_current_fixture_all_markets_sealed(
    *,
    complete_current_history: latest_history.CurrentLatestDurableFreshHistoryHandoff,
    fixture_identity: str,
    provider_semantic_registry: Optional[CurrentSportyBetSemanticRegistry] = None,
) -> CurrentAllMarketShadowFixtureScan:
    """Current source-bound scan with explicit CURRENT_SOURCE_BOUND lane seal."""
    scan = _scan_current(
        complete_current_history=complete_current_history,
        fixture_identity=fixture_identity,
        provider_semantic_registry=provider_semantic_registry,
    )
    return replace(scan, source_lane=SOURCE_LANE_CURRENT_SOURCE_BOUND)


__all__ = ["scan_current_fixture_all_markets_sealed"]
