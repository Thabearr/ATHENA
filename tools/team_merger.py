#!/usr/bin/env python3
"""
Team Name Deduplication / Merger Tool

Finds similar team names across the teams table (using rapidfuzz) and merges their 
historical records. This addresses issues like "Man City" vs "Manchester City" 
where different API sources use slightly different names.
"""

import sqlite3
from rapidfuzz import process, fuzz
from database.database import Database

def merge_teams():
    db = Database()
    
    with db.connect() as conn:
        cursor = conn.cursor()
        
        # Fetch all teams
        cursor.execute("SELECT id, team_id, name, league FROM teams")
        teams = cursor.fetchall()
        
        if not teams:
            print("No teams found.")
            return
            
        team_names = [t[2] for t in teams]
        name_to_row = {t[2]: t for t in teams}
        
        merged_count = 0
        processed_names = set()
        
        for team in teams:
            t_id, t_global_id, t_name, t_league = team
            
            if t_name in processed_names:
                continue
                
            processed_names.add(t_name)
            
            # Find similar names (threshold > 90%)
            # Rapidfuzz process.extract returns a list of tuples: (match_string, score, index)
            matches = process.extract(t_name, team_names, scorer=fuzz.ratio, limit=10)
            
            # Filter matches > 90% and different names
            similar_names = [m[0] for m in matches if m[1] > 90 and m[0] != t_name and m[0] not in processed_names]
            
            for sim_name in similar_names:
                sim_team = name_to_row[sim_name]
                s_id, s_global_id, s_name, s_league = sim_team
                
                print(f"Merging '{s_name}' (ID: {s_global_id}) into '{t_name}' (ID: {t_global_id})")
                
                # Update historical_matches
                cursor.execute("UPDATE historical_matches SET home_id = ? WHERE home_id = ?", (t_global_id, s_global_id))
                cursor.execute("UPDATE historical_matches SET away_id = ? WHERE away_id = ?", (t_global_id, s_global_id))
                
                # Update team_statistics
                cursor.execute("UPDATE team_statistics SET team_id = ? WHERE team_id = ?", (t_global_id, s_global_id))
                
                # Delete duplicate team
                cursor.execute("DELETE FROM teams WHERE team_id = ?", (s_global_id,))
                
                processed_names.add(s_name)
                merged_count += 1
                
        conn.commit()
        print(f"Merge complete! Merged {merged_count} duplicate teams.")

if __name__ == "__main__":
    merge_teams()
