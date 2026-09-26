from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from types import SimpleNamespace

import pytest

from domain import current_shadow_fixture_identity_v2 as identity
from domain import current_shadow_fixture_identity_compatibility as compatibility
from domain import current_shadow_sportybet_international_provider_family_bridge as international_bridge
from domain import current_shadow_sportybet_pc_upcoming_discovery as pc_upcoming


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


def _provider_projection(
    *,
    event_id: str,
    kickoff: datetime,
    category_id: str,
    category_name: str,
    tournament_id: str,
    tournament_name: str,
    home_id: str,
    home: str,
    away_id: str,
    away: str,
    source_page_num: int = 1,
    source_observed_at: str = "2026-09-25T21:40:00Z",
) -> bytes:
    source_raw = hashlib.sha256(_projection_source_raw(
        event_id=event_id,
        kickoff=kickoff,
        category_id=category_id,
        category_name=category_name,
        tournament_id=tournament_id,
        tournament_name=tournament_name,
        home_id=home_id,
        home=home,
        away_id=away_id,
        away=away,
    )).hexdigest()
    payload = {
        "dataset": "ATHENA_PC_UPCOMING_PROVIDER_IDENTITY_PROJECTION_V1",
        "projection_policy_id": "EXACT_NATIVE_FIELDS_DERIVED_FROM_REPLAYED_PC_UPCOMING_RAW_BYTES",
        "is_provider_response": False,
        "source_policy_id": pc_upcoming.POLICY_ID,
        "source_policy_sha256": pc_upcoming.PINNED_POLICY_SHA256,
        "events": [{
            "eventId": event_id,
            "estimateStartTime": int(kickoff.timestamp() * 1000),
            "homeTeamId": home_id,
            "homeTeamName": home,
            "awayTeamId": away_id,
            "awayTeamName": away,
            "sport": {
                "id": "sr:sport:1",
                "category": {
                    "id": category_id,
                    "name": category_name,
                    "tournament": {"id": tournament_id, "name": tournament_name},
                },
            },
            "source_ancestry": {
                "source_raw_sha256": source_raw,
                "source_page_num": source_page_num,
                "source_observed_at": source_observed_at,
            },
        }],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _projection_source_raw(
    *, event_id, kickoff, category_id, category_name, tournament_id,
    tournament_name, home_id, home, away_id, away,
):
    return json.dumps({
        "eventId": event_id,
        "estimateStartTime": int(kickoff.timestamp() * 1000),
        "homeTeamId": home_id,
        "homeTeamName": home,
        "awayTeamId": away_id,
        "awayTeamName": away,
        "sport": {"category": {
            "id": category_id,
            "name": category_name,
            "tournament": {"id": tournament_id, "name": tournament_name},
        }},
    }, ensure_ascii=False, separators=(",", ":")).encode()


def _observe_provider_projection(raw_projection: bytes) -> None:
    event = json.loads(raw_projection)["events"][0]
    category = event["sport"]["category"]
    tournament = category["tournament"]
    provider_page_row = _projection_source_raw(
        event_id=event["eventId"],
        kickoff=datetime.fromtimestamp(event["estimateStartTime"] / 1000, tz=UTC),
        category_id=category["id"],
        category_name=category["name"],
        tournament_id=tournament["id"],
        tournament_name=tournament["name"],
        home_id=event["homeTeamId"],
        home=event["homeTeamName"],
        away_id=event["awayTeamId"],
        away=event["awayTeamName"],
    )
    identity.observe_provider_payload(provider_page_row)
    identity.observe_provider_identity_projection(raw_projection)


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
    assert identity.REGISTRY_SHA256 == "fae19e6db66c1dca559895fb4ae30b591628b72965989c027c5f5ae785bced3f"
    assert identity.registry_sha256() == identity.REGISTRY_SHA256
    assert len(identity.TEAM_IDENTITY_SEEDS) == 64
    assert len(identity.COMPETITION_IDENTITY_SEEDS) == 12


def test_international_bridge_keeps_club_seed_registry_sha_and_one_to_one_maps_unchanged():
    assert identity.SEED_REGISTRY_SHA256 == "7fe662fc91a80daabf1e774ddd5c8ecdb5215eaf63adb03822b3fb05f872df79"
    assert identity.seed_registry_sha256() == identity.SEED_REGISTRY_SHA256
    assert len(identity.COMPETITION_IDENTITY_SEEDS) == 12
    assert len({(row[0], row[1]) for row in identity.COMPETITION_IDENTITY_SEEDS}) == 12
    assert len({(row[2], row[3]) for row in identity.COMPETITION_IDENTITY_SEEDS}) == 12
    assert identity.REGISTRY_SHA256 == "fae19e6db66c1dca559895fb4ae30b591628b72965989c027c5f5ae785bced3f"


@pytest.mark.parametrize(
    "source_primary,source_comp,source_home,source_away,category,tournament,provider_comp",
    [
        (9806, "UEFA Nations League A Grp. 1", "Alpha A", "Beta A", "sr:category:4", "sr:tournament:23755", "UEFA Nations League"),
        (9807, "UEFA Nations League B Grp. 2", "Alpha B", "Beta B", "sr:category:4", "sr:tournament:23755", "UEFA Nations League"),
        (9808, "UEFA Nations League C Grp. 2", "Alpha C", "Beta C", "sr:category:4", "sr:tournament:23755", "UEFA Nations League"),
        (9821, "CONCACAF Nations League B Grp. 3", "Grenada", "Cuba", "sr:category:4", "sr:tournament:27420", "CONCACAF Nations League"),
        (10608, "Africa Cup of Nations Qualification Grp. A", "Alpha AF", "Beta AF", "sr:category:4", "sr:tournament:1848", "Africa Cup of Nations Qualification"),
        (114, "Friendlies", "Alpha IF", "Beta IF", "sr:category:4", "sr:tournament:851", "Int. Friendly Games"),
    ],
)
def test_exact_international_provider_family_matches_without_mutating_one_to_one_competition_state(
    source_primary, source_comp, source_home, source_away, category, tournament, provider_comp,
):
    identity.reset_runtime_evidence()
    identity.configure_persistent_state(None)
    kickoff = datetime(2026, 9, 25, 21, 0, tzinfo=UTC)
    before_forward = dict(identity._comp_forward)
    before_reverse = dict(identity._comp_reverse)
    index = source_primary
    source_home_id = 600000 + index
    source_away_id = 700000 + index
    provider_home_id = f"sr:competitor:{8000000 + index * 2}"
    provider_away_id = f"sr:competitor:{8000001 + index * 2}"
    match_id = 6100000 + index
    event_id = f"sr:match:{8100000 + index}"
    identity.observe_fotmob_payload(_fotmob_raw(
        match_id=match_id, kickoff=kickoff, ccode="INT", primary_id=source_primary,
        competition=source_comp, home_id=source_home_id, home=source_home, home_long=source_home,
        away_id=source_away_id, away=source_away, away_long=source_away,
    ))
    projection = _provider_projection(
        event_id=event_id, kickoff=kickoff, category_id=category,
        category_name="International", tournament_id=tournament,
        tournament_name=provider_comp, home_id=provider_home_id, home=source_home,
        away_id=provider_away_id, away=source_away,
    )
    _observe_provider_projection(projection)
    event = _event(
        event_id=event_id, kickoff=kickoff, competition=provider_comp,
        home=source_home, away=source_away,
    )
    reviewed = _reviewed(
        match_id=match_id, kickoff=kickoff, competition=source_comp,
        home=source_home, away=source_away,
    )

    assert identity.match_event(event, (reviewed,)) == (reviewed,)
    assert identity._comp_forward == before_forward
    assert identity._comp_reverse == before_reverse
    assert identity._learned_comp_rows() == []
    record = identity._evidence_records[-1]
    assert record["provider_payload_sha256"] == record["provider_source_raw_sha256"]
    assert record["provider_source_raw_sha256"] == identity._provider[event_id]["source_raw_sha256"]
    assert record["provider_source_page_num"] == 1
    assert record["provider_identity_projection_sha256"] == hashlib.sha256(projection).hexdigest()
    assert record["international_provider_family_bridge_policy_id"] == international_bridge.POLICY_ID
    assert record["international_provider_family_bridge_policy_sha256"] == international_bridge.PINNED_POLICY_SHA256


def test_p4_4k_grenada_cuba_source_facts_bind_to_synthetic_native_provider_identity():
    identity.reset_runtime_evidence()
    identity.configure_persistent_state(None)
    kickoff = datetime(2026, 9, 25, 21, 0, tzinfo=UTC)
    identity.observe_fotmob_payload(_fotmob_raw(
        match_id=5991922, kickoff=kickoff, ccode="INT", primary_id=9821,
        competition="CONCACAF Nations League B Grp. 3",
        home_id=6548, home="Grenada", home_long="Grenada",
        away_id=5857, away="Cuba", away_long="Cuba",
    ))
    projection = _provider_projection(
        event_id="sr:match:99000001", kickoff=kickoff,
        category_id="sr:category:4", category_name="International",
        tournament_id="sr:tournament:27420", tournament_name="CONCACAF Nations League",
        # Explicitly synthetic IDs: no real Grenada/Cuba SportyBet IDs are claimed.
        home_id="sr:competitor:99000011", home="Grenada",
        away_id="sr:competitor:99000012", away="Cuba",
    )
    _observe_provider_projection(projection)
    reviewed = _reviewed(
        match_id=5991922, kickoff=kickoff,
        competition="CONCACAF Nations League B Grp. 3", home="Grenada", away="Cuba",
    )
    event = _event(
        event_id="sr:match:99000001", kickoff=kickoff,
        competition="CONCACAF Nations League", home="Grenada", away="Cuba",
    )
    assert identity.match_event(event, (reviewed,)) == (reviewed,)
    assert identity._comp_reverse.get(("sr:category:4", "sr:tournament:27420")) is None


def test_international_bridge_evidence_round_trips_without_persisting_competition_mapping(tmp_path):
    state_path = tmp_path / identity.STATE_FILENAME
    identity.reset_runtime_evidence()
    identity.configure_persistent_state(state_path)
    kickoff = datetime(2026, 9, 25, 21, 0, tzinfo=UTC)
    identity.observe_fotmob_payload(_fotmob_raw(
        match_id=5991922, kickoff=kickoff, ccode="INT", primary_id=9821,
        competition="CONCACAF Nations League B Grp. 3",
        home_id=6548, home="Grenada", home_long="Grenada",
        away_id=5857, away="Cuba", away_long="Cuba",
    ))
    _observe_provider_projection(_provider_projection(
        event_id="sr:match:99000002", kickoff=kickoff,
        category_id="sr:category:4", category_name="International",
        tournament_id="sr:tournament:27420", tournament_name="CONCACAF Nations League",
        home_id="sr:competitor:99000021", home="Grenada",
        away_id="sr:competitor:99000022", away="Cuba",
    ))
    reviewed = _reviewed(
        match_id=5991922, kickoff=kickoff,
        competition="CONCACAF Nations League B Grp. 3", home="Grenada", away="Cuba",
    )
    event = _event(
        event_id="sr:match:99000002", kickoff=kickoff,
        competition="CONCACAF Nations League", home="Grenada", away="Cuba",
    )
    assert identity.match_event(event, (reviewed,)) == (reviewed,)
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["payload"]["schema_version"] == 2
    assert saved["payload"]["learned_competition_identities"] == []
    assert saved["payload"]["evidence_records"][0]["provider_source_raw_sha256"] == hashlib.sha256(_projection_source_raw(
        event_id="sr:match:99000002", kickoff=kickoff,
        category_id="sr:category:4", category_name="International",
        tournament_id="sr:tournament:27420", tournament_name="CONCACAF Nations League",
        home_id="sr:competitor:99000021", home="Grenada",
        away_id="sr:competitor:99000022", away="Cuba",
    )).hexdigest()

    identity.reset_runtime_evidence()
    identity.configure_persistent_state(state_path)
    assert identity.state_sha256() == saved["state_sha256"]
    assert identity._comp_reverse.get(("sr:category:4", "sr:tournament:27420")) is None
    assert identity._evidence_records[0]["international_provider_family_bridge_policy_id"] == international_bridge.POLICY_ID


@pytest.mark.parametrize(
    "source_primary,provider_category,provider_category_name,provider_tournament,provider_tournament_name,expected",
    [
        (9821, "sr:category:4", "International", "sr:tournament:23755", "UEFA Nations League", "REVIEWED_SOURCE_PROVIDER_CONFLICT"),
        (9821, "sr:category:99", "International", "sr:tournament:27420", "CONCACAF Nations League", "REVIEWED_SOURCE_PROVIDER_CONFLICT"),
        (9821, "sr:category:4", "International", "sr:tournament:27420", "CONCACAF Nations League B Grp. 3", "REVIEWED_SOURCE_PROVIDER_CONFLICT"),
        (9806, "sr:category:4", "International", "sr:tournament:23755", "CONCACAF Nations League", "REVIEWED_SOURCE_PROVIDER_CONFLICT"),
        (10437, "sr:category:4", "International", "sr:tournament:23755", "UEFA Nations League", "QUALIFIED_SOURCE_WITHOUT_PROVIDER_MAPPING"),
        (9833, "sr:category:4", "International", "sr:tournament:1848", "Africa Cup of Nations Qualification", "QUALIFIED_SOURCE_WITHOUT_PROVIDER_MAPPING"),
        (13287, "sr:category:4", "International", "sr:tournament:27420", "CONCACAF Nations League", "OBSERVED_UNQUALIFIED_SOURCE_IDENTITY"),
        (999999, "sr:category:4", "International", "sr:tournament:27420", "CONCACAF Nations League", "REVIEWED_PROVIDER_SOURCE_CONFLICT"),
        (999999, "sr:category:4", "International", "sr:tournament:999", "Club Cup", "NOT_APPLICABLE"),
    ],
)
def test_international_bridge_conflicts_and_fail_closed_states(
    source_primary, provider_category, provider_category_name, provider_tournament,
    provider_tournament_name, expected,
):
    actual = international_bridge.classify_source_provider_family(
        source_ccode="INT",
        source_primary_id=source_primary,
        provider_category_id=provider_category,
        provider_category_name=provider_category_name,
        provider_tournament_id=provider_tournament,
        provider_tournament_name=provider_tournament_name,
    )
    assert actual.value == expected


def test_bridge_classification_is_type_strict_and_only_known_provider_ids_preempt():
    assert international_bridge.classify_source_provider_family(
        source_ccode="INT", source_primary_id=True,
        provider_category_id="sr:category:4", provider_category_name="International",
        provider_tournament_id="sr:tournament:27420", provider_tournament_name="CONCACAF Nations League",
    ) is international_bridge.InternationalProviderFamilyClassification.REVIEWED_PROVIDER_SOURCE_CONFLICT
    assert international_bridge.classify_source_provider_family(
        source_ccode="int", source_primary_id=9821,
        provider_category_id="sr:category:4", provider_category_name="International",
        provider_tournament_id="sr:tournament:27420", provider_tournament_name="CONCACAF Nations League",
    ) is international_bridge.InternationalProviderFamilyClassification.REVIEWED_PROVIDER_SOURCE_CONFLICT
    assert international_bridge.classify_source_provider_family(
        source_ccode="BEL", source_primary_id=40,
        provider_category_id="sr:category:33", provider_category_name="Belgium",
        provider_tournament_id="sr:tournament:38", provider_tournament_name="First Division A",
    ) is international_bridge.InternationalProviderFamilyClassification.NOT_APPLICABLE


def test_provider_identity_projection_rejects_raw_response_claim_and_wrong_source_policy():
    identity.reset_runtime_evidence()
    identity.configure_persistent_state(None)
    valid = json.loads(_provider_projection(
        event_id="sr:match:99980001", kickoff=datetime(2026, 9, 25, 21, 0, tzinfo=UTC),
        category_id="sr:category:4", category_name="International",
        tournament_id="sr:tournament:27420", tournament_name="CONCACAF Nations League",
        home_id="sr:competitor:99980011", home="Grenada",
        away_id="sr:competitor:99980012", away="Cuba",
    ))
    valid["is_provider_response"] = True
    with pytest.raises(identity.CurrentShadowFixtureIdentityStateError):
        identity.observe_provider_identity_projection(json.dumps(valid).encode())
    valid["is_provider_response"] = False
    valid["source_policy_sha256"] = "0" * 64
    with pytest.raises(identity.CurrentShadowFixtureIdentityStateError):
        identity.observe_provider_identity_projection(json.dumps(valid).encode())


def test_provider_identity_projection_requires_the_exact_raw_page_to_be_observed():
    identity.reset_runtime_evidence()
    identity.configure_persistent_state(None)
    projection = _provider_projection(
        event_id="sr:match:99980002", kickoff=datetime(2026, 9, 25, 21, 0, tzinfo=UTC),
        category_id="sr:category:4", category_name="International",
        tournament_id="sr:tournament:27420", tournament_name="CONCACAF Nations League",
        home_id="sr:competitor:99980021", home="Grenada",
        away_id="sr:competitor:99980022", away="Cuba",
    )
    with pytest.raises(identity.CurrentShadowFixtureIdentityStateError, match="raw source-page ancestry"):
        identity.observe_provider_identity_projection(projection)

    event = json.loads(projection)
    event["events"][0]["source_ancestry"]["source_raw_sha256"] = "0" * 64
    tampered = json.dumps(event, sort_keys=True, separators=(",", ":")).encode()
    valid_payload = json.loads(projection)
    category = valid_payload["events"][0]["sport"]["category"]
    tournament = category["tournament"]
    identity.observe_provider_payload(_projection_source_raw(
        event_id="sr:match:99980002", kickoff=datetime(2026, 9, 25, 21, 0, tzinfo=UTC),
        category_id=category["id"], category_name=category["name"],
        tournament_id=tournament["id"], tournament_name=tournament["name"],
        home_id=valid_payload["events"][0]["homeTeamId"], home=valid_payload["events"][0]["homeTeamName"],
        away_id=valid_payload["events"][0]["awayTeamId"], away=valid_payload["events"][0]["awayTeamName"],
    ))
    with pytest.raises(identity.CurrentShadowFixtureIdentityStateError, match="raw source-page ancestry"):
        identity.observe_provider_identity_projection(tampered)


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


def test_new_exact_identity_persists_across_fresh_runtime_then_survives_display_drift(tmp_path):
    state_path = tmp_path / identity.STATE_FILENAME
    identity.reset_runtime_evidence()
    identity.configure_persistent_state(state_path)
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
    assert state_path.is_file()

    identity.reset_runtime_evidence()
    identity.configure_persistent_state(state_path)
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


def test_failed_partial_bootstrap_does_not_persist_identity_state(tmp_path):
    state_path = tmp_path / identity.STATE_FILENAME
    identity.reset_runtime_evidence()
    identity.configure_persistent_state(state_path)
    kickoff = datetime(2026, 9, 10, 18, 0, tzinfo=UTC)
    identity.observe_fotmob_payload(_fotmob_raw(
        match_id=910001, kickoff=kickoff, ccode="NEW", primary_id=888,
        competition="New League", home_id=910001, home="Alpha", home_long="Alpha United",
        away_id=910002, away="Beta", away_long="Beta City",
    ))
    identity.observe_provider_payload(_provider_raw(
        event_id="sr:match:99100001", kickoff=kickoff,
        category_id="sr:category:998", tournament_id="sr:tournament:998",
        competition="New League", home_id="sr:competitor:991001", home="Alpha United",
        away_id="sr:competitor:991002", away="Unrelated Away",
    ))
    event = _event(event_id="sr:match:99100001", kickoff=kickoff, competition="New League",
                   home="Alpha United", away="Unrelated Away")
    reviewed = _reviewed(match_id=910001, kickoff=kickoff, competition="New League",
                         home="Alpha", away="Beta")
    assert identity.match_event(event, (reviewed,)) == ()
    assert not state_path.exists()


def test_corrupt_persistent_identity_state_fails_closed(tmp_path):
    state_path = tmp_path / identity.STATE_FILENAME
    state_path.write_text("{}\n", encoding="utf-8")
    identity.reset_runtime_evidence()
    with pytest.raises(identity.CurrentShadowFixtureIdentityStateError):
        identity.configure_persistent_state(state_path)


def test_persisted_identity_append_only_guard_rejects_shrink_and_remap():
    retained = compatibility.identity_state_snapshot()
    retained["learned_team_identities"] = [[910001, "sr:competitor:991001"]]
    retained["learned_competition_identities"] = [["NEW", 888, "sr:category:998", "sr:tournament:998"]]
    retained["evidence_records"] = [{"provider_event_id": "sr:match:99100001"}]
    shrunk = json.loads(json.dumps(retained))
    shrunk["learned_team_identities"] = []
    with pytest.raises(compatibility.CurrentShadowFixtureIdentityCompatibilityError, match="shrunk"):
        compatibility.verify_identity_state_append_only_extension(retained, shrunk)
    remapped = json.loads(json.dumps(retained))
    remapped["learned_team_identities"][0] = [910001, "sr:competitor:991002"]
    with pytest.raises(compatibility.CurrentShadowFixtureIdentityCompatibilityError, match="append-only"):
        compatibility.verify_identity_state_append_only_extension(retained, remapped)


def test_persisted_identity_conflicting_tournament_and_competitor_fail_closed():
    state = compatibility.identity_state_snapshot()
    state["learned_team_identities"] = [[910001, "sr:competitor:991001"]]
    state["learned_competition_identities"] = [["NEW", 888, "sr:category:998", "sr:tournament:998"]]
    state["evidence_records"] = []
    with pytest.raises(identity.CurrentShadowFixtureIdentityStateError, match="conflicts or lacks evidence"):
        identity._validate_loaded_bindings(state)
