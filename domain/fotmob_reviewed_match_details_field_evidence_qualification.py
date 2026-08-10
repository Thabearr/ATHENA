"""Exact-observation qualification for reviewed FotMob match-details facts.

PR #58 consumes the complete exact PR #52 -> PR #57 chain and records an
explicit reviewer decision for every exact PR #57 UNVERIFIED fact. A
QUALIFIED decision applies only to that exact observation. It does not create
a source-wide capability, change fact status, build a Fixture Intelligence
snapshot, or authorize modelling/pricing/betting behavior.
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

from domain.fixture_intelligence import (
    FixtureIntelligenceFact,
    IntelligenceCategory,
    IntelligenceFactStatus,
    SourceRole,
)
from domain.fotmob_reviewed_match_details_unverified_facts import (
    EVIDENCE_ROOT,
    FotMobReviewedMatchDetailsUnverifiedFactError,
    ReviewedMatchDetailsUnverifiedFactBundle,
    SOURCE_PROVIDER,
    canonical_reviewed_match_details_unverified_fact_bundle_bytes,
    revalidate_reviewed_match_details_unverified_fact_bundle,
)

SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-reviewed-match-details-field-evidence-qualification-v1"
QUALIFICATION_SCOPE = "EXACT_OBSERVATION_ONLY"
RAW_FILENAME = "response.json"

_SHA_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_FIXTURE_RE = re.compile(r"^FOTMOB:([1-9][0-9]*)$", flags=re.ASCII)
_FIELD_RE = re.compile(r"^[-a-zA-Z0-9_]+$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "source_wide_qualification_authorized",
        "status_classification_authorized",
        "supported_status_authorized",
        "intelligence_snapshot_authorized",
        "model_feature_authorized",
        "probability_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
    }
)


class FotMobReviewedMatchDetailsFieldEvidenceQualificationError(ValueError):
    """Raised when exact field-evidence qualification cannot be proven."""


class FieldEvidenceQualificationDisposition(str, enum.Enum):
    QUALIFIED = "QUALIFIED"
    REJECTED = "REJECTED"


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _text(value: Any, label: str, maximum: int) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
    ):
        raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
            f"{label} must be a non-empty exact trimmed string within {maximum} characters"
        )
    return value


def _utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
            f"{label} must be a datetime"
        )
    if value.tzinfo is not datetime.timezone.utc:
        raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
            f"{label} must already use exact datetime.timezone.utc"
        )
    return value


def _default_safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
            "safety keys mismatch"
        )
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
                f"safety[{key!r}] must be exact bool False"
            )
    return _default_safety()


def _iso(value: datetime.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _expected_evidence_file_path(
    source_match_id: str,
    observed_at: datetime.datetime,
    raw_sha256: str,
) -> str:
    timestamp = observed_at.strftime("%Y%m%dT%H%M%S%fZ")
    capture_identifier = f"{source_match_id}--{timestamp}--{raw_sha256}"
    return f"{EVIDENCE_ROOT}/{capture_identifier}/{RAW_FILENAME}"


def _fact_payload(fact: FixtureIntelligenceFact) -> dict[str, Any]:
    if type(fact) is not FixtureIntelligenceFact:
        raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
            "fact must be exact FixtureIntelligenceFact"
        )
    return {
        "category": fact.category.value,
        "field": fact.field,
        "status": fact.status.value,
        "value": fact.value,
        "source_provider": fact.source_provider,
        "source_role": fact.source_role.value,
        "source_reference": fact.source_reference,
        "observed_at": _iso(fact.observed_at),
        "evidence_file_path": fact.evidence_file_path,
        "evidence_sha256": fact.evidence_sha256,
        "notes": fact.notes,
    }


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
        raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
            "field-evidence qualification serialization failed"
        ) from exc


def _fact_sha256(fact: FixtureIntelligenceFact) -> str:
    return hashlib.sha256(_canonical_json_bytes(_fact_payload(fact))).hexdigest()


def _decision_key(
    category: IntelligenceCategory,
    field: str,
    source_reference: str,
) -> tuple[str, str, str]:
    return (category.value, field, source_reference)


@dataclasses.dataclass(frozen=True)
class MatchDetailsFieldEvidenceReviewDecision:
    """Reviewer input for one exact PR #57 fact."""

    category: IntelligenceCategory
    field: str
    source_reference: str
    disposition: FieldEvidenceQualificationDisposition
    rationale: str

    def __post_init__(self) -> None:
        if not isinstance(self.category, IntelligenceCategory):
            raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
                "category must be IntelligenceCategory"
            )
        field = _text(self.field, "field", 128)
        if _FIELD_RE.fullmatch(field) is None:
            raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
                "field must match the Fixture Intelligence field contract"
            )
        source_reference = _text(self.source_reference, "source_reference", 512)
        if not isinstance(self.disposition, FieldEvidenceQualificationDisposition):
            raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
                "disposition must be FieldEvidenceQualificationDisposition"
            )
        rationale = _text(self.rationale, "rationale", 1024)
        object.__setattr__(self, "field", field)
        object.__setattr__(self, "source_reference", source_reference)
        object.__setattr__(self, "rationale", rationale)

    @property
    def key(self) -> tuple[str, str, str]:
        return _decision_key(self.category, self.field, self.source_reference)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "field": self.field,
            "source_reference": self.source_reference,
            "disposition": self.disposition.value,
            "rationale": self.rationale,
        }


