"""Tests for the exact PR #119 historical completeness/materialization qualification."""
from __future__ import annotations

import hashlib

import domain.fotmob_historical_source_history_completeness_materialization_protocol as pr118
import domain.fotmob_historical_source_history_completeness_materialization_qualification as q
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


def _receipt():
    return q.load_fotmob_historical_source_history_completeness_materialization_qualification_receipt()


def test_receipt_is_exact_canonical_frozen_identity() -> None:
    value = _receipt()
    raw = q.canonical_fotmob_historical_source_history_completeness_materialization_qualification_receipt_bytes()
    assert len(raw) == q.RECEIPT_SIZE == 6_810
    assert hashlib.sha256(raw).hexdigest() == q.RECEIPT_SHA256
    assert q.RECEIPT_SHA256 == "da8037cd9b4a4f91be942a4052e76134b66cc94221ed66e624c14008c9e562a0"
    assert value["repository_main_anchor"] == "2b2f6390f077b562c185768db030c7c4e61a06de"


def test_positive_status_is_exact_pr118_admitted_scoped_result() -> None:
    value = _receipt()
    assert value["qualification_state"] == q.QUALIFICATION_STATE
    status = value["completeness_qualification"]["qualification_status"]
    assert status == q.QUALIFICATION_STATUS
    assert status in pr118.QUALIFICATION_STATUS_VOCABULARY
    assert value["resolved_blocker"] == "BLOCKED_HISTORICAL_COVERAGE_UNPROVEN"


def test_exact_frozen_campaign_completeness_accounting_is_closed() -> None:
    c = _receipt()["completeness_qualification"]
    assert c["request_date_count"] == 2_205
    assert c["capture_manifest_count"] == 4_410
    assert c["target_family_fixture_date_occurrence_count"] == 21_640
    assert c["ordinary_ft_occurrence_count"] == 21_336
    assert c["reviewed_special_state_occurrence_count"] == 304
    assert c["ordinary_ft_occurrence_count"] + c["reviewed_special_state_occurrence_count"] == 21_640
    assert c["preboundary_ordinary_ft_occurrence_count"] == 10
    assert c["on_or_after_floor_materialization_candidate_count"] == 21_326
    assert sum(c["on_or_after_floor_by_model_league"].values()) == 21_326


def test_all_frozen_completeness_and_materialization_conflicts_remain_zero() -> None:
    c = _receipt()["completeness_qualification"]
    for key in (
        "missing_required_date_count",
        "capture_pair_cardinality_mismatch_count",
        "request_identity_mismatch_count",
        "manifest_raw_lineage_mismatch_count",
        "unreviewed_target_state_occurrence_count",
        "ordinary_ft_duplicate_source_fixture_id_count",
        "materializable_duplicate_source_fixture_id_count",
        "same_team_same_source_local_kickoff_conflict_count",
        "same_team_same_utc_kickoff_conflict_count",
        "request_date_kickoff_utc_date_mismatch_count",
        "source_display_time_basis_mismatch_count",
        "source_local_utc_global_order_disagreement_count",
        "final_result_observation_not_after_kickoff_count",
        "materialization_row_invariant_violation_count",
        "materialization_evidence_sha256_duplicate_count",
        "materialization_evidence_reference_duplicate_count",
    ):
        assert c[key] == 0


def test_exact_21326_row_materialization_is_frozen_and_deterministic() -> None:
    value = _receipt()
    materialization = value["materialization"]
    assert materialization["history_row_count"] == 21_326
    assert materialization["projection_sha256"] == q.MATERIALIZATION_PROJECTION_SHA256
    assert materialization["projection_size_bytes"] == q.MATERIALIZATION_PROJECTION_SIZE == 10_545_099
    assert q.MATERIALIZATION_PROJECTION_SHA256 == (
        "e5b78163a5eb68000b9a60dda97f04cac2a970f9cf2aaf588233151e586be8c2"
    )
    assert materialization["pr80_structural_validation_performed"] is True
    assert value["scoped_authority"]["exact_21326_ordinary_ft_history_rows_materialized"] is True
    assert value["scoped_authority"]["exact_21326_ordinary_ft_history_rows_materialization_authorized"] is True


def test_pre_floor_and_special_states_remain_excluded_from_ordinary_history() -> None:
    c = _receipt()["completeness_qualification"]
    assert c["preboundary_ordinary_ft_occurrence_count"] == 10
    assert c["reviewed_special_state_occurrence_count"] == 304
    assert c["special_state_occurrence_counts"] == {
        "ABANDONED": 20,
        "AFTER_EXTRA_TIME": 3,
        "AFTER_PENALTIES": 3,
        "AWARDED_WIN": 26,
        "CANCELLED": 11,
        "POSTPONED": 241,
    }


def test_scoped_historical_completeness_does_not_promote_global_source_capability() -> None:
    value = _receipt()
    assert value["scoped_authority"]["frozen_campaign_historical_source_history_completeness_proven"] is True
    assert value["scoped_authority"]["frozen_campaign_historical_adapter_approved"] is True
    assert all(flag is False for flag in value["global_authority"].values())
    capability = SOURCE_CAPABILITY_REGISTRY[q.SOURCE_NAMESPACE]
    assert capability.full_time_score is CapabilityAvailability.CONFIRMED
    assert capability.reliable_fixture_identity is CapabilityAvailability.CONFIRMED
    assert capability.historical_coverage is CapabilityAvailability.UNKNOWN


def test_pr80_source_local_semantic_equivalence_and_target_use_remain_unproven() -> None:
    value = _receipt()
    assert value["source_evidence"]["source_display_time_basis"] == "Europe/Oslo"
    assert value["source_evidence"]["pr80_source_local_semantic_equivalence"] == "UNPROVEN"
    assert value["materialization"]["pr80_source_local_semantic_equivalence_proven"] is False
    assert value["materialization"]["pr80_constructor_input_authorized"] is False
    assert "PR80_SOURCE_LOCAL_SEMANTIC_EQUIVALENCE_REMAINS_UNPROVEN" in value["handoff_constraints"]
    assert "PR80_TARGET_SPECIFIC_HISTORY_USE_REMAINS_UNREVIEWED" in value["handoff_constraints"]


def test_future_dates_remain_outside_frozen_historical_envelope() -> None:
    value = _receipt()
    assert value["source_evidence"]["historical_request_date_end"] == "2026-08-14"
    assert (
        "TARGETS_REQUIRING_DATES_AFTER_2026_08_14_REQUIRE_A_SEPARATELY_REVIEWED_CONTIGUOUS_PROSPECTIVE_EXTENSION"
        in value["handoff_constraints"]
    )


def test_downstream_safety_remains_closed_and_next_boundary_is_narrow() -> None:
    value = _receipt()
    assert all(flag is False for flag in value["safety"].values())
    assert value["next_required_boundary"] == q.NEXT_REQUIRED_BOUNDARY
    assert q.NEXT_REQUIRED_BOUNDARY == (
        "PRE_REGISTER_REVIEWED_FOTMOB_PR80_SOURCE_LOCAL_TIME_SEMANTIC_EQUIVALENCE_PROTOCOL"
    )
