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
            "--http1.1",
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
            raise RuntimeError(
                f"Curl failed.\n"
                f"Exit Code: {result.returncode}\n\n"
                f"STDERR:\n{result.stderr}"
            )

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            raise RuntimeError("Invalid JSON returned from API.")

    def get_today_fixtures(self):

        today = date.today().strftime("%Y-%m-%d")

        data = self._curl_request(
            "fixtures",
            {
                "date": today
            }
        )

        return data.get("response", [])

    def get_standings(self, league_id, season):

        data = self._curl_request(
            "standings",
            {
                "league": league_id,
                "season": season
            }
        )

        return data.get("response", [])

    def get_status(self):

        return self._curl_request("status")
