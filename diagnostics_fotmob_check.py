import json
from datetime import date, timedelta
from api.fotmob_provider import FotMobProvider


def preview(label, data, limit=1500):
    text = json.dumps(data, indent=2)[:limit]
    print(f"\n--- {label} ---")
    print(text)
    print("...")


def main():
    provider = FotMobProvider()

    today = date.today().strftime("%Y%m%d")
    tomorrow = (date.today() + timedelta(days=1)).strftime("%Y%m%d")

    print(f"=== Fetching FotMob matches for {today} ===")
    data = provider.get_matches_by_date(today)

    leagues = data.get("leagues", [])
    print(f"Leagues returned: {len(leagues)}")

    if not leagues:
        print("No leagues/matches returned for today — trying tomorrow instead.")
        data = provider.get_matches_by_date(tomorrow)
        leagues = data.get("leagues", [])
        print(f"Leagues returned for tomorrow: {len(leagues)}")

    # Look specifically for competitions your APIs don't cover
    target_keywords = ["champions league", "europa", "conference league", "friendl", "qualif"]

    interesting = [
        lg for lg in leagues
        if any(kw in (lg.get("name", "") or "").lower() for kw in target_keywords)
    ]

    print(f"\nLeagues matching CL/EL/ECL/friendly/qualifier keywords: {len(interesting)}")
    for lg in interesting[:5]:
        print(f" - {lg.get('name')} (id={lg.get('id')}), matches: {len(lg.get('matches', []))}")

    if interesting:
        preview("First matching league's raw payload", interesting[0])
    elif leagues:
        preview("First league found (no keyword match) — raw payload", leagues[0])
    else:
        print("Nothing returned at all — endpoint may be blocked, changed, or down.")


if __name__ == "__main__":
    main()
