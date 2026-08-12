from __future__ import annotations

import ast
import hashlib
import inspect
import math

import pytest

from domain.fixture_model_features import ModelFeatureId
from domain.historical_model_feature_replay_candidate import (
    DATASET_NAME,
    MISSING_SOURCE_TIME,
    PR31_FATIGUE_SEMANTIC_EQUIVALENCE,
    REPLAY_SCOPE,
    SOURCE,
    SOURCE_LOCAL_TIMEZONE_UNRESOLVED,
    HistoricalFeatureReplayStatus,
    HistoricalModelFeatureReplayCandidateError,
    HistoricalReplaySourceInput,
    build_historical_model_feature_replay_corpus,
    canonical_historical_model_feature_replay_corpus_bytes,
    revalidate_historical_model_feature_replay_corpus,
    sha256_historical_model_feature_replay_corpus,
)
from scripts.import_football_data_uk import (
    deterministic_fixture_identity,
    deterministic_team_identity,
)


def _csv(rows: list[str]) -> bytes:
    return (
        "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR\n"
        + "\n".join(rows)
        + "\n"
    ).encode("utf-8")


def _row(date: str, time: str, home: str, away: str, hg: int, ag: int) -> str:
    result = "H" if hg > ag else "A" if hg < ag else "D"
    return f"E0,{date},{time},{home},{away},{hg},{ag},{result},0,0,D"


def _source(rows: list[str], season: str = "2020-21", league: str = "E0"):
    return HistoricalReplaySourceInput(season, league, _csv(rows))


def _build(rows: list[str]):
    source = _source(rows)
    corpus = build_historical_model_feature_replay_corpus((source,))
    return corpus, canonical_historical_model_feature_replay_corpus_bytes(corpus), source


def _fixture_for(corpus, home: str, away: str):
    return next(item for item in corpus.fixtures if item.home_team_name == home and item.away_team_name == away)


def _feature(fixture, feature_id: ModelFeatureId):
    return next(item for item in fixture.features if item.feature_id is feature_id)


def test_contract_source_identity_and_determinism():
    rows = [
        _row("01/08/2020", "12:00", "A", "B", 1, 0),
        _row("08/08/2020", "12:00", "A", "C", 0, 0),
    ]
    corpus, corpus_bytes, source = _build(rows)
    assert corpus.dataset_name == DATASET_NAME
    assert corpus.scope == REPLAY_SCOPE
    assert corpus.fixture_count == 2
    assert corpus.source_files[0].raw_sha256 == hashlib.sha256(source.raw_bytes).hexdigest()
    assert corpus.source_files[0].raw_size == len(source.raw_bytes)
    assert corpus.source_files[0].source_row_count == 2
    assert canonical_historical_model_feature_replay_corpus_bytes(corpus) == corpus_bytes
    assert sha256_historical_model_feature_replay_corpus(corpus) == hashlib.sha256(corpus_bytes).hexdigest()
    assert revalidate_historical_model_feature_replay_corpus(source_inputs=(source,), corpus=corpus, corpus_bytes=corpus_bytes) == corpus
    fixture = _fixture_for(corpus, "A", "B")
    assert fixture.source == SOURCE
    assert fixture.fixture_identifier.startswith(f"{SOURCE}:")
    assert fixture.home_source_team_identifier.startswith(f"{SOURCE}:team:")
    assert fixture.kickoff_timezone_status == SOURCE_LOCAL_TIMEZONE_UNRESOLVED
    assert fixture.source_local_kickoff.tzinfo is None


def test_source_scoped_identity_has_exact_importer_parity_without_fuzzy_matching():
    corpus, _, _ = _build([_row("01/08/2020", "12:00", "Malmö FF", "São Paulo", 1, 0)])
    fixture = corpus.fixtures[0]
    _, fixture_fingerprint = deterministic_fixture_identity(
        season="2020-21",
        league="E0",
        match_date="2020-08-01",
        match_time="12:00",
        home_team="Malmö FF",
        away_team="São Paulo",
    )
    assert fixture.fixture_identifier == f"{SOURCE}:{fixture_fingerprint}"
    assert fixture.home_source_team_identifier == f"{SOURCE}:team:{deterministic_team_identity('Malmö FF')}"
    assert fixture.away_source_team_identifier == f"{SOURCE}:team:{deterministic_team_identity('São Paulo')}"
    changed, _, _ = _build([_row("01/08/2020", "12:00", "Malmo FF", "São Paulo", 1, 0)])
    assert changed.fixtures[0].home_source_team_identifier != fixture.home_source_team_identifier


