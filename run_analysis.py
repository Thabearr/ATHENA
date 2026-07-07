import sys
import logging
from workers.api_loader import LiveAPILoader
from services.statistics_service import StatisticsService
from services.team_form_service import TeamFormService
from intelligence.form import FormEngine
from intelligence.motivation import MotivationEngine
from intelligence.weather import WeatherEngine
from intelligence.fatigue import FatigueEngine
from intelligence.injuries import InjuryEngine
from intelligence.match_analyst import MatchAnalyst
from services.analysis_pipeline import AnalysisPipeline
from intelligence.accumulator import AccumulatorEngine

logging.basicConfig(level=logging.WARNING)

def main():
    print("\n" + "="*70)
    print("      🔮 ATHENA FOOTBALL INTELLIGENCE & LIVE FEED LIVE SYSTEM 🔮")
    print("="*70)
    
    try:
        # Step 1: Spin up the Ingestion Worker to capture new matches
        print("📥 Initializing API ingestion sync down worker...")
        loader = LiveAPILoader()
        loader.sync_fixtures_to_db()
        
        # Step 2: Initialize full analytical dependency stack
        stats_svc = StatisticsService()
        form_svc = TeamFormService()
        form_eng = FormEngine(stats_svc, form_svc)
        motivation_eng = MotivationEngine()
        weather_eng = WeatherEngine()
        fatigue_eng = FatigueEngine()
        injury_eng = InjuryEngine()
        
        analyst = MatchAnalyst(form_eng, motivation_eng, weather_eng, fatigue_eng, injury_eng)
        pipeline = AnalysisPipeline(analyst, form_svc)
        
        print("\n⏳ Processing analytical engine vectors across active lines...")
        results = pipeline.run_pipeline_snapshot(execution_limit=10)
        
        # Step 3: Extract and generate high-probability slips matching your bookie options
        acca_engine = AccumulatorEngine(min_edge=0.01)
        slip_5_fold = acca_engine.generate_accumulator(results, fold_size=5)
        
        print("\n" + "🚀 LIVE ACCUMULATOR SELECTIONS (ZERO-VOLATILITY FILTER)")
        print("="*70)
        if not slip_5_fold or 'legs' not in slip_5_fold or len(slip_5_fold['legs']) == 0:
            print(" No qualified high-confidence selections passed structural risk filtering.")
        else:
            print(f" TYPE: {slip_5_fold['fold_size']}-Fold Slip | COMPOUNDED ODDS: {slip_5_fold['total_estimated_odds']}x")
            print("-"*70)
            for idx, leg in enumerate(slip_5_fold['legs'], 1):
                print(f" {idx}. {leg['fixture']:<28} | {leg['market']:<20} -> {leg['selection']}")
        print("="*70 + "\n")

    except Exception as e:
        print(f"❌ System Interrupted: {e}")

if __name__ == "__main__":
    main()
