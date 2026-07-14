from dotenv import load_dotenv
import os

load_dotenv()


class Settings:

    DEBUG = os.getenv("DEBUG", "True") == "True"

    FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY")

    WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

    NEWS_API_KEY = os.getenv("NEWS_API_KEY")

    ODDS_API_KEY = os.getenv("ODDS_API_KEY")

    # Domestic league season, e.g. 2025 = the 2025-26 campaign.
    # Bump this to 2026 once domestic leagues restart around Aug 2026.
    CURRENT_SEASON = int(os.getenv("CURRENT_SEASON", "2025"))

    # International tournaments (World Cup, Euro, Nations League, AFCON)
    # run on the calendar year they're played in, not the domestic
    # season convention above.
    INTERNATIONAL_SEASON = int(os.getenv("INTERNATIONAL_SEASON", "2026"))


settings = Settings()
