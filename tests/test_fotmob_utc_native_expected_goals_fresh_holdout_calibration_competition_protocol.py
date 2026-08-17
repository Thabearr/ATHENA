import math

import pytest

from domain.fotmob_utc_native_expected_goals_fresh_holdout_calibration_competition_protocol import (
    BASE_MAIN_SHA,
    HOME_CALIBRATION_INTERCEPT_HEX,
    HOME_CALIBRATION_SLOPE_HEX,
    LEGACY_PRIMARY_IDS,
    NEXT_REQUIRED_BOUNDARY,
    PROTOCOL_SHA256,
    PROTOCOL_SIZE,
    apply_frozen_home_calibration,
    build_fresh_holdout_home_calibration_competition_identity_protocol,
    canonical_fresh_holdout_home_calibration_competition_identity_protocol_bytes,
)


def test_protocol_pins_reviewed_parent_and_consumed_development_evidence() -> None:
    protocol = build_fresh_holdout_home_calibration_competition_identity_protocol()
    assert BASE_MAIN_SHA == "5c46aa8fcaf4338e8968c50e1c852301f8e2e0cd"
    parent = protocol["reviewed_parent"]
    assert parent["result_review_blob_sha"] == "025a35d1d3b17e49a200dfe654304368fba39add"
    assert parent["xg_validator_blob_sha"] == "0421506b9e6e398c3469bb69196ef8fcad04f2a5"
    assert parent["execution_run_id"] == 32049714066
    assert parent["result_artifact_id"] == 9294215497
    assert parent["development_rows"] == 6948
    assert parent["reviewed_state_required"].endswith("SUCCESSOR_NOT_APPROVED")
    assert parent["sole_failed_strong_check_required"] == (
        "pooled_native_home_wace_strictly_below_pooled_elo_home_wace"
    )


def test_home_calibration_is_frozen_monotone_positive_and_not_retunable() -> None:
    protocol = build_fresh_holdout_home_calibration_competition_identity_protocol()
    calibration = protocol["development_only_calibration"]
    assert calibration["labels_are_consumed_not_fresh"] is True
    assert calibration["intercept_hex"] == HOME_CALIBRATION_INTERCEPT_HEX
    assert calibration["slope_hex"] == HOME_CALIBRATION_SLOPE_HEX
    assert calibration["further_parameter_tuning_after_protocol_merge_forbidden"] is True
    assert float.fromhex(HOME_CALIBRATION_SLOPE_HEX) > 0.0
    values = [0.25, 0.5, 1.0, 2.0, 4.0]
    calibrated = [apply_frozen_home_calibration(value) for value in values]
    assert all(value > 0.0 and math.isfinite(value) for value in calibrated)
    assert calibrated == sorted(calibrated)
    with pytest.raises(ValueError):
        apply_frozen_home_calibration(0.0)


def test_development_diagnostics_are_not_relabelled_as_confirmation() -> None:
    protocol = build_fresh_holdout_home_calibration_competition_identity_protocol()
    calibration = protocol["development_only_calibration"]
    diagnostics = calibration["development_diagnostics_not_confirmation"]
    assert diagnostics["calibrated_home_wace"] < diagnostics["native_home_wace"]
    assert diagnostics["calibrated_home_wace"] < diagnostics["elo_only_home_wace"]
    assert diagnostics["calibrated_home_wsce"] < diagnostics["native_home_wsce"]
    assert diagnostics["calibrated_home_mean_nll"] < diagnostics["native_home_mean_nll"]


def test_competition_identity_uses_exact_provider_ids_not_legacy_codes_or_names() -> None:
    protocol = build_fresh_holdout_home_calibration_competition_identity_protocol()
    identity = protocol["competition_identity"]
    assert identity["wrapper_primary_id_field"] == "leagues[].primaryId"
    assert identity["wrapper_id_field"] == "leagues[].id"
    assert identity["fixture_wrapper_id_field"] == "leagues[].matches[].leagueId"
    assert identity["fixture_id_field"] == "leagues[].matches[].id"
    assert identity["fixture_wrapper_id_must_equal_wrapper_id"] is True
    assert identity["primary_id_must_be_positive_integer"] is True
    assert identity["wrapper_id_must_be_positive_integer"] is True
    assert identity["fixture_id_must_be_positive_integer"] is True
    assert identity["fuzzy_name_mapping_forbidden"] is True
    assert identity["model_league_code_is_not_competition_identity"] is True
    assert tuple(identity["legacy_primary_ids"]) == LEGACY_PRIMARY_IDS
    assert identity["fresh_capture_scope_not_limited_to_legacy_primary_ids"] is True
    assert identity["non_legacy_identity_requires_fresh_structural_qualification"] is True
    assert identity["non_legacy_wrapper_admission_requires_exact_positive_ids_and_wrapper_match"] is True


def test_feature_semantics_do_not_silently_expand_history_scope() -> None:
    protocol = build_fresh_holdout_home_calibration_competition_identity_protocol()
    semantics = protocol["feature_semantics"]
    assert tuple(semantics["history_state_update_scope_primary_ids"]) == LEGACY_PRIMARY_IDS
    assert semantics["non_legacy_evaluation_fixture_may_be_scored_when_features_complete"] is True
    assert semantics["non_legacy_fixture_result_may_not_update_frozen_legacy_history_state"] is True
    assert semantics["historical_feature_scope_may_not_silently_expand_to_all_competitions"] is True
    assert semantics["missing_features_are_missing_not_imputed"] is True


