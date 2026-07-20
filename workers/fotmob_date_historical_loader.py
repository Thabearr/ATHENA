#!/usr/bin/env python3
"""
FotMob Historical Loader via Daily Match Scraping
Uses fotmob.get_matches_by_date() to fetch all matches for each day since 2018.
Filters by target leagues and inserts into historical_matches.
"""
import sqlite3
import hashlib
from fotmob import FotMob
from datetime import datetime, timedelta
import time

DB_PATH = "athena.db"

# All target leagues (domestic + UEFA) – we need their FotMob league IDs
TARGET_LEAGUE_IDS = {
    47,  # Premier League
    87,  # La Liga
    55,  # Serie A
    54,  # Bundesliga
    53,  # Ligue 1
    23,  # Eredivisie
    32,  # Primeira Liga
    152, # Belgian Pro League
    174, # Süper Lig
    158, # Swiss Super League
    189, # Austrian Bundesliga
    204, # Danish Superliga
    203, # Eliteserien
    173, # Allsvenskan
    179, # Scottish Premiership
    183, # Czech First League
    205, # Ekstraklasa
    188, # HNL
    187, # SuperLiga
    186, # Super League Greece
    42,  # UEFA Champions League
    44,  # UEFA Europa League
    848, # UEFA Conference League
    561, # FIFA World Cup
    556, # UEFA EURO
    573, # Copa América
    577, # Africa Cup of Nations
    578, # CONCACAF Gold Cup
    574, # AFC Asian Cup
    559, # CONMEBOL World Cup Qualifiers
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

def main():
    conn = sqlite3.connect(DB_PATH)
    create_tables_if_needed(conn)
    fotmob = FotMob()

    start_date = datetime(2018, 1, 1)
    end_date = datetime.today()
    delta = timedelta(days=1)

    total_inserted = 0
    fixture_counter = 2000000  # avoid collisions

    current = start_date
    while current <= end_date:
        date_str = current.strftime("%Y-%m-%d")
        print(f"Fetching matches for {date_str}...", end="", flush=True)
        try:
            matches = fotmob.get_matches_by_date(date_str)
            if not matches:
                print(" No matches.")
                current += delta
                continue

            # matches is a list of match dicts, each has 'league' with 'id'
            for match in matches:
                league_id = match.get('league', {}).get('id')
                if league_id not in TARGET_LEAGUE_IDS:
                    continue

                # Get match details for score
                match_id = match.get('id')
                if not match_id:
                    continue

                details = fotmob.get_match_details(match_id)
                if not details:
                    continue

                # Extract teams
                home = details.get('homeTeam', {})
                away = details.get('awayTeam', {})
                home_name = home.get('name')
                away_name = away.get('name')
                if not home_name or not away_name:
                    continue

                # Score
                status = details.get('status', {})
                if not status.get('finished', False):
                    continue
                score = details.get('score', {})
                home_score = score.get('fulltime', {}).get('home')
                away_score = score.get('fulltime', {}).get('away')
                if home_score is None or away_score is None:
                    # try alternative
                    home_score = score.get('home')
                    away_score = score.get('away')
                    if home_score is None or away_score is None:
                        continue

                match_date = details.get('date')
                if not match_date:
                    # use the date from the match list
                    match_date = match.get('date')
                    if not match_date:
                        continue

                # Get league name from match list
                league_name = match.get('league', {}).get('name', 'Unknown')

                home_id = get_team_id_global(conn, home_name, league_name)
                away_id = get_team_id_global(conn, away_name, league_name)
                if not home_id or not away_id:
                    continue

                # Use FotMob match ID as fixture_id
                fixture_id = int(match_id) if match_id else fixture_counter
                fixture_counter += 1

                insert_match(conn, fixture_id, home_id, away_id, home_score, away_score, match_date, league_name)
                total_inserted += 1

            conn.commit()
            print(f" Inserted some matches (total now: {total_inserted}).")
        except Exception as e:
            print(f" Error: {e}")

        current += delta
        time.sleep(0.1)  # be gentle

    conn.close()
    print(f"\n🎉 TOTAL HISTORICAL MATCHES ADDED: {total_inserted}")

if __name__ == "__main__":
    main()
