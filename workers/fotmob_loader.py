import asyncio
import sqlite3
import re
import logging
from datetime import datetime
from fotmob import FotMob

# Initialize detailed logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("athena.fotmob_loader")

# Zero-Volatility Exclusion Sets
YOUTH_PATTERN = re.compile(r'\b[uU]\d{2}\b')
WOMENS_BLACKLIST = [" W ", "Women", "Womens", "Femenino", "Frauen", " Féminines", "Fem."]

def is_safe_fixture(home_team: str, away_team: str) -> bool:
    """Enforces strict exclusions on women's games and youth matches."""
    for b in WOMENS_BLACKLIST:
        if b.lower() in home_team.lower() or b.lower() in away_team.lower():
            return False
    if YOUTH_PATTERN.search(home_team) or YOUTH_PATTERN.search(away_team):
        return False
    return True

async def run_sync():
    logger.info("Initializing FotMob API interface...")
    async with FotMob() as fotmob:
        try:
            # Retrieve today's matches
            games_data = await fotmob.todays_games()
        except Exception as e:
            logger.error(f"Failed to fetch games from FotMob: {e}")
            return
        
        # Connect to root database
        conn = sqlite3.connect('athena.db')
        cursor = conn.cursor()
        
        # Ensure baseline schema exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fixtures (
                fixture_id INTEGER PRIMARY KEY,
                league TEXT,
                season INTEGER,
                home_team TEXT,
                away_team TEXT,
                match_date TEXT,
                status TEXT
            )
        """)
        
        # Extract matched leagues
        leagues = games_data.get("leagues", []) if isinstance(games_data, dict) else games_data
        fixtures_to_insert = []
        current_year = datetime.now().year
        
        for league in leagues:
            league_name = league.get("name", "Unknown League")
            matches = league.get("matches", [])
            for match in matches:
                fixture_id = match.get("id")
                home_team = match.get("home", {}).get("name", "Unknown Home")
                away_team = match.get("away", {}).get("name", "Unknown Away")
                
                # Format time properties
                match_date = match.get("status", {}).get("utcTime", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
                status = "NS" if not match.get("status", {}).get("started") else "FT"
                
                # Enforce safety blacklists
                if not is_safe_fixture(home_team, away_team):
                    continue
                
                fixtures_to_insert.append((
                    fixture_id,
                    league_name,
                    current_year,
                    home_team,
                    away_team,
                    match_date,
                    status
                ))
        
        if fixtures_to_insert:
            # Insert or replace to keep up-to-date schedule entries clean
            cursor.executemany("""
                INSERT OR REPLACE INTO fixtures (fixture_id, league, season, home_team, away_team, match_date, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, fixtures_to_insert)
            conn.commit()
            logger.info(f"✅ Successfully synchronized {len(fixtures_to_insert)} safe fixtures into athena.db")
        else:
            logger.warning("No valid, safe fixtures detected in today's payload.")
            
        conn.close()

if __name__ == "__main__":
    asyncio.run(run_sync())
