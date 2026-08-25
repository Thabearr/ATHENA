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
    EXPECTED_WAREHOUSE_SCHEMA_SQL_SHA256_BY_VERSION,
    HISTORICAL_FEATURE_REGISTRY,
    HISTORICAL_FEATURE_REGISTRY_VERSION,
    HISTORICAL_TEAM_IDENTITY_POLICY_ID,
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
    historical_team_identity,
    qualifies_completed_prior_fixture,
    validate_historical_feature_registry,
    validate_warehouse_schema_sql,
)
from scripts.build_historical_asof_feature_corpus import TeamRollingHistory, build_corpus
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
    assert EXPECTED_HISTORICAL_FEATURE_REGISTRY_SHA256_BY_VERSION[1] == "2d1606e54463ee75f984973173af4ba4ba68fe0acc4d0be4e2525b08f5c863f8"
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
        reds_for=None, reds_against=None, blocked_primitives=(), field_source_keys=(),
        conflict_fields=(), projection_sha256=hashlib.sha256(key.encode("utf-8")).hexdigest(),
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


def test_team_identity_is_exact_scope_and_competition_scoped_for_both_builders(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [
        _match("2025-01-01", "United", "League Opponent", 2, 0, source_id="league"),
        _match(
            "2025-01-02", "United", "Cup Opponent", 8, 0, source_id="cup",
            competition_key="eng_fa_cup", competition_name="FA Cup",
        ),
        _match(
            "2025-01-03", "United", "National Opponent", 9, 0, source_id="international",
            competition_key="intl_world_cup", competition_name="FIFA World Cup",
            scope="international", season="2025",
        ),
        _match("2025-01-04", "united", "Case Opponent", 7, 0, source_id="case"),
        _match("2025-01-10", "United", "Target", 0, 0, source_id="target"),
    ])
    direct = build_historical_asof_snapshot(db, keys[-1])
    result = _resolution(direct, "home", HistoricalFeatureId.GOALS_FOR_PER_MATCH)
    assert direct.team_identity_policy_id == HISTORICAL_TEAM_IDENTITY_POLICY_ID
    assert result.value == 2
    assert result.effective_match_sample == 1
    assert historical_team_identity("club", "eng_premier", "United") == (
        "club", "eng_premier", "United",
    )
    assert historical_team_identity("club", "eng_fa_cup", "United") != historical_team_identity(
        "club", "eng_premier", "United"
    )
    assert historical_team_identity("international", "eng_premier", "United") != historical_team_identity(
        "club", "eng_premier", "United"
    )
    assert historical_team_identity("club", "eng_premier", "united") != historical_team_identity(
        "club", "eng_premier", "United"
    )

    output = tmp_path / "identity-features.db"
    build_corpus(db, output, start_date="2025-01-10", limit=1)
    connection = sqlite3.connect(output)
    payload = json.loads(connection.execute(
        "SELECT payload_json FROM historical_asof_snapshots WHERE match_key=?", (keys[-1],)
    ).fetchone()[0])
    metadata = dict(connection.execute("SELECT key,value FROM corpus_meta"))
    connection.close()
    assert payload == direct.to_dict()
    assert json.loads(metadata["historical_team_identity_policy_id"]) == HISTORICAL_TEAM_IDENTITY_POLICY_ID


def test_missing_season_never_becomes_an_all_time_season(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [
        _match("2022-01-01", "Home", "A", 1, 0, source_id="2022", season=None),
        _match("2024-01-01", "Home", "B", 3, 0, source_id="2024", season=None),
        _match("2025-01-01", "Home", "Target", 0, 0, source_id="target", season=None),
    ])
    snapshot = build_historical_asof_snapshot(db, keys[-1])
    season = _resolution(
        snapshot, "home", HistoricalFeatureId.GOALS_FOR_PER_MATCH,
        window=HistoricalWindow.SEASON_TO_DATE,
    )
    rolling = _resolution(snapshot, "home", HistoricalFeatureId.GOALS_FOR_PER_MATCH)
    assert season.status is HistoricalFeatureStatus.MISSING
    assert season.value is None and season.effective_match_sample == 0
    assert rolling.value == 2


