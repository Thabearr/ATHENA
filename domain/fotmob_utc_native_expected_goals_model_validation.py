"""Execute the reviewed FotMob UTC-native expected-goals validation offline.

This module implements merged PR #140 exactly.  It consumes only the exact
qualified V2 feature projection, reuses ATHENA's reviewed deterministic
Poisson-GLM fitter, evaluates the five frozen arms on one common fixture
population, and emits hash-sealed research evidence.  It does not invoke
ScoreMatrix, calculate bookmaker prices, select bets, or authorize production.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import math
import platform
from pathlib import Path
import sys
import types
from typing import Any, Iterable, Mapping, Sequence

import domain.fotmob_utc_native_expected_goals_model_validation_protocol as pr140
import domain.historical_expected_goals_successor_robustness_evaluator as pr76


IMPLEMENTATION_STATE = (
    "IMPLEMENTED_REVIEWED_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION"
)
PROTOCOL_BLOB_SHA = "1780330c4d0ab9140f0b2f6c776dfe79073ca7f8"
SOURCE_NAMESPACE = "fotmob_data_matches_reviewed_ordinary_ft_finished_score"
FRESHNESS_STATUS = "NOT_RECONSTRUCTIBLE_WITH_CURRENT_EVIDENCE"
STRONG_STATE = "STRONG_FOTMOB_UTC_NATIVE_SUCCESSOR_SIGNAL_REVIEW_REQUIRED"
WEAK_STATE = "MIXED_OR_WEAK_FOTMOB_UTC_NATIVE_SUCCESSOR_SIGNAL_REVIEW_REQUIRED"
NEXT_REQUIRED_BOUNDARY = "REVIEW_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_RESULT"

MODEL_IDS = (
    "FOTMOB_NATIVE_SAME_FAMILY_REFIT",
    "HISTORICAL_FIXED_COEFFICIENT_TRANSFER",
    "FOTMOB_NATIVE_ELO_ONLY_NESTED_GLM",
    "FOTMOB_NATIVE_NO_FATIGUE_ABLATION",
    "TRAIN_ONLY_GLOBAL_HOME_AWAY_MEAN_BASELINE",
)

SAFETY_KEYS = pr140.SAFETY_KEYS


class FotMobUTCNativeExpectedGoalsModelValidationError(RuntimeError):
    """Raised when the reviewed model-validation contract cannot be proven."""


def _error(message: str) -> FotMobUTCNativeExpectedGoalsModelValidationError:
    return FotMobUTCNativeExpectedGoalsModelValidationError(message)


def _canonical(value: Any) -> bytes:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("canonical serialization failed") from exc
    return (text + "\n").encode("utf-8")


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def _finite(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise _error(f"{label} must be a finite numeric value")
    return float(value)


def _non_negative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise _error(f"{label} must be an exact non-negative integer")
    return value


def _exact_text(value: Any, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise _error(f"{label} must be exact non-empty text")
    return value


def _parse_utc(value: Any, label: str) -> dt.datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise _error(f"{label} must be exact UTC Z text")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise _error(f"{label} is malformed") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        raise _error(f"{label} must be timezone-aware UTC")
    return parsed.astimezone(dt.timezone.utc)


def _verify_protocol() -> dict[str, Any]:
    payload = pr140.build_fotmob_utc_native_expected_goals_model_validation_protocol()
    raw = pr140.canonical_fotmob_utc_native_expected_goals_model_validation_protocol_bytes()
    if (hashlib.sha256(raw).hexdigest(), len(raw)) != (
        pr140.PROTOCOL_SHA256,
        pr140.PROTOCOL_SIZE,
    ):
        raise _error("PR140 canonical protocol identity changed")
    if _git_blob_sha(Path(pr140.__file__)) != PROTOCOL_BLOB_SHA:
        raise _error("PR140 implementation blob changed")
    if payload["next_required_boundary"] != (
        "IMPLEMENT_REVIEWED_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION"
    ):
        raise _error("PR140 next boundary changed")
    if any(payload["safety"].values()):
        raise _error("PR140 safety boundary changed")
    return payload


@dataclasses.dataclass(frozen=True)
class ValidationFixture:
    fixture_identifier: str
    kickoff_utc_text: str
    kickoff_utc: dt.datetime
    home_goals: int
    away_goals: int
    predictors: tuple[float, float, float, float, float, float]

    def membership_record(self) -> bytes:
        return f"{self.kickoff_utc_text}\t{self.fixture_identifier}\n".encode("utf-8")


@dataclasses.dataclass(frozen=True)
class PredictionRecord:
    fixture_identifier: str
    kickoff_utc: str
    home_goals: int
    away_goals: int
    population: str
    predictions: Mapping[str, tuple[float, float]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "fixture_identifier": self.fixture_identifier,
            "kickoff_utc": self.kickoff_utc,
            "home_goals": self.home_goals,
            "away_goals": self.away_goals,
            "population": self.population,
            "predictions": {
                key: {"home_expected_goals": value[0], "away_expected_goals": value[1]}
                for key, value in sorted(self.predictions.items())
            },
        }


def _feature_mapping(row: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = row.get(key)
    if not isinstance(value, Mapping):
        raise _error(f"{key} must be an object")
    return value


def _available_numeric(
    feature: Mapping[str, Any],
    *,
    label: str,
    allowed_statuses: set[str],
) -> float | None:
    status = feature.get("status")
    value = feature.get("value")
    if status == "MISSING":
        if value is not None:
            raise _error(f"{label} MISSING value must be null")
        return None
    if status not in allowed_statuses:
        raise _error(f"{label} status is outside the reviewed vocabulary")
    if value is None:
        raise _error(f"{label} available value cannot be null")
    return _finite(value, f"{label} value")


def _validated_projection_row(value: Any) -> ValidationFixture | None:
    if not isinstance(value, Mapping):
        raise _error("projection row must be an object")
    if value.get("schema_version") != 1:
        raise _error("projection schema version changed")
    if value.get("source_namespace") != SOURCE_NAMESPACE:
        raise _error("projection source namespace changed")

    fixture_id = _exact_text(value.get("fixture_identifier"), "fixture_identifier")
    kickoff_text = _exact_text(value.get("kickoff_utc"), "kickoff_utc")
    kickoff = _parse_utc(kickoff_text, "kickoff_utc")
    home_goals = _non_negative_int(value.get("home_goals"), "home_goals")
    away_goals = _non_negative_int(value.get("away_goals"), "away_goals")

    home_form = _available_numeric(
        _feature_mapping(value, "home_form"),
        label="home_form",
        allowed_statuses={"CONSTRUCTED_FROM_STRICTLY_PRIOR_UTC_HISTORY"},
    )
    away_form = _available_numeric(
        _feature_mapping(value, "away_form"),
        label="away_form",
        allowed_statuses={"CONSTRUCTED_FROM_STRICTLY_PRIOR_UTC_HISTORY"},
    )
    fatigue = _available_numeric(
        _feature_mapping(value, "fatigue"),
        label="fatigue",
        allowed_statuses={"CONSTRUCTED_FROM_STRICTLY_PRIOR_UTC_HISTORY"},
    )

    home_elo_obj = _feature_mapping(value, "home_elo")
    away_elo_obj = _feature_mapping(value, "away_elo")
    elo_statuses = {
        "CONSTRUCTED_FROM_FROZEN_INITIAL_STATE_ASSUMPTION",
        "CONSTRUCTED_FROM_STRICTLY_PRIOR_UTC_HISTORY",
    }
    home_elo = _available_numeric(
        home_elo_obj,
        label="home_elo",
        allowed_statuses=elo_statuses,
    )
    away_elo = _available_numeric(
        away_elo_obj,
        label="away_elo",
        allowed_statuses=elo_statuses,
    )
    if home_elo is None or away_elo is None:
        raise _error("Elo must be available on every qualified projection row")
    if home_elo_obj.get("rating_component") != "OVERALL":
        raise _error("home Elo component changed")
    if away_elo_obj.get("rating_component") != "OVERALL":
        raise _error("away Elo component changed")

    freshness = _feature_mapping(value, "historical_live_data_freshness")
    if freshness.get("status") != FRESHNESS_STATUS or freshness.get("value") is not None:
        raise _error("historical freshness must remain blocked/null")

    if home_form is None or away_form is None or fatigue is None:
        return None

    return ValidationFixture(
        fixture_identifier=fixture_id,
        kickoff_utc_text=kickoff_text,
        kickoff_utc=kickoff,
        home_goals=home_goals,
        away_goals=away_goals,
        predictors=(
            1.0,
            (home_elo - 1500.0) / 400.0,
            (away_elo - 1500.0) / 400.0,
            home_form - 0.5,
            away_form - 0.5,
            fatigue,
        ),
    )


def parse_projection_bytes(raw: bytes) -> tuple[tuple[ValidationFixture, ...], int]:
    """Parse canonical V2 projection bytes and return complete cases + dropped rows."""
    if type(raw) is not bytes or not raw:
        raise _error("projection bytes must be non-empty exact bytes")
    complete: list[ValidationFixture] = []
    dropped = 0
    seen: set[str] = set()
    for line in raw.splitlines(keepends=True):
        if not line.endswith(b"\n"):
            raise _error("projection NDJSON row must end with newline")
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _error("projection NDJSON row is malformed") from exc
        if line != _canonical(value):
            raise _error("projection NDJSON row is not canonical JSON")
        fixture_id = value.get("fixture_identifier") if isinstance(value, Mapping) else None
        if type(fixture_id) is not str or fixture_id in seen:
            raise _error("projection fixture identity is missing or duplicated")
        seen.add(fixture_id)
        fixture = _validated_projection_row(value)
        if fixture is None:
            dropped += 1
        else:
            complete.append(fixture)
    complete.sort(key=lambda item: (item.kickoff_utc, item.fixture_identifier))
    return tuple(complete), dropped


def _membership_sha(fixtures: Sequence[ValidationFixture]) -> str:
    raw = b"".join(item.membership_record() for item in fixtures)
    return hashlib.sha256(raw).hexdigest()


def _split_complete_cases(
    fixtures: Sequence[ValidationFixture], protocol: Mapping[str, Any]
) -> tuple[tuple[ValidationFixture, ...], tuple[ValidationFixture, ...], tuple[ValidationFixture, ...]]:
    split = protocol["chronological_split_contract"]
    train_start = _parse_utc(split["train"]["start_inclusive"], "train start")
    train_end = _parse_utc(split["train"]["end_exclusive"], "train end")
    a_start = _parse_utc(split["evaluation_a"]["start_inclusive"], "A start")
    a_end = _parse_utc(split["evaluation_a"]["end_exclusive"], "A end")
    b_start = _parse_utc(split["evaluation_b_terminal"]["start_inclusive"], "B start")
    b_end = _parse_utc(split["evaluation_b_terminal"]["end_exclusive"], "B end")
    if not (train_end == a_start and a_end == b_start):
        raise _error("chronological split has a gap or overlap")

    train: list[ValidationFixture] = []
    evaluation_a: list[ValidationFixture] = []
    evaluation_b: list[ValidationFixture] = []
    for fixture in fixtures:
        kickoff = fixture.kickoff_utc
        if train_start <= kickoff < train_end:
            train.append(fixture)
        elif a_start <= kickoff < a_end:
            evaluation_a.append(fixture)
        elif b_start <= kickoff < b_end:
            evaluation_b.append(fixture)
        else:
            raise _error("complete-case fixture lies outside frozen split envelope")
    return tuple(train), tuple(evaluation_a), tuple(evaluation_b)


def _verify_frozen_membership(
    complete: Sequence[ValidationFixture],
    train: Sequence[ValidationFixture],
    evaluation_a: Sequence[ValidationFixture],
    evaluation_b: Sequence[ValidationFixture],
    protocol: Mapping[str, Any],
) -> dict[str, Any]:
    common = protocol["common_population_contract"]
    pooled = tuple(evaluation_a) + tuple(evaluation_b)
    checks = (
        ("all_complete", complete, common["all_complete_rows"], common["all_complete_membership_sha256"]),
        ("train", train, common["train_rows"], common["train_membership_sha256"]),
        ("evaluation_a", evaluation_a, common["evaluation_a_rows"], common["evaluation_a_membership_sha256"]),
        ("evaluation_b", evaluation_b, common["evaluation_b_rows"], common["evaluation_b_membership_sha256"]),
        ("pooled_evaluation", pooled, common["pooled_evaluation_rows"], common["pooled_evaluation_membership_sha256"]),
    )
    result: dict[str, Any] = {}
    for label, fixtures, expected_count, expected_sha in checks:
        actual_sha = _membership_sha(fixtures)
        if len(fixtures) != expected_count or actual_sha != expected_sha:
            raise _error(f"frozen {label} membership changed")
        result[label] = {"count": len(fixtures), "membership_sha256": actual_sha}
    return result


def _fitting_namespace(protocol: Mapping[str, Any]) -> Any:
    frozen = protocol["frozen_fitter_contract"]
    return types.SimpleNamespace(
        maximum_abs_linear_predictor=_finite(
            frozen["maximum_abs_linear_predictor"], "maximum eta"
        ),
        gradient_inf_norm_tolerance=_finite(
            frozen["gradient_inf_norm_tolerance"], "gradient tolerance"
        ),
        max_iterations=_non_negative_int(frozen["max_iterations"], "max_iterations"),
        linear_solve_pivot_tolerance=_finite(
            frozen["linear_solve_pivot_tolerance"], "pivot tolerance"
        ),
        backtracking_factor=_finite(frozen["backtracking_factor"], "backtracking factor"),
        minimum_step=_finite(frozen["minimum_step"], "minimum step"),
        coefficient_rounding_places=_non_negative_int(
            frozen["coefficient_rounding_places"], "coefficient rounding"
        ),
    )


def _fit(
    fixtures: Sequence[ValidationFixture],
    columns: tuple[int, ...],
    fitting: Any,
) -> tuple[pr76.PoissonFit, pr76.PoissonFit]:
    design = tuple(tuple(item.predictors[index] for index in columns) for item in fixtures)
    home = tuple(item.home_goals for item in fixtures)
    away = tuple(item.away_goals for item in fixtures)
    try:
        return (
            pr76.fit_poisson_design(rows=design, responses=home, fitting=fitting),
            pr76.fit_poisson_design(rows=design, responses=away, fitting=fitting),
        )
    except Exception as exc:
        raise _error("reviewed deterministic Poisson fitter failed") from exc


def _rate(
    fixture: ValidationFixture,
    coefficients: Sequence[float],
    columns: tuple[int, ...],
    fitting: Any,
) -> float:
    if len(coefficients) != len(columns):
        raise _error("coefficient dimension changed")
    eta = math.fsum(
        fixture.predictors[index] * coefficient
        for index, coefficient in zip(columns, coefficients)
    )
    if not math.isfinite(eta) or abs(eta) > fitting.maximum_abs_linear_predictor:
        raise _error("evaluation linear predictor exceeds frozen guard")
    rate = math.exp(eta)
    if not math.isfinite(rate) or rate <= 0.0:
        raise _error("expected-goals rate must be finite and positive")
    return rate


def _poisson_nll(goals: int, rate: float) -> float:
    return rate - goals * math.log(rate) + math.lgamma(goals + 1)


def _mean(values: Sequence[float], label: str) -> float:
    if not values:
        raise _error(f"{label} cannot be empty")
    value = math.fsum(values) / len(values)
    if not math.isfinite(value):
        raise _error(f"{label} is non-finite")
    return value


def _calibration(
    predictions: Sequence[float],
    outcomes: Sequence[int],
    bins: Sequence[Sequence[float | None]],
) -> tuple[tuple[dict[str, Any], ...], float, float]:
    if len(predictions) != len(outcomes) or not predictions:
        raise _error("calibration requires exact paired predictions/outcomes")
    result: list[dict[str, Any]] = []
    absolute_terms: list[float] = []
    squared_terms: list[float] = []
    for lower, upper in bins:
        selected = [
            (prediction, outcome)
            for prediction, outcome in zip(predictions, outcomes)
            if prediction >= float(lower)
            and (upper is None or prediction < float(upper))
        ]
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
            continue
        predicted = _mean([item[0] for item in selected], "calibration predicted mean")
        observed = _mean([float(item[1]) for item in selected], "calibration observed mean")
        error = predicted - observed
        count = len(selected)
        absolute_terms.append(count * abs(error))
        squared_terms.append(count * error * error)
        result.append(
            {
                "lower": lower,
                "upper": upper,
                "count": count,
                "mean_predicted_goals": predicted,
                "mean_observed_goals": observed,
                "calibration_error_predicted_minus_observed": error,
            }
        )
    if sum(item["count"] for item in result) != len(predictions):
        raise _error("calibration bins do not reconcile")
    return (
        tuple(result),
        math.fsum(absolute_terms) / len(predictions),
        math.fsum(squared_terms) / len(predictions),
    )


def _model_metrics(
    fixtures: Sequence[ValidationFixture],
    rates: Sequence[tuple[float, float]],
    bins: Sequence[Sequence[float | None]],
) -> dict[str, Any]:
    if len(fixtures) != len(rates) or not fixtures:
        raise _error("model metrics require exact non-empty paired fixtures/rates")
    home_predictions = [item[0] for item in rates]
    away_predictions = [item[1] for item in rates]
    home_actual = [item.home_goals for item in fixtures]
    away_actual = [item.away_goals for item in fixtures]
    home_nlls = [
        _poisson_nll(actual, predicted)
        for actual, predicted in zip(home_actual, home_predictions)
    ]
    away_nlls = [
        _poisson_nll(actual, predicted)
        for actual, predicted in zip(away_actual, away_predictions)
    ]
    home_bins, home_wace, home_wsce = _calibration(home_predictions, home_actual, bins)
    away_bins, away_wace, away_wsce = _calibration(away_predictions, away_actual, bins)
    return {
        "fixture_count": len(fixtures),
        "mean_joint_poisson_nll": _mean(
            [math.fsum((left, right)) for left, right in zip(home_nlls, away_nlls)],
            "mean joint NLL",
        ),
        "home_nll": _mean(home_nlls, "home NLL"),
        "away_nll": _mean(away_nlls, "away NLL"),
        "home_bias": _mean(home_predictions, "home prediction") - _mean(home_actual, "home actual"),
        "away_bias": _mean(away_predictions, "away prediction") - _mean(away_actual, "away actual"),
        "home_mae": _mean(
            [abs(predicted - actual) for predicted, actual in zip(home_predictions, home_actual)],
            "home MAE",
        ),
        "away_mae": _mean(
            [abs(predicted - actual) for predicted, actual in zip(away_predictions, away_actual)],
            "away MAE",
        ),
        "home_rmse": math.sqrt(
            _mean(
                [(predicted - actual) ** 2 for predicted, actual in zip(home_predictions, home_actual)],
                "home MSE",
            )
        ),
        "away_rmse": math.sqrt(
            _mean(
                [(predicted - actual) ** 2 for predicted, actual in zip(away_predictions, away_actual)],
                "away MSE",
            )
        ),
        "home_wace": home_wace,
        "away_wace": away_wace,
        "home_wsce": home_wsce,
        "away_wsce": away_wsce,
        "home_calibration": list(home_bins),
        "away_calibration": list(away_bins),
    }


def _prediction_rates(
    fixtures: Sequence[ValidationFixture],
    *,
    full_home: pr76.PoissonFit,
    full_away: pr76.PoissonFit,
    elo_home: pr76.PoissonFit,
    elo_away: pr76.PoissonFit,
    no_fatigue_home: pr76.PoissonFit,
    no_fatigue_away: pr76.PoissonFit,
    constant_home: float,
    constant_away: float,
    fitting: Any,
) -> dict[str, tuple[tuple[float, float], ...]]:
    result: dict[str, tuple[tuple[float, float], ...]] = {}
    result[MODEL_IDS[0]] = tuple(
        (
            _rate(item, full_home.coefficients, (0, 1, 2, 3, 4, 5), fitting),
            _rate(item, full_away.coefficients, (0, 1, 2, 3, 4, 5), fitting),
        )
        for item in fixtures
    )
    result[MODEL_IDS[1]] = tuple(
        (
            _rate(item, pr140.HISTORICAL_HOME_COEFFICIENTS, (0, 1, 2, 3, 4, 5), fitting),
            _rate(item, pr140.HISTORICAL_AWAY_COEFFICIENTS, (0, 1, 2, 3, 4, 5), fitting),
        )
        for item in fixtures
    )
    result[MODEL_IDS[2]] = tuple(
        (
            _rate(item, elo_home.coefficients, (0, 1, 2), fitting),
            _rate(item, elo_away.coefficients, (0, 1, 2), fitting),
        )
        for item in fixtures
    )
    result[MODEL_IDS[3]] = tuple(
        (
            _rate(item, no_fatigue_home.coefficients, (0, 1, 2, 3, 4), fitting),
            _rate(item, no_fatigue_away.coefficients, (0, 1, 2, 3, 4), fitting),
        )
        for item in fixtures
    )
    result[MODEL_IDS[4]] = tuple((constant_home, constant_away) for _ in fixtures)
    return result


def _paired_deltas(metrics: Mapping[str, Mapping[str, Any]]) -> dict[str, float]:
    nll = {key: float(value["mean_joint_poisson_nll"]) for key, value in metrics.items()}
    return {
        "NATIVE_REFIT_MINUS_ELO_ONLY": nll[MODEL_IDS[0]] - nll[MODEL_IDS[2]],
        "NATIVE_REFIT_MINUS_HISTORICAL_FIXED_TRANSFER": nll[MODEL_IDS[0]] - nll[MODEL_IDS[1]],
        "NATIVE_REFIT_MINUS_CONSTANT": nll[MODEL_IDS[0]] - nll[MODEL_IDS[4]],
        "HISTORICAL_FIXED_TRANSFER_MINUS_CONSTANT": nll[MODEL_IDS[1]] - nll[MODEL_IDS[4]],
        "NO_FATIGUE_MINUS_NATIVE_REFIT": nll[MODEL_IDS[3]] - nll[MODEL_IDS[0]],
    }


def _quarter_key(kickoff: dt.datetime) -> str:
    return f"{kickoff.year:04d}-Q{((kickoff.month - 1) // 3) + 1}"


def _quarter_jackknife(
    fixtures: Sequence[ValidationFixture],
    native_rates: Sequence[tuple[float, float]],
    elo_rates: Sequence[tuple[float, float]],
    expected_clusters: Sequence[Sequence[Any]],
) -> dict[str, Any]:
    if not (len(fixtures) == len(native_rates) == len(elo_rates)) or not fixtures:
        raise _error("quarter jackknife requires exact paired fixture populations")
    differences: list[tuple[str, float]] = []
    counts: dict[str, int] = {}
    for fixture, native, elo in zip(fixtures, native_rates, elo_rates):
        native_joint = math.fsum(
            (_poisson_nll(fixture.home_goals, native[0]), _poisson_nll(fixture.away_goals, native[1]))
        )
        elo_joint = math.fsum(
            (_poisson_nll(fixture.home_goals, elo[0]), _poisson_nll(fixture.away_goals, elo[1]))
        )
        key = _quarter_key(fixture.kickoff_utc)
        counts[key] = counts.get(key, 0) + 1
        differences.append((key, native_joint - elo_joint))

    expected = [(str(key), int(count)) for key, count in expected_clusters]
    if [(key, counts.get(key, 0)) for key, _ in expected] != expected:
        raise _error("UTC-quarter counts changed")
    if set(counts) != {key for key, _ in expected}:
        raise _error("unexpected UTC-quarter cluster observed")

    full = _mean([value for _, value in differences], "paired full estimate")
    deletes: list[dict[str, Any]] = []
    for key, omitted_count in expected:
        remaining = [value for cluster, value in differences if cluster != key]
        if len(remaining) != len(fixtures) - omitted_count:
            raise _error("delete-quarter remaining count changed")
        deletes.append(
            {
                "quarter": key,
                "omitted_fixture_count": omitted_count,
                "remaining_fixture_count": len(remaining),
                "delete_estimate": _mean(remaining, "delete-quarter estimate"),
            }
        )
    theta_bar = _mean([item["delete_estimate"] for item in deletes], "delete center")
    k = len(deletes)
    se = math.sqrt(
        ((k - 1) / k)
        * math.fsum((item["delete_estimate"] - theta_bar) ** 2 for item in deletes)
    )
    return {
        "population_rows": len(fixtures),
        "cluster_count": k,
        "full_estimate": full,
        "delete_estimate_center": theta_bar,
        "jackknife_standard_error": se,
        "interval_lower": full - 1.96 * se,
        "interval_upper": full + 1.96 * se,
        "delete_quarters": deletes,
    }


def _evaluate(
    train: Sequence[ValidationFixture],
    evaluation_a: Sequence[ValidationFixture],
    evaluation_b: Sequence[ValidationFixture],
    protocol: Mapping[str, Any],
) -> tuple[dict[str, Any], bytes]:
    fitting = _fitting_namespace(protocol)
    full_home, full_away = _fit(train, (0, 1, 2, 3, 4, 5), fitting)
    elo_home, elo_away = _fit(train, (0, 1, 2), fitting)
    no_fatigue_home, no_fatigue_away = _fit(train, (0, 1, 2, 3, 4), fitting)
    constant_home = _mean([item.home_goals for item in train], "training home-goal mean")
    constant_away = _mean([item.away_goals for item in train], "training away-goal mean")
    if constant_home <= 0.0 or constant_away <= 0.0:
        raise _error("training global goal means must be positive")

    bins = protocol["evaluation_contract"]["calibration_contract"]["bins"]
    population_fixtures = {
        "EVALUATION_A": tuple(evaluation_a),
        "EVALUATION_B_TERMINAL": tuple(evaluation_b),
        "POOLED_A_PLUS_B": tuple(evaluation_a) + tuple(evaluation_b),
    }
    population_results: dict[str, Any] = {}
    prediction_rows: list[PredictionRecord] = []
    pooled_rates: dict[str, tuple[tuple[float, float], ...]] | None = None

    for population_name, fixtures in population_fixtures.items():
        rates = _prediction_rates(
            fixtures,
            full_home=full_home,
            full_away=full_away,
            elo_home=elo_home,
            elo_away=elo_away,
            no_fatigue_home=no_fatigue_home,
            no_fatigue_away=no_fatigue_away,
            constant_home=constant_home,
            constant_away=constant_away,
            fitting=fitting,
        )
        metrics = {
            model_id: _model_metrics(fixtures, model_rates, bins)
            for model_id, model_rates in rates.items()
        }
        population_results[population_name] = {
            "models": metrics,
            "paired_nll_deltas": _paired_deltas(metrics),
        }
        if population_name == "POOLED_A_PLUS_B":
            pooled_rates = rates
        else:
            for index, fixture in enumerate(fixtures):
                prediction_rows.append(
                    PredictionRecord(
                        fixture_identifier=fixture.fixture_identifier,
                        kickoff_utc=fixture.kickoff_utc_text,
                        home_goals=fixture.home_goals,
                        away_goals=fixture.away_goals,
                        population=population_name,
                        predictions={key: value[index] for key, value in rates.items()},
                    )
                )

    assert pooled_rates is not None
    pooled = population_fixtures["POOLED_A_PLUS_B"]
    quarter = protocol["evaluation_contract"]["temporal_robustness"]
    jackknife = _quarter_jackknife(
        pooled,
        pooled_rates[MODEL_IDS[0]],
        pooled_rates[MODEL_IDS[2]],
        quarter["cluster_keys_and_counts"],
    )

    a_delta = population_results["EVALUATION_A"]["paired_nll_deltas"]["NATIVE_REFIT_MINUS_ELO_ONLY"]
    b_delta = population_results["EVALUATION_B_TERMINAL"]["paired_nll_deltas"]["NATIVE_REFIT_MINUS_ELO_ONLY"]
    pooled_delta = population_results["POOLED_A_PLUS_B"]["paired_nll_deltas"]["NATIVE_REFIT_MINUS_ELO_ONLY"]
    pooled_metrics = population_results["POOLED_A_PLUS_B"]["models"]
    native_metrics = pooled_metrics[MODEL_IDS[0]]
    elo_metrics = pooled_metrics[MODEL_IDS[2]]
    checks = {
        "all_lineage_split_missingness_and_common_membership_checks_pass": True,
        "native_home_and_away_fits_converge": True,
        "native_minus_elo_evaluation_a_nll_strictly_below_zero": a_delta < 0.0,
        "native_minus_elo_evaluation_b_nll_strictly_below_zero": b_delta < 0.0,
        "native_minus_elo_pooled_nll_strictly_below_zero": pooled_delta < 0.0,
        "quarter_jackknife_upper_95_percent_bound_strictly_below_zero": jackknife["interval_upper"] < 0.0,
        "pooled_native_home_wace_strictly_below_pooled_elo_home_wace": native_metrics["home_wace"] < elo_metrics["home_wace"],
        "pooled_native_away_wace_strictly_below_pooled_elo_away_wace": native_metrics["away_wace"] < elo_metrics["away_wace"],
        "pooled_native_home_wsce_strictly_below_pooled_elo_home_wsce": native_metrics["home_wsce"] < elo_metrics["home_wsce"],
        "pooled_native_away_wsce_strictly_below_pooled_elo_away_wsce": native_metrics["away_wsce"] < elo_metrics["away_wsce"],
    }
    required_rule = protocol["evaluation_contract"]["strong_signal_rule"]
    if set(checks) != set(required_rule) or not all(required_rule.values()):
        raise _error("strong-signal contract changed")
    signal_state = STRONG_STATE if all(checks.values()) else WEAK_STATE

    predictions = b"".join(_canonical(item.to_dict()) for item in prediction_rows)
    evaluation = {
        "signal_state": signal_state,
        "strong_signal_checks": checks,
        "fits": {
            MODEL_IDS[0]: {"home": full_home.to_dict(), "away": full_away.to_dict()},
            MODEL_IDS[1]: {
                "home_coefficients": list(pr140.HISTORICAL_HOME_COEFFICIENTS),
                "away_coefficients": list(pr140.HISTORICAL_AWAY_COEFFICIENTS),
                "fit_population": "NONE_FIXED_TRANSFER",
            },
            MODEL_IDS[2]: {"home": elo_home.to_dict(), "away": elo_away.to_dict()},
            MODEL_IDS[3]: {"home": no_fatigue_home.to_dict(), "away": no_fatigue_away.to_dict()},
            MODEL_IDS[4]: {
                "home_expected_goals": constant_home,
                "away_expected_goals": constant_away,
                "fit_population": "EXACT_COMMON_TRAIN_MEAN",
            },
        },
        "populations": population_results,
        "temporal_robustness": jackknife,
        "competition_or_league_robustness_status": (
            "BLOCKED_PROJECTION_DOES_NOT_CARRY_COMPETITION_IDENTITY"
        ),
    }
    return evaluation, predictions


def evaluate_synthetic_fixture_sets_for_tests(
    train: Sequence[ValidationFixture],
    evaluation_a: Sequence[ValidationFixture],
    evaluation_b: Sequence[ValidationFixture],
) -> dict[str, Any]:
    """Synthetic structural seam; it creates no source-bound evidence claim."""
    protocol = _verify_protocol()
    evaluation, predictions = _evaluate(train, evaluation_a, evaluation_b, protocol)
    return {
        "scope": "SYNTHETIC_STRUCTURAL_TEST_ONLY_NO_SOURCE_BOUND_EVIDENCE",
        "evaluation": evaluation,
        "predictions_sha256": hashlib.sha256(predictions).hexdigest(),
        "safety": {key: False for key in sorted(SAFETY_KEYS)},
    }


def build_validation(
    projection: Path,
    *,
    predictions_output: Path | None = None,
) -> tuple[dict[str, Any], bytes]:
    """Execute exact source-bound PR140 validation against the V2 projection."""
    protocol = _verify_protocol()
    projection = Path(projection)
    if not projection.is_file():
        raise _error("qualified V2 projection path does not exist")
    raw = projection.read_bytes()
    evidence = protocol["v2_success_evidence"]
    if (hashlib.sha256(raw).hexdigest(), len(raw)) != (
        evidence["projection_sha256"],
        evidence["projection_size_bytes"],
    ):
        raise _error("qualified V2 projection identity changed")
    if len(raw.splitlines()) != evidence["record_count"]:
        raise _error("qualified V2 projection row count changed")

    complete, dropped = parse_projection_bytes(raw)
    input_contract = protocol["frozen_input_contract"]
    if len(complete) != input_contract["complete_case_row_count"]:
        raise _error("complete-case population count changed")
    if dropped != input_contract["dropped_row_count"]:
        raise _error("dropped-row count changed")
    train, evaluation_a, evaluation_b = _split_complete_cases(complete, protocol)
    membership = _verify_frozen_membership(
        complete, train, evaluation_a, evaluation_b, protocol
    )
    evaluation, predictions = _evaluate(train, evaluation_a, evaluation_b, protocol)

    if predictions_output is not None:
        output = Path(predictions_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(predictions)

    receipt = {
        "schema_version": 1,
        "implementation_state": IMPLEMENTATION_STATE,
        "validation_state": evaluation["signal_state"],
        "protocol": {
            "id": pr140.PROTOCOL_ID,
            "sha256": pr140.PROTOCOL_SHA256,
            "size_bytes": pr140.PROTOCOL_SIZE,
            "implementation_blob_sha": PROTOCOL_BLOB_SHA,
        },
        "input_projection": {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
            "record_count": evidence["record_count"],
            "complete_case_count": len(complete),
            "dropped_incomplete_count": dropped,
            "membership": membership,
        },
        "research_training_executed": True,
        "evaluation": evaluation,
        "predictions": {
            "sha256": hashlib.sha256(predictions).hexdigest(),
            "size_bytes": len(predictions),
            "record_count": len(evaluation_a) + len(evaluation_b),
        },
        "runtime_provenance": {
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cross_runtime_bit_identity_claimed": False,
            "known_pr77_machine_precision_canonicalization_gap_cleared": False,
        },
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": {key: False for key in sorted(SAFETY_KEYS)},
    }
    return receipt, predictions


def canonical_validation_receipt_bytes(receipt: Mapping[str, Any]) -> bytes:
    if not isinstance(receipt, Mapping):
        raise _error("validation receipt must be a mapping")
    safety = receipt.get("safety")
    if not isinstance(safety, Mapping) or set(safety) != SAFETY_KEYS:
        raise _error("validation receipt safety keys changed")
    if any(type(value) is not bool or value is not False for value in safety.values()):
        raise _error("every validation receipt safety flag must remain exact False")
    return _canonical(dict(receipt))


__all__ = [
    "IMPLEMENTATION_STATE",
    "MODEL_IDS",
    "NEXT_REQUIRED_BOUNDARY",
    "PROTOCOL_BLOB_SHA",
    "STRONG_STATE",
    "WEAK_STATE",
    "FotMobUTCNativeExpectedGoalsModelValidationError",
    "PredictionRecord",
    "ValidationFixture",
    "build_validation",
    "canonical_validation_receipt_bytes",
    "evaluate_synthetic_fixture_sets_for_tests",
    "parse_projection_bytes",
]
