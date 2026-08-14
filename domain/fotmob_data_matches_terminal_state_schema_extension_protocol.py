"""Pre-register the reviewed FotMob terminal-state structural schema extension.

PR #86 freezes the exact additive structural rules needed to admit terminal/live
fields observed in the PR #85 capture pair. It does not modify the frozen PR #39
schema, execute a schema extension, infer football semantics, promote source
capabilities, or authorize downstream modelling, pricing, selection, or betting.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import types
from collections.abc import Mapping
from typing import Any

import domain.fotmob_data_matches_post_finish_capture_pair_evidence as pr85
import domain.fotmob_data_matches_schema as pr39_schema
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


SCHEMA_VERSION = 1
PROTOCOL_ID = "FOTMOB_DATA_MATCHES_TERMINAL_STATE_SCHEMA_EXTENSION_PROTOCOL_V1"
PROTOCOL_SCOPE = "PRE_REGISTERED_REVIEWED_TERMINAL_STATE_STRUCTURAL_EXTENSION_ONLY"
PROTOCOL_STATE = "PRE_REGISTERED_NOT_IMPLEMENTED_NO_TERMINAL_STATE_SCHEMA_EXTENSION_QUALIFIED"

REPOSITORY_MAIN_SHA = "4dc04a8856a01d5756bf992887df2553928c48a4"
PR85_EVIDENCE_BLOB_SHA = "7b74e9893071ef47ea425b4f106d92b0c5e1ddc2"
PR85_EVIDENCE_SHA256 = "a181e40c1264eecf6c9da897d826131c48177168e5592a64caa211ce64dacf02"
PR85_EVIDENCE_SIZE = 3921
PR39_SCHEMA_BLOB_SHA = "4dfff0eb05335895c3ee0fcaa7b8da1299ea692f"
CANDIDATE_SOURCE_KEY = "fotmob_data_matches_reviewed_catalog"

BASE_TEAM_KEYS = ("id", "longName", "name", "score")
BASE_STATUS_REQUIRED_KEYS = (
    "cancelled",
    "finished",
    "halfs",
    "periodLength",
    "started",
    "utcTime",
)
BASE_STATUS_OPTIONAL_KEYS = ("aggregatedStr", "reason")
BASE_HALFS_KEYS = ("firstHalfStarted",)

EXTENSION_TEAM_OPTIONAL_KEYS = ("penScore", "redCards")
EXTENSION_STATUS_OPTIONAL_KEYS = (
    "awarded",
    "liveTime",
    "numberOfAwayRedCards",
    "numberOfHomeRedCards",
    "ongoing",
    "scoreStr",
)
EXTENSION_HALFS_OPTIONAL_KEYS = ("secondHalfStarted",)
LIVE_TIME_REQUIRED_KEYS = (
    "addedTime",
    "basePeriod",
    "long",
    "longKey",
    "maxTime",
    "short",
    "shortKey",
)

TYPE_RULES = (
    "team.penScore=OPTIONAL_EXACT_NONNEGATIVE_INT_NULL_FORBIDDEN",
    "team.redCards=OPTIONAL_EXACT_NONNEGATIVE_INT_NULL_FORBIDDEN",
    "status.awarded=OPTIONAL_EXACT_BOOL_NULL_FORBIDDEN",
    "status.liveTime=OPTIONAL_EXACT_OBJECT_NULL_FORBIDDEN_EXACT_REGISTERED_KEYS",
    "status.liveTime.addedTime=REQUIRED_WHEN_LIVETIME_PRESENT_EXACT_NONNEGATIVE_INT_NULL_FORBIDDEN",
    "status.liveTime.basePeriod=REQUIRED_WHEN_LIVETIME_PRESENT_EXACT_NONNEGATIVE_INT_NULL_FORBIDDEN",
    "status.liveTime.long=REQUIRED_WHEN_LIVETIME_PRESENT_EXACT_STRING_NULL_FORBIDDEN_EMPTY_ALLOWED",
    "status.liveTime.longKey=REQUIRED_WHEN_LIVETIME_PRESENT_EXACT_STRING_NULL_FORBIDDEN_EMPTY_ALLOWED",
    "status.liveTime.maxTime=REQUIRED_WHEN_LIVETIME_PRESENT_EXACT_NONNEGATIVE_INT_NULL_FORBIDDEN",
    "status.liveTime.short=REQUIRED_WHEN_LIVETIME_PRESENT_EXACT_STRING_NULL_FORBIDDEN_EMPTY_ALLOWED",
    "status.liveTime.shortKey=REQUIRED_WHEN_LIVETIME_PRESENT_EXACT_STRING_NULL_FORBIDDEN_EMPTY_ALLOWED",
    "status.numberOfAwayRedCards=OPTIONAL_EXACT_NONNEGATIVE_INT_NULL_FORBIDDEN",
    "status.numberOfHomeRedCards=OPTIONAL_EXACT_NONNEGATIVE_INT_NULL_FORBIDDEN",
    "status.ongoing=OPTIONAL_EXACT_BOOL_NULL_FORBIDDEN",
    "status.scoreStr=OPTIONAL_EXACT_STRING_NULL_FORBIDDEN_EMPTY_ALLOWED",
    "status.halfs.secondHalfStarted=OPTIONAL_EXACT_STRING_NULL_FORBIDDEN_EMPTY_ALLOWED",
)

OPTIONALITY_RULE = (
    "ALL_EXTENSION_KEYS_ARE_OPTIONAL_AND_MUST_NOT_BECOME_PR39_BASE_REQUIRED_KEYS"
)
UNKNOWN_KEY_RULE = (
    "ANY_KEY_OUTSIDE_PR39_BASE_PLUS_PRE_REGISTERED_EXTENSION_SETS_FAILS_CLOSED"
)
STRING_SEMANTICS_RULE = (
    "EXTENSION_STRING_VALUES_ARE_OPAQUE_EXACT_STRINGS_NO_PARSING_OR_MEANING_INFERENCE"
)
INTEGER_SEMANTICS_RULE = (
    "EXTENSION_INTEGER_VALUES_ARE_STRUCTURAL_NONNEGATIVE_INTEGERS_ONLY_NO_FOOTBALL_MEANING_INFERENCE"
)
BOOLEAN_SEMANTICS_RULE = (
    "EXTENSION_BOOLEAN_VALUES_ARE_STRUCTURAL_EXACT_BOOLS_ONLY_NO_FOOTBALL_MEANING_INFERENCE"
)
PR39_IMMUTABILITY_RULE = (
    "PR39_V1_REMAINS_FROZEN_THE_EXTENSION_MUST_BE_A_SEPARATE_ADDITIVE_REVIEWED_LAYER"
)
SEMANTIC_EXCLUSION_RULE = (
    "NO_FINAL_RESULT_REGULATION_TIME_EXTRA_TIME_PENALTIES_RED_CARD_AWARD_LIVE_TIME_OR_SETTLEMENT_SEMANTICS_ARE_QUALIFIED_BY_THIS_PROTOCOL"
)
REASON_GATE_RULE = (
    "PR83_STATUS_REASON_REQUIRES_EXPLICIT_REVIEW_REMAINS_UNCHANGED_AND_INDEPENDENT"
)

QUALIFICATION_REQUIREMENTS = (
    "VERIFY_EXACT_PR85_EVIDENCE_RECEIPT_AND_PR39_SCHEMA_ANCESTRY",
    "KEEP_PR39_V1_IMPLEMENTATION_AND_EXISTING_BASE_KEY_CONTRACT_UNCHANGED",
    "ADMIT_ONLY_THE_PRE_REGISTERED_OPTIONAL_EXTENSION_KEYS_AT_TEAM_STATUS_AND_HALFS_LEVELS",
    "REQUIRE_EXACT_BOOL_INT_STRING_OR_OBJECT_TYPES_WITHOUT_COERCION",
    "REQUIRE_ALL_PRE_REGISTERED_INTEGER_EXTENSION_VALUES_TO_BE_NONNEGATIVE",
    "FORBID_NULL_FOR_EVERY_EXTENSION_FIELD_IN_THIS_PROTOCOL",
    "WHEN_STATUS_LIVETIME_IS_PRESENT_REQUIRE_EXACTLY_THE_SEVEN_PRE_REGISTERED_LIVETIME_KEYS",
    "FORBID_UNKNOWN_KEYS_INSIDE_STATUS_LIVETIME",
    "TREAT_ALL_EXTENSION_STRING_VALUES_AS_OPAQUE_STRINGS_AND_DO_NOT_PARSE_THEIR_FOOTBALL_MEANING",
    "PRESERVE_ALL_EXISTING_PR39_TOP_LEVEL_LEAGUE_MATCH_IDENTITY_AND_KICKOFF_VALIDATION_RULES",
    "DO_NOT_USE_EXTENSION_FIELDS_TO_QUALIFY_FINAL_RESULT_SEMANTICS_OR_STATUS_REASON",
    "DO_NOT_CHANGE_SOURCE_CAPABILITIES_OR_AUTHORIZE_DOWNSTREAM_MODEL_PRICING_SELECTION_OR_BETTING",
)

NEXT_REQUIRED_BOUNDARY = (
    "IMPLEMENT_REVIEWED_FOTMOB_DATA_MATCHES_TERMINAL_STATE_SCHEMA_EXTENSION"
)

_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "terminal_schema_extension_implementation_authorized",
        "terminal_schema_extension_qualified",
        "pr39_schema_mutation_authorized",
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

PROTOCOL_SHA256 = "6e2e0936023531ad9c0a87cde68eb0cf4c8753b27aaa8c001bcbd3fcb5daa225"
PROTOCOL_SIZE = 5639


class TerminalStateSchemaExtensionStatus(str, enum.Enum):
    QUALIFIED_STRUCTURAL_TERMINAL_STATE_SCHEMA_EXTENSION = (
        "QUALIFIED_STRUCTURAL_TERMINAL_STATE_SCHEMA_EXTENSION"
    )
    BLOCKED_BASE_PR39_CONTRACT_DRIFT = "BLOCKED_BASE_PR39_CONTRACT_DRIFT"
    BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT = "BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT"
    BLOCKED_EXTRA_KEY_OUTSIDE_PRE_REGISTERED_SET = (
        "BLOCKED_EXTRA_KEY_OUTSIDE_PRE_REGISTERED_SET"
    )
    BLOCKED_EXTENSION_TYPE_OR_NULLABILITY_MISMATCH = (
        "BLOCKED_EXTENSION_TYPE_OR_NULLABILITY_MISMATCH"
    )
    BLOCKED_LIVE_TIME_SHAPE_MISMATCH = "BLOCKED_LIVE_TIME_SHAPE_MISMATCH"


STATUS_VOCABULARY = tuple(item.value for item in TerminalStateSchemaExtensionStatus)


class FotMobDataMatchesTerminalStateSchemaExtensionProtocolError(ValueError):
    """Raised when the frozen PR #86 protocol or its ancestry drifts."""


