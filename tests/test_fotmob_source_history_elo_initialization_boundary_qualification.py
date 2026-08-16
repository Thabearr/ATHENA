"""Tests for the exact PR #114 Elo-initialization qualification receipt."""
from __future__ import annotations

import hashlib

import domain.fotmob_source_history_elo_initialization_boundary_protocol as pr113
import domain.fotmob_source_history_elo_initialization_boundary_qualification as qualification


def _receipt() -> dict:
    return qualification.load_fotmob_source_history_elo_initialization_boundary_qualification_receipt()


def test_receipt_is_exact_canonical_execution_artifact() -> None:
    raw = qualification.canonical_fotmob_source_history_elo_initialization_boundary_qualification_receipt_bytes()
    assert len(raw) == qualification.RECEIPT_SIZE == 24_428
    assert hashlib.sha256(raw).hexdigest() == qualification.RECEIPT_SHA256
    assert qualification.RECEIPT_SHA256 == (
        "fbbec0b858c3e9630d9f4c7dec630012f57811de52d300db3a11b781a719e110"
    )


def test_exact_pr113_execution_boundary_and_status_are_preserved() -> None:
    receipt = _receipt()
    assert receipt["protocol"]["protocol_id"] == pr113.PROTOCOL_ID
    assert receipt["protocol"]["canonical_sha256"] == pr113.PROTOCOL_SHA256
    assert receipt["initialization_boundary_execution_performed"] is True
    assert receipt["initialization_boundary_qualified"] is True
    assert receipt["qualification_status"] == (
        "QUALIFIED_PR69_EQUIVALENT_EMPTY_1500_INITIALIZATION_BOUNDARY"
    )


def test_pr69_exact_66_file_rebuild_is_reproduced() -> None:
    checks = _receipt()["pr69_rebuild"]["checks"]
    assert checks == {
        "canonical_replay_sha256": "b44166b9543a8f436e62a644efc5316ad12fcc260a4c2c5908ad112928bedfe3",
        "canonical_replay_size_bytes": 39_952_730,
        "fixture_count": 21_226,
        "source_corpus_sha256": "c273b4bff2b611e95248133340ff84803ce238814d5dfa7ded5f39fd3d6e25a0",
        "source_file_count": 66,
        "source_total_bytes": 10_006_877,
    }
    source_hashes = _receipt()["pr69_rebuild"]["source_file_sha256"]
    assert len(source_hashes) == 66


def test_exact_eleven_reference_floors_are_independently_derived() -> None:
    witness = _receipt()["pr69_rebuild"]["reference_floor_witness"]
    assert {code: row["reference_floor_source_local_date"] for code, row in witness.items()} == (
        qualification.EXPECTED_FLOORS
    )
    assert qualification.EXPECTED_FLOORS["SC0"] == "2020-08-01"
    assert qualification.EXPECTED_FLOORS["I1"] == "2020-09-19"


def test_campaign_start_is_not_silently_used_as_every_league_floor() -> None:
    floors = set(qualification.EXPECTED_FLOORS.values())
    assert len(floors) > 1
    assert "2020-08-01" in floors
    assert "2020-09-19" in floors
    assert _receipt()["reference_floor_granularity"] == (
        "PR69_SOURCE_LOCAL_CALENDAR_DATE_VS_FOTMOB_REQUEST_DATE_ONLY"
    )


def test_italy_preboundary_evidence_is_preserved_but_never_seeds_state() -> None:
    families = {
        row["model_league_code"]: row
        for row in _receipt()["fotmob_boundary_assessment"]["families"]
    }
    italy = families["I1"]
    assert italy["fotmob_preboundary_fixture_date_occurrence_count"] == 10
    assert italy["fotmob_preboundary_raw_capture_row_count"] == 20
    assert italy["fotmob_preboundary_unique_fixture_id_count"] == 10
    assert italy["preboundary_rows_used_to_seed_or_update_state"] == 0
    assert [
        code
        for code, row in families.items()
        if row["fotmob_preboundary_fixture_date_occurrence_count"]
    ] == ["I1"]


def test_fotmob_target_family_accounting_closes_without_unreviewed_residual_state() -> None:
    checks = _receipt()["fotmob_boundary_assessment"]["checks"]
    assert checks["target_family_fixture_date_pair_count"] == 21_640
    assert checks["target_family_raw_capture_row_count"] == 43_280
    assert checks["preboundary_fixture_date_occurrence_count"] == 10
    assert checks["reviewed_ordinary_ft_candidate_count_on_or_after_floor"] == 21_326
    assert checks["special_state_occurrence_count_on_or_after_floor"] == 304
    assert 10 + 21_326 + 304 == 21_640
    assert checks["target_family_projection_sha256"] == (
        "e98715f599fd9495f7a606e0a05a07bdc56781d35ba497522610efdab775c0b9"
    )


def test_all_initialization_violation_counts_are_zero() -> None:
    checks = _receipt()["fotmob_boundary_assessment"]["checks"]
    for key in (
        "malformed_fixture_identity_count",
        "out_of_universe_state_update_count",
        "preboundary_state_leakage_count",
        "same_date_pair_cardinality_mismatch_count",
        "same_date_pair_relevant_field_conflict_count",
        "season_reset_count",
        "special_or_nonordinary_state_update_count",
        "static_fixture_identity_drift_count",
        "team_identity_violation_count",
    ):
        assert checks[key] == 0
    assert checks["all_eleven_reference_floors_have_reviewed_result_evidence"] is True


def test_first_seen_seed_and_cross_season_state_lifetime_witness_are_frozen() -> None:
    checks = _receipt()["fotmob_boundary_assessment"]["checks"]
    assert checks["first_seen_team_seed_count"] == 282
    assert checks["reused_team_state_observation_count"] == 42_370
    for row in _receipt()["fotmob_boundary_assessment"]["families"]:
        assert row["initial_rating"] == 1500
        assert row["initial_matches"] == 0
        assert row["season_reset_count"] == 0
        assert row["first_seen_team_seed_count"] == row["source_scoped_team_id_count_in_candidate_stream"]


def test_initialization_blocker_only_is_resolved() -> None:
    receipt = _receipt()
    assert receipt["resolved_blocker"] == "BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN"
    assert receipt["remaining_blockers"] == ["BLOCKED_HISTORICAL_COVERAGE_UNPROVEN"]
    assert receipt["historical_coverage_proven"] is False
    assert receipt["ordinary_ft_history_rows_authorized"] is False
    assert receipt["next_required_boundary"] == (
        "EXECUTE_REVIEWED_SOURCE_HISTORY_ADAPTER_AND_COMPLETENESS_ASSESSMENT"
    )


def test_no_cross_source_equivalence_or_downstream_authority_is_created() -> None:
    receipt = _receipt()
    assert receipt["cross_source_fixture_identity_inferred"] is False
    assert receipt["cross_source_team_identity_inferred"] is False
    assert receipt["cross_source_numeric_elo_equivalence_claimed"] is False
    assert receipt["source_history_mutation_performed"] is False
    assert receipt["source_capability_registry_mutation_performed"] is False
    assert receipt["competition_registry_mutation_performed"] is False
    assert all(value is False for value in receipt["safety"].values())
    for key in (
        "source_history_adapter_approved",
        "source_history_completeness_proven",
        "model_training_authorized",
        "probability_inference_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
    ):
        assert receipt["safety"][key] is False
