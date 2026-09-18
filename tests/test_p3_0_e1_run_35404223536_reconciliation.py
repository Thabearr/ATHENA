"""Offline retained-evidence projection for failed P3.0-E1 run 35404223536.

This is deliberately a bounded projection of the retained diagnostics artifact,
not fresh provider evidence.  It exercises the same V3 recovery boundary used by
the P3.0-E1 pre-Router compatibility scope.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

from domain import current_shadow_fixture_identity_v2 as identity
from scripts import current_shadow_fixture_identity_reconciliation_recovery as recovery


UTC = timezone.utc
RUN_ID = 35404223536
ARTIFACT_ID = 10571711837
ARTIFACT_SHA256 = "4f5947c2317fb42709001174e72e72d51881f4389f35ebdd8657ec6b2713c959"


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


# event id, kickoff, category, tournament, provider competition, home id/name, away id/name
EVENTS = (
    ("sr:match:66299550", "2026-09-18T23:30:00Z", "sr:category:26", "sr:tournament:242", "MLS", "sr:competitor:167510", "New York City FC", "sr:competitor:2506", "New York Red Bulls"),
    ("sr:match:67817882", "2026-09-19T07:30:00Z", "sr:category:291", "sr:tournament:410", "K-League 1", "sr:competitor:92539", "Bucheon FC 1995", "sr:competitor:7647", "Gimcheon Sangmu FC"),
    ("sr:match:67912308", "2026-09-19T02:00:00Z", "sr:category:26", "sr:tournament:1690", "National Womens Soccer League", "sr:competitor:874723", "San Diego Wave FC", "sr:competitor:781494", "Kansas City Current"),
    ("sr:match:71936122", "2026-09-19T01:00:00Z", "sr:category:20", "sr:tournament:406", "Liga 1", "sr:competitor:2311", "Alianza Lima", "sr:competitor:655781", "Asociacion Deportiva Tarma"),
    ("sr:match:72053630", "2026-09-19T02:00:00Z", "sr:category:289", "sr:tournament:27092", "Primera Division", "sr:competitor:6576", "Perez Zeledon", "sr:competitor:313515", "Sporting FC"),
    ("sr:match:111111114343675", "2026-09-19T07:50:00Z", "sr:category:291", "sr:simple_tournament:191116", "K3/K4 Championship", "sr:competitor:1111111447098", "FC Pocheon", "sr:competitor:1111111527359", "Busan Transportation Corporation"),
    ("sr:match:111111114362588", "2026-09-19T08:30:00Z", "sr:category:368", "sr:tournament:20560", "Championship", "sr:competitor:1111111543591", "PSPS Pekanbaru", "sr:competitor:1111111129618", "Persiraja Banda Aceh"),
    ("sr:match:111111114435208", "2026-09-18T23:45:00Z", "sr:category:280", "sr:tournament:27216", "Primera Division Reserve, Clausura", "sr:competitor:274673", "Nacional Asuncion Reserve", "sr:competitor:1098853", "Sportivo 2 de Mayo"),
    ("sr:match:111111114466414", "2026-09-19T08:00:00Z", "sr:category:291", "sr:tournament:48521", "K4 League", "sr:competitor:11111111727011", "Jecheon Citizen FC", "sr:competitor:11111111266817", "Geoje FC"),
    ("sr:match:68728734", "2026-09-19T06:00:00Z", "sr:category:52", "sr:tournament:2529", "Nadeshiko League, Div. 1, Women", "sr:competitor:371240", "AS Harima Albion", "sr:competitor:522242", "NGU Loveledge Nagoya"),
)

# fixture, kickoff, ccode, primary, source competition, home id/name, away id/name
FIXTURES = (
    (5071366, "2026-09-18T23:30:00Z", "USA", 130, "Major League Soccer", 546238, "New York City FC", 6514, "Red Bull New York"),
    (5140036, "2026-09-19T07:30:00Z", "KOR", 9080, "K-League 1", 429441, "Bucheon FC 1995", 133901, "Gimcheon Sangmu"),
    (5161643, "2026-09-19T02:00:00Z", "USA", 9134, "NWSL", 1335917, "San Diego Wave FC (W)", 1237561, "Kansas City Current (W)"),
    (1000017238, "2026-09-19T01:00:00Z", "PER", 131, "Liga 1", 6398, "Alianza Lima", 1104719, "Asociación Deportiva Tarma"),
    (5833797, "2026-09-19T02:00:00Z", "CRC", 121, "Primera Division Apertura", 49730, "Municipal Pérez Zeledón", 776638, "Sporting FC"),
)


def _fotmob_payload() -> bytes:
    leagues = []
    for fixture, kickoff, ccode, primary, competition, home_id, home, away_id, away in FIXTURES:
        leagues.append({"ccode": ccode, "primaryId": primary, "name": competition, "matches": [{"id": fixture, "home": {"id": home_id, "name": home, "longName": home}, "away": {"id": away_id, "name": away, "longName": away}, "status": {"utcTime": kickoff}}]})
    return json.dumps({"leagues": leagues}, ensure_ascii=False, separators=(",", ":")).encode()


def _provider_payload() -> bytes:
    values = []
    for event_id, kickoff, category, tournament, competition, home_id, home, away_id, away in EVENTS:
        values.append({"eventId": event_id, "estimateStartTime": int(_utc(kickoff).timestamp() * 1000), "homeTeamId": home_id, "homeTeamName": home, "awayTeamId": away_id, "awayTeamName": away, "sport": {"category": {"id": category, "tournament": {"id": tournament, "name": competition}}}})
    return json.dumps({"events": values}, ensure_ascii=False, separators=(",", ":")).encode()


def _rows():
    return tuple(SimpleNamespace(source_fixture_identifier=str(row[0]), kickoff=_utc(row[1]), competition=row[4], home_team=row[6], away_team=row[8]) for row in FIXTURES)


def _event(row):
    return SimpleNamespace(event_id=row[0], kickoff_utc=_utc(row[1]), competition_name=row[4], home_team_name=row[6], away_team_name=row[8])


@pytest.fixture(autouse=True)
def _runtime_evidence():
    identity.reset_runtime_evidence()
    identity.observe_fotmob_payload(_fotmob_payload())
    identity.observe_provider_payload(_provider_payload())
    yield
    identity.reset_runtime_evidence()


def test_all_ten_retained_events_are_accounted_for_with_five_exact_admissions():
    rows = _rows()
    matched = {event[0]: recovery.match_event(_event(event), rows) for event in EVENTS}
    assert {key: tuple(row.source_fixture_identifier for row in value) for key, value in matched.items()} == {
        "sr:match:66299550": ("5071366",),
        "sr:match:67817882": ("5140036",),
        "sr:match:67912308": ("5161643",),
        "sr:match:71936122": ("1000017238",),
        "sr:match:72053630": ("5833797",),
        "sr:match:111111114343675": (),
        "sr:match:111111114362588": (),
        "sr:match:111111114435208": (),
        "sr:match:111111114466414": (),
        "sr:match:68728734": (),
    }
    assert set(map(tuple, identity._learned_team_rows())) == {
        (546238, "sr:competitor:167510"), (6514, "sr:competitor:2506"),
        (429441, "sr:competitor:92539"), (133901, "sr:competitor:7647"),
        (1335917, "sr:competitor:874723"), (1237561, "sr:competitor:781494"),
        (6398, "sr:competitor:2311"), (1104719, "sr:competitor:655781"),
        (49730, "sr:competitor:6576"), (776638, "sr:competitor:313515"),
    }
    assert set(map(tuple, identity._learned_comp_rows())) == {
        ("USA", 130, "sr:category:26", "sr:tournament:242"),
        ("KOR", 9080, "sr:category:291", "sr:tournament:410"),
        ("USA", 9134, "sr:category:26", "sr:tournament:1690"),
        ("PER", 131, "sr:category:20", "sr:tournament:406"),
        ("CRC", 121, "sr:category:289", "sr:tournament:27092"),
    }


def test_retained_replay_preserves_full_utc_and_home_away_exactness():
    event = _event(EVENTS[0]); event.kickoff_utc = event.kickoff_utc.replace(second=1)
    assert recovery.match_event(event, _rows()) == ()
    event = _event(EVENTS[0]); event.home_team_name, event.away_team_name = event.away_team_name, event.home_team_name
    assert recovery.match_event(event, _rows()) == ()


def test_retained_run_lineage_is_explicit_and_audit_has_no_execution_authority():
    transition = identity.registry_payload()["reviewed_alias_registry_transitions"][1]
    assert transition["capture_run_id"] == RUN_ID
    assert transition["source_diagnostics_artifact_id"] == ARTIFACT_ID
    assert transition["source_diagnostics_zip_sha256"] == ARTIFACT_SHA256
    assert identity._state_authority()["research_shadow_fixture_reconciliation"] is True
    assert all(not value for key, value in identity._state_authority().items() if key != "research_shadow_fixture_reconciliation")
