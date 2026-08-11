"""Human admission of one exact PR #63 candidate set for later review only.

This module deliberately does not create a Fixture Intelligence snapshot.  It
records a narrow human decision about one fully replayed candidate set and no
claim about global completeness, source-wide qualification, or model use.
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

from domain.fotmob_reviewed_match_details_snapshot_candidate_set import (
    FotMobReviewedMatchDetailsSnapshotCandidateSetError,
    ReviewedMatchDetailsSnapshotCandidateSet,
    canonical_reviewed_match_details_snapshot_candidate_set_bytes,
    revalidate_reviewed_match_details_snapshot_candidate_set,
)


SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-reviewed-match-details-snapshot-candidate-admission-v1"
ADMISSION_SCOPE = "EXACT_FIXTURE_CLASSIFICATION_MOMENT_CANDIDATE_SET_ONLY"

_SHA_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_FIXTURE_RE = re.compile(r"^FOTMOB:([1-9][0-9]*)$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "source_wide_qualification_authorized",
        "source_identity_resolution_authorized",
        "snapshot_creation_authorized",
        "conflict_resolution_authorized",
        "model_feature_authorized",
        "probability_authorized",
        "pricing_authorized",
        "selection_authorized",
        "production_approval_authorized",
        "bet_authorized",
    }
)


class FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(ValueError):
    """Raised when an exact candidate-set admission cannot be proven."""


class SnapshotCandidateAdmissionDisposition(str, enum.Enum):
    ADMITTED = "ADMITTED"
    REJECTED = "REJECTED"


class SnapshotCandidateCompletenessAttestation(str, enum.Enum):
    """Narrow reviewer statement; never an objective global-completeness claim."""

    NO_KNOWN_OMITTED_REVIEWED_MATERIALIZATIONS = (
        "NO_KNOWN_OMITTED_REVIEWED_MATERIALIZATIONS"
    )
    NOT_ATTESTED = "NOT_ATTESTED"


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _text(value: Any, label: str, maximum: int) -> str:
    if type(value) is not str or not value or value != value.strip() or len(value) > maximum:
        raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
            f"{label} must be a non-empty exact trimmed string within {maximum} characters"
        )
    return value


def _utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime) or value.tzinfo is not datetime.timezone.utc:
        raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
            f"{label} must already use exact datetime.timezone.utc"
        )
    return value


def _iso(value: datetime.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _hashes(value: Any, label: str, *, unique: bool) -> tuple[str, ...]:
    if type(value) is not tuple or not value:
        raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
            f"{label} must be a non-empty immutable tuple"
        )
    rebuilt = tuple(_sha(item, label) for item in value)
    if rebuilt != tuple(sorted(rebuilt)):
        raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
            f"{label} must be deterministically sorted"
        )
    if unique and len(set(rebuilt)) != len(rebuilt):
        raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
            f"{label} must contain unique values"
        )
    return rebuilt


def _default_safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
            "safety keys mismatch"
        )
    if any(type(item) is not bool or item is not False for item in value.values()):
        raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
            "all safety values must be exact bool False"
        )
    return _default_safety()


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
        raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
            "candidate admission serialization failed"
        ) from exc


def _candidate_identity(candidate: Any) -> dict[str, Any]:
    if type(candidate) is not ReviewedMatchDetailsSnapshotCandidateSet:
        raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
            "candidate set must be exact PR #63 type"
        )
    try:
        rebuilt = dataclasses.replace(candidate)
        exact_bytes = canonical_reviewed_match_details_snapshot_candidate_set_bytes(
            rebuilt
        )
    except (
        FotMobReviewedMatchDetailsSnapshotCandidateSetError,
        AttributeError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
            "candidate set failed local PR #63 invariant revalidation"
        ) from exc
    member_shas = tuple(item.materialization_sha256 for item in rebuilt.members)
    fact_hashes = tuple(
        sorted(item.materialized_fact_sha256 for item in rebuilt.fact_lineage)
    )
    if len(member_shas) != rebuilt.member_count or len(fact_hashes) != len(rebuilt.facts):
        raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
            "candidate set member or fact identity count mismatch"
        )
    return {
        "candidate_set_sha256": hashlib.sha256(exact_bytes).hexdigest(),
        "candidate_set_size": len(exact_bytes),
        "fixture_identifier": rebuilt.fixture_identifier,
        "source_match_id": rebuilt.source_match_id,
        "kickoff": rebuilt.kickoff,
        "classified_at": rebuilt.classified_at,
        "member_count": rebuilt.member_count,
        "fact_count": len(rebuilt.facts),
        "materialization_sha256s": member_shas,
        # This is an ordered multiset, not a deduplicating semantic set.
        "materialized_fact_sha256s": fact_hashes,
    }


@dataclasses.dataclass(frozen=True)
class ReviewedMatchDetailsSnapshotCandidateAdmissionDecision:
    """Explicit human disposition anchored to the whole exact PR #63 identity."""

    candidate_set_sha256: str
    candidate_set_size: int
    fixture_identifier: str
    source_match_id: str
    kickoff: datetime.datetime
    classified_at: datetime.datetime
    member_count: int
    fact_count: int
    materialization_sha256s: tuple[str, ...]
    materialized_fact_sha256s: tuple[str, ...]
    disposition: SnapshotCandidateAdmissionDisposition
    completeness_attestation: SnapshotCandidateCompletenessAttestation
    reviewed_at: datetime.datetime
    reviewer_reference: str
    rationale: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_set_sha256", _sha(self.candidate_set_sha256, "candidate_set_sha256"))
        if type(self.candidate_set_size) is not int or self.candidate_set_size <= 0:
            raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
                "candidate_set_size must be an exact positive integer"
            )
        fixture_identifier = _text(self.fixture_identifier, "fixture_identifier", 512)
        source_match_id = _text(self.source_match_id, "source_match_id", 256)
        match = _FIXTURE_RE.fullmatch(fixture_identifier)
        if match is None or match.group(1) != source_match_id:
            raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
                "fixture_identifier/source_match_id mismatch"
            )
        kickoff = _utc(self.kickoff, "kickoff")
        classified_at = _utc(self.classified_at, "classified_at")
        reviewed_at = _utc(self.reviewed_at, "reviewed_at")
        if classified_at > reviewed_at:
            raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
                "reviewed_at must not predate classified_at"
            )
        if reviewed_at >= kickoff:
            raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
                "reviewed_at must remain strictly before kickoff"
            )
        for label in ("member_count", "fact_count"):
            if type(getattr(self, label)) is not int or getattr(self, label) <= 0:
                raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
                    f"{label} must be an exact positive integer"
                )
        materializations = _hashes(
            self.materialization_sha256s, "materialization_sha256s", unique=True
        )
        facts = _hashes(
            self.materialized_fact_sha256s, "materialized_fact_sha256s", unique=False
        )
        if len(materializations) != self.member_count or len(facts) != self.fact_count:
            raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
                "decision member/fact identities must cover every and only candidate identity"
            )
        if not isinstance(self.disposition, SnapshotCandidateAdmissionDisposition):
            raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
                "disposition must be SnapshotCandidateAdmissionDisposition"
            )
        if not isinstance(self.completeness_attestation, SnapshotCandidateCompletenessAttestation):
            raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
                "completeness_attestation must be SnapshotCandidateCompletenessAttestation"
            )
        expected_attestation = (
            SnapshotCandidateCompletenessAttestation.NO_KNOWN_OMITTED_REVIEWED_MATERIALIZATIONS
            if self.disposition is SnapshotCandidateAdmissionDisposition.ADMITTED
            else SnapshotCandidateCompletenessAttestation.NOT_ATTESTED
        )
        if self.completeness_attestation is not expected_attestation:
            raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
                "disposition requires its exact narrow completeness attestation"
            )
        object.__setattr__(self, "fixture_identifier", fixture_identifier)
        object.__setattr__(self, "source_match_id", source_match_id)
        object.__setattr__(self, "kickoff", kickoff)
        object.__setattr__(self, "classified_at", classified_at)
        object.__setattr__(self, "reviewed_at", reviewed_at)
        object.__setattr__(self, "materialization_sha256s", materializations)
        object.__setattr__(self, "materialized_fact_sha256s", facts)
        object.__setattr__(self, "reviewer_reference", _text(self.reviewer_reference, "reviewer_reference", 512))
        object.__setattr__(self, "rationale", _text(self.rationale, "rationale", 2048))

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_set_sha256": self.candidate_set_sha256,
            "candidate_set_size": self.candidate_set_size,
            "fixture_identifier": self.fixture_identifier,
            "source_match_id": self.source_match_id,
            "kickoff": _iso(self.kickoff),
            "classified_at": _iso(self.classified_at),
            "member_count": self.member_count,
            "fact_count": self.fact_count,
            "materialization_sha256s": list(self.materialization_sha256s),
            "materialized_fact_sha256s": list(self.materialized_fact_sha256s),
            "disposition": self.disposition.value,
            "completeness_attestation": self.completeness_attestation.value,
            "reviewed_at": _iso(self.reviewed_at),
            "reviewer_reference": self.reviewer_reference,
            "rationale": self.rationale,
        }


