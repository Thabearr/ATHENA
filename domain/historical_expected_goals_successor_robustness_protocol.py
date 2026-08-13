"""Frozen post-hoc research protocol for successor robustness analysis.

This module deliberately freezes definitions before any PR75 robustness,
calibration, or fatigue-ablation result is executed.  It is not an evaluator.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import types
from collections.abc import Mapping
from typing import Any

from domain.historical_expected_goals_successor_protocol import (
    EVALUATION_SEASONS,
    PR69_SOURCE_CORPUS_SHA256,
)


SCHEMA_VERSION = 1
PROTOCOL_ID = "HISTORICAL_EXPECTED_GOALS_SUCCESSOR_ROBUSTNESS_PROTOCOL_V1"
PROTOCOL_SCOPE = "POST_HOC_PR74_FOLLOWUP_PRE_REGISTERED_BEFORE_ROBUSTNESS_EXECUTION"
PR74_RECEIPT_SHA256 = "fd8b53b0429227f7595072156b6e06824e88ea53ae7c08807cac47b0a9821d32"
SUCCESSOR_CANDIDATE_SHA256 = "1fe9ff5f0963355bb98ae93d205a5ea3cb9aa53592601a7b06ff4000f6091660"
SUCCESSOR_CANDIDATE_SIZE = 19_956
EVALUATION_FIXTURE_COUNT = 6_903
IDENTITY_LEAGUES = ("B1", "D1", "E0", "F1", "G1", "I1", "N1", "P1", "SC0", "SP1", "T1")
CLUSTER_COUNT = 22
CALIBRATION_BINS = (
    (0.0, 0.5),
    (0.5, 1.0),
    (1.0, 1.5),
    (1.5, 2.0),
    (2.0, 2.5),
    (2.5, 3.0),
    (3.0, None),
)
FATIGUE_SEMANTICS = "HOME_REST_DAYS_MINUS_AWAY_REST_DAYS;LT_MINUS_2_TO_0_30;LT_0_TO_0_10;ELSE_0_00"
FATIGUE_PR31_SEMANTIC_EQUIVALENCE = "UNPROVEN"

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


class HistoricalExpectedGoalsSuccessorRobustnessProtocolError(ValueError):
    """Raised when the frozen PR75 research protocol is not exact."""


def _error(message: str) -> HistoricalExpectedGoalsSuccessorRobustnessProtocolError:
    return HistoricalExpectedGoalsSuccessorRobustnessProtocolError(message)


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("robustness protocol serialization failed") from exc


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _default_safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise _error("robustness protocol safety keys mismatch")
    if any(type(flag) is not bool or flag is not False for flag in value.values()):
        raise _error("robustness protocol safety must be exact bool False")
    return _default_safety()


def _exact_tuple(value: Any, expected: tuple[Any, ...], label: str) -> None:
    if type(value) is not tuple or value != expected:
        raise _error(f"{label} is frozen")


def _validated_pr74_receipt(receipt_bytes: bytes) -> Mapping[str, Any]:
    if type(receipt_bytes) is not bytes or not receipt_bytes:
        raise _error("receipt_bytes must be exact non-empty immutable bytes")
    if _sha256(receipt_bytes) != PR74_RECEIPT_SHA256:
        raise _error("PR74 receipt SHA-256 mismatch")
    try:
        payload = json.loads(receipt_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error("PR74 receipt must be UTF-8 JSON") from exc
    if not isinstance(payload, Mapping) or _canonical_json_bytes(payload) != receipt_bytes:
        raise _error("PR74 receipt must be exact canonical JSON")
    if payload.get("dataset_name") != "athena-historical-expected-goals-successor-real-corpus-receipt-v1":
        raise _error("PR74 receipt dataset mismatch")
    if payload.get("source_corpus_sha256") != PR69_SOURCE_CORPUS_SHA256:
        raise _error("PR74 source corpus ancestry mismatch")
    if payload.get("source_fixture_count") != 21_226:
        raise _error("PR74 source fixture count mismatch")
    candidate = payload.get("candidate")
    if not isinstance(candidate, Mapping):
        raise _error("PR74 receipt candidate is missing")
    candidate_bytes = _canonical_json_bytes(candidate)
    if _sha256(candidate_bytes) != SUCCESSOR_CANDIDATE_SHA256 or len(candidate_bytes) != SUCCESSOR_CANDIDATE_SIZE:
        raise _error("PR74 embedded successor candidate identity mismatch")
    if payload.get("successor_candidate_sha256") != SUCCESSOR_CANDIDATE_SHA256 or payload.get("successor_candidate_size") != SUCCESSOR_CANDIDATE_SIZE:
        raise _error("PR74 successor candidate anchor mismatch")
    fit = candidate.get("fit_evaluation")
    if not isinstance(fit, Mapping):
        raise _error("PR74 candidate fit/evaluation is missing")
    if fit.get("evaluation_fixture_count") != EVALUATION_FIXTURE_COUNT:
        raise _error("PR74 evaluation fixture count mismatch")
    if fit.get("evaluation_season_counts") != {"2024-25": 3468, "2025-26": 3435}:
        raise _error("PR74 evaluation seasons mismatch")
    leagues = fit.get("league_breakdown")
    if not isinstance(leagues, list) or {item.get("group_key") for item in leagues if isinstance(item, Mapping)} != set(IDENTITY_LEAGUES):
        raise _error("PR74 identity league set mismatch")
    return types.MappingProxyType(dict(payload))


@dataclasses.dataclass(frozen=True)
class PairedNllRobustnessSpec:
    comparator: str
    fixture_difference: str
    full_population_fixture_count: int
    cluster_key: tuple[str, str]
    cluster_count: int
    delete_cluster_estimator: str
    jackknife_standard_error: str
    interval_multiplier: float
    interval: str

    def __post_init__(self) -> None:
        if self.comparator != "PR68_ELO_FALLBACK_COMPONENT":
            raise _error("primary comparator is frozen to legacy ELO")
        if self.fixture_difference != "SUCCESSOR_JOINT_POISSON_NLL_MINUS_LEGACY_ELO_JOINT_POISSON_NLL_SAME_FIXTURE":
            raise _error("paired fixture difference is frozen")
        if self.full_population_fixture_count != EVALUATION_FIXTURE_COUNT:
            raise _error("paired population fixture count is frozen")
        _exact_tuple(self.cluster_key, ("season", "identity_league"), "cluster key")
        if self.cluster_count != CLUSTER_COUNT:
            raise _error("cluster count is frozen")
        if self.delete_cluster_estimator != "DELETE_ONE_CLUSTER_FIXTURE_WEIGHTED_MEAN_ON_REMAINING_FIXTURES":
            raise _error("delete-cluster estimator is frozen")
        if self.jackknife_standard_error != "SQRT(((K_MINUS_1)/K)*SUM((THETA_DELETE_J_MINUS_THETA_BAR)^2))":
            raise _error("jackknife formula is frozen")
        if self.interval_multiplier != 1.96 or self.interval != "THETA_PLUS_MINUS_1_96_TIMES_JACKKNIFE_SE":
            raise _error("nominal interval is frozen")

    def to_dict(self) -> dict[str, Any]:
        value = dataclasses.asdict(self)
        value["cluster_key"] = list(self.cluster_key)
        return value


@dataclasses.dataclass(frozen=True)
class CalibrationSpec:
    population: str
    sides: tuple[str, ...]
    models: tuple[str, ...]
    bins: tuple[tuple[float, float | None], ...]
    bin_assignment: str
    per_bin_fields: tuple[str, ...]
    summary_metrics: tuple[str, ...]
    absolute_overall_bias_formula: str
    wace_formula: str
    wsce_formula: str
    comparison_direction: str

    def __post_init__(self) -> None:
        if self.population != "EXACT_PR74_6903_EVALUATION_FIXTURES_FOR_BOTH_MODELS":
            raise _error("same-fixture calibration population is frozen")
        _exact_tuple(self.sides, ("HOME", "AWAY"), "calibration sides")
        _exact_tuple(self.models, ("SUCCESSOR", "PR68_ELO_FALLBACK_COMPONENT"), "calibration models")
        _exact_tuple(self.bins, CALIBRATION_BINS, "calibration bins")
        if self.bin_assignment != "EACH_MODEL_ASSIGNED_BY_ITS_OWN_PREDICTED_RATE":
            raise _error("calibration bin assignment is frozen")
        _exact_tuple(self.per_bin_fields, ("count", "mean_predicted_goals", "mean_observed_goals", "calibration_error_predicted_minus_observed"), "calibration bin fields")
        _exact_tuple(self.summary_metrics, ("ABSOLUTE_OVERALL_BIAS", "WACE", "WSCE"), "calibration summary metrics")
        if self.absolute_overall_bias_formula != "ABS(MEAN_PREDICTED_GOALS_MINUS_MEAN_OBSERVED_GOALS)":
            raise _error("absolute overall bias formula is frozen")
        if self.wace_formula != "SUM(COUNT_B_TIMES_ABS(CALIBRATION_ERROR_B))_DIVIDED_BY_6903":
            raise _error("WACE formula is frozen")
        if self.wsce_formula != "SUM(COUNT_B_TIMES_CALIBRATION_ERROR_B_SQUARED)_DIVIDED_BY_6903":
            raise _error("WSCE formula is frozen")
        if self.comparison_direction != "SUCCESSOR_MINUS_ELO_NEGATIVE_IS_LOWER":
            raise _error("calibration comparison direction is frozen")

    def to_dict(self) -> dict[str, Any]:
        value = dataclasses.asdict(self)
        value["sides"] = list(self.sides)
        value["models"] = list(self.models)
        value["bins"] = [list(item) for item in self.bins]
        value["per_bin_fields"] = list(self.per_bin_fields)
        value["summary_metrics"] = list(self.summary_metrics)
        return value


@dataclasses.dataclass(frozen=True)
class FatigueAnalysisSpec:
    ablation_id: str
    full_predictors: tuple[str, ...]
    ablation_predictors: tuple[str, ...]
    train_seasons: tuple[str, ...]
    evaluation_seasons: tuple[str, ...]
    solver_parity: str
    leave_one_training_seasons: tuple[str, ...]
    fatigue_semantics: str
    fatigue_pr31_semantic_equivalence: str
    retained_predictor_transforms: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.ablation_id != "NO_FATIGUE_ABLATION":
            raise _error("fatigue ablation identity is frozen")
        _exact_tuple(self.full_predictors, ("intercept", "home_elo", "away_elo", "home_form", "away_form", "fatigue"), "full predictors")
        _exact_tuple(self.ablation_predictors, ("intercept", "home_elo", "away_elo", "home_form", "away_form"), "ablation predictors")
        _exact_tuple(self.train_seasons, ("2020-21", "2021-22", "2022-23", "2023-24"), "fatigue training seasons")
        _exact_tuple(self.evaluation_seasons, EVALUATION_SEASONS, "fatigue evaluation seasons")
        if self.solver_parity != "PR72_PR73_FROZEN_POISSON_GLM_NEWTON_LINE_SEARCH_CONVERGENCE_AND_ROUNDING":
            raise _error("fatigue solver parity is frozen")
        _exact_tuple(self.leave_one_training_seasons, self.train_seasons, "leave-one-training-season diagnostics")
        if self.fatigue_semantics != FATIGUE_SEMANTICS or self.fatigue_pr31_semantic_equivalence != FATIGUE_PR31_SEMANTIC_EQUIVALENCE:
            raise _error("fatigue semantics are frozen")
        _exact_tuple(
            self.retained_predictor_transforms,
            (
                "intercept=CONSTANT_ONE",
                "home_elo=(VALUE_MINUS_1500_0)_DIVIDED_BY_400_0",
                "away_elo=(VALUE_MINUS_1500_0)_DIVIDED_BY_400_0",
                "home_form=VALUE_MINUS_0_5",
                "away_form=VALUE_MINUS_0_5",
            ),
            "fatigue ablation retained predictor transforms",
        )

    def to_dict(self) -> dict[str, Any]:
        value = dataclasses.asdict(self)
        for key in ("full_predictors", "ablation_predictors", "train_seasons", "evaluation_seasons", "leave_one_training_seasons"):
            value[key] = list(getattr(self, key))
        return value


@dataclasses.dataclass(frozen=True)
class HistoricalExpectedGoalsSuccessorRobustnessProtocol:
    schema_version: int
    protocol_id: str
    scope: str
    pr74_receipt_sha256: str
    successor_candidate_sha256: str
    successor_candidate_size: int
    source_corpus_sha256: str
    evaluation_fixture_count: int
    evaluation_seasons: tuple[str, ...]
    identity_leagues: tuple[str, ...]
    paired_nll: PairedNllRobustnessSpec
    leave_one_league_out: str
    leave_one_season_out: str
    calibration: CalibrationSpec
    fatigue: FatigueAnalysisSpec
    interpretation_fields: tuple[str, ...]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION or self.protocol_id != PROTOCOL_ID or self.scope != PROTOCOL_SCOPE:
            raise _error("protocol identity is frozen")
        if (self.pr74_receipt_sha256, self.successor_candidate_sha256, self.successor_candidate_size, self.source_corpus_sha256) != (PR74_RECEIPT_SHA256, SUCCESSOR_CANDIDATE_SHA256, SUCCESSOR_CANDIDATE_SIZE, PR69_SOURCE_CORPUS_SHA256):
            raise _error("protocol ancestry is frozen")
        if self.evaluation_fixture_count != EVALUATION_FIXTURE_COUNT:
            raise _error("evaluation fixture count is frozen")
        _exact_tuple(self.evaluation_seasons, EVALUATION_SEASONS, "evaluation seasons")
        _exact_tuple(self.identity_leagues, IDENTITY_LEAGUES, "identity leagues")
        if type(self.paired_nll) is not PairedNllRobustnessSpec or type(self.calibration) is not CalibrationSpec or type(self.fatigue) is not FatigueAnalysisSpec:
            raise _error("nested protocol specification types are exact")
        if self.leave_one_league_out != "OMIT_ONE_IDENTITY_LEAGUE_ACROSS_BOTH_EVALUATION_SEASONS_FIXTURE_WEIGHTED_MEAN":
            raise _error("leave-one-league-out sensitivity is frozen")
        if self.leave_one_season_out != "OMIT_ONE_EVALUATION_SEASON_FIXTURE_WEIGHTED_MEAN":
            raise _error("leave-one-season-out sensitivity is frozen")
        _exact_tuple(self.interpretation_fields, (
            "paired_elo_interval_upper_below_zero", "all_leave_one_league_out_deltas_negative", "both_leave_one_season_out_deltas_negative", "no_fatigue_ablation_better_than_full", "home_fatigue_sign_stable_across_training_season_omissions", "away_fatigue_sign_stable_across_training_season_omissions", "successor_lower_home_wace_than_same_fixture_elo", "successor_lower_away_wace_than_same_fixture_elo", "successor_lower_home_wsce_than_same_fixture_elo", "successor_lower_away_wsce_than_same_fixture_elo",
        ), "interpretation fields")
        object.__setattr__(self, "safety", _validate_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "protocol_id": self.protocol_id,
            "scope": self.scope,
            "pr74_receipt_sha256": self.pr74_receipt_sha256,
            "successor_candidate_sha256": self.successor_candidate_sha256,
            "successor_candidate_size": self.successor_candidate_size,
            "source_corpus_sha256": self.source_corpus_sha256,
            "evaluation_fixture_count": self.evaluation_fixture_count,
            "evaluation_seasons": list(self.evaluation_seasons),
            "identity_leagues": list(self.identity_leagues),
            "paired_nll": self.paired_nll.to_dict(),
            "leave_one_league_out": self.leave_one_league_out,
            "leave_one_season_out": self.leave_one_season_out,
            "calibration": self.calibration.to_dict(),
            "fatigue": self.fatigue.to_dict(),
            "interpretation_fields": list(self.interpretation_fields),
            "safety": dict(self.safety),
        }


def _paired_nll_spec() -> PairedNllRobustnessSpec:
    return PairedNllRobustnessSpec(
        comparator="PR68_ELO_FALLBACK_COMPONENT",
        fixture_difference="SUCCESSOR_JOINT_POISSON_NLL_MINUS_LEGACY_ELO_JOINT_POISSON_NLL_SAME_FIXTURE",
        full_population_fixture_count=EVALUATION_FIXTURE_COUNT,
        cluster_key=("season", "identity_league"),
        cluster_count=CLUSTER_COUNT,
        delete_cluster_estimator="DELETE_ONE_CLUSTER_FIXTURE_WEIGHTED_MEAN_ON_REMAINING_FIXTURES",
        jackknife_standard_error="SQRT(((K_MINUS_1)/K)*SUM((THETA_DELETE_J_MINUS_THETA_BAR)^2))",
        interval_multiplier=1.96,
        interval="THETA_PLUS_MINUS_1_96_TIMES_JACKKNIFE_SE",
    )


def _calibration_spec() -> CalibrationSpec:
    return CalibrationSpec(
        population="EXACT_PR74_6903_EVALUATION_FIXTURES_FOR_BOTH_MODELS",
        sides=("HOME", "AWAY"),
        models=("SUCCESSOR", "PR68_ELO_FALLBACK_COMPONENT"),
        bins=CALIBRATION_BINS,
        bin_assignment="EACH_MODEL_ASSIGNED_BY_ITS_OWN_PREDICTED_RATE",
        per_bin_fields=("count", "mean_predicted_goals", "mean_observed_goals", "calibration_error_predicted_minus_observed"),
        summary_metrics=("ABSOLUTE_OVERALL_BIAS", "WACE", "WSCE"),
        absolute_overall_bias_formula="ABS(MEAN_PREDICTED_GOALS_MINUS_MEAN_OBSERVED_GOALS)",
        wace_formula="SUM(COUNT_B_TIMES_ABS(CALIBRATION_ERROR_B))_DIVIDED_BY_6903",
        wsce_formula="SUM(COUNT_B_TIMES_CALIBRATION_ERROR_B_SQUARED)_DIVIDED_BY_6903",
        comparison_direction="SUCCESSOR_MINUS_ELO_NEGATIVE_IS_LOWER",
    )


def _fatigue_spec() -> FatigueAnalysisSpec:
    return FatigueAnalysisSpec(
        ablation_id="NO_FATIGUE_ABLATION",
        full_predictors=("intercept", "home_elo", "away_elo", "home_form", "away_form", "fatigue"),
        ablation_predictors=("intercept", "home_elo", "away_elo", "home_form", "away_form"),
        train_seasons=("2020-21", "2021-22", "2022-23", "2023-24"),
        evaluation_seasons=EVALUATION_SEASONS,
        solver_parity="PR72_PR73_FROZEN_POISSON_GLM_NEWTON_LINE_SEARCH_CONVERGENCE_AND_ROUNDING",
        leave_one_training_seasons=("2020-21", "2021-22", "2022-23", "2023-24"),
        fatigue_semantics=FATIGUE_SEMANTICS,
        fatigue_pr31_semantic_equivalence=FATIGUE_PR31_SEMANTIC_EQUIVALENCE,
        retained_predictor_transforms=(
            "intercept=CONSTANT_ONE",
            "home_elo=(VALUE_MINUS_1500_0)_DIVIDED_BY_400_0",
            "away_elo=(VALUE_MINUS_1500_0)_DIVIDED_BY_400_0",
            "home_form=VALUE_MINUS_0_5",
            "away_form=VALUE_MINUS_0_5",
        ),
    )


def successor_robustness_protocol(*, receipt_bytes: bytes) -> HistoricalExpectedGoalsSuccessorRobustnessProtocol:
    """Build the result-free protocol from exact canonical PR74 receipt bytes."""

    _validated_pr74_receipt(receipt_bytes)
    return HistoricalExpectedGoalsSuccessorRobustnessProtocol(
        schema_version=SCHEMA_VERSION,
        protocol_id=PROTOCOL_ID,
        scope=PROTOCOL_SCOPE,
        pr74_receipt_sha256=PR74_RECEIPT_SHA256,
        successor_candidate_sha256=SUCCESSOR_CANDIDATE_SHA256,
        successor_candidate_size=SUCCESSOR_CANDIDATE_SIZE,
        source_corpus_sha256=PR69_SOURCE_CORPUS_SHA256,
        evaluation_fixture_count=EVALUATION_FIXTURE_COUNT,
        evaluation_seasons=EVALUATION_SEASONS,
        identity_leagues=IDENTITY_LEAGUES,
        paired_nll=_paired_nll_spec(),
        leave_one_league_out="OMIT_ONE_IDENTITY_LEAGUE_ACROSS_BOTH_EVALUATION_SEASONS_FIXTURE_WEIGHTED_MEAN",
        leave_one_season_out="OMIT_ONE_EVALUATION_SEASON_FIXTURE_WEIGHTED_MEAN",
        calibration=_calibration_spec(),
        fatigue=_fatigue_spec(),
        interpretation_fields=(
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
        ),
        safety=_default_safety(),
    )


def canonical_successor_robustness_protocol_bytes(
    protocol: HistoricalExpectedGoalsSuccessorRobustnessProtocol,
) -> bytes:
    if type(protocol) is not HistoricalExpectedGoalsSuccessorRobustnessProtocol:
        raise _error("protocol must be exact HistoricalExpectedGoalsSuccessorRobustnessProtocol")
    # Reconstruct exact nested values so frozen-object mutation cannot bypass checks.
    HistoricalExpectedGoalsSuccessorRobustnessProtocol(
        **{
            **protocol.__dict__,
            "paired_nll": PairedNllRobustnessSpec(**protocol.paired_nll.__dict__),
            "calibration": CalibrationSpec(**protocol.calibration.__dict__),
            "fatigue": FatigueAnalysisSpec(**protocol.fatigue.__dict__),
        }
    )
    return _canonical_json_bytes(protocol.to_dict())


def sha256_successor_robustness_protocol(
    protocol: HistoricalExpectedGoalsSuccessorRobustnessProtocol,
) -> str:
    return _sha256(canonical_successor_robustness_protocol_bytes(protocol))


def revalidate_successor_robustness_protocol(
    *,
    receipt_bytes: bytes,
    protocol: HistoricalExpectedGoalsSuccessorRobustnessProtocol,
    protocol_bytes: bytes,
) -> HistoricalExpectedGoalsSuccessorRobustnessProtocol:
    """Rebuild the result-free protocol and require exact object/byte parity."""

    if type(protocol_bytes) is not bytes or not protocol_bytes:
        raise _error("protocol_bytes must be exact non-empty immutable bytes")
    rebuilt = successor_robustness_protocol(receipt_bytes=receipt_bytes)
    if protocol != rebuilt:
        raise _error("robustness protocol object does not match deterministic rebuild")
    expected = canonical_successor_robustness_protocol_bytes(rebuilt)
    if protocol_bytes != expected:
        raise _error("robustness protocol canonical bytes mismatch")
    return rebuilt
