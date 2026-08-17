import hashlib

import pytest

import domain.fotmob_utc_native_expected_goals_model_validation_protocol as p


def _protocol():
    return p.build_fotmob_utc_native_expected_goals_model_validation_protocol()


def test_protocol_identity_and_successful_v2_lineage_are_frozen():
    protocol = _protocol()
    raw = p.canonical_fotmob_utc_native_expected_goals_model_validation_protocol_bytes()
    evidence = protocol["v2_success_evidence"]

    assert protocol["base_main_sha"] == "cd67be14f6a4f09484d18a57de360b8a5d4c51d7"
    assert protocol["protocol_state"] == p.PROTOCOL_STATE
    assert evidence["run_id"] == 31990121181
    assert evidence["command_comment_id"] == 5311311034
    assert evidence["attempt_comment_id"] == 5311311868
    assert evidence["result_comment_id"] == 5311318782
    assert evidence["artifact_id"] == 9275052993
    assert evidence["artifact_size_bytes"] == 23349191
    assert evidence["artifact_sha256"] == p.V2_RESULT_ARTIFACT_SHA256
    assert evidence["projection_size_bytes"] == 23342076
    assert evidence["projection_sha256"] == p.V2_PROJECTION_SHA256
    assert evidence["record_count"] == p.V2_PROJECTION_ROWS == 21326
    assert evidence["unique_fixture_count"] == 21326
    assert evidence["identity_or_lineage_conflict_count"] == 0
    assert len(raw) == p.PROTOCOL_SIZE == 15157
    assert hashlib.sha256(raw).hexdigest() == p.PROTOCOL_SHA256
    assert p.PROTOCOL_SHA256 == (
        "7dbae5deb711a1d456fb1304616b2f0b6741ffd2039154806f953221a61e06f6"
    )


def test_input_contract_uses_exact_five_numeric_features_without_imputation():
    contract = _protocol()["frozen_input_contract"]
    assert contract["targets"] == ["home_goals", "away_goals"]
    assert contract["predictors"] == [
        "home_elo_centered_scaled",
        "away_elo_centered_scaled",
        "home_form_centered",
        "away_form_centered",
        "fatigue_raw",
    ]
    assert contract["predictor_transforms"] == {
        "home_elo_centered_scaled": "(home_elo-1500)/400",
        "away_elo_centered_scaled": "(away_elo-1500)/400",
        "home_form_centered": "home_form-0.5",
        "away_form_centered": "away_form-0.5",
        "fatigue_raw": "fatigue",
    }
    assert contract["complete_case_row_count"] == 21129
    assert contract["dropped_row_count"] == 197
    assert contract["historical_live_data_freshness_as_predictor"] is False
    assert contract["zero_or_constant_imputation_for_missing_predictors"] is False
    assert contract["full_athena_competition_universe_claimed"] is False


def test_common_population_is_frozen_before_any_arm_reduction():
    common = _protocol()["common_population_contract"]
    assert common["membership_rule"] == (
        "FULL_FIVE_PREDICTOR_COMPLETE_CASE_MEMBERSHIP_FROZEN_BEFORE_ARM_REDUCTION;"
        "REDUCED_ARMS_DO_NOT_RERUN_ELIGIBILITY"
    )
    assert common["all_complete_rows"] == 21129
    assert common["train_rows"] == 14181
    assert common["evaluation_a_rows"] == 3471
    assert common["evaluation_b_rows"] == 3477
    assert common["pooled_evaluation_rows"] == 6948
    assert common["all_complete_membership_sha256"] == (
        "1374fd323bd5aa7e6da6cee23358621c26435297c2e195553e227373008fd8ed"
    )
    assert common["train_membership_sha256"] == (
        "4c017b9e43ab9e2f231e88187339a3960c5fdfbd087f21ba92ca8855576219a9"
    )
    assert common["evaluation_a_membership_sha256"] == (
        "4361cd60976170bd14442502025160d9b3aa97717fb94afc1b68eee9b88c429f"
    )
    assert common["evaluation_b_membership_sha256"] == (
        "4910b5db577bd87fd4bed4e24f3b1e00dff85d58f23e7ea8558cfba0aa5efd59"
    )
    assert common["pooled_evaluation_membership_sha256"] == (
        "f4d713a739feeac90c166f5125dd80ab7e3063598f9ad0187f07d10b88e5bcdc"
    )
    assert common["reduced_predictor_arms_may_not_admit_additional_rows"] is True
    assert common["paired_comparison_membership_mismatch_fails_closed"] is True


