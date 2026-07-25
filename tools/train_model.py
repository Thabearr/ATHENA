#!/usr/bin/env python3
import sys
import os
import sqlite3
import pandas as pd
import numpy as np
import joblib
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report, mean_squared_error
from sklearn.calibration import CalibratedClassifierCV
from rich.console import Console

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.database import Database

console = Console()
MODEL_DIR = os.path.join(os.path.dirname(__file__), '..', 'models')

def prepare_data(db):
    console.print("[cyan]Loading historical data from database...[/cyan]")
    with db.connect() as conn:
        df = pd.read_sql_query("""
            SELECT h.match_date, h.home_id, h.away_id, h.home_goals, h.away_goals,
                   h.home_pre_elo, h.away_pre_elo, h.home_xg, h.away_xg,
                   h.home_possession, h.away_possession
            FROM historical_matches h
            WHERE h.home_pre_elo IS NOT NULL 
              AND h.away_pre_elo IS NOT NULL
            ORDER BY h.match_date ASC
        """, conn)

    if df.empty:
        console.print("[red]No data found for training.[/red]")
        return pd.DataFrame()

    console.print(f"Loaded {len(df)} matches. Calculating rolling features...")

    # We need to reshape the dataframe to team-level to calculate rolling averages
    home_df = df[['match_date', 'home_id', 'home_xg', 'home_possession', 'home_goals', 'away_goals']].copy()
    home_df.columns = ['match_date', 'team_id', 'xg_for', 'possession', 'goals_for', 'goals_against']
    home_df['is_home'] = 1

    away_df = df[['match_date', 'away_id', 'away_xg', 'away_possession', 'away_goals', 'home_goals']].copy()
    away_df.columns = ['match_date', 'team_id', 'xg_for', 'possession', 'goals_for', 'goals_against']
    # possession for away team might be away_possession. Wait, if away_possession is null, we can't use it.
    away_df['is_home'] = 0

    team_df = pd.concat([home_df, away_df]).sort_values('match_date')
    
    # Calculate rolling averages (last 5 matches), shift by 1 to exclude the current match!
    team_df['rolling_xg'] = team_df.groupby('team_id')['xg_for'].transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())
    team_df['rolling_possession'] = team_df.groupby('team_id')['possession'].transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())
    team_df['rolling_gf'] = team_df.groupby('team_id')['goals_for'].transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())
    team_df['rolling_ga'] = team_df.groupby('team_id')['goals_against'].transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())

    # Map back to original dataframe
    team_rolling = team_df[['match_date', 'team_id', 'rolling_xg', 'rolling_possession', 'rolling_gf', 'rolling_ga']]
    
    # Merge home stats
    df = df.merge(team_rolling, left_on=['match_date', 'home_id'], right_on=['match_date', 'team_id'], how='left')
    df = df.rename(columns={
        'rolling_xg': 'home_rolling_xg', 
        'rolling_possession': 'home_rolling_poss',
        'rolling_gf': 'home_rolling_gf',
        'rolling_ga': 'home_rolling_ga'
    }).drop(columns=['team_id'])

    # Merge away stats
    df = df.merge(team_rolling, left_on=['match_date', 'away_id'], right_on=['match_date', 'team_id'], how='left')
    df = df.rename(columns={
        'rolling_xg': 'away_rolling_xg', 
        'rolling_possession': 'away_rolling_poss',
        'rolling_gf': 'away_rolling_gf',
        'rolling_ga': 'away_rolling_ga'
    }).drop(columns=['team_id'])

    # Drop matches where we don't have rolling history (first few matches of the dataset)
    df = df.dropna(subset=['home_rolling_xg', 'away_rolling_xg', 'home_rolling_poss', 'away_rolling_poss'])

    # Define Target: 1 for Home Win, 0 for Draw, -1 for Away Win
    df['outcome'] = np.where(df['home_goals'] > df['away_goals'], 1, 
                             np.where(df['home_goals'] < df['away_goals'], -1, 0))
    df['total_goals'] = df['home_goals'] + df['away_goals']
    
    # Market specific labels
    df['btts'] = np.where((df['home_goals'] > 0) & (df['away_goals'] > 0), 1, 0)
    df['over_25'] = np.where(df['total_goals'] > 2.5, 1, 0)
    df['ah_home_plus_15'] = np.where(df['home_goals'] - df['away_goals'] > -1.5, 1, 0)
    df['ah_away_plus_15'] = np.where(df['away_goals'] - df['home_goals'] > -1.5, 1, 0)
    
    # Confidence target: 1 if the ELO favorite wins, 0 if it's a draw or upset
    df['is_predictable'] = np.where(
        ((df['home_pre_elo'] > df['away_pre_elo']) & (df['outcome'] == 1)) |
        ((df['home_pre_elo'] < df['away_pre_elo']) & (df['outcome'] == -1)), 1, 0
    )

    # Define Features
    df['elo_diff'] = df['home_pre_elo'] - df['away_pre_elo']
    df['xg_diff'] = df['home_rolling_xg'] - df['away_rolling_xg']
    df['poss_diff'] = df['home_rolling_poss'] - df['away_rolling_poss']
    df['gf_diff'] = df['home_rolling_gf'] - df['away_rolling_gf']
    df['ga_diff'] = df['home_rolling_ga'] - df['away_rolling_ga']

    console.print(f"[green]Data preparation complete. {len(df)} matches ready for training.[/green]")
    return df

