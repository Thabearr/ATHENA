"""
FotMob Advanced Scraper - Zero API Key Required
Extracts comprehensive match intelligence from FotMob's public endpoints.
Includes: fixtures, lineups, injuries, form, weather, odds, referee data.
"""

import asyncio
import logging
import json
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
import sqlite3

try:
    from fotmob import FotMob
except ImportError:
    FotMob = None

from database.database import Database

logger = logging.getLogger("athena.fotmob_advanced_scraper")


class FotMobAdvancedScraper:
    """
    Industrial-grade FotMob scraper using public endpoints.
    No authentication required.
    """
    
    def __init__(self):
        self.db = Database()
        self.fotmob = None
        if FotMob:
            # FotMob async client (public endpoints only)
            self.fotmob = FotMob()
        else:
            logger.warning("fotmob package not installed. Install with: pip install fotmob")
    
    def _parse_datetime(self, dt_str: str) -> Optional[datetime]:
        """
        Parse datetime string from FotMob, handling both naive and timezone-aware formats.
        Always returns timezone-aware datetime in UTC.
        """
        if not dt_str:
            return None
        
        try:
            # Try ISO format with timezone
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            # Ensure it's timezone-aware
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            try:
                # Try without timezone
                dt = datetime.fromisoformat(dt_str)
                # Make it timezone-aware (assume UTC)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except (ValueError, TypeError):
                logger.warning(f"Could not parse datetime: {dt_str}")
                return None
    
    async def fetch_upcoming_matches(self, days_ahead: int = 3) -> List[Dict]:
        """
        Fetch all upcoming matches within N days.
        Returns enriched fixture data with lineups, injuries, odds, weather, etc.
        """
        if not self.fotmob:
            logger.error("FotMob client not available")
            return []
        
        try:
            logger.info(f"🔍 Fetching FotMob matches for next {days_ahead} days...")
            
            # Get today's matches
            todays_matches = await self.fotmob.todays_games()
            all_matches = []
            
            if isinstance(todays_matches, dict):
                leagues = todays_matches.get("leagues", [])
            else:
                leagues = todays_matches
            
            # Cutoff: now + N days, in UTC with timezone awareness
            now_utc = datetime.now(timezone.utc)
            cutoff_date = now_utc + timedelta(days=days_ahead)
            
            for league in leagues:
                league_name = league.get("name", "Unknown")
                matches = league.get("matches", [])
                
                for match in matches:
                    try:
                        match_date_str = match.get("status", {}).get("utcTime", "")
                        
                        # Parse match date with proper timezone handling
                        match_date = self._parse_datetime(match_date_str)
                        
                        if not match_date:
                            logger.debug(f"Could not parse date for match {match.get('id')}")
                            continue
                        
                        # Filter by timeframe (NOW UTC-aware comparison)
                        if match_date > cutoff_date:
                            continue  # Beyond our window
                        
                        fixture_id = match.get("id")
                        home_team = match.get("home", {}).get("name")
                        away_team = match.get("away", {}).get("name")
                        
                        if not all([fixture_id, home_team, away_team]):
                            continue
                        
                        # Build enriched fixture object
                        enriched = {
                            "fixture_id": fixture_id,
                            "league": league_name,
                            "home_team": home_team,
                            "away_team": away_team,
                            "match_date": match_date_str,
                            "status": "NS" if not match.get("status", {}).get("started") else "FT",
                            "data_source": "fotmob_advanced",
                            "season_label": datetime.now(timezone.utc).year,
                        }
                        
                        # Fetch deep match data asynchronously
                        match_details = await self._fetch_match_details(fixture_id)
                        enriched.update(match_details)
                        
                        all_matches.append(enriched)
                    
                    except Exception as e:
                        logger.warning(f"Error processing match {match.get('id')}: {e}")
                        continue
            
            logger.info(f"✅ Fetched {len(all_matches)} enriched fixtures from FotMob")
            return all_matches
        
        except Exception as e:
            logger.error(f"FotMob fetch failed: {e}")
            return []
    
    async def _fetch_match_details(self, fixture_id: int) -> Dict:
        """
        Fetch detailed match info: lineups, injuries, odds, weather, referee.
        """
        details = {}
        
        try:
            # Fetch match page (contains lineups, odds, weather, referee)
            match_info = await self.fotmob.get_match(fixture_id)
            
            if not match_info:
                return details
            
            # === LINEUPS ===
            lineups = match_info.get("lineup", {})
            home_lineup = lineups.get("home", {})
            away_lineup = lineups.get("away", {})
            
            details["home_lineup"] = self._extract_lineup(home_lineup)
            details["away_lineup"] = self._extract_lineup(away_lineup)
            
            # === INJURIES ===
            details["home_injuries"] = self._extract_injuries(home_lineup)
            details["away_injuries"] = self._extract_injuries(away_lineup)
            
            # === ODDS ===
            odds = match_info.get("odds", [])
            details["live_odds"] = self._extract_odds(odds)
            
            # === WEATHER ===
            header = match_info.get("header", {})
            weather = header.get("weather", {})
            details["weather"] = {
                "temperature": weather.get("temperature", 0),
                "condition": weather.get("condition", "Unknown"),
                "wind_speed": weather.get("windSpeed", 0),
            }
            
            # === REFEREE ===
            details["referee"] = header.get("referee", "Unknown")
            
            # === HEAD-TO-HEAD ===
            h2h = match_info.get("h2h", {})
            details["head_to_head"] = {
                "home_wins": h2h.get("homeWins", 0),
                "away_wins": h2h.get("awayWins", 0),
                "draws": h2h.get("draws", 0),
            }
            
            # === TEAM FORM ===
            details["home_form"] = self._extract_form(match_info.get("homeRecentForm", []))
            details["away_form"] = self._extract_form(match_info.get("awayRecentForm", []))
            
        except Exception as e:
            logger.warning(f"Could not fetch detailed info for fixture {fixture_id}: {e}")
        
        return details
    
    def _extract_lineup(self, lineup_data: Dict) -> List[Dict]:
        """
        Extract starting XI + bench from lineup data.
        """
        players = []
        
        if not isinstance(lineup_data, dict):
            return players
        
        # Starting XI
        starting = lineup_data.get("players", [])
        for player in starting:
            if isinstance(player, dict):
                players.append({
                    "name": player.get("name", ""),
                    "number": player.get("number"),
                    "position": player.get("position", ""),
                    "status": "starting"
                })
        
        # Bench
        bench = lineup_data.get("bench", [])
        for player in bench:
            if isinstance(player, dict):
                players.append({
                    "name": player.get("name", ""),
                    "number": player.get("number"),
                    "position": player.get("position", ""),
                    "status": "bench"
                })
        
        return players
    
    def _extract_injuries(self, lineup_data: Dict) -> List[Dict]:
        """
        Extract injury status for unavailable players.
        """
        injuries = []
        
        if not isinstance(lineup_data, dict):
            return injuries
        
        # Check for injury data in the lineup object
        unavailable = lineup_data.get("unavailable", [])
        for player in unavailable:
            if isinstance(player, dict):
                injuries.append({
                    "name": player.get("name", ""),
                    "reason": player.get("injuryReason", "Unknown"),
                    "return_date": player.get("returnDate"),
                })
        
        return injuries
    
    def _extract_odds(self, odds_data: List) -> Dict:
        """
        Extract bookmaker odds (multiple markets).
        """
        odds_dict = {}
        
        for bookmaker in odds_data:
            if not isinstance(bookmaker, dict):
                continue
            
            bm_name = bookmaker.get("bookmaker", "Unknown")
            markets = bookmaker.get("markets", [])
            
            odds_dict[bm_name] = {}
            
            for market in markets:
                if not isinstance(market, dict):
                    continue
                
                market_name = market.get("name", "Unknown")
                odds_dict[bm_name][market_name] = market.get("odds", [])
        
        return odds_dict
    
    def _extract_form(self, form_data: List) -> Dict:
        """
        Extract recent form (last 5 matches).
        """
        if not form_data:
            return {"matches": [], "summary": ""}
        
        recent = []
        for match in form_data[:5]:  # Last 5
            if isinstance(match, dict):
                recent.append({
                    "result": match.get("result", ""),
                    "opponent": match.get("opponent", ""),
                    "date": match.get("date", ""),
                })
        
        return {"matches": recent, "summary": "".join([m.get("result", "") for m in recent])}
    
    def sync_to_db(self, matches: List[Dict]) -> bool:
        """
        Persist enriched fixtures to database.
        Stores main fixture data + extended metadata.
        """
        if not matches:
            logger.warning("No matches to sync")
            return False
        
        try:
            with self.db.connect() as conn:
                cursor = conn.cursor()
                
                # Ensure extended tables exist
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS fixture_extended (
                        fixture_id INTEGER PRIMARY KEY,
                        home_lineup TEXT,
                        away_lineup TEXT,
                        home_injuries TEXT,
                        away_injuries TEXT,
                        live_odds TEXT,
                        weather TEXT,
                        referee TEXT,
                        head_to_head TEXT,
                        home_form TEXT,
                        away_form TEXT,
                        synced_at TEXT
                    )
                """)
                
                for match in matches:
                    fixture_id = match.get("fixture_id")
                    
                    # Main fixtures table
                    cursor.execute("""
                        INSERT INTO fixtures
                            (fixture_id, league, season, home_team, away_team,
                             match_date, status, data_source, season_label)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(fixture_id) DO UPDATE SET
                            league=excluded.league,
                            status=excluded.status,
                            match_date=excluded.match_date
                    """, (
                        fixture_id, match.get("league"), match.get("season_label"),
                        match.get("home_team"), match.get("away_team"),
                        match.get("match_date"), match.get("status"),
                        match.get("data_source"), match.get("season_label")
                    ))
                    
                    # Extended metadata
                    cursor.execute("""
                        INSERT INTO fixture_extended
                            (fixture_id, home_lineup, away_lineup, home_injuries,
                             away_injuries, live_odds, weather, referee,
                             head_to_head, home_form, away_form, synced_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(fixture_id) DO UPDATE SET
                            home_lineup=excluded.home_lineup,
                            away_lineup=excluded.away_lineup,
                            home_injuries=excluded.home_injuries,
                            away_injuries=excluded.away_injuries,
                            live_odds=excluded.live_odds,
                            weather=excluded.weather,
                            referee=excluded.referee,
                            synced_at=excluded.synced_at
                    """, (
                        fixture_id,
                        json.dumps(match.get("home_lineup", [])),
                        json.dumps(match.get("away_lineup", [])),
                        json.dumps(match.get("home_injuries", [])),
                        json.dumps(match.get("away_injuries", [])),
                        json.dumps(match.get("live_odds", {})),
                        json.dumps(match.get("weather", {})),
                        match.get("referee", "Unknown"),
                        json.dumps(match.get("head_to_head", {})),
                        json.dumps(match.get("home_form", {})),
                        json.dumps(match.get("away_form", {})),
                        datetime.now(timezone.utc).isoformat()
                    ))
                
                conn.commit()
                logger.info(f"✅ Synced {len(matches)} enriched fixtures to DB")
                return True
        
        except Exception as e:
            logger.error(f"Failed to sync fixtures: {e}")
            return False


async def main():
    """CLI: Fetch and sync FotMob data."""
    scraper = FotMobAdvancedScraper()
    
    # Fetch next 3 days
    matches = await scraper.fetch_upcoming_matches(days_ahead=3)
    
    if matches:
        scraper.sync_to_db(matches)
        print(f"✅ Synced {len(matches)} FotMob fixtures with full enrichment")
        
        # Display sample
        for match in matches[:3]:
            print(f"\n🎯 {match['home_team']} vs {match['away_team']}")
            print(f"   Home injuries: {len(match.get('home_injuries', []))} players")
            print(f"   Away injuries: {len(match.get('away_injuries', []))} players")
            print(f"   Weather: {match.get('weather', {}).get('condition', '?')}")
            print(f"   Referee: {match.get('referee', 'Unknown')}")
    else:
        print("❌ No matches fetched from FotMob")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
