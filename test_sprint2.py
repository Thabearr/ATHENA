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
    
    logger.info("✅ All Sprint 2 Football Intelligence modules imported successfully!")
    
    # Initialization validation
    stats_svc = StatisticsService()
    form_svc = TeamFormService()
    standings_svc = StandingsService(stats_svc)
    form_eng = FormEngine(stats_svc, form_svc)
    motivation_eng = MotivationEngine()
    
    # Basic functional dry-run execution
    dummy_fixture = {"home_id": 1, "away_id": 2, "home_position": 19, "away_position": 10, "league_id": 39, "season": 2026}
    clash = motivation_eng.analyze_fixture_motivation_clash(dummy_fixture, league_size=20)
    
    logger.info(f"✅ Functional check complete. Home Motivation Score: {clash['home_motivation']} ({clash['home_context']})")
    logger.info("✅ Architecture initialized cleanly without breaking dependencies.")

except Exception as e:
    logger.error(f"❌ Initialization failed: {e}")
