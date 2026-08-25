from __future__ import annotations

import dataclasses
import hashlib
import json
import socket
import sqlite3
from pathlib import Path
from types import MappingProxyType

import pytest

import domain.historical_asof_features as haf
from domain.historical_asof_features import (
    EXPECTED_HISTORICAL_FEATURE_REGISTRY_SHA256_BY_VERSION,
    HISTORICAL_FEATURE_REGISTRY,
    HISTORICAL_FEATURE_REGISTRY_VERSION,
    TEMPORAL_POLICY_ID,
    HistoricalAsOfError,
    HistoricalFeatureFamily,
    HistoricalFeatureId,
    HistoricalFeatureStatus,
    HistoricalTeamScope,
    HistoricalWindow,
    ReadOnlyHistoricalWarehouse,
    TeamMatchProjection,
    build_historical_asof_snapshot,
    calculate_historical_feature_registry_sha256,
    complete_boundary_window,
    file_sha256,
    find_resolution,
    validate_historical_feature_registry,
)
from scripts.build_historical_asof_feature_corpus import build_corpus
from scripts.build_historical_warehouse import Warehouse


def _match(
    match_date: str,
    home: str,
    away: str,
    home_score: int | None,
    away_score: int | None,
    *,
    source_id: str,
    season: str = "2025-26",
    **extra,
) -> dict:
    return {
        "competition_key": "eng_premier",
        "competition_name": "Premier League",
        "scope": "club",
        "season": season,
        "match_date": match_date,
        "kickoff_time": extra.pop("kickoff_time", "20:00"),
        "home_team": home,
        "away_team": away,
        "home_score_ft": home_score,
        "away_score_ft": away_score,
        **extra,
        "_source_id": source_id,
    }


def _warehouse(tmp_path: Path, rows: list[dict]) -> tuple[Path, list[str]]:
    path = tmp_path / "history.db"
    wh = Warehouse(path)
    wh.initialize()
    keys = []
    for row in rows:
        payload = dict(row)
        source_id = payload.pop("_source_id")
        keys.append(wh.upsert_match(payload, source_key="football_data_uk", source_match_id=source_id))
    wh.close()
    return path, keys


def _resolution(snapshot, side: str, feature, scope=HistoricalTeamScope.OVERALL, window=HistoricalWindow.LAST_5):
    return find_resolution(getattr(snapshot, f"{side}_resolutions"), feature, scope, window)


def _feature_payload(snapshot) -> tuple:
    return snapshot.home_resolutions, snapshot.away_resolutions


def test_registry_has_independent_reviewed_pin_and_rejects_drift():
    assert validate_historical_feature_registry() == EXPECTED_HISTORICAL_FEATURE_REGISTRY_SHA256_BY_VERSION[1]
    assert EXPECTED_HISTORICAL_FEATURE_REGISTRY_SHA256_BY_VERSION[1] == "f8014761d168ade0fe95142c3e1358ba4b8d2e065880d37a2162887099269b51"
    changed = list(HISTORICAL_FEATURE_REGISTRY)
    changed[0] = dataclasses.replace(changed[0], algorithm_id="CHANGED_WITHOUT_VERSION")
    new_live_sha = calculate_historical_feature_registry_sha256(changed, 1)
    assert new_live_sha != EXPECTED_HISTORICAL_FEATURE_REGISTRY_SHA256_BY_VERSION[1]
    with pytest.raises(HistoricalAsOfError, match="registry drift"):
        validate_historical_feature_registry(changed, 1)
    with pytest.raises(HistoricalAsOfError, match="unreviewed"):
        validate_historical_feature_registry(changed, 2)
    reviewed_v2 = MappingProxyType({2: calculate_historical_feature_registry_sha256(changed, 2)})
    assert validate_historical_feature_registry(changed, 2, reviewed_v2) == reviewed_v2[2]


