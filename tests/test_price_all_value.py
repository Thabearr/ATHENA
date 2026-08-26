from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import math

import pytest

from domain import sportybet_user_controlled_evidence as manual
from domain import sportybet_user_controlled_native_inventory as native
from domain._forward_calibration_contracts import ForwardCalibrationError, LINE_POLICY_ID
from domain._forward_calibration_fit import fit_forward_calibrator
from domain._forward_calibration_projection import (
    CalibrationPartition,
    CalibrationTopology,
    CalibrationUnitSpec,
    CalibrationVectorRow,
)
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
from domain.markets import MARKET_REGISTRY, MarketId, OutcomeId
from domain.price_all_value import price_all_candidates
from tests._price_all_helpers import EVENT, NOW, phase6_candidate, reviewed_quote_bundle


def candidate(market=MarketId.MATCH_RESULT, outcome=OutcomeId.HOME, line=None,
              probabilities=None):
    defaults = {
        MarketId.MATCH_RESULT: (0.55, 0.25, 0.20),
        MarketId.BTTS: (0.55, 0.45),
        MarketId.DOUBLE_CHANCE: (0.55, 0.45),
        MarketId.DRAW_NO_BET: (0.5, 0.2, 0.3),
        MarketId.TOTAL_GOALS: (0.55, 0.45),
        MarketId.ASIAN_HANDICAP: (0.3, 0.2, 0.1, 0.15, 0.25),
    }
    return phase6_candidate(
        market, outcome, line, probabilities or defaults.get(market, (0.55, 0.45))
    )[0]


def quote_bundle(tmp_path, market=MarketId.MATCH_RESULT,
                 rows=((OutcomeId.HOME, 2.0),), line=None, **kwargs):
    return reviewed_quote_bundle(tmp_path, market, tuple(rows), line, **kwargs)[-1]


def test_frozen_contract_and_independent_mapping_pin_validate():
    identities = validate_price_all_contract()
    assert identities["price_all_contract_sha256"] == EXPECTED_PRICE_ALL_CONTRACT_SHA256_BY_VERSION[1]
    assert calculate_sportybet_mapping_semantics_sha256() == EXPECTED_SPORTYBET_MAPPING_SEMANTICS_SHA256
    assert calculate_price_all_contract_sha256(
        calibration_sha="0" * 64, market_sha="1" * 64, mapping_sha="2" * 64
    ) != EXPECTED_PRICE_ALL_CONTRACT_SHA256_BY_VERSION[1]


def test_quote_price_time_and_snapshot_are_derived_only_from_verified_evidence(tmp_path):
    mapping, inventory, _evidence, _root, quotes = reviewed_quote_bundle(
        tmp_path, MarketId.MATCH_RESULT, ((OutcomeId.HOME, 2.05),))
    exact = quotes[OutcomeId.HOME]
    assert exact.decimal_odds == 2.05
    assert exact.odds_raw == "2.05"
    assert exact.observed_at == NOW
    assert exact.evidence_snapshot_sha256 == native.inventory_sha256(inventory)
    assert exact.source_raw_sha256 == inventory.source_raw_sha256
    assert exact.mapping_evidence_sha256
    assert exact.fixture_reconciliation_sha256 == mapping.source_reconciliation_receipt_sha256
    assert exact.provider_snapshot_id is None
    assert exact.observation_authority == "USER_ATTESTED_NOT_PROVIDER_TIMESTAMP"
    with pytest.raises(PriceAllError, match="issued only"):
        SportyBetExactQuote()


def test_source_evidence_age_drives_fresh_future_and_stale_dispositions(tmp_path):
    fresh = quote_bundle(tmp_path)[OutcomeId.HOME]
    assert price_all_candidates([candidate()], [fresh], evaluation_time=NOW)[0].quote_age_seconds == 0
    future = quote_bundle(tmp_path, observed_at=NOW + timedelta(seconds=1))[OutcomeId.HOME]
    assert price_all_candidates([candidate()], [future], evaluation_time=NOW)[0].disposition is PriceDisposition.UNPRICED_FUTURE_QUOTE
    stale = quote_bundle(tmp_path, observed_at=NOW - timedelta(seconds=901))[OutcomeId.HOME]
    assert price_all_candidates([candidate()], [stale], evaluation_time=NOW)[0].disposition is PriceDisposition.UNPRICED_STALE_QUOTE


