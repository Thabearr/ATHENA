"""Freeze the reviewed outcome of the UTC-native expected-goals validation.

This is a result-review receipt only. It records the exact evidence produced by
run 32049714066 and the reviewed successor decision. It does not fit, calibrate,
score, price, select, or authorize a production model.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

SCHEMA_VERSION = 1
REVIEW_ID = "FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_RESULT_REVIEW_V1"
REVIEW_STATE = "REVIEWED_MIXED_OR_WEAK_FOTMOB_UTC_NATIVE_SUCCESSOR_NOT_APPROVED"
NEXT_REQUIRED_BOUNDARY = (
    "PRE_REGISTER_FRESH_HOLDOUT_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_"
    "HOME_CALIBRATION_AND_COMPETITION_IDENTITY_FOLLOWUP"
)

BASE_MAIN_SHA = "b8ddc00f7529c5533c9da2daad613d997498cbf2"
EXECUTION_RUN_ID = 32049714066
EXECUTION_COMMAND_COMMENT_ID = 5318114406
EXECUTION_ATTEMPT_COMMENT_ID = 5318115383
EXECUTION_RESULT_COMMENT_ID = 5318117332
RESULT_ARTIFACT_ID = 9294215497
RESULT_ARTIFACT_NAME = "fotmob-utc-native-expected-goals-validation-32049714066"
RESULT_ARTIFACT_SIZE_BYTES = 5_441_951
RESULT_ARTIFACT_SHA256 = "e9eac385a66df04bf28e7d69062e55db516829e94405e4a8def0e4d6a346d6c5"
RESULT_RECEIPT_MEMBER = "fotmob-utc-native-xg-validation-receipt.json"
RESULT_RECEIPT_SIZE_BYTES = 55_507
RESULT_RECEIPT_SHA256 = "1fffee7474ab37ee613e6a7943b57fd9231f6d6bdf53ffa6b13ee2b62ceca06a"
PREDICTIONS_MEMBER = "fotmob-utc-native-xg-validation-predictions.ndjson"
PREDICTIONS_SIZE_BYTES = 5_381_414
PREDICTIONS_SHA256 = "2f4939a8f2d41674660144f5315d2420ce2f006ce2b885e52c6655abd0e52420"
PREDICTIONS_ROWS = 6_948

SOURCE_ARTIFACT_ID = 9_275_052_993
SOURCE_ARTIFACT_SHA256 = "f69ffad8f47faadb3ec743c96efa35fb6f4b43776a7650cf0414fb40455d29eb"
SOURCE_PROJECTION_SHA256 = "5519ef40db3efc678c9eef73046c0e577e5f33a85f11b3fe043fc22bca2fcfed"
SOURCE_PROJECTION_ROWS = 21_326
COMPLETE_CASE_ROWS = 21_129
TRAIN_ROWS = 14_181
EVALUATION_A_ROWS = 3_471
EVALUATION_B_ROWS = 3_477
POOLED_EVALUATION_ROWS = 6_948

MIXED_SIGNAL_STATE = "MIXED_OR_WEAK_FOTMOB_UTC_NATIVE_SUCCESSOR_SIGNAL_REVIEW_REQUIRED"
FAILED_STRONG_CHECK = "pooled_native_home_wace_strictly_below_pooled_elo_home_wace"
STRONG_CHECK_COUNT = 10
STRONG_CHECKS_PASSED = 9

SAFETY_KEYS = (
    "bet_authorized",
    "calibration_for_production_authorized",
    "expected_goals_production_authorized",
    "expected_goals_transform_approved",
    "market_activation_authorized",
    "model_training_authorized",
    "pricing_authorized",
    "probability_adjustment_authorized",
    "probability_inference_authorized",
    "production_approval_authorized",
    "score_matrix_authorized",
    "selection_authorized",
    "successor_candidate_approved",
    "successor_live_inputs_qualified",
)


def build_fotmob_utc_native_expected_goals_model_validation_result_review() -> dict[str, Any]:
    """Return the frozen research-only result review receipt."""
    return {
        "schema_version": SCHEMA_VERSION,
        "review_id": REVIEW_ID,
        "review_state": REVIEW_STATE,
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "execution_evidence": {
            "main_sha": BASE_MAIN_SHA,
            "run_id": EXECUTION_RUN_ID,
            "command_comment_id": EXECUTION_COMMAND_COMMENT_ID,
            "attempt_comment_id": EXECUTION_ATTEMPT_COMMENT_ID,
            "result_comment_id": EXECUTION_RESULT_COMMENT_ID,
            "artifact": {
                "id": RESULT_ARTIFACT_ID,
                "name": RESULT_ARTIFACT_NAME,
                "size_bytes": RESULT_ARTIFACT_SIZE_BYTES,
                "sha256": RESULT_ARTIFACT_SHA256,
            },
            "receipt": {
                "member": RESULT_RECEIPT_MEMBER,
                "size_bytes": RESULT_RECEIPT_SIZE_BYTES,
                "sha256": RESULT_RECEIPT_SHA256,
            },
            "predictions": {
                "member": PREDICTIONS_MEMBER,
                "record_count": PREDICTIONS_ROWS,
                "size_bytes": PREDICTIONS_SIZE_BYTES,
                "sha256": PREDICTIONS_SHA256,
            },
        },
        "source_evidence": {
            "artifact_id": SOURCE_ARTIFACT_ID,
            "artifact_sha256": SOURCE_ARTIFACT_SHA256,
            "projection_sha256": SOURCE_PROJECTION_SHA256,
            "projection_rows": SOURCE_PROJECTION_ROWS,
            "complete_case_rows": COMPLETE_CASE_ROWS,
            "train_rows": TRAIN_ROWS,
            "evaluation_a_rows": EVALUATION_A_ROWS,
            "evaluation_b_rows": EVALUATION_B_ROWS,
            "pooled_evaluation_rows": POOLED_EVALUATION_ROWS,
        },
        "reviewed_signal": {
            "reported_state": MIXED_SIGNAL_STATE,
            "strong_check_count": STRONG_CHECK_COUNT,
            "strong_checks_passed": STRONG_CHECKS_PASSED,
            "sole_failed_strong_check": FAILED_STRONG_CHECK,
            "native_minus_elo_mean_joint_nll": {
                "evaluation_a": -0.0019040180402716267,
                "evaluation_b_terminal": -0.002354865405624018,
                "pooled_a_plus_b": -0.0021296363893399395,
            },
            "pooled_home_wace": {
                "native_refit": 0.05778673203465596,
                "elo_only": 0.05490445024426852,
                "native_minus_elo": 0.0028822817903874365,
                "required_relation_for_strong_signal": "NATIVE_STRICTLY_BELOW_ELO",
                "required_relation_passed": False,
            },
            "quarter_jackknife_native_minus_elo": {
                "cluster_count": 9,
                "full_estimate": -0.002129636389340353,
                "standard_error": 0.00053284613491735,
                "interval_lower_95": -0.003174014813778359,
                "interval_upper_95": -0.0010852579649023473,
                "upper_bound_strictly_below_zero": True,
            },
            "diagnostic_report_only_comparisons": {
                "native_minus_historical_fixed_transfer_pooled_nll": 6.292329760881898e-05,
                "no_fatigue_minus_native_refit_pooled_nll": 0.000299254437110541,
                "historical_transfer_is_approval_gate": False,
                "no_fatigue_ablation_is_approval_gate": False,
            },
        },
        "reviewed_decision": {
            "positive_predictive_signal_retained_for_research": True,
            "native_refit_successor_candidate_approved": False,
            "historical_fixed_transfer_promoted_instead": False,
            "home_calibration_followup_required": True,
            "competition_identity_followup_required": True,
            "competition_or_league_robustness_status": (
                "BLOCKED_PROJECTION_DOES_NOT_CARRY_COMPETITION_IDENTITY"
            ),
            "evaluation_a_and_b_labels_now_consumed_by_review": True,
            "retune_on_a_or_b_and_reuse_same_rows_as_fresh_validation_forbidden": True,
            "followup_must_pre_register_before_result_inspection": True,
            "followup_validation_requires_fresh_holdout_beyond_2026_08_15": True,
            "automatic_model_approval": False,
        },
        "runtime_caveats": {
            "cross_runtime_bit_identity_claimed": False,
            "known_pr77_machine_precision_canonicalization_gap_cleared": False,
        },
        "safety": {key: False for key in SAFETY_KEYS},
    }


def canonical_fotmob_utc_native_expected_goals_model_validation_result_review_bytes(
    value: Mapping[str, Any] | None = None,
) -> bytes:
    """Serialize the review deterministically for later provenance pinning."""
    payload = (
        build_fotmob_utc_native_expected_goals_model_validation_result_review()
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
    "FAILED_STRONG_CHECK",
    "NEXT_REQUIRED_BOUNDARY",
    "REVIEW_ID",
    "REVIEW_STATE",
    "build_fotmob_utc_native_expected_goals_model_validation_result_review",
    "canonical_fotmob_utc_native_expected_goals_model_validation_result_review_bytes",
]
