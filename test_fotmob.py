"""Phase 9: Extract full match structure and test matchDetails."""
from workers.fotmob_bypass_client import FotmobBypassClient
import json

def probe():
    client = FotmobBypassClient()
    
    # Get today's matches
    r = client.session.get("https://www.fotmob.com/api/data/matches?date=20260721", headers=client._get_headers(), timeout=15)
    data = r.json()
    leagues = data.get("leagues", [])
    print(f"Total leagues: {len(leagues)}")
    
    # Print all leagues and their match counts
    first_match_id = None
    for league in leagues:
        matches = league.get("matches", [])
        print(f"  {league['name']} ({league['ccode']}): {len(matches)} matches")
        if matches and not first_match_id:
            first_match_id = matches[0].get("id")
            # Print first match structure
            m = matches[0]
            print(f"\n  === SAMPLE MATCH STRUCTURE ===")
            print(f"  {json.dumps(m, indent=2)[:1500]}")
            print(f"  ==============================\n")
    
    # Try to get match details
    if first_match_id:
        print(f"\n=== Match Details for ID {first_match_id} ===")
        detail_url = f"https://www.fotmob.com/api/data/matchDetails?matchId={first_match_id}"
        r2 = client.session.get(detail_url, headers=client._get_headers(), timeout=15)
        print(f"Status: {r2.status_code}")
        if r2.status_code == 200:
            detail = r2.json()
            if isinstance(detail, dict):
                print(f"Top keys: {list(detail.keys())[:15]}")
                for k in list(detail.keys())[:8]:
                    v = detail[k]
                    if isinstance(v, dict):
                        print(f"  {k}: dict keys={list(v.keys())[:10]}")
                    elif isinstance(v, list):
                        print(f"  {k}: list[{len(v)}]")
                    elif isinstance(v, (str, int, float, bool)) or v is None:
                        print(f"  {k}: {str(v)[:100]}")

if __name__ == "__main__":
    probe()