def test_exact_season_to_date_still_uses_only_that_season(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [
        _match("2024-01-01", "Home", "Old", 8, 0, source_id="old", season="2024-25"),
        _match("2025-08-01", "Home", "Current", 2, 0, source_id="current", season="2025-26"),
        _match("2025-08-10", "Home", "Target", 0, 0, source_id="target", season="2025-26"),
    ])
    snapshot = build_historical_asof_snapshot(db, keys[-1])
    season = _resolution(
        snapshot, "home", HistoricalFeatureId.GOALS_FOR_PER_MATCH,
        window=HistoricalWindow.SEASON_TO_DATE,
    )
    assert season.status is HistoricalFeatureStatus.AVAILABLE
    assert season.value == 2 and season.effective_match_sample == 1


def test_dense_schedule_single_and_bulk_snapshots_are_exactly_equivalent(tmp_path: Path):
    rows = [
        _match(f"2025-01-{day:02d}", "Dense", f"Opponent {day}", 1, 0, source_id=f"p{day}")
        for day in range(1, 22)
    ]
    rows.append(_match("2025-01-22", "Dense", "Target", 0, 0, source_id="target"))
    db, keys = _warehouse(tmp_path, rows)
    direct = build_historical_asof_snapshot(db, keys[-1])
    expected = {
        HistoricalFeatureId.DAYS_SINCE_LAST_MATCH: 1,
        HistoricalFeatureId.FIXTURES_LAST_7_DAYS: 7,
        HistoricalFeatureId.FIXTURES_LAST_14_DAYS: 14,
        HistoricalFeatureId.FIXTURES_LAST_28_DAYS: 21,
    }
    for feature_id, value in expected.items():
        assert _resolution(
            direct, "home", feature_id, window=HistoricalWindow.AS_OF
        ).value == value

    output = tmp_path / "dense-features.db"
    build_corpus(db, output, start_date="2025-01-22", limit=1)
    connection = sqlite3.connect(output)
    payload = json.loads(connection.execute(
        "SELECT payload_json FROM historical_asof_snapshots WHERE match_key=?", (keys[-1],)
    ).fetchone()[0])
    connection.close()
    assert payload == direct.to_dict()


def test_conflicts_are_attributed_per_match_and_required_primitive(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [
        _match("2025-01-01", "Home", "A", 1, 0, source_id="home", home_xg=1.0, away_xg=0.5),
        _match("2025-01-02", "B", "Home", 0, 1, source_id="away", home_xg=0.3, away_xg=1.2),
        _match("2025-01-10", "Home", "Target", 0, 0, source_id="target"),
    ])
    connection = sqlite3.connect(db)
    conflicts = (
        (keys[0], "home_xg", "1.1"),
        (keys[0], "away_xg", "0.6"),
        (keys[1], "home_xg", "0.4"),
        (keys[1], "away_xg", "1.3"),
    )
    connection.executemany(
        "INSERT INTO warehouse_conflicts(match_key,field_name,incoming_source,incoming_value) "
        "VALUES(?,?,'weaker',?)", conflicts,
    )
    connection.commit(); connection.close()
    snapshot = build_historical_asof_snapshot(db, keys[-1])
    xg_for = _resolution(snapshot, "home", HistoricalFeatureId.XG_FOR_PER_MATCH)
    xg_against = _resolution(snapshot, "home", HistoricalFeatureId.XG_AGAINST_PER_MATCH)
    xg_total = _resolution(snapshot, "home", HistoricalFeatureId.XG_TOTAL_PER_MATCH)
    assert xg_for.conflict_count == 2
    assert xg_against.conflict_count == 2
    assert xg_total.conflict_count == 4