def test_fresh_holdout_is_prospective_pre_kickoff_and_outcome_independent() -> None:
    protocol = build_fresh_holdout_home_calibration_competition_identity_protocol()
    fresh = protocol["prospective_confirmation"]
    assert fresh["not_before_utc"] == "2026-08-15T00:00:00Z"
    assert "REVIEWED_IMPLEMENTATION_MERGE_TIMESTAMP" in fresh["start_rule"]
    window = fresh["prediction_observation_window"]
    assert window["selection"] == "EARLIEST_QUALIFYING_CAPTURE_IN_WINDOW"
    assert window["capture_observed_at_must_be_on_or_after_holdout_start"] is True
    assert fresh["prediction_record_must_be_sealed_before_kickoff"] is True
    assert fresh["sealed_kickoff_utc_must_equal_settlement_kickoff_utc"] is True
    assert fresh["kickoff_drift_disposition"] == "EXCLUDE_PREDICTION_NO_REUSE_OR_RETIMING"
    assert fresh["no_post_kickoff_prediction_mutation"] is True
    assert fresh["no_confirmation_label_may_select_or_modify_calibration"] is True
    assert fresh["closing_rule_may_not_use_goals_errors_nll_or_calibration_results"] is True
    assert fresh["minimum_calendar_span_days"] == 28
    assert fresh["maximum_calendar_span_days"] == 90
    assert fresh["minimum_gate_evaluation_boundary_rule"] == (
        "HOLDOUT_START_UTC_PLUS_EXACTLY_28_CALENDAR_DAYS"
    )
    assert fresh["hard_close_boundary_rule"] == (
        "HOLDOUT_START_UTC_PLUS_EXACTLY_90_CALENDAR_DAYS"
    )
    assert fresh["scored_population_membership_rule"] == (
        "HOLDOUT_START_UTC<=QUALIFYING_CAPTURE_OBSERVED_AT_UTC_AND_"
        "HOLDOUT_START_UTC<=SEALED_KICKOFF_UTC<SELECTED_CLOSE_BOUNDARY_UTC"
    )
    assert fresh["settlement_after_selected_close_preserves_preclose_kickoff_membership"] is True
    assert fresh["minimum_complete_case_fixtures"] == 1000


def test_fresh_confirmation_rechecks_calibration_predictive_signal_and_competition_robustness() -> None:
    protocol = build_fresh_holdout_home_calibration_competition_identity_protocol()
    gates = protocol["fresh_confirmation_metrics"]["required_pooled_gates"]
    assert "CALIBRATED_HOME_WACE_STRICTLY_BELOW_ELO_ONLY" in gates
    assert "CALIBRATED_JOINT_NLL_STRICTLY_BELOW_ELO_ONLY" in gates
    assert "CALIBRATED_JOINT_NLL_NOT_ABOVE_UNCALIBRATED_NATIVE" in gates
    robustness = protocol["competition_robustness"]
    assert robustness["cluster"] == "PROVIDER_PRIMARY_ID"
    assert robustness["minimum_qualifying_primary_id_clusters"] == 8
    assert robustness["minimum_non_legacy_qualifying_primary_id_clusters"] == 2
    assert robustness["jackknife_reference_validator_blob_sha"] == (
        "0421506b9e6e398c3469bb69196ef8fcad04f2a5"
    )
    assert robustness["full_estimate"] == (
        "FIXTURE_WEIGHTED_MEAN_PAIRED_DELTA_ON_UNION_OF_QUALIFYING_PRIMARY_ID_CLUSTERS"
    )
    assert robustness["delete_one_cluster_estimator"] == (
        "FIXTURE_WEIGHTED_MEAN_OF_REMAINING_PAIRED_FIXTURE_DIFFERENCES"
    )
    assert robustness["delete_estimate_center"] == "ARITHMETIC_MEAN_OF_K_DELETE_ESTIMATES"
    assert robustness["jackknife_standard_error_formula"] == (
        "SQRT(((K-1)/K)*SUM((THETA_DELETE_I-THETA_BAR)^2))"
    )
    assert robustness["jackknife_interval_critical_value"] == 1.96
    assert robustness["jackknife_interval_center"] == "FULL_ESTIMATE"
    assert robustness["jackknife_upper_95_must_be_strictly_below_zero"] is True
    assert robustness["minimum_fraction_of_qualifying_clusters_with_negative_mean_delta"] == 0.75


def test_every_downstream_authority_remains_false_and_next_boundary_is_implementation() -> None:
    protocol = build_fresh_holdout_home_calibration_competition_identity_protocol()
    assert protocol["result_states"]["automatic_successor_approval"] is False
    assert protocol["runtime_caveats"]["cross_runtime_bit_identity_claimed"] is False
    assert all(value is False for value in protocol["safety"].values())
    assert NEXT_REQUIRED_BOUNDARY.startswith("IMPLEMENT_REVIEWED_FRESH_HOLDOUT_")


def test_protocol_canonical_bytes_are_deterministic() -> None:
    import hashlib

    first = canonical_fresh_holdout_home_calibration_competition_identity_protocol_bytes()
    second = canonical_fresh_holdout_home_calibration_competition_identity_protocol_bytes()
    assert first == second
    assert first.endswith(b"\n")
    assert len(first) == PROTOCOL_SIZE
    assert hashlib.sha256(first).hexdigest() == PROTOCOL_SHA256
