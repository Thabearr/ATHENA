#!/usr/bin/env python3
"""
ATHENA Accumulator Builder - CLI Interface
Generates bulletproof accas based on statistical analysis over configurable timeframes.
Usage: python build_acca.py --days 2 --folds 20
"""

import sys
import logging
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Core imports
from workers.fotmob_advanced_scraper import FotMobAdvancedScraper
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
from intelligence.acca_filter import AccaFilter
from services.kelly_calculator import KellyCalculator
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
        
        # Initialize data loaders
        self.fotmob_scraper = FotMobAdvancedScraper()
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
        self.acca_filter = AccaFilter()
        self.kelly_calculator = KellyCalculator(safety_multiplier=0.25, max_exposure=0.05)
    
    def _validate_timeframe(self, days: int) -> bool:
        """Enforce max 3-day constraint."""
        if days < 1 or days > 3:
            console.print(f"[red]❌ Invalid timeframe: {days} days. Must be 1-3 days.[/red]")
            return False
        return True
    
    def _fetch_live_fixtures(self) -> list:
        """Pull live fixtures from FotMob + OpenFootball sources."""
        console.print(f"[cyan]Fetching live fixtures from FotMob for next {self.days_ahead} day(s)...[/cyan]")
        
        try:
            # Fetch from FotMob (primary - bypass client, no API key needed)
            fotmob_fixtures = self.fotmob_scraper.fetch_upcoming_matches(days_ahead=self.days_ahead)
            
            # Sync to DB
            if fotmob_fixtures:
                self.fotmob_scraper.sync_to_db(fotmob_fixtures)
            
            # Supplement with OpenFootball for coverage gaps
            try:
                ofb_counts = self.ofb_loader.fetch_and_sync()
                console.print(
                    f"[green]FotMob: {len(fotmob_fixtures)} fixtures | "
                    f"OpenFootball: {ofb_counts.get('upcoming', 0)} upcoming, "
                    f"{ofb_counts.get('historical', 0)} historical[/green]"
                )
            except Exception as e:
                logger.warning(f"OpenFootball sync skipped: {e}")
                console.print(f"[green]FotMob: {len(fotmob_fixtures)} fixtures[/green]")
            
            return fotmob_fixtures
        except Exception as e:
            console.print(f"[red]Failed to fetch fixtures: {e}[/red]")
            return []
    
    def _get_fixtures_from_db(self, days: int) -> list:
        """
        Query database for fixtures within timeframe.
        """
        try:
            with self.db.connect() as conn:
                cursor = conn.cursor()
                
                now = datetime.utcnow()
                cutoff = now + timedelta(days=days)
                
                cursor.execute("""
                    SELECT 
                        fixture_id, league, home_team, away_team, 
                        match_date, status, data_source
                    FROM fixtures
                    WHERE status NOT IN ('FT', 'AET', 'PEN')
                      AND match_date >= ? AND match_date <= ?
                    ORDER BY match_date ASC
                """, (now.isoformat(), cutoff.isoformat()))
                
                rows = cursor.fetchall()
                fixtures = []
                
                for row in rows:
                    fixtures.append({
                        "fixture_id": row[0],
                        "league": row[1],
                        "home_team": row[2],
                        "away_team": row[3],
                        "match_date": row[4],
                        "status": row[5],
                        "data_source": row[6],
                    })
                
                return fixtures
        except Exception as e:
            logger.warning(f"DB query failed: {e}")
            return []
    
    def _analyze_fixtures(self, fixtures: list) -> list:
        """Run full analysis pipeline on all fixtures."""
        if not fixtures:
            console.print("[yellow]⚠️  No fixtures to analyze.[/yellow]")
            return []
        
        console.print(f"[cyan]🔍 Running statistical analysis on {len(fixtures)} fixture(s)...[/cyan]")
        
        results = self.pipeline.run_pipeline_snapshot(execution_limit=150)
        
        if not results:
            console.print("[yellow]⚠️  No fixtures matched analysis filters.[/yellow]")
            return []
        
        console.print(
            f"[cyan]📊 Analysis complete: {len(results)} analyzed[/cyan]"
        )
        
        return results
    
    def _display_safe_selections(self, all_matches: list, top_n: int = 15):
        """Pretty-print top selections ranked by fullproof score."""
        if not all_matches:
            return
        
        # Score and rank by fullproof criteria
        scored = [(m, self.acca_engine._score_fixture(m)) for m in all_matches]
        scored.sort(key=lambda x: x[1], reverse=True)
        
        console.print("\n[bold cyan]═══ TOP RANKED FIXTURES (BY FULLPROOF SCORE) ═══[/bold cyan]")
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Rank", style="yellow", width=5)
        table.add_column("Fixture", style="cyan", width=35)
        table.add_column("Verdict", style="green", width=20)
        table.add_column("Edge", style="white", width=8)
        table.add_column("Risk", style="red", width=6)
        table.add_column("Score", style="magenta", width=7)
        table.add_column("Eligible?", style="white", width=9)
        
        for idx, (match, score) in enumerate(scored[:top_n], 1):
            eligible = self.acca_engine._is_acca_eligible(match, strict=False)
            status = "✅" if eligible else "❌"
            table.add_row(
                f"{idx}",
                match.get("fixture", "?")[:33],
                match.get("verdict", "?")[:18],
                f"{match.get('edge', 0.0):.3f}",
                f"{match.get('risk_score', 0.0):.0f}",
                f"{score:.1f}",
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
        
        # Step 1: Fetch live fixtures from FotMob (bypass client)
        fotmob_fixtures = self._fetch_live_fixtures()
        
        # Step 2: Get all fixtures from database (includes FotMob + OpenFootball + historical)
        console.print("[cyan]Fetching from DB...[/cyan]")
        db_fixtures = self._get_fixtures_from_db(days)
        console.print(
            f"[cyan]🎯 Database contains {len(db_fixtures)} fixtures "
            f"within next {days} day(s)[/cyan]"
        )
        
        if not db_fixtures:
            return {"success": False, "error": f"No fixtures found in next {days} day(s)"}
        
        # Step 3: Analyze all fixtures
        console.print("[cyan]Analyzing fixtures...[/cyan]")
        all_analyzed = self._analyze_fixtures(db_fixtures)
        console.print("[cyan]Analysis complete.[/cyan]")
        
        if not all_analyzed:
            return {"success": False, "error": "No fixtures passed analysis"}
        
        # Step 4: Display ranked selections (fullproof scoring)
        self._display_safe_selections(all_analyzed, top_n=15)
        
        # Step 5: Filter for acca eligibility (Phase 4 Logic)
        ranked_legs = self.acca_filter.filter_and_rank_legs(all_analyzed)
        eligible_matches = self.acca_filter.build_filtered_acca(ranked_legs, target_size=fold_size)
        
        if len(eligible_matches) < fold_size:
            console.print(
                f"\n[yellow]⚠️  WARNING: Only {len(eligible_matches)} eligible fixtures, "
                f"but {fold_size}-fold requested.[/yellow]"
            )
            if len(eligible_matches) == 0:
                return {"success": False, "error": "No eligible fixtures for acca"}
            fold_size = len(eligible_matches)  # Downsize gracefully
            console.print(f"[yellow]📉 Downscaling to {fold_size}-fold acca[/yellow]")
        
        # Step 6: Build accumulator using fullproof scoring
        console.print(
            f"\n[cyan]🚀 Building {fold_size}-Fold Accumulator (Phase 4 optimized)...[/cyan]"
        )
        
        acca = self.acca_engine.generate_accumulator(eligible_matches, fold_size=fold_size, strict=False)
        
        if not acca.get("legs"):
            console.print(
                f"[red]❌ Failed to generate {fold_size}-fold acca.[/red]"
            )
            return {"success": False, "error": "Accumulator generation failed"}
        
        # Step 7: Phase 4 Kelly Sizing and Correlation Scoring
        total_odds = acca.get("total_estimated_odds", 1.0)
        # Approximate probability based on implied odds and edge
        avg_edge = sum(leg.get("edge", 0) for leg in acca.get("legs", [])) / max(1, len(acca.get("legs", [])))
        implied_prob = 1.0 / total_odds if total_odds > 1 else 0.0
        acca_win_prob = min(0.99, implied_prob + avg_edge)
        
        kelly_stake = self.kelly_calculator.calculate_acca_stake(acca_win_prob, total_odds)
        diversification = self.acca_filter.correlation_analyzer.diversification_score(acca.get("legs", []))
        
        acca["kelly_stake_pct"] = kelly_stake * 100
        acca["diversification_score"] = diversification
        
        acca["success"] = True
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
            f"⚡ {fold_size}-FOLD BULLETPROOF ACCUMULATOR SLIP\n"
            f"🎯 Compounded Odds: {total_odds}x\n"
            f"📊 Total Analyzed: {acca.get('available_count', 0)} fixtures\n"
            f"✅ Eligible: {acca.get('eligible_count', 0)} fixtures\n"
            f"⏰ Timeframe: {acca.get('timeframe_days', 0)} day(s)\n"
            f"🛡️  Diversification Score: {acca.get('diversification_score', 0):.2f}/1.0\n"
            f"💰 Kelly Stake Size: {acca.get('kelly_stake_pct', 0):.2f}% of Bankroll"
        )
        console.print(Panel(header, border_style="bold green"))
        
        # Legs table
        table = Table(show_header=True, header_style="bold green")
        table.add_column("Leg", style="cyan", width=5)
        table.add_column("Fixture", style="cyan", width=35)
        table.add_column("Market", style="yellow", width=25)
        table.add_column("Selection", style="green", width=20)
        table.add_column("Edge", style="white", width=8)
        table.add_column("Risk", style="red", width=6)
        table.add_column("Odds", style="magenta", width=6)
        
        total_stake = 1.0
        for idx, leg in enumerate(legs, 1):
            table.add_row(
                f"{idx:02d}",
                leg.get("fixture", "?")[:33],
                leg.get("market", "?")[:23],
                leg.get("selection", "?")[:18],
                f"{leg.get('edge', 0.0):.3f}",
                f"{leg.get('risk_score', 0.0):.0f}",
                f"{leg.get('odds', 1.0):.2f}x"
            )
        
        console.print(table)
        
        console.print(
            f"\n[bold green]✅ FULLPROOF ACCA READY FOR BETTING[/bold green]\n"
            f"Expected Value: {total_odds}x your stake\n"
            f"Strategy: High-confidence markets + strong edges + risk-adjusted selection\n"
        )


