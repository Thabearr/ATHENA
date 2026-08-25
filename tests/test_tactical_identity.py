from __future__ import annotations

import dataclasses
import json
import shutil
import socket
import sqlite3
from pathlib import Path
from types import MappingProxyType

import pytest

import domain.tactical_identity as ti
from scripts.build_historical_asof_feature_corpus import build_corpus
from scripts.build_historical_warehouse import Warehouse
from scripts.build_tactical_identity_corpus import build_tactical_corpus


def _match(day: str, home: str, away: str, home_score: int, away_score: int,
           source_id: str, **extra) -> dict:
    return {
        "competition_key": extra.pop("competition_key", "test_league"),
        "competition_name": "Test League", "scope": extra.pop("scope", "club"),
        "season": "2025", "match_date": day, "kickoff_time": "15:00",
        "home_team": home, "away_team": away, "home_score_ft": home_score,
        "away_score_ft": away_score, "_source_id": source_id, **extra,
    }


def _warehouse(tmp_path: Path, rows: list[dict]) -> tuple[Path, list[str]]:
    path = tmp_path / "history.db"
    warehouse = Warehouse(path)
    warehouse.initialize()
    for competition_key in sorted({row["competition_key"] for row in rows}):
        warehouse.conn.execute(
            "INSERT OR IGNORE INTO warehouse_competitions(competition_key,display_name,scope,"
            "competition_type,hierarchy_rank,aliases_json) VALUES(?,?,?,?,?,?)",
            (competition_key, "Test League", "club", "league", 1, "[]"),
        )
    keys = []
    for row in rows:
        payload = dict(row)
        source_id = payload.pop("_source_id")
        keys.append(warehouse.upsert_match(
            payload, source_key="football_data_uk", source_match_id=source_id
        ))
    warehouse.close()
    return path, keys


def _rich_rows(low_name: str = "Low Signal") -> list[dict]:
    rows = []
    # Broad, strictly-prior competition population with varied environments.
    for index in range(12):
        day = f"2025-01-{index + 1:02d}"
        high = index % 2 == 0
        rows.append(_match(
            day, f"Base{index}", f"Peer{index}", 4 if high else 1, 2 if high else 1,
            f"base-{index}", home_score_ht=2 if high else 0,
            away_score_ht=1 if high else 0, home_xg=3.4 if high else 1.0,
            away_xg=1.9 if high else 0.8, home_shots=19 if high else 8,
            away_shots=13 if high else 7, home_shots_on_target=9 if high else 3,
            away_shots_on_target=6 if high else 2, home_possession=56.0,
            away_possession=44.0,
        ))
    for index in range(5):
        day = f"2025-02-{index + 1:02d}"
        rows.append(_match(
            day, low_name, f"LowOpp{index}", 0 if index % 2 else 1, 0,
            f"low-{index}", home_score_ht=0, away_score_ht=0,
            home_xg=0.65, away_xg=0.35, home_shots=7, away_shots=4,
            home_shots_on_target=2, away_shots_on_target=1,
            home_possession=45.0, away_possession=55.0,
            home_coach="Coach Low" if index > 1 else "Coach Old",
        ))
        rows.append(_match(
            day, f"HighOpp{index}", "High Signal", 3, 7,
            f"high-{index}", home_score_ht=1, away_score_ht=2,
            home_xg=2.4, away_xg=5.5, home_shots=15, away_shots=28,
            home_shots_on_target=6, away_shots_on_target=15,
            home_possession=42.0, away_possession=58.0,
        ))
    rows.append(_match("2025-03-01", low_name, "High Signal", 9, 8, "target",
                       home_score_ht=5, away_score_ht=4, home_xg=9.9, away_xg=8.8,
                       home_shots=99, away_shots=88, home_coach="Posthoc Target Coach"))
    return rows


def _inputs(tmp_path: Path, rows: list[dict] | None = None):
    db, keys = _warehouse(tmp_path, rows or _rich_rows())
    corpus = tmp_path / "asof.db"
    build_corpus(db, corpus)
    return db, corpus, keys


def _dimension(snapshot, side: str, dimension: ti.TacticalDimensionId):
    return ti.find_dimension(getattr(snapshot, f"{side}_profile"), dimension)


