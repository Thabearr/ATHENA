"""Market-family calibration rows projected from Goal/Score research surfaces.

The projection layer owns no football fitting and no bookmaker input. It turns a
strictly pre-match GoalScoreDistribution plus the post-match regulation score
into auditable calibration vectors using canonical market settlement semantics.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any, Sequence

from domain._forward_calibration_contracts import (
    ForwardCalibrationError,
    LINE_POLICY_ID,
    TACTICAL_EVENT_HIGH,
    TACTICAL_EVENT_LOW,
)
from domain._goal_score_contracts import FeatureStatus, TrainingRow
from domain._goal_score_models import GoalScoreDistribution
from domain.markets import MARKET_REGISTRY, MarketFamily, MarketId, OutcomeId
from domain.score_matrix import DEFAULT_TAIL_TOLERANCE, ScoreMatrix
from domain.score_matrix_settlement import (
    asian_handicap_settlement,
    draw_no_bet_settlement,
)


class CalibrationPartition(str, Enum):
    OOF_CALIBRATION_FIT = "OOF_CALIBRATION_FIT"
    TERMINAL_HOLDOUT_EVALUATION = "TERMINAL_HOLDOUT_EVALUATION"


class CalibrationTopology(str, Enum):
    BINARY_PARTITION = "BINARY_PARTITION"
    SIMPLEX_PARTITION = "SIMPLEX_PARTITION"


@dataclass(frozen=True)
class CalibrationUnitSpec:
    unit_id: str
    market_id: MarketId
    family: MarketFamily
    topology: CalibrationTopology
    components: tuple[str, ...]
    selection_outcome: OutcomeId | None = None
    line: float | None = None
    line_origin_policy_id: str | None = None

    def __post_init__(self) -> None:
        if not self.unit_id or type(self.market_id) is not MarketId:
            raise ForwardCalibrationError("invalid calibration unit identity")
        if self.family is not MARKET_REGISTRY[self.market_id].family:
            raise ForwardCalibrationError("calibration family drifted from market registry")
        if type(self.topology) is not CalibrationTopology:
            raise ForwardCalibrationError("invalid calibration topology")
        if len(self.components) < 2 or len(set(self.components)) != len(self.components):
            raise ForwardCalibrationError("calibration components must be unique")
        if self.topology is CalibrationTopology.BINARY_PARTITION and len(self.components) != 2:
            raise ForwardCalibrationError("binary calibration unit requires two components")
        if self.selection_outcome is not None and type(self.selection_outcome) is not OutcomeId:
            raise ForwardCalibrationError("selection outcome must be canonical")
        if self.line is None:
            if self.line_origin_policy_id is not None:
                raise ForwardCalibrationError("line-origin policy requires explicit line")
        else:
            if not math.isfinite(self.line):
                raise ForwardCalibrationError("calibration line must be finite")
            if self.line_origin_policy_id != LINE_POLICY_ID:
                raise ForwardCalibrationError("research line origin must be explicit")

    def stable_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "market_id": self.market_id.value,
            "family": self.family.value,
            "topology": self.topology.value,
            "components": list(self.components),
            "selection_outcome": (
                None if self.selection_outcome is None else self.selection_outcome.value
            ),
            "line": self.line,
            "line_origin_policy_id": self.line_origin_policy_id,
        }


@dataclass(frozen=True)
class CalibrationVectorRow:
    match_key: str
    match_date: str
    competition_key: str | None
    season: str | None
    regime: str
    model_id: str
    fold_index: int
    fit_end_date: str
    partition: CalibrationPartition
    unit: CalibrationUnitSpec
    raw_probabilities: tuple[float, ...]
    observed_index: int

    def __post_init__(self) -> None:
        if not self.match_key or not self.match_date or not self.model_id:
            raise ForwardCalibrationError("calibration row identity is incomplete")
        if isinstance(self.fold_index, bool) or not isinstance(self.fold_index, int):
            raise ForwardCalibrationError("fold_index must be integer")
        if not self.fit_end_date or self.fit_end_date >= self.match_date:
            raise ForwardCalibrationError(
                "calibration prediction must be generated strictly before target date"
            )
        if type(self.partition) is not CalibrationPartition:
            raise ForwardCalibrationError("invalid calibration partition")
        if type(self.unit) is not CalibrationUnitSpec:
            raise ForwardCalibrationError("invalid calibration unit")
        probabilities = tuple(float(value) for value in self.raw_probabilities)
        if len(probabilities) != len(self.unit.components):
            raise ForwardCalibrationError("calibration vector width mismatch")
        if any(not math.isfinite(value) or value < 0.0 or value > 1.0 for value in probabilities):
            raise ForwardCalibrationError("calibration vector contains invalid probability")
        if not math.isclose(math.fsum(probabilities), 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise ForwardCalibrationError("calibration vector must partition probability mass")
        if (
            isinstance(self.observed_index, bool)
            or not isinstance(self.observed_index, int)
            or not 0 <= self.observed_index < len(probabilities)
        ):
            raise ForwardCalibrationError("observed calibration component is invalid")
        object.__setattr__(self, "raw_probabilities", probabilities)

    @property
    def observed_component(self) -> str:
        return self.unit.components[self.observed_index]


def _finite_line(value: Any, *, quarter: bool) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ForwardCalibrationError("research line must be finite numeric")
    line = float(value)
    units = line * (4.0 if quarter else 2.0)
    if units != float(round(units)):
        raise ForwardCalibrationError(
            "Asian Handicap lines must be quarter-goal; totals must be half-goal"
        )
    if not quarter:
        if line < 0.0 or round(units) % 2 != 1:
            raise ForwardCalibrationError(
                "Total Goals calibration supports non-negative half-goal lines only"
            )
    return 0.0 if line == 0.0 else line


def _line_token(line: float) -> str:
    return f"{line:+.2f}"


def calibration_unit_specs(
    *,
    total_goal_lines: Sequence[float] = (),
    asian_handicap_home_lines: Sequence[float] = (),
) -> tuple[CalibrationUnitSpec, ...]:
    totals = tuple(_finite_line(value, quarter=False) for value in total_goal_lines)
    handicaps = tuple(_finite_line(value, quarter=True) for value in asian_handicap_home_lines)
    if len(totals) != len(set(totals)) or len(handicaps) != len(set(handicaps)):
        raise ForwardCalibrationError("research calibration lines must be unique")

    specs: list[CalibrationUnitSpec] = [
        CalibrationUnitSpec(
            "MATCH_RESULT:PARTITION",
            MarketId.MATCH_RESULT,
            MarketFamily.MATCH_RESULT,
            CalibrationTopology.SIMPLEX_PARTITION,
            ("HOME", "DRAW", "AWAY"),
        ),
        CalibrationUnitSpec(
            "BTTS:PARTITION",
            MarketId.BTTS,
            MarketFamily.BTTS,
            CalibrationTopology.BINARY_PARTITION,
            ("YES", "NO"),
        ),
    ]
    for market_id in (
        MarketId.DRAW_OR_OVER_2_5,
        MarketId.HOME_OR_OVER_2_5,
        MarketId.AWAY_OR_OVER_2_5,
        MarketId.HOME_WIN_TO_NIL,
        MarketId.AWAY_WIN_TO_NIL,
    ):
        specs.append(CalibrationUnitSpec(
            f"{market_id.value}:PARTITION",
            market_id,
            MARKET_REGISTRY[market_id].family,
            CalibrationTopology.BINARY_PARTITION,
            ("YES", "NO"),
        ))
    for outcome in (
        OutcomeId.HOME_OR_DRAW,
        OutcomeId.DRAW_OR_AWAY,
        OutcomeId.HOME_OR_AWAY,
    ):
        specs.append(CalibrationUnitSpec(
            f"DOUBLE_CHANCE:{outcome.value}",
            MarketId.DOUBLE_CHANCE,
            MarketFamily.DOUBLE_CHANCE,
            CalibrationTopology.BINARY_PARTITION,
            ("YES", "NO"),
            selection_outcome=outcome,
        ))
    for outcome in (OutcomeId.HOME, OutcomeId.AWAY):
        specs.append(CalibrationUnitSpec(
            f"DRAW_NO_BET:{outcome.value}",
            MarketId.DRAW_NO_BET,
            MarketFamily.DRAW_NO_BET,
            CalibrationTopology.SIMPLEX_PARTITION,
            ("WIN", "PUSH", "LOSS"),
            selection_outcome=outcome,
        ))
    for line in sorted(totals):
        specs.append(CalibrationUnitSpec(
            f"TOTAL_GOALS:{_line_token(line)}",
            MarketId.TOTAL_GOALS,
            MarketFamily.TOTAL_GOALS,
            CalibrationTopology.BINARY_PARTITION,
            ("OVER", "UNDER"),
            line=line,
            line_origin_policy_id=LINE_POLICY_ID,
        ))
    for home_line in sorted(handicaps):
        for outcome, line in ((OutcomeId.HOME, home_line), (OutcomeId.AWAY, -home_line)):
            specs.append(CalibrationUnitSpec(
                f"ASIAN_HANDICAP:{outcome.value}:{_line_token(line)}",
                MarketId.ASIAN_HANDICAP,
                MarketFamily.ASIAN_HANDICAP,
                CalibrationTopology.SIMPLEX_PARTITION,
                ("WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS"),
                selection_outcome=outcome,
                line=line,
                line_origin_policy_id=LINE_POLICY_ID,
            ))
    return tuple(specs)


def tactical_event_regime(row: TrainingRow) -> str:
    values: list[float] = []
    for feature_id in (
        "TACTICAL.HOME.OVERALL.EVENT_ENVIRONMENT",
        "TACTICAL.AWAY.OVERALL.EVENT_ENVIRONMENT",
    ):
        status, value = row.features.get(feature_id, (FeatureStatus.MISSING, None))
        if status is not FeatureStatus.AVAILABLE or value is None:
            return "UNKNOWN"
        values.append(float(value))
    score = math.fsum(values) / len(values)
    if score <= TACTICAL_EVENT_LOW:
        return "LOW_EVENT"
    if score >= TACTICAL_EVENT_HIGH:
        return "HIGH_EVENT"
    return "MID_EVENT"


def _as_score_matrix(distribution: GoalScoreDistribution) -> ScoreMatrix:
    raw = {
        key: probability * distribution.retained_mass_before_normalization
        for key, probability in distribution.probabilities.items()
    }
    return ScoreMatrix(
        home_expected_goals=distribution.home_intensity,
        away_expected_goals=distribution.away_intensity,
        probabilities=distribution.probabilities,
        raw_probabilities=raw,
        max_home_goal=distribution.max_home_goal,
        max_away_goal=distribution.max_away_goal,
        retained_mass_before_normalization=distribution.retained_mass_before_normalization,
        omitted_tail_mass=distribution.omitted_tail_mass,
        tail_tolerance=DEFAULT_TAIL_TOLERANCE,
        normalization_method=distribution.normalization_method,
    )


def _singleton_score_matrix(home_goals: int, away_goals: int) -> ScoreMatrix:
    probabilities = {(home_goals, away_goals): 1.0}
    return ScoreMatrix(
        home_expected_goals=float(home_goals),
        away_expected_goals=float(away_goals),
        probabilities=probabilities,
        raw_probabilities=probabilities,
        max_home_goal=home_goals,
        max_away_goal=away_goals,
        retained_mass_before_normalization=1.0,
        omitted_tail_mass=0.0,
        tail_tolerance=DEFAULT_TAIL_TOLERANCE,
        normalization_method="observed_singleton_score",
    )


def _settlement_vector(settlement: Any) -> tuple[float, ...]:
    return (
        settlement.full_win,
        settlement.half_win,
        settlement.push,
        settlement.half_loss,
        settlement.full_loss,
    )


def _observed_settlement_index(settlement: Any) -> int:
    vector = _settlement_vector(settlement)
    winners = [index for index, value in enumerate(vector) if math.isclose(value, 1.0)]
    if len(winners) != 1:
        raise ForwardCalibrationError("observed score did not resolve one settlement state")
    return winners[0]


def _vector_and_observed(
    spec: CalibrationUnitSpec,
    row: TrainingRow,
    distribution: GoalScoreDistribution,
) -> tuple[tuple[float, ...], int]:
    matrix = _as_score_matrix(distribution)
    observed_matrix = _singleton_score_matrix(row.home_goals, row.away_goals)
    home, away = row.home_goals, row.away_goals

    if spec.market_id is MarketId.MATCH_RESULT:
        vector = (matrix.home_win, matrix.draw, matrix.away_win)
        observed = 0 if home > away else 1 if home == away else 2
    elif spec.market_id is MarketId.BTTS:
        yes = matrix.btts_yes
        vector = (yes, 1.0 - yes)
        observed = 0 if home > 0 and away > 0 else 1
    elif spec.market_id in {
        MarketId.DRAW_OR_OVER_2_5,
        MarketId.HOME_OR_OVER_2_5,
        MarketId.AWAY_OR_OVER_2_5,
    }:
        result = {
            MarketId.DRAW_OR_OVER_2_5: "DRAW",
            MarketId.HOME_OR_OVER_2_5: "HOME",
            MarketId.AWAY_OR_OVER_2_5: "AWAY",
        }[spec.market_id]
        yes = matrix.result_or_over(result, 2.5)
        result_true = (
            (result == "HOME" and home > away)
            or (result == "DRAW" and home == away)
            or (result == "AWAY" and away > home)
        )
        vector = (yes, 1.0 - yes)
        observed = 0 if result_true or home + away > 2.5 else 1
    elif spec.market_id in {MarketId.HOME_WIN_TO_NIL, MarketId.AWAY_WIN_TO_NIL}:
        yes = (
            matrix.home_win_to_nil
            if spec.market_id is MarketId.HOME_WIN_TO_NIL
            else matrix.away_win_to_nil
        )
        won = (
            home > away and away == 0
            if spec.market_id is MarketId.HOME_WIN_TO_NIL
            else away > home and home == 0
        )
        vector = (yes, 1.0 - yes)
        observed = 0 if won else 1
    elif spec.market_id is MarketId.DOUBLE_CHANCE:
        probability = {
            OutcomeId.HOME_OR_DRAW: matrix.double_chance_home_or_draw,
            OutcomeId.DRAW_OR_AWAY: matrix.double_chance_draw_or_away,
            OutcomeId.HOME_OR_AWAY: matrix.double_chance_home_or_away,
        }[spec.selection_outcome]
        covered = {
            OutcomeId.HOME_OR_DRAW: home >= away,
            OutcomeId.DRAW_OR_AWAY: away >= home,
            OutcomeId.HOME_OR_AWAY: home != away,
        }[spec.selection_outcome]
        vector = (probability, 1.0 - probability)
        observed = 0 if covered else 1
    elif spec.market_id is MarketId.DRAW_NO_BET:
        side = spec.selection_outcome.value
        predicted = draw_no_bet_settlement(matrix, side)
        observed_settlement = draw_no_bet_settlement(observed_matrix, side)
        vector = (predicted.full_win, predicted.push, predicted.full_loss)
        observed = [
            observed_settlement.full_win,
            observed_settlement.push,
            observed_settlement.full_loss,
        ].index(1.0)
    elif spec.market_id is MarketId.TOTAL_GOALS:
        assert spec.line is not None
        over = matrix.over(spec.line)
        vector = (over, 1.0 - over)
        observed = 0 if home + away > spec.line else 1
    elif spec.market_id is MarketId.ASIAN_HANDICAP:
        assert spec.line is not None and spec.selection_outcome is not None
        side = spec.selection_outcome.value
        predicted = asian_handicap_settlement(matrix, side, spec.line)
        observed_settlement = asian_handicap_settlement(observed_matrix, side, spec.line)
        vector = _settlement_vector(predicted)
        observed = _observed_settlement_index(observed_settlement)
    else:
        raise ForwardCalibrationError(
            f"unsupported Goal/Score calibration market: {spec.market_id.value}"
        )
    return tuple(float(value) for value in vector), observed


def project_calibration_rows(
    row: TrainingRow,
    distribution: GoalScoreDistribution,
    *,
    model_id: str,
    fold_index: int,
    fit_end_date: str,
    partition: CalibrationPartition,
    specs: Sequence[CalibrationUnitSpec],
) -> tuple[CalibrationVectorRow, ...]:
    if distribution.model_id != model_id:
        raise ForwardCalibrationError("prediction model identity mismatch")
    regime = tactical_event_regime(row)
    return tuple(
        CalibrationVectorRow(
            match_key=row.match_key,
            match_date=row.match_date,
            competition_key=row.competition_key,
            season=row.season,
            regime=regime,
            model_id=model_id,
            fold_index=fold_index,
            fit_end_date=fit_end_date,
            partition=partition,
            unit=spec,
            raw_probabilities=_vector_and_observed(spec, row, distribution)[0],
            observed_index=_vector_and_observed(spec, row, distribution)[1],
        )
        for spec in specs
    )


__all__ = [name for name in globals() if not name.startswith("_")]
