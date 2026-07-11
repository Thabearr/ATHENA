from database.database import Database


class TeamRepository:

    def __init__(self):

        self.db = Database()

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

    def get_team(self, team_id):

        with self.db.connect() as conn:

            conn.row_factory = lambda cursor, row: {
                cursor.description[i][0]: row[i]
                for i in range(len(row))
            }

            cur = conn.cursor()

            cur.execute(

                """
                SELECT *
                FROM teams
                WHERE team_id=?
                """,

                (team_id,),
            )

            return cur.fetchone()

    def update_form(
        self,
        team_id,
        form,
        wins,
        draws,
        losses,
        goals_for,
        goals_against,
    ):

        with self.db.connect() as conn:

            conn.execute(
                """
                UPDATE teams

                SET

                    form=?,

                    recent_wins=?,

                    recent_draws=?,

                    recent_losses=?,

                    recent_goals_for=?,

                    recent_goals_against=?

                WHERE team_id=?
                """,

                (
                    form,
                    wins,
                    draws,
                    losses,
                    goals_for,
                    goals_against,
                    team_id,
                ),
            )

            conn.commit()
