"""Tests for the reviewed FotMob rearrangement-chronology qualification receipt."""
from __future__ import annotations

import hashlib

import domain.fotmob_source_history_rearrangement_chronology_qualification as qualification
import domain.fotmob_source_history_rearrangement_chronology_semantics_protocol as pr111
import domain.fotmob_source_history_special_result_semantics_qualification as pr110


def _receipt() -> dict[str, object]:
    return qualification.load_fotmob_source_history_rearrangement_chronology_qualification_receipt()


def test_receipt_is_exact_canonical_frozen_evidence() -> None:
    value = _receipt()
    raw = qualification.canonical_fotmob_source_history_rearrangement_chronology_qualification_receipt_bytes()
    assert len(raw) == qualification.RECEIPT_SIZE == 7_980
    assert hashlib.sha256(raw).hexdigest() == qualification.RECEIPT_SHA256
    assert qualification.RECEIPT_SHA256 == (
        "58c7a275580cc74489269a66de2836544e78ca232693d5283f1813ee817d3fc0"
    )
    assert value["repository_main_anchor"] == (
        "9c156e6022b0034dfe16e0d9446b4e1890f53753"
    )


def test_exact_pr111_protocol_and_pr110_receipt_ancestry_are_bound() -> None:
    value = _receipt()
    assert value["protocol"] == {
        "protocol_id": pr111.PROTOCOL_ID,
        "blob_sha": "58eb56a6c55048cb163b7611da7ef85468c91f9a",
        "canonical_sha256": pr111.PROTOCOL_SHA256,
        "canonical_size_bytes": pr111.PROTOCOL_SIZE,
    }
    source = value["source_evidence"]
    assert source["pr110_receipt_sha256"] == pr110.RECEIPT_SHA256
    assert source["pr110_receipt_size_bytes"] == pr110.RECEIPT_SIZE
    assert source["pr110_special_fixture_history_projection_sha256"] == (
        pr110.HISTORY_PROJECTION_SHA256
    )
    assert source["pr110_special_fixture_history_projection_size_bytes"] == (
        pr110.HISTORY_PROJECTION_SIZE
    )


def test_rearranged_and_edge_projections_are_exact() -> None:
    source = _receipt()["source_evidence"]
    assert source["rearranged_fixture_history_projection_sha256"] == (
        "9fa899ebeb0e42154832c1ca9dc040685a359add2a4cf7c1029fd13b7d56dbe8"
    )
    assert source["rearranged_fixture_history_projection_size_bytes"] == 349_277
    assert source["rearrangement_edge_projection_sha256"] == (
        "2c85f3ccfa4fd34af928c339ec6ebc79048ed3a5252f88bb195b77fb61bb13b9"
    )
    assert source["rearrangement_edge_projection_size_bytes"] == 90_086
    assert source["request_date_count"] == 2_205
    assert source["response_file_count"] == 4_410


def test_exact_chronology_counts_and_zero_conflicts_are_qualified() -> None:
    checks = _receipt()["checks"]
    assert checks["rearranged_fixture_id_count"] == 250
    assert checks["rearranged_fixture_date_occurrence_count"] == 502
    assert checks["raw_same_date_capture_observation_count"] == 1_004
    assert checks["same_date_pair_count"] == 502
    assert checks["cross_date_transition_edge_count"] == 252
    for key in (
        "same_date_pair_capture_count_mismatch_count",
        "same_date_pair_relevant_field_conflict_count",
        "cross_date_static_identity_drift_count",
        "request_date_kickoff_utc_date_mismatch_count",
        "non_forward_kickoff_revision_edge_count",
        "unknown_transition_pattern_count",
    ):
        assert checks[key] == 0
    assert checks["exact_six_transition_patterns_observed"] is True
    assert checks["exact_terminal_state_counts_observed"] is True
    assert checks["all_raw_and_fixture_date_evidence_preserved"] is True
    assert checks["destructive_collapse_performed"] is False
    assert (
        checks["real_world_resume_replay_restart_continuation_inference_performed"]
        is False
    )


