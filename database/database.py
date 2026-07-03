import sqlite3
from pathlib import Path


class Database:
    """Handles all database initialization and connections."""

    def __init__(self):
        self.db_path = Path("database/athena.db")
        self.schema_path = Path("database/schema.sql")

    def connect(self):
        """Returns a connection to the SQLite database."""
        return sqlite3.connect(self.db_path)

    def initialize(self):
        """Creates the database and tables if they don't exist."""

        connection = self.connect()
        cursor = connection.cursor()

        if not self.schema_path.exists():
            raise FileNotFoundError(
                f"Schema file not found: {self.schema_path}"
            )

        with open(self.schema_path, "r", encoding="utf-8") as file:
            cursor.executescript(file.read())

        connection.commit()
        connection.close()

        print("✓ Database initialized successfully.")