@dataclasses.dataclass(frozen=True)
class AdmittedReviewedMatchDetailsSnapshotCandidateIdentity:
    """The one detached whole-candidate identity exposed only for ADMITTED."""

    candidate_set_sha256: str
    candidate_set_size: int
    fixture_identifier: str
    source_match_id: str
    kickoff: datetime.datetime
    classified_at: datetime.datetime
    member_count: int
    fact_count: int
    materialization_sha256s: tuple[str, ...]
    materialized_fact_sha256s: tuple[str, ...]

    @classmethod
    def from_decision(
        cls, decision: ReviewedMatchDetailsSnapshotCandidateAdmissionDecision
    ) -> "AdmittedReviewedMatchDetailsSnapshotCandidateIdentity":
        return cls(
            candidate_set_sha256=decision.candidate_set_sha256,
            candidate_set_size=decision.candidate_set_size,
            fixture_identifier=decision.fixture_identifier,
            source_match_id=decision.source_match_id,
            kickoff=decision.kickoff,
            classified_at=decision.classified_at,
            member_count=decision.member_count,
            fact_count=decision.fact_count,
            materialization_sha256s=decision.materialization_sha256s,
            materialized_fact_sha256s=decision.materialized_fact_sha256s,
        )

    def __post_init__(self) -> None:
        # Reuse the decision's strict identity/chronology contract without a human decision.
        probe = ReviewedMatchDetailsSnapshotCandidateAdmissionDecision(
            candidate_set_sha256=self.candidate_set_sha256,
            candidate_set_size=self.candidate_set_size,
            fixture_identifier=self.fixture_identifier,
            source_match_id=self.source_match_id,
            kickoff=self.kickoff,
            classified_at=self.classified_at,
            member_count=self.member_count,
            fact_count=self.fact_count,
            materialization_sha256s=self.materialization_sha256s,
            materialized_fact_sha256s=self.materialized_fact_sha256s,
            disposition=SnapshotCandidateAdmissionDisposition.ADMITTED,
            completeness_attestation=SnapshotCandidateCompletenessAttestation.NO_KNOWN_OMITTED_REVIEWED_MATERIALIZATIONS,
            reviewed_at=self.classified_at,
            reviewer_reference="identity",
            rationale="exact admitted candidate identity",
        )
        for field in (
            "candidate_set_sha256", "candidate_set_size", "fixture_identifier",
            "source_match_id", "kickoff", "classified_at", "member_count",
            "fact_count", "materialization_sha256s", "materialized_fact_sha256s",
        ):
            object.__setattr__(self, field, getattr(probe, field))

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_set_sha256": self.candidate_set_sha256,
            "candidate_set_size": self.candidate_set_size,
            "fixture_identifier": self.fixture_identifier,
            "source_match_id": self.source_match_id,
            "kickoff": _iso(self.kickoff),
            "classified_at": _iso(self.classified_at),
            "member_count": self.member_count,
            "fact_count": self.fact_count,
            "materialization_sha256s": list(self.materialization_sha256s),
            "materialized_fact_sha256s": list(self.materialized_fact_sha256s),
        }


