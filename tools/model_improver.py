#!/usr/bin/env python3
import sys
import os
from rich.console import Console
from rich.table import Table

# Add parent directory to path to allow importing project modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.database import Database
from services.prediction_tracker import PredictionTracker

console = Console()

class ModelImprover:
    def __init__(self):
        self.db = Database()
        self.tracker = PredictionTracker(self.db)
        
    def analyze_weaknesses(self):
        metrics = self.tracker.get_accuracy_metrics()
        
        console.print("[bold cyan]🔍 ATHENA Model Improver & Diagnostics[/bold cyan]")
        console.print(f"Total Predictions Evaluated: {metrics['total']}")
        
        if metrics['total'] == 0:
            console.print("Not enough data to analyze weaknesses. Run backtester first.")
            return
            
        win_rate = (metrics['wins'] / metrics['total']) * 100
        console.print(f"Overall Accuracy: {win_rate:.1f}%")
        
        console.print("\n[bold]📊 Performance By Market[/bold]")
        market_table = Table(show_header=True, header_style="bold magenta")
        market_table.add_column("Market")
        market_table.add_column("Total Picks")
        market_table.add_column("Accuracy")
        market_table.add_column("Status")
        
        for market, stats in metrics['by_market'].items():
            acc = (stats['wins'] / stats['total']) * 100
            
            status = "[green]Excellent[/green]"
            if acc < 50:
                status = "[red]Failing[/red]"
            elif acc < 65:
                status = "[yellow]Needs Improvement[/yellow]"
                
            market_table.add_row(market, str(stats['total']), f"{acc:.1f}%", status)
            
        console.print(market_table)
        
        console.print("\n[bold]📈 Performance By Edge Band[/bold]")
        edge_table = Table(show_header=True, header_style="bold blue")
        edge_table.add_column("Edge Band")
        edge_table.add_column("Total Picks")
        edge_table.add_column("Accuracy")
        
        for edge, stats in metrics['by_edge'].items():
            acc = (stats['wins'] / stats['total']) * 100
            edge_table.add_row(edge, str(stats['total']), f"{acc:.1f}%")
            
        console.print(edge_table)
        
        # Recommendations
        console.print("\n[bold yellow]💡 Optimization Recommendations[/bold yellow]")
        for market, stats in metrics['by_market'].items():
            acc = (stats['wins'] / stats['total']) * 100
            if acc < 60 and stats['total'] > 5:
                console.print(f"• Decrease confidence multiplier for [bold]{market}[/bold] or adjust risk threshold.")
                
        console.print("• [green]Keep edge threshold > 0.10 for maximum accuracy.[/green]")

if __name__ == "__main__":
    improver = ModelImprover()
    improver.analyze_weaknesses()
