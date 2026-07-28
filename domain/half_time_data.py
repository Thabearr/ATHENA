"""Typed, auditable half-time observations and research-readiness reporting."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable, Optional, Tuple


class HalfTimeValidationStatus(str, Enum):
    VALID = "VALID"
    MISSING = "MISSING"
    INVALID = "INVALID"


class ScoreProvenance(str, Enum):
    OBSERVED = "OBSERVED"
    MISSING = "MISSING"
    INFERRED = "INFERRED"
    FABRICATED = "FABRICATED"


class ResearchReadiness(str, Enum):
    READY_FOR_RESEARCH = "READY_FOR_RESEARCH"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    DATA_INVALID = "DATA_INVALID"
    NO_DATA = "NO_DATA"


@dataclass(frozen=True)
class HalfTimeObservation:
    fixture_identity: str
    home_team: str
    away_team: str
    kickoff_time: Optional[datetime]
    full_time_home_goals: Optional[int]
    full_time_away_goals: Optional[int]
    half_time_home_goals: Optional[int]
    half_time_away_goals: Optional[int]
    source: str
    observed_at: Optional[datetime] = None
    source_fixture_id: Optional[str] = None
    half_time_score_provenance: ScoreProvenance = ScoreProvenance.MISSING
    league: Optional[str] = None
    season: Optional[str] = None
    validation_status: HalfTimeValidationStatus = field(init=False)
    rejection_reasons: Tuple[str, ...] = field(init=False)

    def __post_init__(self) -> None:
        reasons = []

        fixture_identity = str(self.fixture_identity or "").strip()
        source = str(self.source or "").strip()
        object.__setattr__(self, "fixture_identity", fixture_identity)
        object.__setattr__(self, "source", source)

        if not fixture_identity:
            reasons.append("fixture identity is required")
        if not source:
            reasons.append("source is required")

        provenance = self.half_time_score_provenance
        if not isinstance(provenance, ScoreProvenance):
            try:
                provenance = ScoreProvenance(str(provenance).strip().upper())
                object.__setattr__(
                    self,
                    "half_time_score_provenance",
                    provenance,
                )
            except ValueError:
                reasons.append("half-time score provenance is invalid")
                provenance = None

        score_fields = (
            ("full-time home goals", self.full_time_home_goals, True),
            ("full-time away goals", self.full_time_away_goals, True),
            ("half-time home goals", self.half_time_home_goals, False),
            ("half-time away goals", self.half_time_away_goals, False),
        )
        valid_scores = {}
        for label, value, required in score_fields:
            if value is None:
                if required:
                    reasons.append(f"{label} are required")
                valid_scores[label] = False
                continue
            if isinstance(value, bool):
                reasons.append(f"{label} must not be boolean")
                valid_scores[label] = False
                continue
            if not isinstance(value, int):
                reasons.append(f"{label} must be an integer")
                valid_scores[label] = False
                continue
            if value < 0:
                reasons.append(f"{label} must be non-negative")
                valid_scores[label] = False
                continue
            valid_scores[label] = True

        home_half_missing = self.half_time_home_goals is None
        away_half_missing = self.half_time_away_goals is None
        half_time_missing = home_half_missing and away_half_missing

        if home_half_missing != away_half_missing:
            reasons.append("half-time scores must be both present or both missing")

        if provenance in {
            ScoreProvenance.INFERRED,
            ScoreProvenance.FABRICATED,
        }:
            reasons.append(
                "inferred or fabricated half-time scores are not accepted"
            )
        elif half_time_missing and provenance == ScoreProvenance.OBSERVED:
            reasons.append(
                "observed half-time provenance requires both half-time scores"
            )
        elif not half_time_missing and provenance != ScoreProvenance.OBSERVED:
            reasons.append(
                "present half-time scores must be explicitly observed"
            )

        if (
            valid_scores.get("half-time home goals")
            and valid_scores.get("full-time home goals")
            and self.half_time_home_goals > self.full_time_home_goals
        ):
            reasons.append(
                "half-time home goals cannot exceed full-time home goals"
            )
        if (
            valid_scores.get("half-time away goals")
            and valid_scores.get("full-time away goals")
            and self.half_time_away_goals > self.full_time_away_goals
        ):
            reasons.append(
                "half-time away goals cannot exceed full-time away goals"
            )

        if reasons:
            status = HalfTimeValidationStatus.INVALID
        elif half_time_missing:
            status = HalfTimeValidationStatus.MISSING
        else:
            status = HalfTimeValidationStatus.VALID

        object.__setattr__(self, "validation_status", status)
        object.__setattr__(self, "rejection_reasons", tuple(reasons))

    def to_dict(self) -> dict:
        return {
            "fixture_identity": self.fixture_identity,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "kickoff_time": (
                self.kickoff_time.isoformat() if self.kickoff_time else None
            ),
            "full_time_home_goals": self.full_time_home_goals,
            "full_time_away_goals": self.full_time_away_goals,
            "half_time_home_goals": self.half_time_home_goals,
            "half_time_away_goals": self.half_time_away_goals,
            "source": self.source,
            "observed_at": (
                self.observed_at.isoformat() if self.observed_at else None
            ),
            "source_fixture_id": self.source_fixture_id,
            "half_time_score_provenance": (
                self.half_time_score_provenance.value
                if isinstance(
                    self.half_time_score_provenance,
                    ScoreProvenance,
                )
                else str(self.half_time_score_provenance)
            ),
            "league": self.league,
            "season": self.season,
            "validation_status": self.validation_status.value,
            "rejection_reasons": list(self.rejection_reasons),
        }


@dataclass(frozen=True)
class ReadinessThresholds:
    minimum_valid_observations: int = 1000
    minimum_overall_coverage: float = 0.80
    minimum_league_coverage: float = 0.60
    maximum_invalid_record_percentage: float = 0.02

    def __post_init__(self) -> None:
        if (
            isinstance(self.minimum_valid_observations, bool)
            or not isinstance(self.minimum_valid_observations, int)
            or self.minimum_valid_observations < 1
        ):
            raise ValueError(
                "minimum_valid_observations must be a positive integer"
            )
        for name in (
            "minimum_overall_coverage",
            "minimum_league_coverage",
            "maximum_invalid_record_percentage",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not 0.0 <= float(value) <= 1.0
            ):
                raise ValueError(f"{name} must be between 0 and 1")

    def to_dict(self) -> dict:
        return {
            "minimum_valid_observations": self.minimum_valid_observations,
            "minimum_overall_coverage": self.minimum_overall_coverage,
            "minimum_league_coverage": self.minimum_league_coverage,
            "maximum_invalid_record_percentage": (
                self.maximum_invalid_record_percentage
            ),
        }


@dataclass(frozen=True)
class CoverageBucket:
    total: int
    valid: int
    missing: int
    invalid: int

    @property
    def coverage_percentage(self) -> float:
        return round((self.valid / self.total) * 100.0, 6) if self.total else 0.0

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "valid": self.valid,
            "missing": self.missing,
            "invalid": self.invalid,
            "coverage_percentage": self.coverage_percentage,
        }


@dataclass(frozen=True)
class HalfTimeCoverageReport:
    total_historical_fixtures_inspected: int
    fixtures_with_valid_half_time_scores: int
    fixtures_missing_half_time_scores: int
    invalid_observations: int
    coverage_percentage: float
    coverage_by_league: dict
    coverage_by_season: dict
    earliest_valid_observation: Optional[datetime]
    latest_valid_observation: Optional[datetime]
    source_breakdown: dict
    readiness: ResearchReadiness
    readiness_reasons: Tuple[str, ...]
    thresholds: ReadinessThresholds

    def to_dict(self) -> dict:
        return {
            "total_historical_fixtures_inspected": (
                self.total_historical_fixtures_inspected
            ),
            "fixtures_with_valid_half_time_scores": (
                self.fixtures_with_valid_half_time_scores
            ),
            "fixtures_missing_half_time_scores": (
                self.fixtures_missing_half_time_scores
            ),
            "invalid_observations": self.invalid_observations,
            "coverage_percentage": self.coverage_percentage,
            "coverage_by_league": self.coverage_by_league,
            "coverage_by_season": self.coverage_by_season,
            "earliest_valid_observation": (
                self.earliest_valid_observation.isoformat()
                if self.earliest_valid_observation
                else None
            ),
            "latest_valid_observation": (
                self.latest_valid_observation.isoformat()
                if self.latest_valid_observation
                else None
            ),
            "source_breakdown": self.source_breakdown,
            "readiness": self.readiness.value,
            "readiness_reasons": list(self.readiness_reasons),
            "thresholds": self.thresholds.to_dict(),
        }


def _datetime_order_value(value: Optional[datetime]) -> float:
    if value is None:
        return float("-inf")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def _observation_order_key(observation: HalfTimeObservation) -> tuple:
    status_rank = {
        HalfTimeValidationStatus.INVALID: 0,
        HalfTimeValidationStatus.MISSING: 1,
        HalfTimeValidationStatus.VALID: 2,
    }[observation.validation_status]
    stable_payload = json.dumps(
        observation.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        _datetime_order_value(observation.observed_at),
        status_rank,
        stable_payload,
    )


def deduplicate_observations(
    observations: Iterable[HalfTimeObservation],
) -> Tuple[HalfTimeObservation, ...]:
    """Select one observation per fixture/source without input-order effects."""
    selected = {}
    for observation in observations:
        if not isinstance(observation, HalfTimeObservation):
            raise TypeError("observations must contain HalfTimeObservation values")
        key = (observation.fixture_identity, observation.source)
        current = selected.get(key)
        if current is None or _observation_order_key(
            observation
        ) > _observation_order_key(current):
            selected[key] = observation
    return tuple(selected[key] for key in sorted(selected))


def _select_one_observation_per_fixture(
    observations: Iterable[HalfTimeObservation],
) -> Tuple[HalfTimeObservation, ...]:
    selected = {}
    for observation in deduplicate_observations(observations):
        current = selected.get(observation.fixture_identity)
        if current is None or _observation_order_key(
            observation
        ) > _observation_order_key(current):
            selected[observation.fixture_identity] = observation
    return tuple(selected[key] for key in sorted(selected))


def _bucket(observations: Iterable[HalfTimeObservation]) -> CoverageBucket:
    values = tuple(observations)
    return CoverageBucket(
        total=len(values),
        valid=sum(
            item.validation_status == HalfTimeValidationStatus.VALID
            for item in values
        ),
        missing=sum(
            item.validation_status == HalfTimeValidationStatus.MISSING
            for item in values
        ),
        invalid=sum(
            item.validation_status == HalfTimeValidationStatus.INVALID
            for item in values
        ),
    )


def _grouped_coverage(
    observations: Iterable[HalfTimeObservation],
    field_name: str,
) -> dict:
    groups = {}
    for observation in observations:
        key = getattr(observation, field_name) or "UNKNOWN"
        groups.setdefault(str(key), []).append(observation)
    return {
        key: _bucket(groups[key]).to_dict()
        for key in sorted(groups)
    }


def audit_half_time_coverage(
    observations: Iterable[HalfTimeObservation],
    thresholds: ReadinessThresholds = ReadinessThresholds(),
) -> HalfTimeCoverageReport:
    selected = _select_one_observation_per_fixture(observations)
    overall = _bucket(selected)
    coverage_ratio = overall.valid / overall.total if overall.total else 0.0
    invalid_ratio = overall.invalid / overall.total if overall.total else 0.0

    coverage_by_league = _grouped_coverage(selected, "league")
    coverage_by_season = _grouped_coverage(selected, "season")
    source_breakdown = _grouped_coverage(selected, "source")

    valid_observed_times = sorted(
        (
            observation.observed_at
            for observation in selected
            if (
                observation.validation_status
                == HalfTimeValidationStatus.VALID
                and observation.observed_at is not None
            )
        ),
        key=_datetime_order_value,
    )

    readiness_reasons = []
    if overall.total == 0:
        readiness = ResearchReadiness.NO_DATA
        readiness_reasons.append("No historical fixture observations exist.")
    elif invalid_ratio > thresholds.maximum_invalid_record_percentage:
        readiness = ResearchReadiness.DATA_INVALID
        readiness_reasons.append(
            "Invalid-record percentage exceeds the configured maximum."
        )
    else:
        if overall.valid < thresholds.minimum_valid_observations:
            readiness_reasons.append(
                "Valid observation count is below the configured minimum."
            )
        if coverage_ratio < thresholds.minimum_overall_coverage:
            readiness_reasons.append(
                "Overall half-time coverage is below the configured minimum."
            )
        below_league_threshold = [
            league
            for league, bucket in coverage_by_league.items()
            if (
                bucket["coverage_percentage"] / 100.0
                < thresholds.minimum_league_coverage
            )
        ]
        if below_league_threshold:
            readiness_reasons.append(
                "League-level coverage is below the configured minimum for: "
                + ", ".join(below_league_threshold)
                + "."
            )
        readiness = (
            ResearchReadiness.INSUFFICIENT_DATA
            if readiness_reasons
            else ResearchReadiness.READY_FOR_RESEARCH
        )

    return HalfTimeCoverageReport(
        total_historical_fixtures_inspected=overall.total,
        fixtures_with_valid_half_time_scores=overall.valid,
        fixtures_missing_half_time_scores=overall.missing,
        invalid_observations=overall.invalid,
        coverage_percentage=overall.coverage_percentage,
        coverage_by_league=coverage_by_league,
        coverage_by_season=coverage_by_season,
        earliest_valid_observation=(
            valid_observed_times[0] if valid_observed_times else None
        ),
        latest_valid_observation=(
            valid_observed_times[-1] if valid_observed_times else None
        ),
        source_breakdown=source_breakdown,
        readiness=readiness,
        readiness_reasons=tuple(readiness_reasons),
        thresholds=thresholds,
    )


__all__ = [
    "CoverageBucket",
    "HalfTimeCoverageReport",
    "HalfTimeObservation",
    "HalfTimeValidationStatus",
    "ReadinessThresholds",
    "ResearchReadiness",
    "ScoreProvenance",
    "audit_half_time_coverage",
    "deduplicate_observations",
]
