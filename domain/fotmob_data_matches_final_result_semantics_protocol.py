"""Pre-register reviewed FotMob data-matches finished-score semantics.

PR #83 freezes the exact evidence needed before ATHENA may interpret the
reviewed ``/api/data/matches`` team score scalars as a source-reported final
score.  It executes no provider acquisition and creates no source-history,
model, pricing, selection, production, or betting authority.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import types
from collections.abc import Mapping
from typing import Any

from domain.prospective_successor_source_history_completeness_assessment import (
    ASSESSMENT_SHA256 as PR82_CANONICAL_SHA256,
    ASSESSMENT_SIZE as PR82_CANONICAL_SIZE,
    ASSESSMENT_STATE as PR82_ASSESSMENT_STATE,
    SMALLEST_MISSING_REVIEWED_BOUNDARY as PR82_SMALLEST_MISSING_BOUNDARY,
    build_prospective_successor_source_history_completeness_assessment,
    canonical_prospective_successor_source_history_completeness_assessment_bytes,
)
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


SCHEMA_VERSION = 1
PROTOCOL_ID = "FOTMOB_DATA_MATCHES_FINAL_RESULT_SEMANTICS_PROTOCOL_V1"
PROTOCOL_SCOPE = "PRE_REGISTERED_REVIEWED_DATA_MATCHES_FINAL_RESULT_SEMANTICS_ONLY"
PROTOCOL_STATE = "PRE_REGISTERED_NOT_EXECUTED_NO_FINAL_RESULT_SEMANTICS_QUALIFIED"

PR82_MAIN_SHA = "a82aa81412f45a04720687c930f36d16dbe39f67"
PR82_ASSESSMENT_BLOB_SHA = "6a46f36d7070e6e62a1587906c2e642fbcfea052"
PR82_ASSESSMENT_SHA256 = "450031e15fbb5878ee87ff7def69e549d0ec47fa94fc80dcb56e0b005408e807"
PR82_ASSESSMENT_SIZE = 3766
DATA_MATCHES_CAPTURE_BLOB_SHA = "ca2149395de868104666620173b55a880b10c729"
DATA_MATCHES_SCHEMA_BLOB_SHA = "4dfff0eb05335895c3ee0fcaa7b8da1299ea692f"
SOURCE_CAPABILITIES_BLOB_SHA = "ffd9730d6675a7dbcc9e8622d6e9844b772b6f96"
CANDIDATE_SOURCE_KEY = "fotmob_data_matches_reviewed_catalog"

CANDIDATE_FIELDS = (
    "match.id",
    "match.leagueId",
    "match.home.id",
    "match.home.score",
    "match.away.id",
    "match.away.score",
    "match.status.utcTime",
    "match.status.started",
    "match.status.cancelled",
    "match.status.finished",
)

TERMINAL_STATE_RULE = "STATUS_FINISHED_TRUE_AND_CANCELLED_FALSE_AND_STARTED_TRUE"
SCORE_RULE = "HOME_AND_AWAY_SCORE_MUST_BE_EXACT_NONNEGATIVE_INTEGERS"
OBSERVATION_RULE = (
    "AT_LEAST_TWO_DISTINCT_POST_KICKOFF_FINISHED_CAPTURES_WITH_DISTINCT_CAPTURE_LINEAGE"
)
MINIMUM_REPEAT_SEPARATION_SECONDS = 300
STABILITY_RULE = (
    "SOURCE_MATCH_TEAM_LEAGUE_KICKOFF_AND_SCORE_PAIR_MUST_BE_IDENTICAL_ACROSS_REQUIRED_FINISHED_CAPTURES"
)
SEMANTIC_SCOPE_RULE = (
    "QUALIFICATION_MEANS_SOURCE_REPORTED_FINISHED_SCORE_ONLY_NOT_REGULATION_TIME_EXTRA_TIME_PENALTIES_OR_SETTLEMENT_SEMANTICS_BEYOND_THE_SOURCE_FIELDS"
)
REASON_FIELD_RULE = "ANY_STATUS_REASON_REQUIRES_EXPLICIT_REVIEW_AND_CANNOT_AUTO_QUALIFY"
STATUS_ID_RULE = (
    "STATUS_ID_IS_RECORDED_AS_EVIDENCE_BUT_NEVER_USED_AS_THE_SOLE_FINALITY_SIGNAL"
)
LEGACY_EXCLUSION_RULE = (
    "LEGACY_FOTMOB_BYPASS_AND_HISTORICAL_SCRAPER_OUTPUT_CANNOT_PROVE_THIS_REVIEWED_DATA_MATCHES_SEMANTIC_BOUNDARY"
)

QUALIFICATION_REQUIREMENTS = (
    "REVALIDATE_EACH_CAPTURE_WITH_PR38_CAPTURE_AND_PR39_STRICT_SCHEMA_CONTRACTS",
    "REQUIRE_IDENTICAL_SOURCE_MATCH_ID_TEAM_IDS_LEAGUE_ID_AND_KICKOFF_ACROSS_OBSERVATIONS",
    "REQUIRE_EACH_USED_OBSERVATION_TO_OCCUR_STRICTLY_AFTER_SOURCE_KICKOFF",
    "REQUIRE_STATUS_FINISHED_TRUE_STARTED_TRUE_CANCELLED_FALSE",
    "REQUIRE_NO_STATUS_REASON_UNLESS_SEPARATELY_REVIEWED_AND_EXPLICITLY_ALLOWED",
    "REQUIRE_EXACT_NONNEGATIVE_HOME_AND_AWAY_SCORE_INTEGERS",
    "REQUIRE_AT_LEAST_TWO_DISTINCT_CAPTURE_MANIFESTS_AND_RAW_SHA256_VALUES",
    "REQUIRE_REQUIRED_OBSERVATIONS_TO_BE_SEPARATED_BY_AT_LEAST_300_SECONDS",
    "REQUIRE_IDENTICAL_HOME_AWAY_SCORE_PAIR_ACROSS_REQUIRED_FINISHED_OBSERVATIONS",
    "PRESERVE_REQUEST_DATE_TIMEZONE_CCODE3_AND_RAW_CAPTURE_LINEAGE_FOR_EVERY_OBSERVATION",
    "NEVER_PROMOTE_STATUS_ID_OR_NUMERIC_SCORE_COINCIDENCE_ALONE",
)

NEXT_REQUIRED_BOUNDARY = (
    "EXECUTE_REVIEWED_FOTMOB_DATA_MATCHES_FINAL_RESULT_SEMANTICS_VALIDATION"
)

_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "final_result_semantics_execution_authorized",
        "final_result_semantics_qualified",
        "source_capability_update_authorized",
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

PROTOCOL_SHA256 = "572dde2f5ba8e68c96188ec2df3cc1fdcfa554aa1023aa56e8b8f8b225d7194b"
PROTOCOL_SIZE = 3995


class FinalResultSemanticsStatus(str, enum.Enum):
    QUALIFIED_STABLE_SOURCE_FINISHED_SCORE_SEMANTICS = (
        "QUALIFIED_STABLE_SOURCE_FINISHED_SCORE_SEMANTICS"
    )
    BLOCKED_NOT_FINISHED = "BLOCKED_NOT_FINISHED"
    BLOCKED_CANCELLED_OR_CONFLICTING_STATUS = "BLOCKED_CANCELLED_OR_CONFLICTING_STATUS"
    BLOCKED_SCORE_INVALID = "BLOCKED_SCORE_INVALID"
    BLOCKED_INSUFFICIENT_POST_FINISH_OBSERVATIONS = (
        "BLOCKED_INSUFFICIENT_POST_FINISH_OBSERVATIONS"
    )
    BLOCKED_POST_FINISH_SCORE_INSTABILITY = "BLOCKED_POST_FINISH_SCORE_INSTABILITY"
    BLOCKED_FIXTURE_IDENTITY_DRIFT = "BLOCKED_FIXTURE_IDENTITY_DRIFT"
    BLOCKED_CAPTURE_LINEAGE_OR_TIME = "BLOCKED_CAPTURE_LINEAGE_OR_TIME"
    BLOCKED_STATUS_REASON_REQUIRES_REVIEW = "BLOCKED_STATUS_REASON_REQUIRES_REVIEW"


STATUS_VOCABULARY = tuple(item.value for item in FinalResultSemanticsStatus)


class FotMobDataMatchesFinalResultSemanticsProtocolError(ValueError):
    """Raised when the frozen PR #83 protocol is altered or its ancestry drifts."""


