"""Execute the PR #99 FotMob ordinary-FT source-history completeness protocol.

This boundary is deliberately static and evidence-only. It revalidates the
registered derived ordinary-FT finished-score capability and executes the frozen
PR #99 completeness gates without acquiring historical data, materializing a
history adapter, constructing successor features, or authorizing any downstream
model/pricing/selection/betting path.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import types
from collections.abc import Mapping
from typing import Any

import domain.fotmob_ordinary_ft_finished_score_source_history_completeness_protocol as pr99
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


SCHEMA_VERSION = 1
DATASET_NAME = (
    "athena-fotmob-ordinary-ft-finished-score-source-history-completeness-assessment-v1"
)
ASSESSMENT_SCOPE = (
    "STATIC_EXECUTION_OF_PR99_REVIEWED_DERIVED_ORDINARY_FT_SOURCE_HISTORY_COMPLETENESS_ONLY"
)
ASSESSMENT_STATE = "EXECUTED_FAIL_CLOSED_HISTORICAL_COVERAGE_NOT_QUALIFIED"
REPOSITORY_MAIN_SHA = "43fb4aa09df0255bd76ddde0b02786a73f758771"

PR99_PROTOCOL_BLOB_SHA = "3dd38f5f61c20c10900fa0bee9a30a69a58a3006"
PR99_PROTOCOL_SHA256 = "edddd7445bb9bb6ed2db4778b6ab48da9489ae6efac822b6e6c139992275bf87"
PR99_PROTOCOL_SIZE = 5741
PR98_SOURCE_CAPABILITIES_BLOB_SHA = "37b919eb5efa0c931e1bf10d3f845865567ef0c4"
REVIEWED_ORDINARY_FT_ADAPTER_BLOB_SHA = "868563206e09010fce74b4ba7954028930baad54"

DERIVED_SOURCE_KEY = "fotmob_data_matches_reviewed_ordinary_ft_finished_score"
PARENT_SOURCE_KEY = "fotmob_data_matches_reviewed_catalog"

_FROZEN_MODEL_LEAGUE_CODES = (
    "B1",
    "D1",
    "E0",
    "F1",
    "G1",
    "I1",
    "N1",
    "P1",
    "SC0",
    "SP1",
    "T1",
)
_INITIALIZATION_BOUNDARY_RULE = (
    "MUST_BE_PROVEN_EQUIVALENT_TO_FROZEN_PR69_REPLAY_START_NOT_CHOSEN_AD_HOC"
)
_DERIVED_SOURCE_ADDITIONAL_REQUIREMENTS = (
    "EVERY_ADMITTED_RESULT_MUST_PASS_THE_REUSABLE_REVIEWED_ORDINARY_FT_FINISHED_SCORE_ADAPTER",
    "ANY_IN_SCOPE_FINISHED_FIXTURE_OUTSIDE_THE_ORDINARY_FT_GATE_BLOCKS_COMPLETENESS_UNLESS_SEPARATELY_REVIEWED",
    "DERIVED_SCORE_CAPABILITY_DOES_NOT_PROVE_HISTORICAL_COVERAGE_OR_DAILY_CAPTURE_COMPLETENESS",
    "DO_NOT_SUBSTITUTE_LEGACY_FOTMOB_HISTORICAL_OR_ANY_OTHER_SOURCE_FOR_THE_REGISTERED_DERIVED_SOURCE",
)

_CURRENT_REVIEWED_SOURCE_FACTS = types.MappingProxyType(
    {
        "derived_full_time_score": "CONFIRMED",
        "derived_reliable_fixture_identity": "CONFIRMED",
        "derived_historical_coverage": "UNKNOWN",
        "parent_full_time_score": "NOT_CAPTURED",
        "parent_historical_coverage": "UNKNOWN",
        "validated_terminal_candidate_count": 29,
        "validated_ordinary_ft_qualified_count": 28,
        "validated_penalty_fixture_excluded": 5844873,
    }
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

ASSESSMENT_SHA256 = "069a66ac3c10d6d1f7da24cd0219fc178328b3327cd1446efaaff3dfec9cffb3"
ASSESSMENT_SIZE = 4720

SMALLEST_MISSING_REVIEWED_BOUNDARY = (
    "PRE_REGISTER_REVIEWED_FOTMOB_ORDINARY_FT_SOURCE_HISTORY_ACQUISITION_PROTOCOL"
)


class FotMobOrdinaryFtSourceHistoryQualificationStatus(str, enum.Enum):
    QUALIFIED_COMPLETE_REVIEWED_ORDINARY_FT_HISTORY = (
        "QUALIFIED_COMPLETE_REVIEWED_ORDINARY_FT_HISTORY"
    )
    BLOCKED_DERIVED_SOURCE_CAPABILITY_DRIFT = "BLOCKED_DERIVED_SOURCE_CAPABILITY_DRIFT"
    BLOCKED_HISTORICAL_COVERAGE_UNPROVEN = "BLOCKED_HISTORICAL_COVERAGE_UNPROVEN"
    BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN = "BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN"
    BLOCKED_LEAGUE_MAPPING_UNPROVEN = "BLOCKED_LEAGUE_MAPPING_UNPROVEN"
    BLOCKED_REQUIRED_DATE_GAP = "BLOCKED_REQUIRED_DATE_GAP"
    BLOCKED_RESULT_EVIDENCE_GAP = "BLOCKED_RESULT_EVIDENCE_GAP"
    BLOCKED_NON_ORDINARY_FT_RESULT_REQUIRES_SEPARATE_REVIEW = (
        "BLOCKED_NON_ORDINARY_FT_RESULT_REQUIRES_SEPARATE_REVIEW"
    )
    BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT = "BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT"


STATUS_VOCABULARY = tuple(
    item.value for item in FotMobOrdinaryFtSourceHistoryQualificationStatus
)

_PRIMARY_STATUS = (
    FotMobOrdinaryFtSourceHistoryQualificationStatus.BLOCKED_HISTORICAL_COVERAGE_UNPROVEN
)
_BLOCKING_STATUSES = (
    FotMobOrdinaryFtSourceHistoryQualificationStatus.BLOCKED_HISTORICAL_COVERAGE_UNPROVEN,
    FotMobOrdinaryFtSourceHistoryQualificationStatus.BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN,
    FotMobOrdinaryFtSourceHistoryQualificationStatus.BLOCKED_LEAGUE_MAPPING_UNPROVEN,
)
_NON_REACHED_STATUSES = (
    FotMobOrdinaryFtSourceHistoryQualificationStatus.BLOCKED_REQUIRED_DATE_GAP,
    FotMobOrdinaryFtSourceHistoryQualificationStatus.BLOCKED_RESULT_EVIDENCE_GAP,
    FotMobOrdinaryFtSourceHistoryQualificationStatus.BLOCKED_NON_ORDINARY_FT_RESULT_REQUIRES_SEPARATE_REVIEW,
    FotMobOrdinaryFtSourceHistoryQualificationStatus.BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT,
)


class FotMobOrdinaryFtFinishedScoreSourceHistoryCompletenessAssessmentError(ValueError):
    """Raised when the frozen PR #100 assessment cannot be reproduced exactly."""


