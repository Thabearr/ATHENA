from typing import List, Dict, Any
from intelligence.correlation_analyzer import CorrelationAnalyzer
from config.league_priority import get_league_tier

class AccaFilter:
    """
    Leg Filtering Engine
    Removes problematic legs before acca generation based on strict rules and tier priorities.
    """

    def __init__(self):
        self.correlation_analyzer = CorrelationAnalyzer()

    def filter_and_rank_legs(self, analyzed_matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Disqualify invalid legs and sort the remaining ones based on edge, risk, and priority.
        """
        valid_legs = []
        
        # Initial disqualification pass
        for match in analyzed_matches:
            # 1. Edge < 0.05 (marginal value)
            if match.get('edge', 0.0) < 0.05:
                continue
                
            # 2. Risk score > 70 (too risky)
            if match.get('risk_score', 0.0) > 70:
                continue
                
            # 3. Data freshness < 0.40 (stale)
            # Assuming freshness is available in match dict, default to 1.0 if not implemented yet
            if match.get('freshness', 1.0) < 0.40:
                continue
                
            # Add tier information for ranking
            league = match.get('league', '')
            match['tier'] = get_league_tier(league)
            
            valid_legs.append(match)

        # Re-rank remaining legs by:
        # Tier (primary - lower is better), Edge quality (secondary - higher is better), Risk score (tertiary - lower is better)
        valid_legs.sort(key=lambda x: (x['tier'], -x.get('edge', 0.0), x.get('risk_score', 0.0)))
        
        return valid_legs

    def build_filtered_acca(self, ranked_legs: List[Dict[str, Any]], target_size: int = 5) -> List[Dict[str, Any]]:
        """
        Builds the final list of legs for the acca, ensuring correlation and league constraints.
        Priority leagues are inherently favored because the input `ranked_legs` is sorted by tier.
        """
        final_acca = []
        league_counts = {}
        team_set = set()

        for leg in ranked_legs:
            if len(final_acca) >= target_size:
                break
                
            league = leg.get('league')
            home_team = leg.get('home_team')
            away_team = leg.get('away_team')

            # 1. Same team in multiple legs
            if home_team in team_set or away_team in team_set:
                continue

            # 2. Max 2 legs from the same league (unless it's an exceptional high-tier value)
            if league_counts.get(league, 0) >= 2:
                # Only dip further into the same league if it's Tier 1 and Edge is massive (>0.15)
                if leg.get('tier', 4) > 1 or leg.get('edge', 0.0) < 0.15:
                    continue

            # 3. Correlation > 0.65 with existing leg
            correlation = self.correlation_analyzer.check_leg_correlation(leg, final_acca)
            if correlation > 0.65:
                continue

            # Leg accepted
            final_acca.append(leg)
            league_counts[league] = league_counts.get(league, 0) + 1
            team_set.add(home_team)
            team_set.add(away_team)

        return final_acca