def test_target_and_later_match_values_never_enter_target_features(tmp_path: Path):
    rows = [
        _match("2025-01-01", "Home", "Prior", 2, 0, source_id="prior", home_score_ht=1, away_score_ht=0,
               home_xg=1.5, away_xg=0.3, home_shots=11, away_shots=4),
        _match("2025-01-10", "Home", "Away", 9, 8, source_id="target", home_score_ht=7, away_score_ht=6,
               home_xg=9.9, away_xg=8.8, home_shots=99, away_shots=88),
        _match("2025-01-11", "Home", "Later", 0, 6, source_id="later", home_xg=0.1, away_xg=5.0),
    ]
    db, keys = _warehouse(tmp_path, rows)
    snapshot = build_historical_asof_snapshot(db, keys[1])
    assert _resolution(snapshot, "home", HistoricalFeatureId.GOALS_FOR_PER_MATCH).value == 2
    assert _resolution(snapshot, "home", HistoricalFeatureId.FIRST_HALF_GOALS_FOR_PER_MATCH).value == 1
    assert _resolution(snapshot, "home", HistoricalFeatureId.XG_FOR_PER_MATCH).value == 1.5
    assert _resolution(snapshot, "home", HistoricalFeatureId.SHOTS_FOR_PER_MATCH).value == 11

    connection = sqlite3.connect(db)
    connection.execute("UPDATE warehouse_matches SET home_score_ft=1,away_score_ft=7,home_score_ht=0,away_score_ht=5,home_xg=0.2,away_xg=7.0,home_shots=1,away_shots=70 WHERE match_key=?", (keys[1],))
    connection.execute("INSERT INTO warehouse_events(event_key,match_key,source_key,event_type,team) VALUES('target-event',?,'football_data_uk','goal','Home')", (keys[1],))
    connection.commit()
    connection.close()
    changed = build_historical_asof_snapshot(db, keys[1])
    assert _feature_payload(changed) == _feature_payload(snapshot)


def test_date_strict_excludes_all_same_day_irrespective_of_raw_clock(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [
        _match("2025-01-01", "Home", "Prior", 1, 0, source_id="prior"),
        _match("2025-01-10", "Home", "SameDay", 8, 0, source_id="same", kickoff_time="01:00"),
        _match("2025-01-10", "Home", "Target", 0, 0, source_id="target", kickoff_time="23:00"),
    ])
    snapshot = build_historical_asof_snapshot(db, keys[2])
    value = _resolution(snapshot, "home", HistoricalFeatureId.GOALS_FOR_PER_MATCH)
    assert snapshot.temporal_policy_id == TEMPORAL_POLICY_ID
    assert value.value == 1
    assert value.effective_match_sample == 1


def test_no_history_is_missing_without_defaults_or_freshness(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [_match("2025-01-10", "Home", "Away", 1, 0, source_id="target")])
    snapshot = build_historical_asof_snapshot(db, keys[0])
    assert all(item.status is HistoricalFeatureStatus.MISSING and item.value is None for item in snapshot.home_resolutions)
    assert "live_data_freshness" not in {item.feature_id.value for item in HISTORICAL_FEATURE_REGISTRY}
    assert not any("odds" in item.feature_id.value or "price" in item.feature_id.value for item in HISTORICAL_FEATURE_REGISTRY)


def test_missing_field_is_not_zero_and_samples_remain_field_specific(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [
        _match("2025-01-01", "Home", "A", 1, 0, source_id="a", home_xg=1.2, away_xg=0.2, home_shots=10),
        _match("2025-01-02", "B", "Home", 0, 1, source_id="b"),
        _match("2025-01-10", "Home", "Target", 0, 0, source_id="target"),
    ])
    snapshot = build_historical_asof_snapshot(db, keys[2])
    xg = _resolution(snapshot, "home", HistoricalFeatureId.XG_FOR_PER_MATCH)
    shots_against = _resolution(snapshot, "home", HistoricalFeatureId.SHOTS_AGAINST_PER_MATCH)
    assert xg.value == 1.2 and xg.effective_match_sample == 2
    assert xg.valid_field_sample == 1 and xg.missing_field_count == 1
    assert shots_against.status is HistoricalFeatureStatus.MISSING and shots_against.value is None


def _projection_for(key: str, match_date: str) -> TeamMatchProjection:
    values = dict(
        match_key=key, match_date=match_date, competition_key="c", scope="club", season="s",
        team="A", opponent="B", side="HOME", goals_for=1, goals_against=0,
        first_half_goals_for=None, first_half_goals_against=None, xg_for=None, xg_against=None,
        shots_for=None, shots_against=None, shots_on_target_for=None, shots_on_target_against=None,
        possession_for=None, possession_against=None, corners_for=None, corners_against=None,
        fouls_for=None, fouls_against=None, yellows_for=None, yellows_against=None,
        reds_for=None, reds_against=None, field_source_keys=(), conflict_fields=(), projection_sha256="0" * 64,
    )
    return TeamMatchProjection(**values)


def test_complete_boundary_date_never_splits_tied_oldest_bucket():
    history = tuple(_projection_for(f"m{i}", day) for i, day in enumerate(
        ["2025-01-01", "2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04", "2025-01-05"]
    ))
    selected = complete_boundary_window(history, 5)
    assert len(selected) == 6
    assert {item.match_key for item in selected if item.match_date == "2025-01-01"} == {"m0", "m1"}
    assert complete_boundary_window(tuple(reversed(history)), 5) == selected


