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
        "competition_name": "Test League",
        "scope": extra.pop("scope", "club"),
        "season": "2025",
        "match_date": day,
        "kickoff_time": "15:00",
        "home_team": home,
        "away_team": away,
        "home_score_ft": home_score,
        "away_score_ft": away_score,
        "_source_id": source_id,
        **extra,
    }


def _warehouse(tmp_path: Path, rows: list[dict]) -> tuple[Path, list[str]]:
    path = tmp_path / "history.db"
    warehouse = Warehouse(path)
    warehouse.initialize()
    scopes = {row["competition_key"]: row.get("scope", "club") for row in rows}
    for competition_key in sorted({row["competition_key"] for row in rows}):
        warehouse.conn.execute(
            "INSERT OR IGNORE INTO warehouse_competitions(competition_key,display_name,scope,"
            "competition_type,hierarchy_rank,aliases_json) VALUES(?,?,?,?,?,?)",
            (competition_key, "Test League", scopes[competition_key], "league", 1, "[]"),
        )
    keys = []
    for row in rows:
        payload = dict(row)
        source_id = payload.pop("_source_id")
        keys.append(warehouse.upsert_match(
            payload,
            source_key="football_data_uk",
            source_match_id=source_id,
        ))
    warehouse.close()
    return path, keys


def _rich_rows(low_name: str = "Low Signal") -> list[dict]:
    rows = []
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
    rows.append(_match(
        "2025-03-01", low_name, "High Signal", 9, 8, "target",
        home_score_ht=5, away_score_ht=4, home_xg=9.9, away_xg=8.8,
        home_shots=99, away_shots=88, home_coach="Posthoc Target Coach",
    ))
    return rows


def _inputs(tmp_path: Path, rows: list[dict] | None = None):
    db, keys = _warehouse(tmp_path, rows or _rich_rows())
    corpus = tmp_path / "asof.db"
    build_corpus(db, corpus)
    return db, corpus, keys


def _dimension(snapshot, side: str, dimension: ti.TacticalDimensionId, *, venue=False, regime=False):
    return ti.find_dimension(
        getattr(snapshot, f"{side}_profile"),
        dimension,
        venue=venue,
        regime=regime,
    )


def _semantic_profile(profile):
    return [
        (
            item.dimension_id,
            item.status,
            item.continuous_score,
            item.descriptor,
            tuple((
                component.feature_id,
                component.status,
                component.raw_team_estimate,
                component.competition_prior,
                component.shrunk_estimate,
                component.relative_z,
            ) for component in item.components),
        )
        for item in profile.overall_dimensions
    ]


def test_registry_and_generation_contract_are_independently_pinned():
    assert ti.validate_tactical_identity_registry() == (
        "f3bc2dadefe51126093c44abdacb0a252498684fbed23c4a5662d8d8e8d01d0e"
    )
    changed = list(ti.TACTICAL_IDENTITY_REGISTRY)
    changed[0] = dataclasses.replace(changed[0], algorithm_id="DRIFT")
    with pytest.raises(ti.TacticalIdentityError, match="registry drift"):
        ti.validate_tactical_identity_registry(changed, 1)
    with pytest.raises(ti.TacticalIdentityError, match="unreviewed"):
        ti.validate_tactical_identity_registry(changed, 2)
    reviewed = MappingProxyType({
        2: ti.calculate_tactical_identity_registry_sha256(changed, 2)
    })
    assert ti.validate_tactical_identity_registry(changed, 2, reviewed) == reviewed[2]

    expected = "5658030a4583acc2c6f35ebc1ea0f950e01f1f22d4c6e82ed722e77f26769f9b"
    assert ti.validate_tactical_generation_contract() == expected
    drift_cases = (
        {"recency_half_life_days": 61.0},
        {"shrinkage_k": 6.0},
        {"minimum_team_component_observations": 4},
        {"minimum_baseline_population": 21},
        {"descriptor_low_z": -0.4},
        {"tactical_history_policy_id": "DRIFT"},
        {"historical_feature_registry_sha256": "0" * 64},
    )
    for overrides in drift_cases:
        with pytest.raises(ti.TacticalIdentityError, match="contract drift"):
            ti.validate_tactical_generation_contract(1, **overrides)
    with pytest.raises(ti.TacticalIdentityError, match="unreviewed"):
        ti.validate_tactical_generation_contract(2)


