import logging
from datetime import datetime
from database.database import Database

logger = logging.getLogger("athena.api_loader")

class LiveAPILoader:
    def __init__(self):
        self.db = Database()
        
    def _is_valid_structural_league(self, league_name: str, league_id: int = 0) -> bool:
        """
        The absolute network firewall. 
        Permanently drops highly volatile environments, youth leagues, and women's 
        sports before they ever consume database storage or CPU cycles.
        """
        blacklist = [
            "women", "womens", "femenino", "frauen", "feminin", 
            "u19", "u21", "youth", "friendly", "amateur"
        ]
        name_lower = league_name.lower()
        if any(b in name_lower for b in blacklist):
            return False
        return True

    def sync_fixtures_to_db(self, raw_fixtures=None):
        """
        Ingests fixtures using bulk transactions to prevent terminal lag.
        """
        if not raw_fixtures:
            logger.info("No live fixtures available for sync.")
            return

        valid_fixtures = []
        valid_odds = []
        
        for item in raw_fixtures:
            fixture_data = item.get("fixture", item)
            league_data = item.get("league", item)
            teams_data = item.get("teams", item)
            odds_data = item.get("odds_mock", {})
            
            league_name = league_data.get("name", "Unknown League")
            league_id = league_data.get("id", 0)
            
            # Apply strict league firewall
            if not self._is_valid_structural_league(league_name, league_id):
                continue
                
            fixture_id = fixture_data.get("id")
            season = league_data.get("season", datetime.utcnow().year)
            status = fixture_data.get("status", {}).get("short", "NS")
            match_date = fixture_data.get("date", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
            
            home_team = teams_data.get("home", {}).get("name")
            away_team = teams_data.get("away", {}).get("name")

            # Structure for fixtures table
            valid_fixtures.append((
                fixture_id, league_name, season, home_team, away_team, match_date, status
            ))

            # Structure for normalized odds table
            market_odds = [
                (fixture_id, "Home Win", odds_data.get("home", 1.44)),
                (fixture_id, "Draw", odds_data.get("draw", 4.73)),
                (fixture_id, "Away Win", odds_data.get("away", 3.58)),
                (fixture_id, "DNB Home", odds_data.get("dnb_home", 1.14)),
                (fixture_id, "DNB Away", odds_data.get("dnb_away", 5.90)),
                (fixture_id, "DC Home", odds_data.get("dc_home", 1.10)),
                (fixture_id, "DC Away", odds_data.get("dc_away", 2.65)),
                (fixture_id, "Over 1.5", odds_data.get("over_15", 1.37)),
                (fixture_id, "Under 3.5", odds_data.get("under_35", 1.29))
            ]
            valid_odds.extend(market_odds)

        # Execute ultra-fast bulk transaction
        self._bulk_write_to_database(valid_fixtures, valid_odds)
        print(f"✅ Ingestion Sync Cycle Complete: Captured {len(valid_fixtures)} tier-1 fixtures.")

    def _bulk_write_to_database(self, fixtures: list, odds: list):
        with self.db.connect() as conn:
            cursor = conn.cursor()
            
            # Bulk Insert Fixtures
            cursor.executemany("""
                INSERT OR REPLACE INTO fixtures (
                    fixture_id, league, season, home_team, away_team, match_date, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, fixtures)
            
            # Bulk Insert Odds
            cursor.executemany("""
                INSERT OR REPLACE INTO odds (
                    fixture_id, market, price
                ) VALUES (?, ?, ?)
            """, odds)
            
            conn.commit()