def _semantic_profile(profile):
    return [
        (item.dimension_id, item.status, item.continuous_score, item.descriptor,
         tuple((component.feature_id, component.status, component.raw_team_estimate,
                component.competition_prior, component.shrunk_estimate,
                component.relative_z) for component in item.components))
        for item in profile.overall_dimensions
    ]


def test_registry_and_generation_contract_are_independently_pinned():
    assert ti.validate_tactical_identity_registry() == (
        "c71f11e9f97fcc71bd38eb7a9fa558ebc09e5dfbc648e5991862dc75b80fcb69"
    )
    changed = list(ti.TACTICAL_IDENTITY_REGISTRY)
    changed[0] = dataclasses.replace(changed[0], algorithm_id="DRIFT")
    with pytest.raises(ti.TacticalIdentityError, match="registry drift"):
        ti.validate_tactical_identity_registry(changed, 1)
    with pytest.raises(ti.TacticalIdentityError, match="unreviewed"):
        ti.validate_tactical_identity_registry(changed, 2)
    reviewed = MappingProxyType({2: ti.calculate_tactical_identity_registry_sha256(changed, 2)})
    assert ti.validate_tactical_identity_registry(changed, 2, reviewed) == reviewed[2]

    expected = "73482eb97e8ad0acaa6690a72921117541cc6c97948e35a4ff49b481b738d701"
    assert ti.validate_tactical_generation_contract() == expected
    with pytest.raises(ti.TacticalIdentityError, match="contract drift"):
        ti.validate_tactical_generation_contract(1, recency_policy_id="DRIFT")
    with pytest.raises(ti.TacticalIdentityError, match="unreviewed"):
        ti.validate_tactical_generation_contract(2)


def test_synthetic_low_and_high_event_profiles_are_evidence_driven(tmp_path: Path):
    db, corpus, keys = _inputs(tmp_path)
    snapshot = ti.build_tactical_identity_snapshot(corpus, db, keys[-1])
    low = _dimension(snapshot, "home", ti.TacticalDimensionId.EVENT_ENVIRONMENT)
    high = _dimension(snapshot, "away", ti.TacticalDimensionId.EVENT_ENVIRONMENT)
    defense = _dimension(snapshot, "home", ti.TacticalDimensionId.DEFENSIVE_SUPPRESSION)
    assert low.descriptor is ti.TacticalDescriptor.LOW_EVENT
    assert high.descriptor is ti.TacticalDescriptor.HIGH_EVENT
    assert low.continuous_score < high.continuous_score
    assert defense.descriptor is ti.TacticalDescriptor.DEFENSIVE_SUPPRESSION_HIGH
    assert snapshot.home_profile.team == "Low Signal"
    assert not any(dict(snapshot.authority_flags).values())


def test_team_rename_does_not_change_profile_scores(tmp_path: Path):
    first = tmp_path / "first"; second = tmp_path / "second"
    first.mkdir(); second.mkdir()
    db_a, corpus_a, keys_a = _inputs(first, _rich_rows("Low Signal"))
    db_b, corpus_b, keys_b = _inputs(second, _rich_rows("Renamed Evidence"))
    a = ti.build_tactical_identity_snapshot(corpus_a, db_a, keys_a[-1])
    b = ti.build_tactical_identity_snapshot(corpus_b, db_b, keys_b[-1])
    assert _semantic_profile(a.home_profile) == _semantic_profile(b.home_profile)
    assert a.home_profile.team != b.home_profile.team


def test_target_statistics_and_same_day_rows_cannot_affect_profile(tmp_path: Path):
    rows = _rich_rows()
    rows.insert(-1, _match("2025-03-01", "Low Signal", "Same Day", 20, 20,
                           "same-day", home_xg=20.0, away_xg=20.0,
                           home_shots=100, away_shots=100))
    db, corpus, keys = _inputs(tmp_path, rows)
    target_key = keys[-1]
    before = ti.build_tactical_identity_snapshot(corpus, db, target_key)
    connection = sqlite3.connect(db)
    connection.execute(
        "UPDATE warehouse_matches SET home_score_ft=0,away_score_ft=0,home_score_ht=0,"
        "away_score_ht=0,home_xg=0.0,away_xg=0.0,home_shots=0,away_shots=0 "
        "WHERE match_key=?", (target_key,))
    connection.commit(); connection.close()
    changed_corpus = tmp_path / "changed-asof.db"
    build_corpus(db, changed_corpus)
    after = ti.build_tactical_identity_snapshot(changed_corpus, db, target_key)
    assert _semantic_profile(before.home_profile) == _semantic_profile(after.home_profile)
    assert _semantic_profile(before.away_profile) == _semantic_profile(after.away_profile)


