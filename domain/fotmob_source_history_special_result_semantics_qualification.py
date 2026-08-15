"""Validate the reviewed FotMob source-history special-result semantics receipt.

PR #110 executes only the PR #109 classification/disposition contract against the
preserved PR #105 campaign artifact. It does not resolve rearrangement chronology,
materialize history, or authorize model, pricing, selection, production, or BET use.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import domain.fotmob_primary_id_competition_mapping_qualification as pr108
import domain.fotmob_source_history_special_result_semantics_protocol as pr109

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = REPOSITORY_ROOT / "artifacts" / "research-manifests" / "fotmob-source-history-special-result-semantics-qualification-v1.json"
RECEIPT_SHA256 = "7d6bb5c86391c45abdbb588a27325c99ebf88c4753f75c108387e2c4d3dbb99d"
RECEIPT_SIZE = 8_558
REPOSITORY_MAIN_ANCHOR = "2d66af0d176828e1a4efbea2abef6385b694330f"
PR109_PROTOCOL_BLOB_SHA = "9c9b10d34c9dacffc27ed4d480c71a241b52eff3"
PR109_PROTOCOL_SHA256 = "5fc2d1c089ecea5fd3ab4b9920f578ac25b555c0d89bebad4eedbfcd80c3cf87"
PR109_PROTOCOL_SIZE = 7_040
PR108_RECEIPT_SHA256 = "fdb55feef9585fe0aa2668ddb9ac9a6eb8e63ac8870c06cdb7917d1f996e7bc9"
PR108_RECEIPT_SIZE = 13_681
PR105_RECEIPT_SHA256 = "a8c5a704e06853d6debfc029653132ca201b98c1fc8a32b3e3095db18f8e1363"
PR105_RECEIPT_SIZE = 11_995
SPECIAL_PROJECTION_SHA256 = "ad2881eb67bec1988462953acc8d55d59366667b47f3b7c55e026d644b85c990"
SPECIAL_PROJECTION_SIZE = 211_526
HISTORY_PROJECTION_SHA256 = "459c94fd53430663562d9ce614ca2b52b518b6a8f06f6661b27b555c567c281d"
HISTORY_PROJECTION_SIZE = 380_539
QUALIFICATION_STATE = "EXECUTED_SPECIAL_RESULT_SEMANTICS_QUALIFIED_CHRONOLOGY_UNRESOLVED"
NEXT_REQUIRED_BOUNDARY = "PRE_REGISTER_REVIEWED_FOTMOB_SOURCE_HISTORY_REARRANGEMENT_CHRONOLOGY_SEMANTICS_PROTOCOL"
RESOLVED_BLOCKER = "BLOCKED_NON_ORDINARY_FT_RESULT_REQUIRES_SEPARATE_REVIEW"
EXPECTED_REMAINING_BLOCKERS = (
    "BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT",
    "BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN",
    "BLOCKED_HISTORICAL_COVERAGE_UNPROVEN",
)
HISTORY_DISPOSITION = "EXCLUDE_FROM_ORDINARY_REGULATION_TIME_MODEL_HISTORY"
PRESERVATION_DISPOSITION = "PRESERVE_AS_SOURCE_EVIDENCE_NO_SILENT_DROP_OR_COERCION"

EXPECTED_CLASS_COUNTS = {
    "AWARDED_WIN": (25, 26, 52, [190], 7),
    "AFTER_EXTRA_TIME": (3, 3, 6, [11], 0),
    "AFTER_PENALTIES": (3, 3, 6, [13], 0),
    "ABANDONED": (20, 20, 40, [17], 7),
    "CANCELLED": (11, 11, 22, [106], 5),
    "POSTPONED": (239, 241, 482, [5], 237),
}
EXPECTED_TRANSITIONS = [
    {"fixture_id_count": 234, "pattern": ["POSTPONED", "ORDINARY_FT"]},
    {"fixture_id_count": 7, "pattern": ["ABANDONED", "ORDINARY_FT"]},
    {"fixture_id_count": 5, "pattern": ["CANCELLED", "AWARDED_WIN"]},
    {"fixture_id_count": 2, "pattern": ["POSTPONED", "POSTPONED", "ORDINARY_FT"]},
    {"fixture_id_count": 1, "pattern": ["POSTPONED", "AWARDED_WIN"]},
    {"fixture_id_count": 1, "pattern": ["AWARDED_WIN", "AWARDED_WIN"]},
]
EXPECTED_TERMINAL_IDS = {
    "AWARDED_WIN": [3428775,3932603,3932609,3932614,3932617,3932622,3932627,3932647,3932653,3932663,3932664,3932668,3932683,3932688,3932695,3932699,3932707,3932708,3932710,3932713,3932723,3932726,3932729,3932731,4649087],
    "AFTER_EXTRA_TIME": [3875039,4481104,4791350],
    "AFTER_PENALTIES": [4176846,5642632,5667811],
}
EXPECTED_UNRESOLVED_IDS = {
    "ABANDONED": [3604442,3624628,3625852,3625959,3917036,3917109,4193691,4219326,4255362,4257277,4514030,4549850,4830760],
    "CANCELLED": [3932631,3932634,3932640,3932645,3932677,3932681],
    "POSTPONED": [3604331,4449361],
}

class FotMobSourceHistorySpecialResultSemanticsQualificationError(ValueError):
    """Raised when the frozen PR #110 receipt no longer revalidates."""


