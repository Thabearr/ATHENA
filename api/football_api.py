import subprocess
import json
from datetime import date


class FootballProvider:

    BASE_URL = "https://v3.football.api-sports.io"

    def __init__(self, api_key):

        if not api_key:
            raise RuntimeError(
                "FOOTBALL_API_KEY not found in environment."
            )

        self.api_key = api_key.strip()

    # --------------------------------------------------
    # Internal CURL Request
    # --------------------------------------------------

    def _curl_request(self, endpoint, params=None):

        url = f"{self.BASE_URL}/{endpoint}"

        if params:
            query = "&".join(
                f"{k}={v}" for k, v in params.items()
            )
            url += f"?{query}"

        command = [

            "/usr/bin/curl",

            "--silent",
            "--show-error",
            "--location",

            "--http1.1",

            "--compressed",

            "--connect-timeout", "20",

            "--max-time", "60",

            "--retry", "3",

            "--retry-delay", "2",

            "--header",
            f"x-apisports-key: {self.api_key}",

            url,

        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:

            raise RuntimeError(
                "Curl failed.\n"
                f"Exit Code: {result.returncode}\n"
                f"STDOUT:\n{result.stdout}\n\n"
                f"STDERR:\n{result.stderr}"
            )

        try:

            data = json.loads(result.stdout)

        except Exception:

            raise RuntimeError(
                f"Invalid JSON returned:\n\n{result.stdout}"
            )

        if data.get("errors"):

            raise RuntimeError(
                f"API Error: {data['errors']}"
            )

        return data

    # --------------------------------------------------
    # Status
    # --------------------------------------------------

    def get_status(self):

        return self._curl_request("status")

    # --------------------------------------------------
    # Fixtures
    # --------------------------------------------------

    def get_today_fixtures(self):

        today = date.today().strftime("%Y-%m-%d")

        return self._curl_request(

            "fixtures",

            {
                "date": today
            }

        ).get("response", [])

    # --------------------------------------------------
    # Standings
    # --------------------------------------------------

    def get_standings(
        self,
        league_id,
        season,
    ):

        return self._curl_request(

            "standings",

            {
                "league": league_id,
                "season": season,
            }

        ).get("response", [])

    # --------------------------------------------------
    # Team Statistics
    # --------------------------------------------------

    def get_team_statistics(
        self,
        league_id,
        season,
        team_id,
    ):

        return self._curl_request(

            "teams/statistics",

            {
                "league": league_id,
                "season": season,
                "team": team_id,
            }

        ).get("response", [])

    # --------------------------------------------------
    # Head To Head
    # --------------------------------------------------

    def get_head_to_head(
        self,
        home_team_id,
        away_team_id,
        last=10,
    ):

        return self._curl_request(

            "fixtures/headtohead",

            {
                "h2h": f"{home_team_id}-{away_team_id}",
                "last": last,
            }

        ).get("response", [])

    # --------------------------------------------------
    # Injuries
    # --------------------------------------------------

    def get_injuries(
        self,
        league_id,
        season,
        team_id,
    ):

        return self._curl_request(

            "injuries",

            {
                "league": league_id,
                "season": season,
                "team": team_id,
            }

        ).get("response", [])

    # --------------------------------------------------
    # Lineups
    # --------------------------------------------------

    def get_lineups(
        self,
        fixture_id,
    ):

        return self._curl_request(

            "fixtures/lineups",

            {
                "fixture": fixture_id,
            }

        ).get("response", [])

    # --------------------------------------------------
    # Statistics
    # --------------------------------------------------

    def get_fixture_statistics(
        self,
        fixture_id,
    ):

        return self._curl_request(

            "fixtures/statistics",

            {
                "fixture": fixture_id,
            }

        ).get("response", [])

    # --------------------------------------------------
    # Events
    # --------------------------------------------------

    def get_fixture_events(
        self,
        fixture_id,
    ):

        return self._curl_request(

            "fixtures/events",

            {
                "fixture": fixture_id,
            }

        ).get("response", [])

    # --------------------------------------------------
    # Odds
    # --------------------------------------------------

    def get_odds(
        self,
        fixture_id,
    ):

        return self._curl_request(

            "odds",

            {
                "fixture": fixture_id,
            }

        ).get("response", [])
