import os
import joblib
import sqlite3
import numpy as np
import pandas as pd
import logging
from database.database import Database

logger = logging.getLogger("athena.ml_engine")
MODEL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'models'))

class MLEngine:
    def __init__(self):
        self.db = Database()
        self.clf = None
        self.reg = None
        self._load_models()
        
    def _load_models(self):
        clf_path = os.path.join(MODEL_DIR, 'outcome_model.joblib')
        reg_path = os.path.join(MODEL_DIR, 'goals_model.joblib')
        
        if os.path.exists(clf_path) and os.path.exists(reg_path):
            self.clf = joblib.load(clf_path)
            self.reg = joblib.load(reg_path)
            logger.info("Loaded ML models successfully.")
        else:
            logger.warning("ML models not found. Run tools/train_model.py to train them. Falling back to heuristic only.")

    def is_ready(self) -> bool:
        return self.clf is not None and self.reg is not None

    def _get_team_rolling_stats(self, team_id: int) -> dict:
        """Fetch rolling average of xG, possession, GF, GA over the last 5 matches for a team."""
        with self.db.connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get last 5 matches for this team where xg is not null
            cursor.execute("""
                SELECT home_id, away_id, home_goals, away_goals, 
                       home_xg, away_xg, home_possession, away_possession
                FROM historical_matches
                WHERE (home_id = ? OR away_id = ?)
                  AND home_xg IS NOT NULL
                ORDER BY match_date DESC
                LIMIT 5
            """, (team_id, team_id))
            
            rows = cursor.fetchall()
            
            if not rows or len(rows) < 1:
                # Default fallback if no data
                return {'rolling_xg': 1.2, 'rolling_poss': 50, 'rolling_gf': 1.2, 'rolling_ga': 1.2}
                
            xgs = []
            possessions = []
            gfs = []
            gas = []
            
            for r in rows:
                if r['home_id'] == team_id:
                    xgs.append(r['home_xg'])
                    possessions.append(r['home_possession'])
                    gfs.append(r['home_goals'])
                    gas.append(r['away_goals'])
                else:
                    xgs.append(r['away_xg'])
                    possessions.append(r['away_possession'])
                    gfs.append(r['away_goals'])
                    gas.append(r['home_goals'])
                    
            return {
                'rolling_xg': np.mean(xgs),
                'rolling_poss': np.mean(possessions),
                'rolling_gf': np.mean(gfs),
                'rolling_ga': np.mean(gas)
            }

    def predict(self, home_id: int, away_id: int, home_elo: int, away_elo: int) -> dict:
        """
        Predict probabilities using the ML model.
        Returns dict with 1X2 probabilities and expected total goals.
        """
        if not self.is_ready():
            return None
            
        home_stats = self._get_team_rolling_stats(home_id)
        away_stats = self._get_team_rolling_stats(away_id)
        
        # Construct feature vector exactly as trained
        # 'home_pre_elo', 'away_pre_elo', 'elo_diff',
        # 'home_rolling_xg', 'away_rolling_xg', 'xg_diff',
        # 'home_rolling_poss', 'away_rolling_poss', 'poss_diff',
        # 'home_rolling_gf', 'away_rolling_gf', 'gf_diff',
        # 'home_rolling_ga', 'away_rolling_ga', 'ga_diff'
        
        features = [
            home_elo, 
            away_elo, 
            home_elo - away_elo,
            
            home_stats['rolling_xg'], 
            away_stats['rolling_xg'], 
            home_stats['rolling_xg'] - away_stats['rolling_xg'],
            
            home_stats['rolling_poss'], 
            away_stats['rolling_poss'], 
            home_stats['rolling_poss'] - away_stats['rolling_poss'],
            
            home_stats['rolling_gf'], 
            away_stats['rolling_gf'], 
            home_stats['rolling_gf'] - away_stats['rolling_gf'],
            
            home_stats['rolling_ga'], 
            away_stats['rolling_ga'], 
            home_stats['rolling_ga'] - away_stats['rolling_ga']
        ]
        
        X = np.array(features).reshape(1, -1)
        
        # Class order is [-1, 0, 1] for Away Win, Draw, Home Win
        probs = self.clf.predict_proba(X)[0]
        classes = self.clf.classes_
        
        prob_dict = {
            "HOME_WIN": 0.0,
            "DRAW": 0.0,
            "AWAY_WIN": 0.0
        }
        
        for i, c in enumerate(classes):
            if c == 1:
                prob_dict["HOME_WIN"] = probs[i]
            elif c == 0:
                prob_dict["DRAW"] = probs[i]
            elif c == -1:
                prob_dict["AWAY_WIN"] = probs[i]
                
        expected_goals = self.reg.predict(X)[0]
        
        return {
            "probabilities": prob_dict,
            "expected_total_goals": expected_goals
        }
