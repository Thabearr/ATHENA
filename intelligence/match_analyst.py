import logging
import math
import hashlib
import sqlite3
import os

logger = logging.getLogger("athena.match_analyst")


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

    def _calculate_poisson_probability(self, actual_goals: int, expected_goals: float) -> float:
        if expected_goals <= 0:
            return 1.0 if actual_goals == 0 else 0.0
        return math.exp(-expected_goals) * (expected_goals ** actual_goals) / math.factorial(actual_goals)

    def _get_team_strength_seed(self, team_name: str) -> float:
        """
        Generate a deterministic but diverse team strength factor (0.8 to 1.2)
        based on team name hash when we have no historical data.
        """
        hash_val = int(hashlib.md5(team_name.encode()).hexdigest(), 16)
        return 0.8 + ((hash_val % 41) / 100.0)

    def _assess_upset_risk(self, prob_home_win: float, prob_away_win: float,
                            fatigue_diff: float, referee_signal: dict,
                            avg_live_ratio: float) -> dict:
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

        if avg_live_ratio < 0.20:
            risk += 30
        elif avg_live_ratio < 0.60:
            risk += 15

        risk = min(risk, 100)
        upset_alert = risk >= 55

        return {
            "risk_score": round(risk, 1),
            "upset_alert": upset_alert,
            "stale_data": avg_live_ratio < 0.60,
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
        home_elo = 1500
        away_elo = 1500
        db_path = "database/athena.db"
        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT elo_rating FROM teams WHERE name = ?", (home_team,))
                h_row = cursor.fetchone()
                if h_row: home_elo = h_row[0]
                
                cursor.execute("SELECT elo_rating FROM teams WHERE name = ?", (away_team,))
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
        prob_over_15 = 0.0
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
                if total_goals > 1:
                    prob_over_15 += p_score
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

        prob_home_win_to_nil_no = 1.0 - prob_home_win_to_nil
        prob_away_win_to_nil_no = 1.0 - prob_away_win_to_nil

        risk_assessment = self._assess_upset_risk(prob_home_win, prob_away_win, fatigue_diff, referee_signal, avg_live_ratio)
        risk_score = risk_assessment["risk_score"]
        upset_alert = risk_assessment["upset_alert"]
        stale_data = risk_assessment["stale_data"]

        def result(verdict, edge):
            return {
                "recommended_analytical_verdict": verdict,
                "edge_differential": edge,
                "upset_alert": upset_alert,
                "risk_score": risk_score,
                "stale_data": stale_data,
            }

        if is_knockout:
            verdict = "TO_QUALIFY_HOME" if prob_home_win >= prob_away_win else "TO_QUALIFY_AWAY"
            edge = abs(prob_home_win - prob_away_win)
            return result(verdict, max(edge, 0.06))

        # DIVERSIFY verdicts: even under upset_alert, offer varied markets
        if upset_alert:
            # Use team seed hash to deterministically pick a market variety
            team_hash = (int(hashlib.md5(home_team.encode()).hexdigest(), 16) + 
                        int(hashlib.md5(away_team.encode()).hexdigest(), 16)) % 5
            
            prob_1x = prob_home_win + prob_draw
            prob_x2 = prob_away_win + prob_draw
            
            # Rotate through different markets based on team hash
            if team_hash == 0:
                return result("DC_1X", prob_1x) if prob_1x >= prob_x2 else result("DC_X2", prob_x2)
            elif team_hash == 1:
                return result("DNB_HOME", prob_home_win) if prob_home_win > prob_away_win else result("DNB_AWAY", prob_away_win)
            elif team_hash == 2:
                return result("GG_YES", prob_gg) if prob_gg > 0.55 else result("GG_NO", 1.0 - prob_gg)
            elif team_hash == 3:
                return result("OVER_15", prob_over_15) if prob_over_15 > 0.70 else result("UNDER_35", prob_under_35)
            else:  # team_hash == 4
                if lambda_val > mu_val:
                    return result("HOME_OR_OVER_25", max(prob_home_win, prob_over_25))
                else:
                    return result("AWAY_OR_OVER_25", max(prob_away_win, prob_over_25))

        if prob_home_win_to_nil_no > 0.65 and prob_home_win > 0.55:
            return result("HOME_WIN_TO_NIL_NO", prob_home_win_to_nil_no)
        if prob_away_win_to_nil_no > 0.65 and prob_away_win > 0.55:
            return result("AWAY_WIN_TO_NIL_NO", prob_away_win_to_nil_no)

        if prob_home_win > 0.72:
            return result("1X2_2UP_HOME", prob_home_win)
        if prob_away_win > 0.72:
            return result("1X2_2UP_AWAY", prob_away_win)
        if prob_home_win > 0.62:
            return result("1X2_1UP_HOME", prob_home_win)
        if prob_away_win > 0.62:
            return result("1X2_1UP_AWAY", prob_away_win)

        if lambda_val > 1.85:
            return result("WIN_EITHER_HALF_HOME_YES", 0.68)
        if mu_val > 1.85:
            return result("WIN_EITHER_HALF_AWAY_YES", 0.68)

        prob_home_or_over_25 = max(prob_home_win, prob_over_25)
        prob_away_or_over_25 = max(prob_away_win, prob_over_25)

        if prob_home_or_over_25 > 0.75 and lambda_val > mu_val:
            return result("HOME_OR_OVER_25", prob_home_or_over_25)
        if prob_away_or_over_25 > 0.75 and mu_val > lambda_val:
            return result("AWAY_OR_OVER_25", prob_away_or_over_25)

        if prob_over_15 > 0.82:
            return result("OVER_15", prob_over_15)
        if prob_under_35 > 0.78:
            return result("UNDER_35", prob_under_35)

        if prob_home_win > 0.48:
            return result("DNB_HOME", prob_home_win)
        if prob_away_win > 0.48:
            return result("DNB_AWAY", prob_away_win)

        if prob_gg > 0.62:
            return result("GG_YES", prob_gg)
        if prob_gg < 0.38:
            return result("GG_NO", 1.0 - prob_gg)

        prob_home_plus_1_5 = prob_home_win + prob_draw + sum(
            score_matrix.get((h, a), 0.0) for h in range(6) for a in range(6) if a - h == 1
        )
        prob_away_plus_1_5 = prob_away_win + prob_draw + sum(
            score_matrix.get((h, a), 0.0) for h in range(6) for a in range(6) if h - a == 1
        )

        if prob_home_plus_1_5 > 0.80 and lambda_val < mu_val:
            return result("ASIAN_HANDICAP_HOME_PLUS_1_5", prob_home_plus_1_5)
        if prob_away_plus_1_5 > 0.80 and mu_val < lambda_val:
            return result("ASIAN_HANDICAP_AWAY_PLUS_1_5", prob_away_plus_1_5)

        prob_1x = prob_home_win + prob_draw
        prob_x2 = prob_away_win + prob_draw
        return result("DC_1X", prob_1x) if prob_1x >= prob_x2 else result("DC_X2", prob_x2)
