import sqlite3
from datetime import datetime

def seed_data():
    conn = sqlite3.connect('database/athena.db')
    cursor = conn.cursor()
    
    # Clear old junk to ensure a fresh test
    cursor.execute("DELETE FROM fixtures")
    
    # Inject 20 mock "Live/Upcoming" matches for today
    today = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    fixtures = [
        (i, "Test League", 2026, f"Team Home {i}", f"Team Away {i}", today, "NS")
        for i in range(100, 120)
    ]
    
    cursor.executemany("""
        INSERT INTO fixtures (fixture_id, league, season, home_team, away_team, match_date, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, fixtures)
    
    conn.commit()
    conn.close()
    print("✅ Seeded 20 valid upcoming fixtures into athena.db")

if __name__ == "__main__":
    seed_data()
