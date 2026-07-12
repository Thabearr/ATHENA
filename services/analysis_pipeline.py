import logging
import re
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
                return row[0] if row else abs(hash(team_name)) % 1000
        except Exception:
            return abs(hash(team_name)) % 1000

    def fetch_upcoming_fixtures(self, limit: int = 200) -> list:
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

    def run_pipeline_snapshot(self, execution_limit: int = 150) -> list:
        upcoming = self.fetch_upcoming_fixtures(limit=execution_limit)
        if not upcoming:
            logger.warning("No unplayed fixtures found in DB.")
            return []

        analyzed_batch = []
        youth_pattern = re.compile(r'\b[uU]\d{2}\b')
        womens_blacklist = [" W ", "Women", "Womens", "Femenino", "Frauen", " Féminines", "Fem."]

        for fix in upcoming:
            # Bulletproof string casting to prevent NULL/NoneType crashes on raw data
            home_team = str(fix.get('home_team') or 'Unknown Home')
            away_team = str(fix.get('away_team') or 'Unknown Away')
            league_name = str(fix.get('league') or '').lower()
            
            # Strict Exclusions
            if any(b.lower() in home_team.lower() or b.lower() in away_team.lower() for b in womens_blacklist):
                continue
                
            if youth_pattern.search(home_team) or youth_pattern.search(away_team):
                continue

            context_payload = {
                "fixture_id": fix.get("fixture_id", 0),
                "home_team": home_team,
                "away_team": away_team,
                "home_id": self._resolve_team_id(home_team),
                "away_id": self._resolve_team_id(away_team),
                "match_date": fix.get("match_date", ""),
                "is_knockout": any(k in league_name for k in ["cup", "champions league", "playoff", "knockout"])
            }

            try:
                analysis = self.analyst.compile_master_fixture_prediction(context_payload)
                analyzed_batch.append({
                    "fixture": f"{home_team} vs {away_team}",
                    "home_team": home_team,
                    "away_team": away_team,
                    "upset_alert": analysis.get("upset_alert", False),
                    "edge": analysis.get("edge_differential", 0),
                    "verdict": analysis.get("recommended_analytical_verdict", "DC_1X"),
                    "home_odds": 1.50, 
                    "away_odds": 2.50
                })
            except Exception as e:
                # If a single match triggers a math or logic error, log it and skip to the next
                logger.error(f"Error compiling prediction for {home_team} vs {away_team}: {e}")
                continue

        return analyzed_batch
