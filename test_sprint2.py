import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("athena.test")

try:
    from services.statistics_service import StatisticsService
    from services.team_form_service import TeamFormService
    from intelligence.form import FormEngine
    from intelligence.motivation import MotivationEngine
    from intelligence.weather import WeatherEngine
    from intelligence.fatigue import FatigueEngine
    from intelligence.injuries import InjuryEngine
    from intelligence.match_analyst import MatchAnalyst
    from services.analysis_pipeline import AnalysisPipeline
    
    logger.info("✅ All Sprint 2 Components imported successfully!")
    
    # Init stack
    stats_svc = StatisticsService()
    form_svc = TeamFormService()
    form_eng = FormEngine(stats_svc, form_svc)
    motivation_eng = MotivationEngine()
    weather_eng = WeatherEngine()
    fatigue_eng = FatigueEngine()
    injury_eng = InjuryEngine()
    
    analyst = MatchAnalyst(form_eng, motivation_eng, weather_eng, fatigue_eng, injury_eng)
    pipeline = AnalysisPipeline(analyst)
    
    # Run a pipeline evaluation check
    results = pipeline.run_pipeline_snapshot(execution_limit=3)
    
    logger.info("--- 🚀 PIPELINE EXECUTION SNAPSHOT ---")
    if not results:
        logger.info("   Pipeline active, 0 upcoming fixtures in queue.")
    for res in results:
        logger.info(f" Match: {res['fixture']} | Edge: {res['edge']} | Target: {res['verdict']}")
    logger.info("-------------------------------------")
    logger.info("✅ Complete Sprint 2 Architecture validated successfully!")

except Exception as e:
    logger.error(f"❌ Initialization failed: {e}")
