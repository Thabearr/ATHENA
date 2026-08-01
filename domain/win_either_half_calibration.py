"""Leakage-safe Stage 4B calibration and subgroup stability research.

The frozen Stage 4A base model is refitted without changing its configuration.
Calibrators learn only from expanding-season out-of-fold TRAIN probabilities.
VALIDATION selects a calibrator, and TEST is transformed only after both target
selections are fixed.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence, Tuple

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from threadpoolctl import threadpool_limits

from domain.win_either_half_benchmarks import (
    BenchmarkError,
    CANONICAL_DECIMAL_PLACES,
    DEFAULT_RANDOM_SEED,
    NUMERICAL_THREAD_LIMIT,
    SPLITS,
    TARGETS,
    ModelConfiguration,
    canonical_float,
    canonicalize_probabilities,
    fit_benchmark_candidate,
    fit_train_preprocessor,
    probability_metrics,
)


TRAIN_SEASONS = ("2020-21", "2021-22", "2022-23", "2023-24")
VALIDATION_SEASONS = ("2024-25",)
TEST_SEASONS = ("2025-26",)
OOF_TARGET_SEASONS = TRAIN_SEASONS[1:]
PLATT_LOGIT_EPSILON = 1e-6
PLATT_MAX_ITERATIONS = 2000
ISOTONIC_MIN_UNIQUE_PREDICTIONS = 3
SUBGROUP_MINIMUM_ROWS = 100
PROBABILITY_BANDS = (
    ("[0.0,0.2)", 0.0, 0.2, False),
    ("[0.2,0.4)", 0.2, 0.4, False),
    ("[0.4,0.6)", 0.4, 0.6, False),
    ("[0.6,0.8)", 0.6, 0.8, False),
    ("[0.8,1.0]", 0.8, 1.0, True),
)
CALIBRATION_SELECTION_RULE = (
    "lowest canonical VALIDATION log loss; then lowest canonical VALIDATION "
    "Brier score; then lower declared calibration complexity; then lexical "
    "candidate identifier"
)


class CalibrationError(ValueError):
    """Raised when Stage 4B input or fitting fails a research safety gate."""


def _canonical_probabilities(probabilities: Sequence[float]) -> np.ndarray:
    try:
        return canonicalize_probabilities(probabilities)
    except BenchmarkError as error:
        raise CalibrationError(str(error)) from error


@dataclass(frozen=True)
class CalibrationConfiguration:
    identifier: str
    family: str
    complexity_rank: int
    parameters: Tuple[Tuple[str, object], ...]

    def parameter_dict(self) -> dict:
        return dict(self.parameters)

    def to_dict(self) -> dict:
        return {
            "complexity_rank": self.complexity_rank,
            "family": self.family,
            "identifier": self.identifier,
            "parameters": self.parameter_dict(),
        }


def default_calibration_configurations(
    random_seed: int = DEFAULT_RANDOM_SEED,
) -> Tuple[CalibrationConfiguration, ...]:
    values = (
        CalibrationConfiguration(
            identifier="identity_calibration_v1",
            family="identity",
            complexity_rank=0,
            parameters=(),
        ),
        CalibrationConfiguration(
            identifier="platt_logit_calibration_v1",
            family="platt_logit",
            complexity_rank=1,
            parameters=(
                ("C", 1e12),
                ("epsilon", PLATT_LOGIT_EPSILON),
                ("max_iter", PLATT_MAX_ITERATIONS),
                ("random_state", random_seed),
                ("solver", "lbfgs"),
            ),
        ),
        CalibrationConfiguration(
            identifier="isotonic_calibration_v1",
            family="isotonic",
            complexity_rank=2,
            parameters=(
                ("increasing", True),
                ("minimum_unique_predictions", ISOTONIC_MIN_UNIQUE_PREDICTIONS),
                ("out_of_bounds", "clip"),
            ),
        ),
    )
    return tuple(sorted(values, key=lambda value: value.identifier))


def _binary_targets(rows: Sequence[Mapping], target: str) -> np.ndarray:
    values = []
    for row in rows:
        value = row.get(target)
        if isinstance(value, bool) or value not in (0, 1):
            raise CalibrationError(f"Target {target} must contain integer 0/1")
        values.append(int(value))
    return np.asarray(values, dtype=int)


def _logit(probabilities: np.ndarray, epsilon: float) -> np.ndarray:
    clipped = np.clip(probabilities, epsilon, 1.0 - epsilon)
    return np.log(clipped / (1.0 - clipped))


@dataclass
class FittedCalibrator:
    configuration: CalibrationConfiguration
    status: str
    reason: str | None = None
    estimator: object | None = None

    def transform(self, probabilities: Sequence[float]) -> np.ndarray:
        values = _canonical_probabilities(probabilities)
        if self.status != "AVAILABLE":
            raise CalibrationError(
                f"Calibration candidate is unavailable: {self.configuration.identifier}"
            )
        if self.configuration.family == "identity":
            return values
        if self.configuration.family == "platt_logit":
            epsilon = float(self.configuration.parameter_dict()["epsilon"])
            logits = _logit(values, epsilon).reshape(-1, 1)
            with threadpool_limits(limits=NUMERICAL_THREAD_LIMIT):
                transformed = self.estimator.predict_proba(logits)[:, 1]
            return _canonical_probabilities(transformed)
        if self.configuration.family == "isotonic":
            with threadpool_limits(limits=NUMERICAL_THREAD_LIMIT):
                transformed = self.estimator.predict(values)
            return _canonical_probabilities(transformed)
        raise CalibrationError(
            f"Unsupported calibration family: {self.configuration.family}"
        )

    def audit(self) -> dict:
        audit = {
            "configuration": self.configuration.to_dict(),
            "reason": self.reason,
            "status": self.status,
        }
        if self.status == "AVAILABLE" and self.configuration.family == "platt_logit":
            audit["fitted_parameters"] = {
                "intercept": canonical_float(self.estimator.intercept_[0]),
                "slope": canonical_float(self.estimator.coef_[0][0]),
            }
        elif self.status == "AVAILABLE" and self.configuration.family == "isotonic":
            audit["fitted_parameters"] = {
                "input_maximum": canonical_float(self.estimator.X_max_),
                "input_minimum": canonical_float(self.estimator.X_min_),
                "threshold_count": len(self.estimator.X_thresholds_),
            }
        else:
            audit["fitted_parameters"] = None
        return audit


def fit_calibrator(
    configuration: CalibrationConfiguration,
    probabilities: Sequence[float],
    targets: Sequence[int],
    *,
    target_name: str,
) -> FittedCalibrator:
    values = _canonical_probabilities(probabilities)
    observed = np.asarray(targets, dtype=int)
    if len(values) == 0 or len(values) != len(observed):
        raise CalibrationError("Calibration inputs must have equal non-zero length")
    if not set(np.unique(observed)).issubset({0, 1}):
        raise CalibrationError("Calibration outcomes must be binary")
    if configuration.family == "identity":
        return FittedCalibrator(configuration, "AVAILABLE")
    if len(np.unique(observed)) < 2:
        return FittedCalibrator(configuration, "UNAVAILABLE", "SINGLE_CLASS")
    if configuration.family == "platt_logit":
        if len(np.unique(values)) < 2:
            return FittedCalibrator(
                configuration,
                "UNAVAILABLE",
                "INSUFFICIENT_UNIQUE_PROBABILITIES",
            )
        parameters = configuration.parameter_dict()
        epsilon = float(parameters["epsilon"])
        estimator = LogisticRegression(
            C=float(parameters["C"]),
            max_iter=int(parameters["max_iter"]),
            random_state=int(parameters["random_state"]),
            solver=str(parameters["solver"]),
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ConvergenceWarning)
            with threadpool_limits(limits=NUMERICAL_THREAD_LIMIT):
                estimator.fit(_logit(values, epsilon).reshape(-1, 1), observed)
        non_converged = any(
            issubclass(warning.category, ConvergenceWarning) for warning in caught
        ) or bool(np.any(np.asarray(estimator.n_iter_) >= estimator.max_iter))
        if non_converged:
            raise CalibrationError(
                "Calibration candidate did not converge for target "
                f"{target_name}: {configuration.identifier}"
            )
        return FittedCalibrator(configuration, "AVAILABLE", estimator=estimator)
    if configuration.family == "isotonic":
        minimum = int(
            configuration.parameter_dict()["minimum_unique_predictions"]
        )
        if len(np.unique(values)) < minimum:
            return FittedCalibrator(
                configuration,
                "UNAVAILABLE",
                "INSUFFICIENT_UNIQUE_PROBABILITIES",
            )
        estimator = IsotonicRegression(increasing=True, out_of_bounds="clip")
        with threadpool_limits(limits=NUMERICAL_THREAD_LIMIT):
            estimator.fit(values, observed)
        return FittedCalibrator(configuration, "AVAILABLE", estimator=estimator)
    raise CalibrationError(
        f"Unsupported calibration family: {configuration.family}"
    )


def _fit_base_model(
    train_rows: Sequence[Mapping],
    prediction_rows: Sequence[Mapping],
    feature_names: Sequence[str],
    configuration: ModelConfiguration,
    target: str,
):
    preprocessor = fit_train_preprocessor(train_rows, feature_names)
    train_imputed, train_scaled, _ = preprocessor.transform(train_rows)
    fitted = fit_benchmark_candidate(
        configuration,
        train_imputed=train_imputed,
        train_scaled=train_scaled,
        train_targets=_binary_targets(train_rows, target),
        target_name=target,
    )
    predict_imputed, predict_scaled, _ = preprocessor.transform(prediction_rows)
    return fitted.predict(predict_imputed, predict_scaled), preprocessor, fitted


def build_expanding_oof_predictions(
    train_rows: Iterable[Mapping],
    feature_names: Sequence[str],
    configuration: ModelConfiguration,
    target: str,
) -> dict:
    supplied_rows = tuple(train_rows)
    if any(row.get("season") not in TRAIN_SEASONS for row in supplied_rows):
        raise CalibrationError("OOF TRAIN seasons differ from the frozen contract")
    rows = tuple(
        sorted(
            supplied_rows,
            key=lambda row: (TRAIN_SEASONS.index(row["season"]), row["fixture_identity"]),
        )
    )
    if not rows or any(row.get("split") != "TRAIN" for row in rows):
        raise CalibrationError("OOF construction accepts TRAIN rows only")
    seasons = {row.get("season") for row in rows}
    if seasons != set(TRAIN_SEASONS):
        raise CalibrationError("OOF TRAIN seasons differ from the frozen contract")
    predictions = []
    folds = []
    for target_season in OOF_TARGET_SEASONS:
        target_index = TRAIN_SEASONS.index(target_season)
        fit_seasons = TRAIN_SEASONS[:target_index]
        fit_rows = tuple(row for row in rows if row["season"] in fit_seasons)
        holdout_rows = tuple(row for row in rows if row["season"] == target_season)
        probabilities, _, _ = _fit_base_model(
            fit_rows,
            holdout_rows,
            feature_names,
            configuration,
            target,
        )
        for row, probability in zip(holdout_rows, probabilities):
            predictions.append(
                {
                    "fixture_identity": row["fixture_identity"],
                    "fit_seasons": list(fit_seasons),
                    "kickoff_utc": row["kickoff_utc"],
                    "league": row["league"],
                    "model_probability": float(probability),
                    "season": row["season"],
                    "split": "TRAIN",
                    "target_name": target,
                    "target_value": int(row[target]),
                }
            )
        folds.append(
            {
                "fit_rows": len(fit_rows),
                "fit_seasons": list(fit_seasons),
                "prediction_rows": len(holdout_rows),
                "prediction_season": target_season,
            }
        )
    predictions.sort(key=lambda row: (row["season"], row["fixture_identity"]))
    return {"folds": folds, "predictions": predictions}


def select_calibration_winner(candidate_summaries: Sequence[Mapping]) -> str:
    available = [value for value in candidate_summaries if value["status"] == "AVAILABLE"]
    if not available:
        raise CalibrationError("No calibration candidate is available")
    ordered = sorted(
        available,
        key=lambda value: (
            canonical_float(value["metrics"]["log_loss"]),
            canonical_float(value["metrics"]["brier_score"]),
            value["complexity_rank"],
            value["candidate_identifier"],
        ),
    )
    return ordered[0]["candidate_identifier"]


def _metric_deltas(candidate: Mapping, identity: Mapping) -> dict:
    fields = {
        "average_precision": "average_precision",
        "brier_score": "brier_score",
        "expected_calibration_error": "calibration.expected_calibration_error",
        "log_loss": "log_loss",
        "roc_auc": "roc_auc",
    }

    def read(source, path):
        value = source
        for part in path.split("."):
            value = value.get(part) if isinstance(value, Mapping) else None
        return value

    return {
        name: (
            canonical_float(read(candidate, path) - read(identity, path))
            if read(candidate, path) is not None and read(identity, path) is not None
            else None
        )
        for name, path in fields.items()
    }


def _subgroup_metrics(targets, probabilities) -> dict:
    if not len(targets):
        return {
            "metrics": {
                "average_precision": None,
                "brier_score": None,
                "calibration": {
                    "actual_bin_count": 0,
                    "bins": [],
                    "expected_calibration_error": None,
                    "intercept": None,
                    "reason": "INSUFFICIENT_ROWS",
                    "slope": None,
                    "status": "UNAVAILABLE",
                },
                "log_loss": None,
                "positive_count": 0,
                "prevalence": None,
                "probability_diagnostics": {
                    "count_nan_or_infinite": 0,
                    "count_outside_unit_interval": 0,
                    "maximum": None,
                    "mean": None,
                    "minimum": None,
                },
                "roc_auc": None,
                "row_count": 0,
                "threshold_diagnostics": {
                    threshold: {
                        "precision": None,
                        "qualifying_predictions": 0,
                        "recall": None,
                    }
                    for threshold in ("0.50", "0.60", "0.70")
                },
            },
            "metric_reasons": ["INSUFFICIENT_ROWS"],
        }
    metrics = probability_metrics(targets, probabilities)
    reasons = []
    if len(set(targets)) < 2:
        metrics["average_precision"] = None
        reasons.append("SINGLE_CLASS")
    if len(set(probabilities)) < 2:
        reasons.append("INSUFFICIENT_UNIQUE_PROBABILITIES")
    if metrics["calibration"].get("status") == "UNAVAILABLE":
        reason = metrics["calibration"].get("reason")
        if reason and reason not in reasons:
            reasons.append(reason)
    return {"metric_reasons": sorted(reasons), "metrics": metrics}


def _subgroup_record(
    *,
    target: str,
    dimension: str,
    group: str,
    rows: Sequence[Mapping],
) -> dict:
    row_count = len(rows)
    if row_count == 0:
        support_status = "UNAVAILABLE"
        support_reason = "INSUFFICIENT_ROWS"
    elif row_count < SUBGROUP_MINIMUM_ROWS:
        support_status = "LOW_SUPPORT"
        support_reason = "INSUFFICIENT_ROWS"
    else:
        support_status = "SUPPORTED"
        support_reason = None
    targets = [row["target_value"] for row in rows]
    identity = _subgroup_metrics(
        targets, [row["model_probability"] for row in rows]
    )
    selected = _subgroup_metrics(
        targets, [row["calibrated_probability"] for row in rows]
    )
    return {
        "dimension": dimension,
        "group": group,
        "identity": identity,
        "metric_deltas": _metric_deltas(
            selected["metrics"], identity["metrics"]
        ),
        "negative_count": row_count - sum(targets),
        "positive_count": sum(targets),
        "row_count": row_count,
        "selected_calibration": selected,
        "support_reason": support_reason,
        "support_status": support_status,
        "target_name": target,
    }


def build_subgroup_evaluations(prediction_rows: Sequence[Mapping]) -> list:
    records = []
    for target in TARGETS:
        target_rows = tuple(row for row in prediction_rows if row["target_name"] == target)
        dimensions = {
            "split": [
                (split, tuple(row for row in target_rows if row["split"] == split))
                for split in SPLITS
            ],
            "season": [
                (season, tuple(row for row in target_rows if row["season"] == season))
                for season in (*TRAIN_SEASONS, *VALIDATION_SEASONS, *TEST_SEASONS)
            ],
            "league": [
                (league, tuple(row for row in target_rows if row["league"] == league))
                for league in sorted({row["league"] for row in target_rows})
            ],
            "league_and_season": [
                (
                    f"{league}|{season}",
                    tuple(
                        row
                        for row in target_rows
                        if row["league"] == league and row["season"] == season
                    ),
                )
                for league, season in sorted(
                    {(row["league"], row["season"]) for row in target_rows}
                )
            ],
            "model_probability_band": [
                (
                    name,
                    tuple(
                        row
                        for row in target_rows
                        if row["model_probability"] >= lower
                        and (
                            row["model_probability"] <= upper
                            if inclusive_upper
                            else row["model_probability"] < upper
                        )
                    ),
                )
                for name, lower, upper, inclusive_upper in PROBABILITY_BANDS
            ],
        }
        for dimension, groups in dimensions.items():
            for group, rows in groups:
                records.append(
                    _subgroup_record(
                        target=target,
                        dimension=dimension,
                        group=group,
                        rows=rows,
                    )
                )
    records.sort(key=lambda row: (row["target_name"], row["dimension"], row["group"]))
    return records


def _assert_frozen_probability_match(
    rows: Sequence[Mapping],
    probabilities: Sequence[float],
    frozen_predictions: Mapping[tuple, float],
    target: str,
) -> None:
    for row, probability in zip(rows, probabilities):
        key = (str(row["fixture_identity"]), target)
        if key not in frozen_predictions:
            raise CalibrationError("Frozen Stage 4A prediction row is missing")
        if canonical_float(probability) != canonical_float(frozen_predictions[key]):
            raise CalibrationError(
                f"Refitted Stage 4A probability differs for {target}: {key[0]}"
            )


def run_calibration_research(
    feature_rows: Iterable[Mapping],
    feature_names: Sequence[str],
    *,
    selected_model_configurations: Mapping[str, ModelConfiguration],
    frozen_predictions: Sequence[Mapping],
    calibration_configurations: Sequence[CalibrationConfiguration] | None = None,
    random_seed: int = DEFAULT_RANDOM_SEED,
) -> dict:
    supplied_rows = tuple(feature_rows)
    if not supplied_rows:
        raise CalibrationError("Feature dataset is empty")
    if any(row.get("split") not in SPLITS for row in supplied_rows):
        raise CalibrationError("Every feature row must use a frozen split")
    rows = tuple(
        sorted(
            supplied_rows,
            key=lambda row: (SPLITS.index(row["split"]), row["fixture_identity"]),
        )
    )
    if len({row["fixture_identity"] for row in rows}) != len(rows):
        raise CalibrationError("Feature fixture identities must be unique")
    expected_seasons = {
        "TRAIN": set(TRAIN_SEASONS),
        "VALIDATION": set(VALIDATION_SEASONS),
        "TEST": set(TEST_SEASONS),
    }
    split_rows = {split: tuple(row for row in rows if row["split"] == split) for split in SPLITS}
    for split in SPLITS:
        if {row["season"] for row in split_rows[split]} != expected_seasons[split]:
            raise CalibrationError(f"{split} seasons differ from the frozen contract")
    frozen = {
        (str(row["fixture_identity"]), str(row["target_name"])): float(
            row["predicted_probability"]
        )
        for row in frozen_predictions
    }
    if len(frozen) != len(rows) * len(TARGETS):
        raise CalibrationError("Frozen Stage 4A prediction accounting differs")
    configurations = tuple(
        sorted(
            calibration_configurations or default_calibration_configurations(random_seed),
            key=lambda value: value.identifier,
        )
    )
    if len({value.identifier for value in configurations}) != len(configurations):
        raise CalibrationError("Calibration candidate identifiers must be unique")

    target_results = {}
    fitted_state = {}
    protocol_events = []
    for target in TARGETS:
        base_configuration = selected_model_configurations.get(target)
        if (
            base_configuration is None
            or base_configuration.identifier != "logistic_l2_c0.1_v1"
        ):
            raise CalibrationError(f"Frozen Stage 4A selected model drifted: {target}")
        oof = build_expanding_oof_predictions(
            split_rows["TRAIN"], feature_names, base_configuration, target
        )
        oof_probabilities = [row["model_probability"] for row in oof["predictions"]]
        oof_targets = [row["target_value"] for row in oof["predictions"]]
        calibrators = {
            configuration.identifier: fit_calibrator(
                configuration,
                oof_probabilities,
                oof_targets,
                target_name=target,
            )
            for configuration in configurations
        }
        protocol_events.append(f"calibrators_fitted_from_train_oof:{target}")
        validation_probabilities, preprocessor, base_model = _fit_base_model(
            split_rows["TRAIN"],
            split_rows["VALIDATION"],
            feature_names,
            base_configuration,
            target,
        )
        _assert_frozen_probability_match(
            split_rows["VALIDATION"], validation_probabilities, frozen, target
        )
        validation_targets = _binary_targets(split_rows["VALIDATION"], target)
        identity_metrics = probability_metrics(
            validation_targets, validation_probabilities, random_seed=random_seed
        )
        candidate_summaries = []
        for configuration in configurations:
            calibrator = calibrators[configuration.identifier]
            summary = {
                "candidate_identifier": configuration.identifier,
                "complexity_rank": configuration.complexity_rank,
                "fit": calibrator.audit(),
                "metrics": None,
                "metric_deltas_from_identity": None,
                "reason": calibrator.reason,
                "status": calibrator.status,
            }
            if calibrator.status == "AVAILABLE":
                transformed = calibrator.transform(validation_probabilities)
                metrics = probability_metrics(
                    validation_targets, transformed, random_seed=random_seed
                )
                summary["metrics"] = metrics
                summary["metric_deltas_from_identity"] = _metric_deltas(
                    metrics, identity_metrics
                )
            candidate_summaries.append(summary)
        selected = select_calibration_winner(candidate_summaries)
        target_results[target] = {
            "calibration_candidates": candidate_summaries,
            "oof": {
                "excluded_seasons": [TRAIN_SEASONS[0]],
                "fit_rows": len(oof["predictions"]),
                "folds": oof["folds"],
            },
            "selected_calibration_identifier": selected,
            "validation_identity_metrics": identity_metrics,
        }
        fitted_state[target] = {
            "base_model": base_model,
            "base_preprocessor": preprocessor,
            "calibrators": calibrators,
            "oof": oof,
            "selected": selected,
        }
        protocol_events.append(f"validation_selected:{target}:{selected}")

    protocol_events.append("both_calibrations_frozen_before_test_transform")
    prediction_rows = []
    for target in TARGETS:
        state = fitted_state[target]
        selected_calibrator = state["calibrators"][state["selected"]]
        oof_rows = state["oof"]["predictions"]
        for row in oof_rows:
            calibrated = selected_calibrator.transform([row["model_probability"]])[0]
            prediction_rows.append(
                {
                    **{key: row[key] for key in (
                        "fixture_identity", "kickoff_utc", "league", "season",
                        "split", "target_name", "target_value",
                    )},
                    "base_model_identifier": selected_model_configurations[target].identifier,
                    "calibrated_probability": float(calibrated),
                    "calibration_identifier": state["selected"],
                    "model_probability": row["model_probability"],
                    "prediction_role": "CALIBRATION_FIT_OOF",
                }
            )
        for split in ("VALIDATION", "TEST"):
            current_rows = split_rows[split]
            imputed, scaled, _ = state["base_preprocessor"].transform(current_rows)
            base_probabilities = state["base_model"].predict(imputed, scaled)
            _assert_frozen_probability_match(current_rows, base_probabilities, frozen, target)
            calibrated_probabilities = selected_calibrator.transform(base_probabilities)
            targets = _binary_targets(current_rows, target)
            if split == "TEST":
                target_results[target]["test_identity_metrics"] = probability_metrics(
                    targets, base_probabilities, random_seed=random_seed
                )
                selected_metrics = probability_metrics(
                    targets, calibrated_probabilities, random_seed=random_seed
                )
                target_results[target]["test_selected_metrics"] = selected_metrics
                target_results[target]["test_metric_deltas_from_identity"] = _metric_deltas(
                    selected_metrics,
                    target_results[target]["test_identity_metrics"],
                )
                protocol_events.append(f"test_evaluated_once:{target}")
            for row, observed, base_probability, calibrated_probability in zip(
                current_rows,
                targets,
                base_probabilities,
                calibrated_probabilities,
            ):
                prediction_rows.append(
                    {
                        "base_model_identifier": selected_model_configurations[target].identifier,
                        "calibrated_probability": float(calibrated_probability),
                        "calibration_identifier": state["selected"],
                        "fixture_identity": row["fixture_identity"],
                        "kickoff_utc": row["kickoff_utc"],
                        "league": row["league"],
                        "model_probability": float(base_probability),
                        "prediction_role": "VALIDATION_SELECTION" if split == "VALIDATION" else "FINAL_TEST",
                        "season": row["season"],
                        "split": split,
                        "target_name": target,
                        "target_value": int(observed),
                    }
                )
    prediction_rows.sort(
        key=lambda row: (row["target_name"], SPLITS.index(row["split"]), row["fixture_identity"])
    )
    subgroup_rows = build_subgroup_evaluations(prediction_rows)
    return {
        "calibration": {
            "calibration_configurations": [value.to_dict() for value in configurations],
            "canonical_decimal_places": CANONICAL_DECIMAL_PLACES,
            "model_probability_bands": [value[0] for value in PROBABILITY_BANDS],
            "platt_logit_epsilon": PLATT_LOGIT_EPSILON,
            "protocol_events": protocol_events,
            "random_seed": random_seed,
            "selection_rule": CALIBRATION_SELECTION_RULE,
            "subgroup_minimum_rows": SUBGROUP_MINIMUM_ROWS,
            "targets": target_results,
            "thread_limit": NUMERICAL_THREAD_LIMIT,
        },
        "prediction_rows": prediction_rows,
        "subgroup_rows": subgroup_rows,
    }


__all__ = [
    "CALIBRATION_SELECTION_RULE",
    "CalibrationConfiguration",
    "CalibrationError",
    "FittedCalibrator",
    "ISOTONIC_MIN_UNIQUE_PREDICTIONS",
    "OOF_TARGET_SEASONS",
    "PLATT_LOGIT_EPSILON",
    "PLATT_MAX_ITERATIONS",
    "PROBABILITY_BANDS",
    "SUBGROUP_MINIMUM_ROWS",
    "TEST_SEASONS",
    "TRAIN_SEASONS",
    "VALIDATION_SEASONS",
    "build_expanding_oof_predictions",
    "build_subgroup_evaluations",
    "default_calibration_configurations",
    "fit_calibrator",
    "run_calibration_research",
    "select_calibration_winner",
]
