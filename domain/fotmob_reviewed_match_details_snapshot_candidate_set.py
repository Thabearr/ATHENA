"""Combine exact PR #62 materializations without admitting a PR #30 snapshot.

This boundary preserves a deliberately supplied set of independently replayed
PR #62 observations for one fixture and one prospective classification time.
It has no completeness claim, chooses no winner, and cannot be used as a
``FixtureIntelligenceSnapshot``.
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import math
import re
import types
from collections.abc import Mapping
from typing import Any

from domain.fixture_intelligence import (
    FixtureIntelligenceError,
    FixtureIntelligenceFact,
    IntelligenceCategory,
    IntelligenceFactStatus,
)
from domain.fotmob_reviewed_match_details_fact_status_materializer import (
    DATASET_NAME as MATERIALIZATION_DATASET_NAME,
    SCHEMA_VERSION as MATERIALIZATION_SCHEMA_VERSION,
    FotMobReviewedMatchDetailsFactStatusMaterializationError,
    ReviewedMatchDetailsFactStatusMaterialization,
    canonical_reviewed_match_details_fact_status_materialization_bytes,
    revalidate_reviewed_match_details_fact_status_materialization,
    sha256_original_reviewed_match_details_fact,
)


SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-reviewed-match-details-snapshot-candidate-set-v1"
CANDIDATE_SCOPE = "EXPLICIT_REVALIDATED_MATERIALIZATION_SET_ONLY"

_SHA_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_FIXTURE_RE = re.compile(r"^FOTMOB:([1-9][0-9]*)$", flags=re.ASCII)
_FIELD_RE = re.compile(r"^[-a-zA-Z0-9_]+$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "source_wide_qualification_authorized",
        "source_identity_resolution_authorized",
        "snapshot_admission_authorized",
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


class FotMobReviewedMatchDetailsSnapshotCandidateSetError(ValueError):
    """Raised when a candidate set cannot be proven from exact PR #62 chains."""


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
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
        raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
            f"{label} must be a non-empty exact trimmed string within {maximum} characters"
        )
    return value


def _utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime) or value.tzinfo is not datetime.timezone.utc:
        raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
            f"{label} must already use exact datetime.timezone.utc"
        )
    return value


def _iso(value: datetime.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _scalar(value: Any) -> str | int | float | bool:
    if type(value) in (bool, int, str):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
        "fact value must remain an exact finite PR #57 scalar"
    )


def _default_safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise FotMobReviewedMatchDetailsSnapshotCandidateSetError("safety keys mismatch")
    if any(type(item) is not bool or item is not False for item in value.values()):
        raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
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
        raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
            "snapshot candidate set serialization failed"
        ) from exc


def _fact_payload(fact: Any) -> dict[str, Any]:
    if type(fact) is not FixtureIntelligenceFact:
        raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
            "fact must be exact FixtureIntelligenceFact"
        )
    try:
        rebuilt = dataclasses.replace(fact)
    except (FixtureIntelligenceError, AttributeError, TypeError, ValueError) as exc:
        raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
            "fact failed exact PR #30 invariant revalidation"
        ) from exc
    return {
        "category": rebuilt.category.value,
        "field": rebuilt.field,
        "status": rebuilt.status.value,
        "value": _scalar(rebuilt.value),
        "source_provider": rebuilt.source_provider,
        "source_role": rebuilt.source_role.value,
        "source_reference": rebuilt.source_reference,
        "observed_at": _iso(rebuilt.observed_at),
        "evidence_file_path": rebuilt.evidence_file_path,
        "evidence_sha256": rebuilt.evidence_sha256,
        "notes": rebuilt.notes,
    }


def sha256_materialized_reviewed_match_details_fact(fact: Any) -> str:
    """Hash one complete status-materialized PR #30 fact without transformation."""

    return hashlib.sha256(_canonical_json_bytes(_fact_payload(fact))).hexdigest()


