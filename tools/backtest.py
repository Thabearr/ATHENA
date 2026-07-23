import os
import sys
import sqlite3
import argparse
from tqdm import tqdm
import math

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.database import Database
from engine.risk_engine import RiskEngine
from intelligence.fatigue import FatigueEngine
from intelligence.form import FormEngine
from intelligence.referee import RefereeEngine
from intelligence.match_analyst import MatchAnalyst

def setup_backtest_table(db: Database):
    with db.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backtest_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fixture_id INTEGER,
                match_date TEXT,
                home_team TEXT,
                away_team TEXT,
                data_source TEXT,
                actual_home_goals INTEGER,
                actual_away_goals INTEGER,
                actual_outcome TEXT,
                predicted_verdict TEXT,
                predicted_prob REAL,
                edge REAL,
                risk_score REAL,
                upset_alert INTEGER,
                stale_data INTEGER,
                grade TEXT
            )
        """)
        # Clear existing backtest results
        cursor.execute("DELETE FROM backtest_results")
        conn.commit()

def calculate_actual_outcome(home_goals, away_goals):
    if home_goals > away_goals:
        return 'HOME_WIN'
    elif away_goals > home_goals:
        return 'AWAY_WIN'
    return 'DRAW'

def grade_prediction(verdict: str, home_goals: int, away_goals: int) -> str:
    from intelligence.backtester import Backtester
    bt = Backtester(None)
    return bt.grade_market(verdict, home_goals, away_goals)

def run_backtest():
    db = Database()
    setup_backtest_table(db)

    # Initialize engines
    from services.statistics_service import StatisticsService
    from services.team_form_service import TeamFormService
    
    stats_svc = StatisticsService()
    form_svc = TeamFormService()
    
    risk_eng = RiskEngine()
    form_eng = FormEngine(stats_svc, form_svc)
    fatigue_eng = FatigueEngine()
    ref_eng = RefereeEngine()
    analyst = MatchAnalyst(
        form_engine=form_eng,
        motivation_engine=None, # Not fully implemented
        weather_engine=None,    # Not fully implemented
        fatigue_engine=fatigue_eng,
        injury_engine=None,     # Not fully implemented
        referee_engine=ref_eng,
        risk_engine=risk_eng
    )

    with db.connect() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Chronological fetch (oldest to newest)
        cursor.execute("""
            SELECT h.id, h.fixture_id, h.league, 
                   COALESCE(t_home.name, 'Home Team') as home_team, 
                   COALESCE(t_away.name, 'Away Team') as away_team,
                   h.home_id, h.away_id, h.match_date, 
                   h.home_goals, h.away_goals, h.data_source,
                   t_home.elo_rating as home_pre_elo,
                   t_away.elo_rating as away_pre_elo
            FROM historical_matches h
            LEFT JOIN teams t_home ON h.home_id = t_home.id
            LEFT JOIN teams t_away ON h.away_id = t_away.id
            WHERE h.home_goals IS NOT NULL AND h.away_goals IS NOT NULL
            ORDER BY h.match_date ASC
        """)
        matches = cursor.fetchall()
        
    print(f"Starting chronologically honest backtest on {len(matches)} historical matches...")
    
    results_to_insert = []
    
    for row in tqdm(matches):
        match_dict = dict(row)
        fixture_context = {
            'fixture_id': match_dict['fixture_id'],
            'match_date': match_dict['match_date'],
            'home_team': match_dict['home_team'],
            'away_team': match_dict['away_team'],
            'home_id': match_dict['home_id'],
            'away_id': match_dict['away_id'],
            'is_knockout': False,
            'home_pre_elo': match_dict['home_pre_elo'] or 1500,
            'away_pre_elo': match_dict['away_pre_elo'] or 1500,
            'is_backtest': True
        }
        
        try:
            # Predict using MatchAnalyst (lookahead bias protected)
            prediction = analyst.compile_master_fixture_prediction(fixture_context)
            
            # Record outcome
            home_goals = match_dict['home_goals']
            away_goals = match_dict['away_goals']
            actual_outcome = calculate_actual_outcome(home_goals, away_goals)
            
            verdict = prediction['recommended_analytical_verdict']
            grade = grade_prediction(verdict, home_goals, away_goals)
            
            viable_markets = prediction.get('viable_markets', [])
            predicted_prob = 0.0
            edge = prediction.get('edge_differential', 0.0)
            if viable_markets and viable_markets[0]['verdict'] == verdict:
                predicted_prob = viable_markets[0]['prob']
            
            results_to_insert.append((
                match_dict['fixture_id'], match_dict['match_date'],
                match_dict['home_team'], match_dict['away_team'], match_dict['data_source'],
                home_goals, away_goals, actual_outcome,
                verdict, predicted_prob, edge,
                prediction['risk_score'], int(prediction['upset_alert']),
                int(prediction['stale_data']), grade
            ))
            
        except Exception as e:
            print(f"Error processing fixture {match_dict['fixture_id']}: {e}")
            continue
            
    # Batch insert results
    with db.connect() as conn:
        cursor = conn.cursor()
        cursor.executemany("""
            INSERT INTO backtest_results (
                fixture_id, match_date, home_team, away_team, data_source,
                actual_home_goals, actual_away_goals, actual_outcome,
                predicted_verdict, predicted_prob, edge, risk_score,
                upset_alert, stale_data, grade
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, results_to_insert)
        conn.commit()
        
    generate_report(db)

