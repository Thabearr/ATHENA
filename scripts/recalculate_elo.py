#!/usr/bin/env python3
import sqlite3
from intelligence.elo_engine import EloEngine

DB_PATH = "database/athena.db"

def main():
    print("Resetting ELO ratings and recalculating historical pre-ELOs...")
    conn = sqlite3.connect(DB_PATH)
    
    # 1. Wipe current ELO
    conn.execute("UPDATE teams SET elo_rating = 1500, home_elo = 1500, away_elo = 1500, matches_processed = 0, last_update = NULL")
    
    # 2. Wipe existing pre-ELOs
    try:
        conn.execute("UPDATE historical_matches SET home_pre_elo = NULL, away_pre_elo = NULL")
    except Exception as e:
        print(f"Notice: {e}")
        
    conn.commit()
    conn.close()
    
    # 3. Process historical matches chronologically
    engine = EloEngine(db_path=DB_PATH)
    engine.process_historical_matches()
    
    print("\n✅ ELO reset and point-in-time pre_elo backfill complete.")

if __name__ == "__main__":
    main()