def _fact_lineage_key(
    materialization_sha256: str,
    original_fact_sha256: str,
) -> tuple[str, str]:
    return (materialization_sha256, original_fact_sha256)


@dataclasses.dataclass(frozen=True)
class ReviewedMatchDetailsMaterializationChainInput:
    """Execution-only complete input required to replay one PR #52 -> PR #62 chain.

    This wrapper is intentionally not a detached evidence artifact.  Its
    upstream objects acquire authority only when the PR #62 revalidator runs.
    """

    evidence: Any
    evidence_receipt_bytes: Any
    manifest_bytes: Any
    raw_bytes: Any
    assessment: Any
    assessment_bytes: Any
    review: Any
    review_bytes: Any
    fact_bundle: Any
    fact_bundle_bytes: Any
    qualification: Any
    qualification_bytes: Any
    policy: Any
    policy_bytes: Any
    evaluation: Any
    evaluation_bytes: Any
    materialization: Any
    materialization_bytes: Any


@dataclasses.dataclass(frozen=True)
class RecordedMatchDetailsSnapshotCandidateSetMember:
    """Canonical identity and counts for one fully replayed PR #62 member."""

    materialization_dataset_name: str
    materialization_schema_version: int
    materialization_sha256: str
    materialization_size: int
    fact_bundle_sha256: str
    evaluation_sha256: str
    fixture_identifier: str
    source_match_id: str
    kickoff: datetime.datetime
    classified_at: datetime.datetime
    supported_count: int
    stale_count: int
    unverified_count: int
    materialized_fact_sha256s: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.materialization_dataset_name != MATERIALIZATION_DATASET_NAME:
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "member materialization dataset mismatch"
            )
        if (
            type(self.materialization_schema_version) is not int
            or self.materialization_schema_version != MATERIALIZATION_SCHEMA_VERSION
        ):
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "member materialization schema mismatch"
            )
        for label in (
            "materialization_sha256",
            "fact_bundle_sha256",
            "evaluation_sha256",
        ):
            object.__setattr__(self, label, _sha(getattr(self, label), label))
        if type(self.materialization_size) is not int or self.materialization_size <= 0:
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "member materialization_size must be an exact positive integer"
            )
        fixture_identifier = _text(self.fixture_identifier, "fixture_identifier", 512)
        source_match_id = _text(self.source_match_id, "source_match_id", 256)
        match = _FIXTURE_RE.fullmatch(fixture_identifier)
        if match is None or match.group(1) != source_match_id:
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "member fixture_identifier/source_match_id mismatch"
            )
        kickoff = _utc(self.kickoff, "member kickoff")
        classified_at = _utc(self.classified_at, "member classified_at")
        if classified_at >= kickoff:
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "member classified_at must remain strictly before kickoff"
            )
        for label in ("supported_count", "stale_count", "unverified_count"):
            if type(getattr(self, label)) is not int or getattr(self, label) < 0:
                raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                    f"member {label} must be an exact non-negative integer"
                )
        hashes = self.materialized_fact_sha256s
        if type(hashes) is not tuple or not hashes:
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "member materialized_fact_sha256s must be a non-empty immutable tuple"
            )
        hashes = tuple(_sha(item, "materialized_fact_sha256") for item in hashes)
        if hashes != tuple(sorted(hashes)) or len(set(hashes)) != len(hashes):
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "member materialized_fact_sha256s must be sorted and unique"
            )
        if sum((self.supported_count, self.stale_count, self.unverified_count)) != len(hashes):
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "member status counts must equal exact materialized fact count"
            )
        object.__setattr__(self, "fixture_identifier", fixture_identifier)
        object.__setattr__(self, "source_match_id", source_match_id)
        object.__setattr__(self, "kickoff", kickoff)
        object.__setattr__(self, "classified_at", classified_at)
        object.__setattr__(self, "materialized_fact_sha256s", hashes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "materialization_dataset_name": self.materialization_dataset_name,
            "materialization_schema_version": self.materialization_schema_version,
            "materialization_sha256": self.materialization_sha256,
            "materialization_size": self.materialization_size,
            "fact_bundle_sha256": self.fact_bundle_sha256,
            "evaluation_sha256": self.evaluation_sha256,
            "fixture_identifier": self.fixture_identifier,
            "source_match_id": self.source_match_id,
            "kickoff": _iso(self.kickoff),
            "classified_at": _iso(self.classified_at),
            "supported_count": self.supported_count,
            "stale_count": self.stale_count,
            "unverified_count": self.unverified_count,
            "materialized_fact_sha256s": list(self.materialized_fact_sha256s),
        }