def test_canonical_schema_sql_is_pinned_and_not_caller_injectable(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [_match("2025-01-10", "Home", "Away", 1, 0, source_id="target")])
    first = build_historical_asof_snapshot(db, keys[0])
    second = build_historical_asof_snapshot(db, keys[0])
    assert first.source_schema_sql_sha256 == second.source_schema_sql_sha256
    assert first.source_schema_sql_sha256 == EXPECTED_WAREHOUSE_SCHEMA_SQL_SHA256_BY_VERSION["1"]
    with pytest.raises(TypeError):
        build_historical_asof_snapshot(db, keys[0], schema_sql_path=tmp_path / "forged.sql")

    modified = tmp_path / "modified-schema.sql"
    modified.write_text("-- not ATHENA's reviewed schema\n", encoding="utf-8")
    with pytest.raises(HistoricalAsOfError, match="schema SQL drift"):
        validate_warehouse_schema_sql("1", modified)
    with pytest.raises(HistoricalAsOfError, match="unreviewed"):
        validate_warehouse_schema_sql("999", modified)


def test_warehouse_schema_version_mismatch_still_fails_closed(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [_match("2025-01-10", "Home", "Away", 1, 0, source_id="target")])
    connection = sqlite3.connect(db)
    connection.execute("UPDATE warehouse_meta SET value='999' WHERE key='schema_version'")
    connection.commit(); connection.close()
    with pytest.raises(HistoricalAsOfError, match="schema version mismatch"):
        build_historical_asof_snapshot(db, keys[0])


@pytest.mark.parametrize("field_name,value,error", [
    ("home_xg", -0.01, "negative xG"),
    ("home_shots", -1, "invalid count"),
    ("home_shots", 1.5, "invalid count"),
])
def test_mechanically_impossible_numeric_values_fail_closed(
    tmp_path: Path, field_name: str, value: float, error: str,
):
    db, keys = _warehouse(tmp_path, [
        _match("2025-01-01", "Home", "Prior", 1, 0, source_id="prior"),
        _match("2025-01-10", "Home", "Target", 0, 0, source_id="target"),
    ])
    connection = sqlite3.connect(db)
    connection.execute(
        f"UPDATE warehouse_matches SET {field_name}=? WHERE match_key=?", (value, keys[0])
    )
    connection.commit(); connection.close()
    with pytest.raises(HistoricalAsOfError, match=error):
        build_historical_asof_snapshot(db, keys[-1])


def test_possession_is_finite_without_inventing_an_unreviewed_range(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [
        _match("2025-01-01", "Home", "Prior", 1, 0, source_id="prior", home_possession=150.0),
        _match("2025-01-10", "Home", "Target", 0, 0, source_id="target"),
    ])
    snapshot = build_historical_asof_snapshot(db, keys[-1])
    possession = _resolution(snapshot, "home", HistoricalFeatureId.POSSESSION_FOR_MEAN)
    assert possession.value == 150.0


@pytest.mark.parametrize("home_ft,away_ft", [(None, None), (1, None), (None, 0)])
def test_incomplete_prior_fixture_contributes_nothing_to_state_or_schedule(
    tmp_path: Path, home_ft: int | None, away_ft: int | None,
):
    db, keys = _warehouse(tmp_path, [
        _match(
            "2025-01-05", "Home", "Unplayed", home_ft, away_ft,
            source_id="unplayed", home_xg=4.0, away_xg=3.0,
            home_shots=30, away_shots=20,
        ),
        _match("2025-01-10", "Home", "Target", 0, 0, source_id="target"),
    ])
    direct = build_historical_asof_snapshot(db, keys[-1])
    assert _resolution(
        direct, "home", HistoricalFeatureId.GOALS_FOR_PER_MATCH
    ).status is HistoricalFeatureStatus.MISSING
    assert _resolution(
        direct, "home", HistoricalFeatureId.XG_FOR_PER_MATCH
    ).status is HistoricalFeatureStatus.MISSING
    assert _resolution(
        direct, "home", HistoricalFeatureId.DAYS_SINCE_LAST_MATCH,
        window=HistoricalWindow.AS_OF,
    ).status is HistoricalFeatureStatus.MISSING

    output = tmp_path / f"incomplete-{home_ft}-{away_ft}.db"
    build_corpus(db, output, start_date="2025-01-10", limit=1)
    connection = sqlite3.connect(output)
    payload = json.loads(connection.execute(
        "SELECT payload_json FROM historical_asof_snapshots WHERE match_key=?", (keys[-1],)
    ).fetchone()[0])
    connection.close()
    assert payload == direct.to_dict()


