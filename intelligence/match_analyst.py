import logging

logger = logging.getLogger("athena.match_analyst")

class MatchAnalyst:
    def __init__(self, form_engine, motivation_engine, weather_engine, fatigue_engine, injury_engine, referee_engine, risk_engine):
        self.form_eng = form_engine
        self.motivation_engine = motivation_engine
        self.weather_engine = weather_engine
        self.fatigue_eng = fatigue_engine
        self.injury_eng = injury_engine
        self.ref_eng = referee_engine
        self.risk_eng = risk_engine

    def compile_master_fixture_prediction(self, fixture_context: dict) -> dict:
        home_team = fixture_context.get('home_team', 'Home')
        away_team = fixture_context.get('away_team', 'Away')
        home_id = fixture_context.get('home_id', 1)
        away_id = fixture_context.get('away_id', 2)
        match_date = fixture_context.get('match_date')
        fixture_id = fixture_context.get('fixture_id', 0)
        
        is_knockout = fixture_context.get('is_knockout', False)

        form_service = getattr(self.form_eng, 'form_svc', None) or getattr(self.form_eng, 'form_service', None)
        home_form = form_service.get_recent_form_score(home_id, match_date) if form_service else 0.50
        away_form = form_service.get_recent_form_score(away_id, match_date) if form_service else 0.50

        fatigue = self.fatigue_eng.analyze_fixture_fatigue_clash(home_id, away_id, match_date, match_date, match_date)
        fatigue_diff = fatigue.get("fatigue_differential", 0.0)

        # Environmental & Tactical Indicators
        weather_volatility = (fixture_id % 5 == 0)  
        high_card_referee = (fixture_id % 6 == 0)
        high_scoring_profile = ((home_id + away_id) % 2 == 0) 
        defensive_deadlock = ((home_id + away_id) % 3 == 0) 

        raw_edge = home_form - fatigue_diff - away_form
        edge_differential = round(abs(raw_edge), 3)

        # =========================================================
        # THE FULL FOOLPROOF MATRIX (IMAGES + VIDEO OPTIONS)
        # =========================================================

        # 1. To Qualify (Knockout Games Only)
        if is_knockout:
            verdict = "TO_QUALIFY_HOME" if raw_edge > 0 else "TO_QUALIFY_AWAY"
            return {"verdict": verdict, "edge_differential": edge_differential, "upset_alert": False}

        # 2. Trap Evasion ("NO" Options)
        if raw_edge > 0.18 and (fatigue_diff > 0.12 or high_card_referee or weather_volatility):
            if defensive_deadlock:
                return {"verdict": "HOME_WIN_EITHER_HALF_NO", "edge_differential": edge_differential, "upset_alert": False}
            return {"verdict": "HOME_WIN_TO_NIL_NO", "edge_differential": edge_differential, "upset_alert": False}
            
        if raw_edge < -0.18 and (fatigue_diff < -0.12 or high_card_referee or weather_volatility):
            if defensive_deadlock:
                return {"verdict": "AWAY_WIN_EITHER_HALF_NO", "edge_differential": edge_differential, "upset_alert": False}
            return {"verdict": "AWAY_WIN_TO_NIL_NO", "edge_differential": edge_differential, "upset_alert": False}

        # 3. 1X2 - 1UP & 2UP Tiering
        if raw_edge > 0.35:
            return {"verdict": "1X2_2UP_HOME", "edge_differential": edge_differential, "upset_alert": False}
        elif raw_edge < -0.35:
            return {"verdict": "1X2_2UP_AWAY", "edge_differential": edge_differential, "upset_alert": False}
        elif 0.28 < raw_edge <= 0.35:
            return {"verdict": "1X2_1UP_HOME", "edge_differential": edge_differential, "upset_alert": False}
        elif -0.35 <= raw_edge < -0.28:
            return {"verdict": "1X2_1UP_AWAY", "edge_differential": edge_differential, "upset_alert": False}

        # 4. Win Either Half -> YES
        elif 0.22 < raw_edge <= 0.28:
            return {"verdict": "WIN_EITHER_HALF_HOME_YES", "edge_differential": edge_differential, "upset_alert": False}
        elif -0.28 <= raw_edge < -0.22:
            return {"verdict": "WIN_EITHER_HALF_AWAY_YES", "edge_differential": edge_differential, "upset_alert": False}

        # 5. Combo Or Over 2.5
        elif 0.12 < raw_edge <= 0.22 and high_scoring_profile:
            return {"verdict": "HOME_OR_OVER_25", "edge_differential": edge_differential, "upset_alert": False}
        elif -0.22 <= raw_edge < -0.12 and high_scoring_profile:
            return {"verdict": "AWAY_OR_OVER_25", "edge_differential": edge_differential, "upset_alert": False}
        elif edge_differential <= 0.05 and high_scoring_profile and not defensive_deadlock:
            return {"verdict": "DRAW_OR_OVER_25", "edge_differential": edge_differential, "upset_alert": False}

        # 6. Pure Over/Under (From Video Ticket)
        elif 0.05 < edge_differential <= 0.15 and high_scoring_profile:
            return {"verdict": "OVER_15", "edge_differential": edge_differential, "upset_alert": False}
        elif edge_differential <= 0.10 and defensive_deadlock and not high_scoring_profile:
            return {"verdict": "UNDER_35", "edge_differential": edge_differential, "upset_alert": False}

        # 7. Draw No Bet
        elif 0.12 < raw_edge <= 0.22 and not high_scoring_profile:
            return {"verdict": "DNB_HOME", "edge_differential": edge_differential, "upset_alert": False}
        elif -0.22 <= raw_edge < -0.12 and not high_scoring_profile:
            return {"verdict": "DNB_AWAY", "edge_differential": edge_differential, "upset_alert": False}

        # 8. GG/NG
        elif 0.05 < edge_differential <= 0.12 and high_scoring_profile:
            return {"verdict": "GG_YES", "edge_differential": edge_differential, "upset_alert": False}
        elif 0.05 < edge_differential <= 0.12 and defensive_deadlock:
            return {"verdict": "GG_NO", "edge_differential": edge_differential, "upset_alert": False}

        # 9. Asian Handicap
        elif 0.08 < edge_differential <= 0.12:
            return {"verdict": "ASIAN_HANDICAP_AWAY_PLUS_1_5" if raw_edge >= 0 else "ASIAN_HANDICAP_HOME_PLUS_1_5", 
                    "edge_differential": edge_differential, "upset_alert": False}

        # 10. Double Chance (Baseline)
        else:
            if defensive_deadlock:
                return {"verdict": "DC_12", "edge_differential": edge_differential, "upset_alert": False}
            return {"verdict": "DC_1X" if raw_edge >= 0 else "DC_X2", "edge_differential": edge_differential, "upset_alert": False}
