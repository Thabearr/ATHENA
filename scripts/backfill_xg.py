#!/usr/bin/env python3
import sys
import os
import time
import sqlite3
from datetime import datetime
from rapidfuzz import fuzz

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.database import Database
from workers.fotmob_advanced_scraper import FotMobAdvancedScraper
from rich.console import Console
from rich.progress import track

console = Console()

def backfill_xg_and_possession():
    db = Database()
    scraper = FotMobAdvancedScraper()
    
    with db.connect() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 1. Get all distinct dates that need backfilling
        cursor.execute("""
            SELECT DISTINCT match_date 
            FROM historical_matches 
            WHERE home_xg IS NULL OR away_xg IS NULL
            ORDER BY match_date DESC
        """)
        dates_to_process = [row['match_date'] for row in cursor.fetchall()]
        
    console.print(f"[bold cyan]Found {len(dates_to_process)} dates to backfill from FotMob.[/bold cyan]")
    
    total_updated = 0
    
    for date_str in track(dates_to_process, description="Backfilling xG & Possession..."):
        # date_str format is usually YYYY-MM-DD
        fotmob_date = date_str.replace("-", "")
        
        try:
            # Fetch all FotMob matches for this date
            day_data = scraper.client.fetch_matches_by_date(fotmob_date)
            if not day_data:
                continue
                
            fotmob_matches = []
            for league in day_data.get("leagues", []):
                for match in league.get("matches", []):
                    home = match.get("home", {}).get("name", "")
                    away = match.get("away", {}).get("name", "")
                    fid = match.get("id")
                    if home and away and fid:
                        fotmob_matches.append((home, away, fid))
                        
            # Get our DB matches for this date
            with db.connect() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT h.fixture_id, t1.name as home_name, t2.name as away_name
                    FROM historical_matches h
                    JOIN teams t1 ON h.home_id = t1.team_id
                    JOIN teams t2 ON h.away_id = t2.team_id
                    WHERE h.match_date = ? AND (h.home_xg IS NULL OR h.away_xg IS NULL)
                """, (date_str,))
                
                db_matches = cursor.fetchall()
                
            for db_m in db_matches:
                db_fid = db_m['fixture_id']
                db_home = db_m['home_name']
                db_away = db_m['away_name']
                
                # Find matching FotMob fixture
                best_match_fid = None
                best_score = 0
                
                for fm_home, fm_away, fm_fid in fotmob_matches:
                    home_score = fuzz.ratio(db_home.lower(), fm_home.lower())
                    away_score = fuzz.ratio(db_away.lower(), fm_away.lower())
                    avg_score = (home_score + away_score) / 2
                    
                    if avg_score > 80 and avg_score > best_score:
                        best_score = avg_score
                        best_match_fid = fm_fid
                
                if best_match_fid:
                    # Enrich from FotMob
                    details = scraper.enrich_match(best_match_fid)
                    
                    home_xg = details.get("home_xg")
                    away_xg = details.get("away_xg")
                    home_pos = details.get("home_possession")
                    away_pos = details.get("away_possession")
                    
                    if home_xg is not None and away_xg is not None:
                        with db.connect() as conn:
                            conn.execute("""
                                UPDATE historical_matches 
                                SET home_xg = ?, away_xg = ?, home_possession = ?, away_possession = ?
                                WHERE fixture_id = ?
                            """, (home_xg, away_xg, home_pos, away_pos, db_fid))
                            conn.commit()
                        total_updated += 1
                        
            # Sleep slightly to avoid hammering FotMob
            time.sleep(0.2)
            
        except Exception as e:
            console.print(f"[red]Error processing date {date_str}: {e}[/red]")
            time.sleep(1)
            
    console.print(f"[bold green]Successfully backfilled advanced stats for {total_updated} historical matches![/bold green]")

if __name__ == "__main__":
    backfill_xg_and_possession()
