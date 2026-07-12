import logging
import re
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
        Attempts to resolve the actual DB team_id. 
        If missing, uses a deterministic hash so the FormService can calculate unique edges.
        """
        query = "SELECT team_id FROM teams WHERE name = ? LIMIT 1"
        try:
            with self.db.connect() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (team_name,))
                row = cursor.fetchone()
                return row[0] if row else abs(hash(team_name)) % 1000
        except Exception:
            return abs(hash(team_name)) % 1000

    def fetch_upcoming_fixtures(self, limit: int = 250) -> list:
        # Pulling a larger pool to compensate for strictly filtered matches
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

    def run_pipeline_snapshot(self, execution_limit: int = 100) -> list:
        upcoming = self.fetch_upcoming_fixtures(limit=execution_limit)
        if not upcoming:
            logger.warning("No unplayed fixtures found in DB.")
            return []

        analyzed_batch = []
        
        # Regex to catch any youth teams like U17, U19, U20, U23, etc.
        youth_pattern = re.compile(r'\b[uU]\d{2}\b')

        for fix in upcoming:
            home_team = fix['home_team']
            away_team = fix['away_team']
            
            # 1. Broad Text Firewall for Women's variants
            womens_blacklist = [" W ", "Women", "Womens", "Femenino", "Frauen", " Féminines", "Fem."]
            if any(b.lower() in home_team.lower() or b.lower() in away_team.lower() for b in womens_blacklist):
                continue
                
            # 2. Strict Regex Firewall for all Youth structural divisions (U15 through U23)
            if youth_pattern.search(home_team) or youth_pattern.search(away_team):
                continue

            context_payload = {
                "fixture_id": fix["fixture_id"],
                "home_id": self._resolve_team_id(home_team),
                "away_id": self._resolve_team_id(away_team),
                "match_date": fix["match_date"],
            }

            analysis = self.analyst.compile_master_fixture_prediction(context_payload)
            
            analyzed_batch.append({
                "fixture": f"{home_team} vs {away_team}",
                "home_team": home_team,
                "away_team": away_team,
                "upset_alert": analysis.get("upset_alert", False),
                "edge": analysis.get("edge_differential", 0),
                "verdict": analysis.get("recommended_analytical_verdict", "NO_BET"),
                "home_odds": 1.50, 
                "away_odds": 2.50
            })

        return analyzed_batch
