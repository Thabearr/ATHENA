"""Explicit review gate between UNREVIEWED FotMob candidates and catalog input."""

from __future__ import annotations

import dataclasses
import datetime
import enum
import hashlib
import json
import re
import types
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any, Tuple

from domain.fotmob_data_matches_capture import RAW_FILENAME, capture_identifier, serialize_utc
from domain.fotmob_fixture_candidates import (
    FotMobFixtureCandidate,
    FotMobFixtureCandidateBundle,
    sha256_fotmob_fixture_candidate_bundle,
)


SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-fixture-candidate-review-v1"
SOURCE_NAME = "FOTMOB"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "raw_capture_authorized",
        "schema_assessment_authorized",
        "candidate_generation_authorized",
        "automatic_review_authorized",
        "source_qualified",
        "team_identity_resolution_authorized",
        "competition_identity_resolution_authorized",
        "fixture_identity_resolution_authorized",
        "fixture_catalog_compile_authorized",
        "fixture_catalog_promotion_authorized",
        "intelligence_authorized",
        "model_feature_authorized",
        "probability_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
    }
)


class FotMobFixtureCandidateReviewError(ValueError):
    """Raised when candidate review evidence fails closed."""


class FixtureCandidateReviewDisposition(str, enum.Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class FixtureCandidateReviewBlockReason(str, enum.Enum):
    DUPLICATE_SOURCE_MATCH_ID = "DUPLICATE_SOURCE_MATCH_ID"
    FIXTURE_IDENTITY_CONFLICT = "FIXTURE_IDENTITY_CONFLICT"
    HOME_TEAM_IDENTITY_CONFLICT = "HOME_TEAM_IDENTITY_CONFLICT"
    AWAY_TEAM_IDENTITY_CONFLICT = "AWAY_TEAM_IDENTITY_CONFLICT"
    COMPETITION_IDENTITY_CONFLICT = "COMPETITION_IDENTITY_CONFLICT"
    CATALOG_HOME_TEAM_INVALID = "CATALOG_HOME_TEAM_INVALID"
    CATALOG_AWAY_TEAM_INVALID = "CATALOG_AWAY_TEAM_INVALID"
    CATALOG_COMPETITION_INVALID = "CATALOG_COMPETITION_INVALID"
    CATALOG_HOME_AWAY_EQUAL = "CATALOG_HOME_AWAY_EQUAL"


def _exact_int(value: Any, label: str, *, minimum: int | None = None) -> int:
    if type(value) is not int or (minimum is not None and value < minimum):
        qualifier = f" >= {minimum}" if minimum is not None else ""
        raise FotMobFixtureCandidateReviewError(f"{label} must be an exact integer{qualifier}")
    return value


def _exact_str(value: Any, label: str, *, non_empty: bool = False, trimmed: bool = False) -> str:
    if type(value) is not str:
        raise FotMobFixtureCandidateReviewError(f"{label} must be an exact string")
    if non_empty and not value:
        raise FotMobFixtureCandidateReviewError(f"{label} must be non-empty")
    if trimmed and value != value.strip():
        raise FotMobFixtureCandidateReviewError(f"{label} must not contain surrounding whitespace")
    return value


def _sha256(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise FotMobFixtureCandidateReviewError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise FotMobFixtureCandidateReviewError(f"{label} must be a datetime")
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            raise FotMobFixtureCandidateReviewError(f"{label} must be timezone-aware")
        return value.astimezone(datetime.timezone.utc)
    except FotMobFixtureCandidateReviewError:
        raise
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobFixtureCandidateReviewError(f"{label} is invalid") from exc


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(_SAFETY_KEYS)}


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise FotMobFixtureCandidateReviewError("safety keys mismatch")
    detached: dict[str, bool] = {}
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise FotMobFixtureCandidateReviewError(f"safety[{key!r}] must be exact bool False")
        detached[key] = False
    return types.MappingProxyType(detached)


def canonical_fotmob_fixture_candidate_bytes(candidate: Any) -> bytes:
    if not isinstance(candidate, FotMobFixtureCandidate):
        raise FotMobFixtureCandidateReviewError("candidate must be FotMobFixtureCandidate")
    try:
        return (
            json.dumps(
                candidate.to_dict(),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobFixtureCandidateReviewError("candidate serialization failed") from exc


def sha256_fotmob_fixture_candidate(candidate: Any) -> str:
    return hashlib.sha256(canonical_fotmob_fixture_candidate_bytes(candidate)).hexdigest()


@dataclasses.dataclass(frozen=True)
class FotMobFixtureCandidateReviewDecision:
    source_capture_manifest_sha256: str
    source_match_id: int
    candidate_sha256: str
    disposition: FixtureCandidateReviewDisposition
    reviewed_at: datetime.datetime
    reviewer_reference: str
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_capture_manifest_sha256",
            _sha256(self.source_capture_manifest_sha256, "source_capture_manifest_sha256"),
        )
        _exact_int(self.source_match_id, "source_match_id")
        object.__setattr__(self, "candidate_sha256", _sha256(self.candidate_sha256, "candidate_sha256"))
        if type(self.disposition) is not FixtureCandidateReviewDisposition:
            raise FotMobFixtureCandidateReviewError("disposition must be FixtureCandidateReviewDisposition")
        object.__setattr__(self, "reviewed_at", _utc(self.reviewed_at, "reviewed_at"))
        _exact_str(self.reviewer_reference, "reviewer_reference", non_empty=True, trimmed=True)
        _exact_str(self.notes, "notes")

    @property
    def candidate_key(self) -> tuple[str, int, str]:
        return (
            self.source_capture_manifest_sha256,
            self.source_match_id,
            self.candidate_sha256,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_capture_manifest_sha256": self.source_capture_manifest_sha256,
            "source_match_id": self.source_match_id,
            "candidate_sha256": self.candidate_sha256,
            "disposition": self.disposition.value,
            "reviewed_at": serialize_utc(self.reviewed_at),
            "reviewer_reference": self.reviewer_reference,
            "notes": self.notes,
        }


@dataclasses.dataclass(frozen=True)
class FotMobFixtureCandidateReviewBlock:
    source_capture_manifest_sha256: str
    source_match_id: int
    candidate_sha256: str
    reasons: Tuple[FixtureCandidateReviewBlockReason, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_capture_manifest_sha256",
            _sha256(self.source_capture_manifest_sha256, "source_capture_manifest_sha256"),
        )
        _exact_int(self.source_match_id, "source_match_id")
        object.__setattr__(self, "candidate_sha256", _sha256(self.candidate_sha256, "candidate_sha256"))
        if type(self.reasons) is not tuple or not self.reasons:
            raise FotMobFixtureCandidateReviewError("block reasons must be a non-empty tuple")
        if any(type(item) is not FixtureCandidateReviewBlockReason for item in self.reasons):
            raise FotMobFixtureCandidateReviewError("block reasons contain an invalid value")
        if self.reasons != tuple(sorted(set(self.reasons), key=lambda item: item.value)):
            raise FotMobFixtureCandidateReviewError("block reasons must be sorted and unique")

    @property
    def candidate_key(self) -> tuple[str, int, str]:
        return (
            self.source_capture_manifest_sha256,
            self.source_match_id,
            self.candidate_sha256,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_capture_manifest_sha256": self.source_capture_manifest_sha256,
            "source_match_id": self.source_match_id,
            "candidate_sha256": self.candidate_sha256,
            "reasons": [item.value for item in self.reasons],
        }


@dataclasses.dataclass(frozen=True)
class FotMobReviewedFixtureCatalogInput:
    source_capture_manifest_sha256: str
    candidate_sha256: str
    source_fixture_identifier: str
    home_team: str
    away_team: str
    competition: str
    kickoff: datetime.datetime
    source_reference: str
    reviewed_at: datetime.datetime
    evidence_file_path: str
    evidence_sha256: str
    reviewer_reference: str
    notes: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_capture_manifest_sha256",
            _sha256(self.source_capture_manifest_sha256, "source_capture_manifest_sha256"),
        )
        object.__setattr__(self, "candidate_sha256", _sha256(self.candidate_sha256, "candidate_sha256"))
        for label in (
            "source_fixture_identifier",
            "home_team",
            "away_team",
            "competition",
            "source_reference",
            "evidence_file_path",
            "reviewer_reference",
        ):
            _exact_str(getattr(self, label), label, non_empty=True, trimmed=True)
        if self.home_team == self.away_team:
            raise FotMobFixtureCandidateReviewError("home_team and away_team must differ")
        object.__setattr__(self, "kickoff", _utc(self.kickoff, "kickoff"))
        object.__setattr__(self, "reviewed_at", _utc(self.reviewed_at, "reviewed_at"))
        object.__setattr__(self, "evidence_sha256", _sha256(self.evidence_sha256, "evidence_sha256"))
        _exact_str(self.notes, "notes")

    def to_catalog_input_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "source": SOURCE_NAME,
            "source_fixture_identifier": self.source_fixture_identifier,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "competition": self.competition,
            "kickoff": serialize_utc(self.kickoff),
            "source_reference": self.source_reference,
            "reviewed_at": serialize_utc(self.reviewed_at),
            "evidence_file_path": self.evidence_file_path,
            "evidence_sha256": self.evidence_sha256,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_capture_manifest_sha256": self.source_capture_manifest_sha256,
            "candidate_sha256": self.candidate_sha256,
            "catalog_input": self.to_catalog_input_dict(),
            "reviewer_reference": self.reviewer_reference,
            "notes": self.notes,
        }


