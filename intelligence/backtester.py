import sqlite3
import datetime
from loguru import logger
from typing import List, Dict, Any
from build_acca import AccaBuilder

class Backtester:
    def __init__(self, db_path="database/athena.db"):
        self.db_path = db_path
        self.builder = AccaBuilder()

    def get_actual_result(self, fixture_id: int) -> Dict[str, Any]:
        """Fetch actual score from results or historical_matches table."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT home_score, away_score FROM results WHERE fixture_id = ?", (fixture_id,))
        row = cursor.fetchone()
        if not row:
            cursor.execute("SELECT home_goals as home_score, away_goals as away_score FROM historical_matches WHERE fixture_id = ?", (fixture_id,))
            row = cursor.fetchone()
        conn.close()
        if row:
            return dict(row)
        return None

    def grade_market(self, market: str, home_score: int, away_score: int) -> str:
        """
        Grades a betting market against the actual score.
        Returns: 'WIN', 'LOSS', 'VOID'
        """
        total = home_score + away_score
        
        # 1X2
        if market == "1X2_1": return "WIN" if home_score > away_score else "LOSS"
        if market == "1X2_X": return "WIN" if home_score == away_score else "LOSS"
        if market == "1X2_2": return "WIN" if away_score > home_score else "LOSS"
        
        # Early Payouts (Assumes if they won by 2 at any point, or won outright, we mark WIN for simplicity in backtest)
        if market == "1X2_2UP_HOME": return "WIN" if home_score > away_score or (home_score - away_score >= 2) else "LOSS"
        if market == "1X2_2UP_AWAY": return "WIN" if away_score > home_score or (away_score - home_score >= 2) else "LOSS"

        # Double Chance
        if market == "DC_1X": return "WIN" if home_score >= away_score else "LOSS"
        if market == "DC_X2": return "WIN" if away_score >= home_score else "LOSS"
        if market == "DC_12": return "WIN" if home_score != away_score else "LOSS"
        
        # Over/Under
        if market == "OVER_15": return "WIN" if total > 1 else "LOSS"
        if market == "OVER_25": return "WIN" if total > 2 else "LOSS"
        if market == "OVER_35": return "WIN" if total > 3 else "LOSS"
        if market == "UNDER_25": return "WIN" if total < 3 else "LOSS"
        if market == "UNDER_35": return "WIN" if total < 4 else "LOSS"
        
        # GG/BTTS
        if market == "GG_YES": return "WIN" if home_score > 0 and away_score > 0 else "LOSS"
        if market == "GG_NO": return "WIN" if home_score == 0 or away_score == 0 else "LOSS"
        
        # Asian Handicap (simplified)
        if market == "AH_HOME_PLUS_15": return "WIN" if (home_score + 1.5) > away_score else "LOSS"
        if market == "AH_AWAY_PLUS_15": return "WIN" if (away_score + 1.5) > home_score else "LOSS"
        if market == "AH_HOME_MINUS_15": return "WIN" if (home_score - 1.5) > away_score else "LOSS"
        if market == "AH_AWAY_MINUS_15": return "WIN" if (away_score - 1.5) > home_score else "LOSS"
        
        # Draw No Bet
        if market == "DNB_HOME": 
            return "WIN" if home_score > away_score else ("VOID" if home_score == away_score else "LOSS")
        if market == "DNB_AWAY": 
            return "WIN" if away_score > home_score else ("VOID" if home_score == away_score else "LOSS")
            
        # Win to Nil
        if market == "HOME_WIN_TO_NIL_YES": return "WIN" if home_score > 0 and away_score == 0 else "LOSS"
        if market == "HOME_WIN_TO_NIL_NO": return "LOSS" if home_score > 0 and away_score == 0 else "WIN"
        if market == "AWAY_WIN_TO_NIL_YES": return "WIN" if away_score > 0 and home_score == 0 else "LOSS"
        if market == "AWAY_WIN_TO_NIL_NO": return "LOSS" if away_score > 0 and home_score == 0 else "WIN"
        
        # Win Either Half (Assuming team won the match, they likely won a half. Imperfect but functional baseline)
        if market == "HOME_WIN_EITHER_HALF": return "WIN" if home_score > away_score else "LOSS"
        if market == "AWAY_WIN_EITHER_HALF": return "WIN" if away_score > home_score else "LOSS"
        
        # Combos
        if market == "HOME_OR_OVER_25": return "WIN" if home_score > away_score or total > 2 else "LOSS"
        if market == "AWAY_OR_OVER_25": return "WIN" if away_score > home_score or total > 2 else "LOSS"
        if market == "DRAW_OR_OVER_25": return "WIN" if home_score == away_score or total > 2 else "LOSS"

        # To Qualify (Requires aggregate data, marking VOID for backtest)
        if market in ["TO_QUALIFY_HOME", "TO_QUALIFY_AWAY"]: return "VOID"

        return "UNKNOWN"

    def run_backtest(self, days_ago: int, fold_size: int = 20, strict: bool = True):
        target_date = datetime.datetime.now() - datetime.timedelta(days=days_ago)
        start_iso = target_date.replace(hour=0, minute=0, second=0).isoformat()
        end_iso = target_date.replace(hour=23, minute=59, second=59).isoformat()

        # Custom DB fetch for the backtest
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                fixture_id, league, home_team, away_team, 
                match_date, status, data_source
            FROM fixtures
            WHERE status IN ('FT', 'AET', 'PEN')
              AND match_date >= ? AND match_date <= ?
            ORDER BY match_date ASC
        """, (start_iso, end_iso))
        rows = cursor.fetchall()
        db_fixtures = [dict(row) for row in rows]
        
        # If no finished fixtures in fixtures table for target date, fallback to historical_matches dataset
        if not db_fixtures:
            cursor.execute("""
                SELECT 
                    h.fixture_id, h.league, 
                    COALESCE(t_home.name, 'Home Team') as home_team, 
                    COALESCE(t_away.name, 'Away Team') as away_team, 
                    h.match_date, 'FT' as status, h.data_source
                FROM historical_matches h
                LEFT JOIN teams t_home ON h.home_id = t_home.id
                LEFT JOIN teams t_away ON h.away_id = t_away.id
                ORDER BY RANDOM()
                LIMIT ?
            """, (max(20, fold_size * 2),))
            rows = cursor.fetchall()
            db_fixtures = [dict(row) for row in rows]
            
        conn.close()

        if not db_fixtures:
            return {"success": False, "error": f"No finished fixtures found for {days_ago} days ago"}

        all_analyzed = []
        for db_fixture in db_fixtures:
            prediction = self.builder.analyst.compile_master_fixture_prediction(
                fixture_context=db_fixture
            )
            
            match_data = {
                "fixture_id": db_fixture.get("fixture_id"),
                "league": db_fixture.get("league"),
                "fixture": f"{db_fixture.get('home_team')} vs {db_fixture.get('away_team')}",
                "home_team": db_fixture.get("home_team"),
                "away_team": db_fixture.get("away_team"),
                "verdict": prediction["recommended_analytical_verdict"],
                "edge": prediction["edge_differential"],
                "upset_alert": prediction["upset_alert"],
                "risk_score": prediction["risk_score"],
                "viable_markets": prediction.get("viable_markets", [])
            }
            all_analyzed.append(match_data)

        # Acca generation logic
        eligible_matches = self.builder.acca_filter.build_filtered_acca(all_analyzed, target_size=fold_size)
        acca = self.builder.acca_engine.generate_accumulator(eligible_matches, fold_size=fold_size, strict=strict)

        if not acca.get("legs"):
            return {"success": False, "error": "No matches passed filtering"}

        # Grade the acca
        wins = 0
        losses = 0
        voids = 0
        graded_legs = []

        for leg in acca["legs"]:
            actual = None
            raw_verdict = None
            fixture_id = leg.get('fixture_id')
            
            # Find the original match in eligible_matches
            matched_fixture = next((m for m in eligible_matches if m["fixture"] == leg["fixture"]), None)
            if matched_fixture:
                if not fixture_id:
                    fixture_id = matched_fixture["fixture_id"]
                raw_verdict = matched_fixture.get("verdict")
            
            if fixture_id:
                actual = self.get_actual_result(fixture_id)
                
            if not actual or not raw_verdict:
                grade = "VOID"
            else:
                grade = self.grade_market(raw_verdict, actual['home_score'], actual['away_score'])
            
            if grade == "WIN": wins += 1
            elif grade == "LOSS": losses += 1
            else: voids += 1
            
            leg['grade'] = grade
            leg['actual_score'] = f"{actual['home_score']}-{actual['away_score']}" if actual else "N/A"
            graded_legs.append(leg)

        strike_rate = wins / (wins + losses) if (wins + losses) > 0 else 0

        return {
            "success": True,
            "date": target_date.strftime("%Y-%m-%d"),
            "legs": graded_legs,
            "wins": wins,
            "losses": losses,
            "voids": voids,
            "strike_rate": strike_rate
        }