@dataclasses.dataclass(frozen=True)
class RecordedMatchDetailsFieldEvidenceDecision:
    """Reviewer decision bound to the exact canonical PR #30 fact bytes."""

    category: IntelligenceCategory
    field: str
    source_reference: str
    fact_sha256: str
    disposition: FieldEvidenceQualificationDisposition
    rationale: str

    def __post_init__(self) -> None:
        if not isinstance(self.category, IntelligenceCategory):
            raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
                "recorded category must be IntelligenceCategory"
            )
        field = _text(self.field, "recorded field", 128)
        if _FIELD_RE.fullmatch(field) is None:
            raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
                "recorded field must match Fixture Intelligence field contract"
            )
        source_reference = _text(
            self.source_reference,
            "recorded source_reference",
            512,
        )
        fact_sha256 = _sha(self.fact_sha256, "fact_sha256")
        if not isinstance(self.disposition, FieldEvidenceQualificationDisposition):
            raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
                "recorded disposition must be FieldEvidenceQualificationDisposition"
            )
        rationale = _text(self.rationale, "recorded rationale", 1024)
        object.__setattr__(self, "field", field)
        object.__setattr__(self, "source_reference", source_reference)
        object.__setattr__(self, "fact_sha256", fact_sha256)
        object.__setattr__(self, "rationale", rationale)

    @property
    def key(self) -> tuple[str, str, str]:
        return _decision_key(self.category, self.field, self.source_reference)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "field": self.field,
            "source_reference": self.source_reference,
            "fact_sha256": self.fact_sha256,
            "disposition": self.disposition.value,
            "rationale": self.rationale,
        }


