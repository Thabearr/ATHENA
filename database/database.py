import sqlite3
from pathlib import Path


class Database:

    def __init__(self):

        self.db_path = Path("database/athena.db")

        self.schema_path = Path("database/schema.sql")


    def initialize(self):

        connection = sqlite3.connect(self.db_path)

        cursor = connection.cursor()

        with open(self.schema_path, "r") as file:

            cursor.executescript(file.read())

        connection.commit()

        connection.close()

        print("✓ Database initialized.")
