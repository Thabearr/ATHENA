"""Validate the exact PR #123 PR69 source-local time-basis qualification receipt.

PR #123 executes the result-free PR #122 protocol and fails closed because no
reviewed primary football-data.co.uk time-basis evidence bundle with preserved
raw bytes, hash, and historical effective scope — and no formal operational-
invariance proof bundle — is available under that protocol. A current official
notes.txt page was discovered, but is recorded only as a non-admissible
candidate because this execution does not possess a reviewed raw-byte capture
and proven historical effective scope. No timezone is inferred and no PR #80,
model, probability, pricing, selection, production, or betting authority is
created.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import domain.fotmob_source_history_elo_initialization_boundary_qualification as pr114
import domain.pr69_source_local_time_basis_resolution_protocol as pr122


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = (
    REPOSITORY_ROOT
    / "artifacts"
    / "research-manifests"
    / "pr69-source-local-time-basis-resolution-qualification-v1.json"
)
RECEIPT_SHA256 = "a3736753862781efc9d8ce6c15aa814185b73ed14fea82c4e8ebaa10a3ab656c"
RECEIPT_SIZE = 12_025
REPOSITORY_MAIN_ANCHOR = "1b57d9ae64d7179734571dbf4691da65a163739a"
PR122_PROTOCOL_BLOB_SHA = "712ce12157ade725a60b24c4557600fc7b06e504"
QUALIFICATION_STATE = "EXECUTED_FAIL_CLOSED_NO_ADMISSIBLE_PRIMARY_TIME_BASIS_EVIDENCE"
QUALIFICATION_STATUS = "BLOCKED_NO_ADMISSIBLE_PRIMARY_TIME_BASIS_EVIDENCE"
SUPERSEDED_BLOCKER = "BLOCKED_PR69_REFERENCE_TIME_BASIS_UNRESOLVED"
NEXT_REQUIRED_BOUNDARY = (
    "PRE_REGISTER_REVIEWED_PR69_PRIMARY_TIME_BASIS_EVIDENCE_ACQUISITION_PROTOCOL"
)
DISCOVERY_URL = "https://www.football-data.co.uk/notes.txt"
DISCOVERY_CAPTURED_AT_UTC = "2026-08-16T05:26:00Z"
DISCOVERY_TIME_FIELD_DESCRIPTION = "Time = Time of match kick off"
PR69_SOURCE_CORPUS_SHA256 = "c273b4bff2b611e95248133340ff84803ce238814d5dfa7ded5f39fd3d6e25a0"
PR69_CANONICAL_REPLAY_SHA256 = "b44166b9543a8f436e62a644efc5316ad12fcc260a4c2c5908ad112928bedfe3"
PR69_CANONICAL_REPLAY_SIZE = 39_952_730
PR69_SOURCE_FILE_SHA256_MANIFEST_SHA256 = (
    "4d04a22f6bd29c0f56c37c8f2e8301f2c90a02516e04ac677d3b6c3d7656501a"
)

SAFETY_KEYS = frozenset(
    {
        "bet_authorized",
        "calibration_for_production_authorized",
        "expected_goals_production_authorized",
        "expected_goals_transform_approved",
        "market_activation_authorized",
        "model_training_authorized",
        "pr69_source_local_time_basis_resolved",
        "pr80_constructor_input_authorized",
        "pricing_authorized",
        "probability_adjustment_authorized",
        "probability_inference_authorized",
        "production_approval_authorized",
        "score_matrix_authorized",
        "selection_authorized",
        "source_local_time_semantic_equivalence_qualified",
        "successor_candidate_approved",
        "successor_live_inputs_qualified",
    }
)


class PR69SourceLocalTimeBasisResolutionQualificationError(ValueError):
    """Raised when the exact PR #123 qualification no longer revalidates."""


