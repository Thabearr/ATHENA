"""Tests for the PR75 result-free successor robustness protocol."""

from __future__ import annotations

import dataclasses
import subprocess
from pathlib import Path

import pytest

from domain.historical_expected_goals_successor_robustness_protocol import (
    CALIBRATION_BINS,
    CLUSTER_COUNT,
    CLUSTER_KEYS,
    EVALUATION_SEASON_COUNTS,
    FATIGUE_PR31_SEMANTIC_EQUIVALENCE,
    FATIGUE_SEMANTICS,
    IDENTITY_LEAGUES,
    PR74_RECEIPT_SHA256,
    PROTOCOL_ID,
    PROTOCOL_SCOPE,
    LEAVE_ONE_TRAINING_SEASON_REMAINING_COUNTS,
    SUCCESSOR_CANDIDATE_SHA256,
    SUCCESSOR_CANDIDATE_SIZE,
    TRAINING_SEASON_COUNTS,
    HistoricalExpectedGoalsSuccessorRobustnessProtocolError,
    canonical_successor_robustness_protocol_bytes,
    revalidate_successor_robustness_protocol,
    sha256_successor_robustness_protocol,
    successor_robustness_protocol,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = "artifacts/research-manifests/historical-expected-goals-successor-real-corpus-receipt-v1.json"
PROTOCOL_SHA256 = "844bc522d7a04164d573ff4fc369565f2757ea7ade9845324a609a6a5ec566a7"


def _receipt_bytes() -> bytes:
    return subprocess.check_output(["git", "show", f"HEAD:{RECEIPT_PATH}"], cwd=REPOSITORY_ROOT)


def _protocol():
    return successor_robustness_protocol(receipt_bytes=_receipt_bytes())


def test_protocol_identity_and_ancestry_are_exact_and_canonical() -> None:
    protocol = _protocol()
    canonical = canonical_successor_robustness_protocol_bytes(protocol)

    assert (protocol.protocol_id, protocol.scope) == (PROTOCOL_ID, PROTOCOL_SCOPE)
    assert protocol.pr74_receipt_sha256 == PR74_RECEIPT_SHA256
    assert (protocol.successor_candidate_sha256, protocol.successor_candidate_size) == (
        SUCCESSOR_CANDIDATE_SHA256,
        SUCCESSOR_CANDIDATE_SIZE,
    )
    assert canonical.endswith(b"\n")
    assert sha256_successor_robustness_protocol(protocol) == PROTOCOL_SHA256
    assert canonical == canonical_successor_robustness_protocol_bytes(_protocol())


def test_primary_paired_nll_cluster_jackknife_is_frozen() -> None:
    paired = _protocol().paired_nll

    assert paired.comparator == "PR68_ELO_FALLBACK_COMPONENT"
    assert paired.fixture_difference == "SUCCESSOR_JOINT_POISSON_NLL_MINUS_LEGACY_ELO_JOINT_POISSON_NLL_SAME_FIXTURE"
    assert paired.full_population_fixture_count == 6903
    assert paired.full_estimate == "FIXTURE_WEIGHTED_ARITHMETIC_MEAN_OF_ALL_6903_PAIRED_FIXTURE_DIFFERENCES"
    assert paired.cluster_key == ("season", "identity_league")
    assert paired.cluster_keys == CLUSTER_KEYS == (
        ("2024-25", "B1"), ("2024-25", "D1"), ("2024-25", "E0"), ("2024-25", "F1"), ("2024-25", "G1"), ("2024-25", "I1"), ("2024-25", "N1"), ("2024-25", "P1"), ("2024-25", "SC0"), ("2024-25", "SP1"), ("2024-25", "T1"),
        ("2025-26", "B1"), ("2025-26", "D1"), ("2025-26", "E0"), ("2025-26", "F1"), ("2025-26", "G1"), ("2025-26", "I1"), ("2025-26", "N1"), ("2025-26", "P1"), ("2025-26", "SC0"), ("2025-26", "SP1"), ("2025-26", "T1"),
    )
    assert paired.cluster_count == CLUSTER_COUNT == 22
    assert paired.delete_cluster_estimator == "DELETE_ONE_CLUSTER_FIXTURE_WEIGHTED_MEAN_ON_REMAINING_FIXTURES"
    assert paired.delete_estimate_center == "ARITHMETIC_MEAN_OF_EXACTLY_22_DELETE_ONE_CLUSTER_ESTIMATES_UNWEIGHTED_BY_REMAINING_FIXTURE_COUNTS"
    assert paired.jackknife_standard_error == "SQRT(((K_MINUS_1)/K)*SUM((THETA_DELETE_J_MINUS_THETA_BAR)^2))"
    assert paired.interval_multiplier == 1.96
    assert paired.interval == "THETA_PLUS_MINUS_1_96_TIMES_JACKKNIFE_SE"


def test_sensitivity_calibration_and_fatigue_specs_are_exact() -> None:
    protocol = _protocol()

    assert protocol.evaluation_seasons == ("2024-25", "2025-26")
    assert protocol.identity_leagues == IDENTITY_LEAGUES
    assert protocol.leave_one_league_out == "OMIT_ONE_IDENTITY_LEAGUE_ACROSS_BOTH_EVALUATION_SEASONS_FIXTURE_WEIGHTED_MEAN"
    assert protocol.leave_one_season_out == "OMIT_ONE_EVALUATION_SEASON_FIXTURE_WEIGHTED_MEAN"
    assert protocol.calibration.bins == CALIBRATION_BINS
    assert protocol.calibration.population == "EXACT_PR74_6903_EVALUATION_FIXTURES_FOR_BOTH_MODELS"
    assert protocol.calibration.summary_metrics == ("ABSOLUTE_OVERALL_BIAS", "WACE", "WSCE")
    assert protocol.calibration.absolute_overall_bias_formula == "ABS(MEAN_PREDICTED_GOALS_MINUS_MEAN_OBSERVED_GOALS)"
    assert protocol.calibration.wace_formula == "SUM(COUNT_B_TIMES_ABS(CALIBRATION_ERROR_B))_DIVIDED_BY_6903"
    assert protocol.calibration.wsce_formula == "SUM(COUNT_B_TIMES_CALIBRATION_ERROR_B_SQUARED)_DIVIDED_BY_6903"
    assert protocol.calibration.comparison_direction == "SUCCESSOR_MINUS_ELO_NEGATIVE_IS_LOWER"
    assert protocol.fatigue.ablation_id == "NO_FATIGUE_ABLATION"
    assert protocol.fatigue.full_predictors[-1] == "fatigue"
    assert "fatigue" not in protocol.fatigue.ablation_predictors
    assert protocol.fatigue.retained_predictor_transforms == (
        "intercept=CONSTANT_ONE",
        "home_elo=(VALUE_MINUS_1500_0)_DIVIDED_BY_400_0",
        "away_elo=(VALUE_MINUS_1500_0)_DIVIDED_BY_400_0",
        "home_form=VALUE_MINUS_0_5",
        "away_form=VALUE_MINUS_0_5",
    )
    assert protocol.fatigue.leave_one_training_seasons == ("2020-21", "2021-22", "2022-23", "2023-24")
    assert protocol.fatigue.population_membership_rule == "EXACT_PR73_SUCCESSOR_ELIGIBLE_FIXTURE_SET_RECONSTRUCTED_FROM_BOUND_PR69_CORPUS"
    assert protocol.fatigue.training_season_counts == TRAINING_SEASON_COUNTS
    assert protocol.fatigue.evaluation_season_counts == EVALUATION_SEASON_COUNTS
    assert (protocol.fatigue.no_fatigue_training_fixture_count, protocol.fatigue.no_fatigue_evaluation_fixture_count) == (14130, 6903)
    assert protocol.fatigue.leave_one_training_season_remaining_counts == LEAVE_ONE_TRAINING_SEASON_REMAINING_COUNTS
    assert protocol.fatigue.fatigue_semantics == FATIGUE_SEMANTICS
    assert protocol.fatigue.fatigue_pr31_semantic_equivalence == FATIGUE_PR31_SEMANTIC_EQUIVALENCE == "UNPROVEN"
    assert protocol.fatigue.sign_stability_rule == "TRUE_IFF_EACH_OF_FOUR_OMISSION_COEFFICIENTS_HAS_SAME_STRICT_NONZERO_SIGN_AS_IMMUTABLE_PR74_FULL_MODEL_COEFFICIENT;ZERO_OR_SIGN_FLIP_IS_FALSE"


def test_protocol_is_result_free_and_authorizes_nothing_downstream() -> None:
    protocol = _protocol()

    payload = protocol.to_dict()
    assert "results" not in payload
    assert "estimate" not in payload
    assert "coefficient" not in payload
    assert all(value is False for value in protocol.safety.values())
    assert protocol.interpretation_fields == (
        "paired_elo_interval_upper_below_zero",
        "all_leave_one_league_out_deltas_negative",
        "both_leave_one_season_out_deltas_negative",
        "no_fatigue_ablation_better_than_full",
        "home_fatigue_sign_stable_across_training_season_omissions",
        "away_fatigue_sign_stable_across_training_season_omissions",
        "successor_lower_home_wace_than_same_fixture_elo",
        "successor_lower_away_wace_than_same_fixture_elo",
        "successor_lower_home_wsce_than_same_fixture_elo",
        "successor_lower_away_wsce_than_same_fixture_elo",
    )


@pytest.mark.parametrize(
    "mutation",
    (
        lambda protocol: dataclasses.replace(protocol, pr74_receipt_sha256="0" * 64),
        lambda protocol: dataclasses.replace(protocol, evaluation_seasons=("2024-25", "2026-27")),
        lambda protocol: dataclasses.replace(protocol, safety={**dict(protocol.safety), "bet_authorized": True}),
        lambda protocol: dataclasses.replace(protocol, paired_nll=dataclasses.replace(protocol.paired_nll, interval_multiplier=2.0)),
        lambda protocol: dataclasses.replace(protocol, paired_nll=dataclasses.replace(protocol.paired_nll, delete_estimate_center="WEIGHTED")),
        lambda protocol: dataclasses.replace(protocol, fatigue=dataclasses.replace(protocol.fatigue, no_fatigue_training_fixture_count=14129)),
        lambda protocol: dataclasses.replace(protocol, fatigue=dataclasses.replace(protocol.fatigue, sign_stability_rule="NONZERO_ONLY")),
    ),
)
def test_mutated_protocol_or_ancestry_fails_closed(mutation) -> None:
    with pytest.raises(HistoricalExpectedGoalsSuccessorRobustnessProtocolError):
        canonical_successor_robustness_protocol_bytes(mutation(_protocol()))


def test_full_revalidation_requires_exact_receipt_and_protocol_bytes() -> None:
    receipt = _receipt_bytes()
    protocol = successor_robustness_protocol(receipt_bytes=receipt)
    canonical = canonical_successor_robustness_protocol_bytes(protocol)

    assert revalidate_successor_robustness_protocol(
        receipt_bytes=receipt,
        protocol=protocol,
        protocol_bytes=canonical,
    ) == protocol
    with pytest.raises(HistoricalExpectedGoalsSuccessorRobustnessProtocolError):
        revalidate_successor_robustness_protocol(
            receipt_bytes=receipt + b" ", protocol=protocol, protocol_bytes=canonical
        )
    with pytest.raises(HistoricalExpectedGoalsSuccessorRobustnessProtocolError):
        revalidate_successor_robustness_protocol(
            receipt_bytes=receipt, protocol=protocol, protocol_bytes=canonical + b" "
        )
