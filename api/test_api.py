import httpx

API_KEY = "bb7c70d58a3c8d5301d3aabb62d39042"

headers = {
    "x-apisports-key": API_KEY
}

try:
    response = httpx.get(
        "https://v3.football.api-sports.io/status",
        headers=headers,
        timeout=20
    )

    print(response.status_code)
    print(response.text)

except Exception as e:
    print(e)
