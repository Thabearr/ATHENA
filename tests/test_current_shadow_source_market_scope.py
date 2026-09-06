from __future__ import annotations

from domain import current_all_market_shadow_probability_settlement as probability
from domain import current_sportybet_semantic_registry as provider
from domain.markets import MARKET_REGISTRY, MarketId
from domain.model_status import AnalyticalProbabilityCapability, MODEL_STATUS_REGISTRY


SOURCE_CANONICAL_MARKETS = frozenset(
    {
        MarketId.MATCH_RESULT,
        MarketId.ASIAN_HANDICAP,
        MarketId.TOTAL_GOALS,
        MarketId.DRAW_OR_OVER_2_5,
        MarketId.AWAY_OR_OVER_2_5,
        MarketId.HOME_OR_OVER_2_5,
        MarketId.HOME_WIN_EITHER_HALF,
        MarketId.AWAY_WIN_EITHER_HALF,
        MarketId.DOUBLE_CHANCE,
        MarketId.BTTS,
        MarketId.DRAW_NO_BET,
        MarketId.HOME_WIN_TO_NIL,
        MarketId.AWAY_WIN_TO_NIL,
        MarketId.MATCH_RESULT_1UP,
        MarketId.MATCH_RESULT_2UP,
    }
)


def test_current_shadow_source_scope_is_exactly_the_15_canonical_markets():
    assert len(SOURCE_CANONICAL_MARKETS) == 15
    assert frozenset(MarketId) == SOURCE_CANONICAL_MARKETS
    assert frozenset(MARKET_REGISTRY) == SOURCE_CANONICAL_MARKETS
    assert frozenset(MODEL_STATUS_REGISTRY) == SOURCE_CANONICAL_MARKETS
    assert all(
        MODEL_STATUS_REGISTRY[market].analytical_probability_capability
        is AnalyticalProbabilityCapability.AVAILABLE
        for market in SOURCE_CANONICAL_MARKETS
    )


def test_current_provider_registry_has_explicit_semantics_for_every_source_market():
    for market in SOURCE_CANONICAL_MARKETS:
        policy = provider._expected_policy(market)
        assert policy["market_ids"]
        assert policy["market_names"]
        assert policy["outcomes"]
        assert policy["settlement"] is not None


def test_mathematical_scan_preserves_all_15_source_markets():
    scan = probability.scan_fixture_all_markets(
        fixture_identity="FOTMOB:SOURCE-SCOPE",
        research_xg=probability.ResearchXGRates(
            calibrated_home=1.4,
            calibrated_away=1.1,
        ),
    )
    ids = tuple(item.market_id for item in scan.market_assessments)
    assert len(ids) == 15
    assert len(set(ids)) == 15
    assert frozenset(ids) == SOURCE_CANONICAL_MARKETS


def test_total_goals_keeps_exact_current_half_line_family_not_legacy_selector_subset():
    # The current provider/model contract is the source-bound exact half-line
    # family.  Do not regress Current Shadow to the unrelated legacy
    # engine.market_selector shortlist.
    scan = probability.scan_fixture_all_markets(
        fixture_identity="FOTMOB:TOTAL-SCOPE",
        research_xg=probability.ResearchXGRates(
            calibrated_home=1.4,
            calibrated_away=1.1,
        ),
        total_goals_lines=(0.5, 1.5, 2.5, 3.5, 4.5, 5.5),
    )
    totals = next(
        item for item in scan.market_assessments if item.market_id is MarketId.TOTAL_GOALS
    )
    assert sorted({event.line for event in totals.event_probabilities}) == [
        0.5,
        1.5,
        2.5,
        3.5,
        4.5,
        5.5,
    ]
