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
WAREHOUSE_SCHEMA_VERSION = "1"


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


_FT = ("goals_for", "goals_against")
HISTORICAL_FEATURE_REGISTRY: tuple[HistoricalFeatureDefinition, ...] = (
    *(_definition(fid, HistoricalFeatureFamily.FORM_RESULTS, _FT) for fid in (
        HistoricalFeatureId.POINTS_PER_MATCH, HistoricalFeatureId.WIN_RATE,
        HistoricalFeatureId.DRAW_RATE, HistoricalFeatureId.LOSS_RATE,
        HistoricalFeatureId.GOALS_FOR_PER_MATCH,
        HistoricalFeatureId.GOALS_AGAINST_PER_MATCH,
        HistoricalFeatureId.GOAL_DIFFERENCE_PER_MATCH,
    )),
    *(_definition(fid, HistoricalFeatureFamily.EVENT_ENVIRONMENT, _FT) for fid in (
        HistoricalFeatureId.TOTAL_GOALS_PER_MATCH,
        HistoricalFeatureId.CLEAN_SHEET_RATE,
        HistoricalFeatureId.FAILED_TO_SCORE_RATE,
        HistoricalFeatureId.BTTS_RATE,
        HistoricalFeatureId.OVER_1_5_RATE,
        HistoricalFeatureId.OVER_2_5_RATE,
    )),
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
    {1: "f8014761d168ade0fe95142c3e1358ba4b8d2e065880d37a2162887099269b51"}
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


@dataclass(frozen=True)
class TeamMatchProjection:
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
    field_source_keys: tuple[tuple[str, str], ...]
    conflict_fields: tuple[str, ...]
    projection_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {field.name: getattr(self, field.name) for field in fields(self)} | {
            "field_source_keys": [list(item) for item in self.field_source_keys],
            "conflict_fields": list(self.conflict_fields),
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
    oldest_included_date: str | None
    newest_included_date: str | None
    algorithm_id: str
    required_primitives: tuple[str, ...]
    contributing_projection_sha256: str | None
    contributing_match_keys: tuple[str, ...]
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
        if self.missing_field_count != self.effective_match_sample - self.valid_field_sample:
            raise HistoricalAsOfError("historical feature sample counts do not reconcile")

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm_id": self.algorithm_id,
            "blocker": self.blocker.value if self.blocker else None,
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
    source_warehouse_sha256: str
    source_warehouse_schema_version: str
    source_schema_sql_sha256: str
    generation_schema_version: int
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
    "warehouse_match_sources", "warehouse_conflicts",
})


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ReadOnlyHistoricalWarehouse:
    """Stable, SHA-bound, query-only view of one warehouse image."""

    def __init__(self, path: Path, *, schema_sql_path: Path | None = None) -> None:
        self.path = Path(path).resolve()
        if not self.path.is_file():
            raise HistoricalAsOfError(f"historical warehouse does not exist: {self.path}")
        for suffix in ("-wal", "-journal"):
            companion = Path(str(self.path) + suffix)
            if companion.exists() and companion.stat().st_size:
                raise HistoricalAsOfError(f"unsafe active SQLite companion file: {companion.name}")
        self._before_stat = self.path.stat()
        self.sha256 = file_sha256(self.path)
        self.connection = sqlite3.connect(f"{self.path.as_uri()}?mode=ro", uri=True)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA query_only = ON")
        self._validate_schema()
        schema_path = schema_sql_path or Path(__file__).resolve().parents[1] / "database" / "historical_warehouse_schema.sql"
        if not schema_path.is_file():
            self.close()
            raise HistoricalAsOfError("historical warehouse schema SQL is unavailable")
        self.schema_sql_sha256 = file_sha256(schema_path)

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
        after = self.path.stat()
        if (after.st_size, after.st_mtime_ns) != (self._before_stat.st_size, self._before_stat.st_mtime_ns):
            raise HistoricalAsOfError("historical warehouse changed during construction")
        if file_sha256(self.path) != self.sha256:
            raise HistoricalAsOfError("historical warehouse bytes changed during construction")

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
    return value