def compute_brier_score(prob, grade):
    # For a binary outcome where WIN=1, LOSS=0. VOID is ignored in aggregation.
    actual = 1.0 if grade == 'WIN' else 0.0
    return (prob - actual) ** 2

def generate_report(db: Database):
    with db.connect() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM backtest_results")
        results = cursor.fetchall()
        
    total_matches = len(results)
    if total_matches == 0:
        print("No results to analyze.")
        return
        
    wins = sum(1 for r in results if r['grade'] == 'WIN')
    losses = sum(1 for r in results if r['grade'] == 'LOSS')
    voids = sum(1 for r in results if r['grade'] == 'VOID')
    
    valid_matches = wins + losses
    accuracy = (wins / valid_matches) * 100 if valid_matches > 0 else 0
    
    print("\n" + "="*50)
    print("ATHENA CHRONOLOGICAL BACKTEST REPORT")
    print("="*50)
    print(f"Total Matches Analyzed: {total_matches}")
    print(f"Overall Accuracy: {accuracy:.2f}% (Wins: {wins}, Losses: {losses}, Voids: {voids})")
    
    # Brier Score & Log Loss
    brier_scores = []
    log_losses = []
    for r in results:
        if r['grade'] in ('WIN', 'LOSS'):
            prob = r['predicted_prob']
            actual = 1.0 if r['grade'] == 'WIN' else 0.0
            
            # Bound prob to avoid log(0)
            p = max(min(prob, 0.999), 0.001)
            b_score = (p - actual) ** 2
            brier_scores.append(b_score)
            
            l_loss = -(actual * math.log(p) + (1 - actual) * math.log(1 - p))
            log_losses.append(l_loss)
            
    avg_brier = sum(brier_scores) / len(brier_scores) if brier_scores else 0
    avg_log_loss = sum(log_losses) / len(log_losses) if log_losses else 0
    
    print(f"Brier Score: {avg_brier:.4f} (Lower is better, perfect=0.0)")
    print(f"Log Loss: {avg_log_loss:.4f} (Lower is better, perfect=0.0)")
    
    # Calibration Table
    print("\n--- Calibration Table (Confidence vs Actual Win Rate) ---")
    buckets = {
        "50-60%": {"count": 0, "wins": 0},
        "60-70%": {"count": 0, "wins": 0},
        "70-80%": {"count": 0, "wins": 0},
        "80-90%": {"count": 0, "wins": 0},
        "90-100%": {"count": 0, "wins": 0},
    }
    for r in results:
        if r['grade'] in ('WIN', 'LOSS'):
            prob = r['predicted_prob']
            bucket_key = None
            if 0.50 <= prob < 0.60: bucket_key = "50-60%"
            elif 0.60 <= prob < 0.70: bucket_key = "60-70%"
            elif 0.70 <= prob < 0.80: bucket_key = "70-80%"
            elif 0.80 <= prob < 0.90: bucket_key = "80-90%"
            elif 0.90 <= prob <= 1.00: bucket_key = "90-100%"
            
            if bucket_key:
                buckets[bucket_key]['count'] += 1
                if r['grade'] == 'WIN':
                    buckets[bucket_key]['wins'] += 1
                    
    print(f"{'Confidence':<15} | {'Matches':<10} | {'Actual Win %'}")
    print("-" * 45)
    for k, v in buckets.items():
        win_pct = (v['wins'] / v['count'] * 100) if v['count'] > 0 else 0
        print(f"{k:<15} | {v['count']:<10} | {win_pct:.1f}%")

    # Upset Alert Precision
    print("\n--- Upset Alert Performance ---")
    upset_flagged = [r for r in results if r['upset_alert'] == 1 and r['grade'] in ('WIN', 'LOSS')]
    unflagged = [r for r in results if r['upset_alert'] == 0 and r['grade'] in ('WIN', 'LOSS')]
    
    upset_win_rate = (sum(1 for r in upset_flagged if r['grade'] == 'WIN') / len(upset_flagged) * 100) if upset_flagged else 0
    unflagged_win_rate = (sum(1 for r in unflagged if r['grade'] == 'WIN') / len(unflagged) * 100) if unflagged else 0
    
    print(f"Matches Flagged as Upset Risk: {len(upset_flagged)} (Model Win Rate: {upset_win_rate:.1f}%)")
    print(f"Matches NOT Flagged (Safe): {len(unflagged)} (Model Win Rate: {unflagged_win_rate:.1f}%)")
    
    if upset_win_rate < unflagged_win_rate:
        print("✅ Upset Alert is working: Flagged matches perform worse, indicating true risk detection.")
    else:
        print("❌ Upset Alert may need tuning: Flagged matches perform better or equal to unflagged matches.")
        
    # Breakdown by Data Source
    print("\n--- Performance by Data Source ---")
    sources = {}
    for r in results:
        if r['grade'] in ('WIN', 'LOSS'):
            src = r['data_source'] or "unknown"
            if src not in sources:
                sources[src] = {"count": 0, "wins": 0}
            sources[src]['count'] += 1
            if r['grade'] == 'WIN':
                sources[src]['wins'] += 1
                
    for src, v in sources.items():
        win_pct = (v['wins'] / v['count']) * 100
        print(f"{src:<30} | {v['count']:<6} matches | {win_pct:.1f}% Win Rate")

if __name__ == "__main__":
    run_backtest()