@dataclasses.dataclass(frozen=True)
class ReviewedMatchDetailsSnapshotCandidateAdmission:
    """A human decision about one whole PR #63 set; not a PR #30 snapshot."""

    schema_version: int
    dataset_name: str
    admission_scope: str
    decision: ReviewedMatchDetailsSnapshotCandidateAdmissionDecision
    admitted_candidate_set_identities: tuple[AdmittedReviewedMatchDetailsSnapshotCandidateIdentity, ...]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError("schema_version mismatch")
        if self.dataset_name != DATASET_NAME or self.admission_scope != ADMISSION_SCOPE:
            raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
                "admission dataset or scope mismatch"
            )
        if type(self.decision) is not ReviewedMatchDetailsSnapshotCandidateAdmissionDecision:
            raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError("decision must be exact admission decision")
        try:
            decision = dataclasses.replace(self.decision)
        except (AttributeError, TypeError, ValueError) as exc:
            raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError("decision invariant revalidation failed") from exc
        identities = self.admitted_candidate_set_identities
        if type(identities) is not tuple or any(type(item) is not AdmittedReviewedMatchDetailsSnapshotCandidateIdentity for item in identities):
            raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
                "admitted_candidate_set_identities must be an immutable exact identity tuple"
            )
        try:
            rebuilt_identities = tuple(dataclasses.replace(item) for item in identities)
        except (AttributeError, TypeError, ValueError) as exc:
            raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError("admitted identity invariant revalidation failed") from exc
        expected = (
            (AdmittedReviewedMatchDetailsSnapshotCandidateIdentity.from_decision(decision),)
            if decision.disposition is SnapshotCandidateAdmissionDisposition.ADMITTED
            else ()
        )
        if rebuilt_identities != expected:
            raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
                "admission must expose one whole exact candidate identity only when ADMITTED"
            )
        object.__setattr__(self, "decision", decision)
        object.__setattr__(self, "admitted_candidate_set_identities", rebuilt_identities)
        object.__setattr__(self, "safety", _validate_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "admission_scope": self.admission_scope,
            "decision": self.decision.to_dict(),
            "admitted_candidate_set_identities": [item.to_dict() for item in self.admitted_candidate_set_identities],
            "safety": dict(self.safety),
        }