def test_overall_and_home_away_scopes_do_not_mix(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [
        _match("2025-01-01", "Home", "A", 3, 0, source_id="home"),
        _match("2025-01-02", "B", "Home", 2, 0, source_id="away"),
        _match("2025-01-03", "C", "Away", 0, 4, source_id="away-side"),
        _match("2025-01-04", "Away", "D", 1, 0, source_id="home-side"),
        _match("2025-01-10", "Home", "Away", 0, 0, source_id="target"),
    ])
    snapshot = build_historical_asof_snapshot(db, keys[-1])
    assert _resolution(snapshot, "home", HistoricalFeatureId.GOALS_FOR_PER_MATCH).value == 1.5
    assert _resolution(snapshot, "home", HistoricalFeatureId.GOALS_FOR_PER_MATCH, HistoricalTeamScope.HOME_ONLY).value == 3
    assert _resolution(snapshot, "away", HistoricalFeatureId.GOALS_FOR_PER_MATCH).value == 2.5
    assert _resolution(snapshot, "away", HistoricalFeatureId.GOALS_FOR_PER_MATCH, HistoricalTeamScope.AWAY_ONLY).value == 4


def test_source_is_read_only_sha_bound_and_caller_cannot_forge_it(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [_match("2025-01-10", "Home", "Away", 1, 0, source_id="target")])
    expected = file_sha256(db)
    with ReadOnlyHistoricalWarehouse(db) as source:
        assert source.sha256 == expected
        with pytest.raises(sqlite3.OperationalError):
            source.connection.execute("DELETE FROM warehouse_matches")
    snapshot = build_historical_asof_snapshot(db, keys[0])
    assert snapshot.source_warehouse_sha256 == expected
    with pytest.raises(TypeError):
        build_historical_asof_snapshot(db, keys[0], source_warehouse_sha256="0" * 64)
    with pytest.raises(HistoricalAsOfError, match="builder-only"):
        haf.HistoricalAsOfFixtureSnapshot(source_warehouse_sha256="0" * 64)


def test_different_database_bytes_change_source_identity_and_same_source_is_deterministic(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [_match("2025-01-10", "Home", "Away", 1, 0, source_id="target")])
    first = build_historical_asof_snapshot(db, keys[0])
    second = build_historical_asof_snapshot(db, keys[0])
    assert first.canonical_bytes == second.canonical_bytes
    assert first.canonical_sha256 == second.canonical_sha256
    connection = sqlite3.connect(db)
    connection.execute("INSERT INTO warehouse_meta VALUES('irrelevant_exact_source_change','yes')")
    connection.commit(); connection.close()
    third = build_historical_asof_snapshot(db, keys[0])
    assert third.source_warehouse_sha256 != first.source_warehouse_sha256
    assert third.canonical_sha256 != first.canonical_sha256


def test_existing_snapshot_serialization_ignores_live_registry_mutation(tmp_path: Path, monkeypatch):
    db, keys = _warehouse(tmp_path, [
        _match("2025-01-01", "Home", "A", 2, 0, source_id="prior", home_xg=1.25, away_xg=0.2),
        _match("2025-01-10", "Home", "Away", 0, 0, source_id="target"),
    ])
    snapshot = build_historical_asof_snapshot(db, keys[1])
    before = snapshot.canonical_bytes, snapshot.canonical_sha256
    changed = dataclasses.replace(HISTORICAL_FEATURE_REGISTRY[0], family=HistoricalFeatureFamily.SCHEDULE)
    monkeypatch.setattr(haf, "HISTORICAL_FEATURE_REGISTRY", (changed,))
    monkeypatch.setattr(haf, "_DEFINITION_BY_ID", MappingProxyType({changed.feature_id: changed}))
    assert (snapshot.canonical_bytes, snapshot.canonical_sha256) == before


def test_invalid_nonfinite_warehouse_numeric_fails_closed(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [
        _match("2025-01-01", "Home", "A", 1, 0, source_id="prior"),
        _match("2025-01-10", "Home", "Away", 0, 0, source_id="target"),
    ])
    connection = sqlite3.connect(db)
    connection.execute("UPDATE warehouse_matches SET home_xg=? WHERE match_key=?", (float("inf"), keys[0]))
    connection.commit(); connection.close()
    with pytest.raises(HistoricalAsOfError, match="invalid numeric"):
        build_historical_asof_snapshot(db, keys[1])


