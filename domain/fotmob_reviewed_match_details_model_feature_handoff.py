"""Bridge one fully replayed PR #65 snapshot into the existing PR #31 contract.

This module adds reviewed ancestry around the real PR #31 model-feature
snapshot.  It performs no feature engineering, inference, conflict resolution,
network access, filesystem access, pricing, selection, or betting behavior.
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
    DATASET_NAME as FIXTURE_INTELLIGENCE_DATASET_NAME,
    SCHEMA_VERSION as FIXTURE_INTELLIGENCE_SCHEMA_VERSION,
    canonical_snapshot_bytes,
)
from domain.fixture_model_features import (
    FixtureModelFeatureError,
    FixtureModelFeatureSnapshot,
    ModelFeatureId,
    ModelFeatureResolution,
    build_model_feature_snapshot,
    canonical_model_feature_snapshot_bytes,
)
from domain.fotmob_reviewed_match_details_fixture_intelligence_snapshot import (
    FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError,
    canonical_reviewed_match_details_fixture_intelligence_snapshot_bytes,
    revalidate_reviewed_match_details_fixture_intelligence_snapshot,
)


SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-reviewed-match-details-model-feature-handoff-v1"
HANDOFF_SCOPE = "EXACT_REVALIDATED_PR65_SNAPSHOT_ONLY"

_SHA_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_FIXTURE_RE = re.compile(r"^FOTMOB:([1-9][0-9]*)$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "source_wide_qualification_authorized",
        "source_identity_resolution_authorized",
        "conflict_resolution_authorized",
        "probability_inference_authorized",
        "probability_adjustment_authorized",
        "pricing_authorized",
        "market_activation_authorized",
        "selection_authorized",
        "production_approval_authorized",
        "bet_authorized",
    }
)


class FotMobReviewedMatchDetailsModelFeatureHandoffError(ValueError):
    """Raised when exact PR #65 to PR #31 lineage cannot be proven."""


def _sha256(value: Any, label: str) -> str:
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
            f"{label} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _positive_size(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
            f"{label} must be an exact positive integer"
        )
    return value


def _text(value: Any, label: str, maximum: int) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
    ):
        raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
            f"{label} must be a non-empty exact trimmed string within {maximum} characters"
        )
    return value


def _utc(value: Any, label: str) -> datetime.datetime:
    if (
        not isinstance(value, datetime.datetime)
        or value.tzinfo is not datetime.timezone.utc
    ):
        raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
            f"{label} must already use exact datetime.timezone.utc"
        )
    return value


def _iso(value: datetime.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _default_safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
            "downstream safety keys mismatch"
        )
    if any(type(item) is not bool or item is not False for item in value.values()):
        raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
            "all downstream safety values must be exact bool False"
        )
    return _default_safety()


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
            "reviewed model-feature handoff serialization failed"
        ) from exc
    return (serialized + "\n").encode("utf-8")


def _rebuild_model_feature_snapshot(
    value: Any,
) -> tuple[FixtureModelFeatureSnapshot, bytes]:
    if type(value) is not FixtureModelFeatureSnapshot:
        raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
            "model_feature_snapshot must be exact FixtureModelFeatureSnapshot"
        )
    if type(value.features) is not tuple or any(
        type(item) is not ModelFeatureResolution for item in value.features
    ):
        raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
            "model features must remain exact immutable ModelFeatureResolution values"
        )
    try:
        rebuilt_features = tuple(dataclasses.replace(item) for item in value.features)
        rebuilt = FixtureModelFeatureSnapshot(
            schema_version=value.schema_version,
            dataset_name=value.dataset_name,
            fixture_identifier=value.fixture_identifier,
            kickoff=value.kickoff,
            as_of=value.as_of,
            source_snapshot_dataset_name=value.source_snapshot_dataset_name,
            source_snapshot_schema_version=value.source_snapshot_schema_version,
            source_snapshot_sha256=value.source_snapshot_sha256,
            features=rebuilt_features,
            safety=dict(value.safety),
        )
        rebuilt_bytes = canonical_model_feature_snapshot_bytes(rebuilt)
        supplied_bytes = canonical_model_feature_snapshot_bytes(value)
    except (
        FixtureModelFeatureError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
            "nested PR #31 snapshot failed exact invariant reconstruction"
        ) from exc
    if supplied_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
            "nested PR #31 snapshot differs from exact invariant reconstruction"
        )
    return rebuilt, rebuilt_bytes


