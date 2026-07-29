import time
from datetime import date

from api.curl_json_client import (
    CurlJsonClient,
    bounded_sanitized_excerpt,
)


class FootballProvider:

    BASE_URL = "https://v3.football.api-sports.io"

    def __init__(self, api_key):

        if not api_key:
            raise RuntimeError(
                "FOOTBALL_API_KEY not found in environment."
            )

        self.api_key = api_key.strip()
        self.curl_client = CurlJsonClient()
        self.curl_executable = self.curl_client.executable

    # --------------------------------------------------
    # Internal CURL Request
    # --------------------------------------------------

    def _single_curl_attempt(self, url):
        data = self.curl_client.request_json(
            url,
            headers={"x-apisports-key": self.api_key},
        )

        if isinstance(data, dict) and data.get("errors"):
            message = bounded_sanitized_excerpt(
                data["errors"],
                sensitive_values=(self.api_key,),
            )
            raise RuntimeError(
                f"API Error: {message}"
            )

        return data

    def _curl_request(self, endpoint, params=None, max_retries: int = 2):

        url = f"{self.BASE_URL}/{endpoint}"

        if params:
            query = "&".join(
                f"{k}={v}" for k, v in params.items()
            )
            url += f"?{query}"

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return self._single_curl_attempt(url)
            except RuntimeError as e:
                last_error = e
                if attempt < max_retries:
                    time.sleep(3)
                continue

        raise last_error

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
    # Fixtures by league / season / date range
    # --------------------------------------------------

    def get_fixtures_by_league(self, league_id, season, date_from=None, date_to=None):

        params = {
            "league": league_id,
            "season": season,
        }

        if date_from:
            params["from"] = date_from
        if date_to:
            params["to"] = date_to

        return self._curl_request("fixtures", params).get("response", [])

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