def test_every_arm_uses_the_exact_common_population():
    arms = _protocol()["candidate_arms"]
    assert [arm["id"] for arm in arms] == [
        "FOTMOB_NATIVE_SAME_FAMILY_REFIT",
        "HISTORICAL_FIXED_COEFFICIENT_TRANSFER",
        "FOTMOB_NATIVE_ELO_ONLY_NESTED_GLM",
        "FOTMOB_NATIVE_NO_FATIGUE_ABLATION",
        "TRAIN_ONLY_GLOBAL_HOME_AWAY_MEAN_BASELINE",
    ]
    assert {arm["evaluation_population"] for arm in arms} == {
        "EXACT_COMMON_A_B_AND_POOLED"
    }
    assert arms[0]["fit_population"] == "EXACT_COMMON_TRAIN"
    assert arms[1]["fit_population"] == "NONE"
    assert arms[2]["fit_population"] == "EXACT_COMMON_TRAIN_NO_ELIGIBILITY_RERUN"
    assert arms[3]["fit_population"] == "EXACT_COMMON_TRAIN_NO_ELIGIBILITY_RERUN"
    assert arms[4]["fit_population"] == "EXACT_COMMON_TRAIN"


def test_chronological_split_is_frozen_and_not_mislabeled_as_prospective():
    split = _protocol()["chronological_split_contract"]
    assert split["train"]["expected_complete_case_rows"] == 14181
    assert split["evaluation_a"]["expected_complete_case_rows"] == 3471
    assert split["evaluation_b_terminal"]["expected_complete_case_rows"] == 3477
    assert (
        split["train"]["expected_complete_case_rows"]
        + split["evaluation_a"]["expected_complete_case_rows"]
        + split["evaluation_b_terminal"]["expected_complete_case_rows"]
        == 21129
    )
    assert split["same_kickoff_must_share_partition"] is True
    assert split["random_train_test_split_forbidden"] is True
    assert split["random_kfold_forbidden"] is True
    assert split["generic_cv5_forbidden"] is True
    assert split["evaluation_labels_used_for_fit_or_tuning"] is False
    assert split["post_evaluation_refit_authorized"] is False
    assert split["evaluation_b_terminal"]["label"] == (
        "CHRONOLOGICALLY_LATER_RETROSPECTIVE_EVALUATION_NOT_PROSPECTIVE_HOLDOUT"
    )


def test_reuses_exact_deterministic_poisson_glm_contract_without_new_tuning():
    fitter = _protocol()["frozen_fitter_contract"]
    assert fitter["implementation_family"] == (
        "REUSE_EXACT_HISTORICAL_SUCCESSOR_DETERMINISTIC_FITTER"
    )
    assert fitter["historical_protocol_blob_is_transitive_fitting_contract"] is True
    assert fitter["algorithm"] == "DETERMINISTIC_NEWTON_POISSON_GLM_WITH_BACKTRACKING_V1"
    assert fitter["scalar_reduction"] == "MATH_FSUM"
    assert fitter["intercept_initialization"] == "LOG_OF_TRAINING_RESPONSE_MEAN"
    assert fitter["non_intercept_initialization"] == "ZERO"
    assert fitter["linear_solver"] == "DETERMINISTIC_GAUSSIAN_ELIMINATION_PARTIAL_PIVOT"
    assert fitter["regularization"] == "NONE"
    assert fitter["hyperparameter_search_authorized"] is False
    assert fitter["sklearn_poisson_regressor_substitution_authorized"] is False
    assert fitter["standardization_refit_authorized"] is False
    assert fitter["coefficient_rounding_places"] == 12


def test_historical_fixed_transfer_coefficients_are_exact_and_unapproved():
    prior = _protocol()["historical_successor_prior"]
    assert prior["historical_home_coefficients"] == list(
        p.HISTORICAL_HOME_COEFFICIENTS
    )
    assert prior["historical_away_coefficients"] == list(
        p.HISTORICAL_AWAY_COEFFICIENTS
    )
    assert prior["historical_candidate_sha256"] == (
        "1fe9ff5f0963355bb98ae93d205a5ea3cb9aa53592601a7b06ff4000f6091660"
    )
    assert prior["historical_robustness_sha256"] == (
        "3ff465edef9c4abd2f0d4dfcb4f776fea64103c0dc26941f44d2b09ba2e4066b"
    )
    assert prior["prior_result_authorizes_current_model_use"] is False


