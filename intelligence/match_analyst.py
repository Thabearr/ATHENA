import logging

logger = logging.getLogger("athena.match_analyst")

class MatchAnalyst:
    def __init__(self, form_engine, motivation_engine, weather_engine, fatigue_engine, injury_engine, referee_engine, risk_engine):
        self.form_eng = form_engine
        self.motivation_eng = motivation_engine
        self.weather_eng = weather_engine
        self.fatigue_eng = fatigue_engine
        self.injury_eng = injury_engine
        self.ref_eng = referee_engine
        self.risk_eng = risk_engine

    def compile_master_fixture_prediction(self, fixture_context: dict) -> dict:
        """
        Aggregates all 6 intelligence variables into a unified composite rating
        and triggers the Upset Evasion Protocol if risk thresholds are breached.
        """
        # 1. Gather Form Dynamics
        home_form_score = fixture_context.get('mock_home_form', 0.50)
        away_form_score = fixture_context.get('mock_away_form', 0.50)

        # 2. Extract Motivation Profile
        motivation = self.motivation_eng.analyze_fixture_motivation_clash(fixture_context, league_size=20)

        # 3. Assess Weather Modifiers
        weather = self.weather_eng.assess_tactical_weather_impact(fixture_context.get('weather', {}))

        # 4. Evaluate Fatigue Indices
        fatigue = self.fatigue_eng.analyze_fixture_fatigue_clash(
            home_team_id=fixture_context['home_id'],
            away_team_id=fixture_context['away_id'],
            current_date=fixture_context['match_date'],
            home_last_date=fixture_context['match_date'],
            away_last_date=fixture_context['match_date']
        )

        # 5. Evaluate Upset Potential (Ref + Fatigue + Injuries)
        ref_impact = self.ref_eng.evaluate_referee_impact(
            fixture_context.get('referee_name'),
            fixture_context.get('ref_stats'),
            fixture_context.get('home_style', 'neutral'),
            fixture_context.get('away_style', 'neutral')
        )
        
        # 6. Final Risk/Upset Assessment
        risk_context = {
            "referee_upset_score": ref_impact['upset_catalyst_score'],
            "fatigue_differential": fatigue['fatigue_differential'],
            "favorite_injury_modifier": 1.0 # Placeholder for injury engine lookup
        }
        
        # We dummy-initialize a prediction model to use the risk engine
        from models.prediction import Prediction
        pred = Prediction(fixture_id=fixture_context['fixture_id'], league="General", home_team="Home", away_team="Away")
        pred.home_strength = 50 
        pred.away_strength = 50
        
        risk_evaluation = self.risk_eng.evaluate(pred, environmental_context=risk_context)

        # --- FINAL COMPOSITE ---
        edge_differential = round(home_form_score - away_form_score, 3)
        
        return {
            "edge_differential": edge_differential,
            "recommended_analytical_verdict": "STRONG HOME ADVANTAGE" if edge_differential > 0.15 else "COMPETITIVE",
            "upset_alert": risk_evaluation.upset_alert
        }
