"""Validate the exact PR #117 historical source-history adapter qualification receipt.

PR #117 qualifies only the frozen-campaign historical ordinary-FT adapter defined
by PR #116. It does not prove source-history completeness, materialize history,
authorize PR #80 inputs, or create model/pricing/selection/BET authority.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import domain.fotmob_historical_source_history_adapter_protocol as pr116
import domain.fotmob_source_history_adapter_completeness_assessment as pr115
import domain.fotmob_source_history_elo_initialization_boundary_qualification as pr114
import domain.fotmob_source_history_rearrangement_chronology_qualification as pr112
import domain.fotmob_source_history_special_result_semantics_qualification as pr110
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = (
    REPOSITORY_ROOT
    / "artifacts"
    / "research-manifests"
    / "fotmob-historical-source-history-adapter-qualification-v1.json"
)
RECEIPT_SHA256 = "a8f06a9d789b20b4ef49766bd771fb5c4d13c4be657ac6a5fc8f284701054020"
RECEIPT_SIZE = 5_081
REPOSITORY_MAIN_ANCHOR = "cbebb42393be50c77011463906b5d2b70e0ef2c5"
PR116_PROTOCOL_BLOB_SHA = "53682e3810bf3c06b1afc90b847361b6dcb3e04f"
PR116_PROTOCOL_SHA256 = "f987bc68eaf9f4c7b57a66788f3dcac5d704be6dad36ecae92bf5dd7e315ea9a"
PR116_PROTOCOL_SIZE = 9_898
ORDINARY_FT_PROJECTION_SHA256 = "eddb7f5b58eb3cb92087dc7bf57a45a270aebabce38641cd3b4ffc2277d67ed3"
ORDINARY_FT_PROJECTION_SIZE = 22_080_831
QUALIFICATION_STATE = "EXECUTED_HISTORICAL_SOURCE_HISTORY_ADAPTER_QUALIFIED_COMPLETENESS_UNPROVEN"
QUALIFICATION_STATUS = "QUALIFIED_FROZEN_CAMPAIGN_HISTORICAL_ORDINARY_FT_ADAPTER"
RESOLVED_BLOCKER = "BLOCKED_RESULT_EVIDENCE_GAP"
EXPECTED_REMAINING_BLOCKERS = ("BLOCKED_HISTORICAL_COVERAGE_UNPROVEN",)
NEXT_REQUIRED_BOUNDARY = (
    "PRE_REGISTER_REVIEWED_FOTMOB_HISTORICAL_SOURCE_HISTORY_COMPLETENESS_AND_MATERIALIZATION_PROTOCOL"
)
DERIVED_SOURCE_KEY = "fotmob_data_matches_reviewed_ordinary_ft_finished_score"

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
        "expected_goals_production_authorized",
        "expected_goals_transform_approved",
        "history_rows_materialization_authorized",
        "market_activation_authorized",
        "model_training_authorized",
        "ordinary_ft_history_rows_authorized",
        "pr80_constructor_input_authorized",
        "pricing_authorized",
        "probability_adjustment_authorized",
        "probability_inference_authorized",
        "production_approval_authorized",
        "score_matrix_authorized",
        "selection_authorized",
        "source_capability_registry_mutation_authorized",
        "source_history_adapter_approved",
        "source_history_completeness_proven",
        "successor_candidate_approved",
        "successor_live_inputs_qualified",
    }
)


class FotMobHistoricalSourceHistoryAdapterQualificationError(ValueError):
    """Raised when the exact PR #117 qualification no longer revalidates."""


