from typing import List, Dict, Any
from database.database import Database

class CorrelationAnalyzer:
    """
    Measures correlation between accumulator legs to ensure diversification.
    """

    def __init__(self):
        self.db = Database()

    def calculate_league_correlation(self, legs: List[Dict[str, Any]]) -> float:
        """
        Same league = higher correlation.
        Penalty: -0.15 for each duplicate league beyond the first instance.
        """
        penalty = 0.0
        leagues = {}
        for leg in legs:
            league = leg.get('league')
            if league:
                leagues[league] = leagues.get(league, 0) + 1
        
        for count in leagues.values():
            if count > 1:
                penalty -= 0.15 * (count - 1)
        
        return penalty

    def calculate_team_correlation(self, legs: List[Dict[str, Any]]) -> float:
        """
        Penalty: -0.20 if the same team plays in multiple legs.
        Checks derbies using database table.
        """
        penalty = 0.0
        teams = set()
        team_list = []
        
        for leg in legs:
            home = leg.get('home_team')
            away = leg.get('away_team')
            
            if home in teams: penalty -= 0.20
            if away in teams: penalty -= 0.20
            
            teams.add(home)
            teams.add(away)
            team_list.extend([home, away])
            
        # Implement database lookup for derbies between team_list
        # and apply penalties if derby matches found
        if team_list:
            try:
                with self.db.connect() as conn:
                    cursor = conn.cursor()
                    placeholders = ', '.join(['?'] * len(team_list))
                    
                    # We need to find team IDs first
                    cursor.execute(f"SELECT team_id, name FROM teams WHERE name IN ({placeholders})", team_list)
                    team_mapping = {row[1]: row[0] for row in cursor.fetchall()}
                    
                    team_ids = list(team_mapping.values())
                    if len(team_ids) > 1:
                        id_placeholders = ', '.join(['?'] * len(team_ids))
                        cursor.execute(f'''
                            SELECT intensity FROM derbies 
                            WHERE team_a_id IN ({id_placeholders}) 
                            AND team_b_id IN ({id_placeholders})
                        ''', team_ids + team_ids)
                        
                        derbies = cursor.fetchall()
                        for derby in derbies:
                            intensity = derby[0]
                            penalty -= 0.15 * intensity
            except Exception as e:
                pass
        
        return penalty

    def calculate_market_correlation(self, legs: List[Dict[str, Any]]) -> float:
        """
        Penalty: -0.10 for similar markets (e.g., all OVER/UNDER).
        """
        penalty = 0.0
        markets = {}
        
        for leg in legs:
            market = leg.get('market')
            if market:
                markets[market] = markets.get(market, 0) + 1
                
        # If more than half the acca is the same market type, apply penalty
        total_legs = len(legs)
        if total_legs > 1:
            for count in markets.values():
                if count > total_legs * 0.5:
                    penalty -= 0.10
        
        return penalty

    def diversification_score(self, legs: List[Dict[str, Any]]) -> float:
        """
        Calculates the overall portfolio quality score (0 to 1).
        Base score is 1.0, and penalties are subtracted.
        """
        base_score = 1.0
        
        league_penalty = self.calculate_league_correlation(legs)
        team_penalty = self.calculate_team_correlation(legs)
        market_penalty = self.calculate_market_correlation(legs)
        
        total_penalty = league_penalty + team_penalty + market_penalty
        
        final_score = max(0.0, base_score + total_penalty)
        return final_score

    def check_leg_correlation(self, new_leg: Dict[str, Any], existing_legs: List[Dict[str, Any]]) -> float:
        """
        Calculates correlation (0-1) between a new leg and existing legs.
        Returns a value > 0.65 if highly correlated.
        """
        correlation = 0.0
        new_league = new_leg.get('league')
        new_home = new_leg.get('home_team')
        new_away = new_leg.get('away_team')
        new_market = new_leg.get('market')
        
        for leg in existing_legs:
            if leg.get('league') == new_league:
                correlation += 0.3
            if leg.get('home_team') in [new_home, new_away] or leg.get('away_team') in [new_home, new_away]:
                correlation += 0.5  # Very high if same team
            if leg.get('market') == new_market:
                correlation += 0.1
                
        return min(1.0, correlation)