@dataclasses.dataclass(frozen=True)
class RecordedMatchDetailsSnapshotCandidateSetFactLineage:
    """Exact relationship between a flattened fact and its PR #62 member."""

    materialization_sha256: str
    original_fact_sha256: str
    materialized_fact_sha256: str
    category: IntelligenceCategory
    field: str
    source_reference: str
    status: IntelligenceFactStatus

    def __post_init__(self) -> None:
        for label in (
            "materialization_sha256",
            "original_fact_sha256",
            "materialized_fact_sha256",
        ):
            object.__setattr__(self, label, _sha(getattr(self, label), label))
        if not isinstance(self.category, IntelligenceCategory):
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "fact lineage category must be IntelligenceCategory"
            )
        field = _text(self.field, "fact lineage field", 128)
        if _FIELD_RE.fullmatch(field) is None:
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "fact lineage field violates the PR #30 field contract"
            )
        if not isinstance(self.status, IntelligenceFactStatus):
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "fact lineage status must be IntelligenceFactStatus"
            )
        if self.status is IntelligenceFactStatus.CONFLICTED:
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "candidate sets cannot assign per-observation CONFLICTED status"
            )
        object.__setattr__(self, "field", field)
        object.__setattr__(
            self,
            "source_reference",
            _text(self.source_reference, "fact lineage source_reference", 512),
        )

    @property
    def key(self) -> tuple[str, str]:
        return _fact_lineage_key(self.materialization_sha256, self.original_fact_sha256)

    def to_dict(self) -> dict[str, Any]:
        return {
            "materialization_sha256": self.materialization_sha256,
            "original_fact_sha256": self.original_fact_sha256,
            "materialized_fact_sha256": self.materialized_fact_sha256,
            "category": self.category.value,
            "field": self.field,
            "source_reference": self.source_reference,
            "status": self.status.value,
        }


