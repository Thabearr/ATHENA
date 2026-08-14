"""Pre-register the reviewed FotMob eliminatedTeamId structural value-domain extension.

This protocol freezes only the evidence-backed structural domain required after
PR #87 exposed a non-null ``eliminatedTeamId`` in the exact PR #85 capture pair.
It does not interpret the field name, infer football semantics, modify PR #39 or
PR #87, promote source capabilities, or authorize downstream modelling, pricing,
selection, production, or betting.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import types
from collections.abc import Mapping
from typing import Any

import domain.fotmob_data_matches_post_finish_capture_pair_evidence as pr85_evidence
import domain.fotmob_data_matches_terminal_state_schema_extension as pr87_implementation
import domain.fotmob_data_matches_terminal_state_schema_extension_protocol as pr86_protocol
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


SCHEMA_VERSION = 1
PROTOCOL_ID = "FOTMOB_DATA_MATCHES_ELIMINATED_TEAM_ID_VALUE_DOMAIN_EXTENSION_PROTOCOL_V1"
PROTOCOL_SCOPE = "PRE_REGISTERED_REVIEWED_ELIMINATED_TEAM_ID_STRUCTURAL_VALUE_DOMAIN_ONLY"
PROTOCOL_STATE = "PRE_REGISTERED_NOT_IMPLEMENTED_NO_SEMANTIC_PROMOTION"
REPOSITORY_MAIN_SHA = "f72ac2210945e35f04b7413e2c31480f027addf0"
CANDIDATE_SOURCE_KEY = "fotmob_data_matches_reviewed_catalog"

PR39_SCHEMA_BLOB_SHA = "4dfff0eb05335895c3ee0fcaa7b8da1299ea692f"
PR85_EVIDENCE_BLOB_SHA = "7b74e9893071ef47ea425b4f106d92b0c5e1ddc2"
PR85_EVIDENCE_SHA256 = "a181e40c1264eecf6c9da897d826131c48177168e5592a64caa211ce64dacf02"
PR85_EVIDENCE_SIZE = 3921
PR86_PROTOCOL_BLOB_SHA = "71b2f1a8add05929835d469df94396375a115391"
PR86_PROTOCOL_SHA256 = "6e2e0936023531ad9c0a87cde68eb0cf4c8753b27aaa8c001bcbd3fcb5daa225"
PR86_PROTOCOL_SIZE = 5639
PR87_IMPLEMENTATION_BLOB_SHA = "fc120476739293abbb5db4374a0b4d7cfe8a1fc3"

FIRST_CAPTURE_ID = "a18e843fabe5aca74846b160"
FIRST_RAW_BLOB_SHA = "ea60c0cac4b3081c3180e00c8bfdcdbdc218915f"
FIRST_RAW_SHA256 = "fbcf24729973dbe7153c87fe9f37bd988aaca14ad10cce6b260ac7df650ff80f"
FIRST_MANIFEST_SHA256 = "27bfb5dc90c67a305bdb045a7ff33010d87c4109925384d3e6d2a6e058d7b302"
FIRST_NON_NULL_COUNT = 1
SECOND_CAPTURE_ID = "e28d9ce746c1ef9102995517"
SECOND_RAW_BLOB_SHA = "2b73b50bfa3f4ab2b49b7a8faf68d3434792ad59"
SECOND_RAW_SHA256 = "175c6f94788fbf676e08a288ff0c46a995cd8798d60e4bc5044076e3c9713f8d"
SECOND_MANIFEST_SHA256 = "d60501a5b7b1b4e5c810a0a0463bdcecb3a0b806110ad4542c314f8fe536824e"
SECOND_NON_NULL_COUNT = 1

OBSERVED_FIXTURE_ID = 5844873
OBSERVED_LEAGUE_ID = 938331
OBSERVED_HOME_TEAM_ID = 6576
OBSERVED_AWAY_TEAM_ID = 1218886
OBSERVED_NON_NULL_VALUE = 6576
OBSERVED_STATUS_ID = 13
OBSERVED_REASON_SHORT = "Pen"
OBSERVED_REASON_SHORT_KEY = "penalties_short"
OBSERVED_REASON_LONG = "After penalties"
OBSERVED_REASON_LONG_KEY = "afterpenalties"
OBSERVED_VALUE_EQUALS_HOME_TEAM_ID = True

NULL_ALLOWED = True
NON_NULL_EXACT_TYPE = "INT_EXCLUDING_BOOL"
NON_NULL_MINIMUM = 1
ENDPOINT_TEAM_ID_EQUALITY_REQUIRED = False
SEMANTIC_MEANING_QUALIFIED = False
PENALTY_RELATIONSHIP_QUALIFIED = False
WINNER_LOSER_RELATIONSHIP_QUALIFIED = False
STATUS_REASON_SEMANTICS_QUALIFIED = False
FINAL_RESULT_SEMANTICS_QUALIFIED = False

QUALIFICATION_REQUIREMENTS = (
    "VERIFY_EXACT_PR85_CAPTURE_PAIR_AND_PR87_IMPLEMENTATION_ANCESTRY",
    "KEEP_FROZEN_PR39_V1_AND_PR87_IMPLEMENTATION_UNCHANGED",
    "ALLOW_ELIMINATED_TEAM_ID_TO_REMAIN_NULL",
    "WHEN_NON_NULL_REQUIRE_EXACT_INTEGER_EXCLUDING_BOOL",
    "WHEN_NON_NULL_REQUIRE_VALUE_GREATER_THAN_OR_EQUAL_TO_ONE",
    "DO_NOT_REQUIRE_OR_INFER_EQUALITY_TO_HOME_OR_AWAY_TEAM_ID_FROM_ONE_OBSERVATION",
    "DO_NOT_INFER_ELIMINATED_WINNER_LOSER_PENALTY_REGULATION_TIME_OR_SETTLEMENT_MEANING",
    "DO_NOT_QUALIFY_STATUS_REASON_OR_FINAL_RESULT_SEMANTICS",
    "DO_NOT_CHANGE_SOURCE_CAPABILITIES_OR_AUTHORIZE_DOWNSTREAM_MODEL_PRICING_SELECTION_OR_BETTING",
)

STATUS_VOCABULARY = (
    "QUALIFIED_STRUCTURAL_ELIMINATED_TEAM_ID_VALUE_DOMAIN",
    "BLOCKED_PR85_EVIDENCE_ANCESTRY_DRIFT",
    "BLOCKED_PR87_IMPLEMENTATION_ANCESTRY_DRIFT",
    "BLOCKED_ELIMINATED_TEAM_ID_TYPE_OR_NULLABILITY_MISMATCH",
    "BLOCKED_ELIMINATED_TEAM_ID_NONPOSITIVE_INTEGER",
)

NEXT_REQUIRED_BOUNDARY = (
    "IMPLEMENT_REVIEWED_FOTMOB_DATA_MATCHES_ELIMINATED_TEAM_ID_VALUE_DOMAIN_EXTENSION"
)

_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "eliminated_team_id_value_domain_implementation_authorized",
        "eliminated_team_id_value_domain_qualified",
        "eliminated_team_id_semantics_qualified",
        "pr39_schema_mutation_authorized",
        "pr87_implementation_mutation_authorized",
        "status_reason_semantics_qualified",
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
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_GIT_BLOB_RE = re.compile(r"^[0-9a-f]{40}$", flags=re.ASCII)

PROTOCOL_SHA256 = "e1b435e8ed833518f9c4a6c5ba89b3c22773c6e3c30e9a50bb85b708b9ff77da"
PROTOCOL_SIZE = 4276


class FotMobDataMatchesEliminatedTeamIdValueDomainProtocolError(ValueError):
    """Raised when the frozen PR #88 protocol or its ancestry drifts."""


