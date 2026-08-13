"""Frozen research-only protocol for ATHENA's successor expected-goals model.

The protocol is intentionally committed before any successor coefficients are fit.
It accepts only the exact canonical PR #71 real-corpus validation receipt bytes,
binds the reviewed PR69/PR70 ancestry, freezes the feature transforms, chronological
split, deterministic fitting algorithm, and evaluation contract, and authorizes
nothing downstream.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import types
from collections.abc import Mapping
from typing import Any

from domain.fixture_model_features import ModelFeatureId


SCHEMA_VERSION = 1
PROTOCOL_ID = "HISTORICAL_EXPECTED_GOALS_SUCCESSOR_PROTOCOL_V1"
PROTOCOL_SCOPE = "RETROSPECTIVE_CHRONOLOGICAL_RESEARCH_PROTOCOL_ONLY"
MODEL_FAMILY = "INDEPENDENT_POISSON_LOG_LINK_TWO_RESPONSE_GLM_V1"
EVALUATION_LABEL = "RETROSPECTIVE_CHRONOLOGICAL_EVALUATION_NOT_UNTOUCHED_HOLDOUT"

PR71_RECEIPT_DATASET_NAME = (
    "athena-historical-expected-goals-real-corpus-validation-receipt-v1"
)
PR71_RECEIPT_SCOPE = "RETROSPECTIVE_REAL_CORPUS_EXECUTION_RECEIPT_RESEARCH_ONLY"
PR71_RECEIPT_SHA256 = "9680b108ac308df5f9d58f18ddacbb8ce1cda8e8806232519d4d327aea2d6da0"
PR69_SOURCE_CORPUS_SHA256 = "c273b4bff2b611e95248133340ff84803ce238814d5dfa7ded5f39fd3d6e25a0"
PR69_CANONICAL_SHA256 = "b44166b9543a8f436e62a644efc5316ad12fcc260a4c2c5908ad112928bedfe3"
PR70_VALIDATION_SHA256 = "c13287a28ac1ffc1bfc02b1ea283c34840a7a00eb14ec13cac39ca67c14ab5e5"
PR68_TRANSFORM_ID = "LEGACY_MATCH_ANALYST_POISSON_RATE_HEURISTIC_V1"
PR68_TRANSFORM_SPEC_SHA256 = "e7a5959eef21be51a45e79da1aa174b164504223ed45774d32b23eb073b3716c"
PR70_VALIDATION_SPEC_SHA256 = "3e4380fa5456e212bbdc422d0b1310ba8a8daf792a38666796f349e096378ce1"

SOURCE_FILE_COUNT = 66
SOURCE_TOTAL_BYTES = 10_006_877
SOURCE_FIXTURE_COUNT = 21_226

TRAIN_SEASONS = ("2020-21", "2021-22", "2022-23", "2023-24")
EVALUATION_SEASONS = ("2024-25", "2025-26")

CALIBRATION_BINS = (
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
        "successor_protocol_approved",
        "successor_model_trained",
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


class HistoricalExpectedGoalsSuccessorProtocolError(ValueError):
    """Raised when the frozen successor research protocol cannot be established."""


def _error(message: str) -> HistoricalExpectedGoalsSuccessorProtocolError:
    return HistoricalExpectedGoalsSuccessorProtocolError(message)


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("successor protocol serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _exact_text(value: Any, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise _error(f"{label} must be a non-empty exact trimmed string")
    return value


def _finite_number(value: Any, label: str) -> float | int:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise _error(f"{label} must be a finite exact numeric value")
    return value


def _default_safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise _error("safety keys mismatch")
    if any(type(flag) is not bool or flag is not False for flag in value.values()):
        raise _error("all successor protocol safety values must be exact bool False")
    return _default_safety()


def _require_path(payload: Mapping[str, Any], *keys: str) -> Any:
    value: Any = payload
    for key in keys:
        if not isinstance(value, Mapping) or key not in value:
            raise _error("PR71 receipt is missing required lineage data")
        value = value[key]
    return value


def _validated_pr71_receipt(receipt_bytes: bytes) -> Mapping[str, Any]:
    if type(receipt_bytes) is not bytes or not receipt_bytes:
        raise _error("receipt_bytes must be exact non-empty immutable bytes")
    if _sha256(receipt_bytes) != PR71_RECEIPT_SHA256:
        raise _error("PR71 receipt SHA-256 mismatch")
    try:
        decoded = receipt_bytes.decode("utf-8")
        payload = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error("PR71 receipt must be valid canonical UTF-8 JSON") from exc
    if not isinstance(payload, Mapping):
        raise _error("PR71 receipt must be a JSON object")
    if _canonical_json_bytes(payload) != receipt_bytes:
        raise _error("PR71 receipt bytes are not exact canonical JSON")

    exact_expectations = {
        ("dataset_name",): PR71_RECEIPT_DATASET_NAME,
        ("scope",): PR71_RECEIPT_SCOPE,
        ("source", "source_file_count"): SOURCE_FILE_COUNT,
        ("source", "source_total_bytes"): SOURCE_TOTAL_BYTES,
        ("source", "fixture_count"): SOURCE_FIXTURE_COUNT,
        ("source", "source_corpus_sha256"): PR69_SOURCE_CORPUS_SHA256,
        ("source", "pr69_canonical_sha256"): PR69_CANONICAL_SHA256,
        ("validation", "pr70_validation_sha256"): PR70_VALIDATION_SHA256,
        ("validation", "target_pr68_transform_id"): PR68_TRANSFORM_ID,
        ("validation", "target_pr68_transform_spec_sha256"): PR68_TRANSFORM_SPEC_SHA256,
        ("validation", "validation_spec_sha256"): PR70_VALIDATION_SPEC_SHA256,
        ("validation", "historical_freshness_regime_reconstructed"): False,
        ("execution", "source_receipt_matched_pr69"): True,
        ("execution", "pr69_revalidator_succeeded"): True,
        ("execution", "pr70_revalidator_succeeded"): True,
    }
    for path, expected in exact_expectations.items():
        if _require_path(payload, *path) != expected:
            raise _error("PR71 receipt lineage/content mismatch")

    safety = _require_path(payload, "safety")
    if not isinstance(safety, Mapping) or not safety:
        raise _error("PR71 receipt safety mapping is missing")
    if any(type(flag) is not bool or flag is not False for flag in safety.values()):
        raise _error("PR71 receipt must retain every recorded authorization as false")
    return types.MappingProxyType(dict(payload))


@dataclasses.dataclass(frozen=True)
class SuccessorPredictorSpec:
    name: str
    source_feature_id: str | None
    transform: str
    center: float | None
    scale: float | None

    def __post_init__(self) -> None:
        _exact_text(self.name, "predictor name")
        _exact_text(self.transform, "predictor transform")
        if self.source_feature_id is None:
            if self.name != "intercept" or self.center is not None or self.scale is not None:
                raise _error("only intercept may omit a source feature")
            return
        valid_feature_ids = {item.value for item in ModelFeatureId}
        if self.source_feature_id not in valid_feature_ids:
            raise _error("predictor source_feature_id must be an exact ModelFeatureId value")
        if self.center is not None:
            _finite_number(self.center, "predictor center")
        if self.scale is not None:
            _finite_number(self.scale, "predictor scale")
            if self.scale <= 0:
                raise _error("predictor scale must be positive")

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class SuccessorFittingSpec:
    algorithm: str
    objective: str
    regularization: str
    response_fit_order: tuple[str, ...]
    initial_intercept: str
    initial_non_intercept_coefficient: float
    max_iterations: int
    gradient_inf_norm_tolerance: float
    backtracking_factor: float
    minimum_step: float
    maximum_abs_linear_predictor: float
    linear_solve_pivot_tolerance: float
    coefficient_rounding_places: int
    hyperparameter_search_authorized: bool
    refit_after_evaluation_authorized: bool

    def __post_init__(self) -> None:
        for field in ("algorithm", "objective", "regularization", "initial_intercept"):
            _exact_text(getattr(self, field), field)
        if self.response_fit_order != ("HOME_GOALS", "AWAY_GOALS"):
            raise _error("response fit order is frozen")
        _finite_number(self.initial_non_intercept_coefficient, "initial coefficient")
        if self.initial_non_intercept_coefficient != 0.0:
            raise _error("non-intercept coefficients must initialize at exact zero")
        if type(self.max_iterations) is not int or self.max_iterations != 200:
            raise _error("max_iterations is frozen at 200")
        for field in (
            "gradient_inf_norm_tolerance",
            "backtracking_factor",
            "minimum_step",
            "maximum_abs_linear_predictor",
            "linear_solve_pivot_tolerance",
        ):
            _finite_number(getattr(self, field), field)
        if not (0.0 < self.gradient_inf_norm_tolerance < 1.0):
            raise _error("invalid gradient tolerance")
        if not (0.0 < self.backtracking_factor < 1.0):
            raise _error("invalid backtracking factor")
        if not (0.0 < self.minimum_step < 1.0):
            raise _error("invalid minimum step")
        if self.maximum_abs_linear_predictor <= 0.0:
            raise _error("maximum linear predictor guard must be positive")
        if self.linear_solve_pivot_tolerance <= 0.0:
            raise _error("pivot tolerance must be positive")
        if type(self.coefficient_rounding_places) is not int or self.coefficient_rounding_places != 12:
            raise _error("coefficient rounding is frozen at 12 places")
        if self.hyperparameter_search_authorized is not False:
            raise _error("hyperparameter search is not authorized")
        if self.refit_after_evaluation_authorized is not False:
            raise _error("post-evaluation refit is not authorized")

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class SuccessorEvaluationSpec:
    primary_metric: str
    legacy_comparators: tuple[str, ...]
    breakdowns: tuple[str, ...]
    calibration_bins: tuple[tuple[float, float | None], ...]
    descriptive_metrics: tuple[str, ...]
    approval_threshold: None
    production_decision: str

    def __post_init__(self) -> None:
        _exact_text(self.primary_metric, "primary metric")
        if self.legacy_comparators != (
            "PR68_FORM_COMPONENT",
            "PR68_ELO_FALLBACK_COMPONENT",
            "PR68_FROZEN_CONSTANT_BASELINE",
            "STRICT_PREMATCH_ROLLING_IDENTITY_LEAGUE_BASELINE",
        ):
            raise _error("legacy comparator set/order is frozen")
        if self.breakdowns != ("SEASON", "IDENTITY_LEAGUE"):
            raise _error("evaluation breakdowns are frozen")
        if self.calibration_bins != CALIBRATION_BINS:
            raise _error("calibration bins must retain PR70 boundaries")
        if self.descriptive_metrics != (
            "MEAN_PREDICTED_HOME_GOALS",
            "MEAN_ACTUAL_HOME_GOALS",
            "HOME_BIAS",
            "MEAN_PREDICTED_AWAY_GOALS",
            "MEAN_ACTUAL_AWAY_GOALS",
            "AWAY_BIAS",
            "HOME_MAE",
            "AWAY_MAE",
            "HOME_RMSE",
            "AWAY_RMSE",
        ):
            raise _error("descriptive metrics are frozen")
        if self.approval_threshold is not None:
            raise _error("no approval threshold may be encoded")
        if self.production_decision != "REPORT_ONLY_NO_AUTOMATIC_APPROVAL":
            raise _error("evaluation may report evidence only")

    def to_dict(self) -> dict[str, Any]:
        result = dataclasses.asdict(self)
        result["calibration_bins"] = [list(item) for item in self.calibration_bins]
        return result


@dataclasses.dataclass(frozen=True)
class HistoricalExpectedGoalsSuccessorProtocol:
    schema_version: int
    protocol_id: str
    scope: str
    evidence_receipt_sha256: str
    source_corpus_sha256: str
    pr69_canonical_sha256: str
    pr70_validation_sha256: str
    target_legacy_transform_id: str
    target_legacy_transform_spec_sha256: str
    model_family: str
    response_distribution: str
    link_function: str
    coefficient_sharing: str
    eligibility_rule: str
    predictors: tuple[SuccessorPredictorSpec, ...]
    train_seasons: tuple[str, ...]
    evaluation_seasons: tuple[str, ...]
    evaluation_label: str
    fitting: SuccessorFittingSpec
    evaluation: SuccessorEvaluationSpec
    prospective_requirement: str
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise _error("schema_version must be exact int 1")
        if self.protocol_id != PROTOCOL_ID or self.scope != PROTOCOL_SCOPE:
            raise _error("successor protocol identity mismatch")
        if self.evidence_receipt_sha256 != PR71_RECEIPT_SHA256:
            raise _error("successor protocol must bind exact PR71 receipt")
        if self.source_corpus_sha256 != PR69_SOURCE_CORPUS_SHA256:
            raise _error("source corpus lineage mismatch")
        if self.pr69_canonical_sha256 != PR69_CANONICAL_SHA256:
            raise _error("PR69 canonical lineage mismatch")
        if self.pr70_validation_sha256 != PR70_VALIDATION_SHA256:
            raise _error("PR70 validation lineage mismatch")
        if self.target_legacy_transform_id != PR68_TRANSFORM_ID:
            raise _error("legacy transform identity mismatch")
        if self.target_legacy_transform_spec_sha256 != PR68_TRANSFORM_SPEC_SHA256:
            raise _error("legacy transform specification mismatch")
        if self.model_family != MODEL_FAMILY:
            raise _error("model family mismatch")
        if self.response_distribution != "POISSON" or self.link_function != "LOG":
            raise _error("successor distribution/link are frozen")
        if self.coefficient_sharing != "NONE_HOME_AND_AWAY_FIT_SEPARATELY":
            raise _error("home and away coefficient sharing is forbidden")
        if self.eligibility_rule != "PR69_FORM_PATH_COMPONENT_ELIGIBLE_AND_ELO_FALLBACK_COMPONENT_ELIGIBLE":
            raise _error("successor eligibility rule is frozen")
        if type(self.predictors) is not tuple or len(self.predictors) != 6:
            raise _error("successor predictor set must contain six frozen predictors")
        if self.predictors != _predictors():
            raise _error("successor predictor specification is frozen exactly")
        if self.train_seasons != TRAIN_SEASONS or self.evaluation_seasons != EVALUATION_SEASONS:
            raise _error("chronological season split is frozen")
        if set(self.train_seasons) & set(self.evaluation_seasons):
            raise _error("training and evaluation seasons must be disjoint")
        if self.evaluation_label != EVALUATION_LABEL:
            raise _error("evaluation label must explicitly reject untouched-holdout claim")
        if type(self.fitting) is not SuccessorFittingSpec or self.fitting != _fitting_spec():
            raise _error("fitting specification is frozen exactly")
        if type(self.evaluation) is not SuccessorEvaluationSpec or self.evaluation != _evaluation_spec():
            raise _error("evaluation specification is frozen exactly")
        if self.prospective_requirement != (
            "PRODUCTION_APPROVAL_REQUIRES_FUTURE_NOT_YET_OBSERVED_EVIDENCE_AFTER_PROTOCOL_FREEZE"
        ):
            raise _error("prospective production requirement must remain explicit")
        object.__setattr__(self, "safety", _validate_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "protocol_id": self.protocol_id,
            "scope": self.scope,
            "evidence_receipt_sha256": self.evidence_receipt_sha256,
            "source_corpus_sha256": self.source_corpus_sha256,
            "pr69_canonical_sha256": self.pr69_canonical_sha256,
            "pr70_validation_sha256": self.pr70_validation_sha256,
            "target_legacy_transform_id": self.target_legacy_transform_id,
            "target_legacy_transform_spec_sha256": self.target_legacy_transform_spec_sha256,
            "model_family": self.model_family,
            "response_distribution": self.response_distribution,
            "link_function": self.link_function,
            "coefficient_sharing": self.coefficient_sharing,
            "eligibility_rule": self.eligibility_rule,
            "predictors": [item.to_dict() for item in self.predictors],
            "train_seasons": list(self.train_seasons),
            "evaluation_seasons": list(self.evaluation_seasons),
            "evaluation_label": self.evaluation_label,
            "fitting": self.fitting.to_dict(),
            "evaluation": self.evaluation.to_dict(),
            "prospective_requirement": self.prospective_requirement,
            "safety": dict(self.safety),
        }


def _predictors() -> tuple[SuccessorPredictorSpec, ...]:
    return (
        SuccessorPredictorSpec("intercept", None, "CONSTANT_ONE", None, None),
        SuccessorPredictorSpec(
            "home_elo_centered_scaled",
            ModelFeatureId.HOME_ELO.value,
            "(VALUE_MINUS_CENTER)_DIVIDED_BY_SCALE",
            1500.0,
            400.0,
        ),
        SuccessorPredictorSpec(
            "away_elo_centered_scaled",
            ModelFeatureId.AWAY_ELO.value,
            "(VALUE_MINUS_CENTER)_DIVIDED_BY_SCALE",
            1500.0,
            400.0,
        ),
        SuccessorPredictorSpec(
            "home_form_centered",
            ModelFeatureId.HOME_FORM.value,
            "VALUE_MINUS_CENTER",
            0.5,
            None,
        ),
        SuccessorPredictorSpec(
            "away_form_centered",
            ModelFeatureId.AWAY_FORM.value,
            "VALUE_MINUS_CENTER",
            0.5,
            None,
        ),
        SuccessorPredictorSpec(
            "fatigue_raw",
            ModelFeatureId.FATIGUE.value,
            "IDENTITY",
            None,
            None,
        ),
    )


def _fitting_spec() -> SuccessorFittingSpec:
    return SuccessorFittingSpec(
        algorithm="DETERMINISTIC_NEWTON_POISSON_GLM_WITH_BACKTRACKING_V1",
        objective="SUM_INDEPENDENT_POISSON_NEGATIVE_LOG_LIKELIHOOD",
        regularization="NONE",
        response_fit_order=("HOME_GOALS", "AWAY_GOALS"),
        initial_intercept="LOG_TRAINING_RESPONSE_MEAN",
        initial_non_intercept_coefficient=0.0,
        max_iterations=200,
        gradient_inf_norm_tolerance=1e-8,
        backtracking_factor=0.5,
        minimum_step=2.0 ** -20,
        maximum_abs_linear_predictor=20.0,
        linear_solve_pivot_tolerance=1e-12,
        coefficient_rounding_places=12,
        hyperparameter_search_authorized=False,
        refit_after_evaluation_authorized=False,
    )


def _evaluation_spec() -> SuccessorEvaluationSpec:
    return SuccessorEvaluationSpec(
        primary_metric="MEAN_JOINT_POISSON_NEGATIVE_LOG_LIKELIHOOD",
        legacy_comparators=(
            "PR68_FORM_COMPONENT",
            "PR68_ELO_FALLBACK_COMPONENT",
            "PR68_FROZEN_CONSTANT_BASELINE",
            "STRICT_PREMATCH_ROLLING_IDENTITY_LEAGUE_BASELINE",
        ),
        breakdowns=("SEASON", "IDENTITY_LEAGUE"),
        calibration_bins=CALIBRATION_BINS,
        descriptive_metrics=(
            "MEAN_PREDICTED_HOME_GOALS",
            "MEAN_ACTUAL_HOME_GOALS",
            "HOME_BIAS",
            "MEAN_PREDICTED_AWAY_GOALS",
            "MEAN_ACTUAL_AWAY_GOALS",
            "AWAY_BIAS",
            "HOME_MAE",
            "AWAY_MAE",
            "HOME_RMSE",
            "AWAY_RMSE",
        ),
        approval_threshold=None,
        production_decision="REPORT_ONLY_NO_AUTOMATIC_APPROVAL",
    )


def build_historical_expected_goals_successor_protocol(
    *, receipt_bytes: bytes
) -> HistoricalExpectedGoalsSuccessorProtocol:
    """Build the frozen protocol only from the exact canonical PR71 receipt."""

    _validated_pr71_receipt(receipt_bytes)
    return HistoricalExpectedGoalsSuccessorProtocol(
        schema_version=SCHEMA_VERSION,
        protocol_id=PROTOCOL_ID,
        scope=PROTOCOL_SCOPE,
        evidence_receipt_sha256=PR71_RECEIPT_SHA256,
        source_corpus_sha256=PR69_SOURCE_CORPUS_SHA256,
        pr69_canonical_sha256=PR69_CANONICAL_SHA256,
        pr70_validation_sha256=PR70_VALIDATION_SHA256,
        target_legacy_transform_id=PR68_TRANSFORM_ID,
        target_legacy_transform_spec_sha256=PR68_TRANSFORM_SPEC_SHA256,
        model_family=MODEL_FAMILY,
        response_distribution="POISSON",
        link_function="LOG",
        coefficient_sharing="NONE_HOME_AND_AWAY_FIT_SEPARATELY",
        eligibility_rule="PR69_FORM_PATH_COMPONENT_ELIGIBLE_AND_ELO_FALLBACK_COMPONENT_ELIGIBLE",
        predictors=_predictors(),
        train_seasons=TRAIN_SEASONS,
        evaluation_seasons=EVALUATION_SEASONS,
        evaluation_label=EVALUATION_LABEL,
        fitting=_fitting_spec(),
        evaluation=_evaluation_spec(),
        prospective_requirement=(
            "PRODUCTION_APPROVAL_REQUIRES_FUTURE_NOT_YET_OBSERVED_EVIDENCE_AFTER_PROTOCOL_FREEZE"
        ),
        safety=_default_safety(),
    )


def canonical_historical_expected_goals_successor_protocol_bytes(
    protocol: HistoricalExpectedGoalsSuccessorProtocol,
) -> bytes:
    if type(protocol) is not HistoricalExpectedGoalsSuccessorProtocol:
        raise _error("protocol must be exact HistoricalExpectedGoalsSuccessorProtocol")
    return _canonical_json_bytes(protocol.to_dict())


def sha256_historical_expected_goals_successor_protocol(
    protocol: HistoricalExpectedGoalsSuccessorProtocol,
) -> str:
    return _sha256(canonical_historical_expected_goals_successor_protocol_bytes(protocol))


def revalidate_historical_expected_goals_successor_protocol(
    *,
    receipt_bytes: bytes,
    protocol: HistoricalExpectedGoalsSuccessorProtocol,
    protocol_bytes: bytes,
) -> None:
    """Rebuild the complete frozen protocol and require exact object/byte parity."""

    if type(protocol_bytes) is not bytes or not protocol_bytes:
        raise _error("protocol_bytes must be exact non-empty immutable bytes")
    rebuilt = build_historical_expected_goals_successor_protocol(receipt_bytes=receipt_bytes)
    if protocol != rebuilt:
        raise _error("successor protocol object does not match deterministic rebuild")
    expected_bytes = canonical_historical_expected_goals_successor_protocol_bytes(rebuilt)
    if protocol_bytes != expected_bytes:
        raise _error("successor protocol canonical bytes mismatch")
