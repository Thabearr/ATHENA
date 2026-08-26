"""Estimator and score-surface implementations for Goal/Score Dynamics v2."""
from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.optimize import minimize_scalar
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import PoissonRegressor

from domain.score_matrix import DEFAULT_TAIL_TOLERANCE, build_score_matrix, poisson_probability
from domain._goal_score_contracts import *


class FoldPreprocessor:
    """Train-fold-only median numeric transform retaining source status."""
    def __init__(self, feature_ids: Sequence[str] | None = None) -> None:
        self.feature_ids = tuple(feature_ids or (item.feature_id for item in GOAL_SCORE_FEATURE_REGISTRY))
        self.medians: dict[str, float] | None = None

    def fit(self, rows: Sequence[TrainingRow]) -> "FoldPreprocessor":
        if not rows:
            raise GoalScoreError("cannot fit preprocessor on empty train fold")
        medians: dict[str, float] = {}
        for feature_id in self.feature_ids:
            values = [
                float(row.features[feature_id][1])
                for row in rows
                if feature_id in row.features
                and row.features[feature_id][0] is FeatureStatus.AVAILABLE
                and row.features[feature_id][1] is not None
            ]
            medians[feature_id] = float(np.median(values)) if values else 0.0
        self.medians = medians
        return self

    def transform(self, rows: Sequence[TrainingRow]) -> np.ndarray:
        if self.medians is None:
            raise GoalScoreError("preprocessor must be fit on train rows first")
        matrix: list[list[float]] = []
        for row in rows:
            output: list[float] = []
            for feature_id in self.feature_ids:
                status, value = row.features.get(feature_id, (FeatureStatus.MISSING, None))
                output.append(float(value) if status is FeatureStatus.AVAILABLE else self.medians[feature_id])
                output.append(1.0 if status is FeatureStatus.MISSING else 0.0)
                output.append(1.0 if status is FeatureStatus.BLOCKED else 0.0)
            matrix.append(output)
        return np.asarray(matrix, dtype=float)


@dataclass(frozen=True)
class CompetitionPrior:
    global_home_rate: float
    global_away_rate: float
    competition_rates: Mapping[str, tuple[float, float, int, float]]

    def rates(self, competition_key: str | None) -> tuple[float, float, int, float]:
        if competition_key is None:
            return self.global_home_rate, self.global_away_rate, 0, 0.0
        return self.competition_rates.get(
            competition_key,
            (self.global_home_rate, self.global_away_rate, 0, 0.0),
        )


def fit_competition_prior(rows: Sequence[TrainingRow]) -> CompetitionPrior:
    if not rows:
        raise GoalScoreError("competition prior requires train rows")
    global_home = max(float(np.mean([row.home_goals for row in rows])), MIN_INTENSITY)
    global_away = max(float(np.mean([row.away_goals for row in rows])), MIN_INTENSITY)
    grouped: dict[str, list[TrainingRow]] = {}
    for row in rows:
        if row.competition_key is not None:
            grouped.setdefault(row.competition_key, []).append(row)
    rates: dict[str, tuple[float, float, int, float]] = {}
    for key, values in grouped.items():
        n = len(values)
        weight = n / (n + COMPETITION_PRIOR_K)
        raw_home = float(np.mean([row.home_goals for row in values]))
        raw_away = float(np.mean([row.away_goals for row in values]))
        home = max(weight * raw_home + (1.0 - weight) * global_home, MIN_INTENSITY)
        away = max(weight * raw_away + (1.0 - weight) * global_away, MIN_INTENSITY)
        rates[key] = (home, away, n, weight)
    return CompetitionPrior(global_home, global_away, MappingProxyType(rates))


def _with_prior_features(x: np.ndarray, rows: Sequence[TrainingRow], prior: CompetitionPrior) -> np.ndarray:
    extras = np.asarray([
        [math.log(prior.rates(row.competition_key)[0]),
         math.log(prior.rates(row.competition_key)[1])]
        for row in rows
    ], dtype=float)
    return np.hstack([x, extras])


