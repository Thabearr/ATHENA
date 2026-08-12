from __future__ import annotations

import ast
import dataclasses
import math
from pathlib import Path

import pytest

from domain.fixture_model_features import ModelFeatureId, ModelFeatureStatus
from domain.fotmob_reviewed_match_details_expected_goals_transform_candidate import (
    ExpectedGoalsFeatureAudit,
    _rates_from_audits as pr68_rates_from_audits,
    legacy_expected_goals_transform_specification,
)
from domain.historical_expected_goals_component_validation import (
    CALIBRATION_SPEC_ID,
    CONSTANT_BASELINE_ID,
    DATASET_NAME,
    ROLLING_BASELINE_ID,
    SCORING_RULE_ID,
    VALIDATION_SCOPE,
    BenchmarkComparison,
    ComparisonResult,
    HistoricalExpectedGoalsComponent,
    HistoricalExpectedGoalsComponentValidationError,
    _Evaluation,
    _calibration,
    _candidate_rates,
    _rolling_rates,
    build_historical_expected_goals_component_validation,
    canonical_historical_expected_goals_component_validation_bytes,
    historical_expected_goals_validation_specification,
    poisson_nll,
    revalidate_historical_expected_goals_component_validation,
    sha256_historical_expected_goals_component_validation,
)
from domain.historical_model_feature_replay_candidate import (
    HistoricalFeatureReplayStatus,
    HistoricalReplayFeatureValue,
    HistoricalReplaySourceInput,
    build_historical_model_feature_replay_corpus,
    canonical_historical_model_feature_replay_corpus_bytes,
)


def _csv(rows: list[tuple[str, str, str, str, int, int]], div: str = "E0") -> bytes:
    lines = ["Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR"]
    for date, time, home, away, hg, ag in rows:
        result = "H" if hg > ag else "A" if hg < ag else "D"
        lines.append(f"{div},{date},{time},{home},{away},{hg},{ag},{result},,,")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _base_rows() -> list[tuple[str, str, str, str, int, int]]:
    return [
        ("01/08/2020", "12:00", "A", "B", 1, 0),
        ("01/08/2020", "15:00", "C", "D", 0, 1),
        ("08/08/2020", "12:00", "A", "C", 2, 1),
        ("08/08/2020", "15:00", "B", "D", 0, 0),
        ("15/08/2020", "12:00", "A", "D", 3, 1),
        ("15/08/2020", "15:00", "B", "C", 1, 2),
        ("22/08/2020", "12:00", "A", "B", 1, 1),
        ("22/08/2020", "15:00", "C", "D", 2, 0),
    ]


def _source(rows: list[tuple[str, str, str, str, int, int]] | None = None, *, season: str = "2020-21", league: str = "E0") -> HistoricalReplaySourceInput:
    return HistoricalReplaySourceInput(
        season=season,
        acquisition_league=league,
        raw_bytes=_csv(_base_rows() if rows is None else rows, div=league),
    )


def _chain(source_inputs: tuple[HistoricalReplaySourceInput, ...] | None = None):
    inputs = source_inputs or (_source(),)
    corpus = build_historical_model_feature_replay_corpus(inputs)
    corpus_bytes = canonical_historical_model_feature_replay_corpus_bytes(corpus)
    validation = build_historical_expected_goals_component_validation(
        source_inputs=inputs,
        corpus=corpus,
        corpus_bytes=corpus_bytes,
    )
    validation_bytes = canonical_historical_expected_goals_component_validation_bytes(validation)
    return inputs, corpus, corpus_bytes, validation, validation_bytes


def _feature(feature_id: ModelFeatureId, value: float) -> HistoricalReplayFeatureValue:
    return HistoricalReplayFeatureValue(
        feature_id=feature_id,
        status=HistoricalFeatureReplayStatus.AVAILABLE_RESEARCH_REPLAY,
        value=value,
        evidence_origin="SYNTHETIC_TEST_REPLAY",
        replay_initial_state_assumption=False,
    )


