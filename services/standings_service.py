import logging
from database.database import get_db_connection

logger = logging.getLogger("athena.standings_service")

class StandingsService:
    def __init__(self, statistics_service):
        self.stats_service = statistics_service

    def process_and_save_standings(self, league_id: int, season: int, standings_list: list):
        for team in standings_list:
            stats_payload = {
                'team_id': team['team']['id'],
                'league_id': league_id,
                'season': season,
                'form': team.get('form', ''),
                'played': team['all']['played'],
                'wins': team['all']['win'],
                'draws': team['all']['draw'],
                'losses': team['all']['lose'],
                'goals_for': team['all']['goals']['for'],
                'goals_against': team['all']['goals']['against'],
                'home_played': team['home']['played'],
                'home_wins': team['home']['win'],
                'home_draws': team['home']['draw'],
                'home_losses': team['home']['lose'],
                'home_goals_for': team['home']['goals']['for'],
                'home_goals_against': team['home']['goals']['against'],
                'away_played': team['away']['played'],
                'away_wins': team['away']['win'],
                'away_draws': team['away']['draw'],
                'away_losses': team['away']['lose'],
                'away_goals_for': team['away']['goals']['for'],
                'away_goals_against': team['away']['goals']['against']
            }
            self.stats_service.save_team_statistics(stats_payload)
