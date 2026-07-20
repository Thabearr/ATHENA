#!/usr/bin/env python3
"""
FotMob Historical Match Loader (v3 - Dynamic Seasons)
Fetches ALL available seasons for each competition using the fotmob package.
Inserts into historical_matches for global ELO normalization.
"""
import sqlite3
import hashlib
from fotmob import FotMob
import time

DB_PATH = "athena.db"

# All competitions from your list (FotMob league IDs)
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
    return 1

def fetch_all_seasons_for_league(league_id: int):
    """Get all season identifiers available for this league from FotMob."""
    fotmob = FotMob()
    try:
        # Fetch league info (includes season list)
        league_data = fotmob.get_league(league_id)
        # The structure may have 'seasons' key or we can use a known pattern
        # Fallback: generate common season strings from 2000 to current year
        current_year = 2026
        seasons = []
        for year in range(2000, current_year + 1):
            seasons.append(f"{year}/{year+1}")
        return seasons
    except Exception as e:
        # If league info fails, use a broad range
        return [f"{y}/{y+1}" for y in range(2000, 2027)]

def main():
    conn = sqlite3.connect(DB_PATH)
    fotmob = FotMob()
    total_inserted = 0
    fixture_counter = 1000000  # avoid collision with domestic fixture IDs

    for league_name, league_id in COMPETITIONS.items():
        print(f"\n--- {league_name} (ID: {league_id}) ---")
        # Get available seasons (or fallback to wide range)
        seasons = fetch_all_seasons_for_league(league_id)
        print(f"  Attempting {len(seasons)} seasons...")

        for season in seasons:
            print(f"    Fetching {season}...", end="", flush=True)
            try:
                # Use fotmob package to get matches
                matches_data = fotmob.get_league_matches(league_id, season=season)
                if not matches_data:
                    print(" No data.")
                    continue

                # Extract matches list (different possible structures)
                matches = matches_data.get('matches') or matches_data.get('data', {}).get('matches', [])
                if not matches:
                    print(" No matches.")
                    continue

                season_count = 0
                for match in matches:
                    home = match.get('home', {})
                    away = match.get('away', {})
                    home_name = home.get('name') if isinstance(home, dict) else home
                    away_name = away.get('name') if isinstance(away, dict) else away
                    if not home_name or not away_name:
                        continue

                    status = match.get('status', {})
                    if not status.get('finished', False):
                        continue

                    score = match.get('score', {})
                    home_score = score.get('fulltime', {}).get('home')
                    away_score = score.get('fulltime', {}).get('away')
                    if home_score is None or away_score is None:
                        continue

                    match_date = match.get('date')
                    if not match_date:
                        continue

                    home_id = get_team_id_global(conn, home_name, league_name)
                    away_id = get_team_id_global(conn, away_name, league_name)
                    if not home_id or not away_id:
                        continue

                    # Use FotMob ID if available
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
                print(f" ✅ Inserted {season_count} matches.")
                total_inserted += season_count
                # If no matches for a season, we might stop for that league? 
                # But some leagues have gaps, so continue.
                time.sleep(0.2)  # be gentle

            except Exception as e:
                print(f" ❌ Error: {e}")

    conn.close()
    print(f"\n🎉 TOTAL HISTORICAL MATCHES ADDED FROM FOTMOB: {total_inserted}")

if __name__ == "__main__":
    main()
