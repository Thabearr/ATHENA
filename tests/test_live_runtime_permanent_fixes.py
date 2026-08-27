import json
import sqlite3
from database.database import Database
from intelligence.accumulator import AccumulatorEngine
from intelligence.match_analyst import score_current_form_snapshot
from workers.fotmob_advanced_scraper import FotMobAdvancedScraper


def test_current_fotmob_form_is_scored_without_default():
    value = {"matches": [{"result": x} for x in "LWWWW"], "summary": "LWWWW"}
    assert score_current_form_snapshot(value) == 0.78
    assert score_current_form_snapshot({"matches": [{"result": "W"}]}) is None


def test_accumulator_null_edge_fails_closed_instead_of_crashing():
    engine = AccumulatorEngine(min_edge=0.05)
    fixture = {"verdict": "DC_1X", "edge": None, "risk_score": 50, "upset_alert": False}
    assert isinstance(engine._score_fixture(fixture), float)
    assert engine._is_acca_eligible(fixture) is False


def test_fixture_source_ids_migrate_and_sync(tmp_path):
    db_path = tmp_path / "athena.db"
    db = Database(str(db_path))
    db.initialize()
    scraper = FotMobAdvancedScraper()
    scraper.db = db
    assert scraper.sync_to_db([{
        "fixture_id": 123456,
        "league": "Test League",
        "season_label": "2026",
        "home_team": "Home",
        "away_team": "Away",
        "home_id": 111,
        "away_id": 222,
        "match_date": "2026-08-27T18:00:00+00:00",
        "status": "NS",
        "data_source": "fotmob_bypass",
        "home_form": {"matches": [{"result": x} for x in "WWWDL"], "summary": "WWWDL"},
        "away_form": {"matches": [{"result": x} for x in "LLDWW"], "summary": "LLDWW"},
        "current_form_observed_at": "2026-08-27T02:16:00+00:00",
        "home_lineup": [],
    }]) is True
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT home_source_id, away_source_id FROM fixtures WHERE fixture_id=123456"
        ).fetchone() == (111, 222)
        ext = conn.execute(
            "SELECT home_form, away_form, synced_at FROM fixture_extended WHERE fixture_id=123456"
        ).fetchone()
        assert json.loads(ext[0])["summary"] == "WWWDL"
        assert json.loads(ext[1])["summary"] == "LLDWW"
        assert ext[2] == "2026-08-27T02:16:00+00:00"
