import subprocess
import json
from datetime import date


class FootballProvider:

    BASE_URL = "https://v3.football.api-sports.io"

    def __init__(self, api_key):
        self.api_key = api_key.strip()

    def _curl_request(self, endpoint, params=None):

        url = f"{self.BASE_URL}/{endpoint}"

        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            url += f"?{query}"

        command = [
            "/usr/bin/curl",
            "--silent",
            "--show-error",
            "--location",
            "--http1.1",
            "--compressed",
            "--connect-timeout", "30",
            "--max-time", "60",
            "--retry", "3",
            "--retry-delay", "2",
            "--header", f"x-apisports-key: {self.api_key}",
            url,
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Curl failed.\n"
                f"Exit Code: {result.returncode}\n"
                f"STDOUT:\n{result.stdout}\n\n"
                f"STDERR:\n{result.stderr}"
            )

        try:
            data = json.loads(result.stdout)
        except Exception:
            raise RuntimeError(
                f"Invalid JSON:\n{result.stdout[:1000]}"
            )

        if data.get("errors"):
            raise RuntimeError(
                f"API Error: {data['errors']}"
            )

        return data

    # -------------------------------------------------
    # Today's Fixtures
    # -------------------------------------------------

    def get_today_fixtures(self):

        today = date.today().strftime("%Y-%m-%d")

        return self._curl_request(
            "fixtures",
            {
                "date": today
            }
        ).get("response", [])

    # -------------------------------------------------
    # League Standings
    # -------------------------------------------------

    def get_standings(self, league_id, season):

        return self._curl_request(
            "standings",
            {
                "league": league_id,
                "season": season,
            },
        ).get("response", [])

    # -------------------------------------------------
    # Last Matches For One Team
    # -------------------------------------------------

    def get_team_last_matches(self, team_id, last=5):

        return self._curl_request(
            "fixtures",
            {
                "team": team_id,
                "last": last,
            },
        ).get("response", [])

    # -------------------------------------------------
    # Team Statistics
    # -------------------------------------------------

    def get_team_statistics(self, league_id, season, team_id):

        return self._curl_request(
            "teams/statistics",
            {
                "league": league_id,
                "season": season,
                "team": team_id,
            },
        ).get("response", {})

    # -------------------------------------------------
    # API Status
    # -------------------------------------------------

    def get_status(self):

        return self._curl_request("status")
