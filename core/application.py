from rich.console import Console
import traceback

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

        try:

            show_banner()

            self.logger.info("ATHENA started.")

            self.console.print(
                "[green]✓ Configuration Loaded[/green]"
            )

            self.console.print(
                f"Debug: {settings.DEBUG}"
            )

            database = Database()

            database.initialize()

            self.console.print(
                "[green]✓ Database initialized successfully.[/green]"
            )

            checker = HealthCheck()

            health = checker.run()

            self.console.print(
                "\n[bold]System Health[/bold]"
            )

            for component, status in health.items():

                icon = "🟢" if status else "🔴"

                self.console.print(
                    f"{icon} {component}"
                )

            self.console.print(
                "\n[bold cyan]Loading Today's Fixtures...[/bold cyan]"
            )

            loader = LiveFixtureLoader()

            fixtures = loader.load_today()

            if not fixtures:

                self.console.print(
                    "[yellow]No fixtures found today.[/yellow]"
                )

                return

            self.console.print(

                f"\n[cyan]Downloaded and stored {len(fixtures)} fixtures.[/cyan]"

            )

            self.console.print("-" * 60)

            for fixture in fixtures[:10]:

                self.console.print(

                    f"{fixture['teams']['home']['name']} vs "

                    f"{fixture['teams']['away']['name']} | "

                    f"{fixture['league']['name']}"

                )

            self.console.print(

                f"\n[cyan]Total Fixtures Found:[/cyan] {len(fixtures)}"

            )

            self.console.print(

                "\n[yellow]Standings update temporarily disabled while stabilizing API networking.[/yellow]"

            )

            self.console.print(

                "\n[bold green]Generating Prediction...[/bold green]"

            )

            prediction_service = PredictionService()

            report = ReportGenerator()

            prediction = prediction_service.predict(

                fixtures[0]

            )

            report.generate(prediction)

        except Exception as e:

            self.console.print(

                f"[red]Startup failed:[/red] {e}"

            )

            traceback.print_exc()

            self.logger.exception(e)
