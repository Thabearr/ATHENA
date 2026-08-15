"""Tests for the reviewed FotMob special-result semantics qualification receipt."""
from __future__ import annotations

import hashlib

import domain.fotmob_source_history_special_result_semantics_qualification as qualification


def _receipt() -> dict[str, object]:
    return qualification.load_fotmob_source_history_special_result_semantics_qualification_receipt()


def test_receipt_is_exact_canonical_frozen_evidence() -> None:
    raw = qualification.canonical_fotmob_source_history_special_result_semantics_qualification_receipt_bytes()
    assert len(raw) == qualification.RECEIPT_SIZE == 8_558
    assert hashlib.sha256(raw).hexdigest() == qualification.RECEIPT_SHA256
    assert qualification.RECEIPT_SHA256 == "7d6bb5c86391c45abdbb588a27325c99ebf88c4753f75c108387e2c4d3dbb99d"
    receipt = _receipt()
    assert receipt["repository_main_anchor"] == "2d66af0d176828e1a4efbea2abef6385b694330f"


def test_exact_preserved_artifact_and_projection_ancestry_are_frozen() -> None:
    source = _receipt()["source_evidence"]
    assert source["artifact_id"] == 9249856559
    assert source["artifact_sha256"] == "7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f"
    assert source["artifact_size_bytes"] == 61_886_753
    assert source["request_date_count"] == 2_205
    assert source["response_file_count"] == 4_410
    assert source["pr105_special_projection_sha256"] == "d5f70aad76424a01249365da09d450b4fb7f27f3d03ab546e8b9783784f5a96b"
    assert source["pr105_unresolved_projection_sha256"] == "153cca2a970bce982eecab45c2df5fbaf1df099d081c45f7c3195bb1580b8593"
    assert source["special_state_projection_sha256"] == qualification.SPECIAL_PROJECTION_SHA256
    assert source["special_state_projection_size_bytes"] == 211_526
    assert source["special_fixture_history_projection_sha256"] == qualification.HISTORY_PROJECTION_SHA256
    assert source["special_fixture_history_projection_size_bytes"] == 380_539


def test_six_reviewed_source_states_are_exactly_qualified() -> None:
    records = {item["state_id"]: item for item in _receipt()["class_records"]}
    assert set(records) == set(qualification.EXPECTED_CLASS_COUNTS)
    for state_id, expected in qualification.EXPECTED_CLASS_COUNTS.items():
        item = records[state_id]
        assert (
            item["observed_unique_fixture_ids"],
            item["observed_date_fixture_occurrences"],
            item["observed_capture_rows"],
            item["status_ids"],
            item["transition_fixture_id_count"],
        ) == expected
        assert item["frozen_membership_match"] is True
        assert item["history_disposition"] == qualification.HISTORY_DISPOSITION
        assert item["preservation_disposition"] == qualification.PRESERVATION_DISPOSITION


def test_pr105_terminal_and_unresolved_membership_is_not_rewritten() -> None:
    records = {item["state_id"]: item for item in _receipt()["class_records"]}
    for state_id, ids in qualification.EXPECTED_TERMINAL_IDS.items():
        assert records[state_id]["frozen_pr105_terminal_fixture_ids"] == ids
        assert records[state_id]["frozen_pr105_unresolved_fixture_ids"] == []
    for state_id, ids in qualification.EXPECTED_UNRESOLVED_IDS.items():
        assert records[state_id]["frozen_pr105_unresolved_fixture_ids"] == ids
        assert records[state_id]["frozen_pr105_terminal_fixture_ids"] == []


def test_penalty_and_nonresult_score_fields_are_dispositioned_without_coercion() -> None:
    records = {item["state_id"]: item for item in _receipt()["class_records"]}
    assert records["AFTER_PENALTIES"]["penalty_occurrences_with_both_pen_scores"] == 3
    assert records["AFTER_PENALTIES"]["penalty_occurrences_with_eliminated_team_id"] == 3
    assert records["ABANDONED"]["nonzero_score_occurrence_count"] == 15
    assert records["CANCELLED"]["nonzero_score_occurrence_count"] == 9
    assert records["POSTPONED"]["nonzero_score_occurrence_count"] == 0
    checks = _receipt()["checks"]
    assert checks["penalty_base_and_pen_score_fields_kept_separate"] is True
    assert checks["nonresult_score_scalars_not_promoted"] is True
    assert checks["special_states_excluded_from_ordinary_regulation_time_model_history"] is True


def test_same_date_pair_evidence_is_exact_and_conflict_free() -> None:
    receipt = _receipt()
    source = receipt["source_evidence"]
    checks = receipt["checks"]
    assert source["special_state_unique_fixture_id_count"] == 295
    assert source["special_state_date_fixture_occurrence_count"] == 304
    assert source["special_state_capture_observation_count"] == 608
    assert source["special_fixture_history_date_fixture_occurrence_count"] == 547
    assert checks["same_date_pair_count"] == 304
    assert checks["same_date_pair_capture_count_mismatch_count"] == 0
    assert checks["same_date_pair_semantic_or_relevant_field_conflict_count"] == 0
    assert checks["unknown_variant_count_within_special_fixture_history"] == 0


def test_cross_date_chronology_is_preserved_and_still_blocked() -> None:
    chronology = _receipt()["chronology_handoff"]
    assert chronology["rearranged_fixture_id_count"] == 250
    assert chronology["chronology_resolved"] is False
    assert chronology["collapsed_to_final_observation"] is False
    assert chronology["transition_summary"] == qualification.EXPECTED_TRANSITIONS
    assert chronology["duplicate_terminal_awarded_fixture"] == {
        "fixture_id": 3_932_603,
        "request_dates": ["20230220", "20230305"],
    }


def test_only_special_result_review_blocker_is_resolved_and_all_authority_stays_closed() -> None:
    receipt = _receipt()
    assert receipt["qualification_state"] == qualification.QUALIFICATION_STATE
    assert receipt["special_result_semantics_execution_performed"] is True
    assert receipt["special_result_semantics_qualified"] is True
    assert receipt["resolved_blocker"] == qualification.RESOLVED_BLOCKER
    assert tuple(receipt["remaining_blockers"]) == qualification.EXPECTED_REMAINING_BLOCKERS
    assert receipt["historical_coverage_proven"] is False
    assert receipt["source_history_mutation_performed"] is False
    assert receipt["competition_registry_mutation_performed"] is False
    assert receipt["source_capability_registry_mutation_performed"] is False
    assert receipt["next_required_boundary"] == qualification.NEXT_REQUIRED_BOUNDARY
    assert all(value is False for value in receipt["safety"].values())
