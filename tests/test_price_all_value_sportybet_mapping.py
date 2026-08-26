from dataclasses import replace
from datetime import datetime, timezone

import pytest

from domain._price_all_contracts import PriceAllError, SportyBetExactQuote
from domain.markets import MarketId, OutcomeId
from tests._price_all_helpers import reviewed_mapping

SHA = "c" * 64
NOW = datetime(2026, 8, 26, 12, tzinfo=timezone.utc)


def test_fresh_quote_layers_on_reviewed_mapping_without_promoting_old_inventory_price():
    mapping = reviewed_mapping(MarketId.TOTAL_GOALS, OutcomeId.OVER, 2.5,
                               fixture_id="fixture-abc", event_id="event-123")
    mapped = mapping.mapped_selections[0]
    exact = SportyBetExactQuote.from_reviewed_mapping(
        mapping, provider_selection_sha256=mapped.provider_selection_sha256,
        snapshot_id="fresh-snapshot", observed_at=NOW, decimal_odds=2.05,
    )
    assert exact.event_id == mapped.event_id
    assert exact.provider_market_id == mapped.provider_market_id
    assert exact.provider_outcome_id == mapped.provider_outcome_id
    assert exact.provider_specifier == mapped.provider_specifier
    assert exact.canonical_market_id is mapped.canonical_market_id
    assert exact.canonical_outcome_id is mapped.canonical_outcome_id
    assert exact.canonical_line == mapped.canonical_line
    assert exact.decimal_odds == 2.05
    assert exact.snapshot_id == "fresh-snapshot"
    assert mapped.provider_snapshot_id is None
    assert mapped.fresh_price_authorized is False


def test_free_form_or_missing_canonical_mapping_cannot_authorize_quote():
    with pytest.raises(PriceAllError, match="issued only"):
        SportyBetExactQuote()
    with pytest.raises(PriceAllError, match="exact reviewed SportyBet mapping"):
        SportyBetExactQuote.from_reviewed_mapping(
            {"event_id": "event-123"}, provider_selection_sha256="a" * 64,  # type: ignore[arg-type]
            snapshot_id="fresh", observed_at=NOW, decimal_odds=2.0,
        )


def test_exact_provider_and_canonical_mapping_identity_is_immutable():
    mapping = reviewed_mapping(MarketId.TOTAL_GOALS, OutcomeId.OVER, 2.5,
                               fixture_id="fixture-abc", event_id="event-123")
    exact = SportyBetExactQuote.from_reviewed_mapping(
        mapping, provider_selection_sha256="a" * 64, snapshot_id="fresh",
        observed_at=NOW, decimal_odds=2.0,
    )
    payload = exact.to_dict()
    assert payload["source"] == "SportyBet"
    assert payload["event_id"] == "event-123"
    assert payload["provider_market_id"] == "pm-TOTAL_GOALS"
    assert payload["provider_outcome_id"] == "po-OVER"
    assert payload["canonical_market_id"] == "TOTAL_GOALS"
    assert payload["canonical_outcome_id"] == "OVER"
    assert payload["canonical_line"] == 2.5
    assert len(payload["mapping_evidence_sha256"]) == 64
    with pytest.raises(PriceAllError, match="issued only"):
        replace(exact, decimal_odds=9.99)


def test_source_snapshot_and_mapping_identity_fail_closed():
    mapping = reviewed_mapping(MarketId.TOTAL_GOALS, OutcomeId.OVER, 2.5,
                               fixture_id="fixture-abc", event_id="event-123")
    common = dict(
        mapping=mapping, provider_selection_sha256="a" * 64,
        observed_at=NOW, decimal_odds=2.0,
    )
    with pytest.raises(PriceAllError, match="snapshot_id"):
        SportyBetExactQuote.from_reviewed_mapping(
            snapshot_id="", **common)
    with pytest.raises(PriceAllError, match="not uniquely present"):
        SportyBetExactQuote.from_reviewed_mapping(
            mapping, provider_selection_sha256="f" * 64,
            snapshot_id="fresh", observed_at=NOW, decimal_odds=2.0)
