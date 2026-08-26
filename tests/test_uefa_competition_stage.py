from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from domain.uefa_competition_stage import (
    AUTHORITY_FLAGS,
    EXPECTED_GOAL_SCORE_TRAINING_VIEW_CONTRACT_SHA256,
    EXPECTED_PARENT_IDENTITY_SHA256,
    EXPECTED_STAGE_CONTRACT_SHA256,
    EXPECTED_STAGE_REGISTRY_SHA256,
    EXPECTED_TRAINING_SIDECAR_CONTRACT_SHA256,
    EXPECTED_WAREHOUSE_SCHEMA_SQL_SHA256,
    REVIEWED_STAGE_SOURCES,
    UEFACompetitionStage,
    UEFAQualificationState,
    UEFAStageError,
    UEFAStageEvidence,
    UEFAStageProjection,
    UEFATieFormat,
    calculate_parent_identity_sha256,
    calculate_stage_contract_sha256,
    calculate_stage_registry_sha256,
    calculate_training_sidecar_contract_sha256,
    project_training_view_uefa_stages,
    project_warehouse_uefa_stages,
    stage_coverage_report,
    validate_training_sidecar_contract,
    validate_uefa_stage_contract,
)


ROOT = Path(__file__).resolve().parents[1]
WAREHOUSE_SCHEMA = ROOT / "database" / "historical_warehouse_schema.sql"
OPENFOOTBALL_URL = (
    "https://github.com/openfootball/champions-league/"
    "archive/refs/heads/master.zip"
)
FEATURE_SHA = (
    "8052e9177e5c9d88226d36b5e7b11308ba0871889439638eb9f3570d37972bb0"
)
MODEL_SHA = (
    "5451bdd4a3463100866b23b29c0399412fab781f664aee8133c3a123e586ac68"
)
EVALUATION_SHA = (
    "20f533874e74195b2dc3ebe93b9edf60a26a9dbc9aaed5668d7c6412f520efd7"
)


def _ensure_source(db: sqlite3.Connection, source: str) -> None:
    db.execute(
        """
        INSERT OR IGNORE INTO warehouse_sources(
          source_key,display_name,homepage,license_name,attribution,
          redistributable,source_priority,notes
        ) VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            source,
            source,
            None,
            None,
            None,
            0,
            10 if source == "openfootball" else 99,
            "test source",
        ),
    )


def _schema(db: sqlite3.Connection) -> None:
    db.executescript(WAREHOUSE_SCHEMA.read_text(encoding="utf-8"))
    db.execute(
        "INSERT OR REPLACE INTO warehouse_meta(key,value) VALUES(?,?)",
        ("schema_version", "1"),
    )
    for source in ("openfootball", "other_source", "unreviewed_source"):
        _ensure_source(db, source)
    for key, name in (
        ("uefa_ucl", "UEFA Champions League"),
        ("uefa_uel", "UEFA Europa League"),
        ("uefa_uecl", "UEFA Conference League"),
    ):
        db.execute(
            """
            INSERT OR REPLACE INTO warehouse_competitions(
              competition_key,display_name,scope,country,confederation,
              competition_type,hierarchy_rank,hierarchy_tier,active,aliases_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                key,
                name,
                "club",
                None,
                "UEFA",
                "continental_club_cup",
                10,
                "TIER_1",
                1,
                "[]",
            ),
        )


