"""Validate the exact PR #121 source-local time semantic-equivalence receipt.

PR #121 executes the result-free PR #120 protocol and fails closed at its first
semantic gate because the frozen PR #69 reference source-local time basis remains
unresolved and no admissible reference-basis or formal invariance proof bundle is
supplied. It does not infer a timezone from results and authorizes no PR #80,
model, probability, pricing, selection, production, or betting path.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import domain.fotmob_pr80_source_local_time_semantic_equivalence_protocol as pr120


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = (
    REPOSITORY_ROOT
    / "artifacts"
    / "research-manifests"
    / "fotmob-pr80-source-local-time-semantic-equivalence-qualification-v1.json"
)
RECEIPT_SHA256 = "8d057e96504a83237b719b3a465e29b7df74e2b6c3630fc1d97e8a2a7bdfb5fb"
RECEIPT_SIZE = 3_599
REPOSITORY_MAIN_ANCHOR = "cadd32bb3d5241afbbb0b9c36326b6ddad820400"
PR120_PROTOCOL_BLOB_SHA = "e07616e99c0beaf2a95bcaec96d02616b21c378f"
QUALIFICATION_STATE = "EXECUTED_FAIL_CLOSED_PR69_REFERENCE_TIME_BASIS_UNRESOLVED"
QUALIFICATION_STATUS = "BLOCKED_PR69_REFERENCE_TIME_BASIS_UNRESOLVED"
NEXT_REQUIRED_BOUNDARY = "PRE_REGISTER_REVIEWED_PR69_SOURCE_LOCAL_TIME_BASIS_RESOLUTION_PROTOCOL"

SAFETY_KEYS = frozenset(
    {
        "bet_authorized",
        "calibration_for_production_authorized",
        "expected_goals_production_authorized",
        "expected_goals_transform_approved",
        "market_activation_authorized",
        "model_training_authorized",
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


class FotMobPR80SourceLocalTimeSemanticEquivalenceQualificationError(ValueError):
    """Raised when the exact PR #121 qualification no longer revalidates."""


