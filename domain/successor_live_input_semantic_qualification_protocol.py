"""Pre-registered semantic qualification protocol for successor live inputs.

This module is deliberately result-free. It freezes the exact historical raw
feature meanings and successor transforms that a later evaluator must prove
against current/live PR31 model features. It performs no acquisition, feature
qualification execution, expected-goals inference, probability inference,
pricing, selection, or betting.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import math
import types
from collections.abc import Mapping
from typing import Any


SCHEMA_VERSION = 1
PROTOCOL_ID = "SUCCESSOR_LIVE_INPUT_SEMANTIC_QUALIFICATION_PROTOCOL_V1"
PROTOCOL_SCOPE = "PRE_REGISTERED_LIVE_TO_HISTORICAL_SUCCESSOR_SEMANTIC_QUALIFICATION_ONLY"
NO_RESULT_STATE = "PRE_REGISTERED_NOT_EXECUTED_NO_FEATURE_QUALIFIED"

PR77_MAIN_SHA = "0bca6d1bc5f156079ecdcea696a7035dc7f4fb0e"
PR31_FIXTURE_MODEL_FEATURES_BLOB_SHA = "e8d9ebf04676b54826b71752eae5aa5d23cb6caa"
PR66_MODEL_FEATURE_HANDOFF_BLOB_SHA = "e7b9adccdde32555ff1f70f1dfa37409165255f8"
PR69_HISTORICAL_REPLAY_BLOB_SHA = "b67a7e52954f47cc90c578ad193545c541984964"
PR72_SUCCESSOR_PROTOCOL_BLOB_SHA = "f0b3a070bcf235a097dd737d715f9d6162505509"
SUCCESSOR_CANDIDATE_SHA256 = "1fe9ff5f0963355bb98ae93d205a5ea3cb9aa53592601a7b06ff4000f6091660"
PR77_ROBUSTNESS_RECEIPT_SHA256 = "db90e0cbb1452a3267c346a190d5936d3576f20a935798e7a2b66e6c5f5c5b14"

ELO_INITIALIZATION_SEMANTICS = (
    "1500_REPLAY_INITIAL_STATE_ASSUMPTION_NOT_OBSERVED_EVIDENCE"
)
FATIGUE_PR31_SEMANTIC_EQUIVALENCE = "UNPROVEN"
LIVE_DATA_FRESHNESS_ROLE = (
    "PR31_FEATURE_NOT_SUCCESSOR_PREDICTOR_NOT_SEMANTIC_QUALIFICATION_CONDITION"
)
AGGREGATE_ROLE = (
    "SEMANTIC_COMPATIBILITY_ONLY_ALL_FIVE_RAW_INPUTS_MUST_BE_EXACTLY_QUALIFIED;"
    "NEVER_MODEL_OR_PRODUCTION_AUTHORIZATION"
)

_SUCCESSOR_RAW_FEATURE_IDS = (
    "home_elo",
    "away_elo",
    "home_form",
    "away_form",
    "fatigue",
)
_PR31_FEATURE_IDS = tuple(sorted(_SUCCESSOR_RAW_FEATURE_IDS + ("live_data_freshness",)))

_SAFETY_KEYS = frozenset(
    {
        "live_semantic_qualification_executed",
        "successor_live_inputs_qualified",
        "successor_candidate_approved",
        "expected_goals_transform_approved",
        "expected_goals_production_authorized",
        "score_matrix_authorized",
        "probability_inference_authorized",
        "probability_adjustment_authorized",
        "calibration_for_production_authorized",
        "pricing_authorized",
        "market_activation_authorized",
        "selection_authorized",
        "production_approval_authorized",
        "bet_authorized",
    }
)


class SuccessorLiveInputSemanticQualificationProtocolError(ValueError):
    """Raised when the pre-registered semantic protocol is altered or invalid."""


def _error(message: str) -> SuccessorLiveInputSemanticQualificationProtocolError:
    return SuccessorLiveInputSemanticQualificationProtocolError(message)


def _exact_text(value: Any, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise _error(f"{label} must be a non-empty exact trimmed string")
    return value


def _finite_number(value: Any, label: str) -> float | int:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise _error(f"{label} must be a finite exact numeric value")
    return value


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
        raise _error("semantic qualification protocol serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _default_safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise _error("semantic qualification safety keys mismatch")
    if any(type(flag) is not bool or flag is not False for flag in value.values()):
        raise _error("all semantic qualification safety values must be exact bool False")
    return _default_safety()


class SemanticQualificationStatus(str, enum.Enum):
    QUALIFIED_EXACT_SEMANTIC_EQUIVALENCE = "QUALIFIED_EXACT_SEMANTIC_EQUIVALENCE"
    UNQUALIFIED_INSUFFICIENT_PROVENANCE = "UNQUALIFIED_INSUFFICIENT_PROVENANCE"
    UNQUALIFIED_DEFINITION_MISMATCH = "UNQUALIFIED_DEFINITION_MISMATCH"
    BLOCKED_SOURCE_FEATURE_UNAVAILABLE = "BLOCKED_SOURCE_FEATURE_UNAVAILABLE"


@dataclasses.dataclass(frozen=True)
class AncestrySpec:
    repository_main_sha: str
    pr31_fixture_model_features_blob_sha: str
    pr66_model_feature_handoff_blob_sha: str
    pr69_historical_replay_blob_sha: str
    pr72_successor_protocol_blob_sha: str
    successor_candidate_sha256: str
    pr77_robustness_receipt_sha256: str

    def __post_init__(self) -> None:
        expected = _ancestry()
        if self != expected:
            raise _error("semantic qualification ancestry is frozen exactly")

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


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
            if self.name != "intercept" or self.transform != "CONSTANT_ONE":
                raise _error("only the frozen intercept may omit a source feature")
            if self.center is not None or self.scale is not None:
                raise _error("intercept cannot have center or scale")
            return
        if self.source_feature_id not in _SUCCESSOR_RAW_FEATURE_IDS:
            raise _error("predictor source_feature_id is not a frozen successor raw input")
        if self.center is not None:
            _finite_number(self.center, "predictor center")
        if self.scale is not None:
            _finite_number(self.scale, "predictor scale")
            if self.scale <= 0:
                raise _error("predictor scale must be positive")

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class HistoricalFormSemantics:
    chronology: str
    window_size: int
    win_points: int
    draw_points: int
    loss_points: int
    base: float
    span: float
    rounding_places: int
    formula: str
    missing_history_behavior: str

    def __post_init__(self) -> None:
        if self != _form_semantics():
            raise _error("historical form semantics are frozen exactly")

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class HistoricalFatigueSemantics:
    chronology: str
    orientation: str
    severe_threshold_days_exclusive: int
    mild_threshold_days_exclusive: int
    severe_value: float
    mild_value: float
    neutral_value: float
    missing_history_behavior: str
    exact_formula: str

    def __post_init__(self) -> None:
        if self != _fatigue_semantics():
            raise _error("historical fatigue semantics are frozen exactly")

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class HistoricalEloSemantics:
    chronology: str
    initial_overall_rating: int
    home_advantage_points: int
    logistic_divisor: float
    observed_score_win: float
    observed_score_draw: float
    observed_score_loss: float
    k_schedule: tuple[tuple[int | None, int], ...]
    update_rule: str
    pre_match_feature_rule: str
    ambiguity_behavior: str
    initialization_semantics: str

    def __post_init__(self) -> None:
        if self != _elo_semantics():
            raise _error("historical Elo semantics are frozen exactly")

    def to_dict(self) -> dict[str, Any]:
        result = dataclasses.asdict(self)
        result["k_schedule"] = [list(item) for item in self.k_schedule]
        return result


@dataclasses.dataclass(frozen=True)
class EvidenceRequirementSpec:
    value_level_compatibility_required: bool
    derivation_provenance_compatibility_required: bool
    pr31_available_implies_qualified: bool
    equal_numeric_value_implies_qualified: bool
    qualification_requires_replayable_evidence_or_exact_reviewed_contract: bool
    insufficient_proofs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self != _evidence_requirements():
            raise _error("semantic evidence requirements are frozen exactly")

    def to_dict(self) -> dict[str, Any]:
        result = dataclasses.asdict(self)
        result["insufficient_proofs"] = list(self.insufficient_proofs)
        return result


@dataclasses.dataclass(frozen=True)
class SuccessorLiveInputSemanticQualificationProtocol:
    schema_version: int
    protocol_id: str
    scope: str
    ancestry: AncestrySpec
    pr31_feature_ids: tuple[str, ...]
    successor_raw_feature_ids: tuple[str, ...]
    predictors: tuple[SuccessorPredictorSpec, ...]
    live_data_freshness_role: str
    qualification_statuses: tuple[str, ...]
    form_semantics: HistoricalFormSemantics
    fatigue_semantics: HistoricalFatigueSemantics
    elo_semantics: HistoricalEloSemantics
    evidence_requirements: EvidenceRequirementSpec
    fatigue_pr31_semantic_equivalence: str
    aggregate_role: str
    no_result_state: str
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise _error("schema_version must be exact int 1")
        if self.protocol_id != PROTOCOL_ID or self.scope != PROTOCOL_SCOPE:
            raise _error("semantic qualification protocol identity mismatch")
        if type(self.ancestry) is not AncestrySpec or self.ancestry != _ancestry():
            raise _error("semantic qualification ancestry mismatch")
        if self.pr31_feature_ids != _PR31_FEATURE_IDS:
            raise _error("PR31 feature identity set/order is frozen")
        if self.successor_raw_feature_ids != _SUCCESSOR_RAW_FEATURE_IDS:
            raise _error("successor raw feature set/order is frozen")
        if type(self.predictors) is not tuple or self.predictors != _predictors():
            raise _error("successor predictor specification is frozen exactly")
        if any(item.source_feature_id == "live_data_freshness" for item in self.predictors):
            raise _error("live_data_freshness cannot be a successor predictor")
        if self.live_data_freshness_role != LIVE_DATA_FRESHNESS_ROLE:
            raise _error("live_data_freshness role is frozen")
        if self.qualification_statuses != tuple(item.value for item in SemanticQualificationStatus):
            raise _error("semantic qualification vocabulary is frozen")
        if type(self.form_semantics) is not HistoricalFormSemantics or self.form_semantics != _form_semantics():
            raise _error("historical form semantics mismatch")
        if type(self.fatigue_semantics) is not HistoricalFatigueSemantics or self.fatigue_semantics != _fatigue_semantics():
            raise _error("historical fatigue semantics mismatch")
        if type(self.elo_semantics) is not HistoricalEloSemantics or self.elo_semantics != _elo_semantics():
            raise _error("historical Elo semantics mismatch")
        if type(self.evidence_requirements) is not EvidenceRequirementSpec or self.evidence_requirements != _evidence_requirements():
            raise _error("semantic evidence requirements mismatch")
        if self.fatigue_pr31_semantic_equivalence != FATIGUE_PR31_SEMANTIC_EQUIVALENCE:
            raise _error("fatigue PR31 semantic equivalence must remain UNPROVEN")
        if self.aggregate_role != AGGREGATE_ROLE:
            raise _error("aggregate semantic compatibility role is frozen")
        if self.no_result_state != NO_RESULT_STATE:
            raise _error("protocol must remain pre-registered and result-free")
        object.__setattr__(self, "safety", _validate_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "protocol_id": self.protocol_id,
            "scope": self.scope,
            "ancestry": self.ancestry.to_dict(),
            "pr31_feature_ids": list(self.pr31_feature_ids),
            "successor_raw_feature_ids": list(self.successor_raw_feature_ids),
            "predictors": [item.to_dict() for item in self.predictors],
            "live_data_freshness_role": self.live_data_freshness_role,
            "qualification_statuses": list(self.qualification_statuses),
            "form_semantics": self.form_semantics.to_dict(),
            "fatigue_semantics": self.fatigue_semantics.to_dict(),
            "elo_semantics": self.elo_semantics.to_dict(),
            "evidence_requirements": self.evidence_requirements.to_dict(),
            "fatigue_pr31_semantic_equivalence": self.fatigue_pr31_semantic_equivalence,
            "aggregate_role": self.aggregate_role,
            "no_result_state": self.no_result_state,
            "safety": dict(self.safety),
        }


def _ancestry() -> AncestrySpec:
    # Bypass __post_init__ recursion only for constructing the immutable reference.
    value = object.__new__(AncestrySpec)
    object.__setattr__(value, "repository_main_sha", PR77_MAIN_SHA)
    object.__setattr__(value, "pr31_fixture_model_features_blob_sha", PR31_FIXTURE_MODEL_FEATURES_BLOB_SHA)
    object.__setattr__(value, "pr66_model_feature_handoff_blob_sha", PR66_MODEL_FEATURE_HANDOFF_BLOB_SHA)
    object.__setattr__(value, "pr69_historical_replay_blob_sha", PR69_HISTORICAL_REPLAY_BLOB_SHA)
    object.__setattr__(value, "pr72_successor_protocol_blob_sha", PR72_SUCCESSOR_PROTOCOL_BLOB_SHA)
    object.__setattr__(value, "successor_candidate_sha256", SUCCESSOR_CANDIDATE_SHA256)
    object.__setattr__(value, "pr77_robustness_receipt_sha256", PR77_ROBUSTNESS_RECEIPT_SHA256)
    return value


def _predictors() -> tuple[SuccessorPredictorSpec, ...]:
    return (
        SuccessorPredictorSpec("intercept", None, "CONSTANT_ONE", None, None),
        SuccessorPredictorSpec("home_elo_centered_scaled", "home_elo", "(VALUE_MINUS_CENTER)_DIVIDED_BY_SCALE", 1500.0, 400.0),
        SuccessorPredictorSpec("away_elo_centered_scaled", "away_elo", "(VALUE_MINUS_CENTER)_DIVIDED_BY_SCALE", 1500.0, 400.0),
        SuccessorPredictorSpec("home_form_centered", "home_form", "VALUE_MINUS_CENTER", 0.5, None),
        SuccessorPredictorSpec("away_form_centered", "away_form", "VALUE_MINUS_CENTER", 0.5, None),
        SuccessorPredictorSpec("fatigue_raw", "fatigue", "IDENTITY", None, None),
    )


def _form_semantics() -> HistoricalFormSemantics:
    value = object.__new__(HistoricalFormSemantics)
    object.__setattr__(value, "chronology", "STRICTLY_PRIOR_FIXTURES_ORDERED_KICKOFF_DESCENDING")
    object.__setattr__(value, "window_size", 5)
    object.__setattr__(value, "win_points", 3)
    object.__setattr__(value, "draw_points", 1)
    object.__setattr__(value, "loss_points", 0)
    object.__setattr__(value, "base", 0.10)
    object.__setattr__(value, "span", 0.85)
    object.__setattr__(value, "rounding_places", 3)
    object.__setattr__(value, "formula", "round(0.10+((points/(n*3))*0.85),3)")
    object.__setattr__(value, "missing_history_behavior", "MISSING_PRIOR_HISTORY_NO_DEFAULT")
    return value


def _fatigue_semantics() -> HistoricalFatigueSemantics:
    value = object.__new__(HistoricalFatigueSemantics)
    object.__setattr__(value, "chronology", "MOST_RECENT_STRICTLY_PRIOR_FIXTURE_PER_TEAM")
    object.__setattr__(value, "orientation", "HOME_REST_DAYS_MINUS_AWAY_REST_DAYS")
    object.__setattr__(value, "severe_threshold_days_exclusive", -2)
    object.__setattr__(value, "mild_threshold_days_exclusive", 0)
    object.__setattr__(value, "severe_value", 0.30)
    object.__setattr__(value, "mild_value", 0.10)
    object.__setattr__(value, "neutral_value", 0.0)
    object.__setattr__(value, "missing_history_behavior", "MISSING_PRIOR_HISTORY_NO_DEFAULT")
    object.__setattr__(value, "exact_formula", "0.30_IF_DIFFERENCE_LT_NEG2_ELSE_0.10_IF_DIFFERENCE_LT_0_ELSE_0.0")
    return value


def _elo_semantics() -> HistoricalEloSemantics:
    value = object.__new__(HistoricalEloSemantics)
    object.__setattr__(value, "chronology", "SOURCE_LOCAL_KICKOFF_ASC_PREMATCH_STATE_ONLY")
    object.__setattr__(value, "initial_overall_rating", 1500)
    object.__setattr__(value, "home_advantage_points", 50)
    object.__setattr__(value, "logistic_divisor", 400.0)
    object.__setattr__(value, "observed_score_win", 1.0)
    object.__setattr__(value, "observed_score_draw", 0.5)
    object.__setattr__(value, "observed_score_loss", 0.0)
    object.__setattr__(value, "k_schedule", ((20, 32), (50, 24), (None, 16)))
    object.__setattr__(value, "update_rule", "int(old_overall+K*(actual_score-expected_score))")
    object.__setattr__(value, "pre_match_feature_rule", "FEATURE_IS_CURRENT_OVERALL_RATING_BEFORE_TARGET_FIXTURE_UPDATE")
    object.__setattr__(value, "ambiguity_behavior", "TEMPORAL_OR_IDENTITY_AMBIGUITY_FAILS_CLOSED_AND_TAINTS_DEPENDENT_REPLAY")
    object.__setattr__(value, "initialization_semantics", ELO_INITIALIZATION_SEMANTICS)
    return value


def _evidence_requirements() -> EvidenceRequirementSpec:
    value = object.__new__(EvidenceRequirementSpec)
    object.__setattr__(value, "value_level_compatibility_required", True)
    object.__setattr__(value, "derivation_provenance_compatibility_required", True)
    object.__setattr__(value, "pr31_available_implies_qualified", False)
    object.__setattr__(value, "equal_numeric_value_implies_qualified", False)
    object.__setattr__(value, "qualification_requires_replayable_evidence_or_exact_reviewed_contract", True)
    object.__setattr__(value, "insufficient_proofs", (
        "SAME_FIELD_NAME",
        "SAME_NUMERIC_RANGE",
        "SAME_CURRENT_VALUE",
        "SAME_SOURCE_CATEGORY",
        "PR31_AVAILABLE_STATUS_ONLY",
        "ONE_HAND_CHECKED_FIXTURE",
        "DOCUMENTATION_CLAIM_WITHOUT_EXECUTABLE_LINEAGE",
        "PROVIDER_LABEL_ELO_ONLY",
        "FATIGUE_VALUE_MATCH_WITHOUT_DERIVATION_PROOF",
    ))
    return value


def build_successor_live_input_semantic_qualification_protocol() -> SuccessorLiveInputSemanticQualificationProtocol:
    """Build the immutable result-free pre-registration protocol."""

    return SuccessorLiveInputSemanticQualificationProtocol(
        schema_version=SCHEMA_VERSION,
        protocol_id=PROTOCOL_ID,
        scope=PROTOCOL_SCOPE,
        ancestry=_ancestry(),
        pr31_feature_ids=_PR31_FEATURE_IDS,
        successor_raw_feature_ids=_SUCCESSOR_RAW_FEATURE_IDS,
        predictors=_predictors(),
        live_data_freshness_role=LIVE_DATA_FRESHNESS_ROLE,
        qualification_statuses=tuple(item.value for item in SemanticQualificationStatus),
        form_semantics=_form_semantics(),
        fatigue_semantics=_fatigue_semantics(),
        elo_semantics=_elo_semantics(),
        evidence_requirements=_evidence_requirements(),
        fatigue_pr31_semantic_equivalence=FATIGUE_PR31_SEMANTIC_EQUIVALENCE,
        aggregate_role=AGGREGATE_ROLE,
        no_result_state=NO_RESULT_STATE,
        safety=_default_safety(),
    )


def successor_live_input_semantic_qualification_protocol_to_dict(value: Any) -> dict[str, Any]:
    if type(value) is not SuccessorLiveInputSemanticQualificationProtocol:
        raise _error("value must be exact SuccessorLiveInputSemanticQualificationProtocol")
    return value.to_dict()


def canonical_successor_live_input_semantic_qualification_protocol_bytes(value: Any) -> bytes:
    return _canonical_json_bytes(successor_live_input_semantic_qualification_protocol_to_dict(value))


def sha256_successor_live_input_semantic_qualification_protocol(value: Any) -> str:
    return _sha256(canonical_successor_live_input_semantic_qualification_protocol_bytes(value))


def revalidate_successor_live_input_semantic_qualification_protocol(
    *,
    protocol: SuccessorLiveInputSemanticQualificationProtocol,
    protocol_bytes: bytes,
) -> SuccessorLiveInputSemanticQualificationProtocol:
    if type(protocol) is not SuccessorLiveInputSemanticQualificationProtocol:
        raise _error("protocol must be exact SuccessorLiveInputSemanticQualificationProtocol")
    if type(protocol_bytes) is not bytes:
        raise _error("protocol_bytes must be exact immutable bytes")
    rebuilt = build_successor_live_input_semantic_qualification_protocol()
    expected = canonical_successor_live_input_semantic_qualification_protocol_bytes(rebuilt)
    supplied = canonical_successor_live_input_semantic_qualification_protocol_bytes(protocol)
    if supplied != expected:
        raise _error("protocol differs from exact frozen semantic qualification contract")
    if protocol_bytes != expected:
        raise _error("protocol_bytes are not exact canonical protocol bytes")
    return rebuilt


__all__ = [
    "AGGREGATE_ROLE",
    "ELO_INITIALIZATION_SEMANTICS",
    "FATIGUE_PR31_SEMANTIC_EQUIVALENCE",
    "LIVE_DATA_FRESHNESS_ROLE",
    "NO_RESULT_STATE",
    "PR31_FIXTURE_MODEL_FEATURES_BLOB_SHA",
    "PR66_MODEL_FEATURE_HANDOFF_BLOB_SHA",
    "PR69_HISTORICAL_REPLAY_BLOB_SHA",
    "PR72_SUCCESSOR_PROTOCOL_BLOB_SHA",
    "PR77_MAIN_SHA",
    "PR77_ROBUSTNESS_RECEIPT_SHA256",
    "PROTOCOL_ID",
    "PROTOCOL_SCOPE",
    "SCHEMA_VERSION",
    "SUCCESSOR_CANDIDATE_SHA256",
    "AncestrySpec",
    "EvidenceRequirementSpec",
    "HistoricalEloSemantics",
    "HistoricalFatigueSemantics",
    "HistoricalFormSemantics",
    "SemanticQualificationStatus",
    "SuccessorLiveInputSemanticQualificationProtocol",
    "SuccessorLiveInputSemanticQualificationProtocolError",
    "SuccessorPredictorSpec",
    "build_successor_live_input_semantic_qualification_protocol",
    "canonical_successor_live_input_semantic_qualification_protocol_bytes",
    "revalidate_successor_live_input_semantic_qualification_protocol",
    "sha256_successor_live_input_semantic_qualification_protocol",
    "successor_live_input_semantic_qualification_protocol_to_dict",
]