def _error(message: str) -> FotMobDataMatchesTerminalStateSchemaExtensionProtocolError:
    return FotMobDataMatchesTerminalStateSchemaExtensionProtocolError(message)


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
        raise _error("terminal-state schema-extension protocol serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _checked_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise _error("terminal-state schema-extension safety keys mismatch")
    if any(type(flag) is not bool or flag is not False for flag in value.values()):
        raise _error("all PR86 safety values must be exact False")
    return _safety()


def _verify_upstream() -> None:
    if (
        pr85.EVIDENCE_SHA256 != PR85_EVIDENCE_SHA256
        or pr85.EVIDENCE_SIZE != PR85_EVIDENCE_SIZE
    ):
        raise _error("PR85 canonical evidence constants changed")
    evidence = pr85.build_fotmob_data_matches_post_finish_capture_pair_evidence()
    exact = pr85.canonical_fotmob_data_matches_post_finish_capture_pair_evidence_bytes(
        evidence
    )
    if (
        hashlib.sha256(exact).hexdigest() != PR85_EVIDENCE_SHA256
        or len(exact) != PR85_EVIDENCE_SIZE
    ):
        raise _error("PR85 canonical evidence identity changed")
    if pr85.EVIDENCE_STATE != (
        "ACQUIRED_DISTINCT_CAPTURE_PAIR_BLOCKED_BY_PR39_TERMINAL_SCHEMA_DRIFT"
    ):
        raise _error("PR85 evidence state changed")
    if pr85.NEXT_REQUIRED_BOUNDARY != (
        "PRE_REGISTER_REVIEWED_FOTMOB_DATA_MATCHES_TERMINAL_STATE_SCHEMA_EXTENSION"
    ):
        raise _error("PR85 next boundary changed")

    if tuple(sorted(pr39_schema.TEAM_KEYS)) != BASE_TEAM_KEYS:
        raise _error("PR39 base team keys changed")
    if tuple(sorted(pr39_schema.STATUS_REQUIRED_KEYS)) != BASE_STATUS_REQUIRED_KEYS:
        raise _error("PR39 required status keys changed")
    if tuple(sorted(pr39_schema.STATUS_OPTIONAL_KEYS)) != BASE_STATUS_OPTIONAL_KEYS:
        raise _error("PR39 optional status keys changed")
    if tuple(sorted(pr39_schema.HALFS_KEYS)) != BASE_HALFS_KEYS:
        raise _error("PR39 halfs keys changed")

    if tuple(pr85.PR39_EXTRA_TEAM_KEYS) != EXTENSION_TEAM_OPTIONAL_KEYS:
        raise _error("PR85 observed team extension keys changed")
    if tuple(pr85.PR39_EXTRA_STATUS_KEYS) != EXTENSION_STATUS_OPTIONAL_KEYS:
        raise _error("PR85 observed status extension keys changed")
    if tuple(pr85.PR39_EXTRA_HALFS_KEYS) != EXTENSION_HALFS_OPTIONAL_KEYS:
        raise _error("PR85 observed halfs extension keys changed")
    if pr85.SECONDARY_BLOCKER != "PR83_STATUS_REASON_REQUIRES_EXPLICIT_REVIEW":
        raise _error("PR85 independent status-reason blocker changed")

    capability = SOURCE_CAPABILITY_REGISTRY.get(CANDIDATE_SOURCE_KEY)
    if capability is None:
        raise _error("reviewed FotMob data-matches capability is missing")
    if capability.reliable_fixture_identity is not CapabilityAvailability.CONFIRMED:
        raise _error("reviewed FotMob fixture identity is no longer confirmed")
    if capability.full_time_score is not CapabilityAvailability.NOT_CAPTURED:
        raise _error("PR86 full-time-score premise changed")
    if capability.historical_coverage is not CapabilityAvailability.UNKNOWN:
        raise _error("PR86 historical-coverage premise changed")


def _payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "protocol_scope": PROTOCOL_SCOPE,
        "protocol_state": PROTOCOL_STATE,
        "repository_main_sha": REPOSITORY_MAIN_SHA,
        "pr85_evidence_blob_sha": PR85_EVIDENCE_BLOB_SHA,
        "pr85_evidence_sha256": PR85_EVIDENCE_SHA256,
        "pr85_evidence_size": PR85_EVIDENCE_SIZE,
        "pr39_schema_blob_sha": PR39_SCHEMA_BLOB_SHA,
        "candidate_source_key": CANDIDATE_SOURCE_KEY,
        "base_team_keys": list(BASE_TEAM_KEYS),
        "base_status_required_keys": list(BASE_STATUS_REQUIRED_KEYS),
        "base_status_optional_keys": list(BASE_STATUS_OPTIONAL_KEYS),
        "base_halfs_keys": list(BASE_HALFS_KEYS),
        "extension_team_optional_keys": list(EXTENSION_TEAM_OPTIONAL_KEYS),
        "extension_status_optional_keys": list(EXTENSION_STATUS_OPTIONAL_KEYS),
        "extension_halfs_optional_keys": list(EXTENSION_HALFS_OPTIONAL_KEYS),
        "live_time_required_keys": list(LIVE_TIME_REQUIRED_KEYS),
        "type_rules": list(TYPE_RULES),
        "optionality_rule": OPTIONALITY_RULE,
        "unknown_key_rule": UNKNOWN_KEY_RULE,
        "string_semantics_rule": STRING_SEMANTICS_RULE,
        "integer_semantics_rule": INTEGER_SEMANTICS_RULE,
        "boolean_semantics_rule": BOOLEAN_SEMANTICS_RULE,
        "pr39_immutability_rule": PR39_IMMUTABILITY_RULE,
        "semantic_exclusion_rule": SEMANTIC_EXCLUSION_RULE,
        "reason_gate_rule": REASON_GATE_RULE,
        "qualification_requirements": list(QUALIFICATION_REQUIREMENTS),
        "status_vocabulary": list(STATUS_VOCABULARY),
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": dict(_safety()),
    }


