from __future__ import annotations

from datetime import date, timedelta
from types import MappingProxyType

import pytest

from domain.forward_calibration import (
    AUTHORITY_FLAGS,
    CALIBRATION_CONTRACT_VERSION,
    EXPECTED_CALIBRATION_CONTRACT_SHA256_BY_VERSION,
    CalibrationPartition,
    CalibrationVectorRow,
    ForwardCalibrationArtifact,
    ForwardCalibrationError,
    calibration_unit_specs,
    evaluate_calibration,
    fit_forward_calibrator,
    project_calibration_rows,
    run_forward_calibration,
    validate_calibration_contract,
)
from domain.goal_score_dynamics import (
    FeatureStatus,
    GOAL_SCORE_FEATURE_REGISTRY,
    TrainingRow,
    build_goal_score_distribution,
)
from domain.markets import MarketFamily, MarketId


F = GOAL_SCORE_FEATURE_REGISTRY[0].feature_id
TACTICAL_HOME = "TACTICAL.HOME.OVERALL.EVENT_ENVIRONMENT"
TACTICAL_AWAY = "TACTICAL.AWAY.OVERALL.EVENT_ENVIRONMENT"


def training_row(index: int, *, low: bool = False, competition: str = "L1") -> TrainingRow:
    match_date = (date(2021, 1, 1) + timedelta(days=index)).isoformat()
    signal = -2.0 if low else 2.0
    return TrainingRow(
        match_key=f"m{index:04d}",
        match_date=match_date,
        scope="club",
        competition_key=competition,
        season="2021",
        home_goals=0 if low else 3,
        away_goals=0 if low else 2,
        features=MappingProxyType({
            F: (FeatureStatus.AVAILABLE, signal),
            TACTICAL_HOME: (FeatureStatus.AVAILABLE, signal),
            TACTICAL_AWAY: (FeatureStatus.AVAILABLE, signal),
        }),
    )


def test_frozen_calibration_contract_validates():
    identities = validate_calibration_contract()
    assert identities["calibration_contract_sha256"] == (
        EXPECTED_CALIBRATION_CONTRACT_SHA256_BY_VERSION[
            CALIBRATION_CONTRACT_VERSION
        ]
    )


def test_specs_are_market_family_scoped_and_specialists_stay_blocked():
    specs = calibration_unit_specs(
        total_goal_lines=(1.5, 2.5, 3.5),
        asian_handicap_home_lines=(-0.25, 0.0, 0.75),
    )
    families = {spec.family for spec in specs}
    assert MarketFamily.WIN_EITHER_HALF not in families
    assert MarketFamily.EARLY_PAYOUT not in families
    assert MarketFamily.MATCH_RESULT in families
    assert MarketFamily.TOTAL_GOALS in families
    assert MarketFamily.ASIAN_HANDICAP in families
    assert all(
        spec.line_origin_policy_id is not None
        for spec in specs
        if spec.line is not None
    )
    with pytest.raises(ForwardCalibrationError):
        calibration_unit_specs(total_goal_lines=(2.0,))
    with pytest.raises(ForwardCalibrationError):
        calibration_unit_specs(asian_handicap_home_lines=(0.1,))


def test_projection_preserves_partition_and_settlement_semantics():
    row = training_row(10, low=False)
    distribution = build_goal_score_distribution(
        "POISSON_GLM_SCORE_V1", 1.8, 1.1
    )
    specs = calibration_unit_specs(
        total_goal_lines=(2.5,),
        asian_handicap_home_lines=(-0.25,),
    )
    projected = project_calibration_rows(
        row,
        distribution,
        model_id="POISSON_GLM_SCORE_V1",
        fold_index=1,
        fit_end_date="2021-01-10",
        partition=CalibrationPartition.OOF_CALIBRATION_FIT,
        specs=specs,
    )
    assert len(projected) == len(specs)
    assert all(sum(item.raw_probabilities) == pytest.approx(1.0) for item in projected)
    dnb_home = next(item for item in projected if item.unit.unit_id == "DRAW_NO_BET:HOME")
    assert dnb_home.observed_component == "WIN"
    ah_home = next(
        item for item in projected
        if item.unit.market_id is MarketId.ASIAN_HANDICAP
        and item.unit.selection_outcome.value == "HOME"
    )
    assert ah_home.observed_component in {"WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS"}


