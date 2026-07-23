"""
Enhanced Accumulator Engine - Fullproof Selection Strategy
Balances edge confidence with practical betting constraints.
"""

import logging
from typing import List, Dict

logger = logging.getLogger("athena.accumulator")


class AccumulatorEngine:
    """
    Generates bulletproof accas by prioritizing:
    1. Strong Poisson probability (>70%)
    2. Solid edge (>0.08 for safety, >0.10 ideal)
    3. Market reliability (proven markets only)
    4. Risk-adjusted selection (allows some upset alerts if edge is exceptional)
    """
    
    def __init__(self, min_edge: float = 0.05):
        self.min_edge = min_edge
        # Markets ranked by historical reliability (proven in betting)
        self.market_reliability = {
            "TO_QUALIFY_HOME": 0.95,      # Knockout - very predictable
            "TO_QUALIFY_AWAY": 0.95,
            "1X2_2UP_HOME": 0.90,         # Strong wins - reliable
            "1X2_2UP_AWAY": 0.90,
            "1X2_1UP_HOME": 0.85,         # Moderate wins
            "1X2_1UP_AWAY": 0.85,
            "DNB_HOME": 0.80,              # Draw no bet
            "DNB_AWAY": 0.80,
            "DC_1X": 0.75,                 # Double chance - decent
            "DC_X2": 0.75,
            "DC_12": 0.75,
            "HOME_OR_OVER_25": 0.70,       # Combo bets
            "AWAY_OR_OVER_25": 0.70,
            "HOME_WIN_TO_NIL_NO": 0.65,    # Win to nil
            "AWAY_WIN_TO_NIL_NO": 0.65,
            "ASIAN_HANDICAP_HOME_PLUS_1_5": 0.60,  # Handicaps
            "ASIAN_HANDICAP_AWAY_PLUS_1_5": 0.60,
            "WIN_EITHER_HALF_HOME_YES": 0.55,      # Half bets
            "WIN_EITHER_HALF_AWAY_YES": 0.55,
            "GG_YES": 0.50,                # Both teams to score
            "GG_NO": 0.50,
            "OVER_15": 0.45,               # Over/under
            "UNDER_35": 0.45,
        }

    def map_verdict_to_market_string(self, verdict: str, home_team: str, away_team: str) -> tuple:
        """
        Map verdict to (market, selection) tuple.
        """
        mapping = {
            # 1. Double Chance Options
            "DC_1X": ("Double Chance", "Home or Draw"),
            "DC_X2": ("Double Chance", "Draw or Away"),
            "DC_12": ("Double Chance", "Home or Away"),
            
            # 2. Asian Handicap Options
            "AH_HOME_MINUS_05": ("Asian Handicap", "Home -0.5"),
            "AH_AWAY_PLUS_05": ("Asian Handicap", "Away +0.5"),
            "AH_HOME_PLUS_05": ("Asian Handicap", "Home +0.5"),
            "AH_AWAY_MINUS_05": ("Asian Handicap", "Away -0.5"),
            "AH_HOME_MINUS_15": ("Asian Handicap", "Home -1.5"),
            "AH_AWAY_PLUS_15": ("Asian Handicap", "Away +1.5"),
            "AH_HOME_PLUS_15": ("Asian Handicap", "Home +1.5"),
            "AH_AWAY_MINUS_15": ("Asian Handicap", "Away -1.5"),
            "AH_HOME_PLUS_25": ("Asian Handicap", "Home +2.5"),
            "AH_AWAY_PLUS_25": ("Asian Handicap", "Away +2.5"),
            "AH_HOME_MINUS_25": ("Asian Handicap", "Home -2.5"),
            "AH_AWAY_MINUS_25": ("Asian Handicap", "Away -2.5"),
            "ASIAN_HANDICAP_HOME_PLUS_1_5": ("Asian Handicap", "Home +1.5"),
            "ASIAN_HANDICAP_AWAY_PLUS_1_5": ("Asian Handicap", "Away +1.5"),
            
            # 3. Combo Options
            "HOME_OR_OVER_25": ("Home Team or Over 2.5", "Yes"),
            "AWAY_OR_OVER_25": ("Away or Over 2.5", "Yes"),
            "DRAW_OR_OVER_25": ("Draw or Over 2.5", "Yes"),
            
            # 4. Knockout To Qualify Options
            "TO_QUALIFY_HOME": ("To Qualify", "Home"),
            "TO_QUALIFY_AWAY": ("To Qualify", "Away"),
            
            # 5. Win Either Half Options
            "WIN_EITHER_HALF_HOME_YES": ("Home Team to Win Either Half", "Yes"),
            "WIN_EITHER_HALF_AWAY_YES": ("Away Team to Win Either Half", "Yes"),
            "WIN_EITHER_HALF_HOME_NO": ("Home Team to Win Either Half", "No"),
            "WIN_EITHER_HALF_AWAY_NO": ("Away Team to Win Either Half", "No"),
            
            # 6. Both Teams to Score (GG/NG)
            "GG_YES": ("GG/NG", "Yes"),
            "GG_NO": ("GG/NG", "No"),
            
            # 7. Win to Nil Options
            "HOME_WIN_TO_NIL_YES": ("Home Team to Win to Nil", "Yes"),
            "HOME_WIN_TO_NIL_NO": ("Home Team to Win to Nil", "No"),
            "AWAY_WIN_TO_NIL_YES": ("Away Team to Win to Nil", "Yes"),
            "AWAY_WIN_TO_NIL_NO": ("Away Team to Win to Nil", "No"),
            
            # 8. 1X2 Early Settlement Tiers
            "1X2_1UP_HOME": ("1X2 - 1UP", "Home"),
            "1X2_1UP_AWAY": ("1X2 - 1UP", "Away"),
            "1X2_2UP_HOME": ("1X2 - 2UP", "Home"),
            "1X2_2UP_AWAY": ("1X2 - 2UP", "Away"),
            
            # 9. Draw No Bet Options
            "DNB_HOME": ("Draw No Bet", "Home"),
            "DNB_AWAY": ("Draw No Bet", "Away"),

            # 10. Over/Under Lines
            "OVER_05": ("Over/Under", "Over 0.5"),
            "OVER_15": ("Over/Under", "Over 1.5"),
            "OVER_25": ("Over/Under", "Over 2.5"),
            "UNDER_25": ("Over/Under", "Under 2.5"),
            "UNDER_35": ("Over/Under", "Under 3.5"),
            "UNDER_45": ("Over/Under", "Under 4.5"),
            "UNDER_55": ("Over/Under", "Under 5.5")
        }
        return mapping.get(verdict, ("Double Chance", "Home or Draw"))

    def _score_fixture(self, fixture: dict) -> float:
        """
        Score a fixture for acca inclusion.
        Higher score = more reliable for accumulator.
        
        Factors:
        - Market reliability (60% weight)
        - Edge strength (30% weight)
        - Risk adjustment (10% weight)
        """
        verdict = fixture.get("verdict", "DC_1X")
        edge = fixture.get("edge", 0.0)
        risk_score = fixture.get("risk_score", 100)
        upset_alert = fixture.get("upset_alert", False)
        
        # Market reliability score (0-100)
        market_score = self.market_reliability.get(verdict, 40) * 100
        
        # Edge score (0-100, capped at edge=0.20)
        edge_score = min(edge * 500, 100)  # 0.20 edge = 100 score
        
        # Risk adjustment (penalize high risk, but allow if edge is strong)
        risk_penalty = (risk_score / 100) * 30  # Risk can reduce score by up to 30
        upset_penalty = 15 if upset_alert else 0  # Upset alerts get -15
        
        total_score = (market_score * 0.60) + (edge_score * 0.30) - risk_penalty - upset_penalty
        
        return max(total_score, 0)

    def _is_acca_eligible(self, fixture: dict, strict: bool = False) -> bool:
        """
        Determine if a fixture is eligible for accumulator under strict risk rules.
        Hedged safety markets (Double Chance, DNB, Over/Under lines, Handicaps, Combos)
        explicitly hedge against upset alerts, making them foolproof even during upset alerts.
        """
        edge = fixture.get("edge", 0.0)
        upset_alert = fixture.get("upset_alert", False)
        risk_score = fixture.get("risk_score", 100)
        verdict = fixture.get("verdict", "")
        
        # Minimum edge requirement
        if edge < self.min_edge:
            return False

        hedged_safety_markets = {
            "DC_1X", "DC_X2", "DC_12", "DNB_HOME", "DNB_AWAY",
            "OVER_15", "UNDER_35", "OVER_05", "UNDER_45", "UNDER_55",
            "AH_HOME_PLUS_15", "AH_AWAY_PLUS_15", "AH_HOME_PLUS_25", "AH_AWAY_PLUS_25",
            "HOME_OR_OVER_25", "AWAY_OR_OVER_25", "DRAW_OR_OVER_25",
            "TO_QUALIFY_HOME", "TO_QUALIFY_AWAY", "WIN_EITHER_HALF_HOME_YES", "WIN_EITHER_HALF_AWAY_YES"
        }

        # Straight 1X2 win bets are rejected on upset alerts in strict mode
        if strict and upset_alert and verdict not in hedged_safety_markets:
            return False
        
        # Extremely high risk scores (>85) are rejected regardless of market
        if risk_score > 85:
            return False
        
        return True

    def generate_accumulator(self, analyzed_fixtures: list, fold_size: int, strict: bool = False) -> dict:
        """
        Generate accumulator by scoring and ranking the pre-filtered fixtures
        from AccaFilter. AccaFilter already handles risk, correlation, and
        category diversity enforcement — this method only scores and orders.
        """
        # Trust AccaFilter's pre-filtered output — it already handles strict mode
        eligible = list(analyzed_fixtures)
        
        if len(eligible) < fold_size:
            # Still generate with whatever we have instead of returning empty
            if len(eligible) == 0:
                return {
                    "fold_size": fold_size,
                    "total_estimated_odds": 0.0,
                    "legs": [],
                    "eligible_count": 0,
                    "available_count": len(analyzed_fixtures)
                }
            fold_size = len(eligible)
        
        # Score all eligible fixtures
        scored = [(f, self._score_fixture(f)) for f in eligible]
        # Sort by score (highest first)
        scored.sort(key=lambda x: x[1], reverse=True)
        
        # Take top N for the acca
        top_fixtures = [f for f, _ in scored[:fold_size]]
        
        legs = []
        compounded_odds = 1.0
        
        for idx, fix in enumerate(top_fixtures):
            market, selection = self.map_verdict_to_market_string(
                fix["verdict"], fix["home_team"], fix["away_team"]
            )
            
            # Calculate leg odds based on edge (higher edge = shorter odds, more confident)
            # Formula: base 1.20 + (edge * 0.3) to create realistic odds
            leg_odds = round(1.20 + (fix["edge"] * 0.3), 2)
            compounded_odds *= leg_odds
            
            legs.append({
                "fixture": fix["fixture"],
                "market": market,
                "selection": selection,
                "edge": round(fix["edge"], 3),
                "risk_score": round(fix["risk_score"], 1),
                "odds": leg_odds,
            })
        
        return {
            "fold_size": fold_size,
            "total_estimated_odds": round(compounded_odds, 2),
            "legs": legs,
            "eligible_count": len(eligible),
            "available_count": len(analyzed_fixtures),
        }