def test_blank_div_preserves_acquisition_only_identity_context_not_observed_league():
    raw = (
        b"Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR\n"
        b",01/08/2020,12:00,A,B,1,0,H,0,0,D\n"
    )
    source = HistoricalReplaySourceInput("2020-21", "E0", raw)
    corpus = build_historical_model_feature_replay_corpus((source,))
    fixture = corpus.fixtures[0]
    _, fingerprint = deterministic_fixture_identity(
        season="2020-21",
        league="E0",
        match_date="2020-08-01",
        match_time="12:00",
        home_team="A",
        away_team="B",
    )
    assert corpus.source_files[0].acquisition_league == "E0"
    assert fixture.fixture_identifier == f"{SOURCE}:{fingerprint}"
    assert fixture.identity_league == "E0"
    assert fixture.observed_league is None
    assert '"observed_league":null' in canonical_historical_model_feature_replay_corpus_bytes(corpus).decode("utf-8")


def test_nonblank_div_remains_observed_league_and_identity_parity():
    corpus, _, _ = _build([_row("01/08/2020", "12:00", "A", "B", 1, 0)])
    fixture = corpus.fixtures[0]
    assert fixture.observed_league == "E0"
    assert fixture.identity_league == "E0"


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"Div,Date\nE0,01/08/2020\n",
        b"Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR\nE0,bad,12:00,A,B,1,0,H,0,0,D\n",
        b"Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR\nE0,01/08/2020,12:00,A,B,1,0,A,0,0,D\n",
    ],
)
def test_bad_source_bytes_fail_closed(raw):
    with pytest.raises(HistoricalModelFeatureReplayCandidateError):
        build_historical_model_feature_replay_corpus((HistoricalReplaySourceInput("2020-21", "E0", raw),))


def test_duplicate_identity_missing_time_and_same_team_collision_fail_closed_temporally():
    duplicate = _source([_row("01/08/2020", "12:00", "A", "B", 1, 0), _row("01/08/2020", "12:00", "A", "B", 1, 0)])
    with pytest.raises(HistoricalModelFeatureReplayCandidateError, match="duplicate"):
        build_historical_model_feature_replay_corpus((duplicate,))
    missing, _, _ = _build([_row("01/08/2020", "", "A", "B", 1, 0)])
    item = missing.fixtures[0]
    assert item.kickoff_timezone_status == MISSING_SOURCE_TIME
    assert all(feature.value is None for feature in item.features)
    assert _feature(item, ModelFeatureId.HOME_FORM).status is HistoricalFeatureReplayStatus.BLOCKED_TEMPORAL_AMBIGUITY
    collision, _, _ = _build([
        _row("01/08/2020", "12:00", "A", "B", 1, 0),
        _row("01/08/2020", "12:00", "A", "C", 1, 0),
    ])
    assert all(_feature(item, ModelFeatureId.HOME_ELO).status is HistoricalFeatureReplayStatus.BLOCKED_TEMPORAL_AMBIGUITY for item in collision.fixtures)


def test_missing_time_taints_later_team_state_and_opponent_propagation():
    corpus, _, _ = _build([
        _row("01/08/2020", "", "A", "B", 1, 0),
        _row("08/08/2020", "12:00", "A", "C", 1, 0),
        _row("15/08/2020", "12:00", "C", "D", 1, 0),
    ])
    first = _fixture_for(corpus, "A", "B")
    second = _fixture_for(corpus, "A", "C")
    third = _fixture_for(corpus, "C", "D")
    assert _feature(first, ModelFeatureId.HOME_ELO).status is HistoricalFeatureReplayStatus.BLOCKED_TEMPORAL_AMBIGUITY
    for fixture in (second, third):
        assert all(
            _feature(fixture, feature_id).status is HistoricalFeatureReplayStatus.BLOCKED_TEMPORAL_AMBIGUITY
            for feature_id in (
                ModelFeatureId.HOME_FORM,
                ModelFeatureId.AWAY_FORM,
                ModelFeatureId.HOME_ELO,
                ModelFeatureId.AWAY_ELO,
                ModelFeatureId.FATIGUE,
            )
        )


