import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("athena.test")

try:
    from services.statistics_service import StatisticsService
    from services.standings_service import StandingsService
    from services.team_form_service import TeamFormService
    # Changed from intelligence.form_engine to match your repository layout
    from intelligence.form import FormEngine
    
    logger.info("✅ All Sprint 2 Football Intelligence modules imported successfully!")
    
    stats_svc = StatisticsService()
    form_svc = TeamFormService()
    standings_svc = StandingsService(stats_svc)
    engine = FormEngine(stats_svc, form_svc)
    
    logger.info("✅ Architecture initialized cleanly without breaking dependencies.")

except Exception as e:
    logger.error(f"❌ Initialization failed: {e}")
