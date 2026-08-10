"""Human-reviewed semantic decisions for exact FotMob match-details structure.

This boundary can attach explicit human-reviewed meaning to exact structural
paths from PR #53. It does not extract response values, qualify the source, or
create Fixture Intelligence facts.
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

from domain.fixture_intelligence import IntelligenceCategory, SourceRole
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
DATASET_NAME = "athena-fotmob-reviewed-match-details-semantic-review-v1"
MAX_REVIEWER_REFERENCE_LENGTH = 256
MAX_RATIONALE_LENGTH = 2048
MAX_NOTES_LENGTH = 4096

_FIELD_RE = re.compile(r"^[a-z][a-z0-9_]{0,127}$", flags=re.ASCII)
_SHA_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "automatic_review_authorized",
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


class FotMobReviewedMatchDetailsSemanticReviewError(ValueError):
    """Raised when a semantic-review decision fails closed."""


class SemanticReviewDisposition(str, enum.Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobReviewedMatchDetailsSemanticReviewError(
            "semantic review canonicalization failed"
        ) from exc


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        raise FotMobReviewedMatchDetailsSemanticReviewError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise FotMobReviewedMatchDetailsSemanticReviewError(
            f"{label} must be a datetime"
        )
    if value.tzinfo is not datetime.timezone.utc:
        raise FotMobReviewedMatchDetailsSemanticReviewError(
            f"{label} must already use datetime.timezone.utc"
        )
    return value


def _text(value: Any, label: str, maximum: int, *, allow_empty: bool) -> str:
    if type(value) is not str:
        raise FotMobReviewedMatchDetailsSemanticReviewError(
            f"{label} must be an exact string"
        )
    if value != value.strip():
        raise FotMobReviewedMatchDetailsSemanticReviewError(
            f"{label} must not have leading/trailing whitespace"
        )
    if (not allow_empty and not value) or len(value) > maximum:
        raise FotMobReviewedMatchDetailsSemanticReviewError(
            f"{label} is empty or exceeds {maximum} characters"
        )
    return value


def _default_safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise FotMobReviewedMatchDetailsSemanticReviewError("safety keys mismatch")
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise FotMobReviewedMatchDetailsSemanticReviewError(
                f"safety[{key!r}] must be exact bool False"
            )
    return _default_safety()


@dataclasses.dataclass(frozen=True)
class ReviewedMatchDetailsFieldDecision:
    """One explicit human decision about one exact PR #53 structural path."""

    json_pointer: str
    observed_kinds: tuple[JsonValueKind, ...]
    disposition: SemanticReviewDisposition
    category: IntelligenceCategory | None
    logical_field: str | None
    source_role: SourceRole | None
    rationale: str

    def __post_init__(self) -> None:
        if type(self.json_pointer) is not str:
            raise FotMobReviewedMatchDetailsSemanticReviewError(
                "json_pointer must be an exact string"
            )
        if self.json_pointer and not self.json_pointer.startswith("/"):
            raise FotMobReviewedMatchDetailsSemanticReviewError(
                "json_pointer must be empty root or start with '/'"
            )
        if type(self.observed_kinds) is not tuple or not self.observed_kinds:
            raise FotMobReviewedMatchDetailsSemanticReviewError(
                "observed_kinds must be a non-empty immutable tuple"
            )
        if any(not isinstance(item, JsonValueKind) for item in self.observed_kinds):
            raise FotMobReviewedMatchDetailsSemanticReviewError(
                "observed_kinds must contain only JsonValueKind values"
            )
        expected_kinds = tuple(
            sorted(set(self.observed_kinds), key=lambda item: item.value)
        )
        if self.observed_kinds != expected_kinds:
            raise FotMobReviewedMatchDetailsSemanticReviewError(
                "observed_kinds must be sorted and unique"
            )
        if not isinstance(self.disposition, SemanticReviewDisposition):
            raise FotMobReviewedMatchDetailsSemanticReviewError(
                "disposition must be SemanticReviewDisposition"
            )
        rationale = _text(
            self.rationale,
            "rationale",
            MAX_RATIONALE_LENGTH,
            allow_empty=False,
        )
        if self.disposition is SemanticReviewDisposition.APPROVED:
            if not isinstance(self.category, IntelligenceCategory):
                raise FotMobReviewedMatchDetailsSemanticReviewError(
                    "APPROVED decision requires IntelligenceCategory"
                )
            if type(self.logical_field) is not str or _FIELD_RE.fullmatch(self.logical_field) is None:
                raise FotMobReviewedMatchDetailsSemanticReviewError(
                    "APPROVED logical_field must be a lowercase ATHENA field identifier"
                )
            if self.source_role is not SourceRole.PRIMARY_FOOTBALL_CONTEXT:
                raise FotMobReviewedMatchDetailsSemanticReviewError(
                    "APPROVED FotMob match-details decision requires PRIMARY_FOOTBALL_CONTEXT"
                )
        else:
            if any(
                item is not None
                for item in (self.category, self.logical_field, self.source_role)
            ):
                raise FotMobReviewedMatchDetailsSemanticReviewError(
                    "REJECTED decision must not carry category, logical_field, or source_role"
                )
        object.__setattr__(self, "rationale", rationale)

    def to_dict(self) -> dict[str, Any]:
        return {
            "json_pointer": self.json_pointer,
            "observed_kinds": [item.value for item in self.observed_kinds],
            "disposition": self.disposition.value,
            "category": self.category.value if self.category is not None else None,
            "logical_field": self.logical_field,
            "source_role": self.source_role.value if self.source_role is not None else None,
            "rationale": self.rationale,
        }


