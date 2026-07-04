from models.fixture import Fixture


class FixtureService:

    def __init__(self, football_provider):
        self.provider = football_provider

    def get_today_fixtures(self):
        """
        Returns today's fixtures as Fixture objects.
        """
        raw_fixtures = self.provider.get_today_fixtures()

        fixtures = []

        for item in raw_fixtures:

            fixture = Fixture(
                fixture_id=item["fixture"]["id"],
                league=item["league"]["name"],
                league_id=item["league"]["id"],

                home_team=item["teams"]["home"]["name"],
                away_team=item["teams"]["away"]["name"],

                home_team_id=item["teams"]["home"]["id"],
                away_team_id=item["teams"]["away"]["id"],

                kickoff=item["fixture"]["date"],
                venue=item["fixture"]["venue"]["name"],
                status=item["fixture"]["status"]["short"]
            )

            fixtures.append(fixture)

        return fixtures
