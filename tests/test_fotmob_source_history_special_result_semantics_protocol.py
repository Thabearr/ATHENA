"""Tests for the pre-registered FotMob source-history special-result semantics."""

from __future__ import annotations

import dataclasses
import hashlib

import pytest

import domain.fotmob_source_history_special_result_semantics_protocol as protocol


def _build() -> protocol.FotMobSourceHistorySpecialResultSemanticsProtocol:
    return protocol.build_fotmob_source_history_special_result_semantics_protocol()


def test_protocol_is_exact_canonical_frozen_contract() -> None:
    value = _build()
    raw = protocol.canonical_fotmob_source_history_special_result_semantics_protocol_bytes(value)
    assert len(raw) == protocol.PROTOCOL_SIZE == 7_040
    assert hashlib.sha256(raw).hexdigest() == protocol.PROTOCOL_SHA256
    assert protocol.PROTOCOL_SHA256 == "5fc2d1c089ecea5fd3ab4b9920f578ac25b555c0d89bebad4eedbfcd80c3cf87"
    payload = value.to_dict()
    assert payload["repository_main_sha"] == "fa3aa9de0a679e6efebc1a53a245bd8b418f3839"
    assert payload["pr108_receipt_sha256"] == "fdb55feef9585fe0aa2668ddb9ac9a6eb8e63ac8870c06cdb7917d1f996e7bc9"
    assert payload["pr108_receipt_size"] == 13_681


def test_evidence_scope_is_exactly_the_pr105_special_and_unresolved_projections() -> None:
    scope = _build().to_dict()["evidence_scope"]
    assert scope == {
        "special_projection_sha256": "d5f70aad76424a01249365da09d450b4fb7f27f3d03ab546e8b9783784f5a96b",
        "special_projection_size": 13_531,
        "unresolved_projection_sha256": "153cca2a970bce982eecab45c2df5fbaf1df099d081c45f7c3195bb1580b8593",
        "unresolved_projection_size": 8_154,
        "awarded_unique": 25,
        "awarded_observations": 26,
        "aet_unique": 3,
        "penalty_unique": 3,
        "abandoned_unique": 13,
        "cancelled_unique": 6,
        "postponed_unique": 2,
        "duplicate_terminal_awarded_fixture": {
            "fixture_id": 3_932_603,
            "request_dates": ["20230220", "20230305"],
        },
    }


def test_exact_reason_and_boolean_semantics_are_frozen_for_six_states() -> None:
    specs = {item["state_id"]: item for item in _build().to_dict()["state_specs"]}
    assert set(specs) == {
        "AWARDED_WIN", "AFTER_EXTRA_TIME", "AFTER_PENALTIES",
        "ABANDONED", "CANCELLED", "POSTPONED",
    }
    expected = {
        "AWARDED_WIN": ("AW", "", "Awarded win", "awarded_win", True, True, False, "EXACT_TRUE"),
        "AFTER_EXTRA_TIME": ("AET", "afterextratime_short", "After extra time", "afterextra", True, True, False, "EXACT_FALSE"),
        "AFTER_PENALTIES": ("Pen", "penalties_short", "After penalties", "afterpenalties", True, True, False, "EXACT_FALSE"),
        "ABANDONED": ("Ab", "aborted_short", "Abandoned", "aborted", True, True, True, "ABSENT_OR_FALSE"),
        "CANCELLED": ("Can", "cancelled_short", "Cancelled", "cancelled", False, False, True, "ABSENT_OR_FALSE"),
        "POSTPONED": ("PP", "postponed_short", "Postponed", "postponed", False, False, True, "ABSENT_OR_FALSE"),
    }
    for state_id, fields in expected.items():
        item = specs[state_id]
        assert (
            item["reason_short"], item["reason_short_key"], item["reason_long"],
            item["reason_long_key"], item["finished"], item["started"],
            item["cancelled"], item["awarded_requirement"],
        ) == fields
        assert item["history_disposition"] == protocol.ORDINARY_HISTORY_DISPOSITION
        assert item["preservation_disposition"] == protocol.PRESERVATION_DISPOSITION


