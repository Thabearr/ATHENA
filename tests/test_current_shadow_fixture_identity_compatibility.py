from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from types import SimpleNamespace

import pytest

from domain import current_shadow_fixture_identity_compatibility as compatibility
from domain import current_shadow_fixture_identity_v2 as identity
from domain import current_shadow_sportybet_international_provider_family_bridge as bridge
from domain import current_shadow_sportybet_pc_upcoming_discovery as pc_upcoming


UTC = timezone.utc
KICKOFF = datetime(2026, 9, 25, 21, 0, tzinfo=UTC)


def _source_capture(*, competition: str = "CONCACAF Nations League B Grp. 3") -> bytes:
    payload = {
        "leagues": [{
            "ccode": "INT",
            "primaryId": 9821,
            "name": competition,
            "matches": [{
                "id": 5991922,
                "home": {"id": 6548, "name": "Grenada", "longName": "Grenada"},
                "away": {"id": 5857, "name": "Cuba", "longName": "Cuba"},
                "status": {"utcTime": "2026-09-25T21:00:00Z"},
            }],
        }],
    }
    return json.dumps(payload, separators=(",", ":")).encode()


def _provider_page_raw(*, tournament_name: str = "CONCACAF Nations League") -> bytes:
    return json.dumps({
        "eventId": "sr:match:99000001",
        "estimateStartTime": int(KICKOFF.timestamp() * 1000),
        "homeTeamId": "sr:competitor:99000011",
        "homeTeamName": "Grenada",
        "awayTeamId": "sr:competitor:99000012",
        "awayTeamName": "Cuba",
        "sport": {"category": {
            "id": "sr:category:4",
            "name": "International",
            "tournament": {"id": "sr:tournament:27420", "name": tournament_name},
        }},
    }, ensure_ascii=False, separators=(",", ":")).encode()