def _error(message: str) -> FotMobDataMatchesFinalResultSemanticsProtocolError:
    return FotMobDataMatchesFinalResultSemanticsProtocolError(message)


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
        raise _error("final-result semantics protocol serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _checked_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise _error("final-result semantics safety keys mismatch")
    if any(type(flag) is not bool or flag is not False for flag in value.values()):
        raise _error("all PR83 safety values must be exact False")
    return _safety()


def _verify_upstream() -> None:
    if (
        PR82_CANONICAL_SHA256 != PR82_ASSESSMENT_SHA256
        or PR82_CANONICAL_SIZE != PR82_ASSESSMENT_SIZE
    ):
        raise _error("PR82 canonical assessment constants changed")
    assessment = build_prospective_successor_source_history_completeness_assessment()
    exact = canonical_prospective_successor_source_history_completeness_assessment_bytes(
        assessment
    )
    if (
        hashlib.sha256(exact).hexdigest() != PR82_ASSESSMENT_SHA256
        or len(exact) != PR82_ASSESSMENT_SIZE
    ):
        raise _error("PR82 canonical assessment identity changed")
    if assessment.assessment_state != PR82_ASSESSMENT_STATE:
        raise _error("PR82 assessment state changed")
    if (
        PR82_SMALLEST_MISSING_BOUNDARY
        != "BUILD_REVIEWED_FOTMOB_DATA_MATCHES_FINAL_RESULT_SEMANTICS_BOUNDARY"
    ):
        raise _error("PR82 smallest missing boundary changed")

    capability = SOURCE_CAPABILITY_REGISTRY.get(CANDIDATE_SOURCE_KEY)
    if capability is None:
        raise _error("reviewed FotMob data-matches capability is missing")
    if capability.reliable_fixture_identity is not CapabilityAvailability.CONFIRMED:
        raise _error("reviewed FotMob fixture identity is no longer confirmed")
    if capability.full_time_score is not CapabilityAvailability.NOT_CAPTURED:
        raise _error("PR83 full-time-score premise changed")
    if capability.historical_coverage is not CapabilityAvailability.UNKNOWN:
        raise _error("PR83 historical-coverage premise changed")


def _payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "protocol_scope": PROTOCOL_SCOPE,
        "protocol_state": PROTOCOL_STATE,
        "repository_main_sha": PR82_MAIN_SHA,
        "pr82_assessment_blob_sha": PR82_ASSESSMENT_BLOB_SHA,
        "pr82_assessment_sha256": PR82_ASSESSMENT_SHA256,
        "pr82_assessment_size": PR82_ASSESSMENT_SIZE,
        "data_matches_capture_blob_sha": DATA_MATCHES_CAPTURE_BLOB_SHA,
        "data_matches_schema_blob_sha": DATA_MATCHES_SCHEMA_BLOB_SHA,
        "source_capabilities_blob_sha": SOURCE_CAPABILITIES_BLOB_SHA,
        "candidate_source_key": CANDIDATE_SOURCE_KEY,
        "candidate_fields": list(CANDIDATE_FIELDS),
        "terminal_state_rule": TERMINAL_STATE_RULE,
        "score_rule": SCORE_RULE,
        "observation_rule": OBSERVATION_RULE,
        "minimum_repeat_separation_seconds": MINIMUM_REPEAT_SEPARATION_SECONDS,
        "stability_rule": STABILITY_RULE,
        "semantic_scope_rule": SEMANTIC_SCOPE_RULE,
        "reason_field_rule": REASON_FIELD_RULE,
        "status_id_rule": STATUS_ID_RULE,
        "legacy_exclusion_rule": LEGACY_EXCLUSION_RULE,
        "qualification_requirements": list(QUALIFICATION_REQUIREMENTS),
        "status_vocabulary": list(STATUS_VOCABULARY),
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": dict(_safety()),
    }


