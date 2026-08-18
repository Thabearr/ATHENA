from __future__ import annotations

import dataclasses

import pytest

from domain import sportybet_fotmob_partial_calendar_reconciliation as partial
from domain import sportybet_official_time_semantics as terms


DETAIL_URL = (
    "https://www.sportybet.com/ng/lite/preMatch/detail?"
    "eventId=sr%3Amatch%3A123&marketGroupsName=Main&sportId=sr%3Asport%3A1"
)


def _candidate() -> partial.SportyBetFotMobPartialCalendarCandidate:
    return partial.SportyBetFotMobPartialCalendarCandidate(
        schema_version=partial.SCHEMA_VERSION,
        dataset_name=partial.DATASET_NAME,
        provider=partial.PROVIDER,
        status=partial.STATUS,
        source_time_basis_sha256="a" * 64,
        event_source_evidence_id="b" * 24,
        event_source_manifest_sha256="c" * 64,
        event_source_native_inventory_sha256="d" * 64,
        event_source_raw_sha256="e" * 64,
        event_candidate_sha256="f" * 64,
        event_source_url=DETAIL_URL,
        terms_evidence_id="1" * 24,
        terms_qualification_sha256="2" * 64,
        terms_raw_sha256="3" * 64,
        terms_source_url=terms.SOURCE_URL,
        terms_rule_sha256=terms.EXPECTED_STATEMENT_SHA256,
        fotmob_population_sha256="4" * 64,
        sportybet_event_id="sr:match:123",
        sportybet_sport_id="sr:sport:1",
        matching_basis=partial.MATCHING_BASIS,
        competition_display="Example Country - Example League",
        home_display="Example Home FC",
        away_display="Example Away FC",
        kickoff_display="18/08 Tuesday 20:00",
        kickoff_day=18,
        kickoff_month=8,
        kickoff_weekday="Tuesday",
        kickoff_hour=20,
        kickoff_minute=0,
        kickoff_timezone="GMT",
        utc_offset_seconds=0,
        sportybet_kickoff_year=None,
        sportybet_kickoff_utc=None,
        sportybet_year_proven=False,
        disposition=partial.PartialCalendarDisposition.NO_EXACT_PARTIAL_CALENDAR_MATCH,
        exact_match_count=0,
        matched_fixture=None,
        safety=partial._default_safety(),
    )


def test_output_event_url_must_bind_event_and_sport_identity() -> None:
    value = _candidate()
    wrong_event = DETAIL_URL.replace("A123", "A999")
    with pytest.raises(partial.SportyBetFotMobPartialCalendarError):
        dataclasses.replace(value, event_source_url=wrong_event)
    with pytest.raises(partial.SportyBetFotMobPartialCalendarError):
        dataclasses.replace(value, sportybet_event_id="sr:match:999")


def test_output_terms_url_and_rule_are_exact() -> None:
    value = _candidate()
    with pytest.raises(partial.SportyBetFotMobPartialCalendarError):
        dataclasses.replace(value, terms_source_url="https://www.sportybet.com/ng/help")
    with pytest.raises(partial.SportyBetFotMobPartialCalendarError):
        dataclasses.replace(value, terms_rule_sha256="0" * 64)


def test_output_display_and_scalar_calendar_must_be_structurally_identical() -> None:
    value = _candidate()
    with pytest.raises(partial.SportyBetFotMobPartialCalendarError):
        dataclasses.replace(value, kickoff_hour=19)
    with pytest.raises(partial.SportyBetFotMobPartialCalendarError):
        dataclasses.replace(value, kickoff_day=31, kickoff_month=4)
    with pytest.raises(partial.SportyBetFotMobPartialCalendarError):
        dataclasses.replace(value, home_display="Example Away FC", away_display="Example Away FC")


def test_output_cannot_change_matching_basis_or_gmt_state() -> None:
    value = _candidate()
    with pytest.raises(partial.SportyBetFotMobPartialCalendarError):
        dataclasses.replace(value, matching_basis="FUZZY")
    with pytest.raises(partial.SportyBetFotMobPartialCalendarError):
        dataclasses.replace(value, kickoff_timezone="WAT")
    with pytest.raises(partial.SportyBetFotMobPartialCalendarError):
        dataclasses.replace(value, utc_offset_seconds=3600)


def test_output_cannot_promote_any_safety_authority() -> None:
    value = _candidate()
    for key in partial._SAFETY_KEYS:
        promoted = dict(value.safety)
        promoted[key] = True
        with pytest.raises(partial.SportyBetFotMobPartialCalendarError):
            dataclasses.replace(value, safety=promoted)
