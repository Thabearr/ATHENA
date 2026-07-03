def run(self):

    show_banner()

    self.logger.info("ATHENA started.")

    self.console.print("[green]✓ Configuration Loaded[/green]")
    self.console.print(f"Debug: {settings.DEBUG}")

    database = Database()
    database.initialize()

    self.logger.info("Database initialized.")

    checker = HealthCheck()
    health = checker.run()

    self.console.print("\n[bold]System Health[/bold]")

    for component, status in health.items():
        icon = "🟢" if status else "🔴"
        self.console.print(f"{icon} {component}")

    self.logger.success("Startup completed successfully.")
