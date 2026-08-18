from __future__ import annotations

import datetime as dt

import pytest

import domain.fotmob_utc_native_expected_goals_fresh_holdout as fresh
import domain.fotmob_utc_native_expected_goals_fresh_holdout_confirmation_evaluator as evaluator


UTC = dt.timezone.utc
START = dt.datetime(2026, 8, 19, tzinfo=UTC)
MIN_CLOSE = dt.datetime(2026, 9, 16, tzinfo=UTC)
HARD_CLOSE = dt.datetime(2026, 11, 17, tzinfo=UTC)
FEATURES = {
    "home_elo": 1300.0,
    "away_elo": 1300.0,
    "home_form": 0.2,
    "away_form": 0.2,
    "fatigue": 0.0,
}
ZERO_SHA = "0" * 64
ONE_SHA = "1" * 64
TWO_SHA = "2" * 64
THREE_SHA = "3" * 64
FOUR_SHA = "4" * 64
FIVE_SHA = "5" * 64


def _prediction(
    fixture_id: int,
    primary_id: int,
    *,
    features: dict[str, float] | None = None,
) -> fresh.SealedFreshPrediction:
    feature_values = dict(FEATURES if features is None else features)
    kickoff = START + dt.timedelta(days=1, minutes=fixture_id)
    observed = kickoff - dt.timedelta(hours=2)
    fixture = fresh.QualifiedCaptureFixture(
        fixture_id=fixture_id,
        provider_primary_id=primary_id,
        wrapper_id=100_000 + fixture_id,
        home_team_id=200_000 + fixture_id * 2,
        away_team_id=200_001 + fixture_id * 2,
        kickoff_utc=kickoff,
        capture_observed_at=observed,
        capture_manifest_sha256=ONE_SHA,
        capture_raw_sha256=TWO_SHA,
    )
    return fresh.SealedFreshPrediction(
        schema_version=1,
        implementation_state=fresh.IMPLEMENTATION_STATE,
        protocol_sha256=fresh.pr148.PROTOCOL_SHA256,
        holdout_start_utc=START,
        fixture=fixture,
        bootstrap_projection_sha256=fresh.BOOTSTRAP_PROJECTION_SHA256,
        history_prefix_sha256=THREE_SHA,
        history_prefix_count=fixture_id,
        feature_projection_sha256=FOUR_SHA,
        features=feature_values,
        rates=fresh._rates_from_features(feature_values),
        safety={key: False for key in fresh.SAFETY_KEYS},
    )


def _settled(prediction: fresh.SealedFreshPrediction) -> fresh.SettledFreshPrediction:
    return fresh.SettledFreshPrediction(
        prediction=prediction,
        home_goals=2,
        away_goals=0,
        settlement_observed_at=prediction.fixture.kickoff_utc + dt.timedelta(hours=3),
        settlement_evidence_sha256=FIVE_SHA,
        ordinary_ft_first_raw_sha256=ZERO_SHA,
        ordinary_ft_second_raw_sha256=ONE_SHA,
        ordinary_ft_first_manifest_sha256=TWO_SHA,
        ordinary_ft_second_manifest_sha256=THREE_SHA,
        legacy_history_state_update=None,
    )


def _population(
    *,
    clusters: int = 10,
    per_cluster: int = 100,
) -> tuple[fresh.SealedFreshPrediction, ...]:
    out = []
    fixture_id = 1
    for cluster in range(clusters):
        primary_id = 1000 + cluster
        for _ in range(per_cluster):
            out.append(_prediction(fixture_id, primary_id))
            fixture_id += 1
    return tuple(out)


def _assessments(
    predictions: tuple[fresh.SealedFreshPrediction, ...],
) -> tuple[fresh.FreshPredictionAssessment, ...]:
    return tuple(
        fresh.FreshPredictionAssessment(
            disposition=fresh.PredictionDisposition.SEALED_COMPLETE_CASE,
            fixture=item.fixture,
            missing_feature_ids=(),
            sealed_prediction=item,
        )
        for item in predictions
    )


def _settled_terminals(
    predictions: tuple[fresh.SealedFreshPrediction, ...],
) -> tuple[evaluator.TerminalSettlementRecord, ...]:
    return tuple(
        evaluator.TerminalSettlementRecord(
            fixture_id=item.fixture.fixture_id,
            disposition=evaluator.TerminalDisposition.SETTLED_REVIEWED_ORDINARY_FT,
            settled_prediction=_settled(item),
        )
        for item in predictions
    )


