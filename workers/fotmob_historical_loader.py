#!/usr/bin/env python3
"""
FotMob Historical Match Loader (v4 - Direct API, all seasons, all leagues)
Uses requests to fetch match data from FotMob's public API.
Fetches domestic leagues, UEFA competitions, and international tournaments.
Seasons: tries from 2010/2011 to current, but you can adjust the start year.
"""
import sqlite3
import requests
import hashlib
import time
from datetime import datetime

DB_PATH = "athena.db"
FOTMOB_API = "https://www.fotmob.com/api"

# All competitions you listed with their FotMob league IDs
# Domestic leagues (top tiers)
DOMESTIC_LEAGUES = {
    "Premier League": 47,
    "La Liga": 87,
    "Serie A": 55,
    "Bundesliga": 54,
    "Ligue 1": 53,
    "Eredivisie": 23,
    "Primeira Liga": 32,
    "Belgian Pro League": 152,
    "Süper Lig": 174,
    "Swiss Super League": 158,
    "Austrian Bundesliga": 189,
    "Danish Superliga": 204,
    "Eliteserien": 203,
    "Allsvenskan": 173,
    "Scottish Premiership": 179,
    "Czech First League": 183,
    "Ekstraklasa": 205,
    "HNL": 188,
    "SuperLiga": 187,
    "Super League Greece": 186,
}

# UEFA & international competitions
INTERNATIONAL_COMPETITIONS = {
    "UEFA Champions League": 42,
    "UEFA Europa League": 44,
    "UEFA Conference League": 848,
    "FIFA World Cup": 561,
    "UEFA EURO": 556,
    "Copa América": 573,
    "Africa Cup of Nations": 577,
    "CONCACAF Gold Cup": 578,
    "AFC Asian Cup": 574,
    "CONMEBOL World Cup Qualifiers": 559,
}

# Combine all
ALL_COMPETITIONS = {**DOMESTIC_LEAGUES, **INTERNATIONAL_COMPETITIONS}

def create_tables_if_needed(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER UNIQUE,
            name TEXT NOT NULL,
            country TEXT,
            league TEXT
        )
    """)
    try:
        conn.execute("ALTER TABLE teams ADD COLUMN league TEXT")
    except sqlite3.OperationalError:
        pass
    conn.execute("""
        CREATE TABLE IF NOT EXISTS historical_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fixture_id INTEGER UNIQUE,
            home_id INTEGER,
            away_id INTEGER,
            home_goals INTEGER,
            away_goals INTEGER,
            match_date TEXT,
            league TEXT
        )
    """)
    try:
        conn.execute("ALTER TABLE historical_matches ADD COLUMN league TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()

def get_team_id_global(conn, name: str, league_context: str) -> int:
    if not name or name.strip() == "":
        return None
    cur = conn.execute("SELECT team_id FROM teams WHERE name = ?", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    # Create new team with hashed ID
    pseudo_id = int(hashlib.md5(name.encode()).hexdigest()[:8], 16) % 10000000
    conn.execute(
        "INSERT OR IGNORE INTO teams (team_id, name, league) VALUES (?, ?, ?)",
        (pseudo_id, name, league_context)
    )
    return pseudo_id

def insert_match(conn, fixture_id, home_id, away_id, home_goals, away_goals, match_date, league_name):
    conn.execute(
        """
        INSERT OR IGNORE INTO historical_matches 
        (fixture_id, home_id, away_id, home_goals, away_goals, match_date, league)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (fixture_id, home_id, away_id, home_goals, away_goals, match_date, league_name)
    )

def fetch_league_season_matches(league_id: int, season: str):
    """Fetch matches for a given league and season using FotMob API."""
    url = f"{FOTMOB_API}/leagues?id={league_id}&season={season}"
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            return None
        data = resp.json()
        # The response may have 'matches' or 'allMatches'
        matches = data.get('matches') or data.get('allMatches') or []
        return matches
    except Exception:
        return None

def main():
    conn = sqlite3.connect(DB_PATH)
    create_tables_if_needed(conn)

    total_inserted = 0
    fixture_counter = 1000000  # avoid collisions

    # Define season range: from 2010/2011 to 2026/2027 (adjust as needed)
    start_year = 2010
    current_year = 2026
    seasons = [f"{y}/{y+1}" for y in range(start_year, current_year+1)]

    for league_name, league_id in ALL_COMPETITIONS.items():
        print(f"\n--- {league_name} (ID: {league_id}) ---")
        for season in seasons:
            print(f"  Fetching {season}...", end="", flush=True)
            matches = fetch_league_season_matches(league_id, season)
            if not matches:
                print(" No data.")
                continue

            season_count = 0
            for match in matches:
                # Extract team names (could be string or dict)
                home = match.get('home', {})
                away = match.get('away', {})
                home_name = home.get('name') if isinstance(home, dict) else home
                away_name = away.get('name') if isinstance(away, dict) else away
                if not home_name or not away_name:
                    continue

                # Status: only finished matches
                status = match.get('status', {})
                if not status.get('finished', False):
                    continue

                # Score extraction
                score = match.get('score', {})
                home_score = score.get('fulltime', {}).get('home')
                away_score = score.get('fulltime', {}).get('away')
                if home_score is None or away_score is None:
                    # Try alternative structure
                    home_score = score.get('home')
                    away_score = score.get('away')
                    if home_score is None or away_score is None:
                        continue

                match_date = match.get('date')
                if not match_date:
                    continue

                home_id = get_team_id_global(conn, home_name, league_name)
                away_id = get_team_id_global(conn, away_name, league_name)
                if not home_id or not away_id:
                    continue

                # Use FotMob match ID if available
                fotmob_id = match.get('id')
                if fotmob_id:
                    try:
                        fixture_id = int(fotmob_id)
                    except:
                        fixture_id = fixture_counter
                else:
                    fixture_id = fixture_counter
                    fixture_counter += 1

                insert_match(conn, fixture_id, home_id, away_id, home_score, away_score, match_date, league_name)
                season_count += 1
                fixture_counter += 1

            conn.commit()
            if season_count > 0:
                print(f" ✅ Inserted {season_count} matches.")
                total_inserted += season_count
            else:
                print(" No finished matches.")
            time.sleep(0.1)  # be gentle

    conn.close()
    print(f"\n🎉 TOTAL HISTORICAL MATCHES ADDED FROM FOTMOB: {total_inserted}")

if __name__ == "__main__":
    main()
