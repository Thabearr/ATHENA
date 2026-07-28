"""Normalized independent-Poisson football score distribution.

The matrix expands adaptively until the joint probability mass outside the
retained rectangle is below the requested tolerance. Derived market
probabilities are calculated only from the normalized matrix.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Callable, Dict, Mapping, Optional, Tuple


DEFAULT_TAIL_TOLERANCE = 1e-10
NORMALIZATION_METHOD = "divide_by_retained_mass"


def _validate_finite_non_negative(value: float, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise ValueError(f"{field} must be a finite non-negative number")
    return float(value)


def _validate_tolerance(value: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 < float(value) < 1.0
    ):
        raise ValueError("tail_tolerance must be finite and between 0 and 1")
    return float(value)


def poisson_probability(goals: int, expected_goals: float) -> float:
    """Return an independent Poisson mass for an exact goal count."""
    expected = _validate_finite_non_negative(
        expected_goals,
        "expected_goals",
    )
    if isinstance(goals, bool) or not isinstance(goals, int) or goals < 0:
        raise ValueError("goals must be a non-negative integer")
    if expected == 0.0:
        return 1.0 if goals == 0 else 0.0
    return math.exp(
        -expected + goals * math.log(expected) - math.lgamma(goals + 1)
    )


def _expand_poisson_marginal(
    expected_goals: float,
    target_tail: float,
    *,
    maximum_goal_index: int,
) -> list[float]:
    probabilities = [poisson_probability(0, expected_goals)]
    retained = probabilities[0]
    while max(0.0, 1.0 - retained) > target_tail:
        next_goal = len(probabilities)
        if next_goal > maximum_goal_index:
            raise RuntimeError(
                "Poisson goal range could not meet the requested tail "
                f"tolerance by goal index {maximum_goal_index}"
            )
        next_probability = poisson_probability(next_goal, expected_goals)
        probabilities.append(next_probability)
        retained = math.fsum(probabilities)
    return probabilities


@dataclass(frozen=True)
class ScoreMatrix:
    home_expected_goals: float
    away_expected_goals: float
    probabilities: Mapping[Tuple[int, int], float]
    raw_probabilities: Mapping[Tuple[int, int], float]
    max_home_goal: int
    max_away_goal: int
    retained_mass_before_normalization: float
    omitted_tail_mass: float
    tail_tolerance: float
    normalization_method: str = NORMALIZATION_METHOD

    def probability(self, home_goals: int, away_goals: int) -> float:
        score = (home_goals, away_goals)
        if score not in self.probabilities:
            raise KeyError(
                f"Scoreline {score} is outside the retained matrix; "
                "its probability was not invented."
            )
        return self.probabilities[score]

    def raw_probability(self, home_goals: int, away_goals: int) -> float:
        score = (home_goals, away_goals)
        if score not in self.raw_probabilities:
            raise KeyError(
                f"Scoreline {score} is outside the retained matrix; "
                "its probability was not invented."
            )
        return self.raw_probabilities[score]

    def sum_where(self, predicate: Callable[[int, int], bool]) -> float:
        return math.fsum(
            probability
            for (home_goals, away_goals), probability
            in self.probabilities.items()
            if predicate(home_goals, away_goals)
        )

    @property
    def home_win(self) -> float:
        return self.sum_where(lambda home, away: home > away)

    @property
    def draw(self) -> float:
        return self.sum_where(lambda home, away: home == away)

    @property
    def away_win(self) -> float:
        return self.sum_where(lambda home, away: away > home)

    def over(self, line: float) -> float:
        validated_line = _validate_finite_non_negative(line, "line")
        return self.sum_where(
            lambda home, away: home + away > validated_line
        )

    def under(self, line: float) -> float:
        validated_line = _validate_finite_non_negative(line, "line")
        return self.sum_where(
            lambda home, away: home + away < validated_line
        )

    @property
    def btts_yes(self) -> float:
        return self.sum_where(lambda home, away: home > 0 and away > 0)

    @property
    def btts_no(self) -> float:
        return self.sum_where(lambda home, away: home == 0 or away == 0)

    @property
    def double_chance_home_or_draw(self) -> float:
        return self.home_win + self.draw

    @property
    def double_chance_draw_or_away(self) -> float:
        return self.draw + self.away_win

    @property
    def double_chance_home_or_away(self) -> float:
        return self.home_win + self.away_win

    @property
    def home_win_to_nil(self) -> float:
        return self.sum_where(lambda home, away: home > 0 and away == 0)

    @property
    def away_win_to_nil(self) -> float:
        return self.sum_where(lambda home, away: away > 0 and home == 0)

    def result_or_over(
        self,
        result: str,
        line: float = 2.5,
    ) -> float:
        normalized_result = str(result).strip().upper()
        if normalized_result not in {"HOME", "DRAW", "AWAY"}:
            raise ValueError("result must be HOME, DRAW, or AWAY")
        validated_line = _validate_finite_non_negative(line, "line")

        def wins_result(home: int, away: int) -> bool:
            if normalized_result == "HOME":
                return home > away
            if normalized_result == "DRAW":
                return home == away
            return away > home

        return self.sum_where(
            lambda home, away: (
                wins_result(home, away)
                or home + away > validated_line
            )
        )

    def asian_handicap_cover(self, side: str, line: float) -> float:
        """Return cover probability for supported non-integer handicap lines."""
        normalized_side = str(side).strip().upper()
        if normalized_side not in {"HOME", "AWAY"}:
            raise ValueError("side must be HOME or AWAY")
        validated_line = _validate_finite_non_negative(abs(line), "line")
        signed_line = float(line)
        if signed_line.is_integer():
            raise ValueError(
                "Push-aware integer Asian Handicap lines are unsupported"
            )
        if normalized_side == "HOME":
            return self.sum_where(
                lambda home, away: home + signed_line > away
            )
        return self.sum_where(
            lambda home, away: away + signed_line > home
        )

    def audit_dict(self) -> Dict[str, float | int | str]:
        return {
            "max_home_goal_index": self.max_home_goal,
            "max_away_goal_index": self.max_away_goal,
            "retained_mass_before_normalization": (
                self.retained_mass_before_normalization
            ),
            "omitted_tail_mass": self.omitted_tail_mass,
            "tail_tolerance": self.tail_tolerance,
            "normalization_method": self.normalization_method,
            "home_expected_goals": self.home_expected_goals,
            "away_expected_goals": self.away_expected_goals,
        }


def build_score_matrix(
    home_expected_goals: float,
    away_expected_goals: float,
    *,
    tail_tolerance: float = DEFAULT_TAIL_TOLERANCE,
    maximum_goal_index: int = 200,
) -> ScoreMatrix:
    """Build an adaptively bounded and deterministically normalized matrix."""
    home_xg = _validate_finite_non_negative(
        home_expected_goals,
        "home_expected_goals",
    )
    away_xg = _validate_finite_non_negative(
        away_expected_goals,
        "away_expected_goals",
    )
    tolerance = _validate_tolerance(tail_tolerance)
    if (
        isinstance(maximum_goal_index, bool)
        or not isinstance(maximum_goal_index, int)
        or maximum_goal_index < 0
    ):
        raise ValueError("maximum_goal_index must be a non-negative integer")

    marginal_tail_target = tolerance / 2.0
    home_marginal = _expand_poisson_marginal(
        home_xg,
        marginal_tail_target,
        maximum_goal_index=maximum_goal_index,
    )
    away_marginal = _expand_poisson_marginal(
        away_xg,
        marginal_tail_target,
        maximum_goal_index=maximum_goal_index,
    )
    retained_mass = math.fsum(home_marginal) * math.fsum(away_marginal)
    omitted_mass = max(0.0, 1.0 - retained_mass)
    if omitted_mass > tolerance:
        raise RuntimeError(
            "Adaptive score matrix did not satisfy the requested joint "
            "tail tolerance"
        )
    if retained_mass <= 0.0:
        raise RuntimeError("Score matrix retained no probability mass")

    raw: Dict[Tuple[int, int], float] = {}
    normalized: Dict[Tuple[int, int], float] = {}
    for home_goals, home_probability in enumerate(home_marginal):
        for away_goals, away_probability in enumerate(away_marginal):
            score_probability = home_probability * away_probability
            score = (home_goals, away_goals)
            raw[score] = score_probability
            normalized[score] = score_probability / retained_mass

    normalized_total = math.fsum(normalized.values())
    if normalized_total != 1.0:
        normalized = {
            score: probability / normalized_total
            for score, probability in normalized.items()
        }

    return ScoreMatrix(
        home_expected_goals=home_xg,
        away_expected_goals=away_xg,
        probabilities=MappingProxyType(normalized),
        raw_probabilities=MappingProxyType(raw),
        max_home_goal=len(home_marginal) - 1,
        max_away_goal=len(away_marginal) - 1,
        retained_mass_before_normalization=retained_mass,
        omitted_tail_mass=omitted_mass,
        tail_tolerance=tolerance,
    )


__all__ = [
    "DEFAULT_TAIL_TOLERANCE",
    "NORMALIZATION_METHOD",
    "ScoreMatrix",
    "build_score_matrix",
    "poisson_probability",
]
