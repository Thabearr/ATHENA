"""Synthetic-only checks for the PR76 robustness machinery."""

from __future__ import annotations

import math
import subprocess
from pathlib import Path
import datetime
import ast
import dataclasses
import json

import pytest

from domain.historical_expected_goals_successor_robustness_evaluator import (
    CLUSTER_KEYS,
    HistoricalExpectedGoalsSuccessorRobustnessEvaluation,
    HistoricalExpectedGoalsSuccessorRobustnessEvaluatorError,
    RobustnessFixture,
    build_historical_expected_goals_successor_robustness_evaluation,
    canonical_historical_expected_goals_successor_robustness_evaluation_bytes,
    evaluate_successor_robustness_fixture_set,
    revalidate_historical_expected_goals_successor_robustness_evaluation,
    _sign_stable,
    _calibration,
)
from domain.historical_expected_goals_successor_robustness_protocol import successor_robustness_protocol
from domain.historical_expected_goals_successor_protocol import build_historical_expected_goals_successor_protocol
from domain.historical_expected_goals_successor_candidate import fit_historical_expected_goals_successor_fixture_set
from domain.historical_model_feature_replay_candidate import (
    SOURCE, SOURCE_LOCAL_TIMEZONE_UNRESOLVED, HistoricalFeatureReplayStatus,
    HistoricalReplayFeatureValue, HistoricalReplayFixture,
)
from domain.fixture_model_features import ModelFeatureId


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
    evaluation = [item for item in _fixtures() if item.split == "EVALUATION"]
    def nll(fixture, home, away):
        return (home - fixture.home_goals * math.log(home) + math.lgamma(fixture.home_goals + 1) + away - fixture.away_goals * math.log(away) + math.lgamma(fixture.away_goals + 1))
    diffs = {item.fixture_identifier: nll(item, item.successor_home_rate, item.successor_away_rate) - nll(item, item.elo_home_rate, item.elo_away_rate) for item in evaluation}
    expected_theta = math.fsum(diffs.values()) / len(diffs)
    expected_deletes = []
    for key in CLUSTER_KEYS:
        remaining = [diffs[item.fixture_identifier] for item in evaluation if (item.season, item.identity_league) != key]
        expected_deletes.append(math.fsum(remaining) / len(remaining))
    expected_center = math.fsum(expected_deletes) / 22
    expected_se = math.sqrt((21 / 22) * math.fsum((item["delete_estimate"] - expected_center) ** 2 for item in deletes))
    assert paired["full_estimate"] == pytest.approx(expected_theta)
    assert [item["delete_estimate"] for item in deletes] == pytest.approx(expected_deletes)
    assert paired["jackknife_se"] == pytest.approx(expected_se)
    assert [item["identity_league"] for item in deletes[:11]] == [key[1] for key in CLUSTER_KEYS[:11]]
    assert all(item["remaining_fixture_count"] < len(_fixtures()) - 1 for item in deletes)


def test_calibration_uses_own_rates_and_freezes_boundaries() -> None:
    result = evaluate_successor_robustness_fixture_set(protocol=_protocol(), fixtures=_fixtures())
    bins = result["calibration"]["bins"]["successor_home"]
    assert [(item["lower"], item["upper"]) for item in bins] == [(0., .5), (.5, 1.), (1., 1.5), (1.5, 2.), (2., 2.5), (2.5, 3.), (3., None)]
    assert sum(item["count"] for item in bins) == len([item for item in _fixtures() if item.split == "EVALUATION"])
    assert set(result["calibration"]["successor_minus_elo"]) == {"home_absolute_overall_bias", "away_absolute_overall_bias", "home_wace", "away_wace", "home_wsce", "away_wsce"}


