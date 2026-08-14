"""Pre-register the reviewed source-history adapter and completeness boundary.

PR #81 deliberately freezes the evidence and completeness requirements before
ATHENA attempts to build a prospective result-history adapter for the PR #80
successor feature constructor.  It authorizes no source history, successor
feature, expected-goals, probability, pricing, selection, production, or betting
path.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import types
from collections.abc import Mapping
from typing import Any

from domain.historical_expected_goals_successor_protocol import (
    ELO_INITIALIZATION_SEMANTICS,
    EVALUATION_SEASONS,
    PR69_SOURCE_CORPUS_SHA256,
    SOURCE_FILE_COUNT,
    SOURCE_FIXTURE_COUNT,
    TRAIN_SEASONS,
)
from domain.prospective_successor_feature_construction_candidate import (
    CONSTRUCTION_SPEC_SHA256,
    CONSTRUCTION_SPEC_SIZE,
    build_prospective_successor_feature_construction_specification,
    canonical_prospective_successor_feature_construction_specification_bytes,
)
from domain.source_capabilities import (
    CapabilityAvailability,
    SOURCE_CAPABILITY_REGISTRY,
)


SCHEMA_VERSION = 1
PROTOCOL_ID = "PROSPECTIVE_SUCCESSOR_SOURCE_HISTORY_ADAPTER_COMPLETENESS_PROTOCOL_V1"
PROTOCOL_SCOPE = "PRE_REGISTERED_REVIEWED_SOURCE_HISTORY_ADAPTER_AND_COMPLETENESS_ONLY"
PROTOCOL_STATE = "PRE_REGISTERED_NOT_EXECUTED_NO_SOURCE_HISTORY_QUALIFIED"
NEXT_REQUIRED_BOUNDARY = "EXECUTE_REVIEWED_SOURCE_HISTORY_ADAPTER_AND_COMPLETENESS_ASSESSMENT"

PR80_MAIN_SHA = "271afbc2b22d39eb6e8cd13f49fd55c4f0c45ba2"
PR80_CONSTRUCTOR_BLOB_SHA = "9135f056d036fd0207a3daead2599ac2520274be"
PR80_CONSTRUCTOR_SPEC_SHA256 = "75fe157d1b767cf374e5c2a27cc3d96434aa12f2214fc37d7c91b1e7127eb4b7"
PR80_CONSTRUCTOR_SPEC_SIZE = 2330
SOURCE_CAPABILITIES_BLOB_SHA = "ffd9730d6675a7dbcc9e8622d6e9844b772b6f96"
FOTMOB_DATA_MATCHES_CAPTURE_BLOB_SHA = "ca2149395de868104666620173b55a880b10c729"
FOTMOB_DATA_MATCHES_SCHEMA_BLOB_SHA = "4dfff0eb05335895c3ee0fcaa7b8da1299ea692f"
CANDIDATE_SOURCE_KEY = "fotmob_data_matches_reviewed_catalog"

FROZEN_MODEL_LEAGUE_CODES = (
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

INITIALIZATION_BOUNDARY_RULE = (
    "MUST_BE_PROVEN_EQUIVALENT_TO_FROZEN_PR69_REPLAY_START_NOT_CHOSEN_AD_HOC"
)
LEAGUE_UNIVERSE_RULE = (
    "EXACT_ELEVEN_FROZEN_MODEL_LEAGUES_REQUIRE_EXPLICIT_REVIEWED_FOTMOB_COMPETITION_MAPPING"
)
RESULT_SEMANTICS_RULE = (
    "FINAL_HOME_AWAY_GOALS_REQUIRE_REVIEWED_FINISHED_SETTLEMENT_SEMANTICS_NOT_RAW_SCORE_COINCIDENCE"
)

HISTORY_ADAPTER_REQUIREMENTS = (
    "ONE_FOTMOB_SOURCE_NAMESPACE_WITH_EXACT_SOURCE_FIXTURE_AND_TEAM_IDENTITIES",
    "EXACT_KICKOFF_UTC_AND_EXPLICIT_SOURCE_LOCAL_TIME_BASIS",
    "EXPLICIT_NONNEGATIVE_FINAL_HOME_AND_AWAY_GOALS",
    "FINAL_RESULT_OBSERVED_AFTER_SOURCE_FIXTURE_KICKOFF_AND_BY_TARGET_AS_OF",
    "CANONICAL_CAPTURE_AND_ROW_LINEAGE_FOR_EVERY_ADMITTED_RESULT",
    "NO_TARGET_FIXTURE_IN_PRIOR_RESULT_HISTORY",
    "NO_CROSS_SOURCE_IDENTITY_INFERENCE",
)

COMPLETENESS_REQUIREMENTS = (
    "PROVE_THE_EXACT_ELO_INITIALIZATION_BOUNDARY_AGAINST_FROZEN_PR69_SEMANTICS",
    "PROVE_EXPLICIT_MAPPING_FOR_ALL_ELEVEN_FROZEN_MODEL_LEAGUES",
    "COVER_EVERY_CALENDAR_DATE_FROM_INITIALIZATION_BOUNDARY_THROUGH_DAY_BEFORE_TARGET",
    "NO_MISSING_FAILED_OR_UNREVIEWED_DAILY_SOURCE_CAPTURE_IN_REQUIRED_INTERVAL",
    "EVERY_IN_SCOPE_FINISHED_FIXTURE_HAS_REVIEWED_FINAL_RESULT_EVIDENCE",
    "DUPLICATE_FIXTURE_ID_OR_SAME_TEAM_SAME_KICKOFF_AMBIGUITY_FAILS_CLOSED",
    "SOURCE_LOCAL_AND_UTC_CHRONOLOGY_MUST_AGREE",
    "TEAM_IDENTITY_CONTINUITY_MUST_BE_SOURCE_SCOPED_AND_EXPLICIT_ACROSS_SEASONS",
    "POSTPONED_CANCELLED_ABANDONED_OR_REARRANGED_FIXTURES_REQUIRE_EXPLICIT_DISPOSITION",
    "NO_SILENT_FILTERING_TO_ONLY_TARGET_TEAMS_BECAUSE_ELO_REPLAY_DEPENDS_ON_OPPONENT_STATE",
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

PROTOCOL_SHA256 = "b8da8a64b5b4c689eeed7fbacb9a093a5ba7409387b6bf61db6a54d9773b96bd"
PROTOCOL_SIZE = 4145


class SourceHistoryQualificationStatus(str, enum.Enum):
    QUALIFIED_COMPLETE_REVIEWED_HISTORY = "QUALIFIED_COMPLETE_REVIEWED_HISTORY"
    BLOCKED_CURRENT_REVIEWED_SOURCE_NO_FINAL_SCORE_SEMANTICS = (
        "BLOCKED_CURRENT_REVIEWED_SOURCE_NO_FINAL_SCORE_SEMANTICS"
    )
    BLOCKED_HISTORICAL_COVERAGE_UNPROVEN = "BLOCKED_HISTORICAL_COVERAGE_UNPROVEN"
    BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN = "BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN"
    BLOCKED_LEAGUE_MAPPING_UNPROVEN = "BLOCKED_LEAGUE_MAPPING_UNPROVEN"
    BLOCKED_REQUIRED_DATE_GAP = "BLOCKED_REQUIRED_DATE_GAP"
    BLOCKED_RESULT_EVIDENCE_GAP = "BLOCKED_RESULT_EVIDENCE_GAP"
    BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT = "BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT"


STATUS_VOCABULARY = tuple(item.value for item in SourceHistoryQualificationStatus)


class ProspectiveSuccessorSourceHistoryCompletenessProtocolError(ValueError):
    """Raised when the frozen PR81 protocol or its ancestry is altered."""


def _error(message: str) -> ProspectiveSuccessorSourceHistoryCompletenessProtocolError:
    return ProspectiveSuccessorSourceHistoryCompletenessProtocolError(message)


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
        raise _error("source-history completeness protocol serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _checked_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise _error("source-history completeness safety keys mismatch")
    if any(type(flag) is not bool or flag is not False for flag in value.values()):
        raise _error("all source-history completeness safety values must be exact False")
    return _safety()


def _verify_upstream() -> None:
    if (
        CONSTRUCTION_SPEC_SHA256 != PR80_CONSTRUCTOR_SPEC_SHA256
        or CONSTRUCTION_SPEC_SIZE != PR80_CONSTRUCTOR_SPEC_SIZE
    ):
        raise _error("PR80 constructor specification constants changed")
    spec = build_prospective_successor_feature_construction_specification()
    exact = canonical_prospective_successor_feature_construction_specification_bytes(spec)
    if (
        hashlib.sha256(exact).hexdigest() != PR80_CONSTRUCTOR_SPEC_SHA256
        or len(exact) != PR80_CONSTRUCTOR_SPEC_SIZE
    ):
        raise _error("PR80 constructor specification canonical identity changed")
    if PR69_SOURCE_CORPUS_SHA256 != "c273b4bff2b611e95248133340ff84803ce238814d5dfa7ded5f39fd3d6e25a0":
        raise _error("PR69 source-corpus ancestry changed")
    if SOURCE_FILE_COUNT != 66 or SOURCE_FIXTURE_COUNT != 21_226:
        raise _error("frozen PR69 source counts changed")
    if tuple(TRAIN_SEASONS) != ("2020-21", "2021-22", "2022-23", "2023-24"):
        raise _error("frozen successor training seasons changed")
    if tuple(EVALUATION_SEASONS) != ("2024-25", "2025-26"):
        raise _error("frozen successor evaluation seasons changed")
    if ELO_INITIALIZATION_SEMANTICS != "1500_REPLAY_INITIAL_STATE_ASSUMPTION_NOT_OBSERVED_EVIDENCE":
        raise _error("frozen Elo initialization semantics changed")

    capability = SOURCE_CAPABILITY_REGISTRY.get(CANDIDATE_SOURCE_KEY)
    if capability is None:
        raise _error("reviewed FotMob catalog capability is missing")
    if capability.reliable_fixture_identity is not CapabilityAvailability.CONFIRMED:
        raise _error("reviewed FotMob fixture identity is no longer confirmed")
    if capability.full_time_score is not CapabilityAvailability.NOT_CAPTURED:
        raise _error("PR81 current-source full-time-score premise changed")
    if capability.historical_coverage is not CapabilityAvailability.UNKNOWN:
        raise _error("PR81 current-source historical-coverage premise changed")


def _protocol_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "protocol_scope": PROTOCOL_SCOPE,
        "protocol_state": PROTOCOL_STATE,
        "repository_main_sha": PR80_MAIN_SHA,
        "pr80_constructor_blob_sha": PR80_CONSTRUCTOR_BLOB_SHA,
        "pr80_constructor_spec_sha256": PR80_CONSTRUCTOR_SPEC_SHA256,
        "pr80_constructor_spec_size": PR80_CONSTRUCTOR_SPEC_SIZE,
        "pr69_source_corpus_sha256": PR69_SOURCE_CORPUS_SHA256,
        "pr69_source_file_count": SOURCE_FILE_COUNT,
        "pr69_source_fixture_count": SOURCE_FIXTURE_COUNT,
        "training_seasons": list(TRAIN_SEASONS),
        "evaluation_seasons": list(EVALUATION_SEASONS),
        "frozen_model_league_codes": list(FROZEN_MODEL_LEAGUE_CODES),
        "elo_initialization_semantics": ELO_INITIALIZATION_SEMANTICS,
        "candidate_source_key": CANDIDATE_SOURCE_KEY,
        "candidate_source_capability_anchor_blob_sha": SOURCE_CAPABILITIES_BLOB_SHA,
        "candidate_data_matches_capture_blob_sha": FOTMOB_DATA_MATCHES_CAPTURE_BLOB_SHA,
        "candidate_data_matches_schema_blob_sha": FOTMOB_DATA_MATCHES_SCHEMA_BLOB_SHA,
        "current_reviewed_source_facts": dict(_CURRENT_REVIEWED_SOURCE_FACTS),
        "initialization_boundary_rule": INITIALIZATION_BOUNDARY_RULE,
        "league_universe_rule": LEAGUE_UNIVERSE_RULE,
        "result_semantics_rule": RESULT_SEMANTICS_RULE,
        "history_adapter_requirements": list(HISTORY_ADAPTER_REQUIREMENTS),
        "completeness_requirements": list(COMPLETENESS_REQUIREMENTS),
        "status_vocabulary": list(STATUS_VOCABULARY),
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": dict(_safety()),
    }


@dataclasses.dataclass(frozen=True)
class ProspectiveSuccessorSourceHistoryCompletenessProtocol:
    schema_version: int
    protocol_id: str
    protocol_scope: str
    protocol_state: str
    repository_main_sha: str
    pr80_constructor_blob_sha: str
    pr80_constructor_spec_sha256: str
    pr80_constructor_spec_size: int
    pr69_source_corpus_sha256: str
    pr69_source_file_count: int
    pr69_source_fixture_count: int
    training_seasons: tuple[str, ...]
    evaluation_seasons: tuple[str, ...]
    frozen_model_league_codes: tuple[str, ...]
    elo_initialization_semantics: str
    candidate_source_key: str
    candidate_source_capability_anchor_blob_sha: str
    candidate_data_matches_capture_blob_sha: str
    candidate_data_matches_schema_blob_sha: str
    current_reviewed_source_facts: Mapping[str, str]
    initialization_boundary_rule: str
    league_universe_rule: str
    result_semantics_rule: str
    history_adapter_requirements: tuple[str, ...]
    completeness_requirements: tuple[str, ...]
    status_vocabulary: tuple[str, ...]
    next_required_boundary: str
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if self.to_dict() != _protocol_payload():
            raise _error("source-history completeness protocol differs from frozen PR81 contract")
        object.__setattr__(
            self,
            "current_reviewed_source_facts",
            types.MappingProxyType(dict(self.current_reviewed_source_facts)),
        )
        object.__setattr__(self, "safety", _checked_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "protocol_id": self.protocol_id,
            "protocol_scope": self.protocol_scope,
            "protocol_state": self.protocol_state,
            "repository_main_sha": self.repository_main_sha,
            "pr80_constructor_blob_sha": self.pr80_constructor_blob_sha,
            "pr80_constructor_spec_sha256": self.pr80_constructor_spec_sha256,
            "pr80_constructor_spec_size": self.pr80_constructor_spec_size,
            "pr69_source_corpus_sha256": self.pr69_source_corpus_sha256,
            "pr69_source_file_count": self.pr69_source_file_count,
            "pr69_source_fixture_count": self.pr69_source_fixture_count,
            "training_seasons": list(self.training_seasons),
            "evaluation_seasons": list(self.evaluation_seasons),
            "frozen_model_league_codes": list(self.frozen_model_league_codes),
            "elo_initialization_semantics": self.elo_initialization_semantics,
            "candidate_source_key": self.candidate_source_key,
            "candidate_source_capability_anchor_blob_sha": self.candidate_source_capability_anchor_blob_sha,
            "candidate_data_matches_capture_blob_sha": self.candidate_data_matches_capture_blob_sha,
            "candidate_data_matches_schema_blob_sha": self.candidate_data_matches_schema_blob_sha,
            "current_reviewed_source_facts": dict(self.current_reviewed_source_facts),
            "initialization_boundary_rule": self.initialization_boundary_rule,
            "league_universe_rule": self.league_universe_rule,
            "result_semantics_rule": self.result_semantics_rule,
            "history_adapter_requirements": list(self.history_adapter_requirements),
            "completeness_requirements": list(self.completeness_requirements),
            "status_vocabulary": list(self.status_vocabulary),
            "next_required_boundary": self.next_required_boundary,
            "safety": dict(self.safety),
        }


def build_prospective_successor_source_history_completeness_protocol(
) -> ProspectiveSuccessorSourceHistoryCompletenessProtocol:
    _verify_upstream()
    payload = _protocol_payload()
    value = ProspectiveSuccessorSourceHistoryCompletenessProtocol(
        schema_version=payload["schema_version"],
        protocol_id=payload["protocol_id"],
        protocol_scope=payload["protocol_scope"],
        protocol_state=payload["protocol_state"],
        repository_main_sha=payload["repository_main_sha"],
        pr80_constructor_blob_sha=payload["pr80_constructor_blob_sha"],
        pr80_constructor_spec_sha256=payload["pr80_constructor_spec_sha256"],
        pr80_constructor_spec_size=payload["pr80_constructor_spec_size"],
        pr69_source_corpus_sha256=payload["pr69_source_corpus_sha256"],
        pr69_source_file_count=payload["pr69_source_file_count"],
        pr69_source_fixture_count=payload["pr69_source_fixture_count"],
        training_seasons=tuple(payload["training_seasons"]),
        evaluation_seasons=tuple(payload["evaluation_seasons"]),
        frozen_model_league_codes=tuple(payload["frozen_model_league_codes"]),
        elo_initialization_semantics=payload["elo_initialization_semantics"],
        candidate_source_key=payload["candidate_source_key"],
        candidate_source_capability_anchor_blob_sha=payload["candidate_source_capability_anchor_blob_sha"],
        candidate_data_matches_capture_blob_sha=payload["candidate_data_matches_capture_blob_sha"],
        candidate_data_matches_schema_blob_sha=payload["candidate_data_matches_schema_blob_sha"],
        current_reviewed_source_facts=types.MappingProxyType(
            dict(payload["current_reviewed_source_facts"])
        ),
        initialization_boundary_rule=payload["initialization_boundary_rule"],
        league_universe_rule=payload["league_universe_rule"],
        result_semantics_rule=payload["result_semantics_rule"],
        history_adapter_requirements=tuple(payload["history_adapter_requirements"]),
        completeness_requirements=tuple(payload["completeness_requirements"]),
        status_vocabulary=tuple(payload["status_vocabulary"]),
        next_required_boundary=payload["next_required_boundary"],
        safety=_safety(),
    )
    exact = canonical_prospective_successor_source_history_completeness_protocol_bytes(value)
    if hashlib.sha256(exact).hexdigest() != PROTOCOL_SHA256 or len(exact) != PROTOCOL_SIZE:
        raise _error("PR81 source-history completeness canonical identity changed")
    return value


def canonical_prospective_successor_source_history_completeness_protocol_bytes(
    value: Any,
) -> bytes:
    if type(value) is not ProspectiveSuccessorSourceHistoryCompletenessProtocol:
        raise _error("value must be exact PR81 source-history completeness protocol")
    try:
        rebuilt = dataclasses.replace(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise _error("source-history completeness protocol failed invariant reconstruction") from exc
    return _canonical(rebuilt.to_dict())


def sha256_prospective_successor_source_history_completeness_protocol(value: Any) -> str:
    return hashlib.sha256(
        canonical_prospective_successor_source_history_completeness_protocol_bytes(value)
    ).hexdigest()


__all__ = [
    "CANDIDATE_SOURCE_KEY",
    "COMPLETENESS_REQUIREMENTS",
    "FROZEN_MODEL_LEAGUE_CODES",
    "HISTORY_ADAPTER_REQUIREMENTS",
    "INITIALIZATION_BOUNDARY_RULE",
    "LEAGUE_UNIVERSE_RULE",
    "NEXT_REQUIRED_BOUNDARY",
    "PROTOCOL_ID",
    "PROTOCOL_SCOPE",
    "PROTOCOL_SHA256",
    "PROTOCOL_SIZE",
    "PROTOCOL_STATE",
    "ProspectiveSuccessorSourceHistoryCompletenessProtocol",
    "ProspectiveSuccessorSourceHistoryCompletenessProtocolError",
    "RESULT_SEMANTICS_RULE",
    "SCHEMA_VERSION",
    "STATUS_VOCABULARY",
    "SourceHistoryQualificationStatus",
    "build_prospective_successor_source_history_completeness_protocol",
    "canonical_prospective_successor_source_history_completeness_protocol_bytes",
    "sha256_prospective_successor_source_history_completeness_protocol",
]