def _error(
    message: str,
) -> FotMobOrdinaryFtFinishedScoreSourceHistoryCompletenessAssessmentError:
    return FotMobOrdinaryFtFinishedScoreSourceHistoryCompletenessAssessmentError(message)


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
        raise _error("PR100 source-history assessment serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _checked_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise _error("PR100 source-history assessment safety keys mismatch")
    if any(type(flag) is not bool or flag is not False for flag in value.values()):
        raise _error("all PR100 downstream safety values must remain exact False")
    return _safety()


@dataclasses.dataclass(frozen=True)
class SourceHistoryGateResult:
    gate_id: str
    outcome: str
    status: FotMobOrdinaryFtSourceHistoryQualificationStatus | None
    reason: str

    def __post_init__(self) -> None:
        if type(self.gate_id) is not str or not self.gate_id:
            raise _error("gate_id must be exact non-empty text")
        if self.outcome not in {"PASSED", "BLOCKED", "UNPROVEN", "NOT_REACHED"}:
            raise _error("gate outcome is outside the frozen PR100 vocabulary")
        if self.status is not None and type(self.status) is not FotMobOrdinaryFtSourceHistoryQualificationStatus:
            raise _error("gate status must be an exact PR100 qualification status or None")
        if self.outcome in {"PASSED", "NOT_REACHED"} and self.status is not None:
            raise _error("passed or not-reached gates must not claim a blocker")
        if self.outcome in {"BLOCKED", "UNPROVEN"} and self.status is None:
            raise _error("blocked or unproven gates must carry a qualification status")
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
            gate_id="DERIVED_SCORE_CAPABILITY",
            outcome="PASSED",
            status=None,
            reason="REGISTERED_DERIVED_SOURCE_REVALIDATES_FULL_TIME_SCORE_CONFIRMED_AND_FIXTURE_IDENTITY_CONFIRMED_WITH_HISTORICAL_COVERAGE_UNKNOWN",
        ),
        SourceHistoryGateResult(
            gate_id="HISTORICAL_COVERAGE",
            outcome="BLOCKED",
            status=FotMobOrdinaryFtSourceHistoryQualificationStatus.BLOCKED_HISTORICAL_COVERAGE_UNPROVEN,
            reason="NO_REVIEWED_COMPLETE_DAILY_HISTORY_CORPUS_OR_APPROVED_SOURCE_HISTORY_ADAPTER_EXISTS_FOR_DERIVED_SOURCE",
        ),
        SourceHistoryGateResult(
            gate_id="ELO_INITIALIZATION_BOUNDARY",
            outcome="UNPROVEN",
            status=FotMobOrdinaryFtSourceHistoryQualificationStatus.BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN,
            reason="NO_REVIEWED_DERIVED_SOURCE_HISTORY_BOUNDARY_IS_PROVEN_EQUIVALENT_TO_FROZEN_PR69_REPLAY_START",
        ),
        SourceHistoryGateResult(
            gate_id="ELEVEN_LEAGUE_MAPPING",
            outcome="UNPROVEN",
            status=FotMobOrdinaryFtSourceHistoryQualificationStatus.BLOCKED_LEAGUE_MAPPING_UNPROVEN,
            reason="NO_EXPLICIT_REVIEWED_FOTMOB_COMPETITION_MAPPING_EXISTS_FOR_ALL_ELEVEN_FROZEN_MODEL_LEAGUES",
        ),
        SourceHistoryGateResult(
            gate_id="DAILY_DATE_COVERAGE",
            outcome="NOT_REACHED",
            status=None,
            reason="NO_REVIEWED_HISTORY_CORPUS_EXISTS_TO_ENUMERATE_REQUIRED_SOURCE_LOCAL_DATES",
        ),
        SourceHistoryGateResult(
            gate_id="FINISHED_RESULT_EVIDENCE_COVERAGE",
            outcome="NOT_REACHED",
            status=None,
            reason="NO_REVIEWED_HISTORY_CORPUS_EXISTS_TO_APPLY_THE_ORDINARY_FT_ADAPTER_ACROSS_THE_REQUIRED_INTERVAL",
        ),
        SourceHistoryGateResult(
            gate_id="NON_ORDINARY_FT_RESULT_STATES",
            outcome="NOT_REACHED",
            status=None,
            reason="NO_REVIEWED_HISTORY_CORPUS_EXISTS_TO_ENUMERATE_FINISHED_FIXTURES_OUTSIDE_THE_ORDINARY_FT_GATE",
        ),
        SourceHistoryGateResult(
            gate_id="IDENTITY_AND_CHRONOLOGY_CONFLICTS",
            outcome="NOT_REACHED",
            status=None,
            reason="NO_REVIEWED_HISTORY_CORPUS_EXISTS_TO_EXECUTE_CROSS_SEASON_IDENTITY_AND_CHRONOLOGY_CHECKS",
        ),
    )


