import hashlib

import pytest

import domain.fotmob_utc_native_expected_goals_model_validation_protocol as p


def _protocol():
    return p.build_fotmob_utc_native_expected_goals_model_validation_protocol()


def test_protocol_identity_and_successful_v2_lineage_are_frozen():
    protocol = _protocol()
    raw = p.canonical_fotmob_utc_native_expected_goals_model_validation_protocol_bytes()
    evidence = protocol["v2_success_evidence"]

    assert protocol["base_main_sha"] == (
        "cd67be14f6a4f09484d18a57de360b8a5d4c51d7"
    )
    assert protocol["protocol_state"] == p.PROTOCOL_STATE
    assert evidence["run_id"] == 31990121181
    assert evidence["command_comment_id"] == 5311311034
    assert evidence["attempt_comment_id"] == 5311311868
    assert evidence["result_comment_id"] == 5311318782
    assert evidence["artifact_id"] == 9275052993
    assert evidence["artifact_sha256"] == p.V2_RESULT_ARTIFACT_SHA256
    assert evidence["projection_sha256"] == p.V2_PROJECTION_SHA256
    assert evidence["record_count"] == p.V2_PROJECTION_ROWS == 21326
    assert evidence["unique_fixture_count"] == 21326
    assert evidence["identity_or_lineage_conflict_count"] == 0
    assert len(raw) == p.PROTOCOL_SIZE == 10903
    assert hashlib.sha256(raw).hexdigest() == p.PROTOCOL_SHA256
    assert p.PROTOCOL_SHA256 == (
        "0ae4966f4a048064f562f3a38218ff5731ce301b369918ed133bf150c1c6540a"
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


def test_reuses_reviewed_deterministic_poisson_glm_family_without_new_tuning():
    fitter = _protocol()["frozen_fitter_contract"]
    assert fitter["implementation_family"] == (
        "REUSE_EXACT_HISTORICAL_SUCCESSOR_DETERMINISTIC_FITTER"
    )
    assert fitter["algorithm"] == (
        "DETERMINISTIC_NEWTON_POISSON_GLM_WITH_BACKTRACKING_V1"
    )
    assert fitter["objective"] == (
        "SUM_INDEPENDENT_POISSON_NEGATIVE_LOG_LIKELIHOOD"
    )
    assert fitter["regularization"] == "NONE"
    assert fitter["hyperparameter_search_authorized"] is False
    assert fitter["sklearn_poisson_regressor_substitution_authorized"] is False
    assert fitter["standardization_refit_authorized"] is False
    assert fitter["coefficient_rounding_places"] == 12


def test_candidate_arms_include_native_refit_transfer_nested_ablated_and_constant():
    arms = _protocol()["candidate_arms"]
    assert [arm["id"] for arm in arms] == [
        "FOTMOB_NATIVE_SAME_FAMILY_REFIT",
        "HISTORICAL_FIXED_COEFFICIENT_TRANSFER",
        "FOTMOB_NATIVE_ELO_ONLY_NESTED_GLM",
        "FOTMOB_NATIVE_NO_FATIGUE_ABLATION",
        "TRAIN_ONLY_GLOBAL_HOME_AWAY_MEAN_BASELINE",
    ]
    assert arms[0]["primary_candidate"] is True
    assert arms[0]["fit_population"] == "TRAIN_ONLY"
    assert arms[1]["fit_population"] == "NONE"
    assert arms[2]["fit_population"] == "TRAIN_ONLY"
    assert arms[3]["fit_population"] == "TRAIN_ONLY"
    assert arms[4]["fit_population"] == "TRAIN_ONLY"


def test_historical_fixed_transfer_coefficients_are_exact():
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


def test_evaluation_contract_freezes_nll_calibration_and_temporal_robustness():
    evaluation = _protocol()["evaluation_contract"]
    assert evaluation["primary_metric"] == (
        "MEAN_JOINT_POISSON_NEGATIVE_LOG_LIKELIHOOD"
    )
    assert evaluation["calibration_bins"] == [
        [0.0, 0.5],
        [0.5, 1.0],
        [1.0, 1.5],
        [1.5, 2.0],
        [2.0, 2.5],
        [2.5, 3.0],
        [3.0, None],
    ]
    robustness = evaluation["temporal_robustness"]
    assert robustness["cluster_definition"] == "UTC_CALENDAR_YEAR_QUARTER"
    assert robustness["delete_one_cluster_estimates_required"] is True
    assert robustness["jackknife_standard_error_required"] is True
    assert robustness["normal_approximation_95_percent_interval_required"] is True
    assert evaluation["competition_or_league_robustness_status"] == (
        "BLOCKED_PROJECTION_DOES_NOT_CARRY_COMPETITION_IDENTITY"
    )
    assert (
        evaluation["competition_identity_may_not_be_invented_or_fuzzily_reconstructed"]
        is True
    )


def test_strong_signal_requires_temporal_and_calibration_advantage_but_no_auto_approval():
    evaluation = _protocol()["evaluation_contract"]
    rule = evaluation["strong_signal_rule"]
    assert all(value is True for value in rule.values())
    assert evaluation["strong_signal_state"] == (
        "STRONG_FOTMOB_UTC_NATIVE_SUCCESSOR_SIGNAL_REVIEW_REQUIRED"
    )
    assert evaluation["non_strong_signal_state"] == (
        "MIXED_OR_WEAK_FOTMOB_UTC_NATIVE_SUCCESSOR_SIGNAL_REVIEW_REQUIRED"
    )
    assert evaluation["automatic_model_approval"] is False
    assert evaluation["score_matrix_evaluation_in_this_boundary"] is False
    assert evaluation["market_probability_evaluation_in_this_boundary"] is False
    assert evaluation["bookmaker_price_evaluation_in_this_boundary"] is False


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


def test_receipt_is_research_only_and_all_downstream_authority_stays_false():
    protocol = _protocol()
    receipt = protocol["execution_receipt_requirements"]
    assert receipt["must_revalidate_v2_artifact_archive_sha256_and_size"] is True
    assert receipt["must_report_exact_complete_case_and_split_counts"] is True
    assert receipt["must_report_all_fit_coefficients_and_convergence_diagnostics"] is True
    assert receipt["must_report_all_quarter_delete_estimates_and_interval"] is True
    assert receipt["must_not_write_production_model_artifact"] is True
    assert receipt["must_not_calculate_score_matrix_market_prices_or_selections"] is True
    assert protocol["next_required_boundary"] == (
        "IMPLEMENT_REVIEWED_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION"
    )
    assert set(protocol["safety"]) == p.SAFETY_KEYS
    assert all(value is False for value in protocol["safety"].values())


def test_forbidden_shortcuts_explicitly_reject_sklearn_switch_and_league_invention():
    forbidden = set(_protocol()["forbidden_shortcuts"])
    assert "DO_NOT_SWITCH_TO_SKLEARN_POISSON_REGRESSOR_OR_ADD_ALPHA_SEARCH" in forbidden
    assert "DO_NOT_INVENT_COMPETITION_OR_LEAGUE_IDENTITY_FROM_THIS_PROJECTION" in forbidden
    assert "DO_NOT_USE_EVALUATION_LABELS_FOR_FIT_TUNING_OR_REFIT" in forbidden
