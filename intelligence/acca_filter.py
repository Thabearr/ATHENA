from typing import List, Dict, Any
from intelligence.correlation_analyzer import CorrelationAnalyzer
from intelligence.match_analyst import MARKET_CATEGORIES
from config.league_priority import get_league_tier


class AccaFilter:
    """
    Leg Filtering Engine — builds diverse, fullproof accumulators.
    
    Key design: When building the acca, fixtures are iterated in rounds.
    In each round, the filter tries to add ONE leg from each underrepresented
    market category before allowing duplicates. This guarantees category spread.
    """

    def __init__(self):
        self.correlation_analyzer = CorrelationAnalyzer()

    def filter_and_rank_legs(self, analyzed_matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Disqualify invalid legs and sort the remaining ones.
        Ranking now prioritizes edge_above_baseline (true value) over raw edge.
        """
        valid_legs = []
        
        for match in analyzed_matches:
            # 1. Edge < 0.05 (marginal value)
            if match.get('edge', 0.0) < 0.05:
                continue
                
            # 2. Risk score > 85 (extreme risk)
            if match.get('risk_score', 0.0) > 85:
                continue
                
            # 3. Data freshness < 0.40 (stale)
            if match.get('freshness', 1.0) < 0.40:
                continue
                
            # Add tier information for ranking
            league = match.get('league', '')
            match['tier'] = get_league_tier(league)
            
            valid_legs.append(match)

        # Rank by: Tier (lower = better), then edge (higher = better), then risk (lower = better)
        valid_legs.sort(key=lambda x: (x['tier'], -x.get('edge', 0.0), x.get('risk_score', 0.0)))
        
        return valid_legs

    def build_filtered_acca(self, ranked_legs: List[Dict[str, Any]], target_size: int = 5, single_league: bool = False) -> List[Dict[str, Any]]:
        """
        Builds the final acca with enforced market category diversity.
        
        Algorithm:
        1. For each fixture, find all viable market options.
        2. Sort viable options by how underrepresented their category is in the
           current acca (least-represented categories first), then by edge.
        3. Pick the best option that passes correlation checks.
        4. If all options for a fixture are blocked, skip it.
        
        This ensures that if we already have 3 OVER_UNDER legs, the next fixture
        will try BTTS, DOUBLE_CHANCE, COMBO, DNB etc. first — even if Over 1.5
        has a higher raw probability.
        """
        final_acca = []
        team_set = set()
        category_counts = {}  # Track how many legs per category

        # Correlation threshold
        correlation_threshold = 0.85 if single_league else 0.65
        max_per_league = target_size if single_league else 4
        league_counts = {}

        for leg in ranked_legs:
            if len(final_acca) >= target_size:
                break
                
            home_team = leg.get('home_team')
            away_team = leg.get('away_team')
            league = leg.get('league')

            # 1. Same team in multiple legs — always block
            if home_team in team_set or away_team in team_set:
                continue

            # 2. League cap check
            if league_counts.get(league, 0) >= max_per_league:
                continue

            # 3. Get viable markets for this fixture
            viable_markets = leg.get('viable_markets', [])
            if not viable_markets:
                viable_markets = [{'verdict': leg.get('verdict'), 'edge': leg.get('edge', 0.05), 'category': 'OTHER'}]

            # 4. Sort viable markets by:
            #    a) Category underrepresentation (least legs in current acca first)
            #    b) Edge above baseline (highest first)
            #    This is the KEY diversity mechanism.
            def market_diversity_key(m):
                cat = m.get('category', MARKET_CATEGORIES.get(m.get('verdict', ''), 'OTHER'))
                current_count = category_counts.get(cat, 0)
                cap = self.correlation_analyzer.CATEGORY_HARD_CAPS.get(cat, 2)
                # Primary: how close to cap (lower = more room = preferred)
                fill_ratio = current_count / max(cap, 1)
                # Secondary: edge above baseline (higher = preferred, so negate)
                edge = m.get('edge_above_baseline', m.get('edge', 0.0))
                return (fill_ratio, -edge)

            sorted_markets = sorted(viable_markets, key=market_diversity_key)

            # 5. Try each market option in diversity-prioritized order
            leg_accepted = False
            for market_option in sorted_markets:
                verdict = market_option['verdict']
                cat = market_option.get('category', MARKET_CATEGORIES.get(verdict, 'OTHER'))

                # Check hard category cap
                if self.correlation_analyzer.is_category_full(verdict, final_acca):
                    continue

                test_leg = leg.copy()
                test_leg['verdict'] = verdict
                test_leg['market'] = verdict
                test_leg['edge'] = market_option.get('edge', 0.05)
                test_leg['market_category'] = cat

                # Check correlation
                correlation = self.correlation_analyzer.check_leg_correlation(
                    test_leg, final_acca, skip_league=single_league
                )
                
                if correlation <= correlation_threshold:
                    final_acca.append(test_leg)
                    league_counts[league] = league_counts.get(league, 0) + 1
                    team_set.add(home_team)
                    team_set.add(away_team)
                    category_counts[cat] = category_counts.get(cat, 0) + 1
                    leg_accepted = True
                    break
                    
            if not leg_accepted:
                continue

        return final_acca
