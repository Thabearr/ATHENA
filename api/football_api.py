import subprocess
import json
from datetime import date


class FootballProvider:

    BASE_URL = "https://v3.football.api-sports.io"

    def __init__(self, api_key):
        self.api_key = api_key

    def _curl_request(self, endpoint, params=None):

        url = f"{self.BASE_URL}/{endpoint}"

        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{url}?{query}"

        command = [
            "curl",
            "-s",
            "-L",
            url,
            "-H",
            f"x-apisports-key: {self.api_key}"
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(
                f"Invalid JSON received:\n{result.stdout}"
            )

    def get_today_fixtures(self):

        today = date.today().strftime("%Y-%m-%d")

        data = self._curl_request(
            "fixtures",
            {
                "date": today
            }
        )

        return data.get("response", [])

    def get_status(self):

        return self._curl_request("status")
