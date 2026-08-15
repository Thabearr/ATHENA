"""Canonical evidence checks for the FotMob 4,410-capture completeness receipt."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import domain.fotmob_ordinary_ft_source_history_acquisition_protocol as pr101


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = (
    REPOSITORY_ROOT
    / "artifacts"
    / "research-manifests"
    / "fotmob-ordinary-ft-source-history-campaign-completeness-receipt-v1.json"
)
RECEIPT_SHA256 = "a8c5a704e06853d6debfc029653132ca201b98c1fc8a32b3e3095db18f8e1363"
RECEIPT_SIZE = 11995
QUALIFIED_ROW_PROJECTION_SHA256 = (
    "5cec30f37dd58f654c94f4fb9190a7098683cee0d1ab073e179e6177b37ec8c8"
)


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def _receipt() -> tuple[dict[str, object], bytes]:
    raw = RECEIPT_PATH.read_bytes()
    return json.loads(raw), raw


def _gates(receipt: dict[str, object]) -> dict[str, dict[str, object]]:
    return {gate["gate_id"]: gate for gate in receipt["gates"]}


def test_receipt_is_exact_canonical_frozen_evidence() -> None:
    receipt, raw = _receipt()
    assert raw == _canonical_bytes(receipt)
    assert len(raw) == RECEIPT_SIZE
    assert hashlib.sha256(raw).hexdigest() == RECEIPT_SHA256
    assert receipt["schema_version"] == 1
    assert receipt["dataset_name"] == (
        "athena-fotmob-ordinary-ft-source-history-campaign-completeness-receipt-v1"
    )
    assert receipt["scope"] == (
        "IMMUTABLE_EXECUTION_RECEIPT_AND_FAIL_CLOSED_SOURCE_HISTORY_COMPLETENESS_ASSESSMENT_ONLY"
    )
    assert receipt["repository_main_anchor"] == (
        "12a32de1cca8ffb657f67fa4a8d3106aec6ce31b"
    )


def test_execution_and_artifact_ancestry_are_exact() -> None:
    receipt, _ = _receipt()
    execution = receipt["execution"]
    artifact = receipt["artifact"]

    assert execution == {
        "artifact_upload_outcome": "success",
        "attempt_marker_comment_id": 5302463691,
        "authorization_comment_id": 5302462991,
        "authorized_main_sha": "12a32de1cca8ffb657f67fa4a8d3106aec6ce31b",
        "control_pr_number": 103,
        "github_job_id": 95018889294,
        "github_run_id": 31887523012,
        "package_outcome": "success",
        "result_comment_id": 5303209973,
        "runner_exit_code": 0,
        "status_exit_code": 0,
        "verification_outcome": "success",
    }
    assert artifact["artifact_id"] == 9249856559
    assert artifact["artifact_name"] == (
        "fotmob-ordinary-ft-source-history-campaign-31887523012"
    )
    assert artifact["artifact_size_bytes"] == 61_886_753
    assert artifact["artifact_sha256"] == (
        "7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f"
    )
    assert artifact["research_cache_tar_gz_size_bytes"] == 61_881_610
    assert artifact["research_cache_tar_gz_sha256"] == (
        "cbe665315258f7820e87265434d7a864c8e909cfb2e51950c56ed349860af5f6"
    )
    assert artifact["campaign_index_size_bytes"] == 3_316_829
    assert artifact["campaign_index_sha256"] == (
        "f0b74711d9df352c5f845838014f72df96eeed0efa3c2740db7b7efb5818be1a"
    )


def test_campaign_integrity_is_complete_without_claiming_history_completeness() -> None:
    receipt, _ = _receipt()
    campaign = receipt["campaign"]

    assert (campaign["request_timezone"], campaign["ccode3"]) == ("UTC", "NGA")
    assert (campaign["start_request_date"], campaign["end_request_date"]) == (
        "20200801",
        "20260814",
    )
    assert campaign["required_date_count"] == 2_205
    assert campaign["required_successful_slot_count"] == 4_410
    assert campaign["successful_slot_count"] == 4_410
    assert campaign["failure_journal_entry_count"] == 0
    assert campaign["response_file_count"] == 4_410
    assert campaign["manifest_file_count"] == 4_410
    assert 300 <= campaign["minimum_pair_separation_seconds"]
    assert campaign["maximum_pair_separation_seconds"] <= 86_400
    assert campaign["campaign_index_sequence_contiguous"] is True
    assert campaign["campaign_index_sha256_chain_valid"] is True
    assert campaign["all_raw_hashes_match_index"] is True
    assert campaign["all_manifest_hashes_match_index"] is True
    assert campaign["all_manifest_request_identities_match_frozen_request"] is True
    assert receipt["historical_coverage_proven"] is False


def test_pr101_did_not_pre_register_primary_id_as_cross_season_mapping_semantics() -> None:
    protocol = pr101.build_fotmob_ordinary_ft_source_history_acquisition_protocol().to_dict()
    assert protocol["league_mapping_rule"] == (
        "ALL_ELEVEN_MAPPINGS_ARE_PRE_REGISTERED_CANDIDATES_AND_MUST_BE_PROVEN_"
        "FROM_CAPTURED_FOTMOB_LEAGUE_ID_NAME_COUNTRY_EVIDENCE_BEFORE_COMPLETENESS"
    )
    assert len(protocol["league_mappings"]) == 11
    for mapping in protocol["league_mappings"]:
        assert set(mapping) == {
            "model_league_code",
            "fotmob_league_id",
            "expected_name",
            "expected_country",
            "mapping_state",
        }
        assert mapping["mapping_state"] == (
            "PRE_REGISTERED_DISCOVERY_ONLY_REQUIRES_CAPTURE_PROOF"
        )
        assert "primaryId" not in mapping
        assert "primary_id" not in mapping


def test_primary_id_evidence_is_preserved_as_discovery_not_qualification() -> None:
    receipt, _ = _receipt()
    mapping = receipt["league_mapping_evidence"]
    assert mapping["mapping_proven"] is False
    assert mapping["mapping_semantics"] == (
        "DISCOVERY_ONLY_FROZEN_CANDIDATE_ROOT_PRIMARY_ID_PLUS_COUNTRY_LINEAGE_"
        "REQUIRES_SEPARATE_REVIEW"
    )
    assert mapping["full_projection_sha256"] == (
        "cd4e83157310cd9652c302f48d3e611867a6ad4e0616ddfe0e858863468c1e32"
    )
    assert mapping["full_projection_size_bytes"] == 5_911

    records = {item["model_league_code"]: item for item in mapping["records"]}
    expected = {
        "B1": (40, "BEL"),
        "D1": (54, "GER"),
        "E0": (47, "ENG"),
        "F1": (53, "FRA"),
        "G1": (135, "GRE"),
        "I1": (55, "ITA"),
        "N1": (57, "NED"),
        "P1": (61, "POR"),
        "SC0": (64, "SCO"),
        "SP1": (87, "ESP"),
        "T1": (71, "TUR"),
    }
    assert set(records) == set(expected)

    for model_code, (primary_id, country_code) in expected.items():
        record = records[model_code]
        assert record["fotmob_primary_id"] == primary_id
        assert record["expected_country_code"] == country_code
        assert record["observed_country_codes"] == [country_code]
        assert record["unique_fixture_ids"] >= record["qualified_ordinary_ft_fixture_ids"]
        assert record["observed_wrapper_league_id_count"] >= 1
        assert record["observed_name_variant_count"] >= 1


def test_discovery_corpus_is_stable_but_contains_special_result_blockers() -> None:
    receipt, _ = _receipt()
    corpus = receipt["target_corpus"]

    assert corpus["mapping_basis"] == (
        "DISCOVERY_ONLY_FROZEN_CANDIDATE_ROOT_PRIMARY_ID_PLUS_COUNTRY_LINEAGE"
    )
    assert corpus["frozen_model_league_codes"] == [
        "B1", "D1", "E0", "F1", "G1", "I1", "N1", "P1", "SC0", "SP1", "T1"
    ]
    assert corpus["unique_source_fixture_ids"] == 21_388
    assert corpus["source_fixture_date_occurrences"] == 21_640
    assert corpus["qualified_ordinary_ft_unique_fixture_ids"] == 21_336
    assert corpus["blocked_nonordinary_finished_unique_fixture_ids"] == 31
    assert corpus["unresolved_nonresult_unique_fixture_ids"] == 21
    assert corpus["qualified_row_projection_sha256"] == QUALIFIED_ROW_PROJECTION_SHA256
    assert corpus["qualified_row_projection_size_bytes"] == 14_997_331

    for key in (
        "within_pair_fixture_presence_drift_count",
        "within_pair_identity_drift_count",
        "within_pair_score_drift_count",
        "within_pair_reason_drift_count",
        "request_date_kickoff_utc_date_mismatch_count",
        "duplicate_fixture_id_within_capture_count",
        "qualified_row_duplicate_identity_key_count",
        "qualified_row_same_team_same_kickoff_ambiguity_count",
        "cross_date_static_identity_drift_count",
    ):
        assert corpus[key] == 0

    assert corpus["cross_date_rearranged_fixture_id_count"] == 250
    assert corpus["cross_date_kickoff_change_fixture_id_count"] == 250
    assert corpus["duplicate_terminal_awarded_fixture_id"] == 3932603


def test_special_and_unresolved_states_are_not_silently_coerced() -> None:
    receipt, _ = _receipt()
    special = receipt["special_result_blockers"]
    unresolved = receipt["unresolved_source_states"]

    assert special["awarded_win_unique_fixture_ids"] == 25
    assert special["awarded_win_observation_count"] == 26
    assert special["after_extra_time_unique_fixture_ids"] == 3
    assert special["after_penalties_unique_fixture_ids"] == 3
    assert len(special["awarded_win_fixture_ids"]) == 25
    assert len(special["after_extra_time_fixture_ids"]) == 3
    assert len(special["after_penalties_fixture_ids"]) == 3
    assert special["full_projection_sha256"] == (
        "d5f70aad76424a01249365da09d450b4fb7f27f3d03ab546e8b9783784f5a96b"
    )
    assert special["full_projection_size_bytes"] == 13_531
    assert special["duplicate_terminal_awarded_fixture"] == {
        "fixture_id": 3932603,
        "request_dates": ["20230220", "20230305"],
    }

    assert unresolved["abandoned_unique_fixture_ids"] == 13
    assert unresolved["postponed_unique_fixture_ids"] == 2
    assert unresolved["cancelled_unique_fixture_ids"] == 6
    assert len(unresolved["abandoned_fixture_ids"]) == 13
    assert len(unresolved["postponed_fixture_ids"]) == 2
    assert len(unresolved["cancelled_fixture_ids"]) == 6
    assert unresolved["full_projection_sha256"] == (
        "153cca2a970bce982eecab45c2df5fbaf1df099d081c45f7c3195bb1580b8593"
    )
    assert unresolved["full_projection_size_bytes"] == 8_154


def test_fail_closed_gate_result_and_next_boundary_are_frozen() -> None:
    receipt, _ = _receipt()
    gates = _gates(receipt)

    assert receipt["assessment_state"] == (
        "EXECUTED_FAIL_CLOSED_HISTORICAL_COVERAGE_NOT_QUALIFIED"
    )
    assert receipt["primary_status"] == "BLOCKED_LEAGUE_MAPPING_UNPROVEN"

    assert gates["DERIVED_SCORE_CAPABILITY"]["outcome"] == "PASSED"
    assert gates["CAMPAIGN_EXECUTION_EVIDENCE"]["outcome"] == "PASSED"
    assert gates["DAILY_DATE_COVERAGE"]["outcome"] == "PASSED"
    assert gates["ELEVEN_LEAGUE_MAPPING"] == {
        "gate_id": "ELEVEN_LEAGUE_MAPPING",
        "outcome": "UNPROVEN",
        "status": "BLOCKED_LEAGUE_MAPPING_UNPROVEN",
        "reason": (
            "ALL_ELEVEN_FROZEN_CANDIDATE_ROOT_IDS_ARE_OBSERVED_AS_FOTMOB_PRIMARY_ID_WITH_"
            "EXPECTED_COUNTRY_LINEAGE_BUT_PR101_DID_NOT_PRE_REGISTER_PRIMARY_ID_AS_THE_"
            "CANONICAL_CROSS_SEASON_MAPPING_FIELD_AND_WRAPPER_IDS_OR_NAMES_VARY"
        ),
    }
    assert gates["ELO_INITIALIZATION_BOUNDARY"]["outcome"] == "UNPROVEN"
    assert gates["ELO_INITIALIZATION_BOUNDARY"]["status"] == (
        "BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN"
    )
    assert gates["FINISHED_RESULT_EVIDENCE_COVERAGE"]["outcome"] == "BLOCKED"
    assert gates["FINISHED_RESULT_EVIDENCE_COVERAGE"]["status"] == (
        "BLOCKED_NON_ORDINARY_FT_RESULT_REQUIRES_SEPARATE_REVIEW"
    )
    assert gates["NON_ORDINARY_FT_RESULT_STATES"]["outcome"] == "BLOCKED"
    assert gates["IDENTITY_AND_CHRONOLOGY_CONFLICTS"]["outcome"] == "BLOCKED"
    assert gates["IDENTITY_AND_CHRONOLOGY_CONFLICTS"]["status"] == (
        "BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT"
    )
    assert gates["HISTORICAL_COVERAGE"]["outcome"] == "BLOCKED"

    assert receipt["historical_coverage_proven"] is False
    assert receipt["source_capability_registry_mutation_performed"] is False
    assert receipt["history_adapter_materialized"] is False
    assert receipt["next_required_boundary"] == (
        "PRE_REGISTER_REVIEWED_FOTMOB_PRIMARY_ID_COMPETITION_MAPPING_SEMANTICS_PROTOCOL"
    )
    assert all(value is False for value in receipt["safety"].values())
