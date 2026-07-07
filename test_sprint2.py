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
    from intelligence.injuries import InjuryEngine
    
    logger.info("✅ All Sprint 2 Football Intelligence modules imported successfully!")
    
    # Core Service and Engine initializations
    stats_svc = StatisticsService()
    form_svc = TeamFormService()
    standings_svc = StandingsService(stats_svc)
    form_eng = FormEngine(stats_svc, form_svc)
    motivation_eng = MotivationEngine()
    weather_eng = WeatherEngine()
    fatigue_eng = FatigueEngine()
    injury_eng = InjuryEngine()
    
    # Comprehensive Dry-Run execution check
    mock_absences = [
        {"name": "Star Striker", "role": "critical", "reason": "Hamstring Strain"},
        {"name": "Main Center Back", "role": "key", "reason": "Suspension"}
    ]
    injury_check = injury_eng.calculate_squad_degradation(mock_absences)
    
    logger.info(f"✅ Injury check complete. Squad Integrity Modifier: {injury_check['squad_integrity_modifier']}")
    for note in injury_check['tactical_impact_notes']:
        logger.info(f"   -> {note}")
        
    logger.info("✅ Complete Sprint 2 Intelligence Architecture initialized cleanly without breaking dependencies!")

except Exception as e:
    logger.error(f"❌ Initialization failed: {e}")