def test_mapping_cannot_replay_different_or_tampered_source_evidence(tmp_path):
    mapping, _inventory, evidence, root, _quotes = reviewed_quote_bundle(
        tmp_path, MarketId.MATCH_RESULT, ((OutcomeId.HOME, 2.0),))
    raw = evidence / manual.RAW_FILENAME
    raw.write_bytes(raw.read_bytes().replace(b"2.00", b"9.99"))
    with pytest.raises(PriceAllError, match="source evidence replay failed"):
        SportyBetExactQuote.from_reviewed_mapping(
            mapping, provider_selection_sha256=mapping.mapped_selections[0].provider_selection_sha256,
            evidence_directory=evidence, allowed_evidence_root=root)


def test_candidate_authority_is_phase6_issued_not_boolean_or_arbitrary_sha():
    item, artifact, row = phase6_candidate()
    assert item.calibration_artifact_sha256 == artifact.artifact_sha256
    assert item.model_id == artifact.model_id
    assert item.probability_map == {"HOME": 0.55, "DRAW": 0.25, "AWAY": 0.20}
    with pytest.raises(PriceAllError, match="issued only"):
        CalibratedValueCandidate()
    with pytest.raises(PriceAllError, match="issued only"):
        replace(item, calibration_artifact_sha256="f" * 64)
    wrong_model = replace(row, model_id="ARBITRARY_MODEL")
    with pytest.raises(PriceAllError, match="artifact/model"):
        CalibratedValueCandidate.from_phase6_calibration(
            artifact, wrong_model, fixture_id="fx", sportybet_event_id=EVENT,
            outcome_id=OutcomeId.HOME)


def test_phase6_unsupported_specialists_and_non_half_totals_fail_closed():
    for market, outcome in (
        (MarketId.HOME_WIN_EITHER_HALF, OutcomeId.YES),
        (MarketId.MATCH_RESULT_1UP, OutcomeId.HOME),
        (MarketId.MATCH_RESULT_2UP, OutcomeId.HOME),
    ):
        with pytest.raises(StopIteration):
            phase6_candidate(market, outcome, probabilities=(0.5, 0.5))
    for line in (2.0, 2.25):
        with pytest.raises(ForwardCalibrationError, match="half-goal"):
            phase6_candidate(MarketId.TOTAL_GOALS, OutcomeId.OVER, line,
                             probabilities=(0.5, 0.5))


