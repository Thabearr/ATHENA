"""Chronological evaluation protocol for Goal/Score Dynamics v2."""
from __future__ import annotations

from dataclasses import dataclass
import itertools
import math
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import numpy as np

from domain._goal_score_contracts import *
from domain._goal_score_models import *


@dataclass(frozen=True)
class ChronologicalSplit:
    development_rows: tuple[TrainingRow, ...]
    holdout_rows: tuple[TrainingRow, ...]
    development_dates: tuple[str, ...]
    holdout_dates: tuple[str, ...]


def chronological_split(rows: Sequence[TrainingRow]) -> ChronologicalSplit:
    ordered = tuple(sorted(rows, key=lambda row: (row.match_date, row.match_key)))
    dates = tuple(sorted({row.match_date for row in ordered}))
    if len(dates) < 12:
        raise GoalScoreError("INSUFFICIENT_CHRONOLOGY")
    holdout_count = max(1, math.ceil(len(dates) * 0.20))
    if len(dates) - holdout_count < 6:
        raise GoalScoreError("INSUFFICIENT_CHRONOLOGY")
    development_dates = dates[:-holdout_count]
    holdout_dates = dates[-holdout_count:]
    development_set = set(development_dates)
    holdout_set = set(holdout_dates)
    return ChronologicalSplit(
        tuple(row for row in ordered if row.match_date in development_set),
        tuple(row for row in ordered if row.match_date in holdout_set),
        development_dates,
        holdout_dates,
    )