@dataclasses.dataclass(frozen=True)
class FotMobReviewedMatchDetailsSemanticReview:
    schema_version: int
    dataset_name: str
    structure_sha256: str
    evidence_receipt_sha256: str
    manifest_sha256: str
    raw_sha256: str
    fixture_identifier: str
    source_match_id: str
    kickoff: datetime.datetime
    evidence_observed_at: datetime.datetime
    reviewed_at: datetime.datetime
    reviewer_reference: str
    notes: str
    decisions: tuple[ReviewedMatchDetailsFieldDecision, ...]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise FotMobReviewedMatchDetailsSemanticReviewError("schema_version mismatch")
        if self.dataset_name != DATASET_NAME:
            raise FotMobReviewedMatchDetailsSemanticReviewError("dataset_name mismatch")
        for label in (
            "structure_sha256",
            "evidence_receipt_sha256",
            "manifest_sha256",
            "raw_sha256",
        ):
            _sha(getattr(self, label), label)
        if type(self.fixture_identifier) is not str or not self.fixture_identifier:
            raise FotMobReviewedMatchDetailsSemanticReviewError(
                "fixture_identifier must be a non-empty exact string"
            )
        if type(self.source_match_id) is not str or not self.source_match_id:
            raise FotMobReviewedMatchDetailsSemanticReviewError(
                "source_match_id must be a non-empty exact string"
            )
        kickoff = _utc(self.kickoff, "kickoff")
        observed = _utc(self.evidence_observed_at, "evidence_observed_at")
        reviewed = _utc(self.reviewed_at, "reviewed_at")
        if observed >= kickoff:
            raise FotMobReviewedMatchDetailsSemanticReviewError(
                "evidence_observed_at must be strictly before kickoff"
            )
        if reviewed < observed:
            raise FotMobReviewedMatchDetailsSemanticReviewError(
                "reviewed_at must not predate evidence observation"
            )
        reviewer = _text(
            self.reviewer_reference,
            "reviewer_reference",
            MAX_REVIEWER_REFERENCE_LENGTH,
            allow_empty=False,
        )
        notes = _text(self.notes, "notes", MAX_NOTES_LENGTH, allow_empty=True)
        if type(self.decisions) is not tuple or not self.decisions:
            raise FotMobReviewedMatchDetailsSemanticReviewError(
                "decisions must be a non-empty immutable tuple"
            )
        if any(type(item) is not ReviewedMatchDetailsFieldDecision for item in self.decisions):
            raise FotMobReviewedMatchDetailsSemanticReviewError(
                "decisions must contain exact ReviewedMatchDetailsFieldDecision values"
            )
        expected = tuple(sorted(self.decisions, key=lambda item: item.json_pointer))
        if self.decisions != expected:
            raise FotMobReviewedMatchDetailsSemanticReviewError(
                "decisions must be sorted by json_pointer"
            )
        if len({item.json_pointer for item in self.decisions}) != len(self.decisions):
            raise FotMobReviewedMatchDetailsSemanticReviewError(
                "each structural json_pointer may be reviewed at most once"
            )
        safety = _validate_safety(self.safety)
        object.__setattr__(self, "kickoff", kickoff)
        object.__setattr__(self, "evidence_observed_at", observed)
        object.__setattr__(self, "reviewed_at", reviewed)
        object.__setattr__(self, "reviewer_reference", reviewer)
        object.__setattr__(self, "notes", notes)
        object.__setattr__(self, "safety", safety)

    def to_dict(self) -> dict[str, Any]:
        def iso(value: datetime.datetime) -> str:
            return value.isoformat().replace("+00:00", "Z")

        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "structure_sha256": self.structure_sha256,
            "evidence_receipt_sha256": self.evidence_receipt_sha256,
            "manifest_sha256": self.manifest_sha256,
            "raw_sha256": self.raw_sha256,
            "fixture_identifier": self.fixture_identifier,
            "source_match_id": self.source_match_id,
            "kickoff": iso(self.kickoff),
            "evidence_observed_at": iso(self.evidence_observed_at),
            "reviewed_at": iso(self.reviewed_at),
            "reviewer_reference": self.reviewer_reference,
            "notes": self.notes,
            "decisions": [item.to_dict() for item in self.decisions],
            "safety": dict(self.safety),
        }