@dataclasses.dataclass(frozen=True)
class FotMobFixtureCandidateReviewBundle:
    schema_version: int
    dataset_name: str
    candidate_bundle_sha256: str
    candidate_count: int
    decision_count: int
    approved_count: int
    rejected_count: int
    unreviewed_count: int
    blocked_candidate_count: int
    blocked_candidates: Tuple[FotMobFixtureCandidateReviewBlock, ...]
    decisions: Tuple[FotMobFixtureCandidateReviewDecision, ...]
    approved_catalog_inputs: Tuple[FotMobReviewedFixtureCatalogInput, ...]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise FotMobFixtureCandidateReviewError("schema_version must be exact integer 1")
        if self.dataset_name != DATASET_NAME:
            raise FotMobFixtureCandidateReviewError(f"dataset_name must be {DATASET_NAME}")
        object.__setattr__(
            self,
            "candidate_bundle_sha256",
            _sha256(self.candidate_bundle_sha256, "candidate_bundle_sha256"),
        )
        for label in (
            "candidate_count",
            "decision_count",
            "approved_count",
            "rejected_count",
            "unreviewed_count",
            "blocked_candidate_count",
        ):
            _exact_int(getattr(self, label), label, minimum=0)
        if type(self.blocked_candidates) is not tuple or any(
            not isinstance(item, FotMobFixtureCandidateReviewBlock) for item in self.blocked_candidates
        ):
            raise FotMobFixtureCandidateReviewError("blocked_candidates must be an immutable block tuple")
        if type(self.decisions) is not tuple or any(
            not isinstance(item, FotMobFixtureCandidateReviewDecision) for item in self.decisions
        ):
            raise FotMobFixtureCandidateReviewError("decisions must be an immutable decision tuple")
        if type(self.approved_catalog_inputs) is not tuple or any(
            not isinstance(item, FotMobReviewedFixtureCatalogInput) for item in self.approved_catalog_inputs
        ):
            raise FotMobFixtureCandidateReviewError(
                "approved_catalog_inputs must be an immutable reviewed-input tuple"
            )
        block_keys = tuple(item.candidate_key for item in self.blocked_candidates)
        decision_keys = tuple(item.candidate_key for item in self.decisions)
        if block_keys != tuple(sorted(block_keys)) or len(set(block_keys)) != len(block_keys):
            raise FotMobFixtureCandidateReviewError("blocked candidates must be sorted and unique")
        if decision_keys != tuple(sorted(decision_keys)) or len(set(decision_keys)) != len(decision_keys):
            raise FotMobFixtureCandidateReviewError("decisions must be sorted and unique")
        approved_keys = tuple(
            (item.source_capture_manifest_sha256, int(item.source_fixture_identifier), item.candidate_sha256)
            for item in self.approved_catalog_inputs
        )
        if approved_keys != tuple(sorted(approved_keys)) or len(set(approved_keys)) != len(approved_keys):
            raise FotMobFixtureCandidateReviewError("approved catalog inputs must be sorted and unique")
        if self.decision_count != len(self.decisions):
            raise FotMobFixtureCandidateReviewError("decision_count mismatch")
        if self.approved_count != len(self.approved_catalog_inputs):
            raise FotMobFixtureCandidateReviewError("approved_count mismatch")
        expected_approved = sum(
            1 for item in self.decisions if item.disposition is FixtureCandidateReviewDisposition.APPROVED
        )
        expected_rejected = sum(
            1 for item in self.decisions if item.disposition is FixtureCandidateReviewDisposition.REJECTED
        )
        if self.approved_count != expected_approved or self.rejected_count != expected_rejected:
            raise FotMobFixtureCandidateReviewError("decision disposition counts mismatch")
        if self.decision_count != self.approved_count + self.rejected_count:
            raise FotMobFixtureCandidateReviewError("decision counts do not reconcile")
        if self.candidate_count != self.decision_count + self.unreviewed_count:
            raise FotMobFixtureCandidateReviewError("candidate review counts do not reconcile")
        if self.blocked_candidate_count != len(self.blocked_candidates):
            raise FotMobFixtureCandidateReviewError("blocked_candidate_count mismatch")
        if any(key in set(block_keys) for key in approved_keys):
            raise FotMobFixtureCandidateReviewError("blocked candidate cannot appear in approved catalog inputs")
        approved_decision_keys = tuple(
            item.candidate_key
            for item in self.decisions
            if item.disposition is FixtureCandidateReviewDisposition.APPROVED
        )
        if approved_keys != approved_decision_keys:
            raise FotMobFixtureCandidateReviewError("approved catalog inputs do not match approved decisions")
        object.__setattr__(self, "safety", _validate_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "candidate_bundle_sha256": self.candidate_bundle_sha256,
            "candidate_count": self.candidate_count,
            "decision_count": self.decision_count,
            "approved_count": self.approved_count,
            "rejected_count": self.rejected_count,
            "unreviewed_count": self.unreviewed_count,
            "blocked_candidate_count": self.blocked_candidate_count,
            "blocked_candidates": [item.to_dict() for item in self.blocked_candidates],
            "decisions": [item.to_dict() for item in self.decisions],
            "approved_catalog_inputs": [item.to_dict() for item in self.approved_catalog_inputs],
            "safety": dict(self.safety),
        }


