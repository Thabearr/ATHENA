"""Execute the frozen PR #81 source-history completeness contract.

This boundary performs a static, evidence-only assessment of ATHENA's exact
currently reviewed FotMob chain. It deliberately materializes no historical rows,
constructs no successor features, and authorizes no expected-goals, probability,
pricing, selection, production, or betting behavior.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import types
from collections.abc import Mapping
from typing import Any

from domain.prospective_successor_source_history_completeness_protocol import (
    CANDIDATE_SOURCE_KEY,
    PROTOCOL_SHA256 as PR81_CANONICAL_SHA256,
    PROTOCOL_SIZE as PR81_CANONICAL_SIZE,
    PROTOCOL_STATE as PR81_PROTOCOL_STATE,
    SourceHistoryQualificationStatus,
    build_prospective_successor_source_history_completeness_protocol,
    canonical_prospective_successor_source_history_completeness_protocol_bytes,
)
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


SCHEMA_VERSION = 1
DATASET_NAME = "athena-prospective-successor-source-history-completeness-assessment-v1"
ASSESSMENT_SCOPE = "STATIC_REVIEWED_SOURCE_HISTORY_COMPLETENESS_EXECUTION_ONLY"
ASSESSMENT_STATE = "EXECUTED_FAIL_CLOSED_CURRENT_REVIEWED_SOURCE_HISTORY_NOT_QUALIFIED"

PR81_MAIN_SHA = "aeac6c3b54c5c39c73f6aadf27a3cd012475a4ed"
PR81_PROTOCOL_BLOB_SHA = "6d9fc8a32d99cd4013836b2378f85b7dfe971d84"
PR81_PROTOCOL_SHA256 = "9d16fcc79e9809a82ef154c75b8e263f782a4e1d4723b57cc216d893c88780ec"
PR81_PROTOCOL_SIZE = 4223

_SOURCE_BLOBS = types.MappingProxyType(
    {
        "fotmob_data_matches_capture": "ca2149395de868104666620173b55a880b10c729",
        "fotmob_data_matches_schema": "4dfff0eb05335895c3ee0fcaa7b8da1299ea692f",
        "fotmob_reviewed_match_details_capture": "22e9b8c111abc38dae043b3274a4b8b2c7b90047",
        "source_capabilities": "ffd9730d6675a7dbcc9e8622d6e9844b772b6f96",
    }
)

_CURRENT_REVIEWED_SOURCE_FACTS = types.MappingProxyType(
    {
        "reliable_fixture_identity": "CONFIRMED",
        "full_time_score": "NOT_CAPTURED",
        "historical_coverage": "UNKNOWN",
        "data_matches_raw_full_time_score_candidate": "AMBIGUOUS",
        "reviewed_match_details_capture_temporal_role": "STRICTLY_PRE_KICKOFF_ONLY",
    }
)

_PRIMARY_STATUS = (
    SourceHistoryQualificationStatus.BLOCKED_CURRENT_REVIEWED_SOURCE_NO_FINAL_SCORE_SEMANTICS
)
_BLOCKING_STATUSES = (
    SourceHistoryQualificationStatus.BLOCKED_CURRENT_REVIEWED_SOURCE_NO_FINAL_SCORE_SEMANTICS,
    SourceHistoryQualificationStatus.BLOCKED_HISTORICAL_COVERAGE_UNPROVEN,
    SourceHistoryQualificationStatus.BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN,
    SourceHistoryQualificationStatus.BLOCKED_LEAGUE_MAPPING_UNPROVEN,
)
_NON_REACHED_STATUSES = (
    SourceHistoryQualificationStatus.BLOCKED_REQUIRED_DATE_GAP,
    SourceHistoryQualificationStatus.BLOCKED_RESULT_EVIDENCE_GAP,
    SourceHistoryQualificationStatus.BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT,
)

SMALLEST_MISSING_REVIEWED_BOUNDARY = (
    "BUILD_REVIEWED_FOTMOB_DATA_MATCHES_FINAL_RESULT_SEMANTICS_BOUNDARY"
)

_SAFETY_KEYS = frozenset(
    {
        "source_history_adapter_approved",
        "source_history_completeness_proven",
        "pr80_constructor_input_authorized",
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

ASSESSMENT_SHA256 = "450031e15fbb5878ee87ff7def69e549d0ec47fa94fc80dcb56e0b005408e807"
ASSESSMENT_SIZE = 3766


class ProspectiveSuccessorSourceHistoryCompletenessAssessmentError(ValueError):
    """Raised when the frozen PR #82 assessment is altered or cannot be proven."""


def _error(message: str) -> ProspectiveSuccessorSourceHistoryCompletenessAssessmentError:
    return ProspectiveSuccessorSourceHistoryCompletenessAssessmentError(message)


