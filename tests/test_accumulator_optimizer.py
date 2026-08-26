from __future__ import annotations

import math

import pytest

from domain._accumulator_optimizer_contracts import (
    EXPECTED_ACCUMULATOR_OPTIMIZER_CONTRACT_SHA256_BY_VERSION,
    AccumulatorOptimizationStatus,
    FragilityStatus,
    validate_accumulator_optimizer_contract,
)
from domain.accumulator_optimizer import optimize_accumulator
from domain.markets import MarketId, OutcomeId
from tests._accumulator_optimizer_helpers import NOW, fixture_input


def test_frozen_accumulator_optimizer_contract_validates():
    identities = validate_accumulator_optimizer_contract()
    assert identities["accumulator_optimizer_contract_sha256"] == (
        "7e7562c67609feaf90be7933090c40a9666ac212abfb067df9e9004e02bb128d"
    )
    assert EXPECTED_ACCUMULATOR_OPTIMIZER_CONTRACT_SHA256_BY_VERSION[1] == (
        identities["accumulator_optimizer_contract_sha256"]
    )
    assert identities["market_router_contract_sha256"] == (
        "0e4486527b060109852ab56dd76774b2d150cf8326875e44537a3bce2dc656bf"
    )


def test_single_router_selected_fixture_becomes_one_source_bound_leg(tmp_path):
    item = fixture_input(tmp_path, 1)
    result = optimize_accumulator([item], target_size=1, evaluation_time=NOW)
    assert result.status is AccumulatorOptimizationStatus.QUALIFIED_SET
    assert result.fulfilled is True
    assert result.shortfall == 0
    assert len(result.selected_legs) == 1
    leg = result.selected_legs[0]
    assert leg.fixture_id == "1001"
    assert leg.home_team == "Home 1"
    assert leg.away_team == "Away 1"
    assert leg.competition == "Competition A"
    assert leg.robust_net_expected_value > 0
    assert leg.survival_probability_floor == pytest.approx(0.60)
    assert result.route_audits[0].portfolio_admitted is True


def test_requested_size_is_target_and_router_no_bet_is_never_padded(tmp_path):
    good = fixture_input(tmp_path, 2)
    no_bet = fixture_input(
        tmp_path,
        3,
        probabilities=(0.50, 0.30, 0.20),
        competition="Competition B",
    )
    result = optimize_accumulator(
        [good, no_bet], target_size=2, evaluation_time=NOW
    )
    assert len(result.selected_legs) == 1
    assert result.shortfall == 1
    assert result.fulfilled is False
    audit = next(item for item in result.route_audits if item.fixture_id == "1003")
    assert audit.router_decision_status == "NO_BET"
    assert audit.portfolio_admitted is False
    assert audit.router_decision.selected_opportunity_id is None


def test_same_team_exposure_cap_creates_shortfall_not_padding(tmp_path):
    first = fixture_input(
        tmp_path, 4, home="Shared FC", competition="Competition A"
    )
    second = fixture_input(
        tmp_path, 5, home="Shared FC", competition="Competition B"
    )
    result = optimize_accumulator(
        [first, second], target_size=2, evaluation_time=NOW
    )
    assert len(result.selected_legs) == 1
    assert result.shortfall == 1
    assert len(result.reserve_legs) == 1
    assert any(
        reason == "TEAM_EXPOSURE_CAP:Shared FC"
        for reason in result.reserve_legs[0].reserve_reasons
    )
    assert result.exposure_summary["team_counts"]["Shared FC"] == 1


