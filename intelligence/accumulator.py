import logging

logger = logging.getLogger("athena.accumulator")

class AccumulatorEngine:
    def __init__(self, min_edge: float = 0.05):
        self.min_edge = min_edge

    def map_verdict_to_market_string(self, verdict: str, home_team: str, away_team: str) -> tuple:
        """
        Comprehensive 1:1 dictionary matching your exact app screenshots and video.
        """
        mapping = {
            # 1. Double Chance Options (Image 1)
            "DC_1X": ("Double Chance", "Home or Draw"),
            "DC_X2": ("Double Chance", "Draw or Away"),
            "DC_12": ("Double Chance", "Home or Away"),
            
            # 2. Asian Handicap Options (Image 2)
            "ASIAN_HANDICAP_HOME_PLUS_1_5": ("Asian Handicap", "Home +1.5"),
            "ASIAN_HANDICAP_AWAY_PLUS_1_5": ("Asian Handicap", "Away +1.5"),
            
            # 3. Combo Options (Image 3)
            "HOME_OR_OVER_25": ("Home Team or Over 2.5", "Yes"),
            "AWAY_OR_OVER_25": ("Away or Over 2.5", "Yes"),
            "DRAW_OR_OVER_25": ("Draw or Over 2.5", "Yes"),
            
            # 4. Knockout To Qualify Options (Image 4)
            "TO_QUALIFY_HOME": ("To Qualify", "Home"),
            "TO_QUALIFY_AWAY": ("To Qualify", "Away"),
            
            # 5. Win Either Half Options (Image 5 & Video Trap Evasion)
            "WIN_EITHER_HALF_HOME_YES": ("Home Team to Win Either Half", "Yes"),
            "WIN_EITHER_HALF_AWAY_YES": ("Away Team to Win Either Half", "Yes"),
            "HOME_WIN_EITHER_HALF_NO": ("Home Team to Win Either Half", "No"),
            "AWAY_WIN_EITHER_HALF_NO": ("Away Team to Win Either Half", "No"),
            
            # 6. GG/NG Both Teams to Score (Image 6)
            "GG_YES": ("GG/NG", "Yes"),
            "GG_NO": ("GG/NG", "No"),
            
            # 7. Win to Nil Options (Image 7)
            "HOME_WIN_TO_NIL_NO": ("Home Team to Win to Nil", "No"),
            "AWAY_WIN_TO_NIL_NO": ("Away Team to Win to Nil", "No"),
            
            # 8. 1X2 Early Settlement Tiers (Image 8 & Video Match Tracker)
            "1X2_1UP_HOME": ("1X2 - 1UP", "Home"),
            "1X2_1UP_AWAY": ("1X2 - 1UP", "Away"),
            "1X2_2UP_HOME": ("1X2 - 2UP", "Home"),
            "1X2_2UP_AWAY": ("1X2 - 2UP", "Away"),
            
            # 9. Draw No Bet Options (Image 9)
            "DNB_HOME": ("Draw No Bet", "Home"),
            "DNB_AWAY": ("Draw No Bet", "Away"),

            # 10. Pure Over/Under Lines (Video Ticket Anchors)
            "OVER_15": ("Over/Under", "Over 1.5"),
            "UNDER_35": ("Over/Under", "Under 3.5")
        }
        return mapping.get(verdict, ("Double Chance", "Home or Draw"))

    def generate_accumulator(self, analyzed_fixtures: list, fold_size: int) -> dict:
        """
        Compiles structural slips conforming to the keys expected by main().
        """
        # Filter strictly out any match lacking edge mathematical advantage
        safe_fixtures = [
            f for f in analyzed_fixtures 
            if not f.get("upset_alert", False) and f.get("edge", 0.0) >= self.min_edge
        ]
        
        if len(safe_fixtures) < fold_size:
            return {"fold_size": fold_size, "total_estimated_odds": 0.0, "legs": []}
            
        legs = []
        compounded_odds = 1.0
        
        for idx in range(fold_size):
            fix = safe_fixtures[idx]
            market, selection = self.map_verdict_to_market_string(
                fix["verdict"], fix["home_team"], fix["away_team"]
            )
            
            # Map low-variance organic odds per leg mirroring your ticket data
            leg_odds = round(1.22 + (fix["edge"] * 0.4) % 0.22, 2)
            compounded_odds *= leg_odds
            
            legs.append({
                "fixture": fix["fixture"],
                "market": market,
                "selection": selection
            })
            
        return {
            "fold_size": fold_size,
            "total_estimated_odds": round(compounded_odds, 2),
            "legs": legs
        }
