from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math

import pytest

from domain._price_all_contracts import (
    EXPECTED_PRICE_ALL_CONTRACT_SHA256_BY_VERSION,
    EXPECTED_SPORTYBET_MAPPING_SEMANTICS_SHA256,
    CalibratedValueCandidate,
    DevigStatus,
    PriceAllError,
    PriceDisposition,
    SportyBetExactQuote,
    calculate_price_all_contract_sha256,
    calculate_sportybet_mapping_semantics_sha256,
    validate_price_all_contract,
)
from domain.markets import MarketId, OutcomeId
from domain.price_all_value import price_all_candidates
from tests._price_all_helpers import reviewed_mapping

NOW = datetime(2026, 8, 26, 12, tzinfo=timezone.utc)
SHA = "a" * 64


def candidate(market=MarketId.MATCH_RESULT, outcome=OutcomeId.HOME, line=None,
              components=("WIN", "LOSS"), probabilities=(0.55, 0.45),
              candidate_id="c1", authorized=True):
    return CalibratedValueCandidate.create(
        candidate_id=candidate_id, fixture_id="fx", sportybet_event_id="evt",
        market_id=market, outcome_id=outcome, line=line, components=components,
        probabilities=probabilities, model_id="goal-score-v2",
        calibration_artifact_sha256=SHA, calibration_strategy="ISOTONIC",
        raw_probability_identity="b" * 64,
        upstream_probability_authorized=authorized,
    )


def quote(market=MarketId.MATCH_RESULT, outcome=OutcomeId.HOME, line=None,
          odds=2.0, snapshot="snap", observed=NOW):
    mapping = reviewed_mapping(market, outcome, line)
    return SportyBetExactQuote.from_reviewed_mapping(
        mapping, provider_selection_sha256="a" * 64, snapshot_id=snapshot,
        observed_at=observed, decimal_odds=odds,
    )


def test_frozen_contract_and_independent_mapping_pin_validate():
    identities = validate_price_all_contract()
    assert identities["price_all_contract_sha256"] == EXPECTED_PRICE_ALL_CONTRACT_SHA256_BY_VERSION[1]
    assert calculate_sportybet_mapping_semantics_sha256() == EXPECTED_SPORTYBET_MAPPING_SEMANTICS_SHA256
    assert calculate_price_all_contract_sha256(
        calibration_sha="0" * 64, market_sha="1" * 64, mapping_sha="2" * 64
    ) != EXPECTED_PRICE_ALL_CONTRACT_SHA256_BY_VERSION[1]


def test_quote_validation_and_age_future_stale_missing_snapshot():
    result = price_all_candidates([candidate()], [quote()], evaluation_time=NOW)[0]
    assert result.disposition is PriceDisposition.PRICED
    assert result.quote_age_seconds == 0
    assert result.quote.provider_market_id == "pm-MATCH_RESULT"
    assert price_all_candidates([candidate()], [quote(observed=NOW + timedelta(seconds=1))], evaluation_time=NOW)[0].disposition is PriceDisposition.UNPRICED_FUTURE_QUOTE
    assert price_all_candidates([candidate()], [quote(observed=NOW - timedelta(seconds=901))], evaluation_time=NOW)[0].disposition is PriceDisposition.UNPRICED_STALE_QUOTE
    with pytest.raises(PriceAllError, match="snapshot_id"):
        quote(snapshot="")
    with pytest.raises(PriceAllError, match="timezone"):
        quote(observed=datetime(2026, 8, 26, 12))
    with pytest.raises(PriceAllError, match="above 1.0"):
        quote(odds=1.0)


def test_complete_partitions_devig_and_cross_snapshot_never_mix():
    quotes = [quote(outcome=OutcomeId.HOME, odds=2.0),
              quote(outcome=OutcomeId.DRAW, odds=4.0),
              quote(outcome=OutcomeId.AWAY, odds=4.0)]
    result = price_all_candidates([candidate()], quotes, evaluation_time=NOW)[0]
    assert result.devig_status is DevigStatus.AVAILABLE_COMPLETE_PARTITION
    assert result.overround == pytest.approx(1.0)
    assert result.fair_probability == pytest.approx(0.5)
    mixed = [quotes[0], quote(outcome=OutcomeId.DRAW, odds=4.0, snapshot="other"),
             quote(outcome=OutcomeId.AWAY, odds=4.0, snapshot="other")]
    result = price_all_candidates([candidate()], mixed, evaluation_time=NOW)[0]
    assert result.devig_status is DevigStatus.UNAVAILABLE_CROSS_SNAPSHOT_PARTITION
    assert result.fair_probability is None


