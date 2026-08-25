"""Leakage-safe, evidence-qualified Tactical Identity research contract.

The engine consumes the exact Phase 2 as-of corpus and, for source-bound prior
match observations, the exact warehouse named by that corpus. It grants no
prediction, pricing, selection, or betting authority.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass, fields
from datetime import date
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from .historical_asof_features import (
    AUTHORITY_FLAGS as HISTORICAL_AUTHORITY_FLAGS,
    HISTORICAL_ADVANCED_PERIOD_SAFETY_POLICY_ID,
    HISTORICAL_ASOF_DATASET,
    HISTORICAL_ASOF_SCHEMA_VERSION,
    HISTORICAL_COMPLETION_POLICY_ID,
    HISTORICAL_FEATURE_REGISTRY_VERSION,
    HISTORICAL_GENERATION_CONTRACT_VERSION,
    HISTORICAL_TEAM_IDENTITY_POLICY_ID,
    TEMPORAL_POLICY_ID,
    HistoricalFeatureId,
    HistoricalFeatureStatus,
    HistoricalTeamScope,
    HistoricalWindow,
    ReadOnlyHistoricalWarehouse,
    TeamMatchProjection,
    _history,
    complete_boundary_window,
    file_sha256,
    validate_historical_feature_registry,
    validate_historical_generation_contract,
)

TACTICAL_IDENTITY_DATASET = "athena_tactical_identity"
TACTICAL_IDENTITY_SCHEMA_VERSION = 1
TACTICAL_IDENTITY_REGISTRY_VERSION = 1
TACTICAL_GENERATION_CONTRACT_VERSION = 1
RECENCY_POLICY_ID = "EXPONENTIAL_DATE_DECAY_60_DAY_HALF_LIFE_V1"
RECENCY_HALF_LIFE_DAYS = 60.0
COMPETITION_BASELINE_POLICY_ID = "DATE_STRICT_COMPETITION_BASELINE_V1"
SHRINKAGE_POLICY_ID = "EFFECTIVE_SAMPLE_EMPIRICAL_SHRINKAGE_K5_V1"
SHRINKAGE_K = 5.0
MANAGER_REGIME_POLICY_ID = "LAST_OBSERVED_PRIOR_EXACT_MANAGER_V1"
OPPONENT_ADJUSTMENT_POLICY_ID = "PRIOR_MATCH_OPPONENT_PREMATCH_RESIDUAL_V1"
DESCRIPTOR_POLICY_ID = "PRIOR_COMPETITION_Z_BANDS_HALF_SIGMA_V1"
SCORE_STATE_POLICY_ID = "FUTURE_EVIDENCE_REQUIRED_V1"
TACTICAL_HISTORY_POLICY_ID = "COMPLETE_BOUNDARY_LAST_20_V1"
SCHEDULE_CONTEXT_POLICY_ID = "COMPETITION_SCOPED_WORKLOAD_CONTEXT_V1"
MIN_TEAM_COMPONENT_OBSERVATIONS = 3
MIN_BASELINE_POPULATION = 20
DESCRIPTOR_LOW_Z = -0.5
DESCRIPTOR_HIGH_Z = 0.5


class TacticalIdentityError(ValueError):
    """Raised when canonical Tactical Identity cannot be proved safely."""


class TacticalStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    BLOCKED = "BLOCKED"


class TacticalDimensionId(str, Enum):
    EVENT_ENVIRONMENT = "EVENT_ENVIRONMENT"
    ATTACKING_PRODUCTION = "ATTACKING_PRODUCTION"
    DEFENSIVE_SUPPRESSION = "DEFENSIVE_SUPPRESSION"
    SHOT_PROFILE = "SHOT_PROFILE"
    FIRST_HALF_ENVIRONMENT = "FIRST_HALF_ENVIRONMENT"
    CONTROL_TEMPO = "CONTROL_TEMPO"
    SCORING_RELIABILITY = "SCORING_RELIABILITY"
    VENUE_EXPRESSION = "VENUE_EXPRESSION"
    OPPONENT_INTERACTION = "OPPONENT_INTERACTION"
    REGIME_CONTEXT = "REGIME_CONTEXT"
    EVIDENCE_UNCERTAINTY = "EVIDENCE_UNCERTAINTY"


class TacticalDescriptor(str, Enum):
    LOW_EVENT = "LOW_EVENT"
    MID_EVENT = "MID_EVENT"
    HIGH_EVENT = "HIGH_EVENT"
    ATTACK_OUTPUT_LOW = "ATTACK_OUTPUT_LOW"
    ATTACK_OUTPUT_MID = "ATTACK_OUTPUT_MID"
    ATTACK_OUTPUT_HIGH = "ATTACK_OUTPUT_HIGH"
    DEFENSIVE_SUPPRESSION_LOW = "DEFENSIVE_SUPPRESSION_LOW"
    DEFENSIVE_SUPPRESSION_MID = "DEFENSIVE_SUPPRESSION_MID"
    DEFENSIVE_SUPPRESSION_HIGH = "DEFENSIVE_SUPPRESSION_HIGH"
    FIRST_HALF_EVENT_LOW = "FIRST_HALF_EVENT_LOW"
    FIRST_HALF_EVENT_MID = "FIRST_HALF_EVENT_MID"
    FIRST_HALF_EVENT_HIGH = "FIRST_HALF_EVENT_HIGH"


@dataclass(frozen=True)
class TacticalDimensionDefinition:
    dimension_id: TacticalDimensionId
    source_feature_ids: tuple[HistoricalFeatureId, ...]
    component_orientations: tuple[int, ...]
    algorithm_id: str
    minimum_components: int
    scope: str = "OVERALL_AND_TARGET_VENUE"

    def __post_init__(self) -> None:
        if len(self.source_feature_ids) != len(self.component_orientations):
            raise TacticalIdentityError("tactical dimension orientation mismatch")
        if self.minimum_components < 1:
            raise TacticalIdentityError("tactical dimensions require evidence")

    def stable_dict(self) -> dict[str, Any]:
        return {
            "algorithm_id": self.algorithm_id,
            "component_orientations": list(self.component_orientations),
            "dimension_id": self.dimension_id.value,
            "minimum_components": self.minimum_components,
            "recency_policy_id": RECENCY_POLICY_ID,
            "scope": self.scope,
            "shrinkage_policy_id": SHRINKAGE_POLICY_ID,
            "source_feature_ids": [item.value for item in self.source_feature_ids],
        }


def _definition(dimension_id: TacticalDimensionId,
                feature_ids: Sequence[HistoricalFeatureId],
                orientations: Sequence[int], minimum_components: int,
                scope: str = "OVERALL_AND_TARGET_VENUE") -> TacticalDimensionDefinition:
    return TacticalDimensionDefinition(
        dimension_id, tuple(feature_ids), tuple(orientations),
        f"{dimension_id.value}_COMPONENT_Z_MEAN_V1", minimum_components, scope,
    )


TACTICAL_IDENTITY_REGISTRY: tuple[TacticalDimensionDefinition, ...] = (
    _definition(TacticalDimensionId.EVENT_ENVIRONMENT, (
        HistoricalFeatureId.TOTAL_GOALS_PER_MATCH, HistoricalFeatureId.XG_TOTAL_PER_MATCH,
        HistoricalFeatureId.OVER_1_5_RATE, HistoricalFeatureId.OVER_2_5_RATE,
        HistoricalFeatureId.BTTS_RATE, HistoricalFeatureId.FIRST_HALF_TOTAL_GOALS_PER_MATCH,
    ), (1, 1, 1, 1, 1, 1), 3),
    _definition(TacticalDimensionId.ATTACKING_PRODUCTION, (
        HistoricalFeatureId.GOALS_FOR_PER_MATCH, HistoricalFeatureId.XG_FOR_PER_MATCH,
        HistoricalFeatureId.SHOTS_FOR_PER_MATCH,
        HistoricalFeatureId.SHOTS_ON_TARGET_FOR_PER_MATCH,
        HistoricalFeatureId.FAILED_TO_SCORE_RATE,
        HistoricalFeatureId.FIRST_HALF_GOALS_FOR_PER_MATCH,
    ), (1, 1, 1, 1, -1, 1), 3),
    _definition(TacticalDimensionId.DEFENSIVE_SUPPRESSION, (
        HistoricalFeatureId.GOALS_AGAINST_PER_MATCH, HistoricalFeatureId.XG_AGAINST_PER_MATCH,
        HistoricalFeatureId.SHOTS_AGAINST_PER_MATCH,
        HistoricalFeatureId.SHOTS_ON_TARGET_AGAINST_PER_MATCH,
        HistoricalFeatureId.CLEAN_SHEET_RATE,
        HistoricalFeatureId.FIRST_HALF_GOALS_AGAINST_PER_MATCH,
    ), (-1, -1, -1, -1, 1, -1), 3),
    _definition(TacticalDimensionId.SHOT_PROFILE, (
        HistoricalFeatureId.SHOTS_FOR_PER_MATCH, HistoricalFeatureId.SHOTS_AGAINST_PER_MATCH,
        HistoricalFeatureId.SHOTS_ON_TARGET_FOR_PER_MATCH,
        HistoricalFeatureId.SHOTS_ON_TARGET_AGAINST_PER_MATCH,
    ), (1, -1, 1, -1), 2),
    _definition(TacticalDimensionId.FIRST_HALF_ENVIRONMENT, (
        HistoricalFeatureId.FIRST_HALF_GOALS_FOR_PER_MATCH,
        HistoricalFeatureId.FIRST_HALF_GOALS_AGAINST_PER_MATCH,
        HistoricalFeatureId.FIRST_HALF_TOTAL_GOALS_PER_MATCH,
    ), (1, 1, 1), 2),
    _definition(TacticalDimensionId.CONTROL_TEMPO, (
        HistoricalFeatureId.POSSESSION_FOR_MEAN, HistoricalFeatureId.SHOTS_FOR_PER_MATCH,
        HistoricalFeatureId.SHOTS_AGAINST_PER_MATCH,
        HistoricalFeatureId.FIRST_HALF_TOTAL_GOALS_PER_MATCH,
    ), (1, 1, -1, -1), 2),
    _definition(TacticalDimensionId.SCORING_RELIABILITY, (
        HistoricalFeatureId.CLEAN_SHEET_RATE, HistoricalFeatureId.FAILED_TO_SCORE_RATE,
        HistoricalFeatureId.BTTS_RATE, HistoricalFeatureId.OVER_1_5_RATE,
        HistoricalFeatureId.OVER_2_5_RATE,
    ), (1, -1, 1, 1, 1), 3),
    _definition(TacticalDimensionId.VENUE_EXPRESSION, (), (), 1, "DERIVED_FROM_SCOPE_DELTA"),
    _definition(TacticalDimensionId.OPPONENT_INTERACTION, (), (), 1, "SAFE_JOIN_OR_MISSING"),
    _definition(TacticalDimensionId.REGIME_CONTEXT, (), (), 1, "PRIOR_COACH_ONLY"),
    _definition(TacticalDimensionId.EVIDENCE_UNCERTAINTY, (), (), 1, "COVERAGE_METADATA"),
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def calculate_tactical_identity_registry_sha256(
    registry: Sequence[TacticalDimensionDefinition], version: int,
) -> str:
    return hashlib.sha256(_canonical_bytes({
        "registry": [item.stable_dict() for item in registry], "version": version,
    })).hexdigest()


# Independently reviewed literals. They are never generated from the live object.
EXPECTED_TACTICAL_IDENTITY_REGISTRY_SHA256_BY_VERSION: Mapping[int, str] = MappingProxyType({
    1: "c71f11e9f97fcc71bd38eb7a9fa558ebc09e5dfbc648e5991862dc75b80fcb69",
})


def validate_tactical_identity_registry(
    registry: Sequence[TacticalDimensionDefinition] = TACTICAL_IDENTITY_REGISTRY,
    version: int = TACTICAL_IDENTITY_REGISTRY_VERSION,
    expected_by_version: Mapping[int, str] = EXPECTED_TACTICAL_IDENTITY_REGISTRY_SHA256_BY_VERSION,
) -> str:
    expected = expected_by_version.get(version)
    if expected is None:
        raise TacticalIdentityError(f"unreviewed tactical registry version: {version}")
    actual = calculate_tactical_identity_registry_sha256(registry, version)
    if actual != expected:
        raise TacticalIdentityError(
            f"tactical registry drift for version {version}: {actual} != {expected}"
        )
    return actual


def calculate_tactical_generation_contract_sha256(
    version: int, *, tactical_registry_sha256: str,
    tactical_registry_version: int = TACTICAL_IDENTITY_REGISTRY_VERSION,
    temporal_policy_id: str = TEMPORAL_POLICY_ID,
    team_identity_policy_id: str = HISTORICAL_TEAM_IDENTITY_POLICY_ID,
    recency_policy_id: str = RECENCY_POLICY_ID,
    baseline_policy_id: str = COMPETITION_BASELINE_POLICY_ID,
    shrinkage_policy_id: str = SHRINKAGE_POLICY_ID,
    manager_regime_policy_id: str = MANAGER_REGIME_POLICY_ID,
    opponent_adjustment_policy_id: str = OPPONENT_ADJUSTMENT_POLICY_ID,
    descriptor_policy_id: str = DESCRIPTOR_POLICY_ID,
    schema_version: int = TACTICAL_IDENTITY_SCHEMA_VERSION,
) -> str:
    return hashlib.sha256(_canonical_bytes({
        "baseline_policy_id": baseline_policy_id, "descriptor_policy_id": descriptor_policy_id,
        "manager_regime_policy_id": manager_regime_policy_id,
        "opponent_adjustment_policy_id": opponent_adjustment_policy_id,
        "recency_policy_id": recency_policy_id, "schema_version": schema_version,
        "shrinkage_policy_id": shrinkage_policy_id,
        "tactical_registry_sha256": tactical_registry_sha256,
        "tactical_registry_version": tactical_registry_version,
        "team_identity_policy_id": team_identity_policy_id,
        "temporal_policy_id": temporal_policy_id, "version": version,
    })).hexdigest()


EXPECTED_TACTICAL_GENERATION_CONTRACT_SHA256_BY_VERSION: Mapping[int, str] = MappingProxyType({
    1: "73482eb97e8ad0acaa6690a72921117541cc6c97948e35a4ff49b481b738d701",
})


def validate_tactical_generation_contract(
    version: int = TACTICAL_GENERATION_CONTRACT_VERSION,
    expected_by_version: Mapping[int, str] = EXPECTED_TACTICAL_GENERATION_CONTRACT_SHA256_BY_VERSION,
    **overrides: Any,
) -> str:
    registry_sha = overrides.pop("tactical_registry_sha256", None)
    if registry_sha is None:
        registry_sha = validate_tactical_identity_registry()
    expected = expected_by_version.get(version)
    if expected is None:
        raise TacticalIdentityError(f"unreviewed tactical generation contract version: {version}")
    actual = calculate_tactical_generation_contract_sha256(
        version, tactical_registry_sha256=registry_sha, **overrides
    )
    if actual != expected:
        raise TacticalIdentityError(
            f"tactical generation contract drift for version {version}: {actual} != {expected}"
        )
    return actual


_PRIMITIVE_BY_FEATURE: Mapping[HistoricalFeatureId, tuple[str, ...]] = MappingProxyType({
    HistoricalFeatureId.GOALS_FOR_PER_MATCH: ("goals_for",),
    HistoricalFeatureId.GOALS_AGAINST_PER_MATCH: ("goals_against",),
    HistoricalFeatureId.TOTAL_GOALS_PER_MATCH: ("goals_for", "goals_against"),
    HistoricalFeatureId.CLEAN_SHEET_RATE: ("goals_against",),
    HistoricalFeatureId.FAILED_TO_SCORE_RATE: ("goals_for",),
    HistoricalFeatureId.BTTS_RATE: ("goals_for", "goals_against"),
    HistoricalFeatureId.OVER_1_5_RATE: ("goals_for", "goals_against"),
    HistoricalFeatureId.OVER_2_5_RATE: ("goals_for", "goals_against"),
    HistoricalFeatureId.FIRST_HALF_GOALS_FOR_PER_MATCH: ("first_half_goals_for",),
    HistoricalFeatureId.FIRST_HALF_GOALS_AGAINST_PER_MATCH: ("first_half_goals_against",),
    HistoricalFeatureId.FIRST_HALF_TOTAL_GOALS_PER_MATCH: (
        "first_half_goals_for", "first_half_goals_against",
    ),
    HistoricalFeatureId.XG_FOR_PER_MATCH: ("xg_for",),
    HistoricalFeatureId.XG_AGAINST_PER_MATCH: ("xg_against",),
    HistoricalFeatureId.XG_TOTAL_PER_MATCH: ("xg_for", "xg_against"),
    HistoricalFeatureId.SHOTS_FOR_PER_MATCH: ("shots_for",),
    HistoricalFeatureId.SHOTS_AGAINST_PER_MATCH: ("shots_against",),
    HistoricalFeatureId.SHOTS_ON_TARGET_FOR_PER_MATCH: ("shots_on_target_for",),
    HistoricalFeatureId.SHOTS_ON_TARGET_AGAINST_PER_MATCH: ("shots_on_target_against",),
    HistoricalFeatureId.POSSESSION_FOR_MEAN: ("possession_for",),
})


def _feature_value(item: TeamMatchProjection, feature_id: HistoricalFeatureId) -> float | None:
    values = [getattr(item, name) for name in _PRIMITIVE_BY_FEATURE[feature_id]]
    if any(value is None for value in values):
        return None
    gf, ga = item.goals_for, item.goals_against
    if feature_id is HistoricalFeatureId.TOTAL_GOALS_PER_MATCH:
        return float(gf + ga)
    if feature_id is HistoricalFeatureId.CLEAN_SHEET_RATE:
        return float(ga == 0)
    if feature_id is HistoricalFeatureId.FAILED_TO_SCORE_RATE:
        return float(gf == 0)
    if feature_id is HistoricalFeatureId.BTTS_RATE:
        return float(gf > 0 and ga > 0)
    if feature_id is HistoricalFeatureId.OVER_1_5_RATE:
        return float(gf + ga > 1.5)
    if feature_id is HistoricalFeatureId.OVER_2_5_RATE:
        return float(gf + ga > 2.5)
    if feature_id in (HistoricalFeatureId.FIRST_HALF_TOTAL_GOALS_PER_MATCH,
                       HistoricalFeatureId.XG_TOTAL_PER_MATCH):
        return float(values[0]) + float(values[1])
    return float(values[0])


def _blocked(item: TeamMatchProjection, feature_id: HistoricalFeatureId) -> bool:
    return any(name in item.blocked_primitives for name in _PRIMITIVE_BY_FEATURE[feature_id])


@dataclass(frozen=True)
class BaselineMoment:
    count: int
    mean: float | None
    standard_deviation: float | None

    def to_dict(self) -> dict[str, Any]:
        return {"count": self.count, "mean": self.mean,
                "standard_deviation": self.standard_deviation}


def _baseline(history: Sequence[TeamMatchProjection], feature_id: HistoricalFeatureId) -> BaselineMoment:
    count = 0
    mean = 0.0
    m2 = 0.0
    for item in history:
        if _blocked(item, feature_id):
            continue
        value = _feature_value(item, feature_id)
        if value is None:
            continue
        count += 1
        delta = value - mean
        mean += delta / count
        m2 += delta * (value - mean)
    if not count:
        return BaselineMoment(0, None, None)
    return BaselineMoment(count, mean, math.sqrt(m2 / count))


@dataclass(frozen=True)
class TacticalComponentEstimate:
    feature_id: HistoricalFeatureId
    status: TacticalStatus
    raw_team_estimate: float | None
    competition_prior: float | None
    reliability_weight: float | None
    shrunk_estimate: float | None
    relative_z: float | None
    raw_match_sample: int
    effective_weighted_sample: float
    valid_field_sample: int
    missing_field_sample: int
    blocked_field_sample: int
    baseline_population_size: int
    oldest_observation_date: str | None
    newest_observation_date: str | None
    contributing_projection_sha256: tuple[str, ...]
    blocked_projection_sha256: tuple[str, ...]
    conflict_count: int

    def __post_init__(self) -> None:
        if self.raw_match_sample != (
            self.valid_field_sample + self.missing_field_sample + self.blocked_field_sample
        ):
            raise TacticalIdentityError("tactical component samples do not reconcile")
        for value in (self.raw_team_estimate, self.competition_prior,
                      self.reliability_weight, self.shrunk_estimate,
                      self.relative_z, self.effective_weighted_sample):
            if value is not None and not math.isfinite(float(value)):
                raise TacticalIdentityError("tactical component values must be finite")
        if self.status is TacticalStatus.AVAILABLE and self.raw_team_estimate is None:
            raise TacticalIdentityError("AVAILABLE tactical component needs team evidence")
        if self.status is not TacticalStatus.AVAILABLE and self.raw_team_estimate is not None:
            raise TacticalIdentityError("unavailable tactical component cannot retain estimate")

    def to_dict(self) -> dict[str, Any]:
        result = {field.name: getattr(self, field.name) for field in fields(self)}
        result["feature_id"] = self.feature_id.value
        result["status"] = self.status.value
        result["contributing_projection_sha256"] = list(self.contributing_projection_sha256)
        result["blocked_projection_sha256"] = list(self.blocked_projection_sha256)
        return result


def _component(history: Sequence[TeamMatchProjection], feature_id: HistoricalFeatureId,
               target_date: str, baseline: BaselineMoment) -> TacticalComponentEstimate:
    target = date.fromisoformat(target_date)
    valid: list[tuple[TeamMatchProjection, float, float]] = []
    blocked: list[TeamMatchProjection] = []
    missing = 0
    for item in history:
        if _blocked(item, feature_id):
            blocked.append(item)
            continue
        value = _feature_value(item, feature_id)
        if value is None:
            missing += 1
            continue
        age = (target - date.fromisoformat(item.match_date)).days
        if age <= 0:
            raise TacticalIdentityError("DATE_STRICT tactical history violation")
        valid.append((item, value, 2.0 ** (-age / RECENCY_HALF_LIFE_DAYS)))
    if not valid:
        return TacticalComponentEstimate(
            feature_id, TacticalStatus.BLOCKED if blocked else TacticalStatus.MISSING,
            None, baseline.mean if baseline.count >= MIN_BASELINE_POPULATION else None,
            None, None, None, len(history), 0.0, 0, missing, len(blocked),
            baseline.count, None, None, (), tuple(item.projection_sha256 for item in blocked),
            sum(len(item.conflict_fields) for item in blocked),
        )
    weight_sum = sum(item[2] for item in valid)
    raw = sum(value * weight for _, value, weight in valid) / weight_sum
    ess = weight_sum * weight_sum / sum(weight * weight for _, _, weight in valid)
    prior = baseline.mean if baseline.count >= MIN_BASELINE_POPULATION else None
    reliability = ess / (ess + SHRINKAGE_K) if prior is not None else None
    shrunk = reliability * raw + (1.0 - reliability) * prior if reliability is not None else None
    z_value = None
    if shrunk is not None and baseline.standard_deviation not in (None, 0.0):
        z_value = (shrunk - prior) / baseline.standard_deviation
    dates = [item.match_date for item, _, _ in valid]
    return TacticalComponentEstimate(
        feature_id, TacticalStatus.AVAILABLE, raw, prior, reliability, shrunk, z_value,
        len(history), ess, len(valid), missing, len(blocked), baseline.count,
        min(dates), max(dates), tuple(item.projection_sha256 for item, _, _ in valid),
        tuple(item.projection_sha256 for item in blocked),
        sum(len(item.conflict_fields) for item, _, _ in valid) +
        sum(len(item.conflict_fields) for item in blocked),
    )


@dataclass(frozen=True)
class TacticalDimensionResolution:
    dimension_id: TacticalDimensionId
    status: TacticalStatus
    components: tuple[TacticalComponentEstimate, ...]
    continuous_score: float | None
    descriptor: TacticalDescriptor | None
    descriptor_percentile: float | None
    algorithm_id: str
    minimum_components: int
    score_state_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"algorithm_id": self.algorithm_id,
                "components": [item.to_dict() for item in self.components],
                "continuous_score": self.continuous_score,
                "descriptor": self.descriptor.value if self.descriptor else None,
                "descriptor_percentile": self.descriptor_percentile,
                "dimension_id": self.dimension_id.value,
                "minimum_components": self.minimum_components,
                "score_state_status": self.score_state_status,
                "status": self.status.value}


def _descriptor(dimension_id: TacticalDimensionId, score: float) -> TacticalDescriptor | None:
    bands = {
        TacticalDimensionId.EVENT_ENVIRONMENT: (
            TacticalDescriptor.LOW_EVENT, TacticalDescriptor.MID_EVENT, TacticalDescriptor.HIGH_EVENT),
        TacticalDimensionId.ATTACKING_PRODUCTION: (
            TacticalDescriptor.ATTACK_OUTPUT_LOW, TacticalDescriptor.ATTACK_OUTPUT_MID,
            TacticalDescriptor.ATTACK_OUTPUT_HIGH),
        TacticalDimensionId.DEFENSIVE_SUPPRESSION: (
            TacticalDescriptor.DEFENSIVE_SUPPRESSION_LOW,
            TacticalDescriptor.DEFENSIVE_SUPPRESSION_MID,
            TacticalDescriptor.DEFENSIVE_SUPPRESSION_HIGH),
        TacticalDimensionId.FIRST_HALF_ENVIRONMENT: (
            TacticalDescriptor.FIRST_HALF_EVENT_LOW,
            TacticalDescriptor.FIRST_HALF_EVENT_MID,
            TacticalDescriptor.FIRST_HALF_EVENT_HIGH),
    }.get(dimension_id)
    if bands is None:
        return None
    return bands[0] if score <= DESCRIPTOR_LOW_Z else bands[2] if score >= DESCRIPTOR_HIGH_Z else bands[1]


def _dimension(definition: TacticalDimensionDefinition,
               history: Sequence[TeamMatchProjection], target_date: str,
               baselines: Mapping[HistoricalFeatureId, BaselineMoment]) -> TacticalDimensionResolution:
    components = tuple(_component(history, feature_id, target_date, baselines[feature_id])
                       for feature_id in definition.source_feature_ids)
    available = [orientation * item.relative_z
                 for item, orientation in zip(components, definition.component_orientations)
                 if item.relative_z is not None
                 and item.valid_field_sample >= MIN_TEAM_COMPONENT_OBSERVATIONS]
    if len(available) >= definition.minimum_components:
        score = sum(available) / len(available)
        descriptor = _descriptor(definition.dimension_id, score)
        percentile = 0.5 * (1.0 + math.erf(score / math.sqrt(2.0)))
        status = TacticalStatus.AVAILABLE
    else:
        score = percentile = None
        descriptor = None
        status = TacticalStatus.BLOCKED if (
            any(item.status is TacticalStatus.BLOCKED for item in components)
            and not any(item.status is TacticalStatus.AVAILABLE for item in components)
        ) else TacticalStatus.MISSING
    return TacticalDimensionResolution(definition.dimension_id, status, components, score,
                                       descriptor, percentile, definition.algorithm_id,
                                       definition.minimum_components)


@dataclass(frozen=True)
class VenueExpression:
    status: TacticalStatus
    venue_scope: str
    dimension_deltas: tuple[tuple[str, float], ...]

    def to_dict(self) -> dict[str, Any]:
        return {"dimension_deltas": [[key, value] for key, value in self.dimension_deltas],
                "status": self.status.value, "venue_scope": self.venue_scope}


@dataclass(frozen=True)
class OpponentAdjustment:
    status: TacticalStatus
    policy_id: str
    sample_count: int
    residuals: tuple[tuple[str, float], ...]
    reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {"policy_id": self.policy_id, "reason": self.reason,
                "residuals": [[key, value] for key, value in self.residuals],
                "sample_count": self.sample_count, "status": self.status.value}


@dataclass(frozen=True)
class ManagerRegimeContext:
    status: TacticalStatus
    semantic_status: str
    last_observed_prior_manager: str | None
    last_observed_prior_match_date: str | None
    prior_matches_observed_under_manager: int
    manager_change_observed_between_prior_matches: bool | None
    regime_match_keys: tuple[str, ...]
    current_manager_confirmed: bool
    blocker: str | None

    def to_dict(self) -> dict[str, Any]:
        result = {field.name: getattr(self, field.name) for field in fields(self)}
        result["status"] = self.status.value
        result["regime_match_keys"] = list(self.regime_match_keys)
        return result


@dataclass(frozen=True)
class TacticalTeamProfile:
    team: str
    target_side: str
    overall_dimensions: tuple[TacticalDimensionResolution, ...]
    venue_dimensions: tuple[TacticalDimensionResolution, ...]
    venue_expression: VenueExpression
    opponent_adjustment: OpponentAdjustment
    manager_regime: ManagerRegimeContext
    schedule_context: tuple[tuple[str, float | int | None], ...]
    schedule_context_policy_id: str
    coverage: tuple[tuple[str, int], ...]

    def to_dict(self) -> dict[str, Any]:
        return {"coverage": dict(self.coverage), "manager_regime": self.manager_regime.to_dict(),
                "opponent_adjustment": self.opponent_adjustment.to_dict(),
                "overall_dimensions": [item.to_dict() for item in self.overall_dimensions],
                "schedule_context": dict(self.schedule_context),
                "schedule_context_policy_id": self.schedule_context_policy_id,
                "target_side": self.target_side, "team": self.team,
                "venue_dimensions": [item.to_dict() for item in self.venue_dimensions],
                "venue_expression": self.venue_expression.to_dict()}


@dataclass(frozen=True)
class MatchupInteraction:
    event_environment_difference: float | None
    home_attack_vs_away_suppression: float | None
    away_attack_vs_home_suppression: float | None
    uncertainty_note: str

    def to_dict(self) -> dict[str, Any]:
        return {field.name: getattr(self, field.name) for field in fields(self)}


TACTICAL_AUTHORITY_FLAGS: Mapping[str, bool] = MappingProxyType({key: False for key in (
    "network_acquisition_authority", "provider_acquisition_authority",
    "probability_inference_authority", "probability_adjustment_authority",
    "model_training_authority", "model_promotion_authority", "calibration_authority",
    "bookmaker_pricing_authority", "market_activation_authority", "router_authority",
    "market_selection_authority", "accumulator_authority", "production_approval_authority",
    "bet_authority",
)})

_SNAPSHOT_TOKEN = object()


@dataclass(frozen=True, init=False)
class TacticalIdentityFixtureSnapshot:
    target_match_key: str
    target_match_date: str
    target_competition_key: str
    target_scope: str
    target_home_team: str
    target_away_team: str
    source_asof_corpus_sha256: str
    source_warehouse_sha256: str
    historical_feature_registry_version: int
    historical_feature_registry_sha256: str
    historical_generation_contract_version: int
    historical_generation_contract_sha256: str
    tactical_registry_version: int
    tactical_registry_sha256: str
    tactical_generation_contract_version: int
    tactical_generation_contract_sha256: str
    temporal_policy_id: str
    team_identity_policy_id: str
    recency_policy_id: str
    competition_baseline_policy_id: str
    shrinkage_policy_id: str
    manager_regime_policy_id: str
    opponent_adjustment_policy_id: str
    descriptor_policy_id: str
    home_profile: TacticalTeamProfile
    away_profile: TacticalTeamProfile
    matchup_interaction: MatchupInteraction
    authority_flags: tuple[tuple[str, bool], ...]

    def __init__(self, *, _token: object | None = None, **values: Any) -> None:
        if _token is not _SNAPSHOT_TOKEN:
            raise TacticalIdentityError("canonical Tactical Identity snapshots are builder-only")
        for field in fields(type(self)):
            object.__setattr__(self, field.name, values[field.name])

    def to_dict(self) -> dict[str, Any]:
        return {
            "authority_flags": dict(self.authority_flags), "away_profile": self.away_profile.to_dict(),
            "competition_baseline_policy_id": self.competition_baseline_policy_id,
            "dataset": TACTICAL_IDENTITY_DATASET, "descriptor_policy_id": self.descriptor_policy_id,
            "historical_feature_registry_sha256": self.historical_feature_registry_sha256,
            "historical_feature_registry_version": self.historical_feature_registry_version,
            "historical_generation_contract_sha256": self.historical_generation_contract_sha256,
            "historical_generation_contract_version": self.historical_generation_contract_version,
            "home_profile": self.home_profile.to_dict(),
            "manager_regime_policy_id": self.manager_regime_policy_id,
            "matchup_interaction": self.matchup_interaction.to_dict(),
            "opponent_adjustment_policy_id": self.opponent_adjustment_policy_id,
            "recency_policy_id": self.recency_policy_id, "schema_version": TACTICAL_IDENTITY_SCHEMA_VERSION,
            "shrinkage_policy_id": self.shrinkage_policy_id,
            "source_asof_corpus_sha256": self.source_asof_corpus_sha256,
            "source_warehouse_sha256": self.source_warehouse_sha256,
            "tactical_generation_contract_sha256": self.tactical_generation_contract_sha256,
            "tactical_generation_contract_version": self.tactical_generation_contract_version,
            "tactical_registry_sha256": self.tactical_registry_sha256,
            "tactical_registry_version": self.tactical_registry_version,
            "target": {"away_team": self.target_away_team,
                       "competition_key": self.target_competition_key,
                       "home_team": self.target_home_team,
                       "match_date": self.target_match_date,
                       "match_key": self.target_match_key, "scope": self.target_scope},
            "team_identity_policy_id": self.team_identity_policy_id,
            "temporal_policy_id": self.temporal_policy_id,
        }

    @property
    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


REQUIRED_ASOF_META = frozenset({
    "dataset", "feature_registry_sha256", "feature_registry_version",
    "generation_schema_version", "generation_contract_version",
    "generation_contract_sha256", "historical_completion_policy_id",
    "historical_advanced_period_safety_policy_id", "historical_team_identity_policy_id",
    "source_warehouse_sha256", "temporal_policy_id",
})


class ReadOnlyHistoricalAsOfCorpus:
    """SHA-bound, stable, query-only view of one Phase 2 corpus."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path).resolve()
        if not self.path.is_file():
            raise TacticalIdentityError(f"historical as-of corpus does not exist: {self.path}")
        self._assert_no_active_companions()
        self._before_stat = self.path.stat()
        self.sha256 = file_sha256(self.path)
        self._assert_no_active_companions()
        self.connection = sqlite3.connect(f"{self.path.as_uri()}?mode=ro", uri=True)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA query_only=ON")
        try:
            self._validate()
            self._assert_no_active_companions()
        except Exception:
            self.close()
            raise

    def _assert_no_active_companions(self) -> None:
        for suffix in ("-wal", "-journal"):
            companion = Path(str(self.path) + suffix)
            if companion.exists() and companion.stat().st_size:
                raise TacticalIdentityError(f"unsafe active SQLite companion: {companion.name}")

    def _validate(self) -> None:
        objects = {row[0] for row in self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if not {"corpus_meta", "historical_asof_snapshots"}.issubset(objects):
            raise TacticalIdentityError("historical as-of corpus schema mismatch")
        raw = dict(self.connection.execute("SELECT key,value FROM corpus_meta"))
        missing = REQUIRED_ASOF_META - raw.keys()
        if missing:
            raise TacticalIdentityError(f"historical as-of corpus metadata missing: {sorted(missing)}")
        try:
            self.meta = MappingProxyType({key: json.loads(value) for key, value in raw.items()})
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise TacticalIdentityError("invalid historical as-of corpus metadata") from exc
        if self.meta["dataset"] != HISTORICAL_ASOF_DATASET:
            raise TacticalIdentityError("unexpected historical as-of dataset")
        if self.meta["generation_schema_version"] != HISTORICAL_ASOF_SCHEMA_VERSION:
            raise TacticalIdentityError("historical as-of schema version mismatch")
        if self.meta["feature_registry_version"] != HISTORICAL_FEATURE_REGISTRY_VERSION:
            raise TacticalIdentityError("historical feature registry version mismatch")
        if self.meta["feature_registry_sha256"] != validate_historical_feature_registry():
            raise TacticalIdentityError("historical feature registry identity mismatch")
        if self.meta["generation_contract_version"] != HISTORICAL_GENERATION_CONTRACT_VERSION:
            raise TacticalIdentityError("historical generation contract version mismatch")
        if self.meta["generation_contract_sha256"] != validate_historical_generation_contract():
            raise TacticalIdentityError("historical generation contract identity mismatch")
        policy_pairs = {"temporal_policy_id": TEMPORAL_POLICY_ID,
                        "historical_team_identity_policy_id": HISTORICAL_TEAM_IDENTITY_POLICY_ID,
                        "historical_completion_policy_id": HISTORICAL_COMPLETION_POLICY_ID,
                        "historical_advanced_period_safety_policy_id": HISTORICAL_ADVANCED_PERIOD_SAFETY_POLICY_ID}
        if any(self.meta[key] != expected for key, expected in policy_pairs.items()):
            raise TacticalIdentityError("historical as-of policy identity mismatch")

    def snapshot_payload(self, match_key: str) -> Mapping[str, Any]:
        row = self.connection.execute(
            "SELECT canonical_sha256,payload_json FROM historical_asof_snapshots WHERE match_key=?",
            (match_key,),
        ).fetchone()
        if row is None:
            raise TacticalIdentityError(f"target missing from historical as-of corpus: {match_key}")
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise TacticalIdentityError("invalid historical as-of snapshot payload") from exc
        canonical = _canonical_bytes(payload)
        if canonical != row["payload_json"].encode("utf-8"):
            raise TacticalIdentityError("historical as-of payload is not canonical")
        if hashlib.sha256(canonical).hexdigest() != row["canonical_sha256"]:
            raise TacticalIdentityError("historical as-of snapshot identity mismatch")
        if payload.get("source_warehouse_sha256") != self.meta["source_warehouse_sha256"]:
            raise TacticalIdentityError("historical snapshot warehouse ancestry mismatch")
        return MappingProxyType(payload)

    def iter_targets(self) -> Iterable[tuple[str, str, str | None]]:
        yield from self.connection.execute(
            "SELECT match_key,match_date,competition_key FROM historical_asof_snapshots "
            "ORDER BY match_date,match_key"
        )

    def assert_unchanged(self) -> None:
        self._assert_no_active_companions()
        after = self.path.stat()
        if (after.st_size, after.st_mtime_ns) != (self._before_stat.st_size, self._before_stat.st_mtime_ns):
            raise TacticalIdentityError("historical as-of corpus changed during construction")
        if file_sha256(self.path) != self.sha256:
            raise TacticalIdentityError("historical as-of corpus bytes changed during construction")
        self._assert_no_active_companions()

    def close(self) -> None:
        connection = getattr(self, "connection", None)
        if connection is not None:
            connection.close()
            self.connection = None

    def __enter__(self) -> "ReadOnlyHistoricalAsOfCorpus":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()


def _all_competition_history(source: ReadOnlyHistoricalWarehouse, scope: str,
                             competition_key: str, target_date: str) -> tuple[TeamMatchProjection, ...]:
    rows = source._bound_matches(
        "m.match_date < ? AND m.scope=? AND m.competition_key=? "
        "AND m.home_score_ft IS NOT NULL AND m.away_score_ft IS NOT NULL",
        (target_date, scope, competition_key), "m.match_date,m.match_key",
    )
    result: list[TeamMatchProjection] = []
    for row in rows:
        result.extend((source.issue_projection(row, row["home_team"]),
                       source.issue_projection(row, row["away_team"])))
    return tuple(result)


def _manager_context(source: ReadOnlyHistoricalWarehouse,
                     history: Sequence[TeamMatchProjection]) -> ManagerRegimeContext:
    observed: list[tuple[str, str, str]] = []
    blocked = False
    for item in history:
        row = source.target_match(item.match_key)
        field_name = "home_coach" if item.side == "HOME" else "away_coach"
        manager = row[field_name]
        conflicts = set(row["conflict_fields"].split("\x1e")) if row["conflict_fields"] else set()
        if field_name in conflicts:
            blocked = True
            continue
        if isinstance(manager, str) and manager and manager == manager.strip():
            observed.append((item.match_date, item.match_key, manager))
    if not observed:
        return ManagerRegimeContext(
            TacticalStatus.BLOCKED if blocked else TacticalStatus.MISSING,
            "LAST_OBSERVED_PRIOR_MANAGER", None, None, 0, None, (), False,
            "CONFLICTING_PRIOR_COACH_EVIDENCE" if blocked else None)
    observed.sort()
    manager = observed[-1][2]
    regime = []
    for value in reversed(observed):
        if value[2] != manager:
            break
        regime.append(value)
    regime.reverse()
    return ManagerRegimeContext(
        TacticalStatus.AVAILABLE, "LAST_OBSERVED_PRIOR_MANAGER", manager,
        observed[-1][0], len(regime),
        any(a[2] != b[2] for a, b in zip(observed, observed[1:])),
        tuple(item[1] for item in regime), False, None)


def _schedule(payload: Mapping[str, Any], side: str) -> tuple[tuple[str, float | int | None], ...]:
    wanted = {HistoricalFeatureId.DAYS_SINCE_LAST_MATCH.value,
              HistoricalFeatureId.FIXTURES_LAST_7_DAYS.value,
              HistoricalFeatureId.FIXTURES_LAST_14_DAYS.value,
              HistoricalFeatureId.FIXTURES_LAST_28_DAYS.value}
    values: dict[str, float | int | None] = {}
    for row in payload[f"{side}_resolutions"]:
        if (row["feature_id"] in wanted and row["scope"] == HistoricalTeamScope.OVERALL.value
                and row["window"] == HistoricalWindow.AS_OF.value):
            values[row["feature_id"]] = (
                row["value"] if row["status"] == HistoricalFeatureStatus.AVAILABLE.value else None
            )
    return tuple(sorted(values.items()))


def _profile(*, source: ReadOnlyHistoricalWarehouse, payload: Mapping[str, Any],
             side: str, team: str, target_date: str,
             history: Sequence[TeamMatchProjection],
             baselines: Mapping[HistoricalFeatureId, BaselineMoment]) -> TacticalTeamProfile:
    recent = complete_boundary_window(history, 20) if history else ()
    venue_name = "HOME_ONLY" if side == "home" else "AWAY_ONLY"
    venue_history = tuple(item for item in recent
                          if item.side == ("HOME" if side == "home" else "AWAY"))
    definitions = [item for item in TACTICAL_IDENTITY_REGISTRY if item.source_feature_ids]
    core_overall = tuple(_dimension(item, recent, target_date, baselines) for item in definitions)
    venue = tuple(_dimension(item, venue_history, target_date, baselines) for item in definitions)
    deltas = tuple((general.dimension_id.value,
                    split.continuous_score - general.continuous_score)
    for general, split in zip(core_overall, venue)
                   if general.continuous_score is not None and split.continuous_score is not None)
    manager = _manager_context(source, recent)
    opponent = OpponentAdjustment(TacticalStatus.MISSING, OPPONENT_ADJUSTMENT_POLICY_ID, 0, (),
                                  "SAFE_PRE_PRIOR_MATCH_OPPONENT_JOIN_NOT_AVAILABLE")
    venue_status = TacticalStatus.AVAILABLE if deltas else TacticalStatus.MISSING
    meta_dimensions = (
        TacticalDimensionResolution(TacticalDimensionId.VENUE_EXPRESSION, venue_status, (),
                                    None, None, None, "TARGET_VENUE_MINUS_OVERALL_V1", 1),
        TacticalDimensionResolution(TacticalDimensionId.OPPONENT_INTERACTION, opponent.status, (),
                                    None, None, None, OPPONENT_ADJUSTMENT_POLICY_ID, 1),
        TacticalDimensionResolution(TacticalDimensionId.REGIME_CONTEXT, manager.status, (),
                                    None, None, None, MANAGER_REGIME_POLICY_ID, 1),
        TacticalDimensionResolution(TacticalDimensionId.EVIDENCE_UNCERTAINTY,
                                    TacticalStatus.AVAILABLE, (), None, None, None,
                                    "EXPLICIT_COMPONENT_COVERAGE_V1", 1,
                                    SCORE_STATE_POLICY_ID),
    )
    overall = core_overall + meta_dimensions
    components = [component for dimension in core_overall for component in dimension.components]
    return TacticalTeamProfile(
        team, side.upper(), overall, venue,
        VenueExpression(TacticalStatus.AVAILABLE if deltas else TacticalStatus.MISSING,
                        venue_name, deltas),
        opponent, manager, _schedule(payload, side),
        SCHEDULE_CONTEXT_POLICY_ID,
        tuple(sorted({"available_components": sum(item.status is TacticalStatus.AVAILABLE for item in components),
                      "blocked_components": sum(item.status is TacticalStatus.BLOCKED for item in components),
                      "missing_components": sum(item.status is TacticalStatus.MISSING for item in components),
                      "raw_match_sample": len(recent)}.items())))


def _find_score(profile: TacticalTeamProfile, dimension: TacticalDimensionId) -> float | None:
    matches = [item.continuous_score for item in profile.overall_dimensions
               if item.dimension_id is dimension]
    return matches[0] if len(matches) == 1 else None


TACTICAL_SOURCE_FEATURE_IDS = frozenset(
    feature for definition in TACTICAL_IDENTITY_REGISTRY
    for feature in definition.source_feature_ids
)


def competition_baselines(
    competition_history: Sequence[TeamMatchProjection],
) -> Mapping[HistoricalFeatureId, BaselineMoment]:
    return MappingProxyType({
        feature: _baseline(competition_history, feature)
        for feature in TACTICAL_SOURCE_FEATURE_IDS
    })


def _assemble_tactical_identity_snapshot(
    *, corpus: ReadOnlyHistoricalAsOfCorpus,
    source: ReadOnlyHistoricalWarehouse,
    payload: Mapping[str, Any],
    target: Any,
    home_history: Sequence[TeamMatchProjection],
    away_history: Sequence[TeamMatchProjection],
    baselines: Mapping[HistoricalFeatureId, BaselineMoment],
    registry_sha: str,
    generation_sha: str,
) -> TacticalIdentityFixtureSnapshot:
    """Assemble only source-issued target/history and reviewed policy state."""
    if corpus.meta["source_warehouse_sha256"] != source.sha256:
        raise TacticalIdentityError("as-of corpus and warehouse SHA mismatch")
    source._require_bound_row(target)
    for projection in (*home_history, *away_history):
        source.verify_issued_projection(projection)
    if registry_sha != validate_tactical_identity_registry():
        raise TacticalIdentityError("tactical registry identity changed during construction")
    if generation_sha != validate_tactical_generation_contract(
        tactical_registry_sha256=registry_sha
    ):
        raise TacticalIdentityError("tactical generation identity changed during construction")
    if set(baselines) != set(TACTICAL_SOURCE_FEATURE_IDS):
        raise TacticalIdentityError("competition baseline registry coverage mismatch")
    target_payload = payload["target"]
    exact = {"match_key": target["match_key"], "match_date": target["match_date"],
             "competition_key": target["competition_key"], "scope": target["scope"],
             "home_team": target["home_team"], "away_team": target["away_team"]}
    if any(target_payload.get(key) != value for key, value in exact.items()):
        raise TacticalIdentityError("as-of target does not replay from bound warehouse")
    if not all(isinstance(exact[key], str) and exact[key] for key in (
        "competition_key", "scope", "home_team", "away_team")):
        raise TacticalIdentityError("unusable competition-scoped target identity")
    if any(item.match_date >= exact["match_date"] for item in (*home_history, *away_history)):
        raise TacticalIdentityError("DATE_STRICT tactical history violation")
    for expected_team, history in ((exact["home_team"], home_history),
                                   (exact["away_team"], away_history)):
        if any(item.team != expected_team or item.scope != exact["scope"]
               or item.competition_key != exact["competition_key"] for item in history):
            raise TacticalIdentityError("tactical history violates team identity policy")
    home = _profile(source=source, payload=payload, side="home", team=exact["home_team"],
                    target_date=exact["match_date"], history=home_history,
                    baselines=baselines)
    away = _profile(source=source, payload=payload, side="away", team=exact["away_team"],
                    target_date=exact["match_date"], history=away_history,
                    baselines=baselines)
    he, ae = (_find_score(home, TacticalDimensionId.EVENT_ENVIRONMENT),
              _find_score(away, TacticalDimensionId.EVENT_ENVIRONMENT))
    ha, aa = (_find_score(home, TacticalDimensionId.ATTACKING_PRODUCTION),
              _find_score(away, TacticalDimensionId.ATTACKING_PRODUCTION))
    hd, ad = (_find_score(home, TacticalDimensionId.DEFENSIVE_SUPPRESSION),
              _find_score(away, TacticalDimensionId.DEFENSIVE_SUPPRESSION))
    return TacticalIdentityFixtureSnapshot(
        _token=_SNAPSHOT_TOKEN, target_match_key=exact["match_key"],
        target_match_date=exact["match_date"], target_competition_key=exact["competition_key"],
        target_scope=exact["scope"], target_home_team=exact["home_team"],
        target_away_team=exact["away_team"], source_asof_corpus_sha256=corpus.sha256,
        source_warehouse_sha256=source.sha256,
        historical_feature_registry_version=corpus.meta["feature_registry_version"],
        historical_feature_registry_sha256=corpus.meta["feature_registry_sha256"],
        historical_generation_contract_version=corpus.meta["generation_contract_version"],
        historical_generation_contract_sha256=corpus.meta["generation_contract_sha256"],
        tactical_registry_version=TACTICAL_IDENTITY_REGISTRY_VERSION,
        tactical_registry_sha256=registry_sha,
        tactical_generation_contract_version=TACTICAL_GENERATION_CONTRACT_VERSION,
        tactical_generation_contract_sha256=generation_sha,
        temporal_policy_id=TEMPORAL_POLICY_ID,
        team_identity_policy_id=HISTORICAL_TEAM_IDENTITY_POLICY_ID,
        recency_policy_id=RECENCY_POLICY_ID,
        competition_baseline_policy_id=COMPETITION_BASELINE_POLICY_ID,
        shrinkage_policy_id=SHRINKAGE_POLICY_ID,
        manager_regime_policy_id=MANAGER_REGIME_POLICY_ID,
        opponent_adjustment_policy_id=OPPONENT_ADJUSTMENT_POLICY_ID,
        descriptor_policy_id=DESCRIPTOR_POLICY_ID, home_profile=home, away_profile=away,
        matchup_interaction=MatchupInteraction(
            he - ae if he is not None and ae is not None else None,
            ha - ad if ha is not None and ad is not None else None,
            aa - hd if aa is not None and hd is not None else None,
            "DESCRIPTIVE_STATISTICAL_DIFFERENCES_ONLY"),
        authority_flags=tuple(sorted(TACTICAL_AUTHORITY_FLAGS.items())))


def build_tactical_identity_snapshot(asof_corpus_path: Path, warehouse_path: Path,
                                     target_match_key: str) -> TacticalIdentityFixtureSnapshot:
    registry_sha = validate_tactical_identity_registry()
    generation_sha = validate_tactical_generation_contract(tactical_registry_sha256=registry_sha)
    with ReadOnlyHistoricalAsOfCorpus(asof_corpus_path) as corpus, \
            ReadOnlyHistoricalWarehouse(warehouse_path) as source:
        payload = corpus.snapshot_payload(target_match_key)
        target = source.target_match(target_match_key)
        home_history = _history(source, target["scope"], target["competition_key"],
                                target["home_team"], target["match_date"])
        away_history = _history(source, target["scope"], target["competition_key"],
                                target["away_team"], target["match_date"])
        competition_history = _all_competition_history(
            source, target["scope"], target["competition_key"], target["match_date"])
        snapshot = _assemble_tactical_identity_snapshot(
            corpus=corpus, source=source, payload=payload, target=target,
            home_history=home_history, away_history=away_history,
            baselines=competition_baselines(competition_history),
            registry_sha=registry_sha, generation_sha=generation_sha)
        source.assert_unchanged()
        corpus.assert_unchanged()
        if any(HISTORICAL_AUTHORITY_FLAGS.values()) or any(dict(snapshot.authority_flags).values()):
            raise TacticalIdentityError("Tactical Identity cannot grant production authority")
        return snapshot


def canonical_tactical_identity_bytes(snapshot: TacticalIdentityFixtureSnapshot) -> bytes:
    return snapshot.canonical_bytes


def find_dimension(profile: TacticalTeamProfile, dimension_id: TacticalDimensionId,
                   *, venue: bool = False) -> TacticalDimensionResolution:
    values = profile.venue_dimensions if venue else profile.overall_dimensions
    matches = [item for item in values if item.dimension_id is dimension_id]
    if len(matches) != 1:
        raise TacticalIdentityError("tactical dimension is not unique")
    return matches[0]
