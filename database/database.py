import sqlite3
from pathlib import Path


class Database:

    def __init__(self, db_path="database/athena.db"):
        self.db_path = db_path

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def initialize(self):

        Path("database").mkdir(exist_ok=True)

        connection = self.get_connection()

        schema = Path("database/schema.sql").read_text()

        connection.executescript(schema)

        connection.commit()

        connection.close()

        print("✓ Database initialized successfully.")
