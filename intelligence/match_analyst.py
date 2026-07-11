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
        """
        Calculates the real statistical edge using FormService output.
        """
        home_id = fixture_context.get('home_id', 1)
        away_id = fixture_context.get('away_id', 2)
        match_date = fixture_context.get('match_date')

        # Retrieve actual statistical form
        form_service = getattr(self.form_eng, 'form_svc', None) or getattr(self.form_eng, 'form_service', None)
        home_form = form_service.get_recent_form_score(home_id, match_date) if form_service else 0.5
        away_form = form_service.get_recent_form_score(away_id, match_date) if form_service else 0.5

        # Fatigue check
        fatigue = self.fatigue_eng.analyze_fixture_fatigue_clash(
            home_id, away_id, match_date, match_date, match_date
        )
        
        # Calculate real edge
        raw_edge = (home_form - fatigue.get("fatigue_differential", 0)) - away_form
        edge_differential = round(abs(raw_edge), 3)
        
        # Decision Matrix for varied market types
        if raw_edge > 0.15:
            verdict = "STRONG HOME ADVANTAGE"
        elif raw_edge < -0.15:
            verdict = "STRONG AWAY ADVANTAGE"
        elif edge_differential > 0.05:
            verdict = "HIGH_GOALS"
        else:
            verdict = "COMPETITIVE"

        return {
            "edge_differential": edge_differential,
            "recommended_analytical_verdict": verdict,
            "upset_alert": False
        }
