"""Push/split-aware market settlement derived from a normalized ScoreMatrix.

This module adds no new football model. It partitions an already-constructed
regulation-time score matrix into exact Draw No Bet and Asian Handicap
settlement states. Pricing, selection, staking, and BET authority are outside
this boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from domain.score_matrix import ScoreMatrix


SETTLEMENT_SUM_TOLERANCE = 1e-12
_DNB_METHOD = "normalized_score_matrix_draw_no_bet_settlement"
_AH_METHOD = "normalized_score_matrix_asian_handicap_settlement"


def _side(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("side must be HOME or AWAY")
    normalized = value.strip().upper()
    if normalized not in {"HOME", "AWAY"}:
        raise ValueError("side must be HOME or AWAY")
    return normalized


def _quarter_line(value: Any) -> tuple[float, int]:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError("line must be a finite numeric quarter-goal line")
    line = float(value)
    quarter_units = line * 4.0
    nearest = round(quarter_units)
    if quarter_units != float(nearest):
        raise ValueError("Asian Handicap line must be an exact multiple of 0.25")
    return nearest / 4.0, int(nearest)


def _quarter_components(line: float, quarter_units: int) -> tuple[float, ...]:
    if quarter_units % 2 == 0:
        return (line,)
    lower = (quarter_units - 1) / 4.0
    upper = (quarter_units + 1) / 4.0
    return (lower, upper)


def _decimal_odds(value: Any) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 1.0
    ):
        raise ValueError("decimal_odds must be a finite number at least 1.0")
    return float(value)


def _probability(value: Any, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
    ):
        raise ValueError(f"{field} must be a finite probability in [0, 1]")
    return float(value)


@dataclass(frozen=True)
class SettlementProbabilities:
    """Probability mass for sportsbook settlement outcomes of one selection."""

    full_win: float
    half_win: float
    push: float
    half_loss: float
    full_loss: float
    method: str
    side: str
    line: float | None = None
    component_lines: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        values = {
            "full_win": _probability(self.full_win, "full_win"),
            "half_win": _probability(self.half_win, "half_win"),
            "push": _probability(self.push, "push"),
            "half_loss": _probability(self.half_loss, "half_loss"),
            "full_loss": _probability(self.full_loss, "full_loss"),
        }
        for field, value in values.items():
            object.__setattr__(self, field, value)

        total = math.fsum(values.values())
        if not math.isclose(
            total,
            1.0,
            rel_tol=0.0,
            abs_tol=SETTLEMENT_SUM_TOLERANCE,
        ):
            raise ValueError(
                "settlement probabilities must partition the normalized matrix"
            )

        normalized_side = _side(self.side)
        object.__setattr__(self, "side", normalized_side)

        if not isinstance(self.method, str) or not self.method.strip():
            raise ValueError("method must be a non-empty string")
        object.__setattr__(self, "method", self.method.strip())

        components = tuple(self.component_lines)
        if self.line is None:
            if components:
                raise ValueError("component_lines require an explicit handicap line")
        else:
            canonical_line, quarter_units = _quarter_line(self.line)
            object.__setattr__(self, "line", canonical_line)
            canonical_components = tuple(_quarter_line(item)[0] for item in components)
            expected_components = _quarter_components(canonical_line, quarter_units)
            if canonical_components != expected_components:
                raise ValueError(
                    "component_lines do not exactly match the canonical handicap line"
                )
            object.__setattr__(self, "component_lines", canonical_components)

    @property
    def total_probability(self) -> float:
        return math.fsum(
            (
                self.full_win,
                self.half_win,
                self.push,
                self.half_loss,
                self.full_loss,
            )
        )

    @property
    def effective_win_mass(self) -> float:
        """Expected fraction of unit stake exposed to a winning settlement."""
        return self.full_win + 0.5 * self.half_win

    @property
    def effective_loss_mass(self) -> float:
        """Expected fraction of unit stake exposed to a losing settlement."""
        return self.full_loss + 0.5 * self.half_loss

    @property
    def neutral_stake_mass(self) -> float:
        """Expected fraction of unit stake returned without profit or loss."""
        return self.push + 0.5 * self.half_win + 0.5 * self.half_loss

    @property
    def active_stake_mass(self) -> float:
        """Expected fraction of stake exposed to win or loss rather than return."""
        return self.effective_win_mass + self.effective_loss_mass

    @property
    def break_even_probability(self) -> float | None:
        """Equivalent win probability after neutral stake portions are removed."""
        active = self.active_stake_mass
        if active <= 0.0:
            return None
        return self.effective_win_mass / active

    @property
    def fair_decimal_odds(self) -> float | None:
        """Return zero-margin decimal odds under this settlement distribution."""
        probability = self.break_even_probability
        if probability is None or probability <= 0.0:
            return None
        return 1.0 / probability

    def expected_profit(self, decimal_odds: float) -> float:
        """Return expected profit for one unit staked at the supplied decimal odds."""
        odds = _decimal_odds(decimal_odds)
        return (
            self.full_win * (odds - 1.0)
            + self.half_win * 0.5 * (odds - 1.0)
            - self.half_loss * 0.5
            - self.full_loss
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "full_win": self.full_win,
            "half_win": self.half_win,
            "push": self.push,
            "half_loss": self.half_loss,
            "full_loss": self.full_loss,
            "total_probability": self.total_probability,
            "effective_win_mass": self.effective_win_mass,
            "effective_loss_mass": self.effective_loss_mass,
            "neutral_stake_mass": self.neutral_stake_mass,
            "active_stake_mass": self.active_stake_mass,
            "break_even_probability": self.break_even_probability,
            "fair_decimal_odds": self.fair_decimal_odds,
            "method": self.method,
            "side": self.side,
            "line": self.line,
            "component_lines": list(self.component_lines),
        }


def draw_no_bet_settlement(
    score_matrix: ScoreMatrix,
    side: str,
) -> SettlementProbabilities:
    """Partition one DNB selection into win, draw-push, and loss probability."""
    if not isinstance(score_matrix, ScoreMatrix):
        raise TypeError("score_matrix must be a ScoreMatrix")
    normalized_side = _side(side)
    if normalized_side == "HOME":
        win = score_matrix.home_win
        loss = score_matrix.away_win
    else:
        win = score_matrix.away_win
        loss = score_matrix.home_win
    return SettlementProbabilities(
        full_win=win,
        half_win=0.0,
        push=score_matrix.draw,
        half_loss=0.0,
        full_loss=loss,
        method=_DNB_METHOD,
        side=normalized_side,
    )


def _component_outcome(
    home_goals: int,
    away_goals: int,
    side: str,
    line: float,
) -> str:
    selected_margin = (
        home_goals - away_goals
        if side == "HOME"
        else away_goals - home_goals
    )
    adjusted_margin = selected_margin + line
    if adjusted_margin > 0.0:
        return "WIN"
    if adjusted_margin < 0.0:
        return "LOSS"
    return "PUSH"


def asian_handicap_settlement(
    score_matrix: ScoreMatrix,
    side: str,
    line: float,
) -> SettlementProbabilities:
    """Partition standard integer/half/quarter Asian Handicap settlement states."""
    if not isinstance(score_matrix, ScoreMatrix):
        raise TypeError("score_matrix must be a ScoreMatrix")
    normalized_side = _side(side)
    canonical_line, quarter_units = _quarter_line(line)
    components = _quarter_components(canonical_line, quarter_units)

    masses: dict[str, list[float]] = {
        "full_win": [],
        "half_win": [],
        "push": [],
        "half_loss": [],
        "full_loss": [],
    }

    for (home_goals, away_goals), probability in score_matrix.probabilities.items():
        outcomes = tuple(
            _component_outcome(
                home_goals,
                away_goals,
                normalized_side,
                component,
            )
            for component in components
        )

        if len(outcomes) == 1:
            state = {
                "WIN": "full_win",
                "PUSH": "push",
                "LOSS": "full_loss",
            }[outcomes[0]]
        elif outcomes == ("WIN", "WIN"):
            state = "full_win"
        elif set(outcomes) == {"WIN", "PUSH"}:
            state = "half_win"
        elif outcomes == ("PUSH", "PUSH"):
            state = "push"
        elif set(outcomes) == {"LOSS", "PUSH"}:
            state = "half_loss"
        elif outcomes == ("LOSS", "LOSS"):
            state = "full_loss"
        elif set(outcomes) == {"WIN", "LOSS"}:
            raise RuntimeError(
                "adjacent quarter-line components produced an impossible "
                "simultaneous win/loss settlement"
            )
        else:
            raise RuntimeError("unrecognized Asian Handicap component settlement")
        masses[state].append(probability)

    return SettlementProbabilities(
        full_win=math.fsum(masses["full_win"]),
        half_win=math.fsum(masses["half_win"]),
        push=math.fsum(masses["push"]),
        half_loss=math.fsum(masses["half_loss"]),
        full_loss=math.fsum(masses["full_loss"]),
        method=_AH_METHOD,
        side=normalized_side,
        line=canonical_line,
        component_lines=components,
    )


__all__ = [
    "SETTLEMENT_SUM_TOLERANCE",
    "SettlementProbabilities",
    "asian_handicap_settlement",
    "draw_no_bet_settlement",
]