def test_implementation_receipt_is_result_free_and_all_authority_false() -> None:
    receipt = evaluator.implementation_receipt()
    assert receipt["fresh_holdout_result_evaluated"] is False
    assert receipt["fresh_labels_read"] is False
    assert receipt["fresh_labels_refit_performed"] is False
    assert receipt["network_acquisition_performed"] is False
    assert receipt["automatic_successor_approval"] is False
    assert not any(receipt["safety"].values())


def test_minimum_close_population_passes_frozen_pooled_and_robustness_gates() -> None:
    predictions = _population()
    result = evaluator.evaluate_fresh_holdout_confirmation(
        prediction_assessments=_assessments(predictions),
        terminal_records=_settled_terminals(predictions),
        selected_close_utc=MIN_CLOSE,
        evaluated_at_utc=MIN_CLOSE + dt.timedelta(hours=24),
    )
    assert result["count_only_boundary"]["decision"] == (
        fresh.HoldoutBoundaryDecision.CLOSE_COUNT_ONLY_COVERAGE_QUALIFIED.value
    )
    assert result["selected_complete_case_count"] == 1000
    assert result["scored_ordinary_ft_count"] == 1000
    assert result["pooled_gates"]["all_pooled_gates_pass"] is True
    assert result["robustness"]["all_robustness_gates_pass"] is True
    assert result["robustness"]["interval_upper"] < 0.0
    assert result["robustness"]["negative_cluster_fraction"] == 1.0
    assert result["all_confirmation_gates_pass"] is True
    assert result["result_state"] == evaluator.RESULT_SIGNAL_REVIEW_REQUIRED
    assert result["automatic_successor_approval"] is False
    assert not any(result["safety"].values())


def test_missing_settlement_is_reported_but_count_only_population_is_not_reselected() -> None:
    predictions = _population()
    terminals = list(_settled_terminals(predictions))
    missing = predictions[-1]
    terminals[-1] = evaluator.TerminalSettlementRecord(
        fixture_id=missing.fixture.fixture_id,
        disposition=evaluator.TerminalDisposition.UNRESOLVED_AT_SETTLEMENT_TAIL,
        settled_prediction=None,
    )
    result = evaluator.evaluate_fresh_holdout_confirmation(
        prediction_assessments=_assessments(predictions),
        terminal_records=tuple(terminals),
        selected_close_utc=MIN_CLOSE,
        evaluated_at_utc=MIN_CLOSE + dt.timedelta(hours=24),
    )
    assert result["selected_complete_case_count"] == 1000
    assert result["scored_ordinary_ft_count"] == 999
    assert result["missing_or_excluded_settlement_count"] == 1
    report = next(
        item
        for item in result["competition_reports"]
        if item["provider_primary_id"] == missing.fixture.provider_primary_id
    )
    assert report["sealed_complete_case_count"] == 100
    assert report["scored_ordinary_ft_count"] == 99
    assert report["missing_or_excluded_settlement_count"] == 1
    assert result["outcome_or_performance_input_used_for_close"] is False


def test_missing_features_are_reported_by_provider_primary_id_without_entering_close_count() -> None:
    predictions = _population()
    missing_source = _prediction(2001, 1000)
    missing_assessment = fresh.FreshPredictionAssessment(
        disposition=fresh.PredictionDisposition.MISSING_REVIEWED_FEATURES,
        fixture=missing_source.fixture,
        missing_feature_ids=("fatigue", "home_form"),
        sealed_prediction=None,
    )
    result = evaluator.evaluate_fresh_holdout_confirmation(
        prediction_assessments=_assessments(predictions) + (missing_assessment,),
        terminal_records=_settled_terminals(predictions),
        selected_close_utc=MIN_CLOSE,
        evaluated_at_utc=MIN_CLOSE + dt.timedelta(hours=24),
    )
    assert result["selected_complete_case_count"] == 1000
    assert result["missing_feature_prediction_count"] == 1
    assert result["missing_feature_id_counts"] == {"fatigue": 1, "home_form": 1}
    report = next(
        item for item in result["competition_reports"]
        if item["provider_primary_id"] == 1000
    )
    assert report["prediction_assessment_count"] == 101
    assert report["sealed_complete_case_count"] == 100
    assert report["missing_feature_prediction_count"] == 1
    assert report["missing_feature_id_counts"] == {"fatigue": 1, "home_form": 1}


