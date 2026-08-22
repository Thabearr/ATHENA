from pathlib import Path

from domain.historical_competitions import resolve_competition
from scripts.build_historical_warehouse import Warehouse, parse_openfootball_text
from scripts.enrich_statsbomb_history import goal_side
from scripts.import_global_football_backbone import classify


def test_international_qualification_not_misclassified():
    assert resolve_competition("FIFA World Cup qualification", "international").key == "intl_world_cup_qual"
    assert resolve_competition("FIFA World Cup", "international").key == "intl_world_cup"


def test_openfootball_parser_reads_ht_and_round():
    text = """= UEFA Champions League 2025/26

▪ League, Matchday 1
  Tue Sep 16 2025
    18:45  Athletic Club (ESP)     v Arsenal FC (ENG)         0-2 (0-0)
           PSV (NED)               v Royale Union Saint-Gilloise (BEL)  1-3 (0-2)
"""
    rows = list(parse_openfootball_text(text, "champions-league-master/2025-26/cl.txt"))
    assert len(rows) == 2
    assert rows[0]["competition_key"] == "uefa_ucl"
    assert rows[0]["match_date"] == "2025-09-16"
    assert rows[0]["home_team"] == "Athletic Club"
    assert rows[0]["away_team"] == "Arsenal FC"
    assert rows[0]["home_score_ht"] == 0
    assert rows[0]["away_score_ft"] == 2
    assert rows[0]["stage"] == "League, Matchday 1"


def test_global_backbone_maps_priority_leagues():
    assert classify({"competition": "Saudi Arabia", "level": "national", "continent": "Asia"}) == ("club", "sau_proleague")
    assert classify({"competition": "USA", "level": "national", "continent": "North America"}) == ("club", "usa_mls")
    assert classify({"competition": "Austria", "level": "national", "continent": "Europe"}) == ("club", "other_euro_topflight")
    assert classify({"competition": "Brazil", "level": "national", "continent": "South America"}) is None


def test_statsbomb_goal_side_handles_own_goal():
    home, away = "Arsenal", "Chelsea"
    normal = {"type": {"name": "Shot"}, "team": {"name": "Arsenal"}, "shot": {"outcome": {"name": "Goal"}}}
    own_goal = {"type": {"name": "Own Goal Against"}, "team": {"name": "Arsenal"}}
    assert goal_side(normal, home, away) == "home"
    assert goal_side(own_goal, home, away) == "away"


def test_stronger_source_wins_conflicting_field(tmp_path: Path):
    db = tmp_path / "history.db"
    wh = Warehouse(db)
    wh.initialize()
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
    key = wh.upsert_match(base, source_key="openfootball", source_match_id="a")
    wh.upsert_match({**base, "home_score_ft": 2, "home_score_ht": 1, "away_score_ht": 0}, source_key="football_data_uk", source_match_id="b")
    row = wh.conn.execute("SELECT home_score_ft,home_score_ht FROM warehouse_matches WHERE match_key=?", (key,)).fetchone()
    assert row["home_score_ft"] == 2
    assert row["home_score_ht"] == 1
    assert wh.conn.execute("SELECT COUNT(*) FROM warehouse_conflicts").fetchone()[0] == 1
    wh.close()


def test_weaker_source_does_not_overwrite_richer_source(tmp_path: Path):
    db = tmp_path / "history.db"
    wh = Warehouse(db)
    wh.initialize()
    base = {
        "competition_key": "intl_world_cup",
        "competition_name": "FIFA Men's World Cup",
        "scope": "international",
        "season": "2022",
        "match_date": "2022-12-18",
        "home_team": "Argentina",
        "away_team": "France",
        "home_score_ft": 2,
        "away_score_ft": 2,
    }
    key = wh.upsert_match(base, source_key="fjelstul_worldcup", source_match_id="M")
    wh.upsert_match({**base, "home_score_ft": 3}, source_key="martj42_international", source_match_id="N")
    row = wh.conn.execute("SELECT home_score_ft FROM warehouse_matches WHERE match_key=?", (key,)).fetchone()
    assert row["home_score_ft"] == 2
    assert wh.conn.execute("SELECT COUNT(*) FROM warehouse_conflicts").fetchone()[0] == 1
    wh.close()
