from database.database import Database


class StatisticsRepository:

    def __init__(self):
        self.db = Database()

    def get_statistics(
        self,
        team_id,
        league_id,
        season
    ):

        query = """
        SELECT *
        FROM team_statistics
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

    def save_statistics(
        self,
        stats
    ):

        query = """
        INSERT OR REPLACE INTO team_statistics
        (
            team_id,
            league_id,
            season,
            form,
            played,
            wins,
            draws,
            losses,
            goals_for,
            goals_against,
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
            updated_at
        )
        VALUES
        (
            ?,?,?,?,?,?,?,?,?,?,
            ?,?,?,?,?,?,?,?,?,?,
            ?,?,?
        )
        """

        with self.db.connect() as conn:

            cursor = conn.cursor()

            cursor.execute(query, stats)

            conn.commit()
