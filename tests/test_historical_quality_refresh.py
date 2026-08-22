from pathlib import Path

from scripts.build_historical_warehouse import Warehouse
from scripts.historical_quality import refresh_quality_set_based
from scripts.run_with_fast_history_quality import fast_upsert_match


def _match(name: str, *, ft=True, ht=False, referee=None, home_coach=None, away_coach=None):
    row = {
        "competition_key": "eng_premier",
        "competition_name": "Premier League",
        "scope": "club",
        "season": "2025-26",
        "match_date": f"2025-09-0{name}",
        "home_team": f"Home {name}",
        "away_team": f"Away {name}",
        "referee": referee,
        "home_coach": home_coach,
        "away_coach": away_coach,
    }
    if ft:
        row.update(home_score_ft=1, away_score_ft=0)
    if ht:
        row.update(home_score_ht=1, away_score_ht=0)
    return row


def test_set_based_quality_refresh_matches_existing_quality_rules(tmp_path: Path):
    warehouse = Warehouse(tmp_path / "history.db")
    warehouse.initialize()

    partial = warehouse.upsert_match(
        _match("1", ft=False),
        source_key="openfootball",
        source_match_id="partial",
    )
    basic = warehouse.upsert_match(
        _match("2"),
        source_key="openfootball",
        source_match_id="basic",
    )
    standard_ht = warehouse.upsert_match(
        _match("3", ht=True),
        source_key="openfootball",
        source_match_id="standard-ht",
    )
    standard_event = warehouse.upsert_match(
        _match("4"),
        source_key="openfootball",
        source_match_id="standard-event",
    )
    rich = warehouse.upsert_match(
        _match(
            "5",
            ht=True,
            referee="Referee",
            home_coach="Home Coach",
            away_coach="Away Coach",
        ),
        source_key="openfootball",
        source_match_id="rich",
    )
    warehouse.event(standard_event, "openfootball", "e-standard", "goal", team="Home 4")
    warehouse.event(rich, "openfootball", "e-rich", "goal", team="Home 5")

    refresh_quality_set_based(warehouse)

    rows = dict(
        warehouse.conn.execute(
            "SELECT match_key,data_quality FROM warehouse_matches"
        ).fetchall()
    )
    assert rows[partial] == "PARTIAL"
    assert rows[basic] == "BASIC"
    assert rows[standard_ht] == "STANDARD"
    assert rows[standard_event] == "STANDARD"
    assert rows[rich] == "RICH"
    warehouse.close()


def test_fast_upsert_preserves_source_priority_and_conflicts(tmp_path: Path):
    warehouse = Warehouse(tmp_path / "history.db")
    warehouse.initialize()
    base = {
        "competition_key": "eng_premier",
        "competition_name": "Premier League",
        "scope": "club",
        "season": "2025-26",
        "match_date": "2025-08-16",
        "home_team": "Example FC",
        "away_team": "Other FC",
        "home_score_ft": 1,
        "away_score_ft": 0,
    }

    key = fast_upsert_match(
        warehouse,
        base,
        source_key="openfootball",
        source_match_id="weak",
    )
    stronger = fast_upsert_match(
        warehouse,
        {
            **base,
            "home_score_ft": 2,
            "home_score_ht": 1,
            "away_score_ht": 0,
            "referee": "Strong Ref",
        },
        source_key="football_data_uk",
        source_match_id="strong",
    )
    weaker_again = fast_upsert_match(
        warehouse,
        {**base, "home_score_ft": 9, "referee": "Weak Ref"},
        source_key="openfootball",
        source_match_id="weak-later",
    )
    warehouse.flush()

    assert key == stronger == weaker_again
    row = warehouse.conn.execute(
        """SELECT home_score_ft,away_score_ft,home_score_ht,away_score_ht,referee
           FROM warehouse_matches WHERE match_key=?""",
        (key,),
    ).fetchone()
    assert tuple(row) == (2, 0, 1, 0, "Strong Ref")

    provenance = {
        item["field_name"]: item["source_key"]
        for item in warehouse.conn.execute(
            """SELECT field_name,source_key FROM warehouse_field_provenance
               WHERE match_key=? AND field_name IN ('home_score_ft','home_score_ht','referee')""",
            (key,),
        )
    }
    assert provenance == {
        "home_score_ft": "football_data_uk",
        "home_score_ht": "football_data_uk",
        "referee": "football_data_uk",
    }
    assert warehouse.conn.execute(
        "SELECT COUNT(*) FROM warehouse_conflicts WHERE match_key=?",
        (key,),
    ).fetchone()[0] >= 2
    assert warehouse.conn.execute(
        "SELECT COUNT(*) FROM warehouse_match_sources WHERE match_key=?",
        (key,),
    ).fetchone()[0] == 3
    warehouse.close()


def test_source_match_identity_lookup_is_indexed(tmp_path: Path):
    warehouse = Warehouse(tmp_path / "history.db")
    warehouse.initialize()

    indexes = {
        row["name"]
        for row in warehouse.conn.execute("PRAGMA index_list('warehouse_match_sources')")
    }
    assert "idx_wh_sources_source_id" in indexes

    plan = " ".join(
        str(part)
        for row in warehouse.conn.execute(
            """EXPLAIN QUERY PLAN
               SELECT match_key FROM warehouse_match_sources
               WHERE source_key=? AND source_match_id=? LIMIT 1""",
            ("martj42_international", "example-source-id"),
        )
        for part in row
    )
    assert "idx_wh_sources_source_id" in plan
    warehouse.close()
