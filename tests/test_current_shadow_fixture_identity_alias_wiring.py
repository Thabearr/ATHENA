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


def test_reviewed_shadow_projection_admits_exact_p3_e1_blocker_away_label_and_retains_raw_sha():
    raw_sha = "46a549f09d3d4864f8b00185b8634d427d11d219e4e0545a5e3746198ec22b11"
    assert label_compat.project_team_label(
        event_id="sr:match:72474956",
        field="awayTeamName",
        value="Comunicaciones FC ",
    ) == "Comunicaciones FC"
    event = fanout.legacy.reviewed._event_from_mapping(
        _provider_event(
            event_id="sr:match:72474956",
            home="CSD Coban Imperial",
            away="Comunicaciones FC ",
            kickoff_ms=1789326000000,
        ),
        inherited_competition=None,
        page_num=1,
        raw_sha256=raw_sha,
        observed_at=datetime(2026, 9, 12, 11, 1, 42, 950736, tzinfo=UTC),
    )
    assert event.home_team_name == "CSD Coban Imperial"
    assert event.away_team_name == "Comunicaciones FC"
    assert event.source_raw_sha256 == raw_sha


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


def test_reviewed_shadow_projection_admits_exact_run126_home_label_and_retains_raw_sha():
    raw_sha = "d25423e8dfea8d8d49b15041338bb7d90e546a918471653afe5bfb5449ee0f54"
    event = fanout.legacy.reviewed._event_from_mapping(
        _provider_event(
            event_id="sr:match:74170884",
            home="Comunicaciones FC ",
            away="CD Marquense",
            kickoff_ms=1788998400000,
        ),
        inherited_competition=None,
        page_num=1,
        raw_sha256=raw_sha,
        observed_at=datetime(2026, 9, 8, 15, 12, 27, 450772, tzinfo=UTC),
    )
    assert event.home_team_name == "Comunicaciones FC"
    assert event.away_team_name == "CD Marquense"
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


