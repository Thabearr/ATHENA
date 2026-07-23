import sys
import os
import typer
from loguru import logger

# Add root to pythonpath
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from intelligence.evolver import ModelEvolver

app = typer.Typer(help="ATHENA Evolution Engine CLI")

@app.command()
def start(
    generations: int = typer.Option(10, "--generations", "-g", help="Number of evolutionary generations"),
    days: int = typer.Option(1, "--days", "-d", help="Days into the past to use for testing"),
):
    """
    Run the genetic algorithm to optimize ATHENA's model weights based on historical data.
    """
    logger.info(f"🚀 Initializing Evolution Engine. Target: {days} days ago | Generations: {generations}")
    evolver = ModelEvolver()
    evolver.evolve(generations=generations, days_to_test=days)
    logger.success("✅ Evolution complete. Weights updated in config/model_weights.json")

if __name__ == "__main__":
    app()
