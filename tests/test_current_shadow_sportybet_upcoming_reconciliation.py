from __future__ import annotations

from datetime import datetime, timezone
import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from domain import current_shadow_all_market_runner as runner
from domain import current_shadow_fixture_identity_compatibility as identity_compatibility
from domain import current_shadow_fixture_identity_v2 as identity_v2
from domain import current_shadow_sportybet_upcoming_reconciliation as current
from domain import current_shadow_sportybet_pc_upcoming_reconciliation as pc_upcoming

UTC = timezone.utc
OBSERVED = datetime(2026, 8, 29, 6, 37, 52, 774398, tzinfo=UTC)
NONCE = int(OBSERVED.timestamp() * 1000) - 250
KICKOFF_MS = int(datetime(2026, 8, 29, 7, 0, tzinfo=UTC).timestamp() * 1000)


def _pr258_shape() -> bytes:
    return json.dumps(
        {
            "bizCode": 10000,
            "message": "0#0",
            "data": [
                {
                    "eventId": "sr:match:111111113587576",
                    "estimateStartTime": KICKOFF_MS,
                    "status": 0,
                    "matchStatus": "Not start",
                    "homeTeamId": "sr:competitor:291001",
                    "homeTeamName": "Seosan FC",
                    "awayTeamId": "sr:competitor:291002",
                    "awayTeamName": "Namyangju FC",
                    "sport": {
                        "id": "sr:sport:1",
                        "name": "Football",
                        "category": {
                            "id": "sr:category:291",
                            "name": "Republic of Korea",
                            "tournament": {
                                "id": "sr:tournament:48521",
                                "name": "K4 League",
                            },
                        },
                    },
                    "markets": [
                        {
                            "id": "18",
                            "specifier": "total=1.5",
                            "desc": "Over/Under",
                            "status": 0,
                            "outcomes": [
                                {"id": "12", "odds": "1.23", "isActive": 1, "desc": "Over 1.5"},
                                {"id": "13", "odds": "3.60", "isActive": 1, "desc": "Under 1.5"},
                            ],
                        }
                    ],
                }
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def test_contract_mirrors_exact_pr258_upcoming_path_without_changing_shared_contract():
    identity = current.validate_contract()
    assert current.UPCOMING_PATH == "/api/ng/factsCenter/wapConfigurableUpcomingEvents"
    assert identity["reviewed_reconciliation_contract_sha256"] == (
        "64c7a2b71304f94a39de7e608be1f76a10e14a1a52a338f89d1c695ba0e5f1ee"
    )
    assert current.EXPECTED_CONTRACT_SHA256 == current.calculate_contract_sha256()
    assert current.CURRENT_SHADOW_UPCOMING_POLICY_ID == (
        "ATHENA_CURRENT_SHADOW_UPCOMING_DISCOVERY_V1"
    )
    assert current.CURRENT_SHADOW_UPCOMING_COMPATIBILITY_SHA256 == (
        current.calculate_current_shadow_upcoming_compatibility_sha256()
    )
    assert current.validate_contract()["identity_compatibility_policy_id"] == (
        "ATHENA_CURRENT_SHADOW_FIXTURE_IDENTITY_COMPATIBILITY_V1"
    )
    assert current.validate_contract()["identity_compatibility_policy_sha256"] == (
        "dbef6539dd7c5d1c1589debe8daca9378ea2e0c0bb32acf3315a0d1a005c2b58"
    )
    compatibility = identity_compatibility.validate_contract()
    assert compatibility["provider_evidence_observation_policy_id"] == (
        "VERIFIED_PROVIDER_RAW_BYTES_PLUS_RAW_ANCESTRY_BOUND_ATHENA_PCUPCOMING_PROJECTION_V2"
    )
    assert compatibility["policy_sha256"] == (
        "dbef6539dd7c5d1c1589debe8daca9378ea2e0c0bb32acf3315a0d1a005c2b58"
    )
    assert current.CURRENT_SHADOW_UPCOMING_POLICY_ID == (
        "ATHENA_CURRENT_SHADOW_UPCOMING_DISCOVERY_V1"
    )
    assert runner.reconciliation is pc_upcoming


def test_request_matches_pr258_public_anonymous_upcoming_shape():
    target = current.request_target(NONCE)
    parsed = urlsplit(target)
    assert parsed.path == "/api/ng/factsCenter/wapConfigurableUpcomingEvents"
    assert parse_qs(parsed.query) == {
        "sportId": ["sr:sport:1"],
        "_t": [str(NONCE)],
    }
    headers = dict(current.REQUEST_HEADERS)
    assert headers["OperId"] == "2"
    assert "Cookie" not in headers and "Authorization" not in headers


def test_exact_pr258_upcoming_row_preserves_identity_competition_and_kickoff():
    snapshot = current._parse_snapshot(
        _pr258_shape(), request_nonce_ms=NONCE, observed_at=OBSERVED
    )
    assert len(snapshot.events) == 1
    event = snapshot.events[0]
    assert event.event_id == "sr:match:111111113587576"
    assert event.home_team_name == "Seosan FC"
    assert event.away_team_name == "Namyangju FC"
    assert event.competition_name == "K4 League"
    assert event.competition_basis == "EVENT_NESTED_TOURNAMENT_NAME"
    assert event.kickoff_utc == datetime(2026, 8, 29, 7, 0, tzinfo=UTC)
    assert event.prematch_bookable_observed is True
    assert event.source_raw_sha256 == snapshot.raw_sha256
    assert event.source_observed_at == OBSERVED


def test_upcoming_source_assessment_exposes_prospective_counts():
    snapshot = current._parse_snapshot(
        _pr258_shape(), request_nonce_ms=NONCE, observed_at=OBSERVED
    )
    assessment = current.prospective_discovery_assessment(
        snapshot, evaluation_time=OBSERVED
    )
    assert assessment["provider_event_count"] == 1
    assert assessment["provider_prematch_bookable_count"] == 1
    assert assessment["provider_inplay_count"] == 0
    assert assessment["provider_future_lead_eligible_count"] == 1
    assert assessment["provider_too_close_count"] == 0
    assert assessment["source_viability"] == current.PROSPECTIVE_DISCOVERY_ELIGIBLE


def test_upcoming_raw_provider_native_ids_are_observed_before_stable_identity_match():
    kickoff = datetime(2026, 8, 29, 7, 0, tzinfo=UTC)
    fotmob_raw = json.dumps({
        "leagues": [{
            "ccode": "ENG",
            "primaryId": 48,
            "name": "Championship",
            "matches": [{
                "id": 5836800,
                "home": {"id": 10172, "name": "QPR", "longName": "Queens Park Rangers"},
                "away": {"id": 8344, "name": "Cardiff", "longName": "Cardiff City"},
                "status": {"utcTime": kickoff.isoformat().replace("+00:00", "Z")},
            }],
        }]
    }, separators=(",", ":")).encode()
    provider_raw = json.dumps({
        "bizCode": 10000,
        "message": "0#0",
        "data": [{
            "eventId": "sr:match:72339764",
            "estimateStartTime": int(kickoff.timestamp() * 1000),
            "status": 0,
            "matchStatus": "Not start",
            "homeTeamId": "sr:competitor:1",
            "homeTeamName": "QPR Provider Renamed",
            "awayTeamId": "sr:competitor:61",
            "awayTeamName": "Cardiff Provider Renamed",
            "sport": {"id": "sr:sport:1", "category": {
                "id": "sr:category:1",
                "tournament": {"id": "sr:tournament:18", "name": "Championship"},
            }},
        }]
    }, separators=(",", ":")).encode()
    snapshot = current._parse_snapshot(
        provider_raw, request_nonce_ms=NONCE, observed_at=OBSERVED
    )
    reviewed = SimpleNamespace(
        source_fixture_identifier="5836800",
        kickoff=kickoff,
        competition="Championship",
        home_team="QPR",
        away_team="Cardiff",
    )
    identity_compatibility.begin_identity_scope(
        ((fotmob_raw, {"source": "test"}),),
        provider_raw_bytes=(provider_raw,),
    )
    try:
        event = snapshot.events[0]
        assert identity_v2._provider[event.event_id]["home_id"] == "sr:competitor:1"
        assert identity_v2._provider[event.event_id]["away_id"] == "sr:competitor:61"
        assert identity_v2._provider[event.event_id]["category"] == "sr:category:1"
        assert identity_v2._provider[event.event_id]["tournament"] == "sr:tournament:18"
        assert event.home_team_name != reviewed.home_team
        assert event.away_team_name != reviewed.away_team
        assert identity_compatibility.match_current_shadow_event(event, (reviewed,)) == (reviewed,)
        evidence = identity_compatibility.identity_state_snapshot()["evidence_records"][-1]
        assert evidence["home_provider_competitor_id"] == "sr:competitor:1"
        assert evidence["away_provider_competitor_id"] == "sr:competitor:61"
        assert evidence["provider_category_id"] == "sr:category:1"
        assert evidence["provider_tournament_id"] == "sr:tournament:18"
        assert len(identity_compatibility.identity_state_snapshot()["learned_team_identities"]) == 0
    finally:
        identity_v2.reset_runtime_evidence()