def _revalidate_structure(
    *,
    structure: Any,
    structure_bytes: Any,
    evidence: Any,
    evidence_receipt_bytes: Any,
    manifest_bytes: Any,
    raw_bytes: Any,
) -> tuple[
    FotMobReviewedMatchDetailsStructureAssessment,
    bytes,
    VerifiedPersistedFotMobMatchDetailsEvidence,
]:
    if type(structure) is not FotMobReviewedMatchDetailsStructureAssessment:
        raise FotMobReviewedMatchDetailsSemanticReviewError(
            "structure must be exact FotMobReviewedMatchDetailsStructureAssessment"
        )
    if type(structure_bytes) is not bytes:
        raise FotMobReviewedMatchDetailsSemanticReviewError(
            "structure_bytes must be exact immutable bytes"
        )
    if type(evidence) is not VerifiedPersistedFotMobMatchDetailsEvidence:
        raise FotMobReviewedMatchDetailsSemanticReviewError(
            "evidence must be exact VerifiedPersistedFotMobMatchDetailsEvidence"
        )
    try:
        supplied_bytes = canonical_reviewed_match_details_structure_bytes(structure)
        rebuilt = assess_reviewed_match_details_structure(
            evidence=evidence,
            evidence_receipt_bytes=evidence_receipt_bytes,
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
        )
        rebuilt_bytes = canonical_reviewed_match_details_structure_bytes(rebuilt)
    except (FotMobReviewedMatchDetailsStructureError, TypeError, ValueError) as exc:
        raise FotMobReviewedMatchDetailsSemanticReviewError(
            "PR #53 structure failed exact current evidence revalidation"
        ) from exc
    if supplied_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsSemanticReviewError(
            "supplied PR #53 structure differs from exact evidence rebuild"
        )
    if structure_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsSemanticReviewError(
            "structure_bytes are not exact canonical PR #53 bytes"
        )
    return rebuilt, rebuilt_bytes, evidence