@dataclasses.dataclass(frozen=True)
class ReviewedMatchDetailsModelFeatureHandoff:
    """Exact PR #52→PR #66 lineage wrapper around one real PR #31 snapshot."""

    schema_version: int
    dataset_name: str
    handoff_scope: str
    source_pr65_artifact_sha256: str
    source_pr65_artifact_size: int
    fixture_identifier: str
    source_match_id: str
    kickoff: datetime.datetime
    as_of: datetime.datetime
    source_fixture_intelligence_snapshot_sha256: str
    source_fixture_intelligence_snapshot_size: int
    model_feature_snapshot: FixtureModelFeatureSnapshot
    model_feature_snapshot_sha256: str
    model_feature_snapshot_size: int
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
                "schema_version mismatch"
            )
        if self.dataset_name != DATASET_NAME:
            raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
                "dataset_name mismatch"
            )
        if self.handoff_scope != HANDOFF_SCOPE:
            raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
                "handoff_scope mismatch"
            )
        pr65_sha = _sha256(
            self.source_pr65_artifact_sha256,
            "source_pr65_artifact_sha256",
        )
        intelligence_sha = _sha256(
            self.source_fixture_intelligence_snapshot_sha256,
            "source_fixture_intelligence_snapshot_sha256",
        )
        feature_sha = _sha256(
            self.model_feature_snapshot_sha256,
            "model_feature_snapshot_sha256",
        )
        pr65_size = _positive_size(
            self.source_pr65_artifact_size,
            "source_pr65_artifact_size",
        )
        intelligence_size = _positive_size(
            self.source_fixture_intelligence_snapshot_size,
            "source_fixture_intelligence_snapshot_size",
        )
        feature_size = _positive_size(
            self.model_feature_snapshot_size,
            "model_feature_snapshot_size",
        )
        fixture_identifier = _text(
            self.fixture_identifier,
            "fixture_identifier",
            512,
        )
        source_match_id = _text(self.source_match_id, "source_match_id", 256)
        match = _FIXTURE_RE.fullmatch(fixture_identifier)
        if match is None or match.group(1) != source_match_id:
            raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
                "fixture_identifier/source_match_id mismatch"
            )
        kickoff = _utc(self.kickoff, "kickoff")
        as_of = _utc(self.as_of, "as_of")
        if as_of >= kickoff:
            raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
                "as_of must remain strictly before kickoff"
            )

        rebuilt_snapshot, exact_feature_bytes = _rebuild_model_feature_snapshot(
            self.model_feature_snapshot
        )
        if rebuilt_snapshot.fixture_identifier != fixture_identifier:
            raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
                "nested PR #31 fixture_identifier differs from wrapper"
            )
        if rebuilt_snapshot.kickoff != kickoff or rebuilt_snapshot.as_of != as_of:
            raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
                "nested PR #31 kickoff/as_of differ from wrapper"
            )
        if rebuilt_snapshot.source_snapshot_sha256 != intelligence_sha:
            raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
                "nested PR #31 source snapshot SHA differs from wrapper"
            )
        if (
            rebuilt_snapshot.source_snapshot_dataset_name
            != FIXTURE_INTELLIGENCE_DATASET_NAME
            or rebuilt_snapshot.source_snapshot_schema_version
            != FIXTURE_INTELLIGENCE_SCHEMA_VERSION
        ):
            raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
                "nested PR #31 source dataset/schema differ from PR #30"
            )
        if len(rebuilt_snapshot.features) != len(ModelFeatureId) or {
            item.feature_id for item in rebuilt_snapshot.features
        } != set(ModelFeatureId):
            raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
                "nested PR #31 must contain exactly one resolution per feature"
            )
        if hashlib.sha256(exact_feature_bytes).hexdigest() != feature_sha:
            raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
                "model_feature_snapshot_sha256 differs from exact PR #31 bytes"
            )
        if len(exact_feature_bytes) != feature_size:
            raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
                "model_feature_snapshot_size differs from exact PR #31 bytes"
            )
        safety = _validate_safety(self.safety)

        object.__setattr__(self, "source_pr65_artifact_sha256", pr65_sha)
        object.__setattr__(self, "source_pr65_artifact_size", pr65_size)
        object.__setattr__(
            self,
            "source_fixture_intelligence_snapshot_sha256",
            intelligence_sha,
        )
        object.__setattr__(
            self,
            "source_fixture_intelligence_snapshot_size",
            intelligence_size,
        )
        object.__setattr__(self, "model_feature_snapshot_sha256", feature_sha)
        object.__setattr__(self, "model_feature_snapshot_size", feature_size)
        object.__setattr__(self, "fixture_identifier", fixture_identifier)
        object.__setattr__(self, "source_match_id", source_match_id)
        object.__setattr__(self, "kickoff", kickoff)
        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(self, "model_feature_snapshot", rebuilt_snapshot)
        object.__setattr__(self, "safety", safety)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "handoff_scope": self.handoff_scope,
            "source_pr65_artifact_sha256": self.source_pr65_artifact_sha256,
            "source_pr65_artifact_size": self.source_pr65_artifact_size,
            "fixture_identifier": self.fixture_identifier,
            "source_match_id": self.source_match_id,
            "kickoff": _iso(self.kickoff),
            "as_of": _iso(self.as_of),
            "source_fixture_intelligence_snapshot_sha256": (
                self.source_fixture_intelligence_snapshot_sha256
            ),
            "source_fixture_intelligence_snapshot_size": (
                self.source_fixture_intelligence_snapshot_size
            ),
            "model_feature_snapshot": self.model_feature_snapshot.to_dict(),
            "model_feature_snapshot_sha256": self.model_feature_snapshot_sha256,
            "model_feature_snapshot_size": self.model_feature_snapshot_size,
            "safety": dict(self.safety),
        }


