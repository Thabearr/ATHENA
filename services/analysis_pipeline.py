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
        try:
            query = "SELECT team_id FROM teams WHERE name = ? LIMIT 1"
            with self.db.connect() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (team_name,))
                row = cursor.fetchone()
                return row[0] if row else abs(hash(team_name)) % 1000
        except Exception:
            return abs(hash(team_name)) % 1000

    def fetch_upcoming_fixtures(self, limit: int = 200) -> list:
        query = """
            SELECT fixture_id, league, season, home_team, away_team, match_date, data_source
            FROM fixtures
            WHERE status NOT IN ('FT', 'AET', 'PEN')
            ORDER BY match_date ASC LIMIT ?
        """
        results = []
        try:
            with self.db.connect() as conn:
                conn.row_factory = lambda cursor, row: dict(
                    (cursor.description[i][0], value) for i, value in enumerate(row)
                )
                cursor = conn.cursor()
                cursor.execute(query, (limit,))
                results = cursor.fetchall()
        except Exception as e:
            logger.error(f"Failed to fetch upcoming fixtures from DB: {e}")

        if not results:
            logger.warning(
                "No real fixtures found in the database. Not fabricating "
                "placeholder matches — run the fixture loader first."
            )

        return results

    def run_pipeline_snapshot(self, execution_limit: int = 150) -> list:
        upcoming = self.fetch_upcoming_fixtures(limit=execution_limit)

        analyzed_batch = []
        youth_pattern = re.compile(r'\b[uU]\d{2}\b')
        womens_blacklist = [" W ", "Women", "Womens", "Femenino", "Frauen", " Féminines", "Fem."]

        for fix in upcoming:
            home_team = str(fix.get('home_team') or 'Unknown Home')
            away_team = str(fix.get('away_team') or 'Unknown Away')
            league_name = str(fix.get('league') or '').lower()

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
                "is_knockout": any(k in league_name for k in ["cup", "champions league", "playoff", "knockout"]),
            }

            try:
                analysis = self.analyst.compile_master_fixture_prediction(context_payload)
                analyzed_batch.append({
                    "fixture": f"{home_team} vs {away_team}",
                    "home_team": home_team,
                    "away_team": away_team,
                    "upset_alert": analysis.get("upset_alert", False),
                    "risk_score": analysis.get("risk_score", 0.0),
                    "stale_data": analysis.get("stale_data", False),
                    "edge": analysis.get("edge_differential", 0.05),
                    "verdict": analysis.get("recommended_analytical_verdict", "DC_1X"),
                    "source": fix.get("data_source", "unknown"),
                })
            except Exception as e:
                logger.error(f"Error compiling prediction for {home_team} vs {away_team}: {e}")
                continue

        return analyzed_batch
