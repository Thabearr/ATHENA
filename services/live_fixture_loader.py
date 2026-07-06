from api.football_api import FootballProvider
from config.settings import settings
from services.fixture_storage import FixtureStorage


class LiveFixtureLoader:

    def __init__(self):

        self.provider = FootballProvider(settings.FOOTBALL_API_KEY)
        self.storage = FixtureStorage()

    def load_today(self):

        fixtures = self.provider.get_today_fixtures()

        self.storage.save(fixtures)

        return fixtures
