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
            url += "?" + query

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

        # If we received JSON, use it regardless of curl's exit code.
        if result.stdout.strip():
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                pass

        raise RuntimeError(
            f"Curl failed.\nExit Code: {result.returncode}\n\nSTDERR:\n{result.stderr}"
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
