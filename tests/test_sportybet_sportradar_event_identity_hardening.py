from __future__ import annotations

import dataclasses

import pytest

from domain import sportybet_sportradar_event_identity as bridge
from tests.test_sportybet_sportradar_event_identity import _build


def test_current_sportradar_id_must_preserve_exact_numeric_payload(tmp_path) -> None:
    value, *_ = _build(tmp_path)
    with pytest.raises(
        bridge.SportyBetSportradarEventIdentityError,
        match="preserve",
    ):
        dataclasses.replace(
            value,
            sportradar_current_sport_event_id="sr:sport_event:124",
        )


def test_numeric_event_id_must_equal_legacy_payload(tmp_path) -> None:
    value, *_ = _build(tmp_path)
    with pytest.raises(
        bridge.SportyBetSportradarEventIdentityError,
        match="numeric Sportradar event ID",
    ):
        dataclasses.replace(value, sportradar_numeric_event_id=124)


def test_legacy_id_must_equal_exact_sportybet_event_id(tmp_path) -> None:
    value, *_ = _build(tmp_path)
    with pytest.raises(
        bridge.SportyBetSportradarEventIdentityError,
        match="legacy Sportradar",
    ):
        dataclasses.replace(
            value,
            sportradar_legacy_sport_event_id="sr:match:124",
        )


def test_source_url_cannot_drift_from_emitted_event_identity(tmp_path) -> None:
    value, *_ = _build(tmp_path)
    changed = value.source_url.replace("%3A123", "%3A124")
    with pytest.raises(
        bridge.SportyBetSportradarEventIdentityError,
        match="source URL",
    ):
        dataclasses.replace(value, source_url=changed)


def test_documentation_contract_hash_is_exact_not_merely_hash_shaped(tmp_path) -> None:
    value, *_ = _build(tmp_path)
    with pytest.raises(
        bridge.SportyBetSportradarEventIdentityError,
        match="documentation_contract_sha256",
    ):
        dataclasses.replace(value, documentation_contract_sha256="0" * 64)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("migration_guide_url", "https://developer.sportradar.com/other"),
        ("id_handling_url", "https://developer.sportradar.com/other"),
        ("identifier_authority", "UNREVIEWED"),
    ],
)
def test_documentation_semantics_metadata_is_frozen(
    tmp_path,
    field: str,
    replacement: str,
) -> None:
    value, *_ = _build(tmp_path)
    with pytest.raises(bridge.SportyBetSportradarEventIdentityError):
        dataclasses.replace(value, **{field: replacement})


@pytest.mark.parametrize(
    "field",
    [
        "numeric_identifier_preserved",
        "soccer_match_identifier_uniqueness_documented",
        "sportradar_namespace_qualified",
    ],
)
def test_documented_true_invariants_cannot_be_demoted(tmp_path, field: str) -> None:
    value, *_ = _build(tmp_path)
    with pytest.raises(bridge.SportyBetSportradarEventIdentityError):
        dataclasses.replace(value, **{field: False})


@pytest.mark.parametrize(
    "field",
    ["event_metadata_resolved", "fixture_identity_proven"],
)
def test_unresolved_authority_cannot_be_promoted(tmp_path, field: str) -> None:
    value, *_ = _build(tmp_path)
    with pytest.raises(bridge.SportyBetSportradarEventIdentityError):
        dataclasses.replace(value, **{field: True})


def test_year_and_utc_cannot_be_smuggled_into_namespace_bridge(tmp_path) -> None:
    value, *_ = _build(tmp_path)
    with pytest.raises(
        bridge.SportyBetSportradarEventIdentityError,
        match="year/UTC",
    ):
        dataclasses.replace(value, sportybet_kickoff_year=2026)
    with pytest.raises(
        bridge.SportyBetSportradarEventIdentityError,
        match="year/UTC",
    ):
        dataclasses.replace(value, sportybet_kickoff_utc="2026-08-18T20:00:00Z")


def test_every_safety_authority_remains_exact_false(tmp_path) -> None:
    value, *_ = _build(tmp_path)
    for key in value.safety:
        promoted = dict(value.safety)
        promoted[key] = True
        with pytest.raises(
            bridge.SportyBetSportradarEventIdentityError,
            match="must be exact bool False",
        ):
            dataclasses.replace(value, safety=promoted)


def test_bridge_rejects_noncanonical_current_prefix(tmp_path) -> None:
    value, *_ = _build(tmp_path)
    with pytest.raises(bridge.SportyBetSportradarEventIdentityError):
        dataclasses.replace(
            value,
            sportradar_current_sport_event_id="SR:SPORT_EVENT:123",
        )
