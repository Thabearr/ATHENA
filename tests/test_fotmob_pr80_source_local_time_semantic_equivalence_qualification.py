"""Tests for PR #121 source-local time semantic-equivalence execution."""
from __future__ import annotations

import hashlib

import domain.fotmob_pr80_source_local_time_semantic_equivalence_qualification as q
import scripts.qualify_fotmob_pr80_source_local_time_semantic_equivalence as exec121


def _receipt():
    return q.load_fotmob_pr80_source_local_time_semantic_equivalence_qualification_receipt()


def test_receipt_is_exact_canonical_identity() -> None:
    raw = q.canonical_fotmob_pr80_source_local_time_semantic_equivalence_qualification_receipt_bytes()
    assert len(raw) == q.RECEIPT_SIZE == 3_599
    assert hashlib.sha256(raw).hexdigest() == q.RECEIPT_SHA256
    assert q.RECEIPT_SHA256 == "8d057e96504a83237b719b3a465e29b7df74e2b6c3630fc1d97e8a2a7bdfb5fb"


def test_execution_reproduces_checked_in_receipt_exactly() -> None:
    generated = exec121.canonical(exec121.build_receipt())
    checked = q.canonical_fotmob_pr80_source_local_time_semantic_equivalence_qualification_receipt_bytes()
    assert generated == checked


def test_first_semantic_gate_fails_closed_on_unresolved_pr69_reference() -> None:
    receipt = _receipt()
    assert receipt["qualification_state"] == (
        "EXECUTED_FAIL_CLOSED_PR69_REFERENCE_TIME_BASIS_UNRESOLVED"
    )
    assert receipt["reference_gate"]["pr69_source_local_timezone_state"] == (
        "SOURCE_LOCAL_TIMEZONE_UNRESOLVED"
    )
    assert receipt["reference_gate"]["reference_basis_resolved"] is False
    assert receipt["reference_gate"]["source_independent_invariance_proven"] is False
    assert receipt["reference_gate"]["qualification_status"] == (
        "BLOCKED_PR69_REFERENCE_TIME_BASIS_UNRESOLVED"
    )


def test_no_evidence_or_invariance_bundle_is_invented() -> None:
    inputs = _receipt()["execution_inputs"]
    assert inputs["exact_pr120_protocol_supplied"] is True
    assert inputs["admissible_reference_basis_evidence_bundle_supplied"] is False
    assert inputs["formal_source_independent_invariance_proof_bundle_supplied"] is False
    assert inputs["campaign_reexecution_required_before_reference_gate"] is False
    assert inputs["campaign_reexecution_performed"] is False


def test_row_level_time_operation_gates_are_not_reached_after_reference_blocker() -> None:
    gates = _receipt()["gate_results"]
    assert gates["EXACT_ANCESTRY_REVALIDATION"] == "PASSED"
    assert gates[
        "PR69_REFERENCE_TIME_BASIS_RESOLUTION_OR_SOURCE_INDEPENDENT_INVARIANCE"
    ] == "BLOCKED_PR69_REFERENCE_TIME_BASIS_UNRESOLVED"
    for name in (
        "FOTMOB_EUROPE_OSLO_ADMISSIBILITY",
        "STRICT_PRIOR_MEMBERSHIP_EQUIVALENCE",
        "FORM_ORDERING_EQUIVALENCE",
        "ELO_ORDERING_EQUIVALENCE",
        "MOST_RECENT_PRIOR_FIXTURE_EQUIVALENCE",
        "DATETIME_DELTA_DAYS_INTEGER_COMPONENT_EQUIVALENCE",
        "REST_DIFFERENCE_AND_FATIGUE_BUCKET_EQUIVALENCE",
        "ZERO_UNRESOLVED_TEMPORAL_AMBIGUITY",
    ):
        assert gates[name] == "NOT_REACHED"


def test_blocker_does_not_claim_europe_oslo_is_wrong_or_right() -> None:
    interpretation = _receipt()["interpretation"]
    assert interpretation["europe_oslo_mismatch_proven"] is False
    assert interpretation["europe_oslo_equivalence_proven"] is False
    assert interpretation["result_driven_timezone_inference_performed"] is False
    assert interpretation["cross_source_fixture_or_team_identity_inference_performed"] is False


def test_frozen_scope_does_not_expand_athena_competition_universe() -> None:
    scope = _receipt()["frozen_scope"]
    assert scope["history_row_count"] == 21_326
    assert scope["historical_request_date_end"] == "2026-08-14"
    assert scope["model_league_codes"] == [
        "B1", "D1", "E0", "F1", "G1", "I1", "N1", "P1", "SC0", "SP1", "T1"
    ]
    assert scope["full_athena_competition_universe_claimed"] is False


def test_all_downstream_authority_remains_false() -> None:
    safety = _receipt()["safety"]
    assert set(safety) == q.SAFETY_KEYS
    assert all(value is False for value in safety.values())


def test_next_boundary_targets_reference_basis_resolution_only() -> None:
    receipt = _receipt()
    assert receipt["remaining_blockers"] == [
        "BLOCKED_PR69_REFERENCE_TIME_BASIS_UNRESOLVED"
    ]
    assert receipt["next_required_boundary"] == (
        "PRE_REGISTER_REVIEWED_PR69_SOURCE_LOCAL_TIME_BASIS_RESOLUTION_PROTOCOL"
    )
    assert receipt["next_required_boundary"] == q.NEXT_REQUIRED_BOUNDARY
