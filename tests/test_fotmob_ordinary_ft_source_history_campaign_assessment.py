from __future__ import annotations

import hashlib
import json
from pathlib import Path


RECEIPT_PATH = Path(
    "artifacts/research-manifests/"
    "fotmob-ordinary-ft-source-history-campaign-assessment-v1.json"
)
DOC_PATH = Path("docs/fotmob_ordinary_ft_source_history_campaign_assessment.md")
EXPECTED_RECEIPT_SHA256 = "5b5333476c7e5742820f9d03fbe8ab70632354befa2ae315ed2c0cd4e47bcacd"
EXPECTED_RECEIPT_SIZE = 5648
EXPECTED_ARTIFACT_SHA256 = "7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f"
EXPECTED_RESEARCH_CACHE_TAR_SHA256 = "cbe665315258f7820e87265434d7a864c8e909cfb2e51950c56ed349860af5f6"
EXPECTED_LEAGUES = {"B1", "D1", "E0", "F1", "G1", "I1", "N1", "P1", "SC0", "SP1", "T1"}


def _load() -> tuple[bytes, dict]:
    raw = RECEIPT_PATH.read_bytes()
    return raw, json.loads(raw)


def test_campaign_assessment_receipt_is_exact_canonical_json() -> None:
    raw, receipt = _load()
    canonical = (
        json.dumps(
            receipt,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")

    assert raw == canonical
    assert len(raw) == EXPECTED_RECEIPT_SIZE
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_RECEIPT_SHA256
    assert receipt["schema_version"] == 1
    assert receipt["dataset_name"] == (
        "athena-fotmob-ordinary-ft-source-history-campaign-assessment-receipt-v1"
    )
    assert receipt["assessment_state"] == (
        "EXECUTED_FAIL_CLOSED_HISTORICAL_COVERAGE_NOT_QUALIFIED"
    )
    assert receipt["primary_status"] == "BLOCKED_HISTORICAL_COVERAGE_UNPROVEN"


def test_execution_and_artifact_are_pinned_to_the_exact_reviewed_campaign() -> None:
    _, receipt = _load()
    execution = receipt["execution"]
    assert execution == {
        "authorized_main_sha": "12a32de1cca8ffb657f67fa4a8d3106aec6ce31b",
        "github_run_attempt": 1,
        "github_run_id": 31887523012,
        "runner_exit_code": 0,
        "status_exit_code": 0,
        "workflow_result_state": "EXECUTION_COMPLETED_4410_SLOTS_EVIDENCE_ARTIFACT_PRESERVED",
        "workflow_verification_outcome": "success",
    }

    artifact = receipt["artifact"]
    assert artifact["artifact_id"] == 9249856559
    assert artifact["artifact_name"] == "fotmob-ordinary-ft-source-history-campaign-31887523012"
    assert artifact["artifact_size_bytes"] == 61_886_753
    assert artifact["artifact_digest_sha256"] == EXPECTED_ARTIFACT_SHA256
    assert artifact["research_cache_tar_sha256"] == EXPECTED_RESEARCH_CACHE_TAR_SHA256


def test_acquisition_integrity_passes_without_promoting_historical_coverage() -> None:
    _, receipt = _load()
    integrity = receipt["acquisition_integrity"]
    assert integrity["required_request_start_date"] == "2020-08-01"
    assert integrity["required_request_end_date"] == "2026-08-14"
    assert integrity["required_date_count"] == 2205
    assert integrity["successful_slot_count"] == 4410
    assert integrity["slot_a_count"] == 2205
    assert integrity["slot_b_count"] == 2205
    assert integrity["dates_with_exactly_two_successful_slots"] == 2205
    assert integrity["failed_attempt_count"] == 0
    assert integrity["attempt_numbers_observed"] == [1]
    assert 300 <= integrity["pair_separation_min_seconds"] <= integrity["pair_separation_max_seconds"] <= 86400
    assert integrity["request_timezone"] == "UTC"
    assert integrity["ccode3"] == "NGA"
    assert integrity["unresolved_inflight_attempt"] is False
    assert integrity["stale_runner_lock"] is False
    assert integrity["historical_coverage_proven_by_runner"] is False

    assert receipt["gates"]["campaign_execution_integrity"] == "PASSED"
    assert receipt["gates"]["required_daily_request_schedule"] == "PASSED"
    assert receipt["gates"]["historical_coverage"] == "BLOCKED_HISTORICAL_COVERAGE_UNPROVEN"


def test_real_corpus_discovery_preserves_mapping_and_special_result_blockers() -> None:
    _, receipt = _load()
    mapping = receipt["league_mapping_discovery"]
    assert set(mapping["frozen_model_league_codes"]) == EXPECTED_LEAGUES
    assert set(mapping["frozen_candidate_root_ids"]) == EXPECTED_LEAGUES
    assert mapping["all_eleven_candidate_root_ids_observed_as_primary_id"] is True
    assert mapping["exact_leaf_id_is_not_stable_for_all_eleven"] is True
    assert mapping["qualification"] == "BLOCKED_LEAGUE_MAPPING_UNPROVEN"
    assert mapping["season_specific_leaf_id_examples"]["B1"] == [868627, 873802, 880058]
    assert mapping["season_specific_leaf_id_examples"]["G1"] == [869504, 874482, 880600]
    assert mapping["season_specific_leaf_id_examples"]["N1"] == [868558, 873789, 879842]
    assert mapping["season_specific_leaf_id_examples"]["SC0"] == [873849, 879858, 886197]

    terminal = receipt["target_family_terminal_discovery"]
    assert terminal["grouping_semantics"].startswith("DISCOVERY_ONLY_")
    assert terminal["unique_terminal_fixture_count"] == 21_367
    assert terminal["unique_ordinary_ft_qualified_fixture_count"] == 21_336
    assert terminal["unique_non_ordinary_or_unreviewed_fixture_count"] == 31
    assert sum(terminal["ordinary_ft_qualified_by_model_league"].values()) == 21_336
    assert terminal["non_ordinary_unique_reason_counts"] == {
        "AFTER_EXTRA_TIME": 3,
        "AFTER_PENALTIES": 3,
        "AWARDED_WIN": 25,
    }
    assert sum(terminal["non_ordinary_unique_by_model_league"].values()) == 31
    assert terminal["qualification"] == (
        "BLOCKED_NON_ORDINARY_FT_RESULT_REQUIRES_SEPARATE_REVIEW"
    )


def test_pair_drift_is_bounded_and_identity_chronology_conflict_remains_visible() -> None:
    _, receipt = _load()
    pair = receipt["pair_stability_discovery"]
    assert pair["raw_identical_date_pair_count"] == 2204
    assert pair["raw_nonidentical_date_pair_count"] == 1
    assert pair["raw_nonidentical_request_dates"] == ["2025-07-12"]
    assert pair["nonidentical_pair_target_family_terminal_set_drift_count"] == 0

    chronology = receipt["identity_chronology_discovery"]
    assert chronology["cross_request_date_duplicate_fixture_id_count"] == 1
    assert chronology["conflicting_fixture_id"] == 3932603
    assert chronology["conflicting_model_league_candidate"] == "T1"
    assert chronology["first_request_date"] == "2023-02-20"
    assert chronology["first_kickoff_utc"] == "2023-02-20T17:00:00.000Z"
    assert chronology["second_request_date"] == "2023-03-05"
    assert chronology["second_kickoff_utc"] == "2023-03-05T17:00:00.000Z"
    assert chronology["qualification"] == "BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT"


def test_initialization_and_all_downstream_authority_remain_fail_closed() -> None:
    _, receipt = _load()
    initialization = receipt["initialization_boundary"]
    assert initialization["campaign_start_is_only_candidate_lower_bound"] is True
    assert initialization["equivalence_to_pr69_proven"] is False
    assert initialization["qualification"] == "BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN"

    gates = receipt["gates"]
    assert gates["eleven_league_mapping"] == "BLOCKED_LEAGUE_MAPPING_UNPROVEN"
    assert gates["elo_initialization_boundary"] == "BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN"
    assert gates["non_ordinary_ft_result_states"] == (
        "BLOCKED_NON_ORDINARY_FT_RESULT_REQUIRES_SEPARATE_REVIEW"
    )
    assert gates["identity_and_chronology"] == "BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT"

    assert all(value is False for value in receipt["safety"].values())
    assert receipt["safety"]["source_history_completeness_proven"] is False
    assert receipt["safety"]["historical_coverage_promoted"] is False
    assert receipt["safety"]["source_capability_registry_update_performed"] is False
    assert receipt["safety"]["probability_inference_authorized"] is False
    assert receipt["safety"]["pricing_authorized"] is False
    assert receipt["safety"]["selection_authorized"] is False
    assert receipt["safety"]["bet_authorized"] is False


def test_documentation_preserves_fail_closed_interpretation_and_next_boundaries() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")
    assert "acquisition success is not historical-completeness approval" in text
    assert "BLOCKED_LEAGUE_MAPPING_UNPROVEN" in text
    assert "BLOCKED_NON_ORDINARY_FT_RESULT_REQUIRES_SEPARATE_REVIEW" in text
    assert "BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT" in text
    assert "BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN" in text
    assert "does not update `SOURCE_CAPABILITY_REGISTRY`" in text
    assert "does not promote `historical_coverage`" in text
    assert "does not authorize" in text