def _capability_facts(capability: Any) -> dict[str, str]:
    return {
        "full_time_score": capability.full_time_score.value,
        "reliable_fixture_identity": capability.reliable_fixture_identity.value,
        "historical_coverage": capability.historical_coverage.value,
    }


def _verify_upstream() -> None:
    if (pr99.PROTOCOL_SHA256, pr99.PROTOCOL_SIZE) != (
        PR99_PROTOCOL_SHA256,
        PR99_PROTOCOL_SIZE,
    ):
        raise _error("PR99 source-history protocol constants changed")

    protocol = pr99.build_fotmob_ordinary_ft_finished_score_source_history_completeness_protocol()
    exact = (
        pr99.canonical_fotmob_ordinary_ft_finished_score_source_history_completeness_protocol_bytes(
            protocol
        )
    )
    if (
        hashlib.sha256(exact).hexdigest() != PR99_PROTOCOL_SHA256
        or len(exact) != PR99_PROTOCOL_SIZE
    ):
        raise _error("PR99 canonical source-history protocol changed")

    if protocol["protocol_state"] != pr99.PROTOCOL_STATE:
        raise _error("PR99 source-history protocol state changed")
    if protocol["derived_source_key"] != DERIVED_SOURCE_KEY:
        raise _error("PR99 derived source key changed")
    if protocol["parent_source_key"] != PARENT_SOURCE_KEY:
        raise _error("PR99 parent source key changed")
    if tuple(protocol["qualification_status_vocabulary"]) != STATUS_VOCABULARY:
        raise _error("PR99 qualification status vocabulary changed")
    if tuple(protocol["frozen_model_league_codes"]) != _FROZEN_MODEL_LEAGUE_CODES:
        raise _error("PR99 frozen model-league universe changed")
    if protocol["pr81_initialization_boundary_rule"] != _INITIALIZATION_BOUNDARY_RULE:
        raise _error("PR99 initialization-boundary rule changed")
    if tuple(protocol["derived_source_additional_requirements"]) != (
        _DERIVED_SOURCE_ADDITIONAL_REQUIREMENTS
    ):
        raise _error("PR99 derived-source completeness requirements changed")
    if protocol["current_pre_execution_disposition"] != _PRIMARY_STATUS.value:
        raise _error("PR99 pre-execution disposition changed")
    if pr99.PR98_SOURCE_CAPABILITIES_BLOB_SHA != PR98_SOURCE_CAPABILITIES_BLOB_SHA:
        raise _error("PR98 source-capabilities ancestry changed")

    derived = SOURCE_CAPABILITY_REGISTRY.get(DERIVED_SOURCE_KEY)
    parent = SOURCE_CAPABILITY_REGISTRY.get(PARENT_SOURCE_KEY)
    if derived is None or parent is None:
        raise _error("required reviewed FotMob source capability is missing")
    if _capability_facts(derived) != {
        "full_time_score": "CONFIRMED",
        "reliable_fixture_identity": "CONFIRMED",
        "historical_coverage": "UNKNOWN",
    }:
        raise _error("derived ordinary-FT score capability drifted")
    if _capability_facts(parent) != {
        "full_time_score": "NOT_CAPTURED",
        "reliable_fixture_identity": "CONFIRMED",
        "historical_coverage": "UNKNOWN",
    }:
        raise _error("parent reviewed catalog capability drifted")
    if derived.full_time_score is not CapabilityAvailability.CONFIRMED:
        raise _error("derived full_time_score must remain CONFIRMED")
    if derived.historical_coverage is not CapabilityAvailability.UNKNOWN:
        raise _error("derived historical coverage is no longer UNKNOWN")


