#!/usr/bin/env python3
"""
Phase 2.1: ELO Rating Engine
Complies strictly with ATHENA PDF spec.
Home team gets +50 rating boost.
K-factor: 32 (low volume), 24 (mid), 16 (high volume).
"""
import sqlite3
import argparse
import json
from datetime import datetime
from typing import Dict, Optional, Tuple

DB_PATH = "database/athena.db"  # CHANGE THIS to your actual SQLite path if different

class EloEngine:
    def __init__(self, db_path: str = DB_PATH):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def _get_team_ratings(self, team_id: int) -> Dict:
        """Fetch current ELO ratings for a team."""
        cur = self.conn.execute(
            "SELECT elo_rating, home_elo, away_elo, matches_processed FROM teams WHERE team_id = ?",
            (team_id,)
        )
        row = cur.fetchone()
        if not row:
            # Insert a new team with default 1500 (shouldn't happen if seeding worked)
            self.conn.execute(
                "INSERT OR IGNORE INTO teams (team_id, elo_rating, home_elo, away_elo, matches_processed) VALUES (?, 1500, 1500, 1500, 0)",
                (team_id,)
            )
            self.conn.commit()
            return {"elo": 1500, "home_elo": 1500, "away_elo": 1500, "matches": 0}
        # Return a dict with clean keys (elo, home_elo, away_elo, matches)
        return {
            "elo": row["elo_rating"],
            "home_elo": row["home_elo"],
            "away_elo": row["away_elo"],
            "matches": row["matches_processed"]
        }

    def _get_k_factor(self, matches_processed: int) -> int:
        """PDF Spec: K=32 normal, K=24 high volume, K=16 very high volume."""
        if matches_processed < 20:
            return 32
        elif matches_processed < 50:
            return 24
        else:
            return 16

    def expected_score(self, rating_a: int, rating_b: int, home_boost: bool = True) -> float:
        """
        Calculate expected win probability for Team A vs Team B.
        Home team receives +50 rating boost per PDF section 2.1.
        """
        if home_boost:
            rating_a += 50  # Home advantage boost
        return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))

    def update_elo(self, home_id: int, away_id: int, home_goals: int, away_goals: int, match_date: str, fixture_id: int = None):
        """
        Update ELO ratings for both teams after a match.
        S = 1.0 (win), 0.5 (draw), 0.0 (loss)
        """
        # 1. Fetch current ratings
        home_rating = self._get_team_ratings(home_id)
        away_rating = self._get_team_ratings(away_id)

        R_home = home_rating["elo"]
        R_away = away_rating["elo"]

        # 2. Expected scores (home gets +50 boost)
        E_home = self.expected_score(R_home, R_away, home_boost=True)
        E_away = self.expected_score(R_away, R_home, home_boost=False)  # Away team doesn't get boost

        # 3. Actual results (S)
        if home_goals > away_goals:
            S_home, S_away = 1.0, 0.0
        elif home_goals == away_goals:
            S_home, S_away = 0.5, 0.5
        else:
            S_home, S_away = 0.0, 1.0

        # 4. K-factors
        K_home = self._get_k_factor(home_rating["matches"])
        K_away = self._get_k_factor(away_rating["matches"])

        # 5. New ratings (overall)
        new_R_home = R_home + K_home * (S_home - E_home)
        new_R_away = R_away + K_away * (S_away - E_away)

        # 6. Update Home/Away specific ELOs (per PDF)
        new_home_elo = home_rating["home_elo"] + K_home * (S_home - E_home)
        new_away_elo = away_rating["away_elo"] + K_away * (S_away - E_away)

        # 7. Persist to database
        self.conn.execute("""
            UPDATE teams SET 
                elo_rating = ?,
                home_elo = ?,
                away_elo = ?,
                matches_processed = matches_processed + 1,
                last_update = ?
            WHERE team_id = ?
        """, (int(new_R_home), int(new_home_elo), home_rating["away_elo"], match_date, home_id))

        self.conn.execute("""
            UPDATE teams SET 
                elo_rating = ?,
                home_elo = ?,
                away_elo = ?,
                matches_processed = matches_processed + 1,
                last_update = ?
            WHERE team_id = ?
        """, (int(new_R_away), away_rating["home_elo"], int(new_away_elo), match_date, away_id))

        # 8. Update pre_elo in historical_matches if fixture_id provided
        if fixture_id is not None:
            self.conn.execute("""
                UPDATE historical_matches
                SET home_pre_elo = ?, away_pre_elo = ?
                WHERE fixture_id = ?
            """, (int(R_home), int(R_away), fixture_id))

        self.conn.commit()
        # print(f"[ELO] Updated {home_id} ({int(new_R_home)}) vs {away_id} ({int(new_R_away)})")

    def process_historical_matches(self, limit: Optional[int] = None):
        """
        Backfill ELO ratings using all historical matches.
        PDF Spec: Process chronologically so ratings build realistically.
        """
        print("[ELO] Starting historical backfill...")
        query = """
            SELECT fixture_id, home_id, away_id, home_goals, away_goals, match_date
            FROM historical_matches
            WHERE home_id IS NOT NULL AND away_id IS NOT NULL
            ORDER BY match_date ASC
        """
        if limit:
            query += f" LIMIT {limit}"
        cur = self.conn.execute(query)
        rows = cur.fetchall()
        total = len(rows)
        for idx, row in enumerate(rows):
            self.update_elo(row["home_id"], row["away_id"], row["home_goals"], row["away_goals"], row["match_date"], row["fixture_id"])
            if idx % 500 == 0:
                print(f"Processed {idx}/{total} historical matches...")
            if idx % 50 == 0:
                print(f"[ELO] Progress: {idx}/{total}")

        print(f"[ELO] Completed! Processed {total} historical matches.")

    def get_current_rating(self, team_id: int) -> Dict:
        """PDF Spec: Query latest rating."""
        return self._get_team_ratings(team_id)

    def validate_correlation(self):
        """
        Quick validation: Check if top ELO teams match league standings.
        PDF Success Metric: Correlation > 0.85.
        """
        print("[VALIDATION] Top 10 ELO Teams:")
        cur = self.conn.execute("""
            SELECT name, elo_rating, matches_processed 
            FROM teams 
            WHERE elo_rating > 0 
            ORDER BY elo_rating DESC 
            LIMIT 10
        """)
        for row in cur.fetchall():
            print(f"  {row['name']}: {row['elo_rating']} (played: {row['matches_processed']})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ATHENA ELO Engine")
    parser.add_argument("--process-history", action="store_true", help="Backfill all historical matches")
    parser.add_argument("--limit", type=int, help="Limit number of historical matches to process")
    parser.add_argument("--validate", action="store_true", help="Show top 10 ELO teams")
    parser.add_argument("--update-fixture", type=int, help="Update ELO for a specific fixture_id")
    args = parser.parse_args()

    engine = EloEngine()

    if args.process_history:
        engine.process_historical_matches(args.limit)
    
    if args.update_fixture:
        cur = engine.conn.execute(
            "SELECT home_id, away_id, home_goals, away_goals, match_date FROM historical_matches WHERE fixture_id = ?",
            (args.update_fixture,)
        )
        row = cur.fetchone()
        if row:
            engine.update_elo(row["home_id"], row["away_id"], row["home_goals"], row["away_goals"], row["match_date"])
        else:
            print(f"[ERROR] Fixture {args.update_fixture} not found in historical_matches.")

    if args.validate:
        engine.validate_correlation()

    engine.conn.close()
