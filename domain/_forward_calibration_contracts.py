"""Frozen contracts for ATHENA Phase 6 forward-chaining calibration.

Calibration corrects research probability bias only. It does not consume prices,
select markets, activate betting, or promote any football model to production.
"""
from __future__ import annotations

import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping

from domain._goal_score_contracts import validate_evaluation_contract
from domain.goal_score_training_view import validate_training_view_contract
from domain.historical_training_coverage import validate_contracts as validate_label_contracts


CALIBRATION_DATASET = "athena_forward_chaining_market_calibration"
CALIBRATION_SCHEMA_VERSION = 1
CALIBRATION_CONTRACT_VERSION = 1

OOF_POLICY_ID = "GOAL_SCORE_DEVELOPMENT_DATE_BUCKET_EXPANDING_5_FOLD_OOF_V1"
TERMINAL_HOLDOUT_POLICY_ID = (
    "PR233_TERMINAL_HOLDOUT_EVALUATION_ONLY_NO_CALIBRATOR_FIT_V1"
)
CALIBRATOR_POLICY_ID = "ONE_VS_REST_ISOTONIC_JSON_THRESHOLDS_V1"
BINARY_PARTITION_POLICY_ID = "PRIMARY_EVENT_CALIBRATE_COMPLEMENT_EXACT_V1"
SIMPLEX_POLICY_ID = "ONE_VS_REST_CALIBRATE_THEN_RENORMALIZE_V1"
HIERARCHY_POLICY_ID = "GLOBAL_THEN_COMPETITION_REGIME_SHRUNK_FALLBACK_V1"
GROUP_POLICY_ID = "PREMATCH_COMPETITION_KEY_AND_TACTICAL_EVENT_REGIME_V1"
LINE_POLICY_ID = "CALLER_DECLARED_RESEARCH_LINES_NOT_BOOKMAKER_OFFER_EVIDENCE_V1"
METRICS_POLICY_ID = "LOGLOSS_BRIER_CLASSWISE_ECE_FIXED_10_BIN_V1"
GATE_POLICY_ID = "ECE_NONWORSE_LOGLOSS_BRIER_MAX_2PCT_REGRESSION_V1"
ARTIFACT_POLICY_ID = "CANONICAL_JSON_NO_PICKLE_SHA256_V1"
NO_BOOKMAKER_POLICY_ID = "NO_BOOKMAKER_ODDS_PRICES_LINES_OR_VALUE_INPUTS_V1"
PRODUCTION_POLICY_ID = "RESEARCH_CALIBRATION_ONLY_NO_PRODUCTION_PROMOTION_V1"

MINIMUM_GLOBAL_SAMPLES = 80
MINIMUM_LOCAL_SAMPLES = 60
MINIMUM_POSITIVE_SAMPLES = 10
MINIMUM_UNIQUE_PROBABILITIES = 8
HIERARCHICAL_SHRINKAGE_K = 100.0
ECE_BINS = 10
MAXIMUM_SECONDARY_RELATIVE_REGRESSION = 0.02
PROBABILITY_CLIP = 1e-9

TACTICAL_EVENT_LOW = -0.5
TACTICAL_EVENT_HIGH = 0.5

FULL_CORPUS_CALIBRATION_STATUS = "NOT_RUN_SOURCE_CORPORA_UNAVAILABLE"

AUTHORITY_FLAGS: Mapping[str, bool] = MappingProxyType({
    "research_calibration": True,
    "football_model_training": False,
    "football_model_promotion": False,
    "production_probability": False,
    "bookmaker_pricing": False,
    "market_activation": False,
    "router": False,
    "selection": False,
    "accumulator": False,
    "production_approval": False,
    "bet": False,
})