def test_fanout_parser_admits_synthetic_p3_e1_tuple_and_preserves_response_ancestry():
    """Synthetic regression payload; run 34689842174 is the provider evidence."""
    observed = datetime(2026, 9, 12, 11, 1, 42, 950736, tzinfo=UTC)
    nonce = int(observed.timestamp() * 1000) - 1000
    raw = json.dumps(
        {
            "bizCode": 10000,
            "data": [
                _provider_event(
                    event_id="sr:match:72474956",
                    home="CSD Coban Imperial",
                    away="Comunicaciones FC ",
                    kickoff_ms=1789326000000,
                )
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    observation, events = fanout._parse_tournament_response(
        raw,
        category_id="sr:category:365",
        tournament_id="sr:tournament:27396",
        request_nonce_ms=nonce,
        observed_at=observed,
    )
    assert len(events) == 1
    assert events[0].away_team_name == "Comunicaciones FC"
    assert events[0].source_raw_sha256 == observation.raw_sha256
    assert observation.event_ids == ("sr:match:72474956",)


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
        _provider_event(
            event_id="sr:match:74170885",
            home="Comunicaciones FC ",
            away="CD Marquense",
            kickoff_ms=1788998400000,
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
        _provider_event(
            event_id="sr:match:74170884",
            home="Comunicaciones FC ",
            away="CD Marquense",
            kickoff_ms=1788998400000,
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
                observed_at=datetime(2026, 9, 8, 15, 12, 27, 450772, tzinfo=UTC),
            )


def test_frozen_non_shadow_parser_rejects_p3_e1_away_trailing_space():
    with pytest.raises(
        fanout.reviewed.SportyBetCurrentEventDiscoveryError,
        match="away_team_name must be an exact non-empty trimmed string",
    ):
        fanout.reviewed._event_from_mapping(
            _provider_event(
                event_id="sr:match:72474956",
                home="CSD Coban Imperial",
                away="Comunicaciones FC ",
                kickoff_ms=1789326000000,
            ),
            inherited_competition=None,
            page_num=1,
            raw_sha256="a" * 64,
            observed_at=datetime(2026, 9, 12, 11, 1, 42, 950736, tzinfo=UTC),
        )


def test_team_label_policy_is_exactly_pinned_to_diagnostic_evidence():
    identity = label_compat.validate_policy()
    assert label_compat.SCHEMA_VERSION == 4
    assert label_compat.POLICY_ID == (
        "ATHENA_CURRENT_SHADOW_EXACT_PROVIDER_TRAILING_SPACE_LABEL_COMPATIBILITY_V4"
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
    assert label_compat.CURRENT_EVIDENCE_WORKFLOW_RUN_ID == 34243048761
    assert label_compat.CURRENT_EVIDENCE_ARTIFACT_ID == 10062892966
    assert label_compat.CURRENT_EVIDENCE_ARTIFACT_SHA256 == (
        "bbc5434425443b38a20d0807cc3e85a269a02a446ff229ea7025d28b4cd0dea4"
    )
    assert label_compat.P3_E1_BLOCKER_EVIDENCE_WORKFLOW_RUN_ID == 34689842174
    assert label_compat.P3_E1_BLOCKER_EVIDENCE_ARTIFACT_ID == 10296832530
    assert label_compat.P3_E1_BLOCKER_EVIDENCE_ARTIFACT_SHA256 == (
        "0077d93de5c9cf729cf9bf6a0a1a9aaff91f4967ec8f0065d350baef0ce79db0"
    )
    assert label_compat.P3_E1_BLOCKER_EVIDENCE_CATALOG_RAW_SHA256 == (
        "94d5826c753c675063cbae29a4adcd76f85e30f5ca9913efefe981cd2c70a1e5"
    )
    assert label_compat.P3_E1_BLOCKER_EVIDENCE_TOURNAMENT_RAW_SHA256 == (
        "46a549f09d3d4864f8b00185b8634d427d11d219e4e0545a5e3746198ec22b11"
    )
    assert label_compat.P3_E1_BLOCKER_EVIDENCE_OBSERVED_AT == "2026-09-12T11:01:42.950736Z"
    assert label_compat.EXPECTED_POLICY_SHA256 == (
        "c7baf2c7c02498e11674839cf5f064a0ede6420e8d98d14e22c315b71c57b302"
    )
    assert label_compat.policy_sha256() == label_compat.EXPECTED_POLICY_SHA256
    assert identity["policy_sha256"] == label_compat.EXPECTED_POLICY_SHA256
    assert identity["latest_evidence_artifact_sha256"] == (
        label_compat.LATEST_EVIDENCE_ARTIFACT_SHA256
    )
    assert identity["current_evidence_artifact_sha256"] == (
        label_compat.CURRENT_EVIDENCE_ARTIFACT_SHA256
    )
    assert identity["p3_e1_blocker_evidence_artifact_sha256"] == (
        label_compat.P3_E1_BLOCKER_EVIDENCE_ARTIFACT_SHA256
    )
    assert len(label_compat.REVIEWED_PROJECTIONS) == 5
    old_rows = {
        ("sr:match:73831434", "homeTeamName", "Jeugd Royal Francs Borains "): (
            "Jeugd Royal Francs Borains", "sr:category:33", "sr:tournament:1117",
            "9df644f04346dee648eeaaeb40756d3e063fe81f3aa68359277dceb7730033f4",
            33743684967, 9888817924,
            "d67c65d8b77ce61fc76a129aaf588b1b6cdf2983f728c803eaef79288f37aaef",
        ),
        ("sr:match:74207246", "awayTeamName", "Comunicaciones FC "): (
            "Comunicaciones FC", "sr:category:365", "sr:tournament:27396",
            "6ca26904b3682f13cf936d1b43fa273fcffd3521668c196c6e625992e272ac80",
            33743684967, 9888817924,
            "d67c65d8b77ce61fc76a129aaf588b1b6cdf2983f728c803eaef79288f37aaef",
        ),
        ("sr:match:73805972", "homeTeamName", "SC Kiyovu "): (
            "SC Kiyovu", "sr:category:951", "sr:tournament:20162",
            "aaffe08813262c4356a53acec4f697d05dcc155862cb3854385965bd779a5597",
            33907719257, 9950240221,
            "87b379f9b8163717869d3fd3d8834fc0434d548c4f2a2522120c28c0508aa609",
        ),
        ("sr:match:74170884", "homeTeamName", "Comunicaciones FC "): (
            "Comunicaciones FC", "sr:category:365", "sr:tournament:27396",
            "d25423e8dfea8d8d49b15041338bb7d90e546a918471653afe5bfb5449ee0f54",
            34243048761, 10062892966,
            "bbc5434425443b38a20d0807cc3e85a269a02a446ff229ea7025d28b4cd0dea4",
        ),
    }
    actual_old_rows = {
        (row.event_id, row.field, row.raw_source_label): (
            row.projected_label, row.category_id, row.tournament_id,
            row.source_raw_sha256, row.evidence_workflow_run_id,
            row.evidence_artifact_id, row.evidence_artifact_sha256,
        )
        for row in label_compat.REVIEWED_PROJECTIONS
        if (row.event_id, row.field, row.raw_source_label) in old_rows
    }
    assert actual_old_rows == old_rows
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
    run126 = next(
        row for row in label_compat.REVIEWED_PROJECTIONS
        if row.event_id == "sr:match:74170884"
    )
    assert run126.field == "homeTeamName"
    assert run126.raw_source_label == "Comunicaciones FC "
    assert run126.projected_label == "Comunicaciones FC"
    assert run126.category_id == "sr:category:365"
    assert run126.tournament_id == "sr:tournament:27396"
    assert run126.source_raw_sha256 == (
        "d25423e8dfea8d8d49b15041338bb7d90e546a918471653afe5bfb5449ee0f54"
    )
    assert run126.evidence_workflow_run_id == 34243048761
    assert run126.evidence_artifact_id == 10062892966
    assert run126.evidence_artifact_sha256 == (
        label_compat.CURRENT_EVIDENCE_ARTIFACT_SHA256
    )
    blocker = next(
        row for row in label_compat.REVIEWED_PROJECTIONS
        if row.event_id == "sr:match:72474956"
    )
    assert blocker.field == "awayTeamName"
    assert blocker.raw_source_label == "Comunicaciones FC "
    assert blocker.projected_label == "Comunicaciones FC"
    assert blocker.category_id == "sr:category:365"
    assert blocker.tournament_id == "sr:tournament:27396"
    assert blocker.source_raw_sha256 == label_compat.P3_E1_BLOCKER_EVIDENCE_TOURNAMENT_RAW_SHA256
    assert blocker.evidence_workflow_run_id == 34689842174
    assert blocker.evidence_artifact_id == 10296832530
    assert blocker.evidence_artifact_sha256 == label_compat.P3_E1_BLOCKER_EVIDENCE_ARTIFACT_SHA256


@pytest.mark.parametrize(
    ("event_id", "field", "value"),
    (
        ("sr:match:99999999", "awayTeamName", "Comunicaciones FC "),
        ("sr:match:72474956", "homeTeamName", "Comunicaciones FC "),
        ("sr:match:72474956", "awayTeamName", " Comunicaciones FC"),
        ("sr:match:72474956", "awayTeamName", "Comunicaciones FC  "),
        ("sr:match:72474956", "awayTeamName", "Comunicaciones FC\t"),
        ("sr:match:72474956", "awayTeamName", "Comunicaciones FC\u00a0"),
        ("sr:match:72474956", "awayTeamName", "Different FC "),
    ),
)
def test_p3_e1_exact_tuple_rejects_all_other_whitespace_shapes(event_id, field, value):
    with pytest.raises(label_compat.CurrentShadowSportyBetTeamLabelCompatibilityError):
        label_compat.project_team_label(event_id=event_id, field=field, value=value)


def test_already_trimmed_p3_e1_label_passes_through_unchanged():
    assert label_compat.project_team_label(
        event_id="sr:match:72474956",
        field="awayTeamName",
        value="Comunicaciones FC",
    ) == "Comunicaciones FC"


def test_team_label_compatibility_authority_remains_source_schema_only():
    assert label_compat.AUTHORITY == {
        "source_schema_compatibility": True,
        "fixture_reconciliation": False,
        "canonical_market_mapping": False,
        "price_all": False,
        "market_router": False,
        "portfolio_optimization": False,
        "final_selection": False,
        "share_code_transport": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "bet": False,
        "wager_placed": False,
    }
