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
        """
        Helper method to resolve a team's database ID from its string name.
        """
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

    def fetch_upcoming_fixtures(self, limit: int = 10) -> list:
        """
        Pulls upcoming unplayed fixtures from the database.
        """
        query = """
            SELECT fixture_id, league_id, season, home_team, away_team, match_date 
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

    def run_pipeline_snapshot(self, execution_limit: int = 5) -> list:
        """
        Orchestrates full live intelligence evaluation across unplayed database fixtures.
        """
        upcoming = self.fetch_upcoming_fixtures(limit=execution_limit)
        if not upcoming:
            logger.warning("No upcoming unplayed fixtures found in the database to analyze.")
            return []

        analyzed_batch = []
        logger.info(f"Processing live intelligence metrics for {len(upcoming)} fixtures...")

        for fix in upcoming:
            # 1. Resolve Text Names to Real IDs
            home_id = self._resolve_team_id(fix["home_team"])
            away_id = self._resolve_team_id(fix["away_team"])

            if not home_id or not away_id:
                logger.warning(f"Skipping match {fix['home_team']} vs {fix['away_team']}: Could not resolve database IDs.")
                continue

            # 2. Extract Real Time Form via TeamFormService
            home_raw_form = self.form_svc.get_recent_raw_form(home_id)
            away_raw_form = self.form_svc.get_recent_raw_form(away_id)

            # 3. Construct Live Input Context for the Match Analyst
            context_payload = {
                "fixture_id": fix["fixture_id"],
                "league_id": fix["league_id"],
                "season": fix["season"],
                "home_id": home_id,
                "away_id": away_id,
                "match_date": fix["match_date"],
                
                # These will default dynamically to lookups within your underlying engines
                "home_position": 10,  
                "away_position": 10,
                
                # Real calculated form metrics passed to engine parameters
                "mock_home_form": self.analyst.form_eng.calculate_weighted_form_index(home_raw_form),
                "mock_away_form": self.analyst.form_eng.calculate_weighted_form_index(away_raw_form),
                
                # Fallbacks for external variables
                "home_last_match": fix["match_date"], 
                "away_last_match": fix["match_date"],
                "weather": {"condition": "clear", "wind_speed": 5.0, "temp": 20.0},
                "home_absences": [],
                "away_absences": []
            }

            # 4. Process predictions through the compiled analytical formulas
            analysis = self.analyst.compile_master_fixture_prediction(context_payload)
            
            analyzed_batch.append({
                "fixture": f"{fix['home_team']} vs {fix['away_team']}",
                "date": fix["match_date"],
                "verdict": analysis["recommended_analytical_verdict"],
                "edge": analysis["edge_differential"]
            })

        return analyzed_batch