@dataclasses.dataclass(frozen=True)
class ReviewedMatchDetailsSnapshotCandidateSet:
    """A lossless, non-admitted aggregation of revalidated PR #62 facts."""

    schema_version: int
    dataset_name: str
    candidate_scope: str
    fixture_identifier: str
    source_match_id: str
    kickoff: datetime.datetime
    classified_at: datetime.datetime
    member_count: int
    members: tuple[RecordedMatchDetailsSnapshotCandidateSetMember, ...]
    facts: tuple[FixtureIntelligenceFact, ...]
    fact_lineage: tuple[RecordedMatchDetailsSnapshotCandidateSetFactLineage, ...]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "schema_version mismatch"
            )
        if self.dataset_name != DATASET_NAME or self.candidate_scope != CANDIDATE_SCOPE:
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "candidate set dataset or scope mismatch"
            )
        fixture_identifier = _text(self.fixture_identifier, "fixture_identifier", 512)
        source_match_id = _text(self.source_match_id, "source_match_id", 256)
        match = _FIXTURE_RE.fullmatch(fixture_identifier)
        if match is None or match.group(1) != source_match_id:
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "fixture_identifier/source_match_id mismatch"
            )
        kickoff = _utc(self.kickoff, "kickoff")
        classified_at = _utc(self.classified_at, "classified_at")
        if classified_at >= kickoff:
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "classified_at must remain strictly before kickoff"
            )
        if type(self.member_count) is not int or self.member_count <= 0:
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "member_count must be an exact positive integer"
            )
        if type(self.members) is not tuple or len(self.members) != self.member_count:
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "members must be an exact immutable member_count tuple"
            )
        if any(type(item) is not RecordedMatchDetailsSnapshotCandidateSetMember for item in self.members):
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "members must contain exact recorded member values"
            )
        try:
            rebuilt_members = tuple(dataclasses.replace(item) for item in self.members)
        except (AttributeError, TypeError, ValueError) as exc:
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "nested member invariant revalidation failed"
            ) from exc
        if rebuilt_members != tuple(sorted(rebuilt_members, key=lambda item: item.materialization_sha256)):
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "members must be deterministically sorted by materialization SHA-256"
            )
        member_shas = tuple(item.materialization_sha256 for item in rebuilt_members)
        if len(set(member_shas)) != len(member_shas):
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "duplicate exact PR #62 materialization SHA-256 is forbidden"
            )
        for item in rebuilt_members:
            if (
                item.fixture_identifier != fixture_identifier
                or item.source_match_id != source_match_id
                or item.kickoff != kickoff
                or item.classified_at != classified_at
            ):
                raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                    "all members must share exact fixture, source match, kickoff, and classified_at"
                )

        if type(self.facts) is not tuple or not self.facts:
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "facts must be a non-empty immutable tuple"
            )
        if any(type(item) is not FixtureIntelligenceFact for item in self.facts):
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "facts must contain exact FixtureIntelligenceFact values"
            )
        try:
            rebuilt_facts = tuple(dataclasses.replace(item) for item in self.facts)
        except (FixtureIntelligenceError, AttributeError, TypeError, ValueError) as exc:
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "nested PR #30 fact invariant revalidation failed"
            ) from exc
        if type(self.fact_lineage) is not tuple or len(self.fact_lineage) != len(rebuilt_facts):
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "fact_lineage must bind one exact record to every flattened fact"
            )
        if any(type(item) is not RecordedMatchDetailsSnapshotCandidateSetFactLineage for item in self.fact_lineage):
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "fact_lineage must contain exact recorded fact lineage values"
            )
        try:
            rebuilt_lineage = tuple(dataclasses.replace(item) for item in self.fact_lineage)
        except (AttributeError, TypeError, ValueError) as exc:
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "nested fact-lineage invariant revalidation failed"
            ) from exc
        expected_lineage = tuple(sorted(rebuilt_lineage, key=lambda item: item.key))
        if rebuilt_lineage != expected_lineage:
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "fact_lineage must be deterministically sorted"
            )
        if len({item.key for item in rebuilt_lineage}) != len(rebuilt_lineage):
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "fact_lineage must not duplicate exact member/original-fact bindings"
            )
        if tuple(item.materialization_sha256 for item in rebuilt_lineage) != tuple(
            sorted(item.materialization_sha256 for item in rebuilt_lineage)
        ):
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "fact_lineage must group records by sorted member SHA-256"
            )

        expected_member_hashes: dict[str, list[str]] = {item: [] for item in member_shas}
        counts: dict[str, list[int]] = {item: [0, 0, 0] for item in member_shas}
        for fact, recorded in zip(rebuilt_facts, rebuilt_lineage):
            if recorded.materialization_sha256 not in expected_member_hashes:
                raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                    "fact lineage refers to an unknown member"
                )
            if fact.category is not recorded.category or fact.field != recorded.field:
                raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                    "flattened fact category/field disagrees with exact lineage"
                )
            if fact.source_reference != recorded.source_reference or fact.status is not recorded.status:
                raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                    "flattened fact source reference/status disagrees with exact lineage"
                )
            if fact.status is IntelligenceFactStatus.CONFLICTED:
                raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                    "candidate sets cannot assign per-observation CONFLICTED status"
                )
            materialized_hash = sha256_materialized_reviewed_match_details_fact(fact)
            if materialized_hash != recorded.materialized_fact_sha256:
                raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                    "flattened fact differs from its exact materialized fact hash"
                )
            try:
                original_projection = dataclasses.replace(
                    fact,
                    status=IntelligenceFactStatus.UNVERIFIED,
                )
            except (FixtureIntelligenceError, AttributeError, TypeError, ValueError) as exc:
                raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                    "flattened fact cannot reconstruct its original PR #57 payload"
                ) from exc
            if sha256_original_reviewed_match_details_fact(original_projection) != recorded.original_fact_sha256:
                raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                    "flattened fact differs from its exact original PR #57 fact"
                )
            expected_member_hashes[recorded.materialization_sha256].append(materialized_hash)
            if fact.status is IntelligenceFactStatus.SUPPORTED:
                counts[recorded.materialization_sha256][0] += 1
            elif fact.status is IntelligenceFactStatus.STALE:
                counts[recorded.materialization_sha256][1] += 1
            else:
                counts[recorded.materialization_sha256][2] += 1
        for item in rebuilt_members:
            if tuple(sorted(expected_member_hashes[item.materialization_sha256])) != item.materialized_fact_sha256s:
                raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                    "member fact identities do not match flattened exact facts"
                )
            if tuple(counts[item.materialization_sha256]) != (
                item.supported_count,
                item.stale_count,
                item.unverified_count,
            ):
                raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                    "member status counts do not match flattened exact facts"
                )

        safety = _validate_safety(self.safety)
        object.__setattr__(self, "fixture_identifier", fixture_identifier)
        object.__setattr__(self, "source_match_id", source_match_id)
        object.__setattr__(self, "kickoff", kickoff)
        object.__setattr__(self, "classified_at", classified_at)
        object.__setattr__(self, "members", rebuilt_members)
        object.__setattr__(self, "facts", rebuilt_facts)
        object.__setattr__(self, "fact_lineage", rebuilt_lineage)
        object.__setattr__(self, "safety", safety)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "candidate_scope": self.candidate_scope,
            "fixture_identifier": self.fixture_identifier,
            "source_match_id": self.source_match_id,
            "kickoff": _iso(self.kickoff),
            "classified_at": _iso(self.classified_at),
            "member_count": self.member_count,
            "members": [item.to_dict() for item in self.members],
            "facts": [_fact_payload(item) for item in self.facts],
            "fact_lineage": [item.to_dict() for item in self.fact_lineage],
            "safety": dict(self.safety),
        }