def _payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "assessment_scope": ASSESSMENT_SCOPE,
        "assessment_state": ASSESSMENT_STATE,
        "repository_main_sha": REPOSITORY_MAIN_SHA,
        "pr99_protocol_blob_sha": PR99_PROTOCOL_BLOB_SHA,
        "pr99_protocol_sha256": PR99_PROTOCOL_SHA256,
        "pr99_protocol_size": PR99_PROTOCOL_SIZE,
        "pr98_source_capabilities_blob_sha": PR98_SOURCE_CAPABILITIES_BLOB_SHA,
        "reviewed_ordinary_ft_adapter_blob_sha": REVIEWED_ORDINARY_FT_ADAPTER_BLOB_SHA,
        "derived_source_key": DERIVED_SOURCE_KEY,
        "parent_source_key": PARENT_SOURCE_KEY,
        "assessment_executed": True,
        "network_acquisition_performed": False,
        "history_adapter_materialized": False,
        "history_rows_materialized": 0,
        "derived_score_capability_revalidated": True,
        "primary_status": _PRIMARY_STATUS.value,
        "blocking_statuses": [item.value for item in _BLOCKING_STATUSES],
        "non_reached_statuses": [item.value for item in _NON_REACHED_STATUSES],
        "current_reviewed_source_facts": dict(_CURRENT_REVIEWED_SOURCE_FACTS),
        "gate_results": [item.to_dict() for item in _gate_results()],
        "frozen_model_league_codes": list(_FROZEN_MODEL_LEAGUE_CODES),
        "initialization_boundary_rule": _INITIALIZATION_BOUNDARY_RULE,
        "derived_source_additional_requirements": list(
            _DERIVED_SOURCE_ADDITIONAL_REQUIREMENTS
        ),
        "smallest_missing_reviewed_boundary": SMALLEST_MISSING_REVIEWED_BOUNDARY,
        "safety": dict(_safety()),
    }


