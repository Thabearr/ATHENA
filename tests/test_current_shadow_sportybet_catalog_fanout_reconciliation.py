from __future__ import annotations

from datetime import datetime, timezone
import json

import pytest

from domain import current_shadow_sportybet_catalog_fanout_reconciliation as fanout

UTC = timezone.utc
OBSERVED = datetime(2026, 8, 31, 7, 30, tzinfo=UTC)


def _raw(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def _catalog(*, duplicate=False, bool_event_size=False):
    tournaments = [
        {"id": "sr:tournament:100", "name": "League A", "eventSize": True if bool_event_size else 2},
        {"id": "sr:tournament:101", "name": "League B", "eventSize": 0},
    ]
    if duplicate:
        tournaments.append({"id": "sr:tournament:100", "name": "League A", "eventSize": 2})
    return _raw({
        "bizCode": 10000,
        "data": [{
            "id": fanout.FOOTBALL_SPORT_ID,
            "name": "Football",
            "categories": [{
                "id": "sr:category:1",
                "name": "England",
                "tournaments": tournaments,
            }],
        }],
    })


def _event(event_id="sr:match:123"):
    return {
        "eventId": event_id,
        "sportId": fanout.FOOTBALL_SPORT_ID,
        "homeTeamName": "Home",
        "awayTeamName": "Away",
        "tournamentName": "League A",
        "estimateStartTime": 1788206400000,
        "bookingStatus": "Open",
        "status": 0,
        "matchStatus": "Not started",
    }


def test_contract_is_pinned_and_dependencies_are_replayed():
    assert fanout.calculate_contract_sha256() == fanout.EXPECTED_CONTRACT_SHA256
    assert fanout.validate_contract()["contract_sha256"] == fanout.EXPECTED_CONTRACT_SHA256
    assert fanout.AUTHORITY["fixture_reconciliation"] is True
    for key in ("login", "cookies", "wallet", "staking", "bet", "wager_placed"):
        assert fanout.AUTHORITY[key] is False


def test_catalog_uses_only_positive_provider_eventsize_pairs():
    rows = fanout._parse_catalog(_catalog())
    assert [(row.category_id, row.tournament_id, row.event_size) for row in rows] == [
        ("sr:category:1", "sr:tournament:100", 2)
    ]


def test_catalog_duplicate_pair_and_boolean_eventsize_fail_closed():
    with pytest.raises(fanout.CurrentShadowSportyBetCatalogFanoutReconciliationError, match="duplicated"):
        fanout._parse_catalog(_catalog(duplicate=True))
    with pytest.raises(fanout.CurrentShadowSportyBetCatalogFanoutReconciliationError, match="eventSize"):
        fanout._parse_catalog(_catalog(bool_event_size=True))


def test_tournament_response_preserves_exact_request_and_raw_ancestry():
    nonce = int(OBSERVED.timestamp() * 1000) - 1000
    raw = _raw({"bizCode": 10000, "data": [_event()]})
    observation, events = fanout._parse_tournament_response(
        raw,
        category_id="sr:category:1",
        tournament_id="sr:tournament:100",
        request_nonce_ms=nonce,
        observed_at=OBSERVED,
    )
    assert observation.request_target == fanout.tournament_request_target(
        category_id="sr:category:1",
        tournament_id="sr:tournament:100",
        request_nonce_ms=nonce,
    )
    assert observation.event_ids == ("sr:match:123",)
    assert events[0].source_raw_sha256 == observation.raw_sha256
    assert events[0].source_observed_at == OBSERVED
    assert events[0].competition_name == "League A"


def test_capture_fans_out_only_ids_from_current_provider_catalog(monkeypatch, tmp_path):
    seen_targets = []
    catalog = _catalog()
    tournament = _raw({"bizCode": 10000, "data": [_event()]})

    def fake_get(target):
        seen_targets.append(target)
        if target == fanout.catalog_request_target():
            return catalog, OBSERVED
        assert "categoryId=sr%3Acategory%3A1" in target
        assert "tournamentId=sr%3Atournament%3A100" in target
        return tournament, OBSERVED

    monkeypatch.setattr(fanout, "_network_get", fake_get)
    monkeypatch.setattr(fanout.time, "time", lambda: OBSERVED.timestamp() - 1)
    directory, snapshot = fanout.capture_current_catalog_fanout_discovery(
        repository_root=tmp_path,
        execute_live_network=True,
    )
    assert len(seen_targets) == 2
    assert len(snapshot.tournaments) == 1
    assert len(snapshot.observations) == 1
    assert len(snapshot.events) == 1
    replayed = fanout.verify_current_catalog_fanout_discovery(
        directory,
        repository_root=tmp_path,
    )
    assert replayed.to_dict() == snapshot.to_dict()


def test_replay_rejects_tampered_tournament_bytes(monkeypatch, tmp_path):
    catalog = _catalog()
    tournament = _raw({"bizCode": 10000, "data": [_event()]})

    def fake_get(target):
        return (catalog if target == fanout.catalog_request_target() else tournament), OBSERVED

    monkeypatch.setattr(fanout, "_network_get", fake_get)
    monkeypatch.setattr(fanout.time, "time", lambda: OBSERVED.timestamp() - 1)
    directory, snapshot = fanout.capture_current_catalog_fanout_discovery(
        repository_root=tmp_path,
        execute_live_network=True,
    )
    observation = snapshot.observations[0]
    raw_path = directory / fanout.TOURNAMENT_DIRNAME / fanout._raw_filename(observation)
    raw_path.write_bytes(raw_path.read_bytes() + b" ")
    with pytest.raises(fanout.CurrentShadowSportyBetCatalogFanoutReconciliationError, match="identity mismatch"):
        fanout.verify_current_catalog_fanout_discovery(directory, repository_root=tmp_path)
