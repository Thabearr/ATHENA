from pathlib import Path

from scripts.audit_historical_data_integrity import audit_integrity
from scripts.build_historical_warehouse import Warehouse, norm_team
from scripts.enrich_statsbomb_history import canonical_event_type
from scripts.import_football_data_history import resolve_team_alias


def _match(home: str, away: str) -> dict[str, object]:
    return {
        "competition_key": "eng_premier",
        "competition_name": "Premier League",
        "scope": "club",
        "season": "2025-26",
        "match_date": "2025-08-30",
        "home_team": home,
        "away_team": away,
        "home_score_ft": 2,
        "away_score_ft": 1,
    }


def _insert_legacy_match(
    warehouse: Warehouse,
    *,
    match_key: str,
    home: str,
    away: str,
    home_score: int,
    away_score: int,
) -> None:
    warehouse.conn.execute(
        """INSERT INTO warehouse_matches(
           match_key,competition_key,competition_name,scope,season,match_date,
           home_team,away_team,home_score_ft,away_score_ft
        ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (
            match_key,
            "eng_premier",
            "Premier League",
            "club",
            "2025-26",
            "2025-08-30",
            home,
            away,
            home_score,
            away_score,
        ),
    )


def test_canonical_match_key_merges_prefix_suffix_club_designators(tmp_path: Path):
    warehouse = Warehouse(tmp_path / "history.db")
    warehouse.initialize()
    first = warehouse.upsert_match(
        _match("AFC Bournemouth", "Fulham FC"),
        source_key="soccer_datalake",
        source_match_id="provider-a",
    )
    second = warehouse.upsert_match(
        _match("Bournemouth AFC", "FC Fulham"),
        source_key="openfootball",
        source_match_id="provider-b",
    )

    report = audit_integrity(warehouse)

    assert first == second
    assert warehouse.conn.execute("SELECT COUNT(*) FROM warehouse_matches").fetchone()[0] == 1
    assert report["logical_duplicate_fixtures"]["duplicate_groups"] == 0
    warehouse.close()


def test_football_data_alias_resolves_explicit_crosswalk_without_fuzzy_guessing(tmp_path: Path):
    warehouse = Warehouse(tmp_path / "history.db")
    warehouse.initialize()
    warehouse.conn.execute(
        """INSERT INTO warehouse_team_aliases(
           competition_key,source_key,alias,alias_norm,canonical_team,source_team_id
        ) VALUES(?,?,?,?,?,?)""",
        (
            "eng_premier",
            "football_data_uk",
            "Man United",
            norm_team("Man United"),
            "Manchester United",
            "33",
        ),
    )
    warehouse.conn.commit()

    assert resolve_team_alias(warehouse, "eng_premier", "Man United") == "Manchester United"
    assert resolve_team_alias(warehouse, "eng_premier", "Man Utd") == "Man Utd"
    assert resolve_team_alias(warehouse, "eng_championship", "Man United") == "Man United"
    warehouse.close()


def test_integrity_audit_detects_reversed_preexisting_fixture_duplicates(tmp_path: Path):
    warehouse = Warehouse(tmp_path / "history.db")
    warehouse.initialize()
    _insert_legacy_match(
        warehouse,
        match_key="legacy-a",
        home="AFC Bournemouth",
        away="Fulham FC",
        home_score=2,
        away_score=1,
    )
    _insert_legacy_match(
        warehouse,
        match_key="legacy-b",
        home="FC Fulham",
        away="Bournemouth AFC",
        home_score=1,
        away_score=2,
    )

    report = audit_integrity(warehouse)

    assert report["logical_duplicate_fixtures"]["duplicate_groups"] == 1
    assert report["complete"] is False
    warehouse.close()


def test_integrity_audit_reports_same_source_date_ambiguity_without_failing(tmp_path: Path):
    warehouse = Warehouse(tmp_path / "history.db")
    warehouse.initialize()
    _insert_legacy_match(
        warehouse,
        match_key="source-a",
        home="AFC Bournemouth",
        away="Fulham FC",
        home_score=2,
        away_score=1,
    )
    _insert_legacy_match(
        warehouse,
        match_key="source-b",
        home="FC Fulham",
        away="Bournemouth AFC",
        home_score=0,
        away_score=3,
    )
    warehouse.conn.executemany(
        """INSERT INTO warehouse_match_sources(
           match_key,source_key,source_match_id,source_url,has_ft
        ) VALUES(?,?,?,?,1)""",
        [
            ("source-a", "schochastics_global", "historical-leg-a", None),
            ("source-b", "schochastics_global", "historical-leg-b", None),
        ],
    )
    warehouse.conn.commit()

    report = audit_integrity(warehouse)
    duplicates = report["logical_duplicate_fixtures"]

    assert duplicates["duplicate_groups"] == 0
    assert duplicates["same_source_ambiguous_groups"] == 1
    assert report["complete"] is True
    warehouse.close()


def test_integrity_audit_detects_cross_source_reversed_fixture_duplicates(tmp_path: Path):
    warehouse = Warehouse(tmp_path / "history.db")
    warehouse.initialize()
    _insert_legacy_match(
        warehouse,
        match_key="provider-a",
        home="AFC Bournemouth",
        away="Fulham FC",
        home_score=2,
        away_score=1,
    )
    _insert_legacy_match(
        warehouse,
        match_key="provider-b",
        home="FC Fulham",
        away="Bournemouth AFC",
        home_score=1,
        away_score=2,
    )
    warehouse.conn.executemany(
        """INSERT INTO warehouse_match_sources(
           match_key,source_key,source_match_id,source_url,has_ft
        ) VALUES(?,?,?,?,1)""",
        [
            ("provider-a", "soccer_datalake", "provider-a", None),
            ("provider-b", "openfootball", "provider-b", None),
        ],
    )
    warehouse.conn.commit()

    report = audit_integrity(warehouse)

    assert report["logical_duplicate_fixtures"]["duplicate_groups"] == 1
    assert report["complete"] is False
    warehouse.close()


def test_linked_coach_and_referee_respect_source_priority(tmp_path: Path):
    warehouse = Warehouse(tmp_path / "history.db")
    warehouse.initialize()
    base = {
        **_match("Arsenal", "Chelsea"),
        "home_coach": "Weaker Coach",
        "referee": "Weaker Referee",
    }
    key = warehouse.upsert_match(
        base,
        source_key="soccer_datalake",
        source_match_id="provider-match",
    )

    warehouse.coach(key, "statsbomb_open", "Arsenal FC", "Stronger Coach")
    warehouse.official(key, "statsbomb_open", "Stronger Referee")

    row = warehouse.conn.execute(
        "SELECT home_coach,referee FROM warehouse_matches WHERE match_key=?",
        (key,),
    ).fetchone()
    provenance = {
        item["field_name"]: item["source_key"]
        for item in warehouse.conn.execute(
            """SELECT field_name,source_key FROM warehouse_field_provenance
               WHERE match_key=? AND field_name IN ('home_coach','referee')""",
            (key,),
        )
    }

    assert row["home_coach"] == "Stronger Coach"
    assert row["referee"] == "Stronger Referee"
    assert provenance == {
        "home_coach": "statsbomb_open",
        "referee": "statsbomb_open",
    }
    warehouse.close()


def test_integrity_audit_accepts_canonical_goal_and_card_incidents(tmp_path: Path):
    warehouse = Warehouse(tmp_path / "history.db")
    warehouse.initialize()
    key = warehouse.upsert_match(
        _match("Arsenal", "Chelsea"),
        source_key="statsbomb_open",
        source_match_id="match-1",
    )
    warehouse.event(
        key,
        "statsbomb_open",
        "goal-1",
        "goal",
        team="Arsenal",
        player="Scorer",
        outcome="Goal",
    )
    warehouse.event(
        key,
        "statsbomb_open",
        "card-1",
        "card",
        team="Chelsea",
        player="Booked Player",
        card_type="Yellow Card",
    )

    report = audit_integrity(warehouse)

    assert report["noncanonical_card_events"] == 0
    assert report["noncanonical_goal_outcome_events"] == 0
    assert report["complete"] is True
    warehouse.close()


def test_statsbomb_provider_declared_goals_are_canonical_without_side_resolution():
    shot_goal = {
        "type": {"name": "Shot"},
        "team": {"name": "Unmatched Provider Team"},
        "shot": {"outcome": {"name": "Goal"}},
    }
    own_goal = {
        "type": {"name": "Own Goal Against"},
        "team": {"name": "Unmatched Provider Team"},
    }

    assert canonical_event_type(shot_goal, "Arsenal", "Chelsea") == "goal"
    assert canonical_event_type(own_goal, "Arsenal", "Chelsea") == "goal"


def test_preferred_event_view_uses_strongest_source_per_event_type(tmp_path: Path):
    warehouse = Warehouse(tmp_path / "history.db")
    warehouse.initialize()
    key = warehouse.upsert_match(
        _match("Arsenal", "Chelsea"),
        source_key="soccer_datalake",
        source_match_id="preferred-events",
    )

    warehouse.event(
        key,
        "soccer_datalake",
        "weak-goal",
        "goal",
        team="Arsenal",
        player="Data Lake Scorer",
        minute=20,
        outcome="Goal",
    )
    warehouse.event(
        key,
        "statsbomb_open",
        "strong-goal",
        "goal",
        team="Arsenal",
        player="StatsBomb Scorer",
        minute=20,
        outcome="Goal",
    )
    warehouse.event(
        key,
        "soccer_datalake",
        "only-card",
        "card",
        team="Chelsea",
        player="Booked Player",
        minute=50,
        card_type="Yellow Card",
    )
    warehouse.flush()

    raw = warehouse.conn.execute(
        "SELECT source_key,event_type FROM warehouse_events WHERE match_key=? ORDER BY event_type,source_key",
        (key,),
    ).fetchall()
    preferred = warehouse.conn.execute(
        "SELECT source_key,event_type FROM warehouse_events_preferred WHERE match_key=? ORDER BY event_type,source_key",
        (key,),
    ).fetchall()

    assert [(row["source_key"], row["event_type"]) for row in raw] == [
        ("soccer_datalake", "card"),
        ("soccer_datalake", "goal"),
        ("statsbomb_open", "goal"),
    ]
    assert [(row["source_key"], row["event_type"]) for row in preferred] == [
        ("soccer_datalake", "card"),
        ("statsbomb_open", "goal"),
    ]
    warehouse.close()