def test_full_calibrated_market_vector_is_preserved_and_prices_selection_settlement():
    item = candidate(components=("HOME", "DRAW", "AWAY"),
                     probabilities=(0.55, 0.25, 0.20))
    result = price_all_candidates([item], [quote(odds=2.0)], evaluation_time=NOW)[0]
    assert result.disposition is PriceDisposition.PRICED
    assert item.probability_map == {"HOME": 0.55, "DRAW": 0.25, "AWAY": 0.20}
    assert result.net_expected_value == pytest.approx(0.55 - 0.45)


@pytest.mark.parametrize("market,outcomes,line", [
    (MarketId.BTTS, (OutcomeId.YES, OutcomeId.NO), None),
    (MarketId.TOTAL_GOALS, (OutcomeId.OVER, OutcomeId.UNDER), 2.5),
])
def test_binary_complete_partitions_devig(market, outcomes, line):
    values = [quote(market, outcomes[0], line, 1.8), quote(market, outcomes[1], line, 2.2)]
    result = price_all_candidates([candidate(market, outcomes[0], line)], values, evaluation_time=NOW)[0]
    assert result.devig_status is DevigStatus.AVAILABLE_COMPLETE_PARTITION
    assert result.fair_probability == pytest.approx((1 / 1.8) / (1 / 1.8 + 1 / 2.2))


def test_double_chance_is_not_false_three_way_devig_but_still_gets_ev():
    values = [quote(MarketId.DOUBLE_CHANCE, item, odds=1.5) for item in (
        OutcomeId.HOME_OR_DRAW, OutcomeId.DRAW_OR_AWAY, OutcomeId.HOME_OR_AWAY)]
    result = price_all_candidates([
        candidate(MarketId.DOUBLE_CHANCE, OutcomeId.HOME_OR_DRAW)
    ], values, evaluation_time=NOW)[0]
    assert result.disposition is PriceDisposition.PRICED
    assert result.devig_status is DevigStatus.NOT_IDENTIFIABLE_OVERLAPPING_EVENTS
    assert result.fair_probability is None
    assert result.net_expected_value == pytest.approx(0.55 * 0.5 - 0.45)


def test_dnb_preserves_push_and_matches_hand_ev():
    item = candidate(MarketId.DRAW_NO_BET, OutcomeId.HOME, components=("WIN", "PUSH", "LOSS"),
                     probabilities=(0.5, 0.2, 0.3))
    result = price_all_candidates([item], [quote(MarketId.DRAW_NO_BET, OutcomeId.HOME, odds=2.1)], evaluation_time=NOW)[0]
    assert result.net_expected_value == pytest.approx(0.5 * 1.1 - 0.3)
    assert result.expected_return_multiplier == pytest.approx(1.25)
    assert result.devig_status is DevigStatus.NOT_IDENTIFIABLE_PUSH_OR_SPLIT_SETTLEMENT


def test_asian_handicap_full_quarter_settlement_ev():
    item = candidate(MarketId.ASIAN_HANDICAP, OutcomeId.HOME, -0.25,
        ("WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS"),
        (0.3, 0.2, 0.1, 0.15, 0.25))
    result = price_all_candidates([item], [quote(MarketId.ASIAN_HANDICAP, OutcomeId.HOME, -0.25, 2.0)], evaluation_time=NOW)[0]
    assert result.net_expected_value == pytest.approx(0.3 + 0.1 - 0.075 - 0.25)
    assert dict(result.settlement_returns)["HALF_WIN"] == pytest.approx(0.5)
    assert dict(result.settlement_returns)["HALF_LOSS"] == -0.5


