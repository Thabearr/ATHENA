from __future__ import annotations

import hashlib

import domain.fotmob_data_matches_full_time_score_capability_promotion_protocol as pr93
import domain.fotmob_data_matches_full_time_score_capability_promotion_assessment_with_validated_adapter as pr97
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


PARENT_SOURCE_KEY = "fotmob_data_matches_reviewed_catalog"
DERIVED_SOURCE_KEY = "fotmob_data_matches_reviewed_ordinary_ft_finished_score"


def _capability_dict(capability) -> dict[str, str]:
    return {
        "full_time_score": capability.full_time_score.value,
        "half_time_score": capability.half_time_score.value,
        "event_timestamps": capability.event_timestamps.value,
        "reliable_fixture_identity": capability.reliable_fixture_identity.value,
        "historical_coverage": capability.historical_coverage.value,
        "freshness_metadata": capability.freshness_metadata.value,
    }


def test_parent_reviewed_catalog_remains_identity_only() -> None:
    parent = SOURCE_CAPABILITY_REGISTRY[PARENT_SOURCE_KEY]
    assert _capability_dict(parent) == {
        "full_time_score": "NOT_CAPTURED",
        "half_time_score": "NOT_CAPTURED",
        "event_timestamps": "NOT_CAPTURED",
        "reliable_fixture_identity": "CONFIRMED",
        "historical_coverage": "UNKNOWN",
        "freshness_metadata": "NOT_CAPTURED",
    }


def test_derived_ordinary_ft_finished_score_capability_is_exact_pr93_contract() -> None:
    protocol = pr93.build_fotmob_data_matches_full_time_score_capability_promotion_protocol()
    derived = SOURCE_CAPABILITY_REGISTRY[DERIVED_SOURCE_KEY]

    assert derived.source == DERIVED_SOURCE_KEY
    assert _capability_dict(derived) == dict(protocol.proposed_capabilities) == {
        "full_time_score": "CONFIRMED",
        "half_time_score": "NOT_CAPTURED",
        "event_timestamps": "NOT_CAPTURED",
        "reliable_fixture_identity": "CONFIRMED",
        "historical_coverage": "UNKNOWN",
        "freshness_metadata": "NOT_CAPTURED",
    }
    assert derived.full_time_score is CapabilityAvailability.CONFIRMED
    assert derived.historical_coverage is CapabilityAvailability.UNKNOWN
    assert derived.evidence == protocol.proposed_evidence
    assert derived.notes == protocol.proposed_notes


def test_registration_does_not_broaden_penalty_settlement_or_downstream_authority() -> None:
    derived = SOURCE_CAPABILITY_REGISTRY[DERIVED_SOURCE_KEY]
    notes = derived.notes.lower()
    for token in (
        "ordinary-ft",
        "penalty",
        "regulation-time",
        "extra-time",
        "bookmaker-settlement",
        "historical-coverage",
        "source-freshness",
        "model-readiness",
        "pricing",
        "selection",
        "betting authority",
    ):
        assert token in notes

    assert derived.half_time_score is CapabilityAvailability.NOT_CAPTURED
    assert derived.event_timestamps is CapabilityAvailability.NOT_CAPTURED
    assert derived.freshness_metadata is CapabilityAvailability.NOT_CAPTURED


def test_pr97_qualified_assessment_remains_canonically_revalidatable_after_registration() -> None:
    receipt = pr97.build_fotmob_data_matches_full_time_score_capability_promotion_assessment_with_validated_adapter()
    exact = pr97.canonical_fotmob_data_matches_full_time_score_capability_promotion_assessment_with_validated_adapter_bytes(
        receipt
    )

    assert hashlib.sha256(exact).hexdigest() == pr97.ASSESSMENT_SHA256 == (
        "edec152475a4c964084cdee1ba7c6a7385457297b63acf4a81e683dc74e99e03"
    )
    assert len(exact) == pr97.ASSESSMENT_SIZE == 5369
    assert receipt["primary_status"] == (
        "QUALIFIED_SCOPED_ORDINARY_FT_FULL_TIME_SCORE_CAPABILITY_REGISTRATION"
    )
    assert receipt["proposed_source_key_present_before_registration"] is False
    assert receipt["registration_qualified"] is True
    assert receipt["registry_update_performed"] is False
    assert all(flag is False for flag in receipt["safety"].values())


def test_registration_is_a_separate_derived_key_not_parent_mutation() -> None:
    assert PARENT_SOURCE_KEY != DERIVED_SOURCE_KEY
    assert SOURCE_CAPABILITY_REGISTRY[PARENT_SOURCE_KEY].full_time_score is CapabilityAvailability.NOT_CAPTURED
    assert SOURCE_CAPABILITY_REGISTRY[DERIVED_SOURCE_KEY].full_time_score is CapabilityAvailability.CONFIRMED
