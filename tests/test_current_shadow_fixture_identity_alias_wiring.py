from __future__ import annotations

from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

from domain import current_shadow_fixture_identity_aliases as aliases
from domain import current_shadow_fixture_identity_v2 as stable_identity
from domain import current_shadow_sportybet_catalog_fanout_reconciliation as fanout
from domain import current_shadow_sportybet_team_label_compatibility as label_compat


UTC = timezone.utc


def test_shadow_reconciliation_contract_binds_exact_alias_registry():
    identity = fanout.validate_contract()
    assert fanout.MATCHING_BASIS == stable_identity.MATCHING_BASIS
    assert fanout.FIXTURE_TEAM_ALIAS_POLICY_ID == aliases.POLICY_ID
    assert fanout.FIXTURE_TEAM_ALIAS_REGISTRY_SHA256 == aliases.REGISTRY_SHA256
    assert fanout.FIXTURE_STABLE_IDENTITY_POLICY_ID == stable_identity.POLICY_ID
    assert fanout.FIXTURE_STABLE_IDENTITY_REGISTRY_SHA256 == stable_identity.REGISTRY_SHA256
    assert fanout.TEAM_LABEL_COMPATIBILITY_POLICY_ID == label_compat.POLICY_ID
    assert fanout.TEAM_LABEL_COMPATIBILITY_POLICY_SHA256 == label_compat.EXPECTED_POLICY_SHA256
    assert identity["contract_sha256"] == fanout.EXPECTED_CONTRACT_SHA256
    assert identity["fixture_team_alias_policy_id"] == aliases.POLICY_ID
    assert identity["fixture_team_alias_registry_sha256"] == aliases.REGISTRY_SHA256
    assert identity["fixture_stable_identity_policy_id"] == stable_identity.POLICY_ID
    assert identity["fixture_stable_identity_registry_sha256"] == stable_identity.REGISTRY_SHA256
    assert identity["team_label_compatibility_policy_id"] == label_compat.POLICY_ID
    assert identity["team_label_compatibility_policy_sha256"] == label_compat.EXPECTED_POLICY_SHA256


def test_candidate_local_shadow_module_preserves_alias_fallback_without_mutating_frozen_reviewed_module():
    kickoff = datetime(2026, 9, 1, 18, 45, tzinfo=UTC)
    event = SimpleNamespace(
        competition_name="Championship",
        home_team_name="Lincoln City",
        away_team_name="Blackburn Rovers",
        kickoff_utc=kickoff,
    )
    reviewed_row = SimpleNamespace(
        competition="Championship",
        home_team="Lincoln",
        away_team="Blackburn",
        kickoff=kickoff,
    )

    assert fanout.legacy.reviewed._match_event(event, (reviewed_row,)) == (reviewed_row,)
    assert fanout.reviewed._match_event(event, (reviewed_row,)) == ()


def _provider_event(*, event_id: str, home: str, away: str, kickoff_ms: int) -> dict:
    return {
        "eventId": event_id,
        "sportId": "sr:sport:1",
        "homeTeamName": home,
        "awayTeamName": away,
        "tournamentName": "Evidence League",
        "estimateStartTime": kickoff_ms,
        "status": 0,
        "bookingStatus": "Booked",
        "matchStatus": "Not start",
    }


def test_reviewed_shadow_projection_admits_exact_observed_home_label_and_retains_raw_sha():
    raw_sha = "9df644f04346dee648eeaaeb40756d3e063fe81f3aa68359277dceb7730033f4"
    event = fanout.legacy.reviewed._event_from_mapping(
        _provider_event(
            event_id="sr:match:73831434",
            home="Jeugd Royal Francs Borains ",
            away="KVC Westerlo",
            kickoff_ms=1788546600000,
        ),
        inherited_competition=None,
        page_num=1,
        raw_sha256=raw_sha,
        observed_at=datetime(2026, 9, 3, 10, 20, tzinfo=UTC),
    )
    assert event.home_team_name == "Jeugd Royal Francs Borains"
    assert event.away_team_name == "KVC Westerlo"
    assert event.source_raw_sha256 == raw_sha


