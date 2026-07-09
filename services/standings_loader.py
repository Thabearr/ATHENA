from api.football_api import FootballProvider
from config.settings import settings
from services.standings_service import StandingsService


class StandingsLoader:

    def __init__(self):

        self.provider = FootballProvider(settings.FOOTBALL_API_KEY)
        self.service = StandingsService()

    def load(self, league_id, season):

        response = self.provider.get_standings(
            league_id,
            season
        )

        if not response:
            return

        league = response[0]["league"]

        standings = league["standings"][0]

        for team in standings:

            self.service.save({

                "team_id": team["team"]["id"],

                "league_id": league["id"],

                "season": league["season"],

                "position": team["rank"],

                "points": team["points"],

                "played": team["all"]["played"],

                "won": team["all"]["win"],

                "drawn": team["all"]["draw"],

                "lost": team["all"]["lose"],

                "goal_difference": team["goalsDiff"]

            })

        return len(standings)
