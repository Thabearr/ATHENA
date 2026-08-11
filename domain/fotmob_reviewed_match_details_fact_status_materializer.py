"""Materialize exact PR #61 decisions as status-only PR #30 facts.

This is the first reviewed promotion boundary in the FotMob match-details
chain.  It replays PR #52 -> PR #61, independently rebuilds the legal PR #57
fact bundle, binds every decision by exact canonical fact SHA-256, and creates
new facts whose only changed payload field is ``status``.  It creates no
Fixture Intelligence snapshot and invokes no model or downstream system.
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
    SourceRole,
)
from domain.fotmob_reviewed_match_details_status_evaluator import (
    FotMobReviewedMatchDetailsStatusEvaluationError,
    ReviewedMatchDetailsStatusEvaluation,
    StatusEvaluationDisposition,
    canonical_reviewed_match_details_status_evaluation_bytes,
    revalidate_reviewed_match_details_status_evaluation,
)
from domain.fotmob_reviewed_match_details_unverified_facts import (
    FotMobReviewedMatchDetailsUnverifiedFactError,
    ReviewedMatchDetailsUnverifiedFactBundle,
    canonical_reviewed_match_details_unverified_fact_bundle_bytes,
    revalidate_reviewed_match_details_unverified_fact_bundle,
)


SCHEMA_VERSION = 1
DATASET_NAME = (
    "athena-fotmob-reviewed-match-details-fact-status-materialization-v1"
)
MATERIALIZATION_SCOPE = "EXACT_EVALUATED_OBSERVATION_ONLY"

_SHA_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_FIXTURE_RE = re.compile(r"^FOTMOB:([1-9][0-9]*)$", flags=re.ASCII)
_FIELD_RE = re.compile(r"^[-a-zA-Z0-9_]+$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "fact_status_materialization_authorized",
        "source_wide_qualification_authorized",
        "source_identity_resolution_authorized",
        "conflict_resolution_authorized",
        "intelligence_snapshot_authorized",
        "model_feature_authorized",
        "probability_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
    }
)


class FotMobReviewedMatchDetailsFactStatusMaterializationError(ValueError):
    """Raised when exact status-only materialization cannot be proven."""


STATUS_MAPPING: Mapping[StatusEvaluationDisposition, IntelligenceFactStatus] = (
    types.MappingProxyType(
        {
            StatusEvaluationDisposition.FRESH_QUALIFIED: (
                IntelligenceFactStatus.SUPPORTED
            ),
            StatusEvaluationDisposition.STALE_QUALIFIED: (
                IntelligenceFactStatus.STALE
            ),
            StatusEvaluationDisposition.BLOCKED_BY_QUALIFICATION: (
                IntelligenceFactStatus.UNVERIFIED
            ),
        }
    )
)


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
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
        raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
            f"{label} must be a non-empty exact trimmed string within {maximum} characters"
        )
    return value


def _utc(value: Any, label: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
            f"{label} must be a datetime"
        )
    if value.tzinfo is not datetime.timezone.utc:
        raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
            f"{label} must already use exact datetime.timezone.utc"
        )
    return value


def _iso(value: datetime.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _scalar(value: Any) -> str | int | float | bool:
    if type(value) is bool:
        return value
    if type(value) is int:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                "fact value must remain a finite exact PR #57 scalar"
            )
        return value
    if type(value) is str:
        return value
    raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
        "fact value must remain an exact PR #57 scalar"
    )


def _default_safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
            "safety keys mismatch"
        )
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                f"safety[{key!r}] must be exact bool False"
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
        raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
            "fact-status materialization serialization failed"
        ) from exc


def _fact_payload(fact: Any) -> dict[str, Any]:
    if type(fact) is not FixtureIntelligenceFact:
        raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
            "fact must be exact FixtureIntelligenceFact"
        )
    try:
        rebuilt = dataclasses.replace(fact)
    except (FixtureIntelligenceError, AttributeError, TypeError, ValueError) as exc:
        raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
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


def sha256_original_reviewed_match_details_fact(fact: Any) -> str:
    """Return the exact canonical fact hash used by PR #58 and PR #61."""

    return hashlib.sha256(_canonical_json_bytes(_fact_payload(fact))).hexdigest()