def _catalog_string_valid(value: str) -> bool:
    return bool(value) and value == value.strip()


def _candidate_key(candidate: FotMobFixtureCandidate) -> tuple[str, int, str]:
    return (
        candidate.source_capture_manifest_sha256,
        candidate.source_match_id,
        sha256_fotmob_fixture_candidate(candidate),
    )


def _derive_blocks(
    bundle: FotMobFixtureCandidateBundle,
) -> Tuple[FotMobFixtureCandidateReviewBlock, ...]:
    source_id_counts = Counter(item.source_match_id for item in bundle.candidates)
    fixture_conflict_ids = {item.source_match_id for item in bundle.fixture_identity_conflicts}
    team_conflict_ids = {item.source_team_id for item in bundle.team_identity_conflicts}
    competition_conflict_ids = {
        item.source_league_id for item in bundle.competition_identity_conflicts
    }
    blocks: list[FotMobFixtureCandidateReviewBlock] = []
    for candidate in bundle.candidates:
        reasons: set[FixtureCandidateReviewBlockReason] = set()
        if source_id_counts[candidate.source_match_id] > 1:
            reasons.add(FixtureCandidateReviewBlockReason.DUPLICATE_SOURCE_MATCH_ID)
        if candidate.source_match_id in fixture_conflict_ids:
            reasons.add(FixtureCandidateReviewBlockReason.FIXTURE_IDENTITY_CONFLICT)
        if candidate.home_source_team_id in team_conflict_ids:
            reasons.add(FixtureCandidateReviewBlockReason.HOME_TEAM_IDENTITY_CONFLICT)
        if candidate.away_source_team_id in team_conflict_ids:
            reasons.add(FixtureCandidateReviewBlockReason.AWAY_TEAM_IDENTITY_CONFLICT)
        if candidate.source_league_id in competition_conflict_ids:
            reasons.add(FixtureCandidateReviewBlockReason.COMPETITION_IDENTITY_CONFLICT)
        if not _catalog_string_valid(candidate.home_name):
            reasons.add(FixtureCandidateReviewBlockReason.CATALOG_HOME_TEAM_INVALID)
        if not _catalog_string_valid(candidate.away_name):
            reasons.add(FixtureCandidateReviewBlockReason.CATALOG_AWAY_TEAM_INVALID)
        if not _catalog_string_valid(candidate.source_competition_name):
            reasons.add(FixtureCandidateReviewBlockReason.CATALOG_COMPETITION_INVALID)
        if candidate.home_name == candidate.away_name:
            reasons.add(FixtureCandidateReviewBlockReason.CATALOG_HOME_AWAY_EQUAL)
        if reasons:
            manifest_sha, source_match_id, candidate_sha = _candidate_key(candidate)
            blocks.append(
                FotMobFixtureCandidateReviewBlock(
                    source_capture_manifest_sha256=manifest_sha,
                    source_match_id=source_match_id,
                    candidate_sha256=candidate_sha,
                    reasons=tuple(sorted(reasons, key=lambda item: item.value)),
                )
            )
    return tuple(sorted(blocks, key=lambda item: item.candidate_key))


