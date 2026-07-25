import logging
import math
import hashlib
import sqlite3
import os
import json

from intelligence.ml_engine import MLEngine

logger = logging.getLogger("athena.match_analyst")


# Global baseline probabilities for each market type.
# These represent the "average" probability across all football matches.
# Edge = fixture_prob - baseline gives VALUE ABOVE MARKET AVERAGE.
MARKET_BASELINES = {

    "DC_1X": 0.72,
    "DC_X2": 0.62,
    "DC_12": 0.74,
    "OVER_05": 0.92,
    "OVER_15": 0.78,
    "OVER_25": 0.52,
    "UNDER_25": 0.48,
    "UNDER_35": 0.72,
    "UNDER_45": 0.86,
    "UNDER_55": 0.95,
    "AH_HOME_PLUS_15": 0.82,
    "AH_AWAY_PLUS_15": 0.82,
    "AH_HOME_PLUS_25": 0.92,
    "AH_AWAY_PLUS_25": 0.92,
    "HOME_OR_OVER_25": 0.68,
    "AWAY_OR_OVER_25": 0.58,
    "DRAW_OR_OVER_25": 0.65,
    "GG_YES": 0.48,
    "GG_NO": 0.52,
    "DNB_HOME": 0.44,
    "DNB_AWAY": 0.36,
    "WIN_EITHER_HALF_HOME_YES": 0.52,
    "WIN_EITHER_HALF_AWAY_YES": 0.42,
    "HOME_WIN_TO_NIL_YES": 0.22,
    "HOME_WIN_TO_NIL_NO": 0.78,
    "AWAY_WIN_TO_NIL_YES": 0.16,
    "AWAY_WIN_TO_NIL_NO": 0.84,
    "1X2_2UP_HOME": 0.44,
    "1X2_2UP_AWAY": 0.36,
    "1X2_1UP_HOME": 0.44,
    "1X2_1UP_AWAY": 0.36,
}

# Load dynamic weights from evolution engine if available
_WEIGHTS_PATH = os.path.join("config", "model_weights.json")
try:
    if os.path.exists(_WEIGHTS_PATH):
        with open(_WEIGHTS_PATH, "r") as f:
            _dynamic_weights = json.load(f)
            if "MARKET_BASELINES" in _dynamic_weights:
                MARKET_BASELINES.update(_dynamic_weights["MARKET_BASELINES"])
except Exception as e:
    logger.warning(f"Failed to load dynamic weights: {e}")

# Market category grouping — used by AccaFilter to enforce diversity caps
MARKET_CATEGORIES = {
    "DC_1X": "DOUBLE_CHANCE",
    "DC_X2": "DOUBLE_CHANCE",
    "DC_12": "DOUBLE_CHANCE",
    "OVER_05": "OVER_UNDER",
    "OVER_15": "OVER_UNDER",
    "OVER_25": "OVER_UNDER",
    "UNDER_25": "OVER_UNDER",
    "UNDER_35": "OVER_UNDER",
    "UNDER_45": "OVER_UNDER",
    "UNDER_55": "OVER_UNDER",
    "AH_HOME_PLUS_15": "ASIAN_HANDICAP",
    "AH_AWAY_PLUS_15": "ASIAN_HANDICAP",
    "AH_HOME_PLUS_25": "ASIAN_HANDICAP",
    "AH_AWAY_PLUS_25": "ASIAN_HANDICAP",
    "HOME_OR_OVER_25": "COMBO",
    "AWAY_OR_OVER_25": "COMBO",
    "DRAW_OR_OVER_25": "COMBO",
    "GG_YES": "BTTS",
    "GG_NO": "BTTS",
    "DNB_HOME": "DRAW_NO_BET",
    "DNB_AWAY": "DRAW_NO_BET",
    "WIN_EITHER_HALF_HOME_YES": "WIN_EITHER_HALF",
    "WIN_EITHER_HALF_AWAY_YES": "WIN_EITHER_HALF",
    "HOME_WIN_TO_NIL_YES": "WIN_TO_NIL",
    "HOME_WIN_TO_NIL_NO": "WIN_TO_NIL",
    "AWAY_WIN_TO_NIL_YES": "WIN_TO_NIL",
    "AWAY_WIN_TO_NIL_NO": "WIN_TO_NIL",
    "1X2_2UP_HOME": "EARLY_PAYOUT",
    "1X2_2UP_AWAY": "EARLY_PAYOUT",
    "1X2_1UP_HOME": "EARLY_PAYOUT",
    "1X2_1UP_AWAY": "EARLY_PAYOUT",

}