def test_integer_and_quarter_totals_preserve_push_and_split_settlement_without_false_devig():
    integer = candidate(MarketId.TOTAL_GOALS, OutcomeId.OVER, 2.0,
                        ("WIN", "PUSH", "LOSS"), (0.4, 0.2, 0.4))
    integer_quotes = [quote(MarketId.TOTAL_GOALS, OutcomeId.OVER, 2.0, 2.1),
                      quote(MarketId.TOTAL_GOALS, OutcomeId.UNDER, 2.0, 1.8)]
    result = price_all_candidates([integer], integer_quotes, evaluation_time=NOW)[0]
    assert result.net_expected_value == pytest.approx(0.4 * 1.1 - 0.4)
    assert result.devig_status is DevigStatus.NOT_IDENTIFIABLE_PUSH_OR_SPLIT_SETTLEMENT
    quarter = candidate(MarketId.TOTAL_GOALS, OutcomeId.OVER, 2.25,
        ("WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS"),
        (0.3, 0.2, 0.0, 0.2, 0.3))
    result = price_all_candidates(
        [quarter], [quote(MarketId.TOTAL_GOALS, OutcomeId.OVER, 2.25, 2.0)],
        evaluation_time=NOW)[0]
    assert result.net_expected_value == pytest.approx(0.3 + 0.1 - 0.1 - 0.3)
    assert result.devig_status is DevigStatus.NOT_IDENTIFIABLE_PUSH_OR_SPLIT_SETTLEMENT


def test_incomplete_distribution_and_exact_line_mismatch_fail_closed():
    malformed = candidate(MarketId.DRAW_NO_BET, OutcomeId.HOME)
    result = price_all_candidates([malformed], [quote(MarketId.DRAW_NO_BET, OutcomeId.HOME)], evaluation_time=NOW)[0]
    assert result.disposition is PriceDisposition.BLOCKED_SETTLEMENT_DISTRIBUTION_INCOMPLETE
    item = candidate(MarketId.TOTAL_GOALS, OutcomeId.OVER, 2.5)
    result = price_all_candidates([item], [quote(MarketId.TOTAL_GOALS, OutcomeId.OVER, 3.5)], evaluation_time=NOW)[0]
    assert result.disposition is PriceDisposition.UNPRICED_NO_EXACT_QUOTE


def test_every_candidate_has_deterministic_explicit_output_and_no_selection_fields():
    values = [candidate(candidate_id="z"), candidate(MarketId.BTTS, OutcomeId.YES, candidate_id="a")]
    results = price_all_candidates(values, [quote()], evaluation_time=NOW)
    assert [item.candidate.candidate_id for item in results] == ["a", "z"]
    assert results[0].disposition is PriceDisposition.UNPRICED_NO_EXACT_QUOTE
    assert results[1].disposition is PriceDisposition.PRICED
    assert "selected" not in results[1].to_dict()
    assert "rank" not in results[1].to_dict()
    assert results[1].canonical_sha256 == hashlib_sha(results[1].canonical_bytes())


def hashlib_sha(value):
    import hashlib
    return hashlib.sha256(value).hexdigest()


def test_duplicates_are_ambiguous_and_specialists_remain_blocked():
    q = quote()
    assert price_all_candidates([candidate()], [q, q], evaluation_time=NOW)[0].disposition is PriceDisposition.UNPRICED_AMBIGUOUS_QUOTE
    for market in (MarketId.HOME_WIN_EITHER_HALF, MarketId.MATCH_RESULT_1UP, MarketId.MATCH_RESULT_2UP):
        outcome = OutcomeId.YES if market is MarketId.HOME_WIN_EITHER_HALF else OutcomeId.HOME
        result = price_all_candidates([candidate(market, outcome)], [quote(market, outcome)], evaluation_time=NOW)[0]
        assert result.disposition is PriceDisposition.BLOCKED_UPSTREAM_PROBABILITY_UNAVAILABLE


def test_probability_values_reject_nan_infinity_and_nonunit_sum():
    for values in ((math.nan, 0.5), (math.inf, 0.0), (0.2, 0.2)):
        with pytest.raises(PriceAllError):
            candidate(probabilities=values)
