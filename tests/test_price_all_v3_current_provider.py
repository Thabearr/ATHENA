from __future__ import annotations

from datetime import timedelta

import pytest

from domain import price_all_v3_current_provider as price
from domain.markets import MarketId, OutcomeId
from domain._price_all_contracts import DevigStatus
from domain.sportybet_reviewed_canonical_market_mapping import SettlementEquivalenceAuthority
from tests._price_all_helpers import phase6_candidate
from tests.test_current_direct_provider_live_quote_mapping_consumption import (
    EVALUATION,
    EVENT,
    FIXTURE,
    _build,
    _install,
    _inventory,
    _mapped_row,
    _selection,
    _source_mapping,
)


def _candidate(
    market: MarketId = MarketId.TOTAL_GOALS,
    outcome: OutcomeId = OutcomeId.OVER,
    line: float | None = 2.5,
    probabilities: tuple[float, ...] = (0.58, 0.42),
):
    return phase6_candidate(
        market,
        outcome,
        line,
        probabilities,
        fixture_id=FIXTURE,
        event_id=EVENT,
    )[0]


def test_frozen_contract_pins_exact_pr253_and_v2_dependencies():
    identities = price.validate_price_all_v3_contract()
    assert identities["pr253_contract_sha256"] == price.PR253_CONTRACT_SHA256
    assert identities["price_all_v2_contract_sha256"] == price.PRICE_ALL_V2_CONTRACT_SHA256
    assert identities["price_all_v3_contract_sha256"] == price.calculate_price_all_v3_contract_sha256()


def test_exact_pr253_quote_is_priced_without_ranking_or_selection(monkeypatch):
    source, calls = _build(monkeypatch)
    evaluation = price.price_all_current_provider_candidates_as_of(
        (_candidate(),), source, evaluation_time=EVALUATION
    )
    result = evaluation.results[0]

    assert calls == {"mapping": 2, "inventory": 2}
    assert result.disposition is price.CurrentProviderPriceDisposition.PRICED
    assert result.quote.source_raw_sha256 == source.current_raw_sha256
    assert result.quote.current_inventory_sha256 == source.current_inventory_sha256
    assert result.source_bundle_sha256 == source.canonical_sha256
    assert result.quote_age_seconds == 60.0
    assert result.net_expected_value == pytest.approx(0.218)
    assert result.devig_status is DevigStatus.UNAVAILABLE_INCOMPLETE_PARTITION
    payload = evaluation.to_dict()
    assert "rank" not in str(payload).lower()
    assert "selected" not in payload
    assert payload["wager_placed"] is False


def test_every_candidate_gets_explicit_result_without_silent_drop(monkeypatch):
    source, _ = _build(monkeypatch)
    candidates = (
        _candidate(),
        _candidate(MarketId.BTTS, OutcomeId.YES, None, (0.52, 0.48)),
    )
    evaluation = price.price_all_current_provider_candidates_as_of(
        candidates, source, evaluation_time=EVALUATION
    )
    by_id = {item.candidate.candidate_id: item.disposition for item in evaluation.results}
    assert len(by_id) == 2
    assert by_id[candidates[0].candidate_id] is price.CurrentProviderPriceDisposition.PRICED
    assert by_id[candidates[1].candidate_id] is price.CurrentProviderPriceDisposition.UNPRICED_NO_EXACT_QUOTE


def test_future_and_stale_rechecks_fail_closed(monkeypatch):
    source, _ = _build(monkeypatch)
    with pytest.raises(price.PriceAllV3CurrentProviderError, match="predates PR253 issuance"):
        price.price_all_current_provider_candidates_as_of(
            (_candidate(),), source, evaluation_time=source.evaluation_time - timedelta(seconds=1)
        )

    stale = price.price_all_current_provider_candidates_as_of(
        (_candidate(),), source, evaluation_time=EVALUATION + timedelta(seconds=841)
    )
    assert stale.results[0].disposition is price.CurrentProviderPriceDisposition.UNPRICED_STALE_QUOTE


def test_candidate_fixture_or_event_cannot_cross_source(monkeypatch):
    source, _ = _build(monkeypatch)
    foreign = phase6_candidate(
        MarketId.TOTAL_GOALS,
        OutcomeId.OVER,
        2.5,
        (0.58, 0.42),
        fixture_id="foreign",
        event_id=EVENT,
    )[0]
    evaluation = price.price_all_current_provider_candidates_as_of(
        (foreign,), source, evaluation_time=EVALUATION
    )
    assert evaluation.results[0].disposition is price.CurrentProviderPriceDisposition.UNPRICED_SOURCE_MISMATCH


def test_complete_total_partition_devigs_only_one_exact_provider_market(monkeypatch):
    selections = (
        _selection(outcome_id="O", outcome_name="Over 2.5", odds_raw="2.10", decimal_odds=2.1),
        _selection(outcome_id="U", outcome_name="Under 2.5", odds_raw="1.80", decimal_odds=1.8),
    )
    inventory = _inventory(*selections)
    mapped = (
        _mapped_row(inventory),
        _mapped_row(
            inventory,
            outcome_id="U",
            outcome_name="Under 2.5",
            canonical_outcome=OutcomeId.UNDER,
        ),
    )
    source_mapping = _source_mapping(inventory, *mapped)
    source, _ = _build(monkeypatch, inventory=inventory, source_mapping=source_mapping)
    evaluation = price.price_all_current_provider_candidates_as_of(
        (_candidate(),), source, evaluation_time=EVALUATION
    )
    result = evaluation.results[0]
    assert result.devig_status is DevigStatus.AVAILABLE_COMPLETE_PARTITION
    assert result.overround == pytest.approx((1 / 2.1) + (1 / 1.8))


