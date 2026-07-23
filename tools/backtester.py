#!/usr/bin/env python3
import sys
import os
import argparse
import sqlite3
from datetime import datetime, timedelta
from rich.console import Console

# Add parent directory to path to allow importing project modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.database import Database
from build_acca import AccaBuilder
from services.prediction_tracker import PredictionTracker

console = Console()

class Backtester:
    def __init__(self, start_date: str, end_date: str, initial_bankroll: float = 1000.0, folds: int = 2):
        self.start_date = datetime.strptime(start_date, "%Y-%m-%d")
        self.end_date = datetime.strptime(end_date, "%Y-%m-%d")
        self.bankroll = initial_bankroll
        self.initial_bankroll = initial_bankroll
        self.folds = folds
        self.db = Database()
        self.builder = AccaBuilder()
        self.tracker = PredictionTracker(self.db)
        
    def _get_fixtures_for_date(self, target_date: datetime) -> list:
        date_str = target_date.strftime("%Y-%m-%d")
        
        with self.db.connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT h.fixture_id, h.league, t1.name as home_team, t2.name as away_team, 
                       h.match_date, h.home_goals, h.away_goals, h.home_pre_elo, h.away_pre_elo
                FROM historical_matches h
                JOIN teams t1 ON h.home_id = t1.team_id
                JOIN teams t2 ON h.away_id = t2.team_id
                WHERE h.match_date LIKE ?
                  AND h.home_pre_elo IS NOT NULL AND h.away_pre_elo IS NOT NULL
            """, (f"{date_str}%",))
            
            rows = cursor.fetchall()
            fixtures = []
            for row in rows:
                fixtures.append({
                    "fixture_id": row["fixture_id"],
                    "league": row["league"],
                    "home_team": row["home_team"],
                    "away_team": row["away_team"],
                    "match_date": row["match_date"],
                    "home_pre_elo": row["home_pre_elo"],
                    "away_pre_elo": row["away_pre_elo"],
                    "actual_home_goals": row["home_goals"],
                    "actual_away_goals": row["away_goals"],
                    "status": "FT",
                    "data_source": "historical"
                })
            return fixtures

    def _evaluate_acca(self, acca_legs: list) -> float:
        """Returns the payout for the acca. 0.0 if it lost."""
        total_odds = 1.0
        
        for leg in acca_legs:
            market = leg["verdict"]
            hg = leg.get("actual_home_goals")
            ag = leg.get("actual_away_goals")
            
            # Simple odds lookup - we'll just mock odds based on edge since historical odds aren't stored
            # In a real scenario, we'd need historical odds. For now, assume average odds of 1.4 per leg
            leg_odds = 1.4
            
            result = self.tracker._evaluate_market(market, hg, ag)
            if result == "LOSS":
                return 0.0
            elif result == "WIN":
                total_odds *= leg_odds
            # VOID just doesn't multiply odds
            
        return total_odds

    def run(self):
        console.print(f"[cyan]🚀 Starting Backtest from {self.start_date.date()} to {self.end_date.date()}...[/cyan]")
        
        current_date = self.start_date
        total_accas = 0
        won_accas = 0
        total_staked = 0.0
        
        while current_date <= self.end_date:
            console.print(f"\n[bold magenta]📅 Running for {current_date.date()}[/bold magenta]")
            fixtures = self._get_fixtures_for_date(current_date)
            
            if not fixtures:
                console.print("No historical matches found for this date.")
                current_date += timedelta(days=1)
                continue
                
            console.print(f"Found {len(fixtures)} matches.")
            
            # Run the analytical pipeline with our historical override
            analyzed = self.builder.pipeline.run_pipeline_snapshot(execution_limit=1000, override_fixtures=fixtures)
            
            # Reattach actual goals for evaluation
            for a in analyzed:
                fix_orig = next((f for f in fixtures if f["home_team"] == a["home_team"] and f["away_team"] == a["away_team"]), None)
                if fix_orig:
                    a["actual_home_goals"] = fix_orig["actual_home_goals"]
                    a["actual_away_goals"] = fix_orig["actual_away_goals"]
            
            # Filter matches using strict criteria
            safe_matches = self.builder.acca_filter.filter_matches(analyzed)
            
            if len(safe_matches) >= self.folds:
                # Build the acca
                acca = self.builder.acca_engine.build_accumulator(safe_matches, fold_size=self.folds)
                
                if acca:
                    total_accas += 1
                    stake = self.bankroll * 0.05 # Kelly / fixed 5% stake
                    total_staked += stake
                    
                    console.print(f"Generated {self.folds}-fold Acca! Staking £{stake:.2f}")
                    
                    # Track individual predictions
                    for leg in acca:
                        self.tracker.record_prediction(
                            fixture_id=0, # Mock fixture ID
                            market=leg["verdict"],
                            prob=0.8,
                            confidence=1.0,
                            edge=leg["edge"],
                            is_value=True
                        )
                        
                    payout_multiplier = self._evaluate_acca(acca)
                    if payout_multiplier > 0:
                        won = stake * payout_multiplier
                        profit = won - stake
                        self.bankroll += profit
                        won_accas += 1
                        console.print(f"[green]✅ Acca WON! Payout: £{won:.2f} (Bankroll: £{self.bankroll:.2f})[/green]")
                    else:
                        self.bankroll -= stake
                        console.print(f"[red]❌ Acca LOST. (Bankroll: £{self.bankroll:.2f})[/red]")
            else:
                console.print(f"Only {len(safe_matches)} safe matches found. Need {self.folds} for acca.")
            
            current_date += timedelta(days=1)
            
        # Summary
        console.print("\n[bold cyan]===== BACKTEST COMPLETE =====[/bold cyan]")
        console.print(f"Start Bankroll: £{self.initial_bankroll:.2f}")
        console.print(f"End Bankroll: £{self.bankroll:.2f}")
        console.print(f"Profit/Loss: £{self.bankroll - self.initial_bankroll:.2f}")
        console.print(f"Total Accas: {total_accas}")
        console.print(f"Win Rate: {(won_accas/total_accas*100) if total_accas > 0 else 0:.1f}%")
        console.print(f"ROI: {((self.bankroll - self.initial_bankroll)/total_staked*100) if total_staked > 0 else 0:.1f}%")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ATHENA Backtesting Engine")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--folds", type=int, default=2, help="Accumulator fold size")
    args = parser.parse_args()
    
    tester = Backtester(start_date=args.start, end_date=args.end, folds=args.folds)
    tester.run()
