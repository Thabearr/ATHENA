import sqlite3
from datetime import datetime, timedelta

def seed_fake_upcoming():
    db_path = "database/athena.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    today = datetime.utcnow()
    
    fake_matches = [
        # Match 1: Huge Edge (Top tier vs bottom tier) - No Upset Alert
        (999001, "Premier League", "Manchester City", "Luton Town", (today + timedelta(hours=12)).isoformat(), "NS", "mock"),
        # Match 2: Big Derby (High Volatility, should get risk penalty)
        (999002, "Premier League", "Arsenal FC", "Tottenham Hotspur FC", (today + timedelta(hours=24)).isoformat(), "NS", "mock"),
        # Match 3: Tier 2 safe match
        (999003, "Eredivisie", "AFC Ajax", "Volendam", (today + timedelta(hours=36)).isoformat(), "NS", "mock"),
        # Match 4: Tier 3 match (Should be skipped unless acca buster needed, or edge is massive)
        (999004, "Süper Lig", "Galatasaray SK", "Pendikspor", (today + timedelta(hours=48)).isoformat(), "NS", "mock"),
        # Match 5: Top tier solid match
        (999005, "La Liga", "Real Madrid CF", "Almeria", (today + timedelta(hours=10)).isoformat(), "NS", "mock"),
        # Match 6: Another Top tier solid match
        (999006, "Serie A", "Juventus FC", "Salernitana", (today + timedelta(hours=5)).isoformat(), "NS", "mock"),
        # Match 7: Another Derby
        (999007, "La Liga", "FC Barcelona", "RCD Espanyol", (today + timedelta(hours=15)).isoformat(), "NS", "mock"),
    ]
    
    for m in fake_matches:
        cursor.execute("""
            INSERT OR REPLACE INTO fixtures 
            (fixture_id, league, season, home_team, away_team, match_date, status, data_source, season_label) 
            VALUES (?, ?, '2023-24', ?, ?, ?, ?, ?, '2023-24')
        """, m)
        
    conn.commit()
    conn.close()
    print("Fake upcoming matches seeded.")

if __name__ == "__main__":
    seed_fake_upcoming()
