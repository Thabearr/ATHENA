from domain.fotmob_utc_native_expected_goals_model_validation_protocol import (
    AUTHORITY,
    BASELINES,
    CANDIDATE_MODEL_FAMILIES,
    FAIL_CLOSED_RULES,
    LEGACY_PATH_CLASSIFICATIONS,
    NUMERIC_MODEL_FEATURES,
    PROTOCOL_ID,
    PROTOCOL_VERSION,
    RUNTIME_TRUST_GATE_FEATURE,
    STATE,
    TARGETS,
    TEMPORAL_SPLIT,
    UPSTREAM_ARTIFACT_ID,
    UPSTREAM_ARTIFACT_SHA256,
    UPSTREAM_ARTIFACT_SIZE_BYTES,
    UPSTREAM_EXPECTED_ROWS,
    UPSTREAM_EXPECTED_UNIQUE_FIXTURES,
    UPSTREAM_MAIN_SHA,
    UPSTREAM_PROJECTION_SHA256,
    UPSTREAM_RESULT_COMMENT_ID,
    UPSTREAM_RUN_ID,
    protocol_receipt,
)


def test_exact_upstream_v2_lineage_is_frozen():
    assert UPSTREAM_MAIN_SHA == "cd67be14f6a4f09484d18a57de360b8a5d4c51d7"
    assert UPSTREAM_RUN_ID == 31990121181
    assert UPSTREAM_RESULT_COMMENT_ID == 5311318782
    assert UPSTREAM_ARTIFACT_ID == 9275052993
    assert UPSTREAM_ARTIFACT_SHA256 == (
        "f69ffad8f47faadb3ec743c96efa35fb6f4b43776a7650cf0414fb40455d29eb"
    )
    assert UPSTREAM_ARTIFACT_SIZE_BYTES == 23349191
    assert UPSTREAM_PROJECTION_SHA256 == (
        "5519ef40db3efc678c9eef73046c0e577e5f33a85f11b3fe043fc22bca2fcfed"
    )
    assert UPSTREAM_EXPECTED_ROWS == 21326
    assert UPSTREAM_EXPECTED_UNIQUE_FIXTURES == 21326


def test_protocol_is_result_free_and_not_executed():
    receipt = protocol_receipt()
    assert PROTOCOL_ID == "FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_V1"
    assert PROTOCOL_VERSION == 1
    assert STATE == "PRE_REGISTERED_NOT_EXECUTED"
    assert receipt["state"] == "PRE_REGISTERED_NOT_EXECUTED"
    assert "result" not in receipt
    assert "winner" not in receipt
    assert "selected_model" not in receipt


def test_freshness_is_a_runtime_trust_gate_not_a_numeric_surrogate():
    assert NUMERIC_MODEL_FEATURES == (
        "home_form",
        "away_form",
        "home_elo",
        "away_elo",
        "fatigue",
    )
    assert RUNTIME_TRUST_GATE_FEATURE == "live_data_freshness"
    assert RUNTIME_TRUST_GATE_FEATURE not in NUMERIC_MODEL_FEATURES
    assert TARGETS == ("home_goals", "away_goals")
    assert "NO_NUMERIC_FRESHNESS_SURROGATE" in FAIL_CLOSED_RULES


def test_legacy_model_paths_remain_unapproved():
    assert LEGACY_PATH_CLASSIFICATIONS["engine/score_engine.py"].endswith(
        "NOT_AUTHORIZED"
    )
    assert LEGACY_PATH_CLASSIFICATIONS["models/goals_model.joblib"].endswith(
        "NOT_AUTHORIZED"
    )
    assert LEGACY_PATH_CLASSIFICATIONS["tools/train_model.py"].endswith(
        "NOT_AUTHORIZED"
    )
    assert LEGACY_PATH_CLASSIFICATIONS["scripts/backfill_xg.py"].endswith(
        "NOT_AUTHORIZED"
    )
    assert LEGACY_PATH_CLASSIFICATIONS["models/expected_goals.py"] == (
        "PLACEHOLDER_NOT_IMPLEMENTATION"
    )


def test_candidate_families_and_baselines_are_pre_registered_without_selection():
    assert CANDIDATE_MODEL_FAMILIES == (
        "POISSON_REGRESSION_L2_HOME_AND_AWAY",
        "HISTOGRAM_GRADIENT_BOOSTING_POISSON_HOME_AND_AWAY",
    )
    assert BASELINES == (
        "GLOBAL_HOME_AWAY_MEAN_BASELINE",
        "STRICTLY_PRIOR_ROLLING_COMPETITION_MEAN_BASELINE",
    )
    receipt = protocol_receipt()
    assert "selected_model" not in receipt


def test_temporal_holdout_is_strict_and_not_misrepresented_as_prospective():
    assert TEMPORAL_SPLIT["development_seasons"] == (
        "2020-21",
        "2021-22",
        "2022-23",
        "2023-24",
    )
    assert TEMPORAL_SPLIT["validation_season"] == "2024-25"
    assert TEMPORAL_SPLIT["final_temporal_holdout_season"] == "2025-26"
    assert TEMPORAL_SPLIT["holdout_is_prospective"] is False
    assert TEMPORAL_SPLIT["same_utc_kickoff_group_must_not_split"] is True
    assert TEMPORAL_SPLIT["history_rule"] == (
        "history_kickoff_utc < target_kickoff_utc"
    )
    assert "NO_RANDOM_OR_SHUFFLED_SPLIT" in FAIL_CLOSED_RULES
    assert "NO_SAME_KICKOFF_LEAKAGE" in FAIL_CLOSED_RULES


def test_no_legacy_post_match_or_fuzzy_inputs_can_be_promoted():
    assert "NO_POST_MATCH_XG_OR_POSSESSION_AS_PRE_MATCH_FEATURES" in FAIL_CLOSED_RULES
    assert "NO_FUZZY_TEAM_IDENTITY" in FAIL_CLOSED_RULES
    assert "NO_TOTAL_GOALS_MODEL_RELABELED_AS_HOME_AWAY_XG" in FAIL_CLOSED_RULES


def test_all_downstream_authority_remains_false():
    assert AUTHORITY
    assert all(value is False for value in AUTHORITY.values())
    assert protocol_receipt()["authority"] == dict(AUTHORITY)
