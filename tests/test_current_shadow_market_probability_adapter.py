from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path

from domain import current_all_market_shadow_probability_settlement as prc
from domain import current_shadow_all_market_price_all as price_all
from domain.current_shadow_market_probability_adapter import (
    market_probability_bundle_from_current_shadow_fixture_scan,
)
from domain.markets import MarketId, OutcomeId
from domain._current_shadow_price_records import ShadowPriceResult
from domain._current_shadow_quote_binding import CurrentShadowPriceContext


FIXTURE = "FOTMOB:P12:PRICEALL:1001"
A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)


def _scan() -> prc.CurrentAllMarketShadowFixtureScan:
    return prc.scan_fixture_all_markets(
        fixture_identity=FIXTURE,
        research_xg=prc.ResearchXGRates(
            calibrated_home=1.7,
            calibrated_away=0.9,
            sealed_prediction_sha256=A,
            history_prefix_identity=B,
            source_fixture_identity=FIXTURE,
        ),
        kickoff_utc_iso="2026-09-12T15:00:00Z",
        total_goals_lines=(1.5, 2.5, 3.5),
        asian_handicap_home_lines=(-0.5, 0.0, 0.5),
        provider_semantic_by_market=None,
    )


def _context(scan: prc.CurrentAllMarketShadowFixtureScan) -> CurrentShadowPriceContext:
    context = object.__new__(CurrentShadowPriceContext)
    values = {
        "fixture_identity": FIXTURE,
        "scan": scan,
        "evaluation_time": NOW,
        "prc_scan_sha256": C,
        "provider_registry_sha256": D,
        "fixture_reconciliation_sha256": A,
        "current_mapping_rebind_sha256": None,
        "bridge_bundle_sha256": None,
    }
    for key, value in values.items():
        object.__setattr__(context, key, value)
    return context


def test_current_shadow_price_all_reads_probability_values_through_canonical_bundle(
    monkeypatch,
) -> None:
    scan = _scan()
    context = _context(scan)
    expected = market_probability_bundle_from_current_shadow_fixture_scan(scan)
    calls: list[object] = []

    def canonical(source_scan):
        calls.append(source_scan)
        return market_probability_bundle_from_current_shadow_fixture_scan(source_scan)

    monkeypatch.setattr(
        price_all,
        "market_probability_bundle_from_current_shadow_fixture_scan",
        canonical,
    )
    monkeypatch.setattr(price_all, "build_current_shadow_exact_quotes", lambda _context: ())

    priced = price_all._price_context(context)
    assert calls == [scan]

    match_result = expected.market(MarketId.MATCH_RESULT)
    home_probability = next(
        item.probability
        for item in match_result.event_probabilities
        if item.outcome_id is OutcomeId.HOME
    )
    home_result = next(
        item
        for item in priced.results
        if type(item) is ShadowPriceResult
        and item.market_id is MarketId.MATCH_RESULT
        and item.outcome_id is OutcomeId.HOME
    )
    assert home_result.model_probability == home_probability


def test_price_all_has_no_legacy_prediction_or_recommended_market_dependency() -> None:
    path = Path("domain/current_shadow_all_market_price_all.py")
    source = path.read_text(encoding="utf-8")
    assert "recommended_market" not in source
    assert "Prediction" not in source

    tree = ast.parse(source)
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
    assert "services.prediction_service" not in imported_modules
    assert "engine.market_selector" not in imported_modules


def test_canonical_probability_owner_does_not_import_pricing_provider_or_selection_layers() -> None:
    source = Path("domain/market_probabilities.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    forbidden_prefixes = (
        "domain.current_shadow",
        "domain.current_sportybet",
        "domain.sportybet",
        "domain.price_all",
        "domain.market_router",
        "domain.portfolio",
        "engine.market_selector",
        "services.prediction_service",
    )
    assert not any(
        module.startswith(prefix)
        for module in imported_modules
        for prefix in forbidden_prefixes
    )