def test_missing_xg_and_ht_remain_missing_without_neutral_defaults(tmp_path: Path):
    rows = [_match("2025-01-01", "Home", "Prior", 1, 0, "prior"),
            _match("2025-02-01", "Home", "Away", 0, 0, "target")]
    db, corpus, keys = _inputs(tmp_path, rows)
    snapshot = ti.build_tactical_identity_snapshot(corpus, db, keys[-1])
    event = _dimension(snapshot, "home", ti.TacticalDimensionId.EVENT_ENVIRONMENT)
    by_id = {item.feature_id: item for item in event.components}
    assert by_id[ti.HistoricalFeatureId.XG_TOTAL_PER_MATCH].status is ti.TacticalStatus.MISSING
    assert by_id[ti.HistoricalFeatureId.XG_TOTAL_PER_MATCH].raw_team_estimate is None
    assert by_id[ti.HistoricalFeatureId.FIRST_HALF_TOTAL_GOALS_PER_MATCH].status is ti.TacticalStatus.MISSING
    assert event.status is ti.TacticalStatus.MISSING


def test_one_game_is_low_effective_sample_and_zero_history_stays_missing(tmp_path: Path):
    db, corpus, keys = _inputs(tmp_path, [
        _match("2025-01-01", "One", "Prior", 1, 0, "prior", home_xg=0.7, away_xg=0.2),
        _match("2025-02-01", "One", "None", 0, 0, "target"),
    ])
    snapshot = ti.build_tactical_identity_snapshot(corpus, db, keys[-1])
    component = _dimension(snapshot, "home", ti.TacticalDimensionId.EVENT_ENVIRONMENT).components[0]
    assert component.effective_weighted_sample == pytest.approx(1.0)
    assert component.shrunk_estimate is None
    assert all(item.status is ti.TacticalStatus.MISSING
               for item in snapshot.away_profile.overall_dimensions
               if item.dimension_id not in {ti.TacticalDimensionId.EVIDENCE_UNCERTAINTY})


def test_home_away_scopes_and_missing_delta_do_not_mix(tmp_path: Path):
    db, corpus, keys = _inputs(tmp_path)
    snapshot = ti.build_tactical_identity_snapshot(corpus, db, keys[-1])
    assert snapshot.home_profile.venue_expression.venue_scope == "HOME_ONLY"
    assert snapshot.away_profile.venue_expression.venue_scope == "AWAY_ONLY"
    no_history = tmp_path / "none"; no_history.mkdir()
    db2, corpus2, keys2 = _inputs(no_history, [_match("2025-01-01", "A", "B", 0, 0, "t")])
    empty = ti.build_tactical_identity_snapshot(corpus2, db2, keys2[-1])
    assert empty.home_profile.venue_expression.status is ti.TacticalStatus.MISSING
    assert not empty.home_profile.venue_expression.dimension_deltas


def test_prior_manager_is_observed_not_target_current_manager(tmp_path: Path):
    db, corpus, keys = _inputs(tmp_path)
    snapshot = ti.build_tactical_identity_snapshot(corpus, db, keys[-1])
    manager = snapshot.home_profile.manager_regime
    assert manager.status is ti.TacticalStatus.AVAILABLE
    assert manager.last_observed_prior_manager == "Coach Low"
    assert manager.manager_change_observed_between_prior_matches is True
    assert manager.current_manager_confirmed is False
    assert manager.last_observed_prior_manager != "Posthoc Target Coach"


