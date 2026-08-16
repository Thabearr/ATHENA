"""Tests for the reviewed FotMob historical source-history adapter protocol."""

from __future__ import annotations

import hashlib

import domain.fotmob_historical_source_history_adapter_protocol as protocol
import domain.fotmob_source_history_adapter_completeness_assessment as pr115


def _value() -> dict[str, object]:
    return protocol.build_fotmob_historical_source_history_adapter_protocol().to_dict()


def test_protocol_is_exact_canonical_frozen_contract() -> None:
    value = protocol.build_fotmob_historical_source_history_adapter_protocol()
    raw = protocol.canonical_fotmob_historical_source_history_adapter_protocol_bytes(value)
    assert len(raw) == protocol.PROTOCOL_SIZE == 9898
    assert hashlib.sha256(raw).hexdigest() == protocol.PROTOCOL_SHA256
    assert protocol.PROTOCOL_SHA256 == "f987bc68eaf9f4c7b57a66788f3dcac5d704be6dad36ecae92bf5dd7e315ea9a"
    assert value.to_dict()["repository_main_sha"] == "3b49eccc9476754972c18b9abcfe013f783a6205"


def test_exact_pr115_fail_closed_ancestry_is_required() -> None:
    value = _value()
    upstream = value["upstream"]
    assert upstream["pr115_assessment_receipt_sha256"] == pr115.RECEIPT_SHA256
    assert upstream["pr115_assessment_receipt_size_bytes"] == pr115.RECEIPT_SIZE
    assert upstream["pr115_assessment_domain_blob_sha"] == "15a120272c08a495c4a12d7321f8b4ff7ec6b2ec"
    assert upstream["pr115_primary_status_required"] == "BLOCKED_RESULT_EVIDENCE_GAP"
    assert upstream["pr115_history_rows_materialized_required"] == 0
    assert upstream["historical_coverage_proven_required"] is False


def test_historical_pair_lineage_does_not_fake_distinct_raw_content() -> None:
    rules = set(_value()["pair_lineage_rules"])
    assert (
        "IDENTICAL_RAW_SHA256_IS_ADMISSIBLE_ONLY_FOR_THIS_FROZEN_HISTORICAL_ADAPTER_WHEN_MANIFEST_LINEAGES_ARE_DISTINCT_AND_ALL_TARGET_RELEVANT_FIELDS_ARE_EXACTLY_STABLE"
        in rules
    )
    assert (
        "IDENTICAL_RAW_SHA256_MEANS_BYTE_IDENTICAL_CONTENT_RETRIEVED_TWICE_NOT_TWO_DISTINCT_CONTENT_LINEAGES"
        in rules
    )
    assert (
        "NEVER_SYNTHESIZE_REWRITE_SALT_OR_MUTATE_RAW_BYTES_OR_MANIFESTS_TO_CREATE_DISTINCT_LINEAGE"
        in rules
    )
    assert (
        "THE_PROSPECTIVE_ORDINARY_FT_ADAPTER_DISTINCT_RAW_LINEAGE_RULE_REMAINS_UNCHANGED"
        in rules
    )


def test_exact_campaign_and_pair_evidence_is_frozen() -> None:
    expected = _value()["evidence_expectations"]
    assert expected["request_date_count"] == 2_205
    assert expected["capture_manifest_count"] == 4_410
    assert expected["capture_pair_count"] == 2_205
    assert expected["distinct_manifest_pair_count"] == 2_205
    assert expected["identical_raw_sha256_pair_count"] == 2_204
    assert expected["distinct_raw_sha256_pair_count"] == 1
    assert expected["distinct_raw_sha256_pair_dates"] == ["20250712"]
    assert expected["target_family_fixture_date_pair_count"] == 21_640
    assert expected["target_family_pairs_on_distinct_raw_dates"] == 0
    assert expected["minimum_pair_separation_seconds"] == 300


def test_historical_structural_scope_is_exact_and_opaque() -> None:
    expected = _value()["evidence_expectations"]
    assert expected["historical_halfs_exact_keys"] == [
        "firstHalfStarted",
        "secondHalfStarted",
    ]
    assert expected["historical_halfs_candidate_count"] == 21_336
    assert expected["historical_halfs_type"] == "EXACT_STRING_FOR_BOTH_KEYS"
    assert expected["historical_halfs_format"] == "%d.%m.%Y %H:%M:%S"

    rules = set(_value()["historical_structural_rules"])
    assert (
        "FIRST_HALF_STARTED_IS_HISTORICAL_OPAQUE_METADATA_AND_IS_NOT_KICKOFF_HALFTIME_DURATION_RESUMPTION_OR_SETTLEMENT_EVIDENCE"
        in rules
    )
    assert (
        "STATUS_UTC_TIME_IS_THE_ONLY_CANONICAL_KICKOFF_FIELD_AND_MUST_PARSE_AS_UTC"
        in rules
    )
    assert (
        "THE_FROZEN_PR89_AND_PROSPECTIVE_ADAPTER_IMPLEMENTATIONS_ARE_NOT_MUTATED_OR_REDEFINED_BY_THIS_HISTORICAL_CONTRACT"
        in rules
    )


