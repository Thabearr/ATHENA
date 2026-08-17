"""Pre-register UTC-native home/away expected-goals model validation.

This protocol is result-free. It binds model-validation design to the exact
successful V2 UTC-native feature projection and deliberately quarantines the
legacy total-goals RandomForest and empty expected-goals/Poisson/Dixon-Coles
placeholders. It does not fit a model, build a score matrix, calculate market
probabilities, inspect bookmaker prices, or authorize BET.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
PROTOCOL_ID = "FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_PROTOCOL_V1"
PROTOCOL_STATE = "PRE_REGISTERED_RESULT_FREE_NOT_EXECUTED_EXPECTED_GOALS_MODEL_VALIDATION_UNQUALIFIED"
BASE_MAIN_SHA = "cd67be14f6a4f09484d18a57de360b8a5d4c51d7"
NEXT_REQUIRED_BOUNDARY = "IMPLEMENT_REVIEWED_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION"

V2_RESULT_ARTIFACT_ID = 9_275_052_993
V2_RESULT_ARTIFACT_SHA256 = "f69ffad8f47faadb3ec743c96efa35fb6f4b43776a7650cf0414fb40455d29eb"
V2_PROJECTION_SHA256 = "5519ef40db3efc678c9eef73046c0e577e5f33a85f11b3fe043fc22bca2fcfed"
V2_PROJECTION_ROWS = 21_326

UTC_FEATURE_PROTOCOL_BLOB_SHA = "57cc133a7fb9daa76c5d5d8e9156903e583c6575"
UTC_FEATURE_RUNNER_BLOB_SHA = "9c9e424791b65292f7bbe8849b3214c140834889"
LEGACY_TRAIN_MODEL_BLOB_SHA = "0f4722f352b03f72540ca5621dc1f75dd9691b7e"
LEGACY_GOALS_MODEL_BLOB_SHA = "bdee71fd6c0b74f5343e8e01e010dd8032d6c694"
EMPTY_MODEL_PLACEHOLDER_BLOB_SHA = "8b137891791fe96927ad78e64b0aad7bded08bdc"

SAFETY_KEYS = frozenset({
    "bet_authorized",
    "calibration_for_production_authorized",
    "expected_goals_production_authorized",
    "expected_goals_transform_approved",
    "market_activation_authorized",
    "model_training_authorized",
    "pricing_authorized",
    "probability_adjustment_authorized",
    "probability_inference_authorized",
    "production_approval_authorized",
    "score_matrix_authorized",
    "selection_authorized",
    "successor_candidate_approved",
    "successor_live_inputs_qualified",
})

PROTOCOL_SHA256 = "2e2ad8d063444d406f0f76014f294905a99f237593928be13b6462be11082f73"
PROTOCOL_SIZE = 6_331


class FotMobUTCNativeExpectedGoalsModelValidationProtocolError(ValueError):
    """Raised when frozen model-validation ancestry or protocol identity changes."""


def _error(message: str) -> FotMobUTCNativeExpectedGoalsModelValidationProtocolError:
    return FotMobUTCNativeExpectedGoalsModelValidationProtocolError(message)


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def _verify_local_lineage() -> None:
    root = Path(__file__).resolve().parents[1]
    expected = {
        "domain/fotmob_utc_native_successor_feature_construction_protocol.py": UTC_FEATURE_PROTOCOL_BLOB_SHA,
        "domain/fotmob_utc_native_successor_feature_construction_qualification.py": UTC_FEATURE_RUNNER_BLOB_SHA,
        "tools/train_model.py": LEGACY_TRAIN_MODEL_BLOB_SHA,
        "models/goals_model.joblib": LEGACY_GOALS_MODEL_BLOB_SHA,
        "models/expected_goals.py": EMPTY_MODEL_PLACEHOLDER_BLOB_SHA,
        "models/poisson.py": EMPTY_MODEL_PLACEHOLDER_BLOB_SHA,
        "models/dixon_coles.py": EMPTY_MODEL_PLACEHOLDER_BLOB_SHA,
    }
    for relative, blob_sha in expected.items():
        path = root / relative
        if not path.exists() or _git_blob_sha(path) != blob_sha:
            raise _error(f"frozen lineage changed: {relative}")


def _payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "protocol_scope": "EXACT_V2_UTC_NATIVE_FEATURE_PROJECTION_HOME_AWAY_GOAL_INTENSITY_RESEARCH_ONLY",
        "protocol_state": PROTOCOL_STATE,
        "base_main_sha": BASE_MAIN_SHA,
        "v2_success_evidence": {
            "run_id": 31_990_121_181,
            "result_comment_id": 5_311_318_782,
            "result_state": "EXECUTION_COMPLETED_EXACT_PR119_UTC_NATIVE_FEATURE_PROJECTION_EVIDENCE_PRESERVED_V2",
            "artifact_id": V2_RESULT_ARTIFACT_ID,
            "artifact_name": "fotmob-utc-native-feature-qualification-v2-31990121181",
            "artifact_sha256": V2_RESULT_ARTIFACT_SHA256,
            "artifact_size_bytes": 23_349_191,
            "projection_sha256": V2_PROJECTION_SHA256,
            "projection_size_bytes": 23_342_076,
            "record_count": V2_PROJECTION_ROWS,
            "unique_fixture_count": 21_326,
            "identity_or_lineage_conflict_count": 0,
            "same_kickoff_group_count": 4_693,
        },
        "frozen_input_contract": {
            "source_namespace": "fotmob_data_matches_reviewed_ordinary_ft_finished_score",
            "kickoff_coordinate": "STATUS_UTCTIME_AWARE_UTC",
            "targets": ["home_goals", "away_goals"],
            "target_meaning": "REGULATION_FULL_TIME_GOALS_FROM_EXACT_QUALIFIED_FIXTURE",
            "predictors": ["home_form", "away_form", "home_elo", "away_elo", "fatigue"],
            "historical_live_data_freshness_status": "NOT_RECONSTRUCTIBLE_WITH_CURRENT_EVIDENCE",
            "historical_live_data_freshness_as_predictor": False,
            "team_identifiers_as_predictors": False,
            "fixture_identifier_as_predictor": False,
            "evidence_reference_as_predictor": False,
            "zero_or_constant_imputation_for_missing_predictors": False,
            "complete_case_row_count": 21_129,
            "full_athena_competition_universe_claimed": False,
            "global_fotmob_historical_coverage_claimed": False,
        },
        "chronological_split_contract": {
            "ordering": ["kickoff_utc", "fixture_identifier"],
            "same_kickoff_must_share_partition": True,
            "train": {
                "start_inclusive": "2020-08-01T00:00:00Z",
                "end_exclusive": "2024-07-01T00:00:00Z",
                "expected_complete_case_rows": 14_181,
            },
            "validation": {
                "start_inclusive": "2024-07-01T00:00:00Z",
                "end_exclusive": "2025-07-01T00:00:00Z",
                "expected_complete_case_rows": 3_471,
            },
            "terminal_holdout": {
                "start_inclusive": "2025-07-01T00:00:00Z",
                "end_exclusive": "2026-08-15T00:00:00Z",
                "expected_complete_case_rows": 3_477,
            },
            "random_train_test_split_forbidden": True,
            "random_kfold_forbidden": True,
            "generic_cv5_forbidden": True,
            "terminal_holdout_used_for_tuning": False,
        },
        "candidate_model_contract": {
            "baseline": {
                "id": "TRAIN_ONLY_GLOBAL_VENUE_MEAN_BASELINE",
                "home_lambda": "mean(home_goals) on train only",
                "away_lambda": "mean(away_goals) on train only",
                "validation_or_terminal_labels_used_for_fit": False,
            },
            "primary": {
                "id": "SEPARATE_STANDARDIZED_POISSON_REGRESSORS_V1",
                "implementation_family": "sklearn.linear_model.PoissonRegressor",
                "separate_home_and_away_models": True,
                "link": "log",
                "output_domain": "lambda_home>=0 and lambda_away>=0",
                "standardize_predictors_using_train_fit_only": True,
                "alpha_grid": [0.0, 0.01, 0.1, 1.0],
                "alpha_selection_data": "validation_only",
                "selection_metric": "combined_home_away_mean_poisson_deviance",
                "refit_after_selection": "train_plus_validation_only",
                "terminal_holdout_labels_used_for_refit": False,
                "random_state_relevant": False,
            },
            "legacy_total_goals_model_eligible": False,
            "empty_expected_goals_poisson_dixon_coles_placeholders_eligible": False,
        },
        "evaluation_contract": {
            "required_primary_metrics": [
                "home_mean_poisson_deviance",
                "away_mean_poisson_deviance",
                "combined_mean_poisson_deviance",
                "home_mae",
                "away_mae",
            ],
            "required_diagnostics": [
                "predicted_vs_observed_goal_mean_by_prediction_quintile",
                "total_goals_distribution",
                "goal_difference_distribution",
                "chronological_subperiod_metrics",
                "missing_row_accounting",
            ],
            "qualification_rule": {
                "combined_terminal_poisson_deviance_must_beat_baseline": True,
                "home_terminal_poisson_deviance_must_not_exceed_baseline": True,
                "away_terminal_poisson_deviance_must_not_exceed_baseline": True,
                "all_lineage_split_and_missingness_checks_must_pass": True,
                "failure_or_tie_state": "MODEL_VALIDATION_NOT_QUALIFIED_REVIEW_BEFORE_ANY_SUCCESSOR_USE",
            },
            "score_matrix_evaluation_in_this_boundary": False,
            "market_probability_evaluation_in_this_boundary": False,
            "bookmaker_price_evaluation_in_this_boundary": False,
        },
        "legacy_quarantine": {
            "goals_model_joblib_blob_sha": LEGACY_GOALS_MODEL_BLOB_SHA,
            "train_model_blob_sha": LEGACY_TRAIN_MODEL_BLOB_SHA,
            "empty_placeholder_blob_sha": EMPTY_MODEL_PLACEHOLDER_BLOB_SHA,
            "legacy_goals_model_semantics": "RANDOM_FOREST_TOTAL_MATCH_GOALS_NOT_SEPARATE_HOME_AWAY_INTENSITIES",
            "legacy_model_authorized_as_expected_goals_model": False,
            "legacy_calibrated_classifier_cv5_authorized_as_temporal_validation_template": False,
        },
        "execution_receipt_requirements": {
            "must_revalidate_v2_artifact_archive_sha256_and_size": True,
            "must_revalidate_projection_sha256_size_and_row_count": True,
            "must_report_exact_split_counts": True,
            "must_report_exact_complete_case_and_dropped_counts": True,
            "must_report_selected_alpha_home_and_away": True,
            "must_report_baseline_and_primary_metrics_for_validation_and_terminal": True,
            "must_emit_hash_sealed_predictions_and_model_validation_receipt": True,
            "must_not_write_production_model_artifact": True,
            "must_not_calculate_market_prices_or_selections": True,
        },
        "forbidden_shortcuts": [
            "DO_NOT_USE_HISTORICAL_LIVE_DATA_FRESHNESS_AS_NUMERIC_TRAINING_INPUT",
            "DO_NOT_ZERO_FILL_OR_CONSTANT_FILL_MISSING_FORM_OR_FATIGUE",
            "DO_NOT_RANDOMIZE_CHRONOLOGICAL_SPLITS_OR_USE_GENERIC_KFOLD",
            "DO_NOT_TUNE_ON_TERMINAL_HOLDOUT",
            "DO_NOT_RECLASSIFY_LEGACY_TOTAL_GOALS_RANDOM_FOREST_AS_HOME_AWAY_EXPECTED_GOALS",
            "DO_NOT_TREAT_EMPTY_EXPECTED_GOALS_POISSON_OR_DIXON_COLES_MODULES_AS_IMPLEMENTED",
            "DO_NOT_AUTHORIZE_SCORE_MATRIX_MARKET_PROBABILITY_PRICING_SELECTION_PRODUCTION_OR_BET",
        ],
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": {key: False for key in sorted(SAFETY_KEYS)},
    }


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def build_fotmob_utc_native_expected_goals_model_validation_protocol() -> dict[str, Any]:
    """Return the frozen result-free model-validation protocol."""
    _verify_local_lineage()
    return _payload()


def canonical_fotmob_utc_native_expected_goals_model_validation_protocol_bytes() -> bytes:
    raw = _canonical(build_fotmob_utc_native_expected_goals_model_validation_protocol())
    if (hashlib.sha256(raw).hexdigest(), len(raw)) != (PROTOCOL_SHA256, PROTOCOL_SIZE):
        raise _error("UTC-native expected-goals validation protocol identity changed")
    return raw


__all__ = [
    "BASE_MAIN_SHA",
    "NEXT_REQUIRED_BOUNDARY",
    "PROTOCOL_ID",
    "PROTOCOL_SHA256",
    "PROTOCOL_SIZE",
    "PROTOCOL_STATE",
    "SAFETY_KEYS",
    "V2_PROJECTION_ROWS",
    "V2_PROJECTION_SHA256",
    "V2_RESULT_ARTIFACT_ID",
    "V2_RESULT_ARTIFACT_SHA256",
    "FotMobUTCNativeExpectedGoalsModelValidationProtocolError",
    "build_fotmob_utc_native_expected_goals_model_validation_protocol",
    "canonical_fotmob_utc_native_expected_goals_model_validation_protocol_bytes",
]
