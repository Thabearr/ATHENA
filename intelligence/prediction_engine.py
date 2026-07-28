"""
prediction_engine.py
This is the layer that actually PRODUCES model_prob for fixture_reasoner.py
(built previously). It is deliberately split into two systems that check
each other, rather than one model expected to do both jobs:

 BASE-RATE MODEL -> pattern memory. Trained on years of structured
                    history (form, xG, rest days, head-to-head...).
                    Consistent and well-tested, but blind to anything
                    that hasn't happened often enough to leave a
                    statistical footprint.

 CONTEXTUAL OVERLAY -> live research reasoning. Reads fresh, one-off,
                       unstructured information for THIS fixture (an
                       injury announced this morning, a sacked manager,
                       a weather forecast) and proposes a bounded,
                       cited nudge to the base rate.

The overlay is capped and required to cite its evidence for the same
reason a human analyst's gut feeling shouldn't override a decade of data
on its own: it can inform the number, not replace it. The size of its
influence also feeds back into how much the downstream reasoning layer
should trust the resulting probability (see discount_sample_size).
"""
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import math

# ---------------------------------------------------------------------
# 1. Evidence the overlay reasons over
# ---------------------------------------------------------------------
SOURCE_TIER_WEIGHTS = {
    "official": 1.0,    # club/league statement, confirmed lineup
    "reported": 0.6,    # credible journalist / established outlet
    "rumor": 0.25,      # unconfirmed, social media, anonymous
}

@dataclass
class SourcedFact:
    description: str
    impact_score: float  # -1.0 to +1.0, effect on the SPECIFIC option being evaluated
    source_tier: str     # "official" / "reported" / "rumor"

# ---------------------------------------------------------------------
# 2. Base-rate model — explicit seam for the trained model
# ---------------------------------------------------------------------
class BaseRateModel:
    """
    Placeholder for whatever trained model performs best on your historical
    data (gradient-boosted trees, a small feed-forward net, etc). Swap
    predict() for a real inference call. Everything downstream only needs:
    - a probability per mutually-exclusive outcome in the market
    - the effective sample size behind that estimate (validation-fold
      size, or a model-specific uncertainty measure)
    Kept as an explicit stub here rather than hidden behind the demo, so
    the seam is obvious.
    """
    def __init__(self, historical_n: int = 800):
        self.historical_n = historical_n

    def predict(self, market_outcomes: List[str]) -> Dict[str, float]:
        # Simple default balanced prior if no historical model is passed
        prob = round(1.0 / len(market_outcomes), 4)
        return {outcome: prob for outcome in market_outcomes}

# ---------------------------------------------------------------------
# 3. Contextual overlay — bounded, cited reasoning on fresh information
# ---------------------------------------------------------------------
def _logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))

def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))

class ContextualOverlay:
    def __init__(self, sensitivity: float = 0.35, max_logit_shift: float = 1.5):
        self.sensitivity = sensitivity
        self.max_logit_shift = max_logit_shift

    def evaluate(self, facts: List[SourcedFact]) -> Tuple[float, List[str]]:
        """Returns (adjustment_in_logit_space, reasoning_trace_lines)."""
        total = 0.0
        lines = []
        for f in facts:
            weight = SOURCE_TIER_WEIGHTS.get(f.source_tier, 0.3)
            contribution = f.impact_score * weight * self.sensitivity
            total += contribution
            lines.append(
                f'"{f.description}" [{f.source_tier}] '
                f'impact {f.impact_score:+.2f} x source-weight {weight:.2f} '
                f'x sensitivity {self.sensitivity:.2f} = {contribution:+.3f} logit'
            )
        capped = max(-self.max_logit_shift, min(self.max_logit_shift, total))
        if abs(capped - total) > 1e-9:
            lines.append(
                f"Raw sum {total:+.3f} exceeds cap of +/-{self.max_logit_shift:.2f} "
                f"logit -> clipped to {capped:+.3f}. A single news cycle cannot "
                f"move the estimate further than this regardless of how it reads."
            )
        return capped, lines