def _canonical(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("source-history completeness assessment serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _checked_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise _error("source-history completeness assessment safety keys mismatch")
    if any(type(flag) is not bool or flag is not False for flag in value.values()):
        raise _error("all PR82 downstream safety values must be exact False")
    return _safety()


@dataclasses.dataclass(frozen=True)
class SourceHistoryGateResult:
    gate_id: str
    outcome: str
    status: SourceHistoryQualificationStatus | None
    reason: str

    def __post_init__(self) -> None:
        if type(self.gate_id) is not str or not self.gate_id:
            raise _error("gate_id must be exact non-empty text")
        if self.outcome not in {"BLOCKED", "UNPROVEN", "NOT_REACHED"}:
            raise _error("gate outcome is outside the frozen PR82 vocabulary")
        if self.status is not None and type(self.status) is not SourceHistoryQualificationStatus:
            raise _error("gate status must be an exact PR81 qualification status or None")
        if self.outcome == "NOT_REACHED" and self.status is not None:
            raise _error("not-reached gates must not claim a blocker was observed")
        if self.outcome != "NOT_REACHED" and self.status is None:
            raise _error("blocked or unproven gates must carry a PR81 status")
        if type(self.reason) is not str or not self.reason:
            raise _error("gate reason must be exact non-empty text")

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "outcome": self.outcome,
            "status": self.status.value if self.status is not None else None,
            "reason": self.reason,
        }


def _gate_results() -> tuple[SourceHistoryGateResult, ...]:
    return (
        SourceHistoryGateResult(
            gate_id="FINAL_RESULT_SEMANTICS",
            outcome="BLOCKED",
            status=SourceHistoryQualificationStatus.BLOCKED_CURRENT_REVIEWED_SOURCE_NO_FINAL_SCORE_SEMANTICS,
            reason="REVIEWED_CATALOG_DOES_NOT_CAPTURE_FINAL_SCORE_DATA_MATCHES_SCORE_REMAINS_AMBIGUOUS_AND_MATCH_DETAILS_CAPTURE_IS_PRE_KICKOFF_ONLY",
        ),
        SourceHistoryGateResult(
            gate_id="HISTORICAL_COVERAGE",
            outcome="UNPROVEN",
            status=SourceHistoryQualificationStatus.BLOCKED_HISTORICAL_COVERAGE_UNPROVEN,
            reason="REVIEWED_CATALOG_HISTORICAL_COVERAGE_IS_UNKNOWN",
        ),
        SourceHistoryGateResult(
            gate_id="ELO_INITIALIZATION_BOUNDARY",
            outcome="UNPROVEN",
            status=SourceHistoryQualificationStatus.BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN,
            reason="NO_REVIEWED_PROSPECTIVE_SOURCE_HISTORY_BOUNDARY_IS_PROVEN_EQUIVALENT_TO_PR69_REPLAY_START",
        ),
        SourceHistoryGateResult(
            gate_id="ELEVEN_LEAGUE_MAPPING",
            outcome="UNPROVEN",
            status=SourceHistoryQualificationStatus.BLOCKED_LEAGUE_MAPPING_UNPROVEN,
            reason="NO_EXPLICIT_REVIEWED_FOTMOB_COMPETITION_MAPPING_FOR_ALL_ELEVEN_FROZEN_MODEL_LEAGUES",
        ),
        SourceHistoryGateResult(
            gate_id="DAILY_DATE_COVERAGE",
            outcome="NOT_REACHED",
            status=None,
            reason="PRIOR_SOURCE_SEMANTICS_AND_COVERAGE_GATES_BLOCK_BEFORE_DAILY_CAPTURE_GAP_ASSESSMENT",
        ),
        SourceHistoryGateResult(
            gate_id="FINISHED_RESULT_EVIDENCE_COVERAGE",
            outcome="NOT_REACHED",
            status=None,
            reason="NO_REVIEWED_FINAL_RESULT_ADAPTER_EXISTS_TO_ENUMERATE_RESULT_EVIDENCE_GAPS",
        ),
        SourceHistoryGateResult(
            gate_id="IDENTITY_AND_CHRONOLOGY_CONFLICTS",
            outcome="NOT_REACHED",
            status=None,
            reason="NO_REVIEWED_HISTORY_CORPUS_EXISTS_TO_EXECUTE_CROSS_SEASON_IDENTITY_AND_CHRONOLOGY_CHECKS",
        ),
    )


def _verify_upstream() -> None:
    if (
        PR81_CANONICAL_SHA256 != PR81_PROTOCOL_SHA256
        or PR81_CANONICAL_SIZE != PR81_PROTOCOL_SIZE
    ):
        raise _error("PR81 canonical protocol constants changed")
    protocol = build_prospective_successor_source_history_completeness_protocol()
    exact = canonical_prospective_successor_source_history_completeness_protocol_bytes(
        protocol
    )
    if (
        hashlib.sha256(exact).hexdigest() != PR81_PROTOCOL_SHA256
        or len(exact) != PR81_PROTOCOL_SIZE
    ):
        raise _error("PR81 protocol canonical identity changed")
    if protocol.protocol_state != PR81_PROTOCOL_STATE:
        raise _error("PR81 protocol state changed")
    if protocol.candidate_source_key != CANDIDATE_SOURCE_KEY:
        raise _error("PR81 candidate source changed")
    if dict(protocol.current_reviewed_source_facts) != dict(_CURRENT_REVIEWED_SOURCE_FACTS):
        raise _error("PR81 reviewed source facts changed")

    capability = SOURCE_CAPABILITY_REGISTRY.get(CANDIDATE_SOURCE_KEY)
    if capability is None:
        raise _error("reviewed FotMob catalog capability is missing")
    if capability.reliable_fixture_identity is not CapabilityAvailability.CONFIRMED:
        raise _error("reviewed FotMob fixture identity is no longer confirmed")
    if capability.full_time_score is not CapabilityAvailability.NOT_CAPTURED:
        raise _error("reviewed FotMob final-score capability premise changed")
    if capability.historical_coverage is not CapabilityAvailability.UNKNOWN:
        raise _error("reviewed FotMob historical-coverage premise changed")


def _payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "assessment_scope": ASSESSMENT_SCOPE,
        "assessment_state": ASSESSMENT_STATE,
        "repository_main_sha": PR81_MAIN_SHA,
        "pr81_protocol_blob_sha": PR81_PROTOCOL_BLOB_SHA,
        "pr81_protocol_sha256": PR81_PROTOCOL_SHA256,
        "pr81_protocol_size": PR81_PROTOCOL_SIZE,
        "source_blob_shas": dict(_SOURCE_BLOBS),
        "candidate_source_key": CANDIDATE_SOURCE_KEY,
        "assessment_executed": True,
        "history_adapter_materialized": False,
        "history_rows_materialized": 0,
        "primary_status": _PRIMARY_STATUS.value,
        "blocking_statuses": [item.value for item in _BLOCKING_STATUSES],
        "non_reached_statuses": [item.value for item in _NON_REACHED_STATUSES],
        "current_reviewed_source_facts": dict(_CURRENT_REVIEWED_SOURCE_FACTS),
        "gate_results": [item.to_dict() for item in _gate_results()],
        "smallest_missing_reviewed_boundary": SMALLEST_MISSING_REVIEWED_BOUNDARY,
        "safety": dict(_safety()),
    }