def test_calibration_row_requires_strictly_prior_fit_cutoff():
    spec = calibration_unit_specs()[0]
    with pytest.raises(ForwardCalibrationError):
        CalibrationVectorRow(
            match_key="x",
            match_date="2024-01-01",
            competition_key="L1",
            season="2024",
            regime="MID_EVENT",
            model_id="POISSON_GLM_SCORE_V1",
            fold_index=1,
            fit_end_date="2024-01-01",
            partition=CalibrationPartition.OOF_CALIBRATION_FIT,
            unit=spec,
            raw_probabilities=(0.4, 0.3, 0.3),
            observed_index=0,
        )


def _binary_rows(*, start: int, partition: CalibrationPartition, repeats: int = 50):
    spec = next(item for item in calibration_unit_specs() if item.unit_id == "BTTS:PARTITION")
    rows = []
    index = start
    for probability_int in range(1, 10):
        probability = probability_int / 10.0
        true_rate = min(0.95, probability + 0.15)
        positives = round(true_rate * repeats)
        for repeat in range(repeats):
            match_date = (date(2024, 1, 1) + timedelta(days=index)).isoformat()
            rows.append(CalibrationVectorRow(
                match_key=f"c{index:06d}",
                match_date=match_date,
                competition_key="L1" if repeat % 2 == 0 else "L2",
                season="2024",
                regime="LOW_EVENT" if repeat % 3 == 0 else "HIGH_EVENT",
                model_id="POISSON_GLM_SCORE_V1",
                fold_index=1 if partition is CalibrationPartition.OOF_CALIBRATION_FIT else 0,
                fit_end_date=(date(2023, 12, 31) if partition is CalibrationPartition.OOF_CALIBRATION_FIT else date(2024, 1, 1) + timedelta(days=start - 1)).isoformat(),
                partition=partition,
                unit=spec,
                raw_probabilities=(probability, 1.0 - probability),
                observed_index=0 if repeat < positives else 1,
            ))
            index += 1
    return tuple(rows)


def test_isotonic_forward_calibration_improves_synthetic_ece_and_roundtrips():
    fit_rows = _binary_rows(
        start=1,
        partition=CalibrationPartition.OOF_CALIBRATION_FIT,
    )
    artifact = fit_forward_calibrator(
        fit_rows,
        model_id="POISSON_GLM_SCORE_V1",
        source_training_view_sha256="0" * 64,
    )
    eval_rows = _binary_rows(
        start=10000,
        partition=CalibrationPartition.TERMINAL_HOLDOUT_EVALUATION,
    )
    evaluation = evaluate_calibration(eval_rows, artifact)
    metrics = evaluation["unit_results"]["BTTS:PARTITION"]["metrics"]
    assert metrics["HIERARCHICAL"]["classwise_ece"] < metrics["RAW"]["classwise_ece"]
    assert evaluation["overall_reliability_ece_gate"] == "PASS"

    encoded = artifact.to_dict()
    rebuilt = ForwardCalibrationArtifact.from_dict(encoded)
    assert rebuilt.artifact_sha256 == artifact.artifact_sha256
    tampered = dict(encoded)
    tampered["model_id"] = "DIXON_COLES_SCORE_V1"
    with pytest.raises(ForwardCalibrationError):
        ForwardCalibrationArtifact.from_dict(tampered)


def test_terminal_rows_cannot_enter_calibrator_fit():
    rows = _binary_rows(
        start=10000,
        partition=CalibrationPartition.TERMINAL_HOLDOUT_EVALUATION,
        repeats=10,
    )
    with pytest.raises(ForwardCalibrationError):
        fit_forward_calibrator(
            rows,
            model_id="POISSON_GLM_SCORE_V1",
            source_training_view_sha256="1" * 64,
        )


def test_full_forward_protocol_is_research_only_and_holdout_is_evaluation_only():
    rows = [
        training_row(index, low=index % 2 == 0, competition="L1" if index % 3 else "L2")
        for index in range(32)
    ]
    artifact, report = run_forward_calibration(
        rows,
        model_id="POISSON_GLM_SCORE_V1",
        source_training_view_sha256="2" * 64,
        total_goal_lines=(2.5,),
        asian_handicap_home_lines=(-0.25,),
    )
    assert artifact.model_id == "POISSON_GLM_SCORE_V1"
    assert report["calibrator_fit_contains_terminal_holdout"] is False
    assert report["oof_identity_sha256"] != report["terminal_holdout_identity_sha256"]
    assert report["blocked_specialist_families"]["WIN_EITHER_HALF"].startswith("BLOCKED")
    assert AUTHORITY_FLAGS["research_calibration"] is True
    assert not any(value for key, value in AUTHORITY_FLAGS.items() if key != "research_calibration")