@dataclasses.dataclass(frozen=True)
class FotMobDataMatchesTerminalStateSchemaExtensionProtocol:
    schema_version: int
    protocol_id: str
    protocol_scope: str
    protocol_state: str
    repository_main_sha: str
    pr85_evidence_blob_sha: str
    pr85_evidence_sha256: str
    pr85_evidence_size: int
    pr39_schema_blob_sha: str
    candidate_source_key: str
    base_team_keys: tuple[str, ...]
    base_status_required_keys: tuple[str, ...]
    base_status_optional_keys: tuple[str, ...]
    base_halfs_keys: tuple[str, ...]
    extension_team_optional_keys: tuple[str, ...]
    extension_status_optional_keys: tuple[str, ...]
    extension_halfs_optional_keys: tuple[str, ...]
    live_time_required_keys: tuple[str, ...]
    type_rules: tuple[str, ...]
    optionality_rule: str
    unknown_key_rule: str
    string_semantics_rule: str
    integer_semantics_rule: str
    boolean_semantics_rule: str
    pr39_immutability_rule: str
    semantic_exclusion_rule: str
    reason_gate_rule: str
    qualification_requirements: tuple[str, ...]
    status_vocabulary: tuple[str, ...]
    next_required_boundary: str
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if self.to_dict() != _payload():
            raise _error(
                "terminal-state schema-extension protocol differs from frozen PR86 contract"
            )
        object.__setattr__(self, "safety", _checked_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        result = {
            field.name: getattr(self, field.name)
            for field in dataclasses.fields(self)
            if field.name != "safety"
        }
        for key in (
            "base_team_keys",
            "base_status_required_keys",
            "base_status_optional_keys",
            "base_halfs_keys",
            "extension_team_optional_keys",
            "extension_status_optional_keys",
            "extension_halfs_optional_keys",
            "live_time_required_keys",
            "type_rules",
            "qualification_requirements",
            "status_vocabulary",
        ):
            result[key] = list(result[key])
        result["safety"] = dict(self.safety)
        return result


def build_fotmob_data_matches_terminal_state_schema_extension_protocol(
) -> FotMobDataMatchesTerminalStateSchemaExtensionProtocol:
    _verify_upstream()
    payload = _payload()
    tuple_fields = {
        "base_team_keys",
        "base_status_required_keys",
        "base_status_optional_keys",
        "base_halfs_keys",
        "extension_team_optional_keys",
        "extension_status_optional_keys",
        "extension_halfs_optional_keys",
        "live_time_required_keys",
        "type_rules",
        "qualification_requirements",
        "status_vocabulary",
    }
    value = FotMobDataMatchesTerminalStateSchemaExtensionProtocol(
        **{
            **{
                key: (tuple(item) if key in tuple_fields else item)
                for key, item in payload.items()
                if key != "safety"
            },
            "safety": _safety(),
        }
    )
    exact = canonical_fotmob_data_matches_terminal_state_schema_extension_protocol_bytes(
        value
    )
    if hashlib.sha256(exact).hexdigest() != PROTOCOL_SHA256 or len(exact) != PROTOCOL_SIZE:
        raise _error("PR86 terminal-state schema-extension canonical identity changed")
    return value


def canonical_fotmob_data_matches_terminal_state_schema_extension_protocol_bytes(
    value: FotMobDataMatchesTerminalStateSchemaExtensionProtocol,
) -> bytes:
    if not isinstance(value, FotMobDataMatchesTerminalStateSchemaExtensionProtocol):
        raise _error("terminal-state schema-extension protocol value has wrong type")
    return _canonical(value.to_dict())


def revalidate_fotmob_data_matches_terminal_state_schema_extension_protocol(
    value: FotMobDataMatchesTerminalStateSchemaExtensionProtocol,
) -> FotMobDataMatchesTerminalStateSchemaExtensionProtocol:
    if not isinstance(value, FotMobDataMatchesTerminalStateSchemaExtensionProtocol):
        raise _error("terminal-state schema-extension protocol value has wrong type")
    expected = build_fotmob_data_matches_terminal_state_schema_extension_protocol()
    if (
        canonical_fotmob_data_matches_terminal_state_schema_extension_protocol_bytes(value)
        != canonical_fotmob_data_matches_terminal_state_schema_extension_protocol_bytes(
            expected
        )
    ):
        raise _error("terminal-state schema-extension protocol changed")
    return expected


__all__ = [
    "PROTOCOL_ID",
    "PROTOCOL_SHA256",
    "PROTOCOL_SIZE",
    "PROTOCOL_STATE",
    "STATUS_VOCABULARY",
    "NEXT_REQUIRED_BOUNDARY",
    "EXTENSION_TEAM_OPTIONAL_KEYS",
    "EXTENSION_STATUS_OPTIONAL_KEYS",
    "EXTENSION_HALFS_OPTIONAL_KEYS",
    "LIVE_TIME_REQUIRED_KEYS",
    "TYPE_RULES",
    "FotMobDataMatchesTerminalStateSchemaExtensionProtocol",
    "FotMobDataMatchesTerminalStateSchemaExtensionProtocolError",
    "TerminalStateSchemaExtensionStatus",
    "build_fotmob_data_matches_terminal_state_schema_extension_protocol",
    "canonical_fotmob_data_matches_terminal_state_schema_extension_protocol_bytes",
    "revalidate_fotmob_data_matches_terminal_state_schema_extension_protocol",
]
