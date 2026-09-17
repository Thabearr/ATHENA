"""Offline replay of the bounded run-16 source-reconciliation evidence."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

from domain import current_shadow_fixture_identity_aliases as aliases
from domain import current_shadow_fixture_identity_v2 as identity
from scripts import current_shadow_fixture_identity_reconciliation_recovery as recovery


UTC = timezone.utc
RUN_ID = 35277452572
ARTIFACT_ID = 10520479660
ARTIFACT_SHA256 = "7e97785ce12d1158455fe49138376cfffa7057b294e84c8ff7316479d5949a8c"
FOTMOB_RAW_SHA256 = "0366592e6b227956d222d67de43031da82de9e4cc063f1529c01db85de722c9d"


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


PROVIDER_EVENTS = (
    ("sr:match:111111114209600", "2026-09-18T01:00:00Z", "sr:category:526", "sr:tournament:19490", "Liga Prom", "sr:competitor:629420", "Champions FC Academy", "sr:competitor:1227541", "Chorrillo FC"),
    ("sr:match:111111114209602", "2026-09-17T23:00:00Z", "sr:category:526", "sr:tournament:19490", "Liga Prom", "sr:competitor:781340", "Alianza FC II", "sr:competitor:1109271", "Academia Costa Del Este"),
    ("sr:match:111111114408558", "2026-09-18T10:30:00Z", "sr:category:352", "sr:simple_tournament:16086", "Bangalore Super Division", "sr:competitor:11111111078157", "Kickstart FC", "sr:competitor:11111111078159", "Bangalore Dream United"),
    ("sr:match:111111114427068", "2026-09-17T22:00:00Z", "sr:category:57", "sr:tournament:37127", "Copa Uruguay", "sr:competitor:11111111347619", "Durazno FC", "sr:competitor:11111111303442", "Deportivo Colonia"),
    ("sr:match:111111114432617", "2026-09-18T05:30:00Z", "sr:category:352", "sr:simple_tournament:16086", "Bangalore Super Division", "sr:competitor:11111111716896", "Stride Sports FC", "sr:competitor:11111111090358", "FC Bengaluru United"),
    ("sr:match:111111114459159", "2026-09-18T08:00:00Z", "sr:category:352", "sr:simple_tournament:16086", "Bangalore Super Division", "sr:competitor:11111111548641", "FC Real Bengaluru", "sr:competitor:1111111968928", "Bengaluru B"),
    ("sr:match:68849770", "2026-09-18T08:00:00Z", "sr:category:21", "sr:tournament:879", "MFL, Division A", "sr:competitor:108405", "Ural Ekaterinburg", "sr:competitor:1243581", "Dinamo-Makhachkala Youth"),
    ("sr:match:69343126", "2026-09-18T11:00:00Z", "sr:category:278", "sr:tournament:682", "Premier League", "sr:competitor:5359", "FC Okzhetpes", "sr:competitor:5363", "FC Zhenis"),
    ("sr:match:69456602", "2026-09-18T10:00:00Z", "sr:category:99", "sr:tournament:782", "China League 1", "sr:competitor:793018", "Yanbian Longding", "sr:competitor:1110267", "Guandong GZ-Power FC"),
    ("sr:match:69456604", "2026-09-18T11:00:00Z", "sr:category:99", "sr:tournament:782", "China League 1", "sr:competitor:1110197", "Dalian Kun City", "sr:competitor:252173", "Ningbo Professional FC"),
)


FOTMOB_FIXTURES = (
    (5898723, "2026-09-18T01:00:00Z", "MEX", 8976, "Liga de Expansion MX Apertura", 162415, "Alacranes de Durango", 598513, "Cruz Azul Hidalgo"),
    (6052545, "2026-09-18T10:30:00Z", "INT", 9833, "Asian Games Grp. D", 610874, "Saudi Arabia U23", 304032, "Qatar U23"),
    (1000019053, "2026-09-17T22:00:00Z", "BOL", 144, "Primera División", 1074622, "Real Tomayapo", 1844, "Oriente Petrolero"),
    (5204254, "2026-09-18T11:00:00Z", "KAZ", 225, "Premier League", 2128, "Okzhetpes Kokshetau", 1614087, "Zhenis"),
    (5207231, "2026-09-18T10:00:00Z", "CHN", 9137, "China League", 1282988, "Yanbian Longding", 1623678, "Guangdong GZ-Power"),
    (5207232, "2026-09-18T11:00:00Z", "CHN", 9137, "China League", 1617860, "Dalian K'un City", 585867, "Ningbo Professional"),
    (6135727, "2026-09-18T11:00:00Z", "VIE", 10161, "Cup", 1151181, "Bình Định", 614354, "Công An Hà Nội"),
)


def _fotmob_payload() -> bytes:
    leagues = []
    for match_id, kickoff, ccode, primary, comp, home_id, home, away_id, away in FOTMOB_FIXTURES:
        leagues.append({"ccode": ccode, "primaryId": primary, "name": comp, "matches": [{"id": match_id, "home": {"id": home_id, "name": home, "longName": home}, "away": {"id": away_id, "name": away, "longName": away}, "status": {"utcTime": kickoff}}]})
    return json.dumps({"leagues": leagues}, ensure_ascii=False, separators=(",", ":")).encode()


def _provider_payload() -> bytes:
    events = []
    for event_id, kickoff, category, tournament, comp, home_id, home, away_id, away in PROVIDER_EVENTS:
        events.append({"eventId": event_id, "estimateStartTime": int(_utc(kickoff).timestamp() * 1000), "homeTeamId": home_id, "homeTeamName": home, "awayTeamId": away_id, "awayTeamName": away, "sport": {"category": {"id": category, "tournament": {"id": tournament, "name": comp}}}})
    return json.dumps({"events": events}, ensure_ascii=False, separators=(",", ":")).encode()


def _rows():
    return tuple(SimpleNamespace(source_fixture_identifier=str(row[0]), kickoff=_utc(row[1]), competition=row[4], home_team=row[6], away_team=row[8]) for row in FOTMOB_FIXTURES)


def _event(row):
    return SimpleNamespace(event_id=row[0], kickoff_utc=_utc(row[1]), competition_name=row[4], home_team_name=row[6], away_team_name=row[8])


@pytest.fixture(autouse=True)
def _runtime_evidence():
    identity.reset_runtime_evidence()
    identity.observe_fotmob_payload(_fotmob_payload())
    identity.observe_provider_payload(_provider_payload())
    yield
    identity.reset_runtime_evidence()


def test_run16_all_ten_events_are_replayed_with_only_three_exact_admissions():
    rows = _rows()
    matches = {event[0]: recovery.match_event(_event(event), rows) for event in PROVIDER_EVENTS}
    assert {event_id: tuple(row.source_fixture_identifier for row in matched) for event_id, matched in matches.items()} == {
        "sr:match:69343126": ("5204254",),
        "sr:match:69456602": ("5207231",),
        "sr:match:69456604": ("5207232",),
        "sr:match:111111114209600": (),
        "sr:match:111111114209602": (),
        "sr:match:111111114408558": (),
        "sr:match:111111114427068": (),
        "sr:match:111111114432617": (),
        "sr:match:111111114459159": (),
        "sr:match:68849770": (),
    }


def test_run16_aliases_are_evidence_scoped_and_not_generic_normalization():
    assert aliases.team_identity_matches(competition="Premier League", fotmob_name="Okzhetpes Kokshetau", sportybet_name="FC Okzhetpes")
    assert aliases.team_identity_matches(competition="China League", fotmob_name="Dalian K'un City", sportybet_name="Dalian Kun City")
    assert not aliases.team_identity_matches(competition="Cup", fotmob_name="Okzhetpes Kokshetau", sportybet_name="FC Okzhetpes")
    assert not aliases.team_identity_matches(competition="China League", fotmob_name="Example", sportybet_name="Example FC")
    assert not aliases.team_identity_matches(competition="China League", fotmob_name="Dalian K'un City", sportybet_name="Dalian Kun City FC")


def test_run16_preserves_exact_kickoff_and_orientation():
    rows = _rows()
    target = list(PROVIDER_EVENTS)[7]
    event = _event(target)
    event.kickoff_utc = event.kickoff_utc.replace(second=1)
    assert recovery.match_event(event, rows) == ()
    event = _event(target)
    event.home_team_name, event.away_team_name = event.away_team_name, event.home_team_name
    assert recovery.match_event(event, rows) == ()


def test_run16_evidence_lineage_is_explicit_and_authority_stays_shadow_only():
    payload = aliases.registry_payload()
    assert payload["evidence_lineage"]["run_35277452572"]["source_diagnostics_artifact_id"] == str(ARTIFACT_ID)
    assert payload["evidence_lineage"]["run_35277452572"]["source_diagnostics_zip_sha256"] == ARTIFACT_SHA256
    assert payload["authority"]["research_shadow_fixture_reconciliation"] is True
    assert all(value is False for key, value in payload["authority"].items() if key != "research_shadow_fixture_reconciliation")