def test_separate_provider_markets_cannot_be_combined_for_devig(monkeypatch):
    selections = (
        _selection(outcome_id="O", outcome_name="Over 2.5", odds_raw="2.10", decimal_odds=2.1),
        _selection(
            market_id="different-market",
            outcome_id="U",
            outcome_name="Under 2.5",
            odds_raw="1.80",
            decimal_odds=1.8,
        ),
    )
    inventory = _inventory(*selections)
    mapped = (
        _mapped_row(inventory),
        _mapped_row(
            inventory,
            market_id="different-market",
            outcome_id="U",
            outcome_name="Under 2.5",
            canonical_outcome=OutcomeId.UNDER,
        ),
    )
    source_mapping = _source_mapping(inventory, *mapped)
    source, _ = _build(monkeypatch, inventory=inventory, source_mapping=source_mapping)
    result = price.price_all_current_provider_candidates_as_of(
        (_candidate(),), source, evaluation_time=EVALUATION
    ).results[0]
    assert result.disposition is price.CurrentProviderPriceDisposition.PRICED
    assert result.devig_status is DevigStatus.UNAVAILABLE_INCOMPLETE_PARTITION


def test_production_lane_owns_wall_clock_and_requires_live_pr253(monkeypatch):
    source, _ = _build(monkeypatch)
    monkeypatch.setattr(price, "_now_utc", lambda: EVALUATION)
    with pytest.raises(price.PriceAllV3CurrentProviderError, match="LIVE_CURRENT"):
        price.price_all_current_provider_candidates((_candidate(),), source)


def test_result_and_evaluation_are_source_reconstructable(monkeypatch):
    source, _ = _build(monkeypatch)
    evaluation = price.price_all_current_provider_candidates_as_of(
        (_candidate(),), source, evaluation_time=EVALUATION
    )
    rebuilt = price.verify_price_all_v3_current_provider_evaluation(evaluation)
    assert rebuilt.canonical_sha256 == evaluation.canonical_sha256
    with pytest.raises(price.PriceAllV3CurrentProviderError, match="builder-only"):
        price.PriceAllV3CurrentProviderEvaluation()
    with pytest.raises(price.PriceAllV3CurrentProviderError, match="builder-only"):
        price.PriceAllV3CurrentProviderResult()


@pytest.mark.parametrize(
    ("market", "line", "specifier", "probabilities", "odds", "expected_ev"),
    (
        (MarketId.DRAW_NO_BET, None, None, (0.50, 0.20, 0.30), 2.0, 0.20),
        (MarketId.ASIAN_HANDICAP, 0.25, "hcp=0.25", (0.30, 0.20, 0.10, 0.15, 0.25), 2.0, 0.075),
    ),
)
def test_full_settlement_dnb_and_ah_ev_are_not_flattened(
    monkeypatch, market, line, specifier, probabilities, odds, expected_ev
):
    selection = _selection(
        market_id=f"provider-{market.value}",
        market_name=market.value,
        specifier=specifier,
        outcome_id="provider-HOME",
        outcome_name="Home",
        odds_raw=str(odds),
        decimal_odds=odds,
    )
    inventory = _inventory(selection)
    mapped = _mapped_row(
        inventory,
        market_id=selection.market_id,
        market_name=selection.market_name,
        specifier=specifier,
        outcome_id=selection.outcome_id,
        outcome_name=selection.outcome_name,
        canonical_market=market,
        canonical_outcome=OutcomeId.HOME,
        line=line,
    )
    source, _ = _build(
        monkeypatch,
        inventory=inventory,
        source_mapping=_source_mapping(inventory, mapped),
    )
    candidate = phase6_candidate(
        market, OutcomeId.HOME, line, probabilities,
        fixture_id=FIXTURE, event_id=EVENT,
    )[0]
    result = price.price_all_current_provider_candidates_as_of(
        (candidate,), source, evaluation_time=EVALUATION
    ).results[0]
    assert result.disposition is price.CurrentProviderPriceDisposition.PRICED
    assert result.net_expected_value == pytest.approx(expected_ev)
    assert result.devig_status is DevigStatus.NOT_IDENTIFIABLE_PUSH_OR_SPLIT_SETTLEMENT


def test_unproven_settlement_equivalence_remains_explicitly_unpriced(monkeypatch):
    inventory = _inventory()
    mapped = _mapped_row(
        inventory,
        settlement=SettlementEquivalenceAuthority.PROVIDER_PROMOTION_RULES_UNPROVEN,
        bookmaker_equivalence=False,
    )
    source, _ = _build(
        monkeypatch,
        inventory=inventory,
        source_mapping=_source_mapping(inventory, mapped),
    )
    result = price.price_all_current_provider_candidates_as_of(
        (_candidate(),), source, evaluation_time=EVALUATION
    ).results[0]
    assert result.disposition is price.CurrentProviderPriceDisposition.UNPRICED_SETTLEMENT_EQUIVALENCE_UNPROVEN


def test_currently_unavailable_exact_provider_outcome_is_explicit(monkeypatch):
    selection = _selection(bookable=False)
    inventory = _inventory(selection)
    mapped = _mapped_row(inventory, bookable=False)
    source, _ = _build(
        monkeypatch,
        inventory=inventory,
        source_mapping=_source_mapping(inventory, mapped),
    )
    result = price.price_all_current_provider_candidates_as_of(
        (_candidate(),), source, evaluation_time=EVALUATION
    ).results[0]
    assert result.disposition is price.CurrentProviderPriceDisposition.UNPRICED_CURRENTLY_UNAVAILABLE