@dataclasses.dataclass(frozen=True)
class ReviewedMatchDetailsFieldEvidenceQualification:
    """Detached exact-observation qualification record for one PR #57 bundle."""

    schema_version: int
    dataset_name: str
    qualification_scope: str
    fact_bundle_sha256: str
    fact_bundle_size: int
    fixture_identifier: str
    source_match_id: str
    kickoff: datetime.datetime
    observed_at: datetime.datetime
    semantic_reviewed_at: datetime.datetime
    raw_sha256: str
    evidence_file_path: str
    source_provider: str
    source_role: SourceRole
    reviewed_at: datetime.datetime
    reviewer_reference: str
    decisions: tuple[RecordedMatchDetailsFieldEvidenceDecision, ...]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
                "schema_version mismatch"
            )
        if self.dataset_name != DATASET_NAME:
            raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
                "dataset_name mismatch"
            )
        if self.qualification_scope != QUALIFICATION_SCOPE:
            raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
                "qualification_scope must remain EXACT_OBSERVATION_ONLY"
            )
        _sha(self.fact_bundle_sha256, "fact_bundle_sha256")
        if type(self.fact_bundle_size) is not int or self.fact_bundle_size <= 0:
            raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
                "fact_bundle_size must be an exact positive integer"
            )

        fixture_identifier = _text(
            self.fixture_identifier,
            "fixture_identifier",
            512,
        )
        source_match_id = _text(self.source_match_id, "source_match_id", 256)
        match = _FIXTURE_RE.fullmatch(fixture_identifier)
        if match is None or match.group(1) != source_match_id:
            raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
                "fixture_identifier/source_match_id mismatch"
            )

        kickoff = _utc(self.kickoff, "kickoff")
        observed_at = _utc(self.observed_at, "observed_at")
        semantic_reviewed_at = _utc(
            self.semantic_reviewed_at,
            "semantic_reviewed_at",
        )
        reviewed_at = _utc(self.reviewed_at, "reviewed_at")
        if observed_at >= kickoff:
            raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
                "observed_at must remain strictly before kickoff"
            )
        if semantic_reviewed_at < observed_at or semantic_reviewed_at >= kickoff:
            raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
                "semantic_reviewed_at must follow observation and remain before kickoff"
            )
        if reviewed_at < semantic_reviewed_at or reviewed_at >= kickoff:
            raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
                "reviewed_at must not precede semantic review and must remain before kickoff"
            )

        raw_sha256 = _sha(self.raw_sha256, "raw_sha256")
        evidence_file_path = _text(
            self.evidence_file_path,
            "evidence_file_path",
            1024,
        )
        expected_path = _expected_evidence_file_path(
            source_match_id,
            observed_at,
            raw_sha256,
        )
        if evidence_file_path != expected_path:
            raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
                "evidence_file_path must match exact durable capture identity"
            )
        if self.source_provider != SOURCE_PROVIDER:
            raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
                "source_provider must remain exact reviewed match-details provider"
            )
        if self.source_role is not SourceRole.PRIMARY_FOOTBALL_CONTEXT:
            raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
                "source_role must remain PRIMARY_FOOTBALL_CONTEXT"
            )
        reviewer_reference = _text(
            self.reviewer_reference,
            "reviewer_reference",
            256,
        )

        if type(self.decisions) is not tuple or not self.decisions:
            raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
                "decisions must be a non-empty immutable tuple"
            )
        if any(
            type(item) is not RecordedMatchDetailsFieldEvidenceDecision
            for item in self.decisions
        ):
            raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
                "decisions must contain exact recorded decision values"
            )
        expected = tuple(sorted(self.decisions, key=lambda item: item.key))
        if self.decisions != expected:
            raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
                "decisions must be deterministically sorted"
            )
        keys = tuple(item.key for item in self.decisions)
        if len(set(keys)) != len(keys):
            raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
                "decisions must target unique exact facts"
            )
        fact_hashes = tuple(item.fact_sha256 for item in self.decisions)
        if len(set(fact_hashes)) != len(fact_hashes):
            raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
                "recorded fact_sha256 values must be unique"
            )
        source_prefix = f"/api/matchDetails?matchId={source_match_id}#/"
        for item in self.decisions:
            if not item.source_reference.startswith(source_prefix):
                raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
                    "recorded source_reference does not match exact source fixture"
                )

        safety = _validate_safety(self.safety)
        object.__setattr__(self, "fixture_identifier", fixture_identifier)
        object.__setattr__(self, "source_match_id", source_match_id)
        object.__setattr__(self, "kickoff", kickoff)
        object.__setattr__(self, "observed_at", observed_at)
        object.__setattr__(self, "semantic_reviewed_at", semantic_reviewed_at)
        object.__setattr__(self, "reviewed_at", reviewed_at)
        object.__setattr__(self, "raw_sha256", raw_sha256)
        object.__setattr__(self, "evidence_file_path", evidence_file_path)
        object.__setattr__(self, "reviewer_reference", reviewer_reference)
        object.__setattr__(self, "safety", safety)

    @property
    def qualified_count(self) -> int:
        return sum(
            item.disposition is FieldEvidenceQualificationDisposition.QUALIFIED
            for item in self.decisions
        )

    @property
    def rejected_count(self) -> int:
        return sum(
            item.disposition is FieldEvidenceQualificationDisposition.REJECTED
            for item in self.decisions
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "qualification_scope": self.qualification_scope,
            "fact_bundle_sha256": self.fact_bundle_sha256,
            "fact_bundle_size": self.fact_bundle_size,
            "fixture_identifier": self.fixture_identifier,
            "source_match_id": self.source_match_id,
            "kickoff": _iso(self.kickoff),
            "observed_at": _iso(self.observed_at),
            "semantic_reviewed_at": _iso(self.semantic_reviewed_at),
            "raw_sha256": self.raw_sha256,
            "evidence_file_path": self.evidence_file_path,
            "source_provider": self.source_provider,
            "source_role": self.source_role.value,
            "reviewed_at": _iso(self.reviewed_at),
            "reviewer_reference": self.reviewer_reference,
            "qualified_count": self.qualified_count,
            "rejected_count": self.rejected_count,
            "decisions": [item.to_dict() for item in self.decisions],
            "safety": dict(self.safety),
        }


