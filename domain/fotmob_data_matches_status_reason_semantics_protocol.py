"""Pre-register the reviewed FotMob ``status.reason`` gate for PR83.

PR #90 reviews only reason-label semantics needed to decide whether an otherwise
PR83-eligible, structurally admitted finished-score observation may clear the
independent ``status.reason`` blocker. It does not execute the review, modify
upstream contracts, promote source capabilities, or authorize downstream use.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import types
from collections.abc import Mapping
from typing import Any

import domain.fotmob_data_matches_eliminated_team_id_value_domain_extension as pr89
import domain.fotmob_data_matches_final_result_semantics_protocol as pr83
import domain.fotmob_data_matches_post_finish_capture_pair_evidence as pr85
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY


SCHEMA_VERSION = 1
PROTOCOL_ID = "FOTMOB_DATA_MATCHES_STATUS_REASON_SEMANTICS_PROTOCOL_V1"
PROTOCOL_SCOPE = "PRE_REGISTERED_REVIEWED_PR83_STATUS_REASON_GATE_ONLY"
PROTOCOL_STATE = "PRE_REGISTERED_NOT_EXECUTED_STATUS_REASON_GATE_UNQUALIFIED"
REPOSITORY_MAIN_SHA = "812e9f36bcffabf5c583ea1af1dd138acf23240a"
CANDIDATE_SOURCE_KEY = "fotmob_data_matches_reviewed_catalog"

PR83_PROTOCOL_BLOB_SHA = "25f8045524badcb90239df59ac9c47f36fcffe34"
PR83_PROTOCOL_SHA256 = "572dde2f5ba8e68c96188ec2df3cc1fdcfa554aa1023aa56e8b8f8b225d7194b"
PR83_PROTOCOL_SIZE = 3995
PR85_EVIDENCE_BLOB_SHA = "7b74e9893071ef47ea425b4f106d92b0c5e1ddc2"
PR85_EVIDENCE_SHA256 = "a181e40c1264eecf6c9da897d826131c48177168e5592a64caa211ce64dacf02"
PR85_EVIDENCE_SIZE = 3921
PR89_IMPLEMENTATION_BLOB_SHA = "f33dd31aedcd92b5691a3503914ed184d601b493"
SOURCE_CAPABILITIES_BLOB_SHA = "ffd9730d6675a7dbcc9e8622d6e9844b772b6f96"

REQUEST_DATE = "20260814"
TIMEZONE = "UTC"
CCODE3 = "NGA"
FIRST_CAPTURE_ID = "a18e843fabe5aca74846b160"
FIRST_RAW_SHA256 = "fbcf24729973dbe7153c87fe9f37bd988aaca14ad10cce6b260ac7df650ff80f"
FIRST_MANIFEST_SHA256 = "27bfb5dc90c67a305bdb045a7ff33010d87c4109925384d3e6d2a6e058d7b302"
SECOND_CAPTURE_ID = "e28d9ce746c1ef9102995517"
SECOND_RAW_SHA256 = "175c6f94788fbf676e08a288ff0c46a995cd8798d60e4bc5044076e3c9713f8d"
SECOND_MANIFEST_SHA256 = "d60501a5b7b1b4e5c810a0a0463bdcecb3a0b806110ad4542c314f8fe536824e"

STABLE_FINISHED_IDENTITY_SCORE_PAIR_COUNT = 29
ORDINARY_FT_REASON_PAIR_COUNT = 28
PENALTY_REASON_PAIR_COUNT = 1
ORDINARY_FT_REASON_TUPLE = types.MappingProxyType(
    {
        "short": "FT",
        "shortKey": "fulltime_short",
        "long": "Full-Time",
        "longKey": "finished",
    }
)
ORDINARY_FT_DISPOSITION = (
    "ALLOW_PR83_REASON_GATE_FOR_SOURCE_REPORTED_FINISHED_SCORE_ONLY_IF_ALL_OTHER_PR83_AND_THIS_PROTOCOL_GATES_PASS"
)
PENALTY_REASON_TUPLE = types.MappingProxyType(
    {
        "short": "Pen",
        "shortKey": "penalties_short",
        "long": "After penalties",
        "longKey": "afterpenalties",
    }
)
PENALTY_FIXTURE_ID = 5844873
PENALTY_HOME_SCORE = 1
PENALTY_AWAY_SCORE = 1
PENALTY_HOME_PEN_SCORE = 5
PENALTY_AWAY_PEN_SCORE = 6
PENALTY_ELIMINATED_TEAM_ID = 6576
PENALTY_DISPOSITION = (
    "BLOCK_PLAIN_HOME_AWAY_SCORE_SEMANTICS_PENDING_SEPARATE_PENALTY_SCORE_REVIEW"
)

REASON_SCOPE_RULE = (
    "ONLY_STATUS_REASON_ON_PR83_STABLE_FINISHED_SCORE_CANDIDATE_OBSERVATIONS_IS_IN_SCOPE"
)
EXACT_TUPLE_RULE = (
    "ALL_FOUR_REASON_FIELDS_MUST_MATCH_ONE_REVIEWED_TUPLE_EXACTLY_WITHOUT_NORMALIZATION_OR_COERCION"
)
ORDINARY_FT_AWARDED_RULE = "STATUS_AWARDED_MUST_BE_ABSENT_OR_EXACT_FALSE"
ORDINARY_FT_PEN_SCORE_RULE = (
    "TEAM_PEN_SCORE_MUST_BE_ABSENT_ON_BOTH_ENDPOINTS_FOR_ORDINARY_FT_REASON_GATE"
)
STATUS_ID_RULE = (
    "STATUS_ID_REMAINS_EVIDENCE_ONLY_AND_CANNOT_QUALIFY_REASON_OR_FINALITY_BY_ITSELF"
)
SCORE_STR_RULE = (
    "STATUS_SCORE_STR_REMAINS_OPAQUE_AND_IS_NOT_USED_TO_QUALIFY_THIS_REASON_GATE"
)
UNKNOWN_REASON_RULE = (
    "ANY_OTHER_PRESENT_REASON_TUPLE_REMAINS_BLOCKED_PENDING_EXPLICIT_REVIEW"
)
SEMANTIC_SCOPE_RULE = (
    "QUALIFIED_ORDINARY_FT_REASON_MEANS_ONLY_SOURCE_LABEL_COMPATIBILITY_WITH_PR83_SOURCE_REPORTED_FINISHED_SCORE_NOT_REGULATION_TIME_EXTRA_TIME_PENALTIES_OR_SETTLEMENT_TRUTH"
)

QUALIFICATION_REQUIREMENTS = (
    "VERIFY_EXACT_PR83_PROTOCOL_PR85_EVIDENCE_PR89_STRUCTURAL_AND_SOURCE_CAPABILITY_ANCESTRY",
    "REVALIDATE_BOTH_EXACT_PR85_RAW_CAPTURE_AND_MANIFEST_LINEAGES_BEFORE_EXECUTION",
    "REQUIRE_PR89_STRUCTURAL_QUALIFICATION_BEFORE_REASON_REVIEW_CAN_PASS",
    "APPLY_REASON_REVIEW_ONLY_TO_PR83_STABLE_FINISHED_STARTED_TRUE_CANCELLED_FALSE_SCORE_CANDIDATES",
    "REQUIRE_EXACT_FOUR_FIELD_REASON_TUPLE_WITHOUT_CASE_FOLDING_NORMALIZATION_ALIASING_OR_PARTIAL_MATCH",
    "ALLOW_ONLY_THE_EXACT_ORDINARY_FT_TUPLE_TO_CLEAR_THE_REASON_GATE",
    "FOR_ORDINARY_FT_REQUIRE_STATUS_AWARDED_ABSENT_OR_EXACT_FALSE",
    "FOR_ORDINARY_FT_REQUIRE_TEAM_PEN_SCORE_ABSENT_ON_BOTH_ENDPOINTS",
    "BLOCK_THE_EXACT_PENALTY_REASON_TUPLE_FROM_PLAIN_HOME_AWAY_SCORE_SEMANTICS",
    "BLOCK_ANY_OTHER_PRESENT_REASON_TUPLE_PENDING_SEPARATE_EXPLICIT_REVIEW",
    "DO_NOT_USE_STATUS_ID_SCORE_STR_ELIMINATED_TEAM_ID_OR_PEN_SCORE_VALUES_TO_CREATE_UNREGISTERED_SEMANTICS",
    "DO_NOT_QUALIFY_REGULATION_TIME_EXTRA_TIME_PENALTY_SETTLEMENT_OR_BOOKMAKER_RULES",
    "DO_NOT_CHANGE_SOURCE_CAPABILITIES_OR_AUTHORIZE_DOWNSTREAM_MODEL_PRICING_SELECTION_OR_BETTING",
)

STATUS_VOCABULARY = (
    "QUALIFIED_PR83_REASON_GATE_ORDINARY_FT_SOURCE_LABEL",
    "BLOCKED_PR83_OR_PR85_ANCESTRY_DRIFT",
    "BLOCKED_PR89_STRUCTURAL_ANCESTRY_DRIFT",
    "BLOCKED_REASON_TUPLE_UNREVIEWED",
    "BLOCKED_REASON_TUPLE_MISMATCH_OR_PARTIAL",
    "BLOCKED_AWARDED_RESULT_REQUIRES_SEPARATE_REVIEW",
    "BLOCKED_PEN_SCORE_PRESENT_REQUIRES_SEPARATE_REVIEW",
    "BLOCKED_PENALTY_REASON_REQUIRES_SEPARATE_SCORE_SEMANTICS",
)

SOURCE_CAPABILITY_FULL_TIME_SCORE_MUST_REMAIN = CapabilityAvailability.NOT_CAPTURED.value
HISTORICAL_COVERAGE_MUST_REMAIN = CapabilityAvailability.UNKNOWN.value
NEXT_REQUIRED_BOUNDARY = (
    "EXECUTE_REVIEWED_FOTMOB_DATA_MATCHES_STATUS_REASON_SEMANTICS_VALIDATION"
)

_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "status_reason_semantics_execution_authorized",
        "status_reason_semantics_qualified",
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
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
PROTOCOL_SHA256 = "08bbc2d1e53cfb1268ba71745ae80d9bc32f4bfad0f02d52225df936c7634f23"
PROTOCOL_SIZE = 5602


class FotMobDataMatchesStatusReasonSemanticsProtocolError(ValueError):
    """Raised when the frozen PR90 protocol or its ancestry drifts."""


def _error(message: str) -> FotMobDataMatchesStatusReasonSemanticsProtocolError:
    return FotMobDataMatchesStatusReasonSemanticsProtocolError(message)


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
        raise _error("status.reason protocol serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _checked_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise _error("status.reason protocol safety keys mismatch")
    if any(type(flag) is not bool or flag is not False for flag in value.values()):
        raise _error("all PR90 safety values must be exact False")
    return _safety()


def _checked_reason(value: Any, expected: Mapping[str, str], label: str) -> Mapping[str, str]:
    if not isinstance(value, Mapping) or dict(value) != dict(expected):
        raise _error(f"{label} changed")
    if set(value) != {"short", "shortKey", "long", "longKey"}:
        raise _error(f"{label} keys changed")
    if any(type(item) is not str or not item for item in value.values()):
        raise _error(f"{label} values must be non-empty exact strings")
    return types.MappingProxyType(dict(expected))


def _verify_sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise _error(f"{label} must be a lowercase SHA-256")
    return value


def _verify_upstream() -> None:
    if pr83.PROTOCOL_SHA256 != PR83_PROTOCOL_SHA256 or pr83.PROTOCOL_SIZE != PR83_PROTOCOL_SIZE:
        raise _error("PR83 protocol identity constants changed")
    pr83_value = pr83.build_fotmob_data_matches_final_result_semantics_protocol()
    pr83_bytes = pr83.canonical_fotmob_data_matches_final_result_semantics_protocol_bytes(pr83_value)
    if hashlib.sha256(pr83_bytes).hexdigest() != PR83_PROTOCOL_SHA256 or len(pr83_bytes) != PR83_PROTOCOL_SIZE:
        raise _error("PR83 canonical protocol identity changed")
    if pr83.REASON_FIELD_RULE != "ANY_STATUS_REASON_REQUIRES_EXPLICIT_REVIEW_AND_CANNOT_AUTO_QUALIFY":
        raise _error("PR83 reason-field rule changed")

    if pr85.EVIDENCE_SHA256 != PR85_EVIDENCE_SHA256 or pr85.EVIDENCE_SIZE != PR85_EVIDENCE_SIZE:
        raise _error("PR85 evidence identity constants changed")
    pr85_value = pr85.build_fotmob_data_matches_post_finish_capture_pair_evidence()
    pr85_bytes = pr85.canonical_fotmob_data_matches_post_finish_capture_pair_evidence_bytes(pr85_value)
    if hashlib.sha256(pr85_bytes).hexdigest() != PR85_EVIDENCE_SHA256 or len(pr85_bytes) != PR85_EVIDENCE_SIZE:
        raise _error("PR85 canonical evidence identity changed")
    if pr85.STABLE_FINISHED_IDENTITY_SCORE_PAIR_COUNT != STABLE_FINISHED_IDENTITY_SCORE_PAIR_COUNT:
        raise _error("PR85 stable finished-pair count changed")
    if pr85.ORDINARY_FT_REASON_PAIR_COUNT != ORDINARY_FT_REASON_PAIR_COUNT:
        raise _error("PR85 ordinary FT reason count changed")
    if pr85.PENALTY_REASON_PAIR_COUNT != PENALTY_REASON_PAIR_COUNT:
        raise _error("PR85 penalty reason count changed")
    if pr85.SELECTED_REASON_SHORT != ORDINARY_FT_REASON_TUPLE["short"]:
        raise _error("PR85 reviewed ordinary FT reason changed")
    if pr85.SELECTED_REASON_SHORT_KEY != ORDINARY_FT_REASON_TUPLE["shortKey"]:
        raise _error("PR85 reviewed ordinary FT reason key changed")
    if pr85.SELECTED_REASON_LONG != ORDINARY_FT_REASON_TUPLE["long"]:
        raise _error("PR85 reviewed ordinary FT long reason changed")
    if pr85.SELECTED_REASON_LONG_KEY != ORDINARY_FT_REASON_TUPLE["longKey"]:
        raise _error("PR85 reviewed ordinary FT long reason key changed")

    if pr89.REPOSITORY_MAIN_SHA != "df6b782e0e1b36c46089333a893a12f44e40fa07":
        raise _error("PR89 implementation ancestry changed")
    if pr89.NEXT_REQUIRED_BOUNDARY != "PRE_REGISTER_REVIEWED_FOTMOB_DATA_MATCHES_STATUS_REASON_SEMANTICS_PROTOCOL":
        raise _error("PR89 next boundary changed")
    if pr89.PR85_EVIDENCE_BLOB_SHA != PR85_EVIDENCE_BLOB_SHA:
        raise _error("PR89 no longer binds PR85 evidence")

    capability = SOURCE_CAPABILITY_REGISTRY.get(CANDIDATE_SOURCE_KEY)
    if capability is None:
        raise _error("reviewed FotMob data-matches capability is missing")
    if capability.reliable_fixture_identity is not CapabilityAvailability.CONFIRMED:
        raise _error("reviewed FotMob fixture identity premise changed")
    if capability.full_time_score is not CapabilityAvailability.NOT_CAPTURED:
        raise _error("full-time-score capability changed before PR90")
    if capability.historical_coverage is not CapabilityAvailability.UNKNOWN:
        raise _error("historical-coverage capability changed before PR90")


def _payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "protocol_scope": PROTOCOL_SCOPE,
        "protocol_state": PROTOCOL_STATE,
        "repository_main_sha": REPOSITORY_MAIN_SHA,
        "candidate_source_key": CANDIDATE_SOURCE_KEY,
        "pr83_protocol_blob_sha": PR83_PROTOCOL_BLOB_SHA,
        "pr83_protocol_sha256": PR83_PROTOCOL_SHA256,
        "pr83_protocol_size": PR83_PROTOCOL_SIZE,
        "pr85_evidence_blob_sha": PR85_EVIDENCE_BLOB_SHA,
        "pr85_evidence_sha256": PR85_EVIDENCE_SHA256,
        "pr85_evidence_size": PR85_EVIDENCE_SIZE,
        "pr89_implementation_blob_sha": PR89_IMPLEMENTATION_BLOB_SHA,
        "source_capabilities_blob_sha": SOURCE_CAPABILITIES_BLOB_SHA,
        "request_date": REQUEST_DATE,
        "timezone": TIMEZONE,
        "ccode3": CCODE3,
        "first_capture_id": FIRST_CAPTURE_ID,
        "first_raw_sha256": FIRST_RAW_SHA256,
        "first_manifest_sha256": FIRST_MANIFEST_SHA256,
        "second_capture_id": SECOND_CAPTURE_ID,
        "second_raw_sha256": SECOND_RAW_SHA256,
        "second_manifest_sha256": SECOND_MANIFEST_SHA256,
        "stable_finished_identity_score_pair_count": STABLE_FINISHED_IDENTITY_SCORE_PAIR_COUNT,
        "ordinary_ft_reason_pair_count": ORDINARY_FT_REASON_PAIR_COUNT,
        "penalty_reason_pair_count": PENALTY_REASON_PAIR_COUNT,
        "ordinary_ft_reason_tuple": dict(ORDINARY_FT_REASON_TUPLE),
        "ordinary_ft_disposition": ORDINARY_FT_DISPOSITION,
        "penalty_reason_tuple": dict(PENALTY_REASON_TUPLE),
        "penalty_fixture_id": PENALTY_FIXTURE_ID,
        "penalty_home_score": PENALTY_HOME_SCORE,
        "penalty_away_score": PENALTY_AWAY_SCORE,
        "penalty_home_pen_score": PENALTY_HOME_PEN_SCORE,
        "penalty_away_pen_score": PENALTY_AWAY_PEN_SCORE,
        "penalty_eliminated_team_id": PENALTY_ELIMINATED_TEAM_ID,
        "penalty_disposition": PENALTY_DISPOSITION,
        "reason_scope_rule": REASON_SCOPE_RULE,
        "exact_tuple_rule": EXACT_TUPLE_RULE,
        "ordinary_ft_awarded_rule": ORDINARY_FT_AWARDED_RULE,
        "ordinary_ft_pen_score_rule": ORDINARY_FT_PEN_SCORE_RULE,
        "status_id_rule": STATUS_ID_RULE,
        "score_str_rule": SCORE_STR_RULE,
        "unknown_reason_rule": UNKNOWN_REASON_RULE,
        "semantic_scope_rule": SEMANTIC_SCOPE_RULE,
        "qualification_requirements": list(QUALIFICATION_REQUIREMENTS),
        "status_vocabulary": list(STATUS_VOCABULARY),
        "source_capability_full_time_score_must_remain": SOURCE_CAPABILITY_FULL_TIME_SCORE_MUST_REMAIN,
        "historical_coverage_must_remain": HISTORICAL_COVERAGE_MUST_REMAIN,
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": dict(_safety()),
    }


@dataclasses.dataclass(frozen=True)
class FotMobDataMatchesStatusReasonSemanticsProtocol:
    schema_version: int
    protocol_id: str
    protocol_scope: str
    protocol_state: str
    repository_main_sha: str
    candidate_source_key: str
    pr83_protocol_blob_sha: str
    pr83_protocol_sha256: str
    pr83_protocol_size: int
    pr85_evidence_blob_sha: str
    pr85_evidence_sha256: str
    pr85_evidence_size: int
    pr89_implementation_blob_sha: str
    source_capabilities_blob_sha: str
    request_date: str
    timezone: str
    ccode3: str
    first_capture_id: str
    first_raw_sha256: str
    first_manifest_sha256: str
    second_capture_id: str
    second_raw_sha256: str
    second_manifest_sha256: str
    stable_finished_identity_score_pair_count: int
    ordinary_ft_reason_pair_count: int
    penalty_reason_pair_count: int
    ordinary_ft_reason_tuple: Mapping[str, str]
    ordinary_ft_disposition: str
    penalty_reason_tuple: Mapping[str, str]
    penalty_fixture_id: int
    penalty_home_score: int
    penalty_away_score: int
    penalty_home_pen_score: int
    penalty_away_pen_score: int
    penalty_eliminated_team_id: int
    penalty_disposition: str
    reason_scope_rule: str
    exact_tuple_rule: str
    ordinary_ft_awarded_rule: str
    ordinary_ft_pen_score_rule: str
    status_id_rule: str
    score_str_rule: str
    unknown_reason_rule: str
    semantic_scope_rule: str
    qualification_requirements: tuple[str, ...]
    status_vocabulary: tuple[str, ...]
    source_capability_full_time_score_must_remain: str
    historical_coverage_must_remain: str
    next_required_boundary: str
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise _error("schema_version must be exact integer 1")
        for label, value in (
            ("pr83_protocol_sha256", self.pr83_protocol_sha256),
            ("pr85_evidence_sha256", self.pr85_evidence_sha256),
            ("first_raw_sha256", self.first_raw_sha256),
            ("first_manifest_sha256", self.first_manifest_sha256),
            ("second_raw_sha256", self.second_raw_sha256),
            ("second_manifest_sha256", self.second_manifest_sha256),
        ):
            _verify_sha(value, label)
        for label, value in (
            ("stable_finished_identity_score_pair_count", self.stable_finished_identity_score_pair_count),
            ("ordinary_ft_reason_pair_count", self.ordinary_ft_reason_pair_count),
            ("penalty_reason_pair_count", self.penalty_reason_pair_count),
            ("penalty_fixture_id", self.penalty_fixture_id),
            ("penalty_eliminated_team_id", self.penalty_eliminated_team_id),
        ):
            if type(value) is not int or value < 1:
                raise _error(f"{label} must be an exact positive integer")
        for label, value in (
            ("penalty_home_score", self.penalty_home_score),
            ("penalty_away_score", self.penalty_away_score),
            ("penalty_home_pen_score", self.penalty_home_pen_score),
            ("penalty_away_pen_score", self.penalty_away_pen_score),
        ):
            if type(value) is not int or value < 0:
                raise _error(f"{label} must be an exact nonnegative integer")
        object.__setattr__(
            self,
            "ordinary_ft_reason_tuple",
            _checked_reason(self.ordinary_ft_reason_tuple, ORDINARY_FT_REASON_TUPLE, "ordinary FT reason tuple"),
        )
        object.__setattr__(
            self,
            "penalty_reason_tuple",
            _checked_reason(self.penalty_reason_tuple, PENALTY_REASON_TUPLE, "penalty reason tuple"),
        )
        object.__setattr__(self, "safety", _checked_safety(self.safety))
        if self.qualification_requirements != QUALIFICATION_REQUIREMENTS:
            raise _error("qualification requirements changed")
        if self.status_vocabulary != STATUS_VOCABULARY:
            raise _error("status vocabulary changed")
        if self.next_required_boundary != NEXT_REQUIRED_BOUNDARY:
            raise _error("next boundary changed")
        if self.to_dict() != _payload():
            raise _error("status.reason protocol differs from frozen PR90 payload")

    def to_dict(self) -> dict[str, Any]:
        result = {
            field.name: getattr(self, field.name)
            for field in dataclasses.fields(self)
            if field.name not in {"ordinary_ft_reason_tuple", "penalty_reason_tuple", "safety"}
        }
        result["ordinary_ft_reason_tuple"] = dict(self.ordinary_ft_reason_tuple)
        result["penalty_reason_tuple"] = dict(self.penalty_reason_tuple)
        result["qualification_requirements"] = list(self.qualification_requirements)
        result["status_vocabulary"] = list(self.status_vocabulary)
        result["safety"] = dict(self.safety)
        return result


def build_fotmob_data_matches_status_reason_semantics_protocol() -> FotMobDataMatchesStatusReasonSemanticsProtocol:
    _verify_upstream()
    payload = _payload()
    value = FotMobDataMatchesStatusReasonSemanticsProtocol(
        **{
            **payload,
            "ordinary_ft_reason_tuple": types.MappingProxyType(dict(payload["ordinary_ft_reason_tuple"])),
            "penalty_reason_tuple": types.MappingProxyType(dict(payload["penalty_reason_tuple"])),
            "qualification_requirements": tuple(payload["qualification_requirements"]),
            "status_vocabulary": tuple(payload["status_vocabulary"]),
            "safety": _safety(),
        }
    )
    exact = canonical_fotmob_data_matches_status_reason_semantics_protocol_bytes(value)
    if hashlib.sha256(exact).hexdigest() != PROTOCOL_SHA256 or len(exact) != PROTOCOL_SIZE:
        raise _error("PR90 status.reason protocol canonical identity changed")
    return value


def canonical_fotmob_data_matches_status_reason_semantics_protocol_bytes(
    value: FotMobDataMatchesStatusReasonSemanticsProtocol,
) -> bytes:
    if not isinstance(value, FotMobDataMatchesStatusReasonSemanticsProtocol):
        raise _error("status.reason protocol value has wrong type")
    return _canonical(value.to_dict())


def revalidate_fotmob_data_matches_status_reason_semantics_protocol(
    value: FotMobDataMatchesStatusReasonSemanticsProtocol,
) -> FotMobDataMatchesStatusReasonSemanticsProtocol:
    if not isinstance(value, FotMobDataMatchesStatusReasonSemanticsProtocol):
        raise _error("status.reason protocol value has wrong type")
    expected = build_fotmob_data_matches_status_reason_semantics_protocol()
    if canonical_fotmob_data_matches_status_reason_semantics_protocol_bytes(value) != canonical_fotmob_data_matches_status_reason_semantics_protocol_bytes(expected):
        raise _error("status.reason protocol changed")
    return expected


__all__ = [
    "CANDIDATE_SOURCE_KEY",
    "NEXT_REQUIRED_BOUNDARY",
    "ORDINARY_FT_REASON_TUPLE",
    "ORDINARY_FT_REASON_PAIR_COUNT",
    "PENALTY_REASON_TUPLE",
    "PENALTY_REASON_PAIR_COUNT",
    "PROTOCOL_ID",
    "PROTOCOL_SCOPE",
    "PROTOCOL_STATE",
    "PROTOCOL_SHA256",
    "PROTOCOL_SIZE",
    "QUALIFICATION_REQUIREMENTS",
    "REPOSITORY_MAIN_SHA",
    "STABLE_FINISHED_IDENTITY_SCORE_PAIR_COUNT",
    "STATUS_VOCABULARY",
    "FotMobDataMatchesStatusReasonSemanticsProtocol",
    "FotMobDataMatchesStatusReasonSemanticsProtocolError",
    "build_fotmob_data_matches_status_reason_semantics_protocol",
    "canonical_fotmob_data_matches_status_reason_semantics_protocol_bytes",
    "revalidate_fotmob_data_matches_status_reason_semantics_protocol",
]