def _synthetic_fixture(corpus, *, home_form=0.7, away_form=0.3, home_elo=1600.0, away_elo=1400.0, fatigue=0.1):
    base = next(item for item in corpus.fixtures if item.form_path_component_eligible and item.elo_fallback_component_eligible)
    values = {
        ModelFeatureId.HOME_FORM: _feature(ModelFeatureId.HOME_FORM, float(home_form)),
        ModelFeatureId.AWAY_FORM: _feature(ModelFeatureId.AWAY_FORM, float(away_form)),
        ModelFeatureId.HOME_ELO: _feature(ModelFeatureId.HOME_ELO, float(home_elo)),
        ModelFeatureId.AWAY_ELO: _feature(ModelFeatureId.AWAY_ELO, float(away_elo)),
        ModelFeatureId.FATIGUE: _feature(ModelFeatureId.FATIGUE, float(fatigue)),
        ModelFeatureId.LIVE_DATA_FRESHNESS: HistoricalReplayFeatureValue(
            feature_id=ModelFeatureId.LIVE_DATA_FRESHNESS,
            status=HistoricalFeatureReplayStatus.NOT_RECONSTRUCTIBLE_WITH_CURRENT_EVIDENCE,
            value=None,
            evidence_origin="NO_RETAINED_PRE_KICKOFF_FRESHNESS_EVIDENCE",
            replay_initial_state_assumption=False,
        ),
    }
    features = tuple(values[key] for key in sorted(ModelFeatureId, key=lambda item: item.value))
    return dataclasses.replace(
        base,
        features=features,
        form_path_component_eligible=True,
        elo_fallback_component_eligible=True,
    )


def _pr68_audits(*, home_form, away_form, home_elo, away_elo, fatigue, freshness):
    values = {
        ModelFeatureId.HOME_FORM: float(home_form),
        ModelFeatureId.AWAY_FORM: float(away_form),
        ModelFeatureId.HOME_ELO: float(home_elo),
        ModelFeatureId.AWAY_ELO: float(away_elo),
        ModelFeatureId.FATIGUE: float(fatigue),
        ModelFeatureId.LIVE_DATA_FRESHNESS: float(freshness),
    }
    return tuple(
        ExpectedGoalsFeatureAudit(
            feature_id=feature_id,
            status=ModelFeatureStatus.AVAILABLE,
            value=values[feature_id],
            blockers=(),
            evidence_sha256s=(),
        )
        for feature_id in sorted(ModelFeatureId, key=lambda item: item.value)
    )


def test_build_revalidates_full_pr69_chain_and_binds_research_only_contract():
    inputs, corpus, corpus_bytes, validation, validation_bytes = _chain()
    assert validation.dataset_name == DATASET_NAME
    assert validation.validation_scope == VALIDATION_SCOPE
    assert validation.scoring_rule_id == SCORING_RULE_ID
    assert validation.constant_baseline_id == CONSTANT_BASELINE_ID
    assert validation.rolling_baseline_id == ROLLING_BASELINE_ID
    assert validation.calibration_spec_id == CALIBRATION_SPEC_ID
    assert validation.historical_freshness_regime_reconstructed is False
    assert all(flag is False for flag in validation.safety.values())
    rebuilt = revalidate_historical_expected_goals_component_validation(
        source_inputs=inputs,
        corpus=corpus,
        corpus_bytes=corpus_bytes,
        validation=validation,
        validation_bytes=validation_bytes,
    )
    assert rebuilt == validation


def test_source_or_corpus_mutation_fails_closed():
    inputs, corpus, corpus_bytes, validation, validation_bytes = _chain()
    mutated_source = dataclasses.replace(inputs[0], raw_bytes=inputs[0].raw_bytes.replace(b"3,1,H", b"4,1,H"))
    with pytest.raises(HistoricalExpectedGoalsComponentValidationError):
        revalidate_historical_expected_goals_component_validation(
            source_inputs=(mutated_source,),
            corpus=corpus,
            corpus_bytes=corpus_bytes,
            validation=validation,
            validation_bytes=validation_bytes,
        )
    with pytest.raises(HistoricalExpectedGoalsComponentValidationError):
        build_historical_expected_goals_component_validation(
            source_inputs=inputs,
            corpus=corpus,
            corpus_bytes=corpus_bytes + b"x",
        )


def test_form_component_matches_exact_pr68_form_path():
    _, corpus, _, _, _ = _chain()
    fixture = _synthetic_fixture(corpus, home_form=0.71, away_form=0.26, fatigue=0.1)
    expected = pr68_rates_from_audits(
        _pr68_audits(home_form=0.71, away_form=0.26, home_elo=1800, away_elo=1200, fatigue=0.1, freshness=0.05),
        legacy_expected_goals_transform_specification(),
    )
    assert _candidate_rates(fixture, HistoricalExpectedGoalsComponent.FORM_COMPONENT) == expected


def test_elo_component_matches_exact_pr68_fallback_and_clamps():
    _, corpus, _, _, _ = _chain()
    fixture = _synthetic_fixture(corpus, home_elo=5000.0, away_elo=-1000.0, fatigue=0.3)
    expected = pr68_rates_from_audits(
        _pr68_audits(home_form=0.2, away_form=0.8, home_elo=5000, away_elo=-1000, fatigue=0.3, freshness=0.049),
        legacy_expected_goals_transform_specification(),
    )
    assert _candidate_rates(fixture, HistoricalExpectedGoalsComponent.ELO_FALLBACK_COMPONENT) == expected


