#!/usr/bin/env python3
"""
Phase 2.2: Home/Away Adjustment
Computes per-team home win % vs league average.
Stores adjustment factors in the teams table.
"""
import sqlite3
import argparse

DB_PATH = "athena.db"

def compute_adjustments(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # 1. League average home win % (across all historical matches)
    avg_home_win = conn.execute("""
        SELECT 
            ROUND(CAST(SUM(CASE WHEN home_goals > away_goals THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) * 100, 2) as avg_pct
        FROM historical_matches
        WHERE home_id IS NOT NULL AND away_id IS NOT NULL
    """).fetchone()["avg_pct"]

    print(f"[VENUE] League average home win %: {avg_home_win}%")

    # 2. Per-team home win %
    teams = conn.execute("""
        SELECT 
            t.team_id,
            t.name,
            COUNT(*) as total_home,
            SUM(CASE WHEN h.home_goals > h.away_goals THEN 1 ELSE 0 END) as home_wins
        FROM teams t
        JOIN historical_matches h ON t.team_id = h.home_id
        GROUP BY t.team_id
        HAVING COUNT(*) >= 5  -- Minimum sample size
    """).fetchall()

    for team in teams:
        home_win_pct = (team["home_wins"] / team["total_home"]) * 100
        adjustment = round((home_win_pct - avg_home_win) / 100, 3)  # e.g., +0.08 for 8% above avg
        
        # Store adjustment
        conn.execute("""
            UPDATE teams SET home_adjustment = ?, away_adjustment = ? WHERE team_id = ?
        """, (adjustment, -adjustment, team["team_id"]))  # Away is inverse

        print(f"[VENUE] {team['name']}: Home Win% {home_win_pct:.1f}% (Adj: {adjustment:+.3f})")

    conn.commit()
    conn.close()
    print("[VENUE] Adjustments saved to teams table.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--compute", action="store_true", help="Compute venue adjustments")
    args = parser.parse_args()
    if args.compute:
        compute_adjustments()