@pytest.mark.parametrize("market,outcome,line,components", [
    (MarketId.HOME_WIN_EITHER_HALF, OutcomeId.YES, None, ("YES", "NO")),
    (MarketId.MATCH_RESULT_1UP, OutcomeId.HOME, None, ("HOME", "DRAW", "AWAY")),
    (MarketId.MATCH_RESULT_2UP, OutcomeId.HOME, None, ("HOME", "DRAW", "AWAY")),
    (MarketId.TOTAL_GOALS, OutcomeId.OVER, 2.0, ("OVER", "UNDER")),
    (MarketId.TOTAL_GOALS, OutcomeId.OVER, 2.25, ("OVER", "UNDER")),
])
def test_even_exact_phase6_artifact_cannot_authorize_unsupported_unit(
    market, outcome, line, components,
):
    unit = CalibrationUnitSpec(
        unit_id=f"adversarial:{market.value}:{line}",
        market_id=market,
        family=MARKET_REGISTRY[market].family,
        topology=(
            CalibrationTopology.SIMPLEX_PARTITION
            if len(components) == 3 else CalibrationTopology.BINARY_PARTITION
        ),
        components=components,
        selection_outcome=None,
        line=line,
        line_origin_policy_id=LINE_POLICY_ID if line is not None else None,
    )
    fit = CalibrationVectorRow(
        match_key="fit", match_date="2024-01-02", competition_key="L1",
        season="2024", regime="MID_EVENT", model_id="POISSON_GLM_SCORE_V1",
        fold_index=1, fit_end_date="2024-01-01",
        partition=CalibrationPartition.OOF_CALIBRATION_FIT,
        unit=unit, raw_probabilities=tuple(1 / len(components) for _ in components),
        observed_index=0,
    )
    artifact = fit_forward_calibrator(
        (fit,), model_id=fit.model_id, source_training_view_sha256="a" * 64,
    )
    target = replace(
        fit,
        match_key="target",
        match_date="2026-08-26",
        fold_index=2,
        fit_end_date="2026-08-25",
        partition=CalibrationPartition.TERMINAL_HOLDOUT_EVALUATION,
    )
    with pytest.raises(PriceAllError, match="unsupported Phase 6"):
        CalibratedValueCandidate.from_phase6_calibration(
            artifact, target, fixture_id="fx", sportybet_event_id=EVENT,
            outcome_id=outcome,
        )


def test_complete_1x2_partition_devigs_and_full_vector_prices(tmp_path):
    quotes = quote_bundle(tmp_path, rows=(
        (OutcomeId.HOME, 2.0), (OutcomeId.DRAW, 4.0), (OutcomeId.AWAY, 4.0)))
    result = price_all_candidates([candidate()], quotes.values(), evaluation_time=NOW)[0]
    assert result.devig_status is DevigStatus.AVAILABLE_COMPLETE_PARTITION
    assert result.overround == pytest.approx(1.0)
    assert result.fair_probability == pytest.approx(0.5)
    assert result.net_expected_value == pytest.approx(0.55 - 0.45)


@pytest.mark.parametrize("market,outcomes,line", [
    (MarketId.BTTS, (OutcomeId.YES, OutcomeId.NO), None),
    (MarketId.TOTAL_GOALS, (OutcomeId.OVER, OutcomeId.UNDER), 2.5),
])
def test_reviewed_binary_partitions_devig(tmp_path, market, outcomes, line):
    quotes = quote_bundle(tmp_path, market, ((outcomes[0], 1.8), (outcomes[1], 2.2)), line)
    result = price_all_candidates([candidate(market, outcomes[0], line)], quotes.values(), evaluation_time=NOW)[0]
    assert result.devig_status is DevigStatus.AVAILABLE_COMPLETE_PARTITION
    assert result.fair_probability == pytest.approx((1 / 1.8) / (1 / 1.8 + 1 / 2.2))


def test_distinct_provider_markets_cannot_form_one_devig_partition(tmp_path):
    _mapping, _inventory, _evidence, _root, quotes = reviewed_quote_bundle(
        tmp_path, MarketId.MATCH_RESULT,
        ((OutcomeId.HOME, 2.0), (OutcomeId.DRAW, 4.0), (OutcomeId.AWAY, 4.0)),
        provider_market_ids={
            OutcomeId.HOME: "provider-market-A",
            OutcomeId.DRAW: "provider-market-B",
            OutcomeId.AWAY: "provider-market-B",
        })
    result = price_all_candidates([candidate()], quotes.values(), evaluation_time=NOW)[0]
    assert result.disposition is PriceDisposition.PRICED
    assert result.devig_status is DevigStatus.UNAVAILABLE_INCOMPLETE_PARTITION
    assert result.fair_probability is None