class ForwardCalibrationError(ValueError):
    """Raised when the frozen forward-calibration contract cannot be satisfied."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def calibration_contract_payload(
    *,
    goal_score_evaluation_sha256: str,
    goal_score_training_view_sha256: str,
    market_label_registry_sha256: str,
    canonical_market_semantics_sha256: str,
    label_generation_contract_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": CALIBRATION_SCHEMA_VERSION,
        "goal_score_evaluation_contract_sha256": goal_score_evaluation_sha256,
        "goal_score_training_view_contract_sha256": goal_score_training_view_sha256,
        "market_label_registry_sha256": market_label_registry_sha256,
        "canonical_market_semantics_sha256": canonical_market_semantics_sha256,
        "label_generation_contract_sha256": label_generation_contract_sha256,
        "oof_policy_id": OOF_POLICY_ID,
        "terminal_holdout_policy_id": TERMINAL_HOLDOUT_POLICY_ID,
        "calibrator_policy_id": CALIBRATOR_POLICY_ID,
        "binary_partition_policy_id": BINARY_PARTITION_POLICY_ID,
        "simplex_policy_id": SIMPLEX_POLICY_ID,
        "hierarchy_policy_id": HIERARCHY_POLICY_ID,
        "group_policy_id": GROUP_POLICY_ID,
        "line_policy_id": LINE_POLICY_ID,
        "metrics_policy_id": METRICS_POLICY_ID,
        "gate_policy_id": GATE_POLICY_ID,
        "artifact_policy_id": ARTIFACT_POLICY_ID,
        "no_bookmaker_policy_id": NO_BOOKMAKER_POLICY_ID,
        "production_policy_id": PRODUCTION_POLICY_ID,
        "minimum_global_samples": MINIMUM_GLOBAL_SAMPLES,
        "minimum_local_samples": MINIMUM_LOCAL_SAMPLES,
        "minimum_positive_samples": MINIMUM_POSITIVE_SAMPLES,
        "minimum_unique_probabilities": MINIMUM_UNIQUE_PROBABILITIES,
        "hierarchical_shrinkage_k": HIERARCHICAL_SHRINKAGE_K,
        "ece_bins": ECE_BINS,
        "maximum_secondary_relative_regression": (
            MAXIMUM_SECONDARY_RELATIVE_REGRESSION
        ),
        "probability_clip": PROBABILITY_CLIP,
    }


def calculate_calibration_contract_sha256(
    *,
    goal_score_evaluation_sha256: str,
    goal_score_training_view_sha256: str,
    market_label_registry_sha256: str,
    canonical_market_semantics_sha256: str,
    label_generation_contract_sha256: str,
    version: int = CALIBRATION_CONTRACT_VERSION,
) -> str:
    return hashlib.sha256(_canonical_bytes({
        "version": version,
        "semantics": calibration_contract_payload(
            goal_score_evaluation_sha256=goal_score_evaluation_sha256,
            goal_score_training_view_sha256=goal_score_training_view_sha256,
            market_label_registry_sha256=market_label_registry_sha256,
            canonical_market_semantics_sha256=canonical_market_semantics_sha256,
            label_generation_contract_sha256=label_generation_contract_sha256,
        ),
    })).hexdigest()


EXPECTED_CALIBRATION_CONTRACT_SHA256_BY_VERSION: Mapping[int, str] = MappingProxyType({
    1: "45c0c614ca8b26ee554cd80d94855227b9995f1b31b2a531dcd3262b667183d9",
})


def validate_calibration_contract() -> dict[str, str]:
    _feature_sha, _model_sha, evaluation_sha = validate_evaluation_contract()
    _feature_sha2, _model_sha2, evaluation_sha2, training_sha = (
        validate_training_view_contract()
    )
    if evaluation_sha2 != evaluation_sha:
        raise ForwardCalibrationError("Goal/Score evaluation identity mismatch")
    label_registry_sha, market_sha, label_generation_sha = validate_label_contracts()
    actual = calculate_calibration_contract_sha256(
        goal_score_evaluation_sha256=evaluation_sha,
        goal_score_training_view_sha256=training_sha,
        market_label_registry_sha256=label_registry_sha,
        canonical_market_semantics_sha256=market_sha,
        label_generation_contract_sha256=label_generation_sha,
    )
    expected = EXPECTED_CALIBRATION_CONTRACT_SHA256_BY_VERSION.get(
        CALIBRATION_CONTRACT_VERSION
    )
    if expected is None or actual != expected:
        raise ForwardCalibrationError("forward-calibration contract drift")
    return {
        "goal_score_evaluation_contract_sha256": evaluation_sha,
        "goal_score_training_view_contract_sha256": training_sha,
        "market_label_registry_sha256": label_registry_sha,
        "canonical_market_semantics_sha256": market_sha,
        "label_generation_contract_sha256": label_generation_sha,
        "calibration_contract_sha256": actual,
    }


__all__ = [name for name in globals() if not name.startswith("_")]
