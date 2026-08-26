"""Chronological evaluation protocol for Goal/Score Dynamics v2."""
from __future__ import annotations

from dataclasses import dataclass
import math
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
    ordered = tuple(sorted(rows, key=lambda r: (r.match_date, r.match_key)))
    dates = tuple(sorted({row.match_date for row in ordered}))
    if len(dates) < 12:
        raise GoalScoreError("INSUFFICIENT_CHRONOLOGY")
    holdout_count = max(1, math.ceil(len(dates) * 0.20))
    if len(dates) - holdout_count < 6:
        raise GoalScoreError("INSUFFICIENT_CHRONOLOGY")
    dev_dates = dates[:-holdout_count]
    holdout_dates = dates[-holdout_count:]
    dev_set, holdout_set = set(dev_dates), set(holdout_dates)
    return ChronologicalSplit(
        tuple(row for row in ordered if row.match_date in dev_set),
        tuple(row for row in ordered if row.match_date in holdout_set),
        dev_dates, holdout_dates,
    )


def rolling_origin_folds(development_rows: Sequence[TrainingRow]) -> tuple[tuple[tuple[TrainingRow, ...], tuple[TrainingRow, ...]], ...]:
    dates = tuple(sorted({row.match_date for row in development_rows}))
    initial = max(1, len(dates) // 2)
    validation_dates = dates[initial:]
    if len(validation_dates) < 5:
        raise GoalScoreError("INSUFFICIENT_CHRONOLOGY_FOR_5_FOLDS")
    chunks = [tuple(chunk.tolist()) for chunk in np.array_split(np.asarray(validation_dates, dtype=object), 5) if len(chunk)]
    folds = []
    for chunk in chunks:
        first = chunk[0]
        train_dates = {date for date in dates if date < first}
        validation_set = set(chunk)
        train = tuple(row for row in development_rows if row.match_date in train_dates)
        validation = tuple(row for row in development_rows if row.match_date in validation_set)
        if not train or not validation or max(r.match_date for r in train) >= min(r.match_date for r in validation):
            raise GoalScoreError("rolling-origin chronology violation")
        folds.append((train, validation))
    if len(folds) != 5:
        raise GoalScoreError("rolling-origin policy did not create five folds")
    return tuple(folds)


def _safe_log_probability(p: float) -> float:
    if not math.isfinite(p) or p <= 0:
        raise GoalScoreError("proper score received zero/invalid probability")
    return -math.log(p)


def _outcome_index(row: TrainingRow) -> int:
    return 0 if row.home_goals > row.away_goals else 1 if row.home_goals == row.away_goals else 2


def _poisson_deviance(y: int, mu: float) -> float:
    if y == 0:
        return 2.0 * mu
    return 2.0 * (y * math.log(y / mu) - (y - mu))


def evaluate_predictions(rows: Sequence[TrainingRow], distributions: Sequence[GoalScoreDistribution]) -> dict[str, float]:
    if not rows or len(rows) != len(distributions):
        raise GoalScoreError("evaluation requires paired non-empty predictions")
    exact_nll=[]; home_dev=[]; away_dev=[]; result_log=[]; result_brier=[]
    total_log=[]; margin_log=[]; btts_brier=[]; btts_log=[]; over_brier=[]; over_log=[]
    pred_home=[]; pred_away=[]
    for row, dist in zip(rows, distributions):
        exact_nll.append(_safe_log_probability(dist.exact_probability(row.home_goals, row.away_goals)))
        home_dev.append(_poisson_deviance(row.home_goals, dist.home_intensity))
        away_dev.append(_poisson_deviance(row.away_goals, dist.away_intensity))
        rp = (dist.home_win, dist.draw, dist.away_win); oi=_outcome_index(row)
        result_log.append(_safe_log_probability(rp[oi]))
        result_brier.append(sum((p-(1.0 if i==oi else 0.0))**2 for i,p in enumerate(rp)))
        total = row.home_goals + row.away_goals
        margin = row.home_goals - row.away_goals
        total_log.append(_safe_log_probability(dist.exact_total_probability(total)))
        margin_log.append(_safe_log_probability(dist.exact_margin_probability(margin)))
        btts = 1.0 if row.home_goals>0 and row.away_goals>0 else 0.0
        btts_brier.append((dist.btts_yes-btts)**2)
        btts_log.append(_safe_log_probability(dist.btts_yes if btts else 1.0-dist.btts_yes))
        over = 1.0 if total>2 else 0.0
        over_brier.append((dist.over_2_5-over)**2)
        over_log.append(_safe_log_probability(dist.over_2_5 if over else 1.0-dist.over_2_5))
        pred_home.append(dist.home_intensity); pred_away.append(dist.away_intensity)
    mean=lambda xs: float(np.mean(xs))
    return {
        "exact_score_nll": mean(exact_nll),
        "home_goal_mean_poisson_deviance": mean(home_dev),
        "away_goal_mean_poisson_deviance": mean(away_dev),
        "combined_goal_deviance": mean(home_dev)+mean(away_dev),
        "result_1x2_log_loss": mean(result_log),
        "result_1x2_brier": mean(result_brier),
        "total_goals_log_loss": mean(total_log),
        "goal_margin_log_loss": mean(margin_log),
        "btts_brier": mean(btts_brier),
        "btts_log_loss": mean(btts_log),
        "over_2_5_brier": mean(over_brier),
        "over_2_5_log_loss": mean(over_log),
        "mean_predicted_home_goals": mean(pred_home),
        "mean_observed_home_goals": mean([r.home_goals for r in rows]),
        "mean_predicted_away_goals": mean(pred_away),
        "mean_observed_away_goals": mean([r.away_goals for r in rows]),
        "prediction_availability": 1.0,
    }


def _fold_development_score(model_id: str, folds: Sequence[Any], feature_ids: Sequence[str] | None = None) -> tuple[float, list[dict[str,float]]]:
    metrics=[]
    for train, validation in folds:
        model=fit_challenger(model_id, train, feature_ids=feature_ids)
        metrics.append(evaluate_predictions(validation, model.predict(validation)))
    return float(np.mean([m["exact_score_nll"] for m in metrics])), metrics


def challenger_disagreement(distributions_by_model: Mapping[str, GoalScoreDistribution]) -> dict[str,float]:
    values=list(distributions_by_model.values())
    if len(values)<2:
        return {"home_intensity_range":0.0,"away_intensity_range":0.0,"total_intensity_range":0.0,"mean_pairwise_total_variation":0.0}
    home=[d.home_intensity for d in values]; away=[d.away_intensity for d in values]
    totals=[h+a for h,a in zip(home,away)]
    tv=[]
    for i in range(len(values)):
        for j in range(i+1,len(values)):
            keys=set(values[i].probabilities)|set(values[j].probabilities)
            tv.append(0.5*sum(abs(values[i].probabilities.get(k,0.0)-values[j].probabilities.get(k,0.0)) for k in keys))
    return {
        "home_intensity_range":max(home)-min(home),
        "away_intensity_range":max(away)-min(away),
        "total_intensity_range":max(totals)-min(totals),
        "mean_pairwise_total_variation":float(np.mean(tv)),
    }


def paired_date_bucket_bootstrap(rows: Sequence[TrainingRow], losses_a: Sequence[float], losses_b: Sequence[float], *, replicates: int = PAIR_BOOTSTRAP_REPLICATES, seed: int = RANDOM_SEED) -> dict[str,float]:
    if len(rows)!=len(losses_a) or len(rows)!=len(losses_b) or not rows:
        raise GoalScoreError("paired bootstrap requires common target set")
    by_date: dict[str,list[int]]={}
    for i,row in enumerate(rows): by_date.setdefault(row.match_date,[]).append(i)
    dates=sorted(by_date); rng=np.random.default_rng(seed); diffs=[]
    for _ in range(replicates):
        sampled=rng.choice(dates,size=len(dates),replace=True)
        idx=[i for d in sampled for i in by_date[d]]
        diffs.append(float(np.mean([losses_a[i]-losses_b[i] for i in idx])))
    return {"mean_difference":float(np.mean(diffs)),"lower_95":float(np.quantile(diffs,0.025)),"upper_95":float(np.quantile(diffs,0.975))}


def evaluate_challengers(rows: Sequence[TrainingRow]) -> dict[str, Any]:
    validate_evaluation_contract()
    split=chronological_split(rows); folds=rolling_origin_folds(split.development_rows)
    development={}; fold_metrics={}
    for definition in GOAL_SCORE_MODEL_REGISTRY:
        score, metrics=_fold_development_score(definition.model_id,folds)
        development[definition.model_id]=score; fold_metrics[definition.model_id]=metrics
    ranked=sorted(development,key=lambda k:(development[k],k))
    holdout_metrics={}; holdout_predictions={}
    for model_id in ranked:
        model=fit_challenger(model_id,split.development_rows)
        predictions=model.predict(split.holdout_rows)
        holdout_predictions[model_id]=predictions
        holdout_metrics[model_id]=evaluate_predictions(split.holdout_rows,predictions)
    best_dev=ranked[0]
    core_features=[f.feature_id for f in GOAL_SCORE_FEATURE_REGISTRY if not f.feature_id.startswith("TACTICAL.")]
    core_score,_=_fold_development_score(best_dev,folds,feature_ids=core_features)
    tactical_ablation={"model_id":best_dev,"historical_core_exact_score_nll":core_score,
                       "historical_plus_tactical_exact_score_nll":development[best_dev],
                       "delta_nll":development[best_dev]-core_score}
    holdout_ranked=sorted(ranked,key=lambda k:(holdout_metrics[k]["exact_score_nll"],k))
    disagreements=[]
    for index,row in enumerate(split.holdout_rows):
        disagreements.append({"match_key":row.match_key,**challenger_disagreement({m:holdout_predictions[m][index] for m in ranked})})
    return {
        "development_ranking":ranked,
        "development_exact_score_nll":development,
        "fold_metrics":fold_metrics,
        "holdout_ranking":holdout_ranked,
        "holdout_metrics":holdout_metrics,
        "research_challenger_winner":holdout_ranked[0],
        "production_promotion_eligible":False,
        "tactical_ablation":tactical_ablation,
        "challenger_disagreement":disagreements,
        "live_champion_replay_status":LIVE_CHAMPION_REPLAY_STATUS,
        "holdout_exposure":True,
        "holdout_dates":list(split.holdout_dates),
        "holdout_match_count":len(split.holdout_rows),
        "authority_flags":dict(AUTHORITY_FLAGS),
    }


__all__ = [name for name in globals() if not name.startswith("_")]
