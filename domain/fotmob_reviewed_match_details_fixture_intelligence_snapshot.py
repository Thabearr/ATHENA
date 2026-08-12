"""Build one real PR #30 snapshot from an exact admitted PR #64 whole set.

This is the reviewed ancestry wrapper around the first real Fixture
Intelligence snapshot in the FotMob match-details chain.  It performs only the
mechanical PR #30 construction and grants no downstream model authority.
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import re
import types
from collections.abc import Mapping
from typing import Any

from domain.fixture_intelligence import (
    FixtureIntelligenceError,
    FixtureIntelligenceFact,
    FixtureIntelligenceSnapshot,
    build_snapshot,
    canonical_snapshot_bytes,
)
from domain.fotmob_reviewed_match_details_snapshot_candidate_admission import (
    FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError,
    SnapshotCandidateAdmissionDisposition,
    SnapshotCandidateCompletenessAttestation,
    canonical_reviewed_match_details_snapshot_candidate_admission_bytes,
    revalidate_reviewed_match_details_snapshot_candidate_admission,
)
from domain.fotmob_reviewed_match_details_snapshot_candidate_set import (
    FotMobReviewedMatchDetailsSnapshotCandidateSetError,
    ReviewedMatchDetailsSnapshotCandidateSet,
    canonical_reviewed_match_details_snapshot_candidate_set_bytes,
    revalidate_reviewed_match_details_snapshot_candidate_set,
    sha256_materialized_reviewed_match_details_fact,
)


SCHEMA_VERSION = 1
DATASET_NAME = (
    "athena-fotmob-reviewed-match-details-fixture-intelligence-snapshot-v1"
)

_SHA_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_FIXTURE_RE = re.compile(r"^FOTMOB:([1-9][0-9]*)$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "source_wide_qualification_authorized",
        "source_identity_resolution_authorized",
        "conflict_resolution_authorized",
        "model_feature_authorized",
        "probability_authorized",
        "pricing_authorized",
        "selection_authorized",
        "production_approval_authorized",
        "bet_authorized",
    }
)


class FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(ValueError):
    """Raised when an admitted whole-set snapshot cannot be proven exactly."""


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _text(value: Any, label: str, maximum: int) -> str:
    if type(value) is not str or not value or value != value.strip() or len(value) > maximum:
        raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
            f"{label} must be a non-empty exact trimmed string within {maximum} characters"
        )
    return value


def _utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime) or value.tzinfo is not datetime.timezone.utc:
        raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
            f"{label} must already use exact datetime.timezone.utc"
        )
    return value


def _iso(value: datetime.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _hashes(value: Any, label: str, *, unique: bool) -> tuple[str, ...]:
    if type(value) is not tuple or not value:
        raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
            f"{label} must be a non-empty immutable tuple"
        )
    rebuilt = tuple(_sha(item, label) for item in value)
    if rebuilt != tuple(sorted(rebuilt)):
        raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
            f"{label} must be deterministically sorted"
        )
    if unique and len(set(rebuilt)) != len(rebuilt):
        raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
            f"{label} must contain unique values"
        )
    return rebuilt


def _default_safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
            "safety keys mismatch"
        )
    if any(type(item) is not bool or item is not False for item in value.values()):
        raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
            "all downstream safety values must be exact bool False"
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
        raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
            "reviewed snapshot wrapper serialization failed"
        ) from exc


def _rebuild_snapshot(value: Any) -> tuple[FixtureIntelligenceSnapshot, bytes]:
    if type(value) is not FixtureIntelligenceSnapshot:
        raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
            "snapshot must be exact FixtureIntelligenceSnapshot"
        )
    if type(value.facts) is not tuple:
        raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
            "snapshot facts must remain an immutable tuple"
        )
    try:
        facts = tuple(dataclasses.replace(item) for item in value.facts)
        rebuilt = build_snapshot(
            value.fixture_identifier,
            value.kickoff,
            value.as_of,
            facts,
        )
        exact_bytes = canonical_snapshot_bytes(rebuilt)
    except (
        FixtureIntelligenceError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
            "nested PR #30 snapshot failed exact invariant reconstruction"
        ) from exc
    try:
        supplied_bytes = canonical_snapshot_bytes(value)
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
            "supplied nested PR #30 snapshot is not canonically serializable"
        ) from exc
    if supplied_bytes != exact_bytes:
        raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
            "nested PR #30 snapshot differs from exact PR #30 reconstruction"
        )
    return rebuilt, exact_bytes


@dataclasses.dataclass(frozen=True)
class ReviewedMatchDetailsFixtureIntelligenceSnapshot:
    """Exact PR #52→PR #65 ancestry wrapper around one real PR #30 snapshot."""

    schema_version: int
    dataset_name: str
    admission_sha256: str
    admission_size: int
    candidate_set_sha256: str
    candidate_set_size: int
    fixture_identifier: str
    source_match_id: str
    kickoff: datetime.datetime
    classified_at: datetime.datetime
    admission_reviewed_at: datetime.datetime
    member_count: int
    fact_count: int
    materialization_sha256s: tuple[str, ...]
    materialized_fact_sha256s: tuple[str, ...]
    snapshot: FixtureIntelligenceSnapshot
    snapshot_sha256: str
    snapshot_size: int
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
                "schema_version mismatch"
            )
        if self.dataset_name != DATASET_NAME:
            raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
                "dataset_name mismatch"
            )
        admission_sha = _sha(self.admission_sha256, "admission_sha256")
        candidate_sha = _sha(self.candidate_set_sha256, "candidate_set_sha256")
        snapshot_sha = _sha(self.snapshot_sha256, "snapshot_sha256")
        for label in ("admission_size", "candidate_set_size", "snapshot_size"):
            if type(getattr(self, label)) is not int or getattr(self, label) <= 0:
                raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
                    f"{label} must be an exact positive integer"
                )
        fixture_identifier = _text(self.fixture_identifier, "fixture_identifier", 512)
        source_match_id = _text(self.source_match_id, "source_match_id", 256)
        match = _FIXTURE_RE.fullmatch(fixture_identifier)
        if match is None or match.group(1) != source_match_id:
            raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
                "fixture_identifier/source_match_id mismatch"
            )
        kickoff = _utc(self.kickoff, "kickoff")
        classified_at = _utc(self.classified_at, "classified_at")
        reviewed_at = _utc(self.admission_reviewed_at, "admission_reviewed_at")
        if classified_at >= kickoff:
            raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
                "classified_at must remain strictly before kickoff"
            )
        if reviewed_at < classified_at or reviewed_at >= kickoff:
            raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
                "admission_reviewed_at chronology mismatch"
            )
        for label in ("member_count", "fact_count"):
            if type(getattr(self, label)) is not int or getattr(self, label) <= 0:
                raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
                    f"{label} must be an exact positive integer"
                )
        materializations = _hashes(
            self.materialization_sha256s,
            "materialization_sha256s",
            unique=True,
        )
        fact_hashes = _hashes(
            self.materialized_fact_sha256s,
            "materialized_fact_sha256s",
            unique=False,
        )
        if len(materializations) != self.member_count or len(fact_hashes) != self.fact_count:
            raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
                "lineage identities must cover exact member and fact counts"
            )

        rebuilt_snapshot, exact_snapshot_bytes = _rebuild_snapshot(self.snapshot)
        if rebuilt_snapshot.fixture_identifier != fixture_identifier:
            raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
                "snapshot fixture_identifier differs from wrapper"
            )
        if rebuilt_snapshot.kickoff != kickoff or rebuilt_snapshot.as_of != classified_at:
            raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
                "snapshot kickoff/as_of differ from exact candidate classification moment"
            )
        if len(rebuilt_snapshot.facts) != self.fact_count:
            raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
                "snapshot fact count differs from exact candidate fact count"
            )
        rebuilt_fact_hashes = tuple(
            sorted(
                sha256_materialized_reviewed_match_details_fact(item)
                for item in rebuilt_snapshot.facts
            )
        )
        if rebuilt_fact_hashes != fact_hashes:
            raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
                "snapshot facts differ from exact materialized-fact identities"
            )
        if hashlib.sha256(exact_snapshot_bytes).hexdigest() != snapshot_sha:
            raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
                "snapshot_sha256 differs from exact PR #30 canonical bytes"
            )
        if len(exact_snapshot_bytes) != self.snapshot_size:
            raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
                "snapshot_size differs from exact PR #30 canonical bytes"
            )
        safety = _validate_safety(self.safety)
        object.__setattr__(self, "admission_sha256", admission_sha)
        object.__setattr__(self, "candidate_set_sha256", candidate_sha)
        object.__setattr__(self, "snapshot_sha256", snapshot_sha)
        object.__setattr__(self, "fixture_identifier", fixture_identifier)
        object.__setattr__(self, "source_match_id", source_match_id)
        object.__setattr__(self, "kickoff", kickoff)
        object.__setattr__(self, "classified_at", classified_at)
        object.__setattr__(self, "admission_reviewed_at", reviewed_at)
        object.__setattr__(self, "materialization_sha256s", materializations)
        object.__setattr__(self, "materialized_fact_sha256s", fact_hashes)
        object.__setattr__(self, "snapshot", rebuilt_snapshot)
        object.__setattr__(self, "safety", safety)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "admission_sha256": self.admission_sha256,
            "admission_size": self.admission_size,
            "candidate_set_sha256": self.candidate_set_sha256,
            "candidate_set_size": self.candidate_set_size,
            "fixture_identifier": self.fixture_identifier,
            "source_match_id": self.source_match_id,
            "kickoff": _iso(self.kickoff),
            "classified_at": _iso(self.classified_at),
            "admission_reviewed_at": _iso(self.admission_reviewed_at),
            "member_count": self.member_count,
            "fact_count": self.fact_count,
            "materialization_sha256s": list(self.materialization_sha256s),
            "materialized_fact_sha256s": list(self.materialized_fact_sha256s),
            "snapshot": self.snapshot.to_dict(),
            "snapshot_sha256": self.snapshot_sha256,
            "snapshot_size": self.snapshot_size,
            "safety": dict(self.safety),
        }


