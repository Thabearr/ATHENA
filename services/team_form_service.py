import logging
from database.database import Database

logger = logging.getLogger("athena.team_form_service")

class TeamFormService:
    def __init__(self):
        self.db = Database()

    def get_recent_form_score(self, team_id: int, match_date: str) -> float:
        """
        Phase 2 Real Data Integration: Replaces placeholder values by parsing 
        the database to calculate a normalized historical efficiency rating (0.0 - 1.0).
        """
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
                    # If team has zero historical data logged, fall back to neutral baseline
                    return 0.50
                    
                points = 0
                total_matches = len(rows)
                
                for row in rows:
                    outcome = row[2]
                    if outcome == 'W':
                        points += 3
                    elif outcome == 'D':
                        points += 1
                        
                # Normalize 15 maximum possible points over 5 matches to a 0.1 - 0.95 form scale
                normalized_form = 0.10 + ((points / (total_matches * 3)) * 0.85)
                return round(normalized_form, 3)
                
        except Exception as e:
            logger.error(f"Error calculating real statistics for team {team_id}: {e}")
            return 0.50

    def get_league_scoring_baselines(self) -> dict:
        """
        Phase 3 Advanced Modeling: Computes baseline coefficients across 
        historical records to normalize true Poisson distribution curves.
        """
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
