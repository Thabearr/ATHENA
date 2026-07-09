import logging

from repositories.standings_repository import StandingsRepository

logger = logging.getLogger("athena.standings")


class StandingsService:

    def __init__(self):

        self.repository = StandingsRepository()

    def save(self, standing: dict):

        try:

            values = (

                standing["team_id"],
                standing["league_id"],
                standing["season"],

                standing["position"],
                standing["points"],

                standing["played"],
                standing["won"],
                standing["drawn"],
                standing["lost"],

                standing["goal_difference"]

            )

            self.repository.save_standings(values)

        except Exception as e:

            logger.error(f"Failed saving standings: {e}")

    def get_team_position(
        self,
        team_id,
        league_id,
        season
    ):

        return self.repository.get_team_position(
            team_id,
            league_id,
            season
        )
