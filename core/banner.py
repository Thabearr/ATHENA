from rich.console import Console

console = Console()

def show_banner():
    console.print(
        """
[bold cyan]
╔════════════════════════════════════════════╗
║                 ATHENA                     ║
║ AI Tactical Football Analytics Engine      ║
║                Version 0.1                 ║
╚════════════════════════════════════════════╝
[/bold cyan]
"""
    )
