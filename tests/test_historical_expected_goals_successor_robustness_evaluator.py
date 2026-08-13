"""Synthetic-only checks for the PR76 robustness machinery."""

from __future__ import annotations

import ast
import dataclasses
import datetime
import json
import math
import subprocess
from pathlib import Path

import pytest

import domain.historical_expected_goals_successor_robustness_evaluator as evaluator_module
from domain.fixture_model_features import ModelFeatureId
from domain.historical_expected_goals_successor_candidate import (
    _ordered_eligible,
    _predictor_vector,
    fit_historical_expected_goals_successor_fixture_set,
)
from domain.historical_expected_goals_successor_protocol import (
    build_historical_expected_goals_successor_protocol,
)
from domain.historical_expected_goals_successor_robustness_evaluator import (
    CLUSTER_KEYS,
    ELO_INITIALIZATION_SEMANTICS,
    FATIGUE_PR31_SEMANTIC_EQUIVALENCE,
    HISTORICAL_FRESHNESS_REGIME_RECONSTRUCTED,
    PR69_CANONICAL_SHA256,
    PR69_CANONICAL_SIZE,
    PR69_SOURCE_CORPUS_SHA256,
    PR69_SOURCE_FILE_COUNT,
    PR69_SOURCE_FIXTURE_COUNT,
    PR69_SOURCE_TOTAL_BYTES,
    SOURCE_BOUND_PROVENANCE,
    HistoricalExpectedGoalsSuccessorRobustnessEvaluation,
    HistoricalExpectedGoalsSuccessorRobustnessEvaluatorError,
    RobustnessFixture,
    _calibration,
    _sign_stable,
    build_historical_expected_goals_successor_robustness_evaluation,
    canonical_historical_expected_goals_successor_robustness_evaluation_bytes,
    evaluate_successor_robustness_fixture_set,
    fit_poisson_design,
    revalidate_historical_expected_goals_successor_robustness_evaluation,
    revalidate_source_bound_historical_expected_goals_successor_robustness_evaluation,
)
from domain.historical_expected_goals_successor_robustness_protocol import (
    canonical_successor_robustness_protocol_bytes,
    successor_robustness_protocol,
)
from domain.historical_model_feature_replay_candidate import (
    SOURCE,
    SOURCE_LOCAL_TIMEZONE_UNRESOLVED,
    HistoricalFeatureReplayStatus,
    HistoricalReplayFeatureValue,
    HistoricalReplayFixture,
)


ROOT = Path(__file__).resolve().parents[1]
PR74_RECEIPT_PATH = (
    "artifacts/research-manifests/"
    "historical-expected-goals-successor-real-corpus-receipt-v1.json"
)
PR71_RECEIPT_PATH = (
    "artifacts/research-manifests/"
    "historical-expected-goals-real-corpus-validation-receipt-v1.json"
)


def _git_blob(path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"HEAD:{path}"], cwd=ROOT)


def _protocol():
    return successor_robustness_protocol(receipt_bytes=_git_blob(PR74_RECEIPT_PATH))


def _protocol73():
    return build_historical_expected_goals_successor_protocol(
        receipt_bytes=_git_blob(PR71_RECEIPT_PATH)
    )


def _fitting():
    return _protocol73().fitting