def train_models():
    os.makedirs(MODEL_DIR, exist_ok=True)
    db = Database()
    df = prepare_data(db)
    
    if df.empty or len(df) < 50:
        console.print("[yellow]Not enough data to train ML model. Please wait for backfill to finish.[/yellow]")
        return

    features = [
        'home_pre_elo', 'away_pre_elo', 'elo_diff',
        'home_rolling_xg', 'away_rolling_xg', 'xg_diff',
        'home_rolling_poss', 'away_rolling_poss', 'poss_diff',
        'home_rolling_gf', 'away_rolling_gf', 'gf_diff',
        'home_rolling_ga', 'away_rolling_ga', 'ga_diff'
    ]

    X = df[features]
    y_outcome = df['outcome']
    y_goals = df['total_goals']
    y_btts = df['btts']
    y_over25 = df['over_25']
    y_conf = df['is_predictable']
    y_ah_home = df['ah_home_plus_15']
    y_ah_away = df['ah_away_plus_15']

    X_train, X_test, y_out_train, y_out_test, y_goal_train, y_goal_test, y_btts_train, y_btts_test, y_o25_train, y_o25_test, y_conf_train, y_conf_test, y_ah_home_train, y_ah_home_test, y_ah_away_train, y_ah_away_test = train_test_split(
        X, y_outcome, y_goals, y_btts, y_over25, y_conf, y_ah_home, y_ah_away, test_size=0.2, random_state=42, shuffle=False # Time series, don't shuffle randomly
    )

    console.print("[cyan]Training Match Outcome Classifier (Calibrated Random Forest - Isotonic)...[/cyan]")
    base_clf = RandomForestClassifier(n_estimators=100, max_depth=10, min_samples_leaf=5, random_state=42)
    clf = CalibratedClassifierCV(estimator=base_clf, method='isotonic', cv=5)
    clf.fit(X_train, y_out_train)
    
    preds = clf.predict(X_test)
    acc = accuracy_score(y_out_test, preds)
    console.print(f"[bold green]Outcome Model Accuracy: {acc:.3f}[/bold green]")
    console.print(classification_report(y_out_test, preds))

    console.print("[cyan]Training Total Goals Regressor (Random Forest)...[/cyan]")
    reg = RandomForestRegressor(n_estimators=100, max_depth=10, min_samples_leaf=5, random_state=42)
    reg.fit(X_train, y_goal_train)
    
    goal_preds = reg.predict(X_test)
    mse = mean_squared_error(y_goal_test, goal_preds)
    console.print(f"[bold green]Goals Model MSE: {mse:.3f}[/bold green]")
    
    console.print("[cyan]Training BTTS Classifier (Calibrated Random Forest - Isotonic)...[/cyan]")
    base_btts = RandomForestClassifier(n_estimators=100, max_depth=10, min_samples_leaf=5, random_state=42)
    btts_clf = CalibratedClassifierCV(estimator=base_btts, method='isotonic', cv=5)
    btts_clf.fit(X_train, y_btts_train)

    console.print("[cyan]Training Over 2.5 Classifier (Calibrated Random Forest - Isotonic)...[/cyan]")
    base_o25 = RandomForestClassifier(n_estimators=100, max_depth=10, min_samples_leaf=5, random_state=42)
    o25_clf = CalibratedClassifierCV(estimator=base_o25, method='isotonic', cv=5)
    o25_clf.fit(X_train, y_o25_train)
    
    console.print("[cyan]Training Confidence Meta-Model (Calibrated Random Forest - Isotonic)...[/cyan]")
    base_conf = RandomForestClassifier(n_estimators=100, max_depth=10, min_samples_leaf=5, random_state=42)
    conf_clf = CalibratedClassifierCV(estimator=base_conf, method='isotonic', cv=5)
    conf_clf.fit(X_train, y_conf_train)

    console.print("[cyan]Training Asian Handicap Classifiers (Calibrated Random Forest - Isotonic)...[/cyan]")
    base_ah = RandomForestClassifier(n_estimators=100, max_depth=10, min_samples_leaf=5, random_state=42)
    ah_home_clf = CalibratedClassifierCV(estimator=base_ah, method='isotonic', cv=5)
    ah_home_clf.fit(X_train, y_ah_home_train)
    ah_away_clf = CalibratedClassifierCV(estimator=base_ah, method='isotonic', cv=5)
    ah_away_clf.fit(X_train, y_ah_away_train)

    # Save models
    clf_path = os.path.join(MODEL_DIR, 'outcome_model.joblib')
    reg_path = os.path.join(MODEL_DIR, 'goals_model.joblib')
    btts_path = os.path.join(MODEL_DIR, 'btts_model.joblib')
    o25_path = os.path.join(MODEL_DIR, 'over25_model.joblib')
    conf_path = os.path.join(MODEL_DIR, 'confidence_model.joblib')
    ah_home_path = os.path.join(MODEL_DIR, 'ah_home_model.joblib')
    ah_away_path = os.path.join(MODEL_DIR, 'ah_away_model.joblib')
    
    joblib.dump(clf, clf_path)
    joblib.dump(reg, reg_path)
    joblib.dump(btts_clf, btts_path)
    joblib.dump(o25_clf, o25_path)
    joblib.dump(conf_clf, conf_path)
    joblib.dump(ah_home_clf, ah_home_path)
    joblib.dump(ah_away_clf, ah_away_path)
    console.print(f"Models saved to [bold]{MODEL_DIR}[/bold]")

if __name__ == "__main__":
    train_models()
