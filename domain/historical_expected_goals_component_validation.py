"""Retrospective, research-only validation of PR69 historical goal-rate components.

This boundary consumes an exact PR69 historical replay rebuilt from preserved
football-data.co.uk source bytes. It evaluates the two frozen PR68 formula
components separately because historical live-data freshness was not retained.
It does not reconstruct a historical regime, run a score matrix, infer market
probabilities, consume prices, or authorize production/betting use.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import math
import types
from collections.abc import Mapping, Sequence
from typing import Any

from domain.fixture_model_features import ModelFeatureId
from domain.fotmob_reviewed_match_details_expected_goals_transform_candidate import (
    TRANSFORM_ID,
    canonical_legacy_expected_goals_transform_specification_bytes,
    legacy_expected_goals_transform_specification,
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
DATASET_NAME = "athena-historical-expected-goals-component-validation-v1"
VALIDATION_SCOPE = "RETROSPECTIVE_PR69_COMPONENT_VALIDATION_RESEARCH_ONLY"
VALIDATION_SPEC_SCHEMA_VERSION = 1
VALIDATION_SPEC_ID = "HISTORICAL_EXPECTED_GOALS_COMPONENT_VALIDATION_SPEC_V1"
SCORING_RULE_ID = "INDEPENDENT_POISSON_JOINT_NLL_WITH_LGAMMA_V1"
CONSTANT_BASELINE_ID = "PR68_FROZEN_HOME_AWAY_BASELINE_V1"
ROLLING_BASELINE_ID = "STRICT_PREMATCH_ROLLING_IDENTITY_LEAGUE_MEAN_V1"
CALIBRATION_SPEC_ID = "FIXED_GOAL_RATE_BINS_V1"
_CALIBRATION_BOUNDS: tuple[tuple[float, float | None], ...] = (
    (0.0, 0.5),
    (0.5, 1.0),
    (1.0, 1.5),
    (1.5, 2.0),
    (2.0, 2.5),
    (2.5, 3.0),
    (3.0, None),
)
_SAFETY_KEYS = frozenset(
    {
        "historical_component_validation_approved",
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


class HistoricalExpectedGoalsComponentValidationError(ValueError):
    """Raised when retrospective component evidence is not exact/reproducible."""


class HistoricalExpectedGoalsComponent(str, enum.Enum):
    FORM_COMPONENT = "FORM_COMPONENT"
    ELO_FALLBACK_COMPONENT = "ELO_FALLBACK_COMPONENT"


class ComparisonResult(str, enum.Enum):
    BETTER = "BETTER"
    WORSE = "WORSE"
    EXACT_TIE = "EXACT_TIE"


def _error(message: str) -> HistoricalExpectedGoalsComponentValidationError:
    return HistoricalExpectedGoalsComponentValidationError(message)


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
        raise _error("historical component validation serialization failed") from exc
    return (payload + "\n").encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _finite(value: Any, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise _error(f"{label} must be a finite numeric value")
    return float(value)


def _nonnegative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise _error(f"{label} must be an exact non-negative integer")
    return value


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise _error(f"{label} must be an exact positive integer")
    return value


def _text(value: Any, label: str, maximum: int = 4096) -> str:
    if type(value) is not str or not value or value != value.strip() or len(value) > maximum:
        raise _error(f"{label} must be a non-empty exact trimmed string")
    return value


def _default_safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise _error("validation safety keys mismatch")
    if any(type(item) is not bool or item is not False for item in value.values()):
        raise _error("all validation safety values must be exact bool False")
    return _default_safety()


def _comparison(delta: float) -> ComparisonResult:
    value = _finite(delta, "paired NLL delta")
    if value < 0.0:
        return ComparisonResult.BETTER
    if value > 0.0:
        return ComparisonResult.WORSE
    return ComparisonResult.EXACT_TIE


@dataclasses.dataclass(frozen=True)
class HistoricalExpectedGoalsValidationSpecification:
    specification_id: str
    schema_version: int
    scoring_rule_id: str
    constant_baseline_id: str
    rolling_baseline_id: str
    calibration_spec_id: str
    calibration_bounds: tuple[tuple[float, float | None], ...]
    retrospective_only: bool
    historical_freshness_regime_reconstructed: bool

    def __post_init__(self) -> None:
        if self.specification_id != VALIDATION_SPEC_ID or self.schema_version != VALIDATION_SPEC_SCHEMA_VERSION:
            raise _error("validation specification identity mismatch")
        if (
            self.scoring_rule_id != SCORING_RULE_ID
            or self.constant_baseline_id != CONSTANT_BASELINE_ID
            or self.rolling_baseline_id != ROLLING_BASELINE_ID
            or self.calibration_spec_id != CALIBRATION_SPEC_ID
        ):
            raise _error("validation specification method identity mismatch")
        if self.calibration_bounds != _CALIBRATION_BOUNDS:
            raise _error("validation calibration bounds differ from frozen specification")
        if type(self.retrospective_only) is not bool or self.retrospective_only is not True:
            raise _error("validation specification must remain retrospective only")
        if (
            type(self.historical_freshness_regime_reconstructed) is not bool
            or self.historical_freshness_regime_reconstructed is not False
        ):
            raise _error("historical freshness regime must remain unreconstructed")

    def to_dict(self) -> dict[str, Any]:
        return {
            "specification_id": self.specification_id,
            "schema_version": self.schema_version,
            "scoring_rule_id": self.scoring_rule_id,
            "constant_baseline_id": self.constant_baseline_id,
            "rolling_baseline_id": self.rolling_baseline_id,
            "calibration_spec_id": self.calibration_spec_id,
            "calibration_bounds": [
                {"lower": lower, "upper": upper} for lower, upper in self.calibration_bounds
            ],
            "retrospective_only": self.retrospective_only,
            "historical_freshness_regime_reconstructed": self.historical_freshness_regime_reconstructed,
        }


def historical_expected_goals_validation_specification() -> HistoricalExpectedGoalsValidationSpecification:
    return HistoricalExpectedGoalsValidationSpecification(
        specification_id=VALIDATION_SPEC_ID,
        schema_version=VALIDATION_SPEC_SCHEMA_VERSION,
        scoring_rule_id=SCORING_RULE_ID,
        constant_baseline_id=CONSTANT_BASELINE_ID,
        rolling_baseline_id=ROLLING_BASELINE_ID,
        calibration_spec_id=CALIBRATION_SPEC_ID,
        calibration_bounds=_CALIBRATION_BOUNDS,
        retrospective_only=True,
        historical_freshness_regime_reconstructed=False,
    )


def canonical_historical_expected_goals_validation_specification_bytes(value: Any) -> bytes:
    if type(value) is not HistoricalExpectedGoalsValidationSpecification:
        raise _error("value must be exact historical validation specification")
    return _canonical_json_bytes(dataclasses.replace(value).to_dict())


@dataclasses.dataclass(frozen=True)
class CalibrationBin:
    lower: float
    upper: float | None
    count: int
    mean_predicted_goals: float | None
    mean_observed_goals: float | None
    calibration_error: float | None

    def __post_init__(self) -> None:
        lower = _finite(self.lower, "calibration lower bound")
        if lower < 0.0:
            raise _error("calibration lower bound must be non-negative")
        upper = None if self.upper is None else _finite(self.upper, "calibration upper bound")
        if upper is not None and upper <= lower:
            raise _error("calibration upper bound must exceed lower bound")
        count = _nonnegative_int(self.count, "calibration count")
        values = (self.mean_predicted_goals, self.mean_observed_goals, self.calibration_error)
        if count == 0:
            if any(item is not None for item in values):
                raise _error("empty calibration bin must use null means/errors")
        else:
            if any(item is None for item in values):
                raise _error("populated calibration bin must retain finite means/errors")
            predicted = _finite(self.mean_predicted_goals, "mean predicted goals")
            observed = _finite(self.mean_observed_goals, "mean observed goals")
            error = _finite(self.calibration_error, "calibration error")
            if error != predicted - observed:
                raise _error("calibration error must equal predicted minus observed")

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class GoalRateMetrics:
    fixture_count: int
    mean_predicted_home_goals: float
    mean_actual_home_goals: float
    home_bias: float
    mean_predicted_away_goals: float
    mean_actual_away_goals: float
    away_bias: float
    home_mae: float
    away_mae: float
    home_rmse: float
    away_rmse: float
    mean_joint_poisson_nll: float

    def __post_init__(self) -> None:
        _positive_int(self.fixture_count, "metrics fixture_count")
        values = (
            self.mean_predicted_home_goals,
            self.mean_actual_home_goals,
            self.home_bias,
            self.mean_predicted_away_goals,
            self.mean_actual_away_goals,
            self.away_bias,
            self.home_mae,
            self.away_mae,
            self.home_rmse,
            self.away_rmse,
            self.mean_joint_poisson_nll,
        )
        for index, value in enumerate(values):
            _finite(value, f"goal-rate metric {index}")
        if self.home_bias != self.mean_predicted_home_goals - self.mean_actual_home_goals:
            raise _error("home bias must equal predicted minus actual")
        if self.away_bias != self.mean_predicted_away_goals - self.mean_actual_away_goals:
            raise _error("away bias must equal predicted minus actual")
        if min(self.home_mae, self.away_mae, self.home_rmse, self.away_rmse) < 0.0:
            raise _error("error metrics must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class BenchmarkComparison:
    benchmark_id: str
    paired_fixture_count: int
    candidate_mean_joint_nll: float
    benchmark_mean_joint_nll: float
    candidate_minus_benchmark_nll: float
    result: ComparisonResult

    def __post_init__(self) -> None:
        _text(self.benchmark_id, "benchmark_id")
        _positive_int(self.paired_fixture_count, "paired_fixture_count")
        candidate = _finite(self.candidate_mean_joint_nll, "candidate mean NLL")
        benchmark = _finite(self.benchmark_mean_joint_nll, "benchmark mean NLL")
        delta = _finite(self.candidate_minus_benchmark_nll, "candidate minus benchmark NLL")
        if delta != candidate - benchmark:
            raise _error("benchmark delta must equal candidate minus benchmark")
        if self.result is not _comparison(delta):
            raise _error("benchmark comparison result differs from delta sign")

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "paired_fixture_count": self.paired_fixture_count,
            "candidate_mean_joint_nll": self.candidate_mean_joint_nll,
            "benchmark_mean_joint_nll": self.benchmark_mean_joint_nll,
            "candidate_minus_benchmark_nll": self.candidate_minus_benchmark_nll,
            "result": self.result.value,
        }


@dataclasses.dataclass(frozen=True)
class GroupValidationSummary:
    group_key: str
    fixture_count: int
    candidate_mean_joint_nll: float
    constant_baseline_mean_joint_nll: float
    candidate_minus_constant_nll: float
    rolling_paired_fixture_count: int
    rolling_candidate_mean_joint_nll: float | None
    rolling_baseline_mean_joint_nll: float | None
    candidate_minus_rolling_nll: float | None

    def __post_init__(self) -> None:
        _text(self.group_key, "group_key")
        _positive_int(self.fixture_count, "group fixture_count")
        candidate = _finite(self.candidate_mean_joint_nll, "group candidate NLL")
        constant = _finite(self.constant_baseline_mean_joint_nll, "group constant NLL")
        delta = _finite(self.candidate_minus_constant_nll, "group constant delta")
        if delta != candidate - constant:
            raise _error("group constant delta mismatch")
        paired = _nonnegative_int(self.rolling_paired_fixture_count, "group rolling paired count")
        rolling_values = (
            self.rolling_candidate_mean_joint_nll,
            self.rolling_baseline_mean_joint_nll,
            self.candidate_minus_rolling_nll,
        )
        if paired == 0:
            if any(item is not None for item in rolling_values):
                raise _error("group without rolling pairs must use null rolling metrics")
        else:
            if any(item is None for item in rolling_values):
                raise _error("group with rolling pairs must retain rolling metrics")
            rolling_candidate = _finite(self.rolling_candidate_mean_joint_nll, "group rolling candidate NLL")
            rolling_baseline = _finite(self.rolling_baseline_mean_joint_nll, "group rolling baseline NLL")
            rolling_delta = _finite(self.candidate_minus_rolling_nll, "group rolling delta")
            if rolling_delta != rolling_candidate - rolling_baseline:
                raise _error("group rolling delta mismatch")

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class ComponentValidationSummary:
    component: HistoricalExpectedGoalsComponent
    metrics: GoalRateMetrics
    constant_baseline: BenchmarkComparison
    rolling_league_baseline: BenchmarkComparison
    season_breakdown: tuple[GroupValidationSummary, ...]
    league_breakdown: tuple[GroupValidationSummary, ...]
    home_calibration: tuple[CalibrationBin, ...]
    away_calibration: tuple[CalibrationBin, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.component, HistoricalExpectedGoalsComponent):
            raise _error("component must be exact HistoricalExpectedGoalsComponent")
        if type(self.metrics) is not GoalRateMetrics:
            raise _error("component metrics must be exact GoalRateMetrics")
        if type(self.constant_baseline) is not BenchmarkComparison or self.constant_baseline.benchmark_id != CONSTANT_BASELINE_ID:
            raise _error("component constant baseline identity mismatch")
        if type(self.rolling_league_baseline) is not BenchmarkComparison or self.rolling_league_baseline.benchmark_id != ROLLING_BASELINE_ID:
            raise _error("component rolling baseline identity mismatch")
        if self.constant_baseline.paired_fixture_count != self.metrics.fixture_count:
            raise _error("constant baseline must use exact component eligible fixture set")
        for groups, label in ((self.season_breakdown, "season"), (self.league_breakdown, "league")):
            if type(groups) is not tuple or not groups or any(type(item) is not GroupValidationSummary for item in groups):
                raise _error(f"{label} breakdown must be a non-empty tuple of exact summaries")
            if groups != tuple(sorted(groups, key=lambda item: item.group_key)):
                raise _error(f"{label} breakdown must be deterministically sorted")
            if sum(item.fixture_count for item in groups) != self.metrics.fixture_count:
                raise _error(f"{label} breakdown fixture counts must reconcile to aggregate")
        for bins, label in ((self.home_calibration, "home"), (self.away_calibration, "away")):
            if type(bins) is not tuple or len(bins) != len(_CALIBRATION_BOUNDS):
                raise _error(f"{label} calibration must retain every frozen bin")
            if tuple((item.lower, item.upper) for item in bins) != _CALIBRATION_BOUNDS:
                raise _error(f"{label} calibration bounds mismatch")
            if sum(item.count for item in bins) != self.metrics.fixture_count:
                raise _error(f"{label} calibration counts must reconcile to aggregate")

    def to_dict(self) -> dict[str, Any]:
        return {
            "component": self.component.value,
            "metrics": self.metrics.to_dict(),
            "constant_baseline": self.constant_baseline.to_dict(),
            "rolling_league_baseline": self.rolling_league_baseline.to_dict(),
            "season_breakdown": [item.to_dict() for item in self.season_breakdown],
            "league_breakdown": [item.to_dict() for item in self.league_breakdown],
            "home_calibration": [item.to_dict() for item in self.home_calibration],
            "away_calibration": [item.to_dict() for item in self.away_calibration],
        }


@dataclasses.dataclass(frozen=True)
class HistoricalExpectedGoalsComponentValidation:
    schema_version: int
    dataset_name: str
    validation_scope: str
    source_pr69_dataset_name: str
    source_pr69_sha256: str
    source_pr69_size: int
    source_corpus_sha256: str
    target_pr68_transform_id: str
    target_pr68_transform_spec_sha256: str
    target_pr68_transform_spec_size: int
    validation_spec_id: str
    validation_spec_sha256: str
    validation_spec_size: int
    scoring_rule_id: str
    constant_baseline_id: str
    rolling_baseline_id: str
    calibration_spec_id: str
    historical_freshness_regime_reconstructed: bool
    form_component_summary: ComponentValidationSummary
    elo_fallback_component_summary: ComponentValidationSummary
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION or type(self.schema_version) is not int:
            raise _error("validation schema_version mismatch")
        if self.dataset_name != DATASET_NAME or self.validation_scope != VALIDATION_SCOPE:
            raise _error("validation dataset/scope identity mismatch")
        if self.source_pr69_dataset_name != PR69_DATASET_NAME:
            raise _error("validation source PR69 dataset identity mismatch")
        for value, label in (
            (self.source_pr69_sha256, "source_pr69_sha256"),
            (self.source_corpus_sha256, "source_corpus_sha256"),
            (self.target_pr68_transform_spec_sha256, "target_pr68_transform_spec_sha256"),
            (self.validation_spec_sha256, "validation_spec_sha256"),
        ):
            if type(value) is not str or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise _error(f"{label} must be exact lowercase SHA-256")
        _positive_int(self.source_pr69_size, "source_pr69_size")
        _positive_int(self.target_pr68_transform_spec_size, "target_pr68_transform_spec_size")
        _positive_int(self.validation_spec_size, "validation_spec_size")
        if self.target_pr68_transform_id != TRANSFORM_ID:
            raise _error("validation target PR68 transform identity mismatch")
        spec = legacy_expected_goals_transform_specification()
        spec_bytes = canonical_legacy_expected_goals_transform_specification_bytes(spec)
        if self.target_pr68_transform_spec_sha256 != _sha256(spec_bytes) or self.target_pr68_transform_spec_size != len(spec_bytes):
            raise _error("validation target PR68 transform specification mismatch")
        validation_spec = historical_expected_goals_validation_specification()
        validation_spec_bytes = canonical_historical_expected_goals_validation_specification_bytes(validation_spec)
        if (
            self.validation_spec_id != VALIDATION_SPEC_ID
            or self.validation_spec_sha256 != _sha256(validation_spec_bytes)
            or self.validation_spec_size != len(validation_spec_bytes)
        ):
            raise _error("validation specification binding mismatch")
        if (
            self.scoring_rule_id != SCORING_RULE_ID
            or self.constant_baseline_id != CONSTANT_BASELINE_ID
            or self.rolling_baseline_id != ROLLING_BASELINE_ID
            or self.calibration_spec_id != CALIBRATION_SPEC_ID
        ):
            raise _error("validation method identity mismatch")
        if (
            type(self.historical_freshness_regime_reconstructed) is not bool
            or self.historical_freshness_regime_reconstructed is not False
        ):
            raise _error("validation must not assign a historical freshness regime")
        if (
            type(self.form_component_summary) is not ComponentValidationSummary
            or self.form_component_summary.component is not HistoricalExpectedGoalsComponent.FORM_COMPONENT
        ):
            raise _error("FORM component summary mismatch")
        if (
            type(self.elo_fallback_component_summary) is not ComponentValidationSummary
            or self.elo_fallback_component_summary.component is not HistoricalExpectedGoalsComponent.ELO_FALLBACK_COMPONENT
        ):
            raise _error("ELO component summary mismatch")
        object.__setattr__(self, "safety", _validate_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "validation_scope": self.validation_scope,
            "source_pr69_dataset_name": self.source_pr69_dataset_name,
            "source_pr69_sha256": self.source_pr69_sha256,
            "source_pr69_size": self.source_pr69_size,
            "source_corpus_sha256": self.source_corpus_sha256,
            "target_pr68_transform_id": self.target_pr68_transform_id,
            "target_pr68_transform_spec_sha256": self.target_pr68_transform_spec_sha256,
            "target_pr68_transform_spec_size": self.target_pr68_transform_spec_size,
            "validation_spec_id": self.validation_spec_id,
            "validation_spec_sha256": self.validation_spec_sha256,
            "validation_spec_size": self.validation_spec_size,
            "scoring_rule_id": self.scoring_rule_id,
            "constant_baseline_id": self.constant_baseline_id,
            "rolling_baseline_id": self.rolling_baseline_id,
            "calibration_spec_id": self.calibration_spec_id,
            "historical_freshness_regime_reconstructed": self.historical_freshness_regime_reconstructed,
            "form_component_summary": self.form_component_summary.to_dict(),
            "elo_fallback_component_summary": self.elo_fallback_component_summary.to_dict(),
            "safety": dict(self.safety),
        }


def poisson_nll(observed_goals: int, rate: float) -> float:
    """Absolute Poisson negative log-likelihood including log-factorial term."""

    if type(observed_goals) is not int or observed_goals < 0:
        raise _error("observed_goals must be an exact non-negative integer")
    value = _finite(rate, "Poisson rate")
    if value <= 0.0:
        raise _error("Poisson rate must be strictly positive")
    result = value - observed_goals * math.log(value) + math.lgamma(observed_goals + 1)
    return _finite(result, "Poisson negative log-likelihood")


def _feature_value(fixture: HistoricalReplayFixture, feature_id: ModelFeatureId) -> float:
    matches = [item for item in fixture.features if item.feature_id is feature_id]
    if len(matches) != 1:
        raise _error("historical replay fixture must contain each exact feature once")
    item = matches[0]
    if item.status is not HistoricalFeatureReplayStatus.AVAILABLE_RESEARCH_REPLAY or item.value is None:
        raise _error("component feature value requested from non-available replay status")
    return _finite(item.value, f"{feature_id.value} replay value")


def _candidate_rates(
    fixture: HistoricalReplayFixture,
    component: HistoricalExpectedGoalsComponent,
) -> tuple[float, float]:
    specification = legacy_expected_goals_transform_specification()
    fatigue = _feature_value(fixture, ModelFeatureId.FATIGUE)
    if component is HistoricalExpectedGoalsComponent.FORM_COMPONENT:
        if fixture.form_path_component_eligible is not True:
            raise _error("FORM rate requested for ineligible historical fixture")
        home_raw = _feature_value(fixture, ModelFeatureId.HOME_FORM)
        away_raw = _feature_value(fixture, ModelFeatureId.AWAY_FORM)
    elif component is HistoricalExpectedGoalsComponent.ELO_FALLBACK_COMPONENT:
        if fixture.elo_fallback_component_eligible is not True:
            raise _error("ELO rate requested for ineligible historical fixture")
        home_elo = _feature_value(fixture, ModelFeatureId.HOME_ELO)
        away_elo = _feature_value(fixture, ModelFeatureId.AWAY_ELO)
        home_raw = 0.50 + ((home_elo - specification.elo_center) / specification.elo_divisor)
        away_raw = 0.50 + ((away_elo - specification.elo_center) / specification.elo_divisor)
        home_raw = max(specification.raw_min, min(specification.raw_max, home_raw))
        away_raw = max(specification.raw_min, min(specification.raw_max, away_raw))
    else:  # pragma: no cover - enum exhaustiveness guard
        raise _error("unknown historical expected-goals component")
    base_home = specification.home_baseline + (home_raw - away_raw) - (fatigue * specification.fatigue_coefficient)
    base_away = specification.away_baseline + (away_raw - home_raw) + (fatigue * specification.fatigue_coefficient)
    home_rate = max(specification.minimum_rate, round(base_home, specification.decimal_rounding_places))
    away_rate = max(specification.minimum_rate, round(base_away, specification.decimal_rounding_places))
    return _finite(home_rate, "home component rate"), _finite(away_rate, "away component rate")


@dataclasses.dataclass(frozen=True)
class _Evaluation:
    fixture: HistoricalReplayFixture
    home_rate: float
    away_rate: float
    candidate_joint_nll: float
    constant_joint_nll: float
    rolling_home_rate: float | None
    rolling_away_rate: float | None
    rolling_joint_nll: float | None


def _rolling_rates(fixtures: Sequence[HistoricalReplayFixture]) -> Mapping[str, tuple[float, float] | None]:
    """Build strict prior league means in same-kickoff batches without leakage."""

    ordered = sorted(
        (fixture for fixture in fixtures if fixture.source_local_kickoff is not None),
        key=lambda fixture: (fixture.source_local_kickoff, fixture.fixture_identifier),
    )
    states: dict[str, list[int]] = {}
    result: dict[str, tuple[float, float] | None] = {
        fixture.fixture_identifier: None for fixture in fixtures
    }
    index = 0
    while index < len(ordered):
        kickoff = ordered[index].source_local_kickoff
        assert kickoff is not None
        end = index
        while end < len(ordered) and ordered[end].source_local_kickoff == kickoff:
            end += 1
        batch = ordered[index:end]
        for fixture in batch:
            state = states.get(fixture.identity_league)
            if state is None or state[0] == 0:
                result[fixture.fixture_identifier] = None
                continue
            count, home_total, away_total = state
            home_rate = home_total / count
            away_rate = away_total / count
            if home_rate > 0.0 and away_rate > 0.0 and math.isfinite(home_rate) and math.isfinite(away_rate):
                result[fixture.fixture_identifier] = (home_rate, away_rate)
            else:
                result[fixture.fixture_identifier] = None
        for fixture in batch:
            state = states.setdefault(fixture.identity_league, [0, 0, 0])
            state[0] += 1
            state[1] += fixture.home_goals
            state[2] += fixture.away_goals
        index = end
    return types.MappingProxyType(result)


def _metrics(evaluations: Sequence[_Evaluation]) -> GoalRateMetrics:
    if not evaluations:
        raise _error("component validation requires at least one eligible fixture")
    count = len(evaluations)
    predicted_home = sum(item.home_rate for item in evaluations) / count
    actual_home = sum(item.fixture.home_goals for item in evaluations) / count
    predicted_away = sum(item.away_rate for item in evaluations) / count
    actual_away = sum(item.fixture.away_goals for item in evaluations) / count
    home_mae = sum(abs(item.home_rate - item.fixture.home_goals) for item in evaluations) / count
    away_mae = sum(abs(item.away_rate - item.fixture.away_goals) for item in evaluations) / count
    home_rmse = math.sqrt(sum((item.home_rate - item.fixture.home_goals) ** 2 for item in evaluations) / count)
    away_rmse = math.sqrt(sum((item.away_rate - item.fixture.away_goals) ** 2 for item in evaluations) / count)
    mean_nll = sum(item.candidate_joint_nll for item in evaluations) / count
    return GoalRateMetrics(
        fixture_count=count,
        mean_predicted_home_goals=_finite(predicted_home, "mean predicted home goals"),
        mean_actual_home_goals=_finite(actual_home, "mean actual home goals"),
        home_bias=_finite(predicted_home - actual_home, "home bias"),
        mean_predicted_away_goals=_finite(predicted_away, "mean predicted away goals"),
        mean_actual_away_goals=_finite(actual_away, "mean actual away goals"),
        away_bias=_finite(predicted_away - actual_away, "away bias"),
        home_mae=_finite(home_mae, "home MAE"),
        away_mae=_finite(away_mae, "away MAE"),
        home_rmse=_finite(home_rmse, "home RMSE"),
        away_rmse=_finite(away_rmse, "away RMSE"),
        mean_joint_poisson_nll=_finite(mean_nll, "mean joint Poisson NLL"),
    )


def _benchmark(
    benchmark_id: str,
    candidate_nlls: Sequence[float],
    benchmark_nlls: Sequence[float],
) -> BenchmarkComparison:
    if not candidate_nlls or len(candidate_nlls) != len(benchmark_nlls):
        raise _error("benchmark comparison requires a non-empty exact paired sample")
    candidate = sum(candidate_nlls) / len(candidate_nlls)
    baseline = sum(benchmark_nlls) / len(benchmark_nlls)
    delta = candidate - baseline
    return BenchmarkComparison(
        benchmark_id=benchmark_id,
        paired_fixture_count=len(candidate_nlls),
        candidate_mean_joint_nll=_finite(candidate, "paired candidate mean NLL"),
        benchmark_mean_joint_nll=_finite(baseline, "paired benchmark mean NLL"),
        candidate_minus_benchmark_nll=_finite(delta, "paired NLL delta"),
        result=_comparison(delta),
    )


def _group_summary(group_key: str, evaluations: Sequence[_Evaluation]) -> GroupValidationSummary:
    candidate = sum(item.candidate_joint_nll for item in evaluations) / len(evaluations)
    constant = sum(item.constant_joint_nll for item in evaluations) / len(evaluations)
    paired = [item for item in evaluations if item.rolling_joint_nll is not None]
    if paired:
        rolling_candidate = sum(item.candidate_joint_nll for item in paired) / len(paired)
        rolling_baseline = sum(item.rolling_joint_nll for item in paired if item.rolling_joint_nll is not None) / len(paired)
        rolling_delta = rolling_candidate - rolling_baseline
    else:
        rolling_candidate = None
        rolling_baseline = None
        rolling_delta = None
    return GroupValidationSummary(
        group_key=group_key,
        fixture_count=len(evaluations),
        candidate_mean_joint_nll=_finite(candidate, "group candidate NLL"),
        constant_baseline_mean_joint_nll=_finite(constant, "group constant NLL"),
        candidate_minus_constant_nll=_finite(candidate - constant, "group constant delta"),
        rolling_paired_fixture_count=len(paired),
        rolling_candidate_mean_joint_nll=None if rolling_candidate is None else _finite(rolling_candidate, "group rolling candidate NLL"),
        rolling_baseline_mean_joint_nll=None if rolling_baseline is None else _finite(rolling_baseline, "group rolling baseline NLL"),
        candidate_minus_rolling_nll=None if rolling_delta is None else _finite(rolling_delta, "group rolling delta"),
    )


def _breakdown(evaluations: Sequence[_Evaluation], attribute: str) -> tuple[GroupValidationSummary, ...]:
    grouped: dict[str, list[_Evaluation]] = {}
    for item in evaluations:
        key = getattr(item.fixture, attribute)
        if type(key) is not str or not key:
            raise _error(f"{attribute} must be an exact non-empty grouping key")
        grouped.setdefault(key, []).append(item)
    return tuple(_group_summary(key, grouped[key]) for key in sorted(grouped))


def _calibration(evaluations: Sequence[_Evaluation], side: str) -> tuple[CalibrationBin, ...]:
    bins: list[CalibrationBin] = []
    for lower, upper in _CALIBRATION_BOUNDS:
        selected: list[tuple[float, int]] = []
        for item in evaluations:
            predicted = item.home_rate if side == "home" else item.away_rate
            observed = item.fixture.home_goals if side == "home" else item.fixture.away_goals
            if predicted >= lower and (upper is None or predicted < upper):
                selected.append((predicted, observed))
        if not selected:
            bins.append(CalibrationBin(lower=lower, upper=upper, count=0, mean_predicted_goals=None, mean_observed_goals=None, calibration_error=None))
            continue
        mean_predicted = sum(item[0] for item in selected) / len(selected)
        mean_observed = sum(item[1] for item in selected) / len(selected)
        bins.append(
            CalibrationBin(
                lower=lower,
                upper=upper,
                count=len(selected),
                mean_predicted_goals=_finite(mean_predicted, "calibration mean predicted"),
                mean_observed_goals=_finite(mean_observed, "calibration mean observed"),
                calibration_error=_finite(mean_predicted - mean_observed, "calibration error"),
            )
        )
    return tuple(bins)


def _component_summary(
    corpus: HistoricalReplayCorpus,
    component: HistoricalExpectedGoalsComponent,
    rolling: Mapping[str, tuple[float, float] | None],
) -> ComponentValidationSummary:
    specification = legacy_expected_goals_transform_specification()
    evaluations: list[_Evaluation] = []
    for fixture in corpus.fixtures:
        eligible = (
            fixture.form_path_component_eligible
            if component is HistoricalExpectedGoalsComponent.FORM_COMPONENT
            else fixture.elo_fallback_component_eligible
        )
        if not eligible:
            continue
        home_rate, away_rate = _candidate_rates(fixture, component)
        candidate_nll = poisson_nll(fixture.home_goals, home_rate) + poisson_nll(fixture.away_goals, away_rate)
        constant_nll = poisson_nll(fixture.home_goals, specification.home_baseline) + poisson_nll(fixture.away_goals, specification.away_baseline)
        rolling_rates = rolling.get(fixture.fixture_identifier)
        if rolling_rates is None:
            rolling_home = rolling_away = rolling_nll = None
        else:
            rolling_home, rolling_away = rolling_rates
            rolling_nll = poisson_nll(fixture.home_goals, rolling_home) + poisson_nll(fixture.away_goals, rolling_away)
        evaluations.append(
            _Evaluation(
                fixture=fixture,
                home_rate=home_rate,
                away_rate=away_rate,
                candidate_joint_nll=_finite(candidate_nll, "candidate joint NLL"),
                constant_joint_nll=_finite(constant_nll, "constant joint NLL"),
                rolling_home_rate=rolling_home,
                rolling_away_rate=rolling_away,
                rolling_joint_nll=None if rolling_nll is None else _finite(rolling_nll, "rolling joint NLL"),
            )
        )
    if not evaluations:
        raise _error(f"{component.value} has no eligible historical fixtures")
    metrics = _metrics(evaluations)
    constant = _benchmark(
        CONSTANT_BASELINE_ID,
        [item.candidate_joint_nll for item in evaluations],
        [item.constant_joint_nll for item in evaluations],
    )
    rolling_paired = [item for item in evaluations if item.rolling_joint_nll is not None]
    if not rolling_paired:
        raise _error(f"{component.value} has no paired rolling-league benchmark fixtures")
    rolling_summary = _benchmark(
        ROLLING_BASELINE_ID,
        [item.candidate_joint_nll for item in rolling_paired],
        [item.rolling_joint_nll for item in rolling_paired if item.rolling_joint_nll is not None],
    )
    return ComponentValidationSummary(
        component=component,
        metrics=metrics,
        constant_baseline=constant,
        rolling_league_baseline=rolling_summary,
        season_breakdown=_breakdown(evaluations, "season"),
        league_breakdown=_breakdown(evaluations, "identity_league"),
        home_calibration=_calibration(evaluations, "home"),
        away_calibration=_calibration(evaluations, "away"),
    )


def build_historical_expected_goals_component_validation(
    *,
    source_inputs: Sequence[HistoricalReplaySourceInput],
    corpus: HistoricalReplayCorpus,
    corpus_bytes: bytes,
) -> HistoricalExpectedGoalsComponentValidation:
    """Revalidate PR69 and produce deterministic retrospective component evidence."""

    try:
        rebuilt = revalidate_historical_model_feature_replay_corpus(
            source_inputs=source_inputs,
            corpus=corpus,
            corpus_bytes=corpus_bytes,
        )
    except (HistoricalModelFeatureReplayCandidateError, TypeError, ValueError, AttributeError) as exc:
        raise _error("PR69 historical replay revalidation failed") from exc
    rebuilt_bytes = canonical_historical_model_feature_replay_corpus_bytes(rebuilt)
    rolling = _rolling_rates(rebuilt.fixtures)
    pr68_spec = legacy_expected_goals_transform_specification()
    pr68_spec_bytes = canonical_legacy_expected_goals_transform_specification_bytes(pr68_spec)
    validation_spec = historical_expected_goals_validation_specification()
    validation_spec_bytes = canonical_historical_expected_goals_validation_specification_bytes(validation_spec)
    return HistoricalExpectedGoalsComponentValidation(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        validation_scope=VALIDATION_SCOPE,
        source_pr69_dataset_name=PR69_DATASET_NAME,
        source_pr69_sha256=_sha256(rebuilt_bytes),
        source_pr69_size=len(rebuilt_bytes),
        source_corpus_sha256=rebuilt.source_corpus_sha256,
        target_pr68_transform_id=TRANSFORM_ID,
        target_pr68_transform_spec_sha256=_sha256(pr68_spec_bytes),
        target_pr68_transform_spec_size=len(pr68_spec_bytes),
        validation_spec_id=VALIDATION_SPEC_ID,
        validation_spec_sha256=_sha256(validation_spec_bytes),
        validation_spec_size=len(validation_spec_bytes),
        scoring_rule_id=SCORING_RULE_ID,
        constant_baseline_id=CONSTANT_BASELINE_ID,
        rolling_baseline_id=ROLLING_BASELINE_ID,
        calibration_spec_id=CALIBRATION_SPEC_ID,
        historical_freshness_regime_reconstructed=False,
        form_component_summary=_component_summary(rebuilt, HistoricalExpectedGoalsComponent.FORM_COMPONENT, rolling),
        elo_fallback_component_summary=_component_summary(rebuilt, HistoricalExpectedGoalsComponent.ELO_FALLBACK_COMPONENT, rolling),
        safety=_default_safety(),
    )


def historical_expected_goals_component_validation_to_dict(value: Any) -> dict[str, Any]:
    if type(value) is not HistoricalExpectedGoalsComponentValidation:
        raise _error("value must be exact historical expected-goals component validation")
    return value.to_dict()


def canonical_historical_expected_goals_component_validation_bytes(value: Any) -> bytes:
    return _canonical_json_bytes(historical_expected_goals_component_validation_to_dict(value))


def sha256_historical_expected_goals_component_validation(value: Any) -> str:
    return _sha256(canonical_historical_expected_goals_component_validation_bytes(value))


def revalidate_historical_expected_goals_component_validation(
    *,
    source_inputs: Sequence[HistoricalReplaySourceInput],
    corpus: HistoricalReplayCorpus,
    corpus_bytes: bytes,
    validation: HistoricalExpectedGoalsComponentValidation,
    validation_bytes: bytes,
) -> HistoricalExpectedGoalsComponentValidation:
    """Fully replay PR69, recompute PR70 and reject coordinated/detached mutation."""

    if type(validation) is not HistoricalExpectedGoalsComponentValidation or type(validation_bytes) is not bytes:
        raise _error("validation and validation_bytes must be exact immutable artifact values")
    supplied = canonical_historical_expected_goals_component_validation_bytes(validation)
    rebuilt = build_historical_expected_goals_component_validation(
        source_inputs=source_inputs,
        corpus=corpus,
        corpus_bytes=corpus_bytes,
    )
    exact = canonical_historical_expected_goals_component_validation_bytes(rebuilt)
    if supplied != exact:
        raise _error("supplied validation differs from exact source-evidence rebuild")
    if validation_bytes != exact:
        raise _error("validation_bytes are not exact canonical validation bytes")
    return rebuilt


__all__ = [
    "CALIBRATION_SPEC_ID",
    "CONSTANT_BASELINE_ID",
    "DATASET_NAME",
    "ROLLING_BASELINE_ID",
    "SCHEMA_VERSION",
    "SCORING_RULE_ID",
    "VALIDATION_SCOPE",
    "VALIDATION_SPEC_ID",
    "BenchmarkComparison",
    "CalibrationBin",
    "ComparisonResult",
    "ComponentValidationSummary",
    "GoalRateMetrics",
    "GroupValidationSummary",
    "HistoricalExpectedGoalsComponent",
    "HistoricalExpectedGoalsComponentValidation",
    "HistoricalExpectedGoalsComponentValidationError",
    "HistoricalExpectedGoalsValidationSpecification",
    "build_historical_expected_goals_component_validation",
    "canonical_historical_expected_goals_component_validation_bytes",
    "canonical_historical_expected_goals_validation_specification_bytes",
    "historical_expected_goals_component_validation_to_dict",
    "historical_expected_goals_validation_specification",
    "poisson_nll",
    "revalidate_historical_expected_goals_component_validation",
    "sha256_historical_expected_goals_component_validation",
]