def test_reviewed_shadow_projection_admits_exact_observed_away_label():
    event = fanout.legacy.reviewed._event_from_mapping(
        _provider_event(
            event_id="sr:match:74207246",
            home="Deportivo Mixco",
            away="Comunicaciones FC ",
            kickoff_ms=1788642000000,
        ),
        inherited_competition=None,
        page_num=1,
        raw_sha256="6ca26904b3682f13cf936d1b43fa273fcffd3521668c196c6e625992e272ac80",
        observed_at=datetime(2026, 9, 3, 10, 20, tzinfo=UTC),
    )
    assert event.home_team_name == "Deportivo Mixco"
    assert event.away_team_name == "Comunicaciones FC"


def test_reviewed_shadow_projection_admits_exact_run33_home_label_and_retains_raw_sha():
    raw_sha = "aaffe08813262c4356a53acec4f697d05dcc155862cb3854385965bd779a5597"
    event = fanout.legacy.reviewed._event_from_mapping(
        _provider_event(
            event_id="sr:match:73805972",
            home="SC Kiyovu ",
            away="Gorilla FC",
            kickoff_ms=1788627600000,
        ),
        inherited_competition=None,
        page_num=1,
        raw_sha256=raw_sha,
        observed_at=datetime(2026, 9, 4, 18, 50, 34, tzinfo=UTC),
    )
    assert event.home_team_name == "SC Kiyovu"
    assert event.away_team_name == "Gorilla FC"
    assert event.source_raw_sha256 == raw_sha