def _projection(row: sqlite3.Row, team: str, provenance: Mapping[str, str], conflicts: Iterable[str]) -> TeamMatchProjection:
    home = team == row["home_team"]
    if not home and team != row["away_team"]:
        raise HistoricalAsOfError("team is not present in prior match")
    side, other = ("home", "away") if home else ("away", "home")
    values: dict[str, Any] = {
        "match_key": row["match_key"], "match_date": row["match_date"],
        "competition_key": row["competition_key"], "scope": row["scope"], "season": row["season"],
        "team": team, "opponent": row[f"{other}_team"], "side": side.upper(),
        "goals_for": _safe_number(row[f"{side}_score_ft"], f"{side}_score_ft"),
        "goals_against": _safe_number(row[f"{other}_score_ft"], f"{other}_score_ft"),
        "first_half_goals_for": _safe_number(row[f"{side}_score_ht"], f"{side}_score_ht"),
        "first_half_goals_against": _safe_number(row[f"{other}_score_ht"], f"{other}_score_ht"),
        "xg_for": _safe_number(row[f"{side}_xg"], f"{side}_xg"),
        "xg_against": _safe_number(row[f"{other}_xg"], f"{other}_xg"),
        "shots_for": _safe_number(row[f"{side}_shots"], f"{side}_shots"),
        "shots_against": _safe_number(row[f"{other}_shots"], f"{other}_shots"),
        "shots_on_target_for": _safe_number(row[f"{side}_shots_on_target"], f"{side}_shots_on_target"),
        "shots_on_target_against": _safe_number(row[f"{other}_shots_on_target"], f"{other}_shots_on_target"),
        "possession_for": _safe_number(row[f"{side}_possession"], f"{side}_possession"),
        "possession_against": _safe_number(row[f"{other}_possession"], f"{other}_possession"),
        "corners_for": _safe_number(row[f"{side}_corners"], f"{side}_corners"),
        "corners_against": _safe_number(row[f"{other}_corners"], f"{other}_corners"),
        "fouls_for": _safe_number(row[f"{side}_fouls"], f"{side}_fouls"),
        "fouls_against": _safe_number(row[f"{other}_fouls"], f"{other}_fouls"),
        "yellows_for": _safe_number(row[f"{side}_yellows"], f"{side}_yellows"),
        "yellows_against": _safe_number(row[f"{other}_yellows"], f"{other}_yellows"),
        "reds_for": _safe_number(row[f"{side}_reds"], f"{side}_reds"),
        "reds_against": _safe_number(row[f"{other}_reds"], f"{other}_reds"),
        "field_source_keys": tuple(sorted(provenance.items())),
        "conflict_fields": tuple(sorted(set(conflicts))),
    }
    identity = {key: value for key, value in values.items() if key not in {"projection_sha256"}}
    identity["field_source_keys"] = [list(item) for item in values["field_source_keys"]]
    identity["conflict_fields"] = list(values["conflict_fields"])
    values["projection_sha256"] = hashlib.sha256(_canonical_bytes(identity)).hexdigest()
    return TeamMatchProjection(**values)


_MATCH_COLUMNS = """m.match_key,m.competition_key,m.scope,m.season,m.match_date,
 m.home_team,m.away_team,m.home_score_ft,m.away_score_ft,m.home_score_ht,m.away_score_ht,
 m.home_xg,m.away_xg,m.home_possession,m.away_possession,m.home_shots,m.away_shots,
 m.home_shots_on_target,m.away_shots_on_target,m.home_corners,m.away_corners,
 m.home_fouls,m.away_fouls,m.home_yellows,m.away_yellows,m.home_reds,m.away_reds"""