def test_same_kickoff_collision_taints_later_team_state_without_target_result_leakage():
    corpus, _, _ = _build([
        _row("01/08/2020", "12:00", "A", "B", 1, 0),
        _row("01/08/2020", "12:00", "A", "C", 1, 0),
        _row("08/08/2020", "12:00", "A", "D", 9, 0),
    ])
    later = _fixture_for(corpus, "A", "D")
    assert all(
        _feature(later, feature_id).status is HistoricalFeatureReplayStatus.BLOCKED_TEMPORAL_AMBIGUITY
        for feature_id in (
            ModelFeatureId.HOME_FORM,
            ModelFeatureId.AWAY_FORM,
            ModelFeatureId.HOME_ELO,
            ModelFeatureId.AWAY_ELO,
            ModelFeatureId.FATIGUE,
        )
    )
    assert _feature(later, ModelFeatureId.HOME_FORM).value is None


def test_form_is_strict_prior_limited_scaled_and_never_defaults():
    rows = [
        _row("01/08/2020", "12:00", "A", "B", 1, 0),  # A W
        _row("02/08/2020", "12:00", "A", "C", 0, 0),  # A D
        _row("03/08/2020", "12:00", "A", "D", 0, 1),  # A L
        _row("04/08/2020", "12:00", "A", "E", 2, 0),  # A W
        _row("05/08/2020", "12:00", "A", "F", 3, 0),  # A W
        _row("06/08/2020", "12:00", "A", "G", 0, 1),  # sixth prior, discarded
        _row("07/08/2020", "12:00", "A", "H", 1, 0),
    ]
    corpus, _, _ = _build(rows)
    first = _fixture_for(corpus, "A", "B")
    assert _feature(first, ModelFeatureId.HOME_FORM).status is HistoricalFeatureReplayStatus.MISSING_PRIOR_HISTORY
    assert _feature(first, ModelFeatureId.HOME_FORM).value is None
    target = _fixture_for(corpus, "A", "H")
    # Latest five A results are D, L, W, W, L: 7 points of 15.
    assert _feature(target, ModelFeatureId.HOME_FORM).value == round(0.10 + (7 / 15) * 0.85, 3)


def test_elo_initial_state_thresholds_and_target_result_only_affects_later_fixture():
    rows = [_row("01/08/2020", "12:00", "A", "B", 1, 0), _row("02/08/2020", "12:00", "A", "C", 0, 0)]
    corpus, _, _ = _build(rows)
    first = _fixture_for(corpus, "A", "B")
    second = _fixture_for(corpus, "A", "C")
    assert _feature(first, ModelFeatureId.HOME_ELO).value == 1500
    assert _feature(first, ModelFeatureId.HOME_ELO).replay_initial_state_assumption is True
    assert _feature(second, ModelFeatureId.HOME_ELO).value == 1513  # int(1500 + 32 * (1 - expected))
    # Exact Elo K changes after 20 then 50 processed source fixtures.
    many = []
    for number in range(1, 53):
        many.append(_row(f"{number:02d}/01/2021" if number <= 31 else f"{number-31:02d}/02/2021", "12:00", "A", f"T{number}", 1, 0))
    many_corpus, _, _ = _build(many)
    ordered_a = sorted((item for item in many_corpus.fixtures if item.home_team_name == "A"), key=lambda item: item.source_local_kickoff)
    assert _feature(ordered_a[19], ModelFeatureId.HOME_ELO).replay_initial_state_assumption is False
    assert _feature(ordered_a[20], ModelFeatureId.HOME_ELO).value != _feature(ordered_a[19], ModelFeatureId.HOME_ELO).value


