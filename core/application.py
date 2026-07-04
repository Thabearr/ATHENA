from rich.console import Console

from config.settings import settings
from core.banner import show_banner
from core.health import HealthCheck
from core.logger import get_logger

from database.database import Database
from services.live_fixture_loader import LiveFixtureLoader


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
            fixtures = loader.load()

            if fixtures:

                self.console.print("\n[bold green]Today's Fixtures[/bold green]")
                self.console.print("-" * 60)

                for fixture in fixtures[:10]:
                    self.console.print(
                        f"{fixture.home_team} vs {fixture.away_team} | {fixture.league}"
                    )

                self.console.print(
                    f"\n[cyan]Total Fixtures Found:[/cyan] {len(fixtures)}"
                )

            else:
                self.console.print("[yellow]No fixtures found today.[/yellow]")

        except Exception as e:
            self.console.print(f"[red]Fixture loading failed:[/red] {e}")
            self.logger.error(str(e))

        self.logger.success("Startup completed successfully.")