def _lineage_key(
    category: IntelligenceCategory,
    field: str,
    source_reference: str,
) -> tuple[str, str, str]:
    return (category.value, field, source_reference)


@dataclasses.dataclass(frozen=True)
class RecordedMatchDetailsFactStatusLineage:
    """One exact PR #57 fact, PR #61 disposition, and resulting PR #30 status."""

    category: IntelligenceCategory
    field: str
    source_reference: str
    original_fact_sha256: str
    evaluation_disposition: StatusEvaluationDisposition
    resulting_status: IntelligenceFactStatus

    def __post_init__(self) -> None:
        if not isinstance(self.category, IntelligenceCategory):
            raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                "category must be IntelligenceCategory"
            )
        field = _text(self.field, "field", 128)
        if _FIELD_RE.fullmatch(field) is None:
            raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                "field must match the Fixture Intelligence field contract"
            )
        source_reference = _text(
            self.source_reference,
            "source_reference",
            512,
        )
        fact_sha256 = _sha(self.original_fact_sha256, "original_fact_sha256")
        if not isinstance(self.evaluation_disposition, StatusEvaluationDisposition):
            raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                "evaluation_disposition must be StatusEvaluationDisposition"
            )
        if not isinstance(self.resulting_status, IntelligenceFactStatus):
            raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                "resulting_status must be IntelligenceFactStatus"
            )
        expected_status = STATUS_MAPPING[self.evaluation_disposition]
        if self.resulting_status is not expected_status:
            raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                "resulting_status disagrees with the exact PR #61 mapping"
            )
        if self.resulting_status is IntelligenceFactStatus.CONFLICTED:
            raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                "CONFLICTED status cannot be materialized per observation"
            )
        object.__setattr__(self, "field", field)
        object.__setattr__(self, "source_reference", source_reference)
        object.__setattr__(self, "original_fact_sha256", fact_sha256)

    @property
    def key(self) -> tuple[str, str, str]:
        return _lineage_key(self.category, self.field, self.source_reference)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "field": self.field,
            "source_reference": self.source_reference,
            "original_fact_sha256": self.original_fact_sha256,
            "evaluation_disposition": self.evaluation_disposition.value,
            "resulting_status": self.resulting_status.value,
        }