def _projection(*, tournament_name: str = "CONCACAF Nations League") -> bytes:
    payload = {
        "dataset": "ATHENA_PC_UPCOMING_PROVIDER_IDENTITY_PROJECTION_V1",
        "projection_policy_id": "EXACT_NATIVE_FIELDS_DERIVED_FROM_REPLAYED_PC_UPCOMING_RAW_BYTES",
        "is_provider_response": False,
        "source_policy_id": pc_upcoming.POLICY_ID,
        "source_policy_sha256": pc_upcoming.PINNED_POLICY_SHA256,
        "events": [{
            "eventId": "sr:match:99000001",
            "estimateStartTime": int(KICKOFF.timestamp() * 1000),
            "homeTeamId": "sr:competitor:99000011",
            "homeTeamName": "Grenada",
            "awayTeamId": "sr:competitor:99000012",
            "awayTeamName": "Cuba",
            "sport": {"id": "sr:sport:1", "category": {
                "id": "sr:category:4",
                "name": "International",
                "tournament": {"id": "sr:tournament:27420", "name": tournament_name},
            }},
            "source_ancestry": {
                "source_raw_sha256": hashlib.sha256(_provider_page_raw(tournament_name=tournament_name)).hexdigest(),
                "source_page_num": 1,
                "source_observed_at": "2026-09-25T21:40:00Z",
            },
        }],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _event(*, competition: str = "CONCACAF Nations League"):
    return SimpleNamespace(
        event_id="sr:match:99000001",
        kickoff_utc=KICKOFF,
        competition_name=competition,
        home_team_name="Grenada",
        away_team_name="Cuba",
    )


def _reviewed(*, competition: str = "CONCACAF Nations League B Grp. 3"):
    return SimpleNamespace(
        source_fixture_identifier="5991922",
        kickoff=KICKOFF,
        competition=competition,
        home_team="Grenada",
        away_team="Cuba",
    )


def test_projection_input_matches_international_fixture_and_records_raw_ancestry():
    identity.reset_runtime_evidence()
    compatibility.begin_identity_scope(
        ((_source_capture(), None),),
        provider_raw_bytes=(_provider_page_raw(),),
        provider_identity_projection_bytes=(_projection(),),
    )
    result = compatibility.match_current_shadow_event(_event(), (_reviewed(),))
    assert result == (_reviewed(),)
    record = identity._evidence_records[-1]
    assert record["provider_payload_sha256"] == record["provider_source_raw_sha256"]
    assert record["provider_source_raw_sha256"] == hashlib.sha256(_provider_page_raw()).hexdigest()
    assert record["provider_source_page_num"] == 1
    assert record["provider_identity_projection_sha256"] == hashlib.sha256(_projection()).hexdigest()
    assert record["international_provider_family_bridge_policy_id"] == bridge.POLICY_ID


def test_known_international_provider_pair_never_falls_through_to_weaker_name_paths(monkeypatch):
    identity.reset_runtime_evidence()
    compatibility.begin_identity_scope(
        ((_source_capture(competition="Champions League"), None),),
        provider_raw_bytes=(_provider_page_raw(tournament_name="Champions League"),),
        provider_identity_projection_bytes=(_projection(tournament_name="Champions League"),),
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("bridge-owned event fell through to a weaker identity path")

    monkeypatch.setattr(compatibility.run199_identity, "match_event", forbidden)
    monkeypatch.setattr(compatibility.identity_recovery, "match_event", forbidden)
    row_that_literal_matching_would_accept = _reviewed(competition="Champions League")
    assert compatibility.match_current_shadow_event(
        _event(competition="Champions League"), (row_that_literal_matching_would_accept,)
    ) == ()


def test_non_bridge_club_event_keeps_existing_run199_v3_v2_then_literal_order(monkeypatch):
    identity.reset_runtime_evidence()
    calls: list[str] = []
    row = SimpleNamespace(
        source_fixture_identifier="club-1",
        kickoff=KICKOFF,
        competition="Championship",
        home_team="Alpha",
        away_team="Beta",
    )
    event = SimpleNamespace(
        event_id="sr:match:90000001",
        kickoff_utc=KICKOFF,
        competition_name="Championship",
        home_team_name="Alpha",
        away_team_name="Beta",
    )

    def run199(*args, **kwargs):
        calls.append("run199")
        return ()

    def v3(*args, **kwargs):
        calls.append("v3")
        return ()

    def v2(*args, **kwargs):
        calls.append("v2")
        return ()

    monkeypatch.setattr(compatibility.run199_identity, "match_event", run199)
    monkeypatch.setattr(compatibility.identity_recovery, "match_event", v3)
    monkeypatch.setattr(identity, "match_event", v2)
    assert compatibility.match_current_shadow_event(event, (row,)) == (row,)
    assert calls == ["run199", "v3", "v2"]


def test_existing_scope_callers_need_not_supply_projection_bytes():
    identity.reset_runtime_evidence()
    assert compatibility.begin_identity_scope(((_source_capture(), None),)) is None
    assert not identity._provider


def test_published_policy_binds_both_match_orders_and_raw_projection_ancestry():
    payload = compatibility._policy_payload()
    assert payload["match_order"] == [
        "RUN199_EXACT_FIXTURE_IDENTITY_OVERLAY", "V3_IDENTITY_RECOVERY",
        "V2_STABLE_IDENTITY", "REVIEWED_LITERAL_MATCH",
    ]
    bridge_path = payload["international_bridge_preemption"]
    assert bridge_path["match_order"] == [
        "V2_STABLE_IDENTITY_WITH_INTERNATIONAL_PROVIDER_FAMILY_BRIDGE",
        "FAIL_CLOSED_NO_RUN199_V3_ALIAS_LITERAL_FALLTHROUGH",
    ]
    assert bridge_path["bridge_policy_sha256"] == bridge.PINNED_POLICY_SHA256
    assert payload["provider_evidence_observation_policy_id"] != "VERIFIED_ACTIVE_SOURCE_RAW_BYTES_ONLY"
    assert payload["provider_evidence_observation"]["athena_projection_requires_exact_observed_provider_page_raw_sha256"] is True
    assert payload["provider_evidence_observation"]["athena_projection_is_provider_response"] is False
    assert compatibility.calculate_policy_sha256() == compatibility.EXPECTED_POLICY_SHA256
    assert compatibility.EXPECTED_POLICY_SHA256 != "e1ce7468c61dcf4067725f6d58cd34d36bd1dc01e3a2177c4a724647bcab324b"


def test_projection_without_prior_exact_provider_page_is_rejected():
    with pytest.raises(compatibility.CurrentShadowFixtureIdentityCompatibilityError):
        compatibility.begin_identity_scope(
            ((_source_capture(), None),),
            provider_identity_projection_bytes=(_projection(),),
        )
