from __future__ import annotations

from domain.markets import MarketId, OutcomeId, make_selection
from domain.sportybet_reviewed_canonical_market_mapping import (
    DATASET_NAME,
    REVIEW_BASIS,
    SCHEMA_VERSION,
    STATUS,
    TARGET_MARKET_IDS,
    MappedSportyBetCanonicalSelection,
    SettlementEquivalenceAuthority,
    SportyBetReviewedCanonicalMarketMapping,
)


def reviewed_mapping(market: MarketId = MarketId.MATCH_RESULT,
                     outcome: OutcomeId = OutcomeId.HOME,
                     line: float | None = None,
                     *, fixture_id: str = "fx", event_id: str = "evt",
                     selection_sha: str = "a" * 64) -> SportyBetReviewedCanonicalMarketMapping:
    selection = make_selection(market, outcome, line=line)
    specifier = None
    if market is MarketId.TOTAL_GOALS:
        specifier = f"total={line}"
    elif market is MarketId.ASIAN_HANDICAP:
        specifier = f"hcp={line}"
    early = market in {MarketId.MATCH_RESULT_1UP, MarketId.MATCH_RESULT_2UP}
    mapped = MappedSportyBetCanonicalSelection(
        provider_selection_sha256=selection_sha,
        event_id=event_id,
        provider_market_id=f"pm-{market.value}",
        provider_market_name=market.value,
        provider_specifier=specifier,
        provider_outcome_id=f"po-{outcome.value}",
        provider_selection_label=selection.selection_display_name,
        availability="AVAILABLE",
        odds_raw="1.91",
        odds_decimal="1.91",
        provider_quote_at=None,
        provider_snapshot_id=None,
        canonical_market_id=market,
        canonical_outcome_id=outcome,
        canonical_line=line,
        canonical_display_label=selection.display_label,
        canonical_selection_display_name=selection.selection_display_name,
        settlement_equivalence_authority=(
            SettlementEquivalenceAuthority.PROVIDER_PROMOTION_RULES_UNPROVEN
            if early else
            SettlementEquivalenceAuthority.REVIEWED_STANDARD_SETTLEMENT_EQUIVALENCE
        ),
        settlement_evidence_sha256=None,
        bookmaker_equivalence_authorized=not early,
        canonical_market_mapping_authorized=True,
        fresh_price_authorized=False,
        href="https://www.sportybet.com/ng/sport/football/event",
    )
    represented = tuple(item for item in TARGET_MARKET_IDS if item is market)
    missing = tuple(item for item in TARGET_MARKET_IDS if item is not market)
    safety = {
        "bet_authorized": False,
        "bookmaker_equivalence_authorized": not early,
        "booking_code_authorized": False,
        "canonical_market_mapping_authorized": True,
        "fixture_reconciliation_authorized": True,
        "fresh_price_authorized": False,
        "model_integration_authorized": False,
        "network_acquisition_authorized": False,
        "pricing_authorized": False,
        "selection_authorized": False,
        "slip_construction_authorized": False,
        "sportybet_execution_authorized": False,
    }
    return SportyBetReviewedCanonicalMarketMapping(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        provider="SportyBet",
        status=STATUS,
        review_basis=REVIEW_BASIS,
        source_reconciliation_receipt_sha256="b" * 64,
        source_native_inventory_sha256="c" * 64,
        source_event_evidence_id="evidence",
        sportybet_event_id=event_id,
        sportybet_sport_id="football",
        matched_fotmob_fixture_id=fixture_id,
        review_decisions_sha256="d" * 64,
        mapped_selections=(mapped,),
        represented_target_market_ids=represented,
        unrepresented_target_market_ids=missing,
        all_15_target_markets_represented=False,
        mapped_selection_count=1,
        unmapped_native_selection_count=0,
        safety=safety,
    )