def test_completed_prior_fixture_qualifies_for_performance_and_schedule(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [
        _match("2025-01-05", "Home", "Completed", 2, 1, source_id="completed"),
        _match("2025-01-10", "Home", "Target", 0, 0, source_id="target"),
    ])
    snapshot = build_historical_asof_snapshot(db, keys[-1])
    assert _resolution(snapshot, "home", HistoricalFeatureId.GOALS_FOR_PER_MATCH).value == 2
    assert _resolution(
        snapshot, "home", HistoricalFeatureId.DAYS_SINCE_LAST_MATCH,
        window=HistoricalWindow.AS_OF,
    ).value == 5
    assert qualifies_completed_prior_fixture({"home_score_ft": 2, "away_score_ft": 1})
    assert not qualifies_completed_prior_fixture({"home_score_ft": None, "away_score_ft": 1})


@pytest.mark.parametrize("suffix", ["-wal", "-journal"])
def test_companion_created_after_open_fails_final_source_validation(tmp_path: Path, suffix: str):
    db, _ = _warehouse(tmp_path, [_match("2025-01-10", "Home", "Away", 1, 0, source_id="target")])
    with ReadOnlyHistoricalWarehouse(db) as source:
        Path(str(db) + suffix).write_bytes(b"appeared-after-open")
        with pytest.raises(HistoricalAsOfError, match="unsafe active"):
            source.assert_unchanged()


def test_schedule_cache_prunes_on_add_even_before_any_target_lookup():
    rolling = TeamRollingHistory()
    for year in range(1990, 2026):
        projection = dataclasses.replace(
            _projection_for(f"m{year}", f"{year}-01-01"), season=None,
        )
        rolling.add_date_bucket(projection.match_date, (projection,))
        assert len(rolling.schedule_date_buckets) <= 1
    assert rolling.schedule_date_buckets[0][0] == "2025-01-01"
    assert sum(len(bucket) for _, bucket in rolling.recent_date_buckets) == 20


def test_days_since_last_match_uses_complete_latest_date_bucket_deterministically():
    older = _projection_for("older", "2025-01-01")
    tied_a = _projection_for("latest-a", "2025-01-05")
    tied_b = _projection_for("latest-b", "2025-01-05")
    forward = haf._schedule_resolutions((older, tied_b, tied_a), "2025-01-10")
    reverse = haf._schedule_resolutions((tied_a, older, tied_b), "2025-01-10")
    days_forward = find_resolution(
        forward, HistoricalFeatureId.DAYS_SINCE_LAST_MATCH,
        HistoricalTeamScope.OVERALL, HistoricalWindow.AS_OF,
    )
    days_reverse = find_resolution(
        reverse, HistoricalFeatureId.DAYS_SINCE_LAST_MATCH,
        HistoricalTeamScope.OVERALL, HistoricalWindow.AS_OF,
    )
    assert days_forward == days_reverse
    assert days_forward.value == 5
    assert days_forward.effective_match_sample == 2
    assert days_forward.contributing_match_keys == ("latest-a", "latest-b")

    zero_forward = find_resolution(
        forward, HistoricalFeatureId.FIXTURES_LAST_7_DAYS,
        HistoricalTeamScope.OVERALL, HistoricalWindow.AS_OF,
    )
    far_forward = haf._schedule_resolutions((older, tied_b, tied_a), "2025-02-10")
    far_reverse = haf._schedule_resolutions((tied_b, tied_a, older), "2025-02-10")
    zero_forward_far = find_resolution(
        far_forward, HistoricalFeatureId.FIXTURES_LAST_7_DAYS,
        HistoricalTeamScope.OVERALL, HistoricalWindow.AS_OF,
    )
    zero_reverse = find_resolution(
        far_reverse, HistoricalFeatureId.FIXTURES_LAST_7_DAYS,
        HistoricalTeamScope.OVERALL, HistoricalWindow.AS_OF,
    )
    assert zero_reverse.value == 0
    assert zero_forward_far == zero_reverse
    assert zero_reverse.contributing_match_keys == ("latest-a", "latest-b")
    assert zero_forward.contributing_match_keys == ("latest-a", "latest-b")