@dataclasses.dataclass(frozen=True)
class ReviewedMatchDetailsFactStatusMaterialization:
    """Detached exact-observation status materialization; no snapshot authority."""

    schema_version: int
    dataset_name: str
    materialization_scope: str
    fixture_identifier: str
    source_match_id: str
    kickoff: datetime.datetime
    classified_at: datetime.datetime
    fact_bundle_sha256: str
    fact_bundle_size: int
    evaluation_sha256: str
    evaluation_size: int
    materialized_facts: tuple[FixtureIntelligenceFact, ...]
    lineage: tuple[RecordedMatchDetailsFactStatusLineage, ...]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                "schema_version mismatch"
            )
        if self.dataset_name != DATASET_NAME:
            raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                "dataset_name mismatch"
            )
        if self.materialization_scope != MATERIALIZATION_SCOPE:
            raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                "materialization_scope must remain EXACT_EVALUATED_OBSERVATION_ONLY"
            )
        fixture_identifier = _text(
            self.fixture_identifier,
            "fixture_identifier",
            512,
        )
        source_match_id = _text(self.source_match_id, "source_match_id", 256)
        match = _FIXTURE_RE.fullmatch(fixture_identifier)
        if match is None or match.group(1) != source_match_id:
            raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                "fixture_identifier/source_match_id mismatch"
            )
        kickoff = _utc(self.kickoff, "kickoff")
        classified_at = _utc(self.classified_at, "classified_at")
        if classified_at >= kickoff:
            raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                "classified_at must remain strictly before kickoff"
            )
        fact_bundle_sha256 = _sha(self.fact_bundle_sha256, "fact_bundle_sha256")
        evaluation_sha256 = _sha(self.evaluation_sha256, "evaluation_sha256")
        for label in ("fact_bundle_size", "evaluation_size"):
            value = getattr(self, label)
            if type(value) is not int or value <= 0:
                raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                    f"{label} must be an exact positive integer"
                )

        if type(self.materialized_facts) is not tuple or not self.materialized_facts:
            raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                "materialized_facts must be a non-empty immutable tuple"
            )
        if any(type(item) is not FixtureIntelligenceFact for item in self.materialized_facts):
            raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                "materialized_facts must contain exact FixtureIntelligenceFact values"
            )
        try:
            rebuilt_facts = tuple(
                dataclasses.replace(item) for item in self.materialized_facts
            )
        except (FixtureIntelligenceError, AttributeError, TypeError, ValueError) as exc:
            raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                "nested materialized fact failed PR #30 invariant revalidation"
            ) from exc

        if type(self.lineage) is not tuple or not self.lineage:
            raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                "lineage must be a non-empty immutable tuple"
            )
        if any(type(item) is not RecordedMatchDetailsFactStatusLineage for item in self.lineage):
            raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                "lineage must contain exact recorded lineage values"
            )
        try:
            rebuilt_lineage = tuple(dataclasses.replace(item) for item in self.lineage)
        except (
            FotMobReviewedMatchDetailsFactStatusMaterializationError,
            AttributeError,
            TypeError,
            ValueError,
        ) as exc:
            raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                "nested lineage failed invariant revalidation"
            ) from exc

        if len(rebuilt_facts) != len(rebuilt_lineage):
            raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                "materialized fact and lineage counts must match"
            )
        fact_key = lambda item: _lineage_key(
            item.category,
            item.field,
            item.source_reference,
        )
        expected_facts = tuple(sorted(rebuilt_facts, key=fact_key))
        expected_lineage = tuple(sorted(rebuilt_lineage, key=lambda item: item.key))
        if rebuilt_facts != expected_facts or rebuilt_lineage != expected_lineage:
            raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                "facts and lineage must be deterministically sorted"
            )
        fact_keys = tuple(fact_key(item) for item in rebuilt_facts)
        lineage_keys = tuple(item.key for item in rebuilt_lineage)
        if fact_keys != lineage_keys or len(set(fact_keys)) != len(fact_keys):
            raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                "facts and lineage must bind one-to-one by exact key"
            )
        original_hashes = tuple(item.original_fact_sha256 for item in rebuilt_lineage)
        if len(set(original_hashes)) != len(original_hashes):
            raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                "original_fact_sha256 values must be unique"
            )
        for fact, recorded in zip(rebuilt_facts, rebuilt_lineage):
            if fact.status is not recorded.resulting_status:
                raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                    "materialized fact status disagrees with exact lineage"
                )
            if fact.status is IntelligenceFactStatus.CONFLICTED:
                raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                    "CONFLICTED status cannot be materialized per observation"
                )
            if fact.source_role is not SourceRole.PRIMARY_FOOTBALL_CONTEXT:
                raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                    "materialized fact source_role must remain PRIMARY_FOOTBALL_CONTEXT"
                )
            if fact.observed_at > classified_at or fact.observed_at >= kickoff:
                raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                    "materialized fact chronology disagrees with exact evaluation"
                )
            _fact_payload(fact)
            try:
                original_projection = dataclasses.replace(
                    fact,
                    status=IntelligenceFactStatus.UNVERIFIED,
                )
            except (
                FixtureIntelligenceError,
                AttributeError,
                TypeError,
                ValueError,
            ) as exc:
                raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                    "materialized fact cannot reconstruct its original PR #57 payload"
                ) from exc
            if (
                sha256_original_reviewed_match_details_fact(original_projection)
                != recorded.original_fact_sha256
            ):
                raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                    "materialized fact payload differs from its exact original PR #57 fact"
                )

        safety = _validate_safety(self.safety)
        object.__setattr__(self, "fixture_identifier", fixture_identifier)
        object.__setattr__(self, "source_match_id", source_match_id)
        object.__setattr__(self, "kickoff", kickoff)
        object.__setattr__(self, "classified_at", classified_at)
        object.__setattr__(self, "fact_bundle_sha256", fact_bundle_sha256)
        object.__setattr__(self, "evaluation_sha256", evaluation_sha256)
        object.__setattr__(self, "materialized_facts", rebuilt_facts)
        object.__setattr__(self, "lineage", rebuilt_lineage)
        object.__setattr__(self, "safety", safety)

    @property
    def supported_count(self) -> int:
        return sum(
            item.status is IntelligenceFactStatus.SUPPORTED
            for item in self.materialized_facts
        )

    @property
    def stale_count(self) -> int:
        return sum(
            item.status is IntelligenceFactStatus.STALE
            for item in self.materialized_facts
        )

    @property
    def unverified_count(self) -> int:
        return sum(
            item.status is IntelligenceFactStatus.UNVERIFIED
            for item in self.materialized_facts
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "materialization_scope": self.materialization_scope,
            "fixture_identifier": self.fixture_identifier,
            "source_match_id": self.source_match_id,
            "kickoff": _iso(self.kickoff),
            "classified_at": _iso(self.classified_at),
            "fact_bundle_sha256": self.fact_bundle_sha256,
            "fact_bundle_size": self.fact_bundle_size,
            "evaluation_sha256": self.evaluation_sha256,
            "evaluation_size": self.evaluation_size,
            "supported_count": self.supported_count,
            "stale_count": self.stale_count,
            "unverified_count": self.unverified_count,
            "materialized_facts": [
                _fact_payload(item) for item in self.materialized_facts
            ],
            "lineage": [item.to_dict() for item in self.lineage],
            "safety": dict(self.safety),
        }


