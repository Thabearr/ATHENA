"""Leakage-safe historical as-of football features.

This research-only contract consumes the canonical historical warehouse.  It
never acquires data, creates probabilities, or grants production authority.
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


HISTORICAL_ASOF_DATASET = "athena_historical_asof_features"
HISTORICAL_ASOF_SCHEMA_VERSION = 1
HISTORICAL_FEATURE_REGISTRY_VERSION = 1
TEMPORAL_POLICY_ID = "DATE_STRICT_PRIOR_FIXTURES_V1"
HISTORICAL_TEAM_IDENTITY_POLICY_ID = "COMPETITION_SCOPED_EXACT_CANONICAL_TEAM_V1"
HISTORICAL_COMPLETION_POLICY_ID = "CANONICAL_REGULATION_FT_BOTH_SIDES_V1"
HISTORICAL_ADVANCED_PERIOD_SAFETY_POLICY_ID = (
    "BLOCK_UNQUALIFIED_AGGREGATES_ON_EXTRA_PERIOD_EVIDENCE_V1"
)
HISTORICAL_GENERATION_CONTRACT_VERSION = 1
WAREHOUSE_SCHEMA_VERSION = "1"
CANONICAL_WAREHOUSE_SCHEMA_SQL = (
    Path(__file__).resolve().parents[1] / "database" / "historical_warehouse_schema.sql"
)
EXPECTED_WAREHOUSE_SCHEMA_SQL_SHA256_BY_VERSION: Mapping[str, str] = MappingProxyType(
    {"1": "d5a3b545a639c43a2b35fb18529a429ba2572d2861ac52c638cce42a8141306f"}
)


class HistoricalAsOfError(ValueError):
    """Raised when historical state cannot be constructed safely."""


class HistoricalFeatureStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    BLOCKED = "BLOCKED"


class HistoricalFeatureBlocker(str, Enum):
    INVALID_SOURCE_VALUE = "INVALID_SOURCE_VALUE"
    UNSAFE_SOURCE_STATE = "UNSAFE_SOURCE_STATE"


class HistoricalFeatureFamily(str, Enum):
    FORM_RESULTS = "FORM_RESULTS"
    EVENT_ENVIRONMENT = "EVENT_ENVIRONMENT"
    HALF_TIME = "HALF_TIME"
    EXPECTED_GOALS = "EXPECTED_GOALS"
    SHOTS = "SHOTS"
    POSSESSION = "POSSESSION"
    DISCIPLINE = "DISCIPLINE"
    SCHEDULE = "SCHEDULE"


class HistoricalTeamScope(str, Enum):
    OVERALL = "OVERALL"
    HOME_ONLY = "HOME_ONLY"
    AWAY_ONLY = "AWAY_ONLY"


class HistoricalWindow(str, Enum):
    LAST_5 = "LAST_5"
    LAST_10 = "LAST_10"
    LAST_20 = "LAST_20"
    SEASON_TO_DATE = "SEASON_TO_DATE"
    AS_OF = "AS_OF"


WINDOW_SIZES: Mapping[HistoricalWindow, int | None] = MappingProxyType(
    {
        HistoricalWindow.LAST_5: 5,
        HistoricalWindow.LAST_10: 10,
        HistoricalWindow.LAST_20: 20,
        HistoricalWindow.SEASON_TO_DATE: None,
        HistoricalWindow.AS_OF: None,
    }
)


class HistoricalFeatureId(str, Enum):
    POINTS_PER_MATCH = "points_per_match"
    WIN_RATE = "win_rate"
    DRAW_RATE = "draw_rate"
    LOSS_RATE = "loss_rate"
    GOALS_FOR_PER_MATCH = "goals_for_per_match"
    GOALS_AGAINST_PER_MATCH = "goals_against_per_match"
    GOAL_DIFFERENCE_PER_MATCH = "goal_difference_per_match"
    TOTAL_GOALS_PER_MATCH = "total_goals_per_match"
    CLEAN_SHEET_RATE = "clean_sheet_rate"
    FAILED_TO_SCORE_RATE = "failed_to_score_rate"
    BTTS_RATE = "btts_rate"
    OVER_1_5_RATE = "over_1_5_rate"
    OVER_2_5_RATE = "over_2_5_rate"
    FIRST_HALF_GOALS_FOR_PER_MATCH = "first_half_goals_for_per_match"
    FIRST_HALF_GOALS_AGAINST_PER_MATCH = "first_half_goals_against_per_match"
    FIRST_HALF_TOTAL_GOALS_PER_MATCH = "first_half_total_goals_per_match"
    XG_FOR_PER_MATCH = "xg_for_per_match"
    XG_AGAINST_PER_MATCH = "xg_against_per_match"
    XG_TOTAL_PER_MATCH = "xg_total_per_match"
    SHOTS_FOR_PER_MATCH = "shots_for_per_match"
    SHOTS_AGAINST_PER_MATCH = "shots_against_per_match"
    SHOTS_ON_TARGET_FOR_PER_MATCH = "shots_on_target_for_per_match"
    SHOTS_ON_TARGET_AGAINST_PER_MATCH = "shots_on_target_against_per_match"
    POSSESSION_FOR_MEAN = "possession_for_mean"
    YELLOWS_FOR_PER_MATCH = "yellows_for_per_match"
    REDS_FOR_PER_MATCH = "reds_for_per_match"
    DAYS_SINCE_LAST_MATCH = "days_since_last_match"
    FIXTURES_LAST_7_DAYS = "fixtures_last_7_days"
    FIXTURES_LAST_14_DAYS = "fixtures_last_14_days"
    FIXTURES_LAST_28_DAYS = "fixtures_last_28_days"


@dataclass(frozen=True)
class HistoricalFeatureDefinition:
    feature_id: HistoricalFeatureId
    family: HistoricalFeatureFamily
    algorithm_id: str
    required_primitives: tuple[str, ...]

    def stable_dict(self) -> dict[str, Any]:
        return {
            "algorithm_id": self.algorithm_id,
            "family": self.family.value,
            "feature_id": self.feature_id.value,
            "required_primitives": list(self.required_primitives),
            "value_type": "FINITE_NUMBER",
        }


def _definition(
    feature_id: HistoricalFeatureId,
    family: HistoricalFeatureFamily,
    required: Sequence[str],
) -> HistoricalFeatureDefinition:
    return HistoricalFeatureDefinition(
        feature_id,
        family,
        f"{feature_id.value.upper()}_V1",
        tuple(required),
    )


HISTORICAL_FEATURE_REGISTRY: tuple[HistoricalFeatureDefinition, ...] = (
    *(_definition(fid, HistoricalFeatureFamily.FORM_RESULTS, ("goals_for", "goals_against")) for fid in (
        HistoricalFeatureId.POINTS_PER_MATCH, HistoricalFeatureId.WIN_RATE,
        HistoricalFeatureId.DRAW_RATE, HistoricalFeatureId.LOSS_RATE,
        HistoricalFeatureId.GOAL_DIFFERENCE_PER_MATCH,
    )),
    _definition(HistoricalFeatureId.GOALS_FOR_PER_MATCH, HistoricalFeatureFamily.FORM_RESULTS, ("goals_for",)),
    _definition(HistoricalFeatureId.GOALS_AGAINST_PER_MATCH, HistoricalFeatureFamily.FORM_RESULTS, ("goals_against",)),
    *(_definition(fid, HistoricalFeatureFamily.EVENT_ENVIRONMENT, ("goals_for", "goals_against")) for fid in (
        HistoricalFeatureId.TOTAL_GOALS_PER_MATCH,
        HistoricalFeatureId.BTTS_RATE,
        HistoricalFeatureId.OVER_1_5_RATE,
        HistoricalFeatureId.OVER_2_5_RATE,
    )),
    _definition(HistoricalFeatureId.CLEAN_SHEET_RATE, HistoricalFeatureFamily.EVENT_ENVIRONMENT, ("goals_against",)),
    _definition(HistoricalFeatureId.FAILED_TO_SCORE_RATE, HistoricalFeatureFamily.EVENT_ENVIRONMENT, ("goals_for",)),
    _definition(HistoricalFeatureId.FIRST_HALF_GOALS_FOR_PER_MATCH, HistoricalFeatureFamily.HALF_TIME, ("first_half_goals_for",)),
    _definition(HistoricalFeatureId.FIRST_HALF_GOALS_AGAINST_PER_MATCH, HistoricalFeatureFamily.HALF_TIME, ("first_half_goals_against",)),
    _definition(HistoricalFeatureId.FIRST_HALF_TOTAL_GOALS_PER_MATCH, HistoricalFeatureFamily.HALF_TIME, ("first_half_goals_for", "first_half_goals_against")),
    _definition(HistoricalFeatureId.XG_FOR_PER_MATCH, HistoricalFeatureFamily.EXPECTED_GOALS, ("xg_for",)),
    _definition(HistoricalFeatureId.XG_AGAINST_PER_MATCH, HistoricalFeatureFamily.EXPECTED_GOALS, ("xg_against",)),
    _definition(HistoricalFeatureId.XG_TOTAL_PER_MATCH, HistoricalFeatureFamily.EXPECTED_GOALS, ("xg_for", "xg_against")),
    _definition(HistoricalFeatureId.SHOTS_FOR_PER_MATCH, HistoricalFeatureFamily.SHOTS, ("shots_for",)),
    _definition(HistoricalFeatureId.SHOTS_AGAINST_PER_MATCH, HistoricalFeatureFamily.SHOTS, ("shots_against",)),
    _definition(HistoricalFeatureId.SHOTS_ON_TARGET_FOR_PER_MATCH, HistoricalFeatureFamily.SHOTS, ("shots_on_target_for",)),
    _definition(HistoricalFeatureId.SHOTS_ON_TARGET_AGAINST_PER_MATCH, HistoricalFeatureFamily.SHOTS, ("shots_on_target_against",)),
    _definition(HistoricalFeatureId.POSSESSION_FOR_MEAN, HistoricalFeatureFamily.POSSESSION, ("possession_for",)),
    _definition(HistoricalFeatureId.YELLOWS_FOR_PER_MATCH, HistoricalFeatureFamily.DISCIPLINE, ("yellows_for",)),
    _definition(HistoricalFeatureId.REDS_FOR_PER_MATCH, HistoricalFeatureFamily.DISCIPLINE, ("reds_for",)),
    _definition(HistoricalFeatureId.DAYS_SINCE_LAST_MATCH, HistoricalFeatureFamily.SCHEDULE, ("prior_match_date",)),
    _definition(HistoricalFeatureId.FIXTURES_LAST_7_DAYS, HistoricalFeatureFamily.SCHEDULE, ("prior_match_date",)),
    _definition(HistoricalFeatureId.FIXTURES_LAST_14_DAYS, HistoricalFeatureFamily.SCHEDULE, ("prior_match_date",)),
    _definition(HistoricalFeatureId.FIXTURES_LAST_28_DAYS, HistoricalFeatureFamily.SCHEDULE, ("prior_match_date",)),
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def calculate_historical_generation_contract_sha256(
    version: int,
    *,
    temporal_policy_id: str = TEMPORAL_POLICY_ID,
    team_identity_policy_id: str = HISTORICAL_TEAM_IDENTITY_POLICY_ID,
    completion_policy_id: str = HISTORICAL_COMPLETION_POLICY_ID,
    advanced_period_safety_policy_id: str = HISTORICAL_ADVANCED_PERIOD_SAFETY_POLICY_ID,
    generation_schema_version: int = HISTORICAL_ASOF_SCHEMA_VERSION,
) -> str:
    payload = {
        "advanced_period_safety_policy_id": advanced_period_safety_policy_id,
        "completion_policy_id": completion_policy_id,
        "generation_schema_version": generation_schema_version,
        "team_identity_policy_id": team_identity_policy_id,
        "temporal_policy_id": temporal_policy_id,
        "version": version,
    }
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


# Independently reviewed pins. Never derive this mapping from the live policies.
EXPECTED_HISTORICAL_GENERATION_CONTRACT_SHA256_BY_VERSION: Mapping[int, str] = (
    MappingProxyType({1: "82c23162aeef7b49a2205c2476f29ff97073b56a3519d6b8b1b7138925d41b3a"})
)


def validate_historical_generation_contract(
    version: int = HISTORICAL_GENERATION_CONTRACT_VERSION,
    expected_by_version: Mapping[int, str] = (
        EXPECTED_HISTORICAL_GENERATION_CONTRACT_SHA256_BY_VERSION
    ),
    **policy_overrides: Any,
) -> str:
    expected = expected_by_version.get(version)
    if expected is None:
        raise HistoricalAsOfError(
            f"unreviewed historical generation contract version: {version}"
        )
    actual = calculate_historical_generation_contract_sha256(
        version, **policy_overrides
    )
    if actual != expected:
        raise HistoricalAsOfError(
            f"historical generation contract drift for version {version}: "
            f"{actual} != {expected}"
        )
    return actual


def calculate_historical_feature_registry_sha256(
    registry: Sequence[HistoricalFeatureDefinition], version: int,
) -> str:
    payload = {
        "registry": [item.stable_dict() for item in registry],
        "version": version,
        "windows": {key.value: value for key, value in WINDOW_SIZES.items()},
    }
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


# Independently reviewed pins. Never derive this mapping from the live registry.
EXPECTED_HISTORICAL_FEATURE_REGISTRY_SHA256_BY_VERSION: Mapping[int, str] = MappingProxyType(
    {1: "2d1606e54463ee75f984973173af4ba4ba68fe0acc4d0be4e2525b08f5c863f8"}
)


def validate_historical_feature_registry(
    registry: Sequence[HistoricalFeatureDefinition] = HISTORICAL_FEATURE_REGISTRY,
    version: int = HISTORICAL_FEATURE_REGISTRY_VERSION,
    expected_by_version: Mapping[int, str] = EXPECTED_HISTORICAL_FEATURE_REGISTRY_SHA256_BY_VERSION,
) -> str:
    expected = expected_by_version.get(version)
    if expected is None:
        raise HistoricalAsOfError(f"unreviewed historical feature registry version: {version}")
    actual = calculate_historical_feature_registry_sha256(registry, version)
    if actual != expected:
        raise HistoricalAsOfError(
            f"historical feature registry drift for version {version}: {actual} != {expected}"
        )
    return actual


_DEFINITION_BY_ID = MappingProxyType({item.feature_id: item for item in HISTORICAL_FEATURE_REGISTRY})


_BOUND_MATCH_TOKEN = object()
_PROJECTION_TOKEN = object()
_TARGET_TOKEN = object()


@dataclass(frozen=True, init=False)
class _SourceBoundWarehouseMatch:
    source_warehouse_sha256: str
    row_items: tuple[tuple[str, Any], ...]
    row_sha256: str
    _source_instance_token: object

    def __init__(
        self, *, _token: object | None = None,
        source_warehouse_sha256: str, row_items: Sequence[tuple[str, Any]],
        _source_instance_token: object,
    ) -> None:
        if _token is not _BOUND_MATCH_TOKEN:
            raise HistoricalAsOfError("warehouse match rows are source-builder-only")
        frozen_items = tuple(sorted((str(key), value) for key, value in row_items))
        identity = {
            "row": [[key, value] for key, value in frozen_items],
            "source_warehouse_sha256": source_warehouse_sha256,
        }
        try:
            row_sha256 = hashlib.sha256(_canonical_bytes(identity)).hexdigest()
        except (TypeError, ValueError) as exc:
            raise HistoricalAsOfError("invalid numeric warehouse value in source row") from exc
        object.__setattr__(self, "source_warehouse_sha256", source_warehouse_sha256)
        object.__setattr__(self, "row_items", frozen_items)
        object.__setattr__(self, "row_sha256", row_sha256)
        object.__setattr__(self, "_source_instance_token", _source_instance_token)

    def __getitem__(self, key: str) -> Any:
        try:
            return dict(self.row_items)[key]
        except KeyError as exc:
            raise KeyError(key) from exc

    def verify_integrity(self) -> None:
        identity = {
            "row": [[key, value] for key, value in self.row_items],
            "source_warehouse_sha256": self.source_warehouse_sha256,
        }
        if hashlib.sha256(_canonical_bytes(identity)).hexdigest() != self.row_sha256:
            raise HistoricalAsOfError("source-bound warehouse match identity mismatch")


@dataclass(frozen=True, init=False)
class HistoricalAsOfTarget:
    match_key: str
    match_date: str
    competition_key: str | None
    competition_name: str
    scope: str
    season: str | None
    stage: str | None
    round_name: str | None
    hierarchy_rank: int | None
    hierarchy_tier: str | None
    home_team: str
    away_team: str
    source_warehouse_sha256: str
    target_sha256: str
    _source_instance_token: object

    def __init__(self, *, _token: object | None = None, **values: Any) -> None:
        if _token is not _TARGET_TOKEN:
            raise HistoricalAsOfError("historical targets are source-builder-only")
        identity = {
            key: values[key] for key in values
            if key not in {"target_sha256", "_source_instance_token"}
        }
        values["target_sha256"] = hashlib.sha256(_canonical_bytes(identity)).hexdigest()
        for field in fields(type(self)):
            object.__setattr__(self, field.name, values[field.name])

    def verify_integrity(self) -> None:
        identity = {
            field.name: getattr(self, field.name)
            for field in fields(type(self))
            if field.name not in {"target_sha256", "_source_instance_token"}
        }
        if hashlib.sha256(_canonical_bytes(identity)).hexdigest() != self.target_sha256:
            raise HistoricalAsOfError("historical target identity mismatch")


@dataclass(frozen=True, init=False)
class TeamMatchProjection:
    source_warehouse_sha256: str
    match_key: str
    match_date: str
    competition_key: str | None
    scope: str
    season: str | None
    team: str
    opponent: str
    side: str
    goals_for: int | None
    goals_against: int | None
    first_half_goals_for: int | None
    first_half_goals_against: int | None
    xg_for: float | None
    xg_against: float | None
    shots_for: int | None
    shots_against: int | None
    shots_on_target_for: int | None
    shots_on_target_against: int | None
    possession_for: float | None
    possession_against: float | None
    corners_for: int | None
    corners_against: int | None
    fouls_for: int | None
    fouls_against: int | None
    yellows_for: int | None
    yellows_against: int | None
    reds_for: int | None
    reds_against: int | None
    blocked_primitives: tuple[str, ...]
    field_source_keys: tuple[tuple[str, str], ...]
    conflict_fields: tuple[str, ...]
    projection_sha256: str
    _source_instance_token: object

    def __init__(self, *, _token: object | None = None, **values: Any) -> None:
        if _token is not _PROJECTION_TOKEN:
            raise HistoricalAsOfError("team match projections are source-builder-only")
        identity = {
            key: values[key] for key in values
            if key not in {"projection_sha256", "_source_instance_token"}
        }
        identity["field_source_keys"] = [list(item) for item in values["field_source_keys"]]
        identity["conflict_fields"] = list(values["conflict_fields"])
        identity["blocked_primitives"] = list(values["blocked_primitives"])
        values["projection_sha256"] = hashlib.sha256(_canonical_bytes(identity)).hexdigest()
        for field in fields(type(self)):
            object.__setattr__(self, field.name, values[field.name])

    def verify_integrity(self) -> None:
        identity = {
            field.name: getattr(self, field.name)
            for field in fields(type(self))
            if field.name not in {"projection_sha256", "_source_instance_token"}
        }
        identity["field_source_keys"] = [list(item) for item in self.field_source_keys]
        identity["conflict_fields"] = list(self.conflict_fields)
        identity["blocked_primitives"] = list(self.blocked_primitives)
        if hashlib.sha256(_canonical_bytes(identity)).hexdigest() != self.projection_sha256:
            raise HistoricalAsOfError("team match projection identity mismatch")

    def to_dict(self) -> dict[str, Any]:
        return {
            field.name: getattr(self, field.name)
            for field in fields(self) if field.name != "_source_instance_token"
        } | {
            "field_source_keys": [list(item) for item in self.field_source_keys],
            "conflict_fields": list(self.conflict_fields),
            "blocked_primitives": list(self.blocked_primitives),
        }


@dataclass(frozen=True)
class HistoricalFeatureResolution:
    feature_id: HistoricalFeatureId
    scope: HistoricalTeamScope
    window: HistoricalWindow
    status: HistoricalFeatureStatus
    value: float | int | None
    blocker: HistoricalFeatureBlocker | None
    requested_window_size: int | None
    effective_match_sample: int
    valid_field_sample: int
    missing_field_count: int
    blocked_field_sample: int
    oldest_included_date: str | None
    newest_included_date: str | None
    algorithm_id: str
    required_primitives: tuple[str, ...]
    contributing_projection_sha256: str | None
    contributing_match_keys: tuple[str, ...]
    blocked_projection_sha256: str | None
    blocked_match_keys: tuple[str, ...]
    blocked_source_field_provenance: tuple[tuple[str, str, str], ...]
    blocked_reasons: tuple[str, ...]
    source_keys: tuple[str, ...]
    source_field_provenance: tuple[tuple[str, str, str], ...]
    conflict_count: int

    def __post_init__(self) -> None:
        if self.status is HistoricalFeatureStatus.AVAILABLE:
            if self.value is None or not isinstance(self.value, (int, float)) or isinstance(self.value, bool):
                raise HistoricalAsOfError("AVAILABLE historical feature requires a number")
            if not math.isfinite(float(self.value)):
                raise HistoricalAsOfError("historical feature values must be finite")
            if self.contributing_projection_sha256 is None:
                raise HistoricalAsOfError("AVAILABLE historical feature requires contributing history")
        elif self.value is not None:
            raise HistoricalAsOfError("MISSING/BLOCKED historical feature cannot retain a value")
        if self.status is HistoricalFeatureStatus.BLOCKED and self.blocker is None:
            raise HistoricalAsOfError("BLOCKED historical feature requires a blocker")
        if self.status is not HistoricalFeatureStatus.BLOCKED and self.blocker is not None:
            raise HistoricalAsOfError("only BLOCKED historical features may retain a blocker")
        if self.effective_match_sample != (
            self.valid_field_sample + self.missing_field_count + self.blocked_field_sample
        ):
            raise HistoricalAsOfError("historical feature sample counts do not reconcile")
        if self.blocked_field_sample != len(self.blocked_match_keys):
            raise HistoricalAsOfError("blocked historical observation counts do not reconcile")
        if self.blocked_field_sample and (
            self.blocked_projection_sha256 is None or not self.blocked_reasons
        ):
            raise HistoricalAsOfError("blocked observations require deterministic evidence")
        if not self.blocked_field_sample and (
            self.blocked_projection_sha256 is not None
            or self.blocked_match_keys
            or self.blocked_source_field_provenance
            or self.blocked_reasons
        ):
            raise HistoricalAsOfError("unblocked observations cannot retain blocked evidence")

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm_id": self.algorithm_id,
            "blocker": self.blocker.value if self.blocker else None,
            "blocked_field_sample": self.blocked_field_sample,
            "blocked_match_keys": list(self.blocked_match_keys),
            "blocked_projection_sha256": self.blocked_projection_sha256,
            "blocked_reasons": list(self.blocked_reasons),
            "blocked_source_field_provenance": [
                list(item) for item in self.blocked_source_field_provenance
            ],
            "conflict_count": self.conflict_count,
            "contributing_projection_sha256": self.contributing_projection_sha256,
            "contributing_match_keys": list(self.contributing_match_keys),
            "effective_match_sample": self.effective_match_sample,
            "feature_id": self.feature_id.value,
            "missing_field_count": self.missing_field_count,
            "newest_included_date": self.newest_included_date,
            "oldest_included_date": self.oldest_included_date,
            "requested_window_size": self.requested_window_size,
            "required_primitives": list(self.required_primitives),
            "scope": self.scope.value,
            "source_keys": list(self.source_keys),
            "source_field_provenance": [list(item) for item in self.source_field_provenance],
            "status": self.status.value,
            "valid_field_sample": self.valid_field_sample,
            "value": self.value,
            "window": self.window.value,
        }


@dataclass(frozen=True)
class HistoricalCoverage:
    total: int
    available: int
    missing: int
    blocked: int

    def to_dict(self) -> dict[str, int]:
        return {"available": self.available, "blocked": self.blocked, "missing": self.missing, "total": self.total}


AUTHORITY_FLAGS: Mapping[str, bool] = MappingProxyType({
    key: False for key in (
        "acquisition_authority", "provider_authority", "probability_inference_authority",
        "probability_adjustment_authority", "model_training_approval",
        "model_promotion_authority", "calibration_authority", "bookmaker_pricing_authority",
        "market_activation_authority", "router_authority", "market_selection_authority",
        "accumulator_authority", "production_approval_authority", "bet_authority",
    )
})


_SNAPSHOT_TOKEN = object()


@dataclass(frozen=True, init=False)
class HistoricalAsOfFixtureSnapshot:
    target_match_key: str
    target_match_date: str
    target_competition_key: str | None
    target_competition_name: str
    target_scope: str
    target_season: str | None
    target_stage: str | None
    target_round_name: str | None
    target_hierarchy_rank: int | None
    target_hierarchy_tier: str | None
    target_home_team: str
    target_away_team: str
    temporal_policy_id: str
    team_identity_policy_id: str
    completion_policy_id: str
    advanced_period_safety_policy_id: str
    source_warehouse_sha256: str
    source_warehouse_schema_version: str
    source_schema_sql_sha256: str
    generation_schema_version: int
    generation_contract_version: int
    generation_contract_sha256: str
    feature_registry_version: int
    feature_registry_sha256: str
    home_resolutions: tuple[HistoricalFeatureResolution, ...]
    away_resolutions: tuple[HistoricalFeatureResolution, ...]
    coverage: HistoricalCoverage
    authority_flags: tuple[tuple[str, bool], ...]

    def __init__(self, *, _token: object | None = None, **values: Any) -> None:
        if _token is not _SNAPSHOT_TOKEN:
            raise HistoricalAsOfError("canonical historical snapshots are builder-only")
        for field in fields(type(self)):
            object.__setattr__(self, field.name, values[field.name])

    def to_dict(self) -> dict[str, Any]:
        return {
            "authority_flags": dict(self.authority_flags),
            "coverage": self.coverage.to_dict(),
            "dataset": HISTORICAL_ASOF_DATASET,
            "feature_registry_sha256": self.feature_registry_sha256,
            "feature_registry_version": self.feature_registry_version,
            "generation_contract_sha256": self.generation_contract_sha256,
            "generation_contract_version": self.generation_contract_version,
            "generation_schema_version": self.generation_schema_version,
            "home_resolutions": [item.to_dict() for item in self.home_resolutions],
            "away_resolutions": [item.to_dict() for item in self.away_resolutions],
            "source_schema_sql_sha256": self.source_schema_sql_sha256,
            "source_warehouse_schema_version": self.source_warehouse_schema_version,
            "source_warehouse_sha256": self.source_warehouse_sha256,
            "target": {
                "away_team": self.target_away_team,
                "competition_key": self.target_competition_key,
                "competition_name": self.target_competition_name,
                "home_team": self.target_home_team,
                "hierarchy_rank": self.target_hierarchy_rank,
                "hierarchy_tier": self.target_hierarchy_tier,
                "match_date": self.target_match_date,
                "match_key": self.target_match_key,
                "round_name": self.target_round_name,
                "scope": self.target_scope,
                "season": self.target_season,
                "stage": self.target_stage,
            },
            "temporal_policy_id": self.temporal_policy_id,
            "team_identity_policy_id": self.team_identity_policy_id,
            "completion_policy_id": self.completion_policy_id,
            "advanced_period_safety_policy_id": self.advanced_period_safety_policy_id,
        }

    @property
    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


REQUIRED_WAREHOUSE_OBJECTS = frozenset({
    "warehouse_meta", "warehouse_sources", "warehouse_matches", "warehouse_match_flat",
    "warehouse_events", "warehouse_events_preferred", "warehouse_lineups",
    "warehouse_coaches", "warehouse_officials", "warehouse_field_provenance",
    "warehouse_match_sources", "warehouse_conflicts", "warehouse_penalty_shootouts",
})


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_warehouse_schema_sql(
    schema_version: str,
    schema_path: Path | None = None,
    expected_by_version: Mapping[str, str] = EXPECTED_WAREHOUSE_SCHEMA_SQL_SHA256_BY_VERSION,
) -> str:
    """Validate canonical schema SQL against an independent versioned pin."""
    expected = expected_by_version.get(schema_version)
    if expected is None:
        raise HistoricalAsOfError(
            f"unreviewed historical warehouse schema SQL version: {schema_version}"
        )
    path = CANONICAL_WAREHOUSE_SCHEMA_SQL if schema_path is None else Path(schema_path)
    if not path.is_file():
        raise HistoricalAsOfError("historical warehouse schema SQL is unavailable")
    actual = file_sha256(path)
    if actual != expected:
        raise HistoricalAsOfError(
            f"historical warehouse schema SQL drift for version {schema_version}: "
            f"{actual} != {expected}"
        )
    return actual


_SOURCE_BOUND_MATCH_SELECT = """
SELECT m.*,
  (SELECT group_concat(pair, char(30)) FROM (
     SELECT p.field_name || char(31) || p.source_key AS pair
     FROM warehouse_field_provenance p
     WHERE p.match_key=m.match_key ORDER BY p.field_name,p.source_key
  )) AS provenance_pairs,
  (SELECT group_concat(field_name, char(30)) FROM (
     SELECT DISTINCT c.field_name AS field_name FROM warehouse_conflicts c
     WHERE c.match_key=m.match_key ORDER BY c.field_name
  )) AS conflict_fields,
  EXISTS(
    SELECT 1 FROM warehouse_events e
    WHERE e.match_key=m.match_key
      AND e.source_key='statsbomb_open'
      AND e.period IN ('3','4')
  ) AS has_reviewed_extra_time_event,
  EXISTS(
    SELECT 1 FROM warehouse_penalty_shootouts p
    WHERE p.match_key=m.match_key
  ) AS has_penalty_shootout_evidence
