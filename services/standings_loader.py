import time

from api.football_api import FootballProvider
from config.settings import settings
from services.standings_service import StandingsService


class StandingsLoader:

    def __init__(self):

        self.provider = FootballProvider(settings.FOOTBALL_API_KEY)
        self.service = StandingsService()

    def load(self, league_id, season):

        response = None

        # Retry API request up to 3 times
        for attempt in range(3):

            try:

                response = self.provider.get_standings(
                    league_id,
                    season
                )

                break

            except Exception as e:

                if attempt == 2:
                    raise

                time.sleep(2)

        if not response:
            return 0

        league = response[0]["league"]

        standings = league["standings"][0]

        saved = 0

        for team in standings:

            try:

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

                saved += 1

            except Exception:
                # Skip bad team data instead of aborting the whole league
                continue

        return saved
