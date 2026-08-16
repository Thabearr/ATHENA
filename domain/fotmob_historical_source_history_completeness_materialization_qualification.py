"""Validate the exact PR #119 historical completeness/materialization receipt.

PR #119 proves only scoped completeness for the exact frozen FotMob campaign and
materializes the exact reviewed ordinary-FT corpus. It does not mutate the global
source capability registry, prove PR #80 source-local semantic equivalence,
authorize target-specific PR #80 construction, or create model/pricing/BET authority.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import domain.fotmob_historical_source_history_adapter_qualification as pr117
import domain.fotmob_historical_source_history_completeness_materialization_protocol as pr118
import domain.fotmob_source_history_elo_initialization_boundary_qualification as pr114
import domain.fotmob_source_history_rearrangement_chronology_qualification as pr112
import domain.fotmob_source_history_special_result_semantics_qualification as pr110
import domain.prospective_successor_feature_construction_candidate as pr80
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = (
    REPOSITORY_ROOT
    / "artifacts"
    / "research-manifests"
    / "fotmob-historical-source-history-completeness-materialization-qualification-v1.json"
)
RECEIPT_SHA256 = "da8037cd9b4a4f91be942a4052e76134b66cc94221ed66e624c14008c9e562a0"
RECEIPT_SIZE = 6_810
REPOSITORY_MAIN_ANCHOR = "2b2f6390f077b562c185768db030c7c4e61a06de"
PR118_PROTOCOL_BLOB_SHA = "be7119f06804093959b6730c2fe8ac05ea4d2f05"
MATERIALIZATION_PROJECTION_SHA256 = "e5b78163a5eb68000b9a60dda97f04cac2a970f9cf2aaf588233151e586be8c2"
MATERIALIZATION_PROJECTION_SIZE = 10_545_099
QUALIFICATION_STATE = (
    "EXECUTED_SCOPED_HISTORICAL_COMPLETENESS_QUALIFIED_ROWS_MATERIALIZED_PR80_USE_UNREVIEWED"
)
QUALIFICATION_STATUS = "QUALIFIED_COMPLETE_FROZEN_HISTORICAL_HISTORY_THROUGH_2026_08_14"
RESOLVED_BLOCKER = "BLOCKED_HISTORICAL_COVERAGE_UNPROVEN"
NEXT_REQUIRED_BOUNDARY = (
    "PRE_REGISTER_REVIEWED_FOTMOB_PR80_SOURCE_LOCAL_TIME_SEMANTIC_EQUIVALENCE_PROTOCOL"
)
SOURCE_NAMESPACE = "fotmob_data_matches_reviewed_ordinary_ft_finished_score"

EXPECTED_BY_LEAGUE = {
    "B1": 1933,
    "D1": 1835,
    "E0": 2280,
    "F1": 2056,
    "G1": 1431,
    "I1": 2280,
    "N1": 1865,
    "P1": 1846,
    "SC0": 1380,
    "SP1": 2280,
    "T1": 2140,
}
EXPECTED_SPECIAL_COUNTS = {
    "ABANDONED": 20,
    "AFTER_EXTRA_TIME": 3,
    "AFTER_PENALTIES": 3,
    "AWARDED_WIN": 26,
    "CANCELLED": 11,
    "POSTPONED": 241,
}
SAFETY_KEYS = frozenset(
    {
        "bet_authorized",
        "calibration_for_production_authorized",
        "competition_registry_mutation_authorized",
        "expected_goals_production_authorized",
        "expected_goals_transform_approved",
        "global_historical_coverage_capability_mutation_authorized",
        "market_activation_authorized",
        "model_training_authorized",
        "pr80_constructor_input_authorized",
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
GLOBAL_AUTHORITY_KEYS = frozenset(
    {
        "global_source_capability_historical_coverage_confirmed",
        "source_capability_registry_mutation_performed",
        "competition_registry_mutation_performed",
        "pr80_constructor_input_authorized",
        "successor_live_inputs_qualified",
        "successor_candidate_approved",
        "model_training_authorized",
        "expected_goals_production_authorized",
        "probability_inference_authorized",
        "pricing_authorized",
        "market_activation_authorized",
        "selection_authorized",
        "production_approval_authorized",
        "bet_authorized",
    }
)


class FotMobHistoricalSourceHistoryCompletenessMaterializationQualificationError(ValueError):
    """Raised when the exact PR #119 qualification no longer revalidates."""


def _error(message: str) -> FotMobHistoricalSourceHistoryCompletenessMaterializationQualificationError:
    return FotMobHistoricalSourceHistoryCompletenessMaterializationQualificationError(message)