@dataclasses.dataclass(frozen=True)
class FotMobOrdinaryFtFinishedScoreSourceHistoryCompletenessAssessment:
    schema_version: int
    dataset_name: str
    assessment_scope: str
    assessment_state: str
    repository_main_sha: str
    pr99_protocol_blob_sha: str
    pr99_protocol_sha256: str
    pr99_protocol_size: int
    pr98_source_capabilities_blob_sha: str
    reviewed_ordinary_ft_adapter_blob_sha: str
    derived_source_key: str
    parent_source_key: str
    assessment_executed: bool
    network_acquisition_performed: bool
    history_adapter_materialized: bool
    history_rows_materialized: int
    derived_score_capability_revalidated: bool
    primary_status: FotMobOrdinaryFtSourceHistoryQualificationStatus
    blocking_statuses: tuple[FotMobOrdinaryFtSourceHistoryQualificationStatus, ...]
    non_reached_statuses: tuple[FotMobOrdinaryFtSourceHistoryQualificationStatus, ...]
    current_reviewed_source_facts: Mapping[str, Any]
    gate_results: tuple[SourceHistoryGateResult, ...]
    frozen_model_league_codes: tuple[str, ...]
    initialization_boundary_rule: str
    derived_source_additional_requirements: tuple[str, ...]
    smallest_missing_reviewed_boundary: str
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.primary_status) is not FotMobOrdinaryFtSourceHistoryQualificationStatus:
            raise _error("primary_status must be an exact PR100 qualification status")
        if type(self.blocking_statuses) is not tuple or any(
            type(item) is not FotMobOrdinaryFtSourceHistoryQualificationStatus
            for item in self.blocking_statuses
        ):
            raise _error("blocking_statuses must be an exact immutable PR100 status tuple")
        if type(self.non_reached_statuses) is not tuple or any(
            type(item) is not FotMobOrdinaryFtSourceHistoryQualificationStatus
            for item in self.non_reached_statuses
        ):
            raise _error("non_reached_statuses must be an exact immutable PR100 status tuple")
        if type(self.gate_results) is not tuple or any(
            type(item) is not SourceHistoryGateResult for item in self.gate_results
        ):
            raise _error("gate_results must be an exact immutable PR100 gate tuple")
        if type(self.assessment_executed) is not bool or self.assessment_executed is not True:
            raise _error("assessment_executed must remain exact True")
        if (
            type(self.network_acquisition_performed) is not bool
            or self.network_acquisition_performed is not False
        ):
            raise _error("network_acquisition_performed must remain exact False")
        if (
            type(self.history_adapter_materialized) is not bool
            or self.history_adapter_materialized is not False
        ):
            raise _error("history_adapter_materialized must remain exact False")
        if type(self.history_rows_materialized) is not int or self.history_rows_materialized != 0:
            raise _error("history_rows_materialized must remain exact zero")
        if (
            type(self.derived_score_capability_revalidated) is not bool
            or self.derived_score_capability_revalidated is not True
        ):
            raise _error("derived_score_capability_revalidated must remain exact True")
        if self.to_dict() != _payload():
            raise _error("PR100 source-history assessment differs from frozen result")

        object.__setattr__(
            self,
            "current_reviewed_source_facts",
            types.MappingProxyType(dict(_CURRENT_REVIEWED_SOURCE_FACTS)),
        )
        object.__setattr__(
            self,
            "gate_results",
            tuple(dataclasses.replace(item) for item in self.gate_results),
        )
        object.__setattr__(self, "safety", _checked_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "assessment_scope": self.assessment_scope,
            "assessment_state": self.assessment_state,
            "repository_main_sha": self.repository_main_sha,
            "pr99_protocol_blob_sha": self.pr99_protocol_blob_sha,
            "pr99_protocol_sha256": self.pr99_protocol_sha256,
            "pr99_protocol_size": self.pr99_protocol_size,
            "pr98_source_capabilities_blob_sha": self.pr98_source_capabilities_blob_sha,
            "reviewed_ordinary_ft_adapter_blob_sha": self.reviewed_ordinary_ft_adapter_blob_sha,
            "derived_source_key": self.derived_source_key,
            "parent_source_key": self.parent_source_key,
            "assessment_executed": self.assessment_executed,
            "network_acquisition_performed": self.network_acquisition_performed,
            "history_adapter_materialized": self.history_adapter_materialized,
            "history_rows_materialized": self.history_rows_materialized,
            "derived_score_capability_revalidated": self.derived_score_capability_revalidated,
            "primary_status": self.primary_status.value,
            "blocking_statuses": [item.value for item in self.blocking_statuses],
            "non_reached_statuses": [item.value for item in self.non_reached_statuses],
            "current_reviewed_source_facts": dict(self.current_reviewed_source_facts),
            "gate_results": [item.to_dict() for item in self.gate_results],
            "frozen_model_league_codes": list(self.frozen_model_league_codes),
            "initialization_boundary_rule": self.initialization_boundary_rule,
            "derived_source_additional_requirements": list(
                self.derived_source_additional_requirements
            ),
            "smallest_missing_reviewed_boundary": self.smallest_missing_reviewed_boundary,
            "safety": dict(self.safety),
        }