def _revalidate_fact_bundle(
    *,
    evidence: Any,
    evidence_receipt_bytes: Any,
    manifest_bytes: Any,
    raw_bytes: Any,
    assessment: Any,
    assessment_bytes: Any,
    review: Any,
    review_bytes: Any,
    fact_bundle: Any,
    fact_bundle_bytes: Any,
) -> tuple[ReviewedMatchDetailsUnverifiedFactBundle, bytes]:
    if type(fact_bundle) is not ReviewedMatchDetailsUnverifiedFactBundle:
        raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
            "fact_bundle must be exact PR #57 bundle"
        )
    if type(fact_bundle_bytes) is not bytes:
        raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
            "fact_bundle_bytes must be exact immutable bytes"
        )
    try:
        rebuilt = revalidate_reviewed_match_details_unverified_fact_bundle(
            evidence=evidence,
            evidence_receipt_bytes=evidence_receipt_bytes,
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            review=review,
            review_bytes=review_bytes,
            fact_bundle=fact_bundle,
            fact_bundle_bytes=fact_bundle_bytes,
        )
        exact_bytes = canonical_reviewed_match_details_unverified_fact_bundle_bytes(
            rebuilt
        )
    except (
        FotMobReviewedMatchDetailsUnverifiedFactError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
            "PR #57 fact bundle failed exact full-chain revalidation"
        ) from exc
    if exact_bytes != fact_bundle_bytes:
        raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
            "fact_bundle_bytes differ from exact PR #57 semantic rebuild"
        )
    return rebuilt, exact_bytes