def _revalidate_member(
    value: ReviewedMatchDetailsMaterializationChainInput,
) -> tuple[ReviewedMatchDetailsFactStatusMaterialization, bytes]:
    try:
        rebuilt = revalidate_reviewed_match_details_fact_status_materialization(
            evidence=value.evidence,
            evidence_receipt_bytes=value.evidence_receipt_bytes,
            manifest_bytes=value.manifest_bytes,
            raw_bytes=value.raw_bytes,
            assessment=value.assessment,
            assessment_bytes=value.assessment_bytes,
            review=value.review,
            review_bytes=value.review_bytes,
            fact_bundle=value.fact_bundle,
            fact_bundle_bytes=value.fact_bundle_bytes,
            qualification=value.qualification,
            qualification_bytes=value.qualification_bytes,
            policy=value.policy,
            policy_bytes=value.policy_bytes,
            evaluation=value.evaluation,
            evaluation_bytes=value.evaluation_bytes,
            materialization=value.materialization,
            materialization_bytes=value.materialization_bytes,
        )
        exact_bytes = canonical_reviewed_match_details_fact_status_materialization_bytes(
            rebuilt
        )
    except (
        FotMobReviewedMatchDetailsFactStatusMaterializationError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
            "PR #52 -> PR #62 member chain failed exact full-chain revalidation"
        ) from exc
    if type(value.materialization_bytes) is not bytes or exact_bytes != value.materialization_bytes:
        raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
            "materialization_bytes differ from exact PR #62 full-chain rebuild"
        )
    return rebuilt, exact_bytes


