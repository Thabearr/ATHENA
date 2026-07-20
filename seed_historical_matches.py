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

DB_PATH = "athena.db"

SEASONS = [
    ("2023-24", "en.1"),   # Premier League 2023-24
    ("2024-25", "en.1"),   # Premier League 2024-25
    ("2025-26", "en.1"),   # Premier League 2025-26 (if available)
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

def insert_team(conn, team_id, name):
    """Insert team if not exists, return nothing."""
    conn.execute(
        "INSERT OR IGNORE INTO teams (team_id, name) VALUES (?, ?)",
        (team_id, name)
    )

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
        # teams mapping: key = team name, value = team_id
        teams_data = data.get("teams", [])
        # Build a dict: team name -> team ID (from JSON)
        team_name_to_id = {}
        for t in teams_data:
            t_id = t.get("id")
            t_name = t.get("name")
            if t_id and t_name:
                team_name_to_id[t_name] = t_id
                insert_team(conn, t_id, t_name)

        matches = data.get("matches", [])
        for match in matches:
            home_name = match.get("team1", {}).get("name")
            away_name = match.get("team2", {}).get("name")
            home_score = match.get("score1")
            away_score = match.get("score2")
            match_date = match.get("date")  # format YYYY-MM-DD
            fixture_id = match.get("id")    # unique per match

            if not all([home_name, away_name, home_score is not None, away_score is not None, match_date]):
                continue

            home_id = team_name_to_id.get(home_name)
            away_id = team_name_to_id.get(away_name)
            if not home_id or not away_id:
                continue   # skip if team not found (shouldn't happen)

            insert_match(conn, fixture_id, home_id, away_id, home_score, away_score, match_date)
            total_matches += 1

        conn.commit()
        print(f"  ✅ Inserted matches for {season}")

    conn.close()
    print(f"\n🎉 Done! Inserted {total_matches} historical matches into the database.")

if __name__ == "__main__":
    main()
