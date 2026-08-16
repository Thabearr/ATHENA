"""Tests for the exact PR #117 historical source-history adapter qualification."""
from __future__ import annotations

import hashlib

import domain.fotmob_historical_source_history_adapter_protocol as pr116
import domain.fotmob_historical_source_history_adapter_qualification as qualification


def _receipt() -> dict[str, object]:
    return qualification.load_fotmob_historical_source_history_adapter_qualification_receipt()


def test_receipt_is_exact_canonical_frozen_identity() -> None:
    raw = qualification.canonical_fotmob_historical_source_history_adapter_qualification_receipt_bytes()
    assert len(raw) == qualification.RECEIPT_SIZE == 5_081
    assert hashlib.sha256(raw).hexdigest() == qualification.RECEIPT_SHA256
    assert qualification.RECEIPT_SHA256 == (
        "a8f06a9d789b20b4ef49766bd771fb5c4d13c4be657ac6a5fc8f284701054020"
    )
    assert _receipt()["repository_main_anchor"] == (
        "cbebb42393be50c77011463906b5d2b70e0ef2c5"
    )


def test_exact_pr116_protocol_is_the_qualification_contract() -> None:
    receipt = _receipt()
    protocol = receipt["protocol"]
    assert protocol["protocol_id"] == pr116.PROTOCOL_ID
    assert protocol["blob_sha"] == "53682e3810bf3c06b1afc90b847361b6dcb3e04f"
    assert protocol["canonical_sha256"] == pr116.PROTOCOL_SHA256
    assert protocol["canonical_size_bytes"] == pr116.PROTOCOL_SIZE == 9_898


def test_historical_pair_lineage_does_not_fake_distinct_raw_content() -> None:
    adapter = _receipt()["adapter_qualification"]
    assert adapter["request_date_count"] == 2_205
    assert adapter["capture_manifest_count"] == 4_410
    assert adapter["distinct_manifest_pair_count"] == 2_205
    assert adapter["identical_raw_sha256_pair_count"] == 2_204
    assert adapter["distinct_raw_sha256_pair_count"] == 1
    assert adapter["distinct_raw_sha256_pair_dates"] == ["20250712"]
    assert adapter["target_family_pairs_on_distinct_raw_dates"] == 0
    checks = _receipt()["checks"]
    assert checks["raw_or_manifest_hash_synthesis_performed"] is False
    assert checks["all_raw_capture_evidence_preserved"] is True


def test_exact_historical_structural_chain_passes_for_all_ordinary_candidates() -> None:
    checks = _receipt()["checks"]
    assert checks["historical_halfs_keyset_mismatch_count"] == 0
    assert checks["historical_halfs_type_mismatch_count"] == 0
    assert checks["historical_halfs_parse_mismatch_count"] == 0
    assert checks["source_display_time_basis"] == "Europe/Oslo"
    assert checks["source_display_time_basis_mismatch_count"] == 0
    assert checks["same_date_target_relevant_field_conflict_count"] == 0


def test_ordinary_projection_is_exact_and_not_materialized_history() -> None:
    receipt = _receipt()
    adapter = receipt["adapter_qualification"]
    assert adapter["qualification_status"] == qualification.QUALIFICATION_STATUS
    assert adapter["ordinary_ft_projection_record_count"] == 21_336
    assert adapter["ordinary_ft_unique_source_fixture_id_count"] == 21_336
    assert adapter["ordinary_ft_duplicate_source_fixture_id_count"] == 0
    assert adapter["ordinary_ft_projection_sha256"] == qualification.ORDINARY_FT_PROJECTION_SHA256
    assert adapter["ordinary_ft_projection_size_bytes"] == qualification.ORDINARY_FT_PROJECTION_SIZE
    assert adapter["ordinary_ft_projection_raw_content_relation"] == (
        "BYTE_IDENTICAL_FOR_ALL_21336_RECORDS"
    )
    assert receipt["history_rows_materialized"] == 0
    assert receipt["ordinary_ft_history_rows_authorized"] is False


def test_pr114_floor_split_and_all_eleven_family_counts_are_exact() -> None:
    checks = _receipt()["checks"]
    assert checks["preboundary_ordinary_ft_occurrence_count"] == 10
    assert checks["on_or_after_floor_ordinary_ft_occurrence_count"] == 21_326
    assert checks["ordinary_ft_candidates_by_model_league"] == qualification.EXPECTED_BY_LEAGUE
    assert sum(checks["ordinary_ft_candidates_by_model_league"].values()) == 21_326


def test_all_304_special_occurrences_remain_reviewed_and_excluded() -> None:
    receipt = _receipt()
    adapter = receipt["adapter_qualification"]
    checks = receipt["checks"]
    assert adapter["target_family_fixture_date_pair_count"] == 21_640
    assert adapter["ordinary_ft_projection_record_count"] == 21_336
    assert adapter["reviewed_special_state_occurrence_count"] == 304
    assert 21_336 + 304 == 21_640
    assert checks["special_state_occurrence_counts"] == qualification.EXPECTED_SPECIAL_COUNTS
    assert checks["unreviewed_target_state_occurrence_count"] == 0


def test_only_adapter_gap_is_resolved_and_historical_coverage_remains_blocked() -> None:
    receipt = _receipt()
    assert receipt["historical_adapter_execution_performed"] is True
    assert receipt["historical_source_history_adapter_qualified"] is True
    assert receipt["resolved_blocker"] == "BLOCKED_RESULT_EVIDENCE_GAP"
    assert receipt["remaining_blockers"] == ["BLOCKED_HISTORICAL_COVERAGE_UNPROVEN"]
    assert receipt["source_history_adapter_approved"] is False
    assert receipt["source_history_completeness_proven"] is False
    assert receipt["historical_coverage_proven"] is False


def test_prospective_adapter_and_all_downstream_authority_remain_untouched() -> None:
    receipt = _receipt()
    checks = receipt["checks"]
    assert checks["prospective_adapter_mutation_performed"] is False
    assert checks["pr89_mutation_performed"] is False
    assert checks["network_acquisition_performed"] is False
    assert receipt["source_history_mutation_performed"] is False
    assert receipt["source_capability_registry_mutation_performed"] is False
    assert receipt["competition_registry_mutation_performed"] is False
    assert all(flag is False for flag in receipt["safety"].values())


def test_next_boundary_requires_separate_completeness_and_materialization_protocol() -> None:
    receipt = _receipt()
    assert receipt["next_required_boundary"] == qualification.NEXT_REQUIRED_BOUNDARY
    assert qualification.NEXT_REQUIRED_BOUNDARY == (
        "PRE_REGISTER_REVIEWED_FOTMOB_HISTORICAL_SOURCE_HISTORY_COMPLETENESS_AND_MATERIALIZATION_PROTOCOL"
    )