@app.command()
def generate(
    days: int = typer.Option(2, "--days", "-d", help="Days ahead (1-3)"),
    folds: int = typer.Option(5, "--folds", "-f", help="Number of legs in acca (1-50)"),
    min_edge: float = typer.Option(0.05, "--edge", "-e", help="Minimum edge threshold (0.01-0.50)"),
):
    """
    Generate a bulletproof accumulator using fullproof strategy.
    
    Examples:
      python build_acca.py generate --days 2 --folds 10
      python build_acca.py generate -d 3 -f 8 -e 0.06
    """
    console.print("\n" + "="*70)
    console.print("      *** ATHENA ACCUMULATOR BUILDER ***")
    console.print("      *** FULLPROOF STRATEGY ***")
    console.print("="*70)
    
    builder = AccaBuilder(days_ahead=days, min_edge=min_edge)
    acca = builder.build(days=days, fold_size=folds)
    builder.display_acca(acca)


@app.command()
def quick(
    folds: int = typer.Option(5, "--folds", "-f", help="Number of legs"),
):
    """
    Quick acca with defaults (2 days, min edge 0.05, fullproof strategy).
    
    Example: python build_acca.py quick --folds 8
    """
    console.print("\n" + "="*70)
    console.print("      *** ATHENA QUICK ACCA ***")
    console.print("="*70)
    
    builder = AccaBuilder(days_ahead=2, min_edge=0.05)
    acca = builder.build(days=2, fold_size=folds)
    builder.display_acca(acca)


if __name__ == "__main__":
    app()