FROM warehouse_match_flat m
"""


class ReadOnlyHistoricalWarehouse:
    """Stable, SHA-bound, query-only view of one warehouse image."""

    def __init__(self, path: Path) -> None:
        self._source_instance_token = object()
        self.path = Path(path).resolve()
        if not self.path.is_file():
            raise HistoricalAsOfError(f"historical warehouse does not exist: {self.path}")
        self._assert_no_active_companions()
        self._before_stat = self.path.stat()
        self.sha256 = file_sha256(self.path)
        self._assert_no_active_companions()
        self.connection = sqlite3.connect(f"{self.path.as_uri()}?mode=ro", uri=True)
        try:
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA query_only = ON")
            self._assert_no_active_companions()
            self._validate_schema()
            self.schema_sql_sha256 = validate_warehouse_schema_sql(self.schema_version)
            self._assert_no_active_companions()
        except Exception:
            self.close()
            raise

    def _assert_no_active_companions(self) -> None:
        for suffix in ("-wal", "-journal"):
            companion = Path(str(self.path) + suffix)
            if companion.exists() and companion.stat().st_size:
                raise HistoricalAsOfError(
                    f"unsafe active SQLite companion file: {companion.name}"
                )

    def _validate_schema(self) -> None:
        objects = {row[0] for row in self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
        )}
        missing = sorted(REQUIRED_WAREHOUSE_OBJECTS - objects)
        if missing:
            self.close()
            raise HistoricalAsOfError(f"historical warehouse missing objects: {missing}")
        row = self.connection.execute(
            "SELECT value FROM warehouse_meta WHERE key='schema_version'"
        ).fetchone()
        if row is None or row[0] != WAREHOUSE_SCHEMA_VERSION:
            self.close()
            raise HistoricalAsOfError("historical warehouse schema version mismatch")
        self.schema_version = row[0]

    def assert_unchanged(self) -> None:
        self._assert_no_active_companions()
        after = self.path.stat()
        if (after.st_size, after.st_mtime_ns) != (self._before_stat.st_size, self._before_stat.st_mtime_ns):
            raise HistoricalAsOfError("historical warehouse changed during construction")
        if file_sha256(self.path) != self.sha256:
            raise HistoricalAsOfError("historical warehouse bytes changed during construction")
        self._assert_no_active_companions()

    def _bound_matches(
        self, where_sql: str = "", parameters: Sequence[Any] = (),
        order_sql: str = "",
    ) -> tuple[_SourceBoundWarehouseMatch, ...]:
        query = _SOURCE_BOUND_MATCH_SELECT
        if where_sql:
            query += " WHERE " + where_sql
        if order_sql:
            query += " ORDER BY " + order_sql
        return tuple(
            _SourceBoundWarehouseMatch(
                _token=_BOUND_MATCH_TOKEN,
                source_warehouse_sha256=self.sha256,
                row_items=tuple((key, row[key]) for key in row.keys()),
                _source_instance_token=self._source_instance_token,
            )
            for row in self.connection.execute(query, tuple(parameters))
        )

    def target_match(self, match_key: str) -> _SourceBoundWarehouseMatch:
        matches = self._bound_matches("m.match_key=?", (match_key,))
        if len(matches) != 1:
            raise HistoricalAsOfError(f"unknown target match_key: {match_key}")
        return matches[0]

    def historical_matches(
        self, scope: str, competition_key: str, team: str, target_date: str,
    ) -> tuple[_SourceBoundWarehouseMatch, ...]:
        return self._bound_matches(
            "m.match_date < ? AND m.scope=? AND m.competition_key=? "
            "AND (m.home_team=? OR m.away_team=?)",
            (target_date, scope, competition_key, team, team),
            "m.match_date,m.match_key",
        )

    def stream_matches(self) -> Iterable[_SourceBoundWarehouseMatch]:
        query = _SOURCE_BOUND_MATCH_SELECT + " ORDER BY m.match_date,m.match_key"
        for row in self.connection.execute(query):
            yield _SourceBoundWarehouseMatch(
                _token=_BOUND_MATCH_TOKEN,
                source_warehouse_sha256=self.sha256,
                row_items=tuple((key, row[key]) for key in row.keys()),
                _source_instance_token=self._source_instance_token,
            )

    def close(self) -> None:
        connection = getattr(self, "connection", None)
        if connection is not None:
            connection.close()
            self.connection = None

    def __enter__(self) -> "ReadOnlyHistoricalWarehouse":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()


def _parse_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise HistoricalAsOfError(f"invalid warehouse match_date: {value!r}") from exc
    if parsed.isoformat() != value:
        raise HistoricalAsOfError(f"noncanonical warehouse match_date: {value!r}")
    return parsed


_NUMERIC_COLUMNS = {
    "home_score_ft", "away_score_ft", "home_score_ht", "away_score_ht", "home_xg", "away_xg",
    "home_possession", "away_possession", "home_shots", "away_shots", "home_shots_on_target",
    "away_shots_on_target", "home_corners", "away_corners", "home_fouls", "away_fouls",
    "home_yellows", "away_yellows", "home_reds", "away_reds",
}


def _safe_number(value: Any, field_name: str) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise HistoricalAsOfError(f"invalid numeric warehouse value for {field_name}")
    if field_name in _NUMERIC_COLUMNS - {"home_xg", "away_xg", "home_possession", "away_possession"}:
        if not isinstance(value, int) or value < 0:
            raise HistoricalAsOfError(f"invalid count warehouse value for {field_name}")
    if field_name in {"home_xg", "away_xg"} and float(value) < 0:
        raise HistoricalAsOfError(f"invalid negative xG warehouse value for {field_name}")
    return value


def qualifies_completed_prior_fixture(
    row: Mapping[str, Any] | sqlite3.Row | _SourceBoundWarehouseMatch,
) -> bool:
    """Return true only for mechanically completed regulation-score rows."""
    scores = (row["home_score_ft"], row["away_score_ft"])
    if any(value is None for value in scores):
        return False
    for field_name, value in zip(("home_score_ft", "away_score_ft"), scores):
        _safe_number(value, field_name)
    return True


_PERIOD_UNQUALIFIED_ADVANCED_PRIMITIVES = frozenset({
    "xg_for", "xg_against", "shots_for", "shots_against",
    "shots_on_target_for", "shots_on_target_against",
    "possession_for", "possession_against", "corners_for", "corners_against",
    "fouls_for", "fouls_against", "yellows_for", "yellows_against",
    "reds_for", "reds_against",
})


def _has_extra_period_evidence(
    row: Mapping[str, Any] | sqlite3.Row | _SourceBoundWarehouseMatch,
) -> bool:
    return any(
        row[field_name] is not None
        for field_name in (
            "home_score_et", "away_score_et", "home_score_pen", "away_score_pen",
        )
    ) or bool(row["has_reviewed_extra_time_event"]) or bool(
        row["has_penalty_shootout_evidence"]
    )


def _decode_pairs(value: str | None) -> tuple[tuple[str, str], ...]:
    if not value:
        return ()
    pairs = []
    for entry in value.split("\x1e"):
        field_name, source_key = entry.split("\x1f", 1)
        pairs.append((field_name, source_key))
    return tuple(sorted(set(pairs)))


def _decode_fields(value: str | None) -> tuple[str, ...]:
    return tuple(sorted(set(value.split("\x1e")))) if value else ()


def _projection(
    row: _SourceBoundWarehouseMatch, team: str,
) -> TeamMatchProjection:
    if not isinstance(row, _SourceBoundWarehouseMatch):
        raise HistoricalAsOfError("team projections require a source-bound warehouse row")
    row.verify_integrity()
    provenance = dict(_decode_pairs(row["provenance_pairs"]))
    conflicts = _decode_fields(row["conflict_fields"])
    home = team == row["home_team"]
    if not home and team != row["away_team"]:
        raise HistoricalAsOfError("team is not present in prior match")
    side, other = ("home", "away") if home else ("away", "home")
    extra_period_evidence = _has_extra_period_evidence(row)
    advanced_fields = {
        "xg_for": f"{side}_xg", "xg_against": f"{other}_xg",
        "shots_for": f"{side}_shots", "shots_against": f"{other}_shots",
        "shots_on_target_for": f"{side}_shots_on_target",
        "shots_on_target_against": f"{other}_shots_on_target",
        "possession_for": f"{side}_possession", "possession_against": f"{other}_possession",
        "corners_for": f"{side}_corners", "corners_against": f"{other}_corners",
        "fouls_for": f"{side}_fouls", "fouls_against": f"{other}_fouls",
        "yellows_for": f"{side}_yellows", "yellows_against": f"{other}_yellows",
        "reds_for": f"{side}_reds", "reds_against": f"{other}_reds",
    }
    if frozenset(advanced_fields) != _PERIOD_UNQUALIFIED_ADVANCED_PRIMITIVES:
        raise HistoricalAsOfError("advanced period-safety registry drift")
    blocked_primitives = frozenset(
        primitive for primitive, field_name in advanced_fields.items()
        if extra_period_evidence and row[field_name] is not None
    )

    def advanced(primitive: str, field_name: str) -> int | float | None:
        if primitive in blocked_primitives:
            return None
        return _safe_number(row[field_name], field_name)

    values: dict[str, Any] = {
        "source_warehouse_sha256": row.source_warehouse_sha256,
        "_source_instance_token": row._source_instance_token,
        "match_key": row["match_key"], "match_date": row["match_date"],
        "competition_key": row["competition_key"], "scope": row["scope"], "season": row["season"],
        "team": team, "opponent": row[f"{other}_team"], "side": side.upper(),
        "goals_for": _safe_number(row[f"{side}_score_ft"], f"{side}_score_ft"),
        "goals_against": _safe_number(row[f"{other}_score_ft"], f"{other}_score_ft"),
        "first_half_goals_for": _safe_number(row[f"{side}_score_ht"], f"{side}_score_ht"),
        "first_half_goals_against": _safe_number(row[f"{other}_score_ht"], f"{other}_score_ht"),
        "xg_for": advanced("xg_for", f"{side}_xg"),
        "xg_against": advanced("xg_against", f"{other}_xg"),
        "shots_for": advanced("shots_for", f"{side}_shots"),
        "shots_against": advanced("shots_against", f"{other}_shots"),
        "shots_on_target_for": advanced("shots_on_target_for", f"{side}_shots_on_target"),
        "shots_on_target_against": advanced("shots_on_target_against", f"{other}_shots_on_target"),
        "possession_for": advanced("possession_for", f"{side}_possession"),
        "possession_against": advanced("possession_against", f"{other}_possession"),
        "corners_for": advanced("corners_for", f"{side}_corners"),
        "corners_against": advanced("corners_against", f"{other}_corners"),
        "fouls_for": advanced("fouls_for", f"{side}_fouls"),
        "fouls_against": advanced("fouls_against", f"{other}_fouls"),
        "yellows_for": advanced("yellows_for", f"{side}_yellows"),
        "yellows_against": advanced("yellows_against", f"{other}_yellows"),
        "reds_for": advanced("reds_for", f"{side}_reds"),
        "reds_against": advanced("reds_against", f"{other}_reds"),
        "blocked_primitives": tuple(sorted(blocked_primitives)),
        "field_source_keys": tuple(sorted(provenance.items())),
        "conflict_fields": tuple(sorted(set(conflicts))),
    }
    return TeamMatchProjection(_token=_PROJECTION_TOKEN, **values)


def historical_team_identity(
    scope: Any, competition_key: Any, canonical_team: Any,
) -> tuple[str, str, str] | None:
    """Return the reviewed narrow identity, or None when it is unusable."""
    if not all(isinstance(value, str) and value and value == value.strip() for value in (
        scope, competition_key, canonical_team,
    )):
        return None
    return scope, competition_key, canonical_team


def _history(
    source: ReadOnlyHistoricalWarehouse,
    scope: Any,
    competition_key: Any,
    team: Any,
    target_date: str,
) -> tuple[TeamMatchProjection, ...]:
    identity = historical_team_identity(scope, competition_key, team)
    if identity is None:
        return ()
    rows = source.historical_matches(
        identity[0], identity[1], identity[2], target_date
    )
    rows = [row for row in rows if qualifies_completed_prior_fixture(row)]
    if not rows:
        return ()
    return tuple(_projection(row, identity[2]) for row in rows)


def complete_boundary_window(history: Sequence[TeamMatchProjection], requested: int) -> tuple[TeamMatchProjection, ...]:
    """Select recent complete date buckets until at least ``requested`` matches."""
    if requested < 1:
        raise HistoricalAsOfError("requested window must be positive")
    selected: list[TeamMatchProjection] = []
    by_date: dict[str, list[TeamMatchProjection]] = {}
    for item in history:
        by_date.setdefault(item.match_date, []).append(item)
    for match_date in sorted(by_date, reverse=True):
        selected.extend(sorted(by_date[match_date], key=lambda item: item.match_key))
        if len(selected) >= requested:
            break
    return tuple(sorted(selected, key=lambda item: (item.match_date, item.match_key)))


def _warehouse_field_for(item: TeamMatchProjection, primitive: str) -> str | None:
    side, other = ("home", "away") if item.side == "HOME" else ("away", "home")
    templates = {
        "goals_for": f"{side}_score_ft", "goals_against": f"{other}_score_ft",
        "first_half_goals_for": f"{side}_score_ht", "first_half_goals_against": f"{other}_score_ht",
        "xg_for": f"{side}_xg", "xg_against": f"{other}_xg",
        "shots_for": f"{side}_shots", "shots_against": f"{other}_shots",
        "shots_on_target_for": f"{side}_shots_on_target",
        "shots_on_target_against": f"{other}_shots_on_target",
        "possession_for": f"{side}_possession", "possession_against": f"{other}_possession",
        "corners_for": f"{side}_corners", "corners_against": f"{other}_corners",
        "fouls_for": f"{side}_fouls", "fouls_against": f"{other}_fouls",
        "yellows_for": f"{side}_yellows", "yellows_against": f"{other}_yellows",
        "reds_for": f"{side}_reds", "reds_against": f"{other}_reds",
        "prior_match_date": "match_date",
    }
    return templates.get(primitive)


def _relevant_provenance(
    history: Sequence[TeamMatchProjection], primitives: Sequence[str],
) -> tuple[tuple[str, str, str], ...]:
    result = []
    for item in history:
        available = dict(item.field_source_keys)
        for primitive in primitives:
            field_name = _warehouse_field_for(item, primitive)
            if field_name is not None and field_name in available:
                result.append((item.match_key, field_name, available[field_name]))
    return tuple(sorted(set(result)))


def _metric_value(feature_id: HistoricalFeatureId, item: TeamMatchProjection) -> float:
    gf, ga = item.goals_for, item.goals_against
    if feature_id is HistoricalFeatureId.POINTS_PER_MATCH:
        return 3.0 if gf > ga else 1.0 if gf == ga else 0.0
    if feature_id is HistoricalFeatureId.WIN_RATE: return float(gf > ga)
    if feature_id is HistoricalFeatureId.DRAW_RATE: return float(gf == ga)
    if feature_id is HistoricalFeatureId.LOSS_RATE: return float(gf < ga)
    if feature_id is HistoricalFeatureId.GOALS_FOR_PER_MATCH: return float(gf)
    if feature_id is HistoricalFeatureId.GOALS_AGAINST_PER_MATCH: return float(ga)
    if feature_id is HistoricalFeatureId.GOAL_DIFFERENCE_PER_MATCH: return float(gf - ga)
    if feature_id is HistoricalFeatureId.TOTAL_GOALS_PER_MATCH: return float(gf + ga)
    if feature_id is HistoricalFeatureId.CLEAN_SHEET_RATE: return float(ga == 0)
    if feature_id is HistoricalFeatureId.FAILED_TO_SCORE_RATE: return float(gf == 0)
    if feature_id is HistoricalFeatureId.BTTS_RATE: return float(gf > 0 and ga > 0)
    if feature_id is HistoricalFeatureId.OVER_1_5_RATE: return float(gf + ga > 1)
    if feature_id is HistoricalFeatureId.OVER_2_5_RATE: return float(gf + ga > 2)
    attributes = {
        HistoricalFeatureId.FIRST_HALF_GOALS_FOR_PER_MATCH: "first_half_goals_for",
        HistoricalFeatureId.FIRST_HALF_GOALS_AGAINST_PER_MATCH: "first_half_goals_against",
        HistoricalFeatureId.XG_FOR_PER_MATCH: "xg_for",
        HistoricalFeatureId.XG_AGAINST_PER_MATCH: "xg_against",
        HistoricalFeatureId.SHOTS_FOR_PER_MATCH: "shots_for",
        HistoricalFeatureId.SHOTS_AGAINST_PER_MATCH: "shots_against",
        HistoricalFeatureId.SHOTS_ON_TARGET_FOR_PER_MATCH: "shots_on_target_for",
        HistoricalFeatureId.SHOTS_ON_TARGET_AGAINST_PER_MATCH: "shots_on_target_against",
        HistoricalFeatureId.POSSESSION_FOR_MEAN: "possession_for",
        HistoricalFeatureId.YELLOWS_FOR_PER_MATCH: "yellows_for",
        HistoricalFeatureId.REDS_FOR_PER_MATCH: "reds_for",
    }
    if feature_id in attributes:
        return float(getattr(item, attributes[feature_id]))
    if feature_id is HistoricalFeatureId.FIRST_HALF_TOTAL_GOALS_PER_MATCH:
        return float(item.first_half_goals_for + item.first_half_goals_against)
    if feature_id is HistoricalFeatureId.XG_TOTAL_PER_MATCH:
        return float(item.xg_for + item.xg_against)
    raise HistoricalAsOfError(f"unsupported historical feature: {feature_id.value}")


def _resolution(
    definition: HistoricalFeatureDefinition, scope: HistoricalTeamScope,
    window: HistoricalWindow, history: Sequence[TeamMatchProjection], target_date: str,
) -> HistoricalFeatureResolution:
    requested = WINDOW_SIZES[window]
    selected = complete_boundary_window(history, requested) if requested else tuple(history)
    blocked = [
        item for item in selected
        if any(primitive in item.blocked_primitives for primitive in definition.required_primitives)
    ]
    valid = [
        item for item in selected
        if item not in blocked
        and all(getattr(item, name) is not None for name in definition.required_primitives)
    ]
    missing = [item for item in selected if item not in blocked and item not in valid]
    dates = [item.match_date for item in selected]
    provenance = _relevant_provenance(valid, definition.required_primitives)
    blocked_provenance = _relevant_provenance(blocked, definition.required_primitives)
    conflict_count = 0
    for item in valid:
        relevant_fields = {
            field_name
            for primitive in definition.required_primitives
            if (field_name := _warehouse_field_for(item, primitive)) is not None
        }
        conflict_count += sum(
            field_name in relevant_fields for field_name in item.conflict_fields
        )
    common = dict(
        feature_id=definition.feature_id, scope=scope, window=window,
        requested_window_size=requested, effective_match_sample=len(selected),
        valid_field_sample=len(valid), missing_field_count=len(missing),
        blocked_field_sample=len(blocked),
        oldest_included_date=min(dates) if dates else None,
        newest_included_date=max(dates) if dates else None,
        algorithm_id=definition.algorithm_id, required_primitives=definition.required_primitives,
        contributing_match_keys=tuple(item.match_key for item in valid),
        blocked_projection_sha256=(
            hashlib.sha256(
                _canonical_bytes([item.projection_sha256 for item in blocked])
            ).hexdigest() if blocked else None
        ),
        blocked_match_keys=tuple(item.match_key for item in blocked),
        blocked_source_field_provenance=blocked_provenance,
        blocked_reasons=(
            (HistoricalFeatureBlocker.UNSAFE_SOURCE_STATE.value,) if blocked else ()
        ),
        source_keys=tuple(sorted({source for _, _, source in provenance})),
        source_field_provenance=provenance,
        conflict_count=conflict_count,
    )
    if not valid:
        if blocked:
            return HistoricalFeatureResolution(
                status=HistoricalFeatureStatus.BLOCKED, value=None,
                blocker=HistoricalFeatureBlocker.UNSAFE_SOURCE_STATE,
                contributing_projection_sha256=None, **common,
            )
        return HistoricalFeatureResolution(
            status=HistoricalFeatureStatus.MISSING, value=None, blocker=None,
            contributing_projection_sha256=None, **common,
        )
    values = [_metric_value(definition.feature_id, item) for item in valid]
    value = sum(values) / len(values)
    projection_sha = hashlib.sha256(_canonical_bytes([item.projection_sha256 for item in valid])).hexdigest()
    return HistoricalFeatureResolution(
        status=HistoricalFeatureStatus.AVAILABLE, value=value, blocker=None,
        contributing_projection_sha256=projection_sha, **common,
    )


def _schedule_resolutions(history: Sequence[TeamMatchProjection], target_date: str) -> tuple[HistoricalFeatureResolution, ...]:
    target = _parse_date(target_date)
    definitions = {item.feature_id: item for item in HISTORICAL_FEATURE_REGISTRY}
    results = []
    latest_date = max((item.match_date for item in history), default=None)
    latest_bucket = tuple(sorted(
        (item for item in history if item.match_date == latest_date),
        key=lambda item: item.match_key,
    )) if latest_date is not None else ()
    for feature_id, days in (
        (HistoricalFeatureId.DAYS_SINCE_LAST_MATCH, None),
        (HistoricalFeatureId.FIXTURES_LAST_7_DAYS, 7),
        (HistoricalFeatureId.FIXTURES_LAST_14_DAYS, 14),
        (HistoricalFeatureId.FIXTURES_LAST_28_DAYS, 28),
    ):
        selected = latest_bucket if days is None else tuple(sorted(
            (
                item for item in history
                if 0 < (target - _parse_date(item.match_date)).days <= days
            ),
            key=lambda item: (item.match_date, item.match_key),
        ))
        definition = definitions[feature_id]
        all_history_exists = bool(history)
        evidence_items = selected or latest_bucket
        provenance = _relevant_provenance(evidence_items, definition.required_primitives) if all_history_exists else ()
        effective = len(selected)
        common = dict(
            feature_id=feature_id, scope=HistoricalTeamScope.OVERALL, window=HistoricalWindow.AS_OF,
            requested_window_size=None, effective_match_sample=effective,
            valid_field_sample=effective if all_history_exists else 0, missing_field_count=0,
            blocked_field_sample=0,
            oldest_included_date=min((x.match_date for x in selected), default=None),
            newest_included_date=max((x.match_date for x in selected), default=None),
            algorithm_id=definition.algorithm_id, required_primitives=definition.required_primitives,
            contributing_match_keys=tuple(item.match_key for item in evidence_items) if all_history_exists else (),
            blocked_projection_sha256=None, blocked_match_keys=(),
            blocked_source_field_provenance=(), blocked_reasons=(),
            source_keys=tuple(sorted({source for _, _, source in provenance})),
            source_field_provenance=provenance,
            conflict_count=sum("match_date" in item.conflict_fields for item in evidence_items),
        )
        if not all_history_exists:
            results.append(HistoricalFeatureResolution(
                status=HistoricalFeatureStatus.MISSING, value=None, blocker=None,
                contributing_projection_sha256=None, **common,
            ))
            continue
        value = (target - _parse_date(latest_date)).days if days is None else effective
        identities = [item.projection_sha256 for item in evidence_items]
        results.append(HistoricalFeatureResolution(
            status=HistoricalFeatureStatus.AVAILABLE, value=value, blocker=None,
            contributing_projection_sha256=hashlib.sha256(_canonical_bytes(identities)).hexdigest(), **common,
        ))
    return tuple(results)


def _team_resolutions(
    history: Sequence[TeamMatchProjection], target_date: str, target_season: str | None,
    venue_scope: HistoricalTeamScope,
) -> tuple[HistoricalFeatureResolution, ...]:
    performance = [item for item in HISTORICAL_FEATURE_REGISTRY if item.family is not HistoricalFeatureFamily.SCHEDULE]
    resolutions: list[HistoricalFeatureResolution] = []
    for scope in (HistoricalTeamScope.OVERALL, venue_scope):
        scoped = tuple(item for item in history if scope is HistoricalTeamScope.OVERALL or item.side == scope.value.removesuffix("_ONLY"))
        for window in (HistoricalWindow.LAST_5, HistoricalWindow.LAST_10, HistoricalWindow.LAST_20, HistoricalWindow.SEASON_TO_DATE):
            if window is HistoricalWindow.SEASON_TO_DATE:
                window_history = tuple(
                    item for item in scoped if _usable_season(target_season) and item.season == target_season
                )
            else:
                window_history = scoped
            resolutions.extend(_resolution(item, scope, window, window_history, target_date) for item in performance)
    resolutions.extend(_schedule_resolutions(history, target_date))
    return tuple(sorted(resolutions, key=lambda item: (item.scope.value, item.window.value, item.feature_id.value)))


def _usable_season(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _target(row: _SourceBoundWarehouseMatch) -> HistoricalAsOfTarget:
    if not isinstance(row, _SourceBoundWarehouseMatch):
        raise HistoricalAsOfError("historical targets require a source-bound warehouse row")
    row.verify_integrity()
    return HistoricalAsOfTarget(
        _token=_TARGET_TOKEN,
        match_key=row["match_key"], match_date=row["match_date"],
        competition_key=row["competition_key"], competition_name=row["competition_name"],
        scope=row["scope"], season=row["season"], stage=row["stage"],
        round_name=row["round_name"], hierarchy_rank=row["hierarchy_rank"],
        hierarchy_tier=row["hierarchy_tier"], home_team=row["home_team"],
        away_team=row["away_team"],
        source_warehouse_sha256=row.source_warehouse_sha256,
        _source_instance_token=row._source_instance_token,
    )


def build_historical_asof_snapshot(
    warehouse_path: Path, target_match_key: str,
) -> HistoricalAsOfFixtureSnapshot:
    registry_sha = validate_historical_feature_registry()
    generation_contract_sha = validate_historical_generation_contract()
    with ReadOnlyHistoricalWarehouse(warehouse_path) as source:
        target = _target(source.target_match(target_match_key))
        _parse_date(target.match_date)
        home_history = _history(
            source, target.scope, target.competition_key,
            target.home_team, target.match_date,
        )
        away_history = _history(
            source, target.scope, target.competition_key,
            target.away_team, target.match_date,
        )
        snapshot = _assemble_snapshot(
            target, home_history, away_history, source, registry_sha,
            generation_contract_sha,
        )
        source.assert_unchanged()
        return snapshot


def _assemble_snapshot(
    target: HistoricalAsOfTarget, home_history: Sequence[TeamMatchProjection],
    away_history: Sequence[TeamMatchProjection], source: ReadOnlyHistoricalWarehouse,
    registry_sha: str, generation_contract_sha: str,
) -> HistoricalAsOfFixtureSnapshot:
    """Internal constructor used by verified file and streaming builders."""
    if registry_sha != validate_historical_feature_registry():
        raise HistoricalAsOfError("historical registry identity changed during construction")
    if generation_contract_sha != validate_historical_generation_contract():
        raise HistoricalAsOfError("historical generation contract changed during construction")
    if not isinstance(target, HistoricalAsOfTarget):
        raise HistoricalAsOfError("canonical assembly requires a source-bound target")
    target.verify_integrity()
    if target.source_warehouse_sha256 != source.sha256:
        raise HistoricalAsOfError("historical target belongs to a different warehouse")
    if target._source_instance_token is not source._source_instance_token:
        raise HistoricalAsOfError("historical target was not issued by the bound warehouse")
    target_date = target.match_date
    _parse_date(target_date)
    home_identity = historical_team_identity(
        target.scope, target.competition_key, target.home_team
    )
    away_identity = historical_team_identity(
        target.scope, target.competition_key, target.away_team
    )
    if home_identity is None or away_identity is None:
        raise HistoricalAsOfError("unusable target team identity")
    for expected, history in ((home_identity, home_history), (away_identity, away_history)):
        for item in history:
            if not isinstance(item, TeamMatchProjection):
                raise HistoricalAsOfError("canonical history requires source-bound projections")
            item.verify_integrity()
            if item.source_warehouse_sha256 != source.sha256:
                raise HistoricalAsOfError("historical projection belongs to a different warehouse")
            if item._source_instance_token is not source._source_instance_token:
                raise HistoricalAsOfError(
                    "historical projection was not issued by the bound warehouse"
                )
        if expected is not None and any(
            historical_team_identity(item.scope, item.competition_key, item.team) != expected
            for item in history
        ):
            raise HistoricalAsOfError("history violates the historical team identity policy")
    if any(item.match_date >= target_date for item in (*home_history, *away_history)):
        raise HistoricalAsOfError("DATE_STRICT history contains target-date or later evidence")
    home = _team_resolutions(home_history, target_date, target.season, HistoricalTeamScope.HOME_ONLY)
    away = _team_resolutions(away_history, target_date, target.season, HistoricalTeamScope.AWAY_ONLY)
    all_resolutions = home + away
    coverage = HistoricalCoverage(
        total=len(all_resolutions),
        available=sum(item.status is HistoricalFeatureStatus.AVAILABLE for item in all_resolutions),
        missing=sum(item.status is HistoricalFeatureStatus.MISSING for item in all_resolutions),
        blocked=sum(item.status is HistoricalFeatureStatus.BLOCKED for item in all_resolutions),
    )
    return HistoricalAsOfFixtureSnapshot(
        _token=_SNAPSHOT_TOKEN,
        target_match_key=target.match_key, target_match_date=target_date,
        target_competition_key=target.competition_key, target_scope=target.scope,
        target_competition_name=target.competition_name, target_season=target.season,
        target_stage=target.stage, target_round_name=target.round_name,
        target_hierarchy_rank=target.hierarchy_rank, target_hierarchy_tier=target.hierarchy_tier,
        target_home_team=target.home_team,
        target_away_team=target.away_team, temporal_policy_id=TEMPORAL_POLICY_ID,
        team_identity_policy_id=HISTORICAL_TEAM_IDENTITY_POLICY_ID,
        completion_policy_id=HISTORICAL_COMPLETION_POLICY_ID,
        advanced_period_safety_policy_id=HISTORICAL_ADVANCED_PERIOD_SAFETY_POLICY_ID,
        source_warehouse_sha256=source.sha256, source_warehouse_schema_version=source.schema_version,
        source_schema_sql_sha256=source.schema_sql_sha256,
        generation_schema_version=HISTORICAL_ASOF_SCHEMA_VERSION,
        generation_contract_version=HISTORICAL_GENERATION_CONTRACT_VERSION,
        generation_contract_sha256=generation_contract_sha,
        feature_registry_version=HISTORICAL_FEATURE_REGISTRY_VERSION,
        feature_registry_sha256=registry_sha, home_resolutions=home, away_resolutions=away,
        coverage=coverage, authority_flags=tuple(sorted(AUTHORITY_FLAGS.items())),
    )


def canonical_historical_asof_bytes(snapshot: HistoricalAsOfFixtureSnapshot) -> bytes:
    return snapshot.canonical_bytes


def find_resolution(
    resolutions: Sequence[HistoricalFeatureResolution], feature_id: HistoricalFeatureId,
    scope: HistoricalTeamScope, window: HistoricalWindow,
) -> HistoricalFeatureResolution:
    matches = [item for item in resolutions if item.feature_id is feature_id and item.scope is scope and item.window is window]
    if len(matches) != 1:
        raise HistoricalAsOfError("historical feature resolution is not unique")
    return matches[0]
