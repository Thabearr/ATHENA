from repositories.team_repository import TeamRepository


class TeamLoader:

    def __init__(self):
        self.repository = TeamRepository()

    def load(self, fixtures):

        loaded = set()

        for fixture in fixtures:

            league = fixture["league"]

            for side in ("home", "away"):

                team = fixture["teams"][side]

                key = (
                    team["id"],
                    league["id"],
                    league["season"]
                )

                if key in loaded:
                    continue

                loaded.add(key)

                self.repository.save_team(
                    team_id=team["id"],
                    name=team["name"],
                    country=league["country"],
                    league_id=league["id"],
                    season=league["season"]
                )

        return len(loaded)