def test_fanout_parser_uses_exact_reviewed_projection_and_preserves_response_ancestry():
    observed = datetime(2026, 9, 3, 10, 20, tzinfo=UTC)
    nonce = int(observed.timestamp() * 1000) - 1000
    raw = json.dumps(
        {
            "bizCode": 10000,
            "data": [
                _provider_event(
                    event_id="sr:match:73831434",
                    home="Jeugd Royal Francs Borains ",
                    away="KVC Westerlo",
                    kickoff_ms=1788546600000,
                )
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    observation, events = fanout._parse_tournament_response(
        raw,
        category_id="sr:category:33",
        tournament_id="sr:tournament:1117",
        request_nonce_ms=nonce,
        observed_at=observed,
    )
    assert len(events) == 1
    assert events[0].home_team_name == "Jeugd Royal Francs Borains"
    assert events[0].source_raw_sha256 == observation.raw_sha256
    assert observation.event_ids == ("sr:match:73831434",)


def test_fanout_parser_admits_exact_run33_projection_and_preserves_response_ancestry():
    observed = datetime(2026, 9, 4, 18, 50, 34, tzinfo=UTC)
    nonce = int(observed.timestamp() * 1000) - 1000
    raw = json.dumps(
        {
            "bizCode": 10000,
            "data": [
                _provider_event(
                    event_id="sr:match:73805972",
                    home="SC Kiyovu ",
                    away="Gorilla FC",
                    kickoff_ms=1788627600000,
                )
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    observation, events = fanout._parse_tournament_response(
        raw,
        category_id="sr:category:951",
        tournament_id="sr:tournament:20162",
        request_nonce_ms=nonce,
        observed_at=observed,
    )
    assert len(events) == 1
    assert events[0].home_team_name == "SC Kiyovu"
    assert events[0].source_raw_sha256 == observation.raw_sha256
    assert observation.event_ids == ("sr:match:73805972",)


def test_unreviewed_trailing_space_or_changed_whitespace_fails_closed():
    observed = datetime(2026, 9, 3, 10, 20, tzinfo=UTC)
    for value in (
        _provider_event(
            event_id="sr:match:99999999",
            home="Unknown FC ",
            away="Other FC",
            kickoff_ms=1788546600000,
        ),
        _provider_event(
            event_id="sr:match:73831434",
            home="Jeugd Royal Francs Borains  ",
            away="KVC Westerlo",
            kickoff_ms=1788546600000,
        ),
        _provider_event(
            event_id="sr:match:73831434",
            home=" Jeugd Royal Francs Borains",
            away="KVC Westerlo",
            kickoff_ms=1788546600000,
        ),
        _provider_event(
            event_id="sr:match:73805972",
            home="SC Kiyovu  ",
            away="Gorilla FC",
            kickoff_ms=1788627600000,
        ),
    ):
        with pytest.raises(
            fanout.reviewed.SportyBetCurrentEventDiscoveryError,
            match="outside reviewed evidence",
        ):
            fanout.legacy.reviewed._event_from_mapping(
                value,
                inherited_competition=None,
                page_num=1,
                raw_sha256="a" * 64,
                observed_at=observed,
            )


def test_frozen_non_shadow_parser_still_rejects_the_observed_trailing_space():
    for value in (
        _provider_event(
            event_id="sr:match:73831434",
            home="Jeugd Royal Francs Borains ",
            away="KVC Westerlo",
            kickoff_ms=1788546600000,
        ),
        _provider_event(
            event_id="sr:match:73805972",
            home="SC Kiyovu ",
            away="Gorilla FC",
            kickoff_ms=1788627600000,
        ),
    ):
        with pytest.raises(
            fanout.reviewed.SportyBetCurrentEventDiscoveryError,
            match="home_team_name must be an exact non-empty trimmed string",
        ):
            fanout.reviewed._event_from_mapping(
                value,
                inherited_competition=None,
                page_num=1,
                raw_sha256="a" * 64,
                observed_at=datetime(2026, 9, 4, 18, 50, 34, tzinfo=UTC),
            )


def test_team_label_policy_is_exactly_pinned_to_diagnostic_evidence():
    identity = label_compat.validate_policy()
    assert label_compat.SCHEMA_VERSION == 2
    assert label_compat.POLICY_ID == (
        "ATHENA_CURRENT_SHADOW_EXACT_PROVIDER_TRAILING_SPACE_LABEL_COMPATIBILITY_V2"
    )
    assert label_compat.EVIDENCE_WORKFLOW_RUN_ID == 33743684967
    assert label_compat.EVIDENCE_ARTIFACT_ID == 9888817924
    assert label_compat.EVIDENCE_ARTIFACT_SHA256 == (
        "d67c65d8b77ce61fc76a129aaf588b1b6cdf2983f728c803eaef79288f37aaef"
    )
    assert label_compat.LATEST_EVIDENCE_WORKFLOW_RUN_ID == 33907719257
    assert label_compat.LATEST_EVIDENCE_ARTIFACT_ID == 9950240221
    assert label_compat.LATEST_EVIDENCE_ARTIFACT_SHA256 == (
        "87b379f9b8163717869d3fd3d8834fc0434d548c4f2a2522120c28c0508aa609"
    )
    assert label_compat.EXPECTED_POLICY_SHA256 == (
        "ce2f87e6f5d9ad3993de5a3d679e25da9d52d9dbaff33fbb622514f67d707f0b"
    )
    assert label_compat.policy_sha256() == label_compat.EXPECTED_POLICY_SHA256
    assert identity["policy_sha256"] == label_compat.EXPECTED_POLICY_SHA256
    assert identity["latest_evidence_artifact_sha256"] == (
        label_compat.LATEST_EVIDENCE_ARTIFACT_SHA256
    )
    assert len(label_compat.REVIEWED_PROJECTIONS) == 3
    run33 = next(
        row for row in label_compat.REVIEWED_PROJECTIONS
        if row.event_id == "sr:match:73805972"
    )
    assert run33.field == "homeTeamName"
    assert run33.raw_source_label == "SC Kiyovu "
    assert run33.projected_label == "SC Kiyovu"
    assert run33.category_id == "sr:category:951"
    assert run33.tournament_id == "sr:tournament:20162"
    assert run33.source_raw_sha256 == (
        "aaffe08813262c4356a53acec4f697d05dcc155862cb3854385965bd779a5597"
    )
    assert run33.evidence_workflow_run_id == 33907719257
    assert run33.evidence_artifact_id == 9950240221
    assert run33.evidence_artifact_sha256 == label_compat.LATEST_EVIDENCE_ARTIFACT_SHA256