def _error(message: str) -> FotMobHistoricalSourceHistoryAdapterQualificationError:
    return FotMobHistoricalSourceHistoryAdapterQualificationError(message)


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
        raise _error("PR117 receipt serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def _verify_upstream() -> None:
    protocol = pr116.build_fotmob_historical_source_history_adapter_protocol()
    protocol_raw = pr116.canonical_fotmob_historical_source_history_adapter_protocol_bytes(protocol)
    if (hashlib.sha256(protocol_raw).hexdigest(), len(protocol_raw)) != (
        PR116_PROTOCOL_SHA256,
        PR116_PROTOCOL_SIZE,
    ):
        raise _error("PR116 protocol identity changed")
    if _git_blob_sha(Path(pr116.__file__)) != PR116_PROTOCOL_BLOB_SHA:
        raise _error("PR116 protocol implementation blob changed")
    if pr116.NEXT_REQUIRED_BOUNDARY != (
        "EXECUTE_REVIEWED_FOTMOB_HISTORICAL_SOURCE_HISTORY_ADAPTER_QUALIFICATION"
    ):
        raise _error("PR116 next boundary changed")

    r110 = pr110.load_fotmob_source_history_special_result_semantics_qualification_receipt()
    if r110.get("special_result_semantics_qualified") is not True:
        raise _error("PR110 special-result qualification changed")
    r112 = pr112.load_fotmob_source_history_rearrangement_chronology_qualification_receipt()
    if r112.get("rearrangement_chronology_qualified") is not True:
        raise _error("PR112 chronology qualification changed")
    r114 = pr114.load_fotmob_source_history_elo_initialization_boundary_qualification_receipt()
    if r114.get("initialization_boundary_qualified") is not True:
        raise _error("PR114 initialization qualification changed")
    r115 = pr115.load_fotmob_source_history_adapter_completeness_assessment_receipt()
    if r115.get("primary_status") != RESOLVED_BLOCKER:
        raise _error("PR115 result-evidence blocker ancestry changed")
    if r115.get("history_rows_materialized") != 0:
        raise _error("PR115 unexpectedly materialized history rows")

    capability = SOURCE_CAPABILITY_REGISTRY.get(DERIVED_SOURCE_KEY)
    if capability is None:
        raise _error("reviewed derived FotMob score source is missing")
    if capability.full_time_score is not CapabilityAvailability.CONFIRMED:
        raise _error("derived full-time score capability changed")
    if capability.reliable_fixture_identity is not CapabilityAvailability.CONFIRMED:
        raise _error("derived fixture identity capability changed")
    if capability.historical_coverage is not CapabilityAvailability.UNKNOWN:
        raise _error("historical coverage must remain UNKNOWN after adapter qualification")


def _validate(receipt: dict[str, Any]) -> None:
    if receipt.get("schema_version") != 1:
        raise _error("PR117 schema version changed")
    if receipt.get("dataset_name") != "athena-fotmob-historical-source-history-adapter-qualification-v1":
        raise _error("PR117 dataset identity changed")
    if receipt.get("qualification_scope") != (
        "IMMUTABLE_FROZEN_CAMPAIGN_HISTORICAL_ORDINARY_FT_ADAPTER_QUALIFICATION_ONLY"
    ):
        raise _error("PR117 qualification scope changed")
    if receipt.get("qualification_state") != QUALIFICATION_STATE:
        raise _error("PR117 qualification state changed")
    if receipt.get("repository_main_anchor") != REPOSITORY_MAIN_ANCHOR:
        raise _error("PR117 main anchor changed")

    if receipt.get("protocol") != {
        "protocol_id": pr116.PROTOCOL_ID,
        "blob_sha": PR116_PROTOCOL_BLOB_SHA,
        "canonical_sha256": PR116_PROTOCOL_SHA256,
        "canonical_size_bytes": PR116_PROTOCOL_SIZE,
    }:
        raise _error("PR116 protocol ancestry changed")
    if receipt.get("upstream_qualifications") != {
        "pr110_special_result_receipt_sha256": pr110.RECEIPT_SHA256,
        "pr112_rearrangement_chronology_receipt_sha256": pr112.RECEIPT_SHA256,
        "pr114_elo_initialization_receipt_sha256": pr114.RECEIPT_SHA256,
        "pr115_adapter_completeness_receipt_sha256": pr115.RECEIPT_SHA256,
    }:
        raise _error("PR117 upstream qualification ancestry changed")

    source = receipt.get("source_evidence")
    if source != {
        "artifact_id": 9_249_856_559,
        "artifact_name": "fotmob-ordinary-ft-source-history-campaign-31887523012",
        "artifact_sha256": "7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f",
        "artifact_size_bytes": 61_886_753,
        "research_cache_sha256": "cbe665315258f7820e87265434d7a864c8e909cfb2e51950c56ed349860af5f6",
        "research_cache_size_bytes": 61_881_610,
        "request_timezone": "UTC",
        "ccode3": "NGA",
        "start_date": "2020-08-01",
        "end_date": "2026-08-14",
    }:
        raise _error("PR117 source evidence envelope changed")

    adapter = receipt.get("adapter_qualification")
    if not isinstance(adapter, dict):
        raise _error("PR117 adapter qualification evidence missing")
    expected_adapter = {
        "qualification_status": QUALIFICATION_STATUS,
        "request_date_count": 2205,
        "capture_manifest_count": 4410,
        "capture_pair_count": 2205,
        "distinct_manifest_pair_count": 2205,
        "identical_raw_sha256_pair_count": 2204,
        "distinct_raw_sha256_pair_count": 1,
        "distinct_raw_sha256_pair_dates": ["20250712"],
        "minimum_pair_separation_microseconds": 3761138022,
        "maximum_pair_separation_microseconds": 7454335835,
        "target_family_fixture_date_pair_count": 21640,
        "target_family_pairs_on_distinct_raw_dates": 0,
        "ordinary_ft_projection_record_count": 21336,
        "ordinary_ft_projection_sha256": ORDINARY_FT_PROJECTION_SHA256,
        "ordinary_ft_projection_size_bytes": ORDINARY_FT_PROJECTION_SIZE,
        "ordinary_ft_projection_raw_content_relation": "BYTE_IDENTICAL_FOR_ALL_21336_RECORDS",
        "ordinary_ft_unique_source_fixture_id_count": 21336,
        "ordinary_ft_duplicate_source_fixture_id_count": 0,
        "reviewed_special_state_occurrence_count": 304,
    }
    if adapter != expected_adapter:
        raise _error("PR117 adapter qualification evidence changed")

    checks = receipt.get("checks")
    if not isinstance(checks, dict):
        raise _error("PR117 qualification checks are missing")
    for key in (
        "manifest_raw_lineage_mismatch_count",
        "request_identity_mismatch_count",
        "network_acquisition_false_count",
        "same_manifest_pair_count",
        "pair_separation_below_300_seconds_count",
        "same_date_target_relevant_field_conflict_count",
        "source_display_time_basis_mismatch_count",
        "historical_halfs_keyset_mismatch_count",
        "historical_halfs_type_mismatch_count",
        "historical_halfs_parse_mismatch_count",
        "unreviewed_target_state_occurrence_count",
    ):
        if checks.get(key) != 0:
            raise _error(f"{key} must remain zero")
    if checks.get("source_display_time_basis") != "Europe/Oslo":
        raise _error("source display-time basis changed")
    if checks.get("preboundary_ordinary_ft_occurrence_count") != 10:
        raise _error("preboundary ordinary-FT count changed")
    if checks.get("on_or_after_floor_ordinary_ft_occurrence_count") != 21326:
        raise _error("on-or-after-floor ordinary-FT count changed")
    if checks.get("ordinary_ft_candidates_by_model_league") != EXPECTED_BY_LEAGUE:
        raise _error("per-league ordinary-FT accounting changed")
    if checks.get("special_state_occurrence_counts") != EXPECTED_SPECIAL_COUNTS:
        raise _error("reviewed special-state accounting changed")
    for key in (
        "all_raw_capture_evidence_preserved",
    ):
        if checks.get(key) is not True:
            raise _error(f"{key} must remain exact True")
    for key in (
        "raw_or_manifest_hash_synthesis_performed",
        "prospective_adapter_mutation_performed",
        "pr89_mutation_performed",
        "network_acquisition_performed",
    ):
        if checks.get(key) is not False:
            raise _error(f"{key} must remain exact False")

    if receipt.get("historical_adapter_execution_performed") is not True:
        raise _error("historical adapter execution flag changed")
    if receipt.get("historical_source_history_adapter_qualified") is not True:
        raise _error("historical adapter qualification flag changed")
    for key in (
        "source_history_adapter_approved",
        "source_history_completeness_proven",
        "historical_coverage_proven",
        "ordinary_ft_history_rows_authorized",
        "source_history_mutation_performed",
        "source_capability_registry_mutation_performed",
        "competition_registry_mutation_performed",
    ):
        if receipt.get(key) is not False:
            raise _error(f"{key} must remain exact False")
    if receipt.get("history_rows_materialized") != 0:
        raise _error("PR117 must materialize zero source-history rows")
    if receipt.get("resolved_blocker") != RESOLVED_BLOCKER:
        raise _error("PR117 resolved blocker changed")
    if receipt.get("remaining_blockers") != list(EXPECTED_REMAINING_BLOCKERS):
        raise _error("PR117 remaining blockers changed")
    if receipt.get("next_required_boundary") != NEXT_REQUIRED_BOUNDARY:
        raise _error("PR117 next boundary changed")

    safety = receipt.get("safety")
    if not isinstance(safety, dict) or set(safety) != SAFETY_KEYS:
        raise _error("PR117 safety key set changed")
    if any(type(value) is not bool or value is not False for value in safety.values()):
        raise _error("all PR117 downstream safety values must remain exact False")


def load_fotmob_historical_source_history_adapter_qualification_receipt() -> dict[str, Any]:
    """Load and revalidate the exact canonical PR #117 receipt."""
    _verify_upstream()
    raw = RECEIPT_PATH.read_bytes()
    if len(raw) != RECEIPT_SIZE or hashlib.sha256(raw).hexdigest() != RECEIPT_SHA256:
        raise _error("PR117 qualification receipt identity changed")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error("PR117 receipt is not valid JSON") from exc
    if not isinstance(value, dict) or raw != _canonical(value):
        raise _error("PR117 receipt is not exact canonical JSON")
    _validate(value)
    return value


def canonical_fotmob_historical_source_history_adapter_qualification_receipt_bytes() -> bytes:
    value = load_fotmob_historical_source_history_adapter_qualification_receipt()
    raw = _canonical(value)
    if len(raw) != RECEIPT_SIZE or hashlib.sha256(raw).hexdigest() != RECEIPT_SHA256:
        raise _error("PR117 canonical receipt identity changed")
    return raw


__all__ = [
    "EXPECTED_BY_LEAGUE",
    "EXPECTED_REMAINING_BLOCKERS",
    "EXPECTED_SPECIAL_COUNTS",
    "NEXT_REQUIRED_BOUNDARY",
    "ORDINARY_FT_PROJECTION_SHA256",
    "ORDINARY_FT_PROJECTION_SIZE",
    "QUALIFICATION_STATE",
    "QUALIFICATION_STATUS",
    "RECEIPT_PATH",
    "RECEIPT_SHA256",
    "RECEIPT_SIZE",
    "RESOLVED_BLOCKER",
    "FotMobHistoricalSourceHistoryAdapterQualificationError",
    "canonical_fotmob_historical_source_history_adapter_qualification_receipt_bytes",
    "load_fotmob_historical_source_history_adapter_qualification_receipt",
]
