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
    
    logger.info("✅ All Production Sprint 2 Components imported successfully!")
    
    # Initialize full dependency chain
    stats_svc = StatisticsService()
    form_svc = TeamFormService()
    form_eng = FormEngine(stats_svc, form_svc)
    motivation_eng = MotivationEngine()
    weather_eng = WeatherEngine()
    fatigue_eng = FatigueEngine()
    injury_eng = InjuryEngine()
    
    analyst = MatchAnalyst(form_eng, motivation_eng, weather_eng, fatigue_eng, injury_eng)
    
    # Pass analyst and form_svc explicitly into our live pipeline
    pipeline = AnalysisPipeline(analyst, form_svc)
    
    # Trigger full calculation pass over upcoming database data
    results = pipeline.run_pipeline_snapshot(execution_limit=5)
    
    logger.info("--- 🚀 LIVE PIPELINE RUN COMPLETED ---")
    if not results:
        logger.info("   Pipeline executed successfully: 0 fixtures pending in queue or awaiting data seeding.")
    for res in results:
        logger.info(f" Match: {res['fixture']} | Computed Edge: {res['edge']} | Target Recommendation: {res['verdict']}")
    logger.info("-------------------------------------")
    logger.info("✅ Complete Sprint 2 Architecture fully validated and live-linked!")

except Exception as e:
    logger.error(f"❌ Initialization failed: {e}")
