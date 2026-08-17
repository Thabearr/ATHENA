"""Pre-registered research-only expected-goals model validation protocol.

This module defines the next reviewed boundary after the successful FotMob
UTC-native successor feature qualification.  It grants no model, market,
pricing, selection, production, or BET authority.
"""

from __future__ import annotations

from types import MappingProxyType

PROTOCOL_ID = "FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_V1"
PROTOCOL_VERSION = 1
STATE = "PRE_REGISTERED_NOT_EXECUTED"

# Exact upstream V2 qualification lineage.
UPSTREAM_MAIN_SHA = "cd67be14f6a4f09484d18a57de360b8a5d4c51d7"
UPSTREAM_RUN_ID = 31990121181
UPSTREAM_RESULT_COMMENT_ID = 5311318782
UPSTREAM_ARTIFACT_ID = 9275052993
UPSTREAM_ARTIFACT_NAME = "fotmob-utc-native-feature-qualification-v2-31990121181"
UPSTREAM_ARTIFACT_SHA256 = "f69ffad8f47faadb3ec743c96efa35fb6f4b43776a7650cf0414fb40455d29eb"
UPSTREAM_ARTIFACT_SIZE_BYTES = 23349191
UPSTREAM_PROJECTION_SHA256 = "5519ef40db3efc678c9eef73046c0e577e5f33a85f11b3fe043fc22bca2fcfed"
UPSTREAM_EXPECTED_ROWS = 21326
UPSTREAM_EXPECTED_UNIQUE_FIXTURES = 21326

# Historical model inputs. live_data_freshness is intentionally not numeric.
NUMERIC_MODEL_FEATURES = (
    "home_form",
    "away_form",
    "home_elo",
    "away_elo",
    "fatigue",
)
RUNTIME_TRUST_GATE_FEATURE = "live_data_freshness"
TARGETS = ("home_goals", "away_goals")

# Competing legacy paths are evidence to classify, not approved model inputs.
LEGACY_PATH_CLASSIFICATIONS = MappingProxyType(
    {
        "engine/score_engine.py": "LEGACY_HEURISTIC_UNREVIEWED_NOT_AUTHORIZED",
        "models/goals_model.joblib": "LEGACY_TOTAL_GOALS_RANDOM_FOREST_NOT_AUTHORIZED",
        "tools/train_model.py": "LEGACY_DIFFERENT_FEATURE_FAMILY_NOT_AUTHORIZED",
        "scripts/backfill_xg.py": "LEGACY_FUZZY_POST_MATCH_BACKFILL_NOT_AUTHORIZED",
        "models/expected_goals.py": "PLACEHOLDER_NOT_IMPLEMENTATION",
        "models/poisson.py": "PLACEHOLDER_NOT_IMPLEMENTATION",
        "models/dixon_coles.py": "PLACEHOLDER_NOT_IMPLEMENTATION",
    }
)

CANDIDATE_MODEL_FAMILIES = (
    "POISSON_REGRESSION_L2_HOME_AND_AWAY",
    "HISTOGRAM_GRADIENT_BOOSTING_POISSON_HOME_AND_AWAY",
)
BASELINES = (
    "GLOBAL_HOME_AWAY_MEAN_BASELINE",
    "STRICTLY_PRIOR_ROLLING_COMPETITION_MEAN_BASELINE",
)

TEMPORAL_SPLIT = MappingProxyType(
    {
        "development_seasons": ("2020-21", "2021-22", "2022-23", "2023-24"),
        "validation_season": "2024-25",
        "final_temporal_holdout_season": "2025-26",
        "holdout_is_prospective": False,
        "same_utc_kickoff_group_must_not_split": True,
        "history_rule": "history_kickoff_utc < target_kickoff_utc",
    }
)

PRIMARY_METRICS = (
    "POISSON_NEGATIVE_LOG_LIKELIHOOD_HOME",
    "POISSON_NEGATIVE_LOG_LIKELIHOOD_AWAY",
    "MAE_HOME",
    "MAE_AWAY",
    "RMSE_HOME",
    "RMSE_AWAY",
    "MEAN_PREDICTION_BIAS_HOME",
    "MEAN_PREDICTION_BIAS_AWAY",
)

