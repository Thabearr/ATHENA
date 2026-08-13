from __future__ import annotations

import ast
import dataclasses
import hashlib
from pathlib import Path

import pytest

import domain.historical_expected_goals_component_validation as pr70
import domain.historical_expected_goals_successor_candidate as subject
from domain.fixture_model_features import ModelFeatureId
from domain.historical_expected_goals_component_validation import (
    HistoricalExpectedGoalsComponent,
)
from domain.historical_expected_goals_successor_candidate import (
    COMPARATOR_IDS,
    HistoricalExpectedGoalsSuccessorCandidateError,
    fit_historical_expected_goals_successor_fixture_set,
)
from domain.historical_expected_goals_successor_protocol import (
    CALIBRATION_BINS,
    build_historical_expected_goals_successor_protocol,
    canonical_historical_expected_goals_successor_protocol_bytes,
)
from domain.historical_model_feature_replay_candidate import (
    MISSING_SOURCE_TIME,
    PR31_FATIGUE_SEMANTIC_EQUIVALENCE,
    SOURCE,
    SOURCE_LOCAL_TIMEZONE_UNRESOLVED,
    HistoricalFeatureReplayStatus,
    HistoricalReplayFeatureValue,
    HistoricalReplayFixture,
)


RECEIPT_PATH = Path(
    "artifacts/research-manifests/"
    "historical-expected-goals-real-corpus-validation-receipt-v1.json"
)
MODULE_PATH = Path("domain/historical_expected_goals_successor_candidate.py")
TRAIN_SEASONS = ("2020-21", "2021-22", "2022-23", "2023-24")
EVAL_SEASONS = ("2024-25", "2025-26")


def _protocol():
    return build_historical_expected_goals_successor_protocol(
        receipt_bytes=RECEIPT_PATH.read_bytes()
    )


def _features(
    *,
    home_elo: float = 1510.0,
    away_elo: float = 1490.0,
    home_form: float = 0.62,
    away_form: float = 0.44,
    fatigue: float = 0.1,
    available: bool = True,
) -> tuple[HistoricalReplayFeatureValue, ...]:
    status = (
        HistoricalFeatureReplayStatus.AVAILABLE_RESEARCH_REPLAY
        if available
        else HistoricalFeatureReplayStatus.BLOCKED_TEMPORAL_AMBIGUITY
    )
    raw = {
        ModelFeatureId.AWAY_ELO: away_elo,
        ModelFeatureId.AWAY_FORM: away_form,
        ModelFeatureId.FATIGUE: fatigue,
        ModelFeatureId.HOME_ELO: home_elo,
        ModelFeatureId.HOME_FORM: home_form,
    }
    values: list[HistoricalReplayFeatureValue] = []
    for feature_id in sorted(ModelFeatureId, key=lambda item: item.value):
        if feature_id is ModelFeatureId.LIVE_DATA_FRESHNESS:
            values.append(
                HistoricalReplayFeatureValue(
                    feature_id=feature_id,
                    status=(
                        HistoricalFeatureReplayStatus.NOT_RECONSTRUCTIBLE_WITH_CURRENT_EVIDENCE
                        if available
                        else HistoricalFeatureReplayStatus.BLOCKED_TEMPORAL_AMBIGUITY
                    ),
                    value=None,
                    evidence_origin="TEST_SYNTHETIC_FRESHNESS_UNAVAILABLE",
                    replay_initial_state_assumption=False,
                )
            )
            continue
        values.append(
            HistoricalReplayFeatureValue(
                feature_id=feature_id,
                status=status,
                value=raw[feature_id] if available else None,
                evidence_origin="TEST_SYNTHETIC_PREMATCH_FEATURE",
                replay_initial_state_assumption=False,
            )
        )
    return tuple(values)


