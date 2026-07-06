import requests
from datetime import date


class FootballProvider:

    BASE_URL = "https://v3.football.api-sports.io"

    def __init__(self, api_key):

        self.api_key = api_key

    def get_today_fixtures(self):

        today = date.today().strftime("%Y-%m-%d")

        response = requests.get(
            f"{self.BASE_URL}/fixtures",
            headers={
                "x-apisports-key": self.api_key
            },
            params={
                "date": today
            },
            timeout=20,
            verify=False
        )

        response.raise_for_status()

        data = response.json()

        return data["response"]