def _reviewed_catalog_input(
    candidate: FotMobFixtureCandidate,
    decision: FotMobFixtureCandidateReviewDecision,
    source: Any,
) -> FotMobReviewedFixtureCatalogInput:
    capture_name = capture_identifier(
        request_date=source.request_date,
        timezone=source.timezone,
        ccode3=source.ccode3,
        observed_at=source.source_observed_at,
        raw_sha256=source.source_raw_sha256,
    )
    evidence_path = f"{source.request_date}/{capture_name}/{RAW_FILENAME}"
    source_reference = (
        "FotMob /api/data/matches capture manifest sha256:"
        f"{source.source_capture_manifest_sha256}"
    )
    return FotMobReviewedFixtureCatalogInput(
        source_capture_manifest_sha256=candidate.source_capture_manifest_sha256,
        candidate_sha256=decision.candidate_sha256,
        source_fixture_identifier=str(candidate.source_match_id),
        home_team=candidate.home_name,
        away_team=candidate.away_name,
        competition=candidate.source_competition_name,
        kickoff=candidate.kickoff_utc,
        source_reference=source_reference,
        reviewed_at=decision.reviewed_at,
        evidence_file_path=evidence_path,
        evidence_sha256=candidate.source_raw_sha256,
        reviewer_reference=decision.reviewer_reference,
        notes=decision.notes,
    )


