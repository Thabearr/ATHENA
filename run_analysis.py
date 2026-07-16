import sys
import logging
from workers.api_loader import LiveAPILoader
from workers.openfootball_loader import OpenFootballLoader
from services.statistics_service import StatisticsService
from services.team_form_service import TeamFormService
from intelligence.form import FormEngine
from intelligence.motivation import MotivationEngine
from intelligence.weather import WeatherEngine
from intelligence.fatigue import FatigueEngine
from intelligence.injuries import InjuryEngine
from intelligence.referee import RefereeEngine
from engine.risk_engine import RiskEngine
from intelligence.match_analyst import MatchAnalyst
from services.analysis_pipeline import AnalysisPipeline
from intelligence.accumulator import AccumulatorEngine
# Kept at warning to keep your terminal output clean during production runs
logging.basicConfig(level=logging.WARNING)
def main():
    print("\n" + "="*70)
    print("      🔮 ATHENA FOOTBALL INTELLIGENCE & LIVE FEED LIVE SYSTEM 🔮")
    print("="*70)
    
    try:
        # Step 1: Spin up the Ingestion Worker to capture new matches
        print("📥 Initializing API ingestion sync down worker...")
        loader = LiveAPILoader()
        
        # Accommodates the updated bulk-transaction loader we built
        raw_fixtures = loader.fetch_upcoming_fixtures() if hasattr(loader, 'fetch_upcoming_fixtures') else []
        try:
            loader.sync_fixtures_to_db(raw_fixtures)
        except TypeError:
            loader.sync_fixtures_to_db()

        # openfootball: public-domain, current-season data for leagues that
        # would otherwise fall back to stale 2022-2024 API-Football data
        try:
            ofb_loader = OpenFootballLoader()
            ofb_counts = ofb_loader.fetch_and_sync()
            print(f"   openfootball: {ofb_counts['upcoming']} live fixtures, {ofb_counts['historical']} live results synced.")
        except Exception as e:
            print(f"   openfootball sync skipped due to error: {e}")
        
        # Step 2: Initialize full analytical dependency stack
        stats_svc = StatisticsService()
        form_svc = TeamFormService()
        
        form_eng = FormEngine(stats_svc, form_svc)
        motivation_eng = MotivationEngine()
        weather_eng = WeatherEngine()
        fatigue_eng = FatigueEngine()
        injury_eng = InjuryEngine()
        referee_eng = RefereeEngine()  # New Upset Mitigation Engine
        risk_eng = RiskEngine()        # New Traps & Variance Filter
        
        # Updated Analyst now maps all 7 parameters for the foolproof matrices
        analyst = MatchAnalyst(
            form_engine=form_eng, 
            motivation_engine=motivation_eng, 
            weather_engine=weather_eng, 
            fatigue_engine=fatigue_eng, 
            injury_engine=injury_eng,
            referee_engine=referee_eng,
            risk_engine=risk_eng
        )
        pipeline = AnalysisPipeline(analyst, form_svc)
        
        print("\n⏳ Processing analytical engine vectors across active lines...")
        # Spiked the execution limit to 150 to ensure enough matches are scanned for a 30-leg slip
        results = pipeline.run_pipeline_snapshot(execution_limit=150)

        # Raw per-fixture analysis, shown regardless of whether there's
        # enough volume for an accumulator. This is the actual output of
        # the prediction engine for every fixture it looked at.
        print("\n" + "🔍 RAW PER-FIXTURE ANALYSIS")
        print("="*70)
        if not results:
            print("No fixtures were analyzed (none in the database matched the filters).")
        else:
            for r in results:
                stale_tag = " [STALE DATA]" if r.get("stale_data") else ""
                upset_tag = " [UPSET RISK]" if r.get("upset_alert") else ""
                print(
                    f" {r['fixture']:<40} | verdict={r['verdict']:<24} "
                    f"| risk={r['risk_score']:<5} | edge={r['edge']:.2f} "
                    f"| source={r.get('source', 'unknown')}{stale_tag}{upset_tag}"
                )
        
        # Step 3: Extract and generate high-probability slips matching your bookie options
        # Bumped min_edge to 0.05 to enforce stricter mathematical safety floors
        acca_engine = AccumulatorEngine(min_edge=0.05)
        
        print("\n" + "🚀 LIVE ACCUMULATOR SELECTIONS (ZERO-VOLATILITY FILTER)")
        print("="*70)
        # Generate cascading slip tiers based on available safe matches
        folds = [5, 10, 20, 30]
        for fold in folds:
            slip = acca_engine.generate_accumulator(results, fold_size=fold)
            
            if not slip or 'legs' not in slip or len(slip['legs']) == 0:
                print(f"\n⚠️  Not enough strictly safe fixtures to fulfill a {fold}-Fold slip.")
                continue
                
            print(f"\n⚡ TYPE: {slip['fold_size']}-Fold Slip | COMPOUNDED ODDS: {slip['total_estimated_odds']}x")
            print("-" * 70)
            for idx, leg in enumerate(slip['legs'], 1):
                # Formatted to perfectly align in a Unix terminal
                print(f" {idx:02d}. {leg['fixture']:<32} | {leg['market']:<15} -> {leg['selection']}")
                
        print("\n" + "="*70 + "\n")
    except Exception as e:
        print(f"❌ System Interrupted: {e}")
if __name__ == "__main__":
    main()
