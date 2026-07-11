from database.database import Database


class TeamRepository:

    def __init__(self):

        self.db = Database()

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