def _fixture(
    index: int,
    *,
    season: str,
    day: int,
    hour: int = 15,
    league: str = "E0",
    home_goals: int | None = None,
    away_goals: int | None = None,
    home_elo: float | None = None,
    away_elo: float | None = None,
    home_form: float | None = None,
    away_form: float | None = None,
    fatigue: float | None = None,
    available: bool = True,
    missing_time: bool = False,
) -> HistoricalReplayFixture:
    year = int(season[:4])
    date = datetime.date(year, 8, day)
    kickoff = None if missing_time else datetime.datetime(year, 8, day, hour, 0)
    h_elo = 1375.0 + ((index * 53) % 301) if home_elo is None else home_elo
    a_elo = 1390.0 + ((index * 71) % 287) if away_elo is None else away_elo
    h_form = 0.12 + ((index * 17) % 70) / 100.0 if home_form is None else home_form
    a_form = 0.11 + ((index * 29) % 72) / 100.0 if away_form is None else away_form
    fat = (0.0, 0.1, 0.3)[index % 3] if fatigue is None else fatigue
    h_goals = (1, 2, 0, 3, 1, 4, 2, 1)[index % 8] if home_goals is None else home_goals
    a_goals = (0, 1, 2, 1, 3, 0, 2, 1)[(index * 3) % 8] if away_goals is None else away_goals
    return HistoricalReplayFixture(
        fixture_identifier=f"synthetic-fixture-{season}-{index:04d}",
        source=SOURCE,
        season=season,
        observed_league=league,
        identity_league=league,
        source_local_date=date,
        source_local_kickoff=kickoff,
        kickoff_timezone_status=(
            MISSING_SOURCE_TIME if missing_time else SOURCE_LOCAL_TIMEZONE_UNRESOLVED
        ),
        home_source_team_identifier=f"{SOURCE}:team:home-{index}",
        away_source_team_identifier=f"{SOURCE}:team:away-{index}",
        home_team_name=f"Home {index}",
        away_team_name=f"Away {index}",
        home_goals=h_goals,
        away_goals=a_goals,
        source_file_sha256="0" * 64,
        source_row_number=index + 2,
        features=_features(
            home_elo=h_elo,
            away_elo=a_elo,
            home_form=h_form,
            away_form=a_form,
            fatigue=fat,
            available=available,
        ),
        fatigue_pr31_semantic_equivalence=PR31_FATIGUE_SEMANTIC_EQUIVALENCE,
        form_path_component_eligible=available,
        elo_fallback_component_eligible=available,
    )


def _fixture_set() -> tuple[HistoricalReplayFixture, ...]:
    fixtures: list[HistoricalReplayFixture] = []
    index = 1
    leagues = ("E0", "E1", "SP1")
    for season in TRAIN_SEASONS:
        for offset in range(12):
            fixtures.append(
                _fixture(
                    index,
                    season=season,
                    day=offset + 1,
                    league=leagues[offset % len(leagues)],
                )
            )
            index += 1
    for season in EVAL_SEASONS:
        for offset in range(6):
            fixtures.append(
                _fixture(
                    index,
                    season=season,
                    day=offset + 1,
                    league=leagues[offset % len(leagues)],
                )
            )
            index += 1
    return tuple(fixtures)


def test_frozen_fixture_set_fit_is_deterministic_and_complete() -> None:
    protocol = _protocol()
    fixtures = _fixture_set()
    first = fit_historical_expected_goals_successor_fixture_set(
        protocol=protocol, fixtures=fixtures
    )
    second = fit_historical_expected_goals_successor_fixture_set(
        protocol=protocol, fixtures=tuple(reversed(fixtures))
    )
    assert first == second
    assert first.training_fixture_count == 48
    assert first.evaluation_fixture_count == 12
    assert tuple(first.training_season_counts) == TRAIN_SEASONS
    assert tuple(first.evaluation_season_counts) == EVAL_SEASONS
    assert first.home_fit.training_fixture_count == 48
    assert first.away_fit.training_fixture_count == 48
    assert len(first.home_fit.coefficients) == 6
    assert len(first.away_fit.coefficients) == 6
    assert all(value == round(value, 12) for value in first.home_fit.coefficients)
    assert all(value == round(value, 12) for value in first.away_fit.coefficients)
    assert tuple(item.benchmark_id for item in first.comparisons) == COMPARATOR_IDS
    assert first.metrics.fixture_count == 12
    assert tuple(item.group_key for item in first.season_breakdown) == EVAL_SEASONS
    assert tuple((item.lower, item.upper) for item in first.home_calibration) == CALIBRATION_BINS
    assert tuple((item.lower, item.upper) for item in first.away_calibration) == CALIBRATION_BINS


def test_evaluation_outcomes_cannot_change_fitted_coefficients() -> None:
    protocol = _protocol()
    fixtures = _fixture_set()
    baseline = fit_historical_expected_goals_successor_fixture_set(
        protocol=protocol, fixtures=fixtures
    )
    mutated = tuple(
        dataclasses.replace(
            fixture,
            home_goals=fixture.home_goals + 4,
            away_goals=fixture.away_goals + 3,
        )
        if fixture.season in EVAL_SEASONS
        else fixture
        for fixture in fixtures
    )
    changed = fit_historical_expected_goals_successor_fixture_set(
        protocol=protocol, fixtures=mutated
    )
    assert changed.home_fit == baseline.home_fit
    assert changed.away_fit == baseline.away_fit
    assert changed.metrics != baseline.metrics


