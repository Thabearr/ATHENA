import logging
from datetime import datetime

from repositories.statistics_repository import StatisticsRepository

logger = logging.getLogger("athena.statistics_service")


class StatisticsService:

    def __init__(self):
        self.repository = StatisticsRepository()

    def save_team_statistics(self, stats_data: dict):

        try:

            values = (
                stats_data["team_id"],
                stats_data["league_id"],
                stats_data["season"],
                stats_data.get("form", ""),
                stats_data.get("played", 0),
                stats_data.get("wins", 0),
                stats_data.get("draws", 0),
                stats_data.get("losses", 0),
                stats_data.get("goals_for", 0),
                stats_data.get("goals_against", 0),
                stats_data.get("home_played", 0),
                stats_data.get("home_wins", 0),
                stats_data.get("home_draws", 0),
                stats_data.get("home_losses", 0),
                stats_data.get("home_goals_for", 0),
                stats_data.get("home_goals_against", 0),
                stats_data.get("away_played", 0),
                stats_data.get("away_wins", 0),
                stats_data.get("away_draws", 0),
                stats_data.get("away_losses", 0),
                stats_data.get("away_goals_for", 0),
                stats_data.get("away_goals_against", 0),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )

            self.repository.save_statistics(values)

        except Exception as e:
            logger.error(f"Failed saving statistics: {e}")

    def get_team_statistics(
        self,
        team_id: int,
        league_id: int,
        season: int
    ):

        try:

            return self.repository.get_statistics(
                team_id,
                league_id,
                season
            )

        except Exception as e:

            logger.error(f"Statistics lookup failed: {e}")

            return None