def build_reviewed_match_details_snapshot_candidate_set(
    *,
    materialization_inputs: Any,
) -> ReviewedMatchDetailsSnapshotCandidateSet:
    """Replay and combine an explicit lossless set of exact PR #62 artifacts."""

    if type(materialization_inputs) is not tuple or not materialization_inputs:
        raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
            "materialization_inputs must be a non-empty immutable tuple"
        )
    if any(type(item) is not ReviewedMatchDetailsMaterializationChainInput for item in materialization_inputs):
        raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
            "materialization_inputs must contain exact execution-only chain wrappers"
        )

    rebuilt_members: list[tuple[ReviewedMatchDetailsFactStatusMaterialization, bytes]] = [
        _revalidate_member(item) for item in materialization_inputs
    ]
    materialization_shas = [hashlib.sha256(item[1]).hexdigest() for item in rebuilt_members]
    if len(set(materialization_shas)) != len(materialization_shas):
        raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
            "duplicate exact PR #62 materialization SHA-256 is forbidden"
        )
    rebuilt_members.sort(key=lambda item: hashlib.sha256(item[1]).hexdigest())
    first = rebuilt_members[0][0]

    members: list[RecordedMatchDetailsSnapshotCandidateSetMember] = []
    facts: list[FixtureIntelligenceFact] = []
    lineage: list[RecordedMatchDetailsSnapshotCandidateSetFactLineage] = []
    for materialization, materialization_bytes in rebuilt_members:
        if (
            materialization.fixture_identifier != first.fixture_identifier
            or materialization.source_match_id != first.source_match_id
            or materialization.kickoff != first.kickoff
            or materialization.classified_at != first.classified_at
        ):
            raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
                "all materializations must share exact fixture, source match, kickoff, and classified_at"
            )
        materialization_sha = hashlib.sha256(materialization_bytes).hexdigest()
        pairs = sorted(
            zip(materialization.materialized_facts, materialization.lineage),
            key=lambda pair: pair[1].original_fact_sha256,
        )
        materialized_hashes = tuple(
            sorted(sha256_materialized_reviewed_match_details_fact(fact) for fact, _ in pairs)
        )
        members.append(
            RecordedMatchDetailsSnapshotCandidateSetMember(
                materialization_dataset_name=materialization.dataset_name,
                materialization_schema_version=materialization.schema_version,
                materialization_sha256=materialization_sha,
                materialization_size=len(materialization_bytes),
                fact_bundle_sha256=materialization.fact_bundle_sha256,
                evaluation_sha256=materialization.evaluation_sha256,
                fixture_identifier=materialization.fixture_identifier,
                source_match_id=materialization.source_match_id,
                kickoff=materialization.kickoff,
                classified_at=materialization.classified_at,
                supported_count=materialization.supported_count,
                stale_count=materialization.stale_count,
                unverified_count=materialization.unverified_count,
                materialized_fact_sha256s=materialized_hashes,
            )
        )
        for fact, pr62_lineage in pairs:
            facts.append(fact)
            lineage.append(
                RecordedMatchDetailsSnapshotCandidateSetFactLineage(
                    materialization_sha256=materialization_sha,
                    original_fact_sha256=pr62_lineage.original_fact_sha256,
                    materialized_fact_sha256=sha256_materialized_reviewed_match_details_fact(
                        fact
                    ),
                    category=fact.category,
                    field=fact.field,
                    source_reference=fact.source_reference,
                    status=fact.status,
                )
            )

    return ReviewedMatchDetailsSnapshotCandidateSet(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        candidate_scope=CANDIDATE_SCOPE,
        fixture_identifier=first.fixture_identifier,
        source_match_id=first.source_match_id,
        kickoff=first.kickoff,
        classified_at=first.classified_at,
        member_count=len(members),
        members=tuple(members),
        facts=tuple(facts),
        fact_lineage=tuple(lineage),
        safety=_default_safety(),
    )


