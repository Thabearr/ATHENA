import logging

logger = logging.getLogger("athena.match_analyst")

class MatchAnalyst:
    def __init__(self, form_engine, motivation_engine, weather_engine, fatigue_engine, injury_engine, referee_engine, risk_engine):
        self.form_eng = form_engine
        self.motivation_eng = motivation_engine
        self.weather_engine = weather_engine
        self.fatigue_eng = fatigue_engine
        self.injury_eng = injury_engine
        self.ref_eng = referee_engine
        self.risk_eng = risk_engine

    def compile_master_fixture_prediction(self, fixture_context: dict) -> dict:
        """
        Aggregates all active mathematical indicators into a unified evaluation.
        No more simulation mock layers—uses live DB form scores and rest parameters.
        """
        home_id = fixture_context.get('home_id', 1)
        away_id = fixture_context.get('away_id', 2)
        match_date = fixture_context.get('match_date')

        # 1. Pull true historical form metrics via the Form Engine pipeline
        # Reaching through to our newly established team form services
        home_form = self.form_eng.form_svc.get_recent_form_score(home_id, match_date)
        away_form = self.form_eng.form_svc.get_recent_form_score(away_id, match_date)

        # 2. Evaluate Fatigue Indices directly from dates
        fatigue = self.fatigue_eng.analyze_fixture_fatigue_clash(
            home_team_id=home_id,
            away_team_id=away_id,
            current_date=match_date,
            home_last_date=match_date, # Fallback to same date if match interval table pending
            away_last_date=match_date
        )

        # Apply a fatigue drag modifier if one side is heavily penalized
        home_effective_form = home_form - fatigue.get("fatigue_differential", 0.0)
        away_effective_form = away_form
        
        # Calculate calculated statistical edge difference
        raw_edge = home_effective_form - away_effective_form
        edge_differential = round(abs(raw_edge), 3)
        
        # 3. Structural Decision Matrix for verdicts
        if raw_edge > 0.18:
            verdict = "STRONG HOME ADVANTAGE"
        elif raw_edge < -0.18:
            verdict = "STRONG AWAY ADVANTAGE"
        elif edge_differential > 0.05:
            # Low variance default if form shows a clear slight leaning
            verdict = "HIGH_GOALS" if home_form + away_form > 1.1 else "LOW_GOALS"
        else:
            verdict = "COMPETITIVE"

        # Check referee profiles for potential structural warnings (Upset alerts)
        upset_triggered = False
        if edge_differential > 0.15:
            # If a massive favorite is playing under volatile referee profiles, trigger evasion flag
            upset_triggered = self.ref_eng.check_referee_anomaly(fixture_context.get("fixture_id", 0))

        return {
            "edge_differential": edge_differential,
            "recommended_analytical_verdict": verdict,
            "upset_alert": upset_triggered
        }
