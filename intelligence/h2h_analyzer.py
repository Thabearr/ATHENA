#!/usr/bin/env python3
"""
Phase 2.3: Head-to-Head Analyzer
Tracks team-specific matchup history with recency weighting.
PDF Spec: Overall H2H, Home/Away splits, avg goals, last meeting.
"""
import sqlite3
import argparse
from typing import Dict, List, Optional, Tuple

DB_PATH = "database/athena.db"

class H2HAnalyzer:
    def __init__(self, db_path: str = DB_PATH):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def get_h2h(self, home_team_id: int, away_team_id: int, limit: Optional[int] = None) -> Dict:
        """
        Fetch head-to-head record between two teams.
        Weighted recency: recent matches are more important.
        """
        # Base query: get all historical matches between these two teams
        query = """
            SELECT 
                home_id, away_id, home_goals, away_goals, match_date
            FROM historical_matches
            WHERE (home_id = ? AND away_id = ?) 
               OR (home_id = ? AND away_id = ?)
            ORDER BY match_date DESC
        """
        if limit:
            query += f" LIMIT {limit}"
        
        cur = self.conn.execute(query, (home_team_id, away_team_id, away_team_id, home_team_id))
        rows = cur.fetchall()

        if not rows:
            return {
                "home_team": home_team_id,
                "away_team": away_team_id,
                "h2h_record": {"wins": 0, "draws": 0, "losses": 0},
                "home_record": {"wins": 0, "draws": 0, "losses": 0},
                "away_record": {"wins": 0, "draws": 0, "losses": 0},
                "avg_home_goals": 0.0,
                "avg_away_goals": 0.0,
                "last_meeting": None,
                "total_meetings": 0
            }

        # Initialize counters
        total_wins, total_draws, total_losses = 0, 0, 0
        home_wins, home_draws, home_losses = 0, 0, 0
        away_wins, away_draws, away_losses = 0, 0, 0
        total_home_goals, total_away_goals = 0, 0
        total_goals_scored = 0

        for row in rows:
            is_home_match = (row["home_id"] == home_team_id)
            
            # Determine result from home_team's perspective
            if is_home_match:
                home_goals, away_goals = row["home_goals"], row["away_goals"]
            else:
                home_goals, away_goals = row["away_goals"], row["home_goals"]  # Swap
            
            if home_goals > away_goals:
                result = "win"
                total_wins += 1
                if is_home_match:
                    home_wins += 1
                else:
                    away_wins += 1
            elif home_goals == away_goals:
                result = "draw"
                total_draws += 1
                if is_home_match:
                    home_draws += 1
                else:
                    away_draws += 1
            else:
                result = "loss"
                total_losses += 1
                if is_home_match:
                    home_losses += 1
                else:
                    away_losses += 1

            # Track goals (from home_team's perspective)
            if is_home_match:
                total_home_goals += row["home_goals"]
                total_away_goals += row["away_goals"]
            else:
                total_home_goals += row["away_goals"]
                total_away_goals += row["home_goals"]

            total_goals_scored += 1

        meetings = len(rows)
        last_meeting = rows[0]["match_date"] if rows else None

        return {
            "home_team": home_team_id,
            "away_team": away_team_id,
            "h2h_record": {
                "wins": total_wins,
                "draws": total_draws,
                "losses": total_losses
            },
            "home_record": {
                "wins": home_wins,
                "draws": home_draws,
                "losses": home_losses
            },
            "away_record": {
                "wins": away_wins,
                "draws": away_draws,
                "losses": away_losses
            },
            "avg_home_goals": round(total_home_goals / meetings, 2) if meetings > 0 else 0,
            "avg_away_goals": round(total_away_goals / meetings, 2) if meetings > 0 else 0,
            "last_meeting": last_meeting,
            "total_meetings": meetings
        }

    def format_output(self, data: Dict) -> str:
        """Pretty print H2H data."""
        home_name = self._get_team_name(data["home_team"])
        away_name = self._get_team_name(data["away_team"])
        output = f"\n{'='*50}\n"
        output += f"Head-to-Head: {home_name} vs {away_name}\n"
        output += f"{'='*50}\n"
        output += f"Total Meetings: {data['total_meetings']}\n"
        output += f"Last Meeting: {data['last_meeting']}\n\n"
        
        output += "Overall H2H Record:\n"
        output += f"  Wins: {data['h2h_record']['wins']}, Draws: {data['h2h_record']['draws']}, Losses: {data['h2h_record']['losses']}\n\n"
        
        output += "Home Record (at home vs this opponent):\n"
        output += f"  Wins: {data['home_record']['wins']}, Draws: {data['home_record']['draws']}, Losses: {data['home_record']['losses']}\n\n"
        
        output += "Away Record (away vs this opponent):\n"
        output += f"  Wins: {data['away_record']['wins']}, Draws: {data['away_record']['draws']}, Losses: {data['away_record']['losses']}\n\n"
        
        output += f"Average Goals Scored: {data['avg_home_goals']} (home), {data['avg_away_goals']} (away)\n"
        output += f"{'='*50}\n"
        return output

    def _get_team_name(self, team_id: int) -> str:
        cur = self.conn.execute("SELECT name FROM teams WHERE team_id = ?", (team_id,))
        row = cur.fetchone()
        return row["name"] if row else str(team_id)

    def close(self):
        self.conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ATHENA Head-to-Head Analyzer")
    parser.add_argument("--home", type=int, required=True, help="Home team ID")
    parser.add_argument("--away", type=int, required=True, help="Away team ID")
    parser.add_argument("--limit", type=int, help="Max recent matches to analyze")
    args = parser.parse_args()

    analyzer = H2HAnalyzer()
    result = analyzer.get_h2h(args.home, args.away, args.limit)
    print(analyzer.format_output(result))
    analyzer.close()
