from dotenv import load_dotenv
import os

load_dotenv()


class Settings:

    DEBUG = os.getenv("DEBUG", "True") == "True"

    FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY")
    FOOTBALL_DATA_ORG_API_KEY = os.getenv("FOOTBALL_DATA_ORG_API_KEY")

    WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
    NEWS_API_KEY = os.getenv("NEWS_API_KEY")
    ODDS_API_KEY = os.getenv("ODDS_API_KEY")

    CURRENT_SEASON = int(os.getenv("CURRENT_SEASON", "2025"))
    INTERNATIONAL_SEASON = int(os.getenv("INTERNATIONAL_SEASON", "2026"))


settings = Settings()
