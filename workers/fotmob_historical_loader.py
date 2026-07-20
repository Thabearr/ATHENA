#!/usr/bin/env python3
"""
FotMob Historical Match Loader
Fetches completed match results for UEFA competitions, World Cup, EURO, etc.
Inserts into historical_matches table for global ELO normalization.
Uses FotMob's public API (no key required).
"""
import sqlite3
import requests
import hashlib
import time
from datetime import datetime
from typing import Optional, Tuple

DB_PATH = "athena.db"
FOTMOB_BASE = "https://www.fotmob.com/api"

# FotMob league IDs for international club and national team competitions
COMPETITIONS = {
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

SEASONS = ["2023/2024", "2024/2025", "2025/2026"]  # FotMob uses slash format

def create_tables_if_needed(conn):
    """Ensure teams and historical_matches exist."""
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
    """Get team ID by name globally; insert if missing."""
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

def fetch_league_matches(league_id: int, season: str) -> list:
    """Fetch list of matches for a given FotMob league ID and season."""
    url = f"{FOTMOB_BASE}/leagues?id={league_id}&season={season}"
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            return []
        data = resp.json()
        # The response structure: data["matches"] or data["allMatches"] 
        matches = data.get("matches") or data.get("allMatches") or []
        return matches
    except Exception as e:
        print(f"    ⚠️  Error fetching league {league_id} for {season}: {e}")
        return []

def fetch_match_details(match_id: int) -> dict:
    """Fetch detailed match info (score, teams, date) from FotMob."""
    url = f"{FOTMOB_BASE}/matchDetails?matchId={match_id}"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return {}
        return resp.json()
    except Exception:
        return {}

def insert_match_from_fotmob(conn, match_data: dict, league_name: str, fixture_counter: int) -> int:
    """Parse FotMob match data and insert into historical_matches."""
    # Extract teams
    home_team = match_data.get("homeTeam", {}).get("name")
    away_team = match_data.get("awayTeam", {}).get("name")
    if not home_team or not away_team:
        return 0

    # Score
    status = match_data.get("status", {})
    if status.get("finished") != True:
        return 0  # Only finished matches

    # Try to get full-time score
    home_score = None
    away_score = None
    score = match_data.get("score")
    if score:
        ft = score.get("fulltime") or score.get("ft")
        if ft and isinstance(ft, list) and len(ft) >= 2:
            home_score, away_score = ft[0], ft[1]
        else:
            # some formats: dict with home/away
            home_score = score.get("home")
            away_score = score.get("away")
    if home_score is None or away_score is None:
        return 0

    # Date
    match_date = match_data.get("date")
    if not match_date:
        return 0

    # Get or create team IDs
    home_id = get_team_id_global(conn, home_team, league_name)
    away_id = get_team_id_global(conn, away_team, league_name)

    # Generate a unique fixture_id (use FotMob match ID if available)
    fotmob_id = match_data.get("id")
    if fotmob_id:
        fixture_id = int(fotmob_id)  # FotMob IDs are integers
    else:
        fixture_id = fixture_counter

    conn.execute(
        """
        INSERT OR IGNORE INTO historical_matches 
        (fixture_id, home_id, away_id, home_goals, away_goals, match_date, league)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (fixture_id, home_id, away_id, home_score, away_score, match_date, league_name)
    )
    return 1

def main():
    conn = sqlite3.connect(DB_PATH)
    create_tables_if_needed(conn)

    total_inserted = 0
    # We'll keep a counter for fixture_id if FotMob ID not available
    fixture_counter = 1

    for league_name, league_id in COMPETITIONS.items():
        print(f"\n--- {league_name} (ID: {league_id}) ---")
        for season in SEASONS:
            print(f"  Fetching {season}...")
            matches = fetch_league_matches(league_id, season)
            if not matches:
                print(f"    ⚠️  No matches found for {season}.")
                continue

            season_count = 0
            for match in matches:
                match_id = match.get("id")
                if not match_id:
                    continue
                # Fetch full details
                details = fetch_match_details(match_id)
                if not details:
                    continue
                if insert_match_from_fotmob(conn, details, league_name, fixture_counter):
                    season_count += 1
                    fixture_counter += 1
                # Be gentle to FotMob's API
                time.sleep(0.2)

            conn.commit()
            print(f"    ✅ Inserted {season_count} matches for {season}.")
            total_inserted += season_count

    conn.close()
    print(f"\n🎉 TOTAL HISTORICAL MATCHES ADDED FROM FOTMOB: {total_inserted}")

if __name__ == "__main__":
    main()