def build_reviewed_match_details_field_evidence_qualification(
    *,
    evidence: Any,
    evidence_receipt_bytes: Any,
    manifest_bytes: Any,
    raw_bytes: Any,
    assessment: Any,
    assessment_bytes: Any,
    review: Any,
    review_bytes: Any,
    fact_bundle: Any,
    fact_bundle_bytes: Any,
    decisions: Any,
    reviewed_at: Any,
    reviewer_reference: Any,
) -> ReviewedMatchDetailsFieldEvidenceQualification:
    """Record explicit exact-observation qualification without status promotion."""

    rebuilt, exact_fact_bundle_bytes = _revalidate_fact_bundle(
        evidence=evidence,
        evidence_receipt_bytes=evidence_receipt_bytes,
        manifest_bytes=manifest_bytes,
        raw_bytes=raw_bytes,
        assessment=assessment,
        assessment_bytes=assessment_bytes,
        review=review,
        review_bytes=review_bytes,
        fact_bundle=fact_bundle,
        fact_bundle_bytes=fact_bundle_bytes,
    )
    semantic_reviewed_at = _utc(
        getattr(review, "reviewed_at", None),
        "semantic_reviewed_at",
    )
    reviewed_at = _utc(reviewed_at, "reviewed_at")
    reviewer_reference = _text(
        reviewer_reference,
        "reviewer_reference",
        256,
    )
    if semantic_reviewed_at < rebuilt.observed_at or semantic_reviewed_at >= rebuilt.kickoff:
        raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
            "semantic review chronology is incompatible with exact PR #57 observation"
        )
    if reviewed_at < semantic_reviewed_at or reviewed_at >= rebuilt.kickoff:
        raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
            "reviewed_at must not precede semantic review and must remain before kickoff"
        )

    if type(decisions) is not tuple or not decisions:
        raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
            "decisions must be a non-empty immutable tuple"
        )
    if any(type(item) is not MatchDetailsFieldEvidenceReviewDecision for item in decisions):
        raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
            "decisions must contain exact review decision values"
        )
    sorted_decisions = tuple(sorted(decisions, key=lambda item: item.key))
    if decisions != sorted_decisions:
        raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
            "review decisions must be deterministically sorted"
        )
    decision_keys = tuple(item.key for item in decisions)
    if len(set(decision_keys)) != len(decision_keys):
        raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
            "review decisions must target unique exact facts"
        )

    facts = tuple(
        sorted(
            rebuilt.facts,
            key=lambda item: (
                item.category.value,
                item.field,
                item.source_reference,
            ),
        )
    )
    fact_by_key = {
        _decision_key(item.category, item.field, item.source_reference): item
        for item in facts
    }
    if set(decision_keys) != set(fact_by_key):
        raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
            "review decisions must cover every and only exact PR #57 fact"
        )

    recorded: list[RecordedMatchDetailsFieldEvidenceDecision] = []
    for decision in decisions:
        fact = fact_by_key[decision.key]
        if fact.status is not IntelligenceFactStatus.UNVERIFIED:
            raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
                "qualification input facts must remain exact UNVERIFIED"
            )
        if fact.source_provider != SOURCE_PROVIDER:
            raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
                "qualification input source_provider mismatch"
            )
        if fact.source_role is not SourceRole.PRIMARY_FOOTBALL_CONTEXT:
            raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
                "qualification input source_role mismatch"
            )
        recorded.append(
            RecordedMatchDetailsFieldEvidenceDecision(
                category=decision.category,
                field=decision.field,
                source_reference=decision.source_reference,
                fact_sha256=_fact_sha256(fact),
                disposition=decision.disposition,
                rationale=decision.rationale,
            )
        )

    return ReviewedMatchDetailsFieldEvidenceQualification(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        qualification_scope=QUALIFICATION_SCOPE,
        fact_bundle_sha256=hashlib.sha256(exact_fact_bundle_bytes).hexdigest(),
        fact_bundle_size=len(exact_fact_bundle_bytes),
        fixture_identifier=rebuilt.fixture_identifier,
        source_match_id=rebuilt.source_match_id,
        kickoff=rebuilt.kickoff,
        observed_at=rebuilt.observed_at,
        semantic_reviewed_at=semantic_reviewed_at,
        raw_sha256=rebuilt.raw_sha256,
        evidence_file_path=rebuilt.evidence_file_path,
        source_provider=SOURCE_PROVIDER,
        source_role=SourceRole.PRIMARY_FOOTBALL_CONTEXT,
        reviewed_at=reviewed_at,
        reviewer_reference=reviewer_reference,
        decisions=tuple(recorded),
        safety=_default_safety(),
    )