def build_reviewed_match_details_fixture_intelligence_snapshot(
    *,
    materialization_inputs: Any,
    candidate_set: Any,
    candidate_set_bytes: Any,
    admission: Any,
    admission_bytes: Any,
) -> ReviewedMatchDetailsFixtureIntelligenceSnapshot:
    """Replay PR #52→PR #64 and mechanically call PR #30 build_snapshot."""

    try:
        rebuilt_candidate = revalidate_reviewed_match_details_snapshot_candidate_set(
            materialization_inputs=materialization_inputs,
            candidate_set=candidate_set,
            candidate_set_bytes=candidate_set_bytes,
        )
        exact_candidate_bytes = canonical_reviewed_match_details_snapshot_candidate_set_bytes(
            rebuilt_candidate
        )
        rebuilt_admission = revalidate_reviewed_match_details_snapshot_candidate_admission(
            materialization_inputs=materialization_inputs,
            candidate_set=rebuilt_candidate,
            candidate_set_bytes=exact_candidate_bytes,
            admission=admission,
            admission_bytes=admission_bytes,
        )
        exact_admission_bytes = canonical_reviewed_match_details_snapshot_candidate_admission_bytes(
            rebuilt_admission
        )
    except (
        FotMobReviewedMatchDetailsSnapshotCandidateSetError,
        FotMobReviewedMatchDetailsSnapshotCandidateAdmissionError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
            "PR #52 -> PR #64 chain failed exact full-chain revalidation"
        ) from exc
    if rebuilt_admission.decision.disposition is not SnapshotCandidateAdmissionDisposition.ADMITTED:
        raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
            "only an exact ADMITTED PR #64 whole candidate set may create a snapshot"
        )
    if rebuilt_admission.decision.completeness_attestation is not (
        SnapshotCandidateCompletenessAttestation.NO_KNOWN_OMITTED_REVIEWED_MATERIALIZATIONS
    ):
        raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
            "ADMITTED PR #64 lacks the exact narrow reviewer attestation"
        )
    decision = rebuilt_admission.decision
    if (
        decision.candidate_set_sha256 != hashlib.sha256(exact_candidate_bytes).hexdigest()
        or decision.candidate_set_size != len(exact_candidate_bytes)
        or decision.fixture_identifier != rebuilt_candidate.fixture_identifier
        or decision.source_match_id != rebuilt_candidate.source_match_id
        or decision.kickoff != rebuilt_candidate.kickoff
        or decision.classified_at != rebuilt_candidate.classified_at
        or decision.member_count != rebuilt_candidate.member_count
        or decision.fact_count != len(rebuilt_candidate.facts)
        or decision.materialization_sha256s
        != tuple(item.materialization_sha256 for item in rebuilt_candidate.members)
        or decision.materialized_fact_sha256s
        != tuple(sorted(item.materialized_fact_sha256 for item in rebuilt_candidate.fact_lineage))
    ):
        raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
            "PR #64 decision does not bind every and only exact PR #63 identity"
        )
    try:
        snapshot = build_snapshot(
            rebuilt_candidate.fixture_identifier,
            rebuilt_candidate.kickoff,
            rebuilt_candidate.classified_at,
            rebuilt_candidate.facts,
        )
        snapshot_bytes = canonical_snapshot_bytes(snapshot)
    except (
        FixtureIntelligenceError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
            "exact admitted candidate facts failed mechanical PR #30 snapshot construction"
        ) from exc
    return ReviewedMatchDetailsFixtureIntelligenceSnapshot(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        admission_sha256=hashlib.sha256(exact_admission_bytes).hexdigest(),
        admission_size=len(exact_admission_bytes),
        candidate_set_sha256=hashlib.sha256(exact_candidate_bytes).hexdigest(),
        candidate_set_size=len(exact_candidate_bytes),
        fixture_identifier=rebuilt_candidate.fixture_identifier,
        source_match_id=rebuilt_candidate.source_match_id,
        kickoff=rebuilt_candidate.kickoff,
        classified_at=rebuilt_candidate.classified_at,
        admission_reviewed_at=decision.reviewed_at,
        member_count=rebuilt_candidate.member_count,
        fact_count=len(rebuilt_candidate.facts),
        materialization_sha256s=decision.materialization_sha256s,
        materialized_fact_sha256s=decision.materialized_fact_sha256s,
        snapshot=snapshot,
        snapshot_sha256=hashlib.sha256(snapshot_bytes).hexdigest(),
        snapshot_size=len(snapshot_bytes),
        safety=_default_safety(),
    )