def _revalidate_inputs(
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
    policy: Any,
    policy_bytes: Any,
    evaluation: Any,
    evaluation_bytes: Any,
) -> tuple[
    ReviewedMatchDetailsUnverifiedFactBundle,
    bytes,
    ReviewedMatchDetailsStatusEvaluation,
    bytes,
]:
    try:
        rebuilt_evaluation = revalidate_reviewed_match_details_status_evaluation(
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
            qualification=qualification,
            qualification_bytes=qualification_bytes,
            policy=policy,
            policy_bytes=policy_bytes,
            evaluation=evaluation,
            evaluation_bytes=evaluation_bytes,
        )
        exact_evaluation_bytes = (
            canonical_reviewed_match_details_status_evaluation_bytes(
                rebuilt_evaluation
            )
        )
        rebuilt_facts = revalidate_reviewed_match_details_unverified_fact_bundle(
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
        exact_fact_bytes = canonical_reviewed_match_details_unverified_fact_bundle_bytes(
            rebuilt_facts
        )
    except (
        FotMobReviewedMatchDetailsStatusEvaluationError,
        FotMobReviewedMatchDetailsUnverifiedFactError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
            "PR #52 -> PR #61 chain failed exact full-chain revalidation"
        ) from exc
    if exact_evaluation_bytes != evaluation_bytes:
        raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
            "evaluation_bytes differ from exact PR #61 full-chain rebuild"
        )
    if exact_fact_bytes != fact_bundle_bytes:
        raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
            "fact_bundle_bytes differ from exact PR #57 full-chain rebuild"
        )
    return (
        rebuilt_facts,
        exact_fact_bytes,
        rebuilt_evaluation,
        exact_evaluation_bytes,
    )


