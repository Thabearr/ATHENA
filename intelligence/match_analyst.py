import logging

logger = logging.getLogger("athena.match_analyst")

class MatchAnalyst:
    def __init__(self, form_engine, motivation_engine, weather_engine, fatigue_engine, injury_engine):
        self.form_eng = form_engine
        self.motivation_eng = motivation_engine
        self.weather_eng = weather_engine
        self.fatigue_eng = fatigue_engine
        self.injury_eng = injury_engine

    def compile_master_fixture_prediction(self, fixture_context: dict) -> dict:
        """
        Aggregates all 5 intelligence variables into a unified composite rating.
        Weights: Form (40%), Motivation (30%), Fatigue (15%), Injuries (10%), Weather (5%)
        """
        # 1. Gather Form Dynamics (Fallback to baseline if no DB record matches yet)
        # For testing, we simulate a form delta or default to neutral 0.5
        home_form_score = fixture_context.get('mock_home_form', 0.50)
        away_form_score = fixture_context.get('mock_away_form', 0.50)

        # 2. Extract Motivation Profile
        motivation = self.motivation_eng.analyze_fixture_motivation_clash(
            fixture_context, league_size=fixture_context.get('league_size', 20)
        )

        # 3. Assess Weather Modifiers
        weather = self.weather_engine_modifier = self.weather_eng.assess_tactical_weather_impact(
            fixture_context.get('weather', {}),
            home_style=fixture_context.get('home_style', 'neutral'),
            away_style=fixture_context.get('away_style', 'neutral')
        )

        # 4. Evaluate Fatigue Indices
        fatigue = self.fatigue_eng.analyze_fixture_fatigue_clash(
            home_team_id=fixture_context['home_id'],
            away_team_id=fixture_context['away_id'],
            current_date=fixture_context['match_date'],
            home_last_date=fixture_context['home_last_match'],
            away_last_date=fixture_context['away_last_match'],
            away_has_continental_travel=fixture_context.get('away_continental', False)
        )

        # 5. Compute Lineup/Injury Degradation
        home_injury = self.injury_eng.calculate_squad_degradation(fixture_context.get('home_absences', []))
        away_injury = self.injury_eng.calculate_squad_degradation(fixture_context.get('away_absences', []))

        # --- MATHEMATICAL COMPOSITE AGGREGATION ---
        # Baseline starting points modified by Injuries and Weather tactical ceilings
        home_base = home_form_score * home_injury['squad_integrity_modifier'] * weather['home_weather_modifier']
        away_base = away_form_score * away_injury['squad_integrity_modifier'] * weather['away_weather_modifier']

        # Apply weighted model formula
        home_composite = (
            (home_base * 0.40) + 
            (motivation['home_motivation'] * 0.30) + 
            ((1.0 - fatigue['home_fatigue_score']) * 0.20) # Lower fatigue = higher rating contribution
        )

        away_composite = (
            (away_base * 0.40) + 
            (motivation['away_motivation'] * 0.30) + 
            ((1.0 - fatigue['away_fatigue_score']) * 0.20)
        )

        # Determine structural value edge
        edge_differential = round(home_composite - away_composite, 3)
        
        if edge_differential > 0.15:
            verdict = "STRONG HOME ADVANTAGE"
        elif edge_differential < -0.15:
            verdict = "STRONG AWAY ADVANTAGE"
        else:
            verdict = "COMPETITIVE / HIGH-RISK DRAW POTENTIAL"

        return {
            "fixture_id": fixture_context.get("fixture_id", 0),
            "home_composite_rating": round(home_composite, 3),
            "away_composite_rating": round(away_composite, 3),
            "edge_differential": edge_differential,
            "recommended_analytical_verdict": verdict
        }