def build_fotmob_fixture_candidate_review_bundle(
    candidate_bundle: Any,
    decisions: Sequence[FotMobFixtureCandidateReviewDecision],
) -> FotMobFixtureCandidateReviewBundle:
    """Validate explicit human review decisions without automatic promotion."""

    if not isinstance(candidate_bundle, FotMobFixtureCandidateBundle):
        raise FotMobFixtureCandidateReviewError(
            "candidate_bundle must be FotMobFixtureCandidateBundle"
        )
    if not isinstance(decisions, Sequence) or isinstance(decisions, (str, bytes)):
        raise FotMobFixtureCandidateReviewError("decisions must be a decision sequence")
    supplied_decisions = tuple(decisions)
    if any(not isinstance(item, FotMobFixtureCandidateReviewDecision) for item in supplied_decisions):
        raise FotMobFixtureCandidateReviewError("decisions contain an invalid value")

    candidate_map: dict[tuple[str, int, str], FotMobFixtureCandidate] = {}
    for candidate in candidate_bundle.candidates:
        key = _candidate_key(candidate)
        if key in candidate_map:
            raise FotMobFixtureCandidateReviewError("candidate bundle contains an ambiguous review key")
        candidate_map[key] = candidate

    ordered_decisions = tuple(sorted(supplied_decisions, key=lambda item: item.candidate_key))
    decision_keys = tuple(item.candidate_key for item in ordered_decisions)
    if len(set(decision_keys)) != len(decision_keys):
        raise FotMobFixtureCandidateReviewError("duplicate review decision")

    blocked_candidates = _derive_blocks(candidate_bundle)
    blocked_keys = {item.candidate_key for item in blocked_candidates}
    source_map = {
        item.source_capture_manifest_sha256: item for item in candidate_bundle.sources
    }
    approved: list[FotMobReviewedFixtureCatalogInput] = []
    for decision in ordered_decisions:
        candidate = candidate_map.get(decision.candidate_key)
        if candidate is None:
            raise FotMobFixtureCandidateReviewError(
                "review decision does not match an exact candidate and candidate SHA-256"
            )
        if decision.reviewed_at < candidate.source_observed_at:
            raise FotMobFixtureCandidateReviewError(
                "reviewed_at must not precede the candidate source observation"
            )
        if decision.disposition is FixtureCandidateReviewDisposition.APPROVED:
            if decision.candidate_key in blocked_keys:
                raise FotMobFixtureCandidateReviewError(
                    "candidate has unresolved review blockers and cannot be approved"
                )
            source = source_map.get(candidate.source_capture_manifest_sha256)
            if source is None:
                raise FotMobFixtureCandidateReviewError("candidate source ancestry is absent")
            approved.append(_reviewed_catalog_input(candidate, decision, source))

    approved_inputs = tuple(
        sorted(
            approved,
            key=lambda item: (
                item.source_capture_manifest_sha256,
                int(item.source_fixture_identifier),
                item.candidate_sha256,
            ),
        )
    )
    approved_count = len(approved_inputs)
    rejected_count = sum(
        1
        for item in ordered_decisions
        if item.disposition is FixtureCandidateReviewDisposition.REJECTED
    )
    return FotMobFixtureCandidateReviewBundle(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        candidate_bundle_sha256=sha256_fotmob_fixture_candidate_bundle(candidate_bundle),
        candidate_count=candidate_bundle.candidate_count,
        decision_count=len(ordered_decisions),
        approved_count=approved_count,
        rejected_count=rejected_count,
        unreviewed_count=candidate_bundle.candidate_count - len(ordered_decisions),
        blocked_candidate_count=len(blocked_candidates),
        blocked_candidates=blocked_candidates,
        decisions=ordered_decisions,
        approved_catalog_inputs=approved_inputs,
        safety=_default_safety(),
    )


