import subprocess
import json
import re
import time


class FootballDataOrgProvider:

    BASE_URL = "https://api.football-data.org/v4"

    def __init__(self, api_key):
        if not api_key:
            raise RuntimeError("FOOTBALL_DATA_ORG_API_KEY not found in environment.")
        self.api_key = api_key.strip()

    def _single_curl_attempt(self, url):
        command = [
            "/usr/bin/curl",
            "--silent",
            "--show-error",
            "--location",
            "--http1.1",
            "--compressed",
            "--connect-timeout", "20",
            "--max-time", "60",
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

        return result.stdout

    def _curl_request(self, path, params=None, max_retries: int = 3):
        url = f"{self.BASE_URL}{path}"

        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            url += f"?{query}"

        attempts = 0
        while True:
            attempts += 1
            raw = self._single_curl_attempt(url)

            try:
                data = json.loads(raw)
            except Exception:
                raise RuntimeError(f"Invalid JSON returned:\n\n{raw}")

            if isinstance(data, dict) and data.get("errorCode") == 429:
                if attempts > max_retries:
                    raise RuntimeError(f"Rate limited after {max_retries} retries: {data}")

                match = re.search(r"Wait (\d+) seconds", data.get("message", ""))
                wait_seconds = int(match.group(1)) if match else 10
                time.sleep(wait_seconds + 1)
                continue

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
