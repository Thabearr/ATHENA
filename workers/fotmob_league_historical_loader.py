#!/usr/bin/env python3
"""
FotMob Historical Loader – League by League (Correct Endpoint)
Fetches all available seasons for each league, then all matches with scores.
Uses: https://www.fotmob.com/api/leagues?id={ID}&season={SEASON}
"""
import sqlite3
import hashlib
import requests
import time
from datetime import datetime

DB_PATH = "database/athena.db"

# All target leagues (domestic + UEFA) – same as before
TARGET_LEAGUES = {
    47: "Premier League",
    87: "La Liga",
    55: "Serie A",
    54: "Bundesliga",
    53: "Ligue 1",
    23: "Eredivisie",
    32: "Primeira Liga",
    152: "Belgian Pro League",
    174: "Süper Lig",
    158: "Swiss Super League",
    189: "Austrian Bundesliga",
    204: "Danish Superliga",
    203: "Eliteserien",
    173: "Allsvenskan",
    179: "Scottish Premiership",
    183: "Czech First League",
    205: "Ekstraklasa",
    188: "HNL",
    187: "SuperLiga",
    186: "Super League Greece",
    42: "UEFA Champions League",
    44: "UEFA Europa League",
    848: "UEFA Conference League",
    561: "FIFA World Cup",
    556: "UEFA EURO",
    573: "Copa América",
    577: "Africa Cup of Nations",
    578: "CONCACAF Gold Cup",
    574: "AFC Asian Cup",
    559: "CONMEBOL World Cup Qualifiers",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

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

def fetch_league_season(league_id: int, season: str):
    """Fetch one league-season from FotMob."""
    url = f"https://www.fotmob.com/api/leagues?id={league_id}&season={season}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception as e:
        print(f"    Error: {e}")
        return None

def get_available_seasons(data: dict) -> list:
    """Extract all season strings from the league response."""
    details = data.get('details', {})
    seasons = details.get('seasons', [])
    # seasons is usually a list of dicts with 'name' (e.g., "2023/2024")
    return [s.get('name') for s in seasons if s.get('name')]

def process_league(conn, league_id: int, league_name: str, fixture_counter: int):
    """Fetch all seasons for a league, then all matches."""
    print(f"\n--- {league_name} (ID: {league_id}) ---")

    # First, fetch the league to get the list of available seasons
    # Use the current/latest season as a probe (e.g., 2023/2024)
    probe_season = "2023/2024"
    data = fetch_league_season(league_id, probe_season)
    if not data:
        print("  No data for probe season.")
        return fixture_counter, 0

    seasons = get_available_seasons(data)
    if not seasons:
        print("  No seasons found.")
        return fixture_counter, 0

    print(f"  Found {len(seasons)} seasons: {', '.join(seasons[:5])}...")

    total_inserted = 0
    for season in seasons:
        print(f"  Fetching {season}...", end="", flush=True)
        data = fetch_league_season(league_id, season)
        if not data:
            print(" No data.")
            continue

        # Extract matches from the correct path
        matches_data = data.get('matches', {})
        all_matches = matches_data.get('allMatches', [])
        if not all_matches:
            print(" No matches.")
            continue

        season_count = 0
        for match in all_matches:
            # Extract teams
            home = match.get('home', {})
            away = match.get('away', {})
            home_name = home.get('name') if isinstance(home, dict) else home
            away_name = away.get('name') if isinstance(away, dict) else away
            if not home_name or not away_name:
                continue

            # Only finished matches
            status = match.get('status', {})
            if not status.get('finished', False):
                continue

            # Score
            score = match.get('score', {})
            home_score = score.get('fulltime', {}).get('home')
            away_score = score.get('fulltime', {}).get('away')
            if home_score is None or away_score is None:
                # fallback
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
            fixture_id = int(fotmob_id) if fotmob_id else fixture_counter
            fixture_counter += 1

            insert_match(conn, fixture_id, home_id, away_id, home_score, away_score, match_date, league_name)
            season_count += 1
            total_inserted += 1

        conn.commit()
        print(f" Inserted {season_count} matches.")
        time.sleep(0.2)  # be gentle

    return fixture_counter, total_inserted

def main():
    conn = sqlite3.connect(DB_PATH)
    create_tables_if_needed(conn)

    fixture_counter = 2000000
    grand_total = 0

    for league_id, league_name in TARGET_LEAGUES.items():
        fixture_counter, inserted = process_league(conn, league_id, league_name, fixture_counter)
        grand_total += inserted

    conn.close()
    print(f"\nTOTAL HISTORICAL MATCHES ADDED: {grand_total}")

if __name__ == "__main__":
    main()
