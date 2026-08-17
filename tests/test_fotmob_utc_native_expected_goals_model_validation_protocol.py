import hashlib

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
    assert evidence["result_comment_id"] == 5311318782
    assert evidence["artifact_id"] == 9275052993
    assert evidence["artifact_sha256"] == p.V2_RESULT_ARTIFACT_SHA256
    assert evidence["projection_sha256"] == p.V2_PROJECTION_SHA256
    assert evidence["record_count"] == p.V2_PROJECTION_ROWS == 21326
    assert evidence["unique_fixture_count"] == 21326
    assert evidence["identity_or_lineage_conflict_count"] == 0
    assert len(raw) == p.PROTOCOL_SIZE == 6331
    assert hashlib.sha256(raw).hexdigest() == p.PROTOCOL_SHA256
    assert p.PROTOCOL_SHA256 == (
        "2e2ad8d063444d406f0f76014f294905a99f237593928be13b6462be11082f73"
    )


def test_targets_are_separate_home_and_away_goal_intensities():
    contract = _protocol()["frozen_input_contract"]
    assert contract["targets"] == ["home_goals", "away_goals"]
    assert contract["predictors"] == [
        "home_form", "away_form", "home_elo", "away_elo", "fatigue"
    ]
    assert contract["complete_case_row_count"] == 21129
    assert contract["historical_live_data_freshness_as_predictor"] is False
    assert contract["team_identifiers_as_predictors"] is False
    assert contract["fixture_identifier_as_predictor"] is False
    assert contract["zero_or_constant_imputation_for_missing_predictors"] is False
    assert contract["full_athena_competition_universe_claimed"] is False


def test_split_is_strictly_chronological_and_terminal_holdout_is_untouched():
    split = _protocol()["chronological_split_contract"]
    assert split["train"]["expected_complete_case_rows"] == 14181
    assert split["validation"]["expected_complete_case_rows"] == 3471
    assert split["terminal_holdout"]["expected_complete_case_rows"] == 3477
    assert sum(
        split[name]["expected_complete_case_rows"]
        for name in ("train", "validation", "terminal_holdout")
    ) == 21129
    assert split["same_kickoff_must_share_partition"] is True
    assert split["random_train_test_split_forbidden"] is True
    assert split["random_kfold_forbidden"] is True
    assert split["generic_cv5_forbidden"] is True
    assert split["terminal_holdout_used_for_tuning"] is False


def test_candidate_family_is_separate_poisson_regression_not_legacy_total_goals():
    candidate = _protocol()["candidate_model_contract"]
    primary = candidate["primary"]
    assert primary["implementation_family"] == "sklearn.linear_model.PoissonRegressor"
    assert primary["separate_home_and_away_models"] is True
    assert primary["alpha_grid"] == [0.0, 0.01, 0.1, 1.0]
    assert primary["alpha_selection_data"] == "validation_only"
    assert primary["refit_after_selection"] == "train_plus_validation_only"
    assert primary["terminal_holdout_labels_used_for_refit"] is False
    assert candidate["legacy_total_goals_model_eligible"] is False
    assert candidate[
        "empty_expected_goals_poisson_dixon_coles_placeholders_eligible"
    ] is False


def test_qualification_requires_terminal_improvement_without_hidden_market_authority():
    evaluation = _protocol()["evaluation_contract"]
    rule = evaluation["qualification_rule"]
    assert rule["combined_terminal_poisson_deviance_must_beat_baseline"] is True
    assert rule["home_terminal_poisson_deviance_must_not_exceed_baseline"] is True
    assert rule["away_terminal_poisson_deviance_must_not_exceed_baseline"] is True
    assert evaluation["score_matrix_evaluation_in_this_boundary"] is False
    assert evaluation["market_probability_evaluation_in_this_boundary"] is False
    assert evaluation["bookmaker_price_evaluation_in_this_boundary"] is False


def test_legacy_training_path_is_explicitly_quarantined():
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
    assert legacy[
        "legacy_calibrated_classifier_cv5_authorized_as_temporal_validation_template"
    ] is False


def test_execution_receipt_is_research_only_and_all_authority_stays_false():
    protocol = _protocol()
    receipt = protocol["execution_receipt_requirements"]
    assert receipt["must_revalidate_v2_artifact_archive_sha256_and_size"] is True
    assert receipt["must_report_exact_split_counts"] is True
    assert receipt[
        "must_emit_hash_sealed_predictions_and_model_validation_receipt"
    ] is True
    assert receipt["must_not_write_production_model_artifact"] is True
    assert receipt["must_not_calculate_market_prices_or_selections"] is True
    assert protocol["next_required_boundary"] == (
        "IMPLEMENT_REVIEWED_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION"
    )
    assert set(protocol["safety"]) == p.SAFETY_KEYS
    assert all(value is False for value in protocol["safety"].values())
