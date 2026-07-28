import logging
import math
import hashlib
import sqlite3
import os
import json

from domain.markets import DecisionStatus
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


MARKET_PROBABILITY_METHODS = {
    "DC_1X": "derived_from_full_time_score_matrix_probabilities",
    "DC_X2": "derived_from_full_time_score_matrix_probabilities",
    "DC_12": "derived_from_full_time_score_matrix_probabilities",
    "OVER_15": "poisson_total_goals_cdf_with_optional_ml_xg_blend",
    "OVER_25": "score_matrix_with_optional_ml_classifier_blend",
    "UNDER_25": "complement_of_over_2_5_probability",
    "UNDER_35": "truncated_poisson_score_matrix",
    "GG_YES": "score_matrix_with_optional_ml_classifier_blend",
    "GG_NO": "complement_of_btts_yes_probability",
    "DNB_HOME": "full_time_home_win_probability_proxy",
    "DNB_AWAY": "full_time_away_win_probability_proxy",
    "HOME_OR_OVER_25": "score_matrix_union_probability",
    "AWAY_OR_OVER_25": "score_matrix_union_probability",
    "DRAW_OR_OVER_25": "score_matrix_union_probability",
    "HOME_WIN_TO_NIL_NO": "complement_of_score_matrix_win_to_nil",
    "AWAY_WIN_TO_NIL_NO": "complement_of_score_matrix_win_to_nil",
    "AH_HOME_PLUS_15": "score_matrix_with_optional_ml_classifier_blend",
    "AH_AWAY_PLUS_15": "score_matrix_with_optional_ml_classifier_blend",
    "AH_HOME_PLUS_25": "score_matrix_handicap_probability",
    "AH_AWAY_PLUS_25": "score_matrix_handicap_probability",
}


