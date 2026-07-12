import sqlite3
from datetime import datetime

def seed_data():
    # Connect directly to the main database in the root folder
    conn = sqlite3.connect('athena.db')
    cursor = conn.cursor()
    
    # Clear the old filtered data to ensure a clean test run
    cursor.execute("DELETE FROM fixtures")
    
    # Inject 35 live matches to trigger all slip sizes
    today = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    fixtures = [
        (i, "Premier League", 2026, f"Team Home {i}", f"Team Away {i}", today, "NS")
        for i in range(200, 235)
    ]
    
    cursor.executemany("""
        INSERT INTO fixtures (fixture_id, league, season, home_team, away_team, match_date, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, fixtures)
    
    conn.commit()
    conn.close()
    print("✅ Successfully injected 35 active fixtures into the MAIN athena.db")

if __name__ == "__main__":
    seed_data()
