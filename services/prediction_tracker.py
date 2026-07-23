#!/usr/bin/env python3
import sqlite3
import json
from datetime import datetime
from database.database import Database

class PredictionTracker:
    def __init__(self, db: Database = None):
        self.db = db if db else Database()
        
    def record_prediction(self, fixture_id: int, market: str, prob: float, confidence: float, edge: float, is_value: bool):
        """Records a prediction when an acca is generated."""
        try:
            with self.db.connect() as conn:
                conn.execute("""
                    INSERT INTO predictions 
                    (fixture_id, market, probability, confidence, edge, is_value_bet, recommendation, actual_result)
                    VALUES (?, ?, ?, ?, ?, ?, 1, NULL)
                """, (fixture_id, market, prob, confidence, edge, int(is_value)))
                conn.commit()
        except Exception as e:
            pass # Fail silently for tracking

    def update_actual_results(self):
        """Finds completed matches and updates the actual_result for pending predictions."""
        with self.db.connect() as conn:
            # Get pending predictions
            cur = conn.execute("""
                SELECT p.id, p.fixture_id, p.market, p.probability, h.home_goals, h.away_goals
                FROM predictions p
                JOIN historical_matches h ON p.fixture_id = h.fixture_id
                WHERE p.actual_result IS NULL AND h.home_goals IS NOT NULL
            """)
            pending = cur.fetchall()
            
            for row in pending:
                pred_id, fix_id, market, prob, hg, ag = row
                
                result = self._evaluate_market(market, hg, ag)
                
                conn.execute("UPDATE predictions SET actual_result = ? WHERE id = ?", (result, pred_id))
            
            conn.commit()
            
    def _evaluate_market(self, market: str, hg: int, ag: int) -> str:
        """Determines if the prediction won or lost based on actual goals."""
        if market == "DC_1X":
            return "WIN" if hg >= ag else "LOSS"
        elif market == "DC_X2":
            return "WIN" if ag >= hg else "LOSS"
        elif market == "DNB_HOME":
            if hg > ag: return "WIN"
            if hg == ag: return "VOID"
            return "LOSS"
        elif market == "DNB_AWAY":
            if ag > hg: return "WIN"
            if ag == hg: return "VOID"
            return "LOSS"
        elif market == "OVER_15":
            return "WIN" if (hg + ag) > 1 else "LOSS"
        elif market == "OVER_25":
            return "WIN" if (hg + ag) > 2 else "LOSS"
        elif market == "UNDER_35":
            return "WIN" if (hg + ag) < 4 else "LOSS"
        elif market == "UNDER_45":
            return "WIN" if (hg + ag) < 5 else "LOSS"
        elif market == "GG_YES":
            return "WIN" if (hg > 0 and ag > 0) else "LOSS"
        elif market == "GG_NO":
            return "WIN" if (hg == 0 or ag == 0) else "LOSS"
        elif market == "HOME_WIN":
            return "WIN" if hg > ag else "LOSS"
        elif market == "AWAY_WIN":
            return "WIN" if ag > hg else "LOSS"
        else:
            # Fallback for complex markets
            return "VOID"
            
    def get_accuracy_metrics(self) -> dict:
        """Returns accuracy statistics by market and edge."""
        metrics = {"total": 0, "wins": 0, "losses": 0, "voids": 0, "by_market": {}, "by_edge": {}}
        
        with self.db.connect() as conn:
            cur = conn.execute("SELECT market, edge, actual_result FROM predictions WHERE actual_result IS NOT NULL")
            rows = cur.fetchall()
            
            for row in rows:
                market, edge, result = row
                
                metrics["total"] += 1
                if result == "WIN": metrics["wins"] += 1
                elif result == "LOSS": metrics["losses"] += 1
                elif result == "VOID": metrics["voids"] += 1
                
                if market not in metrics["by_market"]:
                    metrics["by_market"][market] = {"total": 0, "wins": 0}
                
                metrics["by_market"][market]["total"] += 1
                if result == "WIN":
                    metrics["by_market"][market]["wins"] += 1
                    
                # Edge bands
                edge_band = "0.00-0.05"
                if edge >= 0.15: edge_band = "0.15+"
                elif edge >= 0.10: edge_band = "0.10-0.15"
                elif edge >= 0.05: edge_band = "0.05-0.10"
                
                if edge_band not in metrics["by_edge"]:
                    metrics["by_edge"][edge_band] = {"total": 0, "wins": 0}
                    
                metrics["by_edge"][edge_band]["total"] += 1
                if result == "WIN":
                    metrics["by_edge"][edge_band]["wins"] += 1
                    
        return metrics
