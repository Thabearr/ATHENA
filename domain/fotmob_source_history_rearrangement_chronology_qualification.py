"""Validate the reviewed FotMob rearrangement-chronology qualification receipt.

PR #112 executes only the PR #111 source-scoped chronology contract against the
exact preserved PR #105 campaign artifact. It resolves the reviewed chronology
blocker for the frozen 250-fixture corpus only. It does not materialize source
history or authorize model, probability, pricing, selection, production, or BET use.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import domain.fotmob_source_history_rearrangement_chronology_semantics_protocol as pr111
import domain.fotmob_source_history_special_result_semantics_qualification as pr110

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = (
    REPOSITORY_ROOT
    / "artifacts"
    / "research-manifests"
    / "fotmob-source-history-rearrangement-chronology-qualification-v1.json"
)

RECEIPT_SHA256 = "58c7a275580cc74489269a66de2836544e78ca232693d5283f1813ee817d3fc0"
RECEIPT_SIZE = 7_980
REPOSITORY_MAIN_ANCHOR = "9c156e6022b0034dfe16e0d9446b4e1890f53753"
PR111_PROTOCOL_BLOB_SHA = "58eb56a6c55048cb163b7611da7ef85468c91f9a"
PR111_PROTOCOL_SHA256 = "3f7caa751d0fe8114e50d8fee4bb2afa58023b4bee63429e4c6c51b9d2f92ce3"
PR111_PROTOCOL_SIZE = 7_642
PR110_RECEIPT_SHA256 = "7d6bb5c86391c45abdbb588a27325c99ebf88c4753f75c108387e2c4d3dbb99d"
PR110_RECEIPT_SIZE = 8_558
REARRANGED_HISTORY_PROJECTION_SHA256 = "9fa899ebeb0e42154832c1ca9dc040685a359add2a4cf7c1029fd13b7d56dbe8"
REARRANGED_HISTORY_PROJECTION_SIZE = 349_277
EDGE_PROJECTION_SHA256 = "2c85f3ccfa4fd34af928c339ec6ebc79048ed3a5252f88bb195b77fb61bb13b9"
EDGE_PROJECTION_SIZE = 90_086
QUALIFICATION_STATE = (
    "EXECUTED_REARRANGEMENT_CHRONOLOGY_QUALIFIED_HISTORY_MATERIALIZATION_UNREVIEWED"
)
RESOLVED_BLOCKER = "BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT"
EXPECTED_REMAINING_BLOCKERS = (
    "BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN",
    "BLOCKED_HISTORICAL_COVERAGE_UNPROVEN",
)
NEXT_REQUIRED_BOUNDARY = (
    "PRE_REGISTER_REVIEWED_FOTMOB_SOURCE_HISTORY_ELO_INITIALIZATION_BOUNDARY_PROTOCOL"
)
EXPECTED_STATE_COUNTS = {
    "POSTPONED": 239,
    "ABANDONED": 7,
    "CANCELLED": 5,
    "ORDINARY_FT": 243,
    "AWARDED_WIN": 8,
}
EXPECTED_CHECKS = {
    "rearranged_fixture_id_count": 250,
    "rearranged_fixture_date_occurrence_count": 502,
    "raw_same_date_capture_observation_count": 1004,
    "same_date_pair_count": 502,
    "same_date_pair_capture_count_mismatch_count": 0,
    "same_date_pair_relevant_field_conflict_count": 0,
    "cross_date_transition_edge_count": 252,
    "cross_date_static_identity_drift_count": 0,
    "request_date_kickoff_utc_date_mismatch_count": 0,
    "non_forward_kickoff_revision_edge_count": 0,
    "unknown_transition_pattern_count": 0,
    "exact_six_transition_patterns_observed": True,
    "exact_terminal_state_counts_observed": True,
    "all_raw_and_fixture_date_evidence_preserved": True,
    "destructive_collapse_performed": False,
    "real_world_resume_replay_restart_continuation_inference_performed": False,
}

class FotMobSourceHistoryRearrangementChronologyQualificationError(ValueError):
    """Raised when the frozen PR #112 receipt no longer revalidates."""


