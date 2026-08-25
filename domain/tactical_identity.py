"""Leakage-safe, evidence-qualified Tactical Identity research contract.

This Phase 3 layer consumes the exact Phase 2 historical as-of corpus and the
exact read-only warehouse named by that corpus. It is research-only and grants
no prediction, pricing, selection, accumulator, or betting authority.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, fields
from datetime import date
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Iterator, Mapping, Sequence

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
    _warehouse_field_for,
    complete_boundary_window,
    file_sha256,
    historical_team_identity,
    qualifies_completed_prior_fixture,
    validate_historical_feature_registry,
    validate_historical_generation_contract,
)

TACTICAL_IDENTITY_DATASET = "athena_tactical_identity"
TACTICAL_IDENTITY_SCHEMA_VERSION = 1
TACTICAL_IDENTITY_REGISTRY_VERSION = 1
TACTICAL_GENERATION_CONTRACT_VERSION = 1

RECENCY_POLICY_ID = "EXPONENTIAL_DATE_DECAY_60_DAY_HALF_LIFE_V1"
RECENCY_HALF_LIFE_DAYS = 60.0
RECENCY_RELIABILITY_POLICY_ID = "DECAY_WEIGHT_MASS_EMPIRICAL_SHRINKAGE_K5_V1"
COMPETITION_BASELINE_POLICY_ID = "DATE_STRICT_COMPETITION_BASELINE_V1"
SHRINKAGE_POLICY_ID = "DECAY_WEIGHT_MASS_EMPIRICAL_SHRINKAGE_K5_V1"
SHRINKAGE_K = 5.0
MANAGER_REGIME_POLICY_ID = "LAST_OBSERVED_PRIOR_EXACT_MANAGER_DATE_BUCKET_V1"
OPPONENT_ADJUSTMENT_POLICY_ID = "PRIOR_MATCH_OPPONENT_PREMATCH_RESIDUAL_V1"
DESCRIPTOR_POLICY_ID = "PRIOR_COMPETITION_Z_BANDS_HALF_SIGMA_V1"
SCORE_STATE_POLICY_ID = "FUTURE_EVIDENCE_REQUIRED_V1"
TACTICAL_HISTORY_POLICY_ID = "INDEPENDENT_COMPLETE_BOUNDARY_LAST_20_BY_SCOPE_V1"
SCHEDULE_CONTEXT_POLICY_ID = "COMPETITION_SCOPED_WORKLOAD_CONTEXT_V1"
MATCHUP_INTERACTION_POLICY_ID = "DESCRIPTIVE_STATISTICAL_DIFFERENCES_ONLY_V1"
REGIME_PROFILE_POLICY_ID = "CONTIGUOUS_OBSERVED_PRIOR_MANAGER_WITHOUT_UNKNOWN_GAPS_V1"

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
    scope: str

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
            "scope": self.scope,
            "source_feature_ids": [item.value for item in self.source_feature_ids],
        }


def _component_definition(
    dimension_id: TacticalDimensionId,
    feature_ids: Sequence[HistoricalFeatureId],
    orientations: Sequence[int],
    minimum_components: int,
) -> TacticalDimensionDefinition:
    return TacticalDimensionDefinition(
        dimension_id=dimension_id,
        source_feature_ids=tuple(feature_ids),
        component_orientations=tuple(orientations),
        algorithm_id=f"{dimension_id.value}_COMPONENT_Z_MEAN_V1",
        minimum_components=minimum_components,
        scope="OVERALL_AND_TARGET_VENUE",
    )


def _meta_definition(
    dimension_id: TacticalDimensionId, algorithm_id: str, scope: str,
) -> TacticalDimensionDefinition:
    return TacticalDimensionDefinition(
        dimension_id=dimension_id,
        source_feature_ids=(),
        component_orientations=(),
        algorithm_id=algorithm_id,
        minimum_components=1,
        scope=scope,
    )


TACTICAL_IDENTITY_REGISTRY: tuple[TacticalDimensionDefinition, ...] = (
    _component_definition(TacticalDimensionId.EVENT_ENVIRONMENT, (
        HistoricalFeatureId.TOTAL_GOALS_PER_MATCH,
        HistoricalFeatureId.XG_TOTAL_PER_MATCH,
        HistoricalFeatureId.OVER_1_5_RATE,
        HistoricalFeatureId.OVER_2_5_RATE,
        HistoricalFeatureId.BTTS_RATE,
        HistoricalFeatureId.FIRST_HALF_TOTAL_GOALS_PER_MATCH,
    ), (1, 1, 1, 1, 1, 1), 3),
    _component_definition(TacticalDimensionId.ATTACKING_PRODUCTION, (
        HistoricalFeatureId.GOALS_FOR_PER_MATCH,
        HistoricalFeatureId.XG_FOR_PER_MATCH,
        HistoricalFeatureId.SHOTS_FOR_PER_MATCH,
        HistoricalFeatureId.SHOTS_ON_TARGET_FOR_PER_MATCH,
        HistoricalFeatureId.FAILED_TO_SCORE_RATE,
        HistoricalFeatureId.FIRST_HALF_GOALS_FOR_PER_MATCH,
    ), (1, 1, 1, 1, -1, 1), 3),
    _component_definition(TacticalDimensionId.DEFENSIVE_SUPPRESSION, (
        HistoricalFeatureId.GOALS_AGAINST_PER_MATCH,
        HistoricalFeatureId.XG_AGAINST_PER_MATCH,
        HistoricalFeatureId.SHOTS_AGAINST_PER_MATCH,
        HistoricalFeatureId.SHOTS_ON_TARGET_AGAINST_PER_MATCH,
        HistoricalFeatureId.CLEAN_SHEET_RATE,
        HistoricalFeatureId.FIRST_HALF_GOALS_AGAINST_PER_MATCH,
    ), (-1, -1, -1, -1, 1, -1), 3),
    _component_definition(TacticalDimensionId.SHOT_PROFILE, (
        HistoricalFeatureId.SHOTS_FOR_PER_MATCH,
        HistoricalFeatureId.SHOTS_AGAINST_PER_MATCH,
        HistoricalFeatureId.SHOTS_ON_TARGET_FOR_PER_MATCH,
        HistoricalFeatureId.SHOTS_ON_TARGET_AGAINST_PER_MATCH,
    ), (1, -1, 1, -1), 2),
    _component_definition(TacticalDimensionId.FIRST_HALF_ENVIRONMENT, (
        HistoricalFeatureId.FIRST_HALF_GOALS_FOR_PER_MATCH,
        HistoricalFeatureId.FIRST_HALF_GOALS_AGAINST_PER_MATCH,
        HistoricalFeatureId.FIRST_HALF_TOTAL_GOALS_PER_MATCH,
    ), (1, 1, 1), 2),
    _component_definition(TacticalDimensionId.CONTROL_TEMPO, (
        HistoricalFeatureId.POSSESSION_FOR_MEAN,
        HistoricalFeatureId.SHOTS_FOR_PER_MATCH,
        HistoricalFeatureId.SHOTS_AGAINST_PER_MATCH,
        HistoricalFeatureId.FIRST_HALF_TOTAL_GOALS_PER_MATCH,
    ), (1, 1, -1, -1), 2),
    _component_definition(TacticalDimensionId.SCORING_RELIABILITY, (
        HistoricalFeatureId.CLEAN_SHEET_RATE,
        HistoricalFeatureId.FAILED_TO_SCORE_RATE,
        HistoricalFeatureId.BTTS_RATE,
        HistoricalFeatureId.OVER_1_5_RATE,
        HistoricalFeatureId.OVER_2_5_RATE,
    ), (1, -1, 1, 1, 1), 3),
    _meta_definition(
        TacticalDimensionId.VENUE_EXPRESSION,
        "TARGET_VENUE_MINUS_OVERALL_V1",
        "DERIVED_FROM_INDEPENDENT_SCOPE_WINDOWS",
    ),
    _meta_definition(
        TacticalDimensionId.OPPONENT_INTERACTION,
        OPPONENT_ADJUSTMENT_POLICY_ID,
        "STRICT_PRE_PRIOR_MATCH_ASOF_JOIN",
    ),
    _meta_definition(
        TacticalDimensionId.REGIME_CONTEXT,
        MANAGER_REGIME_POLICY_ID,
        "PRIOR_COACH_DATE_BUCKET_ONLY",
    ),
    _meta_definition(
        TacticalDimensionId.EVIDENCE_UNCERTAINTY,
        "EXPLICIT_COMPONENT_COVERAGE_V1",
        "COVERAGE_METADATA",
    ),
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def calculate_tactical_identity_registry_sha256(
    registry: Sequence[TacticalDimensionDefinition], version: int,
) -> str:
    return hashlib.sha256(_canonical_bytes({
        "registry": [item.stable_dict() for item in registry],
        "version": version,
    })).hexdigest()


EXPECTED_TACTICAL_IDENTITY_REGISTRY_SHA256_BY_VERSION: Mapping[int, str] = MappingProxyType({
    1: "f3bc2dadefe51126093c44abdacb0a252498684fbed23c4a5662d8d8e8d01d0e",
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


def _generation_payload(
    version: int,
    *,
    tactical_registry_sha256: str,
    tactical_registry_version: int = TACTICAL_IDENTITY_REGISTRY_VERSION,
    temporal_policy_id: str = TEMPORAL_POLICY_ID,
    team_identity_policy_id: str = HISTORICAL_TEAM_IDENTITY_POLICY_ID,
    historical_completion_policy_id: str = HISTORICAL_COMPLETION_POLICY_ID,
    historical_period_safety_policy_id: str = HISTORICAL_ADVANCED_PERIOD_SAFETY_POLICY_ID,
    historical_feature_registry_version: int = HISTORICAL_FEATURE_REGISTRY_VERSION,
    historical_feature_registry_sha256: str | None = None,
    historical_generation_contract_version: int = HISTORICAL_GENERATION_CONTRACT_VERSION,
    historical_generation_contract_sha256: str | None = None,
    recency_policy_id: str = RECENCY_POLICY_ID,
    recency_half_life_days: float = RECENCY_HALF_LIFE_DAYS,
    recency_reliability_policy_id: str = RECENCY_RELIABILITY_POLICY_ID,
    baseline_policy_id: str = COMPETITION_BASELINE_POLICY_ID,
    shrinkage_policy_id: str = SHRINKAGE_POLICY_ID,
    shrinkage_k: float = SHRINKAGE_K,
    manager_regime_policy_id: str = MANAGER_REGIME_POLICY_ID,
    regime_profile_policy_id: str = REGIME_PROFILE_POLICY_ID,
    opponent_adjustment_policy_id: str = OPPONENT_ADJUSTMENT_POLICY_ID,
    descriptor_policy_id: str = DESCRIPTOR_POLICY_ID,
    descriptor_low_z: float = DESCRIPTOR_LOW_Z,
    descriptor_high_z: float = DESCRIPTOR_HIGH_Z,
    minimum_team_component_observations: int = MIN_TEAM_COMPONENT_OBSERVATIONS,
    minimum_baseline_population: int = MIN_BASELINE_POPULATION,
    tactical_history_policy_id: str = TACTICAL_HISTORY_POLICY_ID,
    schedule_context_policy_id: str = SCHEDULE_CONTEXT_POLICY_ID,
    score_state_policy_id: str = SCORE_STATE_POLICY_ID,
    matchup_interaction_policy_id: str = MATCHUP_INTERACTION_POLICY_ID,
    schema_version: int = TACTICAL_IDENTITY_SCHEMA_VERSION,
) -> dict[str, Any]:
    if historical_feature_registry_sha256 is None:
        historical_feature_registry_sha256 = validate_historical_feature_registry()
    if historical_generation_contract_sha256 is None:
        historical_generation_contract_sha256 = validate_historical_generation_contract()
    return {
        "baseline_policy_id": baseline_policy_id,
        "descriptor_high_z": descriptor_high_z,
        "descriptor_low_z": descriptor_low_z,
        "descriptor_policy_id": descriptor_policy_id,
        "historical_completion_policy_id": historical_completion_policy_id,
        "historical_feature_registry_sha256": historical_feature_registry_sha256,
        "historical_feature_registry_version": historical_feature_registry_version,
        "historical_generation_contract_sha256": historical_generation_contract_sha256,
        "historical_generation_contract_version": historical_generation_contract_version,
        "historical_period_safety_policy_id": historical_period_safety_policy_id,
        "manager_regime_policy_id": manager_regime_policy_id,
        "matchup_interaction_policy_id": matchup_interaction_policy_id,
        "minimum_baseline_population": minimum_baseline_population,
        "minimum_team_component_observations": minimum_team_component_observations,
        "opponent_adjustment_policy_id": opponent_adjustment_policy_id,
        "recency_half_life_days": recency_half_life_days,
        "recency_policy_id": recency_policy_id,
        "recency_reliability_policy_id": recency_reliability_policy_id,
        "regime_profile_policy_id": regime_profile_policy_id,
        "schedule_context_policy_id": schedule_context_policy_id,
        "schema_version": schema_version,
        "score_state_policy_id": score_state_policy_id,
        "shrinkage_k": shrinkage_k,
        "shrinkage_policy_id": shrinkage_policy_id,
        "tactical_history_policy_id": tactical_history_policy_id,
        "tactical_registry_sha256": tactical_registry_sha256,
        "tactical_registry_version": tactical_registry_version,
        "team_identity_policy_id": team_identity_policy_id,
        "temporal_policy_id": temporal_policy_id,
        "version": version,
    }


def calculate_tactical_generation_contract_sha256(
    version: int, *, tactical_registry_sha256: str, **overrides: Any,
) -> str:
    return hashlib.sha256(_canonical_bytes(_generation_payload(
        version,
        tactical_registry_sha256=tactical_registry_sha256,
        **overrides,
    ))).hexdigest()


EXPECTED_TACTICAL_GENERATION_CONTRACT_SHA256_BY_VERSION: Mapping[int, str] = MappingProxyType({
    1: "5658030a4583acc2c6f35ebc1ea0f950e01f1f22d4c6e82ed722e77f26769f9b",
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
        version,
        tactical_registry_sha256=registry_sha,
        **overrides,
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

TACTICAL_SOURCE_FEATURE_IDS = frozenset(
    feature
    for definition in TACTICAL_IDENTITY_REGISTRY
    for feature in definition.source_feature_ids
)

_OPPONENT_RESIDUAL_SPECS: tuple[tuple[str, str, HistoricalFeatureId], ...] = (
    ("goals_attack_residual", "goals_for", HistoricalFeatureId.GOALS_AGAINST_PER_MATCH),
    ("xg_attack_residual", "xg_for", HistoricalFeatureId.XG_AGAINST_PER_MATCH),
    ("shots_attack_residual", "shots_for", HistoricalFeatureId.SHOTS_AGAINST_PER_MATCH),
    (
        "shots_on_target_attack_residual",
        "shots_on_target_for",
        HistoricalFeatureId.SHOTS_ON_TARGET_AGAINST_PER_MATCH,
    ),
    ("goals_defense_residual", "goals_against", HistoricalFeatureId.GOALS_FOR_PER_MATCH),
    ("xg_defense_residual", "xg_against", HistoricalFeatureId.XG_FOR_PER_MATCH),
    ("shots_defense_residual", "shots_against", HistoricalFeatureId.SHOTS_FOR_PER_MATCH),
    (
        "shots_on_target_defense_residual",
        "shots_on_target_against",
        HistoricalFeatureId.SHOTS_ON_TARGET_FOR_PER_MATCH,
    ),
)


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
        return float(gf + ga > 1)
    if feature_id is HistoricalFeatureId.OVER_2_5_RATE:
        return float(gf + ga > 2)
    if feature_id in {
        HistoricalFeatureId.FIRST_HALF_TOTAL_GOALS_PER_MATCH,
        HistoricalFeatureId.XG_TOTAL_PER_MATCH,
    }:
        return float(values[0]) + float(values[1])
    return float(values[0])


def _blocked(item: TeamMatchProjection, feature_id: HistoricalFeatureId) -> bool:
    return any(
        name in item.blocked_primitives
        for name in _PRIMITIVE_BY_FEATURE[feature_id]
    )


def _relevant_conflict_count(
    item: TeamMatchProjection, feature_id: HistoricalFeatureId,
) -> int:
    relevant = {
        field_name
        for primitive in _PRIMITIVE_BY_FEATURE[feature_id]
        if (field_name := _warehouse_field_for(item, primitive)) is not None
    }
    return sum(field_name in relevant for field_name in item.conflict_fields)


@dataclass(frozen=True)
class BaselineMoment:
    count: int
    mean: float | None
    standard_deviation: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "mean": self.mean,
            "standard_deviation": self.standard_deviation,
        }


@dataclass
class _RunningMoment:
    count: int = 0
    mean: float = 0.0
    m2: float = 0.0

    def add(self, value: float) -> None:
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (value - self.mean)

    def freeze(self) -> BaselineMoment:
        return BaselineMoment(
            self.count,
            self.mean if self.count else None,
            math.sqrt(self.m2 / self.count) if self.count else None,
        )


@dataclass(frozen=True)
class _CorpusSnapshotRecord:
    match_key: str
    match_date: str
    competition_key: str | None
    canonical_sha256: str
    payload: Mapping[str, Any]


class ReadOnlyHistoricalAsOfCorpus:
    """SHA-bound, stable, query-only view of one Phase 2 corpus."""

    REQUIRED_META = frozenset({
        "dataset",
        "feature_registry_sha256",
        "feature_registry_version",
        "generation_schema_version",
        "generation_contract_version",
        "generation_contract_sha256",
        "historical_completion_policy_id",
        "historical_advanced_period_safety_policy_id",
        "historical_team_identity_policy_id",
        "source_warehouse_sha256",
        "temporal_policy_id",
    })

    def __init__(self, path: Path) -> None:
        self.path = Path(path).resolve()
        if not self.path.is_file():
            raise TacticalIdentityError(
                f"historical as-of corpus does not exist: {self.path}"
            )
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
                raise TacticalIdentityError(
                    f"unsafe active SQLite companion: {companion.name}"
                )

    def _validate(self) -> None:
        objects = {
            row[0]
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if not {"corpus_meta", "historical_asof_snapshots"}.issubset(objects):
            raise TacticalIdentityError("historical as-of corpus schema mismatch")
        raw = dict(self.connection.execute("SELECT key,value FROM corpus_meta"))
        missing = self.REQUIRED_META - raw.keys()
        if missing:
            raise TacticalIdentityError(
                f"historical as-of corpus metadata missing: {sorted(missing)}"
            )
        try:
            self.meta = MappingProxyType({
                key: json.loads(value) for key, value in raw.items()
            })
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise TacticalIdentityError(
                "invalid historical as-of corpus metadata"
            ) from exc
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
        expected = {
            "temporal_policy_id": TEMPORAL_POLICY_ID,
            "historical_team_identity_policy_id": HISTORICAL_TEAM_IDENTITY_POLICY_ID,
            "historical_completion_policy_id": HISTORICAL_COMPLETION_POLICY_ID,
            "historical_advanced_period_safety_policy_id": (
                HISTORICAL_ADVANCED_PERIOD_SAFETY_POLICY_ID
            ),
        }
        if any(self.meta[key] != value for key, value in expected.items()):
            raise TacticalIdentityError("historical as-of policy identity mismatch")

    def _record_from_row(self, row: sqlite3.Row) -> _CorpusSnapshotRecord:
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise TacticalIdentityError(
                "invalid historical as-of snapshot payload"
            ) from exc
        canonical = _canonical_bytes(payload)
        if canonical != row["payload_json"].encode("utf-8"):
            raise TacticalIdentityError("historical as-of payload is not canonical")
        canonical_sha = hashlib.sha256(canonical).hexdigest()
        if canonical_sha != row["canonical_sha256"]:
            raise TacticalIdentityError("historical as-of snapshot identity mismatch")
        if payload.get("source_warehouse_sha256") != self.meta["source_warehouse_sha256"]:
            raise TacticalIdentityError("historical snapshot warehouse ancestry mismatch")
        target = payload.get("target")
        if not isinstance(target, dict):
            raise TacticalIdentityError("historical as-of target payload missing")
        if (
            target.get("match_key") != row["match_key"]
            or target.get("match_date") != row["match_date"]
            or target.get("competition_key") != row["competition_key"]
        ):
            raise TacticalIdentityError("historical as-of target row mismatch")
        return _CorpusSnapshotRecord(
            match_key=row["match_key"],
            match_date=row["match_date"],
            competition_key=row["competition_key"],
            canonical_sha256=canonical_sha,
            payload=MappingProxyType(payload),
        )

    def snapshot_record(self, match_key: str) -> _CorpusSnapshotRecord:
        row = self.connection.execute(
            "SELECT match_key,match_date,competition_key,canonical_sha256,payload_json "
            "FROM historical_asof_snapshots WHERE match_key=?",
            (match_key,),
        ).fetchone()
        if row is None:
            raise TacticalIdentityError(
                f"target missing from historical as-of corpus: {match_key}"
            )
        return self._record_from_row(row)

    def maybe_snapshot_record(self, match_key: str) -> _CorpusSnapshotRecord | None:
        row = self.connection.execute(
            "SELECT match_key,match_date,competition_key,canonical_sha256,payload_json "
            "FROM historical_asof_snapshots WHERE match_key=?",
            (match_key,),
        ).fetchone()
        return None if row is None else self._record_from_row(row)

    def iter_snapshot_records(self) -> Iterator[_CorpusSnapshotRecord]:
        cursor = self.connection.execute(
            "SELECT match_key,match_date,competition_key,canonical_sha256,payload_json "
            "FROM historical_asof_snapshots ORDER BY match_date,match_key"
        )
        for row in cursor:
            yield self._record_from_row(row)

    def assert_unchanged(self) -> None:
        self._assert_no_active_companions()
        after = self.path.stat()
        if (after.st_size, after.st_mtime_ns) != (
            self._before_stat.st_size,
            self._before_stat.st_mtime_ns,
        ):
            raise TacticalIdentityError(
                "historical as-of corpus changed during construction"
            )
        if file_sha256(self.path) != self.sha256:
            raise TacticalIdentityError(
                "historical as-of corpus bytes changed during construction"
            )
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


def _resolution_from_payload(
    payload: Mapping[str, Any],
    side: str,
    feature_id: HistoricalFeatureId,
    scope: HistoricalTeamScope = HistoricalTeamScope.OVERALL,
    window: HistoricalWindow = HistoricalWindow.LAST_20,
) -> Mapping[str, Any] | None:
    rows = payload.get(f"{side}_resolutions")
    if not isinstance(rows, list):
        return None
    matches = [
        row for row in rows
        if isinstance(row, dict)
        and row.get("feature_id") == feature_id.value
        and row.get("scope") == scope.value
        and row.get("window") == window.value
    ]
    return matches[0] if len(matches) == 1 else None


def _schedule_context(
    payload: Mapping[str, Any], side: str,
) -> tuple[tuple[str, float | int | None], ...]:
    wanted = (
        HistoricalFeatureId.DAYS_SINCE_LAST_MATCH,
        HistoricalFeatureId.FIXTURES_LAST_7_DAYS,
        HistoricalFeatureId.FIXTURES_LAST_14_DAYS,
        HistoricalFeatureId.FIXTURES_LAST_28_DAYS,
    )
    values: dict[str, float | int | None] = {}
    for feature_id in wanted:
        row = _resolution_from_payload(
            payload,
            side,
            feature_id,
            HistoricalTeamScope.OVERALL,
            HistoricalWindow.AS_OF,
        )
        if row is None or row.get("status") != HistoricalFeatureStatus.AVAILABLE.value:
            values[feature_id.value] = None
        else:
            value = row.get("value")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TacticalIdentityError("invalid historical schedule value")
            if not math.isfinite(float(value)):
                raise TacticalIdentityError("non-finite historical schedule value")
            values[feature_id.value] = value
    return tuple(sorted(values.items()))


@dataclass(frozen=True)
class _OpponentExpectation:
    source_snapshot_sha256: str
    status_by_feature: tuple[tuple[str, str, float | None], ...]

    def lookup(self, feature_id: HistoricalFeatureId) -> tuple[str, float | None] | None:
        for name, status, value in self.status_by_feature:
            if name == feature_id.value:
                return status, value
        return None


@dataclass(frozen=True)
class _TacticalObservation:
    projection: TeamMatchProjection
    manager_name: str | None
    manager_conflicted: bool
    opponent_expectation: _OpponentExpectation | None

    @property
    def match_date(self) -> str:
        return self.projection.match_date

    @property
    def match_key(self) -> str:
        return self.projection.match_key


def _opponent_expectation_from_record(
    record: _CorpusSnapshotRecord | None,
    projection: TeamMatchProjection,
) -> _OpponentExpectation | None:
    if record is None:
        return None
    target = record.payload.get("target")
    if not isinstance(target, dict):
        return None
    if projection.side == "HOME":
        expected_team = target.get("away_team")
        opponent_side = "away"
    else:
        expected_team = target.get("home_team")
        opponent_side = "home"
    if expected_team != projection.opponent:
        raise TacticalIdentityError("prior opponent as-of identity mismatch")
    rows: list[tuple[str, str, float | None]] = []
    needed = sorted({spec[2] for spec in _OPPONENT_RESIDUAL_SPECS}, key=lambda x: x.value)
    for feature_id in needed:
        resolution = _resolution_from_payload(
            record.payload,
            opponent_side,
            feature_id,
            HistoricalTeamScope.OVERALL,
            HistoricalWindow.LAST_20,
        )
        if resolution is None:
            rows.append((feature_id.value, TacticalStatus.MISSING.value, None))
            continue
        status = resolution.get("status")
        if status == HistoricalFeatureStatus.BLOCKED.value:
            rows.append((feature_id.value, TacticalStatus.BLOCKED.value, None))
        elif status == HistoricalFeatureStatus.AVAILABLE.value:
            value = resolution.get("value")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TacticalIdentityError("invalid opponent pre-match feature value")
            if not math.isfinite(float(value)):
                raise TacticalIdentityError("non-finite opponent pre-match feature value")
            rows.append((feature_id.value, TacticalStatus.AVAILABLE.value, float(value)))
        else:
            rows.append((feature_id.value, TacticalStatus.MISSING.value, None))
    return _OpponentExpectation(record.canonical_sha256, tuple(rows))


def _manager_for_projection(row: Any, projection: TeamMatchProjection) -> tuple[str | None, bool]:
    field_name = "home_coach" if projection.side == "HOME" else "away_coach"
    conflicts = set(row["conflict_fields"].split("\x1e")) if row["conflict_fields"] else set()
    if field_name in conflicts:
        return None, True
    value = row[field_name]
    if value is None:
        return None, False
    if not isinstance(value, str) or not value or value != value.strip():
        return None, True
    return value, False


def _observation_from_row(
    source: ReadOnlyHistoricalWarehouse,
    row: Any,
    team: str,
    record: _CorpusSnapshotRecord | None,
) -> _TacticalObservation:
    source._require_bound_row(row)
    projection = source.issue_projection(row, team)
    manager_name, manager_conflicted = _manager_for_projection(row, projection)
    return _TacticalObservation(
        projection=projection,
        manager_name=manager_name,
        manager_conflicted=manager_conflicted,
        opponent_expectation=_opponent_expectation_from_record(record, projection),
    )


def _window_observations(
    observations: Sequence[_TacticalObservation], requested: int = 20,
) -> tuple[_TacticalObservation, ...]:
    if not observations:
        return ()
    projections = complete_boundary_window(
        [item.projection for item in observations],
        requested,
    )
    by_sha = {item.projection.projection_sha256: item for item in observations}
    return tuple(by_sha[item.projection_sha256] for item in projections)


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
    decay_weight_sum: float
    kish_effective_sample: float
    shrinkage_evidence_mass: float
    valid_field_sample: int
    missing_field_sample: int
    blocked_field_sample: int
    baseline_population_size: int
    oldest_observation_date: str | None
    newest_observation_date: str | None
    contributing_projection_sha256: tuple[str, ...]
    blocked_projection_sha256: tuple[str, ...]
    conflict_count: int

    @property
    def effective_weighted_sample(self) -> float:
        """Backward-compatible alias for Kish effective sample."""
        return self.kish_effective_sample

    def __post_init__(self) -> None:
        if self.raw_match_sample != (
            self.valid_field_sample
            + self.missing_field_sample
            + self.blocked_field_sample
        ):
            raise TacticalIdentityError("tactical component samples do not reconcile")
        for value in (
            self.raw_team_estimate,
            self.competition_prior,
            self.reliability_weight,
            self.shrunk_estimate,
            self.relative_z,
            self.decay_weight_sum,
            self.kish_effective_sample,
            self.shrinkage_evidence_mass,
        ):
            if value is not None and not math.isfinite(float(value)):
                raise TacticalIdentityError("tactical component values must be finite")
        if self.status is TacticalStatus.AVAILABLE and self.raw_team_estimate is None:
            raise TacticalIdentityError("AVAILABLE tactical component needs team evidence")
        if self.status is not TacticalStatus.AVAILABLE and self.raw_team_estimate is not None:
            raise TacticalIdentityError("unavailable tactical component cannot retain estimate")

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline_population_size": self.baseline_population_size,
            "blocked_field_sample": self.blocked_field_sample,
            "blocked_projection_sha256": list(self.blocked_projection_sha256),
            "competition_prior": self.competition_prior,
            "conflict_count": self.conflict_count,
            "contributing_projection_sha256": list(self.contributing_projection_sha256),
            "decay_weight_sum": self.decay_weight_sum,
            "feature_id": self.feature_id.value,
            "kish_effective_sample": self.kish_effective_sample,
            "missing_field_sample": self.missing_field_sample,
            "newest_observation_date": self.newest_observation_date,
            "oldest_observation_date": self.oldest_observation_date,
            "raw_match_sample": self.raw_match_sample,
            "raw_team_estimate": self.raw_team_estimate,
            "relative_z": self.relative_z,
            "reliability_weight": self.reliability_weight,
            "shrunk_estimate": self.shrunk_estimate,
            "shrinkage_evidence_mass": self.shrinkage_evidence_mass,
            "status": self.status.value,
            "valid_field_sample": self.valid_field_sample,
        }


def _component(
    observations: Sequence[_TacticalObservation],
    feature_id: HistoricalFeatureId,
    target_date: str,
    baseline: BaselineMoment,
) -> TacticalComponentEstimate:
    target = date.fromisoformat(target_date)
    valid: list[tuple[_TacticalObservation, float, float]] = []
    blocked: list[_TacticalObservation] = []
    missing = 0
    for observation in observations:
        item = observation.projection
        if _blocked(item, feature_id):
            blocked.append(observation)
            continue
        value = _feature_value(item, feature_id)
        if value is None:
            missing += 1
            continue
        age = (target - date.fromisoformat(item.match_date)).days
        if age <= 0:
            raise TacticalIdentityError("DATE_STRICT tactical history violation")
        weight = 2.0 ** (-age / RECENCY_HALF_LIFE_DAYS)
        valid.append((observation, value, weight))
    prior = baseline.mean if baseline.count >= MIN_BASELINE_POPULATION else None
    if not valid:
        return TacticalComponentEstimate(
            feature_id=feature_id,
            status=TacticalStatus.BLOCKED if blocked else TacticalStatus.MISSING,
            raw_team_estimate=None,
            competition_prior=prior,
            reliability_weight=None,
            shrunk_estimate=None,
            relative_z=None,
            raw_match_sample=len(observations),
            decay_weight_sum=0.0,
            kish_effective_sample=0.0,
            shrinkage_evidence_mass=0.0,
            valid_field_sample=0,
            missing_field_sample=missing,
            blocked_field_sample=len(blocked),
            baseline_population_size=baseline.count,
            oldest_observation_date=None,
            newest_observation_date=None,
            contributing_projection_sha256=(),
            blocked_projection_sha256=tuple(
                item.projection.projection_sha256 for item in blocked
            ),
            conflict_count=sum(
                _relevant_conflict_count(item.projection, feature_id)
                for item in blocked
            ),
        )
    weight_sum = sum(item[2] for item in valid)
    raw = sum(value * weight for _, value, weight in valid) / weight_sum
    kish = weight_sum * weight_sum / sum(weight * weight for _, _, weight in valid)
    evidence_mass = weight_sum
    reliability = (
        evidence_mass / (evidence_mass + SHRINKAGE_K)
        if prior is not None
        else None
    )
    shrunk = (
        reliability * raw + (1.0 - reliability) * prior
        if reliability is not None
        else None
    )
    z_value = None
    if (
        shrunk is not None
        and baseline.standard_deviation is not None
        and baseline.standard_deviation > 0.0
    ):
        z_value = (shrunk - prior) / baseline.standard_deviation
    dates = [item.projection.match_date for item, _, _ in valid]
    return TacticalComponentEstimate(
        feature_id=feature_id,
        status=TacticalStatus.AVAILABLE,
        raw_team_estimate=raw,
        competition_prior=prior,
        reliability_weight=reliability,
        shrunk_estimate=shrunk,
        relative_z=z_value,
        raw_match_sample=len(observations),
        decay_weight_sum=weight_sum,
        kish_effective_sample=kish,
        shrinkage_evidence_mass=evidence_mass,
        valid_field_sample=len(valid),
        missing_field_sample=missing,
        blocked_field_sample=len(blocked),
        baseline_population_size=baseline.count,
        oldest_observation_date=min(dates),
        newest_observation_date=max(dates),
        contributing_projection_sha256=tuple(
            item.projection.projection_sha256 for item, _, _ in valid
        ),
        blocked_projection_sha256=tuple(
            item.projection.projection_sha256 for item in blocked
        ),
        conflict_count=sum(
            _relevant_conflict_count(item.projection, feature_id)
            for item, _, _ in valid
        ) + sum(
            _relevant_conflict_count(item.projection, feature_id)
            for item in blocked
        ),
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
        return {
            "algorithm_id": self.algorithm_id,
            "components": [item.to_dict() for item in self.components],
            "continuous_score": self.continuous_score,
            "descriptor": self.descriptor.value if self.descriptor else None,
            "descriptor_percentile": self.descriptor_percentile,
            "dimension_id": self.dimension_id.value,
            "minimum_components": self.minimum_components,
            "score_state_status": self.score_state_status,
            "status": self.status.value,
        }


def _descriptor(
    dimension_id: TacticalDimensionId, score: float,
) -> TacticalDescriptor | None:
    bands = {
        TacticalDimensionId.EVENT_ENVIRONMENT: (
            TacticalDescriptor.LOW_EVENT,
            TacticalDescriptor.MID_EVENT,
            TacticalDescriptor.HIGH_EVENT,
        ),
        TacticalDimensionId.ATTACKING_PRODUCTION: (
            TacticalDescriptor.ATTACK_OUTPUT_LOW,
            TacticalDescriptor.ATTACK_OUTPUT_MID,
            TacticalDescriptor.ATTACK_OUTPUT_HIGH,
        ),
        TacticalDimensionId.DEFENSIVE_SUPPRESSION: (
            TacticalDescriptor.DEFENSIVE_SUPPRESSION_LOW,
            TacticalDescriptor.DEFENSIVE_SUPPRESSION_MID,
            TacticalDescriptor.DEFENSIVE_SUPPRESSION_HIGH,
        ),
        TacticalDimensionId.FIRST_HALF_ENVIRONMENT: (
            TacticalDescriptor.FIRST_HALF_EVENT_LOW,
            TacticalDescriptor.FIRST_HALF_EVENT_MID,
            TacticalDescriptor.FIRST_HALF_EVENT_HIGH,
        ),
    }.get(dimension_id)
    if bands is None:
        return None
    if score <= DESCRIPTOR_LOW_Z:
        return bands[0]
    if score >= DESCRIPTOR_HIGH_Z:
        return bands[2]
    return bands[1]


def _dimension(
    definition: TacticalDimensionDefinition,
    observations: Sequence[_TacticalObservation],
    target_date: str,
    baselines: Mapping[HistoricalFeatureId, BaselineMoment],
) -> TacticalDimensionResolution:
    components = tuple(
        _component(observations, feature_id, target_date, baselines[feature_id])
        for feature_id in definition.source_feature_ids
    )
    available = [
        orientation * item.relative_z
        for item, orientation in zip(components, definition.component_orientations)
        if item.relative_z is not None
        and item.valid_field_sample >= MIN_TEAM_COMPONENT_OBSERVATIONS
    ]
    if len(available) >= definition.minimum_components:
        score = sum(available) / len(available)
        return TacticalDimensionResolution(
            dimension_id=definition.dimension_id,
            status=TacticalStatus.AVAILABLE,
            components=components,
            continuous_score=score,
            descriptor=_descriptor(definition.dimension_id, score),
            descriptor_percentile=0.5 * (1.0 + math.erf(score / math.sqrt(2.0))),
            algorithm_id=definition.algorithm_id,
            minimum_components=definition.minimum_components,
        )
    status = (
        TacticalStatus.BLOCKED
        if any(item.status is TacticalStatus.BLOCKED for item in components)
        and not any(item.status is TacticalStatus.AVAILABLE for item in components)
        else TacticalStatus.MISSING
    )
    return TacticalDimensionResolution(
        dimension_id=definition.dimension_id,
        status=status,
        components=components,
        continuous_score=None,
        descriptor=None,
        descriptor_percentile=None,
        algorithm_id=definition.algorithm_id,
        minimum_components=definition.minimum_components,
    )


@dataclass(frozen=True)
class VenueExpression:
    status: TacticalStatus
    venue_scope: str
    dimension_deltas: tuple[tuple[str, float], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension_deltas": [list(item) for item in self.dimension_deltas],
            "status": self.status.value,
            "venue_scope": self.venue_scope,
        }


@dataclass(frozen=True)
class OpponentAdjustment:
    status: TacticalStatus
    policy_id: str
    sample_count: int
    valid_sample: int
    missing_sample: int
    blocked_sample: int
    residuals: tuple[tuple[str, float], ...]
    contributing_match_keys: tuple[str, ...]
    opponent_snapshot_sha256: tuple[str, ...]
    reason: str | None

    def __post_init__(self) -> None:
        if self.sample_count != self.valid_sample + self.missing_sample + self.blocked_sample:
            raise TacticalIdentityError("opponent-adjustment samples do not reconcile")

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocked_sample": self.blocked_sample,
            "contributing_match_keys": list(self.contributing_match_keys),
            "missing_sample": self.missing_sample,
            "opponent_snapshot_sha256": list(self.opponent_snapshot_sha256),
            "policy_id": self.policy_id,
            "reason": self.reason,
            "residuals": [list(item) for item in self.residuals],
            "sample_count": self.sample_count,
            "status": self.status.value,
            "valid_sample": self.valid_sample,
        }


def _opponent_adjustment(
    observations: Sequence[_TacticalObservation], target_date: str,
) -> OpponentAdjustment:
    target = date.fromisoformat(target_date)
    weighted: dict[str, list[tuple[float, float]]] = defaultdict(list)
    valid_matches: list[str] = []
    snapshots: set[str] = set()
    missing = 0
    blocked = 0
    for observation in observations:
        projection = observation.projection
        expectation = observation.opponent_expectation
        match_valid = False
        match_blocked = False
        if expectation is None:
            missing += 1
            continue
        age = (target - date.fromisoformat(projection.match_date)).days
        if age <= 0:
            raise TacticalIdentityError("DATE_STRICT opponent-adjustment violation")
        weight = 2.0 ** (-age / RECENCY_HALF_LIFE_DAYS)
        for metric, primitive, opponent_feature in _OPPONENT_RESIDUAL_SPECS:
            if primitive in projection.blocked_primitives:
                match_blocked = True
                continue
            observed = getattr(projection, primitive)
            expected = expectation.lookup(opponent_feature)
            if observed is None or expected is None:
                continue
            status, expected_value = expected
            if status == TacticalStatus.BLOCKED.value:
                match_blocked = True
                continue
            if status != TacticalStatus.AVAILABLE.value or expected_value is None:
                continue
            weighted[metric].append((float(observed) - expected_value, weight))
            match_valid = True
        if match_valid:
            valid_matches.append(projection.match_key)
            snapshots.add(expectation.source_snapshot_sha256)
        elif match_blocked:
            blocked += 1
        else:
            missing += 1
    residuals = tuple(sorted(
        (
            metric,
            sum(value * weight for value, weight in values)
            / sum(weight for _, weight in values),
        )
        for metric, values in weighted.items()
        if values
    ))
    valid_count = len(valid_matches)
    sample_count = valid_count + missing + blocked
    if valid_count:
        status = TacticalStatus.AVAILABLE
        reason = None
    elif blocked:
        status = TacticalStatus.BLOCKED
        reason = "ONLY_BLOCKED_OR_MISSING_PRE_PRIOR_MATCH_OPPONENT_EVIDENCE"
    else:
        status = TacticalStatus.MISSING
        reason = "NO_SAFE_PRE_PRIOR_MATCH_OPPONENT_EXPECTATION"
    return OpponentAdjustment(
        status=status,
        policy_id=OPPONENT_ADJUSTMENT_POLICY_ID,
        sample_count=sample_count,
        valid_sample=valid_count,
        missing_sample=missing,
        blocked_sample=blocked,
        residuals=residuals,
        contributing_match_keys=tuple(valid_matches),
        opponent_snapshot_sha256=tuple(sorted(snapshots)),
        reason=reason,
    )


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
    unknown_gap_after_last_observation: bool
    continuity_proven: bool
    blocker: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocker": self.blocker,
            "continuity_proven": self.continuity_proven,
            "current_manager_confirmed": self.current_manager_confirmed,
            "last_observed_prior_manager": self.last_observed_prior_manager,
            "last_observed_prior_match_date": self.last_observed_prior_match_date,
            "manager_change_observed_between_prior_matches": (
                self.manager_change_observed_between_prior_matches
            ),
            "prior_matches_observed_under_manager": self.prior_matches_observed_under_manager,
            "regime_match_keys": list(self.regime_match_keys),
            "semantic_status": self.semantic_status,
            "status": self.status.value,
            "unknown_gap_after_last_observation": self.unknown_gap_after_last_observation,
        }


def _manager_context(
    observations: Sequence[_TacticalObservation],
) -> ManagerRegimeContext:
    if not observations:
        return ManagerRegimeContext(
            TacticalStatus.MISSING,
            "LAST_OBSERVED_PRIOR_MANAGER",
            None,
            None,
            0,
            None,
            (),
            False,
            False,
            False,
            None,
        )
    by_date: dict[str, list[_TacticalObservation]] = defaultdict(list)
    for observation in observations:
        by_date[observation.match_date].append(observation)
    buckets: list[tuple[str, str | None, bool, tuple[str, ...]]] = []
    for match_date in sorted(by_date):
        bucket = by_date[match_date]
        if any(item.manager_conflicted for item in bucket):
            buckets.append((match_date, None, True, tuple(sorted(item.match_key for item in bucket))))
            continue
        names = {item.manager_name for item in bucket if item.manager_name is not None}
        if len(names) > 1:
            return ManagerRegimeContext(
                TacticalStatus.BLOCKED,
                "LAST_OBSERVED_PRIOR_MANAGER",
                None,
                match_date,
                0,
                None,
                (),
                False,
                False,
                False,
                "AMBIGUOUS_SAME_DATE_PRIOR_MANAGER",
            )
        manager = next(iter(names)) if names else None
        buckets.append((match_date, manager, False, tuple(sorted(item.match_key for item in bucket))))
    observed_indexes = [index for index, value in enumerate(buckets) if value[1] is not None]
    if not observed_indexes:
        blocked = any(value[2] for value in buckets)
        return ManagerRegimeContext(
            TacticalStatus.BLOCKED if blocked else TacticalStatus.MISSING,
            "LAST_OBSERVED_PRIOR_MANAGER",
            None,
            None,
            0,
            None,
            (),
            False,
            False,
            False,
            "CONFLICTING_PRIOR_COACH_EVIDENCE" if blocked else None,
        )
    latest_index = observed_indexes[-1]
    latest_date, manager, _, latest_keys = buckets[latest_index]
    assert manager is not None
    unknown_gap_after = any(
        buckets[index][1] is None for index in range(latest_index + 1, len(buckets))
    )
    regime_keys = list(latest_keys)
    continuity_proven = not unknown_gap_after
    cursor = latest_index - 1
    while cursor >= 0:
        _, prior_manager, prior_blocked, keys = buckets[cursor]
        if prior_blocked or prior_manager is None:
            continuity_proven = False
            break
        if prior_manager != manager:
            break
        regime_keys[0:0] = list(keys)
        cursor -= 1
    observed_sequence = [buckets[index][1] for index in observed_indexes]
    manager_change = any(a != b for a, b in zip(observed_sequence, observed_sequence[1:]))
    return ManagerRegimeContext(
        status=TacticalStatus.AVAILABLE,
        semantic_status="LAST_OBSERVED_PRIOR_MANAGER",
        last_observed_prior_manager=manager,
        last_observed_prior_match_date=latest_date,
        prior_matches_observed_under_manager=len(regime_keys),
        manager_change_observed_between_prior_matches=manager_change,
        regime_match_keys=tuple(regime_keys),
        current_manager_confirmed=False,
        unknown_gap_after_last_observation=unknown_gap_after,
        continuity_proven=continuity_proven,
        blocker=None,
    )


@dataclass(frozen=True)
class RegimeExpression:
    status: TacticalStatus
    semantic_status: str
    manager: str | None
    dimension_deltas: tuple[tuple[str, float], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension_deltas": [list(item) for item in self.dimension_deltas],
            "manager": self.manager,
            "semantic_status": self.semantic_status,
            "status": self.status.value,
        }


@dataclass(frozen=True)
class TacticalTeamProfile:
    team: str
    target_side: str
    overall_dimensions: tuple[TacticalDimensionResolution, ...]
    venue_dimensions: tuple[TacticalDimensionResolution, ...]
    regime_dimensions: tuple[TacticalDimensionResolution, ...]
    venue_expression: VenueExpression
    regime_expression: RegimeExpression
    opponent_adjustment: OpponentAdjustment
    manager_regime: ManagerRegimeContext
    schedule_context: tuple[tuple[str, float | int | None], ...]
    schedule_context_policy_id: str
    coverage: tuple[tuple[str, int], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "coverage": dict(self.coverage),
            "manager_regime": self.manager_regime.to_dict(),
            "opponent_adjustment": self.opponent_adjustment.to_dict(),
            "overall_dimensions": [item.to_dict() for item in self.overall_dimensions],
            "regime_dimensions": [item.to_dict() for item in self.regime_dimensions],
            "regime_expression": self.regime_expression.to_dict(),
            "schedule_context": dict(self.schedule_context),
            "schedule_context_policy_id": self.schedule_context_policy_id,
            "target_side": self.target_side,
            "team": self.team,
            "venue_dimensions": [item.to_dict() for item in self.venue_dimensions],
            "venue_expression": self.venue_expression.to_dict(),
        }


@dataclass(frozen=True)
class MatchupInteraction:
    event_environment_difference: float | None
    home_attack_vs_away_suppression: float | None
    away_attack_vs_home_suppression: float | None
    policy_id: str
    uncertainty_note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "away_attack_vs_home_suppression": self.away_attack_vs_home_suppression,
            "event_environment_difference": self.event_environment_difference,
            "home_attack_vs_away_suppression": self.home_attack_vs_away_suppression,
            "policy_id": self.policy_id,
            "uncertainty_note": self.uncertainty_note,
        }


TACTICAL_AUTHORITY_FLAGS: Mapping[str, bool] = MappingProxyType({
    key: False for key in (
        "network_acquisition_authority",
        "provider_acquisition_authority",
        "probability_inference_authority",
        "probability_adjustment_authority",
        "model_training_authority",
        "model_promotion_authority",
        "calibration_authority",
        "bookmaker_pricing_authority",
        "market_activation_authority",
        "router_authority",
        "market_selection_authority",
        "accumulator_authority",
        "production_approval_authority",
        "bet_authority",
    )
})


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
    recency_reliability_policy_id: str
    competition_baseline_policy_id: str
    shrinkage_policy_id: str
    manager_regime_policy_id: str
    regime_profile_policy_id: str
    opponent_adjustment_policy_id: str
    descriptor_policy_id: str
    tactical_history_policy_id: str
    schedule_context_policy_id: str
    score_state_policy_id: str
    matchup_interaction_policy_id: str
    home_profile: TacticalTeamProfile
    away_profile: TacticalTeamProfile
    matchup_interaction: MatchupInteraction
    authority_flags: tuple[tuple[str, bool], ...]

    def __init__(self, **_values: Any) -> None:
        raise TacticalIdentityError(
            "canonical Tactical Identity snapshots are source-builder-only"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "authority_flags": dict(self.authority_flags),
            "away_profile": self.away_profile.to_dict(),
            "competition_baseline_policy_id": self.competition_baseline_policy_id,
            "dataset": TACTICAL_IDENTITY_DATASET,
            "descriptor_policy_id": self.descriptor_policy_id,
            "historical_feature_registry_sha256": self.historical_feature_registry_sha256,
            "historical_feature_registry_version": self.historical_feature_registry_version,
            "historical_generation_contract_sha256": self.historical_generation_contract_sha256,
            "historical_generation_contract_version": self.historical_generation_contract_version,
            "home_profile": self.home_profile.to_dict(),
            "manager_regime_policy_id": self.manager_regime_policy_id,
            "matchup_interaction": self.matchup_interaction.to_dict(),
            "matchup_interaction_policy_id": self.matchup_interaction_policy_id,
            "opponent_adjustment_policy_id": self.opponent_adjustment_policy_id,
            "recency_policy_id": self.recency_policy_id,
            "recency_reliability_policy_id": self.recency_reliability_policy_id,
            "regime_profile_policy_id": self.regime_profile_policy_id,
            "schedule_context_policy_id": self.schedule_context_policy_id,
            "schema_version": TACTICAL_IDENTITY_SCHEMA_VERSION,
            "score_state_policy_id": self.score_state_policy_id,
            "shrinkage_policy_id": self.shrinkage_policy_id,
            "source_asof_corpus_sha256": self.source_asof_corpus_sha256,
            "source_warehouse_sha256": self.source_warehouse_sha256,
            "tactical_generation_contract_sha256": self.tactical_generation_contract_sha256,
            "tactical_generation_contract_version": self.tactical_generation_contract_version,
            "tactical_history_policy_id": self.tactical_history_policy_id,
            "tactical_registry_sha256": self.tactical_registry_sha256,
            "tactical_registry_version": self.tactical_registry_version,
            "target": {
                "away_team": self.target_away_team,
                "competition_key": self.target_competition_key,
                "home_team": self.target_home_team,
                "match_date": self.target_match_date,
                "match_key": self.target_match_key,
                "scope": self.target_scope,
            },
            "team_identity_policy_id": self.team_identity_policy_id,
            "temporal_policy_id": self.temporal_policy_id,
        }

    @property
    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


_CORE_DEFINITIONS = tuple(
    definition
    for definition in TACTICAL_IDENTITY_REGISTRY
    if definition.source_feature_ids
)


def _core_dimensions(
    observations: Sequence[_TacticalObservation],
    target_date: str,
    baselines: Mapping[HistoricalFeatureId, BaselineMoment],
) -> tuple[TacticalDimensionResolution, ...]:
    return tuple(
        _dimension(definition, observations, target_date, baselines)
        for definition in _CORE_DEFINITIONS
    )


def _find_score_in_dimensions(
    dimensions: Sequence[TacticalDimensionResolution],
    dimension_id: TacticalDimensionId,
) -> float | None:
    matches = [
        item.continuous_score
        for item in dimensions
        if item.dimension_id is dimension_id
    ]
    return matches[0] if len(matches) == 1 else None


def _profile(
    *,
    payload: Mapping[str, Any],
    side: str,
    team: str,
    target_date: str,
    overall_observations: Sequence[_TacticalObservation],
    venue_observations: Sequence[_TacticalObservation],
    baselines: Mapping[HistoricalFeatureId, BaselineMoment],
) -> TacticalTeamProfile:
    overall = _core_dimensions(overall_observations, target_date, baselines)
    venue = _core_dimensions(venue_observations, target_date, baselines)
    venue_deltas = tuple(
        (
            general.dimension_id.value,
            split.continuous_score - general.continuous_score,
        )
        for general, split in zip(overall, venue)
        if general.continuous_score is not None
        and split.continuous_score is not None
    )
    manager = _manager_context(overall_observations)
    regime_keys = set(manager.regime_match_keys)
    regime_observations = tuple(
        item for item in overall_observations if item.match_key in regime_keys
    )
    regime = (
        _core_dimensions(regime_observations, target_date, baselines)
        if manager.status is TacticalStatus.AVAILABLE and regime_observations
        else ()
    )
    regime_deltas = tuple(
        (
            general.dimension_id.value,
            regime_dimension.continuous_score - general.continuous_score,
        )
        for general, regime_dimension in zip(overall, regime)
        if general.continuous_score is not None
        and regime_dimension.continuous_score is not None
    )
    opponent = _opponent_adjustment(overall_observations, target_date)
    venue_status = TacticalStatus.AVAILABLE if venue_deltas else TacticalStatus.MISSING
    regime_status = (
        TacticalStatus.AVAILABLE
        if regime
        else manager.status
    )
    meta_dimensions = (
        TacticalDimensionResolution(
            TacticalDimensionId.VENUE_EXPRESSION,
            venue_status,
            (),
            None,
            None,
            None,
            "TARGET_VENUE_MINUS_OVERALL_V1",
            1,
        ),
        TacticalDimensionResolution(
            TacticalDimensionId.OPPONENT_INTERACTION,
            opponent.status,
            (),
            None,
            None,
            None,
            OPPONENT_ADJUSTMENT_POLICY_ID,
            1,
        ),
        TacticalDimensionResolution(
            TacticalDimensionId.REGIME_CONTEXT,
            regime_status,
            (),
            None,
            None,
            None,
            MANAGER_REGIME_POLICY_ID,
            1,
        ),
        TacticalDimensionResolution(
            TacticalDimensionId.EVIDENCE_UNCERTAINTY,
            TacticalStatus.AVAILABLE,
            (),
            None,
            None,
            None,
            "EXPLICIT_COMPONENT_COVERAGE_V1",
            1,
            SCORE_STATE_POLICY_ID,
        ),
    )
    components = [component for dimension in overall for component in dimension.components]
    venue_scope = "HOME_ONLY" if side == "home" else "AWAY_ONLY"
    return TacticalTeamProfile(
        team=team,
        target_side=side.upper(),
        overall_dimensions=overall + meta_dimensions,
        venue_dimensions=venue,
        regime_dimensions=regime,
        venue_expression=VenueExpression(
            venue_status,
            venue_scope,
            venue_deltas,
        ),
        regime_expression=RegimeExpression(
            regime_status,
            "LAST_OBSERVED_PRIOR_MANAGER_REGIME",
            manager.last_observed_prior_manager,
            regime_deltas,
        ),
        opponent_adjustment=opponent,
        manager_regime=manager,
        schedule_context=_schedule_context(payload, side),
        schedule_context_policy_id=SCHEDULE_CONTEXT_POLICY_ID,
        coverage=tuple(sorted({
            "available_components": sum(
                item.status is TacticalStatus.AVAILABLE for item in components
            ),
            "blocked_components": sum(
                item.status is TacticalStatus.BLOCKED for item in components
            ),
            "missing_components": sum(
                item.status is TacticalStatus.MISSING for item in components
            ),
            "overall_match_sample": len(overall_observations),
            "venue_match_sample": len(venue_observations),
            "regime_match_sample": len(regime_observations),
            "opponent_adjusted_match_sample": opponent.valid_sample,
        }.items())),
    )


def _safe_paths(main: Path) -> frozenset[Path]:
    resolved = main.resolve()
    return frozenset(
        {resolved}
        | {Path(str(resolved) + suffix) for suffix in ("-wal", "-journal", "-shm")}
    )


def _temporary_output(output: Path, protected: frozenset[Path]) -> Path:
    for _ in range(100):
        candidate = output.with_name(
            f".{output.name}.{secrets.token_hex(12)}.tmp"
        ).resolve()
        if candidate in protected or candidate.exists():
            continue
        descriptor = os.open(
            candidate,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
        os.close(descriptor)
        return candidate
    raise TacticalIdentityError("cannot allocate safe Tactical Identity output")


def _create_output(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript("""
        PRAGMA journal_mode=DELETE;
        PRAGMA synchronous=FULL;
        CREATE TABLE corpus_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE tactical_identity_snapshots(
          match_key TEXT PRIMARY KEY,
          match_date TEXT NOT NULL,
          competition_key TEXT NOT NULL,
          canonical_sha256 TEXT NOT NULL,
          payload_json TEXT NOT NULL
        );
        CREATE INDEX idx_tactical_date
          ON tactical_identity_snapshots(match_date,match_key);
    """)
    return connection


class _RollingTeamHistory:
    def __init__(self) -> None:
        self._overall: list[tuple[str, list[_TacticalObservation]]] = []
        self._home: list[tuple[str, list[_TacticalObservation]]] = []
        self._away: list[tuple[str, list[_TacticalObservation]]] = []

    @staticmethod
    def _add_bucket(
        buckets: list[tuple[str, list[_TacticalObservation]]],
        match_date: str,
        observations: Sequence[_TacticalObservation],
    ) -> None:
        if not observations:
            return
        buckets.append((
            match_date,
            sorted(observations, key=lambda item: item.match_key),
        ))
        while len(buckets) > 1 and sum(
            len(group) for _, group in buckets[1:]
        ) >= 20:
            buckets.pop(0)

    def add(self, match_date: str, observations: Sequence[_TacticalObservation]) -> None:
        self._add_bucket(self._overall, match_date, observations)
        self._add_bucket(
            self._home,
            match_date,
            [item for item in observations if item.projection.side == "HOME"],
        )
        self._add_bucket(
            self._away,
            match_date,
            [item for item in observations if item.projection.side == "AWAY"],
        )

    @staticmethod
    def _values(
        buckets: Sequence[tuple[str, Sequence[_TacticalObservation]]],
    ) -> tuple[_TacticalObservation, ...]:
        return tuple(item for _, group in buckets for item in group)

    def overall(self) -> tuple[_TacticalObservation, ...]:
        return self._values(self._overall)

    def home(self) -> tuple[_TacticalObservation, ...]:
        return self._values(self._home)

    def away(self) -> tuple[_TacticalObservation, ...]:
        return self._values(self._away)


def _target_identity_from_row(row: Any) -> tuple[str, str, str, str, str, str]:
    values = (
        row["match_key"],
        row["match_date"],
        row["competition_key"],
        row["scope"],
        row["home_team"],
        row["away_team"],
    )
    if not all(isinstance(value, str) and value and value == value.strip() for value in values):
        raise TacticalIdentityError("unusable competition-scoped target identity")
    return values


def _validate_target_record(row: Any, record: _CorpusSnapshotRecord) -> None:
    exact = _target_identity_from_row(row)
    payload_target = record.payload.get("target")
    if not isinstance(payload_target, dict):
        raise TacticalIdentityError("as-of target payload missing")
    expected = {
        "match_key": exact[0],
        "match_date": exact[1],
        "competition_key": exact[2],
        "scope": exact[3],
        "home_team": exact[4],
        "away_team": exact[5],
    }
    if any(payload_target.get(key) != value for key, value in expected.items()):
        raise TacticalIdentityError("as-of target does not replay from bound warehouse")


def _competition_baseline_from_rows(
    source: ReadOnlyHistoricalWarehouse,
    rows: Sequence[Any],
) -> Mapping[HistoricalFeatureId, BaselineMoment]:
    moments = {feature: _RunningMoment() for feature in TACTICAL_SOURCE_FEATURE_IDS}
    for row in rows:
        if not qualifies_completed_prior_fixture(row):
            continue
        for team in (row["home_team"], row["away_team"]):
            projection = source.issue_projection(row, team)
            for feature_id, moment in moments.items():
                if _blocked(projection, feature_id):
                    continue
                value = _feature_value(projection, feature_id)
                if value is not None:
                    moment.add(value)
    return MappingProxyType({
        feature_id: moment.freeze()
        for feature_id, moment in moments.items()
    })


def _team_observations_direct(
    source: ReadOnlyHistoricalWarehouse,
    corpus: ReadOnlyHistoricalAsOfCorpus,
    scope: str,
    competition_key: str,
    team: str,
    target_date: str,
) -> tuple[_TacticalObservation, ...]:
    rows = source.historical_matches(scope, competition_key, team, target_date)
    result: list[_TacticalObservation] = []
    for row in rows:
        if not qualifies_completed_prior_fixture(row):
            continue
        record = corpus.maybe_snapshot_record(row["match_key"])
        result.append(_observation_from_row(source, row, team, record))
    return tuple(result)


def _independent_windows(
    observations: Sequence[_TacticalObservation], target_side: str,
) -> tuple[tuple[_TacticalObservation, ...], tuple[_TacticalObservation, ...]]:
    overall = _window_observations(observations, 20)
    venue_side = "HOME" if target_side == "home" else "AWAY"
    venue = _window_observations(
        [item for item in observations if item.projection.side == venue_side],
        20,
    )
    return overall, venue


def _build_profile_pair(
    *,
    record: _CorpusSnapshotRecord,
    row: Any,
    home_overall: Sequence[_TacticalObservation],
    home_venue: Sequence[_TacticalObservation],
    away_overall: Sequence[_TacticalObservation],
    away_venue: Sequence[_TacticalObservation],
    baselines: Mapping[HistoricalFeatureId, BaselineMoment],
) -> tuple[TacticalTeamProfile, TacticalTeamProfile]:
    _validate_target_record(row, record)
    target_date = row["match_date"]
    if any(
        item.match_date >= target_date
        for item in (*home_overall, *home_venue, *away_overall, *away_venue)
    ):
        raise TacticalIdentityError("DATE_STRICT tactical history violation")
    for expected_team, observations in (
        (row["home_team"], home_overall),
        (row["away_team"], away_overall),
    ):
        for observation in observations:
            projection = observation.projection
            if historical_team_identity(
                projection.scope,
                projection.competition_key,
                projection.team,
            ) != historical_team_identity(
                row["scope"],
                row["competition_key"],
                expected_team,
            ):
                raise TacticalIdentityError(
                    "tactical history violates team identity policy"
                )
    if set(baselines) != set(TACTICAL_SOURCE_FEATURE_IDS):
        raise TacticalIdentityError("competition baseline registry coverage mismatch")
    home = _profile(
        payload=record.payload,
        side="home",
        team=row["home_team"],
        target_date=target_date,
        overall_observations=home_overall,
        venue_observations=home_venue,
        baselines=baselines,
    )
    away = _profile(
        payload=record.payload,
        side="away",
        team=row["away_team"],
        target_date=target_date,
        overall_observations=away_overall,
        venue_observations=away_venue,
        baselines=baselines,
    )
    return home, away


def _snapshot_values(
    *,
    corpus: ReadOnlyHistoricalAsOfCorpus,
    source: ReadOnlyHistoricalWarehouse,
    row: Any,
    home: TacticalTeamProfile,
    away: TacticalTeamProfile,
    registry_sha: str,
    generation_sha: str,
) -> dict[str, Any]:
    he = _find_score_in_dimensions(
        home.overall_dimensions, TacticalDimensionId.EVENT_ENVIRONMENT
    )
    ae = _find_score_in_dimensions(
        away.overall_dimensions, TacticalDimensionId.EVENT_ENVIRONMENT
    )
    ha = _find_score_in_dimensions(
        home.overall_dimensions, TacticalDimensionId.ATTACKING_PRODUCTION
    )
    aa = _find_score_in_dimensions(
        away.overall_dimensions, TacticalDimensionId.ATTACKING_PRODUCTION
    )
    hd = _find_score_in_dimensions(
        home.overall_dimensions, TacticalDimensionId.DEFENSIVE_SUPPRESSION
    )
    ad = _find_score_in_dimensions(
        away.overall_dimensions, TacticalDimensionId.DEFENSIVE_SUPPRESSION
    )
    return {
        "target_match_key": row["match_key"],
        "target_match_date": row["match_date"],
        "target_competition_key": row["competition_key"],
        "target_scope": row["scope"],
        "target_home_team": row["home_team"],
        "target_away_team": row["away_team"],
        "source_asof_corpus_sha256": corpus.sha256,
        "source_warehouse_sha256": source.sha256,
        "historical_feature_registry_version": corpus.meta["feature_registry_version"],
        "historical_feature_registry_sha256": corpus.meta["feature_registry_sha256"],
        "historical_generation_contract_version": corpus.meta["generation_contract_version"],
        "historical_generation_contract_sha256": corpus.meta["generation_contract_sha256"],
        "tactical_registry_version": TACTICAL_IDENTITY_REGISTRY_VERSION,
        "tactical_registry_sha256": registry_sha,
        "tactical_generation_contract_version": TACTICAL_GENERATION_CONTRACT_VERSION,
        "tactical_generation_contract_sha256": generation_sha,
        "temporal_policy_id": TEMPORAL_POLICY_ID,
        "team_identity_policy_id": HISTORICAL_TEAM_IDENTITY_POLICY_ID,
        "recency_policy_id": RECENCY_POLICY_ID,
        "recency_reliability_policy_id": RECENCY_RELIABILITY_POLICY_ID,
        "competition_baseline_policy_id": COMPETITION_BASELINE_POLICY_ID,
        "shrinkage_policy_id": SHRINKAGE_POLICY_ID,
        "manager_regime_policy_id": MANAGER_REGIME_POLICY_ID,
        "regime_profile_policy_id": REGIME_PROFILE_POLICY_ID,
        "opponent_adjustment_policy_id": OPPONENT_ADJUSTMENT_POLICY_ID,
        "descriptor_policy_id": DESCRIPTOR_POLICY_ID,
        "tactical_history_policy_id": TACTICAL_HISTORY_POLICY_ID,
        "schedule_context_policy_id": SCHEDULE_CONTEXT_POLICY_ID,
        "score_state_policy_id": SCORE_STATE_POLICY_ID,
        "matchup_interaction_policy_id": MATCHUP_INTERACTION_POLICY_ID,
        "home_profile": home,
        "away_profile": away,
        "matchup_interaction": MatchupInteraction(
            he - ae if he is not None and ae is not None else None,
            ha - ad if ha is not None and ad is not None else None,
            aa - hd if aa is not None and hd is not None else None,
            MATCHUP_INTERACTION_POLICY_ID,
            "DESCRIPTIVE_STATISTICAL_DIFFERENCES_ONLY",
        ),
        "authority_flags": tuple(sorted(TACTICAL_AUTHORITY_FLAGS.items())),
    }


def _install_canonical_builders() -> tuple[Any, Any]:
    """Install source-owned builders without exposing a constructor token/assembler."""

    def new_snapshot(values: Mapping[str, Any]) -> TacticalIdentityFixtureSnapshot:
        snapshot = object.__new__(TacticalIdentityFixtureSnapshot)
        for field in fields(TacticalIdentityFixtureSnapshot):
            object.__setattr__(snapshot, field.name, values[field.name])
        return snapshot

    def validate_sources(
        corpus: ReadOnlyHistoricalAsOfCorpus,
        source: ReadOnlyHistoricalWarehouse,
    ) -> None:
        if corpus.meta["source_warehouse_sha256"] != source.sha256:
            raise TacticalIdentityError("as-of corpus and warehouse SHA mismatch")

    def direct_build(
        asof_corpus_path: Path,
        warehouse_path: Path,
        target_match_key: str,
    ) -> TacticalIdentityFixtureSnapshot:
        registry_sha = validate_tactical_identity_registry()
        generation_sha = validate_tactical_generation_contract(
            tactical_registry_sha256=registry_sha
        )
        with ReadOnlyHistoricalAsOfCorpus(asof_corpus_path) as corpus, \
                ReadOnlyHistoricalWarehouse(warehouse_path) as source:
            validate_sources(corpus, source)
            record = corpus.snapshot_record(target_match_key)
            row = source.target_match(target_match_key)
            source._require_bound_row(row)
            _validate_target_record(row, record)
            _, target_date, competition_key, scope, home_team, away_team = (
                _target_identity_from_row(row)
            )
            home_all = _team_observations_direct(
                source, corpus, scope, competition_key, home_team, target_date
            )
            away_all = _team_observations_direct(
                source, corpus, scope, competition_key, away_team, target_date
            )
            home_overall, home_venue = _independent_windows(home_all, "home")
            away_overall, away_venue = _independent_windows(away_all, "away")
            competition_rows = source._bound_matches(
                "m.match_date < ? AND m.scope=? AND m.competition_key=?",
                (target_date, scope, competition_key),
                "m.match_date,m.match_key",
            )
            baselines = _competition_baseline_from_rows(source, competition_rows)
            home, away = _build_profile_pair(
                record=record,
                row=row,
                home_overall=home_overall,
                home_venue=home_venue,
                away_overall=away_overall,
                away_venue=away_venue,
                baselines=baselines,
            )
            snapshot = new_snapshot(_snapshot_values(
                corpus=corpus,
                source=source,
                row=row,
                home=home,
                away=away,
                registry_sha=registry_sha,
                generation_sha=generation_sha,
            ))
            source.assert_unchanged()
            corpus.assert_unchanged()
            if any(HISTORICAL_AUTHORITY_FLAGS.values()) or any(
                dict(snapshot.authority_flags).values()
            ):
                raise TacticalIdentityError(
                    "Tactical Identity cannot grant production authority"
                )
            return snapshot

    def bulk_build(
        asof_corpus_path: Path,
        warehouse_path: Path,
        output_path: Path,
        *,
        competition: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
        replace: bool = False,
    ) -> int:
        asof_path = Path(asof_corpus_path).resolve()
        warehouse = Path(warehouse_path).resolve()
        output = Path(output_path).resolve()
        operational = (Path(__file__).resolve().parents[1] / "database" / "athena.db").resolve()
        protected = _safe_paths(asof_path) | _safe_paths(warehouse) | _safe_paths(operational)
        if output in protected:
            raise TacticalIdentityError(
                "output must be separate from all source/operational SQLite paths"
            )
        if output.exists() and not replace:
            raise TacticalIdentityError(f"output already exists: {output}")
        if limit is not None and limit < 1:
            raise TacticalIdentityError("limit must be positive")
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = _temporary_output(output, protected)
        registry_sha = validate_tactical_identity_registry()
        generation_sha = validate_tactical_generation_contract(
            tactical_registry_sha256=registry_sha
        )
        count = 0
        try:
            with ReadOnlyHistoricalAsOfCorpus(asof_path) as corpus, \
                    ReadOnlyHistoricalWarehouse(warehouse) as source:
                validate_sources(corpus, source)
                histories: dict[tuple[str, str, str], _RollingTeamHistory] = defaultdict(
                    _RollingTeamHistory
                )
                moments: dict[
                    tuple[str, str],
                    dict[HistoricalFeatureId, _RunningMoment],
                ] = defaultdict(lambda: {
                    feature: _RunningMoment() for feature in TACTICAL_SOURCE_FEATURE_IDS
                })
                destination = _create_output(temporary)
                try:
                    meta = {
                        "dataset": TACTICAL_IDENTITY_DATASET,
                        "schema_version": TACTICAL_IDENTITY_SCHEMA_VERSION,
                        "source_asof_corpus_sha256": corpus.sha256,
                        "source_warehouse_sha256": source.sha256,
                        "historical_feature_registry_version": corpus.meta["feature_registry_version"],
                        "historical_feature_registry_sha256": corpus.meta["feature_registry_sha256"],
                        "historical_generation_contract_version": corpus.meta["generation_contract_version"],
                        "historical_generation_contract_sha256": corpus.meta["generation_contract_sha256"],
                        "tactical_registry_version": TACTICAL_IDENTITY_REGISTRY_VERSION,
                        "tactical_registry_sha256": registry_sha,
                        "tactical_generation_contract_version": TACTICAL_GENERATION_CONTRACT_VERSION,
                        "tactical_generation_contract_sha256": generation_sha,
                        "recency_policy_id": RECENCY_POLICY_ID,
                        "recency_reliability_policy_id": RECENCY_RELIABILITY_POLICY_ID,
                        "competition_baseline_policy_id": COMPETITION_BASELINE_POLICY_ID,
                        "shrinkage_policy_id": SHRINKAGE_POLICY_ID,
                        "manager_regime_policy_id": MANAGER_REGIME_POLICY_ID,
                        "regime_profile_policy_id": REGIME_PROFILE_POLICY_ID,
                        "opponent_adjustment_policy_id": OPPONENT_ADJUSTMENT_POLICY_ID,
                        "descriptor_policy_id": DESCRIPTOR_POLICY_ID,
                        "tactical_history_policy_id": TACTICAL_HISTORY_POLICY_ID,
                        "schedule_context_policy_id": SCHEDULE_CONTEXT_POLICY_ID,
                        "score_state_policy_id": SCORE_STATE_POLICY_ID,
                        "matchup_interaction_policy_id": MATCHUP_INTERACTION_POLICY_ID,
                    }
                    destination.executemany(
                        "INSERT INTO corpus_meta VALUES(?,?)",
                        sorted(
                            (
                                key,
                                json.dumps(value, separators=(",", ":")),
                            )
                            for key, value in meta.items()
                        ),
                    )
                    corpus_iter = iter(corpus.iter_snapshot_records())
                    next_record = next(corpus_iter, None)
                    batch: list[tuple[Any, _CorpusSnapshotRecord | None]] = []
                    batch_date: str | None = None

                    def advance_record(row: Any) -> _CorpusSnapshotRecord | None:
                        nonlocal next_record
                        row_key = (row["match_date"], row["match_key"])
                        while next_record is not None and (
                            next_record.match_date,
                            next_record.match_key,
                        ) < row_key:
                            next_record = next(corpus_iter, None)
                        if next_record is not None and (
                            next_record.match_date,
                            next_record.match_key,
                        ) == row_key:
                            current = next_record
                            next_record = next(corpus_iter, None)
                            return current
                        return None

                    def process(
                        rows: Sequence[tuple[Any, _CorpusSnapshotRecord | None]],
                    ) -> bool:
                        nonlocal count
                        additions: dict[
                            tuple[str, str, str],
                            list[_TacticalObservation],
                        ] = defaultdict(list)
                        baseline_additions: dict[
                            tuple[str, str],
                            list[TeamMatchProjection],
                        ] = defaultdict(list)
                        for row, record in rows:
                            source._require_bound_row(row)
                            selected = (
                                record is not None
                                and (competition is None or row["competition_key"] == competition)
                                and (start_date is None or row["match_date"] >= start_date)
                                and (end_date is None or row["match_date"] <= end_date)
                                and (limit is None or count < limit)
                            )
                            home_identity = historical_team_identity(
                                row["scope"], row["competition_key"], row["home_team"]
                            )
                            away_identity = historical_team_identity(
                                row["scope"], row["competition_key"], row["away_team"]
                            )
                            if selected:
                                assert record is not None
                                if home_identity is None or away_identity is None:
                                    raise TacticalIdentityError(
                                        "unusable competition-scoped target identity"
                                    )
                                baseline_key = (row["scope"], row["competition_key"])
                                baseline = MappingProxyType({
                                    feature: moment.freeze()
                                    for feature, moment in moments[baseline_key].items()
                                })
                                home_state = histories[home_identity]
                                away_state = histories[away_identity]
                                home, away = _build_profile_pair(
                                    record=record,
                                    row=row,
                                    home_overall=home_state.overall(),
                                    home_venue=home_state.home(),
                                    away_overall=away_state.overall(),
                                    away_venue=away_state.away(),
                                    baselines=baseline,
                                )
                                snapshot = new_snapshot(_snapshot_values(
                                    corpus=corpus,
                                    source=source,
                                    row=row,
                                    home=home,
                                    away=away,
                                    registry_sha=registry_sha,
                                    generation_sha=generation_sha,
                                ))
                                destination.execute(
                                    "INSERT INTO tactical_identity_snapshots VALUES(?,?,?,?,?)",
                                    (
                                        snapshot.target_match_key,
                                        snapshot.target_match_date,
                                        snapshot.target_competition_key,
                                        snapshot.canonical_sha256,
                                        snapshot.canonical_bytes.decode("utf-8"),
                                    ),
                                )
                                count += 1
                            if qualifies_completed_prior_fixture(row):
                                home_observation = _observation_from_row(
                                    source, row, row["home_team"], record
                                )
                                away_observation = _observation_from_row(
                                    source, row, row["away_team"], record
                                )
                                if home_identity is not None:
                                    additions[home_identity].append(home_observation)
                                if away_identity is not None:
                                    additions[away_identity].append(away_observation)
                                baseline_additions[(
                                    row["scope"], row["competition_key"]
                                )].extend((
                                    home_observation.projection,
                                    away_observation.projection,
                                ))
                        match_date = rows[0][0]["match_date"] if rows else None
                        if match_date is not None:
                            for identity, observations in additions.items():
                                histories[identity].add(match_date, observations)
                            for key, projections in baseline_additions.items():
                                for projection in projections:
                                    for feature_id, moment in moments[key].items():
                                        if _blocked(projection, feature_id):
                                            continue
                                        value = _feature_value(projection, feature_id)
                                        if value is not None:
                                            moment.add(value)
                        return limit is not None and count >= limit

                    for row in source.stream_matches():
                        record = advance_record(row)
                        if batch_date is None:
                            batch_date = row["match_date"]
                        if row["match_date"] != batch_date:
                            if process(batch):
                                batch = []
                                break
                            batch = []
                            batch_date = row["match_date"]
                        batch.append((row, record))
                    if batch:
                        process(batch)
                    destination.commit()
                    source.assert_unchanged()
                    corpus.assert_unchanged()
                finally:
                    destination.close()
            os.replace(temporary, output)
            return count
        except Exception:
            if temporary.exists():
                temporary.unlink()
            raise

    return direct_build, bulk_build


build_tactical_identity_snapshot, build_tactical_identity_corpus = _install_canonical_builders()
del _install_canonical_builders


def _assemble_tactical_identity_snapshot(*_args: Any, **_kwargs: Any) -> None:
    """Legacy private name deliberately rejects caller-authoritative assembly."""
    raise TacticalIdentityError(
        "canonical Tactical Identity assembly is source-owned; use the builders"
    )


def canonical_tactical_identity_bytes(
    snapshot: TacticalIdentityFixtureSnapshot,
) -> bytes:
    return snapshot.canonical_bytes


def find_dimension(
    profile: TacticalTeamProfile,
    dimension_id: TacticalDimensionId,
    *,
    venue: bool = False,
    regime: bool = False,
) -> TacticalDimensionResolution:
    if venue and regime:
        raise TacticalIdentityError("dimension lookup scope is ambiguous")
    values = (
        profile.regime_dimensions
        if regime
        else profile.venue_dimensions
        if venue
        else profile.overall_dimensions
    )
    matches = [item for item in values if item.dimension_id is dimension_id]
    if len(matches) != 1:
        raise TacticalIdentityError("tactical dimension is not unique")
    return matches[0]
