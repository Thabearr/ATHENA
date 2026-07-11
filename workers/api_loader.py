import logging
from datetime import datetime
from database.database import Database

logger = logging.getLogger("athena.api_loader")

class LiveAPILoader:
    def __init__(self):
        self.db = Database()
        
    def _is_valid_structural_league(self, league_name: str) -> bool:
        blacklist = ["women", "womens", "u19", "u21", "youth", "friendly", "amateur"]
        return not any(b in league_name.lower() for b in blacklist)

    def sync_fixtures_to_db(self, raw_fixtures=None):
        if not raw_fixtures:
            # If no fixtures provided, we can't sync
            logger.warning("Ingestion Worker received empty payload.")
            return

        logger.info(f"Ingesting {len(raw_fixtures)} fixtures...")
        valid_fixtures = []
        valid_odds = []
        
        for item in raw_fixtures:
            # Ensure we are parsing the correct dict keys
            fixture_data = item.get("fixture", {})
            league_name = item.get("league", {}).get("name", "Unknown")
            
            # Simplified structural firewall
            if not self._is_valid_structural_league(league_name):
                continue
                
            fixture_id = fixture_data.get("id")
            # Force status to 'NS' (Not Started) for testing if empty
            status = fixture_data.get("status", {}).get("short", "NS")
            match_date = fixture_data.get("date", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
            
            valid_fixtures.append((
                fixture_id, league_name, 2026, 
                item.get("teams", {}).get("home", {}).get("name", "Team A"),
                item.get("teams", {}).get("away", {}).get("name", "Team B"),
                match_date, status
            ))

        self._bulk_write_to_database(valid_fixtures, valid_odds)

    def _bulk_write_to_database(self, fixtures: list, odds: list):
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.executemany("""
                INSERT OR REPLACE INTO fixtures (fixture_id, league, season, home_team, away_team, match_date, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, fixtures)
            conn.commit()
