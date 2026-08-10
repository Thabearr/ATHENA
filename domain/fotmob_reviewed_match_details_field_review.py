"""Explicit human-review contract for FotMob match-details field semantics.

This boundary records reviewer decisions anchored to an exact PR #53 structural
assessment. It does not extract response values, qualify the source, or create
Fixture Intelligence facts.
"""

from __future__ import annotations

import dataclasses
import datetime
import enum
import hashlib
import json
import re
import types
from collections.abc import Mapping
from typing import Any

from domain.fixture_intelligence import IntelligenceCategory
from domain.fotmob_reviewed_match_details_persisted_evidence import (
    VerifiedPersistedFotMobMatchDetailsEvidence,
)
from domain.fotmob_reviewed_match_details_structure import (
    FotMobReviewedMatchDetailsStructureAssessment,
    FotMobReviewedMatchDetailsStructureError,
    JsonValueKind,
    assess_reviewed_match_details_structure,
    canonical_reviewed_match_details_structure_bytes,
)

SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-reviewed-match-details-field-review-v1"
MAX_APPROVED_POINTER_LENGTH = 384
_FIELD_RE = re.compile(r"^[-a-zA-Z0-9_]+$", flags=re.ASCII)
_ALLOWED_APPROVED_KINDS = frozenset(
    {
        JsonValueKind.BOOLEAN,
        JsonValueKind.INTEGER,
        JsonValueKind.NUMBER,
        JsonValueKind.STRING,
    }
)
_SAFETY_KEYS = frozenset(
    {
        "automatic_semantic_review_authorized",
        "source_qualification_authorized",
        "value_extraction_authorized",
        "intelligence_fact_authorized",
        "intelligence_snapshot_authorized",
        "model_feature_authorized",
        "probability_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
    }
)


class FotMobReviewedMatchDetailsFieldReviewError(ValueError):
    pass


