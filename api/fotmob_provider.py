import subprocess
import json


class FotMobProvider:
    """
    Wrapper around FotMob's UNOFFICIAL, undocumented internal API.
    Not affiliated with FotMob, no support contract, no rate-limit
    guarantee, can change or break without notice. Used here to cover
    friendlies, CL/EL/ECL qualifying rounds, and other matches the
    official paid/free data sources (API-Football, football-data.org)
    don't track.

    Every match this returns should be tagged data_source='fotmob_unofficial'
    downstream so it's never confused with a supported, contracted source.
    """

    BASE_URL = "https://www.fotmob.com/api"

    def _curl_request(self, path, params=None):
        url = f"{self.BASE_URL}/{path}"

        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            url += f"?{query}"

        command = [
            "/usr/bin/curl",
            "--silent",
            "--show-error",
            "--location",
            "--http1.1",
            "--connect-timeout", "20",
            "--max-time", "60",
            "--header", "User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "--header", "Accept: application/json",
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
            return json.loads(result.stdout)
        except Exception:
            raise RuntimeError(f"Invalid JSON returned (endpoint may have changed):\n\n{result.stdout[:500]}")

    def get_matches_by_date(self, date_str_yyyymmdd: str) -> dict:
        """
        date_str_yyyymmdd: e.g. '20260716'
        Returns the raw response: {"leagues": [...], "date": "..."}
        """
        return self._curl_request("matches", {"date": date_str_yyyymmdd})
