import subprocess
import json


class OpenFootballProvider:
    """
    Wrapper around the openfootball project's raw JSON files on GitHub.
    Public domain (CC0), no API key, no rate limit, no bot protection —
    it's just static files on GitHub. Community-maintained (mostly by one
    person plus contributors), so treat it as good-but-not-guaranteed:
    top leagues/tournaments are kept current, smaller ones may lag.
    """

    RAW_BASE = "https://raw.githubusercontent.com/openfootball"

    def _fetch_raw_json(self, repo: str, path: str):
        url = f"{self.RAW_BASE}/{repo}/master/{path}"

        command = [
            "/usr/bin/curl",
            "--silent",
            "--show-error",
            "--location",
            "--http1.1",
            "--connect-timeout", "20",
            "--max-time", "60",
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

        stripped = result.stdout.strip()
        if stripped.startswith("404:") or stripped == "404: Not Found":
            raise FileNotFoundError(f"No file at {url}")

        try:
            return json.loads(result.stdout)
        except Exception:
            raise RuntimeError(f"Invalid JSON at {url}:\n\n{result.stdout[:300]}")

    def get_league_season(self, season: str, country_division_code: str) -> dict:
        """
        e.g. get_league_season('2025-26', 'en.1') for Premier League
        """
        return self._fetch_raw_json("football.json", f"{season}/{country_division_code}.json")

    def get_worldcup(self, year: str) -> dict:
        """
        e.g. get_worldcup('2026')
        """
        return self._fetch_raw_json("worldcup.json", f"{year}/worldcup.json")

    def try_fetch(self, repo: str, path: str):
        """
        Best-effort fetch that returns None instead of raising, for probing
        whether a given dataset exists without crashing a diagnostic run.
        """
        try:
            return self._fetch_raw_json(repo, path)
        except Exception as e:
            return {"_error": str(e)}