def _fixtures() -> tuple[RobustnessFixture, ...]:
    values: list[RobustnessFixture] = []
    design = (
        (1.0, -0.3, 0.1, 0.1, 0.2),
        (1.0, -0.2, -0.1, 0.4, -0.1),
        (1.0, -0.1, 0.2, 0.2, 0.3),
        (1.0, 0.0, -0.2, 0.0, 0.4),
        (1.0, 0.1, 0.3, 0.3, -0.2),
        (1.0, 0.2, -0.3, 0.5, 0.1),
        (1.0, 0.3, 0.4, -0.1, 0.0),
        (1.0, 0.4, -0.4, 0.2, 0.5),
    )
    for season_index, season in enumerate(
        ("2020-21", "2021-22", "2022-23", "2023-24")
    ):
        for index, row in enumerate(design):
            values.append(
                RobustnessFixture(
                    f"train-{season}-{index}",
                    season,
                    "B1",
                    "TRAIN",
                    (index + season_index) % 4,
                    (index * 2 + season_index) % 3,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    row,
                    row + ((index % 3) / 10.0,),
                )
            )
    for index, (season, league) in enumerate(CLUSTER_KEYS):
        # Unequal cluster sizes make equal-weight cluster mistakes observable.
        for repeat in range(1 + (index % 3)):
            values.append(
                RobustnessFixture(
                    f"{season}-{league}-{repeat}",
                    season,
                    league,
                    "EVALUATION",
                    repeat % 3,
                    (repeat + 1) % 3,
                    1.1 + (index % 4) * 0.03,
                    0.9 + (repeat * 0.04),
                    0.8 + (index % 5) * 0.02,
                    1.2 - (repeat * 0.03),
                    (1.0, 0.1, -0.1, 0.0, 0.0),
                    (1.0, 0.1, -0.1, 0.0, 0.0, 0.1),
                )
            )
    return tuple(values)


def _joint_nll(fixture: RobustnessFixture, home: float, away: float) -> float:
    return math.fsum(
        (
            home
            - fixture.home_goals * math.log(home)
            + math.lgamma(fixture.home_goals + 1),
            away
            - fixture.away_goals * math.log(away)
            + math.lgamma(fixture.away_goals + 1),
        )
    )


def _differences(fixtures: tuple[RobustnessFixture, ...]) -> dict[str, float]:
    return {
        item.fixture_identifier: _joint_nll(
            item, item.successor_home_rate, item.successor_away_rate
        )
        - _joint_nll(item, item.elo_home_rate, item.elo_away_rate)
        for item in fixtures
        if item.split == "EVALUATION"
    }


def _structural_value(*, with_fitting: bool = False):
    protocol = _protocol()
    results = evaluate_successor_robustness_fixture_set(
        protocol=protocol,
        fixtures=_fixtures(),
        fitting=_fitting() if with_fitting else None,
    )
    receipt = _git_blob(PR74_RECEIPT_PATH)
    return build_historical_expected_goals_successor_robustness_evaluation(
        receipt_bytes=receipt,
        protocol=protocol,
        protocol_bytes=canonical_successor_robustness_protocol_bytes(protocol),
        source_corpus_sha256=protocol.source_corpus_sha256,
        results=results,
    )


def _mutable_results(value) -> dict:
    return json.loads(
        canonical_historical_expected_goals_successor_robustness_evaluation_bytes(
            value
        )
    )["results"]


def test_paired_jackknife_and_sensitivity_are_independently_recomputed() -> None:
    fixtures = _fixtures()
    result = evaluate_successor_robustness_fixture_set(
        protocol=_protocol(), fixtures=fixtures
    )
    paired = result["paired_nll"]
    evaluation = tuple(item for item in fixtures if item.split == "EVALUATION")
    differences = _differences(fixtures)

    expected_theta = math.fsum(differences.values()) / len(differences)
    expected_delete: list[float] = []
    for key in CLUSTER_KEYS:
        retained = [
            differences[item.fixture_identifier]
            for item in evaluation
            if (item.season, item.identity_league) != key
        ]
        expected_delete.append(math.fsum(retained) / len(retained))
    expected_center = math.fsum(expected_delete) / len(expected_delete)
    expected_se = math.sqrt(
        (21 / 22)
        * math.fsum((item - expected_center) ** 2 for item in expected_delete)
    )

    assert paired["full_estimate"] == pytest.approx(expected_theta)
    assert [item["delete_estimate"] for item in paired["delete_clusters"]] == pytest.approx(
        expected_delete
    )
    assert paired["jackknife_se"] == pytest.approx(expected_se)
    assert paired["interval_lower"] == pytest.approx(expected_theta - 1.96 * expected_se)
    assert paired["interval_upper"] == pytest.approx(expected_theta + 1.96 * expected_se)

    for record in paired["leave_one_league_out"]:
        league = record["omitted_league"]
        omitted = [item for item in evaluation if item.identity_league == league]
        assert {item.season for item in omitted} == {"2024-25", "2025-26"}
        retained = [
            differences[item.fixture_identifier]
            for item in evaluation
            if item.identity_league != league
        ]
        assert record["omitted_fixture_count"] == len(omitted)
        assert record["candidate_minus_elo_mean_nll"] == pytest.approx(
            math.fsum(retained) / len(retained)
        )

    for record in paired["leave_one_season_out"]:
        omitted = record["omitted_season"]
        remaining_season = "2025-26" if omitted == "2024-25" else "2024-25"
        retained_fixtures = [item for item in evaluation if item.season != omitted]
        assert {item.season for item in retained_fixtures} == {remaining_season}
        retained = [differences[item.fixture_identifier] for item in retained_fixtures]
        assert record["candidate_minus_elo_mean_nll"] == pytest.approx(
            math.fsum(retained) / len(retained)
        )