def _error(message: str) -> PR69SourceLocalTimeBasisResolutionQualificationError:
    return PR69SourceLocalTimeBasisResolutionQualificationError(message)


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
        raise _error("PR123 receipt serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def _expected_source_file_keys() -> list[str]:
    return [
        f"{season}:{league}"
        for season in pr122.SEASONS
        for league in pr122.MODEL_LEAGUE_CODES
    ]


def _expected_source_file_sha256() -> dict[str, str]:
    receipt = pr114.load_fotmob_source_history_elo_initialization_boundary_qualification_receipt()
    if (
        pr114.RECEIPT_SHA256 != pr122.PR114_RECEIPT_SHA256
        or pr114.RECEIPT_SIZE != pr122.PR114_RECEIPT_SIZE
    ):
        raise _error("PR114 receipt identity changed")
    hashes = receipt.get("pr69_rebuild", {}).get("source_file_sha256")
    if not isinstance(hashes, dict):
        raise _error("PR114 per-file PR69 source hashes are missing")
    expected_keys = [key.replace(":", "/") for key in _expected_source_file_keys()]
    if sorted(hashes) != sorted(expected_keys) or len(hashes) != 66:
        raise _error("PR114 per-file PR69 source inventory changed")
    normalized: dict[str, str] = {}
    for key in expected_keys:
        value = hashes.get(key)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(ch not in "0123456789abcdef" for ch in value)
        ):
            raise _error("PR114 per-file PR69 source hash changed")
        normalized[key] = value
    manifest_raw = _canonical(normalized)
    if hashlib.sha256(manifest_raw).hexdigest() != PR69_SOURCE_FILE_SHA256_MANIFEST_SHA256:
        raise _error("PR114 per-file PR69 source hash manifest identity changed")
    return normalized


def _verify_protocol() -> pr122.PR69SourceLocalTimeBasisResolutionProtocol:
    protocol = pr122.build_pr69_source_local_time_basis_resolution_protocol()
    raw = pr122.canonical_pr69_source_local_time_basis_resolution_protocol_bytes(protocol)
    if (hashlib.sha256(raw).hexdigest(), len(raw)) != (
        pr122.PROTOCOL_SHA256,
        pr122.PROTOCOL_SIZE,
    ):
        raise _error("PR122 protocol identity changed")
    if (
        pr122.PROTOCOL_SHA256
        != "d3bf061ade81bb1b60f38e98f5fa3c8c21ba5bf6652879f2cc19e151b53aee4a"
        or pr122.PROTOCOL_SIZE != 6_983
    ):
        raise _error("PR122 frozen canonical identity changed")
    if _git_blob_sha(Path(pr122.__file__)) != PR122_PROTOCOL_BLOB_SHA:
        raise _error("PR122 protocol implementation blob changed")
    if pr122.NEXT_REQUIRED_BOUNDARY != (
        "EXECUTE_REVIEWED_PR69_SOURCE_LOCAL_TIME_BASIS_RESOLUTION_QUALIFICATION"
    ):
        raise _error("PR122 next boundary changed")
    if QUALIFICATION_STATUS not in protocol.qualification_status_vocabulary:
        raise _error("PR123 blocker is no longer admitted by PR122")
    if protocol.execution_output_contract != {
        "evidence_inventory_required": True,
        "primary_evidence_conflict_table_required": True,
        "row_coverage_accounting_required": True,
        "resolution_rule_or_invariance_proof_required_for_positive_status": True,
        "fotmob_equivalence_assessment_performed": False,
        "pr80_constructor_input_authorized": False,
        "next_required_boundary": pr122.NEXT_REQUIRED_BOUNDARY,
    }:
        raise _error("PR122 execution-output contract changed")
    return protocol


