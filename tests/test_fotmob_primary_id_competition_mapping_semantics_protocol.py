"""Tests for the pre-registered generic FotMob competition-mapping semantics."""

from __future__ import annotations

import dataclasses
import hashlib

import pytest

import domain.fotmob_primary_id_competition_mapping_semantics_protocol as protocol


EXPECTED_CANDIDATES = {
    ("B1", 40, "BEL"),
    ("D1", 54, "GER"),
    ("E0", 47, "ENG"),
    ("F1", 53, "FRA"),
    ("G1", 135, "GRE"),
    ("I1", 55, "ITA"),
    ("N1", 57, "NED"),
    ("P1", 61, "POR"),
    ("SC0", 64, "SCO"),
    ("SP1", 87, "ESP"),
    ("T1", 71, "TUR"),
}


def _build() -> protocol.FotMobPrimaryIdCompetitionMappingSemanticsProtocol:
    return protocol.build_fotmob_primary_id_competition_mapping_semantics_protocol()


def test_protocol_is_exact_canonical_frozen_evidence() -> None:
    value = _build()
    raw = protocol.canonical_fotmob_primary_id_competition_mapping_semantics_protocol_bytes(
        value
    )
    assert len(raw) == protocol.PROTOCOL_SIZE == 7_370
    assert hashlib.sha256(raw).hexdigest() == protocol.PROTOCOL_SHA256
    assert protocol.PROTOCOL_SHA256 == (
        "6d3e6083325853b481fe2a5ad928d67c5fe7cb46d25f5c33024146855c6e725e"
    )
    assert value.schema_version == 1
    assert value.source == "fotmob"
    assert value.source_field == "primaryId"


def test_initial_eleven_are_a_proof_set_not_the_final_competition_universe() -> None:
    value = _build()
    candidates = {
        (
            item.model_league_code,
            item.fotmob_primary_id,
            item.expected_country_code,
        )
        for item in value.initial_mapping_candidates
    }
    assert candidates == EXPECTED_CANDIDATES
    assert len(value.initial_mapping_candidates) == 11
    assert {item.competition_class for item in value.initial_mapping_candidates} == {
        "DOMESTIC_LEAGUE"
    }
    assert all(
        item.qualification_state == protocol.INITIAL_QUALIFICATION_STATE
        for item in value.initial_mapping_candidates
    )
    assert value.initial_proof_set_role == (
        "ELEVEN_DOMESTIC_LEAGUES_INITIAL_QUALIFICATION_PROOF_SET_ONLY"
    )
    assert any(
        "NOT_THE_FINAL_ATHENA_COMPETITION_UNIVERSE" in rule
        for rule in value.competition_universe_rules
    )


def test_generic_competition_classes_keep_cups_continental_and_international_open() -> None:
    value = _build()
    assert set(value.supported_competition_classes) == {
        "DOMESTIC_LEAGUE",
        "DOMESTIC_CUP",
        "DOMESTIC_LEAGUE_CUP",
        "CONTINENTAL_CLUB",
        "INTERNATIONAL_TOURNAMENT",
        "INTERNATIONAL_QUALIFIER",
        "INTERNATIONAL_FRIENDLY",
        "OTHER_REVIEW_REQUIRED",
    }
    joined = "\n".join(value.competition_universe_rules)
    for token in (
        "CHAMPIONS_LEAGUE",
        "EUROPA_LEAGUE",
        "CONFERENCE_LEAGUE",
        "DOMESTIC_CUPS",
        "INTERNATIONAL_MATCHES",
    ):
        assert token in joined
    assert "NOT_QUALIFIED_BY_THE_INITIAL_ELEVEN_LEAGUE_PROOF_SET" in joined
    assert "STAGE_PHASE_LEG_TIE_NEUTRAL_VENUE" in joined


