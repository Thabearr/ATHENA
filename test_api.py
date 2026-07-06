import httpx

API_KEY = "bb7c70d58a3c8d5301d3aabb62d39042"

headers = {
    "x-apisports-key": API_KEY
}

try:
    with httpx.Client(
        http2=False,
        verify=True,
        timeout=20
    ) as client:

        r = client.get(
            "https://v3.football.api-sports.io/status",
            headers=headers
        )

        print(r.status_code)
        print(r.text)

except Exception as e:
    print(type(e))
    print(e)