def _validate(receipt: dict[str, Any]) -> None:
    protocol = _verify_protocol()

    if receipt.get("schema_version") != 1:
        raise _error("PR123 schema version changed")
    if receipt.get("dataset_name") != (
        "athena-pr69-source-local-time-basis-resolution-qualification-v1"
    ):
        raise _error("PR123 dataset identity changed")
    if receipt.get("qualification_scope") != (
        "EXACT_FROZEN_PR122_PROTOCOL_EXECUTION_ONLY_NO_TIMEZONE_INFERENCE_WITHOUT_ADMISSIBLE_EVIDENCE"
    ):
        raise _error("PR123 qualification scope changed")
    if receipt.get("qualification_state") != QUALIFICATION_STATE:
        raise _error("PR123 qualification state changed")
    if receipt.get("repository_main_anchor") != REPOSITORY_MAIN_ANCHOR:
        raise _error("PR123 repository main anchor changed")

    if receipt.get("protocol") != {
        "protocol_id": pr122.PROTOCOL_ID,
        "blob_sha": PR122_PROTOCOL_BLOB_SHA,
        "canonical_sha256": pr122.PROTOCOL_SHA256,
        "canonical_size_bytes": pr122.PROTOCOL_SIZE,
    }:
        raise _error("PR122 protocol ancestry changed")

    if receipt.get("frozen_scope") != {
        "source": "football_data_uk_csv",
        "source_local_timezone_state": "SOURCE_LOCAL_TIMEZONE_UNRESOLVED",
        "source_file_count": 66,
        "source_total_bytes": 10_006_877,
        "source_fixture_count": 21_226,
        "seasons": list(pr122.SEASONS),
        "model_league_codes": list(pr122.MODEL_LEAGUE_CODES),
        "full_athena_competition_universe_claimed": False,
    }:
        raise _error("PR123 frozen PR69 scope changed")

    if receipt.get("execution_inputs") != {
        "exact_pr122_protocol_supplied": True,
        "exact_pr69_source_corpus_ancestry_revalidated": True,
        "provenanced_primary_time_basis_evidence_bundle_supplied": False,
        "formal_operational_invariance_proof_bundle_supplied": False,
        "secondary_source_authority_used": False,
        "fotmob_candidate_clock_used_as_reference_evidence": False,
        "source_bytes_mutated": False,
    }:
        raise _error("PR123 execution-input contract changed")

    inventory = receipt.get("evidence_inventory")
    if not isinstance(inventory, dict):
        raise _error("PR123 evidence inventory missing")
    expected_keys = _expected_source_file_keys()
    if inventory.get("pr69_source_file_keys") != expected_keys:
        raise _error("PR123 66-file source inventory changed")
    if inventory.get("pr69_source_file_key_count") != 66 or len(expected_keys) != 66:
        raise _error("PR123 source-file inventory count changed")
    expected_hashes = _expected_source_file_sha256()
    if inventory.get("pr69_source_file_sha256") != expected_hashes:
        raise _error("PR123 exact per-file PR69 source hashes changed")
    if inventory.get("pr69_source_file_sha256_manifest_sha256") != (
        PR69_SOURCE_FILE_SHA256_MANIFEST_SHA256
    ):
        raise _error("PR123 per-file source-hash manifest identity changed")
    if inventory.get("pr69_source_bytes_identity") != {
        "source_file_count": 66,
        "source_total_bytes": 10_006_877,
        "source_fixture_count": 21_226,
        "source_corpus_sha256": PR69_SOURCE_CORPUS_SHA256,
        "canonical_replay_sha256": PR69_CANONICAL_REPLAY_SHA256,
        "canonical_replay_size_bytes": PR69_CANONICAL_REPLAY_SIZE,
    }:
        raise _error("PR123 source-byte ancestry inventory changed")
    if inventory.get("raw_date_time_text_preserved_by_frozen_source_bytes") is not True:
        raise _error("PR123 must preserve frozen source date/time bytes")
    if inventory.get("raw_date_time_text_reinspection_performed") is not False:
        raise _error("PR123 must not claim row reinspection after the evidence gate blocked")
    if inventory.get("raw_date_time_text_reinspection_status") != (
        "NOT_REACHED_BECAUSE_REFERENCE_EVIDENCE_GATE_BLOCKED"
    ):
        raise _error("PR123 raw date/time reinspection status changed")
    if inventory.get("admissible_primary_time_basis_records") != []:
        raise _error("PR123 may not invent admissible primary evidence")
    if inventory.get("formal_operational_invariance_proof_records") != []:
        raise _error("PR123 may not invent an invariance proof bundle")
    if inventory.get("non_admissible_primary_discovery_candidates") != [{
        "url": DISCOVERY_URL,
        "discovered_at_utc": DISCOVERY_CAPTURED_AT_UTC,
        "primary_origin": "football-data.co.uk",
        "observed_time_field_description": DISCOVERY_TIME_FIELD_DESCRIPTION,
        "raw_bytes_preserved": False,
        "raw_sha256": None,
        "historical_effective_scope_proven": False,
        "admissible_under_pr122": False,
        "rejection_reason": (
            "RAW_BYTES_HASH_AND_HISTORICAL_EFFECTIVE_SCOPE_NOT_PRESERVED_IN_A_REVIEWED_EVIDENCE_BUNDLE"
        ),
    }]:
        raise _error("PR123 non-admissible discovery inventory changed")

    if receipt.get("primary_evidence_conflict_table") != []:
        raise _error("PR123 primary evidence conflict table changed")

    if receipt.get("row_coverage_accounting") != {
        "total_pr69_fixture_rows": 21_226,
        "direct_reference_rule_mapped_rows": 0,
        "formal_invariance_proven_rows": 0,
        "unresolved_rows": 21_226,
        "row_level_time_basis_assessment": (
            "NOT_REACHED_NO_ADMISSIBLE_REFERENCE_BASIS_OR_FORMAL_INVARIANCE_PROOF"
        ),
    }:
        raise _error("PR123 row-coverage accounting changed")

    if receipt.get("evidence_assessment") != {
        "admissible_primary_time_basis_evidence_record_count": 0,
        "non_admissible_primary_discovery_candidate_count": 1,
        "primary_evidence_conflict_count": 0,
        "direct_reference_rule_available": False,
        "direct_reference_rule_shape": None,
        "direct_reference_rule_effective_scope_proven": False,
        "all_relevant_pr69_rows_mappable_under_direct_rule": False,
        "formal_invariance_route_available": False,
        "formal_invariance_assumptions_proven": False,
    }:
        raise _error("PR123 evidence assessment changed")

    expected_gates = {
        "EXACT_PR122_PROTOCOL_AND_ANCESTRY_REVALIDATION": "PASSED",
        "EVIDENCE_INVENTORY_AND_ROW_ACCOUNTING": "PASSED",
        "ADMISSIBLE_PRIMARY_TIME_BASIS_EVIDENCE_AVAILABLE": QUALIFICATION_STATUS,
        "DIRECT_REFERENCE_RULE_DERIVATION": "NOT_REACHED",
        "DIRECT_REFERENCE_EFFECTIVE_PERIOD_AND_VERSION_SCOPE": "NOT_REACHED",
        "ALL_RELEVANT_PR69_ROWS_MAPPED": "NOT_REACHED",
        "FORMAL_OPERATIONAL_INVARIANCE_ROUTE": "NOT_REACHED",
        "STRICT_PRIOR_MEMBERSHIP_INVARIANCE": "NOT_REACHED",
        "FORM_ORDERING_AND_TIEBREAK_INVARIANCE": "NOT_REACHED",
        "ELO_ORDERING_AND_TIEBREAK_INVARIANCE": "NOT_REACHED",
        "MOST_RECENT_PRIOR_FIXTURE_INVARIANCE": "NOT_REACHED",
        "INTEGER_DATETIME_DELTA_DAYS_INVARIANCE": "NOT_REACHED",
        "HOME_MINUS_AWAY_REST_DIFFERENCE_INVARIANCE": "NOT_REACHED",
        "FATIGUE_BUCKET_INVARIANCE": "NOT_REACHED",
        "FOTMOB_EUROPE_OSLO_COMPARISON": "NOT_REACHED",
    }
    if receipt.get("gate_results") != expected_gates:
        raise _error("PR123 gate results changed")

    if receipt.get("interpretation") != {
        "qualification_status": QUALIFICATION_STATUS,
        "pr69_source_local_time_basis_resolved": False,
        "named_timezone_inferred": False,
        "fixed_offset_inferred": False,
        "source_defined_local_civil_rule_inferred": False,
        "result_fit_or_majority_vote_used": False,
        "fotmob_equivalence_assessment_performed": False,
        "fotmob_europe_oslo_equivalence_proven": False,
        "fotmob_europe_oslo_mismatch_proven": False,
        "pr80_time_sensitive_row_checks_performed": False,
        "blocked_reason": (
            "NO_REVIEWED_PRIMARY_TIME_BASIS_BUNDLE_WITH_RAW_BYTES_HASH_AND_PROVEN_EFFECTIVE_SCOPE_OR_FORMAL_INVARIANCE_PROOF_IS_AVAILABLE_UNDER_PR122"
        ),
    }:
        raise _error("PR123 interpretation changed")

    if receipt.get("superseded_blocker") != SUPERSEDED_BLOCKER:
        raise _error("PR123 blocker ancestry changed")
    if receipt.get("remaining_blockers") != [QUALIFICATION_STATUS]:
        raise _error("PR123 remaining blocker set changed")
    if receipt.get("next_required_boundary") != NEXT_REQUIRED_BOUNDARY:
        raise _error("PR123 next boundary changed")

    safety = receipt.get("safety")
    if not isinstance(safety, dict) or set(safety) != SAFETY_KEYS:
        raise _error("PR123 safety keys changed")
    if any(type(value) is not bool or value is not False for value in safety.values()):
        raise _error("all PR123 safety values must remain exact False")

    if protocol.frozen_pr69_scope["source_file_count"] != 66:
        raise _error("PR122 source-file count changed")
    if protocol.frozen_pr69_scope["source_fixture_count"] != 21_226:
        raise _error("PR122 source-fixture count changed")