def test_distinct_evidence_and_mapping_ancestry_cannot_form_devig_partition(tmp_path):
    first = quote_bundle(
        tmp_path, rows=((OutcomeId.HOME, 2.0), (OutcomeId.DRAW, 4.0),
                        (OutcomeId.AWAY, 4.0)))
    second = quote_bundle(
        tmp_path, rows=((OutcomeId.HOME, 2.1), (OutcomeId.DRAW, 3.9),
                        (OutcomeId.AWAY, 4.1)))
    mixed = (first[OutcomeId.HOME], second[OutcomeId.DRAW], second[OutcomeId.AWAY])
    result = price_all_candidates([candidate()], mixed, evaluation_time=NOW)[0]
    assert result.disposition is PriceDisposition.PRICED
    assert result.devig_status is DevigStatus.UNAVAILABLE_CROSS_SNAPSHOT_PARTITION
    assert result.fair_probability is None


def test_double_chance_gets_ev_but_never_false_overlapping_devig(tmp_path):
    quotes = quote_bundle(tmp_path, MarketId.DOUBLE_CHANCE, (
        (OutcomeId.HOME_OR_DRAW, 1.5), (OutcomeId.DRAW_OR_AWAY, 1.5),
        (OutcomeId.HOME_OR_AWAY, 1.5)))
    result = price_all_candidates([
        candidate(MarketId.DOUBLE_CHANCE, OutcomeId.HOME_OR_DRAW)
    ], quotes.values(), evaluation_time=NOW)[0]
    assert result.disposition is PriceDisposition.PRICED
    assert result.devig_status is DevigStatus.NOT_IDENTIFIABLE_OVERLAPPING_EVENTS
    assert result.fair_probability is None


def test_dnb_and_quarter_handicap_settlement_ev(tmp_path):
    dnb_quote = quote_bundle(tmp_path, MarketId.DRAW_NO_BET,
                             ((OutcomeId.HOME, 2.1),))[OutcomeId.HOME]
    dnb = price_all_candidates([
        candidate(MarketId.DRAW_NO_BET, OutcomeId.HOME)
    ], [dnb_quote], evaluation_time=NOW)[0]
    assert dnb.net_expected_value == pytest.approx(0.5 * 1.1 - 0.3)
    assert dnb.devig_status is DevigStatus.NOT_IDENTIFIABLE_PUSH_OR_SPLIT_SETTLEMENT
    ah_quote = quote_bundle(tmp_path, MarketId.ASIAN_HANDICAP,
                            ((OutcomeId.HOME, 2.0),), -0.25)[OutcomeId.HOME]
    ah = price_all_candidates([
        candidate(MarketId.ASIAN_HANDICAP, OutcomeId.HOME, -0.25)
    ], [ah_quote], evaluation_time=NOW)[0]
    assert ah.net_expected_value == pytest.approx(0.3 + 0.1 - 0.075 - 0.25)
    assert dict(ah.settlement_returns)["HALF_WIN"] == 0.5


def test_every_candidate_has_explicit_deterministic_output_without_selection(tmp_path):
    home = candidate()
    btts = candidate(MarketId.BTTS, OutcomeId.YES)
    quote = quote_bundle(tmp_path)[OutcomeId.HOME]
    results = price_all_candidates([home, btts], [quote], evaluation_time=NOW)
    assert len(results) == 2
    assert {item.disposition for item in results} == {
        PriceDisposition.PRICED, PriceDisposition.UNPRICED_NO_EXACT_QUOTE}
    assert all("selected" not in item.to_dict() and "rank" not in item.to_dict() for item in results)
    assert [item.candidate.candidate_id for item in results] == sorted(
        item.candidate.candidate_id for item in results)


def test_duplicate_exact_source_quote_is_ambiguous(tmp_path):
    exact = quote_bundle(tmp_path)[OutcomeId.HOME]
    result = price_all_candidates([candidate()], [exact, exact], evaluation_time=NOW)[0]
    assert result.disposition is PriceDisposition.UNPRICED_AMBIGUOUS_QUOTE


def test_nan_infinity_raw_phase6_vectors_are_rejected():
    for values in ((math.nan, 0.25, 0.75), (math.inf, 0.0, 0.0)):
        with pytest.raises(ForwardCalibrationError):
            phase6_candidate(probabilities=values)