def admit_reviewed_match_details_snapshot_candidate_set(
    *,
    materialization_inputs: Any,
    candidate_set: Any,
    candidate_set_bytes: Any,
    disposition: Any,
    completeness_attestation: Any,
    reviewed_at: Any,
    reviewer_reference: Any,
    rationale: Any,
) -> ReviewedMatchDetailsSnapshotCandidateAdmission:
    """Replay PR #52→PR #63, then record a narrow supplied human decision."""

    try:
        rebuilt_candidate = revalidate_reviewed_match_details_snapshot_candidate_set(
            materialization_inputs=materialization_inputs,
            candidate_set=candidate_set,
            candidate_set_bytes=candidate_set_bytes,
        )
    except (
        FotMobReviewedMatchDetailsSnapshotCandidateSetError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
            "PR #52 -> PR #63 candidate chain failed exact full-chain revalidation"
        ) from exc
    identity = _candidate_identity(rebuilt_candidate)
    decision = ReviewedMatchDetailsSnapshotCandidateAdmissionDecision(
        **identity,
        disposition=disposition,
        completeness_attestation=completeness_attestation,
        reviewed_at=reviewed_at,
        reviewer_reference=reviewer_reference,
        rationale=rationale,
    )
    identities = (
        (AdmittedReviewedMatchDetailsSnapshotCandidateIdentity.from_decision(decision),)
        if decision.disposition is SnapshotCandidateAdmissionDisposition.ADMITTED
        else ()
    )
    return ReviewedMatchDetailsSnapshotCandidateAdmission(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        admission_scope=ADMISSION_SCOPE,
        decision=decision,
        admitted_candidate_set_identities=identities,
        safety=_default_safety(),
    )


