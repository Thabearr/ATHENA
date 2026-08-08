"""Verified fixture-intelligence to model-feature mapping contract.

This module is an inert, deterministic boundary.  It does not acquire data,
engineer features, default missing values, or perform model inference.
"""

from __future__ import annotations

import dataclasses
import datetime
import enum
import hashlib
import json
import math
import re
import types
from typing import Any, Mapping, Tuple

from domain.fixture_intelligence import (
    DATASET_NAME as FIXTURE_INTELLIGENCE_DATASET_NAME,
    SCHEMA_VERSION as FIXTURE_INTELLIGENCE_SCHEMA_VERSION,
    FixtureIntelligenceSnapshot,
    IntelligenceCategory,
    IntelligenceFactStatus,
    canonical_snapshot_bytes,
    sha256_bytes,
)


DATASET_NAME = "athena-fixture-model-feature-snapshot-v1"
SCHEMA_VERSION = 1


class FixtureModelFeatureError(ValueError):
    """Raised when model-feature contract input fails closed."""


class ModelFeatureId(str, enum.Enum):
    HOME_FORM = "home_form"
    AWAY_FORM = "away_form"
    HOME_ELO = "home_elo"
    AWAY_ELO = "away_elo"
    FATIGUE = "fatigue"
    LIVE_DATA_FRESHNESS = "live_data_freshness"


class ModelFeatureStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    BLOCKED = "BLOCKED"


class ModelFeatureBlocker(str, enum.Enum):
    CONFLICTED_EVIDENCE = "CONFLICTED_EVIDENCE"
    STALE_EVIDENCE_PRESENT = "STALE_EVIDENCE_PRESENT"
    UNVERIFIED_EVIDENCE_PRESENT = "UNVERIFIED_EVIDENCE_PRESENT"
    NO_SUPPORTED_EVIDENCE = "NO_SUPPORTED_EVIDENCE"
    INVALID_SUPPORTED_VALUE = "INVALID_SUPPORTED_VALUE"


@dataclasses.dataclass(frozen=True)
class ModelFeatureBinding:
    feature_id: ModelFeatureId
    source_category: IntelligenceCategory
    source_field: str

    def __post_init__(self) -> None:
        if not isinstance(self.feature_id, ModelFeatureId):
            raise FixtureModelFeatureError("binding feature_id must be ModelFeatureId")
        if not isinstance(self.source_category, IntelligenceCategory):
            raise FixtureModelFeatureError(
                "binding source_category must be IntelligenceCategory"
            )
        if (
            not isinstance(self.source_field, str)
            or not self.source_field
            or self.source_field != self.source_field.strip()
        ):
            raise FixtureModelFeatureError(
                "binding source_field must be a non-empty unpadded string"
            )


MODEL_FEATURE_BINDINGS: Tuple[ModelFeatureBinding, ...] = tuple(
    sorted(
        (
            ModelFeatureBinding(
                ModelFeatureId.HOME_FORM,
                IntelligenceCategory.FORM,
                "home_form",
            ),
            ModelFeatureBinding(
                ModelFeatureId.AWAY_FORM,
                IntelligenceCategory.FORM,
                "away_form",
            ),
            ModelFeatureBinding(
                ModelFeatureId.HOME_ELO,
                IntelligenceCategory.PERFORMANCE,
                "home_elo",
            ),
            ModelFeatureBinding(
                ModelFeatureId.AWAY_ELO,
                IntelligenceCategory.PERFORMANCE,
                "away_elo",
            ),
            ModelFeatureBinding(
                ModelFeatureId.FATIGUE,
                IntelligenceCategory.SCHEDULE_LOAD,
                "fatigue",
            ),
            ModelFeatureBinding(
                ModelFeatureId.LIVE_DATA_FRESHNESS,
                IntelligenceCategory.FIXTURE_CONTEXT,
                "live_data_freshness",
            ),
        ),
        key=lambda binding: binding.feature_id.value,
    )
)

_BINDING_BY_FEATURE = types.MappingProxyType(
    {binding.feature_id: binding for binding in MODEL_FEATURE_BINDINGS}
)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_SAFETY_KEYS = frozenset(
    {
        "network_acquisition_authorized",
        "scraping_authorized",
        "browser_automation_authorized",
        "probability_inference_authorized",
        "probability_adjustment_authorized",
        "pricing_authorized",
        "market_activation_authorized",
        "selection_authorized",
        "production_approval_authorized",
        "bet_authorized",
    }
)


