import os
import json
import random
from typing import Dict, Tuple
from loguru import logger
from build_acca import AccaBuilder

class ModelEvolver:
    """
    Automated optimization loop for ATHENA.
    Runs backtests, tweaks parameters based on failures, and saves the most profitable configuration.
    """
    def __init__(self, db_path: str = "database/athena.db", config_path: str = "config/model_weights.json"):
        self.db_path = db_path
        self.config_path = config_path
        self.builder = AccaBuilder()
        
    def load_weights(self) -> dict:
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as f:
                return json.load(f)
        return {"MARKET_BASELINES": {}}
        
    def save_weights(self, weights: dict):
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(weights, f, indent=4)
            
    def run_backtest_eval(self, days: int = 1, folds: int = 50) -> Tuple[float, float, float, int, int]:
        """Runs a backtest on historical matches and returns (fitness, strike_rate, roi, total_legs, losses)"""
        from intelligence.backtester import Backtester
        backtester = Backtester(self.db_path)
        
        # Test both strict and value-oriented modes
        res = backtester.run_backtest(days_ago=days, fold_size=folds, strict=False)
        if not res.get("success") or not res.get("legs"):
            res = backtester.run_backtest(days_ago=days, fold_size=folds, strict=True)
            
        if not res.get("success") or not res.get("legs"):
            return 0.0, 0.0, 0.0, 0, 0
            
        wins = res.get("wins", 0)
        losses = res.get("losses", 0)
        voids = res.get("voids", 0)
        legs = res.get("legs", [])
        
        total_return = 0.0
        for leg in legs:
            if leg.get("grade") == "WIN":
                prob = leg.get("prob", 0.5)
                odds = max(1.01, 0.95 / max(0.01, prob))
                total_return += odds
                
        valid_legs = wins + losses
        strike_rate = (wins / valid_legs * 100) if valid_legs > 0 else 0.0
        roi = ((total_return - valid_legs) / valid_legs * 100) if valid_legs > 0 else 0.0
        
        fitness = (strike_rate * 0.4) + (roi * 0.6)
        return fitness, strike_rate, roi, len(legs), losses

    def mutate_weights(self, weights: dict) -> dict:
        """Mutates market baselines and risk thresholds to explore the parameter space."""
        import copy
        new_weights = copy.deepcopy(weights)
        
        # Mutate baselines
        baselines = new_weights.get("MARKET_BASELINES", {})
        for key in baselines:
            if random.random() < 0.35: # 35% chance to mutate a specific market
                delta = random.uniform(-0.05, 0.05)
                baselines[key] = round(max(0.01, min(0.99, baselines[key] + delta)), 3)
                
        # Mutate edge & risk thresholds
        if random.random() < 0.25:
            new_weights["edge_threshold"] = round(max(0.02, min(0.12, new_weights.get("edge_threshold", 0.05) + random.uniform(-0.01, 0.01))), 3)
        if random.random() < 0.25:
            new_weights["risk_threshold"] = int(max(40, min(85, new_weights.get("risk_threshold", 65) + random.choice([-5, -2, 2, 5]))))

        new_weights["MARKET_BASELINES"] = baselines
        return new_weights

    def evolve(self, generations: int = 5, days_to_test: int = 1):
        """Run the genetic algorithm optimization."""
        logger.info(f"🧬 Starting ATHENA Evolution Engine over {generations} generations...")
        best_weights = self.load_weights()
        best_fitness, best_strike, best_roi, total_legs, _ = self.run_backtest_eval(days=days_to_test, folds=50)
        
        logger.info(f"Baseline Fitness: {best_fitness:.2f} (Strike: {best_strike:.1f}%, ROI: {best_roi:.1f}%) in {total_legs} legs")
        
        for gen in range(1, generations + 1):
            candidate_weights = self.mutate_weights(best_weights)
            self.save_weights(candidate_weights) # Save so the model uses them
            
            fitness, strike_rate, roi, total, losses = self.run_backtest_eval(days=days_to_test, folds=50)
            
            if fitness > best_fitness and total >= 5:
                logger.info(f"✅ Gen {gen}: Improvement found! Fitness {best_fitness:.2f} -> {fitness:.2f} (Strike: {strike_rate:.1f}%, ROI: {roi:.1f}%)")
                best_weights = candidate_weights
                best_fitness = fitness
            else:
                logger.info(f"❌ Gen {gen}: No improvement (Fitness: {fitness:.2f}). Reverting...")
                
        # Save best at the end
        self.save_weights(best_weights)
        logger.info(f"🏆 Evolution complete. Best Fitness: {best_fitness:.2f}")

if __name__ == "__main__":
    evolver = ModelEvolver()
    evolver.evolve(generations=5)
