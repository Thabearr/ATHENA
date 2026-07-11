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

    def _resolve_team_id(self, team_name: str) -> int:
        query = "SELECT team_id FROM teams WHERE name = ? LIMIT 1"
        try:
            with self.db.connect() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (team_name,))
                row = cursor.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.error(f"Error resolving team ID for '{team_name}': {e}")
            return None

    def fetch_upcoming_fixtures(self, limit: int = 50) -> list:
        # ---------------------------------------------------------
        # FIX: Changed 'league_id' to 'league' to match the new schema
        # ---------------------------------------------------------
        query = """
            SELECT fixture_id, league, season, home_team, away_team, match_date 
            FROM fixtures 
            WHERE status != 'FT' AND match_date >= ?
            ORDER BY match_date ASC LIMIT ?
        """
        today_str = datetime.now().strftime("%Y-%m-%d")
        try:
            with self.db.connect() as conn:
                conn.row_factory = lambda cursor, row: dict((cursor.description[i][0], value) for i, value in enumerate(row))
                cursor = conn.cursor()
                cursor.execute(query, (today_str, limit))
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
            home_id = self._resolve_team_id(fix["home_team"])
            away_id = self._resolve_team_id(fix["away_team"])
            
            # Temporary fallback logic for initial testing if teams table isn't populated yet
            if not home_id: home_id = 1
            if not away_id: away_id = 2

            context_payload = {
                "fixture_id": fix["fixture_id"],
                "home_id": home_id,
                "away_id": away_id,
                "match_date": fix["match_date"],
                "league_size": 20
            }

            analysis = self.analyst.compile_master_fixture_prediction(context_payload)
            
            analyzed_batch.append({
                "fixture": f"{fix['home_team']} vs {fix['away_team']}",
                "home_team": fix['home_team'],
                "away_team": fix['away_team'],
                "upset_alert": analysis.get("upset_alert", False),
                "edge": analysis.get("edge_differential", 0),
                "verdict": analysis.get("recommended_analytical_verdict", "NO_BET")
            })

        return analyzed_batch