def test_evaluation_features_cannot_change_fitted_coefficients() -> None:
    protocol = _protocol()
    fixtures = _fixture_set()
    baseline = fit_historical_expected_goals_successor_fixture_set(
        protocol=protocol, fixtures=fixtures
    )
    mutated = tuple(
        dataclasses.replace(
            fixture,
            features=_features(
                home_elo=1700.0,
                away_elo=1300.0,
                home_form=0.85,
                away_form=0.15,
                fatigue=0.3,
            ),
        )
        if fixture.season in EVAL_SEASONS
        else fixture
        for fixture in fixtures
    )
    changed = fit_historical_expected_goals_successor_fixture_set(
        protocol=protocol, fixtures=mutated
    )
    assert changed.home_fit == baseline.home_fit
    assert changed.away_fit == baseline.away_fit
    assert changed.metrics != baseline.metrics


def test_target_evaluation_outcome_does_not_enter_its_rate() -> None:
    protocol = _protocol()
    result = fit_historical_expected_goals_successor_fixture_set(
        protocol=protocol, fixtures=_fixture_set()
    )
    fixture = next(item for item in _fixture_set() if item.season == "2024-25")
    mutated = dataclasses.replace(fixture, home_goals=9, away_goals=8)
    first = subject._model_rates(protocol, fixture, result.home_fit, result.away_fit)
    second = subject._model_rates(protocol, mutated, result.home_fit, result.away_fit)
    assert first == second


def test_legacy_comparator_formula_matches_pr70_exactly() -> None:
    fixtures = _fixture_set()[::7]
    for fixture in fixtures:
        assert subject._legacy_rates(
            fixture, HistoricalExpectedGoalsComponent.FORM_COMPONENT
        ) == pr70._candidate_rates(  # type: ignore[attr-defined]
            fixture, HistoricalExpectedGoalsComponent.FORM_COMPONENT
        )
        assert subject._legacy_rates(
            fixture, HistoricalExpectedGoalsComponent.ELO_FALLBACK_COMPONENT
        ) == pr70._candidate_rates(  # type: ignore[attr-defined]
            fixture, HistoricalExpectedGoalsComponent.ELO_FALLBACK_COMPONENT
        )


def test_rolling_baseline_matches_pr70_same_time_and_missing_time_semantics() -> None:
    fixtures = list(_fixture_set()[:6])
    fixtures.append(
        _fixture(
            500,
            season="2020-21",
            day=20,
            league="E0",
            available=False,
            missing_time=True,
        )
    )
    fixtures.append(
        _fixture(501, season="2020-21", day=21, hour=15, league="E0")
    )
    fixtures.append(
        _fixture(502, season="2020-21", day=21, hour=15, league="E0")
    )
    assert dict(subject._rolling_rates(fixtures)) == dict(  # type: ignore[attr-defined]
        pr70._rolling_rates(fixtures)  # type: ignore[attr-defined]
    )


def test_blocked_fixture_is_excluded_without_defaulting() -> None:
    protocol = _protocol()
    fixtures = _fixture_set()
    blocked = _fixture(
        600,
        season="2020-21",
        day=25,
        league="E0",
        available=False,
    )
    result = fit_historical_expected_goals_successor_fixture_set(
        protocol=protocol, fixtures=fixtures + (blocked,)
    )
    assert result.training_fixture_count == 48
    assert result.evaluation_fixture_count == 12


def test_eligible_missing_kickoff_fails_closed() -> None:
    protocol = _protocol()
    fixtures = list(_fixture_set())
    target = next(index for index, item in enumerate(fixtures) if item.season == "2020-21")
    fixture = fixtures[target]
    fixtures[target] = dataclasses.replace(
        fixture,
        source_local_kickoff=None,
        kickoff_timezone_status=MISSING_SOURCE_TIME,
    )
    with pytest.raises(HistoricalExpectedGoalsSuccessorCandidateError, match="kickoff"):
        fit_historical_expected_goals_successor_fixture_set(
            protocol=protocol, fixtures=fixtures
        )


def test_fixture_outside_frozen_seasons_fails_closed() -> None:
    fixtures = _fixture_set() + (
        _fixture(700, season="2026-27", day=1, league="E0"),
    )
    with pytest.raises(HistoricalExpectedGoalsSuccessorCandidateError, match="outside"):
        fit_historical_expected_goals_successor_fixture_set(
            protocol=_protocol(), fixtures=fixtures
        )


def test_zero_training_response_mean_fails_closed() -> None:
    fixtures = tuple(
        dataclasses.replace(fixture, home_goals=0)
        if fixture.season in TRAIN_SEASONS
        else fixture
        for fixture in _fixture_set()
    )
    with pytest.raises(HistoricalExpectedGoalsSuccessorCandidateError, match="response mean"):
        fit_historical_expected_goals_successor_fixture_set(
            protocol=_protocol(), fixtures=fixtures
        )