def build_reviewed_match_details_model_feature_handoff(
    *,
    materialization_inputs: Any,
    candidate_set: Any,
    candidate_set_bytes: Any,
    admission: Any,
    admission_bytes: Any,
    artifact: Any,
    artifact_bytes: Any,
) -> ReviewedMatchDetailsModelFeatureHandoff:
    """Replay PR #52→PR #65 and call the existing PR #31 builder exactly."""

    try:
        rebuilt_pr65 = (
            revalidate_reviewed_match_details_fixture_intelligence_snapshot(
                materialization_inputs=materialization_inputs,
                candidate_set=candidate_set,
                candidate_set_bytes=candidate_set_bytes,
                admission=admission,
                admission_bytes=admission_bytes,
                artifact=artifact,
                artifact_bytes=artifact_bytes,
            )
        )
        exact_pr65_bytes = (
            canonical_reviewed_match_details_fixture_intelligence_snapshot_bytes(
                rebuilt_pr65
            )
        )
        exact_intelligence_bytes = canonical_snapshot_bytes(rebuilt_pr65.snapshot)
        feature_snapshot = build_model_feature_snapshot(rebuilt_pr65.snapshot)
        exact_feature_bytes = canonical_model_feature_snapshot_bytes(feature_snapshot)
    except (
        FotMobReviewedMatchDetailsFixtureIntelligenceSnapshotError,
        FixtureModelFeatureError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
            "PR #52 -> PR #31 handoff failed exact full-chain construction"
        ) from exc

    exact_intelligence_sha = hashlib.sha256(exact_intelligence_bytes).hexdigest()
    if (
        rebuilt_pr65.snapshot_sha256 != exact_intelligence_sha
        or rebuilt_pr65.snapshot_size != len(exact_intelligence_bytes)
        or feature_snapshot.fixture_identifier != rebuilt_pr65.fixture_identifier
        or feature_snapshot.kickoff != rebuilt_pr65.kickoff
        or feature_snapshot.as_of != rebuilt_pr65.classified_at
        or feature_snapshot.as_of != rebuilt_pr65.snapshot.as_of
        or feature_snapshot.source_snapshot_sha256 != rebuilt_pr65.snapshot_sha256
        or feature_snapshot.source_snapshot_dataset_name
        != rebuilt_pr65.snapshot.dataset_name
        or feature_snapshot.source_snapshot_schema_version
        != rebuilt_pr65.snapshot.schema_version
    ):
        raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
            "PR #31 output does not bind the exact rebuilt PR #65 nested snapshot"
        )

    return ReviewedMatchDetailsModelFeatureHandoff(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        handoff_scope=HANDOFF_SCOPE,
        source_pr65_artifact_sha256=hashlib.sha256(exact_pr65_bytes).hexdigest(),
        source_pr65_artifact_size=len(exact_pr65_bytes),
        fixture_identifier=rebuilt_pr65.fixture_identifier,
        source_match_id=rebuilt_pr65.source_match_id,
        kickoff=rebuilt_pr65.kickoff,
        as_of=rebuilt_pr65.classified_at,
        source_fixture_intelligence_snapshot_sha256=exact_intelligence_sha,
        source_fixture_intelligence_snapshot_size=len(exact_intelligence_bytes),
        model_feature_snapshot=feature_snapshot,
        model_feature_snapshot_sha256=hashlib.sha256(exact_feature_bytes).hexdigest(),
        model_feature_snapshot_size=len(exact_feature_bytes),
        safety=_default_safety(),
    )