@dataclass(frozen=True)
class GoalScoreDistribution:
    model_id: str
    home_intensity: float
    away_intensity: float
    rho: float | None
    probabilities: Mapping[tuple[int, int], float]
    max_home_goal: int
    max_away_goal: int
    retained_mass_before_normalization: float
    omitted_tail_mass: float
    normalization_method: str

    def __post_init__(self) -> None:
        for value in (self.home_intensity, self.away_intensity):
            if not math.isfinite(value) or value <= 0:
                raise GoalScoreError("score intensities must be finite and positive")
        total = math.fsum(self.probabilities.values())
        if not math.isfinite(total) or abs(total - 1.0) > 1e-10:
            raise GoalScoreError("normalized score surface must sum to one")
        if any((not math.isfinite(p) or p < 0) for p in self.probabilities.values()):
            raise GoalScoreError("score surface contains invalid probability mass")

    def sum_where(self, predicate: Any) -> float:
        return math.fsum(p for (h, a), p in self.probabilities.items() if predicate(h, a))

    @property
    def home_win(self) -> float:
        return self.sum_where(lambda h, a: h > a)

    @property
    def draw(self) -> float:
        return self.sum_where(lambda h, a: h == a)

    @property
    def away_win(self) -> float:
        return self.sum_where(lambda h, a: h < a)

    @property
    def btts_yes(self) -> float:
        return self.sum_where(lambda h, a: h > 0 and a > 0)

    @property
    def over_2_5(self) -> float:
        return self.sum_where(lambda h, a: h + a > 2.5)

    def total_goals_distribution(self) -> Mapping[int, float]:
        result: dict[int, float] = {}
        for (h, a), p in self.probabilities.items():
            result[h + a] = result.get(h + a, 0.0) + p
        return MappingProxyType(dict(sorted(result.items())))

    def goal_margin_distribution(self) -> Mapping[int, float]:
        result: dict[int, float] = {}
        for (h, a), p in self.probabilities.items():
            result[h - a] = result.get(h - a, 0.0) + p
        return MappingProxyType(dict(sorted(result.items())))

    def exact_probability(self, home_goals: int, away_goals: int) -> float:
        base = poisson_probability(home_goals, self.home_intensity) * poisson_probability(
            away_goals, self.away_intensity
        )
        if self.rho is None:
            return base
        return base * dixon_coles_tau(home_goals, away_goals, self.home_intensity,
                                      self.away_intensity, self.rho)

    def exact_total_probability(self, total_goals: int) -> float:
        if isinstance(total_goals, bool) or not isinstance(total_goals, int) or total_goals < 0:
            raise GoalScoreError("total_goals must be a non-negative integer")
        return math.fsum(self.exact_probability(home, total_goals-home) for home in range(total_goals+1))

    def exact_margin_probability(self, margin: int, maximum_goal_index: int = 200) -> float:
        if isinstance(margin, bool) or not isinstance(margin, int):
            raise GoalScoreError("margin must be an integer")
        start_home=max(0,margin); start_away=max(0,-margin)
        probability=math.fsum(
            self.exact_probability(start_home+offset, start_away+offset)
            for offset in range(maximum_goal_index+1)
        )
        if probability <= 0 or not math.isfinite(probability):
            raise GoalScoreError("invalid exact goal-margin probability")
        return probability


def dixon_coles_tau(h: int, a: int, lam: float, mu: float, rho: float) -> float:
    if (h, a) == (0, 0):
        return 1.0 - lam * mu * rho
    if (h, a) == (0, 1):
        return 1.0 + lam * rho
    if (h, a) == (1, 0):
        return 1.0 + mu * rho
    if (h, a) == (1, 1):
        return 1.0 - rho
    return 1.0


def _rho_bounds(lambdas: Sequence[float], mus: Sequence[float]) -> tuple[float, float]:
    if not lambdas or not mus or len(lambdas) != len(mus):
        raise GoalScoreError("rho fitting requires paired train intensities")
    lower = max(max(-1.0 / lam for lam in lambdas), max(-1.0 / mu for mu in mus)) + 1e-8
    upper = min(1.0, min(1.0 / (lam * mu) for lam, mu in zip(lambdas, mus))) - 1e-8
    if lower >= upper:
        raise GoalScoreError("no safe Dixon-Coles rho interval")
    return lower, upper


def fit_dixon_coles_rho(rows: Sequence[TrainingRow], lambdas: Sequence[float], mus: Sequence[float]) -> float:
    lower, upper = _rho_bounds(lambdas, mus)
    def objective(rho: float) -> float:
        total = 0.0
        for row, lam, mu in zip(rows, lambdas, mus):
            tau = dixon_coles_tau(row.home_goals, row.away_goals, lam, mu, rho)
            if tau <= 0 or not math.isfinite(tau):
                return math.inf
            total -= math.log(tau)
        return total
    result = minimize_scalar(objective, bounds=(lower, upper), method="bounded",
                             options={"xatol": 1e-9, "maxiter": 300})
    if not result.success or not math.isfinite(float(result.x)):
        raise GoalScoreError("Dixon-Coles rho optimization failed")
    rho = float(result.x)
    if any(dixon_coles_tau(h, a, lam, mu, rho) <= 0
           for lam, mu in zip(lambdas, mus) for h, a in ((0,0),(0,1),(1,0),(1,1))):
        raise GoalScoreError("Dixon-Coles fit produced negative low-score mass")
    return rho