def test_calibration_arithmetic_and_empty_bins_are_fully_frozen():
    calibration = _protocol()["evaluation_contract"]["calibration_contract"]
    assert calibration["populations"] == [
        "EVALUATION_A",
        "EVALUATION_B_TERMINAL",
        "POOLED_A_PLUS_B",
    ]
    assert calibration["strong_signal_calibration_population"] == "POOLED_A_PLUS_B"
    assert calibration["same_fixture_population_required_for_all_models"] is True
    assert calibration["bin_assignment"] == "EACH_MODEL_ASSIGNED_BY_ITS_OWN_PREDICTED_RATE"
    assert calibration["interval_semantics"] == (
        "LEFT_INCLUSIVE_RIGHT_EXCLUSIVE;FINAL_BIN_LEFT_INCLUSIVE_UNBOUNDED"
    )
    assert calibration["empty_bin_representation"] == {
        "count": 0,
        "mean_predicted_goals": None,
        "mean_observed_goals": None,
        "calibration_error_predicted_minus_observed": None,
    }
    assert calibration["wace_formula"] == (
        "SUM(COUNT_B*ABS(PREDICTED_MINUS_OBSERVED_ERROR_B))/N_POPULATION"
    )
    assert calibration["wsce_formula"] == (
        "SUM(COUNT_B*(PREDICTED_MINUS_OBSERVED_ERROR_B**2))/N_POPULATION"
    )
    assert calibration["bin_counts_must_sum_to_population_count"] is True
    assert (
        calibration["empty_bins_contribute_zero_weight_not_fabricated_zero_error"]
        is True
    )


def test_quarter_jackknife_cluster_ids_counts_and_arithmetic_are_exact():
    robustness = _protocol()["evaluation_contract"]["temporal_robustness"]
    assert robustness["population"] == "POOLED_A_PLUS_B"
    assert robustness["population_rows"] == 6948
    assert robustness["cluster_count"] == 9
    assert robustness["cluster_keys_and_counts"] == [
        ["2024-Q3", 626],
        ["2024-Q4", 1017],
        ["2025-Q1", 1073],
        ["2025-Q2", 755],
        ["2025-Q3", 599],
        ["2025-Q4", 1020],
        ["2026-Q1", 1097],
        ["2026-Q2", 721],
        ["2026-Q3", 40],
    ]
    assert sum(count for _, count in robustness["cluster_keys_and_counts"]) == 6948
    assert robustness["delete_cluster_estimator"] == (
        "FIXTURE_WEIGHTED_ARITHMETIC_MEAN_OF_REMAINING_PAIRED_FIXTURE_DIFFERENCES"
    )
    assert robustness["delete_estimate_center"] == (
        "UNWEIGHTED_ARITHMETIC_MEAN_OF_EXACTLY_9_DELETE_ONE_QUARTER_ESTIMATES"
    )
    assert robustness["jackknife_standard_error_formula"] == (
        "SQRT(((K_MINUS_1)/K)*SUM((THETA_DELETE_J-THETA_BAR)^2))"
    )
    assert robustness["interval_multiplier"] == 1.96
    assert robustness["interval_formula"] == (
        "FULL_THETA_PLUS_MINUS_1_96_TIMES_JACKKNIFE_STANDARD_ERROR"
    )
    assert robustness["upper_bound_gate"] == (
        "FULL_THETA_PLUS_1_96_TIMES_JACKKNIFE_STANDARD_ERROR_STRICTLY_BELOW_ZERO"
    )


def test_strong_signal_requires_nll_temporal_and_pooled_calibration_advantage():
    evaluation = _protocol()["evaluation_contract"]
    rule = evaluation["strong_signal_rule"]
    assert all(value is True for value in rule.values())
    assert set(rule) == {
        "all_lineage_split_missingness_and_common_membership_checks_pass",
        "native_home_and_away_fits_converge",
        "native_minus_elo_evaluation_a_nll_strictly_below_zero",
        "native_minus_elo_evaluation_b_nll_strictly_below_zero",
        "native_minus_elo_pooled_nll_strictly_below_zero",
        "quarter_jackknife_upper_95_percent_bound_strictly_below_zero",
        "pooled_native_home_wace_strictly_below_pooled_elo_home_wace",
        "pooled_native_away_wace_strictly_below_pooled_elo_away_wace",
        "pooled_native_home_wsce_strictly_below_pooled_elo_home_wsce",
        "pooled_native_away_wsce_strictly_below_pooled_elo_away_wsce",
    }
    assert evaluation["automatic_model_approval"] is False
    assert evaluation["score_matrix_evaluation_in_this_boundary"] is False
    assert evaluation["market_probability_evaluation_in_this_boundary"] is False
    assert evaluation["bookmaker_price_evaluation_in_this_boundary"] is False


