"""ATHENA Goal/Score Dynamics v2 offline challenger protocol.

This module is deliberately research-only. It consumes already-issued pre-match
training rows and produces coherent regulation-time score distributions. It
contains no bookmaker inputs, calibration, routing, selection, accumulator, or
BET authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from domain.score_matrix import DEFAULT_TAIL_TOLERANCE

GOAL_SCORE_DATASET = "athena_goal_score_dynamics_v2"
GOAL_SCORE_SCHEMA_VERSION = 1
GOAL_SCORE_FEATURE_REGISTRY_VERSION = 1
GOAL_SCORE_MODEL_REGISTRY_VERSION = 1
GOAL_SCORE_EVALUATION_CONTRACT_VERSION = 1

MISSINGNESS_POLICY_ID = (
    "TRAIN_FOLD_MEDIAN_PLUS_MISSING_BLOCKED_INDICATORS_V1"
)
COMPETITION_PRIOR_POLICY_ID = (
    "TRAIN_FOLD_HIERARCHICAL_COMPETITION_GOAL_PRIOR_K20_V1"
)
COMPETITION_PRIOR_K = 20.0
CHRONOLOGICAL_SPLIT_POLICY_ID = (
    "LATEST_20_PERCENT_UNIQUE_DATES_TERMINAL_HOLDOUT_V1"
)
ROLLING_ORIGIN_POLICY_ID = "DATE_BUCKET_EXPANDING_5_FOLD_V1"
TERMINAL_HOLDOUT_POLICY_ID = "SINGLE_EXPOSURE_AFTER_DEVELOPMENT_FREEZE_V1"
TARGET_POLICY_ID = "REGULATION_FT_AVAILABLE_HOME_AWAY_GOALS_V1"
FEATURE_TARGET_FIREWALL_POLICY_ID = (
    "PREMATCH_CORPORA_ONLY_POSTMATCH_SCORE_TARGET_ONLY_V1"
)
SCORE_TAIL_POLICY_ID = "ADAPTIVE_POISSON_RECTANGLE_TAIL_1E10_V1"
DIXON_COLES_POLICY_ID = "STANDARD_FOUR_CELL_TAU_TRAIN_ONLY_BOUNDED_RHO_V1"
METRICS_POLICY_ID = (
    "EXACT_SCORE_NLL_AND_COHERENT_SCORE_SURFACE_DIAGNOSTICS_V1"
)
PAIRWISE_POLICY_ID = "COMMON_TARGET_SET_PAIRED_DATE_BUCKET_BOOTSTRAP_V1"
GOAL_MARGIN_METRIC_POLICY_ID = "EXACT_SKELLAM_PLUS_DC_LOCAL_CORRECTION_V1"
STRATIFIED_EVALUATION_POLICY_ID = "FIXED_PREMATCH_STRATA_MIN_SAMPLE_V1"
WINNER_GUARDRAIL_POLICY_ID = (
    "FROZEN_DEVELOPMENT_WINNER_HOLDOUT_NLL_PRIMARY_"
    "SECONDARY_LOGLOSS_5PCT_GUARDRAIL_V1"
)
NO_BOOKMAKER_POLICY_ID = (
    "NO_BOOKMAKER_ODDS_PRICES_LINES_OR_VALUE_INPUTS_V1"
)
PRODUCTION_PROMOTION_POLICY_ID = "RESEARCH_ONLY_NO_PRODUCTION_PROMOTION_V1"
LIVE_CHAMPION_REPLAY_STATUS = "BLOCKED_NOT_CANONICALLY_REPLAYABLE"
FULL_CORPUS_EVALUATION_STATUS = "NOT_RUN_SOURCE_CORPORA_UNAVAILABLE"
RANDOM_SEED = 233
MIN_INTENSITY = 1e-8
PAIR_BOOTSTRAP_REPLICATES = 400
MIN_STRATUM_SAMPLE = 50
STRATIFIED_TACTICAL_EVENT_LOW = -0.5
STRATIFIED_TACTICAL_EVENT_HIGH = 0.5
STRATIFIED_COVERAGE_MID = 0.50
STRATIFIED_COVERAGE_HIGH = 0.80
WINNER_MAX_SECONDARY_RELATIVE_REGRESSION = 0.05
WINNER_MIN_PREDICTION_AVAILABILITY = 0.99

AUTHORITY_FLAGS: Mapping[str, bool] = MappingProxyType({
    "research_goal_score_model": True,
    "production_probability": False,
    "calibrated_probability": False,
    "bookmaker_pricing": False,
    "market_activation": False,
    "router": False,
    "selection": False,
    "accumulator": False,
    "production_approval": False,
    "bet": False,
})


class GoalScoreError(ValueError):
    """Raised when the Goal/Score research contract cannot be satisfied."""


class FeatureStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class GoalScoreFeatureDefinition:
    feature_id: str
    upstream_corpus: str
    upstream_feature_id: str
    side: str
    scope: str
    window: str
    required: bool
    transformation: str = "FINITE_NUMERIC_OR_STATUS"

    def stable_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "upstream_corpus": self.upstream_corpus,
            "upstream_feature_id": self.upstream_feature_id,
            "side": self.side,
            "scope": self.scope,
            "window": self.window,
            "required": self.required,
            "transformation": self.transformation,
        }


def _hist(
    side: str,
    scope: str,
    feature: str,
    window: str = "LAST_20",
    required: bool = False,
) -> GoalScoreFeatureDefinition:
    return GoalScoreFeatureDefinition(
        f"HIST.{side}.{scope}.{window}.{feature}",
        "HISTORICAL_ASOF",
        feature,
        side,
        scope,
        window,
        required,
    )


def _tactical(
    side: str,
    scope: str,
    dimension: str,
) -> GoalScoreFeatureDefinition:
    return GoalScoreFeatureDefinition(
        f"TACTICAL.{side}.{scope}.{dimension}",
        "TACTICAL_IDENTITY",
        dimension,
        side,
        scope,
        "AS_OF",
        False,
    )


_CORE_HISTORICAL_FEATURES = (
    "points_per_match",
    "goals_for_per_match",
    "goals_against_per_match",
    "goal_difference_per_match",
    "total_goals_per_match",
    "clean_sheet_rate",
    "failed_to_score_rate",
    "btts_rate",
    "over_1_5_rate",
    "over_2_5_rate",
    "xg_for_per_match",
    "xg_against_per_match",
    "xg_total_per_match",
    "shots_for_per_match",
    "shots_against_per_match",
    "shots_on_target_for_per_match",
    "shots_on_target_against_per_match",
    "possession_for_mean",
    "first_half_goals_for_per_match",
    "first_half_goals_against_per_match",
    "first_half_total_goals_per_match",
)
_SCHEDULE_FEATURES = (
    "days_since_last_match",
    "fixtures_last_7_days",
    "fixtures_last_14_days",
    "fixtures_last_28_days",
)
_TACTICAL_DIMENSIONS = (
    "EVENT_ENVIRONMENT",
    "ATTACKING_PRODUCTION",
    "DEFENSIVE_SUPPRESSION",
    "SHOT_PROFILE",
    "FIRST_HALF_ENVIRONMENT",
    "CONTROL_TEMPO",
    "SCORING_RELIABILITY",
)

GOAL_SCORE_FEATURE_REGISTRY: tuple[GoalScoreFeatureDefinition, ...] = tuple([
    *(_hist("HOME", "OVERALL", feature) for feature in _CORE_HISTORICAL_FEATURES),
    *(_hist("HOME", "HOME_ONLY", feature) for feature in _CORE_HISTORICAL_FEATURES),
    *(_hist("AWAY", "OVERALL", feature) for feature in _CORE_HISTORICAL_FEATURES),
    *(_hist("AWAY", "AWAY_ONLY", feature) for feature in _CORE_HISTORICAL_FEATURES),
    *(_hist("HOME", "OVERALL", feature, "AS_OF") for feature in _SCHEDULE_FEATURES),
    *(_hist("AWAY", "OVERALL", feature, "AS_OF") for feature in _SCHEDULE_FEATURES),
    *(_tactical("HOME", "OVERALL", dimension) for dimension in _TACTICAL_DIMENSIONS),
    *(_tactical("HOME", "HOME_ONLY", dimension) for dimension in _TACTICAL_DIMENSIONS),
    *(_tactical("AWAY", "OVERALL", dimension) for dimension in _TACTICAL_DIMENSIONS),
    *(_tactical("AWAY", "AWAY_ONLY", dimension) for dimension in _TACTICAL_DIMENSIONS),
])


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def calculate_feature_registry_sha256(
    registry: Sequence[GoalScoreFeatureDefinition] = GOAL_SCORE_FEATURE_REGISTRY,
    version: int = GOAL_SCORE_FEATURE_REGISTRY_VERSION,
) -> str:
    return hashlib.sha256(_canonical_bytes({
        "version": version,
        "features": [item.stable_dict() for item in registry],
    })).hexdigest()


EXPECTED_GOAL_SCORE_FEATURE_REGISTRY_SHA256_BY_VERSION: Mapping[int, str] = (
    MappingProxyType({
        1: "8052e9177e5c9d88226d36b5e7b11308ba0871889439638eb9f3570d37972bb0",
    })
)


def validate_feature_registry(
    registry: Sequence[GoalScoreFeatureDefinition] = GOAL_SCORE_FEATURE_REGISTRY,
    version: int = GOAL_SCORE_FEATURE_REGISTRY_VERSION,
    expected_by_version: Mapping[int, str] = (
        EXPECTED_GOAL_SCORE_FEATURE_REGISTRY_SHA256_BY_VERSION
    ),
) -> str:
    expected = expected_by_version.get(version)
    if expected is None:
        raise GoalScoreError(
            f"unreviewed Goal/Score feature registry version: {version}"
        )
    actual = calculate_feature_registry_sha256(registry, version)
    if actual != expected:
        raise GoalScoreError("Goal/Score feature registry drift")
    return actual


@dataclass(frozen=True)
class GoalScoreModelDefinition:
    model_id: str
    family: str
    estimator: str
    hyperparameters: tuple[tuple[str, Any], ...]
    correction_policy_id: str | None
    random_seed: int | None
    authority: str = "RESEARCH_ONLY"

    def stable_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "family": self.family,
            "estimator": self.estimator,
            "hyperparameters": dict(self.hyperparameters),
            "correction_policy_id": self.correction_policy_id,
            "random_seed": self.random_seed,
            "authority": self.authority,
        }


GOAL_SCORE_MODEL_REGISTRY: tuple[GoalScoreModelDefinition, ...] = (
    GoalScoreModelDefinition(
        "POISSON_GLM_SCORE_V1",
        "INDEPENDENT_POISSON",
        "sklearn.PoissonRegressor",
        (
            ("alpha", 0.25),
            ("fit_intercept", True),
            ("solver", "lbfgs"),
            ("max_iter", 500),
            ("tol", 1e-8),
            ("warm_start", False),
            ("verbose", 0),
        ),
        None,
        None,
    ),
    GoalScoreModelDefinition(
        "DIXON_COLES_SCORE_V1",
        "DIXON_COLES",
        "PoissonRegressor+four_cell_tau",
        (
            ("alpha", 0.25),
            ("fit_intercept", True),
            ("solver", "lbfgs"),
            ("max_iter", 500),
            ("tol", 1e-8),
            ("warm_start", False),
            ("verbose", 0),
        ),
        DIXON_COLES_POLICY_ID,
        None,
    ),
    GoalScoreModelDefinition(
        "HIST_GRADIENT_BOOSTING_POISSON_V1",
        "NONLINEAR_POISSON",
        "sklearn.HistGradientBoostingRegressor",
        (
            ("loss", "poisson"),
            ("quantile", None),
            ("learning_rate", 0.05),
            ("max_iter", 160),
            ("max_leaf_nodes", 15),
            ("max_depth", None),
            ("min_samples_leaf", 12),
            ("l2_regularization", 1.0),
            ("max_features", 1.0),
            ("max_bins", 255),
            ("categorical_features", None),
            ("monotonic_cst", None),
            ("interaction_cst", None),
            ("warm_start", False),
            ("early_stopping", False),
            ("scoring", "loss"),
            ("validation_fraction", 0.1),
            ("n_iter_no_change", 10),
            ("tol", 1e-7),
            ("verbose", 0),
        ),
        None,
        RANDOM_SEED,
    ),
)


def calculate_model_registry_sha256(
    registry: Sequence[GoalScoreModelDefinition] = GOAL_SCORE_MODEL_REGISTRY,
    version: int = GOAL_SCORE_MODEL_REGISTRY_VERSION,
) -> str:
    return hashlib.sha256(_canonical_bytes({
        "version": version,
        "models": [item.stable_dict() for item in registry],
    })).hexdigest()


EXPECTED_GOAL_SCORE_MODEL_REGISTRY_SHA256_BY_VERSION: Mapping[int, str] = (
    MappingProxyType({
        1: "5451bdd4a3463100866b23b29c0399412fab781f664aee8133c3a123e586ac68",
    })
)


def validate_model_registry(
    registry: Sequence[GoalScoreModelDefinition] = GOAL_SCORE_MODEL_REGISTRY,
    version: int = GOAL_SCORE_MODEL_REGISTRY_VERSION,
    expected_by_version: Mapping[int, str] = (
        EXPECTED_GOAL_SCORE_MODEL_REGISTRY_SHA256_BY_VERSION
    ),
) -> str:
    expected = expected_by_version.get(version)
    if expected is None:
        raise GoalScoreError(
            f"unreviewed Goal/Score model registry version: {version}"
        )
    actual = calculate_model_registry_sha256(registry, version)
    if actual != expected:
        raise GoalScoreError("Goal/Score model registry drift")
    return actual


def evaluation_contract_payload(
    feature_sha: str,
    model_sha: str,
) -> dict[str, Any]:
    return {
        "schema_version": GOAL_SCORE_SCHEMA_VERSION,
        "feature_registry_version": GOAL_SCORE_FEATURE_REGISTRY_VERSION,
        "feature_registry_sha256": feature_sha,
        "model_registry_version": GOAL_SCORE_MODEL_REGISTRY_VERSION,
        "model_registry_sha256": model_sha,
        "missingness_policy_id": MISSINGNESS_POLICY_ID,
        "competition_prior_policy_id": COMPETITION_PRIOR_POLICY_ID,
        "competition_prior_k": COMPETITION_PRIOR_K,
        "chronological_split_policy_id": CHRONOLOGICAL_SPLIT_POLICY_ID,
        "rolling_origin_policy_id": ROLLING_ORIGIN_POLICY_ID,
        "terminal_holdout_policy_id": TERMINAL_HOLDOUT_POLICY_ID,
        "target_policy_id": TARGET_POLICY_ID,
        "feature_target_firewall_policy_id": FEATURE_TARGET_FIREWALL_POLICY_ID,
        "score_tail_policy_id": SCORE_TAIL_POLICY_ID,
        "tail_tolerance": DEFAULT_TAIL_TOLERANCE,
        "dixon_coles_policy_id": DIXON_COLES_POLICY_ID,
        "metrics_policy_id": METRICS_POLICY_ID,
        "pairwise_policy_id": PAIRWISE_POLICY_ID,
        "pair_bootstrap_replicates": PAIR_BOOTSTRAP_REPLICATES,
        "goal_margin_metric_policy_id": GOAL_MARGIN_METRIC_POLICY_ID,
        "stratified_evaluation_policy_id": STRATIFIED_EVALUATION_POLICY_ID,
        "minimum_stratum_sample": MIN_STRATUM_SAMPLE,
        "stratified_tactical_event_low": STRATIFIED_TACTICAL_EVENT_LOW,
        "stratified_tactical_event_high": STRATIFIED_TACTICAL_EVENT_HIGH,
        "stratified_coverage_mid": STRATIFIED_COVERAGE_MID,
        "stratified_coverage_high": STRATIFIED_COVERAGE_HIGH,
        "winner_guardrail_policy_id": WINNER_GUARDRAIL_POLICY_ID,
        "winner_max_secondary_relative_regression": (
            WINNER_MAX_SECONDARY_RELATIVE_REGRESSION
        ),
        "winner_min_prediction_availability": WINNER_MIN_PREDICTION_AVAILABILITY,
        "no_bookmaker_policy_id": NO_BOOKMAKER_POLICY_ID,
        "production_promotion_policy_id": PRODUCTION_PROMOTION_POLICY_ID,
        "random_seed": RANDOM_SEED,
        "minimum_intensity": MIN_INTENSITY,
    }


def calculate_evaluation_contract_sha256(
    *,
    feature_sha: str,
    model_sha: str,
    version: int = GOAL_SCORE_EVALUATION_CONTRACT_VERSION,
) -> str:
    return hashlib.sha256(_canonical_bytes({
        "version": version,
        "semantics": evaluation_contract_payload(feature_sha, model_sha),
    })).hexdigest()


EXPECTED_GOAL_SCORE_EVALUATION_CONTRACT_SHA256_BY_VERSION: Mapping[int, str] = (
    MappingProxyType({
        1: "20f533874e74195b2dc3ebe93b9edf60a26a9dbc9aaed5668d7c6412f520efd7",
    })
)


def validate_evaluation_contract() -> tuple[str, str, str]:
    feature_sha = validate_feature_registry()
    model_sha = validate_model_registry()
    actual = calculate_evaluation_contract_sha256(
        feature_sha=feature_sha,
        model_sha=model_sha,
    )
    expected = EXPECTED_GOAL_SCORE_EVALUATION_CONTRACT_SHA256_BY_VERSION.get(
        GOAL_SCORE_EVALUATION_CONTRACT_VERSION
    )
    if expected is None or actual != expected:
        raise GoalScoreError("Goal/Score evaluation contract drift")
    return feature_sha, model_sha, actual


@dataclass(frozen=True)
class TrainingRow:
    match_key: str
    match_date: str
    scope: str
    competition_key: str | None
    season: str | None
    home_goals: int
    away_goals: int
    features: Mapping[str, tuple[FeatureStatus, float | None]]
    canonical_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.match_key or not self.match_date:
            raise GoalScoreError("training rows require canonical identity")
        for value, name in (
            (self.home_goals, "home_goals"),
            (self.away_goals, "away_goals"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise GoalScoreError(
                    f"{name} must be a non-negative integer"
                )
        registered = {item.feature_id for item in GOAL_SCORE_FEATURE_REGISTRY}
        for feature_id, (status, value) in self.features.items():
            if feature_id not in registered:
                raise GoalScoreError(
                    f"unregistered model feature: {feature_id}"
                )
            if status is FeatureStatus.AVAILABLE:
                if (
                    value is None
                    or isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                ):
                    raise GoalScoreError(
                        "AVAILABLE model feature requires finite numeric value"
                    )
            elif value is not None:
                raise GoalScoreError(
                    "MISSING/BLOCKED model feature cannot retain value"
                )


__all__ = [name for name in globals() if not name.startswith("_")]