def _error(message: str) -> FotMobDataMatchesEliminatedTeamIdValueDomainProtocolError:
    return FotMobDataMatchesEliminatedTeamIdValueDomainProtocolError(message)


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
        raise _error("eliminatedTeamId value-domain protocol serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _checked_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise _error("eliminatedTeamId protocol safety keys mismatch")
    if any(type(flag) is not bool or flag is not False for flag in value.values()):
        raise _error("all PR88 safety values must be exact False")
    return _safety()


def _verify_sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise _error(f"{label} must be a lowercase SHA-256")
    return value


def _verify_blob_sha(value: Any, label: str) -> str:
    if type(value) is not str or _GIT_BLOB_RE.fullmatch(value) is None:
        raise _error(f"{label} must be a lowercase Git blob SHA")
    return value


def _verify_upstream() -> None:
    if (
        pr85_evidence.EVIDENCE_SHA256 != PR85_EVIDENCE_SHA256
        or pr85_evidence.EVIDENCE_SIZE != PR85_EVIDENCE_SIZE
    ):
        raise _error("PR85 evidence identity constants changed")
    evidence = pr85_evidence.build_fotmob_data_matches_post_finish_capture_pair_evidence()
    evidence_bytes = (
        pr85_evidence.canonical_fotmob_data_matches_post_finish_capture_pair_evidence_bytes(
            evidence
        )
    )
    if (
        hashlib.sha256(evidence_bytes).hexdigest() != PR85_EVIDENCE_SHA256
        or len(evidence_bytes) != PR85_EVIDENCE_SIZE
    ):
        raise _error("PR85 evidence canonical identity changed")
    if evidence.first_capture_id != FIRST_CAPTURE_ID or evidence.second_capture_id != SECOND_CAPTURE_ID:
        raise _error("PR85 capture identity changed")
    if evidence.first_raw_sha256 != FIRST_RAW_SHA256 or evidence.second_raw_sha256 != SECOND_RAW_SHA256:
        raise _error("PR85 raw lineage changed")
    if (
        evidence.first_manifest_sha256 != FIRST_MANIFEST_SHA256
        or evidence.second_manifest_sha256 != SECOND_MANIFEST_SHA256
    ):
        raise _error("PR85 manifest lineage changed")

    if (
        pr86_protocol.PROTOCOL_SHA256 != PR86_PROTOCOL_SHA256
        or pr86_protocol.PROTOCOL_SIZE != PR86_PROTOCOL_SIZE
    ):
        raise _error("PR86 protocol identity constants changed")
    pr86_value = pr86_protocol.build_fotmob_data_matches_terminal_state_schema_extension_protocol()
    pr86_bytes = (
        pr86_protocol.canonical_fotmob_data_matches_terminal_state_schema_extension_protocol_bytes(
            pr86_value
        )
    )
    if (
        hashlib.sha256(pr86_bytes).hexdigest() != PR86_PROTOCOL_SHA256
        or len(pr86_bytes) != PR86_PROTOCOL_SIZE
    ):
        raise _error("PR86 canonical protocol identity changed")

    if pr87_implementation.PR39_SCHEMA_BLOB_SHA != PR39_SCHEMA_BLOB_SHA:
        raise _error("PR87 no longer binds the frozen PR39 schema")
    if pr87_implementation.PR86_PROTOCOL_BLOB_SHA != PR86_PROTOCOL_BLOB_SHA:
        raise _error("PR87 no longer binds the frozen PR86 protocol")
    if pr87_implementation.NEXT_REQUIRED_BOUNDARY != (
        "PRE_REGISTER_REVIEWED_FOTMOB_DATA_MATCHES_ELIMINATED_TEAM_ID_VALUE_DOMAIN_EXTENSION"
    ):
        raise _error("PR87 next boundary changed")

    capability = SOURCE_CAPABILITY_REGISTRY.get(CANDIDATE_SOURCE_KEY)
    if capability is None:
        raise _error("reviewed FotMob data-matches capability is missing")
    if capability.reliable_fixture_identity is not CapabilityAvailability.CONFIRMED:
        raise _error("reviewed FotMob fixture identity is no longer confirmed")
    if capability.full_time_score is not CapabilityAvailability.NOT_CAPTURED:
        raise _error("full-time-score capability changed before PR88")
    if capability.historical_coverage is not CapabilityAvailability.UNKNOWN:
        raise _error("historical-coverage capability changed before PR88")


def _payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "protocol_scope": PROTOCOL_SCOPE,
        "protocol_state": PROTOCOL_STATE,
        "repository_main_sha": REPOSITORY_MAIN_SHA,
        "candidate_source_key": CANDIDATE_SOURCE_KEY,
        "pr39_schema_blob_sha": PR39_SCHEMA_BLOB_SHA,
        "pr85_evidence_blob_sha": PR85_EVIDENCE_BLOB_SHA,
        "pr85_evidence_sha256": PR85_EVIDENCE_SHA256,
        "pr85_evidence_size": PR85_EVIDENCE_SIZE,
        "pr86_protocol_blob_sha": PR86_PROTOCOL_BLOB_SHA,
        "pr86_protocol_sha256": PR86_PROTOCOL_SHA256,
        "pr86_protocol_size": PR86_PROTOCOL_SIZE,
        "pr87_implementation_blob_sha": PR87_IMPLEMENTATION_BLOB_SHA,
        "first_capture_id": FIRST_CAPTURE_ID,
        "first_raw_blob_sha": FIRST_RAW_BLOB_SHA,
        "first_raw_sha256": FIRST_RAW_SHA256,
        "first_manifest_sha256": FIRST_MANIFEST_SHA256,
        "first_non_null_count": FIRST_NON_NULL_COUNT,
        "second_capture_id": SECOND_CAPTURE_ID,
        "second_raw_blob_sha": SECOND_RAW_BLOB_SHA,
        "second_raw_sha256": SECOND_RAW_SHA256,
        "second_manifest_sha256": SECOND_MANIFEST_SHA256,
        "second_non_null_count": SECOND_NON_NULL_COUNT,
        "observed_fixture_id": OBSERVED_FIXTURE_ID,
        "observed_league_id": OBSERVED_LEAGUE_ID,
        "observed_home_team_id": OBSERVED_HOME_TEAM_ID,
        "observed_away_team_id": OBSERVED_AWAY_TEAM_ID,
        "observed_non_null_value": OBSERVED_NON_NULL_VALUE,
        "observed_status_id": OBSERVED_STATUS_ID,
        "observed_reason_short": OBSERVED_REASON_SHORT,
        "observed_reason_short_key": OBSERVED_REASON_SHORT_KEY,
        "observed_reason_long": OBSERVED_REASON_LONG,
        "observed_reason_long_key": OBSERVED_REASON_LONG_KEY,
        "observed_value_equals_home_team_id": OBSERVED_VALUE_EQUALS_HOME_TEAM_ID,
        "null_allowed": NULL_ALLOWED,
        "non_null_exact_type": NON_NULL_EXACT_TYPE,
        "non_null_minimum": NON_NULL_MINIMUM,
        "endpoint_team_id_equality_required": ENDPOINT_TEAM_ID_EQUALITY_REQUIRED,
        "semantic_meaning_qualified": SEMANTIC_MEANING_QUALIFIED,
        "penalty_relationship_qualified": PENALTY_RELATIONSHIP_QUALIFIED,
        "winner_loser_relationship_qualified": WINNER_LOSER_RELATIONSHIP_QUALIFIED,
        "status_reason_semantics_qualified": STATUS_REASON_SEMANTICS_QUALIFIED,
        "final_result_semantics_qualified": FINAL_RESULT_SEMANTICS_QUALIFIED,
        "qualification_requirements": list(QUALIFICATION_REQUIREMENTS),
        "status_vocabulary": list(STATUS_VOCABULARY),
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": dict(_safety()),
    }


