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
            query = "&".join(
                f"{k}={v}" for k, v in params.items()
            )
            url += "?" + query

        command = [
            "curl",
            "-v",
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

        print("\n========== CURL COMMAND ==========")
        print(" ".join(command))

        print("\n========== RETURN CODE ==========")
        print(result.returncode)

        print("\n========== STDOUT ==========")
        print(result.stdout[:1000])

        print("\n========== STDERR ==========")
        print(result.stderr[:1000])

        if result.returncode != 0:
            raise RuntimeError(
                f"Curl failed with code {result.returncode}"
            )

        data = json.loads(result.stdout)

        return data

    def get_today_fixtures(self):

        today = date.today().strftime("%Y-%m-%d")

        data = self._curl_request(
            "fixtures",
            {"date": today}
        )

        return data.get("response", [])

    def get_status(self):
        return self._curl_request("status")