def _error(message: str) -> FotMobSourceHistorySpecialResultSemanticsQualificationError:
    return FotMobSourceHistorySpecialResultSemanticsQualificationError(message)


def _canonical(value: Any) -> bytes:
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("special-result qualification serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _load_exact_json(path: Path, expected_sha256: str, expected_size: int) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) != expected_size or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise _error(f"{path.name} identity changed")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error(f"{path.name} is not valid JSON") from exc
    if not isinstance(value, dict) or raw != _canonical(value):
        raise _error(f"{path.name} is not exact canonical JSON")
    return value


def _verify_upstream() -> tuple[dict[str, Any], dict[str, Any]]:
    protocol = pr109.build_fotmob_source_history_special_result_semantics_protocol()
    protocol_raw = pr109.canonical_fotmob_source_history_special_result_semantics_protocol_bytes(protocol)
    if (len(protocol_raw), hashlib.sha256(protocol_raw).hexdigest()) != (PR109_PROTOCOL_SIZE, PR109_PROTOCOL_SHA256):
        raise _error("PR109 protocol identity changed")
    if pr109.PROTOCOL_ID != "REVIEWED_FOTMOB_SOURCE_HISTORY_SPECIAL_RESULT_SEMANTICS_PROTOCOL_V1":
        raise _error("PR109 protocol id changed")
    if pr109.NEXT_REQUIRED_BOUNDARY != "EXECUTE_REVIEWED_FOTMOB_SOURCE_HISTORY_SPECIAL_RESULT_SEMANTICS_QUALIFICATION":
        raise _error("PR109 execution boundary changed")

    pr108_receipt = pr108.load_fotmob_primary_id_competition_mapping_qualification_receipt()
    pr108_raw = pr108.canonical_fotmob_primary_id_competition_mapping_qualification_receipt_bytes()
    if (len(pr108_raw), hashlib.sha256(pr108_raw).hexdigest()) != (PR108_RECEIPT_SIZE, PR108_RECEIPT_SHA256):
        raise _error("PR108 receipt identity changed")
    if pr108_receipt.get("mapping_qualification_proven") is not True or pr108_receipt.get("historical_coverage_proven") is not False:
        raise _error("PR108 mapping/history premise changed")

    pr105_receipt = _load_exact_json(pr108.PR105_RECEIPT_PATH, PR105_RECEIPT_SHA256, PR105_RECEIPT_SIZE)
    special = pr105_receipt.get("special_result_blockers")
    unresolved = pr105_receipt.get("unresolved_source_states")
    if not isinstance(special, dict) or not isinstance(unresolved, dict):
        raise _error("PR105 special/unresolved evidence missing")
    if (special.get("full_projection_sha256"), special.get("full_projection_size_bytes")) != (pr109.SPECIAL_PROJECTION_SHA256, pr109.SPECIAL_PROJECTION_SIZE):
        raise _error("PR105 special-result projection changed")
    if (unresolved.get("full_projection_sha256"), unresolved.get("full_projection_size_bytes")) != (pr109.UNRESOLVED_PROJECTION_SHA256, pr109.UNRESOLVED_PROJECTION_SIZE):
        raise _error("PR105 unresolved projection changed")
    return pr108_receipt, pr105_receipt


def _validate_class_records(receipt: dict[str, Any]) -> None:
    records = receipt.get("class_records")
    if not isinstance(records, list) or len(records) != 6 or any(not isinstance(item, dict) for item in records):
        raise _error("qualification must contain six reviewed class records")
    by_state = {item.get("state_id"): item for item in records}
    if set(by_state) != set(EXPECTED_CLASS_COUNTS):
        raise _error("reviewed state set changed")
    for state_id, expected in EXPECTED_CLASS_COUNTS.items():
        record = by_state[state_id]
        actual = (
            record.get("observed_unique_fixture_ids"), record.get("observed_date_fixture_occurrences"),
            record.get("observed_capture_rows"), record.get("status_ids"), record.get("transition_fixture_id_count"),
        )
        if actual != expected:
            raise _error(f"{state_id} evidence counts changed")
        if record.get("frozen_pr105_terminal_fixture_ids") != EXPECTED_TERMINAL_IDS.get(state_id, []):
            raise _error(f"{state_id} frozen terminal membership changed")
        if record.get("frozen_pr105_unresolved_fixture_ids") != EXPECTED_UNRESOLVED_IDS.get(state_id, []):
            raise _error(f"{state_id} frozen unresolved membership changed")
        if record.get("frozen_membership_match") is not True:
            raise _error(f"{state_id} membership must remain qualified")
        if record.get("history_disposition") != HISTORY_DISPOSITION or record.get("preservation_disposition") != PRESERVATION_DISPOSITION:
            raise _error(f"{state_id} disposition changed")
    penalty = by_state["AFTER_PENALTIES"]
    if penalty.get("penalty_occurrences_with_both_pen_scores") != 3 or penalty.get("penalty_occurrences_with_eliminated_team_id") != 3:
        raise _error("penalty score separation evidence changed")
    if by_state["ABANDONED"].get("nonzero_score_occurrence_count") != 15:
        raise _error("abandoned partial-score evidence changed")
    if by_state["CANCELLED"].get("nonzero_score_occurrence_count") != 9:
        raise _error("cancelled non-result score evidence changed")
    if by_state["POSTPONED"].get("nonzero_score_occurrence_count") != 0:
        raise _error("postponed score evidence changed")


def _validate_receipt(receipt: dict[str, Any], pr105_receipt: dict[str, Any]) -> None:
    if receipt.get("schema_version") != 1 or receipt.get("dataset_name") != "athena-fotmob-source-history-special-result-semantics-qualification-v1":
        raise _error("qualification receipt identity fields changed")
    if receipt.get("scope") != "IMMUTABLE_SPECIAL_RESULT_SEMANTICS_QUALIFICATION_RECEIPT_ONLY":
        raise _error("qualification scope changed")
    if receipt.get("repository_main_anchor") != REPOSITORY_MAIN_ANCHOR:
        raise _error("qualification main anchor changed")
    if receipt.get("protocol") != {
        "protocol_id": pr109.PROTOCOL_ID,
        "blob_sha": PR109_PROTOCOL_BLOB_SHA,
        "canonical_sha256": PR109_PROTOCOL_SHA256,
        "canonical_size_bytes": PR109_PROTOCOL_SIZE,
    }:
        raise _error("PR109 protocol ancestry changed")

    artifact = pr105_receipt.get("artifact")
    campaign = pr105_receipt.get("campaign")
    special = pr105_receipt.get("special_result_blockers")
    unresolved = pr105_receipt.get("unresolved_source_states")
    if not all(isinstance(item, dict) for item in (artifact, campaign, special, unresolved)):
        raise _error("PR105 evidence shape changed")
    expected_source = {
        "artifact_id": artifact.get("artifact_id"), "artifact_name": artifact.get("artifact_name"),
        "artifact_sha256": artifact.get("artifact_sha256"), "artifact_size_bytes": artifact.get("artifact_size_bytes"),
        "research_cache_tar_gz_sha256": artifact.get("research_cache_tar_gz_sha256"), "research_cache_tar_gz_size_bytes": artifact.get("research_cache_tar_gz_size_bytes"),
        "pr105_receipt_sha256": PR105_RECEIPT_SHA256, "pr105_receipt_size_bytes": PR105_RECEIPT_SIZE,
        "pr108_receipt_sha256": PR108_RECEIPT_SHA256, "pr108_receipt_size_bytes": PR108_RECEIPT_SIZE,
        "pr105_special_projection_sha256": special.get("full_projection_sha256"), "pr105_special_projection_size_bytes": special.get("full_projection_size_bytes"),
        "pr105_unresolved_projection_sha256": unresolved.get("full_projection_sha256"), "pr105_unresolved_projection_size_bytes": unresolved.get("full_projection_size_bytes"),
        "request_date_count": campaign.get("required_date_count"), "response_file_count": campaign.get("response_file_count"),
        "special_state_projection_sha256": SPECIAL_PROJECTION_SHA256, "special_state_projection_size_bytes": SPECIAL_PROJECTION_SIZE,
        "special_fixture_history_projection_sha256": HISTORY_PROJECTION_SHA256, "special_fixture_history_projection_size_bytes": HISTORY_PROJECTION_SIZE,
        "special_state_unique_fixture_id_count": 295, "special_state_date_fixture_occurrence_count": 304,
        "special_state_capture_observation_count": 608, "special_fixture_history_date_fixture_occurrence_count": 547,
    }
    if receipt.get("source_evidence") != expected_source:
        raise _error("source evidence ancestry or projection identity changed")

    if receipt.get("qualification_state") != QUALIFICATION_STATE:
        raise _error("qualification state changed")
    if receipt.get("special_result_semantics_execution_performed") is not True or receipt.get("special_result_semantics_qualified") is not True:
        raise _error("special-result semantics must remain executed and qualified")
    _validate_class_records(receipt)

    expected_checks = {
        "exact_six_reviewed_state_signatures_observed": True,
        "frozen_pr105_special_finished_membership_accounted": True,
        "frozen_pr105_unresolved_membership_accounted": True,
        "same_date_pair_count": 304,
        "same_date_pair_capture_count_mismatch_count": 0,
        "same_date_pair_semantic_or_relevant_field_conflict_count": 0,
        "unknown_variant_count_within_special_fixture_history": 0,
        "penalty_base_and_pen_score_fields_kept_separate": True,
        "nonresult_score_scalars_not_promoted": True,
        "special_states_excluded_from_ordinary_regulation_time_model_history": True,
    }
    if receipt.get("checks") != expected_checks:
        raise _error("special-result qualification checks changed")
    chronology = receipt.get("chronology_handoff")
    if not isinstance(chronology, dict) or chronology.get("rearranged_fixture_id_count") != 250:
        raise _error("chronology handoff count changed")
    if chronology.get("chronology_resolved") is not False or chronology.get("collapsed_to_final_observation") is not False:
        raise _error("chronology must remain unresolved and uncollapsed")
    if chronology.get("transition_summary") != EXPECTED_TRANSITIONS:
        raise _error("chronology transition summary changed")
    if chronology.get("duplicate_terminal_awarded_fixture") != {"fixture_id": 3932603, "request_dates": ["20230220", "20230305"]}:
        raise _error("duplicate awarded chronology evidence changed")

    for key in ("source_history_mutation_performed", "competition_registry_mutation_performed", "source_capability_registry_mutation_performed", "historical_coverage_proven"):
        if receipt.get(key) is not False:
            raise _error(f"{key} must remain exact False")
    if receipt.get("resolved_blocker") != RESOLVED_BLOCKER:
        raise _error("resolved blocker changed")
    if tuple(receipt.get("remaining_blockers", ())) != EXPECTED_REMAINING_BLOCKERS:
        raise _error("remaining blocker set changed")
    if receipt.get("next_required_boundary") != NEXT_REQUIRED_BOUNDARY:
        raise _error("next reviewed boundary changed")
    safety = receipt.get("safety")
    if not isinstance(safety, dict) or not safety or any(type(value) is not bool or value is not False for value in safety.values()):
        raise _error("all downstream safety flags must remain exact False")


def load_fotmob_source_history_special_result_semantics_qualification_receipt() -> dict[str, Any]:
    """Load and fully validate the canonical PR #110 qualification receipt."""
    _, pr105_receipt = _verify_upstream()
    receipt = _load_exact_json(RECEIPT_PATH, RECEIPT_SHA256, RECEIPT_SIZE)
    _validate_receipt(receipt, pr105_receipt)
    return receipt


def canonical_fotmob_source_history_special_result_semantics_qualification_receipt_bytes() -> bytes:
    receipt = load_fotmob_source_history_special_result_semantics_qualification_receipt()
    raw = _canonical(receipt)
    if len(raw) != RECEIPT_SIZE or hashlib.sha256(raw).hexdigest() != RECEIPT_SHA256:
        raise _error("qualification receipt canonical identity changed")
    return raw
