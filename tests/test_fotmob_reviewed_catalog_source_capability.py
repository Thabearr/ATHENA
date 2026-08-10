from domain.source_capabilities import (
    CapabilityAvailability,
    SOURCE_CAPABILITY_REGISTRY,
)


REVIEWED_SOURCE = "fotmob_data_matches_reviewed_catalog"


def test_reviewed_catalog_capability_is_identity_only() -> None:
    capability = SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE]

    assert capability.source == REVIEWED_SOURCE
    assert capability.reliable_fixture_identity is CapabilityAvailability.CONFIRMED
    assert capability.full_time_score is CapabilityAvailability.NOT_CAPTURED
    assert capability.half_time_score is CapabilityAvailability.NOT_CAPTURED
    assert capability.event_timestamps is CapabilityAvailability.NOT_CAPTURED
    assert capability.historical_coverage is CapabilityAvailability.UNKNOWN
    assert capability.freshness_metadata is CapabilityAvailability.NOT_CAPTURED


def test_raw_fotmob_unofficial_capability_remains_unknown() -> None:
    capability = SOURCE_CAPABILITY_REGISTRY["fotmob_unofficial"]

    assert capability.full_time_score is CapabilityAvailability.UNKNOWN
    assert capability.half_time_score is CapabilityAvailability.UNKNOWN
    assert capability.event_timestamps is CapabilityAvailability.UNKNOWN
    assert capability.reliable_fixture_identity is CapabilityAvailability.UNKNOWN
    assert capability.historical_coverage is CapabilityAvailability.UNKNOWN
    assert capability.freshness_metadata is CapabilityAvailability.UNKNOWN


def test_reviewed_catalog_capability_is_anchored_to_reviewed_pipeline() -> None:
    capability = SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE]

    assert capability.evidence == (
        (
            "domain/fotmob_data_matches_schema.py: strict fixture, team, "
            "competition and kickoff structure"
        ),
        (
            "domain/fotmob_fixture_candidates.py: provenance-backed UNREVIEWED "
            "source match, team, competition and kickoff mapping"
        ),
        (
            "domain/fotmob_fixture_candidate_review.py: exact candidate "
            "review key, conflict blockers and explicit APPROVED decision"
        ),
        (
            "domain/fotmob_fixture_catalog_handoff.py: exact reviewed "
            "candidate bundle reconstruction before catalog input"
        ),
        (
            "domain/fixture_catalog.py: source-scoped FOTMOB fixture identity "
            "and strict provenance normalization"
        ),
        (
            "scripts/manage_fotmob_reviewed_fixture_catalog.py: reviewed "
            "handoff preflight before PR #29 output commit"
        ),
    )


def test_reviewed_catalog_identity_confirmation_does_not_claim_broader_trust() -> None:
    notes = SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE].notes

    for phrase in (
        "source-scoped FOTMOB:<match id> identity",
        "does not establish global team identity",
        "source completeness",
        "score semantics",
        "source freshness",
        "Fixture Intelligence trust",
        "model readiness",
        "pricing",
        "selection",
        "betting authorization",
    ):
        assert phrase in notes


def test_reviewed_catalog_capability_serializes_without_promoting_unknowns() -> None:
    payload = SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE].to_dict()

    assert payload["source"] == REVIEWED_SOURCE
    assert payload["reliable_fixture_identity"] == "CONFIRMED"
    assert payload["historical_coverage"] == "UNKNOWN"
    assert payload["full_time_score"] == "NOT_CAPTURED"
    assert payload["half_time_score"] == "NOT_CAPTURED"
    assert payload["event_timestamps"] == "NOT_CAPTURED"
    assert payload["freshness_metadata"] == "NOT_CAPTURED"
