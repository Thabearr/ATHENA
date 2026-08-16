"""Tests for PR #123 PR69 source-local time-basis resolution qualification."""
from __future__ import annotations

import hashlib

import domain.pr69_source_local_time_basis_resolution_qualification as q


def _receipt():
    return q.load_pr69_source_local_time_basis_resolution_qualification_receipt()


def test_receipt_is_exact_canonical_identity() -> None:
    receipt = _receipt()
    raw = q.canonical_pr69_source_local_time_basis_resolution_qualification_receipt_bytes()
    assert len(raw) == q.RECEIPT_SIZE == 6_596
    assert hashlib.sha256(raw).hexdigest() == q.RECEIPT_SHA256
    assert q.RECEIPT_SHA256 == (
        "ff95a545963b52b6bd63236b6b98f5589ea3d104f424ed37a5e9fe1ce4376d27"
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


def test_execution_output_contract_inventory_and_accounting_are_present() -> None:
    receipt = _receipt()
    inventory = receipt["evidence_inventory"]
    keys = inventory["pr69_source_file_keys"]
    assert len(keys) == inventory["pr69_source_file_key_count"] == 66
    assert len(set(keys)) == 66
    assert keys[0] == "2020-21:B1"
    assert keys[-1] == "2025-26:T1"
    assert inventory["pr69_source_bytes_identity"] == {
        "source_file_count": 66,
        "source_total_bytes": 10_006_877,
        "source_fixture_count": 21_226,
        "source_corpus_sha256": (
            "c273b4bff2b611e95248133340ff84803ce238814d5dfa7ded5f39fd3d6e25a0"
        ),
        "canonical_replay_sha256": (
            "b44166b9543a8f436e62a644efc5316ad12fcc260a4c2c5908ad112928bedfe3"
        ),
        "canonical_replay_size_bytes": 39_952_730,
    }
    assert inventory["raw_date_time_text_preserved_by_frozen_source_bytes"] is True
    assert inventory["raw_date_time_text_reinspection_performed"] is False
    assert receipt["primary_evidence_conflict_table"] == []
    coverage = receipt["row_coverage_accounting"]
    assert coverage["total_pr69_fixture_rows"] == 21_226
    assert coverage["direct_reference_rule_mapped_rows"] == 0
    assert coverage["formal_invariance_proven_rows"] == 0
    assert coverage["unresolved_rows"] == 21_226


def test_current_official_notes_candidate_is_discovery_only_not_authority() -> None:
    receipt = _receipt()
    candidates = receipt["evidence_inventory"][
        "non_admissible_primary_discovery_candidates"
    ]
    assert candidates == [
        {
            "url": q.DISCOVERY_URL,
            "discovered_at_utc": q.DISCOVERY_CAPTURED_AT_UTC,
            "primary_origin": "football-data.co.uk",
            "observed_time_field_description": q.DISCOVERY_TIME_FIELD_DESCRIPTION,
            "raw_bytes_preserved": False,
            "raw_sha256": None,
            "historical_effective_scope_proven": False,
            "admissible_under_pr122": False,
            "rejection_reason": (
                "RAW_BYTES_HASH_AND_HISTORICAL_EFFECTIVE_SCOPE_NOT_PRESERVED_IN_A_REVIEWED_EVIDENCE_BUNDLE"
            ),
        }
    ]
    assert receipt["evidence_assessment"][
        "non_admissible_primary_discovery_candidate_count"
    ] == 1
    assert receipt["evidence_assessment"][
        "admissible_primary_time_basis_evidence_record_count"
    ] == 0


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
    assert receipt["gate_results"]["EVIDENCE_INVENTORY_AND_ROW_ACCOUNTING"] == "PASSED"
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
