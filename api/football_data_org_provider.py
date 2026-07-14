import subprocess
import json


class FootballDataOrgProvider:

    BASE_URL = "https://api.football-data.org/v4"

    def __init__(self, api_key):
        if not api_key:
            raise RuntimeError("FOOTBALL_DATA_ORG_API_KEY not found in environment.")
        self.api_key = api_key.strip()

    def _curl_request(self, path, params=None):
        url = f"{self.BASE_URL}{path}"

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
            "--connect-timeout", "20",
            "--max-time", "60",
            "--retry", "3",
            "--retry-delay", "2",
            "--header", f"X-Auth-Token: {self.api_key}",
            url,
        ]

        result = subprocess.run(command, capture_output=True, text=True)

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
            raise RuntimeError(f"Invalid JSON returned:\n\n{result.stdout}")

        if isinstance(data, dict) and data.get("errorCode"):
            raise RuntimeError(f"API Error: {data.get('message', data)}")

        return data

    def get_available_competitions(self):
        data = self._curl_request("/competitions")
        return data.get("competitions", [])

    def get_matches(self, competition_code, date_from=None, date_to=None, status=None):
        params = {}
        if date_from:
            params["dateFrom"] = date_from
        if date_to:
            params["dateTo"] = date_to
        if status:
            params["status"] = status

        data = self._curl_request(f"/competitions/{competition_code}/matches", params)
        return data.get("matches", [])
