import logging
from datetime import datetime
from database.database import Database

logger = logging.getLogger("athena.statistics_service")

class StatisticsService:
    def __init__(self):
        # Instantiate your custom Database utility class
        self.db = Database()

    def save_team_statistics(self, stats_data: dict):
        query = """
        INSERT INTO team_statistics (
            team_id, league_id, season, form, played, wins, draws, losses,
            goals_for, goals_against, home_played, home_wins, home_draws, home_losses,
            home_goals_for, home_goals_against, away_played, away_wins, away_draws,
            away_losses, away_goals_for, away_goals_against, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(team_id, league_id, season) DO UPDATE SET
            form=excluded.form, played=excluded.played, wins=excluded.wins, 
            draws=excluded.draws, losses=excluded.losses, goals_for=excluded.goals_for,
            goals_against=excluded.goals_against, home_played=excluded.home_played,
            home_wins=excluded.home_wins, home_draws=excluded.home_draws,
            home_losses=excluded.home_losses, home_goals_for=excluded.home_goals_for,
            home_goals_against=excluded.home_goals_against, away_played=excluded.away_played,
            away_wins=excluded.away_wins, away_draws=excluded.away_draws,
            away_losses=excluded.away_losses, away_goals_for=excluded.away_goals_for,
            away_goals_against=excluded.away_goals_against, updated_at=excluded.updated_at;
        """
        try:
            with self.db.connect() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (
                    stats_data['team_id'], stats_data['league_id'], stats_data['season'], stats_data.get('form', ''),
                    stats_data.get('played', 0), stats_data.get('wins', 0), stats_data.get('draws', 0), stats_data.get('losses', 0),
                    stats_data.get('goals_for', 0), stats_data.get('goals_against', 0),
                    stats_data.get('home_played', 0), stats_data.get('home_wins', 0), stats_data.get('home_draws', 0), stats_data.get('home_losses', 0),
                    stats_data.get('home_goals_for', 0), stats_data.get('home_goals_against', 0),
                    stats_data.get('away_played', 0), stats_data.get('away_wins', 0), stats_data.get('away_draws', 0), stats_data.get('away_losses', 0),
                    stats_data.get('away_goals_for', 0), stats_data.get('away_goals_against', 0),
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to persist team statistics for team {stats_data.get('team_id')}: {e}")

    def get_team_statistics(self, team_id: int, league_id: int, season: int) -> dict:
        query = "SELECT * FROM team_statistics WHERE team_id = ? AND league_id = ? AND season = ?"
        try:
            with self.db.connect() as conn:
                conn.row_factory = lambda cursor, row: dict((cursor.description[i][0], value) for i, value in enumerate(row))
                cursor = conn.cursor()
                cursor.execute(query, (team_id, league_id, season))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"Error fetching team stats: {e}")
            return None
                def build_strength_profile(self, team_id: int, league_id: int, season: int):

        stats = self.get_team_statistics(
            team_id,
            league_id,
            season
        )

        if not stats:
            return None

        # Convert form string (WWDLW) into points
        form_points = 0

        for result in stats.get("form", ""):

            if result == "W":
                form_points += 3

            elif result == "D":
                form_points += 1

        goal_difference = (
            stats["goals_for"] -
            stats["goals_against"]
        )

        clean_sheets = 0

        if stats["played"] > 0:

            clean_sheets = max(
                0,
                int(
                    stats["played"] * 0.30
                )
            )

        return {

            "position": stats.get("rank", 20),

            "form_points": form_points,

            "goal_difference": goal_difference,

            "goals_scored": stats["goals_for"],

            "goals_conceded": stats["goals_against"],

            "clean_sheets": clean_sheets,

            "wins": stats["wins"],

            "draws": stats["draws"],

            "losses": stats["losses"]

        }
