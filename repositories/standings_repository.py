from database.database import Database


class StandingsRepository:

    def __init__(self):
        self.db = Database()

    def save_standings(self, standings):

        query = """
        INSERT OR REPLACE INTO standings
        (
            team_id,
            league_id,
            season,
            position,
            points,
            played,
            won,
            drawn,
            lost,
            goal_difference
        )
        VALUES
        (
            ?,?,?,?,?,?,?,?,?,?
        )
        """

        with self.db.connect() as conn:

            cursor = conn.cursor()

            cursor.execute(query, standings)

            conn.commit()

    def get_team_position(
        self,
        team_id,
        league_id,
        season
    ):

        query = """
        SELECT *
        FROM standings
        WHERE team_id = ?
        AND league_id = ?
        AND season = ?
        """

        with self.db.connect() as conn:

            conn.row_factory = lambda cursor, row: {
                cursor.description[i][0]: row[i]
                for i in range(len(row))
            }

            cursor = conn.cursor()

            cursor.execute(
                query,
                (
                    team_id,
                    league_id,
                    season
                )
            )

            return cursor.fetchone()
