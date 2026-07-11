from api.football_api import FootballProvider
from config.settings import settings
from repositories.team_repository import TeamRepository
from datetime import datetime


class StatisticsLoader:

    def __init__(self):

        self.provider = FootballProvider(settings.FOOTBALL_API_KEY)
        self.repository = TeamRepository()

    def load(self, league_id, season, team_id):

        response = self.provider.get_team_statistics(
            league_id,
            season,
            team_id
        )

        if not response:
            return False

        team = response[0]

        fixtures = team["fixtures"]

        goals = team["goals"]

        clean_sheet = team["clean_sheet"]

        failed_to_score = team["failed_to_score"]

        stats = {

            "team_id": team_id,

            "league_id": league_id,

            "season": season,

            "rank": 20,

            "points": 0,

            "form": team.get("form", ""),

            "played": fixtures["played"]["total"],

            "wins": fixtures["wins"]["total"],

            "draws": fixtures["draws"]["total"],

            "losses": fixtures["loses"]["total"],

            "goals_for": goals["for"]["total"]["total"],

            "goals_against": goals["against"]["total"]["total"],

            "goal_difference":
                goals["for"]["total"]["total"]
                -
                goals["against"]["total"]["total"],

            "clean_sheets":
                clean_sheet["total"],

            "failed_to_score":
                failed_to_score["total"],

            "home_played":
                fixtures["played"]["home"],

            "home_wins":
                fixtures["wins"]["home"],

            "home_draws":
                fixtures["draws"]["home"],

            "home_losses":
                fixtures["loses"]["home"],

            "home_goals_for":
                goals["for"]["total"]["home"],

            "home_goals_against":
                goals["against"]["total"]["home"],

            "away_played":
                fixtures["played"]["away"],

            "away_wins":
                fixtures["wins"]["away"],

            "away_draws":
                fixtures["draws"]["away"],

            "away_losses":
                fixtures["loses"]["away"],

            "away_goals_for":
                goals["for"]["total"]["away"],

            "away_goals_against":
                goals["against"]["total"]["away"],

            "btts":
                team["both_teams_score"]["percentage"],

            "over15":
                team["goals"]["for"]["minute"].get("0-15", {}).get("percentage", 0),

            "over25":
                team["lineups"][0].get("formation", 0),

            "over35":
                0,

            "updated_at":
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        }

        self.repository.update_statistics(stats)

        return True
