from api.football_api import FootballProvider
from config.settings import settings
from services.fixture_service import FixtureService


class LiveFixtureLoader:
    """
    Loads live football fixtures using the configured football provider.
    """

    def __init__(self):
        if not settings.FOOTBALL_API_KEY:
            raise ValueError(
                "FOOTBALL_API_KEY is missing. Please check your .env file."
            )

        provider = FootballProvider(settings.FOOTBALL_API_KEY)
        self.fixture_service = FixtureService(provider)

    def load(self):
        """
        Returns today's fixtures as a list of Fixture objects.
        """
        return self.fixture_service.get_today_fixtures()
