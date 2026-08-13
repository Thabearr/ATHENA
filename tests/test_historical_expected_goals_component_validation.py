from __future__ import annotations

import ast
import dataclasses
import math
from pathlib import Path

import pytest

from domain.fixture_model_features import ModelFeatureId, ModelFeatureStatus
from domain.fotmob_reviewed_match_details_expected_goals_transform_candidate import (
    ExpectedGoalsFeatureAudit,
    _rates_from_audits as pr68_rates,
    legacy_expected_goals_transform_specification,
)
from domain.historical_expected_goals_component_validation import (
    CONSTANT_BASELINE_ID,
    DATASET_NAME,
    ROLLING_BASELINE_ID,
    VALIDATION_SCOPE,
    BenchmarkComparison,
    ComparisonResult,
    HistoricalExpectedGoalsComponent,
    HistoricalExpectedGoalsComponentValidationError,
    _Evaluation,
    _benchmark,
    _calibration,
    _candidate_rates,
    _rolling_rates,
    build_historical_expected_goals_component_validation,
    canonical_historical_expected_goals_component_validation_bytes,
    poisson_nll,
    revalidate_historical_expected_goals_component_validation,
)
from domain.historical_model_feature_replay_candidate import (
    HistoricalFeatureReplayStatus,
    HistoricalReplayFeatureValue,
    HistoricalReplaySourceInput,
    build_historical_model_feature_replay_corpus,
    canonical_historical_model_feature_replay_corpus_bytes,
)


def _csv(rows, div="E0") -> bytes:
    lines = ["Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR"]
    for date, time, home, away, hg, ag in rows:
        result = "H" if hg > ag else "A" if hg < ag else "D"
        lines.append(f"{div},{date},{time},{home},{away},{hg},{ag},{result},,,")
    return ("\n".join(lines) + "\n").encode()


def _rows():
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


def _source(rows=None, *, season="2020-21", league="E0"):
    return HistoricalReplaySourceInput(
        season=season,
        acquisition_league=league,
        raw_bytes=_csv(_rows() if rows is None else rows, league),
    )


def _chain(inputs=None):
    inputs = inputs or (_source(),)
    corpus = build_historical_model_feature_replay_corpus(inputs)
    corpus_bytes = canonical_historical_model_feature_replay_corpus_bytes(corpus)
    validation = build_historical_expected_goals_component_validation(
        source_inputs=inputs, corpus=corpus, corpus_bytes=corpus_bytes
    )
    validation_bytes = canonical_historical_expected_goals_component_validation_bytes(validation)
    return inputs, corpus, corpus_bytes, validation, validation_bytes


def _feature(feature_id, value):
    return HistoricalReplayFeatureValue(
        feature_id=feature_id,
        status=HistoricalFeatureReplayStatus.AVAILABLE_RESEARCH_REPLAY,
        value=float(value),
        evidence_origin="SYNTHETIC_TEST_REPLAY",
        replay_initial_state_assumption=False,
    )


def _synthetic_fixture(corpus, **values):
    base = next(f for f in corpus.fixtures if f.form_path_component_eligible and f.elo_fallback_component_eligible)
    defaults = dict(home_form=.7, away_form=.3, home_elo=1600, away_elo=1400, fatigue=.1)
    defaults.update(values)
    mapping = {
        ModelFeatureId.HOME_FORM: _feature(ModelFeatureId.HOME_FORM, defaults["home_form"]),
        ModelFeatureId.AWAY_FORM: _feature(ModelFeatureId.AWAY_FORM, defaults["away_form"]),
        ModelFeatureId.HOME_ELO: _feature(ModelFeatureId.HOME_ELO, defaults["home_elo"]),
        ModelFeatureId.AWAY_ELO: _feature(ModelFeatureId.AWAY_ELO, defaults["away_elo"]),
        ModelFeatureId.FATIGUE: _feature(ModelFeatureId.FATIGUE, defaults["fatigue"]),
        ModelFeatureId.LIVE_DATA_FRESHNESS: HistoricalReplayFeatureValue(
            feature_id=ModelFeatureId.LIVE_DATA_FRESHNESS,
            status=HistoricalFeatureReplayStatus.NOT_RECONSTRUCTIBLE_WITH_CURRENT_EVIDENCE,
            value=None,
            evidence_origin="NO_RETAINED_PRE_KICKOFF_FRESHNESS_EVIDENCE",
            replay_initial_state_assumption=False,
        ),
    }
    return dataclasses.replace(
        base,
        features=tuple(mapping[k] for k in sorted(ModelFeatureId, key=lambda x: x.value)),
        form_path_component_eligible=True,
        elo_fallback_component_eligible=True,
    )


