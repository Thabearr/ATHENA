from api.football_api import FootballProvider
from config.settings import settings

from repositories.team_repository import TeamRepository


class FormLoader:

    def __init__(self):

        self.provider = FootballProvider(settings.FOOTBALL_API_KEY)
        self.repository = TeamRepository()

    def load(self, team_id):

        fixtures = self.provider.get_team_last_matches(team_id, 5)

        if not fixtures:
            return

        wins = 0
        draws = 0
        losses = 0

        goals_for = 0
        goals_against = 0

        form = ""

        for match in fixtures:

            home = match["teams"]["home"]["id"] == team_id

            if home:
                gf = match["goals"]["home"]
                ga = match["goals"]["away"]
            else:
                gf = match["goals"]["away"]
                ga = match["goals"]["home"]

            goals_for += gf
            goals_against += ga

            if gf > ga:
                wins += 1
                form += "W"

            elif gf == ga:
                draws += 1
                form += "D"

            else:
                losses += 1
                form += "L"

        self.repository.update_form(
            team_id,
            form,
            wins,
            draws,
            losses,
            goals_for,
            goals_against
        )

        return len(fixtures)
