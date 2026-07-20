#!/usr/bin/env python3
"""
Standalone historical results seeder.
Fetches openfootball JSON data for Premier League seasons and populates:
- teams (with external team_id)
- historical_matches (with fixture_id, home_id, away_id, goals, date)
"""
import sqlite3
import json
import requests
from datetime import datetime
import hashlib

DB_PATH = "athena.db"

SEASONS = [
    ("2023-24", "en.1"),   # Premier League 2023-24
    ("2024-25", "en.1"),   # Premier League 2024-25
    ("2025-26", "en.1"),   # Premier League 2025-26
]

BASE_URL = "https://raw.githubusercontent.com/openfootball/football.json/master"

def create_tables_if_needed(conn):
    """Ensure teams and historical_matches exist (idempotent)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER UNIQUE,
            name TEXT NOT NULL,
            country TEXT,
            league TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS historical_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fixture_id INTEGER UNIQUE,
            home_id INTEGER,
            away_id INTEGER,
            home_goals INTEGER,
            away_goals INTEGER,
            match_date TEXT
        )
    """)
    conn.commit()

def get_team_id(conn, name):
    """Get team_id from teams table by name, or insert if new."""
    cur = conn.execute("SELECT team_id FROM teams WHERE name = ?", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    
    # Insert new team with a pseudo-ID (hash of name)
    pseudo_id = int(hashlib.md5(name.encode()).hexdigest()[:8], 16) % 1000000
    conn.execute(
        "INSERT OR IGNORE INTO teams (team_id, name) VALUES (?, ?)",
        (pseudo_id, name)
    )
    return pseudo_id

def extract_score(score_data):
    """
    Extract home and away goals from score data.
    Handles both formats:
      - {"ft": [2, 1], "ht": [1, 0]}  (dict)
      - [2, 1]                         (list)
    """
    # If it's a list, use it directly
    if isinstance(score_data, list):
        if len(score_data) >= 2:
            return score_data[0], score_data[1]
        return None, None
    
    # If it's a dict, try ft first, then ht
    if isinstance(score_data, dict):
        ft = score_data.get("ft")
        if ft and isinstance(ft, list) and len(ft) >= 2:
            return ft[0], ft[1]
        ht = score_data.get("ht")
        if ht and isinstance(ht, list) and len(ht) >= 2:
            return ht[0], ht[1]
    
    return None, None

def insert_match(conn, fixture_id, home_id, away_id, home_goals, away_goals, match_date):
    """Insert historical match, skip duplicates."""
    conn.execute(
        """
        INSERT OR IGNORE INTO historical_matches 
        (fixture_id, home_id, away_id, home_goals, away_goals, match_date)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (fixture_id, home_id, away_id, home_goals, away_goals, match_date)
    )

def main():
    conn = sqlite3.connect(DB_PATH)
    create_tables_if_needed(conn)

    total_matches = 0
    fixture_counter = 1

    for season, league_code in SEASONS:
        url = f"{BASE_URL}/{season}/{league_code}.json"
        print(f"Fetching {season} from {url}...")
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            print(f"  ❌ Failed to fetch {season}: {e}")
            continue

        data = resp.json()
        matches = data.get("matches", [])
        
        season_matches = 0
        for match in matches:
            home_name = match.get("team1")
            away_name = match.get("team2")
            
            # Extract score using the flexible function
            score_data = match.get("score")
            home_score, away_score = extract_score(score_data)
            
            match_date = match.get("date")

            if not all([home_name, away_name, home_score is not None, away_score is not None, match_date]):
                continue

            # Get or create team IDs
            home_id = get_team_id(conn, home_name)
            away_id = get_team_id(conn, away_name)

            # Generate a unique fixture_id
            fixture_id = fixture_counter
            fixture_counter += 1

            insert_match(conn, fixture_id, home_id, away_id, home_score, away_score, match_date)
            season_matches += 1
            total_matches += 1

        conn.commit()
        print(f"  ✅ Inserted {season_matches} matches for {season}")

    conn.close()
    print(f"\n🎉 Done! Inserted {total_matches} historical matches into the database.")

if __name__ == "__main__":
    main()