def test_meta_registry_algorithms_match_runtime_contracts():
    by_id = {item.dimension_id: item for item in ti.TACTICAL_IDENTITY_REGISTRY}
    assert by_id[ti.TacticalDimensionId.VENUE_EXPRESSION].algorithm_id == "TARGET_VENUE_MINUS_OVERALL_V1"
    assert by_id[ti.TacticalDimensionId.OPPONENT_INTERACTION].algorithm_id == ti.OPPONENT_ADJUSTMENT_POLICY_ID
    assert by_id[ti.TacticalDimensionId.REGIME_CONTEXT].algorithm_id == ti.MANAGER_REGIME_POLICY_ID
    assert by_id[ti.TacticalDimensionId.EVIDENCE_UNCERTAINTY].algorithm_id == "EXPLICIT_COMPONENT_COVERAGE_V1"


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
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir(); second.mkdir()
    db_a, corpus_a, keys_a = _inputs(first, _rich_rows("Low Signal"))
    db_b, corpus_b, keys_b = _inputs(second, _rich_rows("Renamed Evidence"))
    a = ti.build_tactical_identity_snapshot(corpus_a, db_a, keys_a[-1])
    b = ti.build_tactical_identity_snapshot(corpus_b, db_b, keys_b[-1])
    assert _semantic_profile(a.home_profile) == _semantic_profile(b.home_profile)
    assert a.home_profile.team != b.home_profile.team


def test_target_statistics_and_same_day_rows_cannot_affect_profile(tmp_path: Path):
    rows = _rich_rows()
    rows.insert(-1, _match(
        "2025-03-01", "Low Signal", "Same Day", 20, 20, "same-day",
        home_xg=20.0, away_xg=20.0, home_shots=100, away_shots=100,
    ))
    db, corpus, keys = _inputs(tmp_path, rows)
    target_key = keys[-1]
    before = ti.build_tactical_identity_snapshot(corpus, db, target_key)
    connection = sqlite3.connect(db)
    connection.execute(
        "UPDATE warehouse_matches SET home_score_ft=0,away_score_ft=0,home_score_ht=0,"
        "away_score_ht=0,home_xg=0.0,away_xg=0.0,home_shots=0,away_shots=0 "
        "WHERE match_key=?",
        (target_key,),
    )
    connection.commit(); connection.close()
    changed_corpus = tmp_path / "changed-asof.db"
    build_corpus(db, changed_corpus)
    after = ti.build_tactical_identity_snapshot(changed_corpus, db, target_key)
    assert _semantic_profile(before.home_profile) == _semantic_profile(after.home_profile)
    assert _semantic_profile(before.away_profile) == _semantic_profile(after.away_profile)


def test_missing_xg_and_ht_remain_missing_without_neutral_defaults(tmp_path: Path):
    rows = [
        _match("2025-01-01", "Home", "Prior", 1, 0, "prior"),
        _match("2025-02-01", "Home", "Away", 0, 0, "target"),
    ]
    db, corpus, keys = _inputs(tmp_path, rows)
    snapshot = ti.build_tactical_identity_snapshot(corpus, db, keys[-1])
    event = _dimension(snapshot, "home", ti.TacticalDimensionId.EVENT_ENVIRONMENT)
    by_id = {item.feature_id: item for item in event.components}
    assert by_id[ti.HistoricalFeatureId.XG_TOTAL_PER_MATCH].status is ti.TacticalStatus.MISSING
    assert by_id[ti.HistoricalFeatureId.XG_TOTAL_PER_MATCH].raw_team_estimate is None
    assert by_id[ti.HistoricalFeatureId.FIRST_HALF_TOTAL_GOALS_PER_MATCH].status is ti.TacticalStatus.MISSING
    assert event.status is ti.TacticalStatus.MISSING


