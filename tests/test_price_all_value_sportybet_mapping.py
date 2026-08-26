from dataclasses import replace

import pytest

from domain._price_all_contracts import PriceAllError, SportyBetExactQuote
from domain.markets import MarketId, OutcomeId
from tests._price_all_helpers import reviewed_quote_bundle


def test_verified_source_replay_retains_exact_provider_and_canonical_identity(tmp_path):
    mapping, inventory, _evidence, _root, quotes = reviewed_quote_bundle(
        tmp_path, MarketId.TOTAL_GOALS, ((OutcomeId.OVER, 2.05),), 2.5)
    mapped = mapping.mapped_selections[0]
    exact = quotes[OutcomeId.OVER]
    assert exact.event_id == mapped.event_id == inventory.source_event_id
    assert exact.provider_market_id == mapped.provider_market_id
    assert exact.provider_outcome_id == mapped.provider_outcome_id
    assert exact.provider_specifier == mapped.provider_specifier
    assert exact.canonical_market_id is MarketId.TOTAL_GOALS
    assert exact.canonical_outcome_id is OutcomeId.OVER
    assert exact.canonical_line == 2.5
    assert exact.decimal_odds == 2.05
    assert exact.source_native_inventory_sha256 == mapping.source_native_inventory_sha256
    assert mapped.provider_snapshot_id is None
    assert mapped.fresh_price_authorized is False


def test_free_form_mapping_or_quote_mutation_cannot_mint_source_ancestry(tmp_path):
    with pytest.raises(PriceAllError, match="exact reviewed SportyBet mapping"):
        SportyBetExactQuote.from_reviewed_mapping(
            {"event_id": "event"}, provider_selection_sha256="a" * 64,  # type: ignore[arg-type]
            evidence_directory=tmp_path, allowed_evidence_root=tmp_path)
    exact = reviewed_quote_bundle(
        tmp_path, MarketId.MATCH_RESULT, ((OutcomeId.HOME, 2.0),))[-1][OutcomeId.HOME]
    with pytest.raises(PriceAllError, match="issued only"):
        replace(exact, decimal_odds=9.99)
    with pytest.raises(TypeError):
        SportyBetExactQuote.from_reviewed_mapping(  # type: ignore[call-arg]
            object(), provider_selection_sha256="a" * 64,
            evidence_directory=tmp_path, allowed_evidence_root=tmp_path,
            decimal_odds=9.99)


def test_mapping_inventory_sha_mismatch_fails_closed(tmp_path):
    mapping, _inventory, evidence, root, _quotes = reviewed_quote_bundle(
        tmp_path, MarketId.MATCH_RESULT, ((OutcomeId.HOME, 2.0),))
    forged = replace(mapping, source_native_inventory_sha256="f" * 64)
    with pytest.raises(PriceAllError, match="does not bind exact replayed"):
        SportyBetExactQuote.from_reviewed_mapping(
            forged, provider_selection_sha256=forged.mapped_selections[0].provider_selection_sha256,
            evidence_directory=evidence, allowed_evidence_root=root)


def test_mapping_provider_selection_sha_must_match_exact_source_bytes(tmp_path):
    mapping, _inventory, evidence, root, _quotes = reviewed_quote_bundle(
        tmp_path, MarketId.MATCH_RESULT, ((OutcomeId.HOME, 2.0),))
    mapped = replace(mapping.mapped_selections[0], provider_selection_sha256="f" * 64)
    forged = replace(mapping, mapped_selections=(mapped,))
    with pytest.raises(PriceAllError, match="differs from source evidence"):
        SportyBetExactQuote.from_reviewed_mapping(
            forged, provider_selection_sha256="f" * 64,
            evidence_directory=evidence, allowed_evidence_root=root)
