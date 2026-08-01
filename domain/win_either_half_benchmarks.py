"""Deterministic Stage 4A baselines for Win Either Half research.

Only columns frozen as ``PRE_MATCH_FEATURE`` may enter preprocessing or model
fitting.  TRAIN fits preprocessing and models, VALIDATION selects a winner,
and TEST is transformed and evaluated only after both target winners are fixed.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence, Tuple

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)
from sklearn.tree import DecisionTreeClassifier
from threadpoolctl import threadpool_limits


TARGETS = (
    "home_win_either_half_yes",
    "away_win_either_half_yes",
)
FORBIDDEN_PREDICTOR_NAMES = frozenset(
    (
        "fixture_identity",
        "kickoff_utc",
        "league",
        "season",
        "split",
        "home_team",
        "away_team",
        "home_win_either_half_yes",
        "away_win_either_half_yes",
        "both_teams_won_a_half",
    )
)
SPLITS = ("TRAIN", "VALIDATION", "TEST")
SPLIT_ORDER = {name: index for index, name in enumerate(SPLITS)}
DESCRIPTIVE_THRESHOLDS = (0.50, 0.60, 0.70)
DEFAULT_RANDOM_SEED = 1729
CALIBRATION_BIN_COUNT = 10
CANONICAL_DECIMAL_PLACES = 12
CANONICAL_QUANTUM = 10.0 ** -CANONICAL_DECIMAL_PLACES
NUMERICAL_THREAD_LIMIT = 1
SELECTION_RULE = (
    "lowest VALIDATION log loss; then lowest VALIDATION Brier score; "
    "then lower declared complexity rank; then lexical model identifier"
)


class BenchmarkError(ValueError):
    """Raised when a benchmark input violates the frozen research contract."""


def canonical_float(value: float) -> float:
    """Round a reported float to the Stage 4A canonical decimal precision."""
    numeric = round(float(value), CANONICAL_DECIMAL_PLACES)
    return 0.0 if numeric == 0.0 else numeric


def canonicalize_probabilities(probabilities: Sequence[float]) -> np.ndarray:
    """Validate and quantize probability values before metrics or serialization."""
    values = np.asarray(probabilities, dtype=float)
    if not np.isfinite(values).all():
        raise BenchmarkError("Predicted probabilities must be finite")
    if ((values < 0.0) | (values > 1.0)).any():
        raise BenchmarkError("Predicted probabilities must be in [0, 1]")
    canonical = np.round(values, decimals=CANONICAL_DECIMAL_PLACES)
    return np.clip(canonical, 0.0, 1.0)


def canonicalize_report_value(value):
    """Recursively canonicalize floating-point values in machine-readable output."""
    if isinstance(value, (float, np.floating)):
        return canonical_float(value)
    if isinstance(value, dict):
        return {
            key: canonicalize_report_value(nested)
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [canonicalize_report_value(nested) for nested in value]
    if isinstance(value, tuple):
        return tuple(canonicalize_report_value(nested) for nested in value)
    return value


@dataclass(frozen=True)
class ModelConfiguration:
    identifier: str
    family: str
    complexity_rank: int
    parameters: Tuple[Tuple[str, object], ...]
    preprocessing: str

    def parameter_dict(self) -> dict:
        return dict(self.parameters)

    def to_dict(self) -> dict:
        return {
            "complexity_rank": self.complexity_rank,
            "family": self.family,
            "identifier": self.identifier,
            "parameters": self.parameter_dict(),
            "preprocessing": self.preprocessing,
        }


def default_model_configurations(
    random_seed: int = DEFAULT_RANDOM_SEED,
) -> Tuple[ModelConfiguration, ...]:
    values = (
        ModelConfiguration(
            identifier="constant_train_prevalence_v1",
            family="constant_prevalence",
            complexity_rank=0,
            parameters=(),
            preprocessing="none",
        ),
        ModelConfiguration(
            identifier="decision_tree_depth4_leaf50_v1",
            family="decision_tree",
            complexity_rank=3,
            parameters=(
                ("max_depth", 4),
                ("min_samples_leaf", 50),
                ("random_state", random_seed),
            ),
            preprocessing="train_median_imputation",
        ),
        ModelConfiguration(
            identifier="logistic_l2_c0.1_v1",
            family="logistic_regression",
            complexity_rank=2,
            parameters=(
                ("C", 0.1),
                ("max_iter", 2000),
                ("random_state", random_seed),
                ("solver", "lbfgs"),
            ),
            preprocessing="train_median_imputation_and_standard_scaling",
        ),
        ModelConfiguration(
            identifier="logistic_l2_c1_v1",
            family="logistic_regression",
            complexity_rank=2,
            parameters=(
                ("C", 1.0),
                ("max_iter", 2000),
                ("random_state", random_seed),
                ("solver", "lbfgs"),
            ),
            preprocessing="train_median_imputation_and_standard_scaling",
        ),
        ModelConfiguration(
            identifier="logistic_l2_c10_v1",
            family="logistic_regression",
            complexity_rank=2,
            parameters=(
                ("C", 10.0),
                ("max_iter", 2000),
                ("random_state", random_seed),
                ("solver", "lbfgs"),
            ),
            preprocessing="train_median_imputation_and_standard_scaling",
        ),
        ModelConfiguration(
            identifier="logistic_unregularized_v1",
            family="logistic_regression",
            complexity_rank=1,
            parameters=(
                ("C", 1e12),
                ("max_iter", 2000),
                ("random_state", random_seed),
                ("solver", "lbfgs"),
            ),
            preprocessing="train_median_imputation_and_standard_scaling",
        ),
    )
    return tuple(sorted(values, key=lambda value: value.identifier))


def pre_match_feature_names(feature_schema: Sequence[Mapping]) -> Tuple[str, ...]:
    names = []
    roles = {}
    supported_roles = {
        "IDENTIFIER",
        "PRE_MATCH_FEATURE",
        "TARGET_ONLY",
        "SPLIT_METADATA",
    }
    for entry in feature_schema:
        name = entry.get("name")
        role = entry.get("role")
        if not isinstance(name, str) or not name:
            raise BenchmarkError("Every feature-schema column needs a name")
        if name in roles:
            raise BenchmarkError(f"Duplicate feature-schema column: {name}")
        if role not in supported_roles:
            raise BenchmarkError(f"Unsupported feature role for {name}: {role}")
        roles[name] = role
        if role == "PRE_MATCH_FEATURE":
            if name in FORBIDDEN_PREDICTOR_NAMES:
                raise BenchmarkError(
                    f"Audit/target column cannot be a predictor: {name}"
                )
            names.append(name)
    if not names:
        raise BenchmarkError("The frozen schema has no PRE_MATCH_FEATURE columns")
    for target in (*TARGETS, "both_teams_won_a_half"):
        if roles.get(target) != "TARGET_ONLY":
            raise BenchmarkError(f"Frozen target role is invalid: {target}")
    return tuple(names)


def validate_predictor_columns(
    feature_schema: Sequence[Mapping],
    predictor_names: Sequence[str],
) -> Tuple[str, ...]:
    expected = pre_match_feature_names(feature_schema)
    supplied = tuple(predictor_names)
    if len(set(supplied)) != len(supplied):
        raise BenchmarkError("Predictor columns must be unique")
    roles = {entry["name"]: entry["role"] for entry in feature_schema}
    forbidden = [name for name in supplied if roles.get(name) != "PRE_MATCH_FEATURE"]
    if forbidden:
        raise BenchmarkError(
            "Only PRE_MATCH_FEATURE columns may be predictors: "
            + ", ".join(sorted(forbidden))
        )
    if supplied != expected:
        raise BenchmarkError(
            "Predictor columns must exactly match the frozen PRE_MATCH_FEATURE order"
        )
    return supplied


def _numeric_matrix(rows: Sequence[Mapping], feature_names: Sequence[str]) -> np.ndarray:
    matrix = np.empty((len(rows), len(feature_names)), dtype=float)
    for row_index, row in enumerate(rows):
        for column_index, name in enumerate(feature_names):
            value = row.get(name)
            if value is None:
                matrix[row_index, column_index] = np.nan
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise BenchmarkError(f"Predictor {name} must be numeric or missing")
            numeric = float(value)
            if not np.isfinite(numeric):
                raise BenchmarkError(f"Predictor {name} must be finite when present")
            matrix[row_index, column_index] = numeric
    return matrix


@dataclass(frozen=True)
class TrainOnlyPreprocessor:
    feature_names: Tuple[str, ...]
    medians: Tuple[float, ...]
    means: Tuple[float, ...]
    scales: Tuple[float, ...]

    def transform(self, rows: Sequence[Mapping]) -> Tuple[np.ndarray, np.ndarray, dict]:
        raw = _numeric_matrix(rows, self.feature_names)
        missing_before_by_feature = {
            name: int(np.isnan(raw[:, index]).sum())
            for index, name in enumerate(self.feature_names)
        }
        imputed = raw.copy()
        for index, median in enumerate(self.medians):
            missing = np.isnan(imputed[:, index])
            imputed[missing, index] = median
        if not np.isfinite(imputed).all():
            raise BenchmarkError("Preprocessing left non-finite predictor values")
        scaled = (imputed - np.asarray(self.means)) / np.asarray(self.scales)
        report = {
            "missing_after": int(np.isnan(imputed).sum()),
            "missing_before": int(np.isnan(raw).sum()),
            "missing_before_by_feature": missing_before_by_feature,
            "rows": len(rows),
        }
        return imputed, scaled, report

    def state_fingerprint_payload(self) -> dict:
        return canonicalize_report_value({
            "feature_names": list(self.feature_names),
            "means": list(self.means),
            "medians": list(self.medians),
            "scales": list(self.scales),
        })


def fit_train_preprocessor(
    train_rows: Sequence[Mapping],
    feature_names: Sequence[str],
) -> TrainOnlyPreprocessor:
    if not train_rows:
        raise BenchmarkError("TRAIN must contain rows")
    if any(row.get("split") != "TRAIN" for row in train_rows):
        raise BenchmarkError("Preprocessing may be fitted only on TRAIN rows")
    names = tuple(feature_names)
    raw = _numeric_matrix(train_rows, names)
    medians = []
    for index, name in enumerate(names):
        observed = raw[:, index][~np.isnan(raw[:, index])]
        if not len(observed):
            raise BenchmarkError(
                f"TRAIN has no observed value for predictor {name}"
            )
        medians.append(float(np.median(observed)))
    imputed = raw.copy()
    for index, median in enumerate(medians):
        missing = np.isnan(imputed[:, index])
        imputed[missing, index] = median
    means = np.mean(imputed, axis=0)
    scales = np.std(imputed, axis=0)
    scales[scales == 0.0] = 1.0
    return TrainOnlyPreprocessor(
        feature_names=names,
        medians=tuple(float(value) for value in medians),
        means=tuple(float(value) for value in means),
        scales=tuple(float(value) for value in scales),
    )


def _calibration_bins(
    targets: np.ndarray,
    probabilities: np.ndarray,
    bin_count: int = CALIBRATION_BIN_COUNT,
) -> Tuple[list, float]:
    if bin_count <= 0:
        raise BenchmarkError("Calibration bin count must be positive")
    unique_probabilities = np.unique(probabilities)
    actual_bin_count = min(bin_count, len(unique_probabilities))
    grouped_positions = [
        np.flatnonzero(probabilities == probability)
        for probability in unique_probabilities
    ]
    group_counts = np.asarray(
        [len(positions) for positions in grouped_positions], dtype=int
    )
    cumulative_counts = np.cumsum(group_counts)
    boundaries = []
    previous_boundary = 0
    group_total = len(grouped_positions)
    for bin_index in range(1, actual_bin_count):
        target_count = len(probabilities) * bin_index / actual_bin_count
        minimum_boundary = previous_boundary + 1
        maximum_boundary = group_total - (actual_bin_count - bin_index)
        boundary = min(
            range(minimum_boundary, maximum_boundary + 1),
            key=lambda candidate: (
                abs(cumulative_counts[candidate - 1] - target_count),
                candidate,
            ),
        )
        boundaries.append(boundary)
        previous_boundary = boundary
    boundaries.append(group_total)

    bins = []
    weighted_error = 0.0
    start = 0
    for index, boundary in enumerate(boundaries):
        positions = np.concatenate(grouped_positions[start:boundary])
        predicted_mean = canonical_float(np.mean(probabilities[positions]))
        observed_rate = canonical_float(np.mean(targets[positions]))
        count = int(len(positions))
        weighted_error += count * abs(predicted_mean - observed_rate)
        bins.append(
            {
                "bin": index + 1,
                "count": count,
                "observed_rate": observed_rate,
                "probability_maximum": canonical_float(
                    np.max(probabilities[positions])
                ),
                "probability_minimum": canonical_float(
                    np.min(probabilities[positions])
                ),
                "predicted_mean": predicted_mean,
            }
        )
        start = boundary
    return bins, canonical_float(weighted_error / len(targets))


def _calibration_intercept_slope(
    targets: np.ndarray,
    probabilities: np.ndarray,
    random_seed: int,
) -> dict:
    if len(np.unique(targets)) < 2:
        return {
            "intercept": None,
            "reason": "SINGLE_CLASS",
            "slope": None,
            "status": "UNAVAILABLE",
        }
    clipped = np.clip(probabilities, 1e-12, 1.0 - 1e-12)
    logits = np.log(clipped / (1.0 - clipped))
    if float(np.std(logits)) == 0.0:
        return {
            "intercept": None,
            "reason": "CONSTANT_PREDICTION",
            "slope": None,
            "status": "UNAVAILABLE",
        }
    try:
        diagnostic = LogisticRegression(
            C=1e12,
            solver="lbfgs",
            max_iter=2000,
            random_state=random_seed,
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ConvergenceWarning)
            with threadpool_limits(limits=NUMERICAL_THREAD_LIMIT):
                diagnostic.fit(logits.reshape(-1, 1), targets)
        non_converged = any(
            issubclass(warning.category, ConvergenceWarning)
            for warning in caught
        ) or bool(np.any(np.asarray(diagnostic.n_iter_) >= diagnostic.max_iter))
        if non_converged:
            return {
                "intercept": None,
                "reason": "NON_CONVERGENCE",
                "slope": None,
                "status": "UNAVAILABLE",
            }
    except (ValueError, FloatingPointError):
        return {
            "intercept": None,
            "reason": "FIT_ERROR",
            "slope": None,
            "status": "UNAVAILABLE",
        }
    return {
        "intercept": canonical_float(diagnostic.intercept_[0]),
        "reason": None,
        "slope": canonical_float(diagnostic.coef_[0][0]),
        "status": "AVAILABLE",
    }


def probability_metrics(
    targets: Sequence[int],
    probabilities: Sequence[float],
    *,
    random_seed: int = DEFAULT_RANDOM_SEED,
) -> dict:
    observed = np.asarray(targets, dtype=int)
    raw_predicted = np.asarray(probabilities, dtype=float)
    if len(observed) == 0 or len(observed) != len(raw_predicted):
        raise BenchmarkError("Metric inputs must have the same non-zero length")
    non_finite = int((~np.isfinite(raw_predicted)).sum())
    outside = int(
        ((raw_predicted < 0.0) | (raw_predicted > 1.0)).sum()
    )
    if non_finite or outside:
        raise BenchmarkError("Predicted probabilities must be finite and in [0, 1]")
    predicted = canonicalize_probabilities(raw_predicted)
    if not set(np.unique(observed)).issubset({0, 1}):
        raise BenchmarkError("Targets must be binary")
    positive_count = int(observed.sum())
    bins, ece = _calibration_bins(observed, predicted)
    thresholds = {}
    for threshold in DESCRIPTIVE_THRESHOLDS:
        qualifies = predicted >= threshold
        qualifying_count = int(qualifies.sum())
        true_positives = int(observed[qualifies].sum())
        thresholds[f"{threshold:.2f}"] = {
            "precision": (
                canonical_float(true_positives / qualifying_count)
                if qualifying_count
                else None
            ),
            "qualifying_predictions": qualifying_count,
            "recall": (
                canonical_float(true_positives / positive_count)
                if positive_count
                else None
            ),
        }
    both_classes = len(np.unique(observed)) == 2
    return {
        "average_precision": (
            canonical_float(average_precision_score(observed, predicted))
            if positive_count
            else None
        ),
        "brier_score": canonical_float(brier_score_loss(observed, predicted)),
        "calibration": {
            "actual_bin_count": len(bins),
            "binning": (
                "approximately equal-frequency contiguous probability bins; "
                "identical probabilities are never split"
            ),
            "bins": bins,
            "expected_calibration_error": canonical_float(ece),
            "expected_calibration_error_formula": (
                "sum(bin_count / total * abs(predicted_mean - observed_rate))"
            ),
            **_calibration_intercept_slope(
                observed, predicted, random_seed
            ),
        },
        "log_loss": canonical_float(
            log_loss(observed, predicted, labels=[0, 1])
        ),
        "positive_count": positive_count,
        "prevalence": canonical_float(positive_count / len(observed)),
        "probability_diagnostics": {
            "count_nan_or_infinite": non_finite,
            "count_outside_unit_interval": outside,
            "maximum": canonical_float(np.max(predicted)),
            "mean": canonical_float(np.mean(predicted)),
            "minimum": canonical_float(np.min(predicted)),
        },
        "roc_auc": (
            canonical_float(roc_auc_score(observed, predicted))
            if both_classes
            else None
        ),
        "row_count": len(observed),
        "threshold_diagnostics": thresholds,
    }


@dataclass
class _FittedCandidate:
    configuration: ModelConfiguration
    estimator: object
    train_prevalence: float

    def predict(
        self,
        imputed: np.ndarray,
        scaled: np.ndarray,
    ) -> np.ndarray:
        if self.configuration.family == "constant_prevalence":
            return canonicalize_probabilities(
                np.full(len(imputed), self.train_prevalence, dtype=float)
            )
        matrix = (
            scaled
            if "standard_scaling" in self.configuration.preprocessing
            else imputed
        )
        with threadpool_limits(limits=NUMERICAL_THREAD_LIMIT):
            probabilities = self.estimator.predict_proba(matrix)[:, 1]
        return canonicalize_probabilities(probabilities)


def _fit_candidate(
    configuration: ModelConfiguration,
    *,
    train_imputed: np.ndarray,
    train_scaled: np.ndarray,
    train_targets: np.ndarray,
    target_name: str,
) -> _FittedCandidate:
    prevalence = canonical_float(np.mean(train_targets))
    if configuration.family == "constant_prevalence":
        return _FittedCandidate(configuration, None, prevalence)
    parameters = configuration.parameter_dict()
    if configuration.family == "logistic_regression":
        estimator = LogisticRegression(**parameters)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ConvergenceWarning)
            with threadpool_limits(limits=NUMERICAL_THREAD_LIMIT):
                estimator.fit(train_scaled, train_targets)
        warned = any(
            issubclass(warning.category, ConvergenceWarning)
            for warning in caught
        )
        configured_maximum = parameters.get("max_iter")
        reached_maximum = (
            configured_maximum is not None
            and bool(
                np.any(np.asarray(estimator.n_iter_) >= configured_maximum)
            )
        )
        if warned or reached_maximum:
            raise BenchmarkError(
                "Logistic candidate did not converge for target "
                f"{target_name}: {configuration.identifier}"
            )
    elif configuration.family == "decision_tree":
        estimator = DecisionTreeClassifier(**parameters)
        with threadpool_limits(limits=NUMERICAL_THREAD_LIMIT):
            estimator.fit(train_imputed, train_targets)
    else:
        raise BenchmarkError(f"Unsupported model family: {configuration.family}")
    return _FittedCandidate(configuration, estimator, prevalence)


def fit_benchmark_candidate(
    configuration: ModelConfiguration,
    *,
    train_imputed: np.ndarray,
    train_scaled: np.ndarray,
    train_targets: np.ndarray,
    target_name: str,
):
    """Fit one declared benchmark candidate under the Stage 4A safety policy."""
    return _fit_candidate(
        configuration,
        train_imputed=train_imputed,
        train_scaled=train_scaled,
        train_targets=train_targets,
        target_name=target_name,
    )


def select_validation_winner(candidate_summaries: Sequence[Mapping]) -> str:
    if not candidate_summaries:
        raise BenchmarkError("At least one candidate is required")
    ordered = sorted(
        candidate_summaries,
        key=lambda value: (
            canonical_float(
                value["metrics"]["validation"]["log_loss"]
            ),
            canonical_float(
                value["metrics"]["validation"]["brier_score"]
            ),
            value["complexity_rank"],
            value["model_identifier"],
        ),
    )
    return ordered[0]["model_identifier"]


def _binary_targets(rows: Sequence[Mapping], target: str) -> np.ndarray:
    values = []
    for row in rows:
        value = row.get(target)
        if isinstance(value, bool) or value not in (0, 1):
            raise BenchmarkError(f"Target {target} must contain only integer 0/1")
        values.append(value)
    return np.asarray(values, dtype=int)


def run_baseline_benchmarks(
    rows: Iterable[Mapping],
    feature_names: Sequence[str],
    *,
    model_configurations: Sequence[ModelConfiguration] | None = None,
    random_seed: int = DEFAULT_RANDOM_SEED,
    expected_split_counts: Mapping[str, int] | None = None,
) -> dict:
    ordered_rows = tuple(
        sorted(
            rows,
            key=lambda row: (
                SPLIT_ORDER.get(row.get("split"), 99),
                str(row.get("fixture_identity") or ""),
            ),
        )
    )
    if not ordered_rows:
        raise BenchmarkError("The feature dataset is empty")
    fixture_ids = [str(row.get("fixture_identity") or "") for row in ordered_rows]
    if any(not value for value in fixture_ids) or len(set(fixture_ids)) != len(
        fixture_ids
    ):
        raise BenchmarkError("Fixture identities must be present and unique")
    split_rows = {
        split: tuple(row for row in ordered_rows if row.get("split") == split)
        for split in SPLITS
    }
    if sum(len(values) for values in split_rows.values()) != len(ordered_rows):
        raise BenchmarkError("Every feature row must use a frozen split")
    if any(not split_rows[split] for split in SPLITS):
        raise BenchmarkError("TRAIN, VALIDATION and TEST must all contain rows")
    if expected_split_counts is not None:
        for split in SPLITS:
            if len(split_rows[split]) != expected_split_counts.get(split):
                raise BenchmarkError(
                    f"{split} row count differs from the frozen expectation"
                )
    train_targets = {
        target: _binary_targets(split_rows["TRAIN"], target)
        for target in TARGETS
    }
    validation_targets = {
        target: _binary_targets(split_rows["VALIDATION"], target)
        for target in TARGETS
    }
    for target in TARGETS:
        if len(np.unique(train_targets[target])) < 2:
            raise BenchmarkError(f"TRAIN target has only one class: {target}")

    configurations = tuple(
        sorted(
            model_configurations or default_model_configurations(random_seed),
            key=lambda value: value.identifier,
        )
    )
    if len({value.identifier for value in configurations}) != len(configurations):
        raise BenchmarkError("Model identifiers must be unique")

    preprocessor = fit_train_preprocessor(
        split_rows["TRAIN"], tuple(feature_names)
    )
    train_imputed, train_scaled, train_missing = preprocessor.transform(
        split_rows["TRAIN"]
    )
    validation_imputed, validation_scaled, validation_missing = (
        preprocessor.transform(split_rows["VALIDATION"])
    )

    target_results = {}
    fitted_by_target = {}
    protocol_events = [
        "preprocessing_fitted_on_train",
        "train_and_validation_transformed",
    ]
    for target in TARGETS:
        candidate_summaries = []
        fitted_candidates = {}
        for configuration in configurations:
            fitted = _fit_candidate(
                configuration,
                train_imputed=train_imputed,
                train_scaled=train_scaled,
                train_targets=train_targets[target],
                target_name=target,
            )
            fitted_candidates[configuration.identifier] = fitted
            train_probabilities = fitted.predict(train_imputed, train_scaled)
            validation_probabilities = fitted.predict(
                validation_imputed, validation_scaled
            )
            candidate_summaries.append(
                {
                    "complexity_rank": configuration.complexity_rank,
                    "metrics": {
                        "train": probability_metrics(
                            train_targets[target],
                            train_probabilities,
                            random_seed=random_seed,
                        ),
                        "validation": probability_metrics(
                            validation_targets[target],
                            validation_probabilities,
                            random_seed=random_seed,
                        ),
                    },
                    "model_identifier": configuration.identifier,
                }
            )
        selected = select_validation_winner(candidate_summaries)
        fitted_by_target[target] = fitted_candidates[selected]
        selected_summary = next(
            value
            for value in candidate_summaries
            if value["model_identifier"] == selected
        )
        target_results[target] = {
            "candidates": sorted(
                candidate_summaries,
                key=lambda value: value["model_identifier"],
            ),
            "selected_evaluation": {
                "train": selected_summary["metrics"]["train"],
                "validation": selected_summary["metrics"]["validation"],
            },
            "selected_model_identifier": selected,
        }
        protocol_events.append(f"validation_selected:{target}:{selected}")

    # TEST is first transformed only after both target winners are fixed.
    test_imputed, test_scaled, test_missing = preprocessor.transform(
        split_rows["TEST"]
    )
    protocol_events.append("test_transformed_after_all_validation_selection")
    prediction_rows = []
    matrices = {
        "TRAIN": (train_imputed, train_scaled),
        "VALIDATION": (validation_imputed, validation_scaled),
        "TEST": (test_imputed, test_scaled),
    }
    selected_probabilities = {}
    for target in TARGETS:
        fitted = fitted_by_target[target]
        test_targets = _binary_targets(split_rows["TEST"], target)
        selected_probabilities[target] = {
            split: fitted.predict(*matrices[split]) for split in SPLITS
        }
        test_probabilities = selected_probabilities[target]["TEST"]
        target_results[target]["selected_evaluation"]["test"] = (
            probability_metrics(
                test_targets,
                test_probabilities,
                random_seed=random_seed,
            )
        )
        protocol_events.append(f"test_evaluated_once:{target}")
        for split in SPLITS:
            probabilities = selected_probabilities[target][split]
            targets = _binary_targets(split_rows[split], target)
            for row, observed, probability in zip(
                split_rows[split], targets, probabilities
            ):
                prediction_rows.append(
                    {
                        "fixture_identity": row["fixture_identity"],
                        "kickoff_utc": row["kickoff_utc"],
                        "model_identifier": fitted.configuration.identifier,
                        "predicted_probability": float(probability),
                        "split": split,
                        "target_name": target,
                        "target_value": int(observed),
                    }
                )
    prediction_rows.sort(
        key=lambda row: (
            row["target_name"],
            SPLIT_ORDER[row["split"]],
            row["fixture_identity"],
        )
    )
    return {
        "benchmark": {
            "calibration_policy": "diagnostics only; no calibration fitting",
            "model_configurations": [value.to_dict() for value in configurations],
            "preprocessing": {
                "fit_split": "TRAIN",
                "imputation": "per-feature TRAIN median",
                "scaling": "per-feature TRAIN mean and population standard deviation",
                "state": preprocessor.state_fingerprint_payload(),
                "missing_values": {
                    "test": test_missing,
                    "train": train_missing,
                    "validation": validation_missing,
                },
            },
            "probability_threshold_policy": (
                "0.50, 0.60 and 0.70 are descriptive only and never select a model"
            ),
            "numerical_reproducibility": {
                "artifact_binding": "bound_to_recorded_numerical_runtime",
                "canonical_decimal_places": CANONICAL_DECIMAL_PLACES,
                "canonical_probability_quantum": CANONICAL_QUANTUM,
                "thread_limit": NUMERICAL_THREAD_LIMIT,
            },
            "protocol_events": protocol_events,
            "random_seed": random_seed,
            "selection_metric": "VALIDATION log loss",
            "selection_rule": SELECTION_RULE,
            "split_counts": {
                split.lower(): len(split_rows[split]) for split in SPLITS
            },
            "targets": target_results,
        },
        "prediction_rows": prediction_rows,
    }


__all__ = [
    "BenchmarkError",
    "CALIBRATION_BIN_COUNT",
    "CANONICAL_DECIMAL_PLACES",
    "CANONICAL_QUANTUM",
    "DEFAULT_RANDOM_SEED",
    "DESCRIPTIVE_THRESHOLDS",
    "ModelConfiguration",
    "NUMERICAL_THREAD_LIMIT",
    "SELECTION_RULE",
    "SPLITS",
    "TARGETS",
    "TrainOnlyPreprocessor",
    "canonical_float",
    "canonicalize_probabilities",
    "default_model_configurations",
    "fit_train_preprocessor",
    "fit_benchmark_candidate",
    "pre_match_feature_names",
    "probability_metrics",
    "run_baseline_benchmarks",
    "select_validation_winner",
    "validate_predictor_columns",
]