def test_exact_eleven_model_families_and_candidate_accounting_are_frozen() -> None:
    value = _value()
    assert value["target_competition_families"] == [
        {"model_league_code": "B1", "primary_id": 40},
        {"model_league_code": "D1", "primary_id": 54},
        {"model_league_code": "E0", "primary_id": 47},
        {"model_league_code": "F1", "primary_id": 53},
        {"model_league_code": "G1", "primary_id": 135},
        {"model_league_code": "I1", "primary_id": 55},
        {"model_league_code": "N1", "primary_id": 57},
        {"model_league_code": "P1", "primary_id": 61},
        {"model_league_code": "SC0", "primary_id": 64},
        {"model_league_code": "SP1", "primary_id": 87},
        {"model_league_code": "T1", "primary_id": 71},
    ]
    expected = value["evidence_expectations"]
    assert expected["ordinary_ft_fixture_date_occurrence_count"] == 21_336
    assert expected["ordinary_ft_unique_source_fixture_id_count"] == 21_336
    assert expected["ordinary_ft_duplicate_source_fixture_id_count"] == 0
    assert expected["preboundary_ordinary_ft_occurrence_count"] == 10
    assert expected["on_or_after_floor_ordinary_ft_occurrence_count"] == 21_326
    assert sum(expected["on_or_after_floor_ordinary_ft_by_model_league"].values()) == 21_326
    assert expected["reviewed_special_state_occurrence_count"] == 304
    assert 21_336 + 304 == 21_640


def test_ordinary_ft_semantics_remain_narrow() -> None:
    value = _value()
    assert value["ordinary_ft_reason_tuple"] == {
        "short": "FT",
        "shortKey": "fulltime_short",
        "long": "Full-Time",
        "longKey": "finished",
    }
    rules = set(value["ordinary_ft_semantics"])
    assert "REQUIRE_FINISHED_TRUE_STARTED_TRUE_CANCELLED_FALSE" in rules
    assert "REQUIRE_STATUS_AWARDED_ABSENT_OR_EXACT_FALSE" in rules
    assert "REQUIRE_TEAM_PEN_SCORE_ABSENT_ON_BOTH_ENDPOINTS" in rules
    assert (
        "AWARDED_AFTER_EXTRA_TIME_AFTER_PENALTIES_ABANDONED_CANCELLED_POSTPONED_OR_ANY_UNREVIEWED_STATE_IS_NEVER_ADMITTED_AS_ORDINARY_FT_HISTORY"
        in rules
    )
    assert (
        "FOTMOB_FIXTURE_ID_REMAINS_A_SOURCE_SCOPED_IDENTITY_ONLY_AND_NEVER_CROSS_SOURCE_IDENTITY"
        in rules
    )


def test_preboundary_rows_and_pr80_handoff_remain_blocked() -> None:
    output_rules = set(_value()["qualification_output_rules"])
    assert (
        "THE_TEN_PREBOUNDARY_ORDINARY_FT_OCCURRENCES_REMAIN_EVIDENCE_ONLY_AND_CANNOT_SEED_ELO_OR_MODEL_HISTORY"
        in output_rules
    )
    assert (
        "THE_21326_ON_OR_AFTER_FLOOR_OCCURRENCES_REMAIN_ONLY_FUTURE_HISTORY_MATERIALIZATION_CANDIDATES_UNTIL_COMPLETENESS_IS_RERUN"
        in output_rules
    )
    assert "NO_PROJECTION_RECORD_MAY_BE_PASSED_TO_PR80_DURING_THIS_QUALIFICATION_BOUNDARY" in output_rules


def test_protocol_execution_and_all_downstream_authority_remain_fail_closed() -> None:
    value = _value()
    assert value["historical_adapter_execution_performed"] is False
    assert value["historical_source_history_adapter_qualified"] is False
    assert value["source_history_completeness_proven"] is False
    assert value["historical_coverage_proven"] is False
    assert value["history_rows_materialized"] == 0
    assert value["source_history_mutation_performed"] is False
    assert value["next_required_boundary"] == (
        "EXECUTE_REVIEWED_FOTMOB_HISTORICAL_SOURCE_HISTORY_ADAPTER_QUALIFICATION"
    )
    assert all(flag is False for flag in value["safety"].values())
