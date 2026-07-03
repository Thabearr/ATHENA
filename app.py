from rich.console import Console
from config.settings import settings

console = Console()

console.print("[bold cyan]🦉 ATHENA v0.1[/bold cyan]")
console.print("AI Tactical Heuristic Engine for Networked Analytics\n")

console.print(f"Debug Mode : {settings.DEBUG}")
console.print(f"Log Level  : {settings.LOG_LEVEL}")
console.print(f"Database   : {settings.DATABASE_URL}")

console.print("\n[green]✓ Configuration Loaded Successfully[/green]")