@dataclasses.dataclass(frozen=True)
class ProspectiveSuccessorSourceHistoryCompletenessAssessment:
    schema_version: int
    dataset_name: str
    assessment_scope: str
    assessment_state: str
    repository_main_sha: str
    pr81_protocol_blob_sha: str
    pr81_protocol_sha256: str
    pr81_protocol_size: int
    source_blob_shas: Mapping[str, str]
    candidate_source_key: str
    assessment_executed: bool
    history_adapter_materialized: bool
    history_rows_materialized: int
    primary_status: SourceHistoryQualificationStatus
    blocking_statuses: tuple[SourceHistoryQualificationStatus, ...]
    non_reached_statuses: tuple[SourceHistoryQualificationStatus, ...]
    current_reviewed_source_facts: Mapping[str, str]
    gate_results: tuple[SourceHistoryGateResult, ...]
    smallest_missing_reviewed_boundary: str
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.primary_status) is not SourceHistoryQualificationStatus:
            raise _error("primary_status must be an exact PR81 qualification status")
        if type(self.blocking_statuses) is not tuple or any(
            type(item) is not SourceHistoryQualificationStatus for item in self.blocking_statuses
        ):
            raise _error("blocking_statuses must be an exact immutable PR81 status tuple")
        if type(self.non_reached_statuses) is not tuple or any(
            type(item) is not SourceHistoryQualificationStatus for item in self.non_reached_statuses
        ):
            raise _error("non_reached_statuses must be an exact immutable PR81 status tuple")
        if type(self.gate_results) is not tuple or any(
            type(item) is not SourceHistoryGateResult for item in self.gate_results
        ):
            raise _error("gate_results must be an exact immutable PR82 gate tuple")
        if type(self.assessment_executed) is not bool or self.assessment_executed is not True:
            raise _error("assessment_executed must remain exact True")
        if (
            type(self.history_adapter_materialized) is not bool
            or self.history_adapter_materialized is not False
        ):
            raise _error("history_adapter_materialized must remain exact False")
        if type(self.history_rows_materialized) is not int or self.history_rows_materialized != 0:
            raise _error("history_rows_materialized must remain exact zero")
        if self.to_dict() != _payload():
            raise _error("source-history completeness assessment differs from frozen PR82 result")
        object.__setattr__(self, "source_blob_shas", types.MappingProxyType(dict(_SOURCE_BLOBS)))
        object.__setattr__(
            self,
            "current_reviewed_source_facts",
            types.MappingProxyType(dict(_CURRENT_REVIEWED_SOURCE_FACTS)),
        )
        object.__setattr__(self, "gate_results", tuple(dataclasses.replace(x) for x in self.gate_results))
        object.__setattr__(self, "safety", _checked_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "assessment_scope": self.assessment_scope,
            "assessment_state": self.assessment_state,
            "repository_main_sha": self.repository_main_sha,
            "pr81_protocol_blob_sha": self.pr81_protocol_blob_sha,
            "pr81_protocol_sha256": self.pr81_protocol_sha256,
            "pr81_protocol_size": self.pr81_protocol_size,
            "source_blob_shas": dict(self.source_blob_shas),
            "candidate_source_key": self.candidate_source_key,
            "assessment_executed": self.assessment_executed,
            "history_adapter_materialized": self.history_adapter_materialized,
            "history_rows_materialized": self.history_rows_materialized,
            "primary_status": self.primary_status.value,
            "blocking_statuses": [item.value for item in self.blocking_statuses],
            "non_reached_statuses": [item.value for item in self.non_reached_statuses],
            "current_reviewed_source_facts": dict(self.current_reviewed_source_facts),
            "gate_results": [item.to_dict() for item in self.gate_results],
            "smallest_missing_reviewed_boundary": self.smallest_missing_reviewed_boundary,
            "safety": dict(self.safety),
        }