def _history(connection: sqlite3.Connection, team: str, target_date: str) -> tuple[TeamMatchProjection, ...]:
    rows = connection.execute(
        f"SELECT {_MATCH_COLUMNS} FROM warehouse_matches m "
        "WHERE m.match_date < ? AND (m.home_team=? OR m.away_team=?) "
        "ORDER BY m.match_date,m.match_key", (target_date, team, team),
    ).fetchall()
    if not rows:
        return ()
    provenance_by_match: dict[str, dict[str, str]] = {}
    for item in connection.execute(
        "SELECT p.match_key,p.field_name,p.source_key FROM warehouse_field_provenance p "
        "JOIN warehouse_matches m ON m.match_key=p.match_key "
        "WHERE m.match_date < ? AND (m.home_team=? OR m.away_team=?)",
        (target_date, team, team),
    ):
        provenance_by_match.setdefault(item["match_key"], {})[item["field_name"]] = item["source_key"]
    conflicts_by_match: dict[str, list[str]] = {}
    for item in connection.execute(
        "SELECT c.match_key,c.field_name FROM warehouse_conflicts c "
        "JOIN warehouse_matches m ON m.match_key=c.match_key "
        "WHERE m.match_date < ? AND (m.home_team=? OR m.away_team=?)",
        (target_date, team, team),
    ):
        conflicts_by_match.setdefault(item["match_key"], []).append(item["field_name"])
    return tuple(_projection(
        row, team, provenance_by_match.get(row["match_key"], {}), conflicts_by_match.get(row["match_key"], ()),
    ) for row in rows)


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
    valid = [item for item in selected if all(getattr(item, name) is not None for name in definition.required_primitives)]
    dates = [item.match_date for item in (valid or selected)]
    provenance = _relevant_provenance(valid, definition.required_primitives)
    relevant_fields = {field_name for _, field_name, _ in provenance}
    common = dict(
        feature_id=definition.feature_id, scope=scope, window=window,
        requested_window_size=requested, effective_match_sample=len(selected),
        valid_field_sample=len(valid), missing_field_count=len(selected) - len(valid),
        oldest_included_date=min(dates) if dates else None,
        newest_included_date=max(dates) if dates else None,
        algorithm_id=definition.algorithm_id, required_primitives=definition.required_primitives,
        contributing_match_keys=tuple(item.match_key for item in valid),
        source_keys=tuple(sorted({source for _, _, source in provenance})),
        source_field_provenance=provenance,
        conflict_count=sum(sum(field in relevant_fields for field in item.conflict_fields) for item in valid),
    )
    if not valid:
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
    for feature_id, days in (
        (HistoricalFeatureId.DAYS_SINCE_LAST_MATCH, None),
        (HistoricalFeatureId.FIXTURES_LAST_7_DAYS, 7),
        (HistoricalFeatureId.FIXTURES_LAST_14_DAYS, 14),
        (HistoricalFeatureId.FIXTURES_LAST_28_DAYS, 28),
    ):
        selected = tuple(history[-1:]) if days is None else tuple(
            item for item in history if 0 < (target - _parse_date(item.match_date)).days <= days
        )
        definition = definitions[feature_id]
        all_history_exists = bool(history)
        evidence_items = selected or tuple(history[-1:])
        provenance = _relevant_provenance(evidence_items, definition.required_primitives) if all_history_exists else ()
        effective = len(selected)
        common = dict(
            feature_id=feature_id, scope=HistoricalTeamScope.OVERALL, window=HistoricalWindow.AS_OF,
            requested_window_size=None, effective_match_sample=effective,
            valid_field_sample=effective if all_history_exists else 0, missing_field_count=0,
            oldest_included_date=min((x.match_date for x in selected), default=None),
            newest_included_date=max((x.match_date for x in selected), default=None),
            algorithm_id=definition.algorithm_id, required_primitives=definition.required_primitives,
            contributing_match_keys=tuple(item.match_key for item in evidence_items) if all_history_exists else (),
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
        value = (target - _parse_date(history[-1].match_date)).days if days is None else effective
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
            window_history = scoped if window is not HistoricalWindow.SEASON_TO_DATE else tuple(
                item for item in scoped if item.season == target_season
            )
            resolutions.extend(_resolution(item, scope, window, window_history, target_date) for item in performance)
    resolutions.extend(_schedule_resolutions(history, target_date))
    return tuple(sorted(resolutions, key=lambda item: (item.scope.value, item.window.value, item.feature_id.value)))


def build_historical_asof_snapshot(
    warehouse_path: Path, target_match_key: str, *, schema_sql_path: Path | None = None,
) -> HistoricalAsOfFixtureSnapshot:
    registry_sha = validate_historical_feature_registry()
    with ReadOnlyHistoricalWarehouse(warehouse_path, schema_sql_path=schema_sql_path) as source:
        target = source.connection.execute(
            "SELECT match_key,match_date,competition_key,competition_name,scope,season,stage,round_name,"
            "hierarchy_rank,hierarchy_tier,home_team,away_team "
            "FROM warehouse_match_flat WHERE match_key=?", (target_match_key,),
        ).fetchone()
        if target is None:
            raise HistoricalAsOfError(f"unknown target match_key: {target_match_key}")
        _parse_date(target["match_date"])
        home_history = _history(source.connection, target["home_team"], target["match_date"])
        away_history = _history(source.connection, target["away_team"], target["match_date"])
        snapshot = _assemble_snapshot(target, home_history, away_history, source, registry_sha)
        source.assert_unchanged()
        return snapshot


def _assemble_snapshot(
    target: Mapping[str, Any], home_history: Sequence[TeamMatchProjection],
    away_history: Sequence[TeamMatchProjection], source: ReadOnlyHistoricalWarehouse,
    registry_sha: str,
) -> HistoricalAsOfFixtureSnapshot:
    """Internal constructor used by verified file and streaming builders."""
    if registry_sha != validate_historical_feature_registry():
        raise HistoricalAsOfError("historical registry identity changed during construction")
    target_date = target["match_date"]
    _parse_date(target_date)
    if any(item.match_date >= target_date for item in (*home_history, *away_history)):
        raise HistoricalAsOfError("DATE_STRICT history contains target-date or later evidence")
    home = _team_resolutions(home_history, target_date, target["season"], HistoricalTeamScope.HOME_ONLY)
    away = _team_resolutions(away_history, target_date, target["season"], HistoricalTeamScope.AWAY_ONLY)
    all_resolutions = home + away
    coverage = HistoricalCoverage(
        total=len(all_resolutions),
        available=sum(item.status is HistoricalFeatureStatus.AVAILABLE for item in all_resolutions),
        missing=sum(item.status is HistoricalFeatureStatus.MISSING for item in all_resolutions),
        blocked=sum(item.status is HistoricalFeatureStatus.BLOCKED for item in all_resolutions),
    )
    return HistoricalAsOfFixtureSnapshot(
        _token=_SNAPSHOT_TOKEN,
        target_match_key=target["match_key"], target_match_date=target_date,
        target_competition_key=target["competition_key"], target_scope=target["scope"],
        target_competition_name=target["competition_name"], target_season=target["season"],
        target_stage=target["stage"], target_round_name=target["round_name"],
        target_hierarchy_rank=target["hierarchy_rank"], target_hierarchy_tier=target["hierarchy_tier"],
        target_home_team=target["home_team"],
        target_away_team=target["away_team"], temporal_policy_id=TEMPORAL_POLICY_ID,
        source_warehouse_sha256=source.sha256, source_warehouse_schema_version=source.schema_version,
        source_schema_sql_sha256=source.schema_sql_sha256,
        generation_schema_version=HISTORICAL_ASOF_SCHEMA_VERSION,
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