def rolling_origin_folds(
    development_rows: Sequence[TrainingRow],
) -> tuple[tuple[tuple[TrainingRow, ...], tuple[TrainingRow, ...]], ...]:
    dates = tuple(sorted({row.match_date for row in development_rows}))
    initial = max(1, len(dates) // 2)
    validation_dates = dates[initial:]
    if len(validation_dates) < 5:
        raise GoalScoreError("INSUFFICIENT_CHRONOLOGY_FOR_5_FOLDS")
    chunks = [
        tuple(chunk.tolist())
        for chunk in np.array_split(
            np.asarray(validation_dates, dtype=object), 5
        )
        if len(chunk)
    ]
    folds: list[tuple[tuple[TrainingRow, ...], tuple[TrainingRow, ...]]] = []
    for chunk in chunks:
        first = chunk[0]
        train_dates = {match_date for match_date in dates if match_date < first}
        validation_set = set(chunk)
        train = tuple(
            row for row in development_rows if row.match_date in train_dates
        )
        validation = tuple(
            row for row in development_rows if row.match_date in validation_set
        )
        if (
            not train
            or not validation
            or max(row.match_date for row in train)
            >= min(row.match_date for row in validation)
        ):
            raise GoalScoreError("rolling-origin chronology violation")
        folds.append((train, validation))
    if len(folds) != 5:
        raise GoalScoreError("rolling-origin policy did not create five folds")
    return tuple(folds)


def _safe_log_probability(probability: float) -> float:
    if not math.isfinite(probability) or probability <= 0:
        raise GoalScoreError("proper score received zero/invalid probability")
    return -math.log(probability)


def _multiclass_probs(
    distribution: GoalScoreDistribution,
) -> tuple[float, float, float]:
    return distribution.home_win, distribution.draw, distribution.away_win


def _outcome_index(row: TrainingRow) -> int:
    if row.home_goals > row.away_goals:
        return 0
    if row.home_goals == row.away_goals:
        return 1
    return 2


def _poisson_deviance(observed: int, expected: float) -> float:
    if observed == 0:
        return 2.0 * expected
    return 2.0 * (
        observed * math.log(observed / expected) - (observed - expected)
    )


def exact_score_losses(
    rows: Sequence[TrainingRow],
    distributions: Sequence[GoalScoreDistribution],
) -> tuple[float, ...]:
    if not rows or len(rows) != len(distributions):
        raise GoalScoreError("proper score requires paired non-empty predictions")
    return tuple(
        _safe_log_probability(
            distribution.exact_probability(row.home_goals, row.away_goals)
        )
        for row, distribution in zip(rows, distributions)
    )


def evaluate_predictions(
    rows: Sequence[TrainingRow],
    distributions: Sequence[GoalScoreDistribution],
) -> dict[str, float]:
    if not rows or len(rows) != len(distributions):
        raise GoalScoreError("evaluation requires paired non-empty predictions")
    exact_nll = list(exact_score_losses(rows, distributions))
    home_dev: list[float] = []
    away_dev: list[float] = []
    result_log: list[float] = []
    result_brier: list[float] = []
    total_log: list[float] = []
    margin_log: list[float] = []
    btts_brier: list[float] = []
    btts_log: list[float] = []
    over_brier: list[float] = []
    over_log: list[float] = []
    pred_home: list[float] = []
    pred_away: list[float] = []
    for row, distribution in zip(rows, distributions):
        home_dev.append(
            _poisson_deviance(row.home_goals, distribution.home_intensity)
        )
        away_dev.append(
            _poisson_deviance(row.away_goals, distribution.away_intensity)
        )
        result_probabilities = _multiclass_probs(distribution)
        outcome_index = _outcome_index(row)
        result_log.append(
            _safe_log_probability(result_probabilities[outcome_index])
        )
        result_brier.append(
            sum(
                (
                    probability
                    - (1.0 if index == outcome_index else 0.0)
                )
                ** 2
                for index, probability in enumerate(result_probabilities)
            )
        )
        total = row.home_goals + row.away_goals
        margin = row.home_goals - row.away_goals
        total_log.append(
            _safe_log_probability(distribution.exact_total_probability(total))
        )
        margin_log.append(
            _safe_log_probability(distribution.exact_margin_probability(margin))
        )
        btts = 1.0 if row.home_goals > 0 and row.away_goals > 0 else 0.0
        btts_brier.append((distribution.btts_yes - btts) ** 2)
        btts_log.append(
            _safe_log_probability(
                distribution.btts_yes if btts else 1.0 - distribution.btts_yes
            )
        )
        over = 1.0 if total > 2 else 0.0
        over_brier.append((distribution.over_2_5 - over) ** 2)
        over_log.append(
            _safe_log_probability(
                distribution.over_2_5 if over else 1.0 - distribution.over_2_5
            )
        )
        pred_home.append(distribution.home_intensity)
        pred_away.append(distribution.away_intensity)

    def mean(values: Sequence[float]) -> float:
        return float(np.mean(values))

    return {
        "exact_score_nll": mean(exact_nll),
        "home_goal_mean_poisson_deviance": mean(home_dev),
        "away_goal_mean_poisson_deviance": mean(away_dev),
        "combined_goal_deviance": mean(home_dev) + mean(away_dev),
        "result_1x2_log_loss": mean(result_log),
        "result_1x2_brier": mean(result_brier),
        "total_goals_log_loss": mean(total_log),
        "goal_margin_log_loss": mean(margin_log),
        "btts_brier": mean(btts_brier),
        "btts_log_loss": mean(btts_log),
        "over_2_5_brier": mean(over_brier),
        "over_2_5_log_loss": mean(over_log),
        "mean_predicted_home_goals": mean(pred_home),
        "mean_observed_home_goals": mean([row.home_goals for row in rows]),
        "mean_predicted_away_goals": mean(pred_away),
        "mean_observed_away_goals": mean([row.away_goals for row in rows]),
        "prediction_availability": 1.0,
    }


def _fold_development_score(
    model_id: str,
    folds: Sequence[Any],
    feature_ids: Sequence[str] | None = None,
) -> tuple[float, list[dict[str, float]]]:
    metrics: list[dict[str, float]] = []
    for train, validation in folds:
        model = fit_challenger(model_id, train, feature_ids=feature_ids)
        metrics.append(
            evaluate_predictions(validation, model.predict(validation))
        )
    return (
        float(np.mean([item["exact_score_nll"] for item in metrics])),
        metrics,
    )


def challenger_disagreement(
    distributions_by_model: Mapping[str, GoalScoreDistribution],
) -> dict[str, float]:
    values = list(distributions_by_model.values())
    if len(values) < 2:
        return {
            "home_intensity_range": 0.0,
            "home_intensity_std": 0.0,
            "away_intensity_range": 0.0,
            "away_intensity_std": 0.0,
            "total_intensity_range": 0.0,
            "total_intensity_std": 0.0,
            "mean_pairwise_total_variation": 0.0,
        }
    home = [distribution.home_intensity for distribution in values]
    away = [distribution.away_intensity for distribution in values]
    totals = [home_value + away_value for home_value, away_value in zip(home, away)]
    total_variations: list[float] = []
    for left_index in range(len(values)):
        for right_index in range(left_index + 1, len(values)):
            keys = set(values[left_index].probabilities) | set(
                values[right_index].probabilities
            )
            total_variations.append(
                0.5
                * sum(
                    abs(
                        values[left_index].probabilities.get(key, 0.0)
                        - values[right_index].probabilities.get(key, 0.0)
                    )
                    for key in keys
                )
            )
    return {
        "home_intensity_range": max(home) - min(home),
        "home_intensity_std": float(np.std(home)),
        "away_intensity_range": max(away) - min(away),
        "away_intensity_std": float(np.std(away)),
        "total_intensity_range": max(totals) - min(totals),
        "total_intensity_std": float(np.std(totals)),
        "mean_pairwise_total_variation": float(np.mean(total_variations)),
    }


def paired_date_bucket_bootstrap(
    rows: Sequence[TrainingRow],
    losses_a: Sequence[float],
    losses_b: Sequence[float],
    *,
    replicates: int = PAIR_BOOTSTRAP_REPLICATES,
    seed: int = RANDOM_SEED,
) -> dict[str, float]:
    if len(rows) != len(losses_a) or len(rows) != len(losses_b) or not rows:
        raise GoalScoreError("paired bootstrap requires common target set")
    if isinstance(replicates, bool) or not isinstance(replicates, int) or replicates < 1:
        raise GoalScoreError("paired bootstrap replicate count must be positive")
    by_date: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        by_date.setdefault(row.match_date, []).append(index)
    dates = sorted(by_date)
    rng = np.random.default_rng(seed)
    differences: list[float] = []
    for _ in range(replicates):
        sampled = rng.choice(dates, size=len(dates), replace=True)
        indexes = [index for match_date in sampled for index in by_date[match_date]]
        differences.append(
            float(
                np.mean(
                    [losses_a[index] - losses_b[index] for index in indexes]
                )
            )
        )
    return {
        "mean_difference": float(np.mean(differences)),
        "lower_95": float(np.quantile(differences, 0.025)),
        "upper_95": float(np.quantile(differences, 0.975)),
    }


def _available_feature_fraction(row: TrainingRow) -> float:
    if not row.features:
        return 0.0
    return sum(
        status is FeatureStatus.AVAILABLE for status, _value in row.features.values()
    ) / len(row.features)


def _coverage_tier(row: TrainingRow) -> str:
    fraction = _available_feature_fraction(row)
    if fraction >= 0.80:
        return "HIGH"
    if fraction >= 0.50:
        return "MID"
    return "LOW"


def _tactical_event_regime(row: TrainingRow) -> str:
    values: list[float] = []
    for feature_id in (
        "TACTICAL.HOME.OVERALL.EVENT_ENVIRONMENT",
        "TACTICAL.AWAY.OVERALL.EVENT_ENVIRONMENT",
    ):
        status, value = row.features.get(
            feature_id, (FeatureStatus.MISSING, None)
        )
        if status is not FeatureStatus.AVAILABLE or value is None:
            return "UNKNOWN"
        values.append(float(value))
    score = float(np.mean(values))
    if score <= STRATIFIED_TACTICAL_EVENT_LOW:
        return "LOW_EVENT"
    if score >= STRATIFIED_TACTICAL_EVENT_HIGH:
        return "HIGH_EVENT"
    return "MID_EVENT"


def _stratum_groups(rows: Sequence[TrainingRow]) -> Mapping[str, Mapping[str, tuple[int, ...]]]:
    dimensions: dict[str, dict[str, list[int]]] = {
        "competition": {},
        "season": {},
        "tactical_event_regime": {},
        "evidence_coverage_tier": {},
    }
    for index, row in enumerate(rows):
        values = {
            "competition": row.competition_key or "UNKNOWN",
            "season": row.season or "UNKNOWN",
            "tactical_event_regime": _tactical_event_regime(row),
            "evidence_coverage_tier": _coverage_tier(row),
        }
        for dimension, value in values.items():
            dimensions[dimension].setdefault(value, []).append(index)
    return {
        dimension: {
            value: tuple(indexes)
            for value, indexes in sorted(groups.items())
        }
        for dimension, groups in dimensions.items()
    }


def stratified_evaluation(
    rows: Sequence[TrainingRow],
    predictions_by_model: Mapping[str, Sequence[GoalScoreDistribution]],
) -> dict[str, Any]:
    groups = _stratum_groups(rows)
    output: dict[str, Any] = {}
    for dimension, dimension_groups in groups.items():
        output[dimension] = {}
        for value, indexes in dimension_groups.items():
            if len(indexes) < MIN_STRATUM_SAMPLE:
                output[dimension][value] = {
                    "status": "INSUFFICIENT_SAMPLE",
                    "sample_count": len(indexes),
                }
                continue
            stratum_rows = tuple(rows[index] for index in indexes)
            model_metrics = {
                model_id: evaluate_predictions(
                    stratum_rows,
                    tuple(predictions[index] for index in indexes),
                )
                for model_id, predictions in predictions_by_model.items()
            }
            output[dimension][value] = {
                "status": "AVAILABLE",
                "sample_count": len(indexes),
                "metrics": model_metrics,
            }
    return output


def _pairwise_comparisons(
    rows: Sequence[TrainingRow],
    predictions_by_model: Mapping[str, Sequence[GoalScoreDistribution]],
) -> dict[str, Any]:
    losses = {
        model_id: exact_score_losses(rows, predictions)
        for model_id, predictions in predictions_by_model.items()
    }
    output: dict[str, Any] = {}
    for left, right in itertools.combinations(sorted(losses), 2):
        output[f"{left}__vs__{right}"] = {
            "left_model": left,
            "right_model": right,
            "common_target_count": len(rows),
            "left_prediction_coverage": 1.0,
            "right_prediction_coverage": 1.0,
            "exact_score_nll_difference_left_minus_right": (
                float(np.mean(losses[left])) - float(np.mean(losses[right]))
            ),
            "paired_date_bucket_bootstrap": paired_date_bucket_bootstrap(
                rows, losses[left], losses[right]
            ),
        }
    return output


def _winner_guardrail(
    development_selected_model_id: str,
    holdout_metrics: Mapping[str, Mapping[str, float]],
) -> tuple[str | None, str, dict[str, Any]]:
    if development_selected_model_id not in holdout_metrics:
        return None, "NO_HOLDOUT_CANDIDATES", {}
    candidate = development_selected_model_id
    secondary = (
        "result_1x2_log_loss",
        "total_goals_log_loss",
        "goal_margin_log_loss",
    )
    primary_best_model = min(
        holdout_metrics,
        key=lambda model_id: (
            holdout_metrics[model_id]["exact_score_nll"],
            model_id,
        ),
    )
    primary_best = holdout_metrics[primary_best_model]["exact_score_nll"]
    primary_candidate = holdout_metrics[candidate]["exact_score_nll"]
    primary_passed = primary_candidate <= primary_best + 1e-15
    details: dict[str, Any] = {
        "policy_id": WINNER_GUARDRAIL_POLICY_ID,
        "development_selected_candidate": candidate,
        "terminal_holdout_can_reselect": False,
        "holdout_primary_best_model": primary_best_model,
        "holdout_primary_candidate_nll": primary_candidate,
        "holdout_primary_best_nll": primary_best,
        "holdout_primary_passed": primary_passed,
        "maximum_secondary_relative_regression": (
            WINNER_MAX_SECONDARY_RELATIVE_REGRESSION
        ),
        "minimum_prediction_availability": WINNER_MIN_PREDICTION_AVAILABILITY,
        "secondary_checks": {},
    }
    if not primary_passed:
        details["failure"] = "PRIMARY_NLL_GUARDRAIL"
        return None, "NO_CHALLENGER_CLEARED_GUARDRAILS", details
    if (
        holdout_metrics[candidate]["prediction_availability"]
        < WINNER_MIN_PREDICTION_AVAILABILITY
    ):
        details["failure"] = "PREDICTION_AVAILABILITY_GUARDRAIL"
        return None, "NO_CHALLENGER_CLEARED_GUARDRAILS", details
    for metric in secondary:
        best = min(values[metric] for values in holdout_metrics.values())
        value = holdout_metrics[candidate][metric]
        allowed = best * (1.0 + WINNER_MAX_SECONDARY_RELATIVE_REGRESSION)
        passed = value <= allowed + 1e-15
        details["secondary_checks"][metric] = {
            "candidate": value,
            "best": best,
            "maximum_allowed": allowed,
            "passed": passed,
        }
        if not passed:
            details["failure"] = f"SECONDARY_GUARDRAIL:{metric}"
            return None, "NO_CHALLENGER_CLEARED_GUARDRAILS", details
    return candidate, "RESEARCH_CHALLENGER_WINNER", details


def _evaluate_challengers(
    rows: Sequence[TrainingRow],
) -> tuple[dict[str, Any], dict[str, FittedGoalScoreModel]]:
    validate_evaluation_contract()
    split = chronological_split(rows)
    folds = rolling_origin_folds(split.development_rows)
    development: dict[str, float] = {}
    fold_metrics: dict[str, list[dict[str, float]]] = {}
    for definition in GOAL_SCORE_MODEL_REGISTRY:
        score, metrics = _fold_development_score(definition.model_id, folds)
        development[definition.model_id] = score
        fold_metrics[definition.model_id] = metrics
    ranked = sorted(development, key=lambda key: (development[key], key))
    best_development = ranked[0]

    holdout_metrics: dict[str, dict[str, float]] = {}
    holdout_predictions: dict[str, list[GoalScoreDistribution]] = {}
    fitted_models: dict[str, FittedGoalScoreModel] = {}
    for model_id in ranked:
        model = fit_challenger(model_id, split.development_rows)
        fitted_models[model_id] = model
        predictions = model.predict(split.holdout_rows)
        holdout_predictions[model_id] = predictions
        holdout_metrics[model_id] = evaluate_predictions(
            split.holdout_rows, predictions
        )

    core_features = [
        feature.feature_id
        for feature in GOAL_SCORE_FEATURE_REGISTRY
        if not feature.feature_id.startswith("TACTICAL.")
    ]
    core_score, _ = _fold_development_score(
        best_development, folds, feature_ids=core_features
    )
    tactical_ablation = {
        "model_id": best_development,
        "historical_core_exact_score_nll": core_score,
        "historical_plus_tactical_exact_score_nll": development[
            best_development
        ],
        "delta_nll": development[best_development] - core_score,
        "interpretation": (
            "NEGATIVE_DELTA_MEANS_TACTICAL_IMPROVED_DEVELOPMENT_NLL"
        ),
    }

    holdout_ranked = sorted(
        ranked,
        key=lambda key: (holdout_metrics[key]["exact_score_nll"], key),
    )
    winner, winner_status, winner_guardrail = _winner_guardrail(
        best_development, holdout_metrics
    )
    disagreements = [
        {
            "match_key": row.match_key,
            **challenger_disagreement(
                {
                    model_id: holdout_predictions[model_id][index]
                    for model_id in ranked
                }
            ),
        }
        for index, row in enumerate(split.holdout_rows)
    ]
    pairwise = _pairwise_comparisons(
        split.holdout_rows, holdout_predictions
    )
    stratified = stratified_evaluation(
        split.holdout_rows, holdout_predictions
    )
    holdout_identity_sha256 = hashlib.sha256(
        json.dumps(
            [[row.match_date, row.match_key] for row in split.holdout_rows],
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    result = {
        "development_ranking": ranked,
        "development_selected_model_id": best_development,
        "development_exact_score_nll": development,
        "fold_metrics": fold_metrics,
        "holdout_ranking": holdout_ranked,
        "holdout_ranking_role": "DIAGNOSTIC_ONLY_NO_SELECTION_AUTHORITY",
        "holdout_metrics": holdout_metrics,
        "terminal_holdout_selection_authority": False,
        "research_challenger_winner": winner,
        "research_challenger_winner_status": winner_status,
        "research_winner_guardrail": winner_guardrail,
        "production_promotion_eligible": False,
        "tactical_ablation": tactical_ablation,
        "pairwise_common_set_comparisons": pairwise,
        "stratified_holdout_evaluation": stratified,
        "challenger_disagreement": disagreements,
        "live_champion_replay_status": LIVE_CHAMPION_REPLAY_STATUS,
        "holdout_exposure": True,
        "development_first_date": split.development_dates[0],
        "development_last_date": split.development_dates[-1],
        "development_match_count": len(split.development_rows),
        "development_unique_date_count": len(split.development_dates),
        "holdout_first_date": split.holdout_dates[0],
        "holdout_last_date": split.holdout_dates[-1],
        "holdout_dates": list(split.holdout_dates),
        "holdout_identity_sha256": holdout_identity_sha256,
        "holdout_match_count": len(split.holdout_rows),
        "holdout_unique_date_count": len(split.holdout_dates),
        "authority_flags": dict(AUTHORITY_FLAGS),
    }
    return result, fitted_models


def evaluate_challengers(rows: Sequence[TrainingRow]) -> dict[str, Any]:
    result, _models = _evaluate_challengers(rows)
    return result


def evaluate_challengers_with_models(
    rows: Sequence[TrainingRow],
) -> tuple[dict[str, Any], Mapping[str, FittedGoalScoreModel]]:
    result, models = _evaluate_challengers(rows)
    return result, MappingProxyType(models)


__all__ = [name for name in globals() if not name.startswith("_")]