def _error(message: str) -> FotMobSourceHistoryRearrangementChronologyQualificationError:
    return FotMobSourceHistoryRearrangementChronologyQualificationError(message)


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
        raise _error("rearrangement chronology qualification serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _load_exact_receipt() -> dict[str, Any]:
    raw = RECEIPT_PATH.read_bytes()
    if len(raw) != RECEIPT_SIZE or hashlib.sha256(raw).hexdigest() != RECEIPT_SHA256:
        raise _error("PR112 qualification receipt identity changed")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error("PR112 qualification receipt is not valid JSON") from exc
    if not isinstance(value, dict) or raw != _canonical(value):
        raise _error("PR112 qualification receipt is not exact canonical JSON")
    return value


def _verify_upstream() -> dict[str, Any]:
    protocol = pr111.build_fotmob_source_history_rearrangement_chronology_semantics_protocol()
    protocol_raw = (
        pr111.canonical_fotmob_source_history_rearrangement_chronology_semantics_protocol_bytes(
            protocol
        )
    )
    if (len(protocol_raw), hashlib.sha256(protocol_raw).hexdigest()) != (
        PR111_PROTOCOL_SIZE,
        PR111_PROTOCOL_SHA256,
    ):
        raise _error("PR111 protocol identity changed")
    if pr111.NEXT_REQUIRED_BOUNDARY != (
        "EXECUTE_REVIEWED_FOTMOB_SOURCE_HISTORY_REARRANGEMENT_CHRONOLOGY_QUALIFICATION"
    ):
        raise _error("PR111 execution boundary changed")

    pr110_receipt = pr110.load_fotmob_source_history_special_result_semantics_qualification_receipt()
    pr110_raw = (
        pr110.canonical_fotmob_source_history_special_result_semantics_qualification_receipt_bytes()
    )
    if (len(pr110_raw), hashlib.sha256(pr110_raw).hexdigest()) != (
        PR110_RECEIPT_SIZE,
        PR110_RECEIPT_SHA256,
    ):
        raise _error("PR110 qualification receipt identity changed")
    if pr110_receipt.get("special_result_semantics_qualified") is not True:
        raise _error("PR110 special-result semantics are no longer qualified")
    if pr110_receipt.get("historical_coverage_proven") is not False:
        raise _error("PR110 historical-coverage premise changed")
    chronology = pr110_receipt.get("chronology_handoff")
    if not isinstance(chronology, dict):
        raise _error("PR110 chronology handoff is missing")
    if chronology.get("chronology_resolved") is not False:
        raise _error("PR110 chronology premise must remain unresolved")
    if chronology.get("rearranged_fixture_id_count") != 250:
        raise _error("PR110 rearranged fixture count changed")
    return pr110_receipt


def _validate_transition_records(receipt: dict[str, Any]) -> None:
    records = receipt.get("transition_records")
    if not isinstance(records, list) or len(records) != len(pr111.TRANSITION_SPECS):
        raise _error("qualification must contain exactly six transition records")

    seen_ids: set[int] = set()
    total_edges = 0
    for record, spec in zip(records, pr111.TRANSITION_SPECS):
        if not isinstance(record, dict):
            raise _error("transition record must be an object")
        pattern_id, pattern, fixture_count, _, terminal_disposition = spec
        if record.get("pattern_id") != pattern_id:
            raise _error(f"{pattern_id} record order or identity changed")
        if record.get("pattern") != list(pattern):
            raise _error(f"{pattern_id} state pattern changed")
        if record.get("fixture_id_count") != fixture_count:
            raise _error(f"{pattern_id} fixture count changed")
        if record.get("terminal_state") != pattern[-1]:
            raise _error(f"{pattern_id} terminal state changed")
        if record.get("terminal_disposition") != terminal_disposition:
            raise _error(f"{pattern_id} terminal disposition changed")
        expected_edge_count = fixture_count * (len(pattern) - 1)
        if record.get("transition_edge_count") != expected_edge_count:
            raise _error(f"{pattern_id} edge count changed")
        total_edges += expected_edge_count

        fixture_ids = record.get("fixture_ids")
        if (
            not isinstance(fixture_ids, list)
            or len(fixture_ids) != fixture_count
            or fixture_ids != sorted(fixture_ids)
            or any(type(item) is not int or item <= 0 for item in fixture_ids)
            or len(set(fixture_ids)) != len(fixture_ids)
        ):
            raise _error(f"{pattern_id} fixture membership is malformed")
        overlap = seen_ids.intersection(fixture_ids)
        if overlap:
            raise _error(f"{pattern_id} fixture membership overlaps another pattern")
        seen_ids.update(fixture_ids)

    if len(seen_ids) != 250 or total_edges != 252:
        raise _error("transition membership totals changed")


def _validate_receipt(receipt: dict[str, Any], pr110_receipt: dict[str, Any]) -> None:
    if receipt.get("schema_version") != 1:
        raise _error("qualification schema changed")
    if receipt.get("dataset_name") != (
        "athena-fotmob-source-history-rearrangement-chronology-qualification-v1"
    ):
        raise _error("qualification dataset changed")
    if receipt.get("scope") != (
        "IMMUTABLE_REARRANGEMENT_CHRONOLOGY_QUALIFICATION_RECEIPT_ONLY"
    ):
        raise _error("qualification scope changed")
    if receipt.get("repository_main_anchor") != REPOSITORY_MAIN_ANCHOR:
        raise _error("qualification main anchor changed")
    if receipt.get("protocol") != {
        "protocol_id": pr111.PROTOCOL_ID,
        "blob_sha": PR111_PROTOCOL_BLOB_SHA,
        "canonical_sha256": PR111_PROTOCOL_SHA256,
        "canonical_size_bytes": PR111_PROTOCOL_SIZE,
    }:
        raise _error("PR111 protocol ancestry changed")

    source = receipt.get("source_evidence")
    pr110_source = pr110_receipt.get("source_evidence")
    if not isinstance(source, dict) or not isinstance(pr110_source, dict):
        raise _error("source evidence is missing")
    expected_source = {
        "artifact_id": pr110_source.get("artifact_id"),
        "artifact_name": pr110_source.get("artifact_name"),
        "artifact_sha256": pr110_source.get("artifact_sha256"),
        "artifact_size_bytes": pr110_source.get("artifact_size_bytes"),
        "research_cache_tar_gz_sha256": pr110_source.get("research_cache_tar_gz_sha256"),
        "research_cache_tar_gz_size_bytes": pr110_source.get(
            "research_cache_tar_gz_size_bytes"
        ),
        "pr110_receipt_sha256": PR110_RECEIPT_SHA256,
        "pr110_receipt_size_bytes": PR110_RECEIPT_SIZE,
        "pr110_special_fixture_history_projection_sha256": pr110_source.get(
            "special_fixture_history_projection_sha256"
        ),
        "pr110_special_fixture_history_projection_size_bytes": pr110_source.get(
            "special_fixture_history_projection_size_bytes"
        ),
        "request_date_count": pr110_source.get("request_date_count"),
        "response_file_count": pr110_source.get("response_file_count"),
        "rearranged_fixture_history_projection_sha256": REARRANGED_HISTORY_PROJECTION_SHA256,
        "rearranged_fixture_history_projection_size_bytes": REARRANGED_HISTORY_PROJECTION_SIZE,
        "rearrangement_edge_projection_sha256": EDGE_PROJECTION_SHA256,
        "rearrangement_edge_projection_size_bytes": EDGE_PROJECTION_SIZE,
    }
    if source != expected_source:
        raise _error("source evidence ancestry or chronology projections changed")

    if receipt.get("qualification_state") != QUALIFICATION_STATE:
        raise _error("qualification state changed")
    if receipt.get("chronology_semantics_execution_performed") is not True:
        raise _error("chronology execution must remain qualified")
    if receipt.get("rearrangement_chronology_qualified") is not True:
        raise _error("rearrangement chronology must remain qualified")
    if receipt.get("resolved_blocker") != RESOLVED_BLOCKER:
        raise _error("resolved chronology blocker changed")
    if receipt.get("remaining_blockers") != list(EXPECTED_REMAINING_BLOCKERS):
        raise _error("remaining blocker set changed")
    if receipt.get("checks") != EXPECTED_CHECKS:
        raise _error("chronology qualification checks changed")
    if receipt.get("occurrence_state_counts") != EXPECTED_STATE_COUNTS:
        raise _error("chronology occurrence-state counts changed")

    _validate_transition_records(receipt)

    terminal = receipt.get("terminal_summary")
    if terminal != {
        "ordinary_ft_fixture_count": 243,
        "awarded_win_fixture_count": 7,
        "ordinary_ft_history_rows_authorized": False,
        "awarded_win_history_rows_authorized": False,
        "duplicate_terminal_awarded_fixture": {
            "fixture_id": 3932603,
            "request_dates": ["20230220", "20230305"],
        },
    }:
        raise _error("terminal chronology disposition changed")

    for key in (
        "source_history_mutation_performed",
        "historical_coverage_proven",
        "source_capability_registry_mutation_performed",
        "competition_registry_mutation_performed",
    ):
        if receipt.get(key) is not False:
            raise _error(f"{key} must remain exact False")

    if receipt.get("next_required_boundary") != NEXT_REQUIRED_BOUNDARY:
        raise _error("next reviewed boundary changed")
    safety = receipt.get("safety")
    if not isinstance(safety, dict) or not safety or any(value is not False for value in safety.values()):
        raise _error("all downstream safety flags must remain exact False")


def load_fotmob_source_history_rearrangement_chronology_qualification_receipt() -> dict[str, Any]:
    pr110_receipt = _verify_upstream()
    receipt = _load_exact_receipt()
    _validate_receipt(receipt, pr110_receipt)
    return receipt


def canonical_fotmob_source_history_rearrangement_chronology_qualification_receipt_bytes() -> bytes:
    receipt = load_fotmob_source_history_rearrangement_chronology_qualification_receipt()
    raw = _canonical(receipt)
    if len(raw) != RECEIPT_SIZE or hashlib.sha256(raw).hexdigest() != RECEIPT_SHA256:
        raise _error("qualification canonical identity changed")
    return raw
