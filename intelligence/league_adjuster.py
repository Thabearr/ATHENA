#!/usr/bin/env python3
"""
League Strength Normalizer (Phase 2.4)
Adjusts ELO ratings across leagues so they are globally comparable.
Uses the Premier League as the baseline (1.0).
Weaker leagues get a negative adjustment, stronger leagues get positive (rare).
"""
import sqlite3
import argparse

DB_PATH = "database/athena.db"

# Base league strength factors (based on UEFA coefficients + historical performance)
# Premier League = baseline 1.00
LEAGUE_STRENGTH = {
    "Premier League": 1.00,
    "La Liga": 0.98,
    "Bundesliga": 0.97,
    "Serie A": 0.96,
    "Ligue 1": 0.92,
    "Primeira Liga": 0.88,
    "Eredivisie": 0.85,
    "Belgian Pro League": 0.78,
    "Süper Lig": 0.73,
    "Super League Greece": 0.72,
    "Scottish Premiership": 0.70,
    "Austrian Bundesliga": 0.68,
}

def normalize_elos(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # 1. Get average ELO of top 15 teams in Premier League (baseline)
    pl_avg = conn.execute("""
        SELECT AVG(elo_rating) as avg_elo
        FROM (
            SELECT elo_rating
            FROM teams
            WHERE league = 'Premier League' AND elo_rating > 0
            ORDER BY elo_rating DESC
            LIMIT 15
        )
    """).fetchone()["avg_elo"]

    if not pl_avg:
        print("[ERROR] No Premier League teams found with ELO ratings.")
        return

    print(f"[NORMALIZE] Premier League Top 15 Avg ELO: {pl_avg:.0f}")

    # 2. For each league, compute its top 15 avg ELO and apply a shift
    leagues = conn.execute("""
        SELECT DISTINCT league
        FROM teams
        WHERE league IS NOT NULL AND league != '' AND league != 'Premier League'
    """).fetchall()

    for row in leagues:
        league = row["league"]
        
        league_avg = conn.execute("""
            SELECT AVG(elo_rating) as avg_elo
            FROM (
                SELECT elo_rating
                FROM teams
                WHERE league = ? AND elo_rating > 0
                ORDER BY elo_rating DESC
                LIMIT 15
            )
        """, (league,)).fetchone()["avg_elo"]

        if not league_avg:
            continue

        # Calculate the raw ELO gap
        raw_gap = pl_avg - league_avg
        
        # Apply a strength factor (weaker leagues get a larger adjustment)
        strength_factor = LEAGUE_STRENGTH.get(league, 0.75)
        adjustment = round(raw_gap * strength_factor, 0)
        
        print(f"[NORMALIZE] {league}: Avg {league_avg:.0f}, Raw Gap {raw_gap:.0f}, Adjustment {adjustment:+.0f}")

        # Apply the adjustment to ALL teams in this league
        if adjustment != 0:
            conn.execute("""
                UPDATE teams
                SET elo_rating = elo_rating + ?,
                    home_elo = home_elo + ?,
                    away_elo = away_elo + ?
                WHERE league = ?
            """, (adjustment, adjustment, adjustment, league))
            conn.commit()

    print("[NORMALIZE] Complete. Re-run --validate to see the corrected rankings.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--normalize", action="store_true", help="Normalize ELO across leagues")
    args = parser.parse_args()
    if args.normalize:
        normalize_elos()
