from database.database import Database


class TeamRepository:

    def __init__(self):
        self.db = Database()

    def get_team(self, team_id):

        query = """
            SELECT *
            FROM teams
            WHERE team_id = ?
        """

        with self.db.connect() as conn:

            conn.row_factory = lambda cursor, row: {
                cursor.description[i][0]: row[i]
                for i in range(len(row))
            }

            cursor = conn.cursor()

            cursor.execute(query, (team_id,))

            return cursor.fetchone()

    def save_team(
        self,
        team_id,
        name,
        country,
        league
    ):

        query = """
        INSERT OR REPLACE INTO teams
        (
            team_id,
            name,
            country,
            league
        )
        VALUES
        (
            ?,?,?,?
        )
        """

        with self.db.connect() as conn:

            cursor = conn.cursor()

            cursor.execute(
                query,
                (
                    team_id,
                    name,
                    country,
                    league
                )
            )

            conn.commit()

    def team_exists(self, team_id):

        return self.get_team(team_id) is not None

    def get_all_teams(self):

        query = """
            SELECT *
            FROM teams
            ORDER BY name
        """

        with self.db.connect() as conn:

            conn.row_factory = lambda cursor, row: {
                cursor.description[i][0]: row[i]
                for i in range(len(row))
            }

            cursor = conn.cursor()

            cursor.execute(query)

            return cursor.fetchall()
