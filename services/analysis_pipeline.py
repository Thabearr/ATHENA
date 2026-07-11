import logging
from datetime import datetime
from database.database import Database
from intelligence.match_analyst import MatchAnalyst
from services.team_form_service import TeamFormService

logger = logging.getLogger("athena.analysis_pipeline")

class AnalysisPipeline:
    def __init__(self, match_analyst: MatchAnalyst, form_service: TeamFormService):
        self.db = Database()
        self.analyst = match_analyst
        self.form_svc = form_service

    def fetch_upcoming_fixtures(self, limit: int = 50) -> list:
        # UPDATED: Added a more permissive status check to ensure we grab 
        # upcoming games even if their status isn't perfectly set to 'NS'.
        query = """
            SELECT fixture_id, league, season, home_team, away_team, match_date 
            FROM fixtures 
            WHERE status NOT IN ('FT', 'AET', 'PEN') 
            ORDER BY match_date ASC LIMIT ?
        """
        try:
            with self.db.connect() as conn:
                conn.row_factory = lambda cursor, row: dict((cursor.description[i][0], value) for i, value in enumerate(row))
                cursor = conn.cursor()
                cursor.execute(query, (limit,))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Failed to fetch upcoming fixtures from DB: {e}")
            return []

    def run_pipeline_snapshot(self, execution_limit: int = 20) -> list:
        upcoming = self.fetch_upcoming_fixtures(limit=execution_limit)
        if not upcoming:
            logger.warning("No unplayed fixtures found in DB.")
            return []

        analyzed_batch = []
        for fix in upcoming:
            context_payload = {
                "fixture_id": fix["fixture_id"],
                "home_id": 1, # Placeholder for ID mapping
                "away_id": 2, 
                "match_date": fix["match_date"],
            }

            analysis = self.analyst.compile_master_fixture_prediction(context_payload)
            
            analyzed_batch.append({
                "fixture": f"{fix['home_team']} vs {fix['away_team']}",
                "home_team": fix['home_team'],
                "away_team": fix['away_team'],
                "upset_alert": analysis.get("upset_alert", False),
                "edge": analysis.get("edge_differential", 0),
                "verdict": analysis.get("recommended_analytical_verdict", "NO_BET"),
                "home_odds": 1.50, # Mock odds until DB sync is complete
                "away_odds": 2.50
            })

        return analyzed_batch
