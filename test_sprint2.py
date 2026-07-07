import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("athena.test")

try:
    from services.statistics_service import StatisticsService
    from services.standings_service import StandingsService
    from services.team_form_service import TeamFormService
    from intelligence.form import FormEngine
    from intelligence.motivation import MotivationEngine
    from intelligence.weather import WeatherEngine
    from intelligence.fatigue import FatigueEngine
    from intelligence.injuries import InjuryEngine
    from intelligence.match_analyst import MatchAnalyst
    
    logger.info("✅ All Sprint 2 Football Intelligence modules imported successfully!")
    
    # Initialize complete dependency stack
    stats_svc = StatisticsService()
    form_svc = TeamFormService()
    standings_svc = StandingsService(stats_svc)
    form_eng = FormEngine(stats_svc, form_svc)
    motivation_eng = MotivationEngine()
    weather_eng = WeatherEngine()
    fatigue_eng = FatigueEngine()
    injury_eng = InjuryEngine()
    
    analyst = MatchAnalyst(form_eng, motivation_eng, weather_eng, fatigue_eng, injury_eng)
    
    # Complex simulated match context payload
    simulated_match = {
        "fixture_id": 101, "league_id": 39, "season": 2026, "league_size": 20,
        "home_id": 1, "home_position": 3, "home_style": "passing",
        "away_id": 2, "away_position": 19, "away_style": "long_ball",
        "mock_home_form": 0.85, "mock_away_form": 0.35,
        "match_date": "2026-07-07", "home_last_match": "2026-07-02", "away_last_match": "2026-07-04",
        "away_continental": True,
        "weather": {"condition": "heavy torrential rain", "wind_speed": 12.0, "temp": 15.0},
        "home_absences": [{"name": "Midfield Pivot", "role": "key", "reason": "Knee Strain"}],
        "away_absences": [{"name": "Star Striker", "role": "critical", "reason": "Hamstring Tear"}]
    }
    
    analysis = analyst.compile_master_fixture_prediction(simulated_match)
    
    logger.info("--- 📊 SPRINT 2 INTEGRATED ANALYSIS COMPLETE ---")
    logger.info(f" Home Composite Rating: {analysis['home_composite_rating']}")
    logger.info(f" Away Composite Rating: {analysis['away_composite_rating']}")
    logger.info(f" Net Advantage Margin:  {analysis['edge_differential']}")
    logger.info(f" ATHENA Target Verdict: {analysis['recommended_analytical_verdict']}")
    logger.info("-------------------------------------------------")
    logger.info("✅ Architecture initialized cleanly without breaking dependencies.")

except Exception as e:
    logger.error(f"❌ Initialization failed: {e}")
