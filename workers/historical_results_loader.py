import logging
from datetime import date, timedelta

from config.settings import settings
from config.supported_leagues import SUPPORTED_LEAGUES, season_for_league
from api.football_api import FootballProvider
from database.database import Database

logger = logging.getLogger("athena.historical_results_loader")


class HistoricalResultsLoader:
    """
    Populates historical_matches with REAL finished fixtures so
    TeamFormService can compute genuine recent-form scores instead of
    silently falling back to a neutral 0.50 for every team.

    Run this separately from the daily fixture loader — it's a heavier
    pull across every league and doesn't need to run more than every
    few days, since past results don't change.
    """

    def __init__(self, days_back: int = 120):
        self.days_back = days_back
        self.db = Database()
        self.provider = FootballProvider(settings.FOOTBALL_API_KEY) if settings.FOOTBALL_API_KEY else None

    def load(self) -> int:
        if not self.provider:
            logger.error("FOOTBALL_API_KEY is not set — cannot fetch real results.")
            return 0

        date_from = (date.today() - timedelta(days=self.days_back)).strftime("%Y-%m-%d")
        date_to = date.today().strftime("%Y-%m-%d")

        inserted = 0
        with self.db.connect() as conn:
            cursor = conn.cursor()
            for league_id in SUPPORTED_LEAGUES:
                season = season_for_league(league_id, settings)
                try:
                    response = self.provider.get_fixtures_by_league(
                        league_id=league_id,
                        season=season,
                        date_from=date_from,
                        date_to=date_to,
                    )
                except Exception as e:
                    logger.error(f"Failed to fetch results for league {league_id}: {e}")
                    continue

                for item in response:
                    try:
                        fixture = item["fixture"]
                        if fixture.get("status", {}).get("short") != "FT":
                            continue

                        teams = item["teams"]
                        goals = item["goals"]

                        cursor.execute(
                            """
                            INSERT INTO historical_matches
                                (fixture_id, home_id, away_id, home_goals, away_goals, match_date)
                            VALUES (?, ?, ?, ?, ?, ?)
                            ON CONFLICT(fixture_id) DO UPDATE SET
                                home_goals=excluded.home_goals,
                                away_goals=excluded.away_goals
                            """,
                            (
                                fixture["id"],
                                teams["home"]["id"],
                                teams["away"]["id"],
                                goals.get("home"),
                                goals.get("away"),
                                fixture.get("date", ""),
                            ),
                        )
                        inserted += 1
                    except Exception as e:
                        logger.error(f"Malformed result payload skipped: {e}")
                        continue
            conn.commit()

        logger.info(f"Loaded {inserted} real finished results into historical_matches.")
        return inserted


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    loader = HistoricalResultsLoader(days_back=120)
    count = loader.load()
    print(f"✅ Loaded {count} real historical results into historical_matches.")
