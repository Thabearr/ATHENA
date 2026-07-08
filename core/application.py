from rich.console import Console

from config.settings import settings
from core.banner import show_banner
from core.health import HealthCheck
from core.logger import get_logger

from database.database import Database
from services.live_fixture_loader import LiveFixtureLoader
from services.prediction_service import PredictionService
from engine.report_generator import ReportGenerator


class AthenaApplication:

    def __init__(self):
        self.console = Console()
        self.logger = get_logger()

    def run(self):

        # Show startup banner
        show_banner()

        self.logger.info("ATHENA started.")

        # Configuration
        self.console.print("[green]✓ Configuration Loaded[/green]")
        self.console.print(f"Debug: {settings.DEBUG}")

        # Initialize database
        database = Database()
        database.initialize()

        self.logger.info("Database initialized.")

        # Health check
        checker = HealthCheck()
        health = checker.run()

        self.console.print("\n[bold]System Health[/bold]")

        for component, status in health.items():
            icon = "🟢" if status else "🔴"
            self.console.print(f"{icon} {component}")

        # Load today's fixtures
        self.console.print("\n[bold cyan]Loading Today's Fixtures...[/bold cyan]")

        try:
            loader = LiveFixtureLoader()
            fixtures = loader.load_today()

            if fixtures:

                self.console.print(
                    f"\n[cyan]Downloaded and stored {len(fixtures)} fixtures.[/cyan]"
                )

                self.console.print("-" * 60)

                # Display first 10 fixtures
                for fixture in fixtures[:10]:

                    home = fixture["teams"]["home"]["name"]
                    away = fixture["teams"]["away"]["name"]
                    league = fixture["league"]["name"]

                    self.console.print(
                        f"{home} vs {away} | {league}"
                    )

                self.console.print(
                    f"\n[cyan]Total Fixtures Found:[/cyan] {len(fixtures)}"
                )

                # ==========================================
                # ATHENA Prediction Engine Test
                # ==========================================

                self.console.print(
                    "\n[bold green]Generating Prediction...[/bold green]"
                )

                prediction_service = PredictionService()
                report = ReportGenerator()

                prediction = prediction_service.predict(fixtures[0])

                report.generate(prediction)

            else:

                self.console.print(
                    "[yellow]No fixtures found today.[/yellow]"
                )

       import traceback

except Exception as e:
    self.console.print(f"[red]Fixture loading failed:[/red] {repr(e)}")
    traceback.print_exc()
    self.logger.exception("Fixture loading failed")