def test_target_posthoc_lineup_coach_and_raw_events_have_no_feature_path(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [_match("2025-01-10", "Home", "Away", 1, 0, source_id="target")])
    connection = sqlite3.connect(db)
    connection.execute("UPDATE warehouse_matches SET home_coach='Post Match Coach' WHERE match_key=?", (keys[0],))
    connection.execute("INSERT INTO warehouse_coaches VALUES('c',?,'football_data_uk','Home','Coach',NULL,'head_coach',NULL)", (keys[0],))
    connection.execute("INSERT INTO warehouse_lineups VALUES('l',?,'football_data_uk','Home','Player',NULL,NULL,NULL,1,0,90,'{}')", (keys[0],))
    connection.execute(
        "INSERT INTO warehouse_events(event_key,match_key,source_key,event_type,team,player,minute) "
        "VALUES('e',?,'football_data_uk','goal','Home','Player',1)",
        (keys[0],),
    )
    connection.commit(); connection.close()
    snapshot = build_historical_asof_snapshot(db, keys[0])
    identifiers = {item.feature_id.value for item in HISTORICAL_FEATURE_REGISTRY}
    assert not identifiers & {"manager_regime", "lineup", "availability", "tactical_identity"}
    assert all(item.status is HistoricalFeatureStatus.MISSING for item in snapshot.home_resolutions)


def test_schedule_features_do_not_invent_rest_without_history_and_can_observe_zero_count(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [
        _match("2025-01-01", "Home", "A", 1, 0, source_id="prior"),
        _match("2025-03-01", "Home", "Away", 0, 0, source_id="target"),
    ])
    snapshot = build_historical_asof_snapshot(db, keys[1])
    days = _resolution(snapshot, "home", HistoricalFeatureId.DAYS_SINCE_LAST_MATCH, window=HistoricalWindow.AS_OF)
    seven = _resolution(snapshot, "home", HistoricalFeatureId.FIXTURES_LAST_7_DAYS, window=HistoricalWindow.AS_OF)
    assert days.value == 59
    assert seven.status is HistoricalFeatureStatus.AVAILABLE and seven.value == 0


def test_conflict_and_canonical_source_provenance_are_retained(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [
        _match("2025-01-01", "Home", "A", 1, 0, source_id="prior"),
        _match("2025-01-10", "Home", "Away", 0, 0, source_id="target"),
    ])
    connection = sqlite3.connect(db)
    connection.execute("INSERT INTO warehouse_conflicts(match_key,field_name,incoming_source,incoming_value) VALUES(?,?,?,?)", (keys[0], "home_score_ft", "weaker", "7"))
    connection.commit(); connection.close()
    snapshot = build_historical_asof_snapshot(db, keys[1])
    result = _resolution(snapshot, "home", HistoricalFeatureId.GOALS_FOR_PER_MATCH)
    assert "football_data_uk" in result.source_keys
    assert result.conflict_count >= 1


def test_authority_flags_false_and_no_team_name_tactical_rule(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [_match("2025-01-10", "Getafe", "Racing", 1, 0, source_id="target")])
    snapshot = build_historical_asof_snapshot(db, keys[0])
    assert all(value is False for _, value in snapshot.authority_flags)
    assert "Getafe" not in Path(haf.__file__).read_text(encoding="utf-8")


def test_bulk_builder_is_date_batched_filter_safe_and_separate(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [
        _match("2025-01-01", "Home", "A", 2, 0, source_id="prior"),
        _match("2025-01-10", "Home", "SameDay", 9, 0, source_id="same"),
        _match("2025-01-10", "Home", "Away", 0, 0, source_id="target"),
    ])
    output = tmp_path / "features.db"
    before = file_sha256(db)
    assert build_corpus(db, output, start_date="2025-01-10", limit=1) == 1
    assert file_sha256(db) == before
    connection = sqlite3.connect(output)
    row = connection.execute("SELECT payload_json FROM historical_asof_snapshots").fetchone()
    payload = json.loads(row[0])
    assert payload["temporal_policy_id"] == TEMPORAL_POLICY_ID
    assert payload["source_warehouse_sha256"] == before
    assert len(connection.execute("SELECT * FROM historical_asof_snapshots").fetchall()) == 1
    connection.close()
    with pytest.raises(HistoricalAsOfError, match="output must be separate"):
        build_corpus(db, db)


def test_builders_perform_no_network_calls(tmp_path: Path, monkeypatch):
    db, keys = _warehouse(tmp_path, [_match("2025-01-10", "Home", "Away", 1, 0, source_id="target")])

    def reject_network(*_args, **_kwargs):
        raise AssertionError("historical as-of construction attempted network access")

    monkeypatch.setattr(socket.socket, "connect", reject_network)
    snapshot = build_historical_asof_snapshot(db, keys[0])
    assert snapshot.target_match_key == keys[0]
    assert build_corpus(db, tmp_path / "features.db", limit=1) == 1


def test_active_wal_sidecar_is_rejected(tmp_path: Path):
    db, _ = _warehouse(tmp_path, [_match("2025-01-10", "Home", "Away", 1, 0, source_id="target")])
    Path(str(db) + "-wal").write_bytes(b"active")
    with pytest.raises(HistoricalAsOfError, match="unsafe active"):
        build_historical_asof_snapshot(db, "anything")
