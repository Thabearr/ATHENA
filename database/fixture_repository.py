import sqlite3
from pathlib import Path


class FixtureRepository:

    def __init__(self):
        self.db = Path("database/athena.db")

    def save_fixture(self, fixture):

        connection = sqlite3.connect(self.db)
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT OR REPLACE INTO fixtures
            (
                fixture_id,
                league,
                home_team,
                away_team,
                match_date,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                fixture["fixture"]["id"],
                fixture["league"]["name"],
                fixture["teams"]["home"]["name"],
                fixture["teams"]["away"]["name"],
                fixture["fixture"]["date"],
                fixture["fixture"]["status"]["short"]
            )
        )

        connection.commit()
        connection.close()

    def save_many(self, fixtures):

        for fixture in fixtures:
            self.save_fixture(fixture)
