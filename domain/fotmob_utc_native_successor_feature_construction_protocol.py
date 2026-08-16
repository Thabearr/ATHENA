"""Pre-register a UTC-native FotMob successor feature-construction boundary.

This protocol is independent of the PR69/PR80 source-local equivalence lineage.
It uses only the exact PR119-qualified FotMob ordinary-FT corpus and canonical
``status.utcTime`` as its chronology coordinate. It does not claim PR69 parity,
authorize model training, calculate probabilities, inspect bookmaker prices, or
authorize BET.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import domain.fotmob_historical_source_history_completeness_materialization_qualification as pr119
import domain.prospective_successor_feature_construction_candidate as pr80


SCHEMA_VERSION = 1
PROTOCOL_ID = "FOTMOB_UTC_NATIVE_SUCCESSOR_FEATURE_CONSTRUCTION_PROTOCOL_V1"
PROTOCOL_SCOPE = "FROZEN_PR119_HISTORY_UTC_NATIVE_FEATURE_RESEARCH_ONLY"
PROTOCOL_STATE = (
    "PRE_REGISTERED_NOT_EXECUTED_FOTMOB_UTC_NATIVE_FEATURE_CONSTRUCTION_UNQUALIFIED"
)
BASE_MAIN_SHA = "4a2ca10af4b14194253ba6fc84bca780e2b03d58"
NEXT_REQUIRED_BOUNDARY = (
    "EXECUTE_REVIEWED_FOTMOB_UTC_NATIVE_SUCCESSOR_FEATURE_CONSTRUCTION_QUALIFICATION"
)

PR119_RECEIPT_SHA256 = "da8037cd9b4a4f91be942a4052e76134b66cc94221ed66e624c14008c9e562a0"
PR119_RECEIPT_SIZE = 6_810
PR119_RECEIPT_BLOB_SHA = "870f661501e2a8bb9ca1bfee64a2f1a44319da70"
PR119_QUALIFICATION_BLOB_SHA = "f0d17dbcd70fc8b5432b50061525224642541c05"
PR80_CONSTRUCTOR_BLOB_SHA = "9135f056d036fd0207a3daead2599ac2520274be"
PRESERVED_CAMPAIGN_ARTIFACT_ID = 9_249_856_559
PRESERVED_CAMPAIGN_ARTIFACT_SHA256 = (
    "7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f"
)
PRESERVED_CAMPAIGN_ARTIFACT_SIZE = 61_886_753
PR119_MATERIALIZATION_PROJECTION_SHA256 = (
    "e5b78163a5eb68000b9a60dda97f04cac2a970f9cf2aaf588233151e586be8c2"
)
PR119_MATERIALIZATION_PROJECTION_SIZE = 10_545_099

MODEL_LEAGUE_CODES = (
    "B1", "D1", "E0", "F1", "G1", "I1", "N1", "P1", "SC0", "SP1", "T1"
)

SAFETY_KEYS = frozenset(
    {
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
    }
)

PROTOCOL_SHA256 = "948b34e5f5ca6d69895beed0b0cdb79368bc507015f45975f2b3192b619975db"
PROTOCOL_SIZE = 5_803


class FotMobUTCNativeSuccessorFeatureProtocolError(ValueError):
    """Raised when frozen UTC-native feature ancestry no longer revalidates."""


def _error(message: str) -> FotMobUTCNativeSuccessorFeatureProtocolError:
    return FotMobUTCNativeSuccessorFeatureProtocolError(message)


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def _payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "protocol_scope": PROTOCOL_SCOPE,
        "protocol_state": PROTOCOL_STATE,
        "base_main_sha": BASE_MAIN_SHA,
        "ancestry": {
            "pr119_receipt_sha256": PR119_RECEIPT_SHA256,
            "pr119_receipt_size_bytes": PR119_RECEIPT_SIZE,
            "pr119_receipt_blob_sha": PR119_RECEIPT_BLOB_SHA,
            "pr119_qualification_blob_sha": PR119_QUALIFICATION_BLOB_SHA,
            "pr80_constructor_blob_sha": PR80_CONSTRUCTOR_BLOB_SHA,
            "preserved_campaign_artifact_id": PRESERVED_CAMPAIGN_ARTIFACT_ID,
            "preserved_campaign_artifact_sha256": PRESERVED_CAMPAIGN_ARTIFACT_SHA256,
            "preserved_campaign_artifact_size_bytes": PRESERVED_CAMPAIGN_ARTIFACT_SIZE,
            "pr119_materialization_projection_sha256": PR119_MATERIALIZATION_PROJECTION_SHA256,
            "pr119_materialization_projection_size_bytes": PR119_MATERIALIZATION_PROJECTION_SIZE,
        },
        "frozen_history_scope": {
            "qualified_ordinary_ft_row_count": 21_326,
            "kickoff_utc_min": "2020-08-01T11:30:00Z",
            "kickoff_utc_max": "2026-08-14T19:15:00Z",
            "historical_request_date_end": "2026-08-14",
            "source_namespace": "fotmob_data_matches_reviewed_ordinary_ft_finished_score",
            "model_league_codes": list(MODEL_LEAGUE_CODES),
            "full_athena_competition_universe_claimed": False,
            "global_fotmob_historical_coverage_claimed": False,
        },
        "time_basis": {
            "canonical_coordinate": "STATUS_UTCTIME_AWARE_UTC",
            "raw_field": "status.utcTime",
            "timezone_conversion_permitted": False,
            "display_time_field_used": False,
            "europe_oslo_projection_used": False,
            "naive_datetime_used": False,
            "pr69_source_local_equivalence_claimed": False,
            "pr80_source_local_parity_claimed": False,
        },
        "row_admission": {
            "must_be_exact_pr119_qualified_ordinary_ft_fixture": True,
            "must_revalidate_raw_evidence_lineage": True,
            "must_rederive_kickoff_utc_from_preserved_raw_status_utctime": True,
            "must_match_pr119_fixture_id_team_identity_and_regulation_ft_score": True,
            "special_result_rows_forbidden": True,
            "post_2026_08_14_rows_forbidden_without_separate_contiguous_extension": True,
        },
        "chronology": {
            "strict_prior_rule": "history_kickoff_utc < target_kickoff_utc",
            "same_kickoff_policy": (
                "COMPUTE_ALL_FEATURES_FROM_PRE_GROUP_STATE_THEN_BATCH_APPLY_RESULTS"
            ),
            "fixture_id_role": "DETERMINISTIC_OUTPUT_ORDER_ONLY_NOT_PRIOR_MEMBERSHIP",
            "cross_timezone_comparison_forbidden": True,
        },
        "feature_contract": {
            "home_form": {
                "history": "last_up_to_5_strictly_prior_same_team_ordinary_ft_rows",
                "points": "win=3,draw=1,loss=0",
                "formula": "round(0.10 + ((points / (n * 3)) * 0.85), 3)",
                "no_prior_history_status": "MISSING",
                "default_forbidden": True,
            },
            "away_form": {
                "history": "last_up_to_5_strictly_prior_same_team_ordinary_ft_rows",
                "points": "win=3,draw=1,loss=0",
                "formula": "round(0.10 + ((points / (n * 3)) * 0.85), 3)",
                "no_prior_history_status": "MISSING",
                "default_forbidden": True,
            },
            "home_elo": {
                "initial_rating": 1500,
                "initialization_classification": (
                    "SOURCE_NATIVE_REPLAY_ASSUMPTION_NOT_OBSERVED_EVIDENCE"
                ),
                "home_expected_adjustment": 50,
                "expected_formula": "1/(1+10**((opponent-adjusted-self)/400))",
                "score": "win=1,draw=0.5,loss=0",
                "k_schedule": "32_if_matches_lt_20;24_if_lt_50;else_16",
                "update": "int(old + K * (score - expected))",
                "season_reset": False,
                "same_kickoff_updates_after_group": True,
            },
            "away_elo": {
                "initial_rating": 1500,
                "initialization_classification": (
                    "SOURCE_NATIVE_REPLAY_ASSUMPTION_NOT_OBSERVED_EVIDENCE"
                ),
                "home_expected_adjustment": 50,
                "expected_formula": "1/(1+10**((opponent-adjusted-self)/400))",
                "score": "win=1,draw=0.5,loss=0",
                "k_schedule": "32_if_matches_lt_20;24_if_lt_50;else_16",
                "update": "int(old + K * (score - expected))",
                "season_reset": False,
                "same_kickoff_updates_after_group": True,
            },
            "fatigue": {
                "home_rest_days": (
                    "(target_kickoff_utc - home_last_prior_kickoff_utc).days"
                ),
                "away_rest_days": (
                    "(target_kickoff_utc - away_last_prior_kickoff_utc).days"
                ),
                "differential": "home_rest_days - away_rest_days",
                "bucket": "0.30_if_diff_lt_-2;0.10_if_diff_lt_0;else_0.0",
                "missing_prior_history_status": "MISSING",
                "timezone_conversion_forbidden": True,
            },
            "historical_live_data_freshness": {
                "status": "NOT_RECONSTRUCTIBLE_WITH_CURRENT_EVIDENCE",
                "numeric_default_forbidden": True,
                "excluded_from_historical_training_features": True,
                "prospective_freshness_gate_remains_separate": True,
            },
        },
        "qualification_execution": {
            "must_report_total_rows_seen": True,
            "must_report_per_feature_available_missing_blocked_counts": True,
            "must_report_same_kickoff_group_count": True,
            "must_report_identity_or_lineage_conflicts": True,
            "must_emit_canonical_hash_sealed_projection": True,
            "must_not_fit_or_tune_expected_goals_model": True,
            "must_not_calculate_market_probabilities": True,
            "must_not_use_bookmaker_data": True,
        },
        "forbidden_shortcuts": [
            "DO_NOT_PROJECT_UTC_TO_EUROPE_OSLO_OR_ANY_SOURCE_LOCAL_TIME",
            "DO_NOT_LABEL_NAIVE_UTC_AS_SOURCE_LOCAL_TIME",
            "DO_NOT_CLAIM_PR69_OR_PR80_TIME_PARITY",
            "DO_NOT_DEFAULT_MISSING_FORM_FATIGUE_OR_FRESHNESS",
            "DO_NOT_USE_FUTURE_OR_SAME_KICKOFF_RESULTS_AS_PRIOR_STATE",
            "DO_NOT_ADMIT_SPECIAL_RESULT_ROWS",
            "DO_NOT_MUTATE_SOURCE_OR_COMPETITION_CAPABILITY_REGISTRIES",
            "DO_NOT_AUTHORIZE_MODEL_PROBABILITY_PRICING_SELECTION_PRODUCTION_OR_BET",
        ],
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": {key: False for key in sorted(SAFETY_KEYS)},
    }


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _verify_upstream() -> None:
    receipt = pr119.load_fotmob_historical_source_history_completeness_materialization_qualification_receipt()
    receipt_path = (
        Path(pr119.__file__).resolve().parents[1]
        / "artifacts"
        / "research-manifests"
        / "fotmob-historical-source-history-completeness-materialization-qualification-v1.json"
    )
    raw = receipt_path.read_bytes()
    if (hashlib.sha256(raw).hexdigest(), len(raw), _git_blob_sha(receipt_path)) != (
        PR119_RECEIPT_SHA256,
        PR119_RECEIPT_SIZE,
        PR119_RECEIPT_BLOB_SHA,
    ):
        raise _error("PR119 receipt identity changed")
    if _git_blob_sha(Path(pr119.__file__)) != PR119_QUALIFICATION_BLOB_SHA:
        raise _error("PR119 qualification implementation changed")
    if _git_blob_sha(Path(pr80.__file__)) != PR80_CONSTRUCTOR_BLOB_SHA:
        raise _error("PR80 mathematics reference implementation changed")

    if receipt["qualification_state"] != (
        "EXECUTED_SCOPED_HISTORICAL_COMPLETENESS_QUALIFIED_ROWS_MATERIALIZED_PR80_USE_UNREVIEWED"
    ):
        raise _error("PR119 qualification state changed")
    q = receipt["completeness_qualification"]
    if q["qualification_status"] != (
        "QUALIFIED_COMPLETE_FROZEN_HISTORICAL_HISTORY_THROUGH_2026_08_14"
    ):
        raise _error("PR119 completeness status changed")
    if q["on_or_after_floor_materialization_candidate_count"] != 21_326:
        raise _error("PR119 qualified row count changed")
    if (
        q["materialized_kickoff_utc_min"],
        q["materialized_kickoff_utc_max"],
    ) != (
        "2020-08-01T11:30:00Z",
        "2026-08-14T19:15:00Z",
    ):
        raise _error("PR119 UTC history envelope changed")
    if receipt["source_evidence"]["request_timezone"] != "UTC":
        raise _error("PR119 request timezone changed")
    if receipt["source_evidence"]["artifact_sha256"] != (
        PRESERVED_CAMPAIGN_ARTIFACT_SHA256
    ):
        raise _error("preserved FotMob campaign identity changed")
    if receipt["materialization"]["projection_sha256"] != (
        PR119_MATERIALIZATION_PROJECTION_SHA256
    ):
        raise _error("PR119 materialization projection identity changed")
    if receipt["global_authority"]["global_source_capability_historical_coverage_confirmed"] is not False:
        raise _error("global FotMob historical coverage must remain unqualified")


def build_fotmob_utc_native_successor_feature_construction_protocol() -> dict[str, Any]:
    """Return the result-free UTC-native protocol after exact upstream checks."""
    _verify_upstream()
    return _payload()


def canonical_fotmob_utc_native_successor_feature_construction_protocol_bytes() -> bytes:
    raw = _canonical(build_fotmob_utc_native_successor_feature_construction_protocol())
    if (hashlib.sha256(raw).hexdigest(), len(raw)) != (PROTOCOL_SHA256, PROTOCOL_SIZE):
        raise _error("UTC-native successor feature protocol identity changed")
    return raw


__all__ = [
    "BASE_MAIN_SHA",
    "NEXT_REQUIRED_BOUNDARY",
    "PROTOCOL_ID",
    "PROTOCOL_SCOPE",
    "PROTOCOL_SHA256",
    "PROTOCOL_SIZE",
    "PROTOCOL_STATE",
    "SAFETY_KEYS",
    "FotMobUTCNativeSuccessorFeatureProtocolError",
    "build_fotmob_utc_native_successor_feature_construction_protocol",
    "canonical_fotmob_utc_native_successor_feature_construction_protocol_bytes",
]