def test_rank_deficient_newton_system_fails_closed() -> None:
    fixtures: list[HistoricalReplayFixture] = []
    index = 800
    for season in TRAIN_SEASONS:
        for offset in range(8):
            shared_elo = 1400.0 + 25.0 * offset
            fixtures.append(
                _fixture(
                    index,
                    season=season,
                    day=offset + 1,
                    home_elo=shared_elo,
                    away_elo=shared_elo,
                    home_form=0.2 + 0.05 * offset,
                    away_form=0.7 - 0.04 * offset,
                    fatigue=(0.0, 0.1, 0.3)[offset % 3],
                )
            )
            index += 1
    for season in EVAL_SEASONS:
        for offset in range(3):
            fixtures.append(_fixture(index, season=season, day=offset + 1))
            index += 1
    with pytest.raises(HistoricalExpectedGoalsSuccessorCandidateError, match="singular"):
        fit_historical_expected_goals_successor_fixture_set(
            protocol=_protocol(), fixtures=fixtures
        )


def test_global_duplicate_fixture_identity_fails_even_across_train_eval_slices() -> None:
    fixtures = list(_fixture_set())
    training_fixture = next(item for item in fixtures if item.season == "2020-21")
    evaluation_index = next(
        index for index, item in enumerate(fixtures) if item.season == "2024-25"
    )
    fixtures[evaluation_index] = dataclasses.replace(
        fixtures[evaluation_index], fixture_identifier=training_fixture.fixture_identifier
    )
    with pytest.raises(HistoricalExpectedGoalsSuccessorCandidateError, match="globally unique"):
        fit_historical_expected_goals_successor_fixture_set(
            protocol=_protocol(), fixtures=fixtures
        )


def test_group_comparator_candidate_mean_must_reconcile_to_group_candidate_mean() -> None:
    result = fit_historical_expected_goals_successor_fixture_set(
        protocol=_protocol(), fixtures=_fixture_set()
    )
    group = result.season_breakdown[0]
    original = group.comparisons[0]
    assert original.candidate_mean_joint_nll is not None
    assert original.benchmark_mean_joint_nll is not None
    mutated = dataclasses.replace(
        original,
        candidate_mean_joint_nll=original.candidate_mean_joint_nll + 0.1,
        benchmark_mean_joint_nll=original.benchmark_mean_joint_nll + 0.1,
    )
    with pytest.raises(HistoricalExpectedGoalsSuccessorCandidateError, match="group comparator candidate NLL"):
        dataclasses.replace(
            group,
            comparisons=(mutated, *group.comparisons[1:]),
        )


def test_high_level_builder_refuses_detached_fake_corpus() -> None:
    protocol = _protocol()
    protocol_bytes = canonical_historical_expected_goals_successor_protocol_bytes(protocol)
    with pytest.raises(
        HistoricalExpectedGoalsSuccessorCandidateError,
        match="PR69 source-byte replay revalidation failed",
    ):
        subject.build_historical_expected_goals_successor_candidate(
            source_inputs=(),
            corpus=None,  # type: ignore[arg-type]
            corpus_bytes=b"not-a-corpus",
            receipt_bytes=RECEIPT_PATH.read_bytes(),
            protocol=protocol,
            protocol_bytes=protocol_bytes,
        )


def test_safety_mapping_cannot_be_promoted() -> None:
    safety = dict(subject._default_safety())  # type: ignore[attr-defined]
    assert safety
    assert all(value is False for value in safety.values())
    safety["bet_authorized"] = True
    with pytest.raises(HistoricalExpectedGoalsSuccessorCandidateError, match="False"):
        subject._validate_safety(safety)  # type: ignore[attr-defined]


def test_protocol_controls_are_consumed_instead_of_reopened() -> None:
    protocol = _protocol()
    assert protocol.fitting.algorithm == subject.TRAINING_ENGINE_ID
    assert tuple(protocol.evaluation.legacy_comparators) == COMPARATOR_IDS
    assert protocol.fitting.hyperparameter_search_authorized is False
    assert protocol.fitting.refit_after_evaluation_authorized is False
    assert protocol.evaluation.approval_threshold is None


def test_source_excludes_forbidden_runtime_and_training_shortcuts() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots: set[str] = set()
    called_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called_names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called_names.add(node.func.attr)
    assert not imported_roots.intersection(
        {"sqlite3", "requests", "urllib", "pandas", "numpy", "scipy", "sklearn", "joblib"}
    )
    assert not called_names.intersection(
        {
            "open",
            "build_score_matrix",
            "ProbabilityEngine",
            "SportyBet",
            "pricing",
            "selection",
            "betting",
        }
    )
    assert "math.fsum" in source
    assert ".cache/football-data-uk" not in source
    assert "hyperparameter" not in source.casefold() or "hyperparameter_search_authorized" in source


def test_no_real_successor_coefficients_or_result_receipt_are_tracked() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "REAL_CORPUS_SUCCESSOR_RESULT" not in source
    assert "learned_coefficients" not in source
    assert "production_ready" not in source.casefold()
    assert "bet_ready" not in source.casefold()
