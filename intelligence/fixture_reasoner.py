"""
fixture_reasoner.py
A decision layer that sits ON TOP of a prediction model.
It does not predict outcomes itself — it takes probabilities the model
already produced for every option on a fixture, and decides:

 1. Which options actually have value (edge vs. the market)
 2. How much of those "value" numbers to trust (confidence discount)
 3. Which one(s) to act on, given that options in the same market
    are mutually exclusive and options across markets can be correlated
 4. WHY it picked what it picked, in plain language, option by option

This is the missing "reasoning between options" layer: instead of
silently taking argmax(model_probability), it produces an auditable trace
for every option on the fixture.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict
import math

from domain.markets import MarketId
from domain.model_status import get_model_status

# ---------------------------------------------------------------------
# 1. Data model
# ---------------------------------------------------------------------
@dataclass
class FixtureOption:
    """One analytical outcome (e.g. 'Home Win', 'Over 2.5')."""
    market: str                  # mutually-exclusive group, e.g. "1X2"
    label: str                   # e.g. "Home Win"
    model_prob: float            # calibrated model probability (0-1)
    bookmaker_odds: Optional[float] = None  # genuine current decimal odds
    n_effective: Optional[int] = None      # effective sample size behind model_prob
    correlation_tag: Optional[str] = None  # cross-market correlation group
    market_id: Optional[MarketId] = None   # exact authority lookup; never inferred

    @property
    def model_fair_odds(self) -> Optional[float]:
        if self.model_prob <= 0:
            return None
        return 1.0 / self.model_prob

@dataclass
class OptionVerdict:
    option: FixtureOption
    fair_prob: Optional[float]
    edge_pp: Optional[float]      # edge in percentage points
    kelly_stake_pct: Optional[float]  # recommended stake, % of bankroll
    ci_low: Optional[float]
    ci_high: Optional[float]
    status: str                  # "SELECTED" / "REJECTED" / "DISCOUNTED"
    reason: str

# ---------------------------------------------------------------------
# 2. De-vig: turn bookmaker odds into fair probabilities
# ---------------------------------------------------------------------
def devig_multiplicative(odds_list: List[float]) -> List[float]:
    """Simple overround removal: normalize implied probabilities to sum to 1."""
    raw = [1.0 / o for o in odds_list]
    total = sum(raw)
    return [r / total for r in raw]

def devig_shin(odds_list: List[float], tol: float = 1e-10) -> List[float]:
    """
    Shin's (1993) method. Models the overround as coming from a proportion
    'z' of insider/informed money rather than spreading it evenly, which is
    a better approximation for markets with a strong favorite-longshot bias.
    Falls back to the multiplicative method if it fails to converge.
    """
    raw = [1.0 / o for o in odds_list]
    total = sum(raw)

    def fair_probs_given_z(z):
        return [
            (math.sqrt(z ** 2 + 4 * (1 - z) * (r ** 2) / total) - z) / (2 * (1 - z))
            for r in raw
        ]

    lo, hi = 0.0, 0.999
    for _ in range(200):
        mid = (lo + hi) / 2
        probs = fair_probs_given_z(mid)
        s = sum(probs)
        if abs(s - 1.0) < tol:
            return probs
        if s > 1.0:
            lo = mid
        else:
            hi = mid
    return devig_multiplicative(odds_list)  # fallback

# ---------------------------------------------------------------------
# 3. Edge and Kelly
# ---------------------------------------------------------------------
def edge_percentage_points(model_prob: float, fair_prob: float) -> float:
    return (model_prob - fair_prob) * 100

def kelly_fraction(model_prob: float, odds: float, fraction: float = 1 / 8) -> float:
    """Fractional Kelly stake as a percentage of bankroll. 0 if no edge."""
    b = odds - 1
    if b <= 0:
        return 0.0
    f_full = (model_prob * odds - 1) / b
    return max(0.0, f_full) * fraction * 100

# ---------------------------------------------------------------------
# 4. Confidence discount (Wilson interval on the model's own probability)
# ---------------------------------------------------------------------
def wilson_interval(p: float, n: Optional[int], z: float = 1.96):
    """
    Returns (low, high) around p. If n is unknown, returns (None, None) —
    the caller should treat that estimate as unverified rather than assume
    it is tight.
    """
    if not n or n <= 0:
        return None, None
    denom = 1 + z ** 2 / n
    center = (p + z ** 2 / (2 * n)) / denom
    margin = (z * math.sqrt((p * (1 - p) / n) + (z ** 2 / (4 * n ** 2)))) / denom
    return max(0.0, center - margin), min(1.0, center + margin)

# ---------------------------------------------------------------------
# 5. The reasoning engine
# ---------------------------------------------------------------------
class FixtureReasoner:
    def __init__(
        self,
        min_edge_pp: float = 2.0,
        kelly_fraction_used: float = 1 / 8,
        devig_method: str = "shin"
    ):
        self.min_edge_pp = min_edge_pp
        self.kelly_fraction_used = kelly_fraction_used
        self.devig_method = devig_method

    def _devig(self, odds_list: List[float]) -> List[float]:
        if self.devig_method == "shin":
            return devig_shin(odds_list)
        return devig_multiplicative(odds_list)

    def analyze(self, options: List[FixtureOption]) -> List[OptionVerdict]:
        verdicts: List[OptionVerdict] = []
        
        # Work market by market, since outcomes within a market are
        # mutually exclusive (only one can win) and must be de-vigged together.
        markets: Dict[str, List[FixtureOption]] = {}
        for opt in options:
            markets.setdefault(opt.market, []).append(opt)

        for market, opts in markets.items():
            authority_proven = all(
                type(option.market_id) is MarketId
                and get_model_status(option.market_id).pricing_authorized
                and get_model_status(option.market_id).selectable
                for option in opts
            )
            if not authority_proven:
                for opt in opts:
                    lo, hi = wilson_interval(opt.model_prob, opt.n_effective)
                    verdicts.append(OptionVerdict(
                        option=opt,
                        fair_prob=None,
                        edge_pp=None,
                        kelly_stake_pct=None,
                        ci_low=lo,
                        ci_high=hi,
                        status="ANALYTICAL_CANDIDATE",
                        reason=(
                            f"{opt.label}: analytical probability is available, "
                            "but exact registry pricing and selection authority "
                            "are both absent. Supplied odds cannot expand authority."
                        ),
                    ))
                continue
            if any(
                o.bookmaker_odds is None
                or o.bookmaker_odds <= 1.0
                for o in opts
            ):
                for opt in opts:
                    lo, hi = wilson_interval(opt.model_prob, opt.n_effective)
                    verdicts.append(OptionVerdict(
                        option=opt,
                        fair_prob=None,
                        edge_pp=None,
                        kelly_stake_pct=None,
                        ci_low=lo,
                        ci_high=hi,
                        status="ANALYTICAL_CANDIDATE",
                        reason=(
                            f"{opt.label}: model probability is available, but "
                            "pricing validation is pending because a complete "
                            "genuine current bookmaker market was not provided."
                        ),
                    ))
                continue

            fair_probs = self._devig(
                [o.bookmaker_odds for o in opts]
            )
            market_verdicts = []

            for opt, fair_p in zip(opts, fair_probs):
                edge = edge_percentage_points(opt.model_prob, fair_p)
                stake = kelly_fraction(
                    opt.model_prob,
                    opt.bookmaker_odds,
                    self.kelly_fraction_used,
                )
                lo, hi = wilson_interval(opt.model_prob, opt.n_effective)

                # Discount: if we can't verify the probability's confidence
                # interval, or the interval crosses break-even, don't act on
                # the raw edge number.
                discounted = False
                if lo is not None:
                    breakeven = fair_p
                    if lo < breakeven:
                        discounted = True

                if edge < self.min_edge_pp:
                    status = "REJECTED"
                    reason = (
                        f"{opt.label}: model {opt.model_prob*100:.1f}% vs fair "
                        f"{fair_p*100:.1f}% -> edge {edge:+.1f}pp, below the "
                        f"{self.min_edge_pp:.1f}pp minimum. No action."
                    )
                elif discounted:
                    status = "DISCOUNTED"
                    reason = (
                        f"{opt.label}: raw edge {edge:+.1f}pp looks positive, but the "
                        f"confidence interval on the model probability "
                        f"({lo*100:.1f}%-{hi*100:.1f}%, n={opt.n_effective}) "
                        f"overlaps the break-even point ({fair_p*100:.1f}%). "
                        f"Treated as no-edge until more data tightens the estimate."
                    )
                    stake = 0.0
                else:
                    status = "CANDIDATE"
                    reason = (
                        f"{opt.label}: model {opt.model_prob*100:.1f}% vs fair "
                        f"{fair_p*100:.1f}% -> edge {edge:+.1f}pp, clears the "
                        f"{self.min_edge_pp:.1f}pp threshold."
                    )

                market_verdicts.append(OptionVerdict(
                    option=opt, fair_prob=fair_p, edge_pp=edge,
                    kelly_stake_pct=stake, ci_low=lo, ci_high=hi,
                    status=status, reason=reason,
                ))

            # Within this market, only one outcome can happen — so at most
            # one CANDIDATE gets promoted to SELECTED (the highest edge).
            candidates = [v for v in market_verdicts if v.status == "CANDIDATE"]
            if candidates:
                best = max(candidates, key=lambda v: v.edge_pp)
                for v in market_verdicts:
                    if v is best:
                        v.status = "SELECTED"
                        v.reason += (
                            f" Selected over the other option(s) in '{market}' "
                            f"because it carries the highest edge in this market."
                        )
                    elif v.status == "CANDIDATE":
                        v.status = "REJECTED"
                        v.reason += (
                            f" Passed over in favor of '{best.option.label}', "
                            f"which had higher edge ({best.edge_pp:+.1f}pp vs "
                            f"{v.edge_pp:+.1f}pp) in the same market."
                        )

            verdicts.extend(market_verdicts)

        self._flag_correlation(verdicts)
        return verdicts

    def _flag_correlation(self, verdicts: List[OptionVerdict]):
        """If two SELECTED picks share a correlation tag, warn rather than
        silently stake both at full size — they are not independent bets."""
        selected = [v for v in verdicts if v.status == "SELECTED"]
        tags: Dict[str, List[OptionVerdict]] = {}
        for v in selected:
            tag = v.option.correlation_tag
            if tag:
                tags.setdefault(tag, []).append(v)
        for tag, group in tags.items():
            if len(group) > 1:
                names = ", ".join(g.option.label for g in group)
                for v in group:
                    v.reason += (
                        f" CORRELATION WARNING: shares tag '{tag}' with {names}. "
                        f"These are not independent -- treat combined stake as "
                        f"one correlated position, not two separate edges."
                    )

if __name__ == "__main__":
    fixture = [
        FixtureOption("1X2", "Home Win", model_prob=0.53, bookmaker_odds=2.10, n_effective=800),
        FixtureOption("1X2", "Draw", model_prob=0.22, bookmaker_odds=3.40, n_effective=800),
        FixtureOption("1X2", "Away Win", model_prob=0.25, bookmaker_odds=3.60, n_effective=800),

        FixtureOption("Over/Under 2.5", "Over 2.5", model_prob=0.58, bookmaker_odds=1.90,
                      n_effective=500, correlation_tag="goals_high"),
        FixtureOption("Over/Under 2.5", "Under 2.5", model_prob=0.42, bookmaker_odds=2.00,
                      n_effective=500),

        FixtureOption("BTTS", "BTTS Yes", model_prob=0.57, bookmaker_odds=1.85,
                      n_effective=900, correlation_tag="goals_high"),
        FixtureOption("BTTS", "BTTS No", model_prob=0.43, bookmaker_odds=2.05, n_effective=900),
    ]
    reasoner = FixtureReasoner(min_edge_pp=2.0, kelly_fraction_used=1/8, devig_method="shin")
    results = reasoner.analyze(fixture)
    for market in ["1X2", "Over/Under 2.5", "BTTS"]:
        print(f"\n=== {market} ===")
        for v in results:
            if v.option.market != market:
                continue
            print(f"[{v.status:10s}] {v.reason}")
            if v.status == "SELECTED":
                print(f"         -> Stake: {v.kelly_stake_pct:.2f}% of bankroll (1/8 Kelly)")
