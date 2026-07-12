import logging

logger = logging.getLogger("athena.accumulator_engine")

class AccumulatorEngine:
    def __init__(self):
        pass

    def map_verdict_to_market_string(self, verdict: str, home_team: str, away_team: str) -> tuple:
        """
        Maps structural tokens strictly to the authorized application options.
        """
        mapping = {
            "1X2_1UP_HOME": ("1X2 - 1UP", f"{home_team} (Home)"),
            "1X2_1UP_AWAY": ("1X2 - 1UP", f"{away_team} (Away)"),
            "DNB_AWAY": ("Draw No Bet", f"{away_team}"),
            "DOUBLE_CHANCE_1X": ("Double Chance", "Home or Draw (1X)"),
            "TO_QUALIFY_HOME": ("To Qualify", f"{home_team} to Qualify"),
            "TO_QUALIFY_AWAY": ("To Qualify", f"{away_team} to Qualify"),
            "HOME_WIN_EITHER_HALF_YES": ("Home Team to Win Either Half", "Yes"),
            "HOME_WIN_TO_NIL": ("Home Team to Win to Nil", "Yes"),
            "HOME_OR_OVER_25": ("Home Team or Over 2.5", "Yes"),
            "ASIAN_HANDICAP_AWAY_PLUS_1_5": ("Asian Handicap", f"{away_team} (+1.5)"),
            "GG_YES": ("GG/NG", "GG (Yes)")
        }
        
        return mapping.get(verdict, ("Double Chance", "Home or Draw (1X)"))

    def build_accumulators(self, analyzed_fixtures: list) -> dict:
        slips = {5: [], 10: [], 20: [], 30: []}
        sizes = [5, 10, 20, 30]
        
        for size in sizes:
            if len(analyzed_fixtures) >= size:
                for idx in range(size):
                    fix = analyzed_fixtures[idx]
                    market, selection = self.map_verdict_to_market_string(
                        fix["verdict"], fix["home_team"], fix["away_team"]
                    )
                    slips[size].append({
                        "fixture": fix["fixture"],
                        "market": market,
                        "selection": selection
                    })
        return slips
