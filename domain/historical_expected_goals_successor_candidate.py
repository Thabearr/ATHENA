"""Deterministic research-only fitter/evaluator for ATHENA's frozen successor protocol.

This module executes the protocol frozen by PR #72.  It can fit/evaluate exact
HistoricalReplayFixture values for synthetic/adversarial testing, while the
high-level candidate builder additionally requires complete PR69 source-byte
revalidation, exact PR70 reconstruction, and exact protocol/receipt ancestry.
It performs no score-matrix, probability, pricing, selection, or betting work.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import types
from collections.abc import Mapping, Sequence
from typing import Any

from domain.fixture_model_features import ModelFeatureId
from domain.fotmob_reviewed_match_details_expected_goals_transform_candidate import (
    legacy_expected_goals_transform_specification,
)
from domain.historical_expected_goals_component_validation import (
    BenchmarkComparison,
    CalibrationBin,
    ComparisonResult,
    GoalRateMetrics,
    HistoricalExpectedGoalsComponent,
    HistoricalExpectedGoalsComponentValidationError,
    build_historical_expected_goals_component_validation,
    canonical_historical_expected_goals_component_validation_bytes,
    poisson_nll,
)
from domain.historical_expected_goals_successor_protocol import (
    CALIBRATION_BINS,
    ELO_INITIALIZATION_SEMANTICS,
    EVALUATION_LABEL,
    HistoricalExpectedGoalsSuccessorProtocol,
    HistoricalExpectedGoalsSuccessorProtocolError,
    PR31_FATIGUE_SEMANTIC_EQUIVALENCE,
    revalidate_historical_expected_goals_successor_protocol,
    sha256_historical_expected_goals_successor_protocol,
)
from domain.historical_model_feature_replay_candidate import (
    DATASET_NAME as PR69_DATASET_NAME,
    HistoricalFeatureReplayStatus,
    HistoricalModelFeatureReplayCandidateError,
    HistoricalReplayCorpus,
    HistoricalReplayFixture,
    HistoricalReplaySourceInput,
    canonical_historical_model_feature_replay_corpus_bytes,
    revalidate_historical_model_feature_replay_corpus,
)


SCHEMA_VERSION = 1
DATASET_NAME = "athena-historical-expected-goals-successor-candidate-v1"
CANDIDATE_SCOPE = "RETROSPECTIVE_CHRONOLOGICAL_RESEARCH_CANDIDATE_ONLY"
TRAINING_ENGINE_ID = "DETERMINISTIC_NEWTON_POISSON_GLM_WITH_BACKTRACKING_V1"

FORM_COMPARATOR_ID = "PR68_FORM_COMPONENT"
ELO_COMPARATOR_ID = "PR68_ELO_FALLBACK_COMPONENT"
CONSTANT_COMPARATOR_ID = "PR68_FROZEN_CONSTANT_BASELINE"
ROLLING_COMPARATOR_ID = "STRICT_PREMATCH_ROLLING_IDENTITY_LEAGUE_BASELINE"
COMPARATOR_IDS = (
    FORM_COMPARATOR_ID,
    ELO_COMPARATOR_ID,
    CONSTANT_COMPARATOR_ID,
    ROLLING_COMPARATOR_ID,
)

_SAFETY_KEYS = frozenset(
    {
        "successor_candidate_approved",
        "expected_goals_transform_approved",
        "probability_inference_authorized",
        "score_matrix_authorized",
        "probability_adjustment_authorized",
        "calibration_for_production_authorized",
        "pricing_authorized",
        "market_activation_authorized",
        "selection_authorized",
        "production_approval_authorized",
        "bet_authorized",
    }
)


class HistoricalExpectedGoalsSuccessorCandidateError(ValueError):
    """Raised when the frozen successor candidate cannot be reproduced exactly."""


def _error(message: str) -> HistoricalExpectedGoalsSuccessorCandidateError:
    return HistoricalExpectedGoalsSuccessorCandidateError(message)


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("successor candidate serialization failed") from exc
    return (payload + "\n").encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _finite(value: Any, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise _error(f"{label} must be finite numeric")
    return float(value)


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise _error(f"{label} must be an exact positive integer")
    return value


def _nonnegative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise _error(f"{label} must be an exact non-negative integer")
    return value


def _text(value: Any, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise _error(f"{label} must be exact non-empty trimmed text")
    return value


def _hash(value: Any, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise _error(f"{label} must be lowercase SHA-256")
    return value


def _default_safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise _error("successor candidate safety keys mismatch")
    if any(type(flag) is not bool or flag is not False for flag in value.values()):
        raise _error("all successor candidate safety flags must be exact bool False")
    return _default_safety()


def _comparison(delta: float) -> ComparisonResult:
    value = _finite(delta, "comparison delta")
    if value < 0.0:
        return ComparisonResult.BETTER
    if value > 0.0:
        return ComparisonResult.WORSE
    return ComparisonResult.EXACT_TIE


def _mean(values: Sequence[float], label: str) -> float:
    if not values:
        raise _error(f"{label} requires at least one value")
    return _finite(math.fsum(values) / len(values), label)


@dataclasses.dataclass(frozen=True)
class SuccessorModelFit:
    response: str
    training_fixture_count: int
    coefficients: tuple[float, ...]
    newton_updates: int
    convergence_gradient_inf_norm: float
    rounded_training_mean_nll: float

    def __post_init__(self) -> None:
        if self.response not in {"HOME_GOALS", "AWAY_GOALS"}:
            raise _error("fit response must be HOME_GOALS or AWAY_GOALS")
        _positive_int(self.training_fixture_count, "training_fixture_count")
        if type(self.coefficients) is not tuple or len(self.coefficients) != 6:
            raise _error("fit must retain exactly six coefficients")
        for coefficient in self.coefficients:
            value = _finite(coefficient, "fitted coefficient")
            if value != round(value, 12):
                raise _error("fitted coefficients must be rounded to 12 places")
        updates = _nonnegative_int(self.newton_updates, "newton_updates")
        if updates > 200:
            raise _error("newton_updates cannot exceed frozen maximum")
        gradient = _finite(
            self.convergence_gradient_inf_norm,
            "convergence_gradient_inf_norm",
        )
        if gradient < 0.0 or gradient > 1e-8:
            raise _error("fit must retain a converged pre-round gradient norm")
        if _finite(self.rounded_training_mean_nll, "rounded_training_mean_nll") < 0.0:
            raise _error("training mean NLL must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class SuccessorGroupSummary:
    group_key: str
    fixture_count: int
    candidate_mean_joint_nll: float
    comparisons: tuple[BenchmarkComparison, ...]

    def __post_init__(self) -> None:
        _text(self.group_key, "group_key")
        count = _positive_int(self.fixture_count, "group fixture_count")
        candidate_mean = _finite(self.candidate_mean_joint_nll, "group candidate mean NLL")
        if (
            type(self.comparisons) is not tuple
            or tuple(item.benchmark_id for item in self.comparisons) != COMPARATOR_IDS
            or any(type(item) is not BenchmarkComparison for item in self.comparisons)
        ):
            raise _error("group comparator set/order must match frozen protocol")
        for item in self.comparisons[:3]:
            if item.paired_fixture_count != count:
                raise _error("non-rolling group comparators must use every group fixture")
            if item.candidate_mean_joint_nll != candidate_mean:
                raise _error("group comparator candidate NLL must match group candidate mean")
        if self.comparisons[3].paired_fixture_count > count:
            raise _error("rolling group pairs cannot exceed group fixture count")
        for item in self.comparisons:
            if item.paired_fixture_count and item.candidate_mean_joint_nll is None:
                raise _error("paired group comparator must retain candidate mean NLL")

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_key": self.group_key,
            "fixture_count": self.fixture_count,
            "candidate_mean_joint_nll": self.candidate_mean_joint_nll,
            "comparisons": [item.to_dict() for item in self.comparisons],
        }


@dataclasses.dataclass(frozen=True)
class SuccessorFitEvaluation:
    training_fixture_count: int
    evaluation_fixture_count: int
    training_season_counts: Mapping[str, int]
    evaluation_season_counts: Mapping[str, int]
    home_fit: SuccessorModelFit
    away_fit: SuccessorModelFit
    metrics: GoalRateMetrics
    comparisons: tuple[BenchmarkComparison, ...]
    season_breakdown: tuple[SuccessorGroupSummary, ...]
    league_breakdown: tuple[SuccessorGroupSummary, ...]
    home_calibration: tuple[CalibrationBin, ...]
    away_calibration: tuple[CalibrationBin, ...]

    def __post_init__(self) -> None:
        training_count = _positive_int(
            self.training_fixture_count, "training_fixture_count"
        )
        evaluation_count = _positive_int(
            self.evaluation_fixture_count, "evaluation_fixture_count"
        )
        for mapping, label, expected_total in (
            (self.training_season_counts, "training_season_counts", training_count),
            (self.evaluation_season_counts, "evaluation_season_counts", evaluation_count),
        ):
            if not isinstance(mapping, Mapping) or not mapping:
                raise _error(f"{label} must be a non-empty mapping")
            detached: dict[str, int] = {}
            for key, value in mapping.items():
                _text(key, f"{label} key")
                detached[key] = _positive_int(value, f"{label} value")
            if math.fsum(detached.values()) != expected_total:
                raise _error(f"{label} must reconcile to its fixture count")
            object.__setattr__(
                self,
                label,
                types.MappingProxyType(dict(sorted(detached.items()))),
            )
        if type(self.home_fit) is not SuccessorModelFit or self.home_fit.response != "HOME_GOALS":
            raise _error("home_fit mismatch")
        if type(self.away_fit) is not SuccessorModelFit or self.away_fit.response != "AWAY_GOALS":
            raise _error("away_fit mismatch")
        if (
            self.home_fit.training_fixture_count != training_count
            or self.away_fit.training_fixture_count != training_count
        ):
            raise _error("fit training counts must match evaluation container")
        if type(self.metrics) is not GoalRateMetrics or self.metrics.fixture_count != evaluation_count:
            raise _error("evaluation metrics count mismatch")
        if (
            type(self.comparisons) is not tuple
            or tuple(item.benchmark_id for item in self.comparisons) != COMPARATOR_IDS
            or any(type(item) is not BenchmarkComparison for item in self.comparisons)
        ):
            raise _error("aggregate comparator set/order mismatch")
        for item in self.comparisons[:3]:
            if item.paired_fixture_count != evaluation_count:
                raise _error("non-rolling comparators must use every evaluation fixture")
            if item.candidate_mean_joint_nll != self.metrics.mean_joint_poisson_nll:
                raise _error("aggregate comparator candidate NLL must match metrics")
        if self.comparisons[3].paired_fixture_count > evaluation_count:
            raise _error("rolling pairs cannot exceed evaluation count")
        for groups, label in (
            (self.season_breakdown, "season"),
            (self.league_breakdown, "league"),
        ):
            if type(groups) is not tuple or not groups:
                raise _error(f"{label} breakdown must be non-empty tuple")
            if any(type(item) is not SuccessorGroupSummary for item in groups):
                raise _error(f"{label} breakdown must use exact summaries")
            if groups != tuple(sorted(groups, key=lambda item: item.group_key)):
                raise _error(f"{label} breakdown must be deterministically sorted")
            if math.fsum(item.fixture_count for item in groups) != evaluation_count:
                raise _error(f"{label} breakdown counts must reconcile")
            if math.fsum(item.comparisons[3].paired_fixture_count for item in groups) != self.comparisons[3].paired_fixture_count:
                raise _error(f"{label} rolling pair counts must reconcile")
        for bins, label in (
            (self.home_calibration, "home"),
            (self.away_calibration, "away"),
        ):
            if type(bins) is not tuple or tuple((item.lower, item.upper) for item in bins) != CALIBRATION_BINS:
                raise _error(f"{label} calibration bounds mismatch")
            if math.fsum(item.count for item in bins) != evaluation_count:
                raise _error(f"{label} calibration counts must reconcile")

    def to_dict(self) -> dict[str, Any]:
        return {
            "training_fixture_count": self.training_fixture_count,
            "evaluation_fixture_count": self.evaluation_fixture_count,
            "training_season_counts": dict(self.training_season_counts),
            "evaluation_season_counts": dict(self.evaluation_season_counts),
            "home_fit": self.home_fit.to_dict(),
            "away_fit": self.away_fit.to_dict(),
            "metrics": self.metrics.to_dict(),
            "comparisons": [item.to_dict() for item in self.comparisons],
            "season_breakdown": [item.to_dict() for item in self.season_breakdown],
            "league_breakdown": [item.to_dict() for item in self.league_breakdown],
            "home_calibration": [item.to_dict() for item in self.home_calibration],
            "away_calibration": [item.to_dict() for item in self.away_calibration],
        }


@dataclasses.dataclass(frozen=True)
class HistoricalExpectedGoalsSuccessorCandidate:
    schema_version: int
    dataset_name: str
    candidate_scope: str
    evidence_receipt_sha256: str
    protocol_id: str
    protocol_sha256: str
    protocol_size: int
    source_pr69_dataset_name: str
    source_pr69_sha256: str
    source_pr69_size: int
    source_corpus_sha256: str
    source_pr70_validation_sha256: str
    source_pr70_validation_size: int
    evaluation_label: str
    elo_initialization_semantics: str
    fatigue_pr31_semantic_equivalence: str
    training_engine_id: str
    training_executed: bool
    fit_evaluation: SuccessorFitEvaluation
    historical_freshness_regime_reconstructed: bool
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise _error("candidate schema version mismatch")
        if self.dataset_name != DATASET_NAME or self.candidate_scope != CANDIDATE_SCOPE:
            raise _error("candidate identity/scope mismatch")
        for value, label in (
            (self.evidence_receipt_sha256, "evidence_receipt_sha256"),
            (self.protocol_sha256, "protocol_sha256"),
            (self.source_pr69_sha256, "source_pr69_sha256"),
            (self.source_corpus_sha256, "source_corpus_sha256"),
            (self.source_pr70_validation_sha256, "source_pr70_validation_sha256"),
        ):
            _hash(value, label)
        _text(self.protocol_id, "protocol_id")
        _positive_int(self.protocol_size, "protocol_size")
        if self.source_pr69_dataset_name != PR69_DATASET_NAME:
            raise _error("candidate PR69 dataset identity mismatch")
        _positive_int(self.source_pr69_size, "source_pr69_size")
        _positive_int(self.source_pr70_validation_size, "source_pr70_validation_size")
        if self.evaluation_label != EVALUATION_LABEL:
            raise _error("candidate evaluation label mismatch")
        if self.elo_initialization_semantics != ELO_INITIALIZATION_SEMANTICS:
            raise _error("candidate must preserve Elo initialization caveat")
        if self.fatigue_pr31_semantic_equivalence != PR31_FATIGUE_SEMANTIC_EQUIVALENCE:
            raise _error("candidate must preserve fatigue semantic caveat")
        if self.training_engine_id != TRAINING_ENGINE_ID:
            raise _error("candidate training engine mismatch")
        if type(self.training_executed) is not bool or self.training_executed is not True:
            raise _error("candidate must truthfully record research training execution")
        if type(self.fit_evaluation) is not SuccessorFitEvaluation:
            raise _error("candidate fit_evaluation must be exact SuccessorFitEvaluation")
        if (
            type(self.historical_freshness_regime_reconstructed) is not bool
            or self.historical_freshness_regime_reconstructed is not False
        ):
            raise _error("candidate must not reconstruct historical freshness regime")
        object.__setattr__(self, "safety", _validate_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "candidate_scope": self.candidate_scope,
            "evidence_receipt_sha256": self.evidence_receipt_sha256,
            "protocol_id": self.protocol_id,
            "protocol_sha256": self.protocol_sha256,
            "protocol_size": self.protocol_size,
            "source_pr69_dataset_name": self.source_pr69_dataset_name,
            "source_pr69_sha256": self.source_pr69_sha256,
            "source_pr69_size": self.source_pr69_size,
            "source_corpus_sha256": self.source_corpus_sha256,
            "source_pr70_validation_sha256": self.source_pr70_validation_sha256,
            "source_pr70_validation_size": self.source_pr70_validation_size,
            "evaluation_label": self.evaluation_label,
            "elo_initialization_semantics": self.elo_initialization_semantics,
            "fatigue_pr31_semantic_equivalence": self.fatigue_pr31_semantic_equivalence,
            "training_engine_id": self.training_engine_id,
            "training_executed": self.training_executed,
            "fit_evaluation": self.fit_evaluation.to_dict(),
            "historical_freshness_regime_reconstructed": self.historical_freshness_regime_reconstructed,
            "safety": dict(self.safety),
        }


@dataclasses.dataclass(frozen=True)
class _EvaluationRow:
    fixture: HistoricalReplayFixture
    home_rate: float
    away_rate: float
    candidate_joint_nll: float
    comparator_joint_nlls: Mapping[str, float | None]


def _feature_value(fixture: HistoricalReplayFixture, feature_id: ModelFeatureId) -> float:
    matches = [item for item in fixture.features if item.feature_id is feature_id]
    if len(matches) != 1:
        raise _error("fixture must contain each exact replay feature once")
    item = matches[0]
    if item.status is not HistoricalFeatureReplayStatus.AVAILABLE_RESEARCH_REPLAY:
        raise _error("eligible successor fixture requested a non-available feature")
    if item.value is None:
        raise _error("available successor feature cannot be null")
    return _finite(item.value, f"{feature_id.value} value")


def _predictor_vector(
    protocol: HistoricalExpectedGoalsSuccessorProtocol,
    fixture: HistoricalReplayFixture,
) -> tuple[float, ...]:
    values: list[float] = []
    for specification in protocol.predictors:
        if specification.transform == "CONSTANT_ONE":
            value = 1.0
        else:
            if specification.source_feature_id is None:
                raise _error("non-intercept predictor must retain source feature")
            try:
                feature_id = ModelFeatureId(specification.source_feature_id)
            except ValueError as exc:  # pragma: no cover - protocol already validates
                raise _error("protocol predictor references unknown feature") from exc
            source_value = _feature_value(fixture, feature_id)
            if specification.transform == "(VALUE_MINUS_CENTER)_DIVIDED_BY_SCALE":
                if specification.center is None or specification.scale is None:
                    raise _error("scaled predictor is missing frozen center/scale")
                value = (source_value - specification.center) / specification.scale
            elif specification.transform == "VALUE_MINUS_CENTER":
                if specification.center is None:
                    raise _error("centered predictor is missing frozen center")
                value = source_value - specification.center
            elif specification.transform == "IDENTITY":
                value = source_value
            else:  # pragma: no cover - exact protocol exhaustiveness guard
                raise _error("unsupported frozen predictor transform")
        values.append(_finite(value, f"predictor {specification.name}"))
    if len(values) != 6:
        raise _error("frozen protocol must produce exactly six predictors")
    return tuple(values)


def _eligible(fixture: HistoricalReplayFixture) -> bool:
    return (
        fixture.form_path_component_eligible is True
        and fixture.elo_fallback_component_eligible is True
    )


def _ordered_eligible(
    protocol: HistoricalExpectedGoalsSuccessorProtocol,
    fixtures: Sequence[HistoricalReplayFixture],
    seasons: tuple[str, ...],
) -> tuple[HistoricalReplayFixture, ...]:
    selected: list[HistoricalReplayFixture] = []
    known_seasons = set(protocol.train_seasons) | set(protocol.evaluation_seasons)
    for fixture in fixtures:
        if type(fixture) is not HistoricalReplayFixture:
            raise _error("fixtures must contain exact HistoricalReplayFixture values")
        if fixture.season not in known_seasons:
            raise _error("fixture season lies outside frozen chronological protocol")
        if not _eligible(fixture) or fixture.season not in seasons:
            continue
        if fixture.source_local_kickoff is None:
            raise _error("eligible successor fixture must have exact source-local kickoff")
        selected.append(fixture)
    result = tuple(
        sorted(
            selected,
            key=lambda item: (item.source_local_kickoff, item.fixture_identifier),
        )
    )
    if len({item.fixture_identifier for item in result}) != len(result):
        raise _error("successor fixture identifiers must be unique")
    return result


def _linear_predictor(row: Sequence[float], beta: Sequence[float]) -> float:
    if len(row) != len(beta):
        raise _error("predictor/coefficient dimension mismatch")
    return _finite(
        math.fsum(value * coefficient for value, coefficient in zip(row, beta)),
        "linear predictor",
    )


def _response_nll(
    rows: Sequence[tuple[float, ...]],
    responses: Sequence[int],
    beta: Sequence[float],
    maximum_abs_eta: float,
) -> tuple[float, tuple[float, ...], tuple[float, ...]]:
    if len(rows) != len(responses) or not rows:
        raise _error("response objective requires exact non-empty paired rows")
    etas: list[float] = []
    mus: list[float] = []
    nlls: list[float] = []
    for row, response in zip(rows, responses):
        eta = _linear_predictor(row, beta)
        if abs(eta) > maximum_abs_eta:
            raise _error("absolute linear predictor exceeds frozen guard")
        mu = _finite(math.exp(eta), "Poisson mean")
        etas.append(eta)
        mus.append(mu)
        nlls.append(poisson_nll(response, mu))
    return _finite(math.fsum(nlls), "response NLL"), tuple(etas), tuple(mus)


def _gradient_and_hessian(
    rows: Sequence[tuple[float, ...]],
    responses: Sequence[int],
    mus: Sequence[float],
) -> tuple[tuple[float, ...], tuple[tuple[float, ...], ...]]:
    dimension = len(rows[0])
    gradient = tuple(
        _finite(
            math.fsum(
                row[column] * (response - mu)
                for row, response, mu in zip(rows, responses, mus)
            ),
            "Newton gradient",
        )
        for column in range(dimension)
    )
    hessian = tuple(
        tuple(
            _finite(
                math.fsum(
                    mu * row[left] * row[right]
                    for row, mu in zip(rows, mus)
                ),
                "Newton Hessian",
            )
            for right in range(dimension)
        )
        for left in range(dimension)
    )
    return gradient, hessian


def _solve_linear_system(
    matrix: Sequence[Sequence[float]],
    rhs: Sequence[float],
    pivot_tolerance: float,
) -> tuple[float, ...]:
    dimension = len(rhs)
    if dimension == 0 or len(matrix) != dimension or any(len(row) != dimension for row in matrix):
        raise _error("Newton linear system must be non-empty and square")
    work = [[_finite(value, "linear-system matrix value") for value in row] for row in matrix]
    target = [_finite(value, "linear-system rhs value") for value in rhs]

    for column in range(dimension):
        pivot_row = column
        pivot_abs = abs(work[column][column])
        for row in range(column + 1, dimension):
            candidate_abs = abs(work[row][column])
            if candidate_abs > pivot_abs:
                pivot_abs = candidate_abs
                pivot_row = row
        if pivot_abs <= pivot_tolerance:
            raise _error("Newton Hessian pivot is singular under frozen tolerance")
        if pivot_row != column:
            work[column], work[pivot_row] = work[pivot_row], work[column]
            target[column], target[pivot_row] = target[pivot_row], target[column]
        pivot = work[column][column]
        for row in range(column + 1, dimension):
            factor = work[row][column] / pivot
            work[row][column] = 0.0
            for inner in range(column + 1, dimension):
                work[row][inner] = _finite(
                    work[row][inner] - factor * work[column][inner],
                    "Gaussian elimination value",
                )
            target[row] = _finite(
                target[row] - factor * target[column],
                "Gaussian elimination rhs",
            )

    solution = [0.0] * dimension
    for row in range(dimension - 1, -1, -1):
        remainder = math.fsum(
            work[row][column] * solution[column]
            for column in range(row + 1, dimension)
        )
        pivot = work[row][row]
        if abs(pivot) <= pivot_tolerance:
            raise _error("Newton back-substitution pivot is singular")
        solution[row] = _finite(
            (target[row] - remainder) / pivot,
            "Newton solution value",
        )
    return tuple(solution)


def _rounded_coefficients(values: Sequence[float], places: int) -> tuple[float, ...]:
    return tuple(_finite(round(value, places), "rounded coefficient") for value in values)


def _fit_response(
    *,
    protocol: HistoricalExpectedGoalsSuccessorProtocol,
    fixtures: Sequence[HistoricalReplayFixture],
    response: str,
) -> SuccessorModelFit:
    if response not in {"HOME_GOALS", "AWAY_GOALS"}:
        raise _error("unknown response")
    if not fixtures:
        raise _error("fitting requires at least one training fixture")
    rows = tuple(_predictor_vector(protocol, fixture) for fixture in fixtures)
    responses = tuple(
        fixture.home_goals if response == "HOME_GOALS" else fixture.away_goals
        for fixture in fixtures
    )
    response_mean = _finite(
        math.fsum(responses) / len(responses),
        "training response mean",
    )
    if response_mean <= 0.0:
        raise _error("training response mean must be strictly positive")

    fitting = protocol.fitting
    beta = [0.0] * len(protocol.predictors)
    beta[0] = _finite(math.log(response_mean), "initial intercept")
    updates = 0
    converged_gradient = None

    while True:
        current_nll, _, mus = _response_nll(
            rows,
            responses,
            beta,
            fitting.maximum_abs_linear_predictor,
        )
        gradient, hessian = _gradient_and_hessian(rows, responses, mus)
        gradient_norm = _finite(
            max(abs(value) for value in gradient),
            "gradient infinity norm",
        )
        if gradient_norm <= fitting.gradient_inf_norm_tolerance:
            converged_gradient = gradient_norm
            break
        if updates >= fitting.max_iterations:
            raise _error("frozen Newton solver did not converge within max iterations")
        direction = _solve_linear_system(
            hessian,
            gradient,
            fitting.linear_solve_pivot_tolerance,
        )
        step = 1.0
        accepted = False
        while True:
            candidate = tuple(
                _finite(
                    coefficient + step * delta,
                    "candidate coefficient",
                )
                for coefficient, delta in zip(beta, direction)
            )
            try:
                candidate_nll, _, _ = _response_nll(
                    rows,
                    responses,
                    candidate,
                    fitting.maximum_abs_linear_predictor,
                )
            except HistoricalExpectedGoalsSuccessorCandidateError as exc:
                if "linear predictor exceeds" not in str(exc):
                    raise
                candidate_nll = math.inf
            if candidate_nll <= current_nll:
                beta = list(candidate)
                accepted = True
                updates += 1
                break
            next_step = step * fitting.backtracking_factor
            if next_step < fitting.minimum_step:
                raise _error("frozen Newton backtracking fell below minimum step")
            step = next_step
        if not accepted:  # pragma: no cover - loop either accepts or raises
            raise _error("frozen Newton line search did not accept a step")

    assert converged_gradient is not None
    rounded = _rounded_coefficients(beta, fitting.coefficient_rounding_places)
    rounded_nll, _, _ = _response_nll(
        rows,
        responses,
        rounded,
        fitting.maximum_abs_linear_predictor,
    )
    return SuccessorModelFit(
        response=response,
        training_fixture_count=len(fixtures),
        coefficients=rounded,
        newton_updates=updates,
        convergence_gradient_inf_norm=converged_gradient,
        rounded_training_mean_nll=_finite(
            rounded_nll / len(fixtures),
            "rounded training mean NLL",
        ),
    )


def _model_rates(
    protocol: HistoricalExpectedGoalsSuccessorProtocol,
    fixture: HistoricalReplayFixture,
    home_fit: SuccessorModelFit,
    away_fit: SuccessorModelFit,
) -> tuple[float, float]:
    row = _predictor_vector(protocol, fixture)
    home_eta = _linear_predictor(row, home_fit.coefficients)
    away_eta = _linear_predictor(row, away_fit.coefficients)
    maximum = protocol.fitting.maximum_abs_linear_predictor
    if abs(home_eta) > maximum or abs(away_eta) > maximum:
        raise _error("rounded evaluation coefficient vector exceeds eta guard")
    return (
        _finite(math.exp(home_eta), "successor home rate"),
        _finite(math.exp(away_eta), "successor away rate"),
    )


def _legacy_rates(
    fixture: HistoricalReplayFixture,
    component: HistoricalExpectedGoalsComponent,
) -> tuple[float, float]:
    specification = legacy_expected_goals_transform_specification()
    fatigue = _feature_value(fixture, ModelFeatureId.FATIGUE)
    if component is HistoricalExpectedGoalsComponent.FORM_COMPONENT:
        home_raw = _feature_value(fixture, ModelFeatureId.HOME_FORM)
        away_raw = _feature_value(fixture, ModelFeatureId.AWAY_FORM)
    elif component is HistoricalExpectedGoalsComponent.ELO_FALLBACK_COMPONENT:
        home_elo = _feature_value(fixture, ModelFeatureId.HOME_ELO)
        away_elo = _feature_value(fixture, ModelFeatureId.AWAY_ELO)
        home_raw = 0.50 + (
            (home_elo - specification.elo_center) / specification.elo_divisor
        )
        away_raw = 0.50 + (
            (away_elo - specification.elo_center) / specification.elo_divisor
        )
        home_raw = max(specification.raw_min, min(specification.raw_max, home_raw))
        away_raw = max(specification.raw_min, min(specification.raw_max, away_raw))
    else:  # pragma: no cover
        raise _error("unknown legacy comparator component")
    base_home = (
        specification.home_baseline
        + (home_raw - away_raw)
        - fatigue * specification.fatigue_coefficient
    )
    base_away = (
        specification.away_baseline
        + (away_raw - home_raw)
        + fatigue * specification.fatigue_coefficient
    )
    return (
        _finite(
            max(
                specification.minimum_rate,
                round(base_home, specification.decimal_rounding_places),
            ),
            "legacy home rate",
        ),
        _finite(
            max(
                specification.minimum_rate,
                round(base_away, specification.decimal_rounding_places),
            ),
            "legacy away rate",
        ),
    )


def _league_rate(state: list[int]) -> tuple[float, float] | None:
    if state[0] == 0:
        return None
    home_rate = state[1] / state[0]
    away_rate = state[2] / state[0]
    if (
        home_rate <= 0.0
        or away_rate <= 0.0
        or not math.isfinite(home_rate)
        or not math.isfinite(away_rate)
    ):
        return None
    return float(home_rate), float(away_rate)


def _rolling_rates(
    fixtures: Sequence[HistoricalReplayFixture],
) -> Mapping[str, tuple[float, float] | None]:
    """Exact PR70 rolling-league chronology, including same-time batching."""

    result: dict[str, tuple[float, float] | None] = {
        fixture.fixture_identifier: None for fixture in fixtures
    }
    by_league: dict[str, list[HistoricalReplayFixture]] = {}
    for fixture in fixtures:
        by_league.setdefault(fixture.identity_league, []).append(fixture)
    for league in sorted(by_league):
        state = [0, 0, 0]
        by_date: dict[Any, list[HistoricalReplayFixture]] = {}
        for fixture in by_league[league]:
            by_date.setdefault(fixture.source_local_date, []).append(fixture)
        for source_date in sorted(by_date):
            day = sorted(by_date[source_date], key=lambda item: item.fixture_identifier)
            missing = [item for item in day if item.source_local_kickoff is None]
            known = [item for item in day if item.source_local_kickoff is not None]
            if missing:
                for fixture in day:
                    result[fixture.fixture_identifier] = None
                for fixture in day:
                    state[0] += 1
                    state[1] += fixture.home_goals
                    state[2] += fixture.away_goals
                continue
            ordered = sorted(
                known,
                key=lambda item: (item.source_local_kickoff, item.fixture_identifier),
            )
            index = 0
            while index < len(ordered):
                kickoff = ordered[index].source_local_kickoff
                end = index
                while end < len(ordered) and ordered[end].source_local_kickoff == kickoff:
                    end += 1
                batch = ordered[index:end]
                rate = _league_rate(state)
                for fixture in batch:
                    result[fixture.fixture_identifier] = rate
                for fixture in batch:
                    state[0] += 1
                    state[1] += fixture.home_goals
                    state[2] += fixture.away_goals
                index = end
    return types.MappingProxyType(result)


def _joint_nll(fixture: HistoricalReplayFixture, home_rate: float, away_rate: float) -> float:
    return _finite(
        math.fsum(
            (
                poisson_nll(fixture.home_goals, home_rate),
                poisson_nll(fixture.away_goals, away_rate),
            )
        ),
        "joint Poisson NLL",
    )


def _evaluation_rows(
    *,
    protocol: HistoricalExpectedGoalsSuccessorProtocol,
    all_fixtures: Sequence[HistoricalReplayFixture],
    evaluation_fixtures: Sequence[HistoricalReplayFixture],
    home_fit: SuccessorModelFit,
    away_fit: SuccessorModelFit,
) -> tuple[_EvaluationRow, ...]:
    rolling = _rolling_rates(all_fixtures)
    specification = legacy_expected_goals_transform_specification()
    rows: list[_EvaluationRow] = []
    for fixture in evaluation_fixtures:
        home_rate, away_rate = _model_rates(protocol, fixture, home_fit, away_fit)
        candidate_nll = _joint_nll(fixture, home_rate, away_rate)
        form_home, form_away = _legacy_rates(
            fixture, HistoricalExpectedGoalsComponent.FORM_COMPONENT
        )
        elo_home, elo_away = _legacy_rates(
            fixture, HistoricalExpectedGoalsComponent.ELO_FALLBACK_COMPONENT
        )
        rolling_rate = rolling.get(fixture.fixture_identifier)
        comparator_nlls: dict[str, float | None] = {
            FORM_COMPARATOR_ID: _joint_nll(fixture, form_home, form_away),
            ELO_COMPARATOR_ID: _joint_nll(fixture, elo_home, elo_away),
            CONSTANT_COMPARATOR_ID: _joint_nll(
                fixture,
                specification.home_baseline,
                specification.away_baseline,
            ),
            ROLLING_COMPARATOR_ID: None,
        }
        if rolling_rate is not None:
            comparator_nlls[ROLLING_COMPARATOR_ID] = _joint_nll(
                fixture, rolling_rate[0], rolling_rate[1]
            )
        rows.append(
            _EvaluationRow(
                fixture=fixture,
                home_rate=home_rate,
                away_rate=away_rate,
                candidate_joint_nll=candidate_nll,
                comparator_joint_nlls=types.MappingProxyType(comparator_nlls),
            )
        )
    return tuple(rows)


def _metrics(rows: Sequence[_EvaluationRow]) -> GoalRateMetrics:
    if not rows:
        raise _error("successor evaluation requires at least one fixture")
    count = len(rows)
    predicted_home = _mean([item.home_rate for item in rows], "mean predicted home")
    actual_home = _mean(
        [float(item.fixture.home_goals) for item in rows], "mean actual home"
    )
    predicted_away = _mean([item.away_rate for item in rows], "mean predicted away")
    actual_away = _mean(
        [float(item.fixture.away_goals) for item in rows], "mean actual away"
    )
    home_mae = _mean(
        [abs(item.home_rate - item.fixture.home_goals) for item in rows], "home MAE"
    )
    away_mae = _mean(
        [abs(item.away_rate - item.fixture.away_goals) for item in rows], "away MAE"
    )
    home_rmse = _finite(
        math.sqrt(
            math.fsum(
                (item.home_rate - item.fixture.home_goals) ** 2 for item in rows
            )
            / count
        ),
        "home RMSE",
    )
    away_rmse = _finite(
        math.sqrt(
            math.fsum(
                (item.away_rate - item.fixture.away_goals) ** 2 for item in rows
            )
            / count
        ),
        "away RMSE",
    )
    mean_nll = _mean(
        [item.candidate_joint_nll for item in rows], "mean joint Poisson NLL"
    )
    return GoalRateMetrics(
        fixture_count=count,
        mean_predicted_home_goals=predicted_home,
        mean_actual_home_goals=actual_home,
        home_bias=_finite(predicted_home - actual_home, "home bias"),
        mean_predicted_away_goals=predicted_away,
        mean_actual_away_goals=actual_away,
        away_bias=_finite(predicted_away - actual_away, "away bias"),
        home_mae=home_mae,
        away_mae=away_mae,
        home_rmse=home_rmse,
        away_rmse=away_rmse,
        mean_joint_poisson_nll=mean_nll,
    )


def _benchmark(rows: Sequence[_EvaluationRow], comparator_id: str) -> BenchmarkComparison:
    candidate_values: list[float] = []
    comparator_values: list[float] = []
    for item in rows:
        comparator = item.comparator_joint_nlls[comparator_id]
        if comparator is None:
            continue
        candidate_values.append(item.candidate_joint_nll)
        comparator_values.append(comparator)
    if not candidate_values:
        return BenchmarkComparison(
            benchmark_id=comparator_id,
            paired_fixture_count=0,
            candidate_mean_joint_nll=None,
            benchmark_mean_joint_nll=None,
            candidate_minus_benchmark_nll=None,
            result=None,
        )
    candidate = _mean(candidate_values, "paired candidate mean NLL")
    comparator = _mean(comparator_values, "paired comparator mean NLL")
    delta = _finite(candidate - comparator, "candidate minus comparator NLL")
    return BenchmarkComparison(
        benchmark_id=comparator_id,
        paired_fixture_count=len(candidate_values),
        candidate_mean_joint_nll=candidate,
        benchmark_mean_joint_nll=comparator,
        candidate_minus_benchmark_nll=delta,
        result=_comparison(delta),
    )


def _comparisons(rows: Sequence[_EvaluationRow]) -> tuple[BenchmarkComparison, ...]:
    return tuple(_benchmark(rows, comparator_id) for comparator_id in COMPARATOR_IDS)


def _group_summary(group_key: str, rows: Sequence[_EvaluationRow]) -> SuccessorGroupSummary:
    return SuccessorGroupSummary(
        group_key=group_key,
        fixture_count=len(rows),
        candidate_mean_joint_nll=_mean(
            [item.candidate_joint_nll for item in rows], "group candidate mean NLL"
        ),
        comparisons=_comparisons(rows),
    )


def _breakdown(
    rows: Sequence[_EvaluationRow], attribute: str
) -> tuple[SuccessorGroupSummary, ...]:
    grouped: dict[str, list[_EvaluationRow]] = {}
    for item in rows:
        key = getattr(item.fixture, attribute)
        if type(key) is not str or not key:
            raise _error(f"{attribute} must be exact non-empty grouping key")
        grouped.setdefault(key, []).append(item)
    return tuple(_group_summary(key, grouped[key]) for key in sorted(grouped))


def _calibration(
    rows: Sequence[_EvaluationRow], side: str
) -> tuple[CalibrationBin, ...]:
    if side not in {"home", "away"}:
        raise _error("calibration side must be home or away")
    bins: list[CalibrationBin] = []
    for lower, upper in CALIBRATION_BINS:
        selected: list[tuple[float, int]] = []
        for item in rows:
            predicted = item.home_rate if side == "home" else item.away_rate
            observed = item.fixture.home_goals if side == "home" else item.fixture.away_goals
            if predicted >= lower and (upper is None or predicted < upper):
                selected.append((predicted, observed))
        if not selected:
            bins.append(
                CalibrationBin(
                    lower=lower,
                    upper=upper,
                    count=0,
                    mean_predicted_goals=None,
                    mean_observed_goals=None,
                    calibration_error=None,
                )
            )
            continue
        predicted_mean = _mean(
            [item[0] for item in selected], "calibration predicted mean"
        )
        observed_mean = _mean(
            [float(item[1]) for item in selected], "calibration observed mean"
        )
        bins.append(
            CalibrationBin(
                lower=lower,
                upper=upper,
                count=len(selected),
                mean_predicted_goals=predicted_mean,
                mean_observed_goals=observed_mean,
                calibration_error=_finite(
                    predicted_mean - observed_mean, "calibration error"
                ),
            )
        )
    return tuple(bins)


def _season_counts(fixtures: Sequence[HistoricalReplayFixture]) -> Mapping[str, int]:
    counts: dict[str, int] = {}
    for fixture in fixtures:
        counts[fixture.season] = counts.get(fixture.season, 0) + 1
    return types.MappingProxyType(dict(sorted(counts.items())))


def fit_historical_expected_goals_successor_fixture_set(
    *,
    protocol: HistoricalExpectedGoalsSuccessorProtocol,
    fixtures: Sequence[HistoricalReplayFixture],
) -> SuccessorFitEvaluation:
    """Execute the frozen math on exact fixtures without claiming source ancestry.

    This is the synthetic/adversarial test seam.  Real evidence must use the
    high-level candidate builder below, which fully revalidates PR69/70 ancestry.
    """

    if type(protocol) is not HistoricalExpectedGoalsSuccessorProtocol:
        raise _error("protocol must be exact HistoricalExpectedGoalsSuccessorProtocol")
    if type(fixtures) not in (tuple, list) or not fixtures:
        raise _error("fixtures must be a non-empty exact sequence")
    if tuple(protocol.evaluation.legacy_comparators) != COMPARATOR_IDS:
        raise _error("protocol comparator contract differs from fitter")
    if protocol.fitting.algorithm != TRAINING_ENGINE_ID:
        raise _error("protocol training engine differs from fitter")

    detached = tuple(fixtures)
    if any(type(item) is not HistoricalReplayFixture for item in detached):
        raise _error("fixtures must contain exact HistoricalReplayFixture values")
    identifiers = [item.fixture_identifier for item in detached]
    if len(set(identifiers)) != len(identifiers):
        raise _error("successor fixture identifiers must be globally unique")
    training = _ordered_eligible(protocol, detached, protocol.train_seasons)
    evaluation = _ordered_eligible(protocol, detached, protocol.evaluation_seasons)
    training_counts = _season_counts(training)
    evaluation_counts = _season_counts(evaluation)
    if set(training_counts) != set(protocol.train_seasons):
        raise _error("every frozen training season must retain eligible fixtures")
    if set(evaluation_counts) != set(protocol.evaluation_seasons):
        raise _error("every frozen evaluation season must retain eligible fixtures")

    home_fit = _fit_response(
        protocol=protocol,
        fixtures=training,
        response="HOME_GOALS",
    )
    away_fit = _fit_response(
        protocol=protocol,
        fixtures=training,
        response="AWAY_GOALS",
    )
    rows = _evaluation_rows(
        protocol=protocol,
        all_fixtures=detached,
        evaluation_fixtures=evaluation,
        home_fit=home_fit,
        away_fit=away_fit,
    )
    metrics = _metrics(rows)
    return SuccessorFitEvaluation(
        training_fixture_count=len(training),
        evaluation_fixture_count=len(evaluation),
        training_season_counts=training_counts,
        evaluation_season_counts=evaluation_counts,
        home_fit=home_fit,
        away_fit=away_fit,
        metrics=metrics,
        comparisons=_comparisons(rows),
        season_breakdown=_breakdown(rows, "season"),
        league_breakdown=_breakdown(rows, "identity_league"),
        home_calibration=_calibration(rows, "home"),
        away_calibration=_calibration(rows, "away"),
    )


def build_historical_expected_goals_successor_candidate(
    *,
    source_inputs: Sequence[HistoricalReplaySourceInput],
    corpus: HistoricalReplayCorpus,
    corpus_bytes: bytes,
    receipt_bytes: bytes,
    protocol: HistoricalExpectedGoalsSuccessorProtocol,
    protocol_bytes: bytes,
) -> HistoricalExpectedGoalsSuccessorCandidate:
    """Fully bind source evidence and execute the frozen successor protocol."""

    try:
        revalidate_historical_expected_goals_successor_protocol(
            receipt_bytes=receipt_bytes,
            protocol=protocol,
            protocol_bytes=protocol_bytes,
        )
    except (HistoricalExpectedGoalsSuccessorProtocolError, TypeError, ValueError) as exc:
        raise _error("frozen PR72 protocol revalidation failed") from exc
    try:
        rebuilt = revalidate_historical_model_feature_replay_corpus(
            source_inputs=source_inputs,
            corpus=corpus,
            corpus_bytes=corpus_bytes,
        )
    except (HistoricalModelFeatureReplayCandidateError, TypeError, ValueError) as exc:
        raise _error("PR69 source-byte replay revalidation failed") from exc

    rebuilt_bytes = canonical_historical_model_feature_replay_corpus_bytes(rebuilt)
    if _sha256(rebuilt_bytes) != protocol.pr69_canonical_sha256:
        raise _error("PR69 canonical replay SHA differs from frozen protocol")
    if rebuilt.source_corpus_sha256 != protocol.source_corpus_sha256:
        raise _error("PR69 source corpus SHA differs from frozen protocol")

    try:
        pr70 = build_historical_expected_goals_component_validation(
            source_inputs=source_inputs,
            corpus=rebuilt,
            corpus_bytes=rebuilt_bytes,
        )
    except HistoricalExpectedGoalsComponentValidationError as exc:
        raise _error("PR70 reconstruction failed") from exc
    pr70_bytes = canonical_historical_expected_goals_component_validation_bytes(pr70)
    if _sha256(pr70_bytes) != protocol.pr70_validation_sha256:
        raise _error("PR70 validation SHA differs from frozen protocol")

    fit_evaluation = fit_historical_expected_goals_successor_fixture_set(
        protocol=protocol,
        fixtures=rebuilt.fixtures,
    )
    return HistoricalExpectedGoalsSuccessorCandidate(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        candidate_scope=CANDIDATE_SCOPE,
        evidence_receipt_sha256=protocol.evidence_receipt_sha256,
        protocol_id=protocol.protocol_id,
        protocol_sha256=sha256_historical_expected_goals_successor_protocol(protocol),
        protocol_size=len(protocol_bytes),
        source_pr69_dataset_name=PR69_DATASET_NAME,
        source_pr69_sha256=_sha256(rebuilt_bytes),
        source_pr69_size=len(rebuilt_bytes),
        source_corpus_sha256=rebuilt.source_corpus_sha256,
        source_pr70_validation_sha256=_sha256(pr70_bytes),
        source_pr70_validation_size=len(pr70_bytes),
        evaluation_label=protocol.evaluation_label,
        elo_initialization_semantics=protocol.elo_initialization_semantics,
        fatigue_pr31_semantic_equivalence=protocol.fatigue_pr31_semantic_equivalence,
        training_engine_id=protocol.fitting.algorithm,
        training_executed=True,
        fit_evaluation=fit_evaluation,
        historical_freshness_regime_reconstructed=False,
        safety=_default_safety(),
    )


def historical_expected_goals_successor_candidate_to_dict(value: Any) -> dict[str, Any]:
    if type(value) is not HistoricalExpectedGoalsSuccessorCandidate:
        raise _error("value must be exact HistoricalExpectedGoalsSuccessorCandidate")
    return value.to_dict()


def canonical_historical_expected_goals_successor_candidate_bytes(value: Any) -> bytes:
    return _canonical_json_bytes(historical_expected_goals_successor_candidate_to_dict(value))


def sha256_historical_expected_goals_successor_candidate(value: Any) -> str:
    return _sha256(canonical_historical_expected_goals_successor_candidate_bytes(value))


def revalidate_historical_expected_goals_successor_candidate(
    *,
    source_inputs: Sequence[HistoricalReplaySourceInput],
    corpus: HistoricalReplayCorpus,
    corpus_bytes: bytes,
    receipt_bytes: bytes,
    protocol: HistoricalExpectedGoalsSuccessorProtocol,
    protocol_bytes: bytes,
    candidate: HistoricalExpectedGoalsSuccessorCandidate,
    candidate_bytes: bytes,
) -> HistoricalExpectedGoalsSuccessorCandidate:
    """Rebuild complete ancestry, refit, reevaluate, and require exact byte parity."""

    if type(candidate) is not HistoricalExpectedGoalsSuccessorCandidate:
        raise _error("candidate must be exact HistoricalExpectedGoalsSuccessorCandidate")
    if type(candidate_bytes) is not bytes or not candidate_bytes:
        raise _error("candidate_bytes must be exact non-empty immutable bytes")
    supplied = canonical_historical_expected_goals_successor_candidate_bytes(candidate)
    rebuilt = build_historical_expected_goals_successor_candidate(
        source_inputs=source_inputs,
        corpus=corpus,
        corpus_bytes=corpus_bytes,
        receipt_bytes=receipt_bytes,
        protocol=protocol,
        protocol_bytes=protocol_bytes,
    )
    exact = canonical_historical_expected_goals_successor_candidate_bytes(rebuilt)
    if supplied != exact:
        raise _error("supplied successor candidate differs from exact evidence rebuild")
    if candidate_bytes != exact:
        raise _error("candidate_bytes are not exact canonical successor bytes")
    return rebuilt


__all__ = [
    "CANDIDATE_SCOPE",
    "COMPARATOR_IDS",
    "CONSTANT_COMPARATOR_ID",
    "DATASET_NAME",
    "ELO_COMPARATOR_ID",
    "FORM_COMPARATOR_ID",
    "ROLLING_COMPARATOR_ID",
    "SCHEMA_VERSION",
    "TRAINING_ENGINE_ID",
    "HistoricalExpectedGoalsSuccessorCandidate",
    "HistoricalExpectedGoalsSuccessorCandidateError",
    "SuccessorFitEvaluation",
    "SuccessorGroupSummary",
    "SuccessorModelFit",
    "build_historical_expected_goals_successor_candidate",
    "canonical_historical_expected_goals_successor_candidate_bytes",
    "fit_historical_expected_goals_successor_fixture_set",
    "historical_expected_goals_successor_candidate_to_dict",
    "revalidate_historical_expected_goals_successor_candidate",
    "sha256_historical_expected_goals_successor_candidate",
]