def materialize_reviewed_match_details_fact_statuses(
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
    policy: Any,
    policy_bytes: Any,
    evaluation: Any,
    evaluation_bytes: Any,
) -> ReviewedMatchDetailsFactStatusMaterialization:
    """Replay the full chain and materialize only the reviewed status mapping."""

    (
        rebuilt_fact_bundle,
        exact_fact_bytes,
        rebuilt_evaluation,
        exact_evaluation_bytes,
    ) = _revalidate_inputs(
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
        qualification=qualification,
        qualification_bytes=qualification_bytes,
        policy=policy,
        policy_bytes=policy_bytes,
        evaluation=evaluation,
        evaluation_bytes=evaluation_bytes,
    )

    if (
        rebuilt_fact_bundle.fixture_identifier
        != rebuilt_evaluation.fixture_identifier
        or rebuilt_fact_bundle.source_match_id
        != rebuilt_evaluation.source_match_id
        or rebuilt_fact_bundle.kickoff != rebuilt_evaluation.kickoff
        or rebuilt_fact_bundle.observed_at != rebuilt_evaluation.observed_at
        or rebuilt_fact_bundle.raw_sha256 != rebuilt_evaluation.raw_sha256
        or rebuilt_fact_bundle.evidence_file_path
        != rebuilt_evaluation.evidence_file_path
    ):
        raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
            "PR #57 and PR #61 observation ancestry mismatch"
        )

    fact_by_sha: dict[str, FixtureIntelligenceFact] = {}
    for fact in rebuilt_fact_bundle.facts:
        if fact.status is not IntelligenceFactStatus.UNVERIFIED:
            raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                "original PR #57 fact must remain exact UNVERIFIED"
            )
        fact_sha = sha256_original_reviewed_match_details_fact(fact)
        if fact_sha in fact_by_sha:
            raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                "original PR #57 fact hashes must be unique"
            )
        fact_by_sha[fact_sha] = fact

    decision_hashes = {item.fact_sha256 for item in rebuilt_evaluation.decisions}
    if decision_hashes != set(fact_by_sha):
        raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
            "PR #61 decisions must cover every and only exact PR #57 fact hash"
        )

    materialized: list[FixtureIntelligenceFact] = []
    lineage: list[RecordedMatchDetailsFactStatusLineage] = []
    for decision in rebuilt_evaluation.decisions:
        original = fact_by_sha[decision.fact_sha256]
        original_key = _lineage_key(
            original.category,
            original.field,
            original.source_reference,
        )
        if decision.key != original_key:
            raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                "PR #61 decision metadata does not match its exact PR #57 fact hash"
            )
        resulting_status = STATUS_MAPPING[decision.evaluation_disposition]
        try:
            promoted = FixtureIntelligenceFact(
                category=original.category,
                field=original.field,
                status=resulting_status,
                value=original.value,
                source_provider=original.source_provider,
                source_role=original.source_role,
                source_reference=original.source_reference,
                observed_at=original.observed_at,
                evidence_file_path=original.evidence_file_path,
                evidence_sha256=original.evidence_sha256,
                notes=original.notes,
            )
        except FixtureIntelligenceError as exc:
            raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                "status-only fact reconstruction failed the PR #30 contract"
            ) from exc
        original_payload = _fact_payload(original)
        promoted_payload = _fact_payload(promoted)
        if {
            key: value for key, value in original_payload.items() if key != "status"
        } != {
            key: value for key, value in promoted_payload.items() if key != "status"
        }:
            raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
                "materialized fact changed payload beyond status"
            )
        materialized.append(promoted)
        lineage.append(
            RecordedMatchDetailsFactStatusLineage(
                category=original.category,
                field=original.field,
                source_reference=original.source_reference,
                original_fact_sha256=decision.fact_sha256,
                evaluation_disposition=decision.evaluation_disposition,
                resulting_status=resulting_status,
            )
        )

    return ReviewedMatchDetailsFactStatusMaterialization(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        materialization_scope=MATERIALIZATION_SCOPE,
        fixture_identifier=rebuilt_evaluation.fixture_identifier,
        source_match_id=rebuilt_evaluation.source_match_id,
        kickoff=rebuilt_evaluation.kickoff,
        classified_at=rebuilt_evaluation.classified_at,
        fact_bundle_sha256=hashlib.sha256(exact_fact_bytes).hexdigest(),
        fact_bundle_size=len(exact_fact_bytes),
        evaluation_sha256=hashlib.sha256(exact_evaluation_bytes).hexdigest(),
        evaluation_size=len(exact_evaluation_bytes),
        materialized_facts=tuple(materialized),
        lineage=tuple(lineage),
        safety=_default_safety(),
    )