def build_reviewed_match_details_semantic_review(
    *,
    structure: Any,
    structure_bytes: Any,
    evidence: Any,
    evidence_receipt_bytes: Any,
    manifest_bytes: Any,
    raw_bytes: Any,
    decisions: Any,
    reviewed_at: Any,
    reviewer_reference: Any,
    notes: Any = "",
) -> FotMobReviewedMatchDetailsSemanticReview:
    """Build an explicit human review anchored to exact PR #53 evidence."""

    rebuilt, exact_structure_bytes, exact_evidence = _revalidate_structure(
        structure=structure,
        structure_bytes=structure_bytes,
        evidence=evidence,
        evidence_receipt_bytes=evidence_receipt_bytes,
        manifest_bytes=manifest_bytes,
        raw_bytes=raw_bytes,
    )
    if type(decisions) is not tuple or not decisions:
        raise FotMobReviewedMatchDetailsSemanticReviewError(
            "decisions must be a non-empty immutable tuple"
        )
    if any(type(item) is not ReviewedMatchDetailsFieldDecision for item in decisions):
        raise FotMobReviewedMatchDetailsSemanticReviewError(
            "decisions must contain exact ReviewedMatchDetailsFieldDecision values"
        )
    ordered = tuple(sorted(decisions, key=lambda item: item.json_pointer))
    if len({item.json_pointer for item in ordered}) != len(ordered):
        raise FotMobReviewedMatchDetailsSemanticReviewError(
            "duplicate semantic review json_pointer"
        )
    observed = {item.json_pointer: item for item in rebuilt.fields}
    for decision in ordered:
        field = observed.get(decision.json_pointer)
        if field is None:
            raise FotMobReviewedMatchDetailsSemanticReviewError(
                f"reviewed json_pointer is absent from PR #53: {decision.json_pointer!r}"
            )
        if decision.observed_kinds != field.kinds:
            raise FotMobReviewedMatchDetailsSemanticReviewError(
                f"observed kind mismatch for {decision.json_pointer!r}"
            )
    reviewed = _utc(reviewed_at, "reviewed_at")
    if reviewed < exact_evidence.observed_at:
        raise FotMobReviewedMatchDetailsSemanticReviewError(
            "reviewed_at must not predate exact evidence observation"
        )
    return FotMobReviewedMatchDetailsSemanticReview(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        structure_sha256=hashlib.sha256(exact_structure_bytes).hexdigest(),
        evidence_receipt_sha256=rebuilt.evidence_receipt_sha256,
        manifest_sha256=rebuilt.manifest_sha256,
        raw_sha256=rebuilt.raw_sha256,
        fixture_identifier=rebuilt.fixture_identifier,
        source_match_id=rebuilt.source_match_id,
        kickoff=exact_evidence.kickoff,
        evidence_observed_at=exact_evidence.observed_at,
        reviewed_at=reviewed,
        reviewer_reference=reviewer_reference,
        notes=notes,
        decisions=ordered,
        safety=_default_safety(),
    )


def canonical_reviewed_match_details_semantic_review_bytes(value: Any) -> bytes:
    if type(value) is not FotMobReviewedMatchDetailsSemanticReview:
        raise FotMobReviewedMatchDetailsSemanticReviewError(
            "value must be exact FotMobReviewedMatchDetailsSemanticReview"
        )
    try:
        rebuilt = dataclasses.replace(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise FotMobReviewedMatchDetailsSemanticReviewError(
            "semantic review failed structural revalidation"
        ) from exc
    return _canonical_json_bytes(rebuilt.to_dict())


def sha256_reviewed_match_details_semantic_review(value: Any) -> str:
    return hashlib.sha256(
        canonical_reviewed_match_details_semantic_review_bytes(value)
    ).hexdigest()


__all__ = [
    "DATASET_NAME",
    "SCHEMA_VERSION",
    "FotMobReviewedMatchDetailsSemanticReview",
    "FotMobReviewedMatchDetailsSemanticReviewError",
    "ReviewedMatchDetailsFieldDecision",
    "SemanticReviewDisposition",
    "build_reviewed_match_details_semantic_review",
    "canonical_reviewed_match_details_semantic_review_bytes",
    "sha256_reviewed_match_details_semantic_review",
]