def test_special_scores_are_not_reinterpreted_as_ordinary_regulation_time() -> None:
    specs = {item["state_id"]: item for item in _build().to_dict()["state_specs"]}
    assert "ADMINISTRATIVE_SCORE_NOT_OBSERVED_FOOTBALL_PERFORMANCE" in specs["AWARDED_WIN"]["score_semantics"]
    assert "NOT_REGULATION_TIME_SCORE" in specs["AFTER_EXTRA_TIME"]["score_semantics"]
    assert "TEAM_PEN_SCORE_FIELDS_REMAIN_SEPARATE" in specs["AFTER_PENALTIES"]["score_semantics"]
    assert "NOT_FINAL_REGULATION_RESULT" in specs["ABANDONED"]["score_semantics"]
    assert "NONRESULT_METADATA_NOT_PLAYED_SCORE" in specs["CANCELLED"]["score_semantics"]
    assert "NONRESULT_METADATA_NOT_PLAYED_SCORE" in specs["POSTPONED"]["score_semantics"]


def test_status_id_numeric_scores_and_bookmaker_settlement_cannot_override_source_semantics() -> None:
    joined = "\n".join(_build().to_dict()["semantic_rules"])
    assert "STATUS_ID_IS_SUPPORTING_EVIDENCE_ONLY_NEVER_THE_SOLE_SEMANTIC_CLASSIFIER" in joined
    assert "NUMERIC_SCORE_COINCIDENCE_NEVER_OVERRIDES_STATUS_REASON_SEMANTICS" in joined
    assert "SOURCE_HISTORY_SEMANTICS_DO_NOT_DEFINE_BOOKMAKER_SETTLEMENT_RULES" in joined


def test_cross_date_transitions_stay_blocked_for_separate_chronology_review() -> None:
    joined = "\n".join(_build().to_dict()["chronology_handoff_rules"])
    assert "CROSS_DATE_KICKOFF_OR_STATE_CHANGES_MUST_BE_PRESERVED_AS_TRANSITIONS" in joined
    assert "NOT_COLLAPSED_TO_A_CONVENIENT_FINAL_OBSERVATION" in joined
    assert "POSTPONED_OR_CANCELLED_TO_ORDINARY_FT_AND_CANCELLED_TO_AWARDED_TRANSITIONS_REMAIN_BLOCKED" in joined
    assert "FIXTURE_3932603" in joined


def test_execution_is_frozen_to_preserved_campaign_without_network_reacquisition() -> None:
    joined = "\n".join(_build().to_dict()["qualification_requirements"])
    assert "EXACT_PRESERVED_PR105_CAMPAIGN_ARTIFACT_WITHOUT_NETWORK_REACQUISITION" in joined
    assert "REVALIDATE_PR108_COMPETITION_MAPPING_QUALIFICATION_FIRST" in joined
    assert "ACCOUNT_FOR_EVERY_FIXTURE_IN_THE_PR105_SPECIAL_AND_UNRESOLVED_PROJECTIONS" in joined
    assert "PRODUCE_DETERMINISTIC_CANONICAL_RECEIPT" in joined


def test_pre_registration_grants_no_execution_history_or_downstream_authority() -> None:
    payload = _build().to_dict()
    assert payload["special_result_semantics_execution_performed"] is False
    assert payload["source_history_mutation_performed"] is False
    assert payload["historical_coverage_proven"] is False
    assert all(value is False for value in payload["safety"].values())
    assert payload["next_required_boundary"] == (
        "EXECUTE_REVIEWED_FOTMOB_SOURCE_HISTORY_SPECIAL_RESULT_SEMANTICS_QUALIFICATION"
    )


def test_protocol_cannot_be_mutated_into_authority() -> None:
    value = _build()
    mutated = value.to_dict()
    mutated["safety"]["bet_authorized"] = True
    with pytest.raises(protocol.FotMobSourceHistorySpecialResultSemanticsProtocolError):
        dataclasses.replace(value, payload=mutated)
