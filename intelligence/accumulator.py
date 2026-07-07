import logging

logger = logging.getLogger(__name__)

class AccumulatorEngine:
    def __init__(self, confidence_threshold=0.60, min_edge=0.05):
        """
        Initializes the accumulator engine with strict risk-mitigation guardrails.
        """
        self.confidence_threshold = confidence_threshold
        self.min_edge = min_edge
        
        # Hardcoded market registry mapped directly to approved sportsbook variants
        self.APPROVED_MARKETS = {
            "GG_NG": "GG/NG",                       # Mapped from image_3.png
            "COMBO_OVER_25": "Team or Over 2.5",     # Mapped from image_4.png
            "OVER_UNDER": "Over/Under Total",       # Mapped from image_5.png
            "WIN_TO_NIL": "To Win to Nil",           # Mapped from image_6.png
            "1X2_UP": "1X2 Early Payout (1UP/2UP)",  # Mapped from image_7.png
            "WIN_EITHER_HALF": "To Win Either Half",# Mapped from image_8.png
            "DOUBLE_CHANCE": "Double Chance",       # Mapped from image_9.png
            "ASIAN_HANDICAP": "Asian Handicap",     # Mapped from image_10.png
            "TO_QUALIFY": "To Qualify",             # Mapped from image_11.png
            "DNB": "Draw No Bet"                    # Mapped from image_12.png
            }

    def _is_safe_structural_fixture(self, match_data):
        """
        Executes strict background structural safety checks.
        Filters out highly volatile categories, youth setups, and unsanctioned tiers.
        """
        league = match_data.get('league', '').upper()
        # Enforce structural integrity check across all operational registries
        if "WOMEN" in league or "WNL" in league or "FEMENINO" in league:
            return False
        if "YOUTH" in league or "U19" in league or "U21" in league:
            return False
        return True

    def select_optimal_market(self, match_data):
        """
        Evaluates the analysis data and maps it to the safest, lowest-variance 
        betting line extracted from the approved screenshots to prevent a bust.
        """
        edge = match_data.get('edge', 0)
        verdict = match_data.get('verdict', 'NO_BET')
        home_team = match_data.get('home_team', 'Home')
        away_team = match_data.get('away_team', 'Away')
        
        # Risk Mitigation Strategy: Convert high-edge forecasts into high-probability coverage lines
        if verdict == "HOME_WIN":
            if edge > 0.25:
                # High advantage -> Map to 1X2 Early Payout (image_7.png) or Asian Handicap -0.5 (image_10.png)
                return {"market": self.APPROVED_MARKETS["1X2_UP"], "selection": f"{home_team} to Win", "odds": match_data.get('home_odds', 1.44)}
            elif edge > 0.12:
                # Moderate advantage -> Map to Draw No Bet (image_12.png) to secure a push condition if tied
                return {"market": self.APPROVED_MARKETS["DNB"], "selection": f"{home_team} (Draw No Bet)", "odds": match_data.get('dnb_home_odds', 1.14)}
            else:
                # Conservative advantage -> Map to Double Chance (image_9.png) for maximum safety margin
                return {"market": self.APPROVED_MARKETS["DOUBLE_CHANCE"], "selection": f"{home_team} or Draw", "odds": match_data.get('dc_home_odds', 1.10)}
                
        elif verdict == "AWAY_WIN":
            if edge > 0.25:
                return {"market": self.APPROVED_MARKETS["1X2_UP"], "selection": f"{away_team} to Win", "odds": match_data.get('away_odds', 1.75)}
            elif edge > 0.12:
                return {"market": self.APPROVED_MARKETS["DNB"], "selection": f"{away_team} (Draw No Bet)", "odds": match_data.get('dnb_away_odds', 1.40)}
            else:
                return {"market": self.APPROVED_MARKETS["DOUBLE_CHANCE"], "selection": f"Draw or {away_team}", "odds": match_data.get('dc_away_odds', 1.35)}
                
        elif verdict == "HIGH_GOALS":
            # Map high scoring expectations to low-variance goals lines (image_5.png) or combo safety (image_4.png)
            return {"market": self.APPROVED_MARKETS["OVER_UNDER"], "selection": "Over 1.5 Goals", "odds": match_data.get('over_15_odds', 1.37)}
            
        elif verdict == "LOW_GOALS":
            return {"market": self.APPROVED_MARKETS["OVER_UNDER"], "selection": "Under 3.5 Goals", "odds": match_data.get('under_35_odds', 1.29)}
            
        return None

    def generate_accumulator(self, analyzed_matches, fold_size=5):
        """
        Filters the full slate of upcoming games, prioritizes them by clean 
        mathematical edge, and builds a precise multi-leg selection slip.
        """
        valid_selections = []
        
        for match in analyzed_matches:
            # 1. Structural safety validation filter
            if not self._is_safe_structural_fixture(match):
                continue
                
            # 2. Strict mathematical thresholds verification
            if match.get('edge', 0) < self.min_edge:
                continue
                
            # 3. Optimize selected line from core visual options
            optimal_pick = self.select_optimal_market(match)
            if optimal_pick:
                valid_selections.append({
                    "fixture": f"{match.get('home_team')} vs {match.get('away_team')}",
                    "market": optimal_pick["market"],
                    "selection": optimal_pick["selection"],
                    "odds": optimal_pick["odds"],
                    "edge": match.get('edge', 0)
                })
                
        # Sort selections directly by calculated edge magnitude to maximize system accuracy
        valid_selections.sort(key=lambda x: x['edge'], reverse=True)
        
        if len(valid_selections) < fold_size:
            logger.warning(f"Insufficient qualified lines found to meet the requested {fold_size}-fold target.")
            return valid_selections
            
        # Extract the highest value legs up to the targeted size limit (5, 10, 20, or 30 legs)
        final_slip = valid_selections[:fold_size]
        
        # Compute combined accumulator slip price compounding metrics
        total_odds = 1.0
        for leg in final_slip:
            total_odds *= leg['odds']
            
        return {
            "fold_size": len(final_slip),
            "total_estimated_odds": round(total_odds, 2),
            "legs": final_slip
        }