def canonical_reviewed_match_details_fact_status_materialization_bytes(
    value: Any,
) -> bytes:
    if type(value) is not ReviewedMatchDetailsFactStatusMaterialization:
        raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
            "value must be exact ReviewedMatchDetailsFactStatusMaterialization"
        )
    try:
        rebuilt = dataclasses.replace(value)
        return _canonical_json_bytes(rebuilt.to_dict())
    except FotMobReviewedMatchDetailsFactStatusMaterializationError:
        raise
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
            "fact-status materialization canonicalization failed"
        ) from exc


def revalidate_reviewed_match_details_fact_status_materialization(
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
    policy: Any,
    policy_bytes: Any,
    evaluation: Any,
    evaluation_bytes: Any,
    materialization: Any,
    materialization_bytes: Any,
) -> ReviewedMatchDetailsFactStatusMaterialization:
    """Replay PR #52 -> PR #62 and reject any detached or coordinated forgery."""

    if type(materialization) is not ReviewedMatchDetailsFactStatusMaterialization:
        raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
            "materialization must be exact PR #62 type"
        )
    if type(materialization_bytes) is not bytes:
        raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
            "materialization_bytes must be exact immutable bytes"
        )
    try:
        supplied_bytes = (
            canonical_reviewed_match_details_fact_status_materialization_bytes(
                materialization
            )
        )
        rebuilt = materialize_reviewed_match_details_fact_statuses(
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
            qualification=qualification,
            qualification_bytes=qualification_bytes,
            policy=policy,
            policy_bytes=policy_bytes,
            evaluation=evaluation,
            evaluation_bytes=evaluation_bytes,
        )
        rebuilt_bytes = (
            canonical_reviewed_match_details_fact_status_materialization_bytes(
                rebuilt
            )
        )
    except (
        FotMobReviewedMatchDetailsFactStatusMaterializationError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
            "PR #62 materialization failed exact full-chain revalidation"
        ) from exc
    if supplied_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
            "supplied PR #62 materialization differs from exact full-chain rebuild"
        )
    if materialization_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsFactStatusMaterializationError(
            "materialization_bytes are not exact canonical PR #62 bytes"
        )
    return rebuilt


def sha256_reviewed_match_details_fact_status_materialization(value: Any) -> str:
    return hashlib.sha256(
        canonical_reviewed_match_details_fact_status_materialization_bytes(value)
    ).hexdigest()


__all__ = [
    "DATASET_NAME",
    "MATERIALIZATION_SCOPE",
    "SCHEMA_VERSION",
    "STATUS_MAPPING",
    "FotMobReviewedMatchDetailsFactStatusMaterializationError",
    "RecordedMatchDetailsFactStatusLineage",
    "ReviewedMatchDetailsFactStatusMaterialization",
    "canonical_reviewed_match_details_fact_status_materialization_bytes",
    "materialize_reviewed_match_details_fact_statuses",
    "revalidate_reviewed_match_details_fact_status_materialization",
    "sha256_original_reviewed_match_details_fact",
    "sha256_reviewed_match_details_fact_status_materialization",
]
