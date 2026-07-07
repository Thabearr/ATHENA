import sqlite3

class Database:
    def __init__(self, db_path="athena.db"):
        """
        Initializes the core SQLite database instance for ATHENA.
        """
        self.db_path = db_path
        self._init_db()

    def get_connection(self):
        """
        Returns a clean connection instance to the SQLite database file.
        """
        return sqlite3.connect(self.db_path)

    def connect(self):
        """
        Alias method to support pipeline components calling .connect().
        """
        return self.get_connection()

    def _init_db(self):
        """
        Ensures the structural tables exist upon system initialization.
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fixtures (
                fixture_id INTEGER PRIMARY KEY,
                league_id INTEGER,
                league TEXT,
                match_date TEXT,
                home_team TEXT,
                away_team TEXT,
                home_odds REAL,
                draw_odds REAL,
                away_odds REAL,
                dnb_home_odds REAL,
                dnb_away_odds REAL,
                dc_home_odds REAL,
                dc_away_odds REAL,
                over_15_odds REAL,
                under_35_odds REAL
            )
        """)
        conn.commit()
        conn.close()