def test_competition_and_market_family_concentration_are_joint_constraints(tmp_path):
    # Target 3 -> competition cap 2 and market-family cap 2.
    first = fixture_input(tmp_path, 6, competition="Competition A")
    second = fixture_input(tmp_path, 7, competition="Competition A")
    third = fixture_input(tmp_path, 8, competition="Competition A")
    diversified = fixture_input(
        tmp_path,
        9,
        competition="Competition B",
        market=MarketId.BTTS,
        outcome=OutcomeId.YES,
        probabilities=(0.62, 0.38),
    )
    result = optimize_accumulator(
        [first, second, third, diversified], target_size=3, evaluation_time=NOW
    )
    assert len(result.selected_legs) == 3
    assert result.shortfall == 0
    assert result.exposure_summary["competition_counts"]["Competition A"] == 2
    assert result.exposure_summary["competition_counts"]["Competition B"] == 1
    assert result.exposure_summary["market_family_counts"]["MATCH_RESULT"] == 2
    assert result.exposure_summary["market_family_counts"]["BTTS"] == 1
    assert len(result.reserve_legs) == 1
    assert any(
        reason.startswith("COMPETITION_CONCENTRATION_CAP:")
        or reason.startswith("MARKET_FAMILY_CONCENTRATION_CAP:")
        for reason in result.reserve_legs[0].reserve_reasons
    )


def test_dnb_survival_keeps_push_as_survival_without_scalar_edge(tmp_path):
    dnb = fixture_input(
        tmp_path,
        10,
        competition="Competition DNB",
        market=MarketId.DRAW_NO_BET,
        outcome=OutcomeId.HOME,
        probabilities=(0.60, 0.20, 0.20),
    )
    result = optimize_accumulator([dnb], target_size=1, evaluation_time=NOW)
    leg = result.selected_legs[0]
    assert leg.robust_edge is None
    assert leg.calibrated_event_probability_floor is None
    assert leg.survival_probability_floor == pytest.approx(0.80)
    assert leg.fragility_status is FragilityStatus.NON_FRAGILE


def test_asian_handicap_survival_counts_win_half_win_and_push(tmp_path):
    asian = fixture_input(
        tmp_path,
        11,
        competition="Competition AH",
        market=MarketId.ASIAN_HANDICAP,
        outcome=OutcomeId.HOME,
        line=0.25,
        probabilities=(0.40, 0.20, 0.10, 0.10, 0.20),
    )
    result = optimize_accumulator([asian], target_size=1, evaluation_time=NOW)
    leg = result.selected_legs[0]
    assert leg.robust_edge is None
    assert leg.survival_probability_floor == pytest.approx(0.70)


def test_independence_survival_is_labelled_and_not_correlation_adjusted(tmp_path):
    first = fixture_input(tmp_path, 12, competition="Competition A")
    second = fixture_input(
        tmp_path,
        13,
        competition="Competition B",
        market=MarketId.BTTS,
        outcome=OutcomeId.YES,
        probabilities=(0.65, 0.35),
    )
    result = optimize_accumulator(
        [first, second], target_size=2, evaluation_time=NOW
    )
    expected = math.prod(
        leg.survival_probability_floor for leg in result.selected_legs
    )
    assert result.expected_slip_survival == pytest.approx(expected)
    assert "INDEPENDENCE_BASELINE" in result.expected_slip_survival_method
    assert "NOT_A_CORRELATION_ADJUSTED_JOINT_PROBABILITY" in (
        result.expected_slip_survival_method
    )
    assert result.correlation_adjusted_expected_slip_survival is None
    assert result.exposure_summary["statistical_correlation_coefficients"] is None


def test_input_order_does_not_change_portfolio_identity(tmp_path):
    first = fixture_input(tmp_path, 14, competition="Competition A")
    second = fixture_input(
        tmp_path,
        15,
        competition="Competition B",
        market=MarketId.BTTS,
        outcome=OutcomeId.YES,
        probabilities=(0.64, 0.36),
    )
    forward = optimize_accumulator(
        [first, second], target_size=2, evaluation_time=NOW
    )
    reverse = optimize_accumulator(
        [second, first], target_size=2, evaluation_time=NOW
    )
    assert forward.canonical_sha256 == reverse.canonical_sha256
    assert [item.leg_id for item in forward.selected_legs] == [
        item.leg_id for item in reverse.selected_legs
    ]


def test_no_inputs_is_normal_no_qualified_legs_with_full_shortfall():
    result = optimize_accumulator([], target_size=20, evaluation_time=NOW)
    assert result.status is AccumulatorOptimizationStatus.NO_QUALIFIED_LEGS
    assert result.selected_legs == ()
    assert result.reserve_legs == ()
    assert result.shortfall == 20
    assert result.expected_slip_survival is None
    assert result.combined_decimal_odds_product is None
