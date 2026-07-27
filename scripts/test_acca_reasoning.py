import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from build_acca import AccaBuilder

def test_pipeline():
    print("=== TESTING ATHENA FULL REASONING PIPELINE ===")
    builder = AccaBuilder()
    result = builder.build(days=2, fold_size=5, strict=True)
    
    if not result.get("success"):
        print("Generation failed:", result.get("error"))
        return

    print(f"\nGenerated Accumulator with {len(result['legs'])} legs:")
    print(f"Total Odds: {result['total_estimated_odds']}")
    print(f"Total Kelly Stake: {result['kelly_stake_pct']}%")
    print(f"Diversification Score: {result['diversification_score']}%")
    print("=" * 60)

    for i, leg in enumerate(result['legs'], 1):
        league_name = leg.get('league') or leg.get('league_name') or 'Unknown League'
        print(f"\nLeg {i}: {leg.get('fixture', 'Fixture')} ({league_name})")
        print(f"  Selection: {leg['selection']} | Market: {leg['market']} | Odds: {leg['odds']}")
        print(f"  Analyst Edge: {leg['edge']}")
        if "reasoning_verdicts" in leg:
            print("  Reasoning Traces:")
            for v in leg["reasoning_verdicts"]:
                print(f"    [{v['status']:9s}] {v['reason']}")

if __name__ == "__main__":
    test_pipeline()
