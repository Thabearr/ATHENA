from __future__ import annotations

import math
from pathlib import Path

import pytest

import domain.fotmob_utc_native_expected_goals_model_validation as validation
import domain.fotmob_utc_native_expected_goals_model_validation_protocol as protocol


def test_protocol_lineage_and_runner_boundary_are_exact() -> None:
    payload = protocol.build_fotmob_utc_native_expected_goals_model_validation_protocol()
    assert payload["protocol_id"] == protocol.PROTOCOL_ID
    assert payload["next_required_boundary"] == (
        "IMPLEMENT_REVIEWED_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION"
    )
    assert validation.NEXT_REQUIRED_BOUNDARY == (
        "EXECUTE_REVIEWED_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION"
    )
    assert validation.POST_EXECUTION_REVIEW_BOUNDARY == (
        "REVIEW_EXECUTED_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_RESULT"
    )


def test_frozen_fitter_intercept_only_is_deterministic() -> None:
    matrix = ((1.0,), (1.0,), (1.0,), (1.0,))
    responses = (0, 1, 2, 1)
    first = validation.fit_poisson_glm_for_testing(matrix, responses)
    second = validation.fit_poisson_glm_for_testing(matrix, responses)
    assert first == second
    assert first["training_fixture_count"] == 4
    assert first["coefficients"] == [0.0]
    assert first["newton_updates"] == 0
    assert first["convergence_gradient_inf_norm"] == 0.0
    assert math.isfinite(first["rounded_training_mean_nll"])


def test_frozen_fitter_exercises_newton_without_search_or_randomness() -> None:
    matrix = ((1.0, -1.0), (1.0, 0.0), (1.0, 1.0), (1.0, 2.0))
    responses = (0, 1, 2, 4)
    fit = validation.fit_poisson_glm_for_testing(matrix, responses)
    assert fit["newton_updates"] > 0
    assert fit["newton_updates"] <= 200
    assert len(fit["coefficients"]) == 2
    assert all(value == round(value, 12) for value in fit["coefficients"])
    assert fit["convergence_gradient_inf_norm"] <= 1e-8


def test_calibration_empty_bins_remain_null_and_weighted_metrics_reconcile() -> None:
    table, wace, wsce = validation.calibration_for_testing(
        (0.2, 0.3, 1.2),
        (0, 1, 2),
    )
    assert sum(item["count"] for item in table) == 3
    empty = [item for item in table if item["count"] == 0]
    assert empty
    assert all(item["mean_predicted_goals"] is None for item in empty)
    assert all(item["mean_observed_goals"] is None for item in empty)
    assert all(
        item["calibration_error_predicted_minus_observed"] is None for item in empty
    )
    manual_wace = sum(
        item["count"] * abs(item["calibration_error_predicted_minus_observed"])
        for item in table
        if item["count"]
    ) / 3
    manual_wsce = sum(
        item["count"] * item["calibration_error_predicted_minus_observed"] ** 2
        for item in table
        if item["count"]
    ) / 3
    assert wace == pytest.approx(manual_wace)
    assert wsce == pytest.approx(manual_wsce)


def test_quarter_jackknife_uses_unweighted_delete_estimate_center() -> None:
    paired = (
        ("2024-07-01T00:00:00Z", -0.4),
        ("2024-08-01T00:00:00Z", -0.2),
        ("2024-10-01T00:00:00Z", -0.1),
        ("2024-11-01T00:00:00Z", 0.1),
        ("2025-01-01T00:00:00Z", -0.3),
        ("2025-02-01T00:00:00Z", -0.1),
    )
    result = validation.quarter_jackknife_for_testing(
        paired,
        (("2024-Q3", 2), ("2024-Q4", 2), ("2025-Q1", 2)),
    )
    deletes = [item["theta_delete"] for item in result["delete_estimates"]]
    assert result["delete_estimate_center"] == pytest.approx(sum(deletes) / 3)
    expected_se = math.sqrt(
        (2 / 3)
        * sum(
            (theta - result["delete_estimate_center"]) ** 2 for theta in deletes
        )
    )
    assert result["jackknife_standard_error"] == pytest.approx(expected_se)
    assert result["upper_95_percent_bound"] == pytest.approx(
        result["full_theta"] + 1.96 * expected_se
    )


