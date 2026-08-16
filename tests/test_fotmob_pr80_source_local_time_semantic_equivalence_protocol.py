"""Tests for PR #120 source-local time semantic-equivalence pre-registration."""
from __future__ import annotations

import hashlib

import domain.fotmob_pr80_source_local_time_semantic_equivalence_protocol as p


def _protocol():
    return p.build_fotmob_pr80_source_local_time_semantic_equivalence_protocol()


def test_protocol_is_exact_canonical_frozen_identity() -> None:
    value = _protocol()
    raw = p.canonical_fotmob_pr80_source_local_time_semantic_equivalence_protocol_bytes(value)
    assert len(raw) == p.PROTOCOL_SIZE == 5_242
    assert hashlib.sha256(raw).hexdigest() == p.PROTOCOL_SHA256
    assert p.PROTOCOL_SHA256 == "a938ee4ea45c427c5396fe063af4efd2341a9c8e8ffccc1105aa7bdffdbb2918"
    assert value.repository_main_sha == "37c5f031a71222b13cbea19eaab0fbd92ba74aa0"


def test_protocol_remains_result_free_and_scope_is_exact() -> None:
    value = _protocol()
    assert value.protocol_state == "PRE_REGISTERED_NOT_EXECUTED_SOURCE_LOCAL_TIME_EQUIVALENCE_UNQUALIFIED"
    assert value.frozen_scope["history_row_count"] == 21_326
    assert value.frozen_scope["historical_request_date_end"] == "2026-08-14"
    assert tuple(value.frozen_scope["model_league_codes"]) == p.MODEL_LEAGUE_CODES
    assert value.frozen_scope["full_athena_competition_universe_claimed"] is False
    assert value.frozen_scope["dates_after_historical_ceiling_authorized"] is False
    assert value.frozen_scope["target_specific_pr80_construction_authorized"] is False
    assert value.frozen_scope["global_fotmob_historical_coverage_promoted"] is False


def test_pr69_reference_time_basis_remains_unresolved() -> None:
    value = _protocol()
    reference = value.reference_semantics
    assert reference["pr69_source"] == "football_data_uk_csv"
    assert reference["pr69_source_local_timezone"] == "SOURCE_LOCAL_TIMEZONE_UNRESOLVED"
    assert reference["pr69_local_kickoff_type"] == (
        "NAIVE_DATETIME_COMBINED_FROM_SOURCE_DATE_AND_SOURCE_TIME"
    )
    assert reference["pr80_source_local_time_basis"] == (
        "SOURCE_LOCAL_NAIVE_DATETIME_REQUIRED_FOR_PR78_PARITY"
    )


def test_fotmob_europe_oslo_remains_candidate_not_equivalence() -> None:
    value = _protocol()
    candidate = value.candidate_semantics
    assert candidate["canonical_kickoff_field"] == "status.utcTime"
    assert candidate["source_display_time_basis"] == "Europe/Oslo"
    assert candidate["pr119_source_local_utc_global_order_disagreement_count"] == 0
    assert candidate["pr119_source_local_semantic_equivalence"] == "UNPROVEN"
    assert candidate["pr119_pr80_constructor_input_authorized"] is False
    assert "DO_NOT_ASSUME_EUROPE_OSLO_EQUALS_PR69_SOURCE_LOCAL_TIME" in value.forbidden_shortcuts


def test_time_dependent_pr80_operations_are_frozen_for_future_execution() -> None:
    value = _protocol()
    reference = value.reference_semantics
    assert reference["pr80_form_chronology"] == (
        "STRICTLY_PRIOR_FIXTURES_ORDERED_KICKOFF_DESCENDING"
    )
    assert reference["pr80_elo_chronology"] == (
        "SOURCE_LOCAL_KICKOFF_ASC_THEN_FIXTURE_IDENTIFIER_ASC_PREMATCH_STATE_ONLY"
    )
    assert reference["pr80_fatigue_chronology"] == (
        "MOST_RECENT_STRICTLY_PRIOR_FIXTURE_PER_TEAM"
    )
    assert reference["pr80_fatigue_rest_day_measure"] == (
        "DATETIME_DELTA_DAYS_INTEGER_COMPONENT"
    )
    assert reference["pr80_fatigue_orientation"] == "HOME_REST_DAYS_MINUS_AWAY_REST_DAYS"
    requirements = set(value.qualification_requirements)
    assert "PROVE_DATETIME_DELTA_DAYS_INTEGER_COMPONENT_EQUIVALENCE_FOR_HOME_AND_AWAY_REST" in requirements
    assert "PROVE_HOME_MINUS_AWAY_REST_DAY_DIFFERENCE_EQUIVALENCE_AND_FATIGUE_BUCKET_EQUIVALENCE" in requirements


def test_zero_global_order_disagreement_is_explicitly_insufficient() -> None:
    value = _protocol()
    assert (
        "ZERO_GLOBAL_ORDERING_DISAGREEMENT_DOES_NOT_PROVE_DATETIME_DELTA_DAYS_EQUIVALENCE"
        in value.forbidden_shortcuts
    )
    assert (
        "EQUAL_NUMERIC_FEATURE_VALUES_ALONE_DO_NOT_PROVE_SEMANTIC_EQUIVALENCE"
        in value.forbidden_shortcuts
    )


def test_status_vocabulary_is_exact_and_fail_closed() -> None:
    value = _protocol()
    assert value.qualification_status_vocabulary == (
        "QUALIFIED_EXACT_PR80_SOURCE_LOCAL_TIME_SEMANTIC_EQUIVALENCE",
        "BLOCKED_PR69_REFERENCE_TIME_BASIS_UNRESOLVED",
        "BLOCKED_FOTMOB_TIME_BASIS_EVIDENCE_INSUFFICIENT",
        "BLOCKED_TIME_DEPENDENT_OPERATION_MISMATCH",
        "BLOCKED_TEMPORAL_AMBIGUITY",
        "BLOCKED_ANCESTRY_OR_EVIDENCE_GAP",
    )


def test_all_downstream_authority_remains_false() -> None:
    value = _protocol()
    assert set(value.safety) == p.SAFETY_KEYS
    assert all(flag is False for flag in value.safety.values())


def test_next_boundary_is_execution_only() -> None:
    value = _protocol()
    assert value.next_required_boundary == (
        "EXECUTE_REVIEWED_FOTMOB_PR80_SOURCE_LOCAL_TIME_SEMANTIC_EQUIVALENCE_QUALIFICATION"
    )
    assert value.next_required_boundary == p.NEXT_REQUIRED_BOUNDARY
