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
    
    logger.info("✅ All Sprint 2 Football Intelligence modules imported successfully!")
    
    # Core Service and Engine Initialization
    stats_svc = StatisticsService()
    form_svc = TeamFormService()
    standings_svc = StandingsService(stats_svc)
    form_eng = FormEngine(stats_svc, form_svc)
    motivation_eng = MotivationEngine()
    weather_eng = WeatherEngine()
    
    # Weather Dry-Run Verification
    mock_weather = {"condition": "heavy rain", "wind_speed": 28.5, "temp": 14.0}
    weather_clash = weather_eng.assess_tactical_weather_impact(mock_weather, home_style="passing", away_style="long_ball")
    
    logger.info(f"✅ Weather check complete. Home Mod: {weather_clash['home_weather_modifier']}, Away Mod: {weather_clash['away_weather_modifier']}")
    logger.info("✅ Architecture initialized cleanly without breaking dependencies.")

except Exception as e:
    logger.error(f"❌ Initialization failed: {e}")
