"""Deterministic, research-only evaluator for the frozen PR75 protocol.

The public fixture-set seam is intentionally synthetic/adversarial. The
source-bound builder is separate and must be called with complete PR69--75
ancestry; this module never reads a cache, database, or network itself.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import types
from collections.abc import Mapping, Sequence
from typing import Any

from domain.historical_expected_goals_component_validation import (
    HistoricalExpectedGoalsComponent,
)
from domain.historical_expected_goals_successor_candidate import (
    HistoricalExpectedGoalsSuccessorCandidateError,
    _gradient_and_hessian,
    _legacy_rates,
    _model_rates,
    _ordered_eligible,
    _predictor_vector,
    _response_nll,
    _rounded_coefficients,
    _solve_linear_system,
    build_historical_expected_goals_successor_candidate,
    canonical_historical_expected_goals_successor_candidate_bytes,
    revalidate_historical_expected_goals_successor_candidate,
)
from domain.historical_expected_goals_successor_protocol import (
    HistoricalExpectedGoalsSuccessorProtocol,
)
from domain.historical_expected_goals_successor_robustness_protocol import (
    CLUSTER_KEYS,
    EVALUATION_FIXTURE_COUNT,
    IDENTITY_LEAGUES,
    PROTOCOL_ID,
    PR69_SOURCE_CORPUS_SHA256,
    PR74_RECEIPT_SHA256,
    SUCCESSOR_CANDIDATE_SHA256,
    SUCCESSOR_CANDIDATE_SIZE,
    HistoricalExpectedGoalsSuccessorRobustnessProtocol,
    revalidate_successor_robustness_protocol,
    sha256_successor_robustness_protocol,
)
from domain.historical_model_feature_replay_candidate import (
    HistoricalReplayCorpus,
    HistoricalReplaySourceInput,
    canonical_historical_model_feature_replay_corpus_bytes,
    revalidate_historical_model_feature_replay_corpus,
)


SCHEMA_VERSION = 1
DATASET_NAME = "athena-historical-expected-goals-successor-robustness-evaluation-v1"
EVALUATION_SCOPE = "POST_HOC_PR74_FOLLOWUP_RESEARCH_EVALUATION_ONLY"
SYNTHETIC_PROVENANCE = "SYNTHETIC_STRUCTURAL_ONLY_NOT_SOURCE_VALIDATED"
SOURCE_BOUND_PROVENANCE = "SOURCE_BOUND_FULL_PR69_TO_PR75_REPLAY"

PR69_CANONICAL_SHA256 = (
    "b44166b9543a8f436e62a644efc5316ad12fcc260a4c2c5908ad112928bedfe3"
)
PR69_CANONICAL_SIZE = 39_952_730
PR69_SOURCE_FILE_COUNT = 66
PR69_SOURCE_TOTAL_BYTES = 10_006_877
PR69_SOURCE_FIXTURE_COUNT = 21_226
PR75_PROTOCOL_SHA256 = (
    "eaa2fd1f906f0a18c39f972d919a0393569c85dc8ad6038cbed10819fd2c0774"
)
PR75_PROTOCOL_SIZE = 5_468

ELO_INITIALIZATION_SEMANTICS = (
    "1500_REPLAY_INITIAL_STATE_ASSUMPTION_NOT_OBSERVED_EVIDENCE"
)
FATIGUE_PR31_SEMANTIC_EQUIVALENCE = "UNPROVEN"
HISTORICAL_FRESHNESS_REGIME_RECONSTRUCTED = False
PR74_FULL_HOME_FATIGUE_COEFFICIENT = 0.098533203861
PR74_FULL_AWAY_FATIGUE_COEFFICIENT = -0.252063395175
_SOURCE_BOUND_REFIT_TRAINING_COUNTS = (10_613, 10_564, 10_594, 10_619)

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


class HistoricalExpectedGoalsSuccessorRobustnessEvaluatorError(ValueError):
    """Raised when frozen research-evaluation requirements are not met."""


def _error(message: str) -> HistoricalExpectedGoalsSuccessorRobustnessEvaluatorError:
    return HistoricalExpectedGoalsSuccessorRobustnessEvaluatorError(message)


def _finite(value: Any, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise _error(f"{label} must be finite numeric")
    return float(value)


def _canonical(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("canonical evaluation serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if (
        not isinstance(value, Mapping)
        or set(value) != _SAFETY_KEYS
        or any(type(item) is not bool or item is not False for item in value.values())
    ):
        raise _error("evaluation safety must be exact false mapping")
    return _safety()


def _freeze(value: Any) -> Any:
    """Recursively detach result payload values from caller-owned containers."""
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise _error("result mapping keys must be exact strings")
        return types.MappingProxyType(
            {key: _freeze(item) for key, item in value.items()}
        )
    if type(value) in (list, tuple):
        return tuple(_freeze(item) for item in value)
    if type(value) in (str, bool) or value is None:
        return value
    if type(value) is int:
        _finite(value, "result integer")
        return value
    return _finite(value, "result numeric value")


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if type(value) is tuple:
        return [_thaw(item) for item in value]
    return value


def _require_keys(
    value: Any, keys: frozenset[str], label: str
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise _error(f"{label} keys differ from frozen evaluator contract")
    return value


@dataclasses.dataclass(frozen=True)
class RobustnessFixture:
    """A controlled calculation record; it carries no historical-evidence claim."""

    fixture_identifier: str
    season: str
    identity_league: str
    split: str
    home_goals: int
    away_goals: int
    successor_home_rate: float
    successor_away_rate: float
    elo_home_rate: float
    elo_away_rate: float
    no_fatigue_predictors: tuple[float, ...]
    full_predictors: tuple[float, ...]

    def __post_init__(self) -> None:
        if type(self.fixture_identifier) is not str or not self.fixture_identifier:
            raise _error("fixture identifier must be exact non-empty string")
        if self.split not in {"TRAIN", "EVALUATION"}:
            raise _error("fixture split must be TRAIN or EVALUATION")
        if (
            type(self.home_goals) is not int
            or type(self.away_goals) is not int
            or self.home_goals < 0
            or self.away_goals < 0
        ):
            raise _error("fixture goals must be non-negative exact integers")
        for value, label in (
            (self.successor_home_rate, "successor home rate"),
            (self.successor_away_rate, "successor away rate"),
            (self.elo_home_rate, "ELO home rate"),
            (self.elo_away_rate, "ELO away rate"),
        ):
            if _finite(value, label) <= 0.0:
                raise _error(f"{label} must be positive")
        if (
            type(self.no_fatigue_predictors) is not tuple
            or len(self.no_fatigue_predictors) != 5
        ):
            raise _error("no-fatigue predictor row must contain exactly five values")
        for value in self.no_fatigue_predictors:
            _finite(value, "no-fatigue predictor")
        if type(self.full_predictors) is not tuple or len(self.full_predictors) != 6:
            raise _error("full predictor row must contain exactly six values")
        if self.full_predictors[:5] != self.no_fatigue_predictors:
            raise _error("no-fatigue design must be exact full design without fatigue")
        for value in self.full_predictors:
            _finite(value, "full predictor")


@dataclasses.dataclass(frozen=True)
class PoissonFit:
    coefficients: tuple[float, ...]
    updates: int
    gradient_inf_norm: float
    training_mean_nll: float

    def __post_init__(self) -> None:
        if type(self.coefficients) is not tuple or not self.coefficients:
            raise _error("fit coefficients must be non-empty tuple")
        for value in self.coefficients:
            _finite(value, "fit coefficient")
        if type(self.updates) is not int or self.updates < 0:
            raise _error("fit updates must be non-negative int")
        if (
            _finite(self.gradient_inf_norm, "fit gradient") < 0
            or _finite(self.training_mean_nll, "fit NLL") < 0
        ):
            raise _error("fit diagnostics must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "coefficients": list(self.coefficients),
            "updates": self.updates,
            "gradient_inf_norm": self.gradient_inf_norm,
            "training_mean_nll": self.training_mean_nll,
        }


def fit_poisson_design(
    *, rows: Sequence[tuple[float, ...]], responses: Sequence[int], fitting: Any
) -> PoissonFit:
    """Generic adapter that reuses the frozen PR73 Newton primitives exactly."""
    if type(rows) not in (tuple, list) or not rows or len(rows) != len(responses):
        raise _error("fit rows/responses must be exact non-empty pairs")
    detached = tuple(
        tuple(_finite(value, "design value") for value in row) for row in rows
    )
    dimension = len(detached[0])
    if dimension < 1 or any(len(row) != dimension for row in detached):
        raise _error("design matrix dimensions differ")
    ys = tuple(responses)
    if any(type(value) is not int or value < 0 for value in ys):
        raise _error("Poisson responses must be non-negative exact integers")
    response_mean = math.fsum(ys) / len(ys)
    if not math.isfinite(response_mean) or response_mean <= 0:
        raise _error("training response mean must be strictly positive")

    beta = [math.log(response_mean)] + [0.0] * (dimension - 1)
    updates = 0
    while True:
        nll, _, mus = _response_nll(
            detached, ys, beta, fitting.maximum_abs_linear_predictor
        )
        gradient, hessian = _gradient_and_hessian(detached, ys, mus)
        norm = max(abs(value) for value in gradient)
        if norm <= fitting.gradient_inf_norm_tolerance:
            break
        if updates >= fitting.max_iterations:
            raise _error("frozen Newton solver did not converge")
        direction = _solve_linear_system(
            hessian, gradient, fitting.linear_solve_pivot_tolerance
        )
        step = 1.0
        while True:
            proposal = tuple(
                value + step * delta for value, delta in zip(beta, direction)
            )
            try:
                proposal_nll, _, _ = _response_nll(
                    detached,
                    ys,
                    proposal,
                    fitting.maximum_abs_linear_predictor,
                )
            except HistoricalExpectedGoalsSuccessorCandidateError as exc:
                if "linear predictor exceeds" not in str(exc):
                    raise _error("PR73 numerical primitive failed") from exc
                proposal_nll = math.inf
            if proposal_nll <= nll:
                beta = list(proposal)
                updates += 1
                break
            step *= fitting.backtracking_factor
            if step < fitting.minimum_step:
                raise _error("frozen Newton backtracking failed")

    rounded = _rounded_coefficients(beta, fitting.coefficient_rounding_places)
    rounded_nll, _, _ = _response_nll(
        detached, ys, rounded, fitting.maximum_abs_linear_predictor
    )
    return PoissonFit(
        rounded,
        updates,
        float(norm),
        float(rounded_nll / len(detached)),
    )


def _poisson_nll(goals: int, rate: float) -> float:
    return _finite(
        rate - goals * math.log(rate) + math.lgamma(goals + 1), "Poisson NLL"
    )


def _joint(fixture: RobustnessFixture, home: float, away: float) -> float:
    return math.fsum(
        (
            _poisson_nll(fixture.home_goals, home),
            _poisson_nll(fixture.away_goals, away),
        )
    )


def _mean(values: Sequence[float], label: str) -> float:
    if not values:
        raise _error(f"{label} cannot be empty")
    return _finite(math.fsum(values) / len(values), label)


def _calibration(
    fixtures: Sequence[RobustnessFixture], *, model: str, side: str
) -> tuple[dict[str, Any], ...]:
    bounds = (
        (0.0, 0.5),
        (0.5, 1.0),
        (1.0, 1.5),
        (1.5, 2.0),
        (2.0, 2.5),
        (2.5, 3.0),
        (3.0, None),
    )
    result: list[dict[str, Any]] = []
    for lower, upper in bounds:
        selected: list[tuple[float, int]] = []
        for fixture in fixtures:
            rate = getattr(fixture, f"{model}_{side}_rate")
            if rate >= lower and (upper is None or rate < upper):
                selected.append(
                    (
                        rate,
                        fixture.home_goals if side == "home" else fixture.away_goals,
                    )
                )
        if not selected:
            result.append(
                {
                    "lower": lower,
                    "upper": upper,
                    "count": 0,
                    "mean_predicted_goals": None,
                    "mean_observed_goals": None,
                    "calibration_error_predicted_minus_observed": None,
                }
            )
        else:
            predicted = _mean(
                [item[0] for item in selected], "calibration predicted mean"
            )
            observed = _mean(
                [float(item[1]) for item in selected], "calibration observed mean"
            )
            result.append(
                {
                    "lower": lower,
                    "upper": upper,
                    "count": len(selected),
                    "mean_predicted_goals": predicted,
                    "mean_observed_goals": observed,
                    "calibration_error_predicted_minus_observed": (
                        predicted - observed
                    ),
                }
            )
    return tuple(result)


def _calibration_summary(
    bins: Sequence[Mapping[str, Any]],
    fixtures: Sequence[RobustnessFixture],
    *,
    model: str,
    side: str,
) -> Mapping[str, float]:
    predictions = [getattr(item, f"{model}_{side}_rate") for item in fixtures]
    outcomes = [
        float(item.home_goals if side == "home" else item.away_goals)
        for item in fixtures
    ]
    absolute_errors = [
        item["count"] * abs(item["calibration_error_predicted_minus_observed"])
        for item in bins
        if item["count"]
    ]
    squared_errors = [
        item["count"] * item["calibration_error_predicted_minus_observed"] ** 2
        for item in bins
        if item["count"]
    ]
    return types.MappingProxyType(
        {
            "absolute_overall_bias": abs(
                _mean(predictions, "prediction") - _mean(outcomes, "outcome")
            ),
            "wace": math.fsum(absolute_errors) / len(fixtures),
            "wsce": math.fsum(squared_errors) / len(fixtures),
        }
    )


def _sign_stable(full: float, omission: Sequence[float]) -> bool:
    return (
        len(omission) == 4
        and full != 0.0
        and all(
            value != 0.0 and (value > 0.0) == (full > 0.0)
            for value in omission
        )
    )


def _rate(row: Sequence[float], coefficients: Sequence[float], fitting: Any) -> float:
    eta = math.fsum(left * right for left, right in zip(row, coefficients))
    if abs(eta) > fitting.maximum_abs_linear_predictor:
        raise _error("rounded evaluation coefficient vector exceeds eta guard")
    return _finite(math.exp(eta), "refit rate")


def _validate_fit_payload(
    value: Any, dimension: int, label: str
) -> Mapping[str, Any]:
    value = _require_keys(
        value,
        frozenset(
            {"coefficients", "updates", "gradient_inf_norm", "training_mean_nll"}
        ),
        label,
    )
    coefficients = value["coefficients"]
    if type(coefficients) not in (tuple, list) or len(coefficients) != dimension:
        raise _error(f"{label} coefficient dimension differs")
    for item in coefficients:
        _finite(item, f"{label} coefficient")
    if type(value["updates"]) is not int or value["updates"] < 0:
        raise _error(f"{label} updates differ")
    if _finite(value["gradient_inf_norm"], f"{label} gradient") < 0.0:
        raise _error(f"{label} gradient must be non-negative")
    if _finite(value["training_mean_nll"], f"{label} NLL") < 0.0:
        raise _error(f"{label} NLL must be non-negative")
    return value


def _validate_results(
    value: Any, *, provenance: str | None = None
) -> Mapping[str, Any]:
    """Validate every result field before it can become a canonical artifact."""
    value = _require_keys(
        value,
        frozenset(
            {
                "paired_nll",
                "calibration",
                "no_fatigue",
                "full_fatigue_coefficients",
                "leave_one_training_season_refits",
                "interpretation",
            }
        ),
        "results",
    )

    paired = _require_keys(
        value["paired_nll"],
        frozenset(
            {
                "full_estimate",
                "jackknife_se",
                "interval_lower",
                "interval_upper",
                "cluster_count",
                "delete_clusters",
                "leave_one_league_out",
                "leave_one_season_out",
            }
        ),
        "paired result",
    )
    full_estimate = _finite(paired["full_estimate"], "paired full_estimate")
    jackknife_se = _finite(paired["jackknife_se"], "paired jackknife_se")
    if jackknife_se < 0.0:
        raise _error("paired jackknife SE must be non-negative")
    interval_lower = _finite(paired["interval_lower"], "paired interval_lower")
    interval_upper = _finite(paired["interval_upper"], "paired interval_upper")
    if interval_lower != full_estimate - 1.96 * jackknife_se:
        raise _error("paired lower interval does not derive from frozen formula")
    if interval_upper != full_estimate + 1.96 * jackknife_se:
        raise _error("paired upper interval does not derive from frozen formula")
    if paired["cluster_count"] != len(CLUSTER_KEYS):
        raise _error("paired cluster count differs")

    deletes = paired["delete_clusters"]
    if type(deletes) not in (tuple, list) or len(deletes) != len(CLUSTER_KEYS):
        raise _error("delete-cluster record count differs")
    for record, key in zip(deletes, CLUSTER_KEYS):
        record = _require_keys(
            record,
            frozenset(
                {
                    "season",
                    "identity_league",
                    "omitted_fixture_count",
                    "remaining_fixture_count",
                    "delete_estimate",
                }
            ),
            "delete-cluster record",
        )
        if (record["season"], record["identity_league"]) != key:
            raise _error("delete-cluster identity/order differs")
        if (
            type(record["omitted_fixture_count"]) is not int
            or type(record["remaining_fixture_count"]) is not int
            or record["omitted_fixture_count"] <= 0
            or record["remaining_fixture_count"] <= 0
        ):
            raise _error("delete-cluster counts differ")
        _finite(record["delete_estimate"], "delete estimate")

    population_count = sum(record["omitted_fixture_count"] for record in deletes)
    if population_count <= 0:
        raise _error("delete-cluster population count differs")
    if any(
        record["remaining_fixture_count"]
        != population_count - record["omitted_fixture_count"]
        for record in deletes
    ):
        raise _error("delete-cluster remaining counts do not reconcile")

    league_records = paired["leave_one_league_out"]
    if (
        type(league_records) not in (tuple, list)
        or len(league_records) != len(IDENTITY_LEAGUES)
    ):
        raise _error("leave-one-league records differ")
    for record, league in zip(league_records, IDENTITY_LEAGUES):
        record = _require_keys(
            record,
            frozenset(
                {
                    "omitted_league",
                    "omitted_fixture_count",
                    "remaining_fixture_count",
                    "candidate_minus_elo_mean_nll",
                }
            ),
            "league sensitivity record",
        )
        if record["omitted_league"] != league:
            raise _error("league sensitivity order differs")
        if (
            type(record["omitted_fixture_count"]) is not int
            or type(record["remaining_fixture_count"]) is not int
            or record["omitted_fixture_count"] <= 0
        ):
            raise _error("league sensitivity counts differ")
        _finite(
            record["candidate_minus_elo_mean_nll"],
            "league sensitivity estimate",
        )
    if sum(record["omitted_fixture_count"] for record in league_records) != population_count:
        raise _error("league sensitivity omission counts do not reconcile")
    if any(
        record["remaining_fixture_count"]
        != population_count - record["omitted_fixture_count"]
        for record in league_records
    ):
        raise _error("league sensitivity remaining counts do not reconcile")

    season_records = paired["leave_one_season_out"]
    if type(season_records) not in (tuple, list) or len(season_records) != 2:
        raise _error("leave-one-season records differ")
    for record, season in zip(season_records, ("2024-25", "2025-26")):
        record = _require_keys(
            record,
            frozenset(
                {
                    "omitted_season",
                    "omitted_fixture_count",
                    "remaining_fixture_count",
                    "candidate_minus_elo_mean_nll",
                }
            ),
            "season sensitivity record",
        )
        if record["omitted_season"] != season:
            raise _error("season sensitivity order differs")
        if (
            type(record["omitted_fixture_count"]) is not int
            or type(record["remaining_fixture_count"]) is not int
            or record["omitted_fixture_count"] <= 0
        ):
            raise _error("season sensitivity counts differ")
        _finite(
            record["candidate_minus_elo_mean_nll"],
            "season sensitivity estimate",
        )
    if sum(record["omitted_fixture_count"] for record in season_records) != population_count:
        raise _error("season sensitivity omission counts do not reconcile")
    if any(
        record["remaining_fixture_count"]
        != population_count - record["omitted_fixture_count"]
        for record in season_records
    ):
        raise _error("season sensitivity remaining counts do not reconcile")

    calibration = _require_keys(
        value["calibration"],
        frozenset({"bins", "summaries", "successor_minus_elo"}),
        "calibration",
    )
    expected_calibration = {
        f"{model}_{side}"
        for model in ("successor", "elo")
        for side in ("home", "away")
    }
    bins = calibration["bins"]
    summaries = calibration["summaries"]
    if (
        not isinstance(bins, Mapping)
        or set(bins) != expected_calibration
        or not isinstance(summaries, Mapping)
        or set(summaries) != expected_calibration
    ):
        raise _error("calibration model/side set differs")
    bounds = (
        (0.0, 0.5),
        (0.5, 1.0),
        (1.0, 1.5),
        (1.5, 2.0),
        (2.0, 2.5),
        (2.5, 3.0),
        (3.0, None),
    )
    for name in sorted(expected_calibration):
        rows = bins[name]
        if type(rows) not in (tuple, list) or len(rows) != len(bounds):
            raise _error("calibration bin count differs")
        for row, bound in zip(rows, bounds):
            row = _require_keys(
                row,
                frozenset(
                    {
                        "lower",
                        "upper",
                        "count",
                        "mean_predicted_goals",
                        "mean_observed_goals",
                        "calibration_error_predicted_minus_observed",
                    }
                ),
                "calibration bin",
            )
            if (
                (row["lower"], row["upper"]) != bound
                or type(row["count"]) is not int
                or row["count"] < 0
            ):
                raise _error("calibration bin identity differs")
            if row["count"] == 0:
                if any(
                    row[key] is not None
                    for key in (
                        "mean_predicted_goals",
                        "mean_observed_goals",
                        "calibration_error_predicted_minus_observed",
                    )
                ):
                    raise _error("empty calibration bin must be null")
            else:
                predicted = _finite(
                    row["mean_predicted_goals"], "calibration predicted"
                )
                observed = _finite(
                    row["mean_observed_goals"], "calibration observed"
                )
                if (
                    _finite(
                        row["calibration_error_predicted_minus_observed"],
                        "calibration error",
                    )
                    != predicted - observed
                ):
                    raise _error(
                        "calibration error differs from predicted minus observed"
                    )
        if sum(row["count"] for row in rows) != population_count:
            raise _error("calibration bins do not reconcile to paired population")
        summary = _require_keys(
            summaries[name],
            frozenset({"absolute_overall_bias", "wace", "wsce"}),
            "calibration summary",
        )
        for item in summary.values():
            if _finite(item, "calibration summary value") < 0.0:
                raise _error("calibration summary metrics must be non-negative")

    deltas = calibration["successor_minus_elo"]
    expected_deltas = {
        f"{side}_{metric}"
        for side in ("home", "away")
        for metric in ("absolute_overall_bias", "wace", "wsce")
    }
    if not isinstance(deltas, Mapping) or set(deltas) != expected_deltas:
        raise _error("calibration delta fields differ")
    for side in ("home", "away"):
        for metric in ("absolute_overall_bias", "wace", "wsce"):
            key = f"{side}_{metric}"
            supplied = _finite(deltas[key], "calibration delta")
            expected = summaries[f"successor_{side}"][metric] - summaries[f"elo_{side}"][metric]
            if supplied != expected:
                raise _error("calibration delta does not derive from summaries")

    no_fatigue = _require_keys(
        value["no_fatigue"],
        frozenset(
            {
                "home_fit",
                "away_fit",
                "full_successor_mean_joint_nll",
                "no_fatigue_mean_joint_nll",
                "no_fatigue_minus_full_nll",
            }
        ),
        "no-fatigue",
    )
    if no_fatigue["home_fit"] is not None:
        _validate_fit_payload(no_fatigue["home_fit"], 5, "no-fatigue home")
    if no_fatigue["away_fit"] is not None:
        _validate_fit_payload(no_fatigue["away_fit"], 5, "no-fatigue away")
    for key in (
        "full_successor_mean_joint_nll",
        "no_fatigue_mean_joint_nll",
        "no_fatigue_minus_full_nll",
    ):
        if no_fatigue[key] is not None:
            _finite(no_fatigue[key], f"no-fatigue {key}")
    no_fatigue_values = tuple(
        no_fatigue[key]
        for key in (
            "full_successor_mean_joint_nll",
            "no_fatigue_mean_joint_nll",
            "no_fatigue_minus_full_nll",
        )
    )
    if any(item is None for item in no_fatigue_values):
        if any(item is not None for item in no_fatigue_values):
            raise _error("no-fatigue numeric result must be complete or absent")
    elif (
        no_fatigue["no_fatigue_minus_full_nll"]
        != no_fatigue["no_fatigue_mean_joint_nll"]
        - no_fatigue["full_successor_mean_joint_nll"]
    ):
        raise _error("no-fatigue delta does not derive from its NLL values")

    refits = value["leave_one_training_season_refits"]
    if type(refits) not in (tuple, list) or len(refits) not in (0, 4):
        raise _error("leave-one-training-season record count differs")
    for record, season in zip(
        refits, ("2020-21", "2021-22", "2022-23", "2023-24")
    ):
        record = _require_keys(
            record,
            frozenset(
                {
                    "omitted_training_season",
                    "training_fixture_count",
                    "home_fit",
                    "away_fit",
                    "evaluation_fixture_count",
                    "evaluation_mean_joint_nll",
                    "home_fatigue_coefficient",
                    "away_fatigue_coefficient",
                }
            ),
            "training-season refit",
        )
        if record["omitted_training_season"] != season:
            raise _error("training-season refit order differs")
        home_fit = _validate_fit_payload(record["home_fit"], 6, "refit home")
        away_fit = _validate_fit_payload(record["away_fit"], 6, "refit away")
        _finite(record["evaluation_mean_joint_nll"], "refit evaluation NLL")
        home_fatigue = _finite(
            record["home_fatigue_coefficient"], "home fatigue coefficient"
        )
        away_fatigue = _finite(
            record["away_fatigue_coefficient"], "away fatigue coefficient"
        )
        if home_fatigue != home_fit["coefficients"][-1]:
            raise _error("home fatigue scalar differs from fitted coefficient")
        if away_fatigue != away_fit["coefficients"][-1]:
            raise _error("away fatigue scalar differs from fitted coefficient")
        if (
            type(record["training_fixture_count"]) is not int
            or record["training_fixture_count"] <= 0
            or type(record["evaluation_fixture_count"]) is not int
            or record["evaluation_fixture_count"] != population_count
        ):
            raise _error("training-season refit counts differ")

    full_fatigue = _require_keys(
        value["full_fatigue_coefficients"],
        frozenset({"home", "away"}),
        "full fatigue coefficients",
    )
    _finite(full_fatigue["home"], "full home fatigue coefficient")
    _finite(full_fatigue["away"], "full away fatigue coefficient")

    interpretation = value["interpretation"]
    expected_interpretation = frozenset(
        {
            "paired_elo_interval_upper_below_zero",
            "all_leave_one_league_out_deltas_negative",
            "both_leave_one_season_out_deltas_negative",
            "no_fatigue_ablation_better_than_full",
            "home_fatigue_sign_stable_across_training_season_omissions",
            "away_fatigue_sign_stable_across_training_season_omissions",
            "successor_lower_home_wace_than_same_fixture_elo",
            "successor_lower_away_wace_than_same_fixture_elo",
            "successor_lower_home_wsce_than_same_fixture_elo",
            "successor_lower_away_wsce_than_same_fixture_elo",
        }
    )
    _require_keys(interpretation, expected_interpretation, "interpretation")
    if any(type(item) is not bool for item in interpretation.values()):
        raise _error("interpretation fields must be exact bool")
    expected_interpretation_values = {
        "paired_elo_interval_upper_below_zero": interval_upper < 0.0,
        "all_leave_one_league_out_deltas_negative": all(
            item["candidate_minus_elo_mean_nll"] < 0.0 for item in league_records
        ),
        "both_leave_one_season_out_deltas_negative": all(
            item["candidate_minus_elo_mean_nll"] < 0.0 for item in season_records
        ),
        "no_fatigue_ablation_better_than_full": (
            no_fatigue["no_fatigue_mean_joint_nll"] is not None
            and no_fatigue["no_fatigue_mean_joint_nll"]
            < no_fatigue["full_successor_mean_joint_nll"]
        ),
        "home_fatigue_sign_stable_across_training_season_omissions": (
            len(refits) == 4
            and full_fatigue["home"] != 0.0
            and all(
                item["home_fatigue_coefficient"] != 0.0
                and (item["home_fatigue_coefficient"] > 0.0)
                == (full_fatigue["home"] > 0.0)
                for item in refits
            )
        ),
        "away_fatigue_sign_stable_across_training_season_omissions": (
            len(refits) == 4
            and full_fatigue["away"] != 0.0
            and all(
                item["away_fatigue_coefficient"] != 0.0
                and (item["away_fatigue_coefficient"] > 0.0)
                == (full_fatigue["away"] > 0.0)
                for item in refits
            )
        ),
        "successor_lower_home_wace_than_same_fixture_elo": deltas["home_wace"]
        < 0.0,
        "successor_lower_away_wace_than_same_fixture_elo": deltas["away_wace"]
        < 0.0,
        "successor_lower_home_wsce_than_same_fixture_elo": deltas["home_wsce"]
        < 0.0,
        "successor_lower_away_wsce_than_same_fixture_elo": deltas["away_wsce"]
        < 0.0,
    }
    if dict(interpretation) != expected_interpretation_values:
        raise _error("interpretation values do not derive from frozen numeric results")

    if provenance == SOURCE_BOUND_PROVENANCE:
        if population_count != EVALUATION_FIXTURE_COUNT:
            raise _error("source-bound evaluation population must be exact 6903 fixtures")
        if len(refits) != 4:
            raise _error("source-bound evaluation requires four diagnostic refits")
        if tuple(record["training_fixture_count"] for record in refits) != (
            _SOURCE_BOUND_REFIT_TRAINING_COUNTS
        ):
            raise _error("source-bound omission training counts differ from PR75")
        if (
            no_fatigue["home_fit"] is None
            or no_fatigue["away_fit"] is None
            or any(item is None for item in no_fatigue_values)
        ):
            raise _error("source-bound evaluation requires complete no-fatigue result")
        if full_fatigue["home"] != PR74_FULL_HOME_FATIGUE_COEFFICIENT:
            raise _error("source-bound home fatigue coefficient differs from PR74")
        if full_fatigue["away"] != PR74_FULL_AWAY_FATIGUE_COEFFICIENT:
            raise _error("source-bound away fatigue coefficient differs from PR74")

    return value


@dataclasses.dataclass(frozen=True)
class HistoricalExpectedGoalsSuccessorRobustnessEvaluation:
    schema_version: int
    dataset_name: str
    scope: str
    pr74_receipt_sha256: str
    successor_candidate_sha256: str
    successor_candidate_size: int
    protocol_id: str
    protocol_sha256: str
    protocol_size: int
    source_corpus_sha256: str
    elo_initialization_semantics: str
    fatigue_pr31_semantic_equivalence: str
    historical_freshness_regime_reconstructed: bool
    provenance: str
    results: Mapping[str, Any]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if (self.schema_version, self.dataset_name, self.scope) != (
            SCHEMA_VERSION,
            DATASET_NAME,
            EVALUATION_SCOPE,
        ):
            raise _error("evaluation identity mismatch")
        if (
            self.pr74_receipt_sha256,
            self.successor_candidate_sha256,
            self.successor_candidate_size,
        ) != (
            PR74_RECEIPT_SHA256,
            SUCCESSOR_CANDIDATE_SHA256,
            SUCCESSOR_CANDIDATE_SIZE,
        ):
            raise _error("evaluation candidate ancestry mismatch")
        if (self.protocol_id, self.protocol_sha256, self.protocol_size) != (
            PROTOCOL_ID,
            PR75_PROTOCOL_SHA256,
            PR75_PROTOCOL_SIZE,
        ):
            raise _error("evaluation protocol anchor mismatch")
        if self.source_corpus_sha256 != PR69_SOURCE_CORPUS_SHA256:
            raise _error("evaluation source corpus anchor mismatch")
        if self.elo_initialization_semantics != ELO_INITIALIZATION_SEMANTICS:
            raise _error("evaluation Elo initialization semantics differ")
        if (
            self.fatigue_pr31_semantic_equivalence
            != FATIGUE_PR31_SEMANTIC_EQUIVALENCE
        ):
            raise _error("evaluation fatigue semantic equivalence differs")
        if (
            type(self.historical_freshness_regime_reconstructed) is not bool
            or self.historical_freshness_regime_reconstructed
            is not HISTORICAL_FRESHNESS_REGIME_RECONSTRUCTED
        ):
            raise _error("evaluation historical freshness semantics differ")
        if self.provenance not in {SYNTHETIC_PROVENANCE, SOURCE_BOUND_PROVENANCE}:
            raise _error("evaluation provenance is not an exact allowed boundary")
        object.__setattr__(
            self,
            "results",
            _freeze(_validate_results(self.results, provenance=self.provenance)),
        )
        object.__setattr__(self, "safety", _validate_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "scope": self.scope,
            "pr74_receipt_sha256": self.pr74_receipt_sha256,
            "successor_candidate_sha256": self.successor_candidate_sha256,
            "successor_candidate_size": self.successor_candidate_size,
            "protocol_id": self.protocol_id,
            "protocol_sha256": self.protocol_sha256,
            "protocol_size": self.protocol_size,
            "source_corpus_sha256": self.source_corpus_sha256,
            "elo_initialization_semantics": self.elo_initialization_semantics,
            "fatigue_pr31_semantic_equivalence": self.fatigue_pr31_semantic_equivalence,
            "historical_freshness_regime_reconstructed": (
                self.historical_freshness_regime_reconstructed
            ),
            "provenance": self.provenance,
            "results": _thaw(self.results),
            "safety": dict(self.safety),
        }


def evaluate_successor_robustness_fixture_set(
    *,
    protocol: HistoricalExpectedGoalsSuccessorRobustnessProtocol,
    fixtures: Sequence[RobustnessFixture],
    fitting: Any | None = None,
    full_home_fatigue: float = 1.0,
    full_away_fatigue: float = -1.0,
    omission_fatigue_coefficients: Sequence[tuple[float, float]] = ((1.0, -1.0),)
    * 4,
) -> Mapping[str, Any]:
    """Synthetic calculation seam. It makes no reviewed-historical assertion."""
    if type(protocol) is not HistoricalExpectedGoalsSuccessorRobustnessProtocol:
        raise _error("protocol must be exact PR75 protocol")
    items = tuple(fixtures)
    if not items or any(type(item) is not RobustnessFixture for item in items):
        raise _error("fixtures must be non-empty exact RobustnessFixture values")
    if len({item.fixture_identifier for item in items}) != len(items):
        raise _error("fixture identifiers must be unique")
    evaluation = tuple(item for item in items if item.split == "EVALUATION")
    training = tuple(item for item in items if item.split == "TRAIN")
    if not evaluation or not training:
        raise _error("synthetic seam requires train and evaluation fixtures")
    keys = {(item.season, item.identity_league) for item in evaluation}
    if not keys <= set(CLUSTER_KEYS):
        raise _error("unknown evaluation cluster")
    if keys != set(CLUSTER_KEYS):
        raise _error("missing frozen evaluation cluster")

    differences = {
        item.fixture_identifier: _joint(
            item, item.successor_home_rate, item.successor_away_rate
        )
        - _joint(item, item.elo_home_rate, item.elo_away_rate)
        for item in evaluation
    }
    theta = _mean(list(differences.values()), "paired full estimate")
    deletes: list[dict[str, Any]] = []
    for season, league in CLUSTER_KEYS:
        omitted = [
            item
            for item in evaluation
            if (item.season, item.identity_league) == (season, league)
        ]
        remaining = [
            item
            for item in evaluation
            if (item.season, item.identity_league) != (season, league)
        ]
        if not omitted or not remaining:
            raise _error("invalid delete cluster")
        deletes.append(
            {
                "season": season,
                "identity_league": league,
                "omitted_fixture_count": len(omitted),
                "remaining_fixture_count": len(remaining),
                "delete_estimate": _mean(
                    [differences[item.fixture_identifier] for item in remaining],
                    "delete estimate",
                ),
            }
        )
    theta_bar = _mean(
        [item["delete_estimate"] for item in deletes],
        "unweighted delete estimate center",
    )
    se = math.sqrt(
        ((len(deletes) - 1) / len(deletes))
        * math.fsum(
            (item["delete_estimate"] - theta_bar) ** 2 for item in deletes
        )
    )

    league_out: list[dict[str, Any]] = []
    for league in IDENTITY_LEAGUES:
        omitted = [item for item in evaluation if item.identity_league == league]
        remaining = [item for item in evaluation if item.identity_league != league]
        league_out.append(
            {
                "omitted_league": league,
                "omitted_fixture_count": len(omitted),
                "remaining_fixture_count": len(remaining),
                "candidate_minus_elo_mean_nll": _mean(
                    [differences[item.fixture_identifier] for item in remaining],
                    "league deletion",
                ),
            }
        )

    season_out: list[dict[str, Any]] = []
    for season in ("2024-25", "2025-26"):
        omitted = [item for item in evaluation if item.season == season]
        remaining = [item for item in evaluation if item.season != season]
        season_out.append(
            {
                "omitted_season": season,
                "omitted_fixture_count": len(omitted),
                "remaining_fixture_count": len(remaining),
                "candidate_minus_elo_mean_nll": _mean(
                    [differences[item.fixture_identifier] for item in remaining],
                    "season deletion",
                ),
            }
        )

    calibrations = {
        (model, side): _calibration(evaluation, model=model, side=side)
        for model in ("successor", "elo")
        for side in ("home", "away")
    }
    summaries = {
        (model, side): _calibration_summary(
            calibrations[(model, side)], evaluation, model=model, side=side
        )
        for model in ("successor", "elo")
        for side in ("home", "away")
    }

    omission_records: list[dict[str, Any]] = []
    if fitting is not None:
        no_home = fit_poisson_design(
            rows=[item.no_fatigue_predictors for item in training],
            responses=[item.home_goals for item in training],
            fitting=fitting,
        )
        no_away = fit_poisson_design(
            rows=[item.no_fatigue_predictors for item in training],
            responses=[item.away_goals for item in training],
            fitting=fitting,
        )
        no_nll = _mean(
            [
                _joint(
                    item,
                    _rate(item.no_fatigue_predictors, no_home.coefficients, fitting),
                    _rate(item.no_fatigue_predictors, no_away.coefficients, fitting),
                )
                for item in evaluation
            ],
            "no-fatigue NLL",
        )
        full_nll = _mean(
            [
                _joint(
                    item, item.successor_home_rate, item.successor_away_rate
                )
                for item in evaluation
            ],
            "full successor NLL",
        )
        expected_omissions = (
            "2020-21",
            "2021-22",
            "2022-23",
            "2023-24",
        )
        if {item.season for item in training} != set(expected_omissions):
            raise _error("diagnostic refits require every frozen training season")
        for omitted_season in expected_omissions:
            retained = tuple(
                item for item in training if item.season != omitted_season
            )
            home = fit_poisson_design(
                rows=[item.full_predictors for item in retained],
                responses=[item.home_goals for item in retained],
                fitting=fitting,
            )
            away = fit_poisson_design(
                rows=[item.full_predictors for item in retained],
                responses=[item.away_goals for item in retained],
                fitting=fitting,
            )
            evaluation_nll = _mean(
                [
                    _joint(
                        item,
                        _rate(item.full_predictors, home.coefficients, fitting),
                        _rate(item.full_predictors, away.coefficients, fitting),
                    )
                    for item in evaluation
                ],
                "omission evaluation NLL",
            )
            omission_records.append(
                {
                    "omitted_training_season": omitted_season,
                    "training_fixture_count": len(retained),
                    "home_fit": home.to_dict(),
                    "away_fit": away.to_dict(),
                    "evaluation_fixture_count": len(evaluation),
                    "evaluation_mean_joint_nll": evaluation_nll,
                    "home_fatigue_coefficient": home.coefficients[-1],
                    "away_fatigue_coefficient": away.coefficients[-1],
                }
            )
        omission_fatigue_coefficients = tuple(
            (
                item["home_fatigue_coefficient"],
                item["away_fatigue_coefficient"],
            )
            for item in omission_records
        )
    else:
        no_home = no_away = None
        no_nll = None
        full_nll = None
        omission_fatigue_coefficients = ()

    deltas = {
        f"{side}_{metric}": summaries[("successor", side)][metric]
        - summaries[("elo", side)][metric]
        for side in ("home", "away")
        for metric in ("absolute_overall_bias", "wace", "wsce")
    }
    interpretation = {
        "paired_elo_interval_upper_below_zero": theta + 1.96 * se < 0.0,
        "all_leave_one_league_out_deltas_negative": all(
            item["candidate_minus_elo_mean_nll"] < 0.0 for item in league_out
        ),
        "both_leave_one_season_out_deltas_negative": all(
            item["candidate_minus_elo_mean_nll"] < 0.0 for item in season_out
        ),
        "no_fatigue_ablation_better_than_full": (
            no_nll is not None and no_nll < full_nll
        ),
        "home_fatigue_sign_stable_across_training_season_omissions": _sign_stable(
            full_home_fatigue,
            [item[0] for item in omission_fatigue_coefficients],
        ),
        "away_fatigue_sign_stable_across_training_season_omissions": _sign_stable(
            full_away_fatigue,
            [item[1] for item in omission_fatigue_coefficients],
        ),
        "successor_lower_home_wace_than_same_fixture_elo": deltas["home_wace"]
        < 0.0,
        "successor_lower_away_wace_than_same_fixture_elo": deltas["away_wace"]
        < 0.0,
        "successor_lower_home_wsce_than_same_fixture_elo": deltas["home_wsce"]
        < 0.0,
        "successor_lower_away_wsce_than_same_fixture_elo": deltas["away_wsce"]
        < 0.0,
    }
    return types.MappingProxyType(
        {
            "paired_nll": {
                "full_estimate": theta,
                "jackknife_se": se,
                "interval_lower": theta - 1.96 * se,
                "interval_upper": theta + 1.96 * se,
                "cluster_count": len(deletes),
                "delete_clusters": deletes,
                "leave_one_league_out": league_out,
                "leave_one_season_out": season_out,
            },
            "calibration": {
                "bins": {
                    f"{model}_{side}": list(calibrations[(model, side)])
                    for model in ("successor", "elo")
                    for side in ("home", "away")
                },
                "summaries": {
                    f"{model}_{side}": dict(summaries[(model, side)])
                    for model in ("successor", "elo")
                    for side in ("home", "away")
                },
                "successor_minus_elo": deltas,
            },
            "no_fatigue": {
                "home_fit": None if no_home is None else no_home.to_dict(),
                "away_fit": None if no_away is None else no_away.to_dict(),
                "full_successor_mean_joint_nll": full_nll,
                "no_fatigue_mean_joint_nll": no_nll,
                "no_fatigue_minus_full_nll": (
                    None if no_nll is None else no_nll - full_nll
                ),
            },
            "full_fatigue_coefficients": {
                "home": full_home_fatigue,
                "away": full_away_fatigue,
            },
            "leave_one_training_season_refits": omission_records,
            "interpretation": interpretation,
        }
    )


def canonical_historical_expected_goals_successor_robustness_evaluation_bytes(
    value: HistoricalExpectedGoalsSuccessorRobustnessEvaluation,
) -> bytes:
    if type(value) is not HistoricalExpectedGoalsSuccessorRobustnessEvaluation:
        raise _error("evaluation type mismatch")
    HistoricalExpectedGoalsSuccessorRobustnessEvaluation(**value.__dict__)
    return _canonical(value.to_dict())


def sha256_historical_expected_goals_successor_robustness_evaluation(
    value: HistoricalExpectedGoalsSuccessorRobustnessEvaluation,
) -> str:
    return _sha(
        canonical_historical_expected_goals_successor_robustness_evaluation_bytes(
            value
        )
    )


def build_historical_expected_goals_successor_robustness_evaluation(
    *,
    receipt_bytes: bytes,
    protocol: HistoricalExpectedGoalsSuccessorRobustnessProtocol,
    protocol_bytes: bytes,
    source_corpus_sha256: str,
    results: Mapping[str, Any],
) -> HistoricalExpectedGoalsSuccessorRobustnessEvaluation:
    """Create a synthetic/structural wrapper, never source-bound evidence."""
    revalidate_successor_robustness_protocol(
        receipt_bytes=receipt_bytes,
        protocol=protocol,
        protocol_bytes=protocol_bytes,
    )
    if source_corpus_sha256 != protocol.source_corpus_sha256:
        raise _error("source corpus SHA differs from frozen protocol")
    if not isinstance(results, Mapping):
        raise _error("results must be mapping")
    return HistoricalExpectedGoalsSuccessorRobustnessEvaluation(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        scope=EVALUATION_SCOPE,
        pr74_receipt_sha256=PR74_RECEIPT_SHA256,
        successor_candidate_sha256=SUCCESSOR_CANDIDATE_SHA256,
        successor_candidate_size=SUCCESSOR_CANDIDATE_SIZE,
        protocol_id=protocol.protocol_id,
        protocol_sha256=sha256_successor_robustness_protocol(protocol),
        protocol_size=len(protocol_bytes),
        source_corpus_sha256=source_corpus_sha256,
        elo_initialization_semantics=ELO_INITIALIZATION_SEMANTICS,
        fatigue_pr31_semantic_equivalence=FATIGUE_PR31_SEMANTIC_EQUIVALENCE,
        historical_freshness_regime_reconstructed=(
            HISTORICAL_FRESHNESS_REGIME_RECONSTRUCTED
        ),
        provenance=SYNTHETIC_PROVENANCE,
        results=results,
        safety=_safety(),
    )


def build_source_bound_historical_expected_goals_successor_robustness_evaluation(
    *,
    source_inputs: Sequence[HistoricalReplaySourceInput],
    corpus: HistoricalReplayCorpus,
    corpus_bytes: bytes,
    pr73_receipt_bytes: bytes,
    pr73_protocol: HistoricalExpectedGoalsSuccessorProtocol,
    pr73_protocol_bytes: bytes,
    pr75_receipt_bytes: bytes,
    pr75_protocol: HistoricalExpectedGoalsSuccessorRobustnessProtocol,
    pr75_protocol_bytes: bytes,
) -> HistoricalExpectedGoalsSuccessorRobustnessEvaluation:
    """Future real-evidence boundary; caller supplies all exact PR69--75 inputs."""
    revalidate_successor_robustness_protocol(
        receipt_bytes=pr75_receipt_bytes,
        protocol=pr75_protocol,
        protocol_bytes=pr75_protocol_bytes,
    )
    rebuilt_corpus = revalidate_historical_model_feature_replay_corpus(
        source_inputs=source_inputs,
        corpus=corpus,
        corpus_bytes=corpus_bytes,
    )
    rebuilt_corpus_bytes = canonical_historical_model_feature_replay_corpus_bytes(
        rebuilt_corpus
    )
    if rebuilt_corpus.source_corpus_sha256 != PR69_SOURCE_CORPUS_SHA256:
        raise _error("reconstructed raw source corpus SHA differs from PR75")
    if _sha(rebuilt_corpus_bytes) != PR69_CANONICAL_SHA256:
        raise _error("reconstructed canonical PR69 corpus SHA differs")
    if len(rebuilt_corpus_bytes) != PR69_CANONICAL_SIZE:
        raise _error("reconstructed canonical PR69 corpus size differs")
    if (
        len(rebuilt_corpus.source_files),
        sum(item.raw_size for item in rebuilt_corpus.source_files),
        rebuilt_corpus.fixture_count,
    ) != (
        PR69_SOURCE_FILE_COUNT,
        PR69_SOURCE_TOTAL_BYTES,
        PR69_SOURCE_FIXTURE_COUNT,
    ):
        raise _error("reconstructed PR69 source receipt anchors differ")

    candidate = build_historical_expected_goals_successor_candidate(
        source_inputs=source_inputs,
        corpus=rebuilt_corpus,
        corpus_bytes=rebuilt_corpus_bytes,
        receipt_bytes=pr73_receipt_bytes,
        protocol=pr73_protocol,
        protocol_bytes=pr73_protocol_bytes,
    )
    candidate_bytes = canonical_historical_expected_goals_successor_candidate_bytes(
        candidate
    )
    if (
        _sha(candidate_bytes) != SUCCESSOR_CANDIDATE_SHA256
        or len(candidate_bytes) != SUCCESSOR_CANDIDATE_SIZE
    ):
        raise _error("reconstructed PR73 candidate identity differs from PR74")
    candidate = revalidate_historical_expected_goals_successor_candidate(
        source_inputs=source_inputs,
        corpus=rebuilt_corpus,
        corpus_bytes=rebuilt_corpus_bytes,
        receipt_bytes=pr73_receipt_bytes,
        protocol=pr73_protocol,
        protocol_bytes=pr73_protocol_bytes,
        candidate=candidate,
        candidate_bytes=candidate_bytes,
    )
    if candidate.elo_initialization_semantics != ELO_INITIALIZATION_SEMANTICS:
        raise _error("rebuilt candidate Elo initialization semantics differ")
    if (
        candidate.fatigue_pr31_semantic_equivalence
        != FATIGUE_PR31_SEMANTIC_EQUIVALENCE
    ):
        raise _error("rebuilt candidate fatigue semantic equivalence differs")
    if (
        candidate.historical_freshness_regime_reconstructed
        is not HISTORICAL_FRESHNESS_REGIME_RECONSTRUCTED
    ):
        raise _error("rebuilt candidate historical freshness semantics differ")

    training = _ordered_eligible(
        pr73_protocol, rebuilt_corpus.fixtures, pr73_protocol.train_seasons
    )
    evaluation = _ordered_eligible(
        pr73_protocol, rebuilt_corpus.fixtures, pr73_protocol.evaluation_seasons
    )
    if len(training) != 14_130 or len(evaluation) != EVALUATION_FIXTURE_COUNT:
        raise _error("exact PR73 population membership differs from PR75")
    if tuple(
        (season, sum(item.season == season for item in training))
        for season in pr73_protocol.train_seasons
    ) != pr75_protocol.fatigue.training_season_counts:
        raise _error("PR73 training season membership differs from PR75")
    if tuple(
        (season, sum(item.season == season for item in evaluation))
        for season in pr73_protocol.evaluation_seasons
    ) != pr75_protocol.fatigue.evaluation_season_counts:
        raise _error("PR73 evaluation season membership differs from PR75")
    if {(item.season, item.identity_league) for item in evaluation} != set(
        CLUSTER_KEYS
    ):
        raise _error("PR73 evaluation clusters differ from PR75")

    training_fixture_ids = frozenset(item.fixture_identifier for item in training)
    evaluation_fixture_ids = frozenset(
        item.fixture_identifier for item in evaluation
    )
    if (
        training_fixture_ids & evaluation_fixture_ids
        or len(training_fixture_ids) != len(training)
        or len(evaluation_fixture_ids) != len(evaluation)
    ):
        raise _error("PR73 fixture split identities are not exact disjoint sets")

    calculation: list[RobustnessFixture] = []
    for fixture in tuple(training) + tuple(evaluation):
        home_rate, away_rate = _model_rates(
            pr73_protocol,
            fixture,
            candidate.fit_evaluation.home_fit,
            candidate.fit_evaluation.away_fit,
        )
        elo_home, elo_away = _legacy_rates(
            fixture, HistoricalExpectedGoalsComponent.ELO_FALLBACK_COMPONENT
        )
        full = _predictor_vector(pr73_protocol, fixture)
        calculation.append(
            RobustnessFixture(
                fixture_identifier=fixture.fixture_identifier,
                season=fixture.season,
                identity_league=fixture.identity_league,
                split=(
                    "TRAIN"
                    if fixture.fixture_identifier in training_fixture_ids
                    else "EVALUATION"
                ),
                home_goals=fixture.home_goals,
                away_goals=fixture.away_goals,
                successor_home_rate=home_rate,
                successor_away_rate=away_rate,
                elo_home_rate=elo_home,
                elo_away_rate=elo_away,
                no_fatigue_predictors=tuple(full[:5]),
                full_predictors=full,
            )
        )

    results = evaluate_successor_robustness_fixture_set(
        protocol=pr75_protocol,
        fixtures=tuple(calculation),
        fitting=pr73_protocol.fitting,
        full_home_fatigue=candidate.fit_evaluation.home_fit.coefficients[-1],
        full_away_fatigue=candidate.fit_evaluation.away_fit.coefficients[-1],
    )
    return HistoricalExpectedGoalsSuccessorRobustnessEvaluation(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        scope=EVALUATION_SCOPE,
        pr74_receipt_sha256=PR74_RECEIPT_SHA256,
        successor_candidate_sha256=SUCCESSOR_CANDIDATE_SHA256,
        successor_candidate_size=SUCCESSOR_CANDIDATE_SIZE,
        protocol_id=pr75_protocol.protocol_id,
        protocol_sha256=sha256_successor_robustness_protocol(pr75_protocol),
        protocol_size=len(pr75_protocol_bytes),
        source_corpus_sha256=rebuilt_corpus.source_corpus_sha256,
        elo_initialization_semantics=candidate.elo_initialization_semantics,
        fatigue_pr31_semantic_equivalence=(
            candidate.fatigue_pr31_semantic_equivalence
        ),
        historical_freshness_regime_reconstructed=(
            candidate.historical_freshness_regime_reconstructed
        ),
        provenance=SOURCE_BOUND_PROVENANCE,
        results=results,
        safety=_safety(),
    )


def revalidate_historical_expected_goals_successor_robustness_evaluation(
    *,
    receipt_bytes: bytes,
    protocol: HistoricalExpectedGoalsSuccessorRobustnessProtocol,
    protocol_bytes: bytes,
    evaluation: HistoricalExpectedGoalsSuccessorRobustnessEvaluation,
    evaluation_bytes: bytes,
) -> HistoricalExpectedGoalsSuccessorRobustnessEvaluation:
    """Structural-only revalidation; it does not establish source provenance."""
    if type(evaluation_bytes) is not bytes or not evaluation_bytes:
        raise _error("evaluation bytes must be exact non-empty bytes")
    if evaluation.provenance != SYNTHETIC_PROVENANCE:
        raise _error("structural revalidation requires synthetic provenance")
    rebuilt = build_historical_expected_goals_successor_robustness_evaluation(
        receipt_bytes=receipt_bytes,
        protocol=protocol,
        protocol_bytes=protocol_bytes,
        source_corpus_sha256=evaluation.source_corpus_sha256,
        results=evaluation.results,
    )
    expected = canonical_historical_expected_goals_successor_robustness_evaluation_bytes(
        rebuilt
    )
    if evaluation != rebuilt or evaluation_bytes != expected:
        raise _error("evaluation object or canonical bytes differ from rebuild")
    return rebuilt


def revalidate_source_bound_historical_expected_goals_successor_robustness_evaluation(
    *,
    source_inputs: Sequence[HistoricalReplaySourceInput],
    corpus: HistoricalReplayCorpus,
    corpus_bytes: bytes,
    pr73_receipt_bytes: bytes,
    pr73_protocol: HistoricalExpectedGoalsSuccessorProtocol,
    pr73_protocol_bytes: bytes,
    pr75_receipt_bytes: bytes,
    pr75_protocol: HistoricalExpectedGoalsSuccessorRobustnessProtocol,
    pr75_protocol_bytes: bytes,
    evaluation: HistoricalExpectedGoalsSuccessorRobustnessEvaluation,
    evaluation_bytes: bytes,
) -> HistoricalExpectedGoalsSuccessorRobustnessEvaluation:
    """Full replay revalidator for a future source-bound real evaluation."""
    if type(evaluation_bytes) is not bytes or not evaluation_bytes:
        raise _error("evaluation bytes must be exact non-empty bytes")
    if evaluation.provenance != SOURCE_BOUND_PROVENANCE:
        raise _error(
            "full source-bound revalidation requires source-bound result provenance"
        )
    rebuilt = build_source_bound_historical_expected_goals_successor_robustness_evaluation(
        source_inputs=source_inputs,
        corpus=corpus,
        corpus_bytes=corpus_bytes,
        pr73_receipt_bytes=pr73_receipt_bytes,
        pr73_protocol=pr73_protocol,
        pr73_protocol_bytes=pr73_protocol_bytes,
        pr75_receipt_bytes=pr75_receipt_bytes,
        pr75_protocol=pr75_protocol,
        pr75_protocol_bytes=pr75_protocol_bytes,
    )
    if rebuilt.provenance != SOURCE_BOUND_PROVENANCE:
        raise _error("source-bound builder did not return source-bound provenance")
    exact = canonical_historical_expected_goals_successor_robustness_evaluation_bytes(
        rebuilt
    )
    if evaluation != rebuilt or evaluation_bytes != exact:
        raise _error("source-bound evaluation differs from complete ancestry rebuild")
    return rebuilt