ROBUSTNESS_BREAKDOWNS = (
    "competition_family",
    "season",
    "home_goal_band",
    "away_goal_band",
)

FAIL_CLOSED_RULES = (
    "NO_RANDOM_OR_SHUFFLED_SPLIT",
    "NO_SAME_KICKOFF_LEAKAGE",
    "NO_POST_MATCH_XG_OR_POSSESSION_AS_PRE_MATCH_FEATURES",
    "NO_FUZZY_TEAM_IDENTITY",
    "NO_NUMERIC_FRESHNESS_SURROGATE",
    "NO_MISSING_FEATURE_DEFAULTS",
    "NO_TOTAL_GOALS_MODEL_RELABELED_AS_HOME_AWAY_XG",
    "NO_MODEL_FAMILY_SELECTION_USING_FINAL_HOLDOUT",
    "NO_SCORE_MATRIX_OR_MARKET_APPROVAL_IN_THIS_BOUNDARY",
)

SUCCESS_STATE = "QUALIFIED_EXPECTED_GOALS_MODEL_CANDIDATE_MODEL_USE_UNREVIEWED"
FAILURE_STATE = "EXPECTED_GOALS_MODEL_VALIDATION_NOT_QUALIFIED"
NEXT_REVIEWED_BOUNDARY_ON_SUCCESS = (
    "PRE_REGISTER_REVIEWED_SCORE_MATRIX_AND_CORE_MARKET_PROBABILITY_VALIDATION_PROTOCOL"
)

AUTHORITY = MappingProxyType(
    {
        "expected_goals_model_production_approved": False,
        "score_matrix_authorized": False,
        "probability_inference_authorized": False,
        "calibration_production_authorized": False,
        "pricing_authorized": False,
        "market_activation_authorized": False,
        "selection_authorized": False,
        "production_approval_authorized": False,
        "bet_authorized": False,
    }
)


def protocol_receipt() -> dict[str, object]:
    """Return the deterministic, result-free pre-registration receipt."""

    return {
        "protocol_id": PROTOCOL_ID,
        "protocol_version": PROTOCOL_VERSION,
        "state": STATE,
        "upstream_main_sha": UPSTREAM_MAIN_SHA,
        "upstream_run_id": UPSTREAM_RUN_ID,
        "upstream_result_comment_id": UPSTREAM_RESULT_COMMENT_ID,
        "upstream_artifact_id": UPSTREAM_ARTIFACT_ID,
        "upstream_artifact_name": UPSTREAM_ARTIFACT_NAME,
        "upstream_artifact_sha256": UPSTREAM_ARTIFACT_SHA256,
        "upstream_artifact_size_bytes": UPSTREAM_ARTIFACT_SIZE_BYTES,
        "upstream_projection_sha256": UPSTREAM_PROJECTION_SHA256,
        "expected_rows": UPSTREAM_EXPECTED_ROWS,
        "expected_unique_fixtures": UPSTREAM_EXPECTED_UNIQUE_FIXTURES,
        "numeric_model_features": list(NUMERIC_MODEL_FEATURES),
        "runtime_trust_gate_feature": RUNTIME_TRUST_GATE_FEATURE,
        "targets": list(TARGETS),
        "legacy_path_classifications": dict(LEGACY_PATH_CLASSIFICATIONS),
        "candidate_model_families": list(CANDIDATE_MODEL_FAMILIES),
        "baselines": list(BASELINES),
        "temporal_split": dict(TEMPORAL_SPLIT),
        "primary_metrics": list(PRIMARY_METRICS),
        "robustness_breakdowns": list(ROBUSTNESS_BREAKDOWNS),
        "fail_closed_rules": list(FAIL_CLOSED_RULES),
        "success_state": SUCCESS_STATE,
        "failure_state": FAILURE_STATE,
        "next_reviewed_boundary_on_success": NEXT_REVIEWED_BOUNDARY_ON_SUCCESS,
        "authority": dict(AUTHORITY),
    }
