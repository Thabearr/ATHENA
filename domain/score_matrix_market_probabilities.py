"""Canonical analytical market projections from an existing ScoreMatrix.

This module derives no expected goals and accepts no prices. Ordinary event
markets expose probabilities; DNB and Asian Handicap expose complete
settlement distributions without relabelling break-even quantities as raw
event probabilities. Every downstream authority remains false.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from domain.markets import MARKET_REGISTRY, MarketId, OutcomeId, make_selection
from domain.model_status import (
    AnalyticalProbabilityCapability,
    PricingAuthority,
    SelectionAuthority,
    SettlementCapability,
    get_model_status,
)
from domain.score_matrix import ScoreMatrix
from domain.score_matrix_settlement import (
    SETTLEMENT_SUM_TOLERANCE,
    SettlementProbabilities,
    asian_handicap_settlement,
    draw_no_bet_settlement,
)


SCHEMA_VERSION = 1
DATASET_NAME = "athena-score-matrix-analytical-market-projection-v1"
PROBABILITY_SUM_TOLERANCE = 1e-12


class AnalyticalProjectionError(ValueError):
    """Raised when a requested analytical projection is not defensible."""


class MarketTopology(str, Enum):
    MUTUALLY_EXCLUSIVE_PARTITION = "MUTUALLY_EXCLUSIVE_PARTITION"
    OVERLAPPING_EVENTS = "OVERLAPPING_EVENTS"
    SETTLEMENT_DISTRIBUTIONS = "SETTLEMENT_DISTRIBUTIONS"


_SAFETY_KEYS = {
    "bet_authorized",
    "market_activation_authorized",
    "pricing_authorized",
    "production_approval_authorized",
    "selection_authorized",
}


def _safety() -> Mapping[str, bool]:
    return MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _probability(value: Any, field: str = "probability") -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
    ):
        raise AnalyticalProjectionError(
            f"{field} must be a finite probability in [0, 1]"
        )
    return float(value)


def _finite_line(value: Any, field: str = "line") -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise AnalyticalProjectionError(f"{field} must be finite numeric")
    line = float(value)
    return 0.0 if line == 0.0 else line


def _half_goal_total_line(value: Any) -> float:
    line = _finite_line(value, "total-goals line")
    if line < 0.0 or line * 2.0 != float(round(line * 2.0)):
        raise AnalyticalProjectionError(
            "Total Goals projection requires an exact non-negative half-goal line"
        )
    if round(line * 2.0) % 2 != 1:
        raise AnalyticalProjectionError(
            "Push-capable Total Goals lines are not ordinary binary projections"
        )
    return line


def _quarter_goal_home_line(value: Any) -> float:
    line = _finite_line(value, "Asian Handicap home line")
    units = line * 4.0
    if units != float(round(units)):
        raise AnalyticalProjectionError(
            "Asian Handicap requires an exact quarter-goal home line"
        )
    return line


@dataclass(frozen=True)
class AnalyticalEventProbability:
    outcome_id: OutcomeId
    probability: float
    line: float | None = None

    def __post_init__(self) -> None:
        if type(self.outcome_id) is not OutcomeId:
            raise AnalyticalProjectionError("outcome_id must be exact OutcomeId")
        object.__setattr__(self, "probability", _probability(self.probability))
        if self.line is not None:
            object.__setattr__(self, "line", _finite_line(self.line))

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome_id": self.outcome_id.value,
            "line": self.line,
            "probability": self.probability,
        }


def _detached_settlement(value: SettlementProbabilities) -> SettlementProbabilities:
    if type(value) is not SettlementProbabilities:
        raise AnalyticalProjectionError(
            "settlement must be exact SettlementProbabilities"
        )
    return SettlementProbabilities(
        full_win=value.full_win,
        half_win=value.half_win,
        push=value.push,
        half_loss=value.half_loss,
        full_loss=value.full_loss,
        method=value.method,
        side=value.side,
        line=value.line,
        component_lines=tuple(value.component_lines),
    )


@dataclass(frozen=True)
class AnalyticalSettlementDistribution:
    outcome_id: OutcomeId
    settlement: SettlementProbabilities

    def __post_init__(self) -> None:
        if self.outcome_id not in {OutcomeId.HOME, OutcomeId.AWAY}:
            raise AnalyticalProjectionError("settlement outcome must be HOME or AWAY")
        detached = _detached_settlement(self.settlement)
        if detached.side != self.outcome_id.value:
            raise AnalyticalProjectionError(
                "settlement side must equal its canonical outcome orientation"
            )
        object.__setattr__(self, "settlement", detached)

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome_id": self.outcome_id.value,
            "settlement": _detached_settlement(self.settlement).to_dict(),
        }


@dataclass(frozen=True)
class ScoreMatrixMarketProjection:
    schema_version: int
    dataset_name: str
    market_id: MarketId
    topology: MarketTopology
    probability_method: str
    home_or_total_line: float | None
    event_probabilities: tuple[AnalyticalEventProbability, ...]
    settlement_distributions: tuple[AnalyticalSettlementDistribution, ...]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION or self.dataset_name != DATASET_NAME:
            raise AnalyticalProjectionError("projection schema identity mismatch")
        if type(self.market_id) is not MarketId:
            raise AnalyticalProjectionError("market_id must be exact MarketId")
        if type(self.topology) is not MarketTopology:
            raise AnalyticalProjectionError("topology must be exact MarketTopology")
        definition = get_model_status(self.market_id)
        if (
            definition.analytical_probability_capability
            is not AnalyticalProbabilityCapability.AVAILABLE
            or not definition.analytically_available
        ):
            raise AnalyticalProjectionError(
                f"{self.market_id.value} has no score-matrix analytical capability"
            )
        if self.probability_method != definition.probability_method:
            raise AnalyticalProjectionError("projection probability method drifted")
        if (
            definition.pricing_authority is not PricingAuthority.NOT_AUTHORIZED
            or definition.selection_authority is not SelectionAuthority.NOT_AUTHORIZED
        ):
            raise AnalyticalProjectionError("projection cannot expand authority")

        if type(self.event_probabilities) is not tuple or any(
            type(item) is not AnalyticalEventProbability
            for item in self.event_probabilities
        ):
            raise AnalyticalProjectionError("event probabilities must be exact tuple")
        events = tuple(
            AnalyticalEventProbability(item.outcome_id, item.probability, item.line)
            for item in self.event_probabilities
        )
        if type(self.settlement_distributions) is not tuple or any(
            type(item) is not AnalyticalSettlementDistribution
            for item in self.settlement_distributions
        ):
            raise AnalyticalProjectionError(
                "settlement distributions must be exact tuple"
            )
        settlements = tuple(
            AnalyticalSettlementDistribution(item.outcome_id, item.settlement)
            for item in self.settlement_distributions
        )

        expected_outcomes = MARKET_REGISTRY[self.market_id].supported_outcomes
        represented = tuple(item.outcome_id for item in events) or tuple(
            item.outcome_id for item in settlements
        )
        if represented != expected_outcomes or len(set(represented)) != len(represented):
            raise AnalyticalProjectionError(
                "projection must preserve exact canonical outcome order"
            )

        if self.market_id is MarketId.TOTAL_GOALS:
            line = _half_goal_total_line(self.home_or_total_line)
            if any(item.line != line for item in events):
                raise AnalyticalProjectionError("total-goals selections must share line")
            object.__setattr__(self, "home_or_total_line", line)
        elif self.market_id is MarketId.ASIAN_HANDICAP:
            line = _quarter_goal_home_line(self.home_or_total_line)
            if tuple(item.settlement.line for item in settlements) != (line, -line):
                raise AnalyticalProjectionError(
                    "Asian Handicap uses home line and exact opposite away line"
                )
            object.__setattr__(self, "home_or_total_line", line)
        elif self.home_or_total_line is not None:
            raise AnalyticalProjectionError("this market does not accept a line")

        settlement_market = definition.settlement_capability is (
            SettlementCapability.FULL_SETTLEMENT_DISTRIBUTION
        )
        if settlement_market:
            if events or not settlements:
                raise AnalyticalProjectionError(
                    "settlement market cannot expose fake scalar probabilities"
                )
            if self.topology is not MarketTopology.SETTLEMENT_DISTRIBUTIONS:
                raise AnalyticalProjectionError("settlement topology mismatch")
        else:
            if settlements or not events:
                raise AnalyticalProjectionError("ordinary market requires events")
            expected_topology = (
                MarketTopology.OVERLAPPING_EVENTS
                if self.market_id is MarketId.DOUBLE_CHANCE
                else MarketTopology.MUTUALLY_EXCLUSIVE_PARTITION
            )
            if self.topology is not expected_topology:
                raise AnalyticalProjectionError("ordinary market topology mismatch")
            if expected_topology is MarketTopology.MUTUALLY_EXCLUSIVE_PARTITION:
                if not math.isclose(
                    math.fsum(item.probability for item in events),
                    1.0,
                    rel_tol=0.0,
                    abs_tol=PROBABILITY_SUM_TOLERANCE,
                ):
                    raise AnalyticalProjectionError(
                        "mutually exclusive event probabilities must partition"
                    )

        if not isinstance(self.safety, Mapping) or set(self.safety) != _SAFETY_KEYS:
            raise AnalyticalProjectionError("projection safety keys mismatch")
        if any(type(value) is not bool or value is not False for value in self.safety.values()):
            raise AnalyticalProjectionError("all projection authority must be false")
        object.__setattr__(self, "event_probabilities", events)
        object.__setattr__(self, "settlement_distributions", settlements)
        object.__setattr__(self, "safety", _safety())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "market_id": self.market_id.value,
            "topology": self.topology.value,
            "probability_method": self.probability_method,
            "home_or_total_line": self.home_or_total_line,
            "event_probabilities": [
                AnalyticalEventProbability(
                    item.outcome_id, item.probability, item.line
                ).to_dict()
                for item in self.event_probabilities
            ],
            "settlement_distributions": [
                AnalyticalSettlementDistribution(
                    item.outcome_id, item.settlement
                ).to_dict()
                for item in self.settlement_distributions
            ],
            "safety": dict(self.safety),
        }


def _event_projection(
    market_id: MarketId,
    probabilities: Sequence[tuple[OutcomeId, float]],
    *,
    topology: MarketTopology = MarketTopology.MUTUALLY_EXCLUSIVE_PARTITION,
    line: float | None = None,
) -> ScoreMatrixMarketProjection:
    definition = get_model_status(market_id)
    return ScoreMatrixMarketProjection(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        market_id=market_id,
        topology=topology,
        probability_method=definition.probability_method or "",
        home_or_total_line=line,
        event_probabilities=tuple(
            AnalyticalEventProbability(outcome, value, line)
            for outcome, value in probabilities
        ),
        settlement_distributions=(),
        safety=_safety(),
    )


def _settlement_projection(
    market_id: MarketId,
    settlements: Sequence[tuple[OutcomeId, SettlementProbabilities]],
    *,
    home_line: float | None = None,
) -> ScoreMatrixMarketProjection:
    definition = get_model_status(market_id)
    return ScoreMatrixMarketProjection(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        market_id=market_id,
        topology=MarketTopology.SETTLEMENT_DISTRIBUTIONS,
        probability_method=definition.probability_method or "",
        home_or_total_line=home_line,
        event_probabilities=(),
        settlement_distributions=tuple(
            AnalyticalSettlementDistribution(outcome, value)
            for outcome, value in settlements
        ),
        safety=_safety(),
    )


def project_score_matrix_market(
    score_matrix: ScoreMatrix,
    market_id: MarketId,
    *,
    line: float | None = None,
) -> ScoreMatrixMarketProjection:
    """Project one canonical market from an already-built normalized matrix.

    For Asian Handicap, ``line`` is the HOME handicap; the AWAY selection is
    projected at the exact opposite line. Total Goals accepts only half-lines.
    """

    if type(score_matrix) is not ScoreMatrix:
        raise TypeError("score_matrix must be an exact ScoreMatrix")
    if type(market_id) is not MarketId:
        raise AnalyticalProjectionError("market_id must be exact MarketId")
    definition = get_model_status(market_id)
    if not definition.analytically_available:
        raise AnalyticalProjectionError(
            f"{market_id.value} is analytically blocked: {definition.reason}"
        )

    if market_id is MarketId.TOTAL_GOALS:
        total_line = _half_goal_total_line(line)
        return _event_projection(
            market_id,
            (
                (OutcomeId.OVER, score_matrix.over(total_line)),
                (OutcomeId.UNDER, score_matrix.under(total_line)),
            ),
            line=total_line,
        )
    if market_id is MarketId.ASIAN_HANDICAP:
        home_line = _quarter_goal_home_line(line)
        return _settlement_projection(
            market_id,
            (
                (
                    OutcomeId.HOME,
                    asian_handicap_settlement(score_matrix, "HOME", home_line),
                ),
                (
                    OutcomeId.AWAY,
                    asian_handicap_settlement(score_matrix, "AWAY", -home_line),
                ),
            ),
            home_line=home_line,
        )
    if line is not None:
        raise AnalyticalProjectionError(f"{market_id.value} does not accept a line")

    if market_id is MarketId.MATCH_RESULT:
        return _event_projection(
            market_id,
            (
                (OutcomeId.HOME, score_matrix.home_win),
                (OutcomeId.DRAW, score_matrix.draw),
                (OutcomeId.AWAY, score_matrix.away_win),
            ),
        )
    if market_id is MarketId.DOUBLE_CHANCE:
        return _event_projection(
            market_id,
            (
                (OutcomeId.HOME_OR_DRAW, score_matrix.double_chance_home_or_draw),
                (OutcomeId.DRAW_OR_AWAY, score_matrix.double_chance_draw_or_away),
                (OutcomeId.HOME_OR_AWAY, score_matrix.double_chance_home_or_away),
            ),
            topology=MarketTopology.OVERLAPPING_EVENTS,
        )
    if market_id is MarketId.BTTS:
        return _event_projection(
            market_id,
            ((OutcomeId.YES, score_matrix.btts_yes), (OutcomeId.NO, score_matrix.btts_no)),
        )
    if market_id in {
        MarketId.DRAW_OR_OVER_2_5,
        MarketId.AWAY_OR_OVER_2_5,
        MarketId.HOME_OR_OVER_2_5,
    }:
        result = {
            MarketId.DRAW_OR_OVER_2_5: "DRAW",
            MarketId.AWAY_OR_OVER_2_5: "AWAY",
            MarketId.HOME_OR_OVER_2_5: "HOME",
        }[market_id]
        yes = score_matrix.result_or_over(result, 2.5)
        return _event_projection(
            market_id,
            ((OutcomeId.YES, yes), (OutcomeId.NO, math.fsum((1.0, -yes)))),
        )
    if market_id in {MarketId.HOME_WIN_TO_NIL, MarketId.AWAY_WIN_TO_NIL}:
        yes = (
            score_matrix.home_win_to_nil
            if market_id is MarketId.HOME_WIN_TO_NIL
            else score_matrix.away_win_to_nil
        )
        return _event_projection(
            market_id,
            ((OutcomeId.YES, yes), (OutcomeId.NO, math.fsum((1.0, -yes)))),
        )
    if market_id is MarketId.DRAW_NO_BET:
        return _settlement_projection(
            market_id,
            (
                (OutcomeId.HOME, draw_no_bet_settlement(score_matrix, "HOME")),
                (OutcomeId.AWAY, draw_no_bet_settlement(score_matrix, "AWAY")),
            ),
        )
    raise AnalyticalProjectionError(
        f"{market_id.value} has no canonical score-matrix projection"
    )


def project_score_matrix_markets(
    score_matrix: ScoreMatrix,
    *,
    total_goal_lines: Sequence[float],
    asian_handicap_home_lines: Sequence[float],
) -> tuple[ScoreMatrixMarketProjection, ...]:
    """Project every supported house using caller-declared analytical lines."""

    totals = tuple(_half_goal_total_line(line) for line in total_goal_lines)
    handicaps = tuple(
        _quarter_goal_home_line(line) for line in asian_handicap_home_lines
    )
    if len(totals) != len(set(totals)) or len(handicaps) != len(set(handicaps)):
        raise AnalyticalProjectionError("projection lines must not contain duplicates")
    no_line_markets = (
        MarketId.MATCH_RESULT,
        MarketId.DRAW_OR_OVER_2_5,
        MarketId.AWAY_OR_OVER_2_5,
        MarketId.HOME_OR_OVER_2_5,
        MarketId.DOUBLE_CHANCE,
        MarketId.BTTS,
        MarketId.DRAW_NO_BET,
        MarketId.HOME_WIN_TO_NIL,
        MarketId.AWAY_WIN_TO_NIL,
    )
    return (
        tuple(project_score_matrix_market(score_matrix, market) for market in no_line_markets)
        + tuple(
            project_score_matrix_market(score_matrix, MarketId.TOTAL_GOALS, line=line)
            for line in sorted(totals)
        )
        + tuple(
            project_score_matrix_market(score_matrix, MarketId.ASIAN_HANDICAP, line=line)
            for line in sorted(handicaps)
        )
    )


def canonical_score_matrix_market_projection_bytes(
    projection: ScoreMatrixMarketProjection,
) -> bytes:
    if type(projection) is not ScoreMatrixMarketProjection:
        raise TypeError("projection must be exact ScoreMatrixMarketProjection")
    rebuilt = ScoreMatrixMarketProjection(**{
        **projection.__dict__,
        "event_probabilities": tuple(projection.event_probabilities),
        "settlement_distributions": tuple(projection.settlement_distributions),
        "safety": dict(projection.safety),
    })
    return (
        json.dumps(
            rebuilt.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def sha256_score_matrix_market_projection(
    projection: ScoreMatrixMarketProjection,
) -> str:
    return hashlib.sha256(
        canonical_score_matrix_market_projection_bytes(projection)
    ).hexdigest()


__all__ = [
    "AnalyticalEventProbability",
    "AnalyticalProjectionError",
    "AnalyticalSettlementDistribution",
    "DATASET_NAME",
    "MarketTopology",
    "SCHEMA_VERSION",
    "ScoreMatrixMarketProjection",
    "canonical_score_matrix_market_projection_bytes",
    "project_score_matrix_market",
    "project_score_matrix_markets",
    "sha256_score_matrix_market_projection",
]