def test_primary_id_is_source_scoped_and_wrapper_or_name_fallback_is_forbidden() -> None:
    value = _build()
    joined = "\n".join(value.identity_rules)
    assert "SOURCE_SCOPED_COMPETITION_FAMILY_IDENTITY_ONLY" in joined
    assert "MUST_NOT_BE_PROMOTED_TO_GLOBAL_CROSS_PROVIDER_IDENTITY" in joined
    assert "DISPLAY_NAME_IS_METADATA_ONLY" in joined
    assert "MUST_NOT_FALL_BACK_TO_NAME_OR_WRAPPER_ID" in joined
    assert (
        "ANY_PRIMARY_ID_COLLISION_COUNTRY_CONFLICT_OR_COMPETITION_CLASS_CONFLICT_FAILS_CLOSED"
        in joined
    )
    assert "NOT_MODEL_CALIBRATION_OR_BETTING_ELIGIBILITY" in joined


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {
                "model_league_code": "E0",
                "fotmob_primary_id": 0,
                "expected_country_code": "ENG",
                "competition_class": "DOMESTIC_LEAGUE",
                "qualification_state": protocol.INITIAL_QUALIFICATION_STATE,
            },
            "fotmob_primary_id",
        ),
        (
            {
                "model_league_code": "E0",
                "fotmob_primary_id": 47,
                "expected_country_code": "eng",
                "competition_class": "DOMESTIC_LEAGUE",
                "qualification_state": protocol.INITIAL_QUALIFICATION_STATE,
            },
            "expected_country_code",
        ),
        (
            {
                "model_league_code": "E0",
                "fotmob_primary_id": 47,
                "expected_country_code": "ENG",
                "competition_class": "UNREVIEWED",
                "qualification_state": protocol.INITIAL_QUALIFICATION_STATE,
            },
            "competition_class",
        ),
        (
            {
                "model_league_code": "E0",
                "fotmob_primary_id": 47,
                "expected_country_code": "ENG",
                "competition_class": "DOMESTIC_LEAGUE",
                "qualification_state": "QUALIFIED",
            },
            "unqualified",
        ),
    ],
)
def test_mapping_candidate_validation_fails_closed(
    kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(
        protocol.FotMobPrimaryIdCompetitionMappingSemanticsProtocolError,
        match=message,
    ):
        protocol.InitialCompetitionMappingCandidate(**kwargs)


def test_protocol_pre_registration_grants_no_qualification_or_downstream_authority() -> None:
    value = _build()
    assert value.mapping_qualification_performed is False
    assert value.competition_registry_mutation_performed is False
    assert value.historical_coverage_proven is False
    assert value.safety
    assert all(flag is False for flag in value.safety.values())
    assert value.next_required_boundary == (
        "QUALIFY_REVIEWED_FOTMOB_PRIMARY_ID_COMPETITION_MAPPING_SEMANTICS_"
        "AGAINST_PRESERVED_CAMPAIGN_EVIDENCE"
    )


@pytest.mark.parametrize(
    "field",
    (
        "mapping_qualification_performed",
        "competition_registry_mutation_performed",
        "historical_coverage_proven",
    ),
)
def test_protocol_cannot_be_mutated_into_authority(field: str) -> None:
    value = _build()
    with pytest.raises(
        protocol.FotMobPrimaryIdCompetitionMappingSemanticsProtocolError
    ):
        dataclasses.replace(value, **{field: True})


def test_safety_flags_cannot_be_promoted() -> None:
    value = _build()
    promoted = dict(value.safety)
    promoted["bet_authorized"] = True
    with pytest.raises(
        protocol.FotMobPrimaryIdCompetitionMappingSemanticsProtocolError,
        match="safety",
    ):
        dataclasses.replace(value, safety=promoted)


def test_qualification_is_frozen_to_preserved_evidence_and_keeps_other_blockers_separate() -> None:
    value = _build()
    joined = "\n".join(value.qualification_rules)
    assert "PRESERVED_PR105_CAMPAIGN_EVIDENCE" in joined
    assert "WITHOUT_NETWORK_REACQUISITION_OR_POST_HOC_RULE_CHANGES" in joined
    assert "ALL_OBSERVED_WRAPPER_LEAGUE_IDS_AND_NAME_VARIANTS" in joined
    assert "PRESERVE_CONFLICTS" in joined
    assert "PARTIAL_SUCCESS_DOES_NOT_PROMOTE_HISTORICAL_COVERAGE" in joined
    assert (
        "AWARDED_EXTRA_TIME_PENALTY_REARRANGED_OR_INITIALIZATION_BOUNDARY_BLOCKERS"
        in joined
    )


def test_unknown_competitions_remain_visible_and_fail_closed() -> None:
    value = _build()
    joined = "\n".join(value.competition_universe_rules)
    assert "MAY_ENTER_DISCOVERY_AS_UNQUALIFIED_CANDIDATES" in joined
    assert "WITHOUT_BEING_DROPPED_OR_FORCED_INTO_AN_EXISTING_MODEL_LEAGUE_CODE" in joined
    assert "UNKNOWN_OR_UNQUALIFIED_COMPETITIONS_REMAIN_VISIBLE_AS_SOURCE_EVIDENCE" in joined
    assert "FAIL_CLOSED" in joined
