import httpx
from datetime import date


class FootballProvider:

    BASE_URL = "https://v3.football.api-sports.io"

    def __init__(self, api_key):

        self.api_key = api_key

        self.client = httpx.Client(
            headers={
                "x-apisports-key": self.api_key,
                "Accept": "application/json",
                "User-Agent": "ATHENA/0.1"
            },
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
            http2=False
        )

    def get_today_fixtures(self):

        today = date.today().strftime("%Y-%m-%d")

        try:

            response = self.client.get(
                f"{self.BASE_URL}/fixtures",
                params={
                    "date": today
                }
            )

            print("Status Code:", response.status_code)

            response.raise_for_status()

            data = response.json()

            if "response" not in data:
                raise Exception(f"Unexpected API response: {data}")

            return data["response"]

        except Exception as e:
            print("Football API Error:", e)
            raise