@dataclasses.dataclass(frozen=True)
class FotMobDataMatchesFinalResultSemanticsProtocol:
    schema_version: int
    protocol_id: str
    protocol_scope: str
    protocol_state: str
    repository_main_sha: str
    pr82_assessment_blob_sha: str
    pr82_assessment_sha256: str
    pr82_assessment_size: int
    data_matches_capture_blob_sha: str
    data_matches_schema_blob_sha: str
    source_capabilities_blob_sha: str
    candidate_source_key: str
    candidate_fields: tuple[str, ...]
    terminal_state_rule: str
    score_rule: str
    observation_rule: str
    minimum_repeat_separation_seconds: int
    stability_rule: str
    semantic_scope_rule: str
    reason_field_rule: str
    status_id_rule: str
    legacy_exclusion_rule: str
    qualification_requirements: tuple[str, ...]
    status_vocabulary: tuple[str, ...]
    next_required_boundary: str
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if self.to_dict() != _payload():
            raise _error("final-result semantics protocol differs from frozen PR83 contract")
        object.__setattr__(self, "safety", _checked_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "protocol_id": self.protocol_id,
            "protocol_scope": self.protocol_scope,
            "protocol_state": self.protocol_state,
            "repository_main_sha": self.repository_main_sha,
            "pr82_assessment_blob_sha": self.pr82_assessment_blob_sha,
            "pr82_assessment_sha256": self.pr82_assessment_sha256,
            "pr82_assessment_size": self.pr82_assessment_size,
            "data_matches_capture_blob_sha": self.data_matches_capture_blob_sha,
            "data_matches_schema_blob_sha": self.data_matches_schema_blob_sha,
            "source_capabilities_blob_sha": self.source_capabilities_blob_sha,
            "candidate_source_key": self.candidate_source_key,
            "candidate_fields": list(self.candidate_fields),
            "terminal_state_rule": self.terminal_state_rule,
            "score_rule": self.score_rule,
            "observation_rule": self.observation_rule,
            "minimum_repeat_separation_seconds": self.minimum_repeat_separation_seconds,
            "stability_rule": self.stability_rule,
            "semantic_scope_rule": self.semantic_scope_rule,
            "reason_field_rule": self.reason_field_rule,
            "status_id_rule": self.status_id_rule,
            "legacy_exclusion_rule": self.legacy_exclusion_rule,
            "qualification_requirements": list(self.qualification_requirements),
            "status_vocabulary": list(self.status_vocabulary),
            "next_required_boundary": self.next_required_boundary,
            "safety": dict(self.safety),
        }


