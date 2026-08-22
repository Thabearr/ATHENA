from pathlib import Path

from scripts.audit_historical_data_integrity import audit_integrity
from scripts.build_historical_warehouse import Warehouse


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


def test_integrity_audit_detects_reversed_preexisting_fixture_duplicates(tmp_path: Path):
    warehouse = Warehouse(tmp_path / "history.db")
    warehouse.initialize()
    warehouse.conn.execute(
        """INSERT INTO warehouse_matches(
           match_key,competition_key,competition_name,scope,season,match_date,
           home_team,away_team,home_score_ft,away_score_ft
        ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (
            "legacy-a",
            "eng_premier",
            "Premier League",
            "club",
            "2025-26",
            "2025-08-30",
            "AFC Bournemouth",
            "Fulham FC",
            2,
            1,
        ),
    )
    warehouse.conn.execute(
        """INSERT INTO warehouse_matches(
           match_key,competition_key,competition_name,scope,season,match_date,
           home_team,away_team,home_score_ft,away_score_ft
        ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (
            "legacy-b",
            "eng_premier",
            "Premier League",
            "club",
            "2025-26",
            "2025-08-30",
            "FC Fulham",
            "Bournemouth AFC",
            1,
            2,
        ),
    )

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