def test_hard_close_insufficient_coverage_emits_no_performance_decision() -> None:
    predictions = _population(clusters=9, per_cluster=100)
    terminals = tuple(
        evaluator.TerminalSettlementRecord(
            fixture_id=item.fixture.fixture_id,
            disposition=evaluator.TerminalDisposition.UNRESOLVED_AT_SETTLEMENT_TAIL,
            settled_prediction=None,
        )
        for item in predictions
    )
    result = evaluator.evaluate_fresh_holdout_confirmation(
        prediction_assessments=_assessments(predictions),
        terminal_records=terminals,
        selected_close_utc=HARD_CLOSE,
        evaluated_at_utc=HARD_CLOSE + dt.timedelta(hours=24),
    )
    assert result["count_only_boundary"]["decision"] == (
        fresh.HoldoutBoundaryDecision.CLOSE_INSUFFICIENT_COVERAGE_NO_SUCCESSOR_DECISION.value
    )
    assert result["result_state"] == evaluator.RESULT_INSUFFICIENT_COVERAGE
    assert result["pooled_metrics"] is None
    assert result["pooled_gates"] is None
    assert result["robustness"] is None
    assert result["all_confirmation_gates_pass"] is False


def test_non_terminal_early_boundary_cannot_be_called_selected_close() -> None:
    predictions = _population()
    with pytest.raises(
        evaluator.FreshHoldoutConfirmationEvaluatorError,
        match="not a terminal count-only holdout boundary",
    ):
        evaluator.evaluate_fresh_holdout_confirmation(
            prediction_assessments=_assessments(predictions),
            terminal_records=_settled_terminals(predictions),
            selected_close_utc=START + dt.timedelta(days=7),
            evaluated_at_utc=START + dt.timedelta(days=8),
        )


def test_terminal_accounting_must_cover_every_sealed_fixture_once() -> None:
    predictions = _population()
    with pytest.raises(
        evaluator.FreshHoldoutConfirmationEvaluatorError,
        match="cover every sealed fixture exactly once",
    ):
        evaluator.evaluate_fresh_holdout_confirmation(
            prediction_assessments=_assessments(predictions),
            terminal_records=_settled_terminals(predictions)[:-1],
            selected_close_utc=MIN_CLOSE,
            evaluated_at_utc=MIN_CLOSE + dt.timedelta(hours=24),
        )


def test_settled_terminal_must_bind_exact_same_sealed_prediction() -> None:
    predictions = _population()
    terminals = list(_settled_terminals(predictions))
    original = predictions[0]
    alternate_features = dict(FEATURES)
    alternate_features["home_form"] = 0.25
    alternate = _prediction(
        original.fixture.fixture_id,
        original.fixture.provider_primary_id,
        features=alternate_features,
    )
    assert alternate.fixture == original.fixture
    terminals[0] = evaluator.TerminalSettlementRecord(
        fixture_id=original.fixture.fixture_id,
        disposition=evaluator.TerminalDisposition.SETTLED_REVIEWED_ORDINARY_FT,
        settled_prediction=_settled(alternate),
    )
    with pytest.raises(
        evaluator.FreshHoldoutConfirmationEvaluatorError,
        match="exact supplied sealed prediction",
    ):
        evaluator.evaluate_fresh_holdout_confirmation(
            prediction_assessments=_assessments(predictions),
            terminal_records=tuple(terminals),
            selected_close_utc=MIN_CLOSE,
            evaluated_at_utc=MIN_CLOSE + dt.timedelta(hours=24),
        )


def test_confirmation_cannot_run_before_settlement_tail_end() -> None:
    predictions = _population()
    with pytest.raises(
        evaluator.FreshHoldoutConfirmationEvaluatorError,
        match="24-hour settlement tail",
    ):
        evaluator.evaluate_fresh_holdout_confirmation(
            prediction_assessments=_assessments(predictions),
            terminal_records=_settled_terminals(predictions),
            selected_close_utc=MIN_CLOSE,
            evaluated_at_utc=MIN_CLOSE + dt.timedelta(hours=23, minutes=59),
        )
