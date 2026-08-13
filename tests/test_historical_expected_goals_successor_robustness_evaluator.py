"""Synthetic-only checks for the PR76 robustness machinery."""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

import pytest

from domain.historical_expected_goals_successor_robustness_evaluator import (
    CLUSTER_KEYS,
    HistoricalExpectedGoalsSuccessorRobustnessEvaluation,
    HistoricalExpectedGoalsSuccessorRobustnessEvaluatorError,
    RobustnessFixture,
    build_historical_expected_goals_successor_robustness_evaluation,
    canonical_historical_expected_goals_successor_robustness_evaluation_bytes,
    evaluate_successor_robustness_fixture_set,
)
from domain.historical_expected_goals_successor_robustness_protocol import successor_robustness_protocol
from domain.historical_expected_goals_successor_protocol import build_historical_expected_goals_successor_protocol


ROOT = Path(__file__).resolve().parents[1]


def _protocol():
    raw = subprocess.check_output(["git", "show", "HEAD:artifacts/research-manifests/historical-expected-goals-successor-real-corpus-receipt-v1.json"], cwd=ROOT)
    return successor_robustness_protocol(receipt_bytes=raw)


def _fitting():
    raw = subprocess.check_output(["git", "show", "HEAD:artifacts/research-manifests/historical-expected-goals-real-corpus-validation-receipt-v1.json"], cwd=ROOT)
    return build_historical_expected_goals_successor_protocol(receipt_bytes=raw).fitting


def _fixtures():
    values = []
    design = (
        (1., -.3, .1, .1, .2), (1., -.2, -.1, .4, -.1),
        (1., -.1, .2, .2, .3), (1., 0., -.2, 0., .4),
        (1., .1, .3, .3, -.2), (1., .2, -.3, .5, .1),
        (1., .3, .4, -.1, 0.), (1., .4, -.4, .2, .5),
    )
    for season_index, season in enumerate(("2020-21", "2021-22", "2022-23", "2023-24")):
        for index in range(8):
            row = design[index]
            values.append(RobustnessFixture(
                f"train-{season}-{index}", season, "B1", "TRAIN", (index + season_index) % 4,
                (index * 2 + season_index) % 3, 1.0, 1.0, 1.0, 1.0, row, row + ((index % 3) / 10,),
            ))
    for index, (season, league) in enumerate(CLUSTER_KEYS):
        # Unequal fixture counts make equal-weight cluster mistakes observable.
        for repeat in range(1 + (index % 3)):
            values.append(RobustnessFixture(f"{season}-{league}-{repeat}", season, league, "EVALUATION", repeat % 3, (repeat + 1) % 3, 1.1, 0.9, 0.8, 1.2, (1., .1, -.1, .0, .0), (1., .1, -.1, .0, .0, .1)))
    return tuple(values)


def test_paired_jackknife_is_fixture_weighted_with_unweighted_delete_center() -> None:
    result = evaluate_successor_robustness_fixture_set(protocol=_protocol(), fixtures=_fixtures())
    paired = result["paired_nll"]
    deletes = paired["delete_clusters"]
    assert len(deletes) == 22
    expected_center = math.fsum(item["delete_estimate"] for item in deletes) / 22
    expected_se = math.sqrt((21 / 22) * math.fsum((item["delete_estimate"] - expected_center) ** 2 for item in deletes))
    assert paired["jackknife_se"] == pytest.approx(expected_se)
    assert [item["identity_league"] for item in deletes[:11]] == [key[1] for key in CLUSTER_KEYS[:11]]
    assert all(item["remaining_fixture_count"] < len(_fixtures()) - 1 for item in deletes)


