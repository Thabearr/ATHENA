from database.database import Database

from rich.console import Console

from config.settings import settings
from core.banner import show_banner
from core.health import HealthCheck
from core.logger import get_logger


class AthenaApplication:

    def __init__(self):

        self.console = Console()
        self.logger = get_logger()

    def run(self):

        show_banner()

        self.logger.info("ATHENA started.")

        self.console.print("[green]✓ Configuration Loaded[/green]")
        self.console.print(f"Debug: {settings.DEBUG}")

        checker = HealthCheck()

        health = checker.run()

        self.console.print("\n[bold]System Health[/bold]")

        for component, status in health.items():

            icon = "🟢" if status else "🔴"

            self.console.print(f"{icon} {component}")

        self.logger.info("Startup completed successfully.")