def _independent_calibration_metrics(
    fixtures: tuple[RobustnessFixture, ...], model: str, side: str
) -> tuple[float, float, float]:
    bounds = (
        (0.0, 0.5),
        (0.5, 1.0),
        (1.0, 1.5),
        (1.5, 2.0),
        (2.0, 2.5),
        (2.5, 3.0),
        (3.0, None),
    )
    predictions = [getattr(item, f"{model}_{side}_rate") for item in fixtures]
    observations = [
        item.home_goals if side == "home" else item.away_goals for item in fixtures
    ]
    mean_prediction = math.fsum(predictions) / len(predictions)
    mean_observation = math.fsum(observations) / len(observations)
    absolute_bias = abs(mean_prediction - mean_observation)
    weighted_abs = 0.0
    weighted_square = 0.0
    for lower, upper in bounds:
        selected = [
            (prediction, observation)
            for prediction, observation in zip(predictions, observations)
            if prediction >= lower and (upper is None or prediction < upper)
        ]
        if not selected:
            continue
        predicted = math.fsum(item[0] for item in selected) / len(selected)
        observed = math.fsum(item[1] for item in selected) / len(selected)
        error = predicted - observed
        weighted_abs += len(selected) * abs(error)
        weighted_square += len(selected) * error**2
    return (
        absolute_bias,
        weighted_abs / len(fixtures),
        weighted_square / len(fixtures),
    )


def test_calibration_metrics_are_independent_and_same_population() -> None:
    fixtures = tuple(item for item in _fixtures() if item.split == "EVALUATION")
    result = evaluate_successor_robustness_fixture_set(
        protocol=_protocol(), fixtures=_fixtures()
    )["calibration"]
    for model in ("successor", "elo"):
        for side in ("home", "away"):
            expected = _independent_calibration_metrics(fixtures, model, side)
            summary = result["summaries"][f"{model}_{side}"]
            assert summary["absolute_overall_bias"] == pytest.approx(expected[0])
            assert summary["wace"] == pytest.approx(expected[1])
            assert summary["wsce"] == pytest.approx(expected[2])
            assert sum(
                item["count"] for item in result["bins"][f"{model}_{side}"]
            ) == len(fixtures)

    for side in ("home", "away"):
        for metric in ("absolute_overall_bias", "wace", "wsce"):
            assert result["successor_minus_elo"][f"{side}_{metric}"] == pytest.approx(
                result["summaries"][f"successor_{side}"][metric]
                - result["summaries"][f"elo_{side}"][metric]
            )