def test_one_game_is_low_evidence_and_zero_history_stays_missing(tmp_path: Path):
    db, corpus, keys = _inputs(tmp_path, [
        _match("2025-01-01", "One", "Prior", 1, 0, "prior", home_xg=0.7, away_xg=0.2),
        _match("2025-02-01", "One", "None", 0, 0, "target"),
    ])
    snapshot = ti.build_tactical_identity_snapshot(corpus, db, keys[-1])
    component = _dimension(snapshot, "home", ti.TacticalDimensionId.EVENT_ENVIRONMENT).components[0]
    assert component.kish_effective_sample == pytest.approx(1.0)
    assert component.decay_weight_sum < 1.0
    assert component.shrunk_estimate is None
    assert all(
        item.status is ti.TacticalStatus.MISSING
        for item in snapshot.away_profile.overall_dimensions
        if item.dimension_id is not ti.TacticalDimensionId.EVIDENCE_UNCERTAINTY
    )


def test_recency_reliability_is_age_sensitive(tmp_path: Path):
    rows = []
    for i in range(12):
        rows.append(_match(
            f"2024-01-{i + 1:02d}", f"Base{i}", f"Peer{i}", 2, 1,
            f"b-{i}", home_xg=1.5, away_xg=1.0,
        ))
    for i in range(5):
        rows.append(_match(
            f"2025-12-{i + 1:02d}", "Recent", f"R{i}", 1, 0, f"r-{i}",
            home_xg=1.0, away_xg=0.5,
        ))
        rows.append(_match(
            f"2024-02-{i + 1:02d}", "Ancient", f"A{i}", 1, 0, f"a-{i}",
            home_xg=1.0, away_xg=0.5,
        ))
    rows.append(_match("2026-01-01", "Recent", "X", 0, 0, "target-r"))
    rows.append(_match("2026-01-01", "Ancient", "Y", 0, 0, "target-a"))
    db, corpus, keys = _inputs(tmp_path, rows)
    recent = ti.build_tactical_identity_snapshot(corpus, db, keys[-2])
    ancient = ti.build_tactical_identity_snapshot(corpus, db, keys[-1])
    r = _dimension(recent, "home", ti.TacticalDimensionId.EVENT_ENVIRONMENT).components[0]
    a = _dimension(ancient, "home", ti.TacticalDimensionId.EVENT_ENVIRONMENT).components[0]
    assert r.valid_field_sample == a.valid_field_sample == 5
    assert r.kish_effective_sample == pytest.approx(a.kish_effective_sample, rel=1e-3)
    assert r.decay_weight_sum > a.decay_weight_sum
    assert r.reliability_weight > a.reliability_weight


def test_home_away_scopes_are_independent_last20_windows(tmp_path: Path):
    rows = []
    for index in range(40):
        day = f"2025-{1 + index // 28:02d}-{1 + index % 28:02d}"
        if index % 2 == 0:
            rows.append(_match(day, "Scope Team", f"O{index}", 1, 0, f"m-{index}", home_xg=1.0, away_xg=0.5))
        else:
            rows.append(_match(day, f"O{index}", "Scope Team", 0, 1, f"m-{index}", home_xg=0.5, away_xg=1.0))
    rows.append(_match("2025-03-01", "Scope Team", "Target", 0, 0, "target"))
    db, corpus, keys = _inputs(tmp_path, rows)
    snapshot = ti.build_tactical_identity_snapshot(corpus, db, keys[-1])
    overall = _dimension(snapshot, "home", ti.TacticalDimensionId.EVENT_ENVIRONMENT)
    venue = _dimension(snapshot, "home", ti.TacticalDimensionId.EVENT_ENVIRONMENT, venue=True)
    assert overall.components[0].raw_match_sample == 20
    assert venue.components[0].raw_match_sample == 20
    assert snapshot.home_profile.venue_expression.venue_scope == "HOME_ONLY"


