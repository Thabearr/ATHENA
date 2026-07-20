#!/usr/bin/env python3
"""
FotMob Historical Loader – Async version using asyncio.
Fetches all matches day by day from 2018-01-01 to today.
Filters by target leagues and inserts into historical_matches.
"""
import asyncio
import sqlite3
import hashlib
from datetime import datetime, timedelta
import time
from fotmob import FotMob

DB_PATH = "athena.db"

# All target leagues (domestic + UEFA) – add/remove as needed
TARGET_LEAGUE_IDS = {
    47, 87, 55, 54, 53, 23, 32, 152, 174, 158,
    189, 204, 203, 173, 179, 183, 205, 188, 187, 186,
    42, 44, 848, 561, 556, 573, 577, 578, 574, 559,
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

async def process_date(fotmob, date_str, conn, fixture_counter):
    """Fetch and process matches for a single date."""
    try:
        matches = await fotmob.get_matches_by_date(date_str)
    except Exception as e:
        print(f"  Error fetching {date_str}: {e}")
        return fixture_counter

    if not matches:
        return fixture_counter

    inserted = 0
    for match in matches:
        league_id = match.get('league', {}).get('id')
        if league_id not in TARGET_LEAGUE_IDS:
            continue

        match_id = match.get('id')
        if not match_id:
            continue

        try:
            details = await fotmob.get_match_details(match_id)
        except Exception:
            continue

        if not details:
            continue

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

        league_name = match.get('league', {}).get('name', 'Unknown')

        home_id = get_team_id_global(conn, home_name, league_name)
        away_id = get_team_id_global(conn, away_name, league_name)
        if not home_id or not away_id:
            continue

        # Use FotMob match ID as fixture_id
        fixture_id = int(match_id) if match_id else fixture_counter
        fixture_counter += 1

        insert_match(conn, fixture_id, home_id, away_id, home_score, away_score, match_date, league_name)
        inserted += 1

    conn.commit()
    if inserted:
        print(f"  {date_str}: inserted {inserted} matches.")
    else:
        print(f"  {date_str}: no target matches.")
    return fixture_counter

async def main():
    start_date = datetime(2018, 1, 1)
    end_date = datetime.today()
    delta = timedelta(days=1)

    conn = sqlite3.connect(DB_PATH)
    create_tables_if_needed(conn)
    fotmob = FotMob()
    fixture_counter = 2000000
    total_inserted = 0

    current = start_date
    while current <= end_date:
        date_str = current.strftime("%Y-%m-%d")
        print(f"Processing {date_str}...", end="", flush=True)
        new_counter = await process_date(fotmob, date_str, conn, fixture_counter)
        inserted_this_day = new_counter - fixture_counter
        total_inserted += inserted_this_day
        fixture_counter = new_counter
        # small delay to avoid rate limiting
        await asyncio.sleep(0.1)
        current += delta

    conn.close()
    print(f"\n🎉 TOTAL HISTORICAL MATCHES ADDED: {total_inserted}")

if __name__ == "__main__":
    asyncio.run(main())
