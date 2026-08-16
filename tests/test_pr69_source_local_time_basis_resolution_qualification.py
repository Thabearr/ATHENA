"""Tests for PR #123 PR69 source-local time-basis resolution qualification."""
from __future__ import annotations

import hashlib

import domain.pr69_source_local_time_basis_resolution_qualification as q


def _receipt():
    return q.load_pr69_source_local_time_basis_resolution_qualification_receipt()


def test_receipt_is_exact_canonical_identity() -> None:
    receipt = _receipt()
    raw = q.canonical_pr69_source_local_time_basis_resolution_qualification_receipt_bytes()
    assert len(raw) == q.RECEIPT_SIZE == 4_077
    assert hashlib.sha256(raw).hexdigest() == q.RECEIPT_SHA256
    assert q.RECEIPT_SHA256 == (
        "4cd3f3ecbddbe23f0c29a4c86831083405290658d0cc20f14d134fc55e5e91db"
    )
    assert receipt["qualification_state"] == q.QUALIFICATION_STATE


def test_execution_revalidates_exact_pr122_and_pr69_scope() -> None:
    receipt = _receipt()
    assert receipt["protocol"] == {
        "protocol_id": "REVIEWED_PR69_SOURCE_LOCAL_TIME_BASIS_RESOLUTION_PROTOCOL_V1",
        "blob_sha": q.PR122_PROTOCOL_BLOB_SHA,
        "canonical_sha256": (
            "d3bf061ade81bb1b60f38e98f5fa3c8c21ba5bf6652879f2cc19e151b53aee4a"
        ),
        "canonical_size_bytes": 6_983,
    }
    assert receipt["frozen_scope"]["source"] == "football_data_uk_csv"
    assert receipt["frozen_scope"]["source_file_count"] == 66
    assert receipt["frozen_scope"]["source_fixture_count"] == 21_226
    assert receipt["frozen_scope"]["full_athena_competition_universe_claimed"] is False


def test_qualification_fails_closed_at_missing_admissible_evidence_gate() -> None:
    receipt = _receipt()
    assert receipt["qualification_state"] == (
        "EXECUTED_FAIL_CLOSED_NO_ADMISSIBLE_PRIMARY_TIME_BASIS_EVIDENCE"
    )
    assert receipt["remaining_blockers"] == [
        "BLOCKED_NO_ADMISSIBLE_PRIMARY_TIME_BASIS_EVIDENCE"
    ]
    assert receipt["execution_inputs"][
        "provenanced_primary_time_basis_evidence_bundle_supplied"
    ] is False
    assert receipt["execution_inputs"][
        "formal_operational_invariance_proof_bundle_supplied"
    ] is False
    assert receipt["evidence_assessment"][
        "admissible_primary_time_basis_evidence_record_count"
    ] == 0
    assert receipt["gate_results"][
        "ADMISSIBLE_PRIMARY_TIME_BASIS_EVIDENCE_AVAILABLE"
    ] == q.QUALIFICATION_STATUS


def test_no_timezone_or_reference_rule_is_inferred() -> None:
    receipt = _receipt()
    assessment = receipt["evidence_assessment"]
    interpretation = receipt["interpretation"]
    assert assessment["direct_reference_rule_available"] is False
    assert assessment["direct_reference_rule_shape"] is None
    assert assessment["formal_invariance_route_available"] is False
    assert interpretation["pr69_source_local_time_basis_resolved"] is False
    assert interpretation["named_timezone_inferred"] is False
    assert interpretation["fixed_offset_inferred"] is False
    assert interpretation["source_defined_local_civil_rule_inferred"] is False
    assert interpretation["result_fit_or_majority_vote_used"] is False


def test_later_pr122_gates_remain_not_reached() -> None:
    gates = _receipt()["gate_results"]
    for key in (
        "DIRECT_REFERENCE_RULE_DERIVATION",
        "DIRECT_REFERENCE_EFFECTIVE_PERIOD_AND_VERSION_SCOPE",
        "ALL_RELEVANT_PR69_ROWS_MAPPED",
        "FORMAL_OPERATIONAL_INVARIANCE_ROUTE",
        "STRICT_PRIOR_MEMBERSHIP_INVARIANCE",
        "FORM_ORDERING_AND_TIEBREAK_INVARIANCE",
        "ELO_ORDERING_AND_TIEBREAK_INVARIANCE",
        "MOST_RECENT_PRIOR_FIXTURE_INVARIANCE",
        "INTEGER_DATETIME_DELTA_DAYS_INVARIANCE",
        "HOME_MINUS_AWAY_REST_DIFFERENCE_INVARIANCE",
        "FATIGUE_BUCKET_INVARIANCE",
        "FOTMOB_EUROPE_OSLO_COMPARISON",
    ):
        assert gates[key] == "NOT_REACHED"


def test_fotmob_equivalence_and_pr80_checks_are_not_performed() -> None:
    interpretation = _receipt()["interpretation"]
    assert interpretation["fotmob_equivalence_assessment_performed"] is False
    assert interpretation["fotmob_europe_oslo_equivalence_proven"] is False
    assert interpretation["fotmob_europe_oslo_mismatch_proven"] is False
    assert interpretation["pr80_time_sensitive_row_checks_performed"] is False


def test_all_downstream_authority_remains_false() -> None:
    receipt = _receipt()
    assert set(receipt["safety"]) == q.SAFETY_KEYS
    assert all(value is False for value in receipt["safety"].values())
    assert receipt["safety"]["pr69_source_local_time_basis_resolved"] is False
    assert receipt["safety"]["source_local_time_semantic_equivalence_qualified"] is False
    assert receipt["safety"]["pr80_constructor_input_authorized"] is False
    assert receipt["safety"]["model_training_authorized"] is False
    assert receipt["safety"]["bet_authorized"] is False


def test_blocker_progression_and_next_boundary_are_exact() -> None:
    receipt = _receipt()
    assert receipt["superseded_blocker"] == q.SUPERSEDED_BLOCKER
    assert q.SUPERSEDED_BLOCKER == "BLOCKED_PR69_REFERENCE_TIME_BASIS_UNRESOLVED"
    assert receipt["next_required_boundary"] == q.NEXT_REQUIRED_BOUNDARY
    assert q.NEXT_REQUIRED_BOUNDARY == (
        "PRE_REGISTER_REVIEWED_PR69_PRIMARY_TIME_BASIS_EVIDENCE_ACQUISITION_PROTOCOL"
    )
