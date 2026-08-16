#!/usr/bin/env python3
"""Execute the frozen PR #120 source-local time semantic-equivalence protocol."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import domain.fotmob_pr80_source_local_time_semantic_equivalence_protocol as pr120


REPOSITORY_MAIN_ANCHOR = "cadd32bb3d5241afbbb0b9c36326b6ddad820400"
PR120_PROTOCOL_BLOB_SHA = "e07616e99c0beaf2a95bcaec96d02616b21c378f"
EXPECTED_RECEIPT_SHA256 = "8d057e96504a83237b719b3a465e29b7df74e2b6c3630fc1d97e8a2a7bdfb5fb"
EXPECTED_RECEIPT_SIZE = 3_599
QUALIFICATION_STATUS = "BLOCKED_PR69_REFERENCE_TIME_BASIS_UNRESOLVED"
NEXT_REQUIRED_BOUNDARY = "PRE_REGISTER_REVIEWED_PR69_SOURCE_LOCAL_TIME_BASIS_RESOLUTION_PROTOCOL"

SAFETY_KEYS = (
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
)


class QualificationError(RuntimeError):
    """Raised when the exact PR #121 execution cannot be reproduced."""


def fail(message: str) -> None:
    raise QualificationError(message)


def canonical(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def verify_protocol() -> pr120.FotMobPR80SourceLocalTimeSemanticEquivalenceProtocol:
    protocol = pr120.build_fotmob_pr80_source_local_time_semantic_equivalence_protocol()
    raw = pr120.canonical_fotmob_pr80_source_local_time_semantic_equivalence_protocol_bytes(protocol)
    if (hashlib.sha256(raw).hexdigest(), len(raw)) != (
        pr120.PROTOCOL_SHA256,
        pr120.PROTOCOL_SIZE,
    ):
        fail("PR120 protocol identity changed")
    if git_blob_sha(Path(pr120.__file__)) != PR120_PROTOCOL_BLOB_SHA:
        fail("PR120 protocol implementation blob changed")
    if protocol.next_required_boundary != (
        "EXECUTE_REVIEWED_FOTMOB_PR80_SOURCE_LOCAL_TIME_SEMANTIC_EQUIVALENCE_QUALIFICATION"
    ):
        fail("PR120 next boundary changed")
    if QUALIFICATION_STATUS not in protocol.qualification_status_vocabulary:
        fail("PR121 blocker status is not admitted by PR120")
    return protocol


def build_receipt() -> dict[str, Any]:
    protocol = verify_protocol()

    # PR120 requires this reference gate before any row-level time-operation
    # comparison. This execution intentionally supplies neither an admissible
    # reference-basis evidence bundle nor a formal source-independent invariance
    # proof. Therefore execution must stop at the frozen fail-closed status.
    if protocol.reference_semantics["pr69_source_local_timezone"] != (
        "SOURCE_LOCAL_TIMEZONE_UNRESOLVED"
    ):
        fail("PR69 reference time basis no longer matches the frozen unresolved state")
    if protocol.candidate_semantics["pr119_source_local_semantic_equivalence"] != "UNPROVEN":
        fail("PR119 candidate equivalence is no longer the frozen unproven state")

    return {
        "schema_version": 1,
        "dataset_name": "athena-fotmob-pr80-source-local-time-semantic-equivalence-qualification-v1",
        "qualification_scope": (
            "EXACT_FROZEN_PR120_PROTOCOL_EXECUTION_ONLY_NO_RESULT_DRIVEN_TIME_BASIS_INFERENCE"
        ),
        "qualification_state": "EXECUTED_FAIL_CLOSED_PR69_REFERENCE_TIME_BASIS_UNRESOLVED",
        "repository_main_anchor": REPOSITORY_MAIN_ANCHOR,
        "protocol": {
            "protocol_id": pr120.PROTOCOL_ID,
            "blob_sha": PR120_PROTOCOL_BLOB_SHA,
            "canonical_sha256": pr120.PROTOCOL_SHA256,
            "canonical_size_bytes": pr120.PROTOCOL_SIZE,
        },
        "frozen_scope": {
            "source_namespace": pr120.SOURCE_NAMESPACE,
            "history_row_count": pr120.FROZEN_HISTORY_ROW_COUNT,
            "historical_request_date_end": pr120.HISTORICAL_REQUEST_DATE_END,
            "model_league_codes": list(pr120.MODEL_LEAGUE_CODES),
            "full_athena_competition_universe_claimed": False,
        },
        "execution_inputs": {
            "exact_pr120_protocol_supplied": True,
            "admissible_reference_basis_evidence_bundle_supplied": False,
            "formal_source_independent_invariance_proof_bundle_supplied": False,
            "campaign_reexecution_required_before_reference_gate": False,
            "campaign_reexecution_performed": False,
        },
        "reference_gate": {
            "pr69_source": protocol.reference_semantics["pr69_source"],
            "pr69_source_local_timezone_state": protocol.reference_semantics[
                "pr69_source_local_timezone"
            ],
            "pr69_local_kickoff_type": protocol.reference_semantics[
                "pr69_local_kickoff_type"
            ],
            "pr80_source_local_time_basis": protocol.reference_semantics[
                "pr80_source_local_time_basis"
            ],
            "fotmob_candidate_time_basis": protocol.candidate_semantics[
                "source_display_time_basis"
            ],
            "fotmob_candidate_semantic_equivalence_before_execution": protocol.candidate_semantics[
                "pr119_source_local_semantic_equivalence"
            ],
            "reference_basis_resolved": False,
            "source_independent_invariance_proven": False,
            "qualification_status": QUALIFICATION_STATUS,
        },
        "gate_results": {
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
        },
        "interpretation": {
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
        },
        "remaining_blockers": [QUALIFICATION_STATUS],
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": {key: False for key in sorted(SAFETY_KEYS)},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    receipt = build_receipt()
    raw = canonical(receipt)
    if (hashlib.sha256(raw).hexdigest(), len(raw)) != (
        EXPECTED_RECEIPT_SHA256,
        EXPECTED_RECEIPT_SIZE,
    ):
        fail("PR121 receipt identity changed")
    if args.output is None:
        print(raw.decode("utf-8"), end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