def build_fotmob_ordinary_ft_finished_score_source_history_completeness_assessment(
) -> FotMobOrdinaryFtFinishedScoreSourceHistoryCompletenessAssessment:
    """Execute the frozen PR99 gates without acquiring or materializing history."""

    _verify_upstream()
    value = FotMobOrdinaryFtFinishedScoreSourceHistoryCompletenessAssessment(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        assessment_scope=ASSESSMENT_SCOPE,
        assessment_state=ASSESSMENT_STATE,
        repository_main_sha=REPOSITORY_MAIN_SHA,
        pr99_protocol_blob_sha=PR99_PROTOCOL_BLOB_SHA,
        pr99_protocol_sha256=PR99_PROTOCOL_SHA256,
        pr99_protocol_size=PR99_PROTOCOL_SIZE,
        pr98_source_capabilities_blob_sha=PR98_SOURCE_CAPABILITIES_BLOB_SHA,
        reviewed_ordinary_ft_adapter_blob_sha=REVIEWED_ORDINARY_FT_ADAPTER_BLOB_SHA,
        derived_source_key=DERIVED_SOURCE_KEY,
        parent_source_key=PARENT_SOURCE_KEY,
        assessment_executed=True,
        network_acquisition_performed=False,
        history_adapter_materialized=False,
        history_rows_materialized=0,
        derived_score_capability_revalidated=True,
        primary_status=_PRIMARY_STATUS,
        blocking_statuses=_BLOCKING_STATUSES,
        non_reached_statuses=_NON_REACHED_STATUSES,
        current_reviewed_source_facts=_CURRENT_REVIEWED_SOURCE_FACTS,
        gate_results=_gate_results(),
        frozen_model_league_codes=_FROZEN_MODEL_LEAGUE_CODES,
        initialization_boundary_rule=_INITIALIZATION_BOUNDARY_RULE,
        derived_source_additional_requirements=_DERIVED_SOURCE_ADDITIONAL_REQUIREMENTS,
        smallest_missing_reviewed_boundary=SMALLEST_MISSING_REVIEWED_BOUNDARY,
        safety=_safety(),
    )
    exact = (
        canonical_fotmob_ordinary_ft_finished_score_source_history_completeness_assessment_bytes(
            value
        )
    )
    if hashlib.sha256(exact).hexdigest() != ASSESSMENT_SHA256 or len(exact) != ASSESSMENT_SIZE:
        raise _error("PR100 source-history assessment canonical identity changed")
    return value