def _canonical(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("PR119 receipt serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def _verify_upstream() -> None:
    protocol = pr118.build_fotmob_historical_source_history_completeness_materialization_protocol()
    protocol_raw = pr118.canonical_fotmob_historical_source_history_completeness_materialization_protocol_bytes(protocol)
    if (hashlib.sha256(protocol_raw).hexdigest(), len(protocol_raw)) != (
        pr118.PROTOCOL_SHA256,
        pr118.PROTOCOL_SIZE,
    ):
        raise _error("PR118 protocol identity changed")
    if _git_blob_sha(Path(pr118.__file__)) != PR118_PROTOCOL_BLOB_SHA:
        raise _error("PR118 protocol implementation blob changed")
    if pr118.NEXT_REQUIRED_BOUNDARY != (
        "EXECUTE_REVIEWED_FOTMOB_HISTORICAL_SOURCE_HISTORY_COMPLETENESS_AND_MATERIALIZATION_QUALIFICATION"
    ):
        raise _error("PR118 next boundary changed")
    if QUALIFICATION_STATUS not in pr118.QUALIFICATION_STATUS_VOCABULARY:
        raise _error("PR119 positive status is no longer admitted by PR118")
    if pr118.PR80_SOURCE_LOCAL_SEMANTIC_EQUIVALENCE != "UNPROVEN":
        raise _error("PR118 source-local semantic-equivalence boundary changed")

    r117 = pr117.load_fotmob_historical_source_history_adapter_qualification_receipt()
    if (
        pr117.RECEIPT_SHA256 != "a8f06a9d789b20b4ef49766bd771fb5c4d13c4be657ac6a5fc8f284701054020"
        or pr117.RECEIPT_SIZE != 5_081
        or r117.get("historical_source_history_adapter_qualified") is not True
        or r117.get("history_rows_materialized") != 0
    ):
        raise _error("PR117 historical adapter ancestry changed")

    r110 = pr110.load_fotmob_source_history_special_result_semantics_qualification_receipt()
    if r110.get("special_result_semantics_qualified") is not True:
        raise _error("PR110 special-result qualification changed")
    r112 = pr112.load_fotmob_source_history_rearrangement_chronology_qualification_receipt()
    if r112.get("rearrangement_chronology_qualified") is not True:
        raise _error("PR112 rearrangement chronology qualification changed")
    r114 = pr114.load_fotmob_source_history_elo_initialization_boundary_qualification_receipt()
    if r114.get("initialization_boundary_qualified") is not True:
        raise _error("PR114 Elo initialization qualification changed")

    spec = pr80.build_prospective_successor_feature_construction_specification()
    spec_raw = pr80.canonical_prospective_successor_feature_construction_specification_bytes(spec)
    if (hashlib.sha256(spec_raw).hexdigest(), len(spec_raw)) != (
        pr118.PR80_CONSTRUCTION_SPEC_SHA256,
        pr118.PR80_CONSTRUCTION_SPEC_SIZE,
    ):
        raise _error("PR80 construction specification changed")

    capability = SOURCE_CAPABILITY_REGISTRY.get(SOURCE_NAMESPACE)
    if capability is None:
        raise _error("reviewed derived FotMob source capability is missing")
    if capability.full_time_score is not CapabilityAvailability.CONFIRMED:
        raise _error("reviewed FotMob full-time score capability changed")
    if capability.reliable_fixture_identity is not CapabilityAvailability.CONFIRMED:
        raise _error("reviewed FotMob fixture identity capability changed")
    if capability.historical_coverage is not CapabilityAvailability.UNKNOWN:
        raise _error("global FotMob historical coverage must remain UNKNOWN after PR119")


def _validate(receipt: dict[str, Any]) -> None:
    if receipt.get("schema_version") != 1:
        raise _error("PR119 schema version changed")
    if receipt.get("dataset_name") != (
        "athena-fotmob-historical-source-history-completeness-materialization-qualification-v1"
    ):
        raise _error("PR119 dataset identity changed")
    if receipt.get("qualification_scope") != (
        "IMMUTABLE_FROZEN_CAMPAIGN_SCOPED_HISTORICAL_COMPLETENESS_AND_MATERIALIZATION_ONLY"
    ):
        raise _error("PR119 qualification scope changed")
    if receipt.get("qualification_state") != QUALIFICATION_STATE:
        raise _error("PR119 qualification state changed")
    if receipt.get("repository_main_anchor") != REPOSITORY_MAIN_ANCHOR:
        raise _error("PR119 repository main anchor changed")

    if receipt.get("protocol") != {
        "protocol_id": pr118.PROTOCOL_ID,
        "blob_sha": PR118_PROTOCOL_BLOB_SHA,
        "canonical_sha256": pr118.PROTOCOL_SHA256,
        "canonical_size_bytes": pr118.PROTOCOL_SIZE,
    }:
        raise _error("PR118 protocol ancestry changed")

    expected_upstream = {
        "pr81_protocol_sha256": pr118.PR81_PROTOCOL_SHA256,
        "pr99_protocol_sha256": pr118.PR99_PROTOCOL_SHA256,
        "pr110_special_result_receipt_sha256": pr118.PR110_RECEIPT_SHA256,
        "pr112_rearrangement_chronology_receipt_sha256": pr118.PR112_RECEIPT_SHA256,
        "pr114_elo_initialization_receipt_sha256": pr118.PR114_RECEIPT_SHA256,
        "pr117_historical_adapter_receipt_sha256": pr117.RECEIPT_SHA256,
        "pr117_historical_adapter_receipt_size_bytes": pr117.RECEIPT_SIZE,
        "pr117_ordinary_ft_projection_sha256": pr117.ORDINARY_FT_PROJECTION_SHA256,
        "pr117_ordinary_ft_projection_size_bytes": pr117.ORDINARY_FT_PROJECTION_SIZE,
    }
    if receipt.get("upstream") != expected_upstream:
        raise _error("PR119 upstream ancestry changed")

    if receipt.get("source_evidence") != {
        "artifact_id": pr118.ARTIFACT_ID,
        "artifact_name": "fotmob-ordinary-ft-source-history-campaign-31887523012",
        "artifact_sha256": pr118.ARTIFACT_SHA256,
        "artifact_size_bytes": pr118.ARTIFACT_SIZE,
        "research_cache_sha256": pr118.RESEARCH_CACHE_SHA256,
        "research_cache_size_bytes": pr118.RESEARCH_CACHE_SIZE,
        "request_timezone": pr118.REQUEST_TIMEZONE,
        "ccode3": pr118.REQUEST_CCODE3,
        "historical_request_date_start": pr118.HISTORICAL_REQUEST_DATE_START,
        "historical_request_date_end": pr118.HISTORICAL_REQUEST_DATE_END,
        "source_display_time_basis": pr118.SOURCE_DISPLAY_TIME_BASIS,
        "pr80_source_local_semantic_equivalence": "UNPROVEN",
    }:
        raise _error("PR119 source evidence envelope changed")

    q = receipt.get("completeness_qualification")
    if not isinstance(q, dict):
        raise _error("PR119 completeness qualification missing")
    exact_counts = {
        "qualification_status": QUALIFICATION_STATUS,
        "request_date_count": 2205,
        "capture_manifest_count": 4410,
        "target_family_fixture_date_occurrence_count": 21640,
        "ordinary_ft_occurrence_count": 21336,
        "reviewed_special_state_occurrence_count": 304,
        "preboundary_ordinary_ft_occurrence_count": 10,
        "on_or_after_floor_materialization_candidate_count": 21326,
        "ordinary_ft_unique_source_fixture_id_count": 21336,
        "ordinary_ft_duplicate_source_fixture_id_count": 0,
        "source_scoped_team_identity_count": 282,
        "materialized_kickoff_utc_min": "2020-08-01T11:30:00Z",
        "materialized_kickoff_utc_max": "2026-08-14T19:15:00Z",
        "materialized_observed_at_min": "2026-08-15T13:34:24.178983Z",
        "materialized_observed_at_max": "2026-08-15T14:37:02.830087Z",
        "minimum_final_result_observation_lag_microseconds": 69_722_830_087,
        "maximum_final_result_observation_lag_microseconds": 190_519_464_178_983,
    }
    for key, value in exact_counts.items():
        if q.get(key) != value:
            raise _error(f"PR119 {key} changed")
    if q.get("on_or_after_floor_by_model_league") != EXPECTED_BY_LEAGUE:
        raise _error("PR119 per-league materialization accounting changed")
    if q.get("special_state_occurrence_counts") != EXPECTED_SPECIAL_COUNTS:
        raise _error("PR119 special-state accounting changed")
    for key in (
        "missing_required_date_count",
        "capture_pair_cardinality_mismatch_count",
        "request_identity_mismatch_count",
        "manifest_raw_lineage_mismatch_count",
        "unreviewed_target_state_occurrence_count",
        "materializable_duplicate_source_fixture_id_count",
        "same_team_same_source_local_kickoff_conflict_count",
        "same_team_same_utc_kickoff_conflict_count",
        "request_date_kickoff_utc_date_mismatch_count",
        "source_display_time_basis_mismatch_count",
        "source_local_utc_global_order_disagreement_count",
        "final_result_observation_not_after_kickoff_count",
        "materialization_row_invariant_violation_count",
        "materialization_evidence_sha256_duplicate_count",
        "materialization_evidence_reference_duplicate_count",
    ):
        if q.get(key) != 0:
            raise _error(f"PR119 {key} must remain zero")

    materialization = receipt.get("materialization")
    if materialization != {
        "history_row_count": 21326,
        "projection_format": "CANONICAL_JSON_LINES_SORTED_BY_SOURCE_LOCAL_KICKOFF_THEN_FIXTURE_IDENTIFIER",
        "projection_sha256": MATERIALIZATION_PROJECTION_SHA256,
        "projection_size_bytes": MATERIALIZATION_PROJECTION_SIZE,
        "source_namespace": SOURCE_NAMESPACE,
        "source_local_kickoff_derivation": "CANONICAL_KICKOFF_UTC_TO_EUROPE_OSLO_THEN_NAIVE_DISPLAY_TIME_CANDIDATE",
        "observed_at_rule": "EARLIEST_OF_THE_TWO_PR117_QUALIFIED_MANIFEST_OBSERVATION_TIMES",
        "evidence_sha256_rule": "SHA256_OF_EXACT_CANONICAL_PR117_ORDINARY_FT_PROJECTION_RECORD",
        "evidence_reference_rule": "FROZEN_CAMPAIGN_REQUEST_DATE_AND_SOURCE_FIXTURE_ID",
        "pr80_structural_validation_performed": True,
        "pr80_source_local_semantic_equivalence_proven": False,
        "pr80_constructor_input_authorized": False,
    }:
        raise _error("PR119 materialization contract changed")

    if receipt.get("scoped_authority") != {
        "frozen_campaign_historical_source_history_completeness_proven": True,
        "frozen_campaign_historical_adapter_approved": True,
        "exact_21326_ordinary_ft_history_rows_materialized": True,
        "exact_21326_ordinary_ft_history_rows_materialization_authorized": True,
    }:
        raise _error("PR119 scoped authority changed")

    global_authority = receipt.get("global_authority")
    if not isinstance(global_authority, dict) or set(global_authority) != GLOBAL_AUTHORITY_KEYS:
        raise _error("PR119 global authority key set changed")
    if any(type(value) is not bool or value is not False for value in global_authority.values()):
        raise _error("all PR119 global authority values must remain exact False")

    if receipt.get("handoff_constraints") != [
        "PR80_SOURCE_LOCAL_SEMANTIC_EQUIVALENCE_REMAINS_UNPROVEN",
        "TARGETS_REQUIRING_DATES_AFTER_2026_08_14_REQUIRE_A_SEPARATELY_REVIEWED_CONTIGUOUS_PROSPECTIVE_EXTENSION",
        "PR80_TARGET_SPECIFIC_HISTORY_USE_REMAINS_UNREVIEWED",
    ]:
        raise _error("PR119 handoff constraints changed")
    if receipt.get("resolved_blocker") != RESOLVED_BLOCKER:
        raise _error("PR119 resolved blocker changed")
    if receipt.get("next_required_boundary") != NEXT_REQUIRED_BOUNDARY:
        raise _error("PR119 next boundary changed")

    safety = receipt.get("safety")
    if not isinstance(safety, dict) or set(safety) != SAFETY_KEYS:
        raise _error("PR119 safety key set changed")
    if any(type(value) is not bool or value is not False for value in safety.values()):
        raise _error("all PR119 downstream safety values must remain exact False")


def load_fotmob_historical_source_history_completeness_materialization_qualification_receipt() -> dict[str, Any]:
    """Load and revalidate the exact canonical PR #119 receipt."""
    _verify_upstream()
    raw = RECEIPT_PATH.read_bytes()
    if len(raw) != RECEIPT_SIZE or hashlib.sha256(raw).hexdigest() != RECEIPT_SHA256:
        raise _error("PR119 qualification receipt identity changed")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error("PR119 receipt is not valid JSON") from exc
    if not isinstance(value, dict) or raw != _canonical(value):
        raise _error("PR119 receipt is not exact canonical JSON")
    _validate(value)
    return value


def canonical_fotmob_historical_source_history_completeness_materialization_qualification_receipt_bytes() -> bytes:
    value = load_fotmob_historical_source_history_completeness_materialization_qualification_receipt()
    raw = _canonical(value)
    if len(raw) != RECEIPT_SIZE or hashlib.sha256(raw).hexdigest() != RECEIPT_SHA256:
        raise _error("PR119 canonical receipt identity changed")
    return raw


__all__ = [
    "MATERIALIZATION_PROJECTION_SHA256",
    "MATERIALIZATION_PROJECTION_SIZE",
    "NEXT_REQUIRED_BOUNDARY",
    "QUALIFICATION_STATE",
    "QUALIFICATION_STATUS",
    "RECEIPT_PATH",
    "RECEIPT_SHA256",
    "RECEIPT_SIZE",
    "RESOLVED_BLOCKER",
    "SOURCE_NAMESPACE",
    "FotMobHistoricalSourceHistoryCompletenessMaterializationQualificationError",
    "canonical_fotmob_historical_source_history_completeness_materialization_qualification_receipt_bytes",
    "load_fotmob_historical_source_history_completeness_materialization_qualification_receipt",
]