def test_source_binding_rejects_unrelated_warehouse_or_forged_corpus(tmp_path: Path):
    first = tmp_path / "first"; second = tmp_path / "second"
    first.mkdir(); second.mkdir()
    db, corpus, keys = _inputs(first)
    other, _, _ = _inputs(second)
    connection = sqlite3.connect(other)
    connection.execute("INSERT INTO warehouse_meta VALUES('different_source_bytes','yes')")
    connection.commit(); connection.close()
    with pytest.raises(ti.TacticalIdentityError, match="SHA mismatch"):
        ti.build_tactical_identity_snapshot(corpus, other, keys[-1])
    forged = tmp_path / "forged.db"
    shutil.copy2(corpus, forged)
    connection = sqlite3.connect(forged)
    connection.execute("UPDATE corpus_meta SET value=? WHERE key='source_warehouse_sha256'",
                       (json.dumps("0" * 64),))
    connection.commit(); connection.close()
    with pytest.raises(ti.TacticalIdentityError, match="ancestry mismatch"):
        ti.build_tactical_identity_snapshot(forged, db, keys[-1])


def test_snapshot_is_builder_only_deterministic_and_frozen_from_live_registry(tmp_path: Path,
                                                                              monkeypatch):
    db, corpus, keys = _inputs(tmp_path)
    with pytest.raises(ti.TacticalIdentityError, match="builder-only"):
        ti.TacticalIdentityFixtureSnapshot(target_match_key="forged")
    first = ti.build_tactical_identity_snapshot(corpus, db, keys[-1])
    second = ti.build_tactical_identity_snapshot(corpus, db, keys[-1])
    assert first.canonical_bytes == second.canonical_bytes
    before = first.canonical_bytes, first.canonical_sha256
    monkeypatch.setattr(ti, "TACTICAL_IDENTITY_REGISTRY", ())
    assert (first.canonical_bytes, first.canonical_sha256) == before


def test_no_cross_competition_join_no_odds_and_no_network(tmp_path: Path, monkeypatch):
    rows = [
        _match("2025-01-01", "Same", "Cup Opp", 9, 9, "cup", competition_key="cup"),
        _match("2025-01-02", "Same", "League Opp", 1, 0, "league"),
        _match("2025-02-01", "Same", "Target", 0, 0, "target"),
    ]
    db, corpus, keys = _inputs(tmp_path, rows)
    monkeypatch.setattr(socket, "create_connection", lambda *_a, **_k: (_ for _ in ()).throw(
        AssertionError("network forbidden")))
    snapshot = ti.build_tactical_identity_snapshot(corpus, db, keys[-1])
    component = _dimension(snapshot, "home", ti.TacticalDimensionId.EVENT_ENVIRONMENT).components[0]
    assert component.raw_match_sample == 1
    feature_ids = {feature.value for definition in ti.TACTICAL_IDENTITY_REGISTRY
                   for feature in definition.source_feature_ids}
    assert not any("odds" in value or "bookmaker" in value or "price" in value
                   for value in feature_ids)
    assert snapshot.team_identity_policy_id == "COMPETITION_SCOPED_EXACT_CANONICAL_TEAM_V1"


def test_opponent_and_score_state_fail_closed_when_safe_join_is_unavailable(tmp_path: Path):
    db, corpus, keys = _inputs(tmp_path)
    snapshot = ti.build_tactical_identity_snapshot(corpus, db, keys[-1])
    assert snapshot.home_profile.opponent_adjustment.status is ti.TacticalStatus.MISSING
    assert snapshot.home_profile.opponent_adjustment.sample_count == 0
    assert ti.SCORE_STATE_POLICY_ID == "FUTURE_EVIDENCE_REQUIRED_V1"
    assert snapshot.home_profile.schedule_context_policy_id == (
        "COMPETITION_SCOPED_WORKLOAD_CONTEXT_V1"
    )


def test_bulk_builder_is_date_batched_and_matches_direct_snapshot(tmp_path: Path):
    db, corpus, keys = _inputs(tmp_path)
    direct = ti.build_tactical_identity_snapshot(corpus, db, keys[-1])
    output = tmp_path / "tactical.db"
    assert build_tactical_corpus(corpus, db, output, start_date="2025-03-01") == 1
    connection = sqlite3.connect(output)
    row = connection.execute(
        "SELECT canonical_sha256,payload_json FROM tactical_identity_snapshots"
    ).fetchone()
    connection.close()
    assert row[0] == direct.canonical_sha256
    assert row[1].encode() == direct.canonical_bytes
    with pytest.raises(ti.TacticalIdentityError, match="separate"):
        build_tactical_corpus(corpus, db, db)
