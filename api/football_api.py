import httpx
from datetime import date


class FootballProvider:

    BASE_URL = "https://v3.football.api-sports.io"

    def __init__(self, api_key):

        self.client = httpx.Client(
            headers={
                "x-apisports-key": api_key
            },
            timeout=20
        )

    def get_today_fixtures(self):

        today = date.today().strftime("%Y-%m-%d")

        response = self.client.get(
            f"{self.BASE_URL}/fixtures",
            params={
                "date": today
            }
        )

        response.raise_for_status()

        data = response.json()

        return data["response"]