def test_missing_delta_does_not_become_zero(tmp_path: Path):
    db, corpus, keys = _inputs(tmp_path, [_match("2025-01-01", "A", "B", 0, 0, "t")])
    snapshot = ti.build_tactical_identity_snapshot(corpus, db, keys[-1])
    assert snapshot.home_profile.venue_expression.status is ti.TacticalStatus.MISSING
    assert not snapshot.home_profile.venue_expression.dimension_deltas


def test_prior_manager_profile_is_separate_and_target_is_not_current_manager(tmp_path: Path):
    db, corpus, keys = _inputs(tmp_path)
    snapshot = ti.build_tactical_identity_snapshot(corpus, db, keys[-1])
    manager = snapshot.home_profile.manager_regime
    assert manager.status is ti.TacticalStatus.AVAILABLE
    assert manager.last_observed_prior_manager == "Coach Low"
    assert manager.manager_change_observed_between_prior_matches is True
    assert manager.current_manager_confirmed is False
    assert manager.last_observed_prior_manager != "Posthoc Target Coach"
    assert snapshot.home_profile.regime_dimensions
    assert snapshot.home_profile.regime_expression.semantic_status == "LAST_OBSERVED_PRIOR_MANAGER_REGIME"


def test_same_date_manager_ambiguity_fails_closed(tmp_path: Path):
    rows = [
        _match("2025-01-01", "Team", "A", 1, 0, "a", home_coach="Coach A"),
        _match("2025-01-01", "Team", "B", 1, 0, "b", home_coach="Coach B"),
        _match("2025-02-01", "Team", "Target", 0, 0, "target"),
    ]
    db, corpus, keys = _inputs(tmp_path, rows)
    snapshot = ti.build_tactical_identity_snapshot(corpus, db, keys[-1])
    manager = snapshot.home_profile.manager_regime
    assert manager.status is ti.TacticalStatus.BLOCKED
    assert manager.blocker == "AMBIGUOUS_SAME_DATE_PRIOR_MANAGER"
    assert not snapshot.home_profile.regime_dimensions


def test_unknown_manager_gap_breaks_regime_continuity(tmp_path: Path):
    rows = [
        _match("2025-01-01", "Team", "A", 1, 0, "a", home_coach="Coach A"),
        _match("2025-01-02", "Team", "B", 1, 0, "b"),
        _match("2025-01-03", "Team", "C", 1, 0, "c", home_coach="Coach A"),
        _match("2025-02-01", "Team", "Target", 0, 0, "target"),
    ]
    db, corpus, keys = _inputs(tmp_path, rows)
    snapshot = ti.build_tactical_identity_snapshot(corpus, db, keys[-1])
    manager = snapshot.home_profile.manager_regime
    assert manager.last_observed_prior_manager == "Coach A"
    assert manager.continuity_proven is False
    assert manager.prior_matches_observed_under_manager == 1


def test_feature_local_conflicts_ignore_irrelevant_fields(tmp_path: Path):
    rows = [
        _match("2025-01-01", "Team", "A", 1, 0, "a", home_xg=1.2, away_xg=0.4),
        _match("2025-02-01", "Team", "Target", 0, 0, "target"),
    ]
    db, keys = _warehouse(tmp_path, rows)
    connection = sqlite3.connect(db)
    for field in ("referee", "home_xg"):
        connection.execute(
            "INSERT INTO warehouse_conflicts(match_key,field_name,existing_value,incoming_value,"
            "existing_source,incoming_source) VALUES(?,?,?,?,?,?)",
            (keys[0], field, "x", "y", "a", "b"),
        )
    connection.commit(); connection.close()
    corpus = tmp_path / "asof.db"
    build_corpus(db, corpus)
    snapshot = ti.build_tactical_identity_snapshot(corpus, db, keys[-1])
    attack = _dimension(snapshot, "home", ti.TacticalDimensionId.ATTACKING_PRODUCTION)
    xg = next(item for item in attack.components if item.feature_id is ti.HistoricalFeatureId.XG_FOR_PER_MATCH)
    assert xg.conflict_count == 1