def test_unusable_target_identity_fails_instead_of_emitting_missing(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [
        _match("2025-01-10", "Home", "Away", 1, 0, source_id="target", competition_key=None),
    ])
    with pytest.raises(HistoricalAsOfError, match="unusable target team identity"):
        build_historical_asof_snapshot(db, keys[0])
    with pytest.raises(HistoricalAsOfError, match="unusable target team identity"):
        build_corpus(db, tmp_path / "invalid-identity.db", limit=1)

    db2, keys2 = _warehouse(tmp_path / "blank-team", [
        _match("2025-01-10", "Home", "Away", 1, 0, source_id="target"),
    ])
    connection = sqlite3.connect(db2)
    connection.execute("UPDATE warehouse_matches SET home_team='' WHERE match_key=?", (keys2[0],))
    connection.commit(); connection.close()
    with pytest.raises(HistoricalAsOfError, match="unusable target team identity"):
        build_historical_asof_snapshot(db2, keys2[0])


def test_extra_period_match_keeps_results_and_schedule_but_blocks_advanced_stats(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [
        _match(
            "2025-01-05", "Home", "Cup", 1, 1, source_id="et",
            home_score_et=2, away_score_et=1,
            home_xg=2.5, away_xg=1.1, home_shots=20, away_shots=9,
            home_yellows=3, away_yellows=2,
        ),
        _match("2025-01-10", "Home", "Target", 0, 0, source_id="target"),
    ])
    direct = build_historical_asof_snapshot(db, keys[-1])
    assert _resolution(direct, "home", HistoricalFeatureId.POINTS_PER_MATCH).value == 1
    assert _resolution(
        direct, "home", HistoricalFeatureId.DAYS_SINCE_LAST_MATCH,
        window=HistoricalWindow.AS_OF,
    ).value == 5
    for feature_id in (
        HistoricalFeatureId.XG_FOR_PER_MATCH,
        HistoricalFeatureId.XG_AGAINST_PER_MATCH,
        HistoricalFeatureId.XG_TOTAL_PER_MATCH,
        HistoricalFeatureId.SHOTS_FOR_PER_MATCH,
        HistoricalFeatureId.YELLOWS_FOR_PER_MATCH,
    ):
        resolution = _resolution(direct, "home", feature_id)
        assert resolution.status is HistoricalFeatureStatus.BLOCKED
        assert resolution.blocker is haf.HistoricalFeatureBlocker.UNSAFE_SOURCE_STATE

    output = tmp_path / "et-features.db"
    build_corpus(db, output, start_date="2025-01-10", limit=1)
    connection = sqlite3.connect(output)
    payload = json.loads(connection.execute(
        "SELECT payload_json FROM historical_asof_snapshots WHERE match_key=?", (keys[-1],)
    ).fetchone()[0])
    connection.close()
    assert payload == direct.to_dict()


def test_normal_completed_non_et_match_keeps_advanced_stats(tmp_path: Path):
    db, keys = _warehouse(tmp_path, [
        _match(
            "2025-01-05", "Home", "Normal", 2, 0, source_id="normal",
            home_xg=1.7, away_xg=0.4, home_yellows=1, away_yellows=2,
        ),
        _match("2025-01-10", "Home", "Target", 0, 0, source_id="target"),
    ])
    snapshot = build_historical_asof_snapshot(db, keys[-1])
    assert _resolution(snapshot, "home", HistoricalFeatureId.XG_FOR_PER_MATCH).value == 1.7
    assert _resolution(snapshot, "home", HistoricalFeatureId.YELLOWS_FOR_PER_MATCH).value == 1


