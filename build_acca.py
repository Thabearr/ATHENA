#!/usr/bin/env python3
"""
ATHENA Accumulator Builder - CLI Interface
Generates bulletproof accas based on statistical analysis over configurable timeframes.
Usage: python build_acca.py --days 2 --folds 20
"""

import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Core imports
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
from database.database import Database

# Logger setup
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("athena.build_acca")

app = typer.Typer(help="🎯 ATHENA Accumulator Builder - Generate precision accas")
console = Console()


class AccaBuilder:
    """Orchestrates acca generation pipeline."""
    
    def __init__(self, days_ahead: int = 3, min_edge: float = 0.05):
        self.days_ahead = min(days_ahead, 3)  # Enforce 3-day max
        self.min_edge = min_edge
        self.db = Database()
        
        # Initialize loaders
        self.api_loader = LiveAPILoader(days_ahead=self.days_ahead)
        self.ofb_loader = OpenFootballLoader()
        
        # Initialize analysis stack
        self.stats_svc = StatisticsService()
        self.form_svc = TeamFormService()
        self.form_eng = FormEngine(self.stats_svc, self.form_svc)
        self.motivation_eng = MotivationEngine()
        self.weather_eng = WeatherEngine()
        self.fatigue_eng = FatigueEngine()
        self.injury_eng = InjuryEngine()
        self.referee_eng = RefereeEngine()
        self.risk_eng = RiskEngine()
        
        # Analyst + Pipeline
        self.analyst = MatchAnalyst(
            form_engine=self.form_eng,
            motivation_engine=self.motivation_eng,
            weather_engine=self.weather_eng,
            fatigue_engine=self.fatigue_eng,
            injury_engine=self.injury_eng,
            referee_engine=self.referee_eng,
            risk_engine=self.risk_eng
        )
        self.pipeline = AnalysisPipeline(self.analyst, self.form_svc)
        self.acca_engine = AccumulatorEngine(min_edge=self.min_edge)
    
    def _validate_timeframe(self, days: int) -> bool:
        """Enforce max 3-day constraint."""
        if days < 1 or days > 3:
            console.print(f"[red]❌ Invalid timeframe: {days} days. Must be 1-3 days.[/red]")
            return False
        return True
    
    def _fetch_live_fixtures(self) -> list:
        """Pull live fixtures from all sources within the time window."""
        console.print(f"[cyan]📥 Fetching live fixtures for next {self.days_ahead} day(s)...[/cyan]")
        
        try:
            # Fetch from football-data.org (primary)
            fdo_fixtures = self.api_loader.fetch_upcoming_fixtures()
            
            # Supplement with OpenFootball for coverage gaps
            try:
                ofb_counts = self.ofb_loader.fetch_and_sync()
                console.print(
                    f"[green]✅ Synced {ofb_counts.get('upcoming', 0)} live fixtures, "
                    f"{ofb_counts.get('historical', 0)} historical results[/green]"
                )
            except Exception as e:
                logger.warning(f"OpenFootball sync skipped: {e}")
            
            console.print(f"[green]✅ Loaded {len(fdo_fixtures)} fixtures from live sources[/green]")
            return fdo_fixtures
        except Exception as e:
            console.print(f"[red]❌ Failed to fetch fixtures: {e}[/red]")
            return []
    
    def _filter_by_timeframe(self, fixtures: list, days: int) -> list:
        """Filter fixtures to only those within the next N days."""
        cutoff = datetime.utcnow() + timedelta(days=days)
        filtered = []
        
        for fx in fixtures:
            try:
                fx_date = datetime.fromisoformat(fx.get("match_date", "").replace("Z", "+00:00"))
                if fx_date <= cutoff:
                    filtered.append(fx)
            except (ValueError, TypeError):
                continue
        
        return filtered
    
    def _analyze_fixtures(self, fixtures: list) -> list:
        """Run full analysis pipeline on all fixtures."""
        console.print("[cyan]🔍 Running statistical analysis on all fixtures...[/cyan]")
        
        results = self.pipeline.run_pipeline_snapshot(execution_limit=150)
        
        if not results:
            console.print("[yellow]⚠️  No fixtures matched analysis filters.[/yellow]")
            return []
        
        # Filter to only HIGH-CONFIDENCE selections
        safe_matches = [
            r for r in results
            if not r.get("upset_alert", False) 
            and r.get("edge", 0.0) >= self.min_edge
            and r.get("risk_score", 100) <= 55  # Risk score <= 55 is acceptable
        ]
        
        console.print(
            f"[cyan]📊 Analysis complete: {len(results)} fixtures analyzed, "
            f"{len(safe_matches)} high-confidence selections[/cyan]"
        )
        
        return safe_matches
    
    def _display_safe_selections(self, safe_matches: list):
        """Pretty-print all safe selections before accumulator generation."""
        if not safe_matches:
            return
        
        console.print("\n[bold cyan]═══ SAFE FIXTURE SELECTIONS ═══[/bold cyan]")
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Fixture", style="cyan")
        table.add_column("Verdict", style="green")
        table.add_column("Edge", style="yellow")
        table.add_column("Risk", style="red")
        table.add_column("Status", style="white")
        
        for match in safe_matches[:20]:  # Show top 20
            status = "🟢" if not match.get("upset_alert") else "🟡"
            table.add_row(
                match.get("fixture", "?"),
                match.get("verdict", "?"),
                f"{match.get('edge', 0.0):.3f}",
                f"{match.get('risk_score', 0.0):.0f}",
                status
            )
        
        console.print(table)
    
    def build(self, days: int, fold_size: int) -> dict:
        """Main orchestration: fetch → analyze → generate acca."""
        
        # Validation
        if not self._validate_timeframe(days):
            return {"success": False, "error": "Invalid timeframe"}
        
        if fold_size < 1 or fold_size > 50:
            console.print("[red]❌ Fold size must be 1-50.[/red]")
            return {"success": False, "error": "Invalid fold size"}
        
        # Step 1: Fetch live data
        fixtures = self._fetch_live_fixtures()
        if not fixtures:
            return {"success": False, "error": "No fixtures available"}
        
        # Step 2: Filter by timeframe
        windowed_fixtures = self._filter_by_timeframe(fixtures, days)
        console.print(
            f"[cyan]🎯 Timeframe filter: {len(windowed_fixtures)}/{len(fixtures)} "
            f"fixtures within {days} day(s)[/cyan]"
        )
        
        if not windowed_fixtures:
            return {"success": False, "error": f"No fixtures found in next {days} day(s)"}
        
        # Step 3: Analyze all fixtures
        safe_matches = self._analyze_fixtures(windowed_fixtures)
        
        if len(safe_matches) < fold_size:
            console.print(
                f"[yellow]⚠️  WARNING: Only {len(safe_matches)} safe fixtures available, "
                f"but {fold_size}-fold requested.[/yellow]"
            )
            if len(safe_matches) == 0:
                return {"success": False, "error": "Insufficient safe fixtures for acca"}
            fold_size = len(safe_matches)  # Downsize gracefully
        
        # Display available selections
        self._display_safe_selections(safe_matches)
        
        # Step 4: Build accumulator
        console.print(
            f"\n[cyan]🚀 Building {fold_size}-Fold Accumulator "
            f"(min edge: {self.min_edge:.3f})...[/cyan]"
        )
        
        acca = self.acca_engine.generate_accumulator(safe_matches, fold_size=fold_size)
        
        if not acca.get("legs"):
            console.print(
                f"[red]❌ Failed to generate {fold_size}-fold acca. "
                f"Possible edge threshold mismatch.[/red]"
            )
            return {"success": False, "error": "Accumulator generation failed"}
        
        acca["success"] = True
        acca["safe_fixtures_count"] = len(safe_matches)
        acca["timeframe_days"] = days
        
        return acca
    
    def display_acca(self, acca: dict):
        """Pretty-print the final accumulator slip."""
        if not acca.get("success"):
            console.print(f"[red]❌ {acca.get('error', 'Unknown error')}[/red]")
            return
        
        fold_size = acca.get("fold_size", 0)
        total_odds = acca.get("total_estimated_odds", 0.0)
        legs = acca.get("legs", [])
        
        console.print("\n")
        
        # Header
        header = (
            f"⚡ {fold_size}-FOLD ACCUMULATOR SLIP\n"
            f"🎯 Compounded Odds: {total_odds}x\n"
            f"📊 Safe Selections: {acca.get('safe_fixtures_count', 0)}\n"
            f"⏰ Timeframe: {acca.get('timeframe_days', 0)} day(s)"
        )
        console.print(Panel(header, border_style="green"))
        
        # Legs table
        table = Table(show_header=True, header_style="bold green")
        table.add_column("Leg", style="cyan", width=5)
        table.add_column("Fixture", style="cyan")
        table.add_column("Market", style="yellow")
        table.add_column("Selection", style="green")
        
        for idx, leg in enumerate(legs, 1):
            table.add_row(
                f"{idx:02d}",
                leg.get("fixture", "?"),
                leg.get("market", "?"),
                leg.get("selection", "?")
            )
        
        console.print(table)
        
        console.print(
            f"\n[bold green]✅ ACCA READY FOR BETTING[/bold green]\n"
            f"Expected Value: {total_odds}x stake\n"
        )