def reviewed_match_details_fixture_intelligence_snapshot_to_dict(
    value: Any,
) -> dict[str, Any]:
    if type(value) is not ReviewedMatchDetailsFixtureIntelligenceSnapshot:
        raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
            "value must be exact PR #65 snapshot wrapper"
        )
    return dataclasses.replace(value).to_dict()


def canonical_reviewed_match_details_fixture_intelligence_snapshot_bytes(
    value: Any,
) -> bytes:
    if type(value) is not ReviewedMatchDetailsFixtureIntelligenceSnapshot:
        raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
            "value must be exact PR #65 snapshot wrapper"
        )
    try:
        return _canonical_json_bytes(dataclasses.replace(value).to_dict())
    except FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError:
        raise
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
            "reviewed snapshot wrapper canonicalization failed"
        ) from exc


def revalidate_reviewed_match_details_fixture_intelligence_snapshot(
    *,
    materialization_inputs: Any,
    candidate_set: Any,
    candidate_set_bytes: Any,
    admission: Any,
    admission_bytes: Any,
    artifact: Any,
    artifact_bytes: Any,
) -> ReviewedMatchDetailsFixtureIntelligenceSnapshot:
    """Replay PR #52→PR #65 and reject detached or coordinated mutation."""

    if type(artifact) is not ReviewedMatchDetailsFixtureIntelligenceSnapshot:
        raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
            "artifact must be exact PR #65 snapshot wrapper"
        )
    if type(artifact_bytes) is not bytes:
        raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
            "artifact_bytes must be exact immutable bytes"
        )
    try:
        supplied_bytes = canonical_reviewed_match_details_fixture_intelligence_snapshot_bytes(
            artifact
        )
        rebuilt = build_reviewed_match_details_fixture_intelligence_snapshot(
            materialization_inputs=materialization_inputs,
            candidate_set=candidate_set,
            candidate_set_bytes=candidate_set_bytes,
            admission=admission,
            admission_bytes=admission_bytes,
        )
        rebuilt_bytes = canonical_reviewed_match_details_fixture_intelligence_snapshot_bytes(
            rebuilt
        )
    except (
        FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
            "PR #52 -> PR #65 snapshot chain failed exact full-chain revalidation"
        ) from exc
    if supplied_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
            "supplied PR #65 wrapper differs from exact full-chain rebuild"
        )
    if artifact_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError(
            "artifact_bytes are not exact canonical PR #65 bytes"
        )
    return rebuilt


def sha256_reviewed_match_details_fixture_intelligence_snapshot(value: Any) -> str:
    return hashlib.sha256(
        canonical_reviewed_match_details_fixture_intelligence_snapshot_bytes(value)
    ).hexdigest()


__all__ = [
    "DATASET_NAME",
    "SCHEMA_VERSION",
    "FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError",
    "ReviewedMatchDetailsFixtureIntelligenceSnapshot",
    "build_reviewed_match_details_fixture_intelligence_snapshot",
    "canonical_reviewed_match_details_fixture_intelligence_snapshot_bytes",
    "revalidate_reviewed_match_details_fixture_intelligence_snapshot",
    "reviewed_match_details_fixture_intelligence_snapshot_to_dict",
    "sha256_reviewed_match_details_fixture_intelligence_snapshot",
]