def _projection_row() -> dict:
    return {
        "schema_version": 1,
        "source_namespace": validation.SOURCE_NAMESPACE,
        "fixture_identifier": "1",
        "kickoff_utc": "2024-07-01T12:00:00Z",
        "home_team_identifier": "10",
        "away_team_identifier": "20",
        "home_goals": 2,
        "away_goals": 1,
        "home_form": {
            "status": "CONSTRUCTED_FROM_STRICTLY_PRIOR_UTC_HISTORY",
            "value": 0.6,
        },
        "away_form": {
            "status": "CONSTRUCTED_FROM_STRICTLY_PRIOR_UTC_HISTORY",
            "value": 0.4,
        },
        "home_elo": {
            "status": "CONSTRUCTED_FROM_STRICTLY_PRIOR_UTC_HISTORY",
            "value": 1510,
            "matches_before": 20,
            "rating_component": "OVERALL",
        },
        "away_elo": {
            "status": "CONSTRUCTED_FROM_STRICTLY_PRIOR_UTC_HISTORY",
            "value": 1490,
            "matches_before": 20,
            "rating_component": "OVERALL",
        },
        "fatigue": {
            "status": "CONSTRUCTED_FROM_STRICTLY_PRIOR_UTC_HISTORY",
            "value": 0.1,
            "home_rest_days": 4,
            "away_rest_days": 5,
            "rest_day_differential": -1,
        },
        "historical_live_data_freshness": {
            "status": validation.FRESHNESS_STATUS,
            "value": None,
        },
        "evidence_sha256": "a" * 64,
        "evidence_reference": "fixture:1",
    }


def test_historical_freshness_cannot_become_numeric() -> None:
    row = _projection_row()
    row["historical_live_data_freshness"]["value"] = 0.5
    with pytest.raises(
        validation.FotMobUTCNativeExpectedGoalsModelValidationError,
        match="freshness",
    ):
        validation._validated_projection_row(row)


def test_missing_form_remains_missing_not_defaulted() -> None:
    row = _projection_row()
    row["home_form"] = {"status": "MISSING", "value": None}
    parsed = validation._validated_projection_row(row)
    assert parsed["home_form"] is None
    assert validation._complete(parsed) is False


def test_wrong_archive_fails_before_any_fit(tmp_path: Path) -> None:
    artifact = tmp_path / "fake.zip"
    artifact.write_bytes(b"not-the-reviewed-artifact")
    with pytest.raises(
        validation.FotMobUTCNativeExpectedGoalsModelValidationError,
        match="archive identity changed",
    ):
        validation.build_validation(artifact)


def test_receipt_safety_is_exact_all_false() -> None:
    payload = {
        "automatic_model_approval": False,
        "safety": {key: False for key in protocol.SAFETY_KEYS},
    }
    raw = validation.canonical_validation_receipt_bytes(payload)
    assert raw.endswith(b"\n")
    payload["safety"]["bet_authorized"] = True
    with pytest.raises(
        validation.FotMobUTCNativeExpectedGoalsModelValidationError,
        match="all-false",
    ):
        validation.canonical_validation_receipt_bytes(payload)


def test_runner_source_contains_no_forbidden_model_or_market_shortcut() -> None:
    source = Path(validation.__file__).read_text(encoding="utf-8")
    assert "sklearn" not in source
    assert "joblib.dump" not in source
    assert "build_score_matrix" not in source
    assert "requests." not in source
    assert "httpx." not in source
    assert "arm_membership" in source
    assert "cross_runtime_bit_identity_qualified" in source