def test_calibration_uses_own_rates_and_freezes_boundaries() -> None:
    result = evaluate_successor_robustness_fixture_set(protocol=_protocol(), fixtures=_fixtures())
    bins = result["calibration"]["bins"]["successor_home"]
    assert [(item["lower"], item["upper"]) for item in bins] == [(0., .5), (.5, 1.), (1., 1.5), (1.5, 2.), (2., 2.5), (2.5, 3.), (3., None)]
    assert sum(item["count"] for item in bins) == len([item for item in _fixtures() if item.split == "EVALUATION"])
    assert set(result["calibration"]["successor_minus_elo"]) == {"home_absolute_overall_bias", "away_absolute_overall_bias", "home_wace", "away_wace", "home_wsce", "away_wsce"}


def test_unknown_or_missing_cluster_fails_closed() -> None:
    fixtures = list(_fixtures())
    fixtures[4] = RobustnessFixture("bad", "2024-25", "XX", "EVALUATION", 0, 0, 1., 1., 1., 1., (1., 0., 0., 0., 0.), (1., 0., 0., 0., 0., 0.))
    with pytest.raises(HistoricalExpectedGoalsSuccessorRobustnessEvaluatorError):
        evaluate_successor_robustness_fixture_set(protocol=_protocol(), fixtures=fixtures)


def test_sign_stability_rejects_zero_and_flip() -> None:
    baseline = evaluate_successor_robustness_fixture_set(protocol=_protocol(), fixtures=_fixtures())
    assert baseline["interpretation"]["home_fatigue_sign_stable_across_training_season_omissions"] is True
    zero = evaluate_successor_robustness_fixture_set(protocol=_protocol(), fixtures=_fixtures(), omission_fatigue_coefficients=((0., -1.),) * 4)
    flip = evaluate_successor_robustness_fixture_set(protocol=_protocol(), fixtures=_fixtures(), omission_fatigue_coefficients=((1., -1.), (-1., -1.), (1., -1.), (1., -1.)))
    assert zero["interpretation"]["home_fatigue_sign_stable_across_training_season_omissions"] is False
    assert flip["interpretation"]["home_fatigue_sign_stable_across_training_season_omissions"] is False


def test_no_fatigue_refit_uses_exact_five_columns_and_four_named_omissions() -> None:
    result = evaluate_successor_robustness_fixture_set(
        protocol=_protocol(), fixtures=_fixtures(), fitting=_fitting()
    )
    assert len(result["no_fatigue"]["home_fit"]["coefficients"]) == 5
    assert len(result["no_fatigue"]["away_fit"]["coefficients"]) == 5
    diagnostics = result["leave_one_training_season_refits"]
    assert [item["omitted_training_season"] for item in diagnostics] == ["2020-21", "2021-22", "2022-23", "2023-24"]
    assert all(item["training_fixture_count"] == 24 for item in diagnostics)
    assert all(len(item["home_fit"]["coefficients"]) == 6 for item in diagnostics)
    assert all(len(item["away_fit"]["coefficients"]) == 6 for item in diagnostics)


def test_canonical_wrapper_is_deterministic_and_all_false_safety() -> None:
    protocol = _protocol()
    results = evaluate_successor_robustness_fixture_set(protocol=protocol, fixtures=_fixtures())
    receipt = subprocess.check_output(["git", "show", "HEAD:artifacts/research-manifests/historical-expected-goals-successor-real-corpus-receipt-v1.json"], cwd=ROOT)
    from domain.historical_expected_goals_successor_robustness_protocol import canonical_successor_robustness_protocol_bytes
    value = build_historical_expected_goals_successor_robustness_evaluation(
        receipt_bytes=receipt, protocol=protocol,
        protocol_bytes=canonical_successor_robustness_protocol_bytes(protocol),
        source_corpus_sha256=protocol.source_corpus_sha256, results=results,
    )
    assert canonical_historical_expected_goals_successor_robustness_evaluation_bytes(value).endswith(b"\n")
    assert canonical_historical_expected_goals_successor_robustness_evaluation_bytes(value) == canonical_historical_expected_goals_successor_robustness_evaluation_bytes(value)
    assert all(flag is False for flag in value.safety.values())
