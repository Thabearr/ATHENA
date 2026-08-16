"""Tests for PR #122 PR69 source-local time basis resolution pre-registration."""
from __future__ import annotations

import dataclasses
import hashlib

import pytest

import domain.pr69_source_local_time_basis_resolution_protocol as p


def _protocol():
    return p.build_pr69_source_local_time_basis_resolution_protocol()


def test_protocol_is_exact_canonical_identity() -> None:
    protocol = _protocol()
    raw = p.canonical_pr69_source_local_time_basis_resolution_protocol_bytes(protocol)
    assert len(raw) == p.PROTOCOL_SIZE == 6_983
    assert hashlib.sha256(raw).hexdigest() == p.PROTOCOL_SHA256
    assert p.PROTOCOL_SHA256 == "d3bf061ade81bb1b60f38e98f5fa3c8c21ba5bf6652879f2cc19e151b53aee4a"


def test_protocol_preserves_pr121_blocker_and_exact_pr69_scope() -> None:
    protocol = _protocol()
    assert protocol.protocol_state == (
        "PRE_REGISTERED_NOT_EXECUTED_PR69_SOURCE_LOCAL_TIME_BASIS_UNRESOLVED"
    )
    assert protocol.frozen_pr69_scope["source"] == "football_data_uk_csv"
    assert protocol.frozen_pr69_scope["source_local_timezone_state"] == (
        "SOURCE_LOCAL_TIMEZONE_UNRESOLVED"
    )
    assert protocol.frozen_pr69_scope["source_file_count"] == 66
    assert protocol.frozen_pr69_scope["source_fixture_count"] == 21_226
    assert protocol.frozen_pr69_scope["full_athena_competition_universe_claimed"] is False


def test_direct_resolution_requires_primary_explicit_executable_rule() -> None:
    contract = _protocol().direct_resolution_contract
    assert contract["must_cover_every_relevant_pr69_row"] is True
    assert contract["must_define_dst_or_offset_transition_semantics_when_applicable"] is True
    assert contract["must_define_effective_period_and_version_scope"] is True
    assert contract["must_be_executable_without_cross_source_identity_inference"] is True
    assert contract["raw_source_time_text_remains_immutable"] is True
    assert contract["named_timezone_required"] is False
    assert tuple(contract["accepted_reference_model_shapes"]) == p.DIRECT_REFERENCE_MODEL_SHAPES


def test_invariance_route_is_strict_and_operation_complete() -> None:
    contract = _protocol().invariance_route_contract
    assert contract["available_only_if_direct_primary_semantics_not_recovered"] is True
    assert contract["must_enumerate_every_admissible_reference_transformation"] is True
    for key in (
        "must_prove_strict_prior_membership_invariance",
        "must_prove_form_ordering_and_tiebreak_invariance",
        "must_prove_elo_ordering_and_tiebreak_invariance",
        "must_prove_most_recent_prior_fixture_invariance",
        "must_prove_integer_datetime_delta_days_invariance",
        "must_prove_home_minus_away_rest_difference_invariance",
        "must_prove_fatigue_bucket_invariance",
        "equal_numeric_outputs_without_proven_assumptions_are_insufficient",
    ):
        assert contract[key] is True


def test_forbidden_shortcuts_block_result_driven_timezone_inference() -> None:
    forbidden = set(_protocol().forbidden_shortcuts)
    assert "DO_NOT_INFER_TIMEZONE_FROM_LEAGUE_COUNTRY_TEAM_VENUE_OR_COMMON_FOOTBALL_PRACTICE" in forbidden
    assert "DO_NOT_TREAT_FOTMOB_EUROPE_OSLO_OR_ANY_OTHER_CROSS_SOURCE_CLOCK_AS_THE_PR69_REFERENCE" in forbidden
    assert (
        "DO_NOT_TREAT_EQUAL_KICKOFF_ORDER_EQUAL_FEATURE_VALUES_OR_ZERO_OBSERVED_DISAGREEMENTS_AS_REFERENCE_BASIS_EVIDENCE"
        in forbidden
    )
    assert "DO_NOT_RESOLVE_CONFLICTING_PRIMARY_EVIDENCE_BY_MAJORITY_VOTE_OR_RESULT_FIT" in forbidden


def test_positive_status_requires_rule_or_formal_invariance_not_guessing() -> None:
    protocol = _protocol()
    assert "QUALIFIED_DIRECT_PRIMARY_SOURCE_TIME_BASIS" in protocol.qualification_status_vocabulary
    assert (
        "QUALIFIED_FORMAL_OPERATIONAL_INVARIANCE_WITHOUT_NAMED_TIMEZONE"
        in protocol.qualification_status_vocabulary
    )
    assert (
        protocol.execution_output_contract[
            "resolution_rule_or_invariance_proof_required_for_positive_status"
        ]
        is True
    )
    assert protocol.execution_output_contract["fotmob_equivalence_assessment_performed"] is False
    assert protocol.execution_output_contract["pr80_constructor_input_authorized"] is False


def test_all_downstream_authority_remains_false() -> None:
    protocol = _protocol()
    assert set(protocol.safety) == p.SAFETY_KEYS
    assert all(value is False for value in protocol.safety.values())
    assert protocol.safety["pr69_source_local_time_basis_resolved"] is False
    assert protocol.safety["source_local_time_semantic_equivalence_qualified"] is False
    assert protocol.safety["bet_authorized"] is False


def test_next_boundary_is_execution_only() -> None:
    protocol = _protocol()
    assert protocol.next_required_boundary == (
        "EXECUTE_REVIEWED_PR69_SOURCE_LOCAL_TIME_BASIS_RESOLUTION_QUALIFICATION"
    )
    assert protocol.execution_output_contract["next_required_boundary"] == protocol.next_required_boundary


def test_protocol_is_fail_closed_against_tampering() -> None:
    protocol = _protocol()
    with pytest.raises(p.PR69SourceLocalTimeBasisResolutionProtocolError):
        dataclasses.replace(
            protocol,
            protocol_state="QUALIFIED_DIRECT_PRIMARY_SOURCE_TIME_BASIS",
        )