def _add(
    db: sqlite3.Connection,
    *,
    key: str,
    date: str,
    home: str,
    away: str,
    stage: str | None,
    score: tuple[int, int] | None = None,
    competition: str = "uefa_ucl",
    season: str = "2025-26",
    source: str = "openfootball",
    source_path: str | None = (
        "champions-league-master/2025-26/clq.txt"
    ),
    stage_provenance: bool = True,
    extra_provenance_source: str | None = "openfootball",
    score_provenance_source: str | None = None,
    round_name: str | None = None,
    round_provenance_source: str | None = None,
    duplicate_source_lineage: bool = False,
    source_url: str | None = None,
) -> None:
    for source_key in (
        source,
        extra_provenance_source,
        score_provenance_source,
        round_provenance_source,
    ):
        if source_key:
            _ensure_source(db, source_key)
    extra = (
        json.dumps({"openfootball_path": source_path})
        if source_path
        else "{}"
    )
    home_score, away_score = (
        score if score is not None else (None, None)
    )
    competition_name = {
        "uefa_ucl": "UEFA Champions League",
        "uefa_uel": "UEFA Europa League",
        "uefa_uecl": "UEFA Conference League",
    }[competition]
    db.execute(
        """
        INSERT INTO warehouse_matches(
          match_key,competition_key,competition_name,scope,season,
          stage,round_name,match_date,home_team,away_team,
          home_score_ft,away_score_ft,result,extra_json,data_quality
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            key,
            competition,
            competition_name,
            "club",
            season,
            stage,
            round_name,
            date,
            home,
            away,
            home_score,
            away_score,
            (
                "H"
                if score and home_score > away_score
                else "A"
                if score and away_score > home_score
                else "D"
                if score
                else None
            ),
            extra,
            "BASIC" if score else "PARTIAL",
        ),
    )
    if stage is not None and stage_provenance:
        db.execute(
            "INSERT INTO warehouse_field_provenance "
            "(match_key,field_name,source_key,source_priority) "
            "VALUES(?,?,?,?)",
            (key, "stage", source, 10),
        )
    if round_name is not None and round_provenance_source is not None:
        db.execute(
            "INSERT INTO warehouse_field_provenance "
            "(match_key,field_name,source_key,source_priority) "
            "VALUES(?,?,?,?)",
            (key, "round_name", round_provenance_source, 10),
        )
    if extra_provenance_source is not None:
        db.execute(
            "INSERT INTO warehouse_field_provenance "
            "(match_key,field_name,source_key,source_priority) "
            "VALUES(?,?,?,?)",
            (key, "extra_json", extra_provenance_source, 10),
        )
    if score is not None:
        score_source = score_provenance_source or source
        for field in ("home_score_ft", "away_score_ft"):
            db.execute(
                "INSERT INTO warehouse_field_provenance "
                "(match_key,field_name,source_key,source_priority) "
                "VALUES(?,?,?,?)",
                (key, field, score_source, 10),
            )
    actual_url = source_url
    if actual_url is None:
        actual_url = (
            OPENFOOTBALL_URL
            if source == "openfootball"
            else "https://example.invalid/source"
        )
    db.execute(
        """
        INSERT INTO warehouse_match_sources(
          match_key,source_key,source_match_id,source_url,payload_sha256,
          has_ft,has_ht,has_events,has_cards,has_lineups,has_coaches,
          has_officials,has_advanced_stats
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            key,
            source,
            key,
            actual_url,
            None,
            int(score is not None),
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ),
    )
    if duplicate_source_lineage:
        db.execute(
            """
            INSERT INTO warehouse_match_sources(
              match_key,source_key,source_match_id,source_url,payload_sha256,
              has_ft,has_ht,has_events,has_cards,has_lineups,has_coaches,
              has_officials,has_advanced_stats
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                key,
                source,
                key + "-duplicate",
                actual_url,
                None,
                int(score is not None),
                0,
                0,
                0,
                0,
                0,
                0,
                0,
            ),
        )


def _warehouse(path: Path, rows: list[dict]) -> Path:
    db = sqlite3.connect(path)
    _schema(db)
    for kwargs in rows:
        _add(db, **kwargs)
    db.commit()
    db.close()
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _training_view(
    path: Path,
    warehouse_sha: str,
    rows: list[tuple[str, str]],
    *,
    metadata_overrides: dict[str, object] | None = None,
) -> Path:
    db = sqlite3.connect(path)
    db.executescript(
        """
        CREATE TABLE corpus_meta(
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );
        CREATE TABLE training_rows(
          match_key TEXT PRIMARY KEY,
          competition_key TEXT
        );
        """
    )
    metadata: dict[str, object] = {
        "dataset": "athena_goal_score_training_view",
        "schema_version": 1,
        "source_warehouse_sha256": warehouse_sha,
        "goal_score_feature_registry_sha256": FEATURE_SHA,
        "goal_score_model_registry_sha256": MODEL_SHA,
        "goal_score_evaluation_contract_sha256": EVALUATION_SHA,
        "training_view_generation_contract_sha256": (
            EXPECTED_GOAL_SCORE_TRAINING_VIEW_CONTRACT_SHA256
        ),
    }
    metadata.update(metadata_overrides or {})
    db.executemany(
        "INSERT INTO corpus_meta VALUES(?,?)",
        [
            (
                key,
                json.dumps(
                    value,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ),
            )
            for key, value in sorted(metadata.items())
        ],
    )
    db.executemany(
        "INSERT INTO training_rows VALUES(?,?)",
        rows,
    )
    db.commit()
    db.close()
    return path


def test_contract_identities_are_independently_pinned() -> None:
    parent, registry, contract = validate_uefa_stage_contract()
    assert parent == EXPECTED_PARENT_IDENTITY_SHA256
    assert registry == EXPECTED_STAGE_REGISTRY_SHA256
    assert contract == EXPECTED_STAGE_CONTRACT_SHA256
    assert calculate_parent_identity_sha256() == parent
    assert calculate_stage_registry_sha256() == registry
    assert calculate_stage_contract_sha256(parent, registry) == contract
    sidecar = validate_training_sidecar_contract()
    assert sidecar == EXPECTED_TRAINING_SIDECAR_CONTRACT_SHA256
    assert calculate_training_sidecar_contract_sha256(contract) == sidecar
    assert len(REVIEWED_STAGE_SOURCES) == 1
    assert "openfootball" in REVIEWED_STAGE_SOURCES
    assert len(EXPECTED_WAREHOUSE_SCHEMA_SQL_SHA256) == 64


def test_no_downstream_authority_is_granted() -> None:
    assert AUTHORITY_FLAGS["research_stage_stratification"] is True
    assert AUTHORITY_FLAGS["historical_projection"] is True
    assert AUTHORITY_FLAGS["training_sidecar_join"] is True
    for key in (
        "fixture_state_live_authority",
        "probability_inference",
        "calibration",
        "bookmaker_pricing",
        "market_routing",
        "selection",
        "accumulator",
        "production_approval",
        "bet",
    ):
        assert AUTHORITY_FLAGS[key] is False


def test_callers_cannot_construct_authorized_evidence_or_projection() -> None:
    with pytest.raises(UEFAStageError, match="warehouse replay"):
        UEFAStageEvidence()
    with pytest.raises(UEFAStageError, match="warehouse replay"):
        UEFAStageProjection()


def test_generic_qualifier_stage_requires_same_source_file_ancestry(
    tmp_path: Path,
) -> None:
    good = _warehouse(
        tmp_path / "good.db",
        [dict(key="m1", date="2025-08-05", home="A", away="B", stage="3. Round")],
    )
    row = project_warehouse_uefa_stages(good)[0]
    assert row.competition_stage is UEFACompetitionStage.QUALIFYING_R3
    assert row.stage_authorized is True

    bad = _warehouse(
        tmp_path / "bad.db",
        [dict(key="m1", date="2025-08-05", home="A", away="B", stage="3. Round",
              extra_provenance_source="other_source")],
    )
    blocked = project_warehouse_uefa_stages(bad)[0]
    assert blocked.competition_stage is UEFACompetitionStage.UNKNOWN
    assert blocked.stage_authorized is False


def test_unreviewed_stage_source_fails_closed(tmp_path: Path) -> None:
    warehouse = _warehouse(
        tmp_path / "unreviewed.db",
        [dict(key="m1", date="2025-08-05", home="A", away="B",
              stage="Quarter-finals", source="unreviewed_source",
              extra_provenance_source="unreviewed_source", source_path=None)],
    )
    row = project_warehouse_uefa_stages(warehouse)[0]
    assert row.stage_authorized is False
    assert row.competition_stage is UEFACompetitionStage.UNKNOWN
    assert row.blocker == "UNREVIEWED_STAGE_SOURCE"


def test_openfootball_stage_lineage_requires_reviewed_url(tmp_path: Path) -> None:
    warehouse = _warehouse(
        tmp_path / "badurl.db",
        [dict(key="m1", date="2025-08-05", home="A", away="B",
              stage="Quarter-finals",
              source_url="https://example.invalid/openfootball.zip")],
    )
    row = project_warehouse_uefa_stages(warehouse)[0]
    assert row.stage_authorized is False
    assert row.blocker == "STAGE_SOURCE_LINEAGE_NOT_UNIQUE_OR_UNREVIEWED"


def test_qualifier_file_cannot_cross_parent_competition(tmp_path: Path) -> None:
    warehouse = _warehouse(
        tmp_path / "cross.db",
        [dict(key="m1", date="2025-08-05", home="A", away="B", stage="2. Round",
              competition="uefa_uel",
              source_path="champions-league-master/2025-26/clq.txt")],
    )
    row = project_warehouse_uefa_stages(warehouse)[0]
    assert row.stage_authorized is False
    assert row.competition_stage is UEFACompetitionStage.UNKNOWN


def test_stage_without_field_provenance_stays_unknown(tmp_path: Path) -> None:
    warehouse = _warehouse(
        tmp_path / "noprov.db",
        [dict(key="m1", date="2025-08-05", home="A", away="B",
              stage="Quarter-finals", stage_provenance=False)],
    )
    row = project_warehouse_uefa_stages(warehouse)[0]
    assert row.stage_authorized is False
    assert row.blocker == "STAGE_FIELD_HAS_NO_SOURCE_PROVENANCE"


def test_duplicate_source_lineage_fails_closed(tmp_path: Path) -> None:
    warehouse = _warehouse(
        tmp_path / "duplicate.db",
        [dict(key="m1", date="2025-08-05", home="A", away="B",
              stage="Quarter-finals", duplicate_source_lineage=True)],
    )
    row = project_warehouse_uefa_stages(warehouse)[0]
    assert row.stage_authorized is False
    assert row.blocker == "STAGE_SOURCE_LINEAGE_NOT_UNIQUE_OR_UNREVIEWED"


def test_stage_and_round_source_conflict_fails_closed(tmp_path: Path) -> None:
    warehouse = _warehouse(
        tmp_path / "conflict.db",
        [dict(key="m1", date="2025-08-05", home="A", away="B",
              stage="Quarter-finals", round_name="Quarter-finals",
              round_provenance_source="other_source")],
    )
    row = project_warehouse_uefa_stages(warehouse)[0]
    assert row.stage_authorized is False
    assert row.blocker == "STAGE_ROUND_SOURCE_CONFLICT"


def test_group_and_league_phase_are_era_distinct(tmp_path: Path) -> None:
    warehouse = _warehouse(
        tmp_path / "eras.db",
        [
            dict(key="old", date="2023-09-20", home="A", away="B",
                 stage="Group A - Matchday 1", season="2023-24",
                 source_path="champions-league-master/2023-24/cl.txt"),
            dict(key="new", date="2025-09-20", home="C", away="D",
                 stage="League, Matchday 1", season="2025-26",
                 source_path="champions-league-master/2025-26/cl.txt"),
            dict(key="wrong", date="2023-09-21", home="E", away="F",
                 stage="League, Matchday 1", season="2023-24",
                 source_path="champions-league-master/2023-24/cl.txt"),
        ],
    )
    rows = {row.match_key: row for row in project_warehouse_uefa_stages(warehouse)}
    assert rows["old"].competition_stage is UEFACompetitionStage.GROUP_PHASE
    assert rows["old"].tie_format is UEFATieFormat.LEAGUE
    assert rows["new"].competition_stage is UEFACompetitionStage.LEAGUE_PHASE
    assert rows["new"].tie_format is UEFATieFormat.LEAGUE
    assert rows["wrong"].competition_stage is UEFACompetitionStage.UNKNOWN
    assert rows["wrong"].stage_authorized is False


def test_main_file_playoffs_are_modern_knockout_not_qualifying(tmp_path: Path) -> None:
    warehouse = _warehouse(
        tmp_path / "playoffs.db",
        [dict(key="m1", date="2026-02-17", home="A", away="B", stage="Play-offs",
              season="2025-26", source_path="champions-league-master/2025-26/cl.txt")],
    )
    row = project_warehouse_uefa_stages(warehouse)[0]
    assert row.competition_stage is UEFACompetitionStage.KNOCKOUT_PLAYOFF
    assert row.tie_format is UEFATieFormat.UNKNOWN
    assert row.extra_time_possible is None
    assert row.penalties_possible is None


def test_second_leg_aggregate_requires_replayed_prior_stage_and_scores(tmp_path: Path) -> None:
    warehouse = _warehouse(
        tmp_path / "twoleg.db",
        [
            dict(key="leg1", date="2025-08-05", home="A", away="B",
                 stage="3. Round", score=(1, 2)),
            dict(key="leg2", date="2025-08-12", home="B", away="A",
                 stage="3. Round", score=(0, 0)),
        ],
    )
    rows = {row.match_key: row for row in project_warehouse_uefa_stages(warehouse)}
    assert rows["leg1"].tie_format is UEFATieFormat.UNKNOWN
    assert rows["leg1"].leg_number is None
    assert rows["leg1"].aggregate_home is None
    assert rows["leg2"].tie_format is UEFATieFormat.TWO_LEG
    assert rows["leg2"].leg_number == 2
    assert rows["leg2"].aggregate_home == 2
    assert rows["leg2"].aggregate_away == 1
    assert rows["leg2"].qualification_state is UEFAQualificationState.HOME_ADVANTAGE
    assert rows["leg2"].extra_time_possible is True
    assert rows["leg2"].penalties_possible is True
    assert rows["leg1"].stage_source_identity != rows["leg2"].stage_source_identity


def test_prior_leg_must_replay_its_own_stage_ancestry(tmp_path: Path) -> None:
    warehouse = _warehouse(
        tmp_path / "prior-stage.db",
        [
            dict(key="leg1", date="2025-08-05", home="A", away="B",
                 stage="3. Round", score=(1, 2),
                 extra_provenance_source="other_source"),
            dict(key="leg2", date="2025-08-12", home="B", away="A",
                 stage="3. Round", score=(0, 0)),
        ],
    )
    rows = {row.match_key: row for row in project_warehouse_uefa_stages(warehouse)}
    assert rows["leg1"].stage_authorized is False
    assert rows["leg2"].stage_authorized is True
    assert rows["leg2"].tie_format is UEFATieFormat.UNKNOWN
    assert rows["leg2"].aggregate_home is None
    assert rows["leg2"].aggregate_away is None


def test_cross_source_first_leg_score_cannot_mint_aggregate_authority(tmp_path: Path) -> None:
    warehouse = _warehouse(
        tmp_path / "crossscore.db",
        [
            dict(key="leg1", date="2025-08-05", home="A", away="B",
                 stage="3. Round", score=(1, 2),
                 score_provenance_source="other_source"),
            dict(key="leg2", date="2025-08-12", home="B", away="A",
                 stage="3. Round", score=(0, 0)),
        ],
    )
    row = {r.match_key: r for r in project_warehouse_uefa_stages(warehouse)}["leg2"]
    assert row.stage_authorized is True
    assert row.tie_format is UEFATieFormat.UNKNOWN
    assert row.leg_number is None
    assert row.aggregate_home is None
    assert row.aggregate_away is None
    assert row.qualification_state is UEFAQualificationState.UNKNOWN


def test_away_goals_era_is_not_silently_applied_after_2020_21(tmp_path: Path) -> None:
    old = _warehouse(
        tmp_path / "old.db",
        [
            dict(key="old1", date="2020-08-05", home="A", away="B",
                 stage="Quarter-finals", score=(1, 1), season="2020-21",
                 source_path="champions-league-master/2020-21/cl.txt"),
            dict(key="old2", date="2020-08-12", home="B", away="A",
                 stage="Quarter-finals", score=(0, 0), season="2020-21",
                 source_path="champions-league-master/2020-21/cl.txt"),
        ],
    )
    old2 = {r.match_key: r for r in project_warehouse_uefa_stages(old)}["old2"]
    assert old2.aggregate_home == 1
    assert old2.aggregate_away == 1
    assert old2.qualification_state is UEFAQualificationState.HOME_ADVANTAGE

    new = _warehouse(
        tmp_path / "new.db",
        [
            dict(key="new1", date="2025-04-01", home="A", away="B",
                 stage="Quarter-finals", score=(1, 1), season="2024-25",
                 source_path="champions-league-master/2024-25/cl.txt"),
            dict(key="new2", date="2025-04-08", home="B", away="A",
                 stage="Quarter-finals", score=(0, 0), season="2024-25",
                 source_path="champions-league-master/2024-25/cl.txt"),
        ],
    )
    new2 = {r.match_key: r for r in project_warehouse_uefa_stages(new)}["new2"]
    assert new2.aggregate_home == 1
    assert new2.aggregate_away == 1
    assert new2.qualification_state is UEFAQualificationState.LEVEL


def test_historical_uefa_cup_final_two_leg_era_is_not_single_match(tmp_path: Path) -> None:
    warehouse = _warehouse(
        tmp_path / "uel-final.db",
        [
            dict(key="final1", date="1997-05-07", home="Schalke", away="Inter",
                 stage="Final", score=(1, 0), competition="uefa_uel",
                 season="1996-97", source_path="champions-league-master/1996-97/el.txt"),
            dict(key="final2", date="1997-05-21", home="Inter", away="Schalke",
                 stage="Final", score=(1, 0), competition="uefa_uel",
                 season="1996-97", source_path="champions-league-master/1996-97/el.txt"),
        ],
    )
    rows = {row.match_key: row for row in project_warehouse_uefa_stages(warehouse)}
    assert rows["final1"].competition_stage is UEFACompetitionStage.FINAL
    assert rows["final1"].tie_format is UEFATieFormat.UNKNOWN
    assert rows["final2"].tie_format is UEFATieFormat.TWO_LEG
    assert rows["final2"].leg_number == 2
    assert rows["final2"].aggregate_home == 0
    assert rows["final2"].aggregate_away == 1


def test_modern_europa_final_is_single_match(tmp_path: Path) -> None:
    warehouse = _warehouse(
        tmp_path / "modern-final.db",
        [dict(key="final", date="1998-05-06", home="Inter", away="Lazio",
              stage="Final", score=(3, 0), competition="uefa_uel",
              season="1997-98", source_path="champions-league-master/1997-98/el.txt")],
    )
    row = project_warehouse_uefa_stages(warehouse)[0]
    assert row.competition_stage is UEFACompetitionStage.FINAL
    assert row.tie_format is UEFATieFormat.SINGLE_MATCH
    assert row.extra_time_possible is True
    assert row.penalties_possible is True


def test_training_projection_requires_exact_contract_metadata_and_warehouse_sha(tmp_path: Path) -> None:
    warehouse = _warehouse(
        tmp_path / "warehouse.db",
        [dict(key="m1", date="2025-09-20", home="A", away="B",
              stage="League, Matchday 1",
              source_path="champions-league-master/2025-26/cl.txt")],
    )
    view = _training_view(
        tmp_path / "training.db", _sha(warehouse),
        [("m1", "uefa_ucl"), ("other", "eng_premier")],
    )
    rows = project_training_view_uefa_stages(view, warehouse)
    assert [row.match_key for row in rows] == ["m1"]
    assert rows[0].competition_stage is UEFACompetitionStage.LEAGUE_PHASE

    wrong = _training_view(
        tmp_path / "wrong.db", "0" * 64, [("m1", "uefa_ucl")],
    )
    with pytest.raises(UEFAStageError, match="source_warehouse_sha256"):
        project_training_view_uefa_stages(wrong, warehouse)

    forged_contract = _training_view(
        tmp_path / "forged.db", _sha(warehouse), [("m1", "uefa_ucl")],
        metadata_overrides={"training_view_generation_contract_sha256": "0" * 64},
    )
    with pytest.raises(UEFAStageError, match="training_view_generation_contract_sha256"):
        project_training_view_uefa_stages(forged_contract, warehouse)


def test_lookalike_warehouse_schema_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "lookalike.db"
    db = sqlite3.connect(path)
    db.executescript(
        """
        CREATE TABLE warehouse_meta(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE warehouse_matches(match_key TEXT PRIMARY KEY);
        """
    )
    db.execute("INSERT INTO warehouse_meta VALUES('schema_version','1')")
    db.commit()
    db.close()
    with pytest.raises(UEFAStageError, match="historical warehouse validation failed"):
        project_warehouse_uefa_stages(path)


def test_active_sqlite_companion_fails_closed(tmp_path: Path) -> None:
    warehouse = _warehouse(
        tmp_path / "warehouse.db",
        [dict(key="m1", date="2025-09-20", home="A", away="B",
              stage="League, Matchday 1",
              source_path="champions-league-master/2025-26/cl.txt")],
    )
    Path(str(warehouse) + "-wal").write_bytes(b"not-safe")
    with pytest.raises(UEFAStageError, match="active SQLite companion"):
        project_warehouse_uefa_stages(warehouse)


def test_coverage_report_keeps_unknown_explicit(tmp_path: Path) -> None:
    warehouse = _warehouse(
        tmp_path / "coverage.db",
        [
            dict(key="known", date="2025-09-20", home="A", away="B",
                 stage="League, Matchday 1",
                 source_path="champions-league-master/2025-26/cl.txt"),
            dict(key="unknown", date="2025-09-21", home="C", away="D",
                 stage="Mystery Stage",
                 source_path="champions-league-master/2025-26/cl.txt"),
        ],
    )
    report = stage_coverage_report(project_warehouse_uefa_stages(warehouse))
    assert report["total_uefa_matches"] == 2
    assert report["authorized_stage_matches"] == 1
    assert report["unknown_stage_matches"] == 1
    assert report["coverage_fraction"] == 0.5
    assert report["by_stage"]["UNKNOWN"] == 1
    assert report["authority_flags"]["bet"] is False
    assert report["stage_contract_sha256"] == EXPECTED_STAGE_CONTRACT_SHA256
