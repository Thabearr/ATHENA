import sys
import logging
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
    print("      🔮 ATHENA FOOTBALL INTELLIGENCE & ACCUMULATOR SYSTEM 🔮")
    print("="*70)
    
    try:
        stats_svc = StatisticsService()
        form_svc = TeamFormService()
        form_eng = FormEngine(stats_svc, form_svc)
        motivation_eng = MotivationEngine()
        weather_eng = WeatherEngine()
        fatigue_eng = FatigueEngine()
        injury_eng = InjuryEngine()
        
        analyst = MatchAnalyst(form_eng, motivation_eng, weather_eng, fatigue_eng, injury_eng)
        pipeline = AnalysisPipeline(analyst, form_svc)
        
        print("\n⏳ Processing pipeline metrics over upcoming schedules...")
        results = pipeline.run_pipeline_snapshot(execution_limit=35)
        
        # Initialize the custom Accumulator Engine built from standard options
        acca_engine = AccumulatorEngine(min_edge=0.02)
        
        # Construct an ultra-reliable 5-fold anchor slip for testing
        slip_5_fold = acca_engine.generate_accumulator(results, fold_size=5)
        
        print("\n" + "🚀 TARGET ACCUMULATOR SELECTIONS (LOW-VARIANCE ENGINE)")
        print("="*70)
        if not slip_5_fold or 'legs' not in slip_5_fold:
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
