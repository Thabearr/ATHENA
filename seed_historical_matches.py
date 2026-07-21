#!/usr/bin/env python3
"""
ATHENA Ultimate Seeder – Attempts to fetch ALL competitions available in OpenFootball.
Covers domestic leagues, UEFA, CONMEBOL, CAF, AFC, CONCACAF, and even some national team competitions.
"""
import sqlite3
import requests
import hashlib
from typing import Optional, Tuple

DB_PATH = "database/athena.db"

# Comprehensive list of ALL competition codes that exist in openfootball/football.json
# This is based on the repository structure (2023-24/ subfolders)
COMPETITIONS = {
    # Domestic Leagues (Europe)
    "en.1": "Premier League",
    "en.2": "Championship",
    "es.1": "La Liga",
    "it.1": "Serie A",
    "de.1": "Bundesliga",
    "fr.1": "Ligue 1",
    "nl.1": "Eredivisie",
    "pt.1": "Primeira Liga",
    "be.1": "Belgian Pro League",
    "tr.1": "Süper Lig",
    "ch.1": "Swiss Super League",
    "at.1": "Austrian Bundesliga",
    "dk.1": "Danish Superliga",
    "no.1": "Eliteserien",
    "se.1": "Allsvenskan",
    "sco.1": "Scottish Premiership",
    "cz.1": "Czech First League",
    "pl.1": "Ekstraklasa",
    "hr.1": "HNL",
    "rs.1": "SuperLiga",
    "gr.1": "Super League Greece",
    "ru.1": "Russian Premier League",  # added if available
    "ua.1": "Ukrainian Premier League",
    # UEFA Competitions
    "eu.1": "UEFA Champions League",
    "eu.2": "UEFA Europa League",
    "eu.3": "UEFA Conference League",
    # CONMEBOL (if available)
    "cl": "Copa Libertadores",          # Check if exists
    "cs": "Copa Sudamericana",
    # CAF (if available)
    "caf": "CAF Champions League",
    # AFC (if available)
    "afc": "AFC Champions League Elite",
    # CONCACAF (if available)
    "concacaf": "CONCACAF Champions Cup",
    # National Teams (FIFA World Cup, etc.) - may exist under "world" or specific folders
    "world": "FIFA World Cup",
    "euro": "UEFA European Championship",
    "copa": "Copa América",
    "afcon": "Africa Cup of Nations",
    "goldcup": "CONCACAF Gold Cup",
    "asiancup": "AFC Asian Cup",
}

SEASONS = ["2023-24", "2024-25", "2025-26"]
BASE_URL = "https://raw.githubusercontent.com/openfootball/football.json/master"

def create_tables(conn):
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

def extract_score(score_data):
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

def process_competition(conn, league_code: str, league_name: str, fixture_counter: int):
    total = 0
    for season in SEASONS:
        url = f"{BASE_URL}/{season}/{league_code}.json"
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
        except Exception:
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
            home_id = get_team_id_global(conn, home_name, league_name)
            away_id = get_team_id_global(conn, away_name, league_name)
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
            total += 1
        if season_count > 0:
            print(f"    {season}: {season_count} matches")
        conn.commit()
    return fixture_counter, total

def main():
    conn = sqlite3.connect(DB_PATH)
    create_tables(conn)
    fixture_counter = 1
    grand_total = 0

    print("\n===== FETCHING ALL AVAILABLE COMPETITIONS =====")
    for code, name in COMPETITIONS.items():
        print(f"\n--- {name} ({code}) ---")
        fixture_counter, inserted = process_competition(conn, code, name, fixture_counter)
        if inserted == 0:
            print("    No data found (404 or malformed).")
        grand_total += inserted

    conn.close()
    print(f"\nFINAL: {grand_total} total historical matches inserted.")

if __name__ == "__main__":
    main()
