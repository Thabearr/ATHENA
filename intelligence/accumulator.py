import logging

logger = logging.getLogger("athena.accumulator")

class AccumulatorEngine:
    def __init__(self, confidence_threshold=0.60, min_edge=0.05):
        self.confidence_threshold = confidence_threshold
        self.min_edge = min_edge

    def _is_safe_structural_fixture(self, match_data):
        """Strict structural firewall."""
        league = match_data.get('league', '').upper()
        blacklist = ["WOMEN", "WNL", "FEMENINO", "FRAUEN", "FEMININ", "U19", "U21", "YOUTH"]
        if any(b in league for b in blacklist):
            return False
        return True

    def select_optimal_market(self, match_data):
        """
        Transforms high-confidence outcomes into ultra-safe, low-variance selections
        with an automated 1.15 minimum odds floor.
        """
        edge = match_data.get('edge', 0)
        verdict = match_data.get('verdict', 'NO_BET')
        home_team = match_data.get('home_team', 'Home')
        away_team = match_data.get('away_team', 'Away')
        
        def validate_odds(odds):
            return odds if odds >= 1.15 else None

        if verdict in ["STRONG HOME ADVANTAGE", "HOME_WIN"]:
            if edge > 0.25:
                odds = validate_odds(match_data.get('home_odds', 1.44))
                if odds:
                    return {"market": "1X2 - 1UP/2UP", "selection": f"{home_team} (1UP)", "odds": odds}
            if edge > 0.15:
                odds = validate_odds(match_data.get('dnb_home_odds', 1.20))
                if odds:
                    return {"market": "Draw No Bet", "selection": f"{home_team}", "odds": odds}
            odds = validate_odds(match_data.get('dc_home_odds', 1.16))
            if odds:
                return {"market": "Double Chance", "selection": "Home or Draw", "odds": odds}

        elif verdict in ["STRONG AWAY ADVANTAGE", "AWAY_WIN"]:
            if edge > 0.25:
                odds = validate_odds(match_data.get('away_odds', 1.75))
                if odds:
                    return {"market": "1X2 - 1UP/2UP", "selection": f"{away_team} (1UP)", "odds": odds}
            if edge > 0.15:
                odds = validate_odds(match_data.get('dnb_away_odds', 1.40))
                if odds:
                    return {"market": "Draw No Bet", "selection": f"{away_team}", "odds": odds}
            odds = validate_odds(match_data.get('dc_away_odds', 1.35))
            if odds:
                return {"market": "Double Chance", "selection": "Draw or Away", "odds": odds}

        elif verdict == "HIGH_GOALS":
            odds = validate_odds(match_data.get('over_15_odds', 1.37))
            if odds:
                return {"market": "Over/Under", "selection": "Over 1.5 Goals", "odds": odds}
            
        elif verdict == "LOW_GOALS":
            odds = validate_odds(match_data.get('under_35_odds', 1.29))
            if odds:
                return {"market": "Over/Under", "selection": "Under 3.5 Goals", "odds": odds}
            
        return None

    def generate_accumulator(self, analyzed_matches, fold_size=10):
        """
        Builds the accumulator slip, proactively dropping any fixture 
        flagged with an upset alert or failing structural safety.
        """
        valid_selections = []
        
        for match in analyzed_matches:
            if not self._is_safe_structural_fixture(match):
                continue
            
            if match.get("upset_alert", False):
                logger.info(f"Upset Alert triggered: Dropping {match.get('fixture')} from slip.")
                continue
                
            if match.get('edge', 0) < self.min_edge:
                continue
                
            safe_market = self.select_optimal_market(match)
            if safe_market:
                # Merge the market selection into the match dictionary
                match.update(safe_market)
                valid_selections.append(match)
                
        valid_selections.sort(key=lambda x: x.get('edge', 0), reverse=True)
        
        final_slip = valid_selections[:fold_size]
        
        total_odds = 1.0
        for leg in final_slip:
            total_odds *= leg.get('odds', 1.0)
            
        return {
            "fold_size": len(final_slip),
            "total_estimated_odds": round(total_odds, 2),
            "legs": final_slip
        }