class FieldReviewDisposition(str, enum.Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


def _strict_utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise FotMobReviewedMatchDetailsFieldReviewError(f"{label} must be a datetime")
    if value.tzinfo is not datetime.timezone.utc:
        raise FotMobReviewedMatchDetailsFieldReviewError(
            f"{label} must already use exact datetime.timezone.utc"
        )
    return value


def _text(value: Any, label: str, maximum: int, *, allow_empty: bool = False) -> str:
    if type(value) is not str or value != value.strip():
        raise FotMobReviewedMatchDetailsFieldReviewError(
            f"{label} must be an exact trimmed string"
        )
    if (not allow_empty and not value) or len(value) > maximum:
        raise FotMobReviewedMatchDetailsFieldReviewError(
            f"{label} length is outside reviewed bounds"
        )
    return value


def _default_safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


@dataclasses.dataclass(frozen=True)
class MatchDetailsFieldReviewDecision:
    json_pointer: str
    expected_kind: JsonValueKind
    disposition: FieldReviewDisposition
    category: IntelligenceCategory | None
    field: str | None
    notes: str

    def __post_init__(self) -> None:
        pointer = _text(self.json_pointer, "json_pointer", 2048)
        if not pointer.startswith("/"):
            raise FotMobReviewedMatchDetailsFieldReviewError(
                "json_pointer must target a non-root structural path"
            )
        if not isinstance(self.expected_kind, JsonValueKind):
            raise FotMobReviewedMatchDetailsFieldReviewError(
                "expected_kind must be JsonValueKind"
            )
        if not isinstance(self.disposition, FieldReviewDisposition):
            raise FotMobReviewedMatchDetailsFieldReviewError(
                "disposition must be FieldReviewDisposition"
            )
        notes = _text(self.notes, "notes", 1024, allow_empty=True)
        if self.disposition is FieldReviewDisposition.APPROVED:
            if "/*" in pointer or pointer.endswith("/*"):
                raise FotMobReviewedMatchDetailsFieldReviewError(
                    "APPROVED paths must not contain the reserved array wildcard"
                )
            if len(pointer) > MAX_APPROVED_POINTER_LENGTH:
                raise FotMobReviewedMatchDetailsFieldReviewError(
                    "APPROVED json_pointer exceeds extraction-safe length"
                )
            if self.expected_kind not in _ALLOWED_APPROVED_KINDS:
                raise FotMobReviewedMatchDetailsFieldReviewError(
                    "APPROVED fields must be a non-null scalar kind"
                )
            if not isinstance(self.category, IntelligenceCategory):
                raise FotMobReviewedMatchDetailsFieldReviewError(
                    "APPROVED decision requires IntelligenceCategory"
                )
            if type(self.field) is not str or not self.field or self.field != self.field.strip():
                raise FotMobReviewedMatchDetailsFieldReviewError(
                    "APPROVED decision requires an exact non-empty field"
                )
            if len(self.field) > 128 or _FIELD_RE.fullmatch(self.field) is None:
                raise FotMobReviewedMatchDetailsFieldReviewError(
                    "field must match the Fixture Intelligence field contract"
                )
        else:
            if self.category is not None or self.field is not None:
                raise FotMobReviewedMatchDetailsFieldReviewError(
                    "REJECTED decisions must not carry category or field semantics"
                )
        object.__setattr__(self, "json_pointer", pointer)
        object.__setattr__(self, "notes", notes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "json_pointer": self.json_pointer,
            "expected_kind": self.expected_kind.value,
            "disposition": self.disposition.value,
            "category": self.category.value if self.category is not None else None,
            "field": self.field,
            "notes": self.notes,
        }


@dataclasses.dataclass(frozen=True)
class ReviewedMatchDetailsFieldSemantics:
    schema_version: int
    dataset_name: str
    structure_sha256: str
    evidence_receipt_sha256: str
    manifest_sha256: str
    raw_sha256: str
    fixture_identifier: str
    source_match_id: str
    reviewed_at: datetime.datetime
    reviewer_reference: str
    decisions: tuple[MatchDetailsFieldReviewDecision, ...]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise FotMobReviewedMatchDetailsFieldReviewError("schema_version mismatch")
        if self.dataset_name != DATASET_NAME:
            raise FotMobReviewedMatchDetailsFieldReviewError("dataset_name mismatch")
        for label in (
            "structure_sha256",
            "evidence_receipt_sha256",
            "manifest_sha256",
            "raw_sha256",
        ):
            value = getattr(self, label)
            if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise FotMobReviewedMatchDetailsFieldReviewError(
                    f"{label} must be exactly 64 lowercase hexadecimal characters"
                )
        if type(self.fixture_identifier) is not str or type(self.source_match_id) is not str:
            raise FotMobReviewedMatchDetailsFieldReviewError(
                "fixture/source identity must be exact strings"
            )
        reviewed_at = _strict_utc(self.reviewed_at, "reviewed_at")
        reviewer_reference = _text(self.reviewer_reference, "reviewer_reference", 256)
        if type(self.decisions) is not tuple or not self.decisions:
            raise FotMobReviewedMatchDetailsFieldReviewError(
                "decisions must be a non-empty immutable tuple"
            )
        if any(type(item) is not MatchDetailsFieldReviewDecision for item in self.decisions):
            raise FotMobReviewedMatchDetailsFieldReviewError(
                "decisions must contain exact MatchDetailsFieldReviewDecision values"
            )
        expected = tuple(sorted(self.decisions, key=lambda item: item.json_pointer))
        if self.decisions != expected or len({item.json_pointer for item in self.decisions}) != len(self.decisions):
            raise FotMobReviewedMatchDetailsFieldReviewError(
                "decisions must be sorted by unique json_pointer"
            )
        approved_targets = [
            (item.category.value, item.field)
            for item in self.decisions
            if item.disposition is FieldReviewDisposition.APPROVED
        ]
        if len(set(approved_targets)) != len(approved_targets):
            raise FotMobReviewedMatchDetailsFieldReviewError(
                "APPROVED semantic category/field targets must be unique"
            )
        if not isinstance(self.safety, Mapping) or set(self.safety) != _SAFETY_KEYS:
            raise FotMobReviewedMatchDetailsFieldReviewError("safety keys mismatch")
        for key, value in self.safety.items():
            if type(value) is not bool or value is not False:
                raise FotMobReviewedMatchDetailsFieldReviewError(
                    f"safety[{key!r}] must be exact bool False"
                )
        object.__setattr__(self, "reviewed_at", reviewed_at)
        object.__setattr__(self, "reviewer_reference", reviewer_reference)
        object.__setattr__(self, "safety", _default_safety())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "structure_sha256": self.structure_sha256,
            "evidence_receipt_sha256": self.evidence_receipt_sha256,
            "manifest_sha256": self.manifest_sha256,
            "raw_sha256": self.raw_sha256,
            "fixture_identifier": self.fixture_identifier,
            "source_match_id": self.source_match_id,
            "reviewed_at": self.reviewed_at.isoformat().replace("+00:00", "Z"),
            "reviewer_reference": self.reviewer_reference,
            "decisions": [item.to_dict() for item in self.decisions],
            "safety": dict(self.safety),
        }


def _rebuild_structure(
    *,
    evidence: Any,
    evidence_receipt_bytes: Any,
    manifest_bytes: Any,
    raw_bytes: Any,
    assessment: Any,
    assessment_bytes: Any,
) -> tuple[VerifiedPersistedFotMobMatchDetailsEvidence, FotMobReviewedMatchDetailsStructureAssessment, bytes]:
    if type(evidence) is not VerifiedPersistedFotMobMatchDetailsEvidence:
        raise FotMobReviewedMatchDetailsFieldReviewError(
            "evidence must be exact PR #52 verified evidence"
        )
    if type(assessment) is not FotMobReviewedMatchDetailsStructureAssessment:
        raise FotMobReviewedMatchDetailsFieldReviewError(
            "assessment must be exact PR #53 structural assessment"
        )
    if type(assessment_bytes) is not bytes:
        raise FotMobReviewedMatchDetailsFieldReviewError(
            "assessment_bytes must be exact immutable bytes"
        )
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
        raise FotMobReviewedMatchDetailsFieldReviewError(
            "PR #53 structural assessment failed exact byte revalidation"
        ) from exc
    if supplied != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsFieldReviewError(
            "supplied PR #53 assessment differs from exact semantic rebuild"
        )
    if assessment_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsFieldReviewError(
            "assessment_bytes are not exact canonical PR #53 bytes"
        )
    return evidence, rebuilt, rebuilt_bytes


