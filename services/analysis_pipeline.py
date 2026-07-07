import logging
from datetime import datetime
from database.database import Database
from intelligence.match_analyst import MatchAnalyst

logger = logging.getLogger("athena.analysis_pipeline")

class AnalysisPipeline:
    def __init__(self, match_analyst: MatchAnalyst):
        self.db = Database()
        self.analyst = match_analyst

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
        Orchestrates full intelligence evaluation across upcoming matches.
        """
        upcoming = self.fetch_upcoming_fixtures(limit=execution_limit)
        if not upcoming:
            logger.warning("No upcoming unplayed fixtures found to analyze.")
            return []

        analyzed_batch = []
        logger.info(f"Processing intelligence metrics for {len(upcoming)} fixtures...")

        for fix in upcoming:
            # Resolve unique team IDs based on string names from the fixtures table
            # to pull metrics safely from your data schemas.
            # (Using structured fallbacks for mock pipeline validation)
            context_payload = {
                "fixture_id": fix["fixture_id"],
                "league_id": fix["league_id"],
                "season": fix["season"],
                "home_id": 10,  # Resolved dynamically via team mapper in next iteration
                "away_id": 20,
                "match_date": fix["match_date"],
                "home_last_match": "2026-07-02",
                "away_last_match": "2026-07-03",
                "home_position": 4,
                "away_position": 18,
                "weather": {"condition": "clear", "wind_speed": 5.0, "temp": 22.0},
                "home_absences": [],
                "away_absences": []
            }

            analysis = self.analyst.compile_master_fixture_prediction(context_payload)
            
            analyzed_batch.append({
                "fixture": f"{fix['home_team']} vs {fix['away_team']}",
                "date": fix["match_date"],
                "verdict": analysis["recommended_analytical_verdict"],
                "edge": analysis["edge_differential"]
            })

        return analyzed_batch
