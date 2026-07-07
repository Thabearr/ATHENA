import logging
from services.statistics_service import StatisticsService
from services.team_form_service import TeamFormService

logger = logging.getLogger("athena.form_engine")

class FormEngine:
    def __init__(self, stats_service: StatisticsService, form_service: TeamFormService):
        self.stats_service = stats_service
        self.form_service = form_service

    def calculate_weighted_form_index(self, form_str: str) -> float:
        if not form_str:
            return 0.5
        
        weights = [0.1, 0.15, 0.2, 0.25, 0.3]
        weights = weights[-len(form_str):]
        
        mapping = {'W': 1.0, 'D': 0.5, 'L': 0.0}
        score = 0.0
        
        for idx, char in enumerate(form_str):
            score += mapping.get(char, 0.5) * weights[idx]
            
        return score

    def evaluate_fixture_form_clash(self, home_id: int, away_id: int, league_id: int, season: int) -> dict:
        h_stats = self.stats_service.get_team_statistics(home_id, league_id, season)
        a_stats = self.stats_service.get_team_statistics(away_id, league_id, season)
        
        h_form_seq = h_stats.get('form', '') if h_stats else self.form_service.get_recent_raw_form(home_id)
        a_form_seq = a_stats.get('form', '') if a_stats else self.form_service.get_recent_raw_form(away_id)
        
        h_index = self.calculate_weighted_form_index(h_form_seq)
        a_index = self.calculate_weighted_form_index(a_form_seq)
        
        h_attack_strength = (h_stats['home_goals_for'] / h_stats['home_played']) if h_stats and h_stats.get('home_played', 0) > 0 else 1.0
        a_defense_leak = (a_stats['away_goals_against'] / a_stats['away_played']) if a_stats and a_stats.get('away_played', 0) > 0 else 1.0
        
        return {
            'home_form_index': h_index,
            'away_form_index': a_index,
            'form_differential': h_index - a_index,
            'home_raw_sequence': h_form_seq,
            'away_raw_sequence': a_form_seq,
            'projected_home_offensive_edge': h_attack_strength * a_defense_leak
        }
