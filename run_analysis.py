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

# Suppress background logs to keep the terminal console report pristine
logging.basicConfig(level=logging.WARNING)

def main():
    print("\n" + "="*65)
    print("      🔮 ATHENA FOOTBALL INTELLIGENCE ANALYSIS PIPELINE 🔮")
    print("="*65)
    
    try:
        # Initialize full infrastructure dependency stack
        stats_svc = StatisticsService()
        form_svc = TeamFormService()
        form_eng = FormEngine(stats_svc, form_svc)
        motivation_eng = MotivationEngine()
        weather_eng = WeatherEngine()
        fatigue_eng = FatigueEngine()
        injury_eng = InjuryEngine()
        
        analyst = MatchAnalyst(form_eng, motivation_eng, weather_eng, fatigue_eng, injury_eng)
        pipeline = AnalysisPipeline(analyst, form_svc)
        
        print("\n⏳ Accessing database to capture upcoming unplayed fixtures...")
        results = pipeline.run_pipeline_snapshot(execution_limit=10)
        
        print("\n" + "-"*65)
        print(f" {'UPCOMING FIXTURE':<28} | {'EDGE':<6} | {'TARGET VERDICT'}")
        print("-"*65)
        
        if not results:
            print(f"   {'No upcoming matches currently populated in the database.':^58}")
        else:
            for res in results:
                edge_val = res['edge']
                edge_str = f"+{edge_val:.2f}" if edge_val > 0 else f"{edge_val:.2f}"
                print(f" {res['fixture']:<28} | {edge_str:<6} | {res['verdict']}")
                
        print("="*65 + "\n")

    except Exception as e:
        print(f"❌ Engine Execution Interrupted: {e}")

if __name__ == "__main__":
    main()