def test_competition_robustness_remains_blocked_not_reconstructed():
    evaluation = _protocol()["evaluation_contract"]
    assert evaluation["competition_or_league_robustness_status"] == (
        "BLOCKED_PROJECTION_DOES_NOT_CARRY_COMPETITION_IDENTITY"
    )
    assert (
        evaluation["competition_identity_may_not_be_invented_or_fuzzily_reconstructed"]
        is True
    )


def test_legacy_total_goals_and_empty_model_placeholders_remain_quarantined():
    legacy = _protocol()["legacy_quarantine"]
    assert legacy["goals_model_joblib_blob_sha"] == (
        "bdee71fd6c0b74f5343e8e01e010dd8032d6c694"
    )
    assert legacy["train_model_blob_sha"] == (
        "0f4722f352b03f72540ca5621dc1f75dd9691b7e"
    )
    assert legacy["legacy_goals_model_semantics"] == (
        "RANDOM_FOREST_TOTAL_MATCH_GOALS_NOT_SEPARATE_HOME_AWAY_INTENSITIES"
    )
    assert legacy["legacy_model_authorized_as_expected_goals_model"] is False
    assert legacy["empty_expected_goals_poisson_dixon_coles_placeholders_implemented"] is False


def test_protocol_fails_closed_when_local_lineage_drifts(monkeypatch):
    original = p._git_blob_sha

    def drift(path):
        if path.name == "historical_expected_goals_successor_protocol.py":
            return "0" * 40
        return original(path)

    monkeypatch.setattr(p, "_git_blob_sha", drift)
    with pytest.raises(
        p.FotMobUTCNativeExpectedGoalsModelValidationProtocolError,
        match="frozen implementation lineage changed",
    ):
        p.build_fotmob_utc_native_expected_goals_model_validation_protocol()


def test_receipt_requires_membership_calibration_and_quarter_reconciliation():
    protocol = _protocol()
    receipt = protocol["execution_receipt_requirements"]
    assert receipt["must_recompute_and_match_common_population_membership_hashes"] is True
    assert receipt["must_report_exact_arm_membership_hashes_and_reject_mismatch"] is True
    assert receipt["must_report_calibration_tables_for_a_b_and_pooled"] is True
    assert receipt["must_report_all_nine_quarter_counts_delete_estimates_and_interval"] is True
    assert receipt["must_emit_hash_sealed_predictions_and_model_validation_receipt"] is True
    assert receipt["must_not_write_production_model_artifact"] is True
    assert receipt["must_not_calculate_score_matrix_market_prices_or_selections"] is True


def test_forbidden_shortcuts_explicitly_close_reviewed_ambiguities():
    forbidden = set(_protocol()["forbidden_shortcuts"])
    assert "DO_NOT_RERUN_ELIGIBILITY_FOR_REDUCED_PREDICTOR_ARMS" in forbidden
    assert "DO_NOT_COMPARE_MODELS_ON_DIFFERENT_FIXTURE_POPULATIONS" in forbidden
    assert "DO_NOT_WEIGHT_JACKKNIFE_DELETE_ESTIMATE_CENTER_BY_REMAINING_FIXTURE_COUNTS" in forbidden
    assert "DO_NOT_TREAT_EMPTY_CALIBRATION_BINS_AS_ZERO_ERROR_OBSERVATIONS" in forbidden
    assert "DO_NOT_SWITCH_TO_SKLEARN_POISSON_REGRESSOR_OR_ADD_ALPHA_SEARCH" in forbidden
    assert "DO_NOT_INVENT_COMPETITION_OR_LEAGUE_IDENTITY_FROM_THIS_PROJECTION" in forbidden


def test_all_downstream_authority_stays_exact_false():
    protocol = _protocol()
    assert protocol["next_required_boundary"] == (
        "IMPLEMENT_REVIEWED_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION"
    )
    assert set(protocol["safety"]) == p.SAFETY_KEYS
    assert all(type(value) is bool and value is False for value in protocol["safety"].values())
