"""Deterministic, research-only evaluator for the frozen PR75 protocol.

The public fixture-set seam is intentionally synthetic/adversarial.  The
evidence-bound builder is separate and must be called with complete PR69--75
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

from domain.historical_expected_goals_successor_candidate import (
    HistoricalExpectedGoalsSuccessorCandidate,
    _gradient_and_hessian,
    _response_nll,
    _rounded_coefficients,
    _solve_linear_system,
    build_historical_expected_goals_successor_candidate,
    canonical_historical_expected_goals_successor_candidate_bytes,
    revalidate_historical_expected_goals_successor_candidate,
    _legacy_rates,
    _model_rates,
    _ordered_eligible,
    _predictor_vector,
)
from domain.historical_expected_goals_successor_protocol import HistoricalExpectedGoalsSuccessorProtocol
from domain.historical_expected_goals_component_validation import HistoricalExpectedGoalsComponent
from domain.historical_model_feature_replay_candidate import (
    HistoricalReplayCorpus,
    HistoricalReplaySourceInput,
    canonical_historical_model_feature_replay_corpus_bytes,
    revalidate_historical_model_feature_replay_corpus,
)
from domain.historical_expected_goals_successor_robustness_protocol import (
    CLUSTER_KEYS,
    EVALUATION_FIXTURE_COUNT,
    IDENTITY_LEAGUES,
    PROTOCOL_ID,
    PR74_RECEIPT_SHA256,
    SUCCESSOR_CANDIDATE_SHA256,
    SUCCESSOR_CANDIDATE_SIZE,
    HistoricalExpectedGoalsSuccessorRobustnessProtocol,
    canonical_successor_robustness_protocol_bytes,
    revalidate_successor_robustness_protocol,
    sha256_successor_robustness_protocol,
)


SCHEMA_VERSION = 1
DATASET_NAME = "athena-historical-expected-goals-successor-robustness-evaluation-v1"
EVALUATION_SCOPE = "POST_HOC_PR74_FOLLOWUP_RESEARCH_EVALUATION_ONLY"
_SAFETY_KEYS = frozenset({
    "successor_candidate_approved", "expected_goals_transform_approved",
    "probability_inference_authorized", "score_matrix_authorized",
    "probability_adjustment_authorized", "calibration_for_production_authorized",
    "pricing_authorized", "market_activation_authorized", "selection_authorized",
    "production_approval_authorized", "bet_authorized",
})


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
        return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("canonical evaluation serialization failed") from exc


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS or any(type(v) is not bool or v is not False for v in value.values()):
        raise _error("evaluation safety must be exact false mapping")
    return _safety()


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
        if type(self.home_goals) is not int or type(self.away_goals) is not int or self.home_goals < 0 or self.away_goals < 0:
            raise _error("fixture goals must be non-negative exact integers")
        for value, label in ((self.successor_home_rate, "successor home rate"), (self.successor_away_rate, "successor away rate"), (self.elo_home_rate, "ELO home rate"), (self.elo_away_rate, "ELO away rate")):
            if _finite(value, label) <= 0.0:
                raise _error(f"{label} must be positive")
        if type(self.no_fatigue_predictors) is not tuple or len(self.no_fatigue_predictors) != 5:
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
        if _finite(self.gradient_inf_norm, "fit gradient") < 0 or _finite(self.training_mean_nll, "fit NLL") < 0:
            raise _error("fit diagnostics must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return {"coefficients": list(self.coefficients), "updates": self.updates, "gradient_inf_norm": self.gradient_inf_norm, "training_mean_nll": self.training_mean_nll}


def fit_poisson_design(*, rows: Sequence[tuple[float, ...]], responses: Sequence[int], fitting: Any) -> PoissonFit:
    """Five-or-more dimensional adapter reusing PR73 Newton primitives exactly."""

    if type(rows) not in (tuple, list) or not rows or len(rows) != len(responses):
        raise _error("fit rows/responses must be exact non-empty pairs")
    detached = tuple(tuple(_finite(v, "design value") for v in row) for row in rows)
    dimension = len(detached[0])
    if dimension < 1 or any(len(row) != dimension for row in detached):
        raise _error("design matrix dimensions differ")
    ys = tuple(responses)
    if any(type(y) is not int or y < 0 for y in ys):
        raise _error("Poisson responses must be non-negative exact integers")
    mean = math.fsum(ys) / len(ys)
    if not math.isfinite(mean) or mean <= 0:
        raise _error("training response mean must be strictly positive")
    beta = [math.log(mean)] + [0.0] * (dimension - 1)
    updates = 0
    while True:
        nll, _, mus = _response_nll(detached, ys, beta, fitting.maximum_abs_linear_predictor)
        gradient, hessian = _gradient_and_hessian(detached, ys, mus)
        norm = max(abs(value) for value in gradient)
        if norm <= fitting.gradient_inf_norm_tolerance:
            break
        if updates >= fitting.max_iterations:
            raise _error("frozen Newton solver did not converge")
        direction = _solve_linear_system(hessian, gradient, fitting.linear_solve_pivot_tolerance)
        step = 1.0
        while True:
            proposal = tuple(value + step * delta for value, delta in zip(beta, direction))
            try:
                proposal_nll, _, _ = _response_nll(detached, ys, proposal, fitting.maximum_abs_linear_predictor)
            except Exception as exc:
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
    rounded_nll, _, _ = _response_nll(detached, ys, rounded, fitting.maximum_abs_linear_predictor)
    return PoissonFit(rounded, updates, float(norm), float(rounded_nll / len(detached)))


def _poisson_nll(goals: int, rate: float) -> float:
    return _finite(rate - goals * math.log(rate) + math.lgamma(goals + 1), "Poisson NLL")


def _joint(fixture: RobustnessFixture, home: float, away: float) -> float:
    return math.fsum((_poisson_nll(fixture.home_goals, home), _poisson_nll(fixture.away_goals, away)))


def _mean(values: Sequence[float], label: str) -> float:
    if not values:
        raise _error(f"{label} cannot be empty")
    return _finite(math.fsum(values) / len(values), label)


def _calibration(fixtures: Sequence[RobustnessFixture], *, model: str, side: str) -> tuple[dict[str, Any], ...]:
    bounds = ((0.0, .5), (.5, 1.), (1., 1.5), (1.5, 2.), (2., 2.5), (2.5, 3.), (3., None))
    result = []
    for lower, upper in bounds:
        selected = []
        for fixture in fixtures:
            rate = getattr(fixture, f"{model}_{side}_rate")
            if rate >= lower and (upper is None or rate < upper):
                selected.append((rate, fixture.home_goals if side == "home" else fixture.away_goals))
        if not selected:
            result.append({"lower": lower, "upper": upper, "count": 0, "mean_predicted_goals": None, "mean_observed_goals": None, "calibration_error_predicted_minus_observed": None})
        else:
            predicted = _mean([x[0] for x in selected], "calibration predicted mean")
            observed = _mean([float(x[1]) for x in selected], "calibration observed mean")
            result.append({"lower": lower, "upper": upper, "count": len(selected), "mean_predicted_goals": predicted, "mean_observed_goals": observed, "calibration_error_predicted_minus_observed": predicted - observed})
    return tuple(result)


def _calibration_summary(bins: Sequence[Mapping[str, Any]], fixtures: Sequence[RobustnessFixture], *, model: str, side: str) -> Mapping[str, float]:
    predictions = [getattr(item, f"{model}_{side}_rate") for item in fixtures]
    outcomes = [float(item.home_goals if side == "home" else item.away_goals) for item in fixtures]
    errors = [item["count"] * abs(item["calibration_error_predicted_minus_observed"]) for item in bins if item["count"]]
    squares = [item["count"] * item["calibration_error_predicted_minus_observed"] ** 2 for item in bins if item["count"]]
    return types.MappingProxyType({"absolute_overall_bias": abs(_mean(predictions, "prediction") - _mean(outcomes, "outcome")), "wace": math.fsum(errors) / len(fixtures), "wsce": math.fsum(squares) / len(fixtures)})


def _sign_stable(full: float, omission: Sequence[float]) -> bool:
    return full != 0.0 and all(value != 0.0 and (value > 0.0) == (full > 0.0) for value in omission)


def _rate(row: Sequence[float], coefficients: Sequence[float], fitting: Any) -> float:
    eta = math.fsum(left * right for left, right in zip(row, coefficients))
    if abs(eta) > fitting.maximum_abs_linear_predictor:
        raise _error("rounded evaluation coefficient vector exceeds eta guard")
    return _finite(math.exp(eta), "refit rate")


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
    results: Mapping[str, Any]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if (self.schema_version, self.dataset_name, self.scope) != (SCHEMA_VERSION, DATASET_NAME, EVALUATION_SCOPE):
            raise _error("evaluation identity mismatch")
        if (self.pr74_receipt_sha256, self.successor_candidate_sha256, self.successor_candidate_size) != (PR74_RECEIPT_SHA256, SUCCESSOR_CANDIDATE_SHA256, SUCCESSOR_CANDIDATE_SIZE):
            raise _error("evaluation candidate ancestry mismatch")
        if self.protocol_id != PROTOCOL_ID or type(self.protocol_size) is not int or self.protocol_size <= 0:
            raise _error("evaluation protocol anchor mismatch")
        if not isinstance(self.results, Mapping):
            raise _error("evaluation results must be mapping")
        object.__setattr__(self, "safety", _validate_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "dataset_name": self.dataset_name, "scope": self.scope, "pr74_receipt_sha256": self.pr74_receipt_sha256, "successor_candidate_sha256": self.successor_candidate_sha256, "successor_candidate_size": self.successor_candidate_size, "protocol_id": self.protocol_id, "protocol_sha256": self.protocol_sha256, "protocol_size": self.protocol_size, "source_corpus_sha256": self.source_corpus_sha256, "results": dict(self.results), "safety": dict(self.safety)}


def evaluate_successor_robustness_fixture_set(*, protocol: HistoricalExpectedGoalsSuccessorRobustnessProtocol, fixtures: Sequence[RobustnessFixture], fitting: Any | None = None, full_home_fatigue: float = 1.0, full_away_fatigue: float = -1.0, omission_fatigue_coefficients: Sequence[tuple[float, float]] = ((1., -1.),) * 4) -> Mapping[str, Any]:
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
    if len(keys) != len(CLUSTER_KEYS):
        raise _error("missing frozen evaluation cluster")
    differences = {item.fixture_identifier: _joint(item, item.successor_home_rate, item.successor_away_rate) - _joint(item, item.elo_home_rate, item.elo_away_rate) for item in evaluation}
    theta = _mean(list(differences.values()), "paired full estimate")
    deletes=[]
    for season, league in CLUSTER_KEYS:
        omitted=[item for item in evaluation if (item.season,item.identity_league)==(season,league)]
        remaining=[item for item in evaluation if item not in omitted]
        if not omitted or not remaining: raise _error("invalid delete cluster")
        deletes.append({"season":season,"identity_league":league,"omitted_fixture_count":len(omitted),"remaining_fixture_count":len(remaining),"delete_estimate":_mean([differences[x.fixture_identifier] for x in remaining],"delete estimate")})
    theta_bar=_mean([item["delete_estimate"] for item in deletes],"unweighted delete estimate center")
    se=math.sqrt(((len(deletes)-1)/len(deletes))*math.fsum((item["delete_estimate"]-theta_bar)**2 for item in deletes))
    league_out=[]
    for league in IDENTITY_LEAGUES:
        omitted=[x for x in evaluation if x.identity_league==league]; remaining=[x for x in evaluation if x.identity_league!=league]
        league_out.append({"omitted_league":league,"omitted_fixture_count":len(omitted),"remaining_fixture_count":len(remaining),"candidate_minus_elo_mean_nll":_mean([differences[x.fixture_identifier] for x in remaining],"league deletion")})
    season_out=[]
    for season in ("2024-25","2025-26"):
        omitted=[x for x in evaluation if x.season==season]; remaining=[x for x in evaluation if x.season!=season]
        season_out.append({"omitted_season":season,"omitted_fixture_count":len(omitted),"remaining_fixture_count":len(remaining),"candidate_minus_elo_mean_nll":_mean([differences[x.fixture_identifier] for x in remaining],"season deletion")})
    cals={(model,side):_calibration(evaluation,model=model,side=side) for model in ("successor","elo") for side in ("home","away")}
    summaries={(model,side):_calibration_summary(cals[(model,side)],evaluation,model=model,side=side) for model in ("successor","elo") for side in ("home","away")}
    omission_records=[]
    if fitting is not None:
        no_home=fit_poisson_design(rows=[x.no_fatigue_predictors for x in training],responses=[x.home_goals for x in training],fitting=fitting)
        no_away=fit_poisson_design(rows=[x.no_fatigue_predictors for x in training],responses=[x.away_goals for x in training],fitting=fitting)
        no_rates=lambda item,fit: _rate(item.no_fatigue_predictors,fit.coefficients,fitting)
        no_nll=_mean([_joint(item,no_rates(item,no_home),no_rates(item,no_away)) for item in evaluation],"no-fatigue NLL")
        full_nll = _mean(
            [_joint(item, item.successor_home_rate, item.successor_away_rate) for item in evaluation],
            "full successor NLL",
        )
        expected_omissions=("2020-21","2021-22","2022-23","2023-24")
        if {item.season for item in training} != set(expected_omissions):
            raise _error("diagnostic refits require every frozen training season")
        for omitted in expected_omissions:
            retained=tuple(item for item in training if item.season != omitted)
            home=fit_poisson_design(rows=[x.full_predictors for x in retained],responses=[x.home_goals for x in retained],fitting=fitting)
            away=fit_poisson_design(rows=[x.full_predictors for x in retained],responses=[x.away_goals for x in retained],fitting=fitting)
            mean=_mean([_joint(item,_rate(item.full_predictors,home.coefficients,fitting),_rate(item.full_predictors,away.coefficients,fitting)) for item in evaluation],"omission evaluation NLL")
            omission_records.append({"omitted_training_season":omitted,"training_fixture_count":len(retained),"home_fit":home.to_dict(),"away_fit":away.to_dict(),"evaluation_fixture_count":len(evaluation),"evaluation_mean_joint_nll":mean,"home_fatigue_coefficient":home.coefficients[-1],"away_fatigue_coefficient":away.coefficients[-1]})
        omission_fatigue_coefficients=tuple((item["home_fatigue_coefficient"],item["away_fatigue_coefficient"]) for item in omission_records)
    else:
        no_home=no_away=None; no_nll=None; full_nll=None
    deltas={f"{side}_{metric}":summaries[("successor",side)][metric]-summaries[("elo",side)][metric] for side in ("home","away") for metric in ("absolute_overall_bias","wace","wsce")}
    interpretation={"paired_elo_interval_upper_below_zero": theta+1.96*se<0,"all_leave_one_league_out_deltas_negative":all(x["candidate_minus_elo_mean_nll"]<0 for x in league_out),"both_leave_one_season_out_deltas_negative":all(x["candidate_minus_elo_mean_nll"]<0 for x in season_out),"no_fatigue_ablation_better_than_full": no_nll is not None and no_nll<full_nll,"home_fatigue_sign_stable_across_training_season_omissions":_sign_stable(full_home_fatigue,[x[0] for x in omission_fatigue_coefficients]),"away_fatigue_sign_stable_across_training_season_omissions":_sign_stable(full_away_fatigue,[x[1] for x in omission_fatigue_coefficients]),"successor_lower_home_wace_than_same_fixture_elo":deltas["home_wace"]<0,"successor_lower_away_wace_than_same_fixture_elo":deltas["away_wace"]<0,"successor_lower_home_wsce_than_same_fixture_elo":deltas["home_wsce"]<0,"successor_lower_away_wsce_than_same_fixture_elo":deltas["away_wsce"]<0}
    return types.MappingProxyType({"paired_nll":{"full_estimate":theta,"jackknife_se":se,"interval_lower":theta-1.96*se,"interval_upper":theta+1.96*se,"cluster_count":len(deletes),"delete_clusters":deletes,"leave_one_league_out":league_out,"leave_one_season_out":season_out},"calibration":{"bins":{f"{m}_{s}":list(cals[(m,s)]) for m in ("successor","elo") for s in ("home","away")},"summaries":{f"{m}_{s}":dict(summaries[(m,s)]) for m in ("successor","elo") for s in ("home","away")},"successor_minus_elo":deltas},"no_fatigue":{"home_fit":None if no_home is None else no_home.to_dict(),"away_fit":None if no_away is None else no_away.to_dict(),"full_successor_mean_joint_nll":full_nll,"no_fatigue_mean_joint_nll":no_nll,"no_fatigue_minus_full_nll":None if no_nll is None else no_nll-full_nll},"leave_one_training_season_refits":omission_records,"interpretation":interpretation})


def canonical_historical_expected_goals_successor_robustness_evaluation_bytes(value: HistoricalExpectedGoalsSuccessorRobustnessEvaluation) -> bytes:
    if type(value) is not HistoricalExpectedGoalsSuccessorRobustnessEvaluation: raise _error("evaluation type mismatch")
    HistoricalExpectedGoalsSuccessorRobustnessEvaluation(**value.__dict__)
    return _canonical(value.to_dict())


def sha256_historical_expected_goals_successor_robustness_evaluation(value: HistoricalExpectedGoalsSuccessorRobustnessEvaluation) -> str:
    return _sha(canonical_historical_expected_goals_successor_robustness_evaluation_bytes(value))


def build_historical_expected_goals_successor_robustness_evaluation(
    *,
    receipt_bytes: bytes,
    protocol: HistoricalExpectedGoalsSuccessorRobustnessProtocol,
    protocol_bytes: bytes,
    source_corpus_sha256: str,
    results: Mapping[str, Any],
) -> HistoricalExpectedGoalsSuccessorRobustnessEvaluation:
    """Wrap already recomputed results only after exact PR74/PR75 anchor checks.

    The future source-bound runner supplies results reconstructed from PR69/PR73;
    this small constructor intentionally has no filesystem or corpus access.
    """
    revalidate_successor_robustness_protocol(receipt_bytes=receipt_bytes, protocol=protocol, protocol_bytes=protocol_bytes)
    if source_corpus_sha256 != protocol.source_corpus_sha256:
        raise _error("source corpus SHA differs from frozen protocol")
    if not isinstance(results, Mapping):
        raise _error("results must be mapping")
    return HistoricalExpectedGoalsSuccessorRobustnessEvaluation(
        schema_version=SCHEMA_VERSION, dataset_name=DATASET_NAME, scope=EVALUATION_SCOPE,
        pr74_receipt_sha256=PR74_RECEIPT_SHA256,
        successor_candidate_sha256=SUCCESSOR_CANDIDATE_SHA256,
        successor_candidate_size=SUCCESSOR_CANDIDATE_SIZE,
        protocol_id=protocol.protocol_id,
        protocol_sha256=sha256_successor_robustness_protocol(protocol),
        protocol_size=len(protocol_bytes), source_corpus_sha256=source_corpus_sha256,
        results=types.MappingProxyType(dict(results)), safety=_safety(),
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
    """Future real-evidence boundary; caller supplies all exact PR69--75 inputs.

    It is deliberately not invoked by PR76 tests.  The function rebuilds the
    PR69 corpus and PR73 candidate before it derives a fixture calculation set.
    """
    revalidate_successor_robustness_protocol(
        receipt_bytes=pr75_receipt_bytes, protocol=pr75_protocol,
        protocol_bytes=pr75_protocol_bytes,
    )
    rebuilt_corpus = revalidate_historical_model_feature_replay_corpus(
        source_inputs=source_inputs, corpus=corpus, corpus_bytes=corpus_bytes,
    )
    rebuilt_corpus_bytes = canonical_historical_model_feature_replay_corpus_bytes(rebuilt_corpus)
    if _sha(rebuilt_corpus_bytes) != pr75_protocol.source_corpus_sha256:
        raise _error("reconstructed source corpus SHA differs from PR75")
    candidate = build_historical_expected_goals_successor_candidate(
        source_inputs=source_inputs, corpus=rebuilt_corpus, corpus_bytes=rebuilt_corpus_bytes,
        receipt_bytes=pr73_receipt_bytes, protocol=pr73_protocol,
        protocol_bytes=pr73_protocol_bytes,
    )
    candidate_bytes = canonical_historical_expected_goals_successor_candidate_bytes(candidate)
    if _sha(candidate_bytes) != SUCCESSOR_CANDIDATE_SHA256 or len(candidate_bytes) != SUCCESSOR_CANDIDATE_SIZE:
        raise _error("reconstructed PR73 candidate identity differs from PR74")
    training = _ordered_eligible(pr73_protocol, rebuilt_corpus.fixtures, pr73_protocol.train_seasons)
    evaluation = _ordered_eligible(pr73_protocol, rebuilt_corpus.fixtures, pr73_protocol.evaluation_seasons)
    if len(training) != 14_130 or len(evaluation) != EVALUATION_FIXTURE_COUNT:
        raise _error("exact PR73 population membership differs from PR75")
    if tuple((season, sum(item.season == season for item in training)) for season in pr73_protocol.train_seasons) != pr75_protocol.fatigue.training_season_counts:
        raise _error("PR73 training season membership differs from PR75")
    if tuple((season, sum(item.season == season for item in evaluation)) for season in pr73_protocol.evaluation_seasons) != pr75_protocol.fatigue.evaluation_season_counts:
        raise _error("PR73 evaluation season membership differs from PR75")
    if {(item.season, item.identity_league) for item in evaluation} != set(CLUSTER_KEYS):
        raise _error("PR73 evaluation clusters differ from PR75")
    calculation: list[RobustnessFixture] = []
    for fixture in tuple(training) + tuple(evaluation):
        home_rate, away_rate = _model_rates(pr73_protocol, fixture, candidate.fit_evaluation.home_fit, candidate.fit_evaluation.away_fit)
        elo_home, elo_away = _legacy_rates(
            fixture, HistoricalExpectedGoalsComponent.ELO_FALLBACK_COMPONENT
        )
        full = _predictor_vector(pr73_protocol, fixture)
        calculation.append(RobustnessFixture(
            fixture_identifier=fixture.fixture_identifier, season=fixture.season,
            identity_league=fixture.identity_league,
            split="TRAIN" if fixture in training else "EVALUATION",
            home_goals=fixture.home_goals, away_goals=fixture.away_goals,
            successor_home_rate=home_rate, successor_away_rate=away_rate,
            elo_home_rate=elo_home, elo_away_rate=elo_away,
            no_fatigue_predictors=tuple(full[:5]), full_predictors=full,
        ))
    results = evaluate_successor_robustness_fixture_set(
        protocol=pr75_protocol, fixtures=tuple(calculation), fitting=pr73_protocol.fitting,
        full_home_fatigue=candidate.fit_evaluation.home_fit.coefficients[-1],
        full_away_fatigue=candidate.fit_evaluation.away_fit.coefficients[-1],
    )
    return build_historical_expected_goals_successor_robustness_evaluation(
        receipt_bytes=pr75_receipt_bytes, protocol=pr75_protocol,
        protocol_bytes=pr75_protocol_bytes,
        source_corpus_sha256=rebuilt_corpus.source_corpus_sha256, results=results,
    )


def revalidate_historical_expected_goals_successor_robustness_evaluation(
    *, receipt_bytes: bytes, protocol: HistoricalExpectedGoalsSuccessorRobustnessProtocol,
    protocol_bytes: bytes, evaluation: HistoricalExpectedGoalsSuccessorRobustnessEvaluation,
    evaluation_bytes: bytes,
) -> HistoricalExpectedGoalsSuccessorRobustnessEvaluation:
    """Revalidate detached result identity against exact PR74/PR75 anchors."""
    if type(evaluation_bytes) is not bytes or not evaluation_bytes:
        raise _error("evaluation bytes must be exact non-empty bytes")
    rebuilt = build_historical_expected_goals_successor_robustness_evaluation(
        receipt_bytes=receipt_bytes, protocol=protocol, protocol_bytes=protocol_bytes,
        source_corpus_sha256=evaluation.source_corpus_sha256, results=evaluation.results,
    )
    expected = canonical_historical_expected_goals_successor_robustness_evaluation_bytes(rebuilt)
    if evaluation != rebuilt or evaluation_bytes != expected:
        raise _error("evaluation object or canonical bytes differ from rebuild")
    return rebuilt


def revalidate_source_bound_historical_expected_goals_successor_robustness_evaluation(
    *,
    source_inputs: Sequence[HistoricalReplaySourceInput], corpus: HistoricalReplayCorpus,
    corpus_bytes: bytes, pr73_receipt_bytes: bytes,
    pr73_protocol: HistoricalExpectedGoalsSuccessorProtocol, pr73_protocol_bytes: bytes,
    pr75_receipt_bytes: bytes, pr75_protocol: HistoricalExpectedGoalsSuccessorRobustnessProtocol,
    pr75_protocol_bytes: bytes, evaluation: HistoricalExpectedGoalsSuccessorRobustnessEvaluation,
    evaluation_bytes: bytes,
) -> HistoricalExpectedGoalsSuccessorRobustnessEvaluation:
    """Full replay revalidator for a future source-bound real evaluation."""
    if type(evaluation_bytes) is not bytes or not evaluation_bytes:
        raise _error("evaluation bytes must be exact non-empty bytes")
    rebuilt = build_source_bound_historical_expected_goals_successor_robustness_evaluation(
        source_inputs=source_inputs, corpus=corpus, corpus_bytes=corpus_bytes,
        pr73_receipt_bytes=pr73_receipt_bytes, pr73_protocol=pr73_protocol,
        pr73_protocol_bytes=pr73_protocol_bytes, pr75_receipt_bytes=pr75_receipt_bytes,
        pr75_protocol=pr75_protocol, pr75_protocol_bytes=pr75_protocol_bytes,
    )
    exact = canonical_historical_expected_goals_successor_robustness_evaluation_bytes(rebuilt)
    if evaluation != rebuilt or evaluation_bytes != exact:
        raise _error("source-bound evaluation differs from complete ancestry rebuild")
    return rebuilt
