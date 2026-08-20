"""Exact-observation review and extraction for repeated FotMob player records.

This boundary extends, but does not weaken, PR54: ordinary scalar review still
rejects wildcards.  Array semantics exist only inside an exact PR52/PR53 replay
and an explicit human review of one observed repeated-record structure.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import enum
import hashlib
import json
import math
import re
import types
from typing import Any, Mapping

from domain.fotmob_reviewed_match_details_persisted_evidence import (
    VerifiedPersistedFotMobMatchDetailsEvidence,
)
from domain.fotmob_reviewed_match_details_structure import (
    FotMobReviewedMatchDetailsStructureAssessment,
    FotMobReviewedMatchDetailsStructureError,
    JsonValueKind,
    _strict_response_json,
    assess_reviewed_match_details_structure,
    canonical_reviewed_match_details_structure_bytes,
)
from domain.fotmob_team_strength_fixture_intelligence import (
    LineupState,
    PositionGroup,
    TeamSide,
)


SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-reviewed-match-details-array-records-v1"
REVIEW_SCOPE = "EXACT_OBSERVATION_ONLY"
FRESHNESS_RULE = "EXPLICIT_FRESH_UNTIL_INCLUSIVE"
MAX_POINTER_LENGTH = 2048
_SHA = re.compile(r"^[0-9a-f]{64}$")
_SCALAR_KINDS = frozenset(
    {JsonValueKind.BOOLEAN, JsonValueKind.INTEGER, JsonValueKind.NUMBER, JsonValueKind.STRING}
)
_SAFETY = tuple(
    sorted(
        {
            "bet_authorized": False,
            "network_acquisition_authorized": False,
            "pricing_authorized": False,
            "probability_adjustment_authorized": False,
            "probability_inference_authorized": False,
            "production_approval_authorized": False,
            "selection_authorized": False,
            "source_wide_qualification_authorized": False,
            "team_strength_feature_authorized": False,
        }.items()
    )
)


class ReviewedMatchDetailsArrayRecordsError(ValueError):
    pass


class ArrayRecordSetScope(str, enum.Enum):
    STARTING_XI = "TARGET_STARTING_XI"
    BENCH = "TARGET_BENCH"
    UNAVAILABLE = "TARGET_UNAVAILABLE"


class ArraySemanticRole(str, enum.Enum):
    PLAYER_ID = "PLAYER_ID"
    TEAM_ID = "TEAM_ID"
    IS_HOME_TEAM = "IS_HOME_TEAM"
    SOURCE_POSITION = "SOURCE_POSITION"
    UNAVAILABLE_REASON = "UNAVAILABLE_REASON"


class ArrayReviewQualification(str, enum.Enum):
    QUALIFIED = "QUALIFIED"
    REJECTED = "REJECTED"


class ReviewedArrayEvidenceStatus(str, enum.Enum):
    SUPPORTED = "SUPPORTED"
    STALE = "STALE"
    CONFLICTED = "CONFLICTED"
    UNVERIFIED = "UNVERIFIED"


class ReviewedCompletenessDisposition(str, enum.Enum):
    REVIEWED_COMPLETE_EXACT_OBSERVATION = "REVIEWED_COMPLETE_EXACT_OBSERVATION"


def _utc(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, dt.datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ReviewedMatchDetailsArrayRecordsError(f"{label} must be timezone-aware datetime")
    return value.astimezone(dt.timezone.utc)


def _text(value: Any, label: str, maximum: int = 2048) -> str:
    if type(value) is not str or not value or value != value.strip() or len(value) > maximum:
        raise ReviewedMatchDetailsArrayRecordsError(f"{label} must be exact non-empty text")
    return value


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        raise ReviewedMatchDetailsArrayRecordsError(f"{label} must be lowercase SHA-256")
    return value


def _identity(value: Any, label: str) -> str | int:
    if type(value) is int:
        return value
    if type(value) is str and value and value == value.strip():
        return value
    raise ReviewedMatchDetailsArrayRecordsError(f"{label} must be exact string or integer identity")


def _json_scalar(value: Any, label: str) -> str | int | float | bool:
    if type(value) not in (str, int, float, bool):
        raise ReviewedMatchDetailsArrayRecordsError(f"{label} must be exact JSON scalar")
    if type(value) is float and not math.isfinite(value):
        raise ReviewedMatchDetailsArrayRecordsError(f"{label} must be finite")
    return value


def _kind(value: Any) -> JsonValueKind:
    if type(value) is bool:
        return JsonValueKind.BOOLEAN
    if type(value) is int:
        return JsonValueKind.INTEGER
    if type(value) is float:
        if not math.isfinite(value):
            raise ReviewedMatchDetailsArrayRecordsError("record member number must be finite")
        return JsonValueKind.NUMBER
    if type(value) is str:
        return JsonValueKind.STRING
    if type(value) is list:
        return JsonValueKind.ARRAY
    if type(value) is dict:
        return JsonValueKind.OBJECT
    if value is None:
        return JsonValueKind.NULL
    raise ReviewedMatchDetailsArrayRecordsError("unsupported JSON value")


def _pointer(value: Any, label: str, *, wildcard_required: bool = False) -> str:
    value = _text(value, label, MAX_POINTER_LENGTH)
    if not value.startswith("/"):
        raise ReviewedMatchDetailsArrayRecordsError(f"{label} must be non-root JSON pointer")
    if wildcard_required and "/*" not in value:
        raise ReviewedMatchDetailsArrayRecordsError(f"{label} must contain reviewed array wildcard")
    return value


def _unescape(token: str) -> str:
    if re.search(r"~(?![012])", token):
        raise ReviewedMatchDetailsArrayRecordsError("JSON pointer token is not canonical")
    return token.replace("~2", "*").replace("~1", "/").replace("~0", "~")


def _tokens(pointer: str) -> tuple[str, ...]:
    return tuple("*" if token == "*" else _unescape(token) for token in pointer.split("/")[1:])


def _traverse(payload: Any, pointer: str) -> tuple[tuple[tuple[int, ...], Any], ...]:
    current: list[tuple[tuple[int, ...], Any]] = [((), payload)]
    for token in _tokens(pointer):
        following: list[tuple[tuple[int, ...], Any]] = []
        for coordinate, value in current:
            if token == "*":
                if type(value) is not list:
                    raise ReviewedMatchDetailsArrayRecordsError("wildcard traversal did not encounter array")
                following.extend((coordinate + (index,), item) for index, item in enumerate(value))
            else:
                if type(value) is not dict or token not in value:
                    raise ReviewedMatchDetailsArrayRecordsError("reviewed pointer missing during raw replay")
                following.append((coordinate, value[token]))
        current = following
    return tuple(current)


def _relative(record: dict[str, Any], record_pattern: str, member_pattern: str) -> Any:
    record_tokens = _tokens(record_pattern)
    member_tokens = _tokens(member_pattern)
    if member_tokens[: len(record_tokens)] != record_tokens:
        raise ReviewedMatchDetailsArrayRecordsError("member pointer is outside reviewed record pattern")
    value: Any = record
    for token in member_tokens[len(record_tokens) :]:
        if token == "*" or type(value) is not dict or token not in value:
            raise ReviewedMatchDetailsArrayRecordsError("record member pointer is not exact scalar member")
        value = value[token]
    return value


def _canonical(value: Any) -> bytes:
    try:
        return (
            json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ReviewedMatchDetailsArrayRecordsError("canonical JSON serialization failed") from exc


def _scalar_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


@dataclasses.dataclass(frozen=True)
class ArrayRecordMemberReview:
    role: ArraySemanticRole
    pointer_pattern: str
    expected_kind: JsonValueKind

    def __post_init__(self) -> None:
        if type(self.role) is not ArraySemanticRole or type(self.expected_kind) is not JsonValueKind:
            raise ReviewedMatchDetailsArrayRecordsError("member review enum drift")
        object.__setattr__(self, "pointer_pattern", _pointer(self.pointer_pattern, "member pointer", wildcard_required=True))
        if self.expected_kind not in _SCALAR_KINDS:
            raise ReviewedMatchDetailsArrayRecordsError("reviewed record members must be non-null scalars")

    def to_dict(self) -> dict[str, Any]:
        return {"role": self.role.value, "pointer_pattern": self.pointer_pattern, "expected_kind": self.expected_kind.value}


@dataclasses.dataclass(frozen=True)
class LineupStateReviewMapping:
    source_value: str | int | float | bool
    lineup_state: LineupState

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_value", _json_scalar(self.source_value, "lineup source value"))
        if type(self.lineup_state) is not LineupState:
            raise ReviewedMatchDetailsArrayRecordsError("lineup state mapping drift")

    def to_dict(self) -> dict[str, Any]:
        return {"source_value": self.source_value, "lineup_state": self.lineup_state.value}


@dataclasses.dataclass(frozen=True)
class SourcePositionReviewMapping:
    source_value: str
    position_group: PositionGroup

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_value", _text(self.source_value, "source position", 128))
        if type(self.position_group) is not PositionGroup:
            raise ReviewedMatchDetailsArrayRecordsError("position mapping drift")

    def to_dict(self) -> dict[str, Any]:
        return {"source_value": self.source_value, "position_group": self.position_group.value}


@dataclasses.dataclass(frozen=True)
class ArrayRecordSetReviewDecision:
    scope: ArrayRecordSetScope
    array_root_pointer: str
    record_pointer_pattern: str
    team_side: TeamSide
    source_team_id: str | int
    team_id_pointer: str
    team_id_kind: JsonValueKind
    is_home_pointer: str
    lineup_state_pointer: str | None
    lineup_state_kind: JsonValueKind | None
    member_reviews: tuple[ArrayRecordMemberReview, ...]
    qualification: ArrayReviewQualification
    completeness_attested: bool
    fresh_until: dt.datetime
    notes: str

    def __post_init__(self) -> None:
        if type(self.scope) is not ArrayRecordSetScope or type(self.team_side) is not TeamSide:
            raise ReviewedMatchDetailsArrayRecordsError("record-set scope/team-side drift")
        object.__setattr__(self, "array_root_pointer", _pointer(self.array_root_pointer, "array root"))
        object.__setattr__(self, "record_pointer_pattern", _pointer(self.record_pointer_pattern, "record pattern", wildcard_required=True))
        if self.record_pointer_pattern != self.array_root_pointer + "/*":
            raise ReviewedMatchDetailsArrayRecordsError("record pattern must be exact child of reviewed array root")
        object.__setattr__(self, "source_team_id", _identity(self.source_team_id, "source_team_id"))
        object.__setattr__(self, "team_id_pointer", _pointer(self.team_id_pointer, "team id pointer"))
        object.__setattr__(self, "is_home_pointer", _pointer(self.is_home_pointer, "is-home pointer"))
        if "/*" in self.team_id_pointer or "/*" in self.is_home_pointer:
            raise ReviewedMatchDetailsArrayRecordsError("team identity pointers must resolve exactly once")
        if type(self.team_id_kind) is not JsonValueKind or self.team_id_kind not in {JsonValueKind.INTEGER, JsonValueKind.STRING}:
            raise ReviewedMatchDetailsArrayRecordsError("team id kind must be integer or string")
        if self.lineup_state_pointer is None:
            if self.lineup_state_kind is not None:
                raise ReviewedMatchDetailsArrayRecordsError("lineup state kind requires pointer")
        else:
            object.__setattr__(self, "lineup_state_pointer", _pointer(self.lineup_state_pointer, "lineup state pointer"))
            if "/*" in self.lineup_state_pointer or self.lineup_state_kind not in _SCALAR_KINDS:
                raise ReviewedMatchDetailsArrayRecordsError("lineup state pointer must resolve one scalar")
        if type(self.member_reviews) is not tuple or any(type(item) is not ArrayRecordMemberReview for item in self.member_reviews):
            raise ReviewedMatchDetailsArrayRecordsError("member reviews must be exact immutable tuple")
        roles = tuple(item.role for item in self.member_reviews)
        if len(roles) != len(set(roles)):
            raise ReviewedMatchDetailsArrayRecordsError("record semantic roles must be unique")
        if any(not item.pointer_pattern.startswith(self.record_pointer_pattern + "/") for item in self.member_reviews):
            raise ReviewedMatchDetailsArrayRecordsError("member review is outside record pattern")
        if any("/*" in item.pointer_pattern[len(self.record_pointer_pattern) :] for item in self.member_reviews):
            raise ReviewedMatchDetailsArrayRecordsError("nested unreviewed member arrays are forbidden")
        if type(self.qualification) is not ArrayReviewQualification or type(self.completeness_attested) is not bool:
            raise ReviewedMatchDetailsArrayRecordsError("qualification/completeness type drift")
        if self.qualification is ArrayReviewQualification.REJECTED and self.completeness_attested:
            raise ReviewedMatchDetailsArrayRecordsError("rejected record set cannot attest completeness")
        object.__setattr__(self, "fresh_until", _utc(self.fresh_until, "fresh_until"))
        object.__setattr__(self, "notes", _text(self.notes, "notes", 1024))

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope.value,
            "array_root_pointer": self.array_root_pointer,
            "record_pointer_pattern": self.record_pointer_pattern,
            "team_side": self.team_side.value,
            "source_team_id": self.source_team_id,
            "team_id_pointer": self.team_id_pointer,
            "team_id_kind": self.team_id_kind.value,
            "is_home_pointer": self.is_home_pointer,
            "lineup_state_pointer": self.lineup_state_pointer,
            "lineup_state_kind": None if self.lineup_state_kind is None else self.lineup_state_kind.value,
            "member_reviews": [item.to_dict() for item in self.member_reviews],
            "qualification": self.qualification.value,
            "completeness_attested": self.completeness_attested,
            "fresh_until": self.fresh_until.isoformat().replace("+00:00", "Z"),
            "freshness_rule": FRESHNESS_RULE,
            "notes": self.notes,
        }


@dataclasses.dataclass(frozen=True)
class ReviewedExtractedPlayerRecord:
    scope: ArrayRecordSetScope
    team_side: TeamSide
    source_team_id: str | int
    provider_player_id: str | int
    source_coordinate: tuple[int, ...]
    source_position: str | None
    unavailable_reason: str | None
    lineup_state: LineupState
    evidence_status: ReviewedArrayEvidenceStatus
    fresh_until: dt.datetime
    record_pointer_pattern: str
    evidence_sha256: str

    def __post_init__(self) -> None:
        if type(self.scope) is not ArrayRecordSetScope or type(self.team_side) is not TeamSide:
            raise ReviewedMatchDetailsArrayRecordsError("extracted record enum drift")
        object.__setattr__(self, "source_team_id", _identity(self.source_team_id, "source_team_id"))
        object.__setattr__(self, "provider_player_id", _identity(self.provider_player_id, "provider_player_id"))
        if type(self.source_coordinate) is not tuple or not self.source_coordinate or any(type(x) is not int or x < 0 for x in self.source_coordinate):
            raise ReviewedMatchDetailsArrayRecordsError("source coordinate must preserve exact array indexes")
        if self.source_position is not None: object.__setattr__(self, "source_position", _text(self.source_position, "source_position", 128))
        if self.unavailable_reason is not None: object.__setattr__(self, "unavailable_reason", _text(self.unavailable_reason, "unavailable_reason", 512))
        if type(self.lineup_state) is not LineupState or type(self.evidence_status) is not ReviewedArrayEvidenceStatus:
            raise ReviewedMatchDetailsArrayRecordsError("extracted semantic status drift")
        object.__setattr__(self, "fresh_until", _utc(self.fresh_until, "fresh_until"))
        object.__setattr__(self, "record_pointer_pattern", _pointer(self.record_pointer_pattern, "record pattern", wildcard_required=True))
        _sha(self.evidence_sha256, "record evidence_sha256")

    def identity_key(self) -> tuple[str, str, str]:
        return (self.team_side.value, _scalar_key(self.provider_player_id), self.scope.value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope.value,
            "team_side": self.team_side.value,
            "source_team_id": self.source_team_id,
            "provider_player_id": self.provider_player_id,
            "source_coordinate": list(self.source_coordinate),
            "source_position": self.source_position,
            "unavailable_reason": self.unavailable_reason,
            "lineup_state": self.lineup_state.value,
            "evidence_status": self.evidence_status.value,
            "fresh_until": self.fresh_until.isoformat().replace("+00:00", "Z"),
            "record_pointer_pattern": self.record_pointer_pattern,
            "evidence_sha256": self.evidence_sha256,
        }


@dataclasses.dataclass(frozen=True)
class ReviewedArrayCompletenessReceipt:
    provider: str
    source_dataset_name: str
    scope: ArrayRecordSetScope
    team_side: TeamSide
    source_team_id: str | int
    fixture_identifier: str
    source_match_id: str
    as_of: dt.datetime
    raw_sha256: str
    array_root_pointer: str
    record_pointer_pattern: str
    provider_player_ids: tuple[str | int, ...]
    record_count: int
    disposition: ReviewedCompletenessDisposition
    evidence_sha256s: tuple[str, ...]
    evidence_sha256: str

    def __post_init__(self) -> None:
        if self.provider != "FOTMOB" or self.source_dataset_name != DATASET_NAME:
            raise ReviewedMatchDetailsArrayRecordsError("completeness source identity drift")
        if type(self.scope) is not ArrayRecordSetScope or type(self.team_side) is not TeamSide:
            raise ReviewedMatchDetailsArrayRecordsError("completeness enum drift")
        object.__setattr__(self, "source_team_id", _identity(self.source_team_id, "source_team_id"))
        _text(self.fixture_identifier, "fixture_identifier", 256); _text(self.source_match_id, "source_match_id", 128)
        object.__setattr__(self, "as_of", _utc(self.as_of, "as_of"))
        _sha(self.raw_sha256, "raw_sha256")
        object.__setattr__(self, "array_root_pointer", _pointer(self.array_root_pointer, "array root"))
        object.__setattr__(self, "record_pointer_pattern", _pointer(self.record_pointer_pattern, "record pattern", wildcard_required=True))
        if type(self.provider_player_ids) is not tuple:
            raise ReviewedMatchDetailsArrayRecordsError("completeness player IDs must be immutable tuple")
        for value in self.provider_player_ids: _identity(value, "provider_player_id")
        expected = tuple(sorted(set(self.provider_player_ids), key=_scalar_key))
        if self.provider_player_ids != expected:
            raise ReviewedMatchDetailsArrayRecordsError("completeness player IDs must be unique and identity-sorted")
        if type(self.record_count) is not int or self.record_count != len(self.provider_player_ids):
            raise ReviewedMatchDetailsArrayRecordsError("completeness record count must equal exact identity set")
        if type(self.disposition) is not ReviewedCompletenessDisposition:
            raise ReviewedMatchDetailsArrayRecordsError("completeness disposition drift")
        if type(self.evidence_sha256s) is not tuple or self.evidence_sha256s != tuple(sorted(set(self.evidence_sha256s))) or not self.evidence_sha256s:
            raise ReviewedMatchDetailsArrayRecordsError("completeness evidence set must be nonempty sorted SHA tuple")
        for value in self.evidence_sha256s: _sha(value, "completeness evidence SHA")
        if self.raw_sha256 not in self.evidence_sha256s:
            raise ReviewedMatchDetailsArrayRecordsError("raw SHA must remain in completeness evidence set")
        _sha(self.evidence_sha256, "completeness evidence_sha256")

    def identity_key(self) -> tuple[str, str]:
        return (self.team_side.value, self.scope.value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "source_dataset_name": self.source_dataset_name,
            "scope": self.scope.value,
            "team_side": self.team_side.value,
            "source_team_id": self.source_team_id,
            "fixture_identifier": self.fixture_identifier,
            "source_match_id": self.source_match_id,
            "as_of": self.as_of.isoformat().replace("+00:00", "Z"),
            "raw_sha256": self.raw_sha256,
            "array_root_pointer": self.array_root_pointer,
            "record_pointer_pattern": self.record_pointer_pattern,
            "provider_player_ids": list(self.provider_player_ids),
            "record_count": self.record_count,
            "disposition": self.disposition.value,
            "evidence_sha256s": list(self.evidence_sha256s),
            "evidence_sha256": self.evidence_sha256,
        }


@dataclasses.dataclass(frozen=True)
class ReviewedMatchDetailsArrayRecords:
    schema_version: int
    dataset_name: str
    review_scope: str
    structure_sha256: str
    evidence_receipt_sha256: str
    manifest_sha256: str
    raw_sha256: str
    raw_size: int
    fixture_identifier: str
    source_match_id: str
    kickoff: dt.datetime
    observed_at: dt.datetime
    reviewed_at: dt.datetime
    classified_at: dt.datetime
    reviewer_reference: str
    decisions: tuple[ArrayRecordSetReviewDecision, ...]
    lineup_state_mappings: tuple[LineupStateReviewMapping, ...]
    position_mappings: tuple[SourcePositionReviewMapping, ...]
    records: tuple[ReviewedExtractedPlayerRecord, ...]
    completeness_receipts: tuple[ReviewedArrayCompletenessReceipt, ...]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if (self.schema_version, self.dataset_name, self.review_scope) != (SCHEMA_VERSION, DATASET_NAME, REVIEW_SCOPE):
            raise ReviewedMatchDetailsArrayRecordsError("array artifact identity drift")
        for label in ("structure_sha256", "evidence_receipt_sha256", "manifest_sha256", "raw_sha256"):
            _sha(getattr(self, label), label)
        if type(self.raw_size) is not int or self.raw_size <= 0:
            raise ReviewedMatchDetailsArrayRecordsError("raw_size must be positive integer")
        _text(self.fixture_identifier, "fixture_identifier", 256); _text(self.source_match_id, "source_match_id", 128)
        for label in ("kickoff", "observed_at", "reviewed_at", "classified_at"):
            object.__setattr__(self, label, _utc(getattr(self, label), label))
        if not self.observed_at <= self.reviewed_at <= self.classified_at < self.kickoff:
            raise ReviewedMatchDetailsArrayRecordsError("review/classification chronology drift")
        object.__setattr__(self, "reviewer_reference", _text(self.reviewer_reference, "reviewer_reference", 256))
        exact_types = (
            (self.decisions, ArrayRecordSetReviewDecision),
            (self.lineup_state_mappings, LineupStateReviewMapping),
            (self.position_mappings, SourcePositionReviewMapping),
            (self.records, ReviewedExtractedPlayerRecord),
            (self.completeness_receipts, ReviewedArrayCompletenessReceipt),
        )
        if any(type(values) is not tuple or any(type(item) is not expected for item in values) for values, expected in exact_types):
            raise ReviewedMatchDetailsArrayRecordsError("array artifact nested type drift")
        if self.decisions != tuple(sorted(self.decisions, key=lambda x: (x.team_side.value, x.scope.value, x.array_root_pointer))):
            raise ReviewedMatchDetailsArrayRecordsError("array decisions must be deterministically sorted")
        if self.records != tuple(sorted(self.records, key=lambda x: x.identity_key())):
            raise ReviewedMatchDetailsArrayRecordsError("extracted records must be identity-sorted")
        if self.completeness_receipts != tuple(sorted(self.completeness_receipts, key=lambda x: x.identity_key())):
            raise ReviewedMatchDetailsArrayRecordsError("completeness receipts must be sorted")
        if len({_scalar_key(x.provider_player_id) for x in self.records}) != len(self.records):
            raise ReviewedMatchDetailsArrayRecordsError(
                "provider player identity must be unique across the exact fixture observation"
            )
        if tuple(self.safety.items()) != _SAFETY:
            raise ReviewedMatchDetailsArrayRecordsError("array artifact safety drift")

    def to_dict(self) -> dict[str, Any]:
        iso = lambda value: value.isoformat().replace("+00:00", "Z")
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "review_scope": self.review_scope,
            "structure_sha256": self.structure_sha256,
            "evidence_receipt_sha256": self.evidence_receipt_sha256,
            "manifest_sha256": self.manifest_sha256,
            "raw_sha256": self.raw_sha256,
            "raw_size": self.raw_size,
            "fixture_identifier": self.fixture_identifier,
            "source_match_id": self.source_match_id,
            "kickoff": iso(self.kickoff),
            "observed_at": iso(self.observed_at),
            "reviewed_at": iso(self.reviewed_at),
            "classified_at": iso(self.classified_at),
            "reviewer_reference": self.reviewer_reference,
            "decisions": [item.to_dict() for item in self.decisions],
            "lineup_state_mappings": [item.to_dict() for item in self.lineup_state_mappings],
            "position_mappings": [item.to_dict() for item in self.position_mappings],
            "records": [item.to_dict() for item in self.records],
            "completeness_receipts": [item.to_dict() for item in self.completeness_receipts],
            "safety": dict(self.safety),
        }


def _rebuild_structure(
    *, evidence: Any, evidence_receipt_bytes: Any, manifest_bytes: Any, raw_bytes: Any,
    assessment: Any, assessment_bytes: Any,
) -> tuple[VerifiedPersistedFotMobMatchDetailsEvidence, FotMobReviewedMatchDetailsStructureAssessment, bytes]:
    if type(evidence) is not VerifiedPersistedFotMobMatchDetailsEvidence:
        raise ReviewedMatchDetailsArrayRecordsError("evidence must be exact PR52 receipt")
    if type(assessment) is not FotMobReviewedMatchDetailsStructureAssessment or type(assessment_bytes) is not bytes:
        raise ReviewedMatchDetailsArrayRecordsError("assessment and bytes must be exact PR53 values")
    try:
        supplied = canonical_reviewed_match_details_structure_bytes(assessment)
        rebuilt = assess_reviewed_match_details_structure(
            evidence=evidence,
            evidence_receipt_bytes=evidence_receipt_bytes,
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
        )
        rebuilt_bytes = canonical_reviewed_match_details_structure_bytes(rebuilt)
    except FotMobReviewedMatchDetailsStructureError as exc:
        raise ReviewedMatchDetailsArrayRecordsError("PR52/53 replay failed") from exc
    if supplied != rebuilt_bytes or assessment_bytes != rebuilt_bytes:
        raise ReviewedMatchDetailsArrayRecordsError("PR53 assessment object/bytes differ from exact replay")
    return evidence, rebuilt, rebuilt_bytes


def build_reviewed_match_details_array_records(
    *, evidence: Any, evidence_receipt_bytes: Any, manifest_bytes: Any, raw_bytes: Any,
    assessment: Any, assessment_bytes: Any, decisions: Any, lineup_state_mappings: Any,
    position_mappings: Any, reviewed_at: Any, classified_at: Any, reviewer_reference: Any,
) -> ReviewedMatchDetailsArrayRecords:
    evidence, rebuilt, exact_assessment_bytes = _rebuild_structure(
        evidence=evidence, evidence_receipt_bytes=evidence_receipt_bytes,
        manifest_bytes=manifest_bytes, raw_bytes=raw_bytes,
        assessment=assessment, assessment_bytes=assessment_bytes,
    )
    reviewed_at = _utc(reviewed_at, "reviewed_at"); classified_at = _utc(classified_at, "classified_at")
    if not evidence.observed_at <= reviewed_at <= classified_at < evidence.kickoff:
        raise ReviewedMatchDetailsArrayRecordsError("reviewed_at/classified_at must be prospective")
    reviewer_reference = _text(reviewer_reference, "reviewer_reference", 256)
    if type(decisions) is not tuple or not decisions or any(type(x) is not ArrayRecordSetReviewDecision for x in decisions):
        raise ReviewedMatchDetailsArrayRecordsError("decisions must be nonempty exact immutable tuple")
    if type(lineup_state_mappings) is not tuple or any(type(x) is not LineupStateReviewMapping for x in lineup_state_mappings):
        raise ReviewedMatchDetailsArrayRecordsError("lineup mappings must be exact tuple")
    if type(position_mappings) is not tuple or any(type(x) is not SourcePositionReviewMapping for x in position_mappings):
        raise ReviewedMatchDetailsArrayRecordsError("position mappings must be exact tuple")
    decisions = tuple(sorted((dataclasses.replace(x, member_reviews=tuple(dataclasses.replace(y) for y in x.member_reviews)) for x in decisions), key=lambda x: (x.team_side.value, x.scope.value, x.array_root_pointer)))
    if len({(x.team_side, x.scope) for x in decisions}) != len(decisions):
        raise ReviewedMatchDetailsArrayRecordsError("one exact decision is required per team-side record scope")
    if {x.team_side for x in decisions} != {TeamSide.HOME, TeamSide.AWAY}:
        raise ReviewedMatchDetailsArrayRecordsError("review must bind both exact fixture team sides")
    if any(x.fresh_until < evidence.observed_at for x in decisions):
        raise ReviewedMatchDetailsArrayRecordsError("fresh_until cannot predate source observation")
    lineup_state_mappings = tuple(sorted((dataclasses.replace(x) for x in lineup_state_mappings), key=lambda x: _scalar_key(x.source_value)))
    position_mappings = tuple(sorted((dataclasses.replace(x) for x in position_mappings), key=lambda x: x.source_value))
    if len({_scalar_key(x.source_value) for x in lineup_state_mappings}) != len(lineup_state_mappings):
        raise ReviewedMatchDetailsArrayRecordsError("duplicate lineup-state source mapping")
    if len({x.source_value for x in position_mappings}) != len(position_mappings):
        raise ReviewedMatchDetailsArrayRecordsError("duplicate source-position mapping")
    lineup_map = {_scalar_key(x.source_value): x.lineup_state for x in lineup_state_mappings}
    fields = {field.json_pointer: field for field in rebuilt.fields}
    payload = _strict_response_json(raw_bytes)
    extracted: list[ReviewedExtractedPlayerRecord] = []
    completeness: list[ReviewedArrayCompletenessReceipt] = []
    observed_lineup_values: set[str] = set()
    observed_positions: set[str] = set()
    for decision in decisions:
        root_field = fields.get(decision.array_root_pointer)
        if root_field is None or root_field.kinds != (JsonValueKind.ARRAY,):
            raise ReviewedMatchDetailsArrayRecordsError("reviewed array root was not exact PR53 ARRAY")
        team_field = fields.get(decision.team_id_pointer)
        home_field = fields.get(decision.is_home_pointer)
        if team_field is None or team_field.kinds != (decision.team_id_kind,):
            raise ReviewedMatchDetailsArrayRecordsError("reviewed team-id pointer/kind not exact PR53 scalar")
        if home_field is None or home_field.kinds != (JsonValueKind.BOOLEAN,):
            raise ReviewedMatchDetailsArrayRecordsError("reviewed team-side pointer is not exact PR53 boolean")
        team_values = _traverse(payload, decision.team_id_pointer)
        home_values = _traverse(payload, decision.is_home_pointer)
        if len(team_values) != 1 or team_values[0][1] != decision.source_team_id:
            raise ReviewedMatchDetailsArrayRecordsError("reviewed source team identity does not match raw evidence")
        expected_home = decision.team_side is TeamSide.HOME
        if len(home_values) != 1 or type(home_values[0][1]) is not bool or home_values[0][1] is not expected_home:
            raise ReviewedMatchDetailsArrayRecordsError("reviewed HOME/AWAY identity does not match raw evidence")
        roots = _traverse(payload, decision.array_root_pointer)
        if len(roots) != 1 or type(roots[0][1]) is not list:
            raise ReviewedMatchDetailsArrayRecordsError("reviewed array root must resolve exactly once")
        root_coordinate, raw_records = roots[0]
        record_field = fields.get(decision.record_pointer_pattern)
        if raw_records and (record_field is None or record_field.kinds != (JsonValueKind.OBJECT,)):
            raise ReviewedMatchDetailsArrayRecordsError("nonempty reviewed array requires exact PR53 OBJECT record pattern")
        member_index = {item.role: item for item in decision.member_reviews}
        for member in decision.member_reviews:
            observed = fields.get(member.pointer_pattern)
            if raw_records and (observed is None or observed.kinds != (member.expected_kind,)):
                raise ReviewedMatchDetailsArrayRecordsError("reviewed member pointer/kind not exact PR53 scalar")
        lineup_state = LineupState.UNVERIFIED_LINEUP_STATE
        if decision.lineup_state_pointer is not None:
            observed = fields.get(decision.lineup_state_pointer)
            if observed is None or observed.kinds != (decision.lineup_state_kind,):
                raise ReviewedMatchDetailsArrayRecordsError("lineup-state pointer/kind not exact PR53 scalar")
            values = _traverse(payload, decision.lineup_state_pointer)
            if len(values) != 1:
                raise ReviewedMatchDetailsArrayRecordsError("lineup-state pointer must resolve exactly once")
            observed_lineup_values.add(_scalar_key(values[0][1]))
            lineup_state = lineup_map.get(_scalar_key(values[0][1]), LineupState.UNVERIFIED_LINEUP_STATE)
        status = ReviewedArrayEvidenceStatus.UNVERIFIED
        if decision.qualification is ArrayReviewQualification.QUALIFIED:
            status = ReviewedArrayEvidenceStatus.SUPPORTED if classified_at <= decision.fresh_until else ReviewedArrayEvidenceStatus.STALE
            if raw_records and ArraySemanticRole.PLAYER_ID not in member_index:
                raise ReviewedMatchDetailsArrayRecordsError("qualified nonempty records require reviewed PLAYER_ID")
            identities: list[str | int] = []
            for index, raw_record in enumerate(raw_records):
                if type(raw_record) is not dict:
                    raise ReviewedMatchDetailsArrayRecordsError("reviewed repeated record must be JSON object")
                values = {role: _relative(raw_record, decision.record_pointer_pattern, review.pointer_pattern) for role, review in member_index.items()}
                for role, value in values.items():
                    if _kind(value) is not member_index[role].expected_kind:
                        raise ReviewedMatchDetailsArrayRecordsError("record member kind drift during raw replay")
                player_id = _identity(values[ArraySemanticRole.PLAYER_ID], "provider_player_id")
                if ArraySemanticRole.TEAM_ID in values and values[ArraySemanticRole.TEAM_ID] != decision.source_team_id:
                    raise ReviewedMatchDetailsArrayRecordsError("record provider team ID conflicts with reviewed team binding")
                if ArraySemanticRole.IS_HOME_TEAM in values and (type(values[ArraySemanticRole.IS_HOME_TEAM]) is not bool or values[ArraySemanticRole.IS_HOME_TEAM] is not expected_home):
                    raise ReviewedMatchDetailsArrayRecordsError("record team side conflicts with reviewed team binding")
                source_position = values.get(ArraySemanticRole.SOURCE_POSITION)
                if source_position is not None and type(source_position) is not str:
                    raise ReviewedMatchDetailsArrayRecordsError("source position must remain exact string")
                if source_position is not None: observed_positions.add(source_position)
                reason = values.get(ArraySemanticRole.UNAVAILABLE_REASON)
                if reason is not None and type(reason) is not str:
                    raise ReviewedMatchDetailsArrayRecordsError("unavailable reason must remain exact string")
                record_payload = {
                    "raw_sha256": rebuilt.raw_sha256,
                    "scope": decision.scope.value,
                    "team_side": decision.team_side.value,
                    "source_team_id": decision.source_team_id,
                    "provider_player_id": player_id,
                    "source_coordinate": list(root_coordinate + (index,)),
                    "source_position": source_position,
                    "unavailable_reason": reason,
                    "lineup_state": lineup_state.value,
                    "evidence_status": status.value,
                    "record_pointer_pattern": decision.record_pointer_pattern,
                }
                record_sha = hashlib.sha256(_canonical(record_payload)).hexdigest()
                extracted.append(ReviewedExtractedPlayerRecord(
                    decision.scope, decision.team_side, decision.source_team_id, player_id, root_coordinate + (index,),
                    source_position, reason, lineup_state, status, decision.fresh_until,
                    decision.record_pointer_pattern, record_sha,
                ))
                identities.append(player_id)
            if len({_scalar_key(value) for value in identities}) != len(identities):
                raise ReviewedMatchDetailsArrayRecordsError("duplicate provider player identity in reviewed array")
            if decision.completeness_attested:
                ids = tuple(sorted(identities, key=_scalar_key))
                receipt_payload = {
                    "provider": "FOTMOB",
                    "source_dataset_name": DATASET_NAME,
                    "scope": decision.scope.value,
                    "team_side": decision.team_side.value,
                    "source_team_id": decision.source_team_id,
                    "fixture_identifier": rebuilt.fixture_identifier,
                    "source_match_id": rebuilt.source_match_id,
                    "as_of": classified_at.isoformat().replace("+00:00", "Z"),
                    "raw_sha256": rebuilt.raw_sha256,
                    "array_root_pointer": decision.array_root_pointer,
                    "record_pointer_pattern": decision.record_pointer_pattern,
                    "provider_player_ids": list(ids),
                    "record_count": len(ids),
                    "disposition": ReviewedCompletenessDisposition.REVIEWED_COMPLETE_EXACT_OBSERVATION.value,
                    "evidence_sha256s": sorted({rebuilt.raw_sha256, hashlib.sha256(exact_assessment_bytes).hexdigest()}),
                }
                completeness.append(ReviewedArrayCompletenessReceipt(
                    "FOTMOB", DATASET_NAME, decision.scope, decision.team_side, decision.source_team_id,
                    rebuilt.fixture_identifier, rebuilt.source_match_id, classified_at, rebuilt.raw_sha256,
                    decision.array_root_pointer, decision.record_pointer_pattern, ids, len(ids),
                    ReviewedCompletenessDisposition.REVIEWED_COMPLETE_EXACT_OBSERVATION,
                    tuple(receipt_payload["evidence_sha256s"]),
                    hashlib.sha256(_canonical(receipt_payload)).hexdigest(),
                ))
    if not {_scalar_key(x.source_value) for x in lineup_state_mappings}.issubset(observed_lineup_values):
        raise ReviewedMatchDetailsArrayRecordsError("lineup mapping contains value absent from exact observation")
    if not {x.source_value for x in position_mappings}.issubset(observed_positions):
        raise ReviewedMatchDetailsArrayRecordsError("position mapping contains value absent from exact observation")
    extracted_tuple = tuple(sorted(extracted, key=lambda x: x.identity_key()))
    if len({_scalar_key(x.provider_player_id) for x in extracted_tuple}) != len(extracted_tuple):
        raise ReviewedMatchDetailsArrayRecordsError(
            "same provider player appears in contradictory reviewed fixture scopes"
        )
    return ReviewedMatchDetailsArrayRecords(
        SCHEMA_VERSION, DATASET_NAME, REVIEW_SCOPE,
        hashlib.sha256(exact_assessment_bytes).hexdigest(), rebuilt.evidence_receipt_sha256,
        rebuilt.manifest_sha256, rebuilt.raw_sha256, rebuilt.raw_size,
        rebuilt.fixture_identifier, rebuilt.source_match_id, evidence.kickoff, evidence.observed_at,
        reviewed_at, classified_at, reviewer_reference, decisions, lineup_state_mappings,
        position_mappings, extracted_tuple,
        tuple(sorted(completeness, key=lambda x: x.identity_key())),
        types.MappingProxyType(dict(_SAFETY)),
    )


def canonical_reviewed_match_details_array_records_bytes(value: Any) -> bytes:
    if type(value) is not ReviewedMatchDetailsArrayRecords:
        raise ReviewedMatchDetailsArrayRecordsError("value must be exact reviewed array artifact")
    rebuilt = dataclasses.replace(
        value,
        decisions=tuple(dataclasses.replace(x, member_reviews=tuple(dataclasses.replace(y) for y in x.member_reviews)) for x in value.decisions),
        lineup_state_mappings=tuple(dataclasses.replace(x) for x in value.lineup_state_mappings),
        position_mappings=tuple(dataclasses.replace(x) for x in value.position_mappings),
        records=tuple(dataclasses.replace(x, source_coordinate=tuple(x.source_coordinate)) for x in value.records),
        completeness_receipts=tuple(dataclasses.replace(x, provider_player_ids=tuple(x.provider_player_ids), evidence_sha256s=tuple(x.evidence_sha256s)) for x in value.completeness_receipts),
        safety=types.MappingProxyType(dict(value.safety)),
    )
    return _canonical(rebuilt.to_dict())


def sha256_reviewed_match_details_array_records(value: Any) -> str:
    return hashlib.sha256(canonical_reviewed_match_details_array_records_bytes(value)).hexdigest()


def revalidate_reviewed_match_details_array_records(
    *, evidence: Any, evidence_receipt_bytes: Any, manifest_bytes: Any, raw_bytes: Any,
    assessment: Any, assessment_bytes: Any, artifact: Any, artifact_bytes: Any,
) -> ReviewedMatchDetailsArrayRecords:
    if type(artifact) is not ReviewedMatchDetailsArrayRecords or type(artifact_bytes) is not bytes:
        raise ReviewedMatchDetailsArrayRecordsError("artifact/object bytes must be exact immutable reviewed values")
    supplied = canonical_reviewed_match_details_array_records_bytes(artifact)
    rebuilt = build_reviewed_match_details_array_records(
        evidence=evidence, evidence_receipt_bytes=evidence_receipt_bytes,
        manifest_bytes=manifest_bytes, raw_bytes=raw_bytes, assessment=assessment,
        assessment_bytes=assessment_bytes, decisions=artifact.decisions,
        lineup_state_mappings=artifact.lineup_state_mappings,
        position_mappings=artifact.position_mappings, reviewed_at=artifact.reviewed_at,
        classified_at=artifact.classified_at, reviewer_reference=artifact.reviewer_reference,
    )
    exact = canonical_reviewed_match_details_array_records_bytes(rebuilt)
    if supplied != exact or artifact_bytes != exact:
        raise ReviewedMatchDetailsArrayRecordsError("array artifact differs from exact full replay")
    return rebuilt


__all__ = [
    "ArrayRecordMemberReview", "ArrayRecordSetReviewDecision", "ArrayRecordSetScope",
    "ArrayReviewQualification", "ArraySemanticRole", "DATASET_NAME", "FRESHNESS_RULE",
    "LineupStateReviewMapping", "REVIEW_SCOPE", "ReviewedArrayCompletenessReceipt",
    "ReviewedArrayEvidenceStatus", "ReviewedCompletenessDisposition",
    "ReviewedExtractedPlayerRecord", "ReviewedMatchDetailsArrayRecords",
    "ReviewedMatchDetailsArrayRecordsError", "SCHEMA_VERSION", "SourcePositionReviewMapping",
    "build_reviewed_match_details_array_records",
    "canonical_reviewed_match_details_array_records_bytes",
    "revalidate_reviewed_match_details_array_records",
    "sha256_reviewed_match_details_array_records",
]
