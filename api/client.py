import httpx


class APIClient:
    def __init__(self, api_key: str):
        self.client = httpx.Client(
            headers={
                "x-apisports-key": api_key
            },
            timeout=20
        )

    def get(self, url, params=None):
        response = self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()
