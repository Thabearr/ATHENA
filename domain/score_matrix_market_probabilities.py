"""Canonical analytical market projections from an existing ScoreMatrix.

This module does not build fixture expected-goals rates, fetch provider data,
price selections, or grant selection/BET authority.  It only projects an
already-normalized regulation-time score matrix into the canonical market
shapes whose mathematics is currently reviewed.

Specialized markets (Win Either Half and 1UP/2UP) intentionally fail with a
typed error here because they require their own model families.  The weekend
fixture orchestrator will combine those specialized outputs with this common
score-matrix projection layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any, Optional, Tuple

from domain.markets import MarketId, OutcomeId
from domain.score_matrix import ScoreMatrix
from domain.score_matrix_settlement import (
    SettlementProbabilities,
    asian_handicap_settlement,
    draw_no_bet_settlement,
)


class MarketProjectionError(ValueError):
    """Raised when an analytical market projection cannot be proven safely."""


class SpecializedMarketModelRequired(MarketProjectionError):
    """Raised when a market belongs to a non-score-matrix model family."""


class MarketTopology(str, Enum):
    MUTUALLY_EXCLUSIVE_PARTITION = "MUTUALLY_EXCLUSIVE_PARTITION"
    COMPLEMENT_PAIR = "COMPLEMENT_PAIR"
    OVERLAPPING_EVENTS = "OVERLAPPING_EVENTS"
    SETTLEMENT_DISTRIBUTIONS = "SETTLEMENT_DISTRIBUTIONS"


@dataclass(frozen=True)
class AnalyticalOutcomeProjection:
    outcome_id: OutcomeId
    probability: Optional[float] = None
    settlement: Optional[SettlementProbabilities] = None

    def __post_init__(self) -> None:
        if (self.probability is None) == (self.settlement is None):
            raise MarketProjectionError(
                "an analytical outcome must carry exactly one probability shape"
            )
        if self.probability is not None:
            value = self.probability
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or not 0.0 <= float(value) <= 1.0
            ):
                raise MarketProjectionError(
                    "analytical probability must be finite and in [0, 1]"
                )
            object.__setattr__(self, "probability", float(value))

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome_id": self.outcome_id.value,
            "probability": self.probability,
            "settlement": (
                self.settlement.to_dict() if self.settlement is not None else None
            ),
        }


@dataclass(frozen=True)
class AnalyticalMarketProjection:
    market_id: MarketId
    topology: MarketTopology
    method: str
    outcomes: Tuple[AnalyticalOutcomeProjection, ...]
    line: Optional[float] = None
    analytical_available: bool = True
    pricing_authorized: bool = False
    selection_authorized: bool = False
    bet_authorized: bool = False

    def __post_init__(self) -> None:
        if not self.outcomes:
            raise MarketProjectionError("market projection must contain outcomes")
        outcome_ids = tuple(item.outcome_id for item in self.outcomes)
        if len(set(outcome_ids)) != len(outcome_ids):
            raise MarketProjectionError("market projection outcomes must be unique")
        if not isinstance(self.method, str) or not self.method.strip():
            raise MarketProjectionError("market projection method must be non-empty")
        object.__setattr__(self, "method", self.method.strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_id": self.market_id.value,
            "topology": self.topology.value,
            "method": self.method,
            "line": self.line,
            "outcomes": [item.to_dict() for item in self.outcomes],
            "analytical_available": self.analytical_available,
            "pricing_authorized": self.pricing_authorized,
            "selection_authorized": self.selection_authorized,
            "bet_authorized": self.bet_authorized,
        }


def _matrix(value: Any) -> ScoreMatrix:
    if not isinstance(value, ScoreMatrix):
        raise TypeError("score_matrix must be a ScoreMatrix")
    return value


def _no_line(line: Optional[float], market_id: MarketId) -> None:
    if line is not None:
        raise MarketProjectionError(
            f"{market_id.value} does not accept a separate analytical line"
        )


def _half_goal_total_line(line: Any) -> float:
    if (
        isinstance(line, bool)
        or not isinstance(line, (int, float))
        or not math.isfinite(float(line))
        or float(line) < 0.0
    ):
        raise MarketProjectionError(
            "Total Goals line must be a finite non-negative half-goal line"
        )
    value = float(line)
    if abs(value % 1.0 - 0.5) > 1e-12:
        raise MarketProjectionError(
            "common Total Goals projection currently supports half-goal lines only"
        )
    return value


def _prob(outcome: OutcomeId, probability: float) -> AnalyticalOutcomeProjection:
    return AnalyticalOutcomeProjection(
        outcome_id=outcome,
        probability=probability,
    )


def _settlement(
    outcome: OutcomeId,
    probabilities: SettlementProbabilities,
) -> AnalyticalOutcomeProjection:
    return AnalyticalOutcomeProjection(
        outcome_id=outcome,
        settlement=probabilities,
    )


def project_score_matrix_market(
    score_matrix: ScoreMatrix,
    market_id: MarketId,
    *,
    line: Optional[float] = None,
) -> AnalyticalMarketProjection:
    """Project one reviewed common market from a normalized score matrix."""

    matrix = _matrix(score_matrix)
    market = MarketId(market_id)

    if market == MarketId.MATCH_RESULT:
        _no_line(line, market)
        return AnalyticalMarketProjection(
            market_id=market,
            topology=MarketTopology.MUTUALLY_EXCLUSIVE_PARTITION,
            method="normalized_independent_poisson_score_matrix",
            outcomes=(
                _prob(OutcomeId.HOME, matrix.home_win),
                _prob(OutcomeId.DRAW, matrix.draw),
                _prob(OutcomeId.AWAY, matrix.away_win),
            ),
        )

    if market == MarketId.TOTAL_GOALS:
        total_line = _half_goal_total_line(line)
        return AnalyticalMarketProjection(
            market_id=market,
            topology=MarketTopology.COMPLEMENT_PAIR,
            method="normalized_score_matrix_total_goals",
            line=total_line,
            outcomes=(
                _prob(OutcomeId.OVER, matrix.over(total_line)),
                _prob(OutcomeId.UNDER, matrix.under(total_line)),
            ),
        )

    if market == MarketId.DOUBLE_CHANCE:
        _no_line(line, market)
        return AnalyticalMarketProjection(
            market_id=market,
            topology=MarketTopology.OVERLAPPING_EVENTS,
            method="normalized_score_matrix_result_sum",
            outcomes=(
                _prob(OutcomeId.HOME_OR_DRAW, matrix.double_chance_home_or_draw),
                _prob(OutcomeId.DRAW_OR_AWAY, matrix.double_chance_draw_or_away),
                _prob(OutcomeId.HOME_OR_AWAY, matrix.double_chance_home_or_away),
            ),
        )

    if market == MarketId.BTTS:
        _no_line(line, market)
        return AnalyticalMarketProjection(
            market_id=market,
            topology=MarketTopology.COMPLEMENT_PAIR,
            method="normalized_score_matrix_btts",
            outcomes=(
                _prob(OutcomeId.YES, matrix.btts_yes),
                _prob(OutcomeId.NO, matrix.btts_no),
            ),
        )

    result_or_over = {
        MarketId.HOME_OR_OVER_2_5: "HOME",
        MarketId.DRAW_OR_OVER_2_5: "DRAW",
        MarketId.AWAY_OR_OVER_2_5: "AWAY",
    }
    if market in result_or_over:
        _no_line(line, market)
        yes = matrix.result_or_over(result_or_over[market], 2.5)
        return AnalyticalMarketProjection(
            market_id=market,
            topology=MarketTopology.COMPLEMENT_PAIR,
            method="normalized_score_matrix_union_probability",
            outcomes=(
                _prob(OutcomeId.YES, yes),
                _prob(OutcomeId.NO, 1.0 - yes),
            ),
        )

    if market == MarketId.HOME_WIN_TO_NIL:
        _no_line(line, market)
        yes = matrix.home_win_to_nil
        return AnalyticalMarketProjection(
            market_id=market,
            topology=MarketTopology.COMPLEMENT_PAIR,
            method="normalized_score_matrix_win_to_nil",
            outcomes=(
                _prob(OutcomeId.YES, yes),
                _prob(OutcomeId.NO, 1.0 - yes),
            ),
        )

    if market == MarketId.AWAY_WIN_TO_NIL:
        _no_line(line, market)
        yes = matrix.away_win_to_nil
        return AnalyticalMarketProjection(
            market_id=market,
            topology=MarketTopology.COMPLEMENT_PAIR,
            method="normalized_score_matrix_win_to_nil",
            outcomes=(
                _prob(OutcomeId.YES, yes),
                _prob(OutcomeId.NO, 1.0 - yes),
            ),
        )

    if market == MarketId.DRAW_NO_BET:
        _no_line(line, market)
        return AnalyticalMarketProjection(
            market_id=market,
            topology=MarketTopology.SETTLEMENT_DISTRIBUTIONS,
            method="normalized_score_matrix_draw_no_bet_settlement",
            outcomes=(
                _settlement(
                    OutcomeId.HOME,
                    draw_no_bet_settlement(matrix, "HOME"),
                ),
                _settlement(
                    OutcomeId.AWAY,
                    draw_no_bet_settlement(matrix, "AWAY"),
                ),
            ),
        )

    if market == MarketId.ASIAN_HANDICAP:
        if line is None:
            raise MarketProjectionError(
                "ASIAN_HANDICAP requires an explicit quarter-goal line"
            )
        home = asian_handicap_settlement(matrix, "HOME", line)
        away = asian_handicap_settlement(matrix, "AWAY", -float(line))
        return AnalyticalMarketProjection(
            market_id=market,
            topology=MarketTopology.SETTLEMENT_DISTRIBUTIONS,
            method="normalized_score_matrix_asian_handicap_settlement",
            line=home.line,
            outcomes=(
                _settlement(OutcomeId.HOME, home),
                _settlement(OutcomeId.AWAY, away),
            ),
        )

    if market in {
        MarketId.HOME_WIN_EITHER_HALF,
        MarketId.AWAY_WIN_EITHER_HALF,
        MarketId.MATCH_RESULT_1UP,
        MarketId.MATCH_RESULT_2UP,
    }:
        raise SpecializedMarketModelRequired(
            f"{market.value} requires its specialized analytical model family"
        )

    raise MarketProjectionError(f"No reviewed analytical projection for {market.value}")


def project_common_score_matrix_markets(
    score_matrix: ScoreMatrix,
    *,
    total_goal_lines: Tuple[float, ...] = (1.5, 2.5, 3.5),
    asian_handicap_lines: Tuple[float, ...] = (),
) -> Tuple[AnalyticalMarketProjection, ...]:
    """Return every common score-matrix market projection requested by caller.

    The returned collection deliberately excludes Win Either Half and 1UP/2UP;
    those specialized model families are composed later by the fixture-level
    15-market orchestrator.
    """

    matrix = _matrix(score_matrix)
    projections = [
        project_score_matrix_market(matrix, MarketId.MATCH_RESULT),
        project_score_matrix_market(matrix, MarketId.DOUBLE_CHANCE),
        project_score_matrix_market(matrix, MarketId.BTTS),
        project_score_matrix_market(matrix, MarketId.DRAW_OR_OVER_2_5),
        project_score_matrix_market(matrix, MarketId.AWAY_OR_OVER_2_5),
        project_score_matrix_market(matrix, MarketId.HOME_OR_OVER_2_5),
        project_score_matrix_market(matrix, MarketId.DRAW_NO_BET),
        project_score_matrix_market(matrix, MarketId.HOME_WIN_TO_NIL),
        project_score_matrix_market(matrix, MarketId.AWAY_WIN_TO_NIL),
    ]
    projections.extend(
        project_score_matrix_market(matrix, MarketId.TOTAL_GOALS, line=line)
        for line in total_goal_lines
    )
    projections.extend(
        project_score_matrix_market(matrix, MarketId.ASIAN_HANDICAP, line=line)
        for line in asian_handicap_lines
    )
    return tuple(projections)


__all__ = [
    "AnalyticalMarketProjection",
    "AnalyticalOutcomeProjection",
    "MarketProjectionError",
    "MarketTopology",
    "SpecializedMarketModelRequired",
    "project_common_score_matrix_markets",
    "project_score_matrix_market",
]
