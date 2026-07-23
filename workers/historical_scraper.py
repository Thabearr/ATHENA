import sqlite3
import datetime
import logging
from loguru import logger
from typing import List, Dict, Any

from workers.fotmob_bypass_client import FotmobBypassClient

class HistoricalScraper:
    """Fetches past matches and their actual scores for the backtesting engine."""
    
    def __init__(self, db_path="database/athena.db"):
        self.db_path = db_path
        self.client = FotmobBypassClient()
        
    def _parse_datetime(self, time_str: str) -> datetime.datetime:
        """Parse FotMob UTC time string."""
        if not time_str:
            return None
        try:
            time_str = time_str.replace("Z", "+00:00")
            return datetime.datetime.fromisoformat(time_str)
        except Exception:
            return None

    def scrape_historical(self, days_ago: int) -> List[Dict]:
        """Scrape matches that happened `days_ago`."""
        target_date = datetime.datetime.now() - datetime.timedelta(days=days_ago)
        date_str = target_date.strftime("%Y%m%d")
        
        logger.info(f"Fetching historical matches for {target_date.date()} (FotMob format {date_str})")
        data = self.client.fetch_matches_by_date(date_str)
        
        if not data:
            logger.error("Failed to fetch historical data from FotMob")
            return []
            
        leagues = data.get("leagues", [])
        extracted = []
        
        for league in leagues:
            league_name = league.get("name", "Unknown")
            matches = league.get("matches", [])
            
            for match in matches:
                try:
                    fixture_id = match.get("id")
                    home = match.get("home", {})
                    away = match.get("away", {})
                    home_team = home.get("longName") or home.get("name", "Unknown")
                    away_team = away.get("longName") or away.get("name", "Unknown")
                    
                    status_info = match.get("status", {})
                    if not status_info.get("finished", False):
                        continue # Skip if not finished
                        
                    # Extract score
                    score_str = status_info.get("scoreStr")
                    if not score_str or " - " not in score_str:
                        continue
                        
                    parts = score_str.split(" - ")
                    try:
                        home_score = int(parts[0].strip())
                        away_score = int(parts[1].strip())
                    except ValueError:
                        continue
                        
                    match_date_str = status_info.get("utcTime", "")
                    match_date = self._parse_datetime(match_date_str)
                    if not match_date:
                        continue
                        
                    extracted.append({
                        "fixture_id": fixture_id,
                        "league": league_name,
                        "league_id": league.get("id"),
                        "home_team": home_team,
                        "away_team": away_team,
                        "match_date": match_date_str,
                        "status": "FT",
                        "data_source": "fotmob_historical",
                        "season_label": str(target_date.year),
                        "home_score": home_score,
                        "away_score": away_score
                    })
                except Exception as e:
                    logger.warning(f"Error parsing historical match {match.get('id')}: {e}")
                    
        return extracted
        
    def save_to_db(self, fixtures: List[Dict]):
        if not fixtures:
            return
            
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for f in fixtures:
            # 1. Insert/Update Fixture
            cursor.execute("""
                INSERT INTO fixtures 
                (fixture_id, league, home_team, away_team, match_date, status, data_source, season_label)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fixture_id) DO UPDATE SET
                    status=excluded.status,
                    match_date=excluded.match_date
            """, (
                f['fixture_id'], f['league'], f['home_team'], f['away_team'],
                f['match_date'], f['status'], f['data_source'], f['season_label']
            ))
            
            # 2. Check if Result exists
            cursor.execute("SELECT id FROM results WHERE fixture_id = ?", (f['fixture_id'],))
            res = cursor.fetchone()
            if not res:
                cursor.execute("""
                    INSERT INTO results (fixture_id, home_score, away_score, finished)
                    VALUES (?, ?, ?, 1)
                """, (f['fixture_id'], f['home_score'], f['away_score']))
            else:
                cursor.execute("""
                    UPDATE results SET home_score=?, away_score=?, finished=1 WHERE fixture_id=?
                """, (f['home_score'], f['away_score'], f['fixture_id']))
            
        conn.commit()
        conn.close()
        logger.info(f"Saved {len(fixtures)} historical fixtures & results to DB")

if __name__ == "__main__":
    scraper = HistoricalScraper()
    # Fetch past 7 days of results
    for i in range(1, 8):
        results = scraper.scrape_historical(i)
        scraper.save_to_db(results)
