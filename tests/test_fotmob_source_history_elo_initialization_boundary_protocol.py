"""Tests for the reviewed FotMob Elo-initialization boundary protocol."""
from __future__ import annotations

import hashlib

import pytest

import domain.fotmob_source_history_elo_initialization_boundary_protocol as protocol
import domain.fotmob_source_history_rearrangement_chronology_qualification as pr112
import domain.historical_expected_goals_successor_protocol as successor_protocol
import domain.prospective_successor_source_history_completeness_protocol as pr81


def _value() -> protocol.FotMobSourceHistoryEloInitializationBoundaryProtocol:
    return protocol.build_fotmob_source_history_elo_initialization_boundary_protocol()


def test_protocol_is_exact_canonical_frozen_contract() -> None:
    value = _value()
    raw = protocol.canonical_fotmob_source_history_elo_initialization_boundary_protocol_bytes(value)
    assert len(raw) == protocol.PROTOCOL_SIZE == 8_405
    assert hashlib.sha256(raw).hexdigest() == protocol.PROTOCOL_SHA256
    assert protocol.PROTOCOL_SHA256 == (
        "61f62252c178fb2e87a1f704848dfadb19213a9dede8fd2925b5d938faf0186c"
    )
    assert value.to_dict()["repository_main_sha"] == (
        "4f99b482d4c3f3f1e3ef19e3134e235f1c4c7da8"
    )


def test_exact_pr112_chronology_qualification_ancestry_is_required() -> None:
    value = _value().to_dict()
    upstream = value["upstream"]
    assert upstream["pr112_receipt_sha256"] == pr112.RECEIPT_SHA256
    assert upstream["pr112_receipt_size_bytes"] == pr112.RECEIPT_SIZE
    assert upstream["pr112_qualification_domain_blob_sha"] == (
        "2028c7e4d847ba293bc88ffc718a406853f96d11"
    )
    assert value["fotmob_evidence_envelope"]["rearrangement_chronology_qualified_required"] is True
    assert value["fotmob_evidence_envelope"]["historical_coverage_proven_required"] is False


def test_pr81_initialization_rule_and_exact_eleven_model_families_are_frozen() -> None:
    value = _value().to_dict()
    assert pr81.INITIALIZATION_BOUNDARY_RULE == (
        "MUST_BE_PROVEN_EQUIVALENT_TO_FROZEN_PR69_REPLAY_START_NOT_CHOSEN_AD_HOC"
    )
    assert [row["model_league_code"] for row in value["frozen_model_families"]] == list(
        pr81.FROZEN_MODEL_LEAGUE_CODES
    )
    assert [(row["model_league_code"], row["fotmob_primary_id"]) for row in value["frozen_model_families"]] == [
        ("B1", 40),
        ("D1", 54),
        ("E0", 47),
        ("F1", 53),
        ("G1", 135),
        ("I1", 55),
        ("N1", 57),
        ("P1", 61),
        ("SC0", 64),
        ("SP1", 87),
        ("T1", 71),
    ]


def test_pr69_exact_replay_ancestry_and_initial_state_semantics_are_frozen() -> None:
    upstream = _value().to_dict()["upstream"]
    assert upstream["pr69_source_corpus_sha256"] == successor_protocol.PR69_SOURCE_CORPUS_SHA256
    assert upstream["pr69_canonical_replay_sha256"] == successor_protocol.PR69_CANONICAL_SHA256
    assert upstream["pr69_canonical_replay_size_bytes"] == 39_952_730
    assert upstream["pr69_source_file_count"] == successor_protocol.SOURCE_FILE_COUNT == 66
    assert upstream["pr69_source_fixture_count"] == successor_protocol.SOURCE_FIXTURE_COUNT == 21_226
    assert upstream["pr69_initial_season"] == successor_protocol.TRAIN_SEASONS[0] == "2020-21"
    assert upstream["elo_initialization_semantics"] == (
        "1500_REPLAY_INITIAL_STATE_ASSUMPTION_NOT_OBSERVED_EVIDENCE"
    )


