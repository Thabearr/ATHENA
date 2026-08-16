import hashlib

import domain.fotmob_source_history_adapter_completeness_assessment as assessment
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


def test_pr115_receipt_revalidates_exact_identity_and_primary_blocker():
    receipt = assessment.load_fotmob_source_history_adapter_completeness_assessment_receipt()
    raw = assessment.canonical_fotmob_source_history_adapter_completeness_assessment_receipt_bytes()

    assert len(raw) == assessment.RECEIPT_SIZE == 6634
    assert hashlib.sha256(raw).hexdigest() == assessment.RECEIPT_SHA256
    assert receipt["assessment_state"] == assessment.ASSESSMENT_STATE
    assert receipt["primary_status"] == "BLOCKED_RESULT_EVIDENCE_GAP"
    assert receipt["remaining_blockers"] == [
        "BLOCKED_RESULT_EVIDENCE_GAP",
        "BLOCKED_HISTORICAL_COVERAGE_UNPROVEN",
    ]
    assert receipt["next_required_boundary"] == assessment.NEXT_REQUIRED_BOUNDARY


def test_pr115_preserved_campaign_is_complete_but_prospective_adapter_is_not_history_compatible():
    receipt = assessment.load_fotmob_source_history_adapter_completeness_assessment_receipt()
    checks = receipt["campaign_checks"]
    adapter = receipt["adapter_compatibility"]

    assert checks["request_date_count"] == 2205
    assert checks["capture_manifest_count"] == 4410
    assert checks["distinct_manifest_pair_count"] == 2205
    assert checks["target_family_fixture_date_pair_count"] == 21640
    assert checks["target_family_raw_capture_row_count"] == 43280
    assert checks["same_date_target_relevant_field_conflict_count"] == 0
    assert checks["source_display_time_basis"] == "Europe/Oslo"
    assert checks["source_display_time_basis_mismatch_count"] == 0

    assert adapter["identical_raw_sha256_pair_count"] == 2204
    assert adapter["distinct_raw_sha256_pair_count"] == 1
    assert adapter["distinct_raw_sha256_pair_dates"] == ["20250712"]
    assert adapter["identical_raw_exemplar_adapter_status"] == (
        "BLOCKED_CAPTURE_LINEAGE_OR_REQUEST_IDENTITY"
    )
    assert adapter["ordinary_ft_candidates_blocked_by_identical_raw_lineage_requirement"] == 21326
    assert adapter["distinct_raw_pair_adapter_results"] == [
        {
            "adapter_status": "BLOCKED_STRUCTURAL_REVALIDATION",
            "error_message": "capture pair failed the reviewed PR89 structural chain",
            "outcome": "BLOCKED",
            "request_date": "20250712",
        }
    ]


def test_pr115_closes_pr114_accounting_without_authorizing_rows():
    receipt = assessment.load_fotmob_source_history_adapter_completeness_assessment_receipt()
    checks = receipt["campaign_checks"]

    assert (
        checks["preboundary_ordinary_ft_fixture_date_occurrence_count"]
        + checks["reviewed_ordinary_ft_candidate_count_on_or_after_floor"]
        + checks["special_state_occurrence_count_on_or_after_floor"]
        == checks["target_family_fixture_date_pair_count"]
    )
    assert checks["reviewed_ordinary_ft_candidate_count_on_or_after_floor"] == 21326
    assert receipt["history_rows_materialized"] == 0
    assert receipt["ordinary_ft_history_rows_authorized"] is False
    assert receipt["source_history_adapter_approved"] is False
    assert receipt["source_history_completeness_proven"] is False
    assert receipt["historical_coverage_proven"] is False


def test_pr115_all_downstream_safety_remains_false_and_registry_is_unchanged():
    receipt = assessment.load_fotmob_source_history_adapter_completeness_assessment_receipt()
    assert receipt["safety"]
    assert all(value is False for value in receipt["safety"].values())

    derived = SOURCE_CAPABILITY_REGISTRY[
        "fotmob_data_matches_reviewed_ordinary_ft_finished_score"
    ]
    assert derived.full_time_score is CapabilityAvailability.CONFIRMED
    assert derived.reliable_fixture_identity is CapabilityAvailability.CONFIRMED
    assert derived.historical_coverage is CapabilityAvailability.UNKNOWN


def test_pr115_only_two_result_evidence_gates_are_blocked():
    receipt = assessment.load_fotmob_source_history_adapter_completeness_assessment_receipt()
    blocked = [item for item in receipt["gate_results"] if item["outcome"] == "BLOCKED"]
    assert [item["gate_id"] for item in blocked] == [
        "REUSABLE_ORDINARY_FT_ADAPTER_PAIR_LINEAGE",
        "REUSABLE_ORDINARY_FT_ADAPTER_HISTORICAL_SCHEMA",
    ]
    assert all(item["status"] == "BLOCKED_RESULT_EVIDENCE_GAP" for item in blocked)
