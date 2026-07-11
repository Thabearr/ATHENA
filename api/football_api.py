import json
import subprocess
import time
from datetime import date


class FootballProvider:

    BASE_URL = "https://v3.football.api-sports.io"

    def __init__(self, api_key):

        if not api_key:
            raise RuntimeError("FOOTBALL_API_KEY is missing.")

        self.api_key = api_key.strip()

    def _curl_request(self, endpoint, params=None):

        url = f"{self.BASE_URL}/{endpoint}"

        if params:
            query = "&".join(
                f"{k}={v}"
                for k, v in params.items()
            )
            url += f"?{query}"

        command = [

            "/usr/bin/curl",

            "--silent",
            "--show-error",
            "--location",
            "--http1.1",
            "--compressed",

            "--connect-timeout", "30",
            "--max-time", "90",

            "--retry", "5",
            "--retry-delay", "2",
            "--retry-all-errors",

            "--header",
            f"x-apisports-key: {self.api_key}",

            url

        ]

        last_error = None

        for attempt in range(5):

            result = subprocess.run(
                command,
                capture_output=True,
                text=True
            )

            if result.returncode == 0:

                try:

                    data = json.loads(result.stdout)

                except json.JSONDecodeError:

                    raise RuntimeError(
                        f"Invalid JSON returned.\n\n"
                        f"{result.stdout[:1000]}"
                    )

                if data.get("errors"):

                    raise RuntimeError(
                        f"API Error: {data['errors']}"
                    )

                return data

            last_error = result

            time.sleep(2 ** attempt)

        raise RuntimeError(

            f"Curl failed after 5 attempts.\n\n"

            f"Exit Code: {last_error.returncode}\n\n"

            f"STDOUT:\n{last_error.stdout}\n\n"

            f"STDERR:\n{last_error.stderr}"

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
