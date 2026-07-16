from api.openfootball_provider import OpenFootballProvider


def summarize(label, data):
    if isinstance(data, dict) and "_error" in data:
        print(f"{label}: NOT FOUND")
        return
    name = data.get("name", "?")
    matches = data.get("matches", [])
    print(f"{label}: FOUND — '{name}', {len(matches)} matches")
    if matches:
        print(f"    sample: {matches[0]}")


def main():
    provider = OpenFootballProvider()

    # Confirmed working, for reference
    print("=== CONFIRMED WORKING (sanity check) ===")
    summarize("Premier League 2025-26 (en.1)", provider.try_fetch("football.json", "2025-26/en.1.json"))

    print("\n=== PROBING THE 14 CURRENTLY-STALE LEAGUES ===")
    candidates = {
        "Turkey": "tr.1",
        "Belgium": "be.1",
        "Switzerland": "ch.1",
        "Scotland (guess 1)": "sco.1",
        "Scotland (guess 2)": "gb-sct.1",
        "Norway": "no.1",
        "Sweden": "se.1",
        "Denmark": "dk.1",
        "Austria": "at.1",
        "Greece": "gr.1",
        "Czech Republic": "cz.1",
        "Croatia": "hr.1",
        "Serbia": "rs.1",
        "Poland": "pl.1",
        "Romania": "ro.1",
    }

    for label, code in candidates.items():
        summarize(f"{label} ({code})", provider.try_fetch("football.json", f"2025-26/{code}.json"))


if __name__ == "__main__":
    main()