def canonical_fotmob_fixture_candidate_review_bundle_bytes(bundle: Any) -> bytes:
    if not isinstance(bundle, FotMobFixtureCandidateReviewBundle):
        raise FotMobFixtureCandidateReviewError(
            "bundle must be FotMobFixtureCandidateReviewBundle"
        )
    try:
        return (
            json.dumps(
                bundle.to_dict(),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobFixtureCandidateReviewError("review bundle serialization failed") from exc


def sha256_fotmob_fixture_candidate_review_bundle(bundle: Any) -> str:
    return hashlib.sha256(
        canonical_fotmob_fixture_candidate_review_bundle_bytes(bundle)
    ).hexdigest()


__all__ = [
    "DATASET_NAME",
    "SCHEMA_VERSION",
    "SOURCE_NAME",
    "FixtureCandidateReviewBlockReason",
    "FixtureCandidateReviewDisposition",
    "FotMobFixtureCandidateReviewBlock",
    "FotMobFixtureCandidateReviewBundle",
    "FotMobFixtureCandidateReviewDecision",
    "FotMobFixtureCandidateReviewError",
    "FotMobReviewedFixtureCatalogInput",
    "build_fotmob_fixture_candidate_review_bundle",
    "canonical_fotmob_fixture_candidate_bytes",
    "canonical_fotmob_fixture_candidate_review_bundle_bytes",
    "sha256_fotmob_fixture_candidate",
    "sha256_fotmob_fixture_candidate_review_bundle",
]
