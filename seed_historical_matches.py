#!/usr/bin/env python3
"""
ATHENA Multi-League Historical Seeder (Phase 1+2)
Fetches openfootball JSON for 20 domestic leagues and 3 seasons.
Seeds teams, historical_matches, and populates the 'league' column.
"""
import sqlite3
import requests
import hashlib
from typing import Optional, Tuple

DB_PATH = "athena.db"

# All 20 leagues from your priority list with their openfootball codes
LEAGUES = [
    ("Premier League", "en.1"),         # 1 Elite
    ("La Liga", "es.1"),               # 2 Elite
    ("Serie A", "it.1"),               # 3 Elite
    ("Bundesliga", "de.1"),            # 4 Elite
    ("Ligue 1", "fr.1"),               # 5 Elite
    ("Eredivisie", "nl.1"),            # 6 High
    ("Primeira Liga", "pt.1"),         # 7 High
    ("Belgian Pro League", "be.1"),    # 8 High
    ("Süper Lig", "tr.1"),             # 9 High
    ("Swiss Super League", "ch.1"),    # 10 High
    ("Austrian Bundesliga", "at.1"),   # 11 Medium-High
    ("Danish Superliga", "dk.1"),      # 12 Medium-High
    ("Eliteserien", "no.1"),           # 13 Medium
    ("Allsvenskan", "se.1"),           # 14 Medium
    ("Scottish Premiership", "sco.1"), # 15 Medium
    ("Czech First League", "cz.1"),    # 16 Medium
    ("Ekstraklasa", "pl.1"),           # 17 Medium
    ("HNL", "hr.1"),                   # 18 Medium
    ("SuperLiga", "rs.1"),             # 19 Medium
    ("Super League Greece", "gr.1"),   # 20 Medium
]

SEASONS = ["2023-24", "2024-25", "2025-26"]
BASE_URL = "https://raw.githubusercontent.com/openfootball/football.json/master"

def create_tables(conn):
    """Ensure teams and historical_matches exist, add league column if missing."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER UNIQUE,
            name TEXT NOT NULL,
            country TEXT,
            league TEXT
        )
    """)
    # Add league column if it doesn't exist (idempotent)
    try:
        conn.execute("ALTER TABLE teams ADD COLUMN league TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists
    
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
    # Add league column to historical_matches if missing
    try:
        conn.execute("ALTER TABLE historical_matches ADD COLUMN league TEXT")
    except sqlite3.OperationalError:
        pass
    
    conn.commit()

def get_team_id(conn, name: str, league_name: str) -> int:
    """Get or create team ID. Uses hash of name+league to avoid collisions."""
    # Ensure unique IDs across leagues (e.g., "Real Madrid" exists in La Liga and UCL)
    unique_key = f"{name}_{league_name}"
    pseudo_id = int(hashlib.md5(unique_key.encode()).hexdigest()[:8], 16) % 10000000
    
    # Check if exists
    cur = conn.execute("SELECT team_id FROM teams WHERE name = ? AND league = ?", (name, league_name))
    row = cur.fetchone()
    if row:
        return row[0]
    
    # Insert
    conn.execute(
        "INSERT OR IGNORE INTO teams (team_id, name, league) VALUES (?, ?, ?)",
        (pseudo_id, name, league_name)
    )
    return pseudo_id

def extract_score(score_data) -> Tuple[Optional[int], Optional[int]]:
    if isinstance(score_data, list):
        if len(score_data) >= 2:
            return score_data[0], score_data[1]
        return None, None
    if isinstance(score_data, dict):
        ft = score_data.get("ft")
        if ft and isinstance(ft, list) and len(ft) >= 2:
            return ft[0], ft[1]
        ht = score_data.get("ht")
        if ht and isinstance(ht, list) and len(ht) >= 2:
            return ht[0], ht[1]
    return None, None

def main():
    conn = sqlite3.connect(DB_PATH)
    create_tables(conn)
    total_matches = 0
    fixture_counter = 1

    for league_name, league_code in LEAGUES:
        print(f"\n=== Processing {league_name} ({league_code}) ===")
        
        for season in SEASONS:
            url = f"{BASE_URL}/{season}/{league_code}.json"
            print(f"  Fetching {season}...")
            
            try:
                resp = requests.get(url, timeout=30)
                if resp.status_code == 404:
                    print(f"    ⚠️  {season} not found for {league_code}, skipping.")
                    continue
                resp.raise_for_status()
            except Exception as e:
                print(f"    ❌ Error: {e}")
                continue

            data = resp.json()
            matches = data.get("matches", [])
            season_count = 0

            for match in matches:
                home_name = match.get("team1")
                away_name = match.get("team2")
                if not home_name or not away_name:
                    continue
                
                home_score, away_score = extract_score(match.get("score"))
                match_date = match.get("date")
                
                if None in (home_score, away_score, match_date):
                    continue

                home_id = get_team_id(conn, home_name, league_name)
                away_id = get_team_id(conn, away_name, league_name)

                conn.execute(
                    """
                    INSERT OR IGNORE INTO historical_matches 
                    (fixture_id, home_id, away_id, home_goals, away_goals, match_date, league)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (fixture_counter, home_id, away_id, home_score, away_score, match_date, league_name)
                )
                fixture_counter += 1
                season_count += 1
                total_matches += 1

            conn.commit()
            print(f"    ✅ Inserted {season_count} matches.")
    
    conn.close()
    print(f"\n🎉 GRAND TOTAL: {total_matches} historical matches inserted across {len(LEAGUES)} leagues!")

if __name__ == "__main__":
    main()