def test_calibration_boundaries_are_lower_inclusive_and_model_specific() -> None:
    rates = (.499, .5, .999, 1., 1.499, 1.5, 1.999, 2., 2.499, 2.5, 2.999, 3.)
    values = []
    for index, rate in enumerate(rates):
        values.append(RobustnessFixture(
            f"boundary-{index}", "2024-25", "B1", "EVALUATION", 1, 1,
                rate, 1., 1., .25, (1., 0., 0., 0., 0.), (1., 0., 0., 0., 0., 0.),
        ))
    values.extend(item for item in _fixtures() if item.split == "TRAIN")
    # Supply one neutral record per remaining cluster so only boundary records affect counts.
    for season, league in CLUSTER_KEYS:
        if (season, league) != ("2024-25", "B1"):
            values.append(RobustnessFixture(f"cluster-{season}-{league}", season, league, "EVALUATION", 1, 1, 1.1, 1., 1., 1.1, (1., 0., 0., 0., 0.), (1., 0., 0., 0., 0., 0.)))
    values.append(RobustnessFixture("boundary-other-season", "2025-26", "B1", "EVALUATION", 1, 1, .7, 1., 1., .7, (1., 0., 0., 0., 0.), (1., 0., 0., 0., 0., 0.)))
    result = evaluate_successor_robustness_fixture_set(protocol=_protocol(), fixtures=tuple(values))
    successor = result["calibration"]["bins"]["successor_home"]
    elo = result["calibration"]["bins"]["elo_away"]
    # Boundary records themselves occupy 1 / 2 / 2 / 2 / 2 / 2 / 1 bins;
    # neutral cluster-completeness records all fall into [1.0, 1.5).
    assert [row["count"] for row in successor] == [1, 3, 23, 2, 2, 2, 1]
    # ELO-away receives the same population but assigns it through its own rates.
    assert sum(row["count"] for row in elo) == sum(row["count"] for row in successor)
    assert elo[2]["count"] != successor[2]["count"]
    elo_boundary = tuple(
        RobustnessFixture(
            f"elo-boundary-{index}", "2024-25", "B1", "EVALUATION", 1, 1,
            .25, 1., 1., rate, (1., 0., 0., 0., 0.), (1., 0., 0., 0., 0., 0.),
        )
        for index, rate in enumerate(rates)
    )
    assert [item["count"] for item in _calibration(elo_boundary, model="elo", side="away")] == [1, 2, 2, 2, 2, 2, 1]


def test_unknown_or_missing_cluster_fails_closed() -> None:
    fixtures = list(_fixtures())
    fixtures[4] = RobustnessFixture("bad", "2024-25", "XX", "EVALUATION", 0, 0, 1., 1., 1., 1., (1., 0., 0., 0., 0.), (1., 0., 0., 0., 0., 0.))
    with pytest.raises(HistoricalExpectedGoalsSuccessorRobustnessEvaluatorError):
        evaluate_successor_robustness_fixture_set(protocol=_protocol(), fixtures=fixtures)


def test_sign_stability_rejects_zero_and_flip() -> None:
    assert _sign_stable(1.0, (1.0, 2.0, 0.1, 3.0)) is True
    assert _sign_stable(1.0, (0.0, 1.0, 1.0, 1.0)) is False
    assert _sign_stable(1.0, (1.0, -1.0, 1.0, 1.0)) is False
    assert _sign_stable(0.0, (1.0, 1.0, 1.0, 1.0)) is False
    # No refits means a structural calculation cannot claim coefficient stability.
    result = evaluate_successor_robustness_fixture_set(protocol=_protocol(), fixtures=_fixtures())
    assert result["interpretation"]["home_fatigue_sign_stable_across_training_season_omissions"] is False


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
    with pytest.raises(TypeError):
        value.results["paired_nll"] = None
    with pytest.raises(TypeError):
        value.results["paired_nll"]["full_estimate"] = 0.0
    changed = json.loads(canonical_historical_expected_goals_successor_robustness_evaluation_bytes(value))["results"]
    changed["interpretation"]["paired_elo_interval_upper_below_zero"] = not changed["interpretation"]["paired_elo_interval_upper_below_zero"]
    with pytest.raises(HistoricalExpectedGoalsSuccessorRobustnessEvaluatorError):
        build_historical_expected_goals_successor_robustness_evaluation(
            receipt_bytes=receipt, protocol=protocol,
            protocol_bytes=canonical_successor_robustness_protocol_bytes(protocol),
            source_corpus_sha256=protocol.source_corpus_sha256, results=changed,
        )
    with pytest.raises(HistoricalExpectedGoalsSuccessorRobustnessEvaluatorError):
        dataclasses.replace(value, protocol_sha256="0" * 64)
    with pytest.raises(HistoricalExpectedGoalsSuccessorRobustnessEvaluatorError):
        dataclasses.replace(value, protocol_size=1)
    with pytest.raises(HistoricalExpectedGoalsSuccessorRobustnessEvaluatorError):
        dataclasses.replace(value, source_corpus_sha256="0" * 64)
    with pytest.raises(HistoricalExpectedGoalsSuccessorRobustnessEvaluatorError):
        dataclasses.replace(value, safety={key: False for key in value.safety} | {"bet_authorized": True})
    exact = canonical_historical_expected_goals_successor_robustness_evaluation_bytes(value)
    assert revalidate_historical_expected_goals_successor_robustness_evaluation(
        receipt_bytes=receipt, protocol=protocol,
        protocol_bytes=canonical_successor_robustness_protocol_bytes(protocol),
        evaluation=value, evaluation_bytes=exact,
    ) == value