def build_viable_market_candidates(
    market_probabilities: dict,
    archetype_boosts: dict,
    min_probability: float = 0.55,
) -> list:
    """Build candidates without inventing edge or a fallback selection.

    The returned delta is explicitly a comparison with a global historical
    baseline. It is not bookmaker-implied edge and must not be represented as
    such. Bookmaker value calculation remains a separate stabilization task.
    """
    candidates = []
    for verdict, probability in market_probabilities.items():
        if probability < min_probability:
            continue
        probability_method = MARKET_PROBABILITY_METHODS.get(verdict)
        if not probability_method:
            continue

        baseline = MARKET_BASELINES.get(verdict, 0.50)
        baseline_delta = round(
            probability - baseline + archetype_boosts.get(verdict, 0.0),
            4,
        )
        if baseline_delta <= 0:
            continue

        candidates.append({
            "verdict": verdict,
            "prob": round(probability, 4),
            # Compatibility field: this is not genuine bookmaker edge.
            "edge": baseline_delta,
            "edge_above_baseline": baseline_delta,
            "edge_method": "global_baseline_delta",
            "is_bookmaker_edge": False,
            "probability_method": probability_method,
            "category": MARKET_CATEGORIES.get(verdict, "OTHER"),
        })

    candidates.sort(
        key=lambda candidate: candidate["edge_above_baseline"],
        reverse=True,
    )
    return candidates


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

        prob_1x = prob_home_win + prob_draw
        prob_x2 = prob_away_win + prob_draw
        prob_12 = prob_home_win + prob_away_win

        # --- BUILD CANDIDATES WITH A GLOBAL-BASELINE DELTA ---
        # Each market is only included if its fixture probability exceeds
        # the global baseline, AND the probability meets a minimum threshold.
        # This delta is not bookmaker-implied edge or evidence of betting value.
        
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
            # Win-either-half is intentionally disabled until ATHENA has a
            # valid half-by-half score model. Full-time win probability * 1.35
            # is not a defensible probability calculation.
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


        # Early-payout markets are intentionally not modeled here. Reusing the
        # full-time win probability ignores the bookmaker's lead-path and
        # settlement rules, so those selections remain unavailable for now.

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
            
        # 2. Low Event / Tactical Stalemate
        if total_xg < 2.2:
            archetype_boosts["UNDER_25"] = 0.25
            archetype_boosts["UNDER_35"] = 0.15
            archetype_boosts["DNB_HOME"] = 0.18
            archetype_boosts["DNB_AWAY"] = 0.18
            
        # 3. Smart Upset Pivoting ("The Milan Scenario")
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

        viable_markets = build_viable_market_candidates(
            all_market_probs,
            archetype_boosts,
            min_probability=MIN_PROB,
        )

        # Candidates are sorted by baseline delta, which is not bookmaker value.

        if not viable_markets:
            return {
                "decision_status": DecisionStatus.NO_BET.value,
                "recommended_analytical_verdict": None,
                "edge_differential": None,
                "edge_is_bookmaker_value": False,
                "upset_alert": upset_alert,
                "risk_score": risk_score,
                "stale_data": stale_data,
                "viable_markets": [],
                "reasoning_verdicts": [],
                "no_bet_reasons": [
                    "No market cleared the minimum probability and "
                    "positive baseline-delta thresholds."
                ],
            }
            
        # Model F: Confidence Meta-Model Hard Filter
        # If the ML Meta-Model flags this as an Upset Risk (Reliability < 50%),
        # we set upset_alert to True. AccaFilter may reject the fixture in strict
        # mode; no market is created when the validated candidate list is empty.

        # --- REASONING ENGINE INTEGRATION (Shin De-vig, Wilson CI, Single Market Winner) ---
        from intelligence.fixture_reasoner import FixtureOption, FixtureReasoner
        
        reasoner_options = []
        # Map markets to odds & effective sample sizes
        # 1X2
        h_odds = round(1.0 / max(0.01, prob_home_win), 2)
        d_odds = round(1.0 / max(0.01, prob_draw), 2)
        a_odds = round(1.0 / max(0.01, prob_away_win), 2)
        n_eff = 800 if not stale_data else 300
        
        reasoner_options.extend([
            FixtureOption("1X2", "Home Win", model_prob=prob_home_win, odds=h_odds, n_effective=n_eff),
            FixtureOption("1X2", "Draw", model_prob=prob_draw, odds=d_odds, n_effective=n_eff),
            FixtureOption("1X2", "Away Win", model_prob=prob_away_win, odds=a_odds, n_effective=n_eff),
        ])
        
        # Over/Under 2.5
        o25_odds = round(1.0 / max(0.01, prob_over_25), 2)
        u25_odds = round(1.0 / max(0.01, prob_under_25), 2)
        reasoner_options.extend([
            FixtureOption("Over/Under 2.5", "Over 2.5", model_prob=prob_over_25, odds=o25_odds, n_effective=n_eff, correlation_tag="goals_high"),
            FixtureOption("Over/Under 2.5", "Under 2.5", model_prob=prob_under_25, odds=u25_odds, n_effective=n_eff),
        ])
        
        # BTTS
        gg_odds = round(1.0 / max(0.01, prob_gg), 2)
        ng_odds = round(1.0 / max(0.01, 1.0 - prob_gg), 2)
        reasoner_options.extend([
            FixtureOption("BTTS", "BTTS Yes", model_prob=prob_gg, odds=gg_odds, n_effective=n_eff, correlation_tag="goals_high"),
            FixtureOption("BTTS", "BTTS No", model_prob=1.0 - prob_gg, odds=ng_odds, n_effective=n_eff),
        ])

        reasoner = FixtureReasoner(min_edge_pp=2.0, kelly_fraction_used=1/8, devig_method="shin")
        reasoner_results = reasoner.analyze(reasoner_options)

        best_market = viable_markets[0]

        return {
            "decision_status": DecisionStatus.BET.value,
            "recommended_analytical_verdict": best_market["verdict"],
            "edge_differential": best_market["edge"],
            "edge_is_bookmaker_value": False,
            "upset_alert": upset_alert,
            "risk_score": risk_score,
            "stale_data": stale_data,
            "viable_markets": viable_markets,
            "reasoning_verdicts": [
                {
                    "label": v.option.label,
                    "market": v.option.market,
                    "status": v.status,
                    "edge_pp": round(v.edge_pp, 2),
                    "fair_prob": round(v.fair_prob, 4),
                    "kelly_stake_pct": round(v.kelly_stake_pct, 2),
                    "reason": v.reason
                }
                for v in reasoner_results
            ]
        }