def build_prospective_successor_source_history_completeness_assessment(
) -> ProspectiveSuccessorSourceHistoryCompletenessAssessment:
    _verify_upstream()
    value = ProspectiveSuccessorSourceHistoryCompletenessAssessment(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        assessment_scope=ASSESSMENT_SCOPE,
        assessment_state=ASSESSMENT_STATE,
        repository_main_sha=PR81_MAIN_SHA,
        pr81_protocol_blob_sha=PR81_PROTOCOL_BLOB_SHA,
        pr81_protocol_sha256=PR81_PROTOCOL_SHA256,
        pr81_protocol_size=PR81_PROTOCOL_SIZE,
        source_blob_shas=_SOURCE_BLOBS,
        candidate_source_key=CANDIDATE_SOURCE_KEY,
        assessment_executed=True,
        history_adapter_materialized=False,
        history_rows_materialized=0,
        primary_status=_PRIMARY_STATUS,
        blocking_statuses=_BLOCKING_STATUSES,
        non_reached_statuses=_NON_REACHED_STATUSES,
        current_reviewed_source_facts=_CURRENT_REVIEWED_SOURCE_FACTS,
        gate_results=_gate_results(),
        smallest_missing_reviewed_boundary=SMALLEST_MISSING_REVIEWED_BOUNDARY,
        safety=_safety(),
    )
    exact = canonical_prospective_successor_source_history_completeness_assessment_bytes(value)
    if hashlib.sha256(exact).hexdigest() != ASSESSMENT_SHA256 or len(exact) != ASSESSMENT_SIZE:
        raise _error("PR82 source-history completeness canonical identity changed")
    return value


def canonical_prospective_successor_source_history_completeness_assessment_bytes(
    value: Any,
) -> bytes:
    if type(value) is not ProspectiveSuccessorSourceHistoryCompletenessAssessment:
        raise _error("value must be exact PR82 source-history completeness assessment")
    try:
        rebuilt = dataclasses.replace(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise _error("source-history completeness assessment failed invariant reconstruction") from exc
    return _canonical(rebuilt.to_dict())


def sha256_prospective_successor_source_history_completeness_assessment(value: Any) -> str:
    return hashlib.sha256(
        canonical_prospective_successor_source_history_completeness_assessment_bytes(value)
    ).hexdigest()


__all__ = [
    "ASSESSMENT_SHA256",
    "ASSESSMENT_SIZE",
    "ASSESSMENT_STATE",
    "DATASET_NAME",
    "ProspectiveSuccessorSourceHistoryCompletenessAssessment",
    "ProspectiveSuccessorSourceHistoryCompletenessAssessmentError",
    "SMALLEST_MISSING_REVIEWED_BOUNDARY",
    "SourceHistoryGateResult",
    "build_prospective_successor_source_history_completeness_assessment",
    "canonical_prospective_successor_source_history_completeness_assessment_bytes",
    "sha256_prospective_successor_source_history_completeness_assessment",
]