"""Execute the frozen PR #78 semantic qualification against the reviewed live chain.

This boundary is deliberately static and fail-closed. It evaluates what the exact
reviewed FotMob match-details -> PR31 implementation proves about the five raw
inputs used by the frozen successor expected-goals candidate. It does not acquire
a fixture, infer expected goals, build a score matrix, calculate probabilities,
price markets, select bets, or authorize production behavior.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import types
from collections.abc import Mapping
from typing import Any

from domain.successor_live_input_semantic_qualification_protocol import (
    LIVE_DATA_FRESHNESS_ROLE,
    SemanticQualificationStatus,
    build_successor_live_input_semantic_qualification_protocol,
    canonical_successor_live_input_semantic_qualification_protocol_bytes,
)

SCHEMA_VERSION = 1
DATASET_NAME = "athena-successor-live-input-semantic-qualification-execution-v1"
ASSESSMENT_SCOPE = "STATIC_REVIEWED_LIVE_CHAIN_SEMANTIC_QUALIFICATION_EXECUTION_ONLY"
ASSESSMENT_STATE = "EXECUTED_FAIL_CLOSED_NO_FEATURE_QUALIFIED"
NEXT_REQUIRED_BOUNDARY = "BUILD_REVIEWED_EXACT_PROSPECTIVE_SUCCESSOR_FEATURE_CONSTRUCTION"

PR78_MAIN_SHA = "dacd7d313f7e176cf71ac03b1393bbb1aee37b89"
PR78_PROTOCOL_BLOB_SHA = "cbd409fe42ffa8a3571f604e0817c06671db2a25"
PR78_PROTOCOL_SHA256 = "97a47d431ce57468598b17fcb24e9e0e9a41fa26c80ff1f4df9e2e611107ed7c"
PR78_PROTOCOL_SIZE = 4904

PR55_UNVERIFIED_CANDIDATES_BLOB_SHA = "e556b05c1270893b431cac561bf820319c2033f8"
PR57_UNVERIFIED_FACTS_BLOB_SHA = "a3575598025b93d7b26e58945034580bd4bc65f0"
PR58_FIELD_EVIDENCE_QUALIFICATION_BLOB_SHA = "37cc92b4b80046fc2e25d89ac964a43d6e89d840"
PR62_FACT_STATUS_MATERIALIZER_BLOB_SHA = "bcfa424144249f9609d79b434b3eab4cc5da94e3"
PR65_FIXTURE_INTELLIGENCE_SNAPSHOT_BLOB_SHA = "2d50d3e0338a771e95e1d37038f6f5f2914848f3"
PR66_MODEL_FEATURE_HANDOFF_BLOB_SHA = "e7b9adccdde32555ff1f70f1dfa37409165255f8"
PR31_FIXTURE_MODEL_FEATURES_BLOB_SHA = "e8d9ebf04676b54826b71752eae5aa5d23cb6caa"

_SOURCE_BLOBS = types.MappingProxyType(
    {
        "pr31_fixture_model_features": PR31_FIXTURE_MODEL_FEATURES_BLOB_SHA,
        "pr55_unverified_candidates": PR55_UNVERIFIED_CANDIDATES_BLOB_SHA,
        "pr57_unverified_facts": PR57_UNVERIFIED_FACTS_BLOB_SHA,
        "pr58_field_evidence_qualification": PR58_FIELD_EVIDENCE_QUALIFICATION_BLOB_SHA,
        "pr62_fact_status_materializer": PR62_FACT_STATUS_MATERIALIZER_BLOB_SHA,
        "pr65_fixture_intelligence_snapshot": PR65_FIXTURE_INTELLIGENCE_SNAPSHOT_BLOB_SHA,
        "pr66_model_feature_handoff": PR66_MODEL_FEATURE_HANDOFF_BLOB_SHA,
        "pr78_semantic_protocol": PR78_PROTOCOL_BLOB_SHA,
    }
)

_COMMON_REASON_CODES = (
    "PR55_EXTRACTS_APPROVED_RAW_SCALAR_PATH_WITHOUT_SUCCESSOR_DERIVATION_CONTRACT",
    "PR57_ADAPTS_CANDIDATE_VALUE_TO_FACT_WITHOUT_FEATURE_ENGINEERING",
    "PR58_QUALIFIES_EXACT_OBSERVATION_EVIDENCE_NOT_SUCCESSOR_MATHEMATICAL_SEMANTICS",
    "PR62_MATERIALIZATION_CHANGES_STATUS_ONLY",
    "PR65_MECHANICALLY_BUILDS_PR30_SNAPSHOT_FROM_MATERIALIZED_FACTS",
    "PR66_MECHANICALLY_CALLS_PR31_WITH_NO_FEATURE_ENGINEERING",
    "PR31_AVAILABLE_PROVES_FINITE_SUPPORTED_SCALAR_AND_EVIDENCE_NOT_TRAINING_SEMANTICS",
)

_REQUIRED_SEMANTICS = types.MappingProxyType(
    {
        "home_elo": "PR78_EXACT_HISTORICAL_ELO_REPLAY_SEMANTICS",
        "away_elo": "PR78_EXACT_HISTORICAL_ELO_REPLAY_SEMANTICS",
        "home_form": "PR78_EXACT_HISTORICAL_FORM_SEMANTICS",
        "away_form": "PR78_EXACT_HISTORICAL_FORM_SEMANTICS",
        "fatigue": "PR78_EXACT_HISTORICAL_FATIGUE_SEMANTICS",
    }
)

_FEATURE_ORDER = ("home_elo", "away_elo", "home_form", "away_form", "fatigue")

_SAFETY_KEYS = frozenset(
    {
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


class SuccessorLiveInputSemanticQualificationExecutionError(ValueError):
    """Raised when the frozen semantic qualification result is altered or invalid."""


def _error(message: str) -> SuccessorLiveInputSemanticQualificationExecutionError:
    return SuccessorLiveInputSemanticQualificationExecutionError(message)


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
        raise _error("live semantic qualification serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _default_safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise _error("live semantic qualification safety keys mismatch")
    if any(type(flag) is not bool or flag is not False for flag in value.values()):
        raise _error("all downstream safety values must be exact bool False")
    return _default_safety()


@dataclasses.dataclass(frozen=True)
class FeatureSemanticQualification:
    feature_id: str
    status: SemanticQualificationStatus
    value_level_compatibility: str
    derivation_provenance_compatibility: str
    required_semantics: str
    reviewed_live_value_origin: str
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.feature_id not in _FEATURE_ORDER:
            raise _error("feature_id is not one of the frozen successor raw inputs")
        if self.status is not SemanticQualificationStatus.UNQUALIFIED_INSUFFICIENT_PROVENANCE:
            raise _error("current reviewed live chain cannot positively qualify any successor raw input")
        if self.value_level_compatibility != "NOT_SUFFICIENT_TO_ESTABLISH_SEMANTIC_EQUIVALENCE":
            raise _error("value-level compatibility conclusion is frozen")
        if self.derivation_provenance_compatibility != "NOT_PROVEN_BY_REVIEWED_LIVE_CHAIN":
            raise _error("derivation/provenance conclusion is frozen")
        if self.required_semantics != _REQUIRED_SEMANTICS[self.feature_id]:
            raise _error("required historical semantics mismatch")
        if self.reviewed_live_value_origin != "REVIEWED_FOTMOB_MATCH_DETAILS_SCALAR_PRESERVED_THROUGH_PR31":
            raise _error("reviewed live value origin is frozen")
        if self.reason_codes != _COMMON_REASON_CODES:
            raise _error("semantic qualification reason codes are frozen exactly")

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "status": self.status.value,
            "value_level_compatibility": self.value_level_compatibility,
            "derivation_provenance_compatibility": self.derivation_provenance_compatibility,
            "required_semantics": self.required_semantics,
            "reviewed_live_value_origin": self.reviewed_live_value_origin,
            "reason_codes": list(self.reason_codes),
        }


@dataclasses.dataclass(frozen=True)
class SuccessorLiveInputSemanticQualificationExecution:
    schema_version: int
    dataset_name: str
    assessment_scope: str
    assessment_state: str
    repository_main_sha: str
    protocol_blob_sha: str
    protocol_sha256: str
    protocol_size: int
    source_blob_shas: Mapping[str, str]
    semantic_qualification_executed: bool
    features: tuple[FeatureSemanticQualification, ...]
    all_five_exact_semantic_equivalence: bool
    live_data_freshness_role: str
    next_required_boundary: str
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise _error("schema_version mismatch")
        if self.dataset_name != DATASET_NAME or self.assessment_scope != ASSESSMENT_SCOPE:
            raise _error("assessment identity mismatch")
        if self.assessment_state != ASSESSMENT_STATE:
            raise _error("assessment state must remain fail-closed with no feature qualified")
        if self.repository_main_sha != PR78_MAIN_SHA:
            raise _error("repository main ancestry mismatch")
        if self.protocol_blob_sha != PR78_PROTOCOL_BLOB_SHA:
            raise _error("PR78 protocol blob ancestry mismatch")
        if self.protocol_sha256 != PR78_PROTOCOL_SHA256 or self.protocol_size != PR78_PROTOCOL_SIZE:
            raise _error("PR78 canonical protocol identity mismatch")
        if not isinstance(self.source_blob_shas, Mapping) or dict(self.source_blob_shas) != dict(_SOURCE_BLOBS):
            raise _error("reviewed live source blob ancestry mismatch")
        if type(self.semantic_qualification_executed) is not bool or self.semantic_qualification_executed is not True:
            raise _error("this boundary must record exact semantic qualification execution")
        if type(self.features) is not tuple or tuple(item.feature_id for item in self.features) != _FEATURE_ORDER:
            raise _error("feature qualification set/order is frozen")
        if any(type(item) is not FeatureSemanticQualification for item in self.features):
            raise _error("features must contain exact FeatureSemanticQualification values")
        rebuilt = tuple(dataclasses.replace(item) for item in self.features)
        expected = _feature_results()
        if rebuilt != expected:
            raise _error("feature semantic qualification results differ from frozen reviewed-chain conclusion")
        if type(self.all_five_exact_semantic_equivalence) is not bool or self.all_five_exact_semantic_equivalence is not False:
            raise _error("all five raw inputs are not proven semantically equivalent")
        if self.live_data_freshness_role != LIVE_DATA_FRESHNESS_ROLE:
            raise _error("live_data_freshness role must remain the PR78 non-predictor role")
        if self.next_required_boundary != NEXT_REQUIRED_BOUNDARY:
            raise _error("next required boundary mismatch")
        object.__setattr__(self, "source_blob_shas", types.MappingProxyType(dict(_SOURCE_BLOBS)))
        object.__setattr__(self, "features", rebuilt)
        object.__setattr__(self, "safety", _validate_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "assessment_scope": self.assessment_scope,
            "assessment_state": self.assessment_state,
            "repository_main_sha": self.repository_main_sha,
            "protocol_blob_sha": self.protocol_blob_sha,
            "protocol_sha256": self.protocol_sha256,
            "protocol_size": self.protocol_size,
            "source_blob_shas": dict(self.source_blob_shas),
            "semantic_qualification_executed": self.semantic_qualification_executed,
            "features": [item.to_dict() for item in self.features],
            "all_five_exact_semantic_equivalence": self.all_five_exact_semantic_equivalence,
            "live_data_freshness_role": self.live_data_freshness_role,
            "next_required_boundary": self.next_required_boundary,
            "safety": dict(self.safety),
        }


def _feature_results() -> tuple[FeatureSemanticQualification, ...]:
    return tuple(
        FeatureSemanticQualification(
            feature_id=feature_id,
            status=SemanticQualificationStatus.UNQUALIFIED_INSUFFICIENT_PROVENANCE,
            value_level_compatibility="NOT_SUFFICIENT_TO_ESTABLISH_SEMANTIC_EQUIVALENCE",
            derivation_provenance_compatibility="NOT_PROVEN_BY_REVIEWED_LIVE_CHAIN",
            required_semantics=_REQUIRED_SEMANTICS[feature_id],
            reviewed_live_value_origin="REVIEWED_FOTMOB_MATCH_DETAILS_SCALAR_PRESERVED_THROUGH_PR31",
            reason_codes=_COMMON_REASON_CODES,
        )
        for feature_id in _FEATURE_ORDER
    )


def build_successor_live_input_semantic_qualification_execution() -> SuccessorLiveInputSemanticQualificationExecution:
    """Execute the frozen PR78 semantic test against the exact reviewed implementation chain."""

    protocol = build_successor_live_input_semantic_qualification_protocol()
    protocol_bytes = canonical_successor_live_input_semantic_qualification_protocol_bytes(protocol)
    if len(protocol_bytes) != PR78_PROTOCOL_SIZE:
        raise _error("checked-out PR78 protocol canonical size differs from frozen ancestry")
    if hashlib.sha256(protocol_bytes).hexdigest() != PR78_PROTOCOL_SHA256:
        raise _error("checked-out PR78 protocol canonical SHA-256 differs from frozen ancestry")

    return SuccessorLiveInputSemanticQualificationExecution(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        assessment_scope=ASSESSMENT_SCOPE,
        assessment_state=ASSESSMENT_STATE,
        repository_main_sha=PR78_MAIN_SHA,
        protocol_blob_sha=PR78_PROTOCOL_BLOB_SHA,
        protocol_sha256=PR78_PROTOCOL_SHA256,
        protocol_size=PR78_PROTOCOL_SIZE,
        source_blob_shas=_SOURCE_BLOBS,
        semantic_qualification_executed=True,
        features=_feature_results(),
        all_five_exact_semantic_equivalence=False,
        live_data_freshness_role=LIVE_DATA_FRESHNESS_ROLE,
        next_required_boundary=NEXT_REQUIRED_BOUNDARY,
        safety=_default_safety(),
    )


def canonical_successor_live_input_semantic_qualification_execution_bytes(value: Any) -> bytes:
    if type(value) is not SuccessorLiveInputSemanticQualificationExecution:
        raise _error("value must be exact SuccessorLiveInputSemanticQualificationExecution")
    return _canonical_json_bytes(value.to_dict())


def sha256_successor_live_input_semantic_qualification_execution(value: Any) -> str:
    return hashlib.sha256(
        canonical_successor_live_input_semantic_qualification_execution_bytes(value)
    ).hexdigest()


def revalidate_successor_live_input_semantic_qualification_execution(
    *,
    assessment: SuccessorLiveInputSemanticQualificationExecution,
    assessment_bytes: bytes,
) -> SuccessorLiveInputSemanticQualificationExecution:
    if type(assessment) is not SuccessorLiveInputSemanticQualificationExecution:
        raise _error("assessment must be exact SuccessorLiveInputSemanticQualificationExecution")
    if type(assessment_bytes) is not bytes:
        raise _error("assessment_bytes must be exact immutable bytes")
    rebuilt = build_successor_live_input_semantic_qualification_execution()
    expected = canonical_successor_live_input_semantic_qualification_execution_bytes(rebuilt)
    supplied = canonical_successor_live_input_semantic_qualification_execution_bytes(assessment)
    if supplied != expected:
        raise _error("assessment differs from exact reviewed-chain semantic conclusion")
    if assessment_bytes != expected:
        raise _error("assessment_bytes are not exact canonical assessment bytes")
    return rebuilt


__all__ = [
    "ASSESSMENT_SCOPE",
    "ASSESSMENT_STATE",
    "DATASET_NAME",
    "NEXT_REQUIRED_BOUNDARY",
    "PR31_FIXTURE_MODEL_FEATURES_BLOB_SHA",
    "PR55_UNVERIFIED_CANDIDATES_BLOB_SHA",
    "PR57_UNVERIFIED_FACTS_BLOB_SHA",
    "PR58_FIELD_EVIDENCE_QUALIFICATION_BLOB_SHA",
    "PR62_FACT_STATUS_MATERIALIZER_BLOB_SHA",
    "PR65_FIXTURE_INTELLIGENCE_SNAPSHOT_BLOB_SHA",
    "PR66_MODEL_FEATURE_HANDOFF_BLOB_SHA",
    "PR78_MAIN_SHA",
    "PR78_PROTOCOL_BLOB_SHA",
    "PR78_PROTOCOL_SHA256",
    "PR78_PROTOCOL_SIZE",
    "SCHEMA_VERSION",
    "FeatureSemanticQualification",
    "SuccessorLiveInputSemanticQualificationExecution",
    "SuccessorLiveInputSemanticQualificationExecutionError",
    "build_successor_live_input_semantic_qualification_execution",
    "canonical_successor_live_input_semantic_qualification_execution_bytes",
    "revalidate_successor_live_input_semantic_qualification_execution",
    "sha256_successor_live_input_semantic_qualification_execution",
]