# ---------------------------------------------------------------------
# 4. Fusion + coherence + uncertainty feedback
# ---------------------------------------------------------------------
def fuse(base_prob: float, adjustment_logit: float) -> float:
    """Combine in logit space so the result always stays in (0,1)
    and small adjustments behave close to linearly near 0.5."""
    return _sigmoid(_logit(base_prob) + adjustment_logit)

def renormalize_market(probs: Dict[str, float]) -> Dict[str, float]:
    """After adjusting one outcome, the market's probabilities no longer
    sum to 1. Redistribute proportionally so the set stays coherent —
    outcomes in the same market are still mutually exclusive."""
    total = sum(probs.values())
    if total <= 0:
        return probs
    return {k: v / total for k, v in probs.items()}

def discount_sample_size(n_base: int, adjustment_logit: float, k: float = 1.0) -> int:
    """The overlay shifts the central estimate using judgment, not new
    statistical history — it should never leave the confidence interval
    as tight as pure historical data would justify. The bigger the nudge,
    the more the effective sample size behind the final number is
    discounted, which directly widens the Wilson interval in the
    downstream reasoning layer (fixture_reasoner.py)."""
    return max(1, int(n_base / (1 + k * abs(adjustment_logit))))

# ---------------------------------------------------------------------
# 5. End-to-end demo run
# ---------------------------------------------------------------------
if __name__ == "__main__":
    try:
        from intelligence.fixture_reasoner import FixtureOption, FixtureReasoner
    except ImportError:
        from fixture_reasoner import FixtureOption, FixtureReasoner

    base_rates = {"Home Win": 0.48, "Draw": 0.25, "Away Win": 0.27}
    base_n = 800

    facts = [
        SourcedFact("Home team's first-choice striker ruled out, no like-for-like replacement in the squad",
                    impact_score=-0.55, source_tier="official"),
        SourcedFact("Away manager sacked 3 days ago, interim coach in temporary charge for the first time",
                    impact_score=+0.20, source_tier="reported"),
        SourcedFact("Heavy rain forecast; historically favors the Home team's more direct playing style",
                    impact_score=+0.15, source_tier="reported"),
    ]

    overlay = ContextualOverlay(sensitivity=0.35, max_logit_shift=1.5)
    adjustment_logit, trace = overlay.evaluate(facts)

    print("=== Contextual overlay reasoning trace (Home Win) ===")
    for line in trace:
        print(" -", line)
    print(f"Net adjustment: {adjustment_logit:+.3f} logit\n")

    adjusted_home = fuse(base_rates["Home Win"], adjustment_logit)
    fused = renormalize_market({
        "Home Win": adjusted_home,
        "Draw": base_rates["Draw"],
        "Away Win": base_rates["Away Win"],
    })

    n_effective = discount_sample_size(base_n, adjustment_logit)
    print("=== Fused, coherent market probabilities ===")
    for outcome, p in fused.items():
        print(f"  {outcome}: {p*100:.1f}% (n_effective={n_effective})")
    print()

    fixture = [
        FixtureOption("1X2", "Home Win", model_prob=fused["Home Win"], bookmaker_odds=2.10, n_effective=n_effective),
        FixtureOption("1X2", "Draw", model_prob=fused["Draw"], bookmaker_odds=3.40, n_effective=n_effective),
        FixtureOption("1X2", "Away Win", model_prob=fused["Away Win"], bookmaker_odds=3.60, n_effective=n_effective),
    ]

    reasoner = FixtureReasoner(min_edge_pp=2.0, kelly_fraction_used=1/8)
    print("=== Part 1 reasoning layer, using the fused probabilities ===")
    for v in reasoner.analyze(fixture):
        print(f"[{v.status:9s}] {v.reason}")
        if v.status == "SELECTED":
            print(f"         -> Stake: {v.kelly_stake_pct:.2f}% of bankroll (1/8 Kelly)")
