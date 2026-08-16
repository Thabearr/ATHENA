import hashlib

import domain.fotmob_utc_native_successor_feature_construction_protocol as p


def _protocol():
    return p.build_fotmob_utc_native_successor_feature_construction_protocol()


def test_protocol_revalidates_frozen_pr119_lineage_and_canonical_identity():
    protocol = _protocol()
    raw = p.canonical_fotmob_utc_native_successor_feature_construction_protocol_bytes()

    assert protocol["base_main_sha"] == (
        "4a2ca10af4b14194253ba6fc84bca780e2b03d58"
    )
    assert protocol["protocol_state"] == (
        "PRE_REGISTERED_NOT_EXECUTED_FOTMOB_UTC_NATIVE_FEATURE_CONSTRUCTION_UNQUALIFIED"
    )
    assert len(raw) == p.PROTOCOL_SIZE == 5803
    assert hashlib.sha256(raw).hexdigest() == p.PROTOCOL_SHA256
    assert p.PROTOCOL_SHA256 == (
        "948b34e5f5ca6d69895beed0b0cdb79368bc507015f45975f2b3192b619975db"
    )


def test_scope_is_exact_pr119_history_not_global_fotmob_coverage():
    scope = _protocol()["frozen_history_scope"]

    assert scope["qualified_ordinary_ft_row_count"] == 21326
    assert scope["kickoff_utc_min"] == "2020-08-01T11:30:00Z"
    assert scope["kickoff_utc_max"] == "2026-08-14T19:15:00Z"
    assert scope["historical_request_date_end"] == "2026-08-14"
    assert scope["full_athena_competition_universe_claimed"] is False
    assert scope["global_fotmob_historical_coverage_claimed"] is False
    assert len(scope["model_league_codes"]) == 11


def test_time_basis_is_aware_utc_only_and_never_source_local_projection():
    time_basis = _protocol()["time_basis"]

    assert time_basis["canonical_coordinate"] == "STATUS_UTCTIME_AWARE_UTC"
    assert time_basis["raw_field"] == "status.utcTime"
    assert time_basis["timezone_conversion_permitted"] is False
    assert time_basis["display_time_field_used"] is False
    assert time_basis["europe_oslo_projection_used"] is False
    assert time_basis["naive_datetime_used"] is False
    assert time_basis["pr69_source_local_equivalence_claimed"] is False
    assert time_basis["pr80_source_local_parity_claimed"] is False


def test_row_admission_requires_exact_qualified_raw_lineage():
    admission = _protocol()["row_admission"]

    assert admission["must_be_exact_pr119_qualified_ordinary_ft_fixture"] is True
    assert admission["must_revalidate_raw_evidence_lineage"] is True
    assert admission["must_rederive_kickoff_utc_from_preserved_raw_status_utctime"] is True
    assert admission[
        "must_match_pr119_fixture_id_team_identity_and_regulation_ft_score"
    ] is True
    assert admission["special_result_rows_forbidden"] is True
    assert admission[
        "post_2026_08_14_rows_forbidden_without_separate_contiguous_extension"
    ] is True


def test_same_kickoff_fixtures_cannot_leak_into_each_other():
    chronology = _protocol()["chronology"]

    assert chronology["strict_prior_rule"] == (
        "history_kickoff_utc < target_kickoff_utc"
    )
    assert chronology["same_kickoff_policy"] == (
        "COMPUTE_ALL_FEATURES_FROM_PRE_GROUP_STATE_THEN_BATCH_APPLY_RESULTS"
    )
    assert chronology["fixture_id_role"] == (
        "DETERMINISTIC_OUTPUT_ORDER_ONLY_NOT_PRIOR_MEMBERSHIP"
    )
    assert chronology["cross_timezone_comparison_forbidden"] is True


def test_form_elo_and_fatigue_math_is_explicit_without_source_local_clock():
    features = _protocol()["feature_contract"]

    for key in ("home_form", "away_form"):
        assert features[key]["history"] == (
            "last_up_to_5_strictly_prior_same_team_ordinary_ft_rows"
        )
        assert features[key]["points"] == "win=3,draw=1,loss=0"
        assert features[key]["no_prior_history_status"] == "MISSING"
        assert features[key]["default_forbidden"] is True

    for key in ("home_elo", "away_elo"):
        assert features[key]["initial_rating"] == 1500
        assert features[key]["initialization_classification"] == (
            "SOURCE_NATIVE_REPLAY_ASSUMPTION_NOT_OBSERVED_EVIDENCE"
        )
        assert features[key]["season_reset"] is False
        assert features[key]["same_kickoff_updates_after_group"] is True

    fatigue = features["fatigue"]
    assert fatigue["differential"] == "home_rest_days - away_rest_days"
    assert fatigue["missing_prior_history_status"] == "MISSING"
    assert fatigue["timezone_conversion_forbidden"] is True


def test_historical_freshness_remains_unknown_and_out_of_training_features():
    freshness = _protocol()["feature_contract"]["historical_live_data_freshness"]

    assert freshness["status"] == "NOT_RECONSTRUCTIBLE_WITH_CURRENT_EVIDENCE"
    assert freshness["numeric_default_forbidden"] is True
    assert freshness["excluded_from_historical_training_features"] is True
    assert freshness["prospective_freshness_gate_remains_separate"] is True


def test_execution_is_feature_materialization_only():
    execution = _protocol()["qualification_execution"]

    assert execution["must_report_total_rows_seen"] is True
    assert execution["must_report_per_feature_available_missing_blocked_counts"] is True
    assert execution["must_report_same_kickoff_group_count"] is True
    assert execution["must_report_identity_or_lineage_conflicts"] is True
    assert execution["must_emit_canonical_hash_sealed_projection"] is True
    assert execution["must_not_fit_or_tune_expected_goals_model"] is True
    assert execution["must_not_calculate_market_probabilities"] is True
    assert execution["must_not_use_bookmaker_data"] is True


def test_no_source_local_shortcut_or_downstream_authority_is_created():
    protocol = _protocol()

    assert "DO_NOT_LABEL_NAIVE_UTC_AS_SOURCE_LOCAL_TIME" in (
        protocol["forbidden_shortcuts"]
    )
    assert "DO_NOT_CLAIM_PR69_OR_PR80_TIME_PARITY" in (
        protocol["forbidden_shortcuts"]
    )
    assert protocol["next_required_boundary"] == (
        "EXECUTE_REVIEWED_FOTMOB_UTC_NATIVE_SUCCESSOR_FEATURE_CONSTRUCTION_QUALIFICATION"
    )
    assert set(protocol["safety"]) == p.SAFETY_KEYS
    assert all(value is False for value in protocol["safety"].values())
