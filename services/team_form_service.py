import logging
from database.database import Database

logger = logging.getLogger("athena.team_form_service")

class TeamFormService:
    def __init__(self):
        self.db = Database()

    def get_recent_form_score(self, team_id: int, match_date: str) -> float:
        query = """
            SELECT 
                CASE WHEN home_id = ? THEN home_goals ELSE away_goals END as goals_scored,
                CASE WHEN home_id = ? THEN away_goals ELSE home_goals END as goals_conceded,
                CASE 
                    WHEN home_id = ? AND home_goals > away_goals THEN 'W'
                    WHEN away_id = ? AND away_goals > home_goals THEN 'W'
                    WHEN home_goals = away_goals THEN 'D'
                    ELSE 'L'
                END as outcome
            FROM historical_matches
            WHERE (home_id = ? OR away_id = ?) AND match_date < ?
            ORDER BY match_date DESC LIMIT 5
        """
        try:
            with self.db.connect() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (team_id, team_id, team_id, team_id, team_id, team_id, match_date))
                rows = cursor.fetchall()

                if not rows:
                    return 0.50

                points = 0
                total_matches = len(rows)

                for row in rows:
                    outcome = row[2]
                    if outcome == 'W':
                        points += 3
                    elif outcome == 'D':
                        points += 1

                normalized_form = 0.10 + ((points / (total_matches * 3)) * 0.85)
                return round(normalized_form, 3)

        except Exception as e:
            logger.error(f"Error calculating real statistics for team {team_id}: {e}")
            return 0.50

    def get_data_freshness(self, team_id: int, match_date: str) -> dict:
        """
        Reports how much of the form data behind get_recent_form_score is
        actually live (football_data_org_live) vs stale 2022-2024
        (api_football_2022_2024), so callers can treat them differently
        instead of pretending both are equally reliable.
        """
        query = """
            SELECT match_date, data_source
            FROM historical_matches
            WHERE (home_id = ? OR away_id = ?) AND match_date < ?
            ORDER BY match_date DESC LIMIT 5
        """
        try:
            with self.db.connect() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (team_id, team_id, match_date))
                rows = cursor.fetchall()

                if not rows:
                    return {"has_data": False, "live_ratio": 0.0, "sample_size": 0}

                live_count = sum(1 for r in rows if r[1] == "football_data_org_live")
                return {
                    "has_data": True,
                    "live_ratio": round(live_count / len(rows), 2),
                    "sample_size": len(rows),
                }
        except Exception as e:
            logger.error(f"Error checking data freshness for team {team_id}: {e}")
            return {"has_data": False, "live_ratio": 0.0, "sample_size": 0}

    def get_last_match_date(self, team_id: int, before_date: str) -> str:
        """
        Returns this team's most recent real match_date strictly before
        `before_date`, or None if we have no record of one. Used to feed
        real rest-day calculations into FatigueEngine — returning None
        rather than guessing means the fatigue engine can honestly report
        "no data" instead of silently treating "no data" as "just played".
        """
        query = """
            SELECT match_date
            FROM historical_matches
            WHERE (home_id = ? OR away_id = ?) AND match_date < ?
            ORDER BY match_date DESC LIMIT 1
        """
        try:
            with self.db.connect() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (team_id, team_id, before_date))
                row = cursor.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.error(f"Error fetching last match date for team {team_id}: {e}")
            return None

    def get_league_scoring_baselines(self) -> dict:
        query = "SELECT AVG(home_goals), AVG(away_goals) FROM historical_matches"
        try:
            with self.db.connect() as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                row = cursor.fetchone()
                if row and row[0] is not None:
                    return {"avg_home_goals": round(row[0], 2), "avg_away_goals": round(row[1], 2)}
        except Exception:
            pass
        return {"avg_home_goals": 1.45, "avg_away_goals": 1.15}