def reviewed_match_details_snapshot_candidate_admission_to_dict(value: Any) -> dict[str, Any]:
    if type(value) is not ReviewedMatchDetailsSnapshotCandidateAdmission:
        raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
            "value must be exact PR #64 admission type"
        )
    return dataclasses.replace(value).to_dict()


def canonical_reviewed_match_details_snapshot_candidate_admission_bytes(value: Any) -> bytes:
    if type(value) is not ReviewedMatchDetailsSnapshotCandidateAdmission:
        raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
            "value must be exact PR #64 admission type"
        )
    try:
        return _canonical_json_bytes(dataclasses.replace(value).to_dict())
    except FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError:
        raise
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
            "candidate admission canonicalization failed"
        ) from exc


def revalidate_reviewed_match_details_snapshot_candidate_admission(
    *,
    materialization_inputs: Any,
    candidate_set: Any,
    candidate_set_bytes: Any,
    admission: Any,
    admission_bytes: Any,
) -> ReviewedMatchDetailsSnapshotCandidateAdmission:
    """Replay PR #52→PR #63 and rebuild the exact human admission artifact."""

    if type(admission) is not ReviewedMatchDetailsSnapshotCandidateAdmission:
        raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
            "admission must be exact PR #64 type"
        )
    if type(admission_bytes) is not bytes:
        raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
            "admission_bytes must be exact immutable bytes"
        )
    try:
        supplied_bytes = canonical_reviewed_match_details_snapshot_candidate_admission_bytes(admission)
        rebuilt = admit_reviewed_match_details_snapshot_candidate_set(
            materialization_inputs=materialization_inputs,
            candidate_set=candidate_set,
            candidate_set_bytes=candidate_set_bytes,
            disposition=admission.decision.disposition,
            completeness_attestation=admission.decision.completeness_attestation,
            reviewed_at=admission.decision.reviewed_at,
            reviewer_reference=admission.decision.reviewer_reference,
            rationale=admission.decision.rationale,
        )
        rebuilt_bytes = canonical_reviewed_match_details_snapshot_candidate_admission_bytes(rebuilt)
    except (
        FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
            "PR #52 -> PR #64 admission chain failed exact full-chain revalidation"
        ) from exc
    if supplied_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
            "supplied PR #64 admission differs from exact full-chain rebuild"
        )
    if admission_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError(
            "admission_bytes are not exact canonical PR #64 bytes"
        )
    return rebuilt


def sha256_reviewed_match_details_snapshot_candidate_admission(value: Any) -> str:
    return hashlib.sha256(
        canonical_reviewed_match_details_snapshot_candidate_admission_bytes(value)
    ).hexdigest()


__all__ = [
    "ADMISSION_SCOPE", "DATASET_NAME", "SCHEMA_VERSION",
    "AdmittedReviewedMatchDetailsSnapshotCandidateIdentity",
    "FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError",
    "ReviewedMatchDetailsSnapshotCandidateAdmission",
    "ReviewedMatchDetailsSnapshotCandidateAdmissionDecision",
    "SnapshotCandidateAdmissionDisposition",
    "SnapshotCandidateCompletenessAttestation",
    "admit_reviewed_match_details_snapshot_candidate_set",
    "canonical_reviewed_match_details_snapshot_candidate_admission_bytes",
    "revalidate_reviewed_match_details_snapshot_candidate_admission",
    "reviewed_match_details_snapshot_candidate_admission_to_dict",
    "sha256_reviewed_match_details_snapshot_candidate_admission",
]