def test_calibration_boundaries_are_lower_inclusive_and_model_specific() -> None:
    rates = (
        0.499,
        0.5,
        0.999,
        1.0,
        1.499,
        1.5,
        1.999,
        2.0,
        2.499,
        2.5,
        2.999,
        3.0,
    )
    successor_rows = tuple(
        RobustnessFixture(
            f"successor-boundary-{index}",
            "2024-25",
            "B1",
            "EVALUATION",
            1,
            1,
            rate,
            1.0,
            1.0,
            0.25,
            (1.0, 0.0, 0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        )
        for index, rate in enumerate(rates)
    )
    elo_rows = tuple(
        RobustnessFixture(
            f"elo-boundary-{index}",
            "2024-25",
            "B1",
            "EVALUATION",
            1,
            1,
            0.25,
            1.0,
            1.0,
            rate,
            (1.0, 0.0, 0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        )
        for index, rate in enumerate(rates)
    )
    expected_counts = [1, 2, 2, 2, 2, 2, 1]
    assert [
        item["count"] for item in _calibration(successor_rows, model="successor", side="home")
    ] == expected_counts
    assert [
        item["count"] for item in _calibration(elo_rows, model="elo", side="away")
    ] == expected_counts


def test_unknown_and_actual_missing_cluster_fail_separately() -> None:
    unknown = list(_fixtures())
    first_evaluation = next(index for index, item in enumerate(unknown) if item.split == "EVALUATION")
    original = unknown[first_evaluation]
    unknown[first_evaluation] = dataclasses.replace(original, identity_league="XX")
    with pytest.raises(HistoricalExpectedGoalsSuccessorRobustnessEvaluatorError, match="unknown"):
        evaluate_successor_robustness_fixture_set(protocol=_protocol(), fixtures=unknown)

    missing_key = CLUSTER_KEYS[0]
    missing = tuple(
        item
        for item in _fixtures()
        if not (
            item.split == "EVALUATION"
            and (item.season, item.identity_league) == missing_key
        )
    )
    with pytest.raises(HistoricalExpectedGoalsSuccessorRobustnessEvaluatorError, match="missing"):
        evaluate_successor_robustness_fixture_set(protocol=_protocol(), fixtures=missing)


def test_duplicate_fixture_identifier_fails_closed() -> None:
    fixtures = list(_fixtures())
    fixtures.append(dataclasses.replace(fixtures[-1]))
    with pytest.raises(HistoricalExpectedGoalsSuccessorRobustnessEvaluatorError, match="unique"):
        evaluate_successor_robustness_fixture_set(protocol=_protocol(), fixtures=fixtures)


def test_sign_stability_rejects_zero_and_flip() -> None:
    assert _sign_stable(1.0, (1.0, 2.0, 0.1, 3.0)) is True
    assert _sign_stable(1.0, (0.0, 1.0, 1.0, 1.0)) is False
    assert _sign_stable(1.0, (1.0, -1.0, 1.0, 1.0)) is False
    assert _sign_stable(0.0, (1.0, 1.0, 1.0, 1.0)) is False


def test_no_fatigue_refit_uses_five_columns_and_four_named_omissions() -> None:
    result = evaluate_successor_robustness_fixture_set(
        protocol=_protocol(), fixtures=_fixtures(), fitting=_fitting()
    )
    assert len(result["no_fatigue"]["home_fit"]["coefficients"]) == 5
    assert len(result["no_fatigue"]["away_fit"]["coefficients"]) == 5
    diagnostics = result["leave_one_training_season_refits"]
    assert [item["omitted_training_season"] for item in diagnostics] == [
        "2020-21",
        "2021-22",
        "2022-23",
        "2023-24",
    ]
    assert all(item["training_fixture_count"] == 24 for item in diagnostics)
    for item in diagnostics:
        assert len(item["home_fit"]["coefficients"]) == 6
        assert len(item["away_fit"]["coefficients"]) == 6
        assert item["home_fatigue_coefficient"] == item["home_fit"]["coefficients"][-1]
        assert item["away_fatigue_coefficient"] == item["away_fit"]["coefficients"][-1]


def test_canonical_semantics_immutability_and_structural_revalidation() -> None:
    value = _structural_value()
    exact = canonical_historical_expected_goals_successor_robustness_evaluation_bytes(value)
    assert exact.endswith(b"\n")
    assert exact == canonical_historical_expected_goals_successor_robustness_evaluation_bytes(value)
    assert value.elo_initialization_semantics == ELO_INITIALIZATION_SEMANTICS
    assert value.fatigue_pr31_semantic_equivalence == FATIGUE_PR31_SEMANTIC_EQUIVALENCE
    assert value.historical_freshness_regime_reconstructed is HISTORICAL_FRESHNESS_REGIME_RECONSTRUCTED
    assert all(flag is False for flag in value.safety.values())
    with pytest.raises(TypeError):
        value.results["paired_nll"]["full_estimate"] = 0.0

    for field, replacement in (
        ("protocol_sha256", "0" * 64),
        ("protocol_size", 1),
        ("source_corpus_sha256", "0" * 64),
        ("elo_initialization_semantics", "OBSERVED"),
        ("fatigue_pr31_semantic_equivalence", "PROVEN"),
        ("historical_freshness_regime_reconstructed", True),
    ):
        with pytest.raises(HistoricalExpectedGoalsSuccessorRobustnessEvaluatorError):
            dataclasses.replace(value, **{field: replacement})
    with pytest.raises(HistoricalExpectedGoalsSuccessorRobustnessEvaluatorError):
        dataclasses.replace(
            value,
            safety={key: False for key in value.safety} | {"bet_authorized": True},
        )

    assert revalidate_historical_expected_goals_successor_robustness_evaluation(
        receipt_bytes=_git_blob(PR74_RECEIPT_PATH),
        protocol=_protocol(),
        protocol_bytes=canonical_successor_robustness_protocol_bytes(_protocol()),
        evaluation=value,
        evaluation_bytes=exact,
    ) == value


def _expect_mutated_results_rejected(mutator, *, with_fitting: bool = False) -> None:
    value = _structural_value(with_fitting=with_fitting)
    changed = _mutable_results(value)
    mutator(changed)
    with pytest.raises(HistoricalExpectedGoalsSuccessorRobustnessEvaluatorError):
        build_historical_expected_goals_successor_robustness_evaluation(
            receipt_bytes=_git_blob(PR74_RECEIPT_PATH),
            protocol=_protocol(),
            protocol_bytes=canonical_successor_robustness_protocol_bytes(_protocol()),
            source_corpus_sha256=_protocol().source_corpus_sha256,
            results=changed,
        )


def test_interval_calibration_delta_and_refit_scalar_mutations_fail() -> None:
    _expect_mutated_results_rejected(
        lambda value: value["paired_nll"].__setitem__(
            "interval_lower", value["paired_nll"]["interval_lower"] + 0.01
        )
    )
    _expect_mutated_results_rejected(
        lambda value: value["paired_nll"].__setitem__(
            "interval_upper", value["paired_nll"]["interval_upper"] - 0.01
        )
    )
    _expect_mutated_results_rejected(
        lambda value: value["calibration"]["successor_minus_elo"].__setitem__(
            "home_wace",
            value["calibration"]["successor_minus_elo"]["home_wace"] + 0.01,
        )
    )
    _expect_mutated_results_rejected(
        lambda value: value["leave_one_training_season_refits"][0].__setitem__(
            "home_fatigue_coefficient",
            value["leave_one_training_season_refits"][0]["home_fatigue_coefficient"]
            + 0.01,
        ),
        with_fitting=True,
    )
    _expect_mutated_results_rejected(
        lambda value: value["leave_one_training_season_refits"][0].__setitem__(
            "away_fatigue_coefficient",
            value["leave_one_training_season_refits"][0]["away_fatigue_coefficient"]
            - 0.01,
        ),
        with_fitting=True,
    )


def test_every_interpretation_boolean_is_mechanically_derived() -> None:
    value = _structural_value(with_fitting=True)
    names = tuple(value.results["interpretation"])
    assert len(names) == 10
    for name in names:
        changed = _mutable_results(value)
        changed["interpretation"][name] = not changed["interpretation"][name]
        with pytest.raises(HistoricalExpectedGoalsSuccessorRobustnessEvaluatorError):
            build_historical_expected_goals_successor_robustness_evaluation(
                receipt_bytes=_git_blob(PR74_RECEIPT_PATH),
                protocol=_protocol(),
                protocol_bytes=canonical_successor_robustness_protocol_bytes(_protocol()),
                source_corpus_sha256=_protocol().source_corpus_sha256,
                results=changed,
            )


def test_small_structural_result_cannot_be_relabelled_source_bound() -> None:
    value = _structural_value(with_fitting=True)
    with pytest.raises(HistoricalExpectedGoalsSuccessorRobustnessEvaluatorError):
        dataclasses.replace(value, provenance=SOURCE_BOUND_PROVENANCE)


def _feature_tuple(
    *,
    home_elo: float,
    away_elo: float,
    home_form: float,
    away_form: float,
    fatigue: float,
) -> tuple[HistoricalReplayFeatureValue, ...]:
    supplied = {
        ModelFeatureId.HOME_ELO: home_elo,
        ModelFeatureId.AWAY_ELO: away_elo,
        ModelFeatureId.HOME_FORM: home_form,
        ModelFeatureId.AWAY_FORM: away_form,
        ModelFeatureId.FATIGUE: fatigue,
    }
    result: list[HistoricalReplayFeatureValue] = []
    for feature_id in sorted(ModelFeatureId, key=lambda item: item.value):
        if feature_id is ModelFeatureId.LIVE_DATA_FRESHNESS:
            result.append(
                HistoricalReplayFeatureValue(
                    feature_id,
                    HistoricalFeatureReplayStatus.NOT_RECONSTRUCTIBLE_WITH_CURRENT_EVIDENCE,
                    None,
                    "synthetic",
                    False,
                )
            )
        else:
            result.append(
                HistoricalReplayFeatureValue(
                    feature_id,
                    HistoricalFeatureReplayStatus.AVAILABLE_RESEARCH_REPLAY,
                    supplied[feature_id],
                    "synthetic",
                    False,
                )
            )
    return tuple(result)


_TRANSFORMED_FULL_RANK_ROWS = (
    (0.0, 0.0, 0.0, 0.0, 0.0),
    (0.2, 0.0, 0.0, 0.0, 0.0),
    (0.0, 0.2, 0.0, 0.0, 0.0),
    (0.0, 0.0, 0.2, 0.0, 0.0),
    (0.0, 0.0, 0.0, 0.2, 0.0),
    (0.0, 0.0, 0.0, 0.0, 0.1),
    (0.1, -0.1, 0.1, -0.1, 0.3),
    (-0.2, 0.1, -0.2, 0.2, 0.1),
)
_HOME_GOALS = (1, 3, 0, 2, 1, 3, 2, 0)
_AWAY_GOALS = (1, 0, 3, 1, 2, 1, 3, 2)


def _pr73_fixture(index: int, season: str, *, evaluation: bool = False) -> HistoricalReplayFixture:
    transformed = _TRANSFORMED_FULL_RANK_ROWS[index % len(_TRANSFORMED_FULL_RANK_ROWS)]
    home_elo_delta, away_elo_delta, home_form_delta, away_form_delta, fatigue = transformed
    year = int(season[:4])
    day = (index % 20) + 1
    date = datetime.date(year, 8, day)
    suffix = "eval" if evaluation else "train"
    return HistoricalReplayFixture(
        f"pr73-{suffix}-{season}-{index}",
        SOURCE,
        season,
        "B1",
        "B1",
        date,
        datetime.datetime.combine(date, datetime.time(15)),
        SOURCE_LOCAL_TIMEZONE_UNRESOLVED,
        f"h-{season}-{index}",
        f"a-{season}-{index}",
        f"Home {season} {index}",
        f"Away {season} {index}",
        _HOME_GOALS[index % len(_HOME_GOALS)],
        _AWAY_GOALS[index % len(_AWAY_GOALS)],
        "0" * 64,
        index + 2,
        _feature_tuple(
            home_elo=1500.0 + 400.0 * home_elo_delta,
            away_elo=1500.0 + 400.0 * away_elo_delta,
            home_form=0.5 + home_form_delta,
            away_form=0.5 + away_form_delta,
            fatigue=fatigue,
        ),
        "UNPROVEN",
        True,
        True,
    )


def test_generic_six_dimensional_adapter_has_exact_full_rank_pr73_parity() -> None:
    protocol = _protocol73()
    fixtures: list[HistoricalReplayFixture] = []
    for season in protocol.train_seasons:
        fixtures.extend(_pr73_fixture(index, season) for index in range(8))
    for season in protocol.evaluation_seasons:
        fixtures.extend(
            _pr73_fixture(index, season, evaluation=True) for index in range(2)
        )
    fixture_tuple = tuple(fixtures)
    expected = fit_historical_expected_goals_successor_fixture_set(
        protocol=protocol, fixtures=fixture_tuple
    )
    training = _ordered_eligible(protocol, fixture_tuple, protocol.train_seasons)
    rows = tuple(_predictor_vector(protocol, item) for item in training)

    # Baseline + five independent axis rows occur in every training season, so
    # the six-column design (including intercept) is full rank by construction.
    assert len({row for row in rows}) >= 6
    assert expected.home_fit.newton_updates > 0
    assert expected.away_fit.newton_updates > 0

    home = fit_poisson_design(
        rows=rows,
        responses=tuple(item.home_goals for item in training),
        fitting=protocol.fitting,
    )
    away = fit_poisson_design(
        rows=rows,
        responses=tuple(item.away_goals for item in training),
        fitting=protocol.fitting,
    )
    assert home.coefficients == expected.home_fit.coefficients
    assert home.updates == expected.home_fit.newton_updates
    assert home.gradient_inf_norm == expected.home_fit.convergence_gradient_inf_norm
    assert home.training_mean_nll == expected.home_fit.rounded_training_mean_nll
    assert away.coefficients == expected.away_fit.coefficients
    assert away.updates == expected.away_fit.newton_updates
    assert away.gradient_inf_norm == expected.away_fit.convergence_gradient_inf_norm
    assert away.training_mean_nll == expected.away_fit.rounded_training_mean_nll


def _unsafe_source_bound_copy(value, *, results=None):
    copied = object.__new__(HistoricalExpectedGoalsSuccessorRobustnessEvaluation)
    for field in dataclasses.fields(HistoricalExpectedGoalsSuccessorRobustnessEvaluation):
        object.__setattr__(
            copied,
            field.name,
            results if field.name == "results" and results is not None else getattr(value, field.name),
        )
    object.__setattr__(copied, "provenance", SOURCE_BOUND_PROVENANCE)
    return copied


def test_full_revalidator_rejects_coordinated_object_and_byte_mutation(monkeypatch) -> None:
    structural = _structural_value()
    reference = _unsafe_source_bound_copy(structural)
    changed = _mutable_results(structural)
    changed["paired_nll"]["full_estimate"] += 0.123
    mutated = _unsafe_source_bound_copy(structural, results=changed)

    monkeypatch.setattr(
        evaluator_module,
        "build_source_bound_historical_expected_goals_successor_robustness_evaluation",
        lambda **_: reference,
    )
    monkeypatch.setattr(
        evaluator_module,
        "canonical_historical_expected_goals_successor_robustness_evaluation_bytes",
        lambda value: b"reference\n" if value is reference else b"mutated\n",
    )
    with pytest.raises(
        HistoricalExpectedGoalsSuccessorRobustnessEvaluatorError,
        match="complete ancestry rebuild",
    ):
        revalidate_source_bound_historical_expected_goals_successor_robustness_evaluation(
            source_inputs=(),
            corpus=None,
            corpus_bytes=b"unused",
            pr73_receipt_bytes=b"unused",
            pr73_protocol=None,
            pr73_protocol_bytes=b"unused",
            pr75_receipt_bytes=b"unused",
            pr75_protocol=None,
            pr75_protocol_bytes=b"unused",
            evaluation=mutated,
            evaluation_bytes=b"mutated\n",
        )


def test_raw_and_canonical_pr69_hash_domains_are_explicitly_distinct() -> None:
    assert PR69_CANONICAL_SHA256 != PR69_SOURCE_CORPUS_SHA256
    assert (
        PR69_SOURCE_FILE_COUNT,
        PR69_SOURCE_TOTAL_BYTES,
        PR69_SOURCE_FIXTURE_COUNT,
    ) == (66, 10_006_877, 21_226)
    assert PR69_CANONICAL_SIZE == 39_952_730


def test_production_ast_excludes_disallowed_execution_dependencies() -> None:
    path = ROOT / "domain" / "historical_expected_goals_successor_robustness_evaluator.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    module_paths: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            module_paths.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                module_paths.add(node.module)
    lowered = "\n".join(sorted(module_paths)).casefold()
    for prohibited in (
        "sqlite",
        "requests",
        "urllib",
        "httpx",
        "aiohttp",
        "pandas",
        "numpy",
        "scipy",
        "sklearn",
        "joblib",
        "score_matrix",
        "probability",
        "pricing",
        "selection",
        "betting",
    ):
        assert prohibited not in lowered