def _error(message: str) -> FotMobPR80SourceLocalTimeSemanticEquivalenceQualificationError:
    return FotMobPR80SourceLocalTimeSemanticEquivalenceQualificationError(message)


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
        raise _error("PR121 receipt serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def _verify_protocol() -> pr120.FotMobPR80SourceLocalTimeSemanticEquivalenceProtocol:
    protocol = pr120.build_fotmob_pr80_source_local_time_semantic_equivalence_protocol()
    raw = pr120.canonical_fotmob_pr80_source_local_time_semantic_equivalence_protocol_bytes(protocol)
    if (hashlib.sha256(raw).hexdigest(), len(raw)) != (
        pr120.PROTOCOL_SHA256,
        pr120.PROTOCOL_SIZE,
    ):
        raise _error("PR120 protocol identity changed")
    if _git_blob_sha(Path(pr120.__file__)) != PR120_PROTOCOL_BLOB_SHA:
        raise _error("PR120 protocol implementation blob changed")
    if pr120.NEXT_REQUIRED_BOUNDARY != (
        "EXECUTE_REVIEWED_FOTMOB_PR80_SOURCE_LOCAL_TIME_SEMANTIC_EQUIVALENCE_QUALIFICATION"
    ):
        raise _error("PR120 next boundary changed")
    if QUALIFICATION_STATUS not in protocol.qualification_status_vocabulary:
        raise _error("PR121 blocker status is no longer admitted by PR120")
    return protocol


def _validate(receipt: dict[str, Any]) -> None:
    protocol = _verify_protocol()
    if receipt.get("schema_version") != 1:
        raise _error("PR121 schema version changed")
    if receipt.get("dataset_name") != (
        "athena-fotmob-pr80-source-local-time-semantic-equivalence-qualification-v1"
    ):
        raise _error("PR121 dataset identity changed")
    if receipt.get("qualification_scope") != (
        "EXACT_FROZEN_PR120_PROTOCOL_EXECUTION_ONLY_NO_RESULT_DRIVEN_TIME_BASIS_INFERENCE"
    ):
        raise _error("PR121 qualification scope changed")
    if receipt.get("qualification_state") != QUALIFICATION_STATE:
        raise _error("PR121 qualification state changed")
    if receipt.get("repository_main_anchor") != REPOSITORY_MAIN_ANCHOR:
        raise _error("PR121 repository main anchor changed")

    if receipt.get("protocol") != {
        "protocol_id": pr120.PROTOCOL_ID,
        "blob_sha": PR120_PROTOCOL_BLOB_SHA,
        "canonical_sha256": pr120.PROTOCOL_SHA256,
        "canonical_size_bytes": pr120.PROTOCOL_SIZE,
    }:
        raise _error("PR120 protocol ancestry changed")

    if receipt.get("frozen_scope") != {
        "source_namespace": pr120.SOURCE_NAMESPACE,
        "history_row_count": pr120.FROZEN_HISTORY_ROW_COUNT,
        "historical_request_date_end": pr120.HISTORICAL_REQUEST_DATE_END,
        "model_league_codes": list(pr120.MODEL_LEAGUE_CODES),
        "full_athena_competition_universe_claimed": False,
    }:
        raise _error("PR121 frozen scope changed")

    if receipt.get("execution_inputs") != {
        "exact_pr120_protocol_supplied": True,
        "admissible_reference_basis_evidence_bundle_supplied": False,
        "formal_source_independent_invariance_proof_bundle_supplied": False,
        "campaign_reexecution_required_before_reference_gate": False,
        "campaign_reexecution_performed": False,
    }:
        raise _error("PR121 execution-input contract changed")

    reference = receipt.get("reference_gate")
    if reference != {
        "pr69_source": protocol.reference_semantics["pr69_source"],
        "pr69_source_local_timezone_state": "SOURCE_LOCAL_TIMEZONE_UNRESOLVED",
        "pr69_local_kickoff_type": protocol.reference_semantics["pr69_local_kickoff_type"],
        "pr80_source_local_time_basis": protocol.reference_semantics["pr80_source_local_time_basis"],
        "fotmob_candidate_time_basis": protocol.candidate_semantics["source_display_time_basis"],
        "fotmob_candidate_semantic_equivalence_before_execution": "UNPROVEN",
        "reference_basis_resolved": False,
        "source_independent_invariance_proven": False,
        "qualification_status": QUALIFICATION_STATUS,
    }:
        raise _error("PR121 reference gate changed")

    expected_gates = {
        "EXACT_ANCESTRY_REVALIDATION": "PASSED",
        "PR69_REFERENCE_TIME_BASIS_RESOLUTION_OR_SOURCE_INDEPENDENT_INVARIANCE": QUALIFICATION_STATUS,
        "FOTMOB_EUROPE_OSLO_ADMISSIBILITY": "NOT_REACHED",
        "STRICT_PRIOR_MEMBERSHIP_EQUIVALENCE": "NOT_REACHED",
        "FORM_ORDERING_EQUIVALENCE": "NOT_REACHED",
        "ELO_ORDERING_EQUIVALENCE": "NOT_REACHED",
        "MOST_RECENT_PRIOR_FIXTURE_EQUIVALENCE": "NOT_REACHED",
        "DATETIME_DELTA_DAYS_INTEGER_COMPONENT_EQUIVALENCE": "NOT_REACHED",
        "REST_DIFFERENCE_AND_FATIGUE_BUCKET_EQUIVALENCE": "NOT_REACHED",
        "ZERO_UNRESOLVED_TEMPORAL_AMBIGUITY": "NOT_REACHED",
    }
    if receipt.get("gate_results") != expected_gates:
        raise _error("PR121 gate results changed")

    if receipt.get("interpretation") != {
        "europe_oslo_mismatch_proven": False,
        "europe_oslo_equivalence_proven": False,
        "blocked_reason": (
            "NO_ADMISSIBLE_REFERENCE_BASIS_OR_FORMAL_INVARIANCE_PROOF_WAS_SUPPLIED_TO_THE_FROZEN_EXECUTION"
        ),
        "row_level_time_operation_checks_skipped_reason": (
            "PR120_REQUIRES_REFERENCE_BASIS_RESOLUTION_OR_FORMAL_INVARIANCE_FIRST"
        ),
        "result_driven_timezone_inference_performed": False,
        "cross_source_fixture_or_team_identity_inference_performed": False,
    }:
        raise _error("PR121 interpretation changed")

    if receipt.get("remaining_blockers") != [QUALIFICATION_STATUS]:
        raise _error("PR121 remaining blockers changed")
    if receipt.get("next_required_boundary") != NEXT_REQUIRED_BOUNDARY:
        raise _error("PR121 next boundary changed")

    safety = receipt.get("safety")
    if not isinstance(safety, dict) or set(safety) != SAFETY_KEYS:
        raise _error("PR121 safety keys changed")
    if any(type(value) is not bool or value is not False for value in safety.values()):
        raise _error("all PR121 safety values must remain exact False")


def load_fotmob_pr80_source_local_time_semantic_equivalence_qualification_receipt() -> dict[str, Any]:
    """Load and validate the exact checked-in PR #121 receipt."""
    try:
        raw = RECEIPT_PATH.read_bytes()
    except OSError as exc:
        raise _error("PR121 receipt cannot be read") from exc
    if hashlib.sha256(raw).hexdigest() != RECEIPT_SHA256 or len(raw) != RECEIPT_SIZE:
        raise _error("PR121 receipt identity changed")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error("PR121 receipt is not valid JSON") from exc
    if not isinstance(value, dict) or raw != _canonical(value):
        raise _error("PR121 receipt is not exact canonical JSON")
    _validate(value)
    return value


def canonical_fotmob_pr80_source_local_time_semantic_equivalence_qualification_receipt_bytes() -> bytes:
    value = load_fotmob_pr80_source_local_time_semantic_equivalence_qualification_receipt()
    return _canonical(value)


__all__ = [
    "NEXT_REQUIRED_BOUNDARY",
    "PR120_PROTOCOL_BLOB_SHA",
    "QUALIFICATION_STATE",
    "QUALIFICATION_STATUS",
    "RECEIPT_PATH",
    "RECEIPT_SHA256",
    "RECEIPT_SIZE",
    "REPOSITORY_MAIN_ANCHOR",
    "SAFETY_KEYS",
    "FotMobPR80SourceLocalTimeSemanticEquivalenceQualificationError",
    "canonical_fotmob_pr80_source_local_time_semantic_equivalence_qualification_receipt_bytes",
    "load_fotmob_pr80_source_local_time_semantic_equivalence_qualification_receipt",
]
