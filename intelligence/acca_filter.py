from typing import List, Dict, Any
from domain.markets import DecisionStatus
from intelligence.correlation_analyzer import CorrelationAnalyzer
from intelligence.match_analyst import MARKET_CATEGORIES
from config.league_priority import get_league_tier
from services.nlp_engine import NLPEngine
from loguru import logger


class AccaFilter:
    """
    Leg Filtering Engine — builds diverse, fullproof accumulators.
    
    Key design: When building the acca, fixtures are iterated in rounds.
    In each round, the filter tries to add ONE leg from each underrepresented
    market category before allowing duplicates. This guarantees category spread.
    """

    def __init__(self):
        self.correlation_analyzer = CorrelationAnalyzer()
        self.nlp_engine = NLPEngine()

    def filter_and_rank_legs(self, analyzed_matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Disqualify invalid legs and sort the remaining ones.
        Ranking uses the explicitly labeled global-baseline delta. This is not
        bookmaker-implied betting value.
        """
        valid_legs = []
        
        for match in analyzed_matches:
            if match.get("decision_status") == DecisionStatus.NO_BET.value:
                continue
            if not match.get("viable_markets"):
                continue

            # 1. Baseline delta < 0.05
            edge = match.get('edge')
            if not isinstance(edge, (int, float)) or edge < 0.05:
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
            viable_markets = leg.get('viable_markets') or []

            # A fixture with no validated candidate is NO BET. Do not invent a
            # fallback verdict merely to fill the accumulator.
            if not viable_markets:
                continue

            # 1. Same team in multiple legs — always block
            if home_team in team_set or away_team in team_set:
                continue

            # 2. League cap check
            if league_counts.get(league, 0) >= max_per_league:
                continue

            # 3. Real-time NLP Web Search for late-breaking news
            try:
                nlp_data = self.nlp_engine.analyze_fixture(home_team, away_team)
                
                # Check for critical injuries/absences that ruin predictability
                if nlp_data.get("absence_risk", 0) >= 20:
                    logger.warning(f"🚨 NLP FATAL RISK: {home_team} vs {away_team} flagged for heavy injuries. Skipping fixture.")
                    continue
                # Apply Contextual Penalties (Fatigue & Pressure)
                fatigue = nlp_data.get("fatigue_score", 0)
                pressure = nlp_data.get("pressure_score", 0)
                if fatigue > 10:
                    leg['risk_score'] = leg.get('risk_score', 0) + fatigue
                    logger.warning(f"⚠️ NLP Fatigue flagged for {home_team} vs {away_team} (+{fatigue} risk)")
                if pressure > 10:
                    leg['risk_score'] = leg.get('risk_score', 0) + (pressure / 2)
                    
                # Apply Contextual Boosts (Motivation)
                motivation = nlp_data.get("motivation_score", 0)
                if motivation > 5:
                    leg['risk_score'] = max(0, leg.get('risk_score', 0) - (motivation / 2))
                    logger.info(f"🔥 NLP Motivation Boost for {home_team} vs {away_team} (-{motivation/2} risk)")

                # We can store the nlp_edge to boost market edge later
                # We boost edge further if highly motivated
                nlp_edge_boost = nlp_data.get("nlp_edge", 0.0) + (motivation * 0.01)
                
            except Exception as e:
                logger.error(f"NLP Engine failed for {home_team} vs {away_team}: {e}")
                nlp_edge_boost = 0.0

            # 4. Get viable markets for this fixture
            # 4. Sort viable markets by:
            #    a) Category underrepresentation (least legs in current acca first)
            #    b) Global-baseline delta (highest first)
            #    This is the KEY diversity mechanism.
            def market_diversity_key(m):
                cat = m.get('category', MARKET_CATEGORIES.get(m.get('verdict', ''), 'OTHER'))
                current_count = category_counts.get(cat, 0)
                cap = self.correlation_analyzer.CATEGORY_HARD_CAPS.get(cat, 2)
                # Primary: how close to cap (lower = more room = preferred)
                fill_ratio = current_count / max(cap, 1)
                # Secondary: edge above baseline (higher = preferred, so negate)
                # Apply the real-time NLP edge boost to the edge
                base_edge = m.get('edge_above_baseline', m.get('edge', 0.0))
                total_edge = base_edge + nlp_edge_boost
                return (fill_ratio, -total_edge)

            sorted_markets = sorted(viable_markets, key=market_diversity_key)

            # 5. Try each market option in diversity-prioritized order
            leg_accepted = False
            for market_option in sorted_markets:
                verdict = market_option['verdict']
                cat = market_option.get('category', MARKET_CATEGORIES.get(verdict, 'OTHER'))
                market_delta = market_option.get('edge')
                if not isinstance(market_delta, (int, float)):
                    continue

                # Check hard category cap
                if self.correlation_analyzer.is_category_full(verdict, final_acca):
                    continue

                test_leg = leg.copy()
                test_leg['verdict'] = verdict
                test_leg['market'] = verdict
                test_leg['edge'] = market_delta
                test_leg['edge_is_bookmaker_value'] = market_option.get(
                    'is_bookmaker_edge',
                    False,
                )
                test_leg['edge_method'] = market_option.get('edge_method')
                test_leg['estimated_probability'] = market_option.get('prob')
                test_leg['probability_method'] = market_option.get(
                    'probability_method'
                )
                test_leg['bookmaker_odds'] = market_option.get(
                    'bookmaker_odds'
                )
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
