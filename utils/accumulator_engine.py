import logging

logger = logging.getLogger("athena.accumulator_engine")

class AccumulatorEngine:
    def __init__(self):
        pass

    def map_verdict_to_market_string(self, verdict: str, home_team: str, away_team: str) -> tuple:
        mapping = {
            # Double Chance
            "DC_1X": ("Double Chance", "Home or Draw"),
            "DC_X2": ("Double Chance", "Draw or Away"),
            "DC_12": ("Double Chance", "Home or Away"),
            
            # Asian Handicap
            "ASIAN_HANDICAP_HOME_PLUS_1_5": ("Asian Handicap", "Home +1.5"),
            "ASIAN_HANDICAP_AWAY_PLUS_1_5": ("Asian Handicap", "Away +1.5"),
            
            # Combo Or Over 2.5
            "HOME_OR_OVER_25": ("Home Team or Over 2.5", "Yes"),
            "AWAY_OR_OVER_25": ("Away or Over 2.5", "Yes"),
            "DRAW_OR_OVER_25": ("Draw or Over 2.5", "Yes"),
            
            # Pure Over/Under (Video Anchors)
            "OVER_15": ("Over/Under", "Over 1.5"),
            "UNDER_35": ("Over/Under", "Under 3.5"),
            
            # To Qualify
            "TO_QUALIFY_HOME": ("To Qualify", f"Home"),
            "TO_QUALIFY_AWAY": ("To Qualify", f"Away"),
            
            # Win Either Half
            "WIN_EITHER_HALF_HOME_YES": ("Home Team to Win Either Half", "Yes"),
            "WIN_EITHER_HALF_AWAY_YES": ("Away Team to Win Either Half", "Yes"),
            "HOME_WIN_EITHER_HALF_NO": ("Home Team to Win Either Half", "No"),
            "AWAY_WIN_EITHER_HALF_NO": ("Away Team to Win Either Half", "No"),
            
            # GG/NG
            "GG_YES": ("GG/NG", "Yes"),
            "GG_NO": ("GG/NG", "No"),
            
            # Win to Nil
            "HOME_WIN_TO_NIL_NO": ("Home Team to Win to Nil", "No"),
            "AWAY_WIN_TO_NIL_NO": ("Away Team to Win to Nil", "No"),
            
            # 1X2 Early Settlement
            "1X2_1UP_HOME": ("1X2 - 1UP", "Home"),
            "1X2_1UP_AWAY": ("1X2 - 1UP", "Away"),
            "1X2_2UP_HOME": ("1X2 - 2UP", "Home"),
            "1X2_2UP_AWAY": ("1X2 - 2UP", "Away"),
            
            # Draw No Bet
            "DNB_HOME": ("Draw No Bet", "Home"),
            "DNB_AWAY": ("Draw No Bet", "Away"),
        }
        
        return mapping.get(verdict, ("Double Chance", "Home or Draw"))

    def build_accumulators(self, analyzed_fixtures: list) -> dict:
        safe_fixtures = [f for f in analyzed_fixtures if not f.get("upset_alert", False)]
        
        slips = {5: [], 10: [], 20: [], 30: []}
        sizes = [5, 10, 20, 30]
        
        for size in sizes:
            if len(safe_fixtures) >= size:
                for idx in range(size):
                    fix = safe_fixtures[idx]
                    market, selection = self.map_verdict_to_market_string(
                        fix["verdict"], fix["home_team"], fix["away_team"]
                    )
                    slips[size].append({
                        "fixture": fix["fixture"],
                        "market": market,
                        "selection": selection
                    })
        return slips