def test_occurrence_state_counts_are_exact_for_the_250_lineages() -> None:
    assert _receipt()["occurrence_state_counts"] == {
        "POSTPONED": 239,
        "ABANDONED": 7,
        "CANCELLED": 5,
        "ORDINARY_FT": 243,
        "AWARDED_WIN": 8,
    }


def test_exact_six_transition_patterns_and_membership_partition_are_preserved() -> None:
    records = _receipt()["transition_records"]
    assert [(item["pattern"], item["fixture_id_count"]) for item in records] == [
        (["POSTPONED", "ORDINARY_FT"], 234),
        (["ABANDONED", "ORDINARY_FT"], 7),
        (["CANCELLED", "AWARDED_WIN"], 5),
        (["POSTPONED", "POSTPONED", "ORDINARY_FT"], 2),
        (["POSTPONED", "AWARDED_WIN"], 1),
        (["AWARDED_WIN", "AWARDED_WIN"], 1),
    ]
    all_ids = [fixture_id for item in records for fixture_id in item["fixture_ids"]]
    assert len(all_ids) == len(set(all_ids)) == 250
    assert sum(item["transition_edge_count"] for item in records) == 252
    assert all(item["fixture_ids"] == sorted(item["fixture_ids"]) for item in records)

    by_pattern = {tuple(item["pattern"]): item for item in records}
    assert by_pattern[("AWARDED_WIN", "AWARDED_WIN")]["fixture_ids"] == [3_932_603]
    assert by_pattern[("POSTPONED", "AWARDED_WIN")]["fixture_ids"] == [3_932_609]
    assert by_pattern[("CANCELLED", "AWARDED_WIN")]["fixture_ids"] == [
        3_932_614,
        3_932_617,
        3_932_647,
        3_932_653,
        3_932_663,
    ]


def test_terminal_dispositions_do_not_materialize_model_history() -> None:
    value = _receipt()
    terminal = value["terminal_summary"]
    assert terminal == {
        "ordinary_ft_fixture_count": 243,
        "awarded_win_fixture_count": 7,
        "ordinary_ft_history_rows_authorized": False,
        "awarded_win_history_rows_authorized": False,
        "duplicate_terminal_awarded_fixture": {
            "fixture_id": 3_932_603,
            "request_dates": ["20230220", "20230305"],
        },
    }
    records = value["transition_records"]
    ordinary = [item for item in records if item["terminal_state"] == "ORDINARY_FT"]
    awarded = [item for item in records if item["terminal_state"] == "AWARDED_WIN"]
    assert sum(item["fixture_id_count"] for item in ordinary) == 243
    assert sum(item["fixture_id_count"] for item in awarded) == 7
    assert all(
        item["terminal_disposition"].startswith("EXCLUDE_FROM_ORDINARY_REGULATION_TIME_MODEL_HISTORY")
        for item in awarded
    )


def test_chronology_blocker_only_is_resolved_and_downstream_remains_fail_closed() -> None:
    value = _receipt()
    assert value["qualification_state"] == (
        "EXECUTED_REARRANGEMENT_CHRONOLOGY_QUALIFIED_HISTORY_MATERIALIZATION_UNREVIEWED"
    )
    assert value["chronology_semantics_execution_performed"] is True
    assert value["rearrangement_chronology_qualified"] is True
    assert value["resolved_blocker"] == "BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT"
    assert value["remaining_blockers"] == [
        "BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN",
        "BLOCKED_HISTORICAL_COVERAGE_UNPROVEN",
    ]
    assert value["source_history_mutation_performed"] is False
    assert value["historical_coverage_proven"] is False
    assert value["source_capability_registry_mutation_performed"] is False
    assert value["competition_registry_mutation_performed"] is False
    assert value["next_required_boundary"] == (
        "PRE_REGISTER_REVIEWED_FOTMOB_SOURCE_HISTORY_ELO_INITIALIZATION_BOUNDARY_PROTOCOL"
    )
    assert all(flag is False for flag in value["safety"].values())
