from api.football import FootballProvider
from config.settings import settings
from services.fixture_service import FixtureService


class LiveFixtureLoader:

    def __init__(self):

        provider = FootballProvider(settings.FOOTBALL_API_KEY)

        self.service = FixtureService(provider)

    def load(self):

        return self.service.get_today_fixtures()
