def sync_fixtures_to_db(self):
        raw_fixtures = self.fetch_upcoming_fixtures()
        synced_count = 0
        
        for item in raw_fixtures:
            fixture_data = item.get("fixture", item)
            league_data = item.get("league", item)
            teams_data = item.get("teams", item)
            odds_data = item.get("odds_mock", {})
            
            league_name = league_data.get("name", "Unknown League")
            league_id = league_data.get("id", 0)
            season = league_data.get("season", 2026)
            
            # The filter to keep the lines strict
            if not self._is_valid_structural_league(league_name, league_id):
                continue
                
            home_team = teams_data.get("home", {}).get("name")
            away_team = teams_data.get("away", {}).get("name")
            fixture_id = fixture_data.get("id")
            match_date = fixture_data.get("date", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
            
            # Extract status, default to 'NS' (Not Started)
            status = fixture_data.get("status", {}).get("short", "NS")

            payload = {
                "fixture_id": fixture_id,
                "league_id": league_id,
                "league": league_name,
                "season": season,
                "status": status,
                "match_date": match_date,
                "home_team": home_team,
                "away_team": away_team,
                "home_odds": odds_data.get("home", 1.44),
                "draw_odds": odds_data.get("draw", 4.73),
                "away_odds": odds_data.get("away", 3.58),
                "dnb_home_odds": odds_data.get("dnb_home", 1.14),
                "dnb_away_odds": odds_data.get("dnb_away", 5.90),
                "dc_home_odds": odds_data.get("dc_home", 1.10),
                "dc_away_odds": odds_data.get("dc_away", 2.65),
                "over_15_odds": odds_data.get("over_15", 1.37),
                "under_35_odds": odds_data.get("under_35", 1.29)
            }
            
            self._write_to_database(payload)
            synced_count += 1
            
        print(f"✅ Ingestion Sync Cycle Complete: Captured {synced_count} tier-1 fixtures.")

    def _write_to_database(self, p):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # Ensure the schema here matches the new one
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fixtures (
                fixture_id INTEGER PRIMARY KEY, league_id INTEGER, league TEXT, season INTEGER, status TEXT, match_date TEXT,
                home_team TEXT, away_team TEXT, home_odds REAL, draw_odds REAL, away_odds REAL,
                dnb_home_odds REAL, dnb_away_odds REAL, dc_home_odds REAL, dc_away_odds REAL,
                over_15_odds REAL, under_35_odds REAL
            )
        """)
        
        cursor.execute("""
            INSERT OR REPLACE INTO fixtures (
                fixture_id, league_id, league, season, status, match_date, home_team, away_team, home_odds, draw_odds, away_odds,
                dnb_home_odds, dnb_away_odds, dc_home_odds, dc_away_odds, over_15_odds, under_35_odds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            p["fixture_id"], p["league_id"], p["league"], p["season"], p["status"], p["match_date"], p["home_team"], p["away_team"],
            p["home_odds"], p["draw_odds"], p["away_odds"], p["dnb_home_odds"], p["dnb_away_odds"],
            p["dc_home_odds"], p["dc_away_odds"], p["over_15_odds"], p["under_35_odds"]
        ))
        conn.commit()
        conn.close()
