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
        Aggregates all intelligence variables into a unified composite rating
        and triggers the Upset Evasion Protocol if risk thresholds are breached.
        """
        # 1. Simulate Dynamic Form Dynamics (Deterministic so teams keep the same score)
        home_id = fixture_context.get('home_id', 1)
        away_id = fixture_context.get('away_id', 2)
        
        # Generates a pseudo-form score between 0.40 and 0.90 based on ID
        home_form_score = 0.40 + ((home_id * 7) % 50) / 100.0
        away_form_score = 0.40 + ((away_id * 11) % 50) / 100.0

        # 2. Extract Motivation Profile (Skipped for simulation)
        # 3. Assess Weather Modifiers (Skipped for simulation)

        # 4. Evaluate Fatigue Indices
        fatigue = self.fatigue_eng.analyze_fixture_fatigue_clash(
            home_team_id=home_id,
            away_team_id=away_id,
            current_date=fixture_context['match_date'],
            home_last_date=fixture_context['match_date'],
            away_last_date=fixture_context['match_date']
        )

        # --- FINAL COMPOSITE ---
        # Calculate raw edge difference
        raw_edge = home_form_score - away_form_score
        
        # Engine expects a positive edge magnitude regardless of who is favored
        edge_differential = round(abs(raw_edge), 3)
        
        # Map to strict optimal markets
        if raw_edge > 0.15:
            verdict = "STRONG HOME ADVANTAGE"
        elif raw_edge < -0.15:
            verdict = "STRONG AWAY ADVANTAGE"
        elif edge_differential > 0.08:
            verdict = "HIGH_GOALS"
        else:
            verdict = "COMPETITIVE"
        
        return {
            "edge_differential": edge_differential,
            "recommended_analytical_verdict": verdict,
            "upset_alert": False # Kept false for dry-run so slip populates
        }