class MatchAnalyst:
    def __init__(self, form_engine, motivation_engine, weather_engine, fatigue_engine,
                 injury_engine, referee_engine, risk_engine):
        self.form_eng = form_engine
        self.motivation_engine = motivation_engine
        self.weather_engine = weather_engine
        self.fatigue_eng = fatigue_engine
        self.injury_eng = injury_engine
        self.ref_eng = referee_engine
        self.risk_eng = risk_engine
        
        self.ml_eng = MLEngine()

    def _calculate_poisson_probability(self, actual_goals: int, expected_goals: float) -> float:
        if expected_goals <= 0:
            return 1.0 if actual_goals == 0 else 0.0
        return math.exp(-expected_goals) * (expected_goals ** actual_goals) / math.factorial(actual_goals)



    def _assess_upset_risk(self, prob_home_win: float, prob_away_win: float,
                            fatigue_diff: float, referee_signal: dict,
                            avg_live_ratio: float, is_backtest: bool = False) -> dict:
        favorite_prob = max(prob_home_win, prob_away_win)

        risk = 0.0
        if favorite_prob < 0.55:
            risk += 35
        elif favorite_prob < 0.65:
            risk += 20
        else:
            risk += 8

        if fatigue_diff >= 0.30:
            risk += 25
        elif fatigue_diff >= 0.10:
            risk += 10

        if referee_signal.get("has_data") and referee_signal.get("high_volatility"):
            risk += 20

        if not is_backtest:
            if avg_live_ratio < 0.20:
                risk += 30
            elif avg_live_ratio < 0.60:
                risk += 15

        risk = min(risk, 100)
        upset_alert = risk >= 55

        return {
            "risk_score": round(risk, 1),
            "upset_alert": upset_alert,
            "stale_data": avg_live_ratio < 0.60 and not is_backtest,
        }

    def compile_master_fixture_prediction(self, fixture_context: dict) -> dict:
        home_team = fixture_context.get('home_team', 'Home')
        away_team = fixture_context.get('away_team', 'Away')
        home_id = fixture_context.get('home_id', 1)
        away_id = fixture_context.get('away_id', 2)
        match_date = fixture_context.get('match_date')
        fixture_id = fixture_context.get('fixture_id', 0)
        is_knockout = fixture_context.get('is_knockout', False)

        form_service = getattr(self.form_eng, 'form_svc', None) or getattr(self.form_eng, 'form_service', None)
        home_raw = form_service.get_recent_form_score(home_id, match_date) if form_service else 0.50
        away_raw = form_service.get_recent_form_score(away_id, match_date) if form_service else 0.50

        home_freshness = form_service.get_data_freshness(home_id, match_date) if form_service else {"live_ratio": 0.0}
        away_freshness = form_service.get_data_freshness(away_id, match_date) if form_service else {"live_ratio": 0.0}
        avg_live_ratio = (home_freshness.get("live_ratio", 0.0) + away_freshness.get("live_ratio", 0.0)) / 2

        home_last_date = form_service.get_last_match_date(home_id, match_date) if form_service else None
        away_last_date = form_service.get_last_match_date(away_id, match_date) if form_service else None

        fatigue = self.fatigue_eng.analyze_fixture_fatigue_clash(
            home_id, away_id, match_date, home_last_date, away_last_date
        )
        fatigue_diff = fatigue.get("fatigue_differential", 0.0)

        referee_signal = self.ref_eng.check_referee_anomaly(fixture_id)

        # Use ELO ratings instead of form data if available
        home_elo = fixture_context.get('home_pre_elo', 1500)
        away_elo = fixture_context.get('away_pre_elo', 1500)
        
        if 'home_pre_elo' not in fixture_context or 'away_pre_elo' not in fixture_context:
            db_path = "database/athena.db"
            if os.path.exists(db_path):
                try:
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT elo_rating FROM teams WHERE team_id = ? OR name = ?", (home_id, home_team))
                    h_row = cursor.fetchone()
                    if h_row: home_elo = h_row[0]
                    
                    cursor.execute("SELECT elo_rating FROM teams WHERE team_id = ? OR name = ?", (away_id, away_team))
                    a_row = cursor.fetchone()
                    if a_row: away_elo = a_row[0]
                    conn.close()
                except Exception as e:
                    logger.error(f"Failed to fetch ELO: {e}")

        if avg_live_ratio < 0.05:
            # Normalize ELO to a roughly 0.2 to 0.8 scale, where 1500 is 0.50
            # A 200 point ELO diff is very large.
            home_raw = 0.50 + ((home_elo - 1500) / 800.0)
            away_raw = 0.50 + ((away_elo - 1500) / 800.0)
            
            # Ensure boundaries
            home_raw = max(0.1, min(0.9, home_raw))
            away_raw = max(0.1, min(0.9, away_raw))

        base_home_lambda = 1.45 + (home_raw - away_raw) - (fatigue_diff * 0.5)
        base_away_mu = 1.25 + (away_raw - home_raw) + (fatigue_diff * 0.5)

        lambda_val = max(0.05, round(base_home_lambda, 3))
        mu_val = max(0.05, round(base_away_mu, 3))

        score_matrix = {}
        prob_home_win = 0.0
        prob_away_win = 0.0
        prob_draw = 0.0
        prob_under_35 = 0.0
        prob_over_25 = 0.0
        prob_gg = 0.0
        prob_home_win_to_nil = 0.0
        prob_away_win_to_nil = 0.0

        for h in range(6):
            for a in range(6):
                p_score = self._calculate_poisson_probability(h, lambda_val) * self._calculate_poisson_probability(a, mu_val)
                score_matrix[(h, a)] = p_score

                if h > a:
                    prob_home_win += p_score
                elif a > h:
                    prob_away_win += p_score
                else:
                    prob_draw += p_score

                total_goals = h + a
                if total_goals < 4:
                    prob_under_35 += p_score
                if total_goals > 2:
                    prob_over_25 += p_score

                if h >= 1 and a >= 1:
                    prob_gg += p_score

                if h > 0 and a == 0:
                    prob_home_win_to_nil += p_score
                if a > 0 and h == 0:
                    prob_away_win_to_nil += p_score

        # --- ML ENGINE INTEGRATION ---
        # Blend Poisson probabilities with ML probabilities if the model is ready
        ml_preds = self.ml_eng.predict(home_id, away_id, home_elo, away_elo, match_date=match_date)
        if ml_preds:
            ml_p = ml_preds["probabilities"]
            # 50/50 blend between heuristic Poisson and Random Forest
            prob_home_win = (prob_home_win + ml_p["HOME_WIN"]) / 2
            prob_away_win = (prob_away_win + ml_p["AWAY_WIN"]) / 2
            prob_draw = (prob_draw + ml_p["DRAW"]) / 2
            
            # Use ML expected goals if available
            ml_xg = ml_preds["expected_total_goals"]
            expected_goals = (lambda_val + mu_val + ml_xg) / 2
            
            # Blend explicit ML market classifiers if they exist
            if ml_preds.get("btts_yes") is not None:
                prob_gg = (prob_gg + ml_preds["btts_yes"]) / 2
            if ml_preds.get("over_25") is not None:
                prob_over_25 = (prob_over_25 + ml_preds["over_25"]) / 2
        else:
            expected_goals = lambda_val + mu_val
            
        # Re-derive Over 1.5 from blended expected goals using Poisson CDF
        prob_over_15 = 1.0 - (self._calculate_poisson_probability(0, expected_goals) + self._calculate_poisson_probability(1, expected_goals))

        is_backtest = fixture_context.get('is_backtest', False)
        stale_data = avg_live_ratio < 0.60 and not is_backtest
        
        # Default heuristic risk
        risk_assessment = self._assess_upset_risk(prob_home_win, prob_away_win, fatigue_diff, referee_signal, avg_live_ratio, is_backtest)
        risk_score = risk_assessment["risk_score"]
        upset_alert = risk_assessment["upset_alert"]
        
        # Override with Confidence Meta-Model if available
        if ml_preds and ml_preds.get("reliability_score") is not None:
            reliability = ml_preds["reliability_score"]
            risk_score = (1.0 - reliability) * 100
            upset_alert = reliability < 0.50 # Adjusted ML confidence threshold to align with 50% base rate

        # --- COMPREHENSIVE MARKET PROBABILITY CALCULATIONS ---
        prob_over_05 = 1.0 - score_matrix.get((0, 0), 0.0)
        prob_under_25 = 1.0 - prob_over_25
        prob_under_45 = sum(score_matrix.get((h, a), 0.0) for h in range(6) for a in range(6) if h + a <= 4)
        prob_under_55 = sum(score_matrix.get((h, a), 0.0) for h in range(6) for a in range(6) if h + a <= 5)

        prob_home_plus_1_5 = prob_home_win + prob_draw + sum(
            score_matrix.get((h, a), 0.0) for h in range(6) for a in range(6) if a - h == 1
        )
        prob_away_plus_1_5 = prob_away_win + prob_draw + sum(
            score_matrix.get((h, a), 0.0) for h in range(6) for a in range(6) if h - a == 1
        )
        
        # Blend explicit ML Handicap classifiers if they exist
        if ml_preds and ml_preds.get("ah_home_plus_15") is not None:
            prob_home_plus_1_5 = (prob_home_plus_1_5 + ml_preds["ah_home_plus_15"]) / 2
        if ml_preds and ml_preds.get("ah_away_plus_15") is not None:
            prob_away_plus_1_5 = (prob_away_plus_1_5 + ml_preds["ah_away_plus_15"]) / 2

        prob_home_plus_2_5 = prob_home_win + prob_draw + sum(
            score_matrix.get((h, a), 0.0) for h in range(6) for a in range(6) if a - h in [1, 2]
        )
        prob_away_plus_2_5 = prob_away_win + prob_draw + sum(
            score_matrix.get((h, a), 0.0) for h in range(6) for a in range(6) if h - a in [1, 2]
        )

        # Combo probabilities (OR logic = P(A) + P(B) - P(A and B))
        prob_draw_or_over_25 = prob_draw + prob_over_25 - sum(
            score_matrix.get((h, a), 0.0) for h in range(6) for a in range(6) if h == a and h + a > 2
        )
        prob_home_or_over_25 = prob_home_win + prob_over_25 - sum(
            score_matrix.get((h, a), 0.0) for h in range(6) for a in range(6) if h > a and h + a > 2
        )
        prob_away_or_over_25 = prob_away_win + prob_over_25 - sum(
            score_matrix.get((h, a), 0.0) for h in range(6) for a in range(6) if a > h and h + a > 2
        )

        prob_win_either_half_home = min(0.95, prob_home_win * 1.35)
        prob_win_either_half_away = min(0.95, prob_away_win * 1.35)

        prob_1x = prob_home_win + prob_draw
        prob_x2 = prob_away_win + prob_draw
        prob_12 = prob_home_win + prob_away_win

        # --- BUILD VIABLE MARKETS WITH TRUE EDGE-ABOVE-BASELINE ---
        # Each market is only included if its fixture probability exceeds
        # the global baseline, AND the probability meets a minimum threshold.
        # Edge = fixture_prob - baseline. Higher edge = more value for THIS fixture.
        
        all_market_probs = {
            "DC_1X": prob_1x,
            "DC_X2": prob_x2,
            "DC_12": prob_12,
            "OVER_15": prob_over_15,
            "OVER_25": prob_over_25,
            "UNDER_25": prob_under_25,
            "UNDER_35": prob_under_35,
            "GG_YES": prob_gg,
            "GG_NO": 1.0 - prob_gg,
            "DNB_HOME": prob_home_win,
            "DNB_AWAY": prob_away_win,
            "WIN_EITHER_HALF_HOME_YES": prob_win_either_half_home,
            "WIN_EITHER_HALF_AWAY_YES": prob_win_either_half_away,
            "HOME_OR_OVER_25": prob_home_or_over_25,
            "AWAY_OR_OVER_25": prob_away_or_over_25,
            "DRAW_OR_OVER_25": prob_draw_or_over_25,
            "HOME_WIN_TO_NIL_NO": 1.0 - prob_home_win_to_nil,
            "AWAY_WIN_TO_NIL_NO": 1.0 - prob_away_win_to_nil,
            "AH_HOME_PLUS_15": prob_home_plus_1_5,
            "AH_AWAY_PLUS_15": prob_away_plus_1_5,
            "AH_HOME_PLUS_25": prob_home_plus_2_5,
            "AH_AWAY_PLUS_25": prob_away_plus_2_5,
        }


        # 1X2 Early Payout
        if prob_home_win >= 0.48:
            all_market_probs["1X2_2UP_HOME"] = prob_home_win
            all_market_probs["1X2_1UP_HOME"] = prob_home_win
        if prob_away_win >= 0.48:
            all_market_probs["1X2_2UP_AWAY"] = prob_away_win
            all_market_probs["1X2_1UP_AWAY"] = prob_away_win

        # --- ARCHETYPE ENGINE ---
        # Classify the match state and boost specific variance-reducing markets
        total_xg = expected_goals
        elo_diff = abs(home_elo - away_elo)
        
        archetype_boosts = {}
        
        # 1. High Event / Chaos
        if total_xg > 2.8 and 50 < elo_diff < 350:
            archetype_boosts["AWAY_OR_OVER_25"] = 0.15
            archetype_boosts["HOME_OR_OVER_25"] = 0.15
            archetype_boosts["GG_YES"] = 0.10
            archetype_boosts["OVER_25"] = 0.15
            
        # 2. Heavy Dominance / Fast Starters
        if lambda_val > 2.2 and home_elo > away_elo + 250:
            archetype_boosts["1X2_2UP_HOME"] = 0.20
            archetype_boosts["1X2_1UP_HOME"] = 0.25
        elif mu_val > 2.2 and away_elo > home_elo + 250:
            archetype_boosts["1X2_2UP_AWAY"] = 0.20
            archetype_boosts["1X2_1UP_AWAY"] = 0.25
            
        # 3. Heavy Dominance / Congested Schedule (Fatigue)
        if elo_diff > 250 and fatigue_diff > 0.05:
            if home_elo > away_elo:
                archetype_boosts["HOME_WIN_EITHER_HALF"] = 0.18
                archetype_boosts["HOME_WIN_TO_NIL_YES"] = 0.15
            else:
                archetype_boosts["AWAY_WIN_EITHER_HALF"] = 0.18
                archetype_boosts["AWAY_WIN_TO_NIL_YES"] = 0.15
                
        # 4. Low Event / Tactical Stalemate
        if total_xg < 2.2:
            archetype_boosts["UNDER_25"] = 0.25
            archetype_boosts["UNDER_35"] = 0.15
            archetype_boosts["DNB_HOME"] = 0.18
            archetype_boosts["DNB_AWAY"] = 0.18
            
        # 5. Asymmetric Threat
        if (home_elo > away_elo + 200) and mu_val < 0.6 and lambda_val > 1.8:
            archetype_boosts["HOME_WIN_TO_NIL_YES"] = 0.20
        elif (away_elo > home_elo + 200) and lambda_val < 0.6 and mu_val > 1.8:
            archetype_boosts["AWAY_WIN_TO_NIL_YES"] = 0.20
            
        # 6. Smart Upset Pivoting ("The Milan Scenario")
        # If ATHENA detects an upset trap against a heavy favorite, brilliantly pivot to the underdog.
        if upset_alert:
            if prob_home_win > prob_away_win:
                # Home is heavily favored but vulnerable! Pivot to Away underdog options.
                archetype_boosts["DC_X2"] = 0.25
                archetype_boosts["DNB_AWAY"] = 0.20
                archetype_boosts["AH_AWAY_PLUS_15"] = 0.25
                archetype_boosts["AH_AWAY_PLUS_25"] = 0.15
            else:
                # Away is heavily favored but vulnerable! Pivot to Home underdog options.
                archetype_boosts["DC_1X"] = 0.25
                archetype_boosts["DNB_HOME"] = 0.20
                archetype_boosts["AH_HOME_PLUS_15"] = 0.25
                archetype_boosts["AH_HOME_PLUS_25"] = 0.15

        # Minimum probability threshold per fixture to be considered viable
        MIN_PROB = 0.55

        viable_markets = []
        for verdict, prob in all_market_probs.items():
            if prob < MIN_PROB:
                continue

            baseline = MARKET_BASELINES.get(verdict, 0.50)
            edge_above_baseline = round(prob - baseline, 4)
            
            # Apply Archetype Boosts
            boost = archetype_boosts.get(verdict, 0.0)
            edge_above_baseline += boost

            category = MARKET_CATEGORIES.get(verdict, "OTHER")

            viable_markets.append({
                "verdict": verdict,
                "prob": round(prob, 4),
                "edge": round(max(edge_above_baseline, 0.05), 4),  # Floor at 0.05 for acca filter
                "edge_above_baseline": edge_above_baseline,
                "category": category,
            })

        # Sort by edge above baseline descending — the market where THIS fixture
        # offers the most value above the average match is ranked #1.
        viable_markets.sort(key=lambda x: x["edge_above_baseline"], reverse=True)

        # Fallback: if nothing passed the probability filter, pick the
        # best Double Chance as a safety net
        if not viable_markets:
            best_dc = "DC_1X" if prob_1x >= prob_x2 else "DC_X2"
            best_dc_prob = max(prob_1x, prob_x2)
            viable_markets.append({
                "verdict": best_dc,
                "prob": round(best_dc_prob, 4),
                "edge": 0.05,
                "edge_above_baseline": 0.01,
                "category": "DOUBLE_CHANCE",
            })
            
        # Model F: Confidence Meta-Model Hard Filter
        # If the ML Meta-Model flags this as an Upset Risk (Reliability < 50%),
        # we set upset_alert to True. The AccaFilter will reject this fixture in strict mode,
        # but we preserve the viable markets so that fallback (no-strict) mode works properly.
        # (Removed the early return that was overriding the verdict to NO_BET)

        best_market = viable_markets[0]

        return {
            "recommended_analytical_verdict": best_market["verdict"],
            "edge_differential": best_market["edge"],
            "upset_alert": upset_alert,
            "risk_score": risk_score,
            "stale_data": stale_data,
            "viable_markets": viable_markets
        }
