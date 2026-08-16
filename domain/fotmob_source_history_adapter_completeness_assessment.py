"""Validate the frozen PR #115 source-history adapter/completeness receipt.

PR #115 executes the PR81/PR99 boundary against the preserved historical
campaign. It fails closed because the reviewed prospective ordinary-FT adapter
cannot consume the campaign under its frozen pair-lineage and structural-schema
requirements. No historical rows or downstream model/betting authority are
created by this module.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import domain.fotmob_ordinary_ft_finished_score_source_history_completeness_protocol as pr99
import domain.fotmob_source_history_elo_initialization_boundary_qualification as pr114
import domain.prospective_successor_source_history_completeness_protocol as pr81
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = REPOSITORY_ROOT / "artifacts" / "research-manifests" / "fotmob-source-history-adapter-completeness-assessment-v1.json"
RECEIPT_SHA256 = "247dd06389f17cc2d27af568b92f19de1da49b3d3fce1c73ad901d904a2366b2"
RECEIPT_SIZE = 6_634
REPOSITORY_MAIN_ANCHOR = "1571ab8f1431bd7e083a02f5c55e30ff11c01c5a"
DATASET_NAME = "athena-fotmob-source-history-adapter-completeness-assessment-v1"
ASSESSMENT_STATE = "EXECUTED_FAIL_CLOSED_REVIEWED_PROSPECTIVE_ADAPTER_INCOMPATIBLE_WITH_HISTORICAL_CAMPAIGN"
PRIMARY_STATUS = "BLOCKED_RESULT_EVIDENCE_GAP"
NEXT_REQUIRED_BOUNDARY = "PRE_REGISTER_REVIEWED_FOTMOB_HISTORICAL_SOURCE_HISTORY_ADAPTER_PROTOCOL"
DERIVED_SOURCE_KEY = "fotmob_data_matches_reviewed_ordinary_ft_finished_score"
REVIEWED_ADAPTER_BLOB_SHA = "868563206e09010fce74b4ba7954028930baad54"
PR81_SHA256 = "9d16fcc79e9809a82ef154c75b8e263f782a4e1d4723b57cc216d893c88780ec"
PR81_SIZE = 4_223
PR99_SHA256 = "edddd7445bb9bb6ed2db4778b6ab48da9489ae6efac822b6e6c139992275bf87"
PR99_SIZE = 5_741
PR108_RECEIPT_SHA256 = "fdb55feef9585fe0aa2668ddb9ac9a6eb8e63ac8870c06cdb7917d1f996e7bc9"
PR110_RECEIPT_SHA256 = "7d6bb5c86391c45abdbb588a27325c99ebf88c4753f75c108387e2c4d3dbb99d"
PR112_RECEIPT_SHA256 = "58c7a275580cc74489269a66de2836544e78ca232693d5283f1813ee817d3fc0"
PR114_RECEIPT_SHA256 = "fbbec0b858c3e9630d9f4c7dec630012f57811de52d300db3a11b781a719e110"
ARTIFACT_SHA256 = "7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f"

EXPECTED_BY_LEAGUE = {
    "B1": 1933, "D1": 1835, "E0": 2280, "F1": 2056, "G1": 1431,
    "I1": 2280, "N1": 1865, "P1": 1846, "SC0": 1380, "SP1": 2280, "T1": 2140,
}
EXPECTED_GATE_IDS = (
    "DERIVED_SCORE_CAPABILITY",
    "REQUIRED_DAILY_CAPTURE_COVERAGE",
    "ELEVEN_LEAGUE_MAPPING",
    "NON_ORDINARY_RESULT_DISPOSITION",
    "IDENTITY_AND_REARRANGEMENT_CHRONOLOGY",
    "ELO_INITIALIZATION_BOUNDARY",
    "SOURCE_DISPLAY_TIME_BASIS",
    "REUSABLE_ORDINARY_FT_ADAPTER_PAIR_LINEAGE",
    "REUSABLE_ORDINARY_FT_ADAPTER_HISTORICAL_SCHEMA",
    "HISTORICAL_RESULT_ROW_MATERIALIZATION",
    "PR80_CONSTRUCTOR_HANDOFF",
)
SAFETY_KEYS = frozenset({
    "source_history_adapter_approved", "source_history_completeness_proven",
    "ordinary_ft_history_rows_authorized", "pr80_constructor_input_authorized",
    "successor_live_inputs_qualified", "successor_candidate_approved",
    "expected_goals_transform_approved", "expected_goals_production_authorized",
    "score_matrix_authorized", "probability_inference_authorized",
    "probability_adjustment_authorized", "calibration_for_production_authorized",
    "pricing_authorized", "market_activation_authorized", "selection_authorized",
    "production_approval_authorized", "model_training_authorized", "bet_authorized",
    "competition_registry_mutation_authorized", "source_capability_registry_mutation_authorized",
})


class FotMobSourceHistoryAdapterCompletenessAssessmentError(ValueError):
    """Raised when the exact PR115 receipt no longer revalidates."""


def _error(message: str) -> FotMobSourceHistoryAdapterCompletenessAssessmentError:
    return FotMobSourceHistoryAdapterCompletenessAssessmentError(message)


def _canonical(value: Any) -> bytes:
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("PR115 receipt serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _verify_upstream() -> None:
    p81 = pr81.build_prospective_successor_source_history_completeness_protocol()
    raw81 = pr81.canonical_prospective_successor_source_history_completeness_protocol_bytes(p81)
    if (hashlib.sha256(raw81).hexdigest(), len(raw81)) != (PR81_SHA256, PR81_SIZE):
        raise _error("PR81 source-history protocol identity changed")
    p99 = pr99.build_fotmob_ordinary_ft_finished_score_source_history_completeness_protocol()
    raw99 = pr99.canonical_fotmob_ordinary_ft_finished_score_source_history_completeness_protocol_bytes(p99)
    if (hashlib.sha256(raw99).hexdigest(), len(raw99)) != (PR99_SHA256, PR99_SIZE):
        raise _error("PR99 derived-source protocol identity changed")
    pr114_receipt = pr114.load_fotmob_source_history_elo_initialization_boundary_qualification_receipt()
    if pr114_receipt.get("initialization_boundary_qualified") is not True:
        raise _error("PR114 initialization qualification changed")
    if pr114_receipt.get("remaining_blockers") != ["BLOCKED_HISTORICAL_COVERAGE_UNPROVEN"]:
        raise _error("PR114 blocker ancestry changed")
    derived = SOURCE_CAPABILITY_REGISTRY.get(DERIVED_SOURCE_KEY)
    if derived is None:
        raise _error("reviewed derived source capability is missing")
    if derived.full_time_score is not CapabilityAvailability.CONFIRMED:
        raise _error("derived full-time score capability changed")
    if derived.reliable_fixture_identity is not CapabilityAvailability.CONFIRMED:
        raise _error("derived fixture identity capability changed")
    if derived.historical_coverage is not CapabilityAvailability.UNKNOWN:
        raise _error("source capability registry historical coverage must remain UNKNOWN")


def _validate(receipt: dict[str, Any]) -> None:
    if receipt.get("schema_version") != 1 or receipt.get("dataset_name") != DATASET_NAME:
        raise _error("PR115 receipt identity fields changed")
    if receipt.get("assessment_state") != ASSESSMENT_STATE:
        raise _error("PR115 assessment state changed")
    if receipt.get("repository_main_anchor") != REPOSITORY_MAIN_ANCHOR:
        raise _error("PR115 main anchor changed")
    if receipt.get("protocols") != {
        "pr81": {"canonical_sha256": PR81_SHA256, "canonical_size_bytes": PR81_SIZE},
        "pr99": {"canonical_sha256": PR99_SHA256, "canonical_size_bytes": PR99_SIZE},
    }:
        raise _error("PR115 protocol ancestry changed")
    if receipt.get("upstream_qualifications") != {
        "pr108_mapping_receipt_sha256": PR108_RECEIPT_SHA256,
        "pr110_special_result_receipt_sha256": PR110_RECEIPT_SHA256,
        "pr112_chronology_receipt_sha256": PR112_RECEIPT_SHA256,
        "pr114_initialization_receipt_sha256": PR114_RECEIPT_SHA256,
    }:
        raise _error("PR115 qualification ancestry changed")

    source = receipt.get("source_evidence")
    if not isinstance(source, dict) or source.get("artifact_sha256") != ARTIFACT_SHA256:
        raise _error("PR115 preserved artifact identity changed")
    if (source.get("start_date"), source.get("end_date"), source.get("request_timezone"), source.get("ccode3")) != (
        "2020-08-01", "2026-08-14", "UTC", "NGA"
    ):
        raise _error("PR115 campaign envelope changed")

    checks = receipt.get("campaign_checks")
    if not isinstance(checks, dict):
        raise _error("PR115 campaign checks missing")
    expected_checks = {
        "request_date_count": 2205,
        "capture_manifest_count": 4410,
        "distinct_manifest_pair_count": 2205,
        "target_family_fixture_date_pair_count": 21640,
        "target_family_raw_capture_row_count": 43280,
        "preboundary_ordinary_ft_fixture_date_occurrence_count": 10,
        "reviewed_ordinary_ft_candidate_count_on_or_after_floor": 21326,
        "special_state_occurrence_count_on_or_after_floor": 304,
        "same_date_target_relevant_field_conflict_count": 0,
        "source_display_time_basis": "Europe/Oslo",
        "source_display_time_basis_mismatch_count": 0,
        "ordinary_ft_candidates_by_model_league": EXPECTED_BY_LEAGUE,
        "minimum_pair_separation_microseconds": 3761138022,
        "maximum_pair_separation_microseconds": 7454335835,
    }
    if checks != expected_checks:
        raise _error("PR115 campaign checks changed")

    adapter = receipt.get("adapter_compatibility")
    if not isinstance(adapter, dict):
        raise _error("PR115 adapter compatibility evidence missing")
    if adapter.get("reviewed_adapter_blob_sha") != REVIEWED_ADAPTER_BLOB_SHA:
        raise _error("reviewed adapter ancestry changed")
    if adapter.get("capture_pair_count") != 2205:
        raise _error("adapter capture-pair count changed")
    if adapter.get("identical_raw_sha256_pair_count") != 2204:
        raise _error("identical-raw pair count changed")
    if adapter.get("distinct_raw_sha256_pair_count") != 1 or adapter.get("distinct_raw_sha256_pair_dates") != ["20250712"]:
        raise _error("distinct-raw pair evidence changed")
    if adapter.get("ordinary_ft_candidates_blocked_by_identical_raw_lineage_requirement") != 21326:
        raise _error("blocked ordinary-FT candidate accounting changed")
    if adapter.get("target_family_fixture_date_pairs_on_distinct_raw_dates") != 0 or adapter.get("ordinary_ft_candidates_on_or_after_floor_on_distinct_raw_dates") != 0:
        raise _error("distinct-raw target-family accounting changed")
    if adapter.get("identical_raw_exemplar_adapter_status") != "BLOCKED_CAPTURE_LINEAGE_OR_REQUEST_IDENTITY":
        raise _error("identical-raw adapter blocker changed")
    distinct_results = adapter.get("distinct_raw_pair_adapter_results")
    if distinct_results != [{
        "adapter_status": "BLOCKED_STRUCTURAL_REVALIDATION",
        "error_message": "capture pair failed the reviewed PR89 structural chain",
        "outcome": "BLOCKED",
        "request_date": "20250712",
    }]:
        raise _error("distinct-raw structural adapter result changed")

    gates = receipt.get("gate_results")
    if not isinstance(gates, list) or tuple(item.get("gate_id") for item in gates if isinstance(item, dict)) != EXPECTED_GATE_IDS:
        raise _error("PR115 gate set or order changed")
    blocked = [item for item in gates if item.get("outcome") == "BLOCKED"]
    if len(blocked) != 2 or any(item.get("status") != PRIMARY_STATUS for item in blocked):
        raise _error("PR115 fail-closed gate disposition changed")

    if receipt.get("primary_status") != PRIMARY_STATUS:
        raise _error("PR115 primary status changed")
    if receipt.get("remaining_blockers") != [PRIMARY_STATUS, "BLOCKED_HISTORICAL_COVERAGE_UNPROVEN"]:
        raise _error("PR115 remaining blockers changed")
    if receipt.get("next_required_boundary") != NEXT_REQUIRED_BOUNDARY:
        raise _error("PR115 next boundary changed")
    for key in (
        "source_history_adapter_approved", "source_history_completeness_proven",
        "historical_coverage_proven", "ordinary_ft_history_rows_authorized",
    ):
        if receipt.get(key) is not False:
            raise _error(f"{key} must remain exact False")
    if receipt.get("history_rows_materialized") != 0:
        raise _error("PR115 must not materialize history rows")

    safety = receipt.get("safety")
    if not isinstance(safety, dict) or set(safety) != SAFETY_KEYS:
        raise _error("PR115 safety key set changed")
    if any(type(value) is not bool or value is not False for value in safety.values()):
        raise _error("all PR115 downstream safety values must remain exact False")


def load_fotmob_source_history_adapter_completeness_assessment_receipt() -> dict[str, Any]:
    """Load and revalidate the exact canonical PR115 receipt."""
    _verify_upstream()
    raw = RECEIPT_PATH.read_bytes()
    if len(raw) != RECEIPT_SIZE or hashlib.sha256(raw).hexdigest() != RECEIPT_SHA256:
        raise _error("PR115 assessment receipt identity changed")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error("PR115 receipt is not valid JSON") from exc
    if not isinstance(value, dict) or raw != _canonical(value):
        raise _error("PR115 receipt is not exact canonical JSON")
    _validate(value)
    return value


def canonical_fotmob_source_history_adapter_completeness_assessment_receipt_bytes() -> bytes:
    value = load_fotmob_source_history_adapter_completeness_assessment_receipt()
    raw = _canonical(value)
    if len(raw) != RECEIPT_SIZE or hashlib.sha256(raw).hexdigest() != RECEIPT_SHA256:
        raise _error("PR115 canonical receipt identity changed")
    return raw


__all__ = [
    "ASSESSMENT_STATE", "DATASET_NAME", "NEXT_REQUIRED_BOUNDARY", "PRIMARY_STATUS",
    "RECEIPT_PATH", "RECEIPT_SHA256", "RECEIPT_SIZE",
    "FotMobSourceHistoryAdapterCompletenessAssessmentError",
    "canonical_fotmob_source_history_adapter_completeness_assessment_receipt_bytes",
    "load_fotmob_source_history_adapter_completeness_assessment_receipt",
]
