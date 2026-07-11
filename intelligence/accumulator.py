    def select_optimal_market(self, match_data):
        """
        Upgraded Athena Visual Mapping Layer.
        Transforms high-confidence outcomes into ultra-safe, low-variance selections.
        """
        edge = match_data.get('edge', 0)
        verdict = match_data.get('verdict', 'NO_BET')
        home_team = match_data.get('home_team', 'Home')
        away_team = match_data.get('away_team', 'Away')
        
        # ------------------------------------------------------------------
        # HOME ADVANTAGE PROCESSING (Targeting Early Payout & Protection)
        # ------------------------------------------------------------------
        if verdict == "STRONG HOME ADVANTAGE" or verdict == "HOME_WIN":
            if edge > 0.25:
                # Elite edge -> Leverage Early Payout (1UP/2UP) to secure victory early
                return {
                    "market": "1X2 - 1UP/2UP", 
                    "selection": f"{home_team} (Early Payout Trigger)", 
                    "odds": match_data.get('home_odds', 1.44)
                }
            elif edge > 0.15:
                # Moderate advantage -> Map to Draw No Bet to force a void/push on tie
                return {
                    "market": "Draw No Bet", 
                    "selection": f"{home_team}", 
                    "odds": match_data.get('dnb_home_odds', 1.14)
                }
            else:
                # Conservative edge -> Double Chance for wide safety margin
                return {
                    "market": "Double Chance", 
                    "selection": "Home or Draw", 
                    "odds": match_data.get('dc_home_odds', 1.10)
                }

        # ------------------------------------------------------------------
        # AWAY ADVANTAGE PROCESSING 
        # ------------------------------------------------------------------
        elif verdict == "STRONG AWAY ADVANTAGE" or verdict == "AWAY_WIN":
            if edge > 0.25:
                return {
                    "market": "1X2 - 1UP/2UP", 
                    "selection": f"{away_team} (Early Payout Trigger)", 
                    "odds": match_data.get('away_odds', 1.75)
                }
            elif edge > 0.15:
                return {
                    "market": "Draw No Bet", 
                    "selection": f"{away_team}", 
                    "odds": match_data.get('dnb_away_odds', 1.40)
                }
            else:
                return {
                    "market": "Double Chance", 
                    "selection": "Draw or Away", 
                    "odds": match_data.get('dc_away_odds', 1.35)
                }

        # ------------------------------------------------------------------
        # GOALS GOVERNANCE (Strictly Over 1.5 baseline, completely banning 0.5)
        # ------------------------------------------------------------------
        elif verdict == "HIGH_GOALS":
            return {
                "market": "Over/Under", 
                "selection": "Over 1.5 Goals", 
                "odds": match_data.get('over_15_odds', 1.37)
            }
            
        elif verdict == "LOW_GOALS":
            return {
                "market": "Over/Under", 
                "selection": "Under 3.5 Goals", 
                "odds": match_data.get('under_35_odds', 1.29)
            }
            
        return None
