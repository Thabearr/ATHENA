from pathlib import Path

from scripts.build_historical_warehouse import Warehouse
from scripts.run_with_fast_history_quality import fast_upsert_match


def international_row(home: str, away: str, home_score: int, away_score: int, result: str):
    return {
        "competition_key": "intl_afcon",
        "competition_name": "Africa Cup of Nations",
        "scope": "international",
        "season": "2024",
        "match_date": "2024-01-22",
        "home_team": home,
        "away_team": away,
        "home_score_ft": home_score,
        "away_score_ft": away_score,
        "home_score_ht": 0 if home_score == 0 else 1,
        "away_score_ht": 1 if away_score else 0,
        "result": result,
        "neutral": 1,
    }


def test_fast_upsert_reconciles_cross_source_international_home_away_flip(tmp_path: Path):
    wh = Warehouse(tmp_path / "history.db")
    wh.initialize()

    datalake = international_row("Equatorial Guinea", "Ivory Coast", 0, 4, "A")
    martj42 = international_row("Ivory Coast", "Equatorial Guinea", 4, 0, "H")

    first_key = fast_upsert_match(
        wh,
        datalake,
        source_key="soccer_datalake",
        source_match_id="datalake-afcon-2024",
    )
    second_key = fast_upsert_match(
        wh,
        martj42,
        source_key="martj42_international",
        source_match_id="martj42-afcon-2024",
    )

    assert second_key == first_key
    row = wh.conn.execute(
        """SELECT home_team,away_team,home_score_ft,away_score_ft,result
           FROM warehouse_matches WHERE match_key=?""",
        (first_key,),
    ).fetchone()
    assert (row["home_team"], row["away_team"]) == ("Equatorial Guinea", "Ivory Coast")
    assert (row["home_score_ft"], row["away_score_ft"], row["result"]) == (0, 4, "A")
    assert wh.conn.execute(
        "SELECT COUNT(*) FROM warehouse_match_sources WHERE match_key=?",
        (first_key,),
    ).fetchone()[0] == 2
    assert wh.conn.execute("SELECT COUNT(*) FROM warehouse_matches").fetchone()[0] == 1
    wh.close()


def test_fast_upsert_keeps_same_source_reverse_records_distinct(tmp_path: Path):
    wh = Warehouse(tmp_path / "history.db")
    wh.initialize()

    first = international_row("Team A", "Team B", 2, 1, "H")
    reverse = international_row("Team B", "Team A", 1, 2, "A")
    first_key = fast_upsert_match(
        wh,
        first,
        source_key="martj42_international",
        source_match_id="same-source-a",
    )
    reverse_key = fast_upsert_match(
        wh,
        reverse,
        source_key="martj42_international",
        source_match_id="same-source-b",
    )

    assert reverse_key != first_key
    assert wh.conn.execute("SELECT COUNT(*) FROM warehouse_matches").fetchone()[0] == 2
    wh.close()


def test_fast_upsert_keeps_cross_source_club_home_away_distinct(tmp_path: Path):
    wh = Warehouse(tmp_path / "history.db")
    wh.initialize()
    first = {
        "competition_key": "eng_premier",
        "competition_name": "Premier League",
        "scope": "club",
        "season": "2025-26",
        "match_date": "2025-08-16",
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "home_score_ft": 2,
        "away_score_ft": 1,
        "result": "H",
    }
    reverse = {
        **first,
        "home_team": "Chelsea",
        "away_team": "Arsenal",
        "home_score_ft": 1,
        "away_score_ft": 2,
        "result": "A",
    }

    first_key = fast_upsert_match(
        wh,
        first,
        source_key="soccer_datalake",
        source_match_id="club-a",
    )
    reverse_key = fast_upsert_match(
        wh,
        reverse,
        source_key="openfootball",
        source_match_id="club-b",
    )

    assert reverse_key != first_key
    assert wh.conn.execute("SELECT COUNT(*) FROM warehouse_matches").fetchone()[0] == 2
    wh.close()
