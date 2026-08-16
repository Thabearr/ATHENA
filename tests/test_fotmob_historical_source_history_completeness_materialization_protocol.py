"""Tests for the exact PR #118 historical completeness/materialization protocol."""
from __future__ import annotations

import hashlib

import domain.fotmob_historical_source_history_adapter_qualification as pr117
import domain.fotmob_ordinary_ft_finished_score_source_history_completeness_protocol as pr99
import domain.prospective_successor_source_history_completeness_protocol as pr81
import domain.fotmob_historical_source_history_completeness_materialization_protocol as protocol
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


def _value():
    return protocol.build_fotmob_historical_source_history_completeness_materialization_protocol()


def test_protocol_is_exact_canonical_frozen_identity() -> None:
    value = _value()
    raw = protocol.canonical_fotmob_historical_source_history_completeness_materialization_protocol_bytes(value)
    assert len(raw) == protocol.PROTOCOL_SIZE == 9_708
    assert hashlib.sha256(raw).hexdigest() == protocol.PROTOCOL_SHA256
    assert protocol.PROTOCOL_SHA256 == (
        "c4d9d019fa433677d82354570df1fe1c0e634c14b91c1f9ba0c3b47f91258209"
    )
    assert value["repository_main_sha"] == "7e0e43852ff6527021de6ece52394b44bf222234"


def test_pr81_and_pr99_contracts_are_reconciled_not_rewritten() -> None:
    value = _value()
    assert value["upstream"]["pr81_protocol_sha256"] == pr81.PROTOCOL_SHA256
    assert value["upstream"]["pr99_protocol_sha256"] == pr99.PROTOCOL_SHA256
    rules = value["contract_reconciliation_rules"]
    assert "PR81_SOURCE_HISTORY_COMPLETENESS_REQUIREMENTS_REMAIN_AUTHORITATIVE_AND_ARE_NOT_REWRITTEN" in rules
    assert "PR99_PROSPECTIVE_DERIVED_SCORE_SOURCE_COMPLETENESS_PROTOCOL_REMAINS_UNCHANGED_FOR_PROSPECTIVE_USE" in rules
    assert any("PR117_QUALIFIED_HISTORICAL_ADAPTER" in rule for rule in rules)


def test_pr117_adapter_qualification_and_projection_are_exact_ancestry() -> None:
    value = _value()
    upstream = value["upstream"]
    assert upstream["pr117_historical_adapter_receipt_sha256"] == pr117.RECEIPT_SHA256
    assert upstream["pr117_historical_adapter_receipt_size_bytes"] == pr117.RECEIPT_SIZE == 5_081
    assert upstream["pr117_ordinary_ft_projection_sha256"] == pr117.ORDINARY_FT_PROJECTION_SHA256
    assert upstream["pr117_ordinary_ft_projection_size_bytes"] == pr117.ORDINARY_FT_PROJECTION_SIZE


def test_exact_eleven_family_floors_and_candidate_counts_are_frozen() -> None:
    value = _value()
    assert set(value["frozen_family_reference_floors"]) == {
        "B1", "D1", "E0", "F1", "G1", "I1", "N1", "P1", "SC0", "SP1", "T1"
    }
    evidence = value["evidence_expectations"]
    assert evidence["ordinary_ft_occurrence_count"] == 21_336
    assert evidence["reviewed_special_state_occurrence_count"] == 304
    assert evidence["target_family_fixture_date_pair_count"] == 21_640
    assert evidence["preboundary_ordinary_ft_occurrence_count"] == 10
    assert evidence["on_or_after_floor_materialization_candidate_count"] == 21_326
    assert sum(evidence["on_or_after_floor_by_model_league"].values()) == 21_326


def test_materialization_preserves_preboundary_and_special_exclusions() -> None:
    rules = _value()["materialization_rules"]
    assert any("21326_PR117_ORDINARY_FT_OCCURRENCES" in rule for rule in rules)
    assert any("10_PRE_FLOOR" in rule and "EVIDENCE_ONLY" in rule for rule in rules)
    assert any("304_REVIEWED_SPECIAL_STATE_OCCURRENCES" in rule for rule in rules)
    assert any("PR80_PROSPECTIVE_MATCH_EVIDENCE" in rule for rule in rules)


def test_materialized_row_semantics_are_source_scoped_and_temporally_conservative() -> None:
    value = _value()
    assert value["source_scope"]["source_namespace"] == protocol.SOURCE_NAMESPACE
    assert value["source_scope"]["source_local_time_basis"] == "Europe/Oslo"
    rules = value["materialization_rules"]
    assert any("EXACT_DECIMAL_STRINGS_OF_POSITIVE_FOTMOB_SOURCE_IDS" in rule for rule in rules)
    assert any("EARLIEST_OF_THE_TWO_PR117_QUALIFIED_MANIFEST_OBSERVATION_TIMES" in rule for rule in rules)
    assert any("STRICTLY_AFTER_KICKOFF_UTC" in rule for rule in rules)


def test_daily_completeness_and_future_ceiling_remain_fail_closed() -> None:
    value = _value()
    assert value["source_scope"]["historical_request_date_start"] == "2020-08-01"
    assert value["source_scope"]["historical_request_date_end"] == "2026-08-14"
    rules = value["completeness_rules"]
    assert any("ALL_2205_REQUEST_DATES" in rule for rule in rules)
    assert any("TARGET_REQUIRING_ANY_REQUEST_DATE_AFTER_2026_08_14" in rule for rule in rules)
    future = value["future_extension_rules"]
    assert any("CONTIGUOUS_WITH_THE_2026_08_14_HISTORICAL_CEILING" in rule for rule in future)
    assert any("NO_TARGET_AFTER_THE_HISTORICAL_CEILING" in rule for rule in future)


def test_global_capability_registry_is_not_promoted_by_pr118() -> None:
    value = _value()
    capability = SOURCE_CAPABILITY_REGISTRY[protocol.SOURCE_NAMESPACE]
    assert capability.full_time_score is CapabilityAvailability.CONFIRMED
    assert capability.reliable_fixture_identity is CapabilityAvailability.CONFIRMED
    assert capability.historical_coverage is CapabilityAvailability.UNKNOWN
    assert value["source_scope"]["global_source_capability_historical_coverage_must_remain"] == "UNKNOWN"
    assert "GLOBAL_SOURCE_CAPABILITY_HISTORICAL_COVERAGE_CONFIRMED" in value["positive_execution_must_remain_false"]


def test_pr118_grants_no_authority_and_freezes_execution_boundary() -> None:
    value = _value()
    assert value["protocol_state"] == "PRE_REGISTERED_NOT_EXECUTED_HISTORICAL_COVERAGE_UNPROVEN"
    assert value["current_pre_execution_disposition"] == "BLOCKED_HISTORICAL_COVERAGE_UNPROVEN"
    assert all(flag is False for flag in value["safety"].values())
    assert value["next_required_boundary"] == protocol.NEXT_REQUIRED_BOUNDARY
    assert protocol.NEXT_REQUIRED_BOUNDARY == (
        "EXECUTE_REVIEWED_FOTMOB_HISTORICAL_SOURCE_HISTORY_COMPLETENESS_AND_MATERIALIZATION_QUALIFICATION"
    )