def test_synthetic_witness_proves_1500_seed_and_cross_season_carryover() -> None:
    witness = _value().to_dict()["pr69_synthetic_witness"]
    first = witness["first_fixture"]
    assert first["home_elo"] == first["away_elo"] == 1500
    assert first["home_initial_state_assumption"] is True
    assert first["away_initial_state_assumption"] is True
    later = witness["cross_season_fixture"]
    assert later["home_team"] == first["home_team"] == "Alpha FC"
    assert later["home_elo"] == 1513
    assert later["home_initial_state_assumption"] is False
    assert later["away_elo"] == 1500
    assert later["away_initial_state_assumption"] is True


def test_campaign_start_is_not_silently_promoted_to_elo_reset_date() -> None:
    value = _value().to_dict()
    assert value["fotmob_evidence_envelope"]["campaign_start_date"] == "20200801"
    rules = value["boundary_reference_rules"]
    assert "FOTMOB_CAMPAIGN_START_IS_A_COVERAGE_ENVELOPE_NOT_THE_ELO_INITIALIZATION_DATE" in rules
    assert any("EXACT_PR69_2020_21_SOURCE_FILE" in rule for rule in rules)
    assert any("PRE_2020_21_RESULTS" in rule for rule in rules)
    assert any("PRESERVE_BUT_EXCLUDE" in rule for rule in rules)


def test_initialization_state_forbids_season_reset_preseed_and_out_of_universe_updates() -> None:
    rules = _value().to_dict()["elo_state_rules"]
    assert any("NO_PER_SEASON_RATING_RESET" in rule for rule in rules)
    assert any("NEWLY_PROMOTED" in rule and "1500" in rule for rule in rules)
    assert any("LOWER_DIVISION_CUP_CONTINENTAL_INTERNATIONAL_FRIENDLY" in rule for rule in rules)
    assert any("PREMATCH_ELO_IS_CAPTURED_BEFORE" in rule for rule in rules)
    assert any("AWARDED_AFTER_EXTRA_TIME_AFTER_PENALTIES" in rule for rule in rules)


def test_protocol_forbids_cross_source_numeric_elo_equivalence_claim() -> None:
    rules = _value().to_dict()["elo_state_rules"]
    assert any("NO_CROSS_SOURCE_TEAM_IDENTITY_OR_NUMERIC_PR69_VS_FOTMOB_ELO_EQUALITY" in rule for rule in rules)
    requirements = _value().to_dict()["qualification_requirements"]
    assert "DO_NOT_REQUIRE_OR_INFER_CROSS_SOURCE_FIXTURE_OR_TEAM_IDENTITY_ALIGNMENT" in requirements


def test_execution_requirement_is_exact_source_rebuild_plus_preserved_fotmob_artifact() -> None:
    value = _value().to_dict()
    requirements = value["qualification_requirements"]
    assert "USE_ONLY_THE_EXACT_PRESERVED_FOTMOB_CAMPAIGN_ARTIFACT_WITHOUT_FOTMOB_NETWORK_REACQUISITION" in requirements
    assert any("REBUILD_PR69_FROM_ALL_66_EXACT_FOOTBALL_DATA_UK_SOURCE_FILES" in item for item in requirements)
    assert any("ALL_ELEVEN_PR69_2020_21_REFERENCE_FLOORS" in item for item in requirements)
    assert any("PREBOUNDARY_COUNTS" in item for item in requirements)
    assert value["next_required_boundary"] == (
        "EXECUTE_REVIEWED_FOTMOB_SOURCE_HISTORY_ELO_INITIALIZATION_BOUNDARY_QUALIFICATION"
    )


def test_protocol_is_pre_registration_only_and_all_downstream_authority_stays_false() -> None:
    value = _value().to_dict()
    assert value["initialization_boundary_execution_performed"] is False
    assert value["initialization_boundary_qualified"] is False
    assert value["source_history_mutation_performed"] is False
    assert value["historical_coverage_proven"] is False
    assert all(flag is False for flag in value["safety"].values())
    for key in (
        "initialization_boundary_proven",
        "ordinary_ft_history_rows_authorized",
        "source_history_completeness_proven",
        "model_training_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
    ):
        assert value["safety"][key] is False


def test_payload_mutation_fails_closed() -> None:
    payload = _value().to_dict()
    payload["historical_coverage_proven"] = True
    with pytest.raises(protocol.FotMobSourceHistoryEloInitializationBoundaryProtocolError):
        protocol.FotMobSourceHistoryEloInitializationBoundaryProtocol(payload)