def test_minimum_floor_fatigue_and_rounding_order_are_frozen():
    _, corpus, _, _, _ = _chain()
    fixture = _synthetic_fixture(corpus, home_form=0.1004, away_form=0.8996, fatigue=10.0)
    home, away = _candidate_rates(fixture, HistoricalExpectedGoalsComponent.FORM_COMPONENT)
    spec = legacy_expected_goals_transform_specification()
    expected_home = max(spec.minimum_rate, round(spec.home_baseline + (0.1004 - 0.8996) - 10.0 * spec.fatigue_coefficient, 3))
    expected_away = max(spec.minimum_rate, round(spec.away_baseline + (0.8996 - 0.1004) + 10.0 * spec.fatigue_coefficient, 3))
    assert (home, away) == (expected_home, expected_away)
    assert home == spec.minimum_rate


def test_target_outcome_cannot_change_candidate_rates_and_ineligible_rows_are_excluded():
    _, corpus, _, validation, _ = _chain()
    fixture = next(item for item in corpus.fixtures if item.form_path_component_eligible)
    changed = dataclasses.replace(fixture, home_goals=9, away_goals=8)
    assert _candidate_rates(fixture, HistoricalExpectedGoalsComponent.FORM_COMPONENT) == _candidate_rates(changed, HistoricalExpectedGoalsComponent.FORM_COMPONENT)
    expected_form = sum(item.form_path_component_eligible for item in corpus.fixtures)
    expected_elo = sum(item.elo_fallback_component_eligible for item in corpus.fixtures)
    assert validation.form_component_summary.metrics.fixture_count == expected_form
    assert validation.elo_fallback_component_summary.metrics.fixture_count == expected_elo
    assert expected_form < corpus.fixture_count


def test_poisson_nll_is_absolute_formula_and_rejects_nonpositive_rate():
    assert poisson_nll(0, 1.0) == 1.0
    assert poisson_nll(1, 1.0) == 1.0
    expected = 2.5 - 3 * math.log(2.5) + math.lgamma(4)
    assert poisson_nll(3, 2.5) == expected
    with pytest.raises(HistoricalExpectedGoalsComponentValidationError):
        poisson_nll(1, 0.0)
    with pytest.raises(HistoricalExpectedGoalsComponentValidationError):
        poisson_nll(1, -1.0)


def test_constant_baseline_uses_exact_pr68_baselines_and_delta_sign():
    _, _, _, validation, _ = _chain()
    spec = legacy_expected_goals_transform_specification()
    form = validation.form_component_summary
    assert form.constant_baseline.paired_fixture_count == form.metrics.fixture_count
    assert form.constant_baseline.result in set(ComparisonResult)
    assert form.constant_baseline.candidate_minus_benchmark_nll == (
        form.constant_baseline.candidate_mean_joint_nll - form.constant_baseline.benchmark_mean_joint_nll
    )
    assert (spec.home_baseline, spec.away_baseline) == (1.45, 1.25)
    assert BenchmarkComparison(CONSTANT_BASELINE_ID, 1, 1.0, 2.0, -1.0, ComparisonResult.BETTER).result is ComparisonResult.BETTER
    assert BenchmarkComparison(CONSTANT_BASELINE_ID, 1, 2.0, 1.0, 1.0, ComparisonResult.WORSE).result is ComparisonResult.WORSE
    assert BenchmarkComparison(CONSTANT_BASELINE_ID, 1, 1.0, 1.0, 0.0, ComparisonResult.EXACT_TIE).result is ComparisonResult.EXACT_TIE


def test_rolling_baseline_is_strict_prior_and_same_kickoff_batched():
    rows = [
        ("01/08/2020", "10:00", "A", "B", 2, 1),
        ("08/08/2020", "12:00", "C", "D", 9, 0),
        ("08/08/2020", "12:00", "E", "F", 0, 9),
        ("15/08/2020", "12:00", "G", "H", 1, 1),
    ]
    corpus = build_historical_model_feature_replay_corpus((_source(rows),))
    rolling = _rolling_rates(corpus.fixtures)
    by_teams = {(item.home_team_name, item.away_team_name): item for item in corpus.fixtures}
    first_same = by_teams[("C", "D")]
    second_same = by_teams[("E", "F")]
    later = by_teams[("G", "H")]
    assert rolling[first_same.fixture_identifier] == (2.0, 1.0)
    assert rolling[second_same.fixture_identifier] == (2.0, 1.0)
    assert rolling[later.fixture_identifier] == ((2 + 9 + 0) / 3, (1 + 0 + 9) / 3)