@dataclasses.dataclass(frozen=True)
class FotMobDataMatchesEliminatedTeamIdValueDomainProtocol:
    schema_version: int
    protocol_id: str
    protocol_scope: str
    protocol_state: str
    repository_main_sha: str
    candidate_source_key: str
    pr39_schema_blob_sha: str
    pr85_evidence_blob_sha: str
    pr85_evidence_sha256: str
    pr85_evidence_size: int
    pr86_protocol_blob_sha: str
    pr86_protocol_sha256: str
    pr86_protocol_size: int
    pr87_implementation_blob_sha: str
    first_capture_id: str
    first_raw_blob_sha: str
    first_raw_sha256: str
    first_manifest_sha256: str
    first_non_null_count: int
    second_capture_id: str
    second_raw_blob_sha: str
    second_raw_sha256: str
    second_manifest_sha256: str
    second_non_null_count: int
    observed_fixture_id: int
    observed_league_id: int
    observed_home_team_id: int
    observed_away_team_id: int
    observed_non_null_value: int
    observed_status_id: int
    observed_reason_short: str
    observed_reason_short_key: str
    observed_reason_long: str
    observed_reason_long_key: str
    observed_value_equals_home_team_id: bool
    null_allowed: bool
    non_null_exact_type: str
    non_null_minimum: int
    endpoint_team_id_equality_required: bool
    semantic_meaning_qualified: bool
    penalty_relationship_qualified: bool
    winner_loser_relationship_qualified: bool
    status_reason_semantics_qualified: bool
    final_result_semantics_qualified: bool
    qualification_requirements: tuple[str, ...]
    status_vocabulary: tuple[str, ...]
    next_required_boundary: str
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise _error("schema_version must be exact integer 1")
        for label, value in (
            ("pr85_evidence_sha256", self.pr85_evidence_sha256),
            ("pr86_protocol_sha256", self.pr86_protocol_sha256),
            ("first_raw_sha256", self.first_raw_sha256),
            ("first_manifest_sha256", self.first_manifest_sha256),
            ("second_raw_sha256", self.second_raw_sha256),
            ("second_manifest_sha256", self.second_manifest_sha256),
        ):
            _verify_sha(value, label)
        for label, value in (
            ("pr39_schema_blob_sha", self.pr39_schema_blob_sha),
            ("pr85_evidence_blob_sha", self.pr85_evidence_blob_sha),
            ("pr86_protocol_blob_sha", self.pr86_protocol_blob_sha),
            ("pr87_implementation_blob_sha", self.pr87_implementation_blob_sha),
            ("first_raw_blob_sha", self.first_raw_blob_sha),
            ("second_raw_blob_sha", self.second_raw_blob_sha),
        ):
            _verify_blob_sha(value, label)
        if type(self.first_non_null_count) is not int or self.first_non_null_count != 1:
            raise _error("first_non_null_count must be exact integer 1")
        if type(self.second_non_null_count) is not int or self.second_non_null_count != 1:
            raise _error("second_non_null_count must be exact integer 1")
        for label, value in (
            ("observed_fixture_id", self.observed_fixture_id),
            ("observed_league_id", self.observed_league_id),
            ("observed_home_team_id", self.observed_home_team_id),
            ("observed_away_team_id", self.observed_away_team_id),
            ("observed_non_null_value", self.observed_non_null_value),
            ("observed_status_id", self.observed_status_id),
            ("non_null_minimum", self.non_null_minimum),
        ):
            if type(value) is not int or value < 1:
                raise _error(f"{label} must be an exact positive integer")
        for label, value in (
            ("observed_value_equals_home_team_id", self.observed_value_equals_home_team_id),
            ("null_allowed", self.null_allowed),
            ("endpoint_team_id_equality_required", self.endpoint_team_id_equality_required),
            ("semantic_meaning_qualified", self.semantic_meaning_qualified),
            ("penalty_relationship_qualified", self.penalty_relationship_qualified),
            ("winner_loser_relationship_qualified", self.winner_loser_relationship_qualified),
            ("status_reason_semantics_qualified", self.status_reason_semantics_qualified),
            ("final_result_semantics_qualified", self.final_result_semantics_qualified),
        ):
            if type(value) is not bool:
                raise _error(f"{label} must be an exact bool")
        if self.observed_value_equals_home_team_id is not True:
            raise _error("the frozen evidence relationship changed")
        if self.null_allowed is not True:
            raise _error("null must remain structurally allowed")
        for label, value in (
            ("endpoint_team_id_equality_required", self.endpoint_team_id_equality_required),
            ("semantic_meaning_qualified", self.semantic_meaning_qualified),
            ("penalty_relationship_qualified", self.penalty_relationship_qualified),
            ("winner_loser_relationship_qualified", self.winner_loser_relationship_qualified),
            ("status_reason_semantics_qualified", self.status_reason_semantics_qualified),
            ("final_result_semantics_qualified", self.final_result_semantics_qualified),
        ):
            if value is not False:
                raise _error(f"{label} must remain exact False")
        if self.observed_non_null_value != self.observed_home_team_id:
            raise _error("the frozen observed value no longer equals the observed home team id")
        if self.non_null_exact_type != "INT_EXCLUDING_BOOL" or self.non_null_minimum != 1:
            raise _error("non-null structural domain changed")
        if self.qualification_requirements != QUALIFICATION_REQUIREMENTS:
            raise _error("qualification requirements changed")
        if self.status_vocabulary != STATUS_VOCABULARY:
            raise _error("status vocabulary changed")
        if self.next_required_boundary != NEXT_REQUIRED_BOUNDARY:
            raise _error("next boundary changed")
        if self.to_dict() != _payload():
            raise _error("eliminatedTeamId protocol differs from frozen PR88 payload")
        object.__setattr__(self, "safety", _checked_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        result = {
            field.name: getattr(self, field.name)
            for field in dataclasses.fields(self)
            if field.name != "safety"
        }
        result["qualification_requirements"] = list(self.qualification_requirements)
        result["status_vocabulary"] = list(self.status_vocabulary)
        result["safety"] = dict(self.safety)
        return result


def build_fotmob_data_matches_eliminated_team_id_value_domain_protocol(
) -> FotMobDataMatchesEliminatedTeamIdValueDomainProtocol:
    _verify_upstream()
    payload = _payload()
    value = FotMobDataMatchesEliminatedTeamIdValueDomainProtocol(
        **{
            **payload,
            "qualification_requirements": tuple(payload["qualification_requirements"]),
            "status_vocabulary": tuple(payload["status_vocabulary"]),
            "safety": _safety(),
        }
    )
    exact = canonical_fotmob_data_matches_eliminated_team_id_value_domain_protocol_bytes(
        value
    )
    if hashlib.sha256(exact).hexdigest() != PROTOCOL_SHA256 or len(exact) != PROTOCOL_SIZE:
        raise _error("PR88 eliminatedTeamId protocol canonical identity changed")
    return value


def canonical_fotmob_data_matches_eliminated_team_id_value_domain_protocol_bytes(
    value: FotMobDataMatchesEliminatedTeamIdValueDomainProtocol,
) -> bytes:
    if not isinstance(value, FotMobDataMatchesEliminatedTeamIdValueDomainProtocol):
        raise _error("eliminatedTeamId protocol value has wrong type")
    return _canonical(value.to_dict())


def revalidate_fotmob_data_matches_eliminated_team_id_value_domain_protocol(
    value: FotMobDataMatchesEliminatedTeamIdValueDomainProtocol,
) -> FotMobDataMatchesEliminatedTeamIdValueDomainProtocol:
    if not isinstance(value, FotMobDataMatchesEliminatedTeamIdValueDomainProtocol):
        raise _error("eliminatedTeamId protocol value has wrong type")
    expected = build_fotmob_data_matches_eliminated_team_id_value_domain_protocol()
    if canonical_fotmob_data_matches_eliminated_team_id_value_domain_protocol_bytes(value) != (
        canonical_fotmob_data_matches_eliminated_team_id_value_domain_protocol_bytes(expected)
    ):
        raise _error("eliminatedTeamId protocol changed")
    return expected


__all__ = [
    "CANDIDATE_SOURCE_KEY",
    "ENDPOINT_TEAM_ID_EQUALITY_REQUIRED",
    "FINAL_RESULT_SEMANTICS_QUALIFIED",
    "FIRST_CAPTURE_ID",
    "FIRST_NON_NULL_COUNT",
    "FIRST_RAW_BLOB_SHA",
    "NEXT_REQUIRED_BOUNDARY",
    "NON_NULL_EXACT_TYPE",
    "NON_NULL_MINIMUM",
    "NULL_ALLOWED",
    "OBSERVED_AWAY_TEAM_ID",
    "OBSERVED_FIXTURE_ID",
    "OBSERVED_HOME_TEAM_ID",
    "OBSERVED_LEAGUE_ID",
    "OBSERVED_NON_NULL_VALUE",
    "OBSERVED_STATUS_ID",
    "PROTOCOL_ID",
    "PROTOCOL_SHA256",
    "PROTOCOL_SIZE",
    "PROTOCOL_STATE",
    "PROTOCOL_SCOPE",
    "QUALIFICATION_REQUIREMENTS",
    "REPOSITORY_MAIN_SHA",
    "SECOND_CAPTURE_ID",
    "SECOND_NON_NULL_COUNT",
    "SECOND_RAW_BLOB_SHA",
    "SEMANTIC_MEANING_QUALIFIED",
    "STATUS_REASON_SEMANTICS_QUALIFIED",
    "STATUS_VOCABULARY",
    "FotMobDataMatchesEliminatedTeamIdValueDomainProtocol",
    "FotMobDataMatchesEliminatedTeamIdValueDomainProtocolError",
    "build_fotmob_data_matches_eliminated_team_id_value_domain_protocol",
    "canonical_fotmob_data_matches_eliminated_team_id_value_domain_protocol_bytes",
    "revalidate_fotmob_data_matches_eliminated_team_id_value_domain_protocol",
]