def build_fotmob_data_matches_final_result_semantics_protocol(
) -> FotMobDataMatchesFinalResultSemanticsProtocol:
    _verify_upstream()
    payload = _payload()
    value = FotMobDataMatchesFinalResultSemanticsProtocol(
        schema_version=payload["schema_version"],
        protocol_id=payload["protocol_id"],
        protocol_scope=payload["protocol_scope"],
        protocol_state=payload["protocol_state"],
        repository_main_sha=payload["repository_main_sha"],
        pr82_assessment_blob_sha=payload["pr82_assessment_blob_sha"],
        pr82_assessment_sha256=payload["pr82_assessment_sha256"],
        pr82_assessment_size=payload["pr82_assessment_size"],
        data_matches_capture_blob_sha=payload["data_matches_capture_blob_sha"],
        data_matches_schema_blob_sha=payload["data_matches_schema_blob_sha"],
        source_capabilities_blob_sha=payload["source_capabilities_blob_sha"],
        candidate_source_key=payload["candidate_source_key"],
        candidate_fields=tuple(payload["candidate_fields"]),
        terminal_state_rule=payload["terminal_state_rule"],
        score_rule=payload["score_rule"],
        observation_rule=payload["observation_rule"],
        minimum_repeat_separation_seconds=payload[
            "minimum_repeat_separation_seconds"
        ],
        stability_rule=payload["stability_rule"],
        semantic_scope_rule=payload["semantic_scope_rule"],
        reason_field_rule=payload["reason_field_rule"],
        status_id_rule=payload["status_id_rule"],
        legacy_exclusion_rule=payload["legacy_exclusion_rule"],
        qualification_requirements=tuple(payload["qualification_requirements"]),
        status_vocabulary=tuple(payload["status_vocabulary"]),
        next_required_boundary=payload["next_required_boundary"],
        safety=_safety(),
    )
    exact = canonical_fotmob_data_matches_final_result_semantics_protocol_bytes(value)
    if hashlib.sha256(exact).hexdigest() != PROTOCOL_SHA256 or len(exact) != PROTOCOL_SIZE:
        raise _error("PR83 final-result semantics canonical identity changed")
    return value


def canonical_fotmob_data_matches_final_result_semantics_protocol_bytes(
    value: Any,
) -> bytes:
    if type(value) is not FotMobDataMatchesFinalResultSemanticsProtocol:
        raise _error("value must be exact PR83 final-result semantics protocol")
    try:
        rebuilt = dataclasses.replace(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise _error("final-result semantics protocol failed invariant reconstruction") from exc
    return _canonical(rebuilt.to_dict())


def sha256_fotmob_data_matches_final_result_semantics_protocol(value: Any) -> str:
    return hashlib.sha256(
        canonical_fotmob_data_matches_final_result_semantics_protocol_bytes(value)
    ).hexdigest()


__all__ = [
    "CANDIDATE_FIELDS",
    "FinalResultSemanticsStatus",
    "FotMobDataMatchesFinalResultSemanticsProtocol",
    "FotMobDataMatchesFinalResultSemanticsProtocolError",
    "MINIMUM_REPEAT_SEPARATION_SECONDS",
    "NEXT_REQUIRED_BOUNDARY",
    "PROTOCOL_ID",
    "PROTOCOL_SHA256",
    "PROTOCOL_SIZE",
    "PROTOCOL_STATE",
    "QUALIFICATION_REQUIREMENTS",
    "STATUS_VOCABULARY",
    "build_fotmob_data_matches_final_result_semantics_protocol",
    "canonical_fotmob_data_matches_final_result_semantics_protocol_bytes",
    "sha256_fotmob_data_matches_final_result_semantics_protocol",
]