def test_rolling_league_histories_are_separate():
    e0 = _source([
        ("01/08/2020", "10:00", "A", "B", 4, 1),
        ("08/08/2020", "10:00", "C", "D", 1, 1),
    ], league="E0")
    sp1 = _source([
        ("01/08/2020", "10:00", "E", "F", 1, 3),
        ("08/08/2020", "10:00", "G", "H", 1, 1),
    ], league="SP1")
    corpus = build_historical_model_feature_replay_corpus((e0, sp1))
    rolling = _rolling_rates(corpus.fixtures)
    targets = {(item.identity_league, item.home_team_name): item for item in corpus.fixtures}
    assert rolling[targets[("E0", "C")].fixture_identifier] == (4.0, 1.0)
    assert rolling[targets[("SP1", "G")].fixture_identifier] == (1.0, 3.0)


def test_season_and_league_breakdowns_reconcile_and_no_group_is_silently_omitted():
    _, _, _, validation, _ = _chain()
    for summary in (validation.form_component_summary, validation.elo_fallback_component_summary):
        assert sum(item.fixture_count for item in summary.season_breakdown) == summary.metrics.fixture_count
        assert sum(item.fixture_count for item in summary.league_breakdown) == summary.metrics.fixture_count
        assert {item.group_key for item in summary.season_breakdown} == {"2020-21"}
        assert {item.group_key for item in summary.league_breakdown} == {"E0"}


def test_calibration_boundaries_are_left_closed_right_open_and_infinity_is_not_serialized():
    _, corpus, _, _, _ = _chain()
    fixture = next(item for item in corpus.fixtures if item.form_path_component_eligible)
    rates = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    evaluations = [
        _Evaluation(
            fixture=fixture,
            home_rate=rate,
            away_rate=rate,
            candidate_joint_nll=1.0,
            constant_joint_nll=1.0,
            rolling_home_rate=None,
            rolling_away_rate=None,
            rolling_joint_nll=None,
        )
        for rate in rates
    ]
    bins = _calibration(evaluations, "home")
    assert [item.count for item in bins] == [0, 1, 1, 1, 1, 1, 1]
    assert bins[-1].upper is None
    payload = historical_expected_goals_validation_specification().to_dict()
    encoded = str(payload)
    assert "inf" not in encoded.lower()


def test_canonical_bytes_are_deterministic_and_mutation_fails_revalidation():
    inputs, corpus, corpus_bytes, validation, validation_bytes = _chain()
    assert canonical_historical_expected_goals_component_validation_bytes(validation) == validation_bytes
    assert sha256_historical_expected_goals_component_validation(validation) == sha256_historical_expected_goals_component_validation(validation)
    metrics = validation.form_component_summary.metrics
    mutated_metrics = dataclasses.replace(metrics, home_mae=metrics.home_mae + 0.0001)
    mutated_summary = dataclasses.replace(validation.form_component_summary, metrics=mutated_metrics)
    mutated = dataclasses.replace(validation, form_component_summary=mutated_summary)
    with pytest.raises(HistoricalExpectedGoalsComponentValidationError):
        revalidate_historical_expected_goals_component_validation(
            source_inputs=inputs,
            corpus=corpus,
            corpus_bytes=corpus_bytes,
            validation=mutated,
            validation_bytes=canonical_historical_expected_goals_component_validation_bytes(mutated),
        )
    with pytest.raises(HistoricalExpectedGoalsComponentValidationError):
        revalidate_historical_expected_goals_component_validation(
            source_inputs=inputs,
            corpus=corpus,
            corpus_bytes=corpus_bytes,
            validation=validation,
            validation_bytes=validation_bytes + b"x",
        )


def test_no_approval_ready_or_historical_regime_state_exists():
    _, _, _, validation, _ = _chain()
    enum_values = {item.value for item in HistoricalExpectedGoalsComponent} | {item.value for item in ComparisonResult}
    assert not any("APPROVED" in item or "READY" in item or "HISTORICAL_REGIME" in item for item in enum_values)
    assert validation.historical_freshness_regime_reconstructed is False
    assert all(flag is False for flag in validation.safety.values())


def test_production_module_has_no_forbidden_runtime_dependencies_or_downstream_execution():
    path = Path(__file__).parents[1] / "domain" / "historical_expected_goals_component_validation.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called.add(node.func.attr)
    forbidden_import_fragments = ("sqlite3", "requests", "urllib", "pandas", "numpy", "scipy", "sklearn", "joblib")
    assert not any(any(fragment in name for fragment in forbidden_import_fragments) for name in imported)
    forbidden_calls = {"build_score_matrix", "ProbabilityEngine", "SportyBet"}
    assert not (forbidden_calls & called)
