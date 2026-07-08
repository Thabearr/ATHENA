import json
import pycurl
from io import BytesIO
from datetime import date


class FootballProvider:

    BASE_URL = "https://v3.football.api-sports.io"

    def __init__(self, api_key):
        self.api_key = api_key

    def _request(self, endpoint, params=None):

        url = f"{self.BASE_URL}/{endpoint}"

        if params:
            query = "&".join(
                f"{k}={v}" for k, v in params.items()
            )
            url = f"{url}?{query}"

        buffer = BytesIO()

        curl = pycurl.Curl()

        curl.setopt(curl.URL, url)
        curl.setopt(curl.HTTPHEADER, [
            f"x-apisports-key: {self.api_key}"
        ])

        curl.setopt(curl.WRITEDATA, buffer)

        # SSL
        curl.setopt(curl.SSL_VERIFYPEER, 1)
        curl.setopt(curl.SSL_VERIFYHOST, 2)

        # Timeouts
        curl.setopt(curl.CONNECTTIMEOUT, 20)
        curl.setopt(curl.TIMEOUT, 60)

        # Compression
        curl.setopt(curl.ACCEPT_ENCODING, "")

        try:
            curl.perform()

            status = curl.getinfo(pycurl.RESPONSE_CODE)

            if status != 200:
                raise RuntimeError(f"HTTP {status}")

            body = buffer.getvalue().decode("utf-8")

            return json.loads(body)

        finally:
            curl.close()

    def get_today_fixtures(self):

        today = date.today().strftime("%Y-%m-%d")

        data = self._request(
            "fixtures",
            {
                "date": today
            }
        )

        return data.get("response", [])

    def get_status(self):

        return self._request("status")