def _audits(*, home_form, away_form, home_elo, away_elo, fatigue, freshness):
    values = {
        ModelFeatureId.HOME_FORM: home_form,
        ModelFeatureId.AWAY_FORM: away_form,
        ModelFeatureId.HOME_ELO: home_elo,
        ModelFeatureId.AWAY_ELO: away_elo,
        ModelFeatureId.FATIGUE: fatigue,
        ModelFeatureId.LIVE_DATA_FRESHNESS: freshness,
    }
    return tuple(
        ExpectedGoalsFeatureAudit(
            feature_id=k, status=ModelFeatureStatus.AVAILABLE, value=float(values[k]), blockers=(), evidence_sha256s=()
        )
        for k in sorted(ModelFeatureId, key=lambda x: x.value)
    )


def test_full_chain_binds_pr69_and_revalidates_exact_bytes():
    inputs, corpus, corpus_bytes, validation, validation_bytes = _chain()
    assert validation.dataset_name == DATASET_NAME
    assert validation.validation_scope == VALIDATION_SCOPE
    assert validation.historical_freshness_regime_reconstructed is False
    assert all(v is False for v in validation.safety.values())
    assert revalidate_historical_expected_goals_component_validation(
        source_inputs=inputs, corpus=corpus, corpus_bytes=corpus_bytes,
        validation=validation, validation_bytes=validation_bytes
    ) == validation


def test_source_corpus_and_validation_mutations_fail_closed():
    inputs, corpus, corpus_bytes, validation, validation_bytes = _chain()
    changed = dataclasses.replace(inputs[0], raw_bytes=inputs[0].raw_bytes.replace(b"3,1,H", b"4,1,H"))
    with pytest.raises(HistoricalExpectedGoalsComponentValidationError):
        revalidate_historical_expected_goals_component_validation(
            source_inputs=(changed,), corpus=corpus, corpus_bytes=corpus_bytes,
            validation=validation, validation_bytes=validation_bytes
        )
    with pytest.raises(HistoricalExpectedGoalsComponentValidationError):
        build_historical_expected_goals_component_validation(
            source_inputs=inputs, corpus=corpus, corpus_bytes=corpus_bytes + b"x"
        )
    bad = dataclasses.replace(
        validation.form_component_summary.metrics,
        home_mae=validation.form_component_summary.metrics.home_mae + 0.001,
    )
    mutated = dataclasses.replace(
        validation,
        form_component_summary=dataclasses.replace(validation.form_component_summary, metrics=bad),
    )
    with pytest.raises(HistoricalExpectedGoalsComponentValidationError):
        revalidate_historical_expected_goals_component_validation(
            source_inputs=inputs, corpus=corpus, corpus_bytes=corpus_bytes,
            validation=mutated,
            validation_bytes=canonical_historical_expected_goals_component_validation_bytes(mutated),
        )


@pytest.mark.parametrize(
    "component,fixture_kwargs,freshness",
    [
        (HistoricalExpectedGoalsComponent.FORM_COMPONENT, dict(home_form=.71, away_form=.26, fatigue=.1), .05),
        (HistoricalExpectedGoalsComponent.ELO_FALLBACK_COMPONENT, dict(home_elo=5000, away_elo=-1000, fatigue=.3), .049),
    ],
)
def test_component_rates_match_frozen_pr68(component, fixture_kwargs, freshness):
    _, corpus, *_ = _chain()
    fixture = _synthetic_fixture(corpus, **fixture_kwargs)
    audit_kwargs = dict(home_form=.71, away_form=.26, home_elo=5000, away_elo=-1000, fatigue=fixture_kwargs["fatigue"], freshness=freshness)
    expected = pr68_rates(_audits(**audit_kwargs), legacy_expected_goals_transform_specification())
    assert _candidate_rates(fixture, component) == expected


def test_floor_rounding_and_target_outcome_independence():
    _, corpus, *_ = _chain()
    fixture = _synthetic_fixture(corpus, home_form=.1004, away_form=.8996, fatigue=10)
    rates = _candidate_rates(fixture, HistoricalExpectedGoalsComponent.FORM_COMPONENT)
    assert rates[0] == legacy_expected_goals_transform_specification().minimum_rate
    changed = dataclasses.replace(fixture, home_goals=9, away_goals=8)
    assert _candidate_rates(changed, HistoricalExpectedGoalsComponent.FORM_COMPONENT) == rates


def test_poisson_absolute_nll_and_nonpositive_rate_rejected():
    assert poisson_nll(0, 1.0) == 1.0
    assert poisson_nll(3, 2.5) == 2.5 - 3 * math.log(2.5) + math.lgamma(4)
    for rate in (0.0, -1.0):
        with pytest.raises(HistoricalExpectedGoalsComponentValidationError):
            poisson_nll(1, rate)


def test_constant_baseline_and_zero_pair_rolling_state():
    _, _, _, validation, _ = _chain()
    for summary in (validation.form_component_summary, validation.elo_fallback_component_summary):
        assert summary.constant_baseline.paired_fixture_count == summary.metrics.fixture_count
        assert summary.constant_baseline.candidate_mean_joint_nll == summary.metrics.mean_joint_poisson_nll
    empty = _benchmark(ROLLING_BASELINE_ID, [], [])
    assert empty == BenchmarkComparison(ROLLING_BASELINE_ID, 0, None, None, None, None)
    assert BenchmarkComparison(CONSTANT_BASELINE_ID, 1, 1.0, 2.0, -1.0, ComparisonResult.BETTER).result is ComparisonResult.BETTER


