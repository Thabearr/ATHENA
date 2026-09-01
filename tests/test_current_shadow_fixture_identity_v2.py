from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

from domain import current_shadow_fixture_identity_v2 as identity


UTC = timezone.utc


def _fotmob_raw(
    *,
    match_id: int,
    kickoff: datetime,
    ccode: str,
    primary_id: int,
    competition: str,
    home_id: int,
    home: str,
    home_long: str,
    away_id: int,
    away: str,
    away_long: str,
) -> bytes:
    payload = {
        "leagues": [
            {
                "ccode": ccode,
                "primaryId": primary_id,
                "name": competition,
                "matches": [
                    {
                        "id": match_id,
                        "home": {"id": home_id, "name": home, "longName": home_long},
                        "away": {"id": away_id, "name": away, "longName": away_long},
                        "status": {"utcTime": kickoff.isoformat().replace("+00:00", "Z")},
                    }
                ],
            }
        ]
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _provider_raw(
    *,
    event_id: str,
    kickoff: datetime,
    category_id: str,
    tournament_id: str,
    competition: str,
    home_id: str,
    home: str,
    away_id: str,
    away: str,
) -> bytes:
    payload = {
        "eventId": event_id,
        "estimateStartTime": int(kickoff.timestamp() * 1000),
        "homeTeamId": home_id,
        "homeTeamName": home,
        "awayTeamId": away_id,
        "awayTeamName": away,
        "sport": {
            "category": {
                "id": category_id,
                "tournament": {"id": tournament_id, "name": competition},
            }
        },
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _event(*, event_id: str, kickoff: datetime, competition: str, home: str, away: str):
    return SimpleNamespace(
        event_id=event_id,
        kickoff_utc=kickoff,
        competition_name=competition,
        home_team_name=home,
        away_team_name=away,
    )


def _reviewed(*, match_id: int, kickoff: datetime, competition: str, home: str, away: str):
    return SimpleNamespace(
        source_fixture_identifier=str(match_id),
        kickoff=kickoff,
        competition=competition,
        home_team=home,
        away_team=away,
    )


def test_registry_identity_is_pinned_to_retained_run38_evidence():
    assert identity.POLICY_ID == "ATHENA_CURRENT_SHADOW_STABLE_SOURCE_PROVIDER_IDENTITY_V2"
    assert identity.REGISTRY_SHA256 == "46375f5a7e594c2814ccf6d16576b9f540b7c9822a7417d697d94f0a74363d7e"
    assert identity.registry_sha256() == identity.REGISTRY_SHA256
    assert len(identity.TEAM_IDENTITY_SEEDS) == 64
    assert len(identity.COMPETITION_IDENTITY_SEEDS) == 12


def test_run38_denmark_competition_and_team_label_drift_use_stable_ids():
    identity.reset_runtime_evidence()
    kickoff = datetime(2026, 9, 2, 18, 0, tzinfo=UTC)
    identity.observe_fotmob_payload(_fotmob_raw(
        match_id=5739497, kickoff=kickoff, ccode="DEN", primary_id=46,
        competition="Superligaen", home_id=8071, home="AGF", home_long="AGF",
        away_id=8113, away="FC Midtjylland", away_long="FC Midtjylland",
    ))
    identity.observe_provider_payload(_provider_raw(
        event_id="sr:match:71924960", kickoff=kickoff,
        category_id="sr:category:8", tournament_id="sr:tournament:39",
        competition="Superliga", home_id="sr:competitor:1291", home="Aarhus New Label",
        away_id="sr:competitor:1289", away="Midtjylland New Label",
    ))
    event = _event(event_id="sr:match:71924960", kickoff=kickoff, competition="Superliga",
                   home="Aarhus New Label", away="Midtjylland New Label")
    reviewed = _reviewed(match_id=5739497, kickoff=kickoff, competition="Superligaen",
                         home="AGF", away="FC Midtjylland")
    assert identity.match_event(event, (reviewed,)) == (reviewed,)


def test_run38_qpr_and_cardiff_remain_matched_after_future_display_drift():
    identity.reset_runtime_evidence()
    kickoff = datetime(2026, 9, 2, 18, 45, tzinfo=UTC)
    identity.observe_fotmob_payload(_fotmob_raw(
        match_id=5836800, kickoff=kickoff, ccode="ENG", primary_id=48,
        competition="Championship", home_id=10172, home="QPR", home_long="Queens Park Rangers",
        away_id=8344, away="Cardiff", away_long="Cardiff City",
    ))
    identity.observe_provider_payload(_provider_raw(
        event_id="sr:match:72339764", kickoff=kickoff,
        category_id="sr:category:1", tournament_id="sr:tournament:18",
        competition="Championship", home_id="sr:competitor:1", home="QPR Provider Renamed",
        away_id="sr:competitor:61", away="Cardiff Provider Renamed",
    ))
    event = _event(event_id="sr:match:72339764", kickoff=kickoff, competition="Championship",
                   home="QPR Provider Renamed", away="Cardiff Provider Renamed")
    reviewed = _reviewed(match_id=5836800, kickoff=kickoff, competition="Championship",
                         home="QPR", away="Cardiff")
    assert identity.match_event(event, (reviewed,)) == (reviewed,)


def test_known_source_team_rejects_wrong_provider_competitor_even_when_name_looks_exact():
    identity.reset_runtime_evidence()
    kickoff = datetime(2026, 9, 2, 18, 45, tzinfo=UTC)
    identity.observe_fotmob_payload(_fotmob_raw(
        match_id=5836800, kickoff=kickoff, ccode="ENG", primary_id=48,
        competition="Championship", home_id=10172, home="QPR", home_long="Queens Park Rangers",
        away_id=8344, away="Cardiff", away_long="Cardiff City",
    ))
    identity.observe_provider_payload(_provider_raw(
        event_id="sr:match:99900001", kickoff=kickoff,
        category_id="sr:category:1", tournament_id="sr:tournament:18",
        competition="Championship", home_id="sr:competitor:999999", home="Queens Park Rangers",
        away_id="sr:competitor:61", away="Cardiff City",
    ))
    event = _event(event_id="sr:match:99900001", kickoff=kickoff, competition="Championship",
                   home="Queens Park Rangers", away="Cardiff City")
    reviewed = _reviewed(match_id=5836800, kickoff=kickoff, competition="Championship",
                         home="QPR", away="Cardiff")
    assert identity.match_event(event, (reviewed,)) == ()


def test_home_away_orientation_and_full_utc_remain_exact():
    identity.reset_runtime_evidence()
    kickoff = datetime(2026, 9, 2, 18, 45, tzinfo=UTC)
    identity.observe_fotmob_payload(_fotmob_raw(
        match_id=5836800, kickoff=kickoff, ccode="ENG", primary_id=48,
        competition="Championship", home_id=10172, home="QPR", home_long="Queens Park Rangers",
        away_id=8344, away="Cardiff", away_long="Cardiff City",
    ))
    identity.observe_provider_payload(_provider_raw(
        event_id="sr:match:99900002", kickoff=kickoff,
        category_id="sr:category:1", tournament_id="sr:tournament:18",
        competition="Championship", home_id="sr:competitor:61", home="Cardiff City",
        away_id="sr:competitor:1", away="Queens Park Rangers",
    ))
    reviewed = _reviewed(match_id=5836800, kickoff=kickoff, competition="Championship",
                         home="QPR", away="Cardiff")
    reversed_event = _event(event_id="sr:match:99900002", kickoff=kickoff,
                            competition="Championship", home="Cardiff City", away="Queens Park Rangers")
    assert identity.match_event(reversed_event, (reviewed,)) == ()

    exact_event = _event(event_id="sr:match:99900002", kickoff=kickoff + timedelta(seconds=1),
                         competition="Championship", home="Cardiff City", away="Queens Park Rangers")
    assert identity.match_event(exact_event, (reviewed,)) == ()


def test_new_exact_identity_bootstraps_once_then_survives_later_name_and_competition_drift():
    identity.reset_runtime_evidence()
    first = datetime(2026, 9, 10, 18, 0, tzinfo=UTC)
    second = datetime(2026, 9, 17, 18, 0, tzinfo=UTC)
    identity.observe_fotmob_payload(_fotmob_raw(
        match_id=900001, kickoff=first, ccode="TST", primary_id=777,
        competition="Test League", home_id=900001, home="Alpha", home_long="Alpha United",
        away_id=900002, away="Beta", away_long="Beta City",
    ))
    identity.observe_provider_payload(_provider_raw(
        event_id="sr:match:99000001", kickoff=first,
        category_id="sr:category:999", tournament_id="sr:tournament:999",
        competition="Test League", home_id="sr:competitor:990001", home="Alpha United",
        away_id="sr:competitor:990002", away="Beta City",
    ))
    first_event = _event(event_id="sr:match:99000001", kickoff=first, competition="Test League",
                         home="Alpha United", away="Beta City")
    first_reviewed = _reviewed(match_id=900001, kickoff=first, competition="Test League",
                               home="Alpha", away="Beta")
    assert identity.match_event(first_event, (first_reviewed,)) == (first_reviewed,)

    identity.observe_fotmob_payload(_fotmob_raw(
        match_id=900002, kickoff=second, ccode="TST", primary_id=777,
        competition="Test League", home_id=900001, home="Alpha", home_long="Alpha United",
        away_id=900002, away="Beta", away_long="Beta City",
    ))
    identity.observe_provider_payload(_provider_raw(
        event_id="sr:match:99000002", kickoff=second,
        category_id="sr:category:999", tournament_id="sr:tournament:999",
        competition="Provider League Renamed", home_id="sr:competitor:990001", home="Alpha New Display",
        away_id="sr:competitor:990002", away="Beta New Display",
    ))
    second_event = _event(event_id="sr:match:99000002", kickoff=second,
                          competition="Provider League Renamed", home="Alpha New Display", away="Beta New Display")
    second_reviewed = _reviewed(match_id=900002, kickoff=second, competition="Test League",
                                home="Alpha", away="Beta")
    assert identity.match_event(second_event, (second_reviewed,)) == (second_reviewed,)
