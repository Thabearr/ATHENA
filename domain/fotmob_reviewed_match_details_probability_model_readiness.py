"""Assess probability-model readiness from one fully replayed PR #66 handoff.

This boundary compares the exact reviewed PR #31 feature state with the live
canonical model-status registry.  It never substitutes missing inputs and it
does not execute a probability method, an expected-goals transform, pricing,
selection, or betting behavior.
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

from domain.fixture_model_features import (
    FixtureModelFeatureError,
    ModelFeatureBlocker,
    ModelFeatureId,
    ModelFeatureResolution,
    ModelFeatureStatus,
    canonical_model_feature_snapshot_bytes,
)
from domain.fotmob_reviewed_match_details_model_feature_handoff import (
    FotMobReviewedMatchDetailsModelFeatureHandoffError,
    canonical_reviewed_match_details_model_feature_handoff_bytes,
    revalidate_reviewed_match_details_model_feature_handoff,
)
from domain.markets import MarketId
from domain.model_status import (
    MODEL_STATUS_REGISTRY,
    MarketModelStatus,
    MissingInputPolicy,
    ModelStatus,
    get_model_status,
)


SCHEMA_VERSION = 1
DATASET_NAME = "athena-fotmob-reviewed-match-details-probability-model-readiness-v1"
READINESS_SCOPE = "EXACT_REVALIDATED_PR66_FEATURE_STATE_ONLY"
REVIEWED_MISSING_INPUT_POLICY = "REJECT_NON_AVAILABLE"

_SHA_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_FIXTURE_RE = re.compile(r"^FOTMOB:([1-9][0-9]*)$", flags=re.ASCII)
_SAFETY_KEYS = frozenset(
    {
        "probability_inference_authorized",
        "probability_adjustment_authorized",
        "pricing_authorized",
        "market_activation_authorized",
        "selection_authorized",
        "production_approval_authorized",
        "bet_authorized",
    }
)


class FotMobReviewedMatchDetailsProbabilityModelReadinessError(ValueError):
    """Raised when exact reviewed probability readiness cannot be proven."""


class DeclaredInputStatus(str, enum.Enum):
    SATISFIED = "SATISFIED"
    BLOCKED = "BLOCKED"


class ProbabilityReadinessStatus(str, enum.Enum):
    BLOCKED_MODEL_STATUS = "BLOCKED_MODEL_STATUS"
    BLOCKED_FEATURE_INPUTS = "BLOCKED_FEATURE_INPUTS"
    BLOCKED_UNREVIEWED_TRANSFORM = "BLOCKED_UNREVIEWED_TRANSFORM"
    RESEARCH_ONLY_UNREVIEWED_TRANSFORM = "RESEARCH_ONLY_UNREVIEWED_TRANSFORM"


class ProbabilityReadinessReason(str, enum.Enum):
    MODEL_STATUS_DISABLED = "MODEL_STATUS_DISABLED"
    MODEL_STATUS_UNSUPPORTED = "MODEL_STATUS_UNSUPPORTED"
    NON_AVAILABLE_DECLARED_FEATURES = "NON_AVAILABLE_DECLARED_FEATURES"
    REVIEWED_EXPECTED_GOALS_TRANSFORM_NOT_ESTABLISHED = (
        "REVIEWED_EXPECTED_GOALS_TRANSFORM_NOT_ESTABLISHED"
    )
    EXPERIMENTAL_RESEARCH_ONLY = "EXPERIMENTAL_RESEARCH_ONLY"


def _error(message: str) -> FotMobReviewedMatchDetailsProbabilityModelReadinessError:
    return FotMobReviewedMatchDetailsProbabilityModelReadinessError(message)


def _sha256(value: Any, label: str) -> str:
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        raise _error(f"{label} must be exactly 64 lowercase hexadecimal characters")
    return value


def _positive_size(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise _error(f"{label} must be an exact positive integer")
    return value


def _text(value: Any, label: str, maximum: int) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
    ):
        raise _error(
            f"{label} must be a non-empty exact trimmed string within {maximum} characters"
        )
    return value


def _utc(value: Any, label: str) -> datetime.datetime:
    if (
        not isinstance(value, datetime.datetime)
        or value.tzinfo is not datetime.timezone.utc
    ):
        raise _error(f"{label} must already use exact datetime.timezone.utc")
    return value


def _iso(value: datetime.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


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
        raise _error("probability readiness serialization failed") from exc
    return (serialized + "\n").encode("utf-8")


def _default_safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in sorted(_SAFETY_KEYS)})


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise _error("downstream safety keys mismatch")
    if any(type(item) is not bool or item is not False for item in value.values()):
        raise _error("all downstream safety values must be exact bool False")
    return _default_safety()


def _validate_string_tuple(value: Any, label: str) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise _error(f"{label} must be an exact immutable tuple")
    rebuilt = tuple(_text(item, f"{label} item", 512) for item in value)
    if len(rebuilt) != len(set(rebuilt)):
        raise _error(f"{label} must not contain duplicates")
    return rebuilt


def _registry_records() -> tuple[dict[str, Any], ...]:
    """Validate and mechanically snapshot the live canonical registry."""

    if type(MODEL_STATUS_REGISTRY) is not dict:
        raise _error("MODEL_STATUS_REGISTRY must remain an exact dictionary")
    if set(MODEL_STATUS_REGISTRY) != set(MarketId) or any(
        type(key) is not MarketId for key in MODEL_STATUS_REGISTRY
    ):
        raise _error("model-status registry must cover every and only MarketId")

    records: list[dict[str, Any]] = []
    for market_id in sorted(MarketId, key=lambda item: item.value):
        try:
            definition = get_model_status(market_id)
        except (KeyError, TypeError, ValueError) as exc:
            raise _error("model-status registry lookup failed") from exc
        if type(definition) is not MarketModelStatus:
            raise _error("model-status registry values must be exact MarketModelStatus")
        if not isinstance(definition.status, ModelStatus):
            raise _error("registry model status must be exact ModelStatus")
        if not isinstance(definition.missing_input_policy, MissingInputPolicy):
            raise _error("registry missing-input policy must be exact MissingInputPolicy")

        if definition.probability_method is None:
            probability_method = None
        else:
            probability_method = _text(
                definition.probability_method,
                "registry probability_method",
                512,
            )
        if definition.status in {ModelStatus.ACTIVE, ModelStatus.EXPERIMENTAL} and (
            probability_method is None
        ):
            raise _error("ACTIVE/EXPERIMENTAL market requires probability_method")

        reason = _text(definition.reason, "registry reason", 4096)
        probability_inputs = _validate_string_tuple(
            definition.probability_inputs,
            "registry probability_inputs",
        )
        feature_ids: list[ModelFeatureId] = []
        for item in probability_inputs:
            try:
                feature_ids.append(ModelFeatureId(item))
            except ValueError as exc:
                raise _error(
                    "registry probability input is not an exact PR #31 ModelFeatureId"
                ) from exc
        if len(feature_ids) != len(set(feature_ids)):
            raise _error("registry probability inputs must not contain duplicates")
        pricing_inputs = _validate_string_tuple(
            definition.pricing_inputs,
            "registry pricing_inputs",
        )
        records.append(
            {
                "market_id": market_id.value,
                "model_status": definition.status.value,
                "probability_method": probability_method,
                "reason": reason,
                "probability_inputs": [item.value for item in feature_ids],
                "pricing_inputs": list(pricing_inputs),
                "missing_input_policy": definition.missing_input_policy.value,
            }
        )
    return tuple(records)


def canonical_model_status_registry_view_bytes() -> bytes:
    """Return the exact canonical identity view consumed by this assessment."""

    return _canonical_json_bytes({"markets": list(_registry_records())})


def sha256_model_status_registry_view() -> str:
    return hashlib.sha256(canonical_model_status_registry_view_bytes()).hexdigest()


@dataclasses.dataclass(frozen=True)
class ProbabilityFeatureAudit:
    feature_id: ModelFeatureId
    status: ModelFeatureStatus
    blockers: tuple[ModelFeatureBlocker, ...]
    evidence_sha256s: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.feature_id, ModelFeatureId):
            raise _error("feature audit feature_id must be exact ModelFeatureId")
        if not isinstance(self.status, ModelFeatureStatus):
            raise _error("feature audit status must be exact ModelFeatureStatus")
        if type(self.blockers) is not tuple or any(
            not isinstance(item, ModelFeatureBlocker) for item in self.blockers
        ):
            raise _error("feature audit blockers must be exact immutable blockers")
        if self.blockers != tuple(sorted(set(self.blockers), key=lambda item: item.value)):
            raise _error("feature audit blockers must be unique and sorted")
        if type(self.evidence_sha256s) is not tuple:
            raise _error("feature audit evidence SHA values must be an immutable tuple")
        evidence = tuple(
            _sha256(item, "feature audit evidence SHA")
            for item in self.evidence_sha256s
        )
        if evidence != tuple(sorted(set(evidence))):
            raise _error("feature audit evidence SHA values must be unique and sorted")
        if self.status is ModelFeatureStatus.AVAILABLE and self.blockers:
            raise _error("AVAILABLE feature audit must not contain blockers")
        if self.status is ModelFeatureStatus.MISSING and (
            self.blockers or self.evidence_sha256s
        ):
            raise _error("MISSING feature audit must not invent evidence or blockers")
        if self.status is ModelFeatureStatus.BLOCKED and not self.blockers:
            raise _error("BLOCKED feature audit must preserve blockers")
        object.__setattr__(self, "evidence_sha256s", evidence)

    @classmethod
    def from_resolution(cls, resolution: Any) -> "ProbabilityFeatureAudit":
        if type(resolution) is not ModelFeatureResolution:
            raise _error("feature audit source must be exact ModelFeatureResolution")
        try:
            rebuilt = dataclasses.replace(resolution)
        except (FixtureModelFeatureError, TypeError, ValueError) as exc:
            raise _error("PR #31 feature resolution failed reconstruction") from exc
        return cls(
            feature_id=rebuilt.feature_id,
            status=rebuilt.status,
            blockers=rebuilt.blockers,
            evidence_sha256s=rebuilt.evidence_sha256s,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id.value,
            "status": self.status.value,
            "blockers": [item.value for item in self.blockers],
            "evidence_sha256s": list(self.evidence_sha256s),
        }


def _expected_readiness(
    model_status: ModelStatus,
    unavailable: tuple[ModelFeatureId, ...],
) -> tuple[
    DeclaredInputStatus,
    ProbabilityReadinessStatus,
    tuple[ProbabilityReadinessReason, ...],
]:
    declared = (
        DeclaredInputStatus.SATISFIED
        if not unavailable
        else DeclaredInputStatus.BLOCKED
    )
    if model_status is ModelStatus.DISABLED:
        return (
            declared,
            ProbabilityReadinessStatus.BLOCKED_MODEL_STATUS,
            (ProbabilityReadinessReason.MODEL_STATUS_DISABLED,),
        )
    if model_status is ModelStatus.UNSUPPORTED:
        return (
            declared,
            ProbabilityReadinessStatus.BLOCKED_MODEL_STATUS,
            (ProbabilityReadinessReason.MODEL_STATUS_UNSUPPORTED,),
        )
    if unavailable:
        return (
            declared,
            ProbabilityReadinessStatus.BLOCKED_FEATURE_INPUTS,
            (ProbabilityReadinessReason.NON_AVAILABLE_DECLARED_FEATURES,),
        )
    if model_status is ModelStatus.ACTIVE:
        return (
            declared,
            ProbabilityReadinessStatus.BLOCKED_UNREVIEWED_TRANSFORM,
            (
                ProbabilityReadinessReason.REVIEWED_EXPECTED_GOALS_TRANSFORM_NOT_ESTABLISHED,
            ),
        )
    if model_status is ModelStatus.EXPERIMENTAL:
        return (
            declared,
            ProbabilityReadinessStatus.RESEARCH_ONLY_UNREVIEWED_TRANSFORM,
            (
                ProbabilityReadinessReason.EXPERIMENTAL_RESEARCH_ONLY,
                ProbabilityReadinessReason.REVIEWED_EXPECTED_GOALS_TRANSFORM_NOT_ESTABLISHED,
            ),
        )
    raise _error("unhandled canonical model status")


@dataclasses.dataclass(frozen=True)
class ProbabilityMarketReadiness:
    market_id: MarketId
    model_status: ModelStatus
    probability_method: str | None
    declared_probability_inputs: tuple[ModelFeatureId, ...]
    declared_pricing_inputs: tuple[str, ...]
    legacy_missing_input_policy: MissingInputPolicy
    reviewed_missing_input_policy: str
    required_feature_records: tuple[ProbabilityFeatureAudit, ...]
    unavailable_feature_ids: tuple[ModelFeatureId, ...]
    blocked_feature_ids: tuple[ModelFeatureId, ...]
    declared_input_status: DeclaredInputStatus
    readiness_status: ProbabilityReadinessStatus
    readiness_reasons: tuple[ProbabilityReadinessReason, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.market_id, MarketId):
            raise _error("market readiness market_id must be exact MarketId")
        if not isinstance(self.model_status, ModelStatus):
            raise _error("market readiness model_status must be exact ModelStatus")
        if self.probability_method is not None:
            _text(self.probability_method, "probability_method", 512)
        if self.model_status in {ModelStatus.ACTIVE, ModelStatus.EXPERIMENTAL} and (
            self.probability_method is None
        ):
            raise _error("ACTIVE/EXPERIMENTAL readiness requires probability_method")
        if type(self.declared_probability_inputs) is not tuple or any(
            not isinstance(item, ModelFeatureId)
            for item in self.declared_probability_inputs
        ):
            raise _error("declared probability inputs must be exact ModelFeatureId tuple")
        if len(set(self.declared_probability_inputs)) != len(
            self.declared_probability_inputs
        ):
            raise _error("declared probability inputs must not contain duplicates")
        pricing = _validate_string_tuple(
            self.declared_pricing_inputs,
            "declared pricing inputs",
        )
        if not isinstance(self.legacy_missing_input_policy, MissingInputPolicy):
            raise _error("legacy missing-input policy must be exact MissingInputPolicy")
        if self.reviewed_missing_input_policy != REVIEWED_MISSING_INPUT_POLICY:
            raise _error("reviewed missing-input policy mismatch")
        try:
            registry_definition = get_model_status(self.market_id)
        except (KeyError, TypeError, ValueError) as exc:
            raise _error("market readiness cannot resolve canonical registry entry") from exc
        expected_inputs = tuple(
            ModelFeatureId(item) for item in registry_definition.probability_inputs
        )
        if (
            self.model_status is not registry_definition.status
            or self.probability_method != registry_definition.probability_method
            or self.declared_probability_inputs != expected_inputs
            or self.declared_pricing_inputs != registry_definition.pricing_inputs
            or self.legacy_missing_input_policy
            is not registry_definition.missing_input_policy
        ):
            raise _error("market readiness differs from canonical registry entry")
        if type(self.required_feature_records) is not tuple or any(
            type(item) is not ProbabilityFeatureAudit
            for item in self.required_feature_records
        ):
            raise _error("required feature records must be exact immutable audits")
        rebuilt_audits = tuple(
            dataclasses.replace(item) for item in self.required_feature_records
        )
        if tuple(item.feature_id for item in rebuilt_audits) != (
            self.declared_probability_inputs
        ):
            raise _error("required feature records must match declared inputs exactly")
        unavailable = tuple(
            item.feature_id
            for item in rebuilt_audits
            if item.status is not ModelFeatureStatus.AVAILABLE
        )
        blocked = tuple(
            item.feature_id
            for item in rebuilt_audits
            if item.status is ModelFeatureStatus.BLOCKED
        )
        if self.unavailable_feature_ids != unavailable:
            raise _error("unavailable feature identities do not match exact audits")
        if self.blocked_feature_ids != blocked:
            raise _error("blocked feature identities do not match exact audits")
        expected_declared, expected_readiness, expected_reasons = _expected_readiness(
            self.model_status,
            unavailable,
        )
        if self.declared_input_status is not expected_declared:
            raise _error("declared input status differs from exact feature audits")
        if self.readiness_status is not expected_readiness:
            raise _error("probability readiness status differs from reviewed rules")
        if self.readiness_reasons != expected_reasons:
            raise _error("probability readiness reasons differ from reviewed rules")
        object.__setattr__(self, "declared_pricing_inputs", pricing)
        object.__setattr__(self, "required_feature_records", rebuilt_audits)

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_id": self.market_id.value,
            "model_status": self.model_status.value,
            "probability_method": self.probability_method,
            "declared_probability_inputs": [
                item.value for item in self.declared_probability_inputs
            ],
            "declared_pricing_inputs": list(self.declared_pricing_inputs),
            "legacy_missing_input_policy": self.legacy_missing_input_policy.value,
            "reviewed_missing_input_policy": self.reviewed_missing_input_policy,
            "required_feature_records": [
                dataclasses.replace(item).to_dict()
                for item in self.required_feature_records
            ],
            "unavailable_feature_ids": [
                item.value for item in self.unavailable_feature_ids
            ],
            "blocked_feature_ids": [item.value for item in self.blocked_feature_ids],
            "declared_input_status": self.declared_input_status.value,
            "readiness_status": self.readiness_status.value,
            "readiness_reasons": [item.value for item in self.readiness_reasons],
        }


@dataclasses.dataclass(frozen=True)
class ReviewedMatchDetailsProbabilityModelReadiness:
    schema_version: int
    dataset_name: str
    readiness_scope: str
    source_pr66_sha256: str
    source_pr66_size: int
    fixture_identifier: str
    source_match_id: str
    kickoff: datetime.datetime
    as_of: datetime.datetime
    source_model_feature_snapshot_sha256: str
    source_model_feature_snapshot_size: int
    model_status_registry_sha256: str
    model_status_registry_size: int
    reviewed_missing_input_policy: str
    market_readiness: tuple[ProbabilityMarketReadiness, ...]
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise _error("schema_version mismatch")
        if self.dataset_name != DATASET_NAME:
            raise _error("dataset_name mismatch")
        if self.readiness_scope != READINESS_SCOPE:
            raise _error("readiness_scope mismatch")
        source_sha = _sha256(self.source_pr66_sha256, "source_pr66_sha256")
        feature_sha = _sha256(
            self.source_model_feature_snapshot_sha256,
            "source_model_feature_snapshot_sha256",
        )
        registry_sha = _sha256(
            self.model_status_registry_sha256,
            "model_status_registry_sha256",
        )
        source_size = _positive_size(self.source_pr66_size, "source_pr66_size")
        feature_size = _positive_size(
            self.source_model_feature_snapshot_size,
            "source_model_feature_snapshot_size",
        )
        registry_size = _positive_size(
            self.model_status_registry_size,
            "model_status_registry_size",
        )
        fixture = _text(self.fixture_identifier, "fixture_identifier", 512)
        source_match_id = _text(self.source_match_id, "source_match_id", 256)
        match = _FIXTURE_RE.fullmatch(fixture)
        if match is None or match.group(1) != source_match_id:
            raise _error("fixture_identifier/source_match_id mismatch")
        kickoff = _utc(self.kickoff, "kickoff")
        as_of = _utc(self.as_of, "as_of")
        if as_of >= kickoff:
            raise _error("as_of must remain strictly before kickoff")
        if self.reviewed_missing_input_policy != REVIEWED_MISSING_INPUT_POLICY:
            raise _error("reviewed missing-input policy mismatch")
        exact_registry_bytes = canonical_model_status_registry_view_bytes()
        if hashlib.sha256(exact_registry_bytes).hexdigest() != registry_sha:
            raise _error("model_status_registry_sha256 differs from live registry view")
        if len(exact_registry_bytes) != registry_size:
            raise _error("model_status_registry_size differs from live registry view")
        if type(self.market_readiness) is not tuple or any(
            type(item) is not ProbabilityMarketReadiness
            for item in self.market_readiness
        ):
            raise _error("market readiness must be an exact immutable tuple")
        markets = tuple(dataclasses.replace(item) for item in self.market_readiness)
        expected_ids = tuple(sorted(MarketId, key=lambda item: item.value))
        if tuple(item.market_id for item in markets) != expected_ids:
            raise _error("market readiness must contain every MarketId exactly once")
        safety = _validate_safety(self.safety)
        object.__setattr__(self, "source_pr66_sha256", source_sha)
        object.__setattr__(self, "source_pr66_size", source_size)
        object.__setattr__(self, "source_model_feature_snapshot_sha256", feature_sha)
        object.__setattr__(self, "source_model_feature_snapshot_size", feature_size)
        object.__setattr__(self, "model_status_registry_sha256", registry_sha)
        object.__setattr__(self, "model_status_registry_size", registry_size)
        object.__setattr__(self, "fixture_identifier", fixture)
        object.__setattr__(self, "source_match_id", source_match_id)
        object.__setattr__(self, "kickoff", kickoff)
        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(self, "market_readiness", markets)
        object.__setattr__(self, "safety", safety)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "readiness_scope": self.readiness_scope,
            "source_pr66_sha256": self.source_pr66_sha256,
            "source_pr66_size": self.source_pr66_size,
            "fixture_identifier": self.fixture_identifier,
            "source_match_id": self.source_match_id,
            "kickoff": _iso(self.kickoff),
            "as_of": _iso(self.as_of),
            "source_model_feature_snapshot_sha256": (
                self.source_model_feature_snapshot_sha256
            ),
            "source_model_feature_snapshot_size": (
                self.source_model_feature_snapshot_size
            ),
            "model_status_registry_sha256": self.model_status_registry_sha256,
            "model_status_registry_size": self.model_status_registry_size,
            "reviewed_missing_input_policy": self.reviewed_missing_input_policy,
            "market_readiness": [
                dataclasses.replace(item).to_dict() for item in self.market_readiness
            ],
            "safety": dict(self.safety),
        }


def _build_market_readiness(
    feature_by_id: Mapping[ModelFeatureId, ModelFeatureResolution],
) -> tuple[ProbabilityMarketReadiness, ...]:
    records = _registry_records()
    results: list[ProbabilityMarketReadiness] = []
    for record in records:
        market_id = MarketId(record["market_id"])
        model_status = ModelStatus(record["model_status"])
        declared = tuple(ModelFeatureId(item) for item in record["probability_inputs"])
        audits = tuple(
            ProbabilityFeatureAudit.from_resolution(feature_by_id[item])
            for item in declared
        )
        unavailable = tuple(
            item.feature_id
            for item in audits
            if item.status is not ModelFeatureStatus.AVAILABLE
        )
        blocked = tuple(
            item.feature_id
            for item in audits
            if item.status is ModelFeatureStatus.BLOCKED
        )
        declared_status, readiness_status, reasons = _expected_readiness(
            model_status,
            unavailable,
        )
        results.append(
            ProbabilityMarketReadiness(
                market_id=market_id,
                model_status=model_status,
                probability_method=record["probability_method"],
                declared_probability_inputs=declared,
                declared_pricing_inputs=tuple(record["pricing_inputs"]),
                legacy_missing_input_policy=MissingInputPolicy(
                    record["missing_input_policy"]
                ),
                reviewed_missing_input_policy=REVIEWED_MISSING_INPUT_POLICY,
                required_feature_records=audits,
                unavailable_feature_ids=unavailable,
                blocked_feature_ids=blocked,
                declared_input_status=declared_status,
                readiness_status=readiness_status,
                readiness_reasons=reasons,
            )
        )
    return tuple(results)


def build_reviewed_match_details_probability_model_readiness(
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
) -> ReviewedMatchDetailsProbabilityModelReadiness:
    """Replay PR #52→PR #66 and assess every canonical market mechanically."""

    try:
        rebuilt_pr66 = revalidate_reviewed_match_details_model_feature_handoff(
            materialization_inputs=materialization_inputs,
            candidate_set=candidate_set,
            candidate_set_bytes=candidate_set_bytes,
            admission=admission,
            admission_bytes=admission_bytes,
            artifact=artifact,
            artifact_bytes=artifact_bytes,
            handoff=handoff,
            handoff_bytes=handoff_bytes,
        )
        exact_pr66_bytes = (
            canonical_reviewed_match_details_model_feature_handoff_bytes(rebuilt_pr66)
        )
        exact_feature_bytes = canonical_model_feature_snapshot_bytes(
            rebuilt_pr66.model_feature_snapshot
        )
        registry_bytes = canonical_model_status_registry_view_bytes()
        features = rebuilt_pr66.model_feature_snapshot.features
        if type(features) is not tuple or {
            item.feature_id for item in features
        } != set(ModelFeatureId) or len(features) != len(ModelFeatureId):
            raise _error("rebuilt PR #31 snapshot must contain every feature exactly once")
        feature_by_id = types.MappingProxyType(
            {item.feature_id: dataclasses.replace(item) for item in features}
        )
        markets = _build_market_readiness(feature_by_id)
    except (
        FotMobReviewedMatchDetailsProbabilityModelReadinessError,
        FotMobReviewedMatchDetailsModelFeatureHandoffError,
        FixtureModelFeatureError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise _error("PR #52 -> PR #67 readiness construction failed closed") from exc

    exact_feature_sha = hashlib.sha256(exact_feature_bytes).hexdigest()
    if (
        rebuilt_pr66.model_feature_snapshot_sha256 != exact_feature_sha
        or rebuilt_pr66.model_feature_snapshot_size != len(exact_feature_bytes)
    ):
        raise _error("rebuilt PR #66 does not retain exact nested PR #31 identity")

    return ReviewedMatchDetailsProbabilityModelReadiness(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        readiness_scope=READINESS_SCOPE,
        source_pr66_sha256=hashlib.sha256(exact_pr66_bytes).hexdigest(),
        source_pr66_size=len(exact_pr66_bytes),
        fixture_identifier=rebuilt_pr66.fixture_identifier,
        source_match_id=rebuilt_pr66.source_match_id,
        kickoff=rebuilt_pr66.kickoff,
        as_of=rebuilt_pr66.as_of,
        source_model_feature_snapshot_sha256=exact_feature_sha,
        source_model_feature_snapshot_size=len(exact_feature_bytes),
        model_status_registry_sha256=hashlib.sha256(registry_bytes).hexdigest(),
        model_status_registry_size=len(registry_bytes),
        reviewed_missing_input_policy=REVIEWED_MISSING_INPUT_POLICY,
        market_readiness=markets,
        safety=_default_safety(),
    )


def reviewed_match_details_probability_model_readiness_to_dict(
    value: Any,
) -> dict[str, Any]:
    if type(value) is not ReviewedMatchDetailsProbabilityModelReadiness:
        raise _error("value must be exact PR #67 readiness artifact")
    return dataclasses.replace(value).to_dict()


def canonical_reviewed_match_details_probability_model_readiness_bytes(
    value: Any,
) -> bytes:
    if type(value) is not ReviewedMatchDetailsProbabilityModelReadiness:
        raise _error("value must be exact PR #67 readiness artifact")
    try:
        return _canonical_json_bytes(dataclasses.replace(value).to_dict())
    except FotMobReviewedMatchDetailsProbabilityModelReadinessError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
        raise _error("PR #67 readiness canonicalization failed") from exc


def sha256_reviewed_match_details_probability_model_readiness(value: Any) -> str:
    return hashlib.sha256(
        canonical_reviewed_match_details_probability_model_readiness_bytes(value)
    ).hexdigest()


def revalidate_reviewed_match_details_probability_model_readiness(
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
    readiness: Any,
    readiness_bytes: Any,
) -> ReviewedMatchDetailsProbabilityModelReadiness:
    """Replay PR #52→PR #67 and reject detached or coordinated mutation."""

    if type(readiness) is not ReviewedMatchDetailsProbabilityModelReadiness:
        raise _error("readiness must be exact PR #67 artifact")
    if type(readiness_bytes) is not bytes:
        raise _error("readiness_bytes must be exact immutable bytes")
    try:
        supplied = canonical_reviewed_match_details_probability_model_readiness_bytes(
            readiness
        )
        rebuilt = build_reviewed_match_details_probability_model_readiness(
            materialization_inputs=materialization_inputs,
            candidate_set=candidate_set,
            candidate_set_bytes=candidate_set_bytes,
            admission=admission,
            admission_bytes=admission_bytes,
            artifact=artifact,
            artifact_bytes=artifact_bytes,
            handoff=handoff,
            handoff_bytes=handoff_bytes,
        )
        exact = canonical_reviewed_match_details_probability_model_readiness_bytes(
            rebuilt
        )
    except (
        FotMobReviewedMatchDetailsProbabilityModelReadinessError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise _error("PR #52 -> PR #67 readiness failed exact full-chain replay") from exc
    if supplied != exact:
        raise _error("supplied PR #67 artifact differs from exact full-chain rebuild")
    if readiness_bytes != exact:
        raise _error("readiness_bytes are not exact canonical PR #67 bytes")
    return rebuilt


__all__ = [
    "DATASET_NAME",
    "READINESS_SCOPE",
    "REVIEWED_MISSING_INPUT_POLICY",
    "SCHEMA_VERSION",
    "DeclaredInputStatus",
    "FotMobReviewedMatchDetailsProbabilityModelReadinessError",
    "ProbabilityFeatureAudit",
    "ProbabilityMarketReadiness",
    "ProbabilityReadinessReason",
    "ProbabilityReadinessStatus",
    "ReviewedMatchDetailsProbabilityModelReadiness",
    "build_reviewed_match_details_probability_model_readiness",
    "canonical_model_status_registry_view_bytes",
    "canonical_reviewed_match_details_probability_model_readiness_bytes",
    "revalidate_reviewed_match_details_probability_model_readiness",
    "reviewed_match_details_probability_model_readiness_to_dict",
    "sha256_model_status_registry_view",
    "sha256_reviewed_match_details_probability_model_readiness",
]