def load_pr69_source_local_time_basis_resolution_qualification_receipt() -> dict[str, Any]:
    """Load and fully validate the exact checked-in PR #123 receipt."""
    try:
        raw = RECEIPT_PATH.read_bytes()
    except OSError as exc:
        raise _error("PR123 receipt cannot be read") from exc
    if hashlib.sha256(raw).hexdigest() != RECEIPT_SHA256 or len(raw) != RECEIPT_SIZE:
        raise _error("PR123 receipt identity changed")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error("PR123 receipt is not valid JSON") from exc
    if not isinstance(value, dict) or raw != _canonical(value):
        raise _error("PR123 receipt is not exact canonical JSON")
    _validate(value)
    return value


def canonical_pr69_source_local_time_basis_resolution_qualification_receipt_bytes() -> bytes:
    """Return the exact canonical checked-in PR #123 receipt bytes."""
    value = load_pr69_source_local_time_basis_resolution_qualification_receipt()
    raw = _canonical(value)
    if hashlib.sha256(raw).hexdigest() != RECEIPT_SHA256 or len(raw) != RECEIPT_SIZE:
        raise _error("PR123 canonical receipt identity changed")
    return raw


__all__ = [
    "DISCOVERY_CAPTURED_AT_UTC",
    "DISCOVERY_TIME_FIELD_DESCRIPTION",
    "DISCOVERY_URL",
    "NEXT_REQUIRED_BOUNDARY",
    "PR122_PROTOCOL_BLOB_SHA",
    "PR69_SOURCE_FILE_SHA256_MANIFEST_SHA256",
    "QUALIFICATION_STATE",
    "QUALIFICATION_STATUS",
    "RECEIPT_PATH",
    "RECEIPT_SHA256",
    "RECEIPT_SIZE",
    "REPOSITORY_MAIN_ANCHOR",
    "SAFETY_KEYS",
    "SUPERSEDED_BLOCKER",
    "PR69SourceLocalTimeBasisResolutionQualificationError",
    "canonical_pr69_source_local_time_basis_resolution_qualification_receipt_bytes",
    "load_pr69_source_local_time_basis_resolution_qualification_receipt",
]
