from database.database import Database


class TeamRepository:

    def __init__(self):
        self.db = Database()

    # -------------------------------------------------
    # Save Team
    # -------------------------------------------------

    def save_team(
        self,
        team_id,
        name,
        country,
        league_id,
        season,
    ):

        with self.db.connect() as conn:

            conn.execute(
                """
                INSERT INTO teams
                (
                    team_id,
                    name,
                    country,
                    league_id,
                    season
                )

                VALUES (?, ?, ?, ?, ?)

                ON CONFLICT(team_id)

                DO UPDATE SET

                    name=excluded.name,
                    country=excluded.country,
                    league_id=excluded.league_id,
                    season=excluded.season
                """,

                (
                    team_id,
                    name,
                    country,
                    league_id,
                    season,
                ),
            )

            conn.commit()

    # -------------------------------------------------
    # Get Team
    # -------------------------------------------------

    def get_team(self, team_id):

        with self.db.connect() as conn:

            conn.row_factory = lambda cursor, row: {
                cursor.description[i][0]: row[i]
                for i in range(len(row))
            }

            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT *
                FROM teams
                WHERE team_id=?
                """,
                (team_id,),
            )

            return cursor.fetchone()

    # -------------------------------------------------
    # Get Team Statistics
    # -------------------------------------------------

    def get_team_statistics(
        self,
        team_id,
        league_id,
        season,
    ):

        with self.db.connect() as conn:

            conn.row_factory = lambda cursor, row: {
                cursor.description[i][0]: row[i]
                for i in range(len(row))
            }

            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT *

                FROM team_statistics

                WHERE
                    team_id=?
                AND league_id=?
                AND season=?
                """,

                (
                    team_id,
                    league_id,
                    season,
                ),
            )

            return cursor.fetchone()

    # -------------------------------------------------
    # Update Statistics
    # -------------------------------------------------

    def update_statistics(
        self,
        stats,
    ):

        with self.db.connect() as conn:

            conn.execute(
                """
                INSERT INTO team_statistics(

                    team_id,
                    league_id,
                    season,

                    rank,
                    points,
                    form,

                    played,
                    wins,
                    draws,
                    losses,

                    goals_for,
                    goals_against,
                    goal_difference,

                    clean_sheets,
                    failed_to_score,

                    home_played,
                    home_wins,
                    home_draws,
                    home_losses,
                    home_goals_for,
                    home_goals_against,

                    away_played,
                    away_wins,
                    away_draws,
                    away_losses,
                    away_goals_for,
                    away_goals_against,

                    btts,
                    over15,
                    over25,
                    over35,

                    updated_at

                )

                VALUES(

                    :team_id,
                    :league_id,
                    :season,

                    :rank,
                    :points,
                    :form,

                    :played,
                    :wins,
                    :draws,
                    :losses,

                    :goals_for,
                    :goals_against,
                    :goal_difference,

                    :clean_sheets,
                    :failed_to_score,

                    :home_played,
                    :home_wins,
                    :home_draws,
                    :home_losses,
                    :home_goals_for,
                    :home_goals_against,

                    :away_played,
                    :away_wins,
                    :away_draws,
                    :away_losses,
                    :away_goals_for,
                    :away_goals_against,

                    :btts,
                    :over15,
                    :over25,
                    :over35,

                    :updated_at

                )

                ON CONFLICT(team_id, league_id, season)

                DO UPDATE SET

                    rank=excluded.rank,
                    points=excluded.points,
                    form=excluded.form,

                    played=excluded.played,
                    wins=excluded.wins,
                    draws=excluded.draws,
                    losses=excluded.losses,

                    goals_for=excluded.goals_for,
                    goals_against=excluded.goals_against,
                    goal_difference=excluded.goal_difference,

                    clean_sheets=excluded.clean_sheets,
                    failed_to_score=excluded.failed_to_score,

                    home_played=excluded.home_played,
                    home_wins=excluded.home_wins,
                    home_draws=excluded.home_draws,
                    home_losses=excluded.home_losses,
                    home_goals_for=excluded.home_goals_for,
                    home_goals_against=excluded.home_goals_against,

                    away_played=excluded.away_played,
                    away_wins=excluded.away_wins,
                    away_draws=excluded.away_draws,
                    away_losses=excluded.away_losses,
                    away_goals_for=excluded.away_goals_for,
                    away_goals_against=excluded.away_goals_against,

                    btts=excluded.btts,
                    over15=excluded.over15,
                    over25=excluded.over25,
                    over35=excluded.over35,

                    updated_at=excluded.updated_at
                """,
                stats,
            )

            conn.commit()