def reviewed_match_details_model_feature_handoff_to_dict(
    value: Any,
) -> dict[str, Any]:
    if type(value) is not ReviewedMatchDetailsModelFeatureHandoff:
        raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
            "value must be exact PR #66 handoff wrapper"
        )
    return dataclasses.replace(value).to_dict()


def canonical_reviewed_match_details_model_feature_handoff_bytes(
    value: Any,
) -> bytes:
    if type(value) is not ReviewedMatchDetailsModelFeatureHandoff:
        raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
            "value must be exact PR #66 handoff wrapper"
        )
    try:
        return _canonical_json_bytes(dataclasses.replace(value).to_dict())
    except FotMobReviewedMatchDetailsModelFeatureHandoffError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
        raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
            "reviewed model-feature handoff canonicalization failed"
        ) from exc


def revalidate_reviewed_match_details_model_feature_handoff(
    *,
    materialization_inputs: Any,
    candidate_set: Any,
    candidate_set_bytes: Any,
    admission: Any,
    admission_bytes: Any,
    artifact: Any,
    artifact_bytes: Any,
    handoff: Any,
    handoff_bytes: Any,
) -> ReviewedMatchDetailsModelFeatureHandoff:
    """Replay PR #52→PR #66 and reject detached or coordinated mutation."""

    if type(handoff) is not ReviewedMatchDetailsModelFeatureHandoff:
        raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
            "handoff must be exact PR #66 wrapper"
        )
    if type(handoff_bytes) is not bytes:
        raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
            "handoff_bytes must be exact immutable bytes"
        )
    try:
        supplied_bytes = canonical_reviewed_match_details_model_feature_handoff_bytes(
            handoff
        )
        rebuilt = build_reviewed_match_details_model_feature_handoff(
            materialization_inputs=materialization_inputs,
            candidate_set=candidate_set,
            candidate_set_bytes=candidate_set_bytes,
            admission=admission,
            admission_bytes=admission_bytes,
            artifact=artifact,
            artifact_bytes=artifact_bytes,
        )
        rebuilt_bytes = canonical_reviewed_match_details_model_feature_handoff_bytes(
            rebuilt
        )
    except (
        FotMobReviewedMatchDetailsModelFeatureHandoffError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
            "PR #52 -> PR #66 handoff failed exact full-chain revalidation"
        ) from exc
    if supplied_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
            "supplied PR #66 wrapper differs from exact full-chain rebuild"
        )
    if handoff_bytes != rebuilt_bytes:
        raise FotMobReviewedMatchDetailsModelFeatureHandoffError(
            "handoff_bytes are not exact canonical PR #66 bytes"
        )
    return rebuilt


def sha256_reviewed_match_details_model_feature_handoff(value: Any) -> str:
    return hashlib.sha256(
        canonical_reviewed_match_details_model_feature_handoff_bytes(value)
    ).hexdigest()


__all__ = [
    "DATASET_NAME",
    "HANDOFF_SCOPE",
    "SCHEMA_VERSION",
    "FotMobReviewedMatchDetailsModelFeatureHandoffError",
    "ReviewedMatchDetailsModelFeatureHandoff",
    "build_reviewed_match_details_model_feature_handoff",
    "canonical_reviewed_match_details_model_feature_handoff_bytes",
    "revalidate_reviewed_match_details_model_feature_handoff",
    "reviewed_match_details_model_feature_handoff_to_dict",
    "sha256_reviewed_match_details_model_feature_handoff",
]
