    def select_optimal_market(self, match_data):
        """
        Upgraded Athena Visual Mapping Layer.
        Transforms high-confidence outcomes into ultra-safe, low-variance selections
        with an automated 1.15 minimum odds floor for accumulator viability.
        """
        edge = match_data.get('edge', 0)
        verdict = match_data.get('verdict', 'NO_BET')
        home_team = match_data.get('home_team', 'Home')
        away_team = match_data.get('away_team', 'Away')
        
        # ------------------------------------------------------------------
        # SAFETY CHECK: Minimum Odds Floor
        # We define 1.15 as the minimum "value" threshold for 20-30 leg accas.
        # Legs below this add excessive risk without enough compounding power.
        # ------------------------------------------------------------------
        def validate_odds(odds):
            return odds if odds >= 1.15 else None

        # ------------------------------------------------------------------
        # HOME ADVANTAGE PROCESSING
        # ------------------------------------------------------------------
        if verdict in ["STRONG HOME ADVANTAGE", "HOME_WIN"]:
            if edge > 0.25:
                odds = validate_odds(match_data.get('home_odds', 1.44))
                if odds:
                    return {"market": "1X2 - 1UP/2UP", "selection": f"{home_team} (1UP)", "odds": odds}
            
            if edge > 0.15:
                odds = validate_odds(match_data.get('dnb_home_odds', 1.20))
                if odds:
                    return {"market": "Draw No Bet", "selection": f"{home_team}", "odds": odds}
            
            # If edge is low, default to Double Chance ONLY if odds meet the floor
            odds = validate_odds(match_data.get('dc_home_odds', 1.16))
            if odds:
                return {"market": "Double Chance", "selection": "Home or Draw", "odds": odds}

        # ------------------------------------------------------------------
        # AWAY ADVANTAGE PROCESSING 
        # ------------------------------------------------------------------
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

        # ------------------------------------------------------------------
        # GOALS GOVERNANCE (No Over 0.5)
        # ------------------------------------------------------------------
        elif verdict == "HIGH_GOALS":
            odds = validate_odds(match_data.get('over_15_odds', 1.37))
            if odds:
                return {"market": "Over/Under", "selection": "Over 1.5 Goals", "odds": odds}
            
        elif verdict == "LOW_GOALS":
            odds = validate_odds(match_data.get('under_35_odds', 1.29))
            if odds:
                return {"market": "Over/Under", "selection": "Under 3.5 Goals", "odds": odds}
            
        # If no markets meet the safety floor, return None to exclude this leg from the slip
        return None