def _binding_for(feature_id: ModelFeatureId) -> ModelFeatureBinding:
    try:
        return _BINDING_BY_FEATURE[feature_id]
    except (KeyError, TypeError) as exc:
        raise FixtureModelFeatureError(
            "feature_id has no canonical model-feature binding"
        ) from exc


def _utc_datetime(value: Any, field_name: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise FixtureModelFeatureError(f"{field_name} must be a datetime")
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            raise FixtureModelFeatureError(f"{field_name} must be timezone-aware")
        return value.astimezone(datetime.timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise FixtureModelFeatureError(f"{field_name} is invalid") from exc


def _datetime_to_iso(value: datetime.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _finite_float(value: Any) -> float:
    if type(value) not in (int, float):
        raise FixtureModelFeatureError("feature value must be an int or float")
    try:
        normalized = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise FixtureModelFeatureError("feature value is not a finite scalar") from exc
    if not math.isfinite(normalized):
        raise FixtureModelFeatureError("feature value is not finite")
    return normalized


def _canonical_fact_value(value: Any) -> str:
    """Canonical comparison used only as a defensive conflict check."""

    def thaw(item: Any) -> Any:
        if isinstance(item, Mapping):
            return {key: thaw(child) for key, child in item.items()}
        if isinstance(item, (tuple, list)):
            return [thaw(child) for child in item]
        return item

    try:
        return json.dumps(
            thaw(value),
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise FixtureModelFeatureError(
            "supported evidence value cannot be compared canonically"
        ) from exc


def _validate_sha256s(values: Any) -> Tuple[str, ...]:
    if not isinstance(values, tuple):
        raise FixtureModelFeatureError("evidence_sha256s must be a tuple")
    for value in values:
        if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
            raise FixtureModelFeatureError(
                "each evidence SHA-256 must be 64 lowercase hexadecimal characters"
            )
    if len(values) != len(set(values)):
        raise FixtureModelFeatureError("evidence_sha256s must not contain duplicates")
    if values != tuple(sorted(values)):
        raise FixtureModelFeatureError("evidence_sha256s must be sorted")
    return values


def _validate_blockers(values: Any) -> Tuple[ModelFeatureBlocker, ...]:
    if not isinstance(values, tuple):
        raise FixtureModelFeatureError("blockers must be a tuple")
    if any(not isinstance(value, ModelFeatureBlocker) for value in values):
        raise FixtureModelFeatureError("blockers must contain ModelFeatureBlocker values")
    if len(values) != len(set(values)):
        raise FixtureModelFeatureError("blockers must not contain duplicates")
    expected = tuple(sorted(values, key=lambda blocker: blocker.value))
    if values != expected:
        raise FixtureModelFeatureError("blockers must be sorted by enum value")
    return values


@dataclasses.dataclass(frozen=True)
class ModelFeatureResolution:
    feature_id: ModelFeatureId
    status: ModelFeatureStatus
    value: float | None
    source_category: IntelligenceCategory
    source_field: str
    blockers: Tuple[ModelFeatureBlocker, ...]
    evidence_sha256s: Tuple[str, ...]

    def __post_init__(self) -> None:
        try:
            if not isinstance(self.feature_id, ModelFeatureId):
                raise FixtureModelFeatureError("feature_id must be ModelFeatureId")
            if not isinstance(self.status, ModelFeatureStatus):
                raise FixtureModelFeatureError("status must be ModelFeatureStatus")
            if not isinstance(self.source_category, IntelligenceCategory):
                raise FixtureModelFeatureError(
                    "source_category must be IntelligenceCategory"
                )
            if not isinstance(self.source_field, str) or not self.source_field:
                raise FixtureModelFeatureError("source_field must be non-empty")

            binding = _binding_for(self.feature_id)
            if self.source_category is not binding.source_category:
                raise FixtureModelFeatureError(
                    "source_category does not match the canonical feature binding"
                )
            if self.source_field != binding.source_field:
                raise FixtureModelFeatureError(
                    "source_field does not match the canonical feature binding"
                )

            blockers = _validate_blockers(self.blockers)
            evidence_sha256s = _validate_sha256s(self.evidence_sha256s)

            if self.status is ModelFeatureStatus.AVAILABLE:
                normalized = _finite_float(self.value)
                if blockers:
                    raise FixtureModelFeatureError(
                        "AVAILABLE feature must not contain blockers"
                    )
                if not evidence_sha256s:
                    raise FixtureModelFeatureError(
                        "AVAILABLE feature must retain evidence SHA-256 values"
                    )
                object.__setattr__(self, "value", normalized)
            elif self.status is ModelFeatureStatus.MISSING:
                if self.value is not None:
                    raise FixtureModelFeatureError("MISSING feature value must be None")
                if blockers:
                    raise FixtureModelFeatureError(
                        "MISSING feature must not contain blockers"
                    )
                if evidence_sha256s:
                    raise FixtureModelFeatureError(
                        "MISSING feature must not contain evidence SHA-256 values"
                    )
            else:
                if self.value is not None:
                    raise FixtureModelFeatureError("BLOCKED feature value must be None")
                if not blockers:
                    raise FixtureModelFeatureError(
                        "BLOCKED feature must contain at least one blocker"
                    )
                if not evidence_sha256s:
                    raise FixtureModelFeatureError(
                        "BLOCKED feature must retain evidence SHA-256 values"
                    )
        except FixtureModelFeatureError:
            raise
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
            raise FixtureModelFeatureError(
                f"invalid model feature resolution: {exc}"
            ) from exc


def _default_safety() -> dict[str, bool]:
    return {key: False for key in sorted(_REQUIRED_SAFETY_KEYS)}


@dataclasses.dataclass(frozen=True)
class FixtureModelFeatureSnapshot:
    schema_version: int
    dataset_name: str
    fixture_identifier: str
    kickoff: datetime.datetime
    as_of: datetime.datetime
    source_snapshot_dataset_name: str
    source_snapshot_schema_version: int
    source_snapshot_sha256: str
    features: Tuple[ModelFeatureResolution, ...]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        try:
            if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
                raise FixtureModelFeatureError(
                    f"schema_version must be exact int {SCHEMA_VERSION}"
                )
            if self.dataset_name != DATASET_NAME:
                raise FixtureModelFeatureError(f"dataset_name must be {DATASET_NAME}")
            if (
                not isinstance(self.fixture_identifier, str)
                or not self.fixture_identifier
                or self.fixture_identifier != self.fixture_identifier.strip()
            ):
                raise FixtureModelFeatureError(
                    "fixture_identifier must be a non-empty unpadded string"
                )

            kickoff = _utc_datetime(self.kickoff, "kickoff")
            as_of = _utc_datetime(self.as_of, "as_of")
            if as_of >= kickoff:
                raise FixtureModelFeatureError("as_of must be strictly before kickoff")
            object.__setattr__(self, "kickoff", kickoff)
            object.__setattr__(self, "as_of", as_of)

            if self.source_snapshot_dataset_name != FIXTURE_INTELLIGENCE_DATASET_NAME:
                raise FixtureModelFeatureError(
                    "source_snapshot_dataset_name must identify fixture intelligence v1"
                )
            if (
                type(self.source_snapshot_schema_version) is not int
                or self.source_snapshot_schema_version
                != FIXTURE_INTELLIGENCE_SCHEMA_VERSION
            ):
                raise FixtureModelFeatureError(
                    "source_snapshot_schema_version must be exact int 1"
                )
            if (
                not isinstance(self.source_snapshot_sha256, str)
                or _SHA256_PATTERN.fullmatch(self.source_snapshot_sha256) is None
            ):
                raise FixtureModelFeatureError(
                    "source_snapshot_sha256 must be 64 lowercase hexadecimal characters"
                )

            if not isinstance(self.features, tuple):
                raise FixtureModelFeatureError("features must be a tuple")
            if any(
                not isinstance(feature, ModelFeatureResolution)
                for feature in self.features
            ):
                raise FixtureModelFeatureError(
                    "features must contain ModelFeatureResolution values"
                )
            feature_ids = tuple(feature.feature_id for feature in self.features)
            if len(feature_ids) != len(set(feature_ids)):
                raise FixtureModelFeatureError("features must not contain duplicates")
            if set(feature_ids) != set(ModelFeatureId):
                raise FixtureModelFeatureError(
                    "features must contain exactly one resolution per ModelFeatureId"
                )
            expected_features = tuple(
                sorted(self.features, key=lambda feature: feature.feature_id.value)
            )
            if self.features != expected_features:
                raise FixtureModelFeatureError(
                    "features must be sorted by feature_id value"
                )

            if not isinstance(self.safety, Mapping):
                raise FixtureModelFeatureError("safety must be a mapping")
            if set(self.safety.keys()) != _REQUIRED_SAFETY_KEYS:
                raise FixtureModelFeatureError("safety keys mismatch")
            detached_safety: dict[str, bool] = {}
            for key, value in self.safety.items():
                if type(value) is not bool or value is not False:
                    raise FixtureModelFeatureError(
                        f"safety[{key!r}] must be exactly bool False"
                    )
                detached_safety[key] = False
            object.__setattr__(
                self,
                "safety",
                types.MappingProxyType(dict(detached_safety)),
            )
        except FixtureModelFeatureError:
            raise
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
            raise FixtureModelFeatureError(
                f"invalid fixture model feature snapshot: {exc}"
            ) from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "fixture_identifier": self.fixture_identifier,
            "kickoff": _datetime_to_iso(self.kickoff),
            "as_of": _datetime_to_iso(self.as_of),
            "source_snapshot_dataset_name": self.source_snapshot_dataset_name,
            "source_snapshot_schema_version": self.source_snapshot_schema_version,
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "features": [
                {
                    "feature_id": feature.feature_id.value,
                    "status": feature.status.value,
                    "value": feature.value,
                    "source_category": feature.source_category.value,
                    "source_field": feature.source_field,
                    "blockers": [blocker.value for blocker in feature.blockers],
                    "evidence_sha256s": list(feature.evidence_sha256s),
                }
                for feature in self.features
            ],
            "safety": dict(self.safety),
        }


def _resolution_for(
    intelligence_snapshot: FixtureIntelligenceSnapshot,
    binding: ModelFeatureBinding,
) -> ModelFeatureResolution:
    matching = tuple(
        fact
        for fact in intelligence_snapshot.facts
        if fact.category is binding.source_category
        and fact.field == binding.source_field
    )
    if not matching:
        return ModelFeatureResolution(
            feature_id=binding.feature_id,
            status=ModelFeatureStatus.MISSING,
            value=None,
            source_category=binding.source_category,
            source_field=binding.source_field,
            blockers=(),
            evidence_sha256s=(),
        )

    evidence_sha256s = tuple(sorted({fact.evidence_sha256 for fact in matching}))
    field_key = (binding.source_category.value, binding.source_field)
    is_conflicted = field_key in intelligence_snapshot.conflicted_fields or any(
        fact.status is IntelligenceFactStatus.CONFLICTED for fact in matching
    )
    if is_conflicted:
        return ModelFeatureResolution(
            feature_id=binding.feature_id,
            status=ModelFeatureStatus.BLOCKED,
            value=None,
            source_category=binding.source_category,
            source_field=binding.source_field,
            blockers=(ModelFeatureBlocker.CONFLICTED_EVIDENCE,),
            evidence_sha256s=evidence_sha256s,
        )

    supported = tuple(
        fact for fact in matching if fact.status is IntelligenceFactStatus.SUPPORTED
    )
    if supported:
        canonical_values = {_canonical_fact_value(fact.value) for fact in supported}
        if len(canonical_values) != 1:
            return ModelFeatureResolution(
                feature_id=binding.feature_id,
                status=ModelFeatureStatus.BLOCKED,
                value=None,
                source_category=binding.source_category,
                source_field=binding.source_field,
                blockers=(ModelFeatureBlocker.CONFLICTED_EVIDENCE,),
                evidence_sha256s=evidence_sha256s,
            )
        try:
            value = _finite_float(supported[0].value)
        except FixtureModelFeatureError:
            return ModelFeatureResolution(
                feature_id=binding.feature_id,
                status=ModelFeatureStatus.BLOCKED,
                value=None,
                source_category=binding.source_category,
                source_field=binding.source_field,
                blockers=(ModelFeatureBlocker.INVALID_SUPPORTED_VALUE,),
                evidence_sha256s=evidence_sha256s,
            )
        return ModelFeatureResolution(
            feature_id=binding.feature_id,
            status=ModelFeatureStatus.AVAILABLE,
            value=value,
            source_category=binding.source_category,
            source_field=binding.source_field,
            blockers=(),
            evidence_sha256s=evidence_sha256s,
        )

    blockers = {ModelFeatureBlocker.NO_SUPPORTED_EVIDENCE}
    if any(fact.status is IntelligenceFactStatus.STALE for fact in matching):
        blockers.add(ModelFeatureBlocker.STALE_EVIDENCE_PRESENT)
    if any(fact.status is IntelligenceFactStatus.UNVERIFIED for fact in matching):
        blockers.add(ModelFeatureBlocker.UNVERIFIED_EVIDENCE_PRESENT)
    return ModelFeatureResolution(
        feature_id=binding.feature_id,
        status=ModelFeatureStatus.BLOCKED,
        value=None,
        source_category=binding.source_category,
        source_field=binding.source_field,
        blockers=tuple(sorted(blockers, key=lambda blocker: blocker.value)),
        evidence_sha256s=evidence_sha256s,
    )


def build_model_feature_snapshot(
    intelligence_snapshot: FixtureIntelligenceSnapshot,
) -> FixtureModelFeatureSnapshot:
    """Resolve the six registered inputs from one exact intelligence snapshot."""

    if not isinstance(intelligence_snapshot, FixtureIntelligenceSnapshot):
        raise FixtureModelFeatureError(
            "intelligence_snapshot must be FixtureIntelligenceSnapshot"
        )
    try:
        features = tuple(
            _resolution_for(intelligence_snapshot, binding)
            for binding in MODEL_FEATURE_BINDINGS
        )
        source_bytes = canonical_snapshot_bytes(intelligence_snapshot)
        source_sha256 = sha256_bytes(source_bytes)
        return FixtureModelFeatureSnapshot(
            schema_version=SCHEMA_VERSION,
            dataset_name=DATASET_NAME,
            fixture_identifier=intelligence_snapshot.fixture_identifier,
            kickoff=intelligence_snapshot.kickoff,
            as_of=intelligence_snapshot.as_of,
            source_snapshot_dataset_name=intelligence_snapshot.dataset_name,
            source_snapshot_schema_version=intelligence_snapshot.schema_version,
            source_snapshot_sha256=source_sha256,
            features=features,
            safety=_default_safety(),
        )
    except FixtureModelFeatureError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
        raise FixtureModelFeatureError(
            f"could not build fixture model feature snapshot: {exc}"
        ) from exc


def model_feature_snapshot_to_dict(
    snapshot: FixtureModelFeatureSnapshot,
) -> dict[str, Any]:
    if not isinstance(snapshot, FixtureModelFeatureSnapshot):
        raise FixtureModelFeatureError(
            "snapshot must be FixtureModelFeatureSnapshot"
        )
    return snapshot.to_dict()


def canonical_model_feature_snapshot_bytes(
    snapshot: FixtureModelFeatureSnapshot,
) -> bytes:
    if not isinstance(snapshot, FixtureModelFeatureSnapshot):
        raise FixtureModelFeatureError(
            "snapshot must be FixtureModelFeatureSnapshot"
        )
    try:
        serialized = json.dumps(
            snapshot.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise FixtureModelFeatureError(
            f"snapshot is not canonically serializable: {exc}"
        ) from exc
    return (serialized + "\n").encode("utf-8")


def sha256_model_feature_snapshot(snapshot: FixtureModelFeatureSnapshot) -> str:
    return hashlib.sha256(canonical_model_feature_snapshot_bytes(snapshot)).hexdigest()


__all__ = [
    "DATASET_NAME",
    "SCHEMA_VERSION",
    "FixtureModelFeatureError",
    "FixtureModelFeatureSnapshot",
    "MODEL_FEATURE_BINDINGS",
    "ModelFeatureBinding",
    "ModelFeatureBlocker",
    "ModelFeatureId",
    "ModelFeatureResolution",
    "ModelFeatureStatus",
    "build_model_feature_snapshot",
    "canonical_model_feature_snapshot_bytes",
    "model_feature_snapshot_to_dict",
    "sha256_model_feature_snapshot",
]
