import sys
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
    
    logger.info("✅ All Sprint 2 Football Intelligence modules imported successfully!")
    
    # Initialize Core Classes
    stats_svc = StatisticsService()
    form_svc = TeamFormService()
    standings_svc = StandingsService(stats_svc)
    form_eng = FormEngine(stats_svc, form_svc)
    motivation_eng = MotivationEngine()
    weather_eng = WeatherEngine()
    fatigue_eng = FatigueEngine()
    
    # Fatigue Dry-Run Verification
    fatigue_clash = fatigue_eng.analyze_fixture_fatigue_clash(
        home_team_id=10, away_team_id=20,
        current_date="2026-07-07",
        home_last_date="2026-07-02",  # 5 days rest
        away_last_date="2026-07-04",  # 3 days rest + continental travel
        away_has_continental_travel=True
    )
    
    logger.info(f"✅ Fatigue check complete. Home Index: {fatigue_clash['home_fatigue_score']}, Away Index: {fatigue_clash['away_fatigue_score']}")
    logger.info("✅ Architecture initialized cleanly without breaking dependencies.")

except Exception as e:
    logger.error(f"❌ Initialization failed: {e}")