def reviewed_match_details_snapshot_candidate_set_to_dict(
    value: Any,
) -> dict[str, Any]:
    if type(value) is not ReviewedMatchDetailsSnapshotCandidateSet:
        raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
            "value must be exact ReviewedMatchDetailsSnapshotCandidateSet"
        )
    return dataclasses.replace(value).to_dict()


def canonical_reviewed_match_details_snapshot_candidate_set_bytes(value: Any) -> bytes:
    if type(value) is not ReviewedMatchDetailsSnapshotCandidateSet:
        raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
            "value must be exact ReviewedMatchDetailsSnapshotCandidateSet"
        )
    try:
        return _canonical_json_bytes(dataclasses.replace(value).to_dict())
    except FotMobReviewedMatchDetailsSnapshotCandidateSetError:
        raise
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
            "snapshot candidate set canonicalization failed"
        ) from exc


def revalidate_reviewed_match_details_snapshot_candidate_set(
    *,
    materialization_inputs: Any,
    candidate_set: Any,
    candidate_set_bytes: Any,
) -> ReviewedMatchDetailsSnapshotCandidateSet:
    """Replay every PR #52 -> PR #62 member before accepting a PR #63 artifact."""

    if type(candidate_set) is not ReviewedMatchDetailsSnapshotCandidateSet:
        raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
            "candidate_set must be exact PR #63 type"
        )
    if type(candidate_set_bytes) is not bytes:
        raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
            "candidate_set_bytes must be exact immutable bytes"
        )
    try:
        supplied_bytes = canonical_reviewed_match_details_snapshot_candidate_set_bytes(
            candidate_set
        )
        rebuilt = build_reviewed_match_details_snapshot_candidate_set(
            materialization_inputs=materialization_inputs
        )
        rebuilt_bytes = canonical_reviewed_match_details_snapshot_candidate_set_bytes(
            rebuilt
        )
    except (
        FotMobReviewedMatchDetailsSnapshotCandidateSetError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
            "PR #52 -> PR #63 candidate-set chain failed exact full-chain revalidation"
        ) from exc
    if supplied_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
            "supplied PR #63 candidate set differs from exact full-chain rebuild"
        )
    if candidate_set_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsSnapshotCandidateSetError(
            "candidate_set_bytes are not exact canonical PR #63 bytes"
        )
    return rebuilt


def sha256_reviewed_match_details_snapshot_candidate_set(value: Any) -> str:
    return hashlib.sha256(
        canonical_reviewed_match_details_snapshot_candidate_set_bytes(value)
    ).hexdigest()


__all__ = [
    "CANDIDATE_SCOPE",
    "DATASET_NAME",
    "SCHEMA_VERSION",
    "FotMobReviewedMatchDetailsSnapshotCandidateSetError",
    "RecordedMatchDetailsSnapshotCandidateSetFactLineage",
    "RecordedMatchDetailsSnapshotCandidateSetMember",
    "ReviewedMatchDetailsMaterializationChainInput",
    "ReviewedMatchDetailsSnapshotCandidateSet",
    "build_reviewed_match_details_snapshot_candidate_set",
    "canonical_reviewed_match_details_snapshot_candidate_set_bytes",
    "revalidate_reviewed_match_details_snapshot_candidate_set",
    "reviewed_match_details_snapshot_candidate_set_to_dict",
    "sha256_materialized_reviewed_match_details_fact",
    "sha256_reviewed_match_details_snapshot_candidate_set",
]