def canonical_fotmob_ordinary_ft_finished_score_source_history_completeness_assessment_bytes(
    value: Any,
) -> bytes:
    if type(value) is not FotMobOrdinaryFtFinishedScoreSourceHistoryCompletenessAssessment:
        raise _error("value must be exact PR100 source-history completeness assessment")
    try:
        rebuilt = dataclasses.replace(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise _error("PR100 source-history assessment failed invariant reconstruction") from exc
    return _canonical(rebuilt.to_dict())


def sha256_fotmob_ordinary_ft_finished_score_source_history_completeness_assessment(
    value: Any,
) -> str:
    return hashlib.sha256(
        canonical_fotmob_ordinary_ft_finished_score_source_history_completeness_assessment_bytes(
            value
        )
    ).hexdigest()


__all__ = [
    "ASSESSMENT_SHA256",
    "ASSESSMENT_SIZE",
    "ASSESSMENT_STATE",
    "DATASET_NAME",
    "DERIVED_SOURCE_KEY",
    "FotMobOrdinaryFtFinishedScoreSourceHistoryCompletenessAssessment",
    "FotMobOrdinaryFtFinishedScoreSourceHistoryCompletenessAssessmentError",
    "FotMobOrdinaryFtSourceHistoryQualificationStatus",
    "PARENT_SOURCE_KEY",
    "SMALLEST_MISSING_REVIEWED_BOUNDARY",
    "STATUS_VOCABULARY",
    "SourceHistoryGateResult",
    "build_fotmob_ordinary_ft_finished_score_source_history_completeness_assessment",
    "canonical_fotmob_ordinary_ft_finished_score_source_history_completeness_assessment_bytes",
    "sha256_fotmob_ordinary_ft_finished_score_source_history_completeness_assessment",
]
