"""Pre-register FotMob UTC-native expected-goals model validation.

Result-free protocol only. It binds the exact successful V2 UTC-native feature
projection to ATHENA's reviewed two-response deterministic Poisson-GLM family.
It does not fit a model, build ScoreMatrix, calculate probabilities, inspect
prices, select bets, or authorize production.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2
PROTOCOL_ID = "FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_PROTOCOL_V2"
PROTOCOL_STATE = "PRE_REGISTERED_RESULT_FREE_NOT_EXECUTED_EXPECTED_GOALS_MODEL_VALIDATION_UNQUALIFIED"
BASE_MAIN_SHA = "cd67be14f6a4f09484d18a57de360b8a5d4c51d7"
NEXT_REQUIRED_BOUNDARY = "IMPLEMENT_REVIEWED_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION"
PROTOCOL_SHA256 = "7dbae5deb711a1d456fb1304616b2f0b6741ffd2039154806f953221a61e06f6"
PROTOCOL_SIZE = 15157

V2_RESULT_ARTIFACT_ID = 9_275_052_993
V2_RESULT_ARTIFACT_SHA256 = "f69ffad8f47faadb3ec743c96efa35fb6f4b43776a7650cf0414fb40455d29eb"
V2_PROJECTION_SHA256 = "5519ef40db3efc678c9eef73046c0e577e5f33a85f11b3fe043fc22bca2fcfed"
V2_PROJECTION_ROWS = 21_326

HISTORICAL_HOME_COEFFICIENTS = (
    0.394404544376,
    0.892777950622,
    -0.837026702225,
    0.147004464963,
    -0.064780063421,
    0.098533203861,
)
HISTORICAL_AWAY_COEFFICIENTS = (
    0.224976524130,
    -0.739617173734,
    0.902201743673,
    -0.136313417150,
    0.201174538524,
    -0.252063395175,
)

SAFETY_KEYS = frozenset({'successor_live_inputs_qualified', 'model_training_authorized', 'expected_goals_production_authorized', 'market_activation_authorized', 'probability_inference_authorized', 'probability_adjustment_authorized', 'calibration_for_production_authorized', 'successor_candidate_approved', 'score_matrix_authorized', 'pricing_authorized', 'selection_authorized', 'production_approval_authorized', 'bet_authorized', 'expected_goals_transform_approved'})

_LINEAGE_FILES = {'domain/fotmob_utc_native_successor_feature_construction_protocol.py': '57cc133a7fb9daa76c5d5d8e9156903e583c6575',
 'domain/fotmob_utc_native_successor_feature_construction_qualification.py': '9c9e424791b65292f7bbe8849b3214c140834889',
 'scripts/qualify_fotmob_utc_native_successor_feature_construction.py': '68503c85569f31532a1a810249073c36242055e0',
 'domain/historical_expected_goals_successor_protocol.py': 'f0b3a070bcf235a097dd737d715f9d6162505509',
 'domain/historical_expected_goals_successor_candidate.py': 'd1d22f44436775a8fd7fa6d4970d8d230d59ebef',
 'domain/historical_expected_goals_successor_robustness_protocol.py': 'b9efdb831363293826fc97b5145839232d7ac53d',
 'domain/historical_expected_goals_successor_robustness_evaluator.py': '28e33a625c02c7f005232d6c5d05d6a0a52397b7',
 'tools/train_model.py': '0f4722f352b03f72540ca5621dc1f75dd9691b7e',
 'models/goals_model.joblib': 'bdee71fd6c0b74f5343e8e01e010dd8032d6c694',
 'models/expected_goals.py': '8b137891791fe96927ad78e64b0aad7bded08bdc',
 'models/poisson.py': '8b137891791fe96927ad78e64b0aad7bded08bdc',
 'models/dixon_coles.py': '8b137891791fe96927ad78e64b0aad7bded08bdc'}

_PROTOCOL_PAYLOAD_JSON = r'''{
  "base_main_sha": "cd67be14f6a4f09484d18a57de360b8a5d4c51d7",
  "candidate_arms": [
    {
      "evaluation_population": "EXACT_COMMON_A_B_AND_POOLED",
      "fit_population": "EXACT_COMMON_TRAIN",
      "fitter": "FROZEN_FITTER_CONTRACT",
      "id": "FOTMOB_NATIVE_SAME_FAMILY_REFIT",
      "predictors": [
        "INTERCEPT",
        "HOME_ELO",
        "AWAY_ELO",
        "HOME_FORM",
        "AWAY_FORM",
        "FATIGUE"
      ],
      "primary_candidate": true
    },
    {
      "coefficients": "EXACT_HISTORICAL_SUCCESSOR_PRIOR_COEFFICIENTS",
      "evaluation_population": "EXACT_COMMON_A_B_AND_POOLED",
      "fit_population": "NONE",
      "id": "HISTORICAL_FIXED_COEFFICIENT_TRANSFER",
      "predictors": [
        "INTERCEPT",
        "HOME_ELO",
        "AWAY_ELO",
        "HOME_FORM",
        "AWAY_FORM",
        "FATIGUE"
      ],
      "primary_candidate": false
    },
    {
      "evaluation_population": "EXACT_COMMON_A_B_AND_POOLED",
      "fit_population": "EXACT_COMMON_TRAIN_NO_ELIGIBILITY_RERUN",
      "fitter": "FROZEN_FITTER_CONTRACT",
      "id": "FOTMOB_NATIVE_ELO_ONLY_NESTED_GLM",
      "predictors": [
        "INTERCEPT",
        "HOME_ELO",
        "AWAY_ELO"
      ],
      "primary_candidate": false
    },
    {
      "evaluation_population": "EXACT_COMMON_A_B_AND_POOLED",
      "fit_population": "EXACT_COMMON_TRAIN_NO_ELIGIBILITY_RERUN",
      "fitter": "FROZEN_FITTER_CONTRACT",
      "id": "FOTMOB_NATIVE_NO_FATIGUE_ABLATION",
      "predictors": [
        "INTERCEPT",
        "HOME_ELO",
        "AWAY_ELO",
        "HOME_FORM",
        "AWAY_FORM"
      ],
      "primary_candidate": false
    },
    {
      "away_lambda": "MEAN_EXACT_COMMON_TRAIN_AWAY_GOALS",
      "evaluation_population": "EXACT_COMMON_A_B_AND_POOLED",
      "fit_population": "EXACT_COMMON_TRAIN",
      "home_lambda": "MEAN_EXACT_COMMON_TRAIN_HOME_GOALS",
      "id": "TRAIN_ONLY_GLOBAL_HOME_AWAY_MEAN_BASELINE",
      "predictors": [
        "INTERCEPT_ONLY"
      ],
      "primary_candidate": false
    }
  ],
  "chronological_split_contract": {
    "evaluation_a": {
      "end_exclusive": "2025-07-01T00:00:00Z",
      "expected_complete_case_rows": 3471,
      "fit_labels_available": false,
      "start_inclusive": "2024-07-01T00:00:00Z"
    },
    "evaluation_b_terminal": {
      "end_exclusive": "2026-08-15T00:00:00Z",
      "expected_complete_case_rows": 3477,
      "fit_labels_available": false,
      "label": "CHRONOLOGICALLY_LATER_RETROSPECTIVE_EVALUATION_NOT_PROSPECTIVE_HOLDOUT",
      "start_inclusive": "2025-07-01T00:00:00Z"
    },
    "evaluation_labels_used_for_fit_or_tuning": false,
    "generic_cv5_forbidden": true,
    "ordering": [
      "kickoff_utc",
      "fixture_identifier"
    ],
    "post_evaluation_refit_authorized": false,
    "random_kfold_forbidden": true,
    "random_train_test_split_forbidden": true,
    "same_kickoff_must_share_partition": true,
    "train": {
      "end_exclusive": "2024-07-01T00:00:00Z",
      "expected_complete_case_rows": 14181,
      "fit_labels_available": true,
      "start_inclusive": "2020-08-01T00:00:00Z"
    }
  },
  "common_population_contract": {
    "all_complete_membership_sha256": "1374fd323bd5aa7e6da6cee23358621c26435297c2e195553e227373008fd8ed",
    "all_complete_rows": 21129,
    "all_five_arms_must_preserve_common_fixture_order_for_paired_outputs": true,
    "all_five_arms_must_use_exact_common_fixture_identities": true,
    "evaluation_a_membership_sha256": "4361cd60976170bd14442502025160d9b3aa97717fb94afc1b68eee9b88c429f",
    "evaluation_a_rows": 3471,
    "evaluation_b_membership_sha256": "4910b5db577bd87fd4bed4e24f3b1e00dff85d58f23e7ea8558cfba0aa5efd59",
    "evaluation_b_rows": 3477,
    "global_mean_baseline_fit_uses_same_train_rows": true,
    "historical_transfer_uses_same_evaluation_rows": true,
    "membership_record_format": "KICKOFF_UTC_TAB_FIXTURE_IDENTIFIER_NEWLINE_SORTED_BY_KICKOFF_UTC_THEN_FIXTURE_IDENTIFIER",
    "membership_rule": "FULL_FIVE_PREDICTOR_COMPLETE_CASE_MEMBERSHIP_FROZEN_BEFORE_ARM_REDUCTION;REDUCED_ARMS_DO_NOT_RERUN_ELIGIBILITY",
    "paired_comparison_membership_mismatch_fails_closed": true,
    "pooled_evaluation_membership_sha256": "f4d713a739feeac90c166f5125dd80ab7e3063598f9ad0187f07d10b88e5bcdc",
    "pooled_evaluation_rows": 6948,
    "reduced_predictor_arms_may_not_admit_additional_rows": true,
    "train_membership_sha256": "4c017b9e43ab9e2f231e88187339a3960c5fdfbd087f21ba92ca8855576219a9",
    "train_rows": 14181
  },
  "evaluation_contract": {
    "automatic_model_approval": false,
    "bookmaker_price_evaluation_in_this_boundary": false,
    "calibration_contract": {
      "bin_assignment": "EACH_MODEL_ASSIGNED_BY_ITS_OWN_PREDICTED_RATE",
      "bin_counts_must_sum_to_population_count": true,
      "bins": [
        [0.0,0.5],[0.5,1.0],[1.0,1.5],[1.5,2.0],[2.0,2.5],[2.5,3.0],[3.0,null]
      ],
      "empty_bin_representation": {
        "calibration_error_predicted_minus_observed": null,
        "count": 0,
        "mean_observed_goals": null,
        "mean_predicted_goals": null
      },
      "empty_bins_contribute_zero_weight_not_fabricated_zero_error": true,
      "interval_semantics": "LEFT_INCLUSIVE_RIGHT_EXCLUSIVE;FINAL_BIN_LEFT_INCLUSIVE_UNBOUNDED",
      "per_bin_fields": ["count","mean_predicted_goals","mean_observed_goals","calibration_error_predicted_minus_observed"],
      "populations": ["EVALUATION_A","EVALUATION_B_TERMINAL","POOLED_A_PLUS_B"],
      "same_fixture_population_required_for_all_models": true,
      "strong_signal_calibration_population": "POOLED_A_PLUS_B",
      "wace_formula": "SUM(COUNT_B*ABS(PREDICTED_MINUS_OBSERVED_ERROR_B))/N_POPULATION",
      "wsce_formula": "SUM(COUNT_B*(PREDICTED_MINUS_OBSERVED_ERROR_B**2))/N_POPULATION"
    },
    "competition_identity_may_not_be_invented_or_fuzzily_reconstructed": true,
    "competition_or_league_robustness_status": "BLOCKED_PROJECTION_DOES_NOT_CARRY_COMPETITION_IDENTITY",
    "evaluation_populations": ["EVALUATION_A","EVALUATION_B_TERMINAL","POOLED_A_PLUS_B"],
    "historical_transfer_and_no_fatigue_are_report_only_not_approval_gates": true,
    "market_probability_evaluation_in_this_boundary": false,
    "non_strong_signal_state": "MIXED_OR_WEAK_FOTMOB_UTC_NATIVE_SUCCESSOR_SIGNAL_REVIEW_REQUIRED",
    "primary_metric": "MEAN_JOINT_POISSON_NEGATIVE_LOG_LIKELIHOOD",
    "required_paired_deltas": ["NATIVE_REFIT_MINUS_ELO_ONLY","NATIVE_REFIT_MINUS_HISTORICAL_FIXED_TRANSFER","NATIVE_REFIT_MINUS_CONSTANT","HISTORICAL_FIXED_TRANSFER_MINUS_CONSTANT","NO_FATIGUE_MINUS_NATIVE_REFIT"],
    "score_matrix_evaluation_in_this_boundary": false,
    "secondary_metrics": ["HOME_NLL","AWAY_NLL","HOME_BIAS","AWAY_BIAS","HOME_MAE","AWAY_MAE","HOME_RMSE","AWAY_RMSE","HOME_WACE","AWAY_WACE","HOME_WSCE","AWAY_WSCE"],
    "strong_signal_rule": {
      "all_lineage_split_missingness_and_common_membership_checks_pass": true,
      "native_home_and_away_fits_converge": true,
      "native_minus_elo_evaluation_a_nll_strictly_below_zero": true,
      "native_minus_elo_evaluation_b_nll_strictly_below_zero": true,
      "native_minus_elo_pooled_nll_strictly_below_zero": true,
      "pooled_native_away_wace_strictly_below_pooled_elo_away_wace": true,
      "pooled_native_away_wsce_strictly_below_pooled_elo_away_wsce": true,
      "pooled_native_home_wace_strictly_below_pooled_elo_home_wace": true,
      "pooled_native_home_wsce_strictly_below_pooled_elo_home_wsce": true,
      "quarter_jackknife_upper_95_percent_bound_strictly_below_zero": true
    },
    "strong_signal_state": "STRONG_FOTMOB_UTC_NATIVE_SUCCESSOR_SIGNAL_REVIEW_REQUIRED",
    "temporal_robustness": {
      "cluster_count": 9,
      "cluster_definition": "UTC_CALENDAR_YEAR_QUARTER",
      "cluster_keys_and_counts": [["2024-Q3",626],["2024-Q4",1017],["2025-Q1",1073],["2025-Q2",755],["2025-Q3",599],["2025-Q4",1020],["2026-Q1",1097],["2026-Q2",721],["2026-Q3",40]],
      "cluster_membership_rule": "EVERY_POOLED_EVALUATION_FIXTURE_MAPS_TO_EXACTLY_ONE_FROZEN_NONEMPTY_QUARTER;MISSING_UNEXPECTED_OR_EMPTY_CLUSTER_FAILS_CLOSED",
      "delete_cluster_estimator": "FIXTURE_WEIGHTED_ARITHMETIC_MEAN_OF_REMAINING_PAIRED_FIXTURE_DIFFERENCES",
      "delete_estimate_center": "UNWEIGHTED_ARITHMETIC_MEAN_OF_EXACTLY_9_DELETE_ONE_QUARTER_ESTIMATES",
      "full_estimate": "ARITHMETIC_MEAN_OF_ALL_6948_PAIRED_FIXTURE_DIFFERENCES",
      "interval_formula": "FULL_THETA_PLUS_MINUS_1_96_TIMES_JACKKNIFE_STANDARD_ERROR",
      "interval_multiplier": 1.96,
      "jackknife_standard_error_formula": "SQRT(((K_MINUS_1)/K)*SUM((THETA_DELETE_J-THETA_BAR)^2))",
      "paired_difference": "NATIVE_REFIT_JOINT_NLL_MINUS_ELO_ONLY_JOINT_NLL_SAME_FIXTURE",
      "partial_terminal_cluster_note": "2026-Q3_CONTAINS_ONLY_QUALIFIED_ROWS_BEFORE_2026-08-15_EXCLUSIVE",
      "population": "POOLED_A_PLUS_B",
      "population_rows": 6948,
      "upper_bound_gate": "FULL_THETA_PLUS_1_96_TIMES_JACKKNIFE_STANDARD_ERROR_STRICTLY_BELOW_ZERO"
    }
  },
  "execution_receipt_requirements": {
    "must_emit_hash_sealed_predictions_and_model_validation_receipt": true,
    "must_not_calculate_score_matrix_market_prices_or_selections": true,
    "must_not_write_production_model_artifact": true,
    "must_recompute_and_match_common_population_membership_hashes": true,
    "must_report_all_arm_metrics_and_required_paired_deltas": true,
    "must_report_all_fit_coefficients_and_convergence_diagnostics": true,
    "must_report_all_nine_quarter_counts_delete_estimates_and_interval": true,
    "must_report_calibration_tables_for_a_b_and_pooled": true,
    "must_report_exact_arm_membership_hashes_and_reject_mismatch": true,
    "must_report_exact_complete_case_and_split_counts": true,
    "must_revalidate_projection_sha256_size_and_row_count": true,
    "must_revalidate_v2_artifact_archive_sha256_and_size": true
  },
  "forbidden_shortcuts": [
    "DO_NOT_USE_HISTORICAL_LIVE_DATA_FRESHNESS_AS_NUMERIC_TRAINING_INPUT",
    "DO_NOT_ZERO_FILL_OR_CONSTANT_FILL_MISSING_FORM_OR_FATIGUE",
    "DO_NOT_RERUN_ELIGIBILITY_FOR_REDUCED_PREDICTOR_ARMS",
    "DO_NOT_COMPARE_MODELS_ON_DIFFERENT_FIXTURE_POPULATIONS",
    "DO_NOT_RANDOMIZE_CHRONOLOGICAL_SPLITS",
    "DO_NOT_USE_EVALUATION_LABELS_FOR_FIT_TUNING_OR_REFIT",
    "DO_NOT_SWITCH_TO_SKLEARN_POISSON_REGRESSOR_OR_ADD_ALPHA_SEARCH",
    "DO_NOT_RECLASSIFY_LEGACY_TOTAL_GOALS_RANDOM_FOREST_AS_HOME_AWAY_EXPECTED_GOALS",
    "DO_NOT_INVENT_COMPETITION_OR_LEAGUE_IDENTITY_FROM_THIS_PROJECTION",
    "DO_NOT_WEIGHT_JACKKNIFE_DELETE_ESTIMATE_CENTER_BY_REMAINING_FIXTURE_COUNTS",
    "DO_NOT_TREAT_EMPTY_CALIBRATION_BINS_AS_ZERO_ERROR_OBSERVATIONS",
    "DO_NOT_AUTHORIZE_SCORE_MATRIX_MARKET_PROBABILITY_PRICING_SELECTION_PRODUCTION_OR_BET"
  ],
  "frozen_fitter_contract": {
    "algorithm": "DETERMINISTIC_NEWTON_POISSON_GLM_WITH_BACKTRACKING_V1",
    "backtracking_factor": 0.5,
    "coefficient_rounding_places": 12,
    "gradient_inf_norm_tolerance": 1e-08,
    "historical_protocol_blob_is_transitive_fitting_contract": true,
    "hyperparameter_search_authorized": false,
    "implementation_family": "REUSE_EXACT_HISTORICAL_SUCCESSOR_DETERMINISTIC_FITTER",
    "intercept_initialization": "LOG_OF_TRAINING_RESPONSE_MEAN",
    "linear_solve_pivot_tolerance": 1e-12,
    "linear_solver": "DETERMINISTIC_GAUSSIAN_ELIMINATION_PARTIAL_PIVOT",
    "link": "LOG",
    "max_iterations": 200,
    "maximum_abs_linear_predictor": 20.0,
    "minimum_step": 9.5367431640625e-07,
    "non_intercept_initialization": "ZERO",
    "objective": "SUM_INDEPENDENT_POISSON_NEGATIVE_LOG_LIKELIHOOD",
    "regularization": "NONE",
    "response_fit_order": ["HOME_GOALS","AWAY_GOALS"],
    "rounded_coefficients_are_evaluation_coefficients": true,
    "scalar_reduction": "MATH_FSUM",
    "sklearn_poisson_regressor_substitution_authorized": false,
    "standardization_refit_authorized": false
  },
  "frozen_input_contract": {
    "complete_case_row_count": 21129,
    "complete_case_rule": "ALL_FIVE_NUMERIC_PREDICTORS_AVAILABLE",
    "dropped_row_count": 197,
    "evidence_reference_as_predictor": false,
    "fixture_identifier_as_predictor": false,
    "full_athena_competition_universe_claimed": false,
    "global_fotmob_historical_coverage_claimed": false,
    "historical_live_data_freshness_as_predictor": false,
    "historical_live_data_freshness_status": "NOT_RECONSTRUCTIBLE_WITH_CURRENT_EVIDENCE",
    "kickoff_coordinate": "STATUS_UTCTIME_AWARE_UTC",
    "predictor_transforms": {
      "away_elo_centered_scaled": "(away_elo-1500)/400",
      "away_form_centered": "away_form-0.5",
      "fatigue_raw": "fatigue",
      "home_elo_centered_scaled": "(home_elo-1500)/400",
      "home_form_centered": "home_form-0.5"
    },
    "predictors": ["home_elo_centered_scaled","away_elo_centered_scaled","home_form_centered","away_form_centered","fatigue_raw"],
    "source_namespace": "fotmob_data_matches_reviewed_ordinary_ft_finished_score",
    "target_meaning": "REGULATION_FULL_TIME_GOALS_FROM_EXACT_QUALIFIED_FIXTURE",
    "targets": ["home_goals","away_goals"],
    "team_identifiers_as_predictors": false,
    "zero_or_constant_imputation_for_missing_predictors": false
  },
  "historical_successor_prior": {
    "historical_away_coefficients": [0.22497652413,-0.739617173734,0.902201743673,-0.13631341715,0.201174538524,-0.252063395175],
    "historical_candidate_sha256": "1fe9ff5f0963355bb98ae93d205a5ea3cb9aa53592601a7b06ff4000f6091660",
    "historical_candidate_size_bytes": 19956,
    "historical_fatigue_pr31_semantic_equivalence": "UNPROVEN",
    "historical_freshness_regime_reconstructed": false,
    "historical_home_coefficients": [0.394404544376,0.892777950622,-0.837026702225,0.147004464963,-0.064780063421,0.098533203861],
    "historical_robustness_sha256": "3ff465edef9c4abd2f0d4dfcb4f776fea64103c0dc26941f44d2b09ba2e4066b",
    "historical_robustness_size_bytes": 15974,
    "model_family": "INDEPENDENT_POISSON_LOG_LINK_TWO_RESPONSE_GLM_V1",
    "prior_result_authorizes_current_model_use": false,
    "robustness_protocol_sha256": "eaa2fd1f906f0a18c39f972d919a0393569c85dc8ad6038cbed10819fd2c0774"
  },
  "implementation_lineage": {
    "empty_model_placeholder_blob_sha": "8b137891791fe96927ad78e64b0aad7bded08bdc",
    "historical_robustness_evaluator_blob_sha": "28e33a625c02c7f005232d6c5d05d6a0a52397b7",
    "historical_robustness_protocol_blob_sha": "b9efdb831363293826fc97b5145839232d7ac53d",
    "historical_successor_candidate_blob_sha": "d1d22f44436775a8fd7fa6d4970d8d230d59ebef",
    "historical_successor_protocol_blob_sha": "f0b3a070bcf235a097dd737d715f9d6162505509",
    "legacy_goals_model_blob_sha": "bdee71fd6c0b74f5343e8e01e010dd8032d6c694",
    "legacy_train_model_blob_sha": "0f4722f352b03f72540ca5621dc1f75dd9691b7e",
    "utc_feature_cli_blob_sha": "68503c85569f31532a1a810249073c36242055e0",
    "utc_feature_protocol_blob_sha": "57cc133a7fb9daa76c5d5d8e9156903e583c6575",
    "utc_feature_runner_blob_sha": "9c9e424791b65292f7bbe8849b3214c140834889"
  },
  "legacy_quarantine": {
    "empty_expected_goals_poisson_dixon_coles_placeholders_implemented": false,
    "empty_placeholder_blob_sha": "8b137891791fe96927ad78e64b0aad7bded08bdc",
    "goals_model_joblib_blob_sha": "bdee71fd6c0b74f5343e8e01e010dd8032d6c694",
    "legacy_goals_model_semantics": "RANDOM_FOREST_TOTAL_MATCH_GOALS_NOT_SEPARATE_HOME_AWAY_INTENSITIES",
    "legacy_model_authorized_as_expected_goals_model": false,
    "train_model_blob_sha": "0f4722f352b03f72540ca5621dc1f75dd9691b7e"
  },
  "next_required_boundary": "IMPLEMENT_REVIEWED_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION",
  "protocol_id": "FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_PROTOCOL_V2",
  "protocol_scope": "EXACT_V2_UTC_NATIVE_FEATURE_PROJECTION_SAME_REVIEWED_POISSON_GLM_FAMILY_RESEARCH_ONLY",
  "protocol_state": "PRE_REGISTERED_RESULT_FREE_NOT_EXECUTED_EXPECTED_GOALS_MODEL_VALIDATION_UNQUALIFIED",
  "safety": {
    "bet_authorized": false,
    "calibration_for_production_authorized": false,
    "expected_goals_production_authorized": false,
    "expected_goals_transform_approved": false,
    "market_activation_authorized": false,
    "model_training_authorized": false,
    "pricing_authorized": false,
    "probability_adjustment_authorized": false,
    "probability_inference_authorized": false,
    "production_approval_authorized": false,
    "score_matrix_authorized": false,
    "selection_authorized": false,
    "successor_candidate_approved": false,
    "successor_live_inputs_qualified": false
  },
  "schema_version": 2,
  "v2_success_evidence": {
    "artifact_id": 9275052993,
    "artifact_name": "fotmob-utc-native-feature-qualification-v2-31990121181",
    "artifact_sha256": "f69ffad8f47faadb3ec743c96efa35fb6f4b43776a7650cf0414fb40455d29eb",
    "artifact_size_bytes": 23349191,
    "attempt_comment_id": 5311311868,
    "command_comment_id": 5311311034,
    "identity_or_lineage_conflict_count": 0,
    "projection_sha256": "5519ef40db3efc678c9eef73046c0e577e5f33a85f11b3fe043fc22bca2fcfed",
    "projection_size_bytes": 23342076,
    "record_count": 21326,
    "result_comment_id": 5311318782,
    "result_state": "EXECUTION_COMPLETED_EXACT_PR119_UTC_NATIVE_FEATURE_PROJECTION_EVIDENCE_PRESERVED_V2",
    "run_id": 31990121181,
    "same_kickoff_group_count": 4693,
    "unique_fixture_count": 21326
  }
}'''


class FotMobUTCNativeExpectedGoalsModelValidationProtocolError(ValueError):
    """Raised when frozen protocol identity or implementation lineage drifts."""


def _error(message: str) -> FotMobUTCNativeExpectedGoalsModelValidationProtocolError:
    return FotMobUTCNativeExpectedGoalsModelValidationProtocolError(message)


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def _verify_local_lineage() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative, expected_sha in _LINEAGE_FILES.items():
        path = root / relative
        if not path.is_file() or _git_blob_sha(path) != expected_sha:
            raise _error(f"frozen implementation lineage changed: {relative}")


def _canonical(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("protocol serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _payload() -> dict[str, Any]:
    value = json.loads(_PROTOCOL_PAYLOAD_JSON)
    if not isinstance(value, dict):
        raise _error("embedded protocol payload must be an object")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise _error("embedded protocol schema version changed")
    if value.get("protocol_id") != PROTOCOL_ID:
        raise _error("embedded protocol identity changed")
    if value.get("protocol_state") != PROTOCOL_STATE:
        raise _error("embedded protocol state changed")
    if value.get("base_main_sha") != BASE_MAIN_SHA:
        raise _error("embedded protocol base main changed")
    if value.get("next_required_boundary") != NEXT_REQUIRED_BOUNDARY:
        raise _error("embedded next boundary changed")
    prior = value.get("historical_successor_prior")
    if not isinstance(prior, dict):
        raise _error("historical successor prior missing")
    if prior.get("historical_home_coefficients") != list(HISTORICAL_HOME_COEFFICIENTS):
        raise _error("historical home coefficient transfer identity changed")
    if prior.get("historical_away_coefficients") != list(HISTORICAL_AWAY_COEFFICIENTS):
        raise _error("historical away coefficient transfer identity changed")
    safety = value.get("safety")
    if not isinstance(safety, dict) or set(safety) != SAFETY_KEYS:
        raise _error("protocol safety keys changed")
    if any(type(flag) is not bool or flag is not False for flag in safety.values()):
        raise _error("every protocol safety flag must remain exact False")
    common = value.get("common_population_contract")
    if not isinstance(common, dict) or common.get("all_complete_rows") != 21_129:
        raise _error("common complete-case population changed")
    temporal = value.get("evaluation_contract", {}).get("temporal_robustness")
    if not isinstance(temporal, dict) or temporal.get("cluster_count") != 9:
        raise _error("temporal robustness cluster contract changed")
    if sum(count for _, count in temporal.get("cluster_keys_and_counts", [])) != 6_948:
        raise _error("temporal robustness cluster counts do not reconcile")
    return value


def build_fotmob_utc_native_expected_goals_model_validation_protocol() -> dict[str, Any]:
    """Return the result-free protocol after exact local-lineage verification."""
    _verify_local_lineage()
    return _payload()


def canonical_fotmob_utc_native_expected_goals_model_validation_protocol_bytes() -> bytes:
    """Return exact canonical protocol bytes and fail if identity drifts."""
    raw = _canonical(build_fotmob_utc_native_expected_goals_model_validation_protocol())
    if (hashlib.sha256(raw).hexdigest(), len(raw)) != (
        PROTOCOL_SHA256,
        PROTOCOL_SIZE,
    ):
        raise _error("UTC-native expected-goals validation protocol identity changed")
    return raw


__all__ = [
    "BASE_MAIN_SHA",
    "HISTORICAL_AWAY_COEFFICIENTS",
    "HISTORICAL_HOME_COEFFICIENTS",
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