def test_same_kickoff_is_batched_and_future_results_do_not_leak():
    rows = [
        ("01/08/2020", "10:00", "A", "B", 2, 1),
        ("08/08/2020", "12:00", "C", "D", 9, 0),
        ("08/08/2020", "12:00", "E", "F", 0, 9),
        ("15/08/2020", "12:00", "G", "H", 1, 1),
    ]
    corpus = build_historical_model_feature_replay_corpus((_source(rows),))
    rolling = _rolling_rates(corpus.fixtures)
    by = {(f.home_team_name, f.away_team_name): f for f in corpus.fixtures}
    assert rolling[by[("C", "D")].fixture_identifier] == (2.0, 1.0)
    assert rolling[by[("E", "F")].fixture_identifier] == (2.0, 1.0)
    assert rolling[by[("G", "H")].fixture_identifier] == (11 / 3, 10 / 3)


def test_missing_source_time_blocks_same_date_but_recovers_for_later_dates():
    rows = [
        ("01/08/2020", "10:00", "A", "B", 2, 1),
        ("08/08/2020", "", "C", "D", 4, 2),
        ("08/08/2020", "12:00", "E", "F", 1, 1),
        ("15/08/2020", "12:00", "G", "H", 3, 2),
    ]
    corpus = build_historical_model_feature_replay_corpus((_source(rows),))
    rolling = _rolling_rates(corpus.fixtures)
    by = {(f.home_team_name, f.away_team_name): f for f in corpus.fixtures}
    assert rolling[by[("C", "D")].fixture_identifier] is None
    assert rolling[by[("E", "F")].fixture_identifier] is None
    assert rolling[by[("G", "H")].fixture_identifier] == (7 / 3, 4 / 3)


def test_league_histories_remain_separate():
    e0 = _source([("01/08/2020", "10:00", "A", "B", 4, 1), ("08/08/2020", "10:00", "C", "D", 1, 1)], league="E0")
    sp1 = _source([("01/08/2020", "10:00", "E", "F", 1, 3), ("08/08/2020", "10:00", "G", "H", 1, 1)], league="SP1")
    corpus = build_historical_model_feature_replay_corpus((e0, sp1))
    rolling = _rolling_rates(corpus.fixtures)
    targets = {(f.identity_league, f.home_team_name): f for f in corpus.fixtures}
    assert rolling[targets[("E0", "C")].fixture_identifier] == (4.0, 1.0)
    assert rolling[targets[("SP1", "G")].fixture_identifier] == (1.0, 3.0)


def test_breakdowns_and_rolling_counts_reconcile():
    _, _, _, validation, _ = _chain()
    for summary in (validation.form_component_summary, validation.elo_fallback_component_summary):
        for groups in (summary.season_breakdown, summary.league_breakdown):
            assert sum(g.fixture_count for g in groups) == summary.metrics.fixture_count
            assert sum(g.rolling_paired_fixture_count for g in groups) == summary.rolling_league_baseline.paired_fixture_count


def test_calibration_bins_boundaries_and_invalid_side():
    _, corpus, *_ = _chain()
    fixture = next(f for f in corpus.fixtures if f.form_path_component_eligible)
    evals = [
        _Evaluation(fixture, r, r, 1.0, 1.0, None, None, None)
        for r in (.5, 1.0, 1.5, 2.0, 2.5, 3.0)
    ]
    bins = _calibration(evals, "home")
    assert [b.count for b in bins] == [0, 1, 1, 1, 1, 1, 1]
    assert bins[-1].upper is None
    with pytest.raises(HistoricalExpectedGoalsComponentValidationError):
        _calibration(evals, "neutral")


def test_summary_invariants_reject_impossible_rolling_reconciliation():
    _, _, _, validation, _ = _chain()
    summary = validation.form_component_summary
    group = summary.season_breakdown[0]
    impossible = dataclasses.replace(group, rolling_paired_fixture_count=group.fixture_count + 1)
    with pytest.raises(HistoricalExpectedGoalsComponentValidationError):
        dataclasses.replace(summary, season_breakdown=(impossible,))


def test_no_approval_state_and_runtime_dependencies_are_forbidden():
    _, _, _, validation, _ = _chain()
    assert all(v is False for v in validation.safety.values())
    assert validation.historical_freshness_regime_reconstructed is False
    assert not any("APPROVED" in x.value or "READY" in x.value for x in HistoricalExpectedGoalsComponent)
    path = Path(__file__).parents[1] / "domain" / "historical_expected_goals_component_validation.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported, called = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.Call):
            called.add(node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else "")
    assert not any(fragment in name for name in imported for fragment in ("sqlite3", "requests", "urllib", "pandas", "numpy", "scipy", "sklearn", "joblib"))
    assert not ({"build_score_matrix", "ProbabilityEngine", "SportyBet"} & called)