def build_goal_score_distribution(model_id: str, home_intensity: float,
                                  away_intensity: float, rho: float | None = None) -> GoalScoreDistribution:
    lam = float(home_intensity)
    mu = float(away_intensity)
    if not math.isfinite(lam) or not math.isfinite(mu) or lam <= 0 or mu <= 0:
        raise GoalScoreError("model intensities must be finite and positive")
    matrix = build_score_matrix(lam, mu, tail_tolerance=DEFAULT_TAIL_TOLERANCE)
    raw: dict[tuple[int, int], float] = {}
    for score, p in matrix.raw_probabilities.items():
        tau = 1.0 if rho is None else dixon_coles_tau(score[0], score[1], lam, mu, rho)
        corrected = p * tau
        if not math.isfinite(corrected) or corrected < 0:
            raise GoalScoreError("invalid corrected score probability")
        raw[score] = corrected
    retained = math.fsum(raw.values())
    if retained <= 0:
        raise GoalScoreError("score distribution retained no mass")
    normalized = MappingProxyType({score: p / retained for score, p in raw.items()})
    return GoalScoreDistribution(
        model_id=model_id,
        home_intensity=lam,
        away_intensity=mu,
        rho=rho,
        probabilities=normalized,
        max_home_goal=matrix.max_home_goal,
        max_away_goal=matrix.max_away_goal,
        retained_mass_before_normalization=retained,
        omitted_tail_mass=max(0.0, 1.0 - retained),
        normalization_method="CORRECT_THEN_DIVIDE_BY_RETAINED_MASS_V1" if rho is not None else matrix.normalization_method,
    )


class FittedGoalScoreModel:
    def __init__(self, definition: GoalScoreModelDefinition, preprocessor: FoldPreprocessor,
                 prior: CompetitionPrior, home_model: Any, away_model: Any, rho: float | None = None):
        self.definition = definition
        self.preprocessor = preprocessor
        self.prior = prior
        self.home_model = home_model
        self.away_model = away_model
        self.rho = rho

    def predict_intensities(self, rows: Sequence[TrainingRow]) -> tuple[np.ndarray, np.ndarray]:
        x = _with_prior_features(self.preprocessor.transform(rows), rows, self.prior)
        home = np.asarray(self.home_model.predict(x), dtype=float)
        away = np.asarray(self.away_model.predict(x), dtype=float)
        if np.any(~np.isfinite(home)) or np.any(~np.isfinite(away)):
            raise GoalScoreError("challenger produced non-finite intensities")
        return np.maximum(home, MIN_INTENSITY), np.maximum(away, MIN_INTENSITY)

    def predict(self, rows: Sequence[TrainingRow]) -> list[GoalScoreDistribution]:
        home, away = self.predict_intensities(rows)
        return [build_goal_score_distribution(self.definition.model_id, float(lam), float(mu), self.rho)
                for lam, mu in zip(home, away)]


def _definition_by_id(model_id: str) -> GoalScoreModelDefinition:
    matches = [item for item in GOAL_SCORE_MODEL_REGISTRY if item.model_id == model_id]
    if len(matches) != 1:
        raise GoalScoreError(f"unknown Goal/Score challenger: {model_id}")
    return matches[0]


def fit_challenger(model_id: str, rows: Sequence[TrainingRow], *, feature_ids: Sequence[str] | None = None) -> FittedGoalScoreModel:
    if len(rows) < 2:
        raise GoalScoreError("challenger fitting requires at least two train rows")
    definition = _definition_by_id(model_id)
    preprocessor = FoldPreprocessor(feature_ids).fit(rows)
    prior = fit_competition_prior(rows)
    x = _with_prior_features(preprocessor.transform(rows), rows, prior)
    y_home = np.asarray([row.home_goals for row in rows], dtype=float)
    y_away = np.asarray([row.away_goals for row in rows], dtype=float)
    params = dict(definition.hyperparameters)
    if definition.family in {"INDEPENDENT_POISSON", "DIXON_COLES"}:
        home_model = PoissonRegressor(**params).fit(x, y_home)
        away_model = PoissonRegressor(**params).fit(x, y_away)
        fitted = FittedGoalScoreModel(definition, preprocessor, prior, home_model, away_model)
        rho = None
        if definition.family == "DIXON_COLES":
            lambdas, mus = fitted.predict_intensities(rows)
            rho = fit_dixon_coles_rho(rows, list(lambdas), list(mus))
        return FittedGoalScoreModel(definition, preprocessor, prior, home_model, away_model, rho)
    if definition.family == "NONLINEAR_POISSON":
        home_model = HistGradientBoostingRegressor(random_state=definition.random_seed, **params).fit(x, y_home)
        away_model = HistGradientBoostingRegressor(random_state=definition.random_seed, **params).fit(x, y_away)
        return FittedGoalScoreModel(definition, preprocessor, prior, home_model, away_model)
    raise GoalScoreError("unsupported challenger family")


__all__ = [name for name in globals() if not name.startswith("_")]