def canonical_reviewed_match_details_field_evidence_qualification_bytes(
    value: Any,
) -> bytes:
    if type(value) is not ReviewedMatchDetailsFieldEvidenceQualification:
        raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
            "value must be exact ReviewedMatchDetailsFieldEvidenceQualification"
        )
    try:
        rebuilt = dataclasses.replace(value)
        return _canonical_json_bytes(rebuilt.to_dict())
    except FotMobReviewedMatchDetailsFieldEvidenceQualificationError:
        raise
    except (TypeError, ValueError, OverflowError, AttributeError) as exc:
        raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
            "field-evidence qualification canonicalization failed"
        ) from exc


def revalidate_reviewed_match_details_field_evidence_qualification(
    *,
    evidence: Any,
    evidence_receipt_bytes: Any,
    manifest_bytes: Any,
    raw_bytes: Any,
    assessment: Any,
    assessment_bytes: Any,
    review: Any,
    review_bytes: Any,
    fact_bundle: Any,
    fact_bundle_bytes: Any,
    qualification: Any,
    qualification_bytes: Any,
) -> ReviewedMatchDetailsFieldEvidenceQualification:
    """Replay PR #52 -> #58 before trusting an existing qualification record."""

    if type(qualification) is not ReviewedMatchDetailsFieldEvidenceQualification:
        raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
            "qualification must be exact ReviewedMatchDetailsFieldEvidenceQualification"
        )
    if type(qualification_bytes) is not bytes:
        raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
            "qualification_bytes must be exact immutable bytes"
        )
    try:
        supplied_bytes = canonical_reviewed_match_details_field_evidence_qualification_bytes(
            qualification
        )
        review_decisions = tuple(
            MatchDetailsFieldEvidenceReviewDecision(
                category=item.category,
                field=item.field,
                source_reference=item.source_reference,
                disposition=item.disposition,
                rationale=item.rationale,
            )
            for item in qualification.decisions
        )
        rebuilt = build_reviewed_match_details_field_evidence_qualification(
            evidence=evidence,
            evidence_receipt_bytes=evidence_receipt_bytes,
            manifest_bytes=manifest_bytes,
            raw_bytes=raw_bytes,
            assessment=assessment,
            assessment_bytes=assessment_bytes,
            review=review,
            review_bytes=review_bytes,
            fact_bundle=fact_bundle,
            fact_bundle_bytes=fact_bundle_bytes,
            decisions=review_decisions,
            reviewed_at=qualification.reviewed_at,
            reviewer_reference=qualification.reviewer_reference,
        )
        rebuilt_bytes = canonical_reviewed_match_details_field_evidence_qualification_bytes(
            rebuilt
        )
    except (
        FotMobReviewedMatchDetailsFieldEvidenceQualificationError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
            "PR #58 qualification failed exact full-chain revalidation"
        ) from exc
    if supplied_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
            "supplied PR #58 qualification differs from exact full-chain rebuild"
        )
    if qualification_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsFieldEvidenceQualificationError(
            "qualification_bytes are not exact canonical PR #58 bytes"
        )
    return rebuilt


def sha256_reviewed_match_details_field_evidence_qualification(value: Any) -> str:
    return hashlib.sha256(
        canonical_reviewed_match_details_field_evidence_qualification_bytes(value)
    ).hexdigest()


__all__ = [
    "DATASET_NAME",
    "QUALIFICATION_SCOPE",
    "RAW_FILENAME",
    "SCHEMA_VERSION",
    "FieldEvidenceQualificationDisposition",
    "FotMobReviewedMatchDetailsFieldEvidenceQualificationError",
    "MatchDetailsFieldEvidenceReviewDecision",
    "RecordedMatchDetailsFieldEvidenceDecision",
    "ReviewedMatchDetailsFieldEvidenceQualification",
    "build_reviewed_match_details_field_evidence_qualification",
    "canonical_reviewed_match_details_field_evidence_qualification_bytes",
    "revalidate_reviewed_match_details_field_evidence_qualification",
    "sha256_reviewed_match_details_field_evidence_qualification",
]