@app.command()
def generate(
    days: int = typer.Option(2, "--days", "-d", help="Days ahead (1-3)"),
    folds: int = typer.Option(5, "--folds", "-f", help="Number of legs in acca (1-50)"),
    min_edge: float = typer.Option(0.05, "--edge", "-e", help="Minimum edge threshold (0.01-0.50)"),
):
    """
    Generate a precision accumulator.
    
    Examples:
      python build_acca.py generate --days 2 --folds 20
      python build_acca.py generate -d 3 -f 15 -e 0.06
    """
    console.print("\n" + "="*70)
    console.print("      🔮 ATHENA ACCUMULATOR BUILDER 🔮")
    console.print("="*70)
    
    builder = AccaBuilder(days_ahead=days, min_edge=min_edge)
    acca = builder.build(days=days, fold_size=folds)
    builder.display_acca(acca)


@app.command()
def quick(
    folds: int = typer.Option(5, "--folds", "-f", help="Number of legs"),
):
    """
    Quick acca with defaults (2 days, min edge 0.05).
    
    Example: python build_acca.py quick --folds 10
    """
    console.print("\n" + "="*70)
    console.print("      🔮 ATHENA QUICK ACCA 🔮")
    console.print("="*70)
    
    builder = AccaBuilder(days_ahead=2, min_edge=0.05)
    acca = builder.build(days=2, fold_size=folds)
    builder.display_acca(acca)


if __name__ == "__main__":
    app()
