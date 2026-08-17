"""Pre-register the fresh-holdout home-calibration and competition-identity follow-up.

This protocol is result-free with respect to the future confirmation population.
It freezes the development-only home-rate calibration selected after review of
the consumed A/B labels, the exact provider-native competition identity fields,
and the prospective confirmation/robustness gates.  It does not collect fresh
fixtures, fit on fresh labels, authorize ScoreMatrix/probability/pricing use, or
approve a production/BET model.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

SCHEMA_VERSION = 1
PROTOCOL_ID = (
    "FOTMOB_UTC_NATIVE_EXPECTED_GOALS_FRESH_HOLDOUT_"
    "HOME_CALIBRATION_COMPETITION_IDENTITY_PROTOCOL_V1"
)
PROTOCOL_STATE = (
    "PRE_REGISTERED_FRESH_HOLDOUT_CALIBRATION_AND_COMPETITION_IDENTITY_"
    "NOT_IMPLEMENTED_NOT_EXECUTED"
)
BASE_MAIN_SHA = "5c46aa8fcaf4338e8968c50e1c852301f8e2e0cd"
PROTOCOL_SHA256 = "cfceeac4124f72595b97736d3dae76b518ff3a94428cb2a7a0bf9c52550c2313"
PROTOCOL_SIZE = 8933
NEXT_REQUIRED_BOUNDARY = (
    "IMPLEMENT_REVIEWED_FRESH_HOLDOUT_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_"
    "CALIBRATION_AND_COMPETITION_IDENTITY_FOLLOWUP"
)

RESULT_REVIEW_BLOB_SHA = "025a35d1d3b17e49a200dfe654304368fba39add"
XG_VALIDATOR_BLOB_SHA = "0421506b9e6e398c3469bb69196ef8fcad04f2a5"
FOTMOB_HISTORICAL_ADAPTER_EXECUTOR_BLOB_SHA = (
    "33c6e95ed0d41dc9b0d510124bd9f30ad9eee34d"
)

EXECUTION_RUN_ID = 32049714066
RESULT_ARTIFACT_ID = 9294215497
RESULT_ARTIFACT_SHA256 = (
    "e9eac385a66df04bf28e7d69062e55db516829e94405e4a8def0e4d6a346d6c5"
)
RESULT_RECEIPT_SHA256 = (
    "1fffee7474ab37ee613e6a7943b57fd9231f6d6bdf53ffa6b13ee2b62ceca06a"
)
PREDICTIONS_SHA256 = (
    "2f4939a8f2d41674660144f5315d2420ce2f006ce2b885e52c6655abd0e52420"
)
DEVELOPMENT_ROWS = 6_948

LEGACY_PRIMARY_IDS = (40, 47, 53, 54, 55, 57, 61, 64, 71, 87, 135)

NATIVE_HOME_COEFFICIENTS = (
    0.394790673980,
    0.900689319890,
    -0.844380323936,
    0.133540447574,
    -0.058009514743,
    0.108204674639,
)
NATIVE_AWAY_COEFFICIENTS = (
    0.224028141954,
    -0.746802331416,
    0.905426841106,
    -0.121639766119,
    0.193824256317,
    -0.219951439274,
)
ELO_ONLY_HOME_COEFFICIENTS = (
    0.404548228885,
    0.981072036699,
    -0.884436628617,
)
ELO_ONLY_AWAY_COEFFICIENTS = (
    0.222063385866,
    -0.828101056370,
    1.021712053735,
)

HOME_CALIBRATION_INTERCEPT_HEX = "0x1.11df1d736f167p-4"
HOME_CALIBRATION_SLOPE_HEX = "0x1.b4f2aad487cafp-1"
HOME_CALIBRATION_INTERCEPT = float.fromhex(HOME_CALIBRATION_INTERCEPT_HEX)
HOME_CALIBRATION_SLOPE = float.fromhex(HOME_CALIBRATION_SLOPE_HEX)

FRESH_HOLDOUT_NOT_BEFORE_UTC = "2026-08-15T00:00:00Z"
MINIMUM_CALENDAR_SPAN_DAYS = 28
MAXIMUM_CALENDAR_SPAN_DAYS = 90
MINIMUM_COMPLETE_CASE_FIXTURES = 1_000
QUALIFYING_COMPETITION_MIN_FIXTURES = 30
MINIMUM_QUALIFYING_COMPETITIONS = 8
MINIMUM_NON_LEGACY_QUALIFYING_COMPETITIONS = 2
MINIMUM_NEGATIVE_COMPETITION_FRACTION = 0.75

SAFETY_KEYS = (
    "bet_authorized",
    "calibration_for_production_authorized",
    "competition_registry_mutation_authorized",
    "expected_goals_production_authorized",
    "expected_goals_transform_approved",
    "market_activation_authorized",
    "model_training_authorized",
    "network_acquisition_authorized",
    "pricing_authorized",
    "probability_adjustment_authorized",
    "probability_inference_authorized",
    "production_approval_authorized",
    "score_matrix_authorized",
    "selection_authorized",
    "successor_candidate_approved",
    "successor_live_inputs_qualified",
)

def apply_frozen_home_calibration(native_home_lambda: float) -> float:
    """Apply the frozen monotone positive home-rate calibration."""
    if (
        type(native_home_lambda) is not float
        or not (native_home_lambda > 0.0)
        or native_home_lambda == float("inf")
    ):
        raise ValueError("native_home_lambda must be a finite positive float")
    import math
    return math.exp(
        HOME_CALIBRATION_INTERCEPT
        + HOME_CALIBRATION_SLOPE * math.log(native_home_lambda)
    )

def build_fresh_holdout_home_calibration_competition_identity_protocol() -> dict[str, Any]:
    """Return the frozen result-free follow-up protocol."""
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "protocol_state": PROTOCOL_STATE,
        "base_main_sha": BASE_MAIN_SHA,
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "reviewed_parent": {
            "result_review_blob_sha": RESULT_REVIEW_BLOB_SHA,
            "xg_validator_blob_sha": XG_VALIDATOR_BLOB_SHA,
            "execution_run_id": EXECUTION_RUN_ID,
            "result_artifact_id": RESULT_ARTIFACT_ID,
            "result_artifact_sha256": RESULT_ARTIFACT_SHA256,
            "result_receipt_sha256": RESULT_RECEIPT_SHA256,
            "predictions_sha256": PREDICTIONS_SHA256,
            "development_rows": DEVELOPMENT_ROWS,
            "reviewed_state_required": (
                "REVIEWED_MIXED_OR_WEAK_FOTMOB_UTC_NATIVE_SUCCESSOR_NOT_APPROVED"
            ),
            "sole_failed_strong_check_required": (
                "pooled_native_home_wace_strictly_below_pooled_elo_home_wace"
            ),
        },
        "development_only_calibration": {
            "labels_are_consumed_not_fresh": True,
            "population": "EXACT_POOLED_EVALUATION_A_PLUS_B_6948_ROWS",
            "source_predictions_member_sha256": PREDICTIONS_SHA256,
            "target": "HOME_GOALS_ONLY",
            "away_transform": "IDENTITY_NATIVE_AWAY_RATE",
            "family": "TWO_PARAMETER_MONOTONE_LOG_RATE_POISSON_CALIBRATION",
            "formula": "CALIBRATED_HOME_LAMBDA=EXP(A+B*LN(NATIVE_HOME_LAMBDA))",
            "fit_design": ["INTERCEPT", "LN_NATIVE_HOME_LAMBDA"],
            "fit_objective": "SUM_HOME_POISSON_NEGATIVE_LOG_LIKELIHOOD",
            "fit_initialization": [0.0, 1.0],
            "fit_solver": "DETERMINISTIC_TWO_BY_TWO_NEWTON_BINARY64_MATH_FSUM",
            "fit_max_updates": 100,
            "fit_step_tolerance": 1e-14,
            "regularization": "NONE",
            "clipping": "NONE",
            "selected_updates": 5,
            "selected_gradient_inf_norm": 1.5343282200319663e-13,
            "intercept_hex": HOME_CALIBRATION_INTERCEPT_HEX,
            "slope_hex": HOME_CALIBRATION_SLOPE_HEX,
            "intercept_decimal": HOME_CALIBRATION_INTERCEPT,
            "slope_decimal": HOME_CALIBRATION_SLOPE,
            "development_diagnostics_not_confirmation": {
                "native_home_wace": 0.05778673203465596,
                "elo_only_home_wace": 0.05490445024426852,
                "calibrated_home_wace": 0.016320745023423927,
                "native_home_wsce": 0.0069982959681213885,
                "elo_only_home_wsce": 0.007723157270694639,
                "calibrated_home_wsce": 0.0006027164419862363,
                "native_home_mean_nll": 1.514098418973565,
                "calibrated_home_mean_nll": 1.5122486374803892,
            },
            "further_parameter_tuning_after_protocol_merge_forbidden": True,
        },
        "frozen_model_rates": {
            "native_predictors": [
                "INTERCEPT",
                "(HOME_ELO-1500)/400",
                "(AWAY_ELO-1500)/400",
                "HOME_FORM-0.5",
                "AWAY_FORM-0.5",
                "FATIGUE",
            ],
            "native_home_coefficients": list(NATIVE_HOME_COEFFICIENTS),
            "native_away_coefficients": list(NATIVE_AWAY_COEFFICIENTS),
            "elo_only_predictors": [
                "INTERCEPT",
                "(HOME_ELO-1500)/400",
                "(AWAY_ELO-1500)/400",
            ],
            "elo_only_home_coefficients": list(ELO_ONLY_HOME_COEFFICIENTS),
            "elo_only_away_coefficients": list(ELO_ONLY_AWAY_COEFFICIENTS),
            "fresh_labels_may_not_refit_any_coefficient": True,
        },
        "competition_identity": {
            "source": "FOTMOB_DATA_MATCHES_PROVIDER_NATIVE_FIELDS",
            "source_adapter_executor_blob_sha": (
                FOTMOB_HISTORICAL_ADAPTER_EXECUTOR_BLOB_SHA
            ),
            "legacy_field_semantics_qualification_scope": (
                "EXISTING_REVIEWED_PARSER_QUALIFIES_MAPPED_LEGACY_TARGET_FAMILIES_ONLY"
            ),
            "wrapper_primary_id_field": "leagues[].primaryId",
            "wrapper_id_field": "leagues[].id",
            "fixture_wrapper_id_field": "leagues[].matches[].leagueId",
            "fixture_id_field": "leagues[].matches[].id",
            "fixture_wrapper_id_must_equal_wrapper_id": True,
            "primary_id_must_be_positive_integer": True,
            "wrapper_id_must_be_positive_integer": True,
            "fuzzy_name_mapping_forbidden": True,
            "model_league_code_is_not_competition_identity": True,
            "legacy_primary_ids": list(LEGACY_PRIMARY_IDS),
            "fresh_capture_scope_not_limited_to_legacy_primary_ids": True,
            "non_legacy_identity_requires_fresh_structural_qualification": True,
            "non_legacy_wrapper_admission_requires_exact_positive_ids_and_wrapper_match": True,
            "competition_robustness_cluster_key": "PROVIDER_PRIMARY_ID",
            "wrapper_id_retained_for_edition_and_lineage_audit": True,
            "competition_registry_mutation_in_this_boundary": False,
        },
        "feature_semantics": {
            "preserve_reviewed_native_predictor_meanings": True,
            "history_state_update_scope_primary_ids": list(LEGACY_PRIMARY_IDS),
            "non_legacy_evaluation_fixture_may_be_scored_when_features_complete": True,
            "non_legacy_fixture_result_may_not_update_frozen_legacy_history_state": True,
            "strictly_prior_utc_history_only": True,
            "same_kickoff_batching_required": True,
            "missing_features_are_missing_not_imputed": True,
            "missingness_reported_by_provider_primary_id": True,
            "historical_feature_scope_may_not_silently_expand_to_all_competitions": True,
        },
        "prospective_confirmation": {
            "not_before_utc": FRESH_HOLDOUT_NOT_BEFORE_UTC,
            "start_rule": (
                "FIRST_UTC_00_00_BOUNDARY_STRICTLY_AFTER_REVIEWED_IMPLEMENTATION_"
                "MERGE_TIMESTAMP_AND_NOT_EARLIER_THAN_NOT_BEFORE_UTC"
            ),
            "prediction_observation_window": {
                "earliest_hours_before_kickoff": 24,
                "latest_minutes_before_kickoff": 60,
                "selection": "EARLIEST_QUALIFYING_CAPTURE_IN_WINDOW",
                "no_qualifying_capture_disposition": "MISSING_NOT_RETROFILLED",
            },
            "prediction_record_must_be_sealed_before_kickoff": True,
            "competition_identity_must_be_sealed_with_prediction": True,
            "sealed_kickoff_utc_must_equal_settlement_kickoff_utc": True,
            "kickoff_drift_disposition": "EXCLUDE_PREDICTION_NO_REUSE_OR_RETIMING",
            "settlement_must_match_fixture_and_competition_identity": True,
            "ordinary_ft_settlement_semantics_only": True,
            "cancelled_postponed_special_or_unreviewed_states_not_scored": True,
            "no_post_kickoff_prediction_mutation": True,
            "no_confirmation_label_may_select_or_modify_calibration": True,
            "minimum_calendar_span_days": MINIMUM_CALENDAR_SPAN_DAYS,
            "maximum_calendar_span_days": MAXIMUM_CALENDAR_SPAN_DAYS,
            "close_rule": (
                "AT_FIRST_UTC_DAY_BOUNDARY_AFTER_MINIMUM_SPAN_WHEN_ALL_COUNT_ONLY_"
                "COVERAGE_GATES_PASS;OTHERWISE_CLOSE_AT_MAXIMUM_SPAN_AND_BLOCK"
            ),
            "closing_rule_may_not_use_goals_errors_nll_or_calibration_results": True,
            "minimum_complete_case_fixtures": MINIMUM_COMPLETE_CASE_FIXTURES,
            "qualifying_competition_min_fixtures": QUALIFYING_COMPETITION_MIN_FIXTURES,
            "minimum_qualifying_competitions": MINIMUM_QUALIFYING_COMPETITIONS,
            "minimum_non_legacy_qualifying_competitions": (
                MINIMUM_NON_LEGACY_QUALIFYING_COMPETITIONS
            ),
        },
        "fresh_confirmation_metrics": {
            "calibration_bins": [
                [0.0, 0.5],
                [0.5, 1.0],
                [1.0, 1.5],
                [1.5, 2.0],
                [2.0, 2.5],
                [2.5, 3.0],
                [3.0, None],
            ],
            "calibration_bin_semantics": (
                "LEFT_INCLUSIVE_RIGHT_EXCLUSIVE_FINAL_LEFT_INCLUSIVE_UNBOUNDED"
            ),
            "each_model_uses_own_predicted_rate_for_bin_assignment": True,
            "primary_metric": "MEAN_JOINT_POISSON_NEGATIVE_LOG_LIKELIHOOD",
            "required_pooled_gates": [
                "CALIBRATED_HOME_WACE_STRICTLY_BELOW_UNCALIBRATED_NATIVE",
                "CALIBRATED_HOME_WACE_STRICTLY_BELOW_ELO_ONLY",
                "CALIBRATED_HOME_WSCE_STRICTLY_BELOW_UNCALIBRATED_NATIVE",
                "CALIBRATED_HOME_WSCE_STRICTLY_BELOW_ELO_ONLY",
                "CALIBRATED_JOINT_NLL_STRICTLY_BELOW_ELO_ONLY",
                "CALIBRATED_JOINT_NLL_NOT_ABOVE_UNCALIBRATED_NATIVE",
                "NATIVE_AWAY_WACE_STRICTLY_BELOW_ELO_ONLY",
                "NATIVE_AWAY_WSCE_STRICTLY_BELOW_ELO_ONLY",
            ],
            "paired_fixture_identity_and_order_required": True,
        },
        "competition_robustness": {
            "qualifying_primary_id_min_fixtures": QUALIFYING_COMPETITION_MIN_FIXTURES,
            "minimum_qualifying_primary_id_clusters": MINIMUM_QUALIFYING_COMPETITIONS,
            "minimum_non_legacy_qualifying_primary_id_clusters": (
                MINIMUM_NON_LEGACY_QUALIFYING_COMPETITIONS
            ),
            "robustness_population": (
                "UNION_OF_FRESH_COMPLETE_CASE_FIXTURES_IN_QUALIFYING_PRIMARY_ID_CLUSTERS"
            ),
            "paired_difference": "CALIBRATED_NATIVE_JOINT_NLL_MINUS_ELO_ONLY_JOINT_NLL",
            "cluster": "PROVIDER_PRIMARY_ID",
            "delete_one_cluster_estimator": (
                "FIXTURE_WEIGHTED_MEAN_OF_REMAINING_PAIRED_FIXTURE_DIFFERENCES"
            ),
            "jackknife_interval": "FULL_ESTIMATE_PLUS_MINUS_1_96_TIMES_JACKKNIFE_SE",
            "jackknife_upper_95_must_be_strictly_below_zero": True,
            "minimum_fraction_of_qualifying_clusters_with_negative_mean_delta": (
                MINIMUM_NEGATIVE_COMPETITION_FRACTION
            ),
            "per_competition_nll_wace_wsce_and_missingness_report_required": True,
            "small_competitions_below_threshold_report_only": True,
        },
        "result_states": {
            "all_gates_pass": (
                "FRESH_HOLDOUT_CALIBRATION_AND_COMPETITION_ROBUSTNESS_SIGNAL_"
                "REVIEW_REQUIRED"
            ),
            "coverage_insufficient": (
                "FRESH_HOLDOUT_INSUFFICIENT_COVERAGE_NO_SUCCESSOR_DECISION"
            ),
            "performance_gate_failed": (
                "FRESH_HOLDOUT_CALIBRATION_OR_ROBUSTNESS_GATE_FAILED_REVIEW_REQUIRED"
            ),
            "automatic_successor_approval": False,
        },
        "runtime_caveats": {
            "cross_runtime_bit_identity_claimed": False,
            "known_pr77_machine_precision_canonicalization_gap_cleared": False,
        },
        "safety": {key: False for key in SAFETY_KEYS},
    }

def canonical_fresh_holdout_home_calibration_competition_identity_protocol_bytes(
    value: Mapping[str, Any] | None = None,
) -> bytes:
    payload = (
        build_fresh_holdout_home_calibration_competition_identity_protocol()
        if value is None
        else dict(value)
    )
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")

__all__ = [
    "BASE_MAIN_SHA",
    "HOME_CALIBRATION_INTERCEPT_HEX",
    "HOME_CALIBRATION_SLOPE_HEX",
    "LEGACY_PRIMARY_IDS",
    "NEXT_REQUIRED_BOUNDARY",
    "PROTOCOL_ID",
    "PROTOCOL_STATE",
    "apply_frozen_home_calibration",
    "build_fresh_holdout_home_calibration_competition_identity_protocol",
    "canonical_fresh_holdout_home_calibration_competition_identity_protocol_bytes",
]