def build_reviewed_match_details_field_semantics(
    *,
    evidence: Any,
    evidence_receipt_bytes: Any,
    manifest_bytes: Any,
    raw_bytes: Any,
    assessment: Any,
    assessment_bytes: Any,
    decisions: Any,
    reviewed_at: Any,
    reviewer_reference: Any,
) -> ReviewedMatchDetailsFieldSemantics:
    evidence, rebuilt, exact_assessment_bytes = _rebuild_structure(
        evidence=evidence,
        evidence_receipt_bytes=evidence_receipt_bytes,
        manifest_bytes=manifest_bytes,
        raw_bytes=raw_bytes,
        assessment=assessment,
        assessment_bytes=assessment_bytes,
    )
    reviewed_at = _strict_utc(reviewed_at, "reviewed_at")
    if reviewed_at < evidence.observed_at:
        raise FotMobReviewedMatchDetailsFieldReviewError(
            "reviewed_at must not predate evidence observation"
        )
    if reviewed_at >= evidence.kickoff:
        raise FotMobReviewedMatchDetailsFieldReviewError(
            "reviewed_at must be strictly before fixture kickoff"
        )
    reviewer_reference = _text(reviewer_reference, "reviewer_reference", 256)
    if type(decisions) is not tuple or not decisions:
        raise FotMobReviewedMatchDetailsFieldReviewError(
            "decisions must be a non-empty immutable tuple"
        )
    rebuilt_decisions = tuple(dataclasses.replace(item) for item in decisions)
    fields = {item.json_pointer: item for item in rebuilt.fields}
    for decision in rebuilt_decisions:
        observed = fields.get(decision.json_pointer)
        if observed is None:
            raise FotMobReviewedMatchDetailsFieldReviewError(
                f"review decision path was not observed: {decision.json_pointer}"
            )
        if decision.expected_kind not in observed.kinds:
            raise FotMobReviewedMatchDetailsFieldReviewError(
                "expected_kind was not observed at reviewed structural path"
            )
        if decision.disposition is FieldReviewDisposition.APPROVED:
            if len(observed.kinds) != 1 or observed.kinds[0] is not decision.expected_kind:
                raise FotMobReviewedMatchDetailsFieldReviewError(
                    "APPROVED path must have exactly one unambiguous observed kind"
                )
    sorted_decisions = tuple(sorted(rebuilt_decisions, key=lambda item: item.json_pointer))
    return ReviewedMatchDetailsFieldSemantics(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        structure_sha256=hashlib.sha256(exact_assessment_bytes).hexdigest(),
        evidence_receipt_sha256=rebuilt.evidence_receipt_sha256,
        manifest_sha256=rebuilt.manifest_sha256,
        raw_sha256=rebuilt.raw_sha256,
        fixture_identifier=rebuilt.fixture_identifier,
        source_match_id=rebuilt.source_match_id,
        reviewed_at=reviewed_at,
        reviewer_reference=reviewer_reference,
        decisions=sorted_decisions,
        safety=_default_safety(),
    )


def canonical_reviewed_match_details_field_semantics_bytes(value: Any) -> bytes:
    if type(value) is not ReviewedMatchDetailsFieldSemantics:
        raise FotMobReviewedMatchDetailsFieldReviewError(
            "value must be exact ReviewedMatchDetailsFieldSemantics"
        )
    rebuilt = dataclasses.replace(value)
    try:
        return (
            json.dumps(
                rebuilt.to_dict(),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobReviewedMatchDetailsFieldReviewError(
            "field review serialization failed"
        ) from exc


def sha256_reviewed_match_details_field_semantics(value: Any) -> str:
    return hashlib.sha256(
        canonical_reviewed_match_details_field_semantics_bytes(value)
    ).hexdigest()


__all__ = [
    "DATASET_NAME", "MAX_APPROVED_POINTER_LENGTH", "SCHEMA_VERSION",
    "FieldReviewDisposition", "FotMobReviewedMatchDetailsFieldReviewError",
    "MatchDetailsFieldReviewDecision", "ReviewedMatchDetailsFieldSemantics",
    "build_reviewed_match_details_field_semantics",
    "canonical_reviewed_match_details_field_semantics_bytes",
    "sha256_reviewed_match_details_field_semantics",
]
