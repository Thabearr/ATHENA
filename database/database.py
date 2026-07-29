import sqlite3
from pathlib import Path


class Database:

    def __init__(self, db_path="database/athena.db"):
        self.db_path = db_path

    def connect(self):
        return sqlite3.connect(self.db_path)

    def get_connection(self):
        return self.connect()

    def initialize(self):
        Path("database").mkdir(exist_ok=True)

        connection = self.connect()
        try:
            schema = Path("database/schema.sql").read_text()
            connection.executescript(schema)
            connection.commit()

            self._migrate_add_column(connection, "fixtures", "data_source", "TEXT")
            self._migrate_add_column(connection, "fixtures", "season_label", "TEXT")
            self._migrate_add_column(connection, "historical_matches", "data_source", "TEXT")
            self._migrate_add_column(connection, "historical_matches", "season_label", "TEXT")
            self._migrate_add_column(
                connection,
                "half_time_observations",
                "conflict_status",
                "INTEGER NOT NULL DEFAULT 0",
            )
            self._migrate_add_column(
                connection,
                "half_time_observations",
                "conflict_fingerprint",
                "TEXT",
            )
            self._migrate_add_column(
                connection,
                "half_time_observations",
                "conflict_reason",
                "TEXT",
            )
            self._migrate_add_column(
                connection,
                "half_time_observations",
                "conflict_observed_at",
                "TEXT",
            )
        finally:
            connection.close()

    def _migrate_add_column(self, connection, table, column, col_type):
        try:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            connection.commit()
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e):
                raise
