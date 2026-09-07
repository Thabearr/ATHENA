from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from domain import current_shadow_fixture_identity_v2 as identity
from domain import current_shadow_sportybet_catalog_fanout_reconciliation as reconciliation
from scripts import current_shadow_fixture_identity_reconciliation_recovery as recovery


UTC = timezone.utc


def _fotmob_raw(*, match_id, kickoff, ccode, primary, competition, home_id, home, away_id, away):
    import json

    return json.dumps(
        {
            "leagues": [
                {
                    "ccode": ccode,
                    "primaryId": primary,
                    "name": competition,
                    "matches": [
                        {
                            "id": match_id,
                            "home": {"id": home_id, "name": home, "longName": home},
                            "away": {"id": away_id, "name": away, "longName": away},
                            "status": {
                                "utcTime": kickoff.isoformat().replace("+00:00", "Z")
                            },
                        }
                    ],
                }
            ]
        },
        separators=(",", ":"),
    ).encode()


def _provider_raw(*, event_id, kickoff, category, tournament, competition, home_id, home, away_id, away):
    import json

    return json.dumps(
        {
            "eventId": event_id,
            "estimateStartTime": int(kickoff.timestamp() * 1000),
            "homeTeamId": home_id,
            "homeTeamName": home,
            "awayTeamId": away_id,
            "awayTeamName": away,
            "sport": {
                "category": {
                    "id": category,
                    "tournament": {"id": tournament, "name": competition},
                }
            },
        },
        separators=(",", ":"),
    ).encode()


def _event(event_id, kickoff, competition, home, away):
    return SimpleNamespace(
        event_id=event_id,
        kickoff_utc=kickoff,
        competition_name=competition,
        home_team_name=home,
        away_team_name=away,
    )


def _row(match_id, kickoff, competition, home, away):
    return SimpleNamespace(
        source_fixture_identifier=str(match_id),
        kickoff=kickoff,
        competition=competition,
        home_team=home,
        away_team=away,
    )


def test_v3_recovers_exact_same_country_competition_primary_id_drift():
    identity.reset_runtime_evidence()
    kickoff = datetime(2026, 9, 7, 18, 0, tzinfo=UTC)
    identity.observe_fotmob_payload(
        _fotmob_raw(
            match_id=5749662,
            kickoff=kickoff,
            ccode="ITA",
            primary=55,
            competition="Serie A",
            home_id=8529,
            home="Cagliari",
            away_id=9888,
            away="Lecce",
        )
    )
    identity.observe_provider_payload(
        _provider_raw(
            event_id="sr:match:71945228",
            kickoff=kickoff,
            category="sr:category:31",
            tournament="sr:tournament:328",
            competition="Serie A",
            home_id="sr:competitor:2719",
            home="Cagliari",
            away_id="sr:competitor:2689",
            away="Lecce",
        )
    )
    event = _event("sr:match:71945228", kickoff, "Serie A", "Cagliari", "Lecce")
    row = _row(5749662, kickoff, "Serie A", "Cagliari", "Lecce")

    # V2 has the provider tournament bound to the older ITA primary 141 seed.
    assert identity.match_event(event, (row,)) == ()
    assert recovery.match_event(event, (row,)) == (row,)


def test_v3_binds_unseen_competition_from_two_confirmed_teams_not_display_label():
    identity.reset_runtime_evidence()
    kickoff = datetime(2026, 9, 8, 19, 0, tzinfo=UTC)
    identity.observe_fotmob_payload(
        _fotmob_raw(
            match_id=6106242,
            kickoff=kickoff,
            ccode="INT",
            primary=42,
            competition="Champions League",
            home_id=900001,
            home="Real Madrid",
            away_id=900002,
            away="Inter",
        )
    )
    identity.observe_provider_payload(
        _provider_raw(
            event_id="sr:match:74165878",
            kickoff=kickoff,
            category="sr:category:393",
            tournament="sr:tournament:7",
            competition="UEFA Champions League",
            home_id="sr:competitor:2829",
            home="Real Madrid",
            away_id="sr:competitor:2697",
            away="Inter",
        )
    )
    event = _event(
        "sr:match:74165878",
        kickoff,
        "UEFA Champions League",
        "Real Madrid",
        "Inter",
    )
    row = _row(6106242, kickoff, "Champions League", "Real Madrid", "Inter")

    assert identity.match_event(event, (row,)) == ()
    assert recovery.match_event(event, (row,)) == (row,)


def test_v3_still_rejects_wrong_team_and_does_not_learn_competition():
    identity.reset_runtime_evidence()
    kickoff = datetime(2026, 9, 8, 19, 0, tzinfo=UTC)
    identity.observe_fotmob_payload(
        _fotmob_raw(
            match_id=9100001,
            kickoff=kickoff,
            ccode="INT",
            primary=4242,
            competition="Competition A",
            home_id=910001,
            home="Alpha",
            away_id=910002,
            away="Beta",
        )
    )
    identity.observe_provider_payload(
        _provider_raw(
            event_id="sr:match:99100001",
            kickoff=kickoff,
            category="sr:category:998",
            tournament="sr:tournament:998",
            competition="Different Competition",
            home_id="sr:competitor:991001",
            home="Alpha",
            away_id="sr:competitor:991002",
            away="Not Beta",
        )
    )
    event = _event(
        "sr:match:99100001",
        kickoff,
        "Different Competition",
        "Alpha",
        "Not Beta",
    )
    row = _row(9100001, kickoff, "Competition A", "Alpha", "Beta")
    before = dict(identity._comp_forward)
    assert recovery.match_event(event, (row,)) == ()
    assert identity._comp_forward == before


def test_worker_install_binds_new_matching_basis_into_reconciliation_contract_and_restores():
    original_match = identity.match_event
    original_basis = reconciliation.MATCHING_BASIS
    original_expected = reconciliation.EXPECTED_CONTRACT_SHA256
    hooks = recovery.install(reconciliation)
    try:
        assert identity.match_event is recovery.match_event
        assert reconciliation.MATCHING_BASIS == recovery.MATCHING_BASIS
        assert reconciliation.EXPECTED_CONTRACT_SHA256 != original_expected
        assert reconciliation.validate_contract()["contract_sha256"] == (
            reconciliation.EXPECTED_CONTRACT_SHA256
        )
    finally:
        recovery.restore(reconciliation, hooks)
    assert identity.match_event is original_match
    assert reconciliation.MATCHING_BASIS == original_basis
    assert reconciliation.EXPECTED_CONTRACT_SHA256 == original_expected