def test_exact_elo_constants_match_frozen_legacy_engine():
    import domain.historical_model_feature_replay_candidate as module

    assert module._k_factor(19) == 32
    assert module._k_factor(20) == 24
    assert module._k_factor(49) == 24
    assert module._k_factor(50) == 16
    assert module._expected_score(1500, 1500, home_boost=True) == pytest.approx(
        1.0 / (1.0 + 10.0 ** (-50 / 400))
    )
    assert module._expected_score(1500, 1500, home_boost=False) == 0.5


def test_fatigue_thresholds_freshness_and_component_eligibility():
    rows = [
        _row("01/08/2020", "12:00", "A", "B", 1, 0),
        _row("01/08/2020", "12:00", "C", "D", 1, 0),
        _row("10/08/2020", "12:00", "A", "C", 1, 0),
    ]
    corpus, _, _ = _build(rows)
    target = _fixture_for(corpus, "A", "C")
    fatigue = _feature(target, ModelFeatureId.FATIGUE)
    assert fatigue.status is HistoricalFeatureReplayStatus.AVAILABLE_RESEARCH_REPLAY
    assert fatigue.value == 0.0
    assert target.fatigue_pr31_semantic_equivalence == PR31_FATIGUE_SEMANTIC_EQUIVALENCE
    freshness = _feature(target, ModelFeatureId.LIVE_DATA_FRESHNESS)
    assert freshness.status is HistoricalFeatureReplayStatus.NOT_RECONSTRUCTIBLE_WITH_CURRENT_EVIDENCE
    assert freshness.value is None
    assert target.form_path_component_eligible is True
    assert target.elo_fallback_component_eligible is True
    assert corpus.aggregate_coverage["live_data_freshness_available_count"] == 0
    assert corpus.aggregate_coverage["exact_six_feature_eligible_count"] == 0


@pytest.mark.parametrize(
    ("home_last", "away_last", "expected"),
    [
        ("09/08/2020", "01/08/2020", 0.30),
        ("09/08/2020", "08/08/2020", 0.10),
        ("01/08/2020", "09/08/2020", 0.0),
    ],
)
def test_fatigue_threshold_parity(home_last, away_last, expected):
    rows = [
        _row(home_last, "12:00", "A", "B", 1, 0),
        _row(away_last, "12:00", "C", "D", 1, 0),
        _row("10/08/2020", "12:00", "A", "C", 1, 0),
    ]
    corpus, _, _ = _build(rows)
    assert _feature(_fixture_for(corpus, "A", "C"), ModelFeatureId.FATIGUE).value == expected


def test_input_order_does_not_change_corpus_and_mutation_fails_full_replay():
    one = _source([_row("01/08/2020", "12:00", "A", "B", 1, 0)], "2020-21", "E0")
    two = _source([_row("02/08/2020", "12:00", "C", "D", 1, 0)], "2021-22", "E0")
    first = build_historical_model_feature_replay_corpus((one, two))
    second = build_historical_model_feature_replay_corpus((two, one))
    assert canonical_historical_model_feature_replay_corpus_bytes(first) == canonical_historical_model_feature_replay_corpus_bytes(second)
    artifact_bytes = canonical_historical_model_feature_replay_corpus_bytes(first)
    object.__setattr__(first.fixtures[0].features[0], "value", 999.0)
    with pytest.raises(HistoricalModelFeatureReplayCandidateError):
        revalidate_historical_model_feature_replay_corpus(source_inputs=(one, two), corpus=first, corpus_bytes=artifact_bytes)


def test_production_is_pure_and_excludes_downstream_execution():
    import domain.historical_model_feature_replay_candidate as module

    tree = ast.parse(inspect.getsource(module))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    forbidden = {"sqlite3", "requests", "urllib", "joblib"}
    assert not imported & forbidden
    source = inspect.getsource(module)
    for forbidden_name in ("build_score_matrix", "ProbabilityEngine", "MatchAnalyst", "team_merger", "SportyBet"):
        assert forbidden_name not in source
    corpus, _, _ = _build([_row("01/08/2020", "12:00", "A", "B", 1, 0)])
    assert set(corpus.safety.values()) == {False}
    assert not any(name in {"APPROVED", "READY", "PRODUCTION_READY"} for name in HistoricalFeatureReplayStatus.__members__)
