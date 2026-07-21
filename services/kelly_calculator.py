import math

class KellyCalculator:
    """
    Implements optimal stake sizing based on the Kelly Criterion.
    Formula: f = (bp - q) / b
    where:
    f = fraction of bankroll to wager
    b = decimal odds - 1 (the fractional odds)
    p = probability of winning
    q = probability of losing (1 - p)
    """

    def __init__(self, safety_multiplier=0.25, max_exposure=0.05):
        self.safety_multiplier = safety_multiplier  # 0.25 = Quarter Kelly
        self.max_exposure = max_exposure  # Never exceed 5% bankroll per acca

    def kelly_fraction(self, probability: float, decimal_odds: float) -> float:
        """Calculate the raw Kelly fraction for a single bet or accumulator."""
        if decimal_odds <= 1.0 or probability <= 0.0:
            return 0.0

        b = decimal_odds - 1.0
        p = probability
        q = 1.0 - p

        f = (b * p - q) / b
        return max(0.0, f)  # Never suggest a negative bet (laying)

    def apply_safety_multiplier(self, fraction: float) -> float:
        """Apply the safety multiplier (e.g., Quarter Kelly)."""
        return fraction * self.safety_multiplier

    def bankroll_protection(self, fraction: float) -> float:
        """Cap the fraction at the maximum allowed exposure."""
        return min(fraction, self.max_exposure)

    def calculate_acca_stake(self, acca_win_probability: float, acca_odds: float) -> float:
        """
        Calculate the safe stake size for an accumulator.
        """
        raw_kelly = self.kelly_fraction(acca_win_probability, acca_odds)
        safe_kelly = self.apply_safety_multiplier(raw_kelly)
        final_stake = self.bankroll_protection(safe_kelly)
        
        return final_stake
