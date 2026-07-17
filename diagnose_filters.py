#!/usr/bin/env python3
"""
Diagnostic: Show why matches are being filtered from accas.
"""

import logging
from datetime import datetime, timedelta

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
from database.database import Database
from rich.console import Console
from rich.table import Table

logging.basicConfig(level=logging.WARNING)
console = Console()

# Initialize
db = Database()
stats_svc = StatisticsService()
form_svc = TeamFormService()
form_eng = FormEngine(stats_svc, form_svc)
motivation_eng = MotivationEngine()
weather_eng = WeatherEngine()
fatigue_eng = FatigueEngine()
injury_eng = InjuryEngine()
referee_eng = RefereeEngine()
risk_eng = RiskEngine()

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

print("\n" + "="*100)
print("  🔍 ACCA FILTER DIAGNOSTIC - Why Matches Are Rejected")
print("="*100 + "\n")

# Fetch all upcoming
upcoming = pipeline.fetch_upcoming_fixtures(limit=150)
print(f"📊 Total upcoming fixtures: {len(upcoming)}\n")

# Analyze all and show why each is accepted/rejected
results = pipeline.run_pipeline_snapshot(execution_limit=150)

# Display detailed breakdown
table = Table(show_header=True, header_style="bold cyan")
table.add_column("Fixture", style="cyan", width=30)
table.add_column("Verdict", style="yellow", width=20)
table.add_column("Edge", style="green", width=8)
table.add_column("Risk", style="magenta", width=6)
table.add_column("Upset?", style="red", width=7)
table.add_column("Stale?", style="orange", width=7)
table.add_column("Status", style="white", width=8)

safe_count = 0
reject_count = 0

for r in results:
    is_safe = not r.get("upset_alert", False) and r.get("edge", 0.0) >= 0.05 and r.get("risk_score", 100) <= 55
    
    if is_safe:
        status = "✅ SAFE"
        safe_count += 1
    else:
        status = "❌ REJECT"
        reject_count += 1
    
    table.add_row(
        r.get("fixture", "?")[:28],
        r.get("verdict", "?")[:18],
        f"{r.get('edge', 0.0):.3f}",
        f"{r.get('risk_score', 0.0):.0f}",
        "YES" if r.get("upset_alert") else "NO",
        "YES" if r.get("stale_data") else "NO",
        status
    )

console.print(table)

print(f"\n✅ Safe selections: {safe_count}")
print(f"❌ Rejected selections: {reject_count}")
print(f"⚠️  Rejection rate: {100 * reject_count / len(results):.1f}%\n")

# Suggest tuning
if reject_count / len(results) > 0.95:
    console.print("[red]⚠️  FILTER IS TOO STRICT[/red]")
    console.print("Suggestions:")
    console.print("  1. Reduce min_edge threshold (currently 0.05)")
    console.print("  2. Increase risk_score threshold (currently 55)")
    console.print("  3. Allow some upset_alert matches (currently blocking all)")
    print()

print("="*100 + "\n")
