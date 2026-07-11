import sqlite3
from pathlib import Path


class Database:

    def __init__(self, db_path="database/athena.db"):

        self.db_path = db_path

    # --------------------------------------------------
    # Main connection method
    # --------------------------------------------------

    def connect(self):

        return sqlite3.connect(self.db_path)

    # --------------------------------------------------
    # Backwards compatibility
    # Older modules call get_connection()
    # --------------------------------------------------

    def get_connection(self):

        return self.connect()

    # --------------------------------------------------
    # Initialize database
    # --------------------------------------------------

    def initialize(self):

        Path("database").mkdir(exist_ok=True)

        with self.connect() as connection:

            schema = Path(
                "database/schema.sql"
            ).read_text()

            connection.executescript(schema)

            connection.commit()

        print("✓ Database initialized successfully.")
