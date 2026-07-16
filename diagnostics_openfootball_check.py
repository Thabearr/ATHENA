from api.openfootball_provider import OpenFootballProvider


def summarize(label, data):
    print(f"\n--- {label} ---")
    if isinstance(data, dict) and "_error" in data:
        print(f"NOT FOUND / ERROR: {data['_error']}")
        return
    name = data.get("name", "?")
    matches = data.get("matches", [])
    print(f"name: {name}")
    print(f"match count: {len(matches)}")
    if matches:
        print(f"sample match: {matches[0]}")


def main():
    provider = OpenFootballProvider()

    summarize("Premier League 2025-26", provider.try_fetch("football.json", "2025-26/en.1.json"))
    summarize("World Cup 2026", provider.try_fetch("worldcup.json", "2026/worldcup.json"))

    candidates = [
        ("football.json", "2024-25/uefa.cl.json"),
        ("football.json", "2025-26/uefa.cl.json"),
        ("football.json", "2025-26/uefa.el.json"),
    ]
    for repo, path in candidates:
        summarize(f"Probe: {repo}/{path}", provider.try_fetch(repo, path))


if __name__ == "__main__":
    main()