def test_safe_opponent_pre_p_adjustment_uses_only_pre_match_state(tmp_path: Path):
    rows = [
        _match("2025-01-01", "Opponent", "Seed", 0, 1, "opp-prior"),
        _match("2025-01-02", "Team", "Opponent", 2, 0, "team-p"),
        _match("2025-02-01", "Team", "Target", 0, 0, "target"),
    ]
    db, corpus, keys = _inputs(tmp_path, rows)
    snapshot = ti.build_tactical_identity_snapshot(corpus, db, keys[-1])
    adjustment = snapshot.home_profile.opponent_adjustment
    assert adjustment.status is ti.TacticalStatus.AVAILABLE
    assert adjustment.valid_sample == 1
    residuals = dict(adjustment.residuals)
    assert residuals["goals_attack_residual"] == pytest.approx(1.0)
    assert keys[1] in adjustment.contributing_match_keys
    assert adjustment.opponent_snapshot_sha256


def test_opponent_adjustment_missing_without_safe_pre_p_state(tmp_path: Path):
    db, corpus, keys = _inputs(tmp_path, [
        _match("2025-01-01", "Team", "New Opp", 1, 0, "p"),
        _match("2025-02-01", "Team", "Target", 0, 0, "t"),
    ])
    snapshot = ti.build_tactical_identity_snapshot(corpus, db, keys[-1])
    adjustment = snapshot.home_profile.opponent_adjustment
    assert adjustment.status is ti.TacticalStatus.MISSING
    assert adjustment.valid_sample == 0


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
    connection.execute(
        "UPDATE corpus_meta SET value=? WHERE key='source_warehouse_sha256'",
        (json.dumps("0" * 64),),
    )
    connection.commit(); connection.close()
    with pytest.raises(ti.TacticalIdentityError, match="ancestry mismatch"):
        ti.build_tactical_identity_snapshot(forged, db, keys[-1])


def test_caller_authoritative_assembly_is_rejected_even_with_fake_payload_or_baseline():
    assert not hasattr(ti, "_SNAPSHOT_TOKEN")
    with pytest.raises(ti.TacticalIdentityError, match="source-owned"):
        ti._assemble_tactical_identity_snapshot(
            payload={"home_resolutions": [{"value": 999}]},
            baselines={ti.HistoricalFeatureId.GOALS_FOR_PER_MATCH: ti.BaselineMoment(999, 999.0, 1.0)},
        )
    with pytest.raises(ti.TacticalIdentityError, match="source-builder-only"):
        ti.TacticalIdentityFixtureSnapshot(target_match_key="forged")


def test_snapshot_is_deterministic_and_frozen_from_live_registry(tmp_path: Path, monkeypatch):
    db, corpus, keys = _inputs(tmp_path)
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
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("network forbidden")),
    )
    snapshot = ti.build_tactical_identity_snapshot(corpus, db, keys[-1])
    component = _dimension(snapshot, "home", ti.TacticalDimensionId.EVENT_ENVIRONMENT).components[0]
    assert component.raw_match_sample == 1
    feature_ids = {
        feature.value
        for definition in ti.TACTICAL_IDENTITY_REGISTRY
        for feature in definition.source_feature_ids
    }
    assert not any(
        "odds" in value or "bookmaker" in value or "price" in value
        for value in feature_ids
    )
    assert snapshot.team_identity_policy_id == "COMPETITION_SCOPED_EXACT_CANONICAL_TEAM_V1"
    assert snapshot.schedule_context_policy_id == "COMPETITION_SCOPED_WORKLOAD_CONTEXT_V1"
    assert snapshot.score_state_policy_id == "FUTURE_EVIDENCE_REQUIRED_V1"


def test_bulk_builder_streams_targets_and_matches_direct_snapshot(tmp_path: Path, monkeypatch):
    db, corpus, keys = _inputs(tmp_path)
    direct = ti.build_tactical_identity_snapshot(corpus, db, keys[-1])
    assert not hasattr(ti.ReadOnlyHistoricalAsOfCorpus, "iter_targets")
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
