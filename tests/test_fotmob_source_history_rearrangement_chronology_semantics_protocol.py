"""Tests for the reviewed FotMob rearrangement chronology semantics protocol."""

from __future__ import annotations

import hashlib

import domain.fotmob_source_history_rearrangement_chronology_semantics_protocol as protocol
import domain.fotmob_source_history_special_result_semantics_qualification as pr110


def _value() -> dict[str, object]:
    return protocol.build_fotmob_source_history_rearrangement_chronology_semantics_protocol().to_dict()


def test_protocol_is_exact_canonical_frozen_contract() -> None:
    value = protocol.build_fotmob_source_history_rearrangement_chronology_semantics_protocol()
    raw = protocol.canonical_fotmob_source_history_rearrangement_chronology_semantics_protocol_bytes(value)
    assert len(raw) == protocol.PROTOCOL_SIZE == 7_642
    assert hashlib.sha256(raw).hexdigest() == protocol.PROTOCOL_SHA256
    assert protocol.PROTOCOL_SHA256 == "3f7caa751d0fe8114e50d8fee4bb2afa58023b4bee63429e4c6c51b9d2f92ce3"
    assert value.to_dict()["repository_main_sha"] == "8bc0a8afc20b71958dee9d14ab1d783eff646447"


def test_exact_pr110_ancestry_and_unresolved_premise_are_required() -> None:
    value = _value()
    upstream = value["upstream"]
    assert upstream["pr110_qualification_receipt_sha256"] == pr110.RECEIPT_SHA256
    assert upstream["pr110_qualification_receipt_size_bytes"] == pr110.RECEIPT_SIZE
    assert upstream["pr110_qualification_domain_blob_sha"] == (
        "ed3f2053ab9732e1e34e2e54f6f1e3531d01a4ca"
    )
    assert upstream["special_result_semantics_qualified_required"] is True
    assert upstream["historical_coverage_proven_required"] is False
    assert upstream["chronology_resolved_required"] is False
    assert upstream["special_fixture_history_projection_sha256"] == pr110.HISTORY_PROJECTION_SHA256
    assert upstream["special_fixture_history_projection_size_bytes"] == pr110.HISTORY_PROJECTION_SIZE


def test_frozen_rearrangement_evidence_expectations_are_exact() -> None:
    expected = _value()["evidence_expectations"]
    assert expected["rearranged_fixture_id_count"] == 250
    assert expected["rearranged_fixture_date_occurrence_count"] == 502
    assert expected["raw_pair_capture_observation_count"] == 1_004
    assert expected["transition_edge_count"] == 252
    assert expected["terminal_ordinary_ft_fixture_count"] == 243
    assert expected["terminal_awarded_win_fixture_count"] == 7
    assert expected["state_occurrence_counts"] == {
        "POSTPONED": 239,
        "ABANDONED": 7,
        "CANCELLED": 5,
        "ORDINARY_FT": 243,
        "AWARDED_WIN": 8,
    }
    assert expected["same_date_pair_capture_count_required"] == 2
    assert expected["same_date_pair_conflict_count_required"] == 0
    assert expected["cross_date_static_identity_drift_count_required"] == 0
    assert expected["request_date_kickoff_utc_date_mismatch_count_required"] == 0
    assert expected["kickoff_revision_direction"] == (
        "STRICTLY_FORWARD_FOR_EVERY_REVIEWED_CROSS_DATE_EDGE"
    )


def test_exact_six_transition_patterns_are_pre_registered() -> None:
    specs = _value()["transition_specs"]
    assert [(item["pattern"], item["fixture_id_count"]) for item in specs] == [
        (["POSTPONED", "ORDINARY_FT"], 234),
        (["ABANDONED", "ORDINARY_FT"], 7),
        (["CANCELLED", "AWARDED_WIN"], 5),
        (["POSTPONED", "POSTPONED", "ORDINARY_FT"], 2),
        (["POSTPONED", "AWARDED_WIN"], 1),
        (["AWARDED_WIN", "AWARDED_WIN"], 1),
    ]
    assert sum(item["fixture_id_count"] for item in specs) == 250


def test_kickoff_revision_is_source_scoped_and_not_global_identity_redefinition() -> None:
    semantics = set(_value()["identity_semantics"])
    assert (
        "FOTMOB_FIXTURE_ID_IS_ONLY_A_SOURCE_SCOPED_LINEAGE_ANCHOR_AND_NEVER_A_CROSS_SOURCE_IDENTITY"
        in semantics
    )
    assert (
        "CHANGED_KICKOFF_ALONE_DOES_NOT_CREATE_A_NEW_SOURCE_FIXTURE_IDENTITY_WHEN_ALL_FROZEN_STATIC_IDENTITY_FIELDS_REMAIN_EXACT"
        in semantics
    )
    assert (
        "KICKOFF_REVISION_SEMANTICS_ARE_LIMITED_TO_THE_FROZEN_REARRANGED_CORPUS_AND_DO_NOT_GLOBALLY_REDEFINE_FIXTURE_IDENTITY"
        in semantics
    )


def test_abandoned_to_ft_does_not_invent_real_world_resume_or_replay_semantics() -> None:
    semantics = set(_value()["chronology_semantics"])
    assert (
        "A_LATER_ORDINARY_FT_STATE_DOES_NOT_PROVE_WHETHER_AN_EARLIER_ABANDONED_MATCH_WAS_RESUMED_REPLAYED_RESTARTED_OR_REPLACED"
        in semantics
    )
    specs = {item["pattern_id"]: item for item in _value()["transition_specs"]}
    assert specs["ABANDONED_TO_ORDINARY_FT"]["chronology_semantics"] == (
        "SOURCE_LATER_REPORTS_ORDINARY_FT_AFTER_ABANDONED_STATE_WITHOUT_INFERRING_RESUMED_REPLAYED_RESTARTED_OR_CONTINUED_PLAY"
    )


def test_awarded_transitions_remain_excluded_from_ordinary_model_history() -> None:
    specs = _value()["transition_specs"]
    awarded = [item for item in specs if item["pattern"][-1] == "AWARDED_WIN"]
    assert sum(item["fixture_id_count"] for item in awarded) == 7
    assert all(
        item["terminal_disposition"].startswith("EXCLUDE_FROM_ORDINARY_REGULATION_TIME_MODEL_HISTORY")
        for item in awarded
    )
    expected = _value()["evidence_expectations"]
    assert expected["duplicate_terminal_awarded_fixture"] == {
        "fixture_id": 3_932_603,
        "request_dates": ["20230220", "20230305"],
    }


def test_protocol_execution_and_all_downstream_authority_remain_fail_closed() -> None:
    value = _value()
    assert value["chronology_semantics_execution_performed"] is False
    assert value["rearrangement_chronology_qualified"] is False
    assert value["source_history_mutation_performed"] is False
    assert value["historical_coverage_proven"] is False
    assert value["next_required_boundary"] == (
        "EXECUTE_REVIEWED_FOTMOB_SOURCE_HISTORY_REARRANGEMENT_CHRONOLOGY_QUALIFICATION"
    )
    assert all(flag is False for flag in value["safety"].values())
