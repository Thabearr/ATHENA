from typing import List, Dict, Any
import logging
from database.database import Database

# Import market category mapping from match_analyst
from intelligence.match_analyst import MARKET_CATEGORIES


class CorrelationAnalyzer:
    """
    Measures correlation between accumulator legs to ensure genuine diversification.
    Uses market CATEGORY grouping (not individual market codes) so that e.g.
    Over 1.5 and Under 3.5 are both counted under OVER_UNDER and capped together.
    """

    # Hard caps: max legs per market category in ANY acca
    # Designed for 20-fold: spread across at least 5 categories
    CATEGORY_HARD_CAPS = {
        "DOUBLE_CHANCE": 4,
        "OVER_UNDER": 4,
        "ASIAN_HANDICAP": 3,
        "COMBO": 3,
        "BTTS": 3,
        "DRAW_NO_BET": 3,
        "WIN_EITHER_HALF": 3,
        "WIN_TO_NIL": 2,
        "EARLY_PAYOUT": 2,
        "TO_QUALIFY": 3,
        "OTHER": 2,
    }

    def __init__(self):
        self.db = Database()

    def _get_category(self, verdict: str) -> str:
        """Map a verdict code to its market category."""
        return MARKET_CATEGORIES.get(verdict, "OTHER")

    def _count_categories(self, legs: List[Dict[str, Any]]) -> Dict[str, int]:
        """Count how many legs belong to each market category."""
        counts = {}
        for leg in legs:
            verdict = leg.get('market') or leg.get('verdict', '')
            cat = self._get_category(verdict)
            counts[cat] = counts.get(cat, 0) + 1
        return counts

    def is_category_full(self, verdict: str, existing_legs: List[Dict[str, Any]]) -> bool:
        """
        Check if adding a leg with this verdict would exceed the hard cap
        for its market category.
        """
        cat = self._get_category(verdict)
        counts = self._count_categories(existing_legs)
        cap = self.CATEGORY_HARD_CAPS.get(cat, 2)
        return counts.get(cat, 0) >= cap

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
                logging.getLogger("athena.correlation_analyzer").error(f"Failed to calculate derby correlation: {e}")
        
        return penalty

    def calculate_market_correlation(self, legs: List[Dict[str, Any]]) -> float:
        """
        Penalty based on market CATEGORY concentration.
        The more concentrated in one category, the higher the penalty.
        """
        penalty = 0.0
        cat_counts = self._count_categories(legs)
        total_legs = len(legs)
        
        if total_legs > 1:
            for cat, count in cat_counts.items():
                cap = self.CATEGORY_HARD_CAPS.get(cat, 2)
                if count > cap:
                    # Over hard cap = severe penalty
                    penalty -= 0.30 * (count - cap)
                elif count > total_legs * 0.30:
                    # More than 30% of acca in one category = moderate penalty
                    penalty -= 0.10 * (count - int(total_legs * 0.30))
        
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
        
        # Bonus for number of unique categories used
        cat_counts = self._count_categories(legs)
        unique_cats = len(cat_counts)
        if unique_cats >= 5:
            diversity_bonus = 0.15
        elif unique_cats >= 4:
            diversity_bonus = 0.10
        elif unique_cats >= 3:
            diversity_bonus = 0.05
        else:
            diversity_bonus = 0.0
        
        final_score = max(0.0, min(1.0, base_score + total_penalty + diversity_bonus))
        return final_score

    def check_leg_correlation(self, new_leg: Dict[str, Any], existing_legs: List[Dict[str, Any]], skip_league: bool = False) -> float:
        """
        Calculates correlation (0-1) between a new leg and existing legs.
        Returns a value > threshold if highly correlated.
        
        Key change: uses category-based correlation instead of exact market match,
        and enforces hard caps via is_category_full().
        
        skip_league: If True, ignores same-league penalty (used for single-competition accas).
        """
        new_verdict = new_leg.get('market') or new_leg.get('verdict', '')
        new_league = new_leg.get('league')
        new_home = new_leg.get('home_team')
        new_away = new_leg.get('away_team')
        new_category = self._get_category(new_verdict)

        # Hard cap check — instant rejection
        if self.is_category_full(new_verdict, existing_legs):
            return 1.0  # Maximum correlation = blocked

        correlation = 0.0

        # Count how many existing legs share the same category
        cat_count = 0
        for leg in existing_legs:
            leg_verdict = leg.get('market') or leg.get('verdict', '')
            leg_category = self._get_category(leg_verdict)

            if not skip_league and leg.get('league') == new_league:
                correlation += 0.08  # Mild penalty for same league

            if leg.get('home_team') in [new_home, new_away] or leg.get('away_team') in [new_home, new_away]:
                correlation += 0.5  # Very high if same team — always enforced

            if leg_category == new_category:
                cat_count += 1

            # Exact same market type gets extra penalty
            if leg_verdict == new_verdict:
                correlation += 0.12

        # Progressive category penalty: each additional same-category leg adds more
        correlation += cat_count * 0.15
                
        return min(1.0, correlation)
