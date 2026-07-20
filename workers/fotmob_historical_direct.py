#!/usr/bin/env python3
"""
FotMob Historical Loader – Direct API (no package)
Fetches all matches per day from 2018-01-01 to today using:
  GET https://www.fotmob.com/api/matches?date=YYYY-MM-DD
Then fetches match details for each match to get scores.
Filters by target league IDs.
Inserts into historical_matches.
"""
import sqlite3
import hashlib
import requests
import time
from datetime import datetime, timedelta

DB_PATH = "athena.db"

# All target league IDs (domestic + UEFA)
TARGET_LEAGUE_IDS = {
    47, 87, 55, 54, 53, 23, 32, 152, 174, 158,
    189, 204, 203, 173, 179, 183, 205, 188, 187, 186,
    42, 44, 848, 561, 556, 573, 577, 578, 574, 559,
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
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

def fetch_matches_by_date(date_str: str):
    """Fetch all matches for a given date from FotMob API."""
    url = f"https://www.fotmob.com/api/matches?date={date_str}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception:
        return None

def fetch_match_details(match_id: int):
    """Fetch full match details including score and teams."""
    url = f"https://www.fotmob.com/api/matchDetails?matchId={match_id}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception:
        return None

def process_date(date_str, conn, fixture_counter):
    """Process all matches for a single date, insert into DB."""
    data = fetch_matches_by_date(date_str)
    if not data:
        return fixture_counter, 0

    # The API response structure: likely contains 'leagues' key, each league has 'matches'
    leagues = data.get('leagues', [])
    inserted = 0
    for league in leagues:
        league_id = league.get('id')
        if league_id not in TARGET_LEAGUE_IDS:
            continue
        league_name = league.get('name', 'Unknown')
        matches = league.get('matches', [])
        for match in matches:
            # Sometimes the match might be a dict with 'id' and other fields
            match_id = match.get('id')
            if not match_id:
                continue
            # We need to fetch details to get the score (the match list doesn't include scores)
            details = fetch_match_details(match_id)
            if not details:
                continue

            # Extract data from details
            home = details.get('homeTeam', {})
            away = details.get('awayTeam', {})
            home_name = home.get('name')
            away_name = away.get('name')
            if not home_name or not away_name:
                continue

            status = details.get('status', {})
            if not status.get('finished', False):
                continue

            score = details.get('score', {})
            home_score = score.get('fulltime', {}).get('home')
            away_score = score.get('fulltime', {}).get('away')
            if home_score is None or away_score is None:
                # fallback
                home_score = score.get('home')
                away_score = score.get('away')
                if home_score is None or away_score is None:
                    continue

            match_date = details.get('date') or match.get('date')
            if not match_date:
                continue

            home_id = get_team_id_global(conn, home_name, league_name)
            away_id = get_team_id_global(conn, away_name, league_name)
            if not home_id or not away_id:
                continue

            fixture_id = match_id if isinstance(match_id, int) else fixture_counter
            fixture_counter += 1

            insert_match(conn, fixture_id, home_id, away_id, home_score, away_score, match_date, league_name)
            inserted += 1

    conn.commit()
    return fixture_counter, inserted

def main():
    start_date = datetime(2018, 1, 1)
    end_date = datetime.today()
    delta = timedelta(days=1)

    conn = sqlite3.connect(DB_PATH)
    create_tables_if_needed(conn)
    fixture_counter = 2000000
    total_inserted = 0

    current = start_date
    while current <= end_date:
        date_str = current.strftime("%Y-%m-%d")
        print(f"Processing {date_str}...", end="", flush=True)
        new_counter, inserted = process_date(date_str, conn, fixture_counter)
        fixture_counter = new_counter
        total_inserted += inserted
        print(f" inserted {inserted} matches (total: {total_inserted})")
        current += delta
        time.sleep(0.1)  # be gentle

    conn.close()
    print(f"\n🎉 TOTAL HISTORICAL MATCHES ADDED: {total_inserted}")

if __name__ == "__main__":
    main()