def _six_features() -> tuple[HistoricalReplayFeatureValue, ...]:
    values = {"home_elo": 1510., "away_elo": 1490., "home_form": .6, "away_form": .4, "fatigue": .1}
    result=[]
    for feature_id in sorted(ModelFeatureId, key=lambda item: item.value):
        if feature_id is ModelFeatureId.LIVE_DATA_FRESHNESS:
            result.append(HistoricalReplayFeatureValue(feature_id, HistoricalFeatureReplayStatus.NOT_RECONSTRUCTIBLE_WITH_CURRENT_EVIDENCE, None, "synthetic", False))
        else:
            result.append(HistoricalReplayFeatureValue(feature_id, HistoricalFeatureReplayStatus.AVAILABLE_RESEARCH_REPLAY, values[feature_id.value], "synthetic", False))
    return tuple(result)


def _pr73_fixture(index: int, season: str) -> HistoricalReplayFixture:
    date=datetime.date(int(season[:4]),8,index+1)
    return HistoricalReplayFixture(f"pr73-{season}-{index}", SOURCE, season, "B1", "B1", date, datetime.datetime.combine(date,datetime.time(15)), SOURCE_LOCAL_TIMEZONE_UNRESOLVED, f"h{index}", f"a{index}", "H", "A", index % 4, (index * 2) % 3, "0" * 64, index + 2, _six_features(), "UNPROVEN", True, True)


def test_generic_six_dimensional_adapter_has_exact_pr73_parity() -> None:
    protocol73 = _fitting().__class__  # type sentinel only; actual protocol below
    raw = subprocess.check_output(["git", "show", "HEAD:artifacts/research-manifests/historical-expected-goals-real-corpus-validation-receipt-v1.json"], cwd=ROOT)
    p = build_historical_expected_goals_successor_protocol(receipt_bytes=raw)
    fixtures = tuple(_pr73_fixture(index, season) for season in ("2020-21", "2021-22", "2022-23", "2023-24") for index in range(1, 9)) + tuple(_pr73_fixture(index + 10, season) for season in ("2024-25", "2025-26") for index in range(1, 3))
    expected = fit_historical_expected_goals_successor_fixture_set(protocol=p, fixtures=fixtures)
    rows = tuple((1., (1510.-1500.)/400., (1490.-1500.)/400., .1, -.1, .1) for _ in fixtures if _.season in p.train_seasons)
    # The constant duplicate design is singular; take the exact vectors from the PR73 fixture seam instead.
    from domain.historical_expected_goals_successor_candidate import _predictor_vector
    train = tuple(item for item in fixtures if item.season in p.train_seasons)
    home = __import__("domain.historical_expected_goals_successor_robustness_evaluator", fromlist=["fit_poisson_design"]).fit_poisson_design(rows=tuple(_predictor_vector(p, item) for item in train), responses=tuple(item.home_goals for item in train), fitting=p.fitting)
    away = __import__("domain.historical_expected_goals_successor_robustness_evaluator", fromlist=["fit_poisson_design"]).fit_poisson_design(rows=tuple(_predictor_vector(p, item) for item in train), responses=tuple(item.away_goals for item in train), fitting=p.fitting)
    assert home.coefficients == expected.home_fit.coefficients
    assert home.updates == expected.home_fit.newton_updates
    assert home.gradient_inf_norm == expected.home_fit.convergence_gradient_inf_norm
    assert home.training_mean_nll == expected.home_fit.rounded_training_mean_nll
    assert away.coefficients == expected.away_fit.coefficients
    assert away.updates == expected.away_fit.newton_updates
    assert away.gradient_inf_norm == expected.away_fit.convergence_gradient_inf_norm
    assert away.training_mean_nll == expected.away_fit.rounded_training_mean_nll


def test_raw_and_canonical_pr69_hash_domains_are_explicitly_distinct() -> None:
    from domain.historical_expected_goals_successor_robustness_evaluator import (
        PR69_CANONICAL_SHA256,
        PR69_CANONICAL_SIZE,
        PR69_SOURCE_CORPUS_SHA256,
        PR69_SOURCE_FILE_COUNT,
        PR69_SOURCE_FIXTURE_COUNT,
        PR69_SOURCE_TOTAL_BYTES,
    )

    assert PR69_CANONICAL_SHA256 != PR69_SOURCE_CORPUS_SHA256
    assert (PR69_SOURCE_FILE_COUNT, PR69_SOURCE_TOTAL_BYTES, PR69_SOURCE_FIXTURE_COUNT) == (66, 10_006_877, 21_226)
    assert PR69_CANONICAL_SIZE == 39_952_730


def test_production_ast_excludes_disallowed_execution_dependencies() -> None:
    path = ROOT / "domain" / "historical_expected_goals_successor_robustness_evaluator.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    forbidden = {"sqlite3", "requests", "urllib", "pandas", "numpy", "scipy", "sklearn", "joblib"}
    assert not imports & forbidden
    forbidden_calls = {"build_score_matrix", "ProbabilityEngine"}
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert not names & forbidden_calls