def _manual_feature_resolution(
    projection: TeamMatchProjection, feature_id: HistoricalFeatureId,
):
    definition = next(item for item in HISTORICAL_FEATURE_REGISTRY if item.feature_id is feature_id)
    return haf._resolution(
        definition, HistoricalTeamScope.OVERALL, HistoricalWindow.LAST_5,
        (projection,), "2025-01-10",
    )


def test_minimal_score_dependencies_allow_only_mathematically_supported_features():
    base = _projection_for("partial", "2025-01-01")
    goals_for_only = dataclasses.replace(base, goals_for=2, goals_against=None)
    goals_for_mean = _manual_feature_resolution(
        goals_for_only, HistoricalFeatureId.GOALS_FOR_PER_MATCH
    )
    failed_to_score = _manual_feature_resolution(
        goals_for_only, HistoricalFeatureId.FAILED_TO_SCORE_RATE
    )
    assert goals_for_mean.status is HistoricalFeatureStatus.AVAILABLE
    assert goals_for_mean.value == 2
    assert failed_to_score.status is HistoricalFeatureStatus.AVAILABLE
    assert failed_to_score.value == 0
    assert _manual_feature_resolution(
        goals_for_only, HistoricalFeatureId.GOALS_AGAINST_PER_MATCH
    ).status is HistoricalFeatureStatus.MISSING
    assert _manual_feature_resolution(
        goals_for_only, HistoricalFeatureId.CLEAN_SHEET_RATE
    ).status is HistoricalFeatureStatus.MISSING

    goals_against_only = dataclasses.replace(base, goals_for=None, goals_against=0)
    goals_against_mean = _manual_feature_resolution(
        goals_against_only, HistoricalFeatureId.GOALS_AGAINST_PER_MATCH
    )
    clean_sheet = _manual_feature_resolution(
        goals_against_only, HistoricalFeatureId.CLEAN_SHEET_RATE
    )
    assert goals_against_mean.status is HistoricalFeatureStatus.AVAILABLE
    assert goals_against_mean.value == 0
    assert clean_sheet.status is HistoricalFeatureStatus.AVAILABLE
    assert clean_sheet.value == 1
    assert _manual_feature_resolution(
        goals_against_only, HistoricalFeatureId.GOALS_FOR_PER_MATCH
    ).status is HistoricalFeatureStatus.MISSING
    assert _manual_feature_resolution(
        goals_against_only, HistoricalFeatureId.FAILED_TO_SCORE_RATE
    ).status is HistoricalFeatureStatus.MISSING

    two_sided = (
        HistoricalFeatureId.POINTS_PER_MATCH, HistoricalFeatureId.WIN_RATE,
        HistoricalFeatureId.DRAW_RATE, HistoricalFeatureId.LOSS_RATE,
        HistoricalFeatureId.GOAL_DIFFERENCE_PER_MATCH,
        HistoricalFeatureId.TOTAL_GOALS_PER_MATCH, HistoricalFeatureId.BTTS_RATE,
        HistoricalFeatureId.OVER_1_5_RATE, HistoricalFeatureId.OVER_2_5_RATE,
    )
    for feature_id in two_sided:
        assert _manual_feature_resolution(
            goals_for_only, feature_id
        ).status is HistoricalFeatureStatus.MISSING
        assert _manual_feature_resolution(
            goals_against_only, feature_id
        ).status is HistoricalFeatureStatus.MISSING
        assert _manual_feature_resolution(
            dataclasses.replace(base, goals_for=2, goals_against=0), feature_id
        ).status is HistoricalFeatureStatus.AVAILABLE
